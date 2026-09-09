"""Privacy-safe product analytics projections for the admin overview.

The event table is intentionally treated as an append-only delivery log.  The
projection below deduplicates users for funnel and retention denominators while
retaining raw event counts for delivery diagnostics.  It does not expose event
payloads, email addresses, CV text, or other user-entered content.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping


PRODUCT_ANALYTICS_SCHEMA_VERSION = "product_analytics_v1"
PRODUCT_ANALYTICS_WINDOW_DAYS = 90

PRODUCT_ANALYTICS_EVENT_QUERY = """
    SELECT
      e.event_name,
      e.occurred_at,
      e.user_id,
      e.workspace_id,
      e.run_id,
      e.job_id,
      e.source,
      e.payload_json,
      u.payload_json AS user_payload_json
    FROM analytics_events e
    LEFT JOIN users u ON u.user_id = e.user_id
    WHERE e.occurred_at >= ? AND e.occurred_at < ?
    ORDER BY e.occurred_at ASC
"""

_FUNNEL_STAGES = (
    ("signup", ("user_signed_up",)),
    ("profile_ready", ("profile_ready",)),
    ("relevant_job", ("job_relevant_viewed",)),
    ("saved_job", ("job_saved",)),
    ("application_prepared", ("cv_generation_completed",)),
    ("confirmed_application_outcome", ("application_status_updated",)),
    ("paid_conversion", ("subscription_started",)),
)

_VALUE_EVENT_NAMES = frozenset(
    {
        "session_started",
        "page_view",
        "jobs_feed_viewed",
        "job_relevant_viewed",
        "job_saved",
        "cv_generation_completed",
        "application_status_updated",
        "subscription_started",
    }
)

_LATENCY_EVENT_NAMES = frozenset(
    {
        "frontend_api_request_slow",
        "run_completed",
        "run_failed",
        "cv_generation_completed",
    }
)

_FAILURE_EVENT_NAMES = frozenset(
    {
        "frontend_api_request_failed",
        "run_failed",
        "automation_step_failed",
    }
)

_VERSION_KEYS = (
    "release_version",
    "app_version",
    "worker_version",
    "version",
)

_CONFIRMED_OUTCOME_STATUSES = frozenset(
    {"applied", "interviewing", "offer", "hired"}
)


def _normalise_environment(value: Any) -> str:
    normalized = str(value or "").strip().casefold()
    aliases = {
        "prod": "production",
        "production": "production",
        "stage": "staging",
        "staging": "staging",
        "test": "test",
        "testing": "test",
        "dev": "development",
        "development": "development",
        "local": "local",
        "internal": "internal",
    }
    return aliases.get(normalized, normalized or "unknown")


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}
    return {}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _event_environment(row: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
    return _normalise_environment(
        payload.get("analytics_environment")
        or row.get("analytics_environment")
        or "unknown"
    )


def _exclusion_reason(row: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
    user_id = str(row.get("user_id") or "").strip()
    user_key = user_id.casefold()
    if user_key.startswith(("e2e-", "test-", "internal-")):
        return "test_or_internal_user_id"
    if _as_bool(payload.get("analytics_excluded")):
        return "event_exclusion_flag"

    user_payload = _as_mapping(row.get("user_payload_json"))
    metadata = _as_mapping(user_payload.get("metadata"))
    if _as_bool(user_payload.get("analytics_excluded")) or _as_bool(metadata.get("analytics_excluded")):
        return "user_exclusion_flag"
    email = str(user_payload.get("email") or metadata.get("email") or "").strip().casefold()
    if email.endswith("@runr.test") or email.endswith("@example.com"):
        return "test_email_domain"
    return ""


def _duration_ms(payload: Mapping[str, Any]) -> float | None:
    for key in ("duration_ms", "latency_ms"):
        try:
            value = float(payload.get(key))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    try:
        value = float(payload.get("duration_seconds")) * 1000
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _latency_band(duration_ms: float | None) -> str:
    if duration_ms is None:
        return "unknown"
    if duration_ms < 1_000:
        return "<1s"
    if duration_ms < 5_000:
        return "1-5s"
    if duration_ms < 20_000:
        return "5-20s"
    return "20s+"


def _confirmed_outcome(event_name: str, payload: Mapping[str, Any]) -> bool:
    if event_name != "application_status_updated":
        return False
    if _as_bool(payload.get("email_confirmed")):
        return True
    return str(payload.get("to_status") or payload.get("status") or "").strip().casefold() in _CONFIRMED_OUTCOME_STATUSES


def _event_matches_stage(event_name: str, payload: Mapping[str, Any], names: Iterable[str]) -> bool:
    return event_name in names and (
        event_name != "application_status_updated" or _confirmed_outcome(event_name, payload)
    )


def _cohort_week(value: datetime) -> str:
    start = value.date() - timedelta(days=value.weekday())
    return start.isoformat()


def _percentage(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(100 * numerator / denominator, 1)


def _empty_environment_summary(environment: str) -> dict[str, Any]:
    return {
        "environment": environment,
        "events": 0,
        "unique_users": 0,
        "signups": 0,
        "value_users": 0,
    }


def build_product_analytics(
    rows: Iterable[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    environment: str | None = None,
) -> dict[str, Any]:
    """Build the RC-030 projection from bounded analytics event rows.

    ``rows`` is deliberately accepted as a plain iterable so this contract can
    be tested without a database and can be reused by a future Turso adapter.
    Funnel stages only count events after a same-environment signup.  A stage
    event without a signup remains accounted for in ``orphan_stage_events`` but
    cannot inflate the funnel denominator.
    """

    end = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = end - timedelta(days=PRODUCT_ANALYTICS_WINDOW_DAYS)
    selected_environment = _normalise_environment(
        environment if environment is not None else os.getenv("RUNR_ENV") or "development"
    )

    events: list[dict[str, Any]] = []
    excluded_events = 0
    excluded_users: set[str] = set()
    exclusion_reasons: defaultdict[str, int] = defaultdict(int)
    unparseable_events = 0
    for raw_row in rows:
        row = dict(raw_row or {})
        occurred_at = _parse_datetime(row.get("occurred_at"))
        if occurred_at is None:
            unparseable_events += 1
            continue
        if occurred_at < start or occurred_at >= end:
            continue
        payload = _as_mapping(row.get("payload") or row.get("payload_json"))
        reason = _exclusion_reason(row, payload)
        if reason:
            excluded_events += 1
            user_id = str(row.get("user_id") or "").strip()
            if user_id:
                excluded_users.add(user_id)
            exclusion_reasons[reason] += 1
            continue
        user_id = str(row.get("user_id") or "").strip()
        events.append(
            {
                "event_name": str(row.get("event_name") or "").strip(),
                "occurred_at": occurred_at,
                "user_id": user_id,
                "environment": _event_environment(row, payload),
                "run_id": str(row.get("run_id") or payload.get("run_id") or "").strip(),
                "job_id": str(
                    row.get("job_id")
                    or payload.get("job_id")
                    or payload.get("job_preview_id")
                    or ""
                ).strip(),
                "source": str(row.get("source") or "").strip() or "unknown",
                "payload": payload,
            }
        )

    environment_events = [item for item in events if item["environment"] == selected_environment]
    signup_times: dict[str, datetime] = {}
    for event in environment_events:
        if event["event_name"] != "user_signed_up" or not event["user_id"]:
            continue
        signup_times[event["user_id"]] = min(
            signup_times.get(event["user_id"], event["occurred_at"]), event["occurred_at"]
        )

    def post_signup(event: Mapping[str, Any]) -> bool:
        user_id = str(event.get("user_id") or "")
        signup_at = signup_times.get(user_id)
        return bool(signup_at and event["occurred_at"] >= signup_at)

    funnel_stages: list[dict[str, Any]] = []
    orphan_stage_events = 0
    for stage_name, event_names in _FUNNEL_STAGES:
        matching = [
            event
            for event in environment_events
            if _event_matches_stage(event["event_name"], event["payload"], event_names)
        ]
        if stage_name == "signup":
            eligible = [event for event in matching if event["user_id"] in signup_times]
        else:
            eligible = [event for event in matching if post_signup(event)]
            orphan_stage_events += len(matching) - len(eligible)
        users = {event["user_id"] for event in eligible if event["user_id"]}
        funnel_stages.append(
            {
                "stage": stage_name,
                "event_names": list(event_names),
                "events": len(eligible),
                "unique_users": len(users),
                "conversion_pct": _percentage(len(users), len(signup_times)),
                "first_at": min((event["occurred_at"] for event in eligible), default=None).isoformat()
                if eligible
                else None,
                "last_at": max((event["occurred_at"] for event in eligible), default=None).isoformat()
                if eligible
                else None,
                "backend_confirmed": stage_name
                in {
                    "signup",
                    "profile_ready",
                    "saved_job",
                    "application_prepared",
                    "confirmed_application_outcome",
                    "paid_conversion",
                },
            }
        )

    eligible_value_events = [
        event
        for event in environment_events
        if event["event_name"] in _VALUE_EVENT_NAMES and post_signup(event)
    ]
    feature_usage: list[dict[str, Any]] = []
    for event_name in sorted(_VALUE_EVENT_NAMES):
        matching = [event for event in eligible_value_events if event["event_name"] == event_name]
        if not matching:
            continue
        feature_usage.append(
            {
                "event_name": event_name,
                "events": len(matching),
                "unique_users": len({event["user_id"] for event in matching if event["user_id"]}),
                "distinct_jobs": len({event["job_id"] for event in matching if event["job_id"]}),
                "distinct_runs": len({event["run_id"] for event in matching if event["run_id"]}),
                "sources": sorted({event["source"] for event in matching}),
                "versions": sorted(
                    {
                        str(event["payload"].get(key)).strip()
                        for event in matching
                        for key in _VERSION_KEYS
                        if str(event["payload"].get(key) or "").strip()
                    }
                ),
            }
        )

    value_events_by_user: defaultdict[str, list[datetime]] = defaultdict(list)
    for event in eligible_value_events:
        if event["user_id"]:
            value_events_by_user[event["user_id"]].append(event["occurred_at"])
    cohorts: defaultdict[str, list[tuple[str, datetime]]] = defaultdict(list)
    for user_id, signup_at in signup_times.items():
        cohorts[_cohort_week(signup_at)].append((user_id, signup_at))
    retention_cohorts: list[dict[str, Any]] = []
    for cohort, members in sorted(cohorts.items()):
        eligible_d7 = [
            (user_id, signup_at)
            for user_id, signup_at in members
            if end >= signup_at + timedelta(days=8)
        ]
        eligible_d30 = [
            (user_id, signup_at)
            for user_id, signup_at in members
            if end >= signup_at + timedelta(days=31)
        ]

        def returned_at(member: tuple[str, datetime], offset_days: int) -> bool:
            user_id, signup_at = member
            lower = signup_at + timedelta(days=offset_days)
            upper = lower + timedelta(days=1)
            return any(lower <= value_at < upper for value_at in value_events_by_user.get(user_id, []))

        returned_d7 = sum(returned_at(member, 7) for member in eligible_d7)
        returned_d30 = sum(returned_at(member, 30) for member in eligible_d30)
        retention_cohorts.append(
            {
                "cohort_week": cohort,
                "signups": len(members),
                "eligible_d7": len(eligible_d7),
                "returned_d7": returned_d7,
                "return_d7_pct": _percentage(returned_d7, len(eligible_d7)),
                "eligible_d30": len(eligible_d30),
                "returned_d30": returned_d30,
                "return_d30_pct": _percentage(returned_d30, len(eligible_d30)),
            }
        )

    latency_bands: dict[str, list[dict[str, Any]]] = defaultdict(list)
    latency_events = [
        event
        for event in environment_events
        if event["event_name"] in _LATENCY_EVENT_NAMES and post_signup(event)
    ]
    for event in latency_events:
        latency_bands[_latency_band(_duration_ms(event["payload"]))].append(event)
    latency_rows: list[dict[str, Any]] = []
    for band in ("<1s", "1-5s", "5-20s", "20s+", "unknown"):
        matching = latency_bands.get(band, [])
        if not matching:
            continue
        matching_users = {event["user_id"] for event in matching if event["user_id"]}
        later_confirmed_users = {
            event["user_id"]
            for event in environment_events
            if event["user_id"] in matching_users
            and _event_matches_stage(
                event["event_name"], event["payload"], ("application_status_updated",)
            )
            and any(
                prior["user_id"] == event["user_id"]
                and prior["occurred_at"] <= event["occurred_at"]
                and prior in matching
                for prior in matching
            )
        }
        latency_rows.append(
            {
                "band": band,
                "events": len(matching),
                "unique_users": len(matching_users),
                "confirmed_outcome_users_after": len(later_confirmed_users),
            }
        )

    failure_rows: list[dict[str, Any]] = []
    failure_groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in environment_events:
        if event["event_name"] not in _FAILURE_EVENT_NAMES or not post_signup(event):
            continue
        category = str(
            event["payload"].get("error_code")
            or event["payload"].get("failure_code")
            or event["payload"].get("failure_stage")
            or "unknown"
        ).strip()[:80] or "unknown"
        failure_groups[category].append(event)
    for category, matching in sorted(failure_groups.items(), key=lambda item: (-len(item[1]), item[0])):
        users = {event["user_id"] for event in matching if event["user_id"]}
        later_value_users = {
            event["user_id"]
            for event in eligible_value_events
            if event["user_id"] in users
            and any(
                prior["user_id"] == event["user_id"]
                and prior["occurred_at"] <= event["occurred_at"]
                for prior in matching
            )
        }
        failure_rows.append(
            {
                "category": category,
                "events": len(matching),
                "unique_users": len(users),
                "later_value_users": len(later_value_users),
            }
        )

    by_environment: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_environment[event["environment"]].append(event)
    environment_rows = []
    for name in sorted(set(by_environment) | {selected_environment}):
        matching = by_environment.get(name, [])
        matching_signups = {event["user_id"] for event in matching if event["event_name"] == "user_signed_up" and event["user_id"]}
        matching_value_users = {event["user_id"] for event in matching if event["event_name"] in _VALUE_EVENT_NAMES and event["user_id"]}
        environment_rows.append(
            {
                **_empty_environment_summary(name),
                "events": len(matching),
                "unique_users": len({event["user_id"] for event in matching if event["user_id"]}),
                "signups": len(matching_signups),
                "value_users": len(matching_value_users),
            }
        )

    return {
        "schema_version": PRODUCT_ANALYTICS_SCHEMA_VERSION,
        "environment": selected_environment,
        "window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": PRODUCT_ANALYTICS_WINDOW_DAYS,
            "boundary": "start_inclusive_end_exclusive",
        },
        "funnel": {
            "denominator": {"stage": "signup", "unique_users": len(signup_times)},
            "stages": funnel_stages,
            "orphan_stage_events": orphan_stage_events,
        },
        "retention": {
            "cohort_unit": "signup_week",
            "value_event_names": sorted(_VALUE_EVENT_NAMES),
            "day_7_window": "signup_plus_7d_through_signup_plus_8d_exclusive",
            "day_30_window": "signup_plus_30d_through_signup_plus_31d_exclusive",
            "cohorts": retention_cohorts,
        },
        "feature_usage": feature_usage,
        "latency_bands": latency_rows,
        "failure_categories": failure_rows,
        "by_environment": environment_rows,
        "exclusions": {
            "excluded_events": excluded_events,
            "excluded_users": len(excluded_users),
            "reasons": dict(sorted(exclusion_reasons.items())),
            "unparseable_events": unparseable_events,
        },
    }


def load_product_analytics(
    query_rows: Callable[[str, Iterable[Any]], list[dict[str, Any]]],
    *,
    now: datetime | None = None,
    environment: str | None = None,
) -> dict[str, Any]:
    """Load the bounded event window through an existing SQL-capable store."""

    end = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = end - timedelta(days=PRODUCT_ANALYTICS_WINDOW_DAYS)
    rows = query_rows(PRODUCT_ANALYTICS_EVENT_QUERY, (start.isoformat(), end.isoformat()))
    return build_product_analytics(rows, now=end, environment=environment)
