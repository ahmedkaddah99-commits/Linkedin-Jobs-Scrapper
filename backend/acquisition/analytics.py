"""Read-only, bounded analytics for the acquisition operations dashboard.

The analytics contract deliberately uses the existing acquisition tables as its
source of truth.  It never starts providers, mutates catalog state, or treats a
bounded source snapshot as an estimate of the external job market.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.database.connection import database_session


ANALYTICS_SCHEMA_VERSION = "acquisition_analytics_v1"
ACQUISITION_COVERAGE_SCHEMA_VERSION = "acquisition_coverage_v1"
ANALYTICS_MAX_DAYS = 30
ANALYTICS_RANGES = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}
_UTC = timezone.utc
_MISSING = object()
_WORKER_HEARTBEAT_STALE_SECONDS = 120
_TASK_STUCK_SECONDS = 15 * 60

# These are the frozen input-contract facts from BASELINE_AND_INPUT_CONTRACT.md.
# They are deliberately not calculated from application rows: application rows
# are a runtime subset and cannot replace the source master denominator.
_MASTER_INPUT_BASELINE = {
    "source_document": "BASELINE_AND_INPUT_CONTRACT.md",
    "input_path": "Company-Urls/Master-Company-Url/cleaned/Master-Company-Url-canonical_cleaned_linkedin_ids.csv",
    "input_sha256": "7f416ec6ebbcb936a42061ef0adaa07e4a6c04d2959d0eb579779126682440d9",
    "master_rows": 17601,
    "existing_master_ids": 7513,
    "missing_master_ids": 10088,
    "unique_linkedin_organization_ids": 11907,
    "conflicting_organizations": 37,
}


@dataclass(frozen=True, slots=True)
class AnalyticsWindow:
    range_key: str
    timezone_name: str
    start: datetime
    end: datetime

    @property
    def start_iso(self) -> str:
        return self.start.isoformat()

    @property
    def end_iso(self) -> str:
        return self.end.isoformat()

    @property
    def duration_seconds(self) -> int:
        return max(0, int((self.end - self.start).total_seconds()))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return default
    return parsed


def _utc_iso(value: datetime) -> str:
    return value.astimezone(_UTC).isoformat()


def _parse_datetime(value: str, *, timezone_value: ZoneInfo, name: str) -> datetime:
    raw = _text(value)
    if not raw:
        raise ValueError(f"{name} is required when using a custom analytics window.")
    normalized = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone_value)
    return parsed.astimezone(_UTC)


def parse_analytics_window(
    *,
    range_key: str = "7d",
    start: str = "",
    end: str = "",
    timezone_name: str = "UTC",
    now: datetime | None = None,
) -> AnalyticsWindow:
    """Validate and normalize a bounded period to UTC, preserving its TZ name."""

    requested_timezone = _text(timezone_name) or "UTC"
    try:
        local_zone = ZoneInfo(requested_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be a supported IANA timezone.") from exc

    normalized_range = _text(range_key).casefold() or "7d"
    if start or end:
        start_utc = _parse_datetime(start, timezone_value=local_zone, name="start")
        end_utc = _parse_datetime(end, timezone_value=local_zone, name="end")
        normalized_range = "custom"
    else:
        if normalized_range not in ANALYTICS_RANGES:
            raise ValueError("range must be one of: 24h, 7d, 30d.")
        current = (now or datetime.now(_UTC)).astimezone(local_zone)
        end_utc = current.astimezone(_UTC)
        start_utc = (current - ANALYTICS_RANGES[normalized_range]).astimezone(_UTC)

    if end_utc <= start_utc:
        raise ValueError("analytics end must be after start.")
    if end_utc - start_utc > timedelta(days=ANALYTICS_MAX_DAYS):
        raise ValueError("analytics windows cannot exceed 30 days.")
    return AnalyticsWindow(
        range_key=normalized_range,
        timezone_name=requested_timezone,
        start=start_utc,
        end=end_utc,
    )


def _period(column: str, window: AnalyticsWindow) -> tuple[str, tuple[str, str]]:
    # Stored timestamps are UTC ISO-8601 values. Plain comparisons preserve the
    # timestamp indexes; callers receive start-inclusive/end-exclusive bounds.
    return f"{column} >= ? AND {column} < ?", (window.start_iso, window.end_iso)


def _count(connection, table: str, column: str, window: AnalyticsWindow, extra: str = "", params: tuple[Any, ...] = ()) -> int:
    predicate, bounds = _period(column, window)
    row = connection.execute(
        f"SELECT COUNT(*) AS count FROM {table} WHERE {predicate}{extra}",  # noqa: S608 - table/column names are internal constants
        (*bounds, *params),
    ).fetchone()
    return int(row["count"] or 0) if row is not None else 0


def _group_counts(connection, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [{key: row[key] for key in row.keys()} for row in connection.execute(sql, params).fetchall()]


def _status_counts(connection, table: str, date_column: str, window: AnalyticsWindow) -> dict[str, int]:
    predicate, bounds = _period(date_column, window)
    rows = connection.execute(
        f"SELECT LOWER(status) AS status, COUNT(*) AS count FROM {table} WHERE {predicate} GROUP BY LOWER(status)",  # noqa: S608 - internal table/column names
        bounds,
    ).fetchall()
    result = {key: 0 for key in ("successful", "partial", "failed", "paused", "running")}
    for row in rows:
        status = _text(row["status"]).casefold()
        if status in {"completed", "complete", "succeeded", "success", "valid", "published"}:
            bucket = "successful"
        elif status in {"partial", "partially_completed", "needs_attention", "incomplete", "interrupted"}:
            bucket = "partial"
        elif status in {"failed", "error", "permanent_error"}:
            bucket = "failed"
        elif status in {"paused", "blocked", "cancelled", "cancel_requested"}:
            bucket = "paused"
        else:
            bucket = "running"
        result[bucket] += int(row["count"] or 0)
    return result


def _row_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()} if row is not None else {}


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _source_performance(connection, window: AnalyticsWindow) -> list[dict[str, Any]]:
    predicate, bounds = _period("a.started_at", window)
    attempt_rows = _group_counts(
        connection,
        f"""
        SELECT target_id, LOWER(status) AS status, COUNT(*) AS count
        FROM acquisition_target_attempts a
        WHERE {predicate}
        GROUP BY target_id, LOWER(status)
        """,
        bounds,
    )
    attempts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in attempt_rows:
        attempts[_text(row["target_id"])][_text(row["status"]).casefold()] += int(row["count"] or 0)

    request_predicate, request_bounds = _period("r.started_at", window)
    request_rows = _group_counts(
        connection,
        f"""
        SELECT target_id, COUNT(*) AS requests,
               COALESCE(SUM(credits_actual), 0) AS credits_actual,
               COALESCE(SUM(credits_estimated), 0) AS credits_estimated,
               AVG(NULLIF(latency_ms, 0)) AS duration_ms,
               MAX(CASE WHEN LOWER(status) IN ('completed', 'success', 'succeeded') THEN completed_at ELSE '' END) AS last_success_at,
               MAX(started_at) AS last_attempt_at
        FROM acquisition_requests r
        WHERE {request_predicate}
        GROUP BY target_id
        """,
        request_bounds,
    )
    requests = {_text(row["target_id"]): row for row in request_rows}

    observation_predicate, observation_bounds = _period("o.observed_at", window)
    observation_rows = _group_counts(
        connection,
        f"""
        SELECT o.target_id,
               COUNT(DISTINCT o.observation_id) AS observations,
               COUNT(DISTINCT CASE WHEN j.created_at >= ? AND j.created_at < ? THEN j.canonical_job_id END) AS new_canonical_jobs,
               COUNT(DISTINCT CASE WHEN v.version_number > 1 AND v.created_at >= ? AND v.created_at < ? THEN v.canonical_job_id END) AS updated_jobs
        FROM job_source_observations o
        LEFT JOIN canonical_jobs j ON j.canonical_job_id=o.canonical_job_id
        LEFT JOIN job_posting_versions v ON v.source_observation_id=o.observation_id
        WHERE {observation_predicate}
        GROUP BY o.target_id
        """,
        (*observation_bounds, *observation_bounds, *observation_bounds),
    )
    # The assignment expression above keeps the three identical bound pairs
    # explicit for libSQL/SQLite positional parameters.
    observation_by_target = {_text(row["target_id"]): row for row in observation_rows}

    quality_predicate, quality_bounds = _period("q.created_at", window)
    quality_rows = _group_counts(
        connection,
        f"SELECT target_id, COUNT(*) AS findings FROM acquisition_quality_events q WHERE {quality_predicate} GROUP BY target_id",
        quality_bounds,
    )
    quality_by_target = {_text(row["target_id"]): int(row["findings"] or 0) for row in quality_rows}

    task_rows = connection.execute(
        """
        SELECT t.target_id, t.status, t.complete_snapshot, t.valid_snapshot,
               t.collection_metadata_json, t.completed_at, t.updated_at
        FROM acquisition_tasks t
        WHERE t.task_id = (
            SELECT latest.task_id FROM acquisition_tasks latest
            WHERE latest.target_id=t.target_id
            ORDER BY latest.updated_at DESC, latest.task_id DESC LIMIT 1
        )
        """
    ).fetchall()
    latest_tasks = {_text(row["target_id"]): _row_dict(row) for row in task_rows}

    target_rows = connection.execute(
        """
        SELECT target_id, display_name, connector, provider, maturity_state,
               enabled, quarantined, last_attempt_at, last_success_at,
               request_mode, config_json
        FROM acquisition_targets
        ORDER BY target_id
        LIMIT 500
        """
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in target_rows:
        target_id = _text(row["target_id"])
        attempts_for_source = attempts.get(target_id, {})
        total_attempts = sum(attempts_for_source.values())
        failed_attempts = sum(
            value for key, value in attempts_for_source.items() if key in {"failed", "error", "permanent_error"}
        )
        partial_attempts = sum(
            value for key, value in attempts_for_source.items() if key in {"partial", "incomplete", "interrupted"}
        )
        task = latest_tasks.get(target_id, {})
        metadata = _json(task.get("collection_metadata_json"), {})
        metadata = metadata if isinstance(metadata, Mapping) else {}
        request = requests.get(target_id, {})
        observation = observation_by_target.get(target_id, {})
        total_observations = int(observation.get("observations") or 0)
        readiness = "ready" if bool(row["enabled"]) and not bool(row["quarantined"]) else _text(row["maturity_state"]) or "unknown"
        result.append(
            {
                "source_id": target_id,
                "name": _text(row["display_name"]) or target_id,
                "connector": _text(row["connector"]) or None,
                "provider": _text(row["provider"]) or None,
                "runs": total_attempts,
                "success_count": sum(value for key, value in attempts_for_source.items() if key in {"completed", "complete", "success", "succeeded"}),
                "partial_count": partial_attempts,
                "failure_count": failed_attempts,
                "success_rate": _safe_rate(sum(value for key, value in attempts_for_source.items() if key in {"completed", "complete", "success", "succeeded"}), total_attempts),
                "partial_rate": _safe_rate(partial_attempts, total_attempts),
                "failure_rate": _safe_rate(failed_attempts, total_attempts),
                "observations": total_observations,
                "new_canonical_jobs": int(observation.get("new_canonical_jobs") or 0),
                "updated_jobs": int(observation.get("updated_jobs") or 0),
                "quality_findings": quality_by_target.get(target_id, 0),
                "quality_rate": _safe_rate(quality_by_target.get(target_id, 0), total_observations),
                "last_successful_collection": _text(row["last_success_at"]) or _text(request.get("last_success_at")) or None,
                "last_attempted_collection": _text(row["last_attempt_at"]) or _text(request.get("last_attempt_at")) or None,
                "readiness": readiness,
                "bounded_collection": {
                    "state": "complete" if bool(task.get("complete_snapshot")) else "partial" if task else "unknown",
                    "complete_snapshot": bool(task.get("complete_snapshot")) if task else None,
                    "valid_snapshot": bool(task.get("valid_snapshot")) if task else None,
                    "stop_reason": _text(metadata.get("stop_reason")) or None,
                    "closure_safe": metadata.get("closure_safe") if "closure_safe" in metadata else None,
                },
                "request_use": {
                    "requests": int(request.get("requests") or 0),
                    "credits_actual": int(request.get("credits_actual") or 0),
                    "credits_estimated": int(request.get("credits_estimated") or 0),
                    "duration_ms": round(float(request.get("duration_ms") or 0), 2) if request.get("duration_ms") is not None else None,
                },
                "error_categories": [
                    {"category": _text(item["error_code"]), "count": int(item["count"] or 0)}
                    for item in _group_counts(
                        connection,
                        f"SELECT error_code, COUNT(*) AS count FROM acquisition_requests r WHERE r.target_id=? AND {request_predicate} AND error_code <> '' GROUP BY error_code ORDER BY count DESC LIMIT 20",
                        (target_id, *request_bounds),
                    )
                    if _text(item["error_code"])
                ],
            }
        )
    return result


def _explicit_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    normalized = _text(value).casefold()
    if normalized in {"true", "yes", "1", "enabled", "eligible", "verified"}:
        return True
    if normalized in {"false", "no", "0", "disabled", "ineligible", "unverified"}:
        return False
    return None


def _optional_number(value: Any) -> int | float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not parsed.is_integer():
        return parsed
    return int(parsed)


def _stored_datetime(value: Any) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None
    normalized = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or _UTC).astimezone(_UTC)


def _age_seconds(value: Any, *, at: datetime) -> int | None:
    parsed = _stored_datetime(value)
    if parsed is None:
        return None
    return max(0, int((at - parsed).total_seconds()))


def _task_coverage_state(task: Mapping[str, Any]) -> str:
    if not task:
        return "not_started"
    status = _text(task.get("status")).casefold()
    if status in {"failed", "error", "permanent_error"}:
        return "failed"
    if status in {"paused", "blocked", "cancelled", "deferred"}:
        return "deferred"
    if bool(task.get("complete_snapshot")) and bool(task.get("valid_snapshot")):
        return "complete"
    if status in {"partial", "incomplete", "needs_attention", "interrupted"}:
        return "partial"
    if status in {"running", "pending", "queued", "retryable", "retryable_error"}:
        return "running"
    return "partial"


def _config_value(config: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = config.get(key)
        if value not in (None, ""):
            return value
    return None


def _coverage_analytics(connection, window: AnalyticsWindow) -> dict[str, Any]:
    """Build the bounded company/source coverage read model.

    A row is emitted once per durable acquisition target. Runtime counts are
    never used to replace the frozen source-master denominator, and blocked or
    failed targets without evidence keep job metrics unknown rather than zero.
    """

    target_rows = connection.execute(
        """
        SELECT target_id, display_name, connector, provider, maturity_state,
               enabled, quarantined, last_attempt_at, last_success_at,
               config_json
        FROM acquisition_targets
        ORDER BY target_id
        LIMIT 5000
        """
    ).fetchall()
    task_rows = connection.execute(
        """
        SELECT t.*
        FROM acquisition_tasks t
        WHERE t.task_id = (
            SELECT latest.task_id FROM acquisition_tasks latest
            WHERE latest.target_id=t.target_id
            ORDER BY latest.updated_at DESC, latest.task_id DESC LIMIT 1
        )
        """
    ).fetchall()
    latest_tasks = {_text(row["target_id"]): _row_dict(row) for row in task_rows}
    task_total_row = connection.execute("SELECT COUNT(*) AS count FROM acquisition_tasks").fetchone()
    source_task_total = int(task_total_row["count"] or 0) if task_total_row else 0

    request_rows = connection.execute(
        """
        SELECT target_id, COUNT(*) AS requests,
               COALESCE(SUM(credits_actual), 0) AS credits_actual,
               COALESCE(SUM(credits_estimated), 0) AS credits_estimated,
               SUM(CASE WHEN json_extract(detail_json, '$.cost_known') = 1 THEN 1 ELSE 0 END) AS cost_known
        FROM acquisition_requests
        GROUP BY target_id
        """
    ).fetchall()
    requests_by_target = {_text(row["target_id"]): _row_dict(row) for row in request_rows}
    attempt_rows = connection.execute(
        """
        SELECT target_id, COUNT(*) AS attempts,
               SUM(CASE WHEN LOWER(status) IN ('failed', 'error', 'permanent_error') THEN 1 ELSE 0 END) AS failures,
               MAX(attempt_number) AS latest_attempt
        FROM acquisition_target_attempts
        GROUP BY target_id
        """
    ).fetchall()
    attempts_by_target = {_text(row["target_id"]): _row_dict(row) for row in attempt_rows}

    sources: list[dict[str, Any]] = []
    organization_groups: set[str] = set()
    explicit_employers: set[str] = set()
    evidence_eligible = 0
    evidence_values_seen = False
    source_state_counts: dict[str, int] = defaultdict(int)
    for row in target_rows:
        target_id = _text(row["target_id"])
        task = latest_tasks.get(target_id, {})
        request = requests_by_target.get(target_id, {})
        attempts = attempts_by_target.get(target_id, {})
        config = _json(row["config_json"], {})
        config = config if isinstance(config, Mapping) else {}
        state = _task_coverage_state(task)
        source_state_counts[state] += 1

        group_id = _text(_config_value(config, "organization_group_id", "scan_group_id")) or None
        employer_id = _text(_config_value(config, "employer_id", "canonical_company_id", "organization_id")) or None
        if group_id:
            organization_groups.add(group_id)
        if employer_id:
            explicit_employers.add(employer_id)

        explicit_evidence = _config_value(config, "evidence_verified_eligible")
        eligibility_config = config.get("eligibility")
        if explicit_evidence is None and isinstance(eligibility_config, Mapping):
            explicit_evidence = _config_value(eligibility_config, "evidence_verified_eligible", "verified")
        evidence_value = _explicit_bool(explicit_evidence)
        evidence_values_seen = evidence_values_seen or evidence_value is not None
        if evidence_value is True:
            evidence_eligible += 1

        if bool(row["quarantined"]):
            operational_state = "quarantined"
        elif not bool(row["enabled"]):
            operational_state = "disabled"
        elif _text(row["maturity_state"]).casefold() in {"ready", "approved", "active"}:
            operational_state = "eligible"
        else:
            operational_state = _text(row["maturity_state"]).casefold() or "unknown"

        raw_counts = {
            key: int(task.get(key) or 0)
            for key in ("jobs_observed", "jobs_new", "jobs_updated", "jobs_unchanged", "jobs_published", "jobs_rejected")
        }
        has_count_evidence = state in {"complete", "partial", "running"} or any(raw_counts.values())
        counts = {
            "jobs_observed": raw_counts["jobs_observed"] if has_count_evidence else None,
            "jobs_accepted": (
                raw_counts["jobs_new"] + raw_counts["jobs_updated"] + raw_counts["jobs_unchanged"]
                if has_count_evidence
                else None
            ),
            "jobs_published": raw_counts["jobs_published"] if has_count_evidence else None,
            "jobs_rejected": raw_counts["jobs_rejected"] if has_count_evidence else None,
        }

        last_attempt = _text(row["last_attempt_at"]) or _text(task.get("started_at")) or None
        last_success = _text(row["last_success_at"])
        if not last_success and state == "complete":
            last_success = _text(task.get("completed_at"))
        freshness_limit = _optional_number(
            _config_value(config, "freshness_max_age_hours", "freshness_sla_hours")
        )
        freshness_age = _age_seconds(last_success, at=window.end)
        if freshness_age is None or freshness_limit is None:
            freshness_state = "unknown"
        elif freshness_age <= int(float(freshness_limit) * 3600):
            freshness_state = "fresh"
        else:
            freshness_state = "stale"

        metadata = _json(task.get("collection_metadata_json"), {})
        metadata = metadata if isinstance(metadata, Mapping) else {}
        stop_reason = _text(metadata.get("stop_reason")) or _text(task.get("error_code")) or None
        if state == "complete" and not stop_reason:
            stop_reason = "bounded_snapshot_complete"
        if state == "deferred" and not stop_reason:
            stop_reason = "deferred_by_policy_or_operator"
        if state == "failed" and not stop_reason:
            stop_reason = "source_task_failed"

        if operational_state == "quarantined":
            next_action = "Review quarantine before any retry"
        elif operational_state == "disabled":
            next_action = "Confirm source enablement with operations"
        elif state == "failed":
            next_action = "Review failure evidence before bounded retry"
        elif state == "deferred":
            next_action = "Resume only through an authorized admin action"
        elif state == "partial":
            next_action = "Inspect partial evidence and schedule bounded retry"
        elif state == "not_started":
            next_action = "Schedule the first bounded source task"
        elif freshness_state == "stale":
            next_action = "Schedule a freshness retry"
        else:
            next_action = "Await the next scheduled cycle"

        request_count = int(request.get("requests") or 0)
        cost_known = bool(int(request.get("cost_known") or 0)) if request_count else False
        sources.append(
            {
                "source_id": target_id,
                "name": _text(row["display_name"]) or target_id,
                "connector": _text(row["connector"]) or None,
                "provider": _text(row["provider"]) or None,
                "organization_group_id": group_id,
                "employer_id": employer_id,
                "eligibility": {
                    "operational_state": operational_state,
                    "evidence_verified": evidence_value,
                    "definition": "Evidence eligibility is counted only when explicitly persisted by the source manifest/runtime configuration.",
                },
                "coverage_state": state,
                **counts,
                "stop_reason": stop_reason,
                "freshness": {
                    "state": freshness_state,
                    "last_attempt_at": last_attempt,
                    "last_success_at": last_success or None,
                    "age_seconds": freshness_age,
                    "max_age_hours": freshness_limit,
                },
                "next_action": next_action,
                "retries": {
                    "attempts": int(attempts.get("attempts") or 0),
                    "failures": int(attempts.get("failures") or 0),
                    "latest_attempt": int(attempts.get("latest_attempt") or 0),
                },
                "cost": {
                    "state": "known" if cost_known else "unknown",
                    "requests": request_count,
                    "credits_actual": int(request.get("credits_actual") or 0) if cost_known else None,
                    "credits_estimated": int(request.get("credits_estimated") or 0) if cost_known else None,
                },
            }
        )

    def backlog_count(sql: str, params: tuple[Any, ...] = ()) -> int:
        row = connection.execute(sql, params).fetchone()
        return int(row["count"] or 0) if row else 0

    identity_review = backlog_count(
        "SELECT COUNT(*) AS count FROM company_link_candidates WHERE review_required=1 AND LOWER(decision) IN ('needs_review', 'pending', 'unresolved')"
    )
    identity_evidence_review = backlog_count(
        "SELECT COUNT(*) AS count FROM company_identity_evidence WHERE review_required=1 AND LOWER(link_state) IN ('needs_review', 'pending', 'unresolved')"
    )
    alias_review = backlog_count(
        "SELECT COUNT(*) AS count FROM canonical_company_aliases WHERE LOWER(confidence) IN ('needs_review', 'pending', 'unverified', 'ambiguous')"
    )
    due_retry = 0
    negative_recheck = 0
    for task in task_rows:
        due_at = _stored_datetime(task.get("next_attempt_at"))
        if due_at is None or due_at > window.end:
            continue
        if _text(task.get("status")).casefold() not in {"failed", "partial", "needs_attention", "retryable", "retryable_error"}:
            continue
        if int(task.get("attempt_count") or 0) >= int(task.get("max_attempts") or 0) > 0:
            continue
        due_retry += 1
        metadata = _json(task.get("collection_metadata_json"), {})
        if isinstance(metadata, Mapping) and (
            _explicit_bool(metadata.get("negative_result")) is True
            or _text(metadata.get("result_kind")).casefold() in {"negative", "no_jobs", "empty_result"}
        ):
            negative_recheck += 1

    denominator = {
        "master_rows": _MASTER_INPUT_BASELINE["master_rows"],
        "existing_master_ids": _MASTER_INPUT_BASELINE["existing_master_ids"],
        "missing_master_ids": _MASTER_INPUT_BASELINE["missing_master_ids"],
        "unique_employer_organizations": _MASTER_INPUT_BASELINE["unique_linkedin_organization_ids"],
        "organization_scan_groups": len(organization_groups) if organization_groups else None,
        "source_tasks": source_task_total,
        "evidence_verified_eligible": evidence_eligible if evidence_values_seen else None,
        "runtime_explicit_employers": len(explicit_employers) if explicit_employers else None,
    }
    return {
        "schema_version": ACQUISITION_COVERAGE_SCHEMA_VERSION,
        "baseline": dict(_MASTER_INPUT_BASELINE),
        "denominators": denominator,
        "backlogs": {
            "identity_review": identity_review,
            "identity_evidence_review": identity_evidence_review,
            "alias_review": alias_review,
            "negative_result_recheck": negative_recheck,
            "due_retry": due_retry,
        },
        "totals": {
            "source_rows": len(sources),
            "source_rows_returned": len(sources),
            "source_rows_truncated": len(target_rows) >= 5000,
            "source_task_states": dict(sorted(source_state_counts.items())),
            "jobs_observed": sum(row["jobs_observed"] or 0 for row in sources),
            "jobs_accepted": sum(row["jobs_accepted"] or 0 for row in sources),
            "jobs_published": sum(row["jobs_published"] or 0 for row in sources),
            "jobs_rejected": sum(row["jobs_rejected"] or 0 for row in sources),
            "unknown_job_count_sources": sum(row["jobs_observed"] is None for row in sources),
        },
        "definitions": {
            "master_rows": "Frozen source-master rows from the baseline contract; not a runtime task count.",
            "unique_employer_organizations": "Unique numeric LinkedIn organization IDs in the frozen input; it does not prove ownership or eligibility.",
            "organization_scan_groups": "Distinct explicit organization_group_id/scan_group_id values in acquisition target configuration; null means the current runtime did not persist this grouping.",
            "source_tasks": "All durable acquisition_tasks currently stored; per-source rows use the latest task only.",
            "jobs_accepted": "jobs_new + jobs_updated + jobs_unchanged from the durable task counters; no version rows are counted separately.",
            "unknown_jobs": "Blocked, deferred, failed, or unstarted work without an authoritative result is unknown, not zero.",
            "evidence_verified_eligible": "Explicit eligibility evidence only; missing manifest/configuration is null and never inferred from enabled state.",
        },
        "sources": sources,
    }


def _health_analytics(connection, window: AnalyticsWindow, coverage: Mapping[str, Any]) -> dict[str, Any]:
    """Return role/version-aware health facts without changing durable state."""

    workers: list[dict[str, Any]] = []
    worker_rows = connection.execute(
        """
        SELECT worker_id, status, host_name, process_id, current_run_id,
               started_at, last_heartbeat_at, lease_expires_at, metadata_json
        FROM workers
        ORDER BY worker_id
        LIMIT 200
        """
    ).fetchall()
    for row in worker_rows:
        metadata = _json(row["metadata_json"], {})
        metadata = metadata if isinstance(metadata, Mapping) else {}
        heartbeat_age = _age_seconds(row["last_heartbeat_at"], at=window.end)
        stale_after = _optional_number(metadata.get("heartbeat_stale_after_seconds")) or _WORKER_HEARTBEAT_STALE_SECONDS
        if heartbeat_age is None:
            liveness = "unknown"
        elif heartbeat_age <= int(stale_after):
            liveness = "online"
        else:
            liveness = "stale"
        resource_values = metadata.get("resources") if isinstance(metadata.get("resources"), Mapping) else metadata
        workers.append(
            {
                "worker_id": _text(row["worker_id"]),
                "role": _text(metadata.get("role") or metadata.get("worker_role")) or "unknown",
                "version": _text(metadata.get("version") or metadata.get("worker_version")) or "unknown",
                "stored_status": _text(row["status"]) or "unknown",
                "liveness": liveness,
                "heartbeat_at": _text(row["last_heartbeat_at"]) or None,
                "heartbeat_age_seconds": heartbeat_age,
                "heartbeat_stale_after_seconds": int(stale_after),
                "current_run_id": _text(row["current_run_id"]) or None,
                "resources": {
                    key: _optional_number(resource_values.get(key))
                    for key in ("disk_free_bytes", "disk_used_bytes", "memory_used_bytes", "memory_limit_bytes")
                },
            }
        )

    run_rows = connection.execute(
        """
        SELECT status, created_at, queued_at, started_at, finished_at, attempt_count
        FROM runs
        WHERE created_at <= ?
        """,
        (window.end_iso,),
    ).fetchall()
    queued_ages = []
    processing_durations = []
    queue_failures = 0
    queue_retries = 0
    active_queue = 0
    for row in run_rows:
        status = _text(row["status"]).casefold()
        if status in {"queued", "pending"}:
            active_queue += 1
            age = _age_seconds(_text(row["queued_at"]) or _text(row["created_at"]), at=window.end)
            if age is not None:
                queued_ages.append(age)
        if status in {"failed", "error"}:
            queue_failures += 1
        if int(row["attempt_count"] or 0) > 1:
            queue_retries += 1
        started = _stored_datetime(row["started_at"])
        finished = _stored_datetime(row["finished_at"])
        if started is not None and finished is not None and finished >= started:
            processing_durations.append(int((finished - started).total_seconds() * 1000))

    db_started = time.perf_counter()
    connection.execute("SELECT 1").fetchone()
    db_latency_ms = round((time.perf_counter() - db_started) * 1000, 3)

    task_stuck_before = window.end - timedelta(seconds=_TASK_STUCK_SECONDS)
    stuck_tasks_row = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM acquisition_tasks
        WHERE LOWER(status) IN ('running', 'in_progress')
          AND updated_at <> '' AND updated_at < ?
        """,
        (task_stuck_before.isoformat(),),
    ).fetchone()
    stuck_tasks = int(stuck_tasks_row["count"] or 0) if stuck_tasks_row else 0

    throttled_rows = connection.execute(
        """
        SELECT COALESCE(NULLIF(t.provider, ''), 'unknown') AS provider,
               COUNT(*) AS throttled_requests
        FROM acquisition_requests r
        LEFT JOIN acquisition_targets t ON t.target_id=r.target_id
        WHERE r.provider_status=429 OR LOWER(r.error_code) LIKE '%thrott%'
        GROUP BY provider ORDER BY provider
        """
    ).fetchall()
    provider_throttling = [
        {
            "provider": _text(row["provider"]) or "unknown",
            "state": "throttled",
            "throttled_requests": int(row["throttled_requests"] or 0),
        }
        for row in throttled_rows
    ]

    budget_rows = connection.execute(
        """
        SELECT provider_id, configured, enabled, max_requests, max_cost_units,
               requests_used, cost_units_used, policy_state
        FROM enrichment_provider_budgets
        ORDER BY provider_id LIMIT 100
        """
    ).fetchall()
    limits = []
    for row in budget_rows:
        max_requests = int(row["max_requests"] or 0)
        max_cost = float(row["max_cost_units"] or 0)
        requests_used = int(row["requests_used"] or 0)
        cost_used = float(row["cost_units_used"] or 0)
        breached = (max_requests > 0 and requests_used >= max_requests) or (max_cost > 0 and cost_used >= max_cost)
        limits.append(
            {
                "provider": _text(row["provider_id"]),
                "policy_state": _text(row["policy_state"]) or "unknown",
                "requests_used": requests_used,
                "max_requests": max_requests or None,
                "cost_units_used": cost_used,
                "max_cost_units": max_cost or None,
                "state": "limit_reached" if breached else "within_limit" if max_requests or max_cost else "unknown",
            }
        )

    alerts: list[dict[str, Any]] = []
    if not workers:
        alerts.append({"code": "missing_workers", "severity": "warning", "message": "No durable worker heartbeat is present."})
    for worker in workers:
        if worker["liveness"] == "stale":
            alerts.append({"code": "stale_worker", "severity": "warning", "worker_id": worker["worker_id"], "message": "Worker heartbeat is older than its freshness threshold."})
    for source in coverage.get("sources", []):
        if source.get("freshness", {}).get("state") == "stale":
            alerts.append({"code": "stale_coverage", "severity": "warning", "source_id": source["source_id"], "message": "Source coverage is older than its explicit freshness threshold."})
    if stuck_tasks:
        alerts.append({"code": "stuck_tasks", "severity": "warning", "count": stuck_tasks, "message": "Running acquisition tasks have not moved for the bounded stuck-task interval."})
    for limit in limits:
        if limit["state"] == "limit_reached":
            alerts.append({"code": "spend_limit", "severity": "warning", "provider": limit["provider"], "message": "Provider budget usage has reached its configured limit."})
    for provider in provider_throttling:
        alerts.append({"code": "provider_throttling", "severity": "warning", **provider, "message": "Provider throttling was observed in durable request records."})

    return {
        "schema_version": "acquisition_health_v1",
        "workers": workers,
        "queue": {
            "active_count": active_queue,
            "oldest_queued_age_seconds": max(queued_ages) if queued_ages else None,
            "processing_duration_ms": {
                "average": round(sum(processing_durations) / len(processing_durations), 2) if processing_durations else None,
                "max": max(processing_durations) if processing_durations else None,
                "sample_count": len(processing_durations),
            },
            "failure_count": queue_failures,
            "retry_count": queue_retries,
        },
        "tasks": {"stuck_count": stuck_tasks, "stuck_after_seconds": _TASK_STUCK_SECONDS},
        "database": {
            "latency_ms": db_latency_ms,
            "measurement": "local read-only SELECT 1; this is not a Turso/network latency claim.",
        },
        "provider_throttling": provider_throttling,
        "limits": {
            "providers": limits,
            "retention": {"state": "unknown", "note": "The current schema has no durable retention telemetry."},
        },
        "resource_contract": {
            "source": "worker metadata resources when explicitly reported",
            "fields": ["disk_free_bytes", "disk_used_bytes", "memory_used_bytes", "memory_limit_bytes"],
            "missing_values": "null means the worker did not report the metric; no host inspection is performed by this read model.",
        },
        "alerts": alerts,
    }


def _quality_analytics(connection, window: AnalyticsWindow) -> dict[str, Any]:
    predicate, bounds = _period("created_at", window)
    by_rule = _group_counts(
        connection,
        f"SELECT warning_code AS rule, severity, COUNT(*) AS count FROM acquisition_quality_events WHERE {predicate} GROUP BY warning_code, severity ORDER BY count DESC, rule LIMIT 200",
        bounds,
    )
    over_time = _group_counts(
        connection,
        f"SELECT SUBSTR(created_at, 1, 10) AS day, COUNT(*) AS count FROM acquisition_quality_events WHERE {predicate} GROUP BY SUBSTR(created_at, 1, 10) ORDER BY day",
        bounds,
    )
    by_source = _group_counts(
        connection,
        f"SELECT COALESCE(NULLIF(connector, ''), NULLIF(target_id, ''), 'unknown') AS source, COUNT(*) AS count FROM acquisition_quality_events WHERE {predicate} GROUP BY source ORDER BY count DESC LIMIT 100",
        bounds,
    )
    by_field = _group_counts(
        connection,
        f"""
        SELECT COALESCE(NULLIF(json_extract(details_json, '$.field'), ''), warning_code) AS field,
               COUNT(*) AS count
        FROM acquisition_quality_events
        WHERE {predicate}
        GROUP BY field ORDER BY count DESC LIMIT 200
        """,
        bounds,
    )
    by_kind = _group_counts(
        connection,
        f"""
        SELECT CASE
                 WHEN LOWER(warning_code) LIKE '%missing%' THEN 'missing'
                 WHEN LOWER(warning_code) LIKE '%conflict%' THEN 'conflicting'
                 WHEN LOWER(warning_code) LIKE '%invalid%' THEN 'invalid'
                 ELSE 'other'
               END AS kind, COUNT(*) AS count
        FROM acquisition_quality_events
        WHERE {predicate}
        GROUP BY kind ORDER BY count DESC
        """,
        bounds,
    )
    return {
        "findings_created": sum(int(row["count"] or 0) for row in by_rule),
        "by_rule": by_rule,
        "by_severity": _group_counts(
            connection,
            f"SELECT severity, COUNT(*) AS count FROM acquisition_quality_events WHERE {predicate} GROUP BY severity ORDER BY count DESC",
            bounds,
        ),
        "over_time": over_time,
        "bucket_timezone": "UTC",
        "by_source": by_source,
        "by_field": by_field,
        "by_kind": by_kind,
        "open_count": None,
        "reviewed_count": None,
        "resolved_count": None,
        "resolution_available": False,
        "resolution_note": "Quality findings have no durable reviewed/resolved state in the current contract; they remain report-only.",
    }


def _enrichment_analytics(connection, window: AnalyticsWindow) -> dict[str, Any]:
    predicate, bounds = _period("i.updated_at", window)
    states = _group_counts(
        connection,
        f"""
        SELECT COALESCE(r.provider_id, 'unknown') AS provider,
               i.target_type, i.field_path, LOWER(i.attempt_state) AS state, COUNT(*) AS count
        FROM enrichment_operation_run_items i
        LEFT JOIN enrichment_operation_runs r ON r.run_id=i.run_id
        WHERE {predicate}
        GROUP BY provider, i.target_type, i.field_path, LOWER(i.attempt_state)
        ORDER BY provider, i.target_type, i.field_path, state
        LIMIT 2000
        """,
        bounds,
    )
    summary: dict[str, int] = defaultdict(int)
    for row in states:
        summary[_text(row["state"]).casefold() or "unknown"] += int(row["count"] or 0)
    confidence = _group_counts(
        connection,
        f"""
        SELECT CASE
                 WHEN confidence IS NULL THEN 'unknown'
                 WHEN confidence < 0.5 THEN '0-49%'
                 WHEN confidence < 0.75 THEN '50-74%'
                 WHEN confidence < 0.9 THEN '75-89%'
                 ELSE '90-100%'
               END AS bucket, COUNT(*) AS count
        FROM enrichment_operation_run_items i
        WHERE {predicate}
        GROUP BY bucket ORDER BY bucket
        """,
        bounds,
    )
    run_predicate, run_bounds = _period("created_at", window)
    usage = _group_counts(
        connection,
        f"SELECT provider_id AS provider, COALESCE(SUM(requests_used), 0) AS requests, COALESCE(SUM(cost_units_used), 0) AS cost_units FROM enrichment_operation_runs WHERE {run_predicate} GROUP BY provider_id ORDER BY provider_id",
        run_bounds,
    )
    action_predicate, action_bounds = _period("created_at", window)
    proposal_actions = _group_counts(
        connection,
        f"SELECT LOWER(action) AS action, COUNT(*) AS count FROM enrichment_proposal_actions WHERE {action_predicate} GROUP BY LOWER(action) ORDER BY action",
        action_bounds,
    )
    budget_rows = _group_counts(
        connection,
        "SELECT provider_id, configured, enabled, max_requests, max_cost_units, requests_used, cost_units_used, policy_state FROM enrichment_provider_budgets ORDER BY provider_id LIMIT 100",
        (),
    )
    return {
        "by_state": states,
        "state_totals": dict(sorted(summary.items())),
        "confidence_distribution": confidence,
        "usage": usage,
        "proposal_actions": proposal_actions,
        "cache": {
            "hit": None,
            "miss": None,
            "positive": None,
            "negative": None,
            "available": False,
            "note": "The current cache contract stores entries, not hit/miss telemetry.",
        },
        "budgets": budget_rows,
        "provider_activation": False,
    }


def _publication_analytics(connection, window: AnalyticsWindow) -> dict[str, Any]:
    head = connection.execute(
        """
        SELECT p.publication_id, p.published_at, p.status, p.snapshot_json,
               p.preflight_json, p.previous_publication_id
        FROM acquisition_publications p
        WHERE p.status='valid' AND p.published_at <> '' AND p.published_at <= ?
        ORDER BY p.published_at DESC, p.publication_id DESC LIMIT 1
        """,
        (window.end_iso,),
    ).fetchone()
    head_value = _row_dict(head) if head is not None else {}
    live_count = 0
    closed_live_count = 0
    canonical_unpublished_count: int | None = None
    if head_value.get("publication_id"):
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM acquisition_publication_jobs WHERE publication_id=?",
            (head_value["publication_id"],),
        ).fetchone()
        live_count = int(row["count"] or 0) if row is not None else 0
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM acquisition_publication_jobs pj
            JOIN canonical_jobs j ON j.canonical_job_id=pj.canonical_job_id
            WHERE pj.publication_id=? AND j.lifecycle_state='closed'
            """,
            (head_value["publication_id"],),
        ).fetchone()
        closed_live_count = int(row["count"] or 0) if row is not None else 0
        row = connection.execute(
            """
            SELECT COUNT(*) AS count FROM canonical_jobs j
            WHERE j.created_at <= ?
              AND NOT EXISTS (
                SELECT 1 FROM acquisition_publication_jobs pj
                WHERE pj.publication_id=? AND pj.canonical_job_id=j.canonical_job_id
              )
            """,
            (window.end_iso, head_value["publication_id"]),
        ).fetchone()
        canonical_unpublished_count = int(row["count"] or 0) if row is not None else 0

    predicate, bounds = _period("published_at", window)
    publication_rows = _group_counts(
        connection,
        f"""
        SELECT status, COUNT(*) AS count,
               COALESCE(SUM(json_array_length(json_extract(preflight_json, '$.additions'))), 0) AS added,
               COALESCE(SUM(json_array_length(json_extract(preflight_json, '$.removals'))), 0) AS removed,
               COALESCE(SUM(json_array_length(json_extract(preflight_json, '$.changed_jobs'))), 0) AS changed,
               COALESCE(SUM(json_array_length(json_extract(snapshot_json, '$')) - json_array_length(json_extract(preflight_json, '$.additions'))), 0) AS retained
        FROM acquisition_publications
        WHERE {predicate}
        GROUP BY status
        """,
        bounds,
    )
    audit_predicate, audit_bounds = _period("created_at", window)
    audit_rows = _group_counts(
        connection,
        f"SELECT event_type, COUNT(*) AS count FROM publication_audit_events WHERE {audit_predicate} GROUP BY event_type ORDER BY event_type",
        audit_bounds,
    )
    legacy_rows = _group_counts(
        connection,
        f"SELECT event_type, COUNT(*) AS count FROM admin_job_audit_events WHERE {audit_predicate} GROUP BY event_type ORDER BY event_type",
        audit_bounds,
    )
    audit_counts: dict[str, int] = defaultdict(int)
    for row in (*audit_rows, *legacy_rows):
        audit_counts[_text(row["event_type"])] += int(row["count"] or 0)
    head_published_at = _text(head_value.get("published_at"))
    age_seconds: int | None = None
    if head_published_at:
        try:
            published = datetime.fromisoformat(head_published_at.replace("Z", "+00:00"))
            age_seconds = max(0, int((window.end - published.astimezone(_UTC)).total_seconds()))
        except ValueError:
            age_seconds = None
    history = _group_counts(
        connection,
        f"""
        SELECT publication_id, status, published_at, origin,
               json_array_length(json_extract(preflight_json, '$.additions')) AS added,
               json_array_length(json_extract(preflight_json, '$.removals')) AS removed,
               json_array_length(json_extract(preflight_json, '$.changed_jobs')) AS changed
        FROM acquisition_publications
        WHERE {predicate}
        ORDER BY published_at DESC, publication_id DESC LIMIT 100
        """,
        bounds,
    )
    return {
        "current_head": {
            "publication_id": _text(head_value.get("publication_id")) or None,
            "published_at": head_published_at or None,
            "age_seconds": age_seconds,
            "job_count": live_count,
            "closed_or_stale_job_count": closed_live_count,
        },
        "publication_count": sum(int(row["count"] or 0) for row in publication_rows),
        "by_status": publication_rows,
        "added_count": sum(int(row["added"] or 0) for row in publication_rows),
        "removed_count": sum(int(row["removed"] or 0) for row in publication_rows),
        "retained_count": sum(int(row["retained"] or 0) for row in publication_rows),
        "changed_count": sum(int(row["changed"] or 0) for row in publication_rows),
        "preview_count": sum(int(row["count"] or 0) for row in publication_rows if _text(row["status"]).casefold() in {"staging", "preview"}),
        "published_count": audit_counts.get("publication_published", 0) + audit_counts.get("publication_created", 0),
        "undo_count": audit_counts.get("publication_undone", 0) + audit_counts.get("publication_rollback", 0),
        "audit_events": [*audit_rows, *legacy_rows],
        "history": history,
        "canonical_unpublished_count": canonical_unpublished_count,
        "live_catalog_navigation": "/admin/acquisition/live-catalog",
    }


def _funnel(connection, window: AnalyticsWindow) -> dict[str, Any]:
    observation_predicate, observation_bounds = _period("o.observed_at", window)
    period_jobs = """
        SELECT DISTINCT o.canonical_job_id
        FROM job_source_observations o
        WHERE {predicate}
    """.format(predicate=observation_predicate)
    stages = []
    observed = connection.execute(f"SELECT COUNT(*) AS count FROM ({period_jobs}) period_jobs", observation_bounds).fetchone()
    observed_count = int(observed["count"] or 0) if observed is not None else 0
    versioned = connection.execute(
        f"""
        SELECT COUNT(DISTINCT v.canonical_job_id) AS count
        FROM job_posting_versions v
        JOIN job_source_observations o ON o.observation_id=v.source_observation_id
        WHERE {observation_predicate} AND v.created_at <= ?
        """,
        (*observation_bounds, window.end_iso),
    ).fetchone()
    canonical_count = observed_count
    versioned_count = int(versioned["count"] or 0) if versioned is not None else 0
    reviewed = connection.execute(
        f"""
        SELECT COUNT(DISTINCT d.canonical_job_id) AS count
        FROM admin_job_review_decisions d
        JOIN ({period_jobs}) period_jobs ON period_jobs.canonical_job_id=d.canonical_job_id
        WHERE d.created_at <= ? AND d.decision <> '' AND d.undone_at=''
        """,
        (*observation_bounds, window.end_iso),
    ).fetchone()
    reviewed_count = int(reviewed["count"] or 0) if reviewed is not None else 0
    preview = connection.execute(
        f"""
        SELECT COUNT(DISTINCT pj.canonical_job_id) AS count
        FROM acquisition_publication_jobs pj
        JOIN acquisition_publications p ON p.publication_id=pj.publication_id
        JOIN ({period_jobs}) period_jobs ON period_jobs.canonical_job_id=pj.canonical_job_id
        WHERE p.status IN ('staging', 'preview') AND p.published_at <= ?
        """,
        (*observation_bounds, window.end_iso),
    ).fetchone()
    preview_count = int(preview["count"] or 0) if preview is not None else 0
    live = connection.execute(
        f"""
        SELECT COUNT(DISTINCT pj.canonical_job_id) AS count
        FROM acquisition_publication_jobs pj
        JOIN acquisition_publications p ON p.publication_id=pj.publication_id
        JOIN ({period_jobs}) period_jobs ON period_jobs.canonical_job_id=pj.canonical_job_id
        WHERE p.status='valid' AND p.published_at <= ?
          AND NOT EXISTS (
            SELECT 1 FROM acquisition_publications newer
            WHERE newer.status='valid' AND newer.published_at <= ?
              AND (newer.published_at > p.published_at OR (newer.published_at=p.published_at AND newer.publication_id > p.publication_id))
          )
        """,
        (*observation_bounds, window.end_iso, window.end_iso),
    ).fetchone()
    live_count = int(live["count"] or 0) if live is not None else 0
    for key, label, count, definition in (
        ("observed", "Observed", observed_count, "Distinct canonical job IDs with an immutable source observation in the selected period."),
        ("normalized_versioned", "Normalized / versioned", versioned_count, "Distinct canonical job IDs whose posting version is linked to a selected-period observation and exists by the period end."),
        ("canonical", "Canonical", canonical_count, "Distinct canonical job IDs represented by selected-period observations; posting versions are not counted as extra jobs."),
        ("reviewed", "Reviewed", reviewed_count, "Selected-period canonical jobs with a non-undone admin review decision by the period end."),
        ("publication_preview", "Publication preview", preview_count, "Selected-period canonical jobs present in a staging/preview publication created by the period end."),
        ("published_live", "Published / live", live_count, "Selected-period canonical jobs present in the latest valid publication snapshot at the period end."),
    ):
        stages.append({"key": key, "label": label, "count": count, "definition": definition})
    return {
        "boundary": "event timestamps are start-inclusive/end-exclusive; snapshot stages are evaluated at period end",
        "snapshot_at": window.end_iso,
        "external_market_claim": False,
        "stages": stages,
        "unknown_behavior": "A zero is returned only when the authoritative table has no matching rows; unsupported fields are null elsewhere.",
    }


def _reprocessing_metrics(connection, window: AnalyticsWindow) -> dict[str, Any]:
    predicate, bounds = _period("created_at", window)
    rows = connection.execute(
        f"SELECT status, counts_json FROM acquisition_reprocessing_runs WHERE {predicate} ORDER BY created_at DESC LIMIT 500",
        bounds,
    ).fetchall()
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        value = _json(row["counts_json"], {})
        if isinstance(value, Mapping):
            for key, raw in value.items():
                try:
                    counts[_text(key)] += max(0, int(raw))
                except (TypeError, ValueError):
                    continue
    status_counts = defaultdict(int)
    for row in rows:
        status_counts[_text(row["status"]).casefold()] += 1
    return {
        "runs": len(rows),
        "by_status": dict(sorted(status_counts.items())),
        "affected_records": dict(sorted(counts.items())),
    }


def _operations(connection, window: AnalyticsWindow) -> list[dict[str, Any]]:
    predicate, bounds = _period("created_at", window)
    items: list[dict[str, Any]] = []
    import_rows = connection.execute(
        f"""
        SELECT import_id, status, created_at, started_at, completed_at, error_code, cycle_id
        FROM admin_job_imports
        WHERE status IN ('queued', 'running', 'paused', 'pending') OR {predicate}
        ORDER BY updated_at DESC, import_id DESC LIMIT 100
        """,
        bounds,
    ).fetchall()
    for row in import_rows:
        item = _row_dict(row)
        cycle_id = _text(item.get("cycle_id"))
        progress = {"completed_tasks": None, "total_tasks": None, "percentage": None}
        if cycle_id:
            task = connection.execute(
                "SELECT COUNT(*) AS total, SUM(CASE WHEN status IN ('completed', 'failed', 'partial', 'needs_attention') THEN 1 ELSE 0 END) AS completed FROM acquisition_tasks WHERE cycle_id=?",
                (cycle_id,),
            ).fetchone()
            if task is not None:
                total = int(task["total"] or 0)
                completed = int(task["completed"] or 0)
                progress = {"completed_tasks": completed, "total_tasks": total, "percentage": round(100 * completed / total) if total else None}
        items.append({"kind": "import", "id": _text(item.get("import_id")), "status": _text(item.get("status")), "created_at": _text(item.get("created_at")), "started_at": _text(item.get("started_at")) or None, "completed_at": _text(item.get("completed_at")) or None, "failure_code": _text(item.get("error_code")) or None, "progress": progress, "href": "/admin/acquisition/imports"})

    enrichment_rows = connection.execute(
        f"SELECT run_id, status, created_at, started_at, completed_at, error_code FROM enrichment_operation_runs WHERE status IN ('pending', 'running', 'paused') OR {predicate} ORDER BY updated_at DESC, run_id DESC LIMIT 100",
        bounds,
    ).fetchall()
    for row in enrichment_rows:
        item = _row_dict(row)
        counts_row = connection.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN attempt_state NOT IN ('pending', 'running', 'retryable_error') THEN 1 ELSE 0 END) AS completed FROM enrichment_operation_run_items WHERE run_id=?",
            (item["run_id"],),
        ).fetchone()
        total = int(counts_row["total"] or 0) if counts_row else 0
        completed = int(counts_row["completed"] or 0) if counts_row else 0
        items.append({"kind": "enrichment", "id": _text(item.get("run_id")), "status": _text(item.get("status")), "created_at": _text(item.get("created_at")), "started_at": _text(item.get("started_at")) or None, "completed_at": _text(item.get("completed_at")) or None, "failure_code": _text(item.get("error_code")) or None, "progress": {"completed_items": completed, "total_items": total, "percentage": round(100 * completed / total) if total else None}, "href": "/admin/acquisition/enrichment"})

    reprocessing_rows = connection.execute(
        f"SELECT reprocessing_id, status, created_at, started_at, completed_at, error_json FROM acquisition_reprocessing_runs WHERE status IN ('running', 'planned', 'incomplete') OR {predicate} ORDER BY updated_at DESC, reprocessing_id DESC LIMIT 100",
        bounds,
    ).fetchall()
    for row in reprocessing_rows:
        item = _row_dict(row)
        stage = connection.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed FROM acquisition_stage_results WHERE execution_id=?",
            (item["reprocessing_id"],),
        ).fetchone()
        total = int(stage["total"] or 0) if stage else 0
        completed = int(stage["completed"] or 0) if stage else 0
        error = _json(item.get("error_json"), {})
        items.append({"kind": "reprocessing", "id": _text(item.get("reprocessing_id")), "status": _text(item.get("status")), "created_at": _text(item.get("created_at")), "started_at": _text(item.get("started_at")) or None, "completed_at": _text(item.get("completed_at")) or None, "failure_code": _text(error.get("code")) or None if isinstance(error, Mapping) else None, "progress": {"completed_stages": completed, "total_stages": total, "percentage": round(100 * completed / total) if total else None}, "href": "/admin/acquisition/reprocessing"})
    items.sort(key=lambda item: (_text(item.get("created_at")), _text(item.get("id"))), reverse=True)
    return items[:200]


def build_acquisition_analytics(db_path: str | Path, *, window: AnalyticsWindow) -> dict[str, Any]:
    """Build the bounded analytics response using aggregate SQL only."""

    with database_session(db_path) as connection:
        collection_status = _status_counts(connection, "acquisition_cycles", "scheduled_at", window)
        import_status = _status_counts(connection, "admin_job_imports", "created_at", window)
        observations = _count(connection, "job_source_observations", "observed_at", window)
        new_jobs = _count(connection, "canonical_jobs", "created_at", window)
        versions = _count(connection, "job_posting_versions", "created_at", window, " AND version_number > 1")
        companies = _count(connection, "canonical_companies", "created_at", window)
        identity_evidence = _count(connection, "company_identity_evidence", "created_at", window)
        quality = _quality_analytics(connection, window)
        duplicate_predicate, duplicate_bounds = _period("created_at", window)
        duplicate_created = _count(connection, "acquisition_duplicate_clusters", "created_at", window)
        duplicate_reviewed = connection.execute(
            f"SELECT COUNT(DISTINCT cluster_id) AS count FROM acquisition_duplicate_decisions WHERE {duplicate_predicate}",
            duplicate_bounds,
        ).fetchone()
        duplicate_states = _group_counts(
            connection,
            f"SELECT state, COUNT(*) AS count FROM acquisition_duplicate_clusters WHERE {duplicate_predicate} GROUP BY state ORDER BY state",
            duplicate_bounds,
        )
        enrichment = _enrichment_analytics(connection, window)
        reprocessing = _reprocessing_metrics(connection, window)
        publication = _publication_analytics(connection, window)
        coverage = _coverage_analytics(connection, window)
        terminal_enrichment_states = {
            key: value
            for key, value in enrichment["state_totals"].items()
            if key not in {"pending", "running", "retryable_error"}
        }
        return {
            "schema_version": ANALYTICS_SCHEMA_VERSION,
            "read_only": True,
            "providers_activated": False,
            "window": {
                "range": window.range_key,
                "timezone": window.timezone_name,
                "start": window.start_iso,
                "end": window.end_iso,
                "boundary": "start inclusive, end exclusive",
            },
            "definitions": {
                "collection_runs": "acquisition_cycles scheduled in the selected period; import runs are reported separately because one admin import may own one cycle.",
                "observations": "immutable job_source_observations observed in the selected period.",
                "new_canonical_jobs": "canonical_jobs created in the selected period; versions never increase this count.",
                "updated_jobs": "distinct canonical jobs with a posting version_number greater than 1 created in the selected period.",
                "companies": "canonical_companies created in the selected period.",
                "reconciled_companies": "distinct company identity evidence rows created in the selected period; no unsupported merge count is inferred.",
                "quality": "acquisition_quality_events created in the selected period; findings remain report-only.",
                "source_performance": "source-target aggregates bounded to the selected period, plus current readiness and latest task state.",
                "live_catalog": "the latest valid publication snapshot at the period end, not the external market total.",
                "unknown": "null means the current schema does not persist an authoritative value; zero means an authoritative aggregate matched no rows.",
            },
            "summary": {
                "collection_runs": _count(connection, "acquisition_cycles", "scheduled_at", window),
                "import_runs": _count(connection, "admin_job_imports", "created_at", window),
                "operations": {"collection": collection_status, "imports": import_status},
                "observations_received": observations,
                "new_canonical_jobs": new_jobs,
                "updated_jobs": versions,
                "existing_jobs_versioned": versions,
                "canonical_companies_created": companies,
                "companies_reconciled": identity_evidence,
                "quality_findings_created": quality["findings_created"],
                "quality_findings_resolved": None,
                "duplicate_clusters_created": duplicate_created,
                "duplicate_clusters_reviewed": int(duplicate_reviewed["count"] or 0) if duplicate_reviewed else 0,
                "enrichment_items_completed": sum(terminal_enrichment_states.values()),
                "reprocessing_runs": reprocessing["runs"],
            },
            "funnel": _funnel(connection, window),
            "sources": _source_performance(connection, window),
            "quality": quality,
            "duplicates": {"created": duplicate_created, "reviewed": int(duplicate_reviewed["count"] or 0) if duplicate_reviewed else 0, "by_state": duplicate_states},
            "enrichment": enrichment,
            "reprocessing": reprocessing,
            "publication": publication,
            "operations": _operations(connection, window),
            "coverage": coverage,
            "health": _health_analytics(connection, window, coverage),
        }


__all__ = [
    "ANALYTICS_MAX_DAYS",
    "ANALYTICS_RANGES",
    "ANALYTICS_SCHEMA_VERSION",
    "ACQUISITION_COVERAGE_SCHEMA_VERSION",
    "AnalyticsWindow",
    "build_acquisition_analytics",
    "parse_analytics_window",
]
