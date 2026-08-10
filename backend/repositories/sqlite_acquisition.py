from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from backend.domain.models import utc_now_iso, utc_plus_seconds
from backend.acquisition.network_policy import hostname_for_url
from backend.acquisition.phase_g import (
    applicant_source_gate,
    has_applicant_evidence,
    is_portal_target,
    normalize_applicant_snapshot,
    portal_audit_gate,
)
from backend.acquisition.quality import (
    DIRECT_APPLICATION_CLASSIFICATIONS,
    canonical_employer_name,
    classify_job_url,
    company_name_key,
    completeness_rules,
    normalize_job_for_ingestion,
    posted_age_hours,
    posted_age_hours_for_job,
    source_employer_name,
    stable_content_payload,
)
from backend.acquisition.unified_mapping import UNIFIED_RULE_VERSION
from backend.repositories.sqlite_core import _SqliteStore


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode(value: str | bytes | None, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _dict_row(row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _bool(value: Any) -> bool:
    return bool(int(value or 0))


def _is_unknown_value(value: Any) -> bool:
    return isinstance(value, str) and value.strip().casefold() in {
        "unknown",
        "not available",
        "not disclosed",
        "undisclosed",
        "n/a",
    }


_COMPANY_PROFILE_FIELDS = (
    "description",
    "website",
    "careers_page",
    "industry",
    "company_size",
    "headquarters",
    "founded_year",
    "company_stage",
    "funding_stage",
    "total_funding",
    "funding_year",
    "leadership_type",
    "benefits",
    "sponsorship",
    "logo",
)


def _profile_field(value: Any = None, *, source: str = "", provenance_url: str = "", verified_at: str = "") -> dict[str, Any]:
    known = value not in (None, "", []) and not _is_unknown_value(value)
    return {
        "value": value if known else None,
        "state": "known" if known else "unknown",
        "provenance": {"source": str(source or ""), "url": str(provenance_url or "")} if known else None,
        "verified_at": str(verified_at or "") if known else None,
    }


def _company_profile_payload(source: Mapping[str, Any] | None, *, provenance_url: str, verified_at: str) -> dict[str, Any]:
    raw = dict(source or {})
    aliases = {
        "description": ("description", "company_description", "about"),
        "website": ("website", "company_website", "site"),
        "careers_page": ("careers_page", "careers_url", "career_page", "jobs_url"),
        "industry": ("industry", "company_industry"),
        "company_size": ("company_size", "size", "employees"),
        "headquarters": ("headquarters", "company_headquarters", "hq"),
        "founded_year": ("founded_year", "company_founded_year", "founded"),
        "company_stage": ("company_stage", "stage", "company_growth_stage"),
        "funding_stage": ("funding_stage", "company_funding_stage"),
        "total_funding": ("total_funding", "total_funding_amount", "funding"),
        "funding_year": ("funding_year", "last_funding_year"),
        "leadership_type": ("leadership_type", "leadership"),
        "benefits": ("benefits", "company_benefits"),
        "sponsorship": ("sponsorship", "sponsorship_information", "sponsors_h1b"),
        "logo": ("logo_url", "logo", "company_logo"),
    }
    return {
        "schema_version": "phase_f_v1",
        "fields": {
            field: _profile_field(
                next((raw.get(alias) for alias in names if raw.get(alias) not in (None, "", [])), None),
                source="official_employer_source" if raw else "",
                provenance_url=provenance_url,
                verified_at=verified_at,
            )
            for field, names in aliases.items()
        },
    }


class SqliteAcquisitionStore(_SqliteStore):
    """Durable repository for system-owned acquisition work and public catalog state."""

    def ensure_targets(self, targets: Iterable[Mapping[str, Any]]) -> None:
        now = utc_now_iso()
        rows = [dict(target) for target in targets]

        def write(connection) -> None:
            for target in rows:
                target_id = str(target.get("target_id") or "").strip()
                if not target_id:
                    raise ValueError("Acquisition target requires target_id.")
                target_kind = str(target.get("target_kind") or "employer_career_site")
                is_quarantined = target_kind.casefold() == "fixture" or target_id in {"fixture_source", "x"}
                connection.execute(
                    """
                    INSERT INTO acquisition_targets (
                        target_id, target_kind, display_name, canonical_target_url,
                        provenance_url, request_url, connector, provider, source_token,
                        policy_version, maturity_state, enabled, publication_enabled,
                        max_direct_requests, request_mode, config_json, quarantined,
                        quarantine_reason, quarantined_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(target_id) DO UPDATE SET
                        target_kind=excluded.target_kind,
                        display_name=excluded.display_name,
                        canonical_target_url=excluded.canonical_target_url,
                        provenance_url=excluded.provenance_url,
                        request_url=excluded.request_url,
                        connector=excluded.connector,
                        provider=excluded.provider,
                        source_token=excluded.source_token,
                        policy_version=excluded.policy_version,
                        maturity_state=CASE WHEN acquisition_targets.quarantined=1 THEN 'quarantined' ELSE excluded.maturity_state END,
                        enabled=CASE WHEN acquisition_targets.quarantined=1 THEN 0 ELSE excluded.enabled END,
                        publication_enabled=CASE WHEN acquisition_targets.quarantined=1 THEN 0 ELSE excluded.publication_enabled END,
                        max_direct_requests=excluded.max_direct_requests,
                        request_mode=excluded.request_mode,
                        config_json=excluded.config_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        target_id,
                        str(target.get("target_kind") or "employer_career_site"),
                        str(target.get("display_name") or target_id),
                        str(target.get("canonical_target_url") or ""),
                        str(target.get("provenance_url") or ""),
                        str(target.get("request_url") or target.get("canonical_target_url") or ""),
                        str(target.get("connector") or "bounded_probe"),
                        str(target.get("provider") or ""),
                        str(target.get("source_token") or ""),
                        str(target.get("policy_version") or "phase_a_v1"),
                        "quarantined" if is_quarantined else str(target.get("maturity_state") or "unproven"),
                        0 if is_quarantined else int(bool(target.get("enabled", False))),
                        0 if is_quarantined else int(bool(target.get("publication_enabled", False))),
                        max(1, int(target.get("max_direct_requests") or 3)),
                        str(target.get("request_mode") or "direct"),
                        _json(
                            {
                                **dict(target.get("config") or {}),
                                **(
                                    {"official_employer_hosts": list(target.get("official_employer_hosts") or [])}
                                    if target.get("official_employer_hosts")
                                    else {}
                                ),
                                **(
                                    {"canonical_company_name": str(target.get("canonical_company_name") or "")}
                                    if target.get("canonical_company_name")
                                    else {}
                                ),
                            }
                        ),
                        int(is_quarantined),
                        "fixture_or_test_target" if is_quarantined else "",
                        now if is_quarantined else "",
                        now,
                        now,
                    ),
                )

        self._run_transaction(write)

    def list_targets(self, *, include_disabled: bool = True) -> list[dict[str, Any]]:
        with self._connect() as connection:
            sql = "SELECT * FROM acquisition_targets"
            params: tuple[Any, ...] = ()
            if not include_disabled:
                sql += " WHERE enabled = 1 AND COALESCE(quarantined, 0) = 0"
            sql += " ORDER BY target_kind, display_name"
            rows = connection.execute(sql, params).fetchall()
        return [self._target_payload(_dict_row(row)) for row in rows]

    def get_target(self, target_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM acquisition_targets WHERE target_id = ?",
                (str(target_id or "").strip(),),
            ).fetchone()
        if row is None:
            raise KeyError(f"Acquisition target '{target_id}' not found.")
        return self._target_payload(_dict_row(row))

    def update_target_state(
        self,
        target_id: str,
        *,
        maturity_state: str,
        reason: str,
        zero_yield_streak: int | None = None,
        attempted_at: str = "",
        successful_at: str = "",
    ) -> None:
        now = utc_now_iso()
        with self._connect() as connection:
            current = connection.execute(
                "SELECT maturity_state, zero_yield_streak, last_success_at, last_state_transition_at "
                "FROM acquisition_targets WHERE target_id = ?",
                (target_id,),
            ).fetchone()
            if current is None:
                raise KeyError(f"Acquisition target '{target_id}' not found.")
            previous = str(current["maturity_state"] or "")
            streak = (
                int(current["zero_yield_streak"] or 0) if zero_yield_streak is None else max(0, int(zero_yield_streak))
            )
            preserved_success = str(current["last_success_at"] or "")
            connection.execute(
                """
                UPDATE acquisition_targets
                SET maturity_state = ?, zero_yield_streak = ?, last_attempt_at = ?,
                    last_success_at = ?, last_state_transition_at = ?,
                    state_transition_reason = ?, updated_at = ?
                WHERE target_id = ?
                """,
                (
                    str(maturity_state),
                    streak,
                    str(attempted_at or now),
                    str(successful_at or preserved_success),
                    now if previous != maturity_state else str(current["last_state_transition_at"] or ""),
                    str(reason or ""),
                    now,
                    target_id,
                ),
            )

    def claim_due_cycle(
        self,
        *,
        window_key: str,
        lease_owner: str,
        scheduled_at: str,
        lease_seconds: int = 300,
        force: bool = False,
    ) -> dict[str, Any] | None:
        cycle_id = f"acq_cycle_{uuid4().hex}"
        now = utc_now_iso()
        lease_expires = utc_plus_seconds(lease_seconds)

        def claim(connection):
            existing = connection.execute(
                "SELECT * FROM acquisition_cycles WHERE window_key = ?",
                (window_key,),
            ).fetchone()
            if existing is not None:
                existing_payload = _dict_row(existing)
                status = str(existing_payload.get("status") or "")
                lease = str(existing_payload.get("lease_expires_at") or "")
                if status == "running" and lease > now:
                    return None
                if status == "completed" and not force:
                    return None
                if status in {"recovery_required", "partial", "interrupted"}:
                    return None
                connection.execute(
                    """
                    UPDATE acquisition_cycles
                    SET status='running', lease_owner=?, lease_expires_at=?, started_at=?,
                        completed_at='', error_code='', error_message='', updated_at=?
                    WHERE cycle_id = ?
                    """,
                    (lease_owner, lease_expires, now, now, existing_payload["cycle_id"]),
                )
                row = connection.execute(
                    "SELECT * FROM acquisition_cycles WHERE cycle_id = ?",
                    (existing_payload["cycle_id"],),
                ).fetchone()
                return _dict_row(row)
            connection.execute(
                """
                INSERT INTO acquisition_cycles (
                    cycle_id, window_key, status, lease_owner, lease_expires_at,
                    scheduled_at, started_at, created_at, updated_at
                ) VALUES (?, ?, 'running', ?, ?, ?, ?, ?, ?)
                """,
                (cycle_id, window_key, lease_owner, lease_expires, scheduled_at, now, now, now),
            )
            row = connection.execute("SELECT * FROM acquisition_cycles WHERE cycle_id = ?", (cycle_id,)).fetchone()
            return _dict_row(row)

        return self._run_transaction(claim)

    def ensure_cycle_tasks(self, cycle_id: str, targets: Iterable[Mapping[str, Any]]) -> None:
        now = utc_now_iso()
        rows = [dict(target) for target in targets if bool(target.get("enabled", False))]
        with self._connect() as connection:
            for target in rows:
                connection.execute(
                    """
                    INSERT INTO acquisition_tasks (
                        task_id, cycle_id, target_id, status, created_at, updated_at
                    ) VALUES (?, ?, ?, 'pending', ?, ?)
                    ON CONFLICT(cycle_id, target_id) DO NOTHING
                    """,
                    (f"acq_task_{uuid4().hex}", cycle_id, str(target["target_id"]), now, now),
                )

    def set_cycle_forecast(self, cycle_id: str, *, requests: int, credits: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE acquisition_cycles SET forecast_requests=?, forecast_credits=?, updated_at=? WHERE cycle_id=?",
                (max(0, int(requests)), max(0, int(credits)), utc_now_iso(), cycle_id),
            )

    def claim_next_task(
        self,
        *,
        cycle_id: str,
        lease_owner: str,
        lease_seconds: int = 300,
    ) -> dict[str, Any] | None:
        now = utc_now_iso()
        lease_expires = utc_plus_seconds(lease_seconds)

        def claim(connection):
            row = connection.execute(
                """
                SELECT * FROM acquisition_tasks
                WHERE cycle_id = ? AND (
                    status = 'pending' OR (status = 'running' AND lease_expires_at <= ?)
                )
                ORDER BY CASE target_id
                    WHEN 'n26_greenhouse' THEN 0
                    WHEN 'qonto_lever' THEN 1
                    ELSE 2
                END, created_at, task_id
                LIMIT 1
                """,
                (cycle_id, now),
            ).fetchone()
            if row is None:
                return None
            task_id = str(row["task_id"])
            connection.execute(
                """
                UPDATE acquisition_tasks
                SET status='running', attempt_count=attempt_count+1, lease_owner=?,
                    lease_expires_at=?, started_at=?, updated_at=?
                WHERE task_id = ?
                """,
                (lease_owner, lease_expires, now, now, task_id),
            )
            updated = connection.execute("SELECT * FROM acquisition_tasks WHERE task_id = ?", (task_id,)).fetchone()
            return _dict_row(updated)

        return self._run_transaction(claim)

    def reserve_request(
        self,
        *,
        cycle_id: str,
        task_id: str,
        target_id: str,
        request_url: str,
        method: str = "GET",
        mode: str = "direct",
        request_kind: str = "listing",
        idempotency_key: str,
        credits_estimated: int = 0,
        request_limit: int = 0,
        credit_limit: int = 0,
    ) -> dict[str, Any]:
        now = utc_now_iso()

        def reserve(connection):
            existing = connection.execute(
                "SELECT * FROM acquisition_requests WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                return _dict_row(existing)
            request_id = f"acq_request_{uuid4().hex}"
            connection.execute(
                """
                INSERT INTO acquisition_requests (
                    request_id, idempotency_key, cycle_id, task_id, target_id,
                    request_url, method, mode, request_kind, status,
                    credits_estimated, started_at, dispatch_started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'dispatching', ?, ?, '')
                """,
                (
                    request_id,
                    idempotency_key,
                    cycle_id,
                    task_id,
                    target_id,
                    request_url,
                    method,
                    mode,
                    request_kind,
                    max(0, int(credits_estimated)),
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO acquisition_budget_reservations (
                    reservation_id, idempotency_key, cycle_id, task_id, target_id,
                    request_limit, credit_limit, requests_reserved, credits_reserved,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, 'reserved', ?)
                """,
                (
                    f"acq_reservation_{uuid4().hex}",
                    idempotency_key,
                    cycle_id,
                    task_id,
                    target_id,
                    max(0, int(request_limit)),
                    max(0, int(credit_limit)),
                    max(0, int(credits_estimated)),
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE acquisition_cycles
                SET reserved_requests=reserved_requests+1,
                    reserved_credits=reserved_credits+?, updated_at=?
                WHERE cycle_id = ?
                """,
                (max(0, int(credits_estimated)), now, cycle_id),
            )
            row = connection.execute(
                "SELECT * FROM acquisition_requests WHERE request_id = ?", (request_id,)
            ).fetchone()
            return _dict_row(row)

        return self._run_transaction(reserve)

    def mark_request_dispatching(self, request_id: str) -> None:
        """Durably mark the exact point at which the external call is about to start."""

        now = utc_now_iso()
        with self._connect() as connection:
            updated = connection.execute(
                """
                UPDATE acquisition_requests
                SET status='dispatching', dispatch_started_at=?
                WHERE request_id=? AND completed_at=''
                """,
                (now, request_id),
            )
            if updated.rowcount != 1:
                raise KeyError(f"Acquisition request '{request_id}' is not dispatchable.")

    def complete_request(
        self,
        request_id: str,
        *,
        status: str,
        provider_status: int = 0,
        credits_actual: int = 0,
        jobs_returned: int = 0,
        resolved_url: str = "",
        latency_ms: int = 0,
        detail: Mapping[str, Any] | None = None,
        error_code: str = "",
        error_message: str = "",
        recovery_state: str = "",
        uncertain_external_outcome: bool = False,
    ) -> None:
        now = utc_now_iso()

        def complete(connection):
            row = connection.execute(
                "SELECT * FROM acquisition_requests WHERE request_id = ?", (request_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Acquisition request '{request_id}' not found.")
            if str(row["completed_at"] or ""):
                return
            actual = max(0, int(credits_actual))
            connection.execute(
                """
                UPDATE acquisition_requests
                SET status=?, provider_status=?, credits_actual=?, jobs_returned=?,
                    resolved_url=?, latency_ms=?, detail_json=?, completed_at=?, error_code=?, error_message=?,
                    recovery_state=?, uncertain_external_outcome=?
                WHERE request_id = ?
                """,
                (
                    status,
                    int(provider_status or 0),
                    actual,
                    max(0, int(jobs_returned)),
                    str(resolved_url or ""),
                    max(0, int(latency_ms or 0)),
                    _json(dict(detail or {})),
                    now,
                    error_code,
                    error_message,
                    recovery_state,
                    int(bool(uncertain_external_outcome)),
                    request_id,
                ),
            )
            reservation_status = {
                "completed": "reconciled",
                "uncertain": "uncertain",
                "blocked": "blocked",
            }.get(str(status), "failed")
            reconciled_at = "" if reservation_status == "uncertain" else now
            connection.execute(
                """
                UPDATE acquisition_budget_reservations
                SET requests_actual=1, credits_actual=?, status=?, reconciled_at=?
                WHERE idempotency_key = ?
                """,
                (actual, reservation_status, reconciled_at, str(row["idempotency_key"])),
            )
            connection.execute(
                """
                UPDATE acquisition_cycles
                SET actual_requests=actual_requests+1, actual_credits=actual_credits+?, updated_at=?
                WHERE cycle_id = ?
                """,
                (actual, now, str(row["cycle_id"])),
            )

        self._run_transaction(complete)

    def record_job_rejections(
        self,
        *,
        request_id: str,
        cycle_id: str,
        task_id: str,
        target_id: str,
        rejections: Iterable[Mapping[str, Any]],
        observed_at: str = "",
    ) -> None:
        """Persist every source record rejected before canonical ingestion."""

        now = str(observed_at or utc_now_iso())
        rows = [dict(item) for item in rejections]
        if not rows:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO acquisition_job_rejections (
                    rejection_id, request_id, cycle_id, task_id, target_id,
                    external_job_id, title, reason_code, observed_at, detail_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        f"acq_rejection_{uuid4().hex}",
                        request_id,
                        cycle_id,
                        task_id,
                        target_id,
                        str(item.get("external_job_id") or ""),
                        str(item.get("title") or ""),
                        str(item.get("reason") or "unknown_rejection"),
                        now,
                        _json(item),
                    )
                    for item in rows
                ],
            )

    def recover_dispatching_requests(self) -> list[dict[str, Any]]:
        """Convert abandoned pre-dispatch rows into explicit uncertain outcomes."""

        now = utc_now_iso()

        def recover(connection):
            rows = connection.execute(
                """
                SELECT * FROM acquisition_requests
                WHERE status IN ('dispatching', 'sent') AND completed_at=''
                ORDER BY started_at, request_id
                """
            ).fetchall()
            recovered: list[dict[str, Any]] = []
            for row in rows:
                payload = _dict_row(row)
                request_id = str(payload["request_id"])
                cycle_id = str(payload["cycle_id"])
                task_id = str(payload["task_id"])
                connection.execute(
                    """
                    UPDATE acquisition_requests
                    SET status='uncertain', completed_at=?, recovery_state='recovery_required',
                        uncertain_external_outcome=1, error_code='uncertain_external_outcome',
                        error_message='Worker stopped after durable dispatch state; external outcome is unknown.'
                    WHERE request_id=? AND completed_at=''
                    """,
                    (now, request_id),
                )
                connection.execute(
                    """
                    UPDATE acquisition_budget_reservations
                    SET requests_actual=1, status='uncertain', reconciled_at=''
                    WHERE idempotency_key=?
                    """,
                    (str(payload["idempotency_key"]),),
                )
                connection.execute(
                    """
                    UPDATE acquisition_cycles
                    SET status='recovery_required', actual_requests=actual_requests+1,
                        lease_owner='', lease_expires_at='', completed_at=?,
                        error_code='uncertain_external_outcome',
                        error_message='One or more acquisition requests require explicit recovery.', updated_at=?
                    WHERE cycle_id=?
                    """,
                    (now, now, cycle_id),
                )
                connection.execute(
                    """
                    UPDATE acquisition_tasks
                    SET status='recovery_required', completed_at=?, lease_owner='', lease_expires_at='',
                        error_code='uncertain_external_outcome',
                        error_message='External acquisition may have occurred; explicit recovery is required.', updated_at=?
                    WHERE task_id=?
                    """,
                    (now, now, task_id),
                )
                updated = connection.execute(
                    "SELECT * FROM acquisition_requests WHERE request_id=?", (request_id,)
                ).fetchone()
                recovered.append(self._request_payload(_dict_row(updated)))
            return recovered

        return self._run_transaction(recover)

    def decide_uncertain_request(
        self,
        request_id: str,
        *,
        decision: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Release an uncertain reservation or explicitly authorize one bounded retry."""

        normalized = str(decision or "").strip().casefold()
        if normalized not in {"release", "retry"}:
            raise ValueError("Uncertain request decision must be 'release' or 'retry'.")
        if normalized == "release" and not str(reason or "").strip():
            raise ValueError("A release decision requires an audit reason.")
        now = utc_now_iso()

        def decide(connection):
            row = connection.execute(
                "SELECT * FROM acquisition_requests WHERE request_id=? AND status='uncertain'",
                (request_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Uncertain acquisition request '{request_id}' not found.")
            payload = _dict_row(row)
            cycle_id = str(payload["cycle_id"])
            task_id = str(payload["task_id"])
            target_id = str(payload["target_id"])
            if normalized == "release":
                connection.execute(
                    """
                    UPDATE acquisition_requests
                    SET status='reconciled_unknown', recovery_state='released_without_retry',
                        error_code='released_without_retry', error_message=?
                    WHERE request_id=?
                    """,
                    (str(reason)[:500], request_id),
                )
                connection.execute(
                    """
                    UPDATE acquisition_budget_reservations
                    SET status='released', reconciled_at=?
                    WHERE idempotency_key=?
                    """,
                    (now, str(payload["idempotency_key"])),
                )
                connection.execute(
                    """
                    UPDATE acquisition_tasks
                    SET status='reconciled_unknown', error_code='released_without_retry',
                        error_message=?, updated_at=? WHERE task_id=?
                    """,
                    (str(reason)[:500], now, task_id),
                )
                unresolved = connection.execute(
                    "SELECT COUNT(*) AS count FROM acquisition_requests WHERE cycle_id=? AND status='uncertain'",
                    (cycle_id,),
                ).fetchone()["count"]
                if int(unresolved or 0) == 0:
                    connection.execute(
                        """
                        UPDATE acquisition_cycles
                        SET status='partial', lease_owner='', lease_expires_at='', completed_at=?,
                            error_code='uncertain_request_released', error_message=?, updated_at=?
                        WHERE cycle_id=?
                        """,
                        (now, str(reason)[:500], now, cycle_id),
                    )
            else:
                target = connection.execute(
                    "SELECT max_direct_requests FROM acquisition_targets WHERE target_id=?", (target_id,)
                ).fetchone()
                limit = max(1, int(target["max_direct_requests"] or 1)) if target is not None else 1
                prior = connection.execute(
                    """
                    SELECT COUNT(*) AS count FROM acquisition_requests
                    WHERE cycle_id=? AND target_id=? AND status NOT IN ('reconciled_unknown', 'released')
                    """,
                    (cycle_id, target_id),
                ).fetchone()["count"]
                if int(prior or 0) >= limit:
                    raise RuntimeError("Explicit retry would exceed the target request ceiling.")
                connection.execute(
                    """
                    UPDATE acquisition_requests
                    SET status='retry_authorized', recovery_state='retry_authorized',
                        error_code='retry_authorized', error_message=?
                    WHERE request_id=?
                    """,
                    (str(reason or "Explicit bounded retry authorized")[:500], request_id),
                )
                connection.execute(
                    """
                    UPDATE acquisition_budget_reservations
                    SET status='retry_authorized'
                    WHERE idempotency_key=?
                    """,
                    (str(payload["idempotency_key"]),),
                )
                connection.execute(
                    """
                    UPDATE acquisition_tasks
                    SET status='pending', completed_at='', lease_owner='', lease_expires_at='',
                        error_code='retry_authorized', error_message=?, updated_at=? WHERE task_id=?
                    """,
                    (str(reason or "Explicit bounded retry authorized")[:500], now, task_id),
                )
                connection.execute(
                    """
                    UPDATE acquisition_cycles
                    SET status='running', lease_owner='', lease_expires_at='', completed_at='',
                        error_code='', error_message='', updated_at=? WHERE cycle_id=?
                    """,
                    (now, cycle_id),
                )
            updated = connection.execute(
                "SELECT * FROM acquisition_requests WHERE request_id=?", (request_id,)
            ).fetchone()
            return self._request_payload(_dict_row(updated))

        return self._run_transaction(decide)

    def ingest_snapshot(
        self,
        *,
        cycle_id: str,
        task_id: str,
        target_id: str,
        jobs: Iterable[Mapping[str, Any]],
        complete_snapshot: bool,
        valid_snapshot: bool,
        observed_at: str = "",
    ) -> dict[str, int | bool]:
        now = str(observed_at or utc_now_iso())
        job_rows = [dict(job) for job in jobs]

        def ingest(connection):
            target_row = connection.execute(
                "SELECT * FROM acquisition_targets WHERE target_id = ?", (target_id,)
            ).fetchone()
            if target_row is None:
                raise KeyError(f"Acquisition target '{target_id}' not found.")
            target = _dict_row(target_row)
            target_for_gate = {
                "target_id": target_id,
                "target_kind": str(target["target_kind"] or ""),
                "connector": str(target["connector"] or ""),
                "display_name": str(target["display_name"] or ""),
                "canonical_target_url": str(target["canonical_target_url"] or ""),
                "request_url": str(target["request_url"] or ""),
                "provenance_url": str(target["provenance_url"] or ""),
                "source_token": str(target["source_token"] or ""),
                "config": _decode(target["config_json"], {}),
            }
            applicant_gate = applicant_source_gate(target_for_gate)
            if is_portal_target(target_for_gate):
                audit = portal_audit_gate(target_for_gate)
                if not audit["approved"]:
                    raise ValueError(f"portal_audit_not_passed:{','.join(audit['missing'])}")
            seen_external: set[str] = set()
            counts = {
                "observed": 0,
                "new": 0,
                "updated": 0,
                "unchanged": 0,
                "closed": 0,
                "rejected": 0,
                "duplicates": 0,
                "applicant_snapshots_blocked": 0,
            }
            config = _decode(target.get("config_json"), {})
            absence_grace_attempts = max(
                1,
                int(
                    config.get("absence_grace_attempts")
                    or config.get("source_absence_grace_attempts")
                    or 3
                ),
            )
            target_payload = {**target_for_gate, "target_id": target_id}
            company_name = canonical_employer_name(target_payload) or source_employer_name(str(target["display_name"] or "")) or target_id
            entity_kind = "employer"
            company_id = self._ensure_company(
                connection,
                company_name,
                entity_kind,
                now,
                provenance_url=str(target.get("provenance_url") or ""),
                aliases=(str(target["display_name"] or ""), str(target["source_token"] or "")),
            )
            company_source: Mapping[str, Any] = {}
            configured_profile = config.get("company_profile") or config.get("company")
            if isinstance(configured_profile, Mapping):
                company_source = dict(configured_profile)
            else:
                for candidate in job_rows:
                    nested_company = candidate.get("company")
                    if isinstance(nested_company, Mapping):
                        company_source = dict(nested_company)
                        break
            self._ensure_company_profile(
                connection,
                company_id,
                company_source,
                now=now,
                provenance_url=str(target.get("provenance_url") or ""),
            )
            quality_events: list[dict[str, Any]] = []
            for raw_job in job_rows:
                raw_job = dict(raw_job)
                job = normalize_job_for_ingestion(raw_job, {**target_payload, "canonical_company_name": company_name})
                external_id = str(job.get("job_id") or job.get("external_job_id") or "").strip()
                title = str(job.get("title") or "").strip()
                original_url = str(job.get("job_detail_url") or job.get("url") or job.get("link") or job.get("source_url") or job.get("absolute_url") or "").strip()
                if not external_id or not title or not original_url:
                    counts["rejected"] += 1
                    continue
                if external_id in seen_external:
                    counts["duplicates"] += 1
                    continue
                seen_external.add(external_id)
                replay = connection.execute(
                    """
                    SELECT observation_id FROM job_source_observations
                    WHERE target_id=? AND cycle_id=? AND external_job_id=?
                    LIMIT 1
                    """,
                    (target_id, cycle_id, external_id),
                ).fetchone()
                if replay is not None:
                    # A replay is a no-op: do not create observations, versions,
                    # source aliases, or additional lifecycle transitions.
                    continue
                location_value = job.get("location") or job.get("location_raw") or ""
                if isinstance(location_value, Mapping):
                    location_value = location_value.get("name") or location_value.get("address") or ""
                location = str(location_value).strip()
                identity_key = self._identity_key(company_name, title, location, original_url)
                identity_signature = self._identity_signature(company_name, title, location)
                canonical = self._external_canonical(connection, target_id, external_id)
                if canonical is None:
                    canonical = self._find_existing_canonical(
                        connection,
                        identity_key=identity_key,
                        identity_signature=identity_signature,
                        original_url=original_url,
                        company_id=company_id,
                        title=title,
                        location=location,
                    )
                canonical_was_new = canonical is None
                reopened_from_closed = bool(canonical is not None and str(canonical["lifecycle_state"] or "") == "closed")
                if canonical is None:
                    canonical_id = f"canonical_job_{uuid4().hex}"
                    durable_identity_key = self._unique_identity_key(connection, identity_key)
                    connection.execute(
                        """
                        INSERT INTO canonical_jobs (
                            canonical_job_id, company_id, identity_key, title, location,
                            canonical_url, identity_signature, lifecycle_state, first_seen_at, last_seen_at,
                            last_verified_at, absence_count, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, 0, ?, ?)
                        """,
                        (
                            canonical_id,
                            company_id,
                            durable_identity_key,
                            title,
                            location,
                            original_url,
                            identity_signature,
                            now,
                            now,
                            now,
                            now,
                            now,
                        ),
                    )
                    counts["new"] += 1
                else:
                    canonical_id = str(canonical["canonical_job_id"])
                    previous_hash = self._current_content_hash(connection, canonical_id)
                    payload_hash = self._payload_hash(job)
                    if previous_hash and previous_hash != payload_hash:
                        counts["updated"] += 1
                    else:
                        counts["unchanged"] += 1
                    connection.execute(
                        """
                        UPDATE canonical_jobs
                        SET title=?, location=?, canonical_url=?, identity_signature=?, lifecycle_state='active',
                            last_seen_at=?, last_verified_at=?, absence_count=0, updated_at=?
                        WHERE canonical_job_id = ?
                        """,
                        (title, location, original_url, identity_signature, now, now, now, canonical_id),
                    )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO canonical_job_url_aliases (
                        alias_id, canonical_job_id, url, source, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (f"job_alias_{uuid4().hex}", canonical_id, original_url, target_id, now),
                )
                connection.execute(
                    """
                    INSERT INTO canonical_job_external_ids (
                        external_id_id, canonical_job_id, source_id, external_job_id,
                        first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id, external_job_id) DO UPDATE SET
                        canonical_job_id=excluded.canonical_job_id,
                        last_seen_at=excluded.last_seen_at
                    """,
                    (
                        f"external_id_{uuid4().hex}",
                        canonical_id,
                        target_id,
                        external_id,
                        now,
                        now,
                    ),
                )
                related = connection.execute(
                    """
                    SELECT canonical_job_id, lifecycle_state FROM canonical_jobs
                    WHERE company_id = ? AND title = ? AND location = ? AND canonical_job_id != ?
                    ORDER BY first_seen_at LIMIT 1
                    """,
                    (company_id, title, location, canonical_id),
                ).fetchone()
                if related is not None:
                    if canonical_was_new and str(related["lifecycle_state"] or "") == "closed":
                        connection.execute(
                            "UPDATE canonical_jobs SET lifecycle_state='reposted', updated_at=? WHERE canonical_job_id=?",
                            (now, canonical_id),
                        )
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO canonical_job_relationships (
                            relationship_id, canonical_job_id, related_job_id,
                            relationship_type, created_at
                        ) VALUES (?, ?, ?, 'repost', ?)
                        """,
                        (f"job_relationship_{uuid4().hex}", canonical_id, str(related["canonical_job_id"]), now),
                    )
                observation_id = f"observation_{uuid4().hex}"
                payload_hash = self._payload_hash(job)
                raw_content_hash = hashlib.sha256(_json(raw_job).encode("utf-8")).hexdigest()
                connection.execute(
                    """
                    INSERT OR IGNORE INTO job_source_observations (
                        observation_id, canonical_job_id, target_id, cycle_id, task_id,
                        external_job_id, original_url, apply_url, source_ats,
                        content_hash, payload_json, observed_at, active,
                        source_display_name, source_token, source_connector, application_url,
                        application_classification, quality_warnings_json
                        , raw_payload_json, raw_content_hash, rule_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observation_id,
                        canonical_id,
                        target_id,
                        cycle_id,
                        task_id,
                        external_id,
                        original_url,
                        str(job.get("apply_link") or original_url),
                        str(job.get("source_ats") or ""),
                        payload_hash,
                        _json(job),
                        now,
                        str(job.get("source_display_name") or target.get("display_name") or ""),
                        str(job.get("source_token") or target.get("source_token") or ""),
                        str(job.get("source_ats") or target.get("connector") or ""),
                        str(job.get("application_url") or ""),
                        str((job.get("application_destination") or {}).get("classification") if isinstance(job.get("application_destination"), Mapping) else "unknown"),
                        _json(list(job.get("quality_warnings") or [])),
                        _json(raw_job),
                        raw_content_hash,
                        str(job.get("unified_rule_version") or UNIFIED_RULE_VERSION),
                    ),
                )
                persisted_observation = connection.execute(
                    "SELECT observation_id FROM job_source_observations WHERE target_id=? AND cycle_id=? AND external_job_id=?",
                    (target_id, cycle_id, external_id),
                ).fetchone()
                observation_id = str(persisted_observation["observation_id"]) if persisted_observation else observation_id
                prior_observation = connection.execute(
                    """
                    SELECT observation_id, canonical_job_id, target_id
                    FROM job_source_observations
                    WHERE canonical_job_id=? AND target_id!=? AND observation_id!=?
                    ORDER BY observed_at DESC, observation_id DESC LIMIT 1
                    """,
                    (canonical_id, target_id, observation_id),
                ).fetchone()
                if prior_observation is not None:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO job_source_observation_relationships (
                            relationship_id, observation_id, related_observation_id,
                            relationship_type, created_at
                        ) VALUES (?, ?, ?, 'duplicate', ?)
                        """,
                        (
                            f"observation_relationship_{uuid4().hex}",
                            observation_id,
                            str(prior_observation["observation_id"]),
                            now,
                        ),
                    )
                    # Keep the cross-source duplicate relationship visible to
                    # administrators even though the public catalog has one
                    # canonical posting.  The self edge represents two source
                    # observations of the same canonical posting.
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO canonical_job_relationships (
                            relationship_id, canonical_job_id, related_job_id,
                            relationship_type, created_at
                        ) VALUES (?, ?, ?, 'duplicate', ?)
                        """,
                        (
                            f"job_duplicate_{uuid4().hex}",
                            canonical_id,
                            canonical_id,
                            now,
                        ),
                    )
                self._upsert_source_state(
                    connection,
                    target_id=target_id,
                    canonical_job_id=canonical_id,
                    external_job_id=external_id,
                    cycle_id=cycle_id,
                    observed_at=now,
                    grace_attempts=absence_grace_attempts,
                )
                # Publication-quality checks are shadow validation only. The
                # report is persisted with the version so no new quality
                # rule can block import, scraping, enrichment, or publication.
                job["quality_completeness"] = completeness_rules(
                    job=job,
                    company={"company_id": company_id, "name": company_name},
                    source={"target_id": target_id, "source_observation_ids": [observation_id], "external_job_id": external_id},
                    admin={"state": "staged"},
                )
                self._ensure_version(
                    connection,
                    canonical_id,
                    title=title,
                    description=str(job.get("description_text") or job.get("description") or job.get("full_description") or ""),
                    location=location,
                    # The version column is the verified direct destination;
                    # the source/detail fallback remains in payload_json and
                    # application_destination.user_facing_url.
                    apply_url=str(job.get("application_url") or ""),
                    content_hash=payload_hash,
                    source_observation_id=observation_id,
                    payload=job,
                    now=now,
                    force_new_version=reopened_from_closed,
                )
                self._persist_unified_mapping(
                    connection,
                    canonical_job_id=canonical_id,
                    company_id=company_id,
                    source_observation_id=observation_id,
                    execution_id=cycle_id,
                    mapping=job.get("unified_mapping") if isinstance(job.get("unified_mapping"), Mapping) else {},
                    job=job,
                    observed_at=now,
                )
                applicant_snapshot = normalize_applicant_snapshot(
                    job,
                    observed_at=now,
                    source_ats=str(job.get("source_ats") or ""),
                    provenance_url=original_url or str(target["provenance_url"] or ""),
                    first_seen_at=now if canonical_was_new else str(
                        connection.execute(
                            "SELECT first_seen_at FROM canonical_jobs WHERE canonical_job_id = ?",
                            (canonical_id,),
                        ).fetchone()["first_seen_at"]
                        or now
                    ),
                    last_verified_at=now,
                )
                if applicant_snapshot is not None and applicant_gate["approved"]:
                    self._ensure_applicant_snapshot(
                        connection,
                        canonical_job_id=canonical_id,
                        source_observation_id=observation_id,
                        snapshot=applicant_snapshot,
                        now=now,
                    )
                elif has_applicant_evidence(job):
                    counts["applicant_snapshots_blocked"] += 1
                counts["observed"] += 1
                for warning_code in job.get("quality_warnings") or []:
                    quality_events.append(
                        {
                            "canonical_job_id": canonical_id,
                            "company_id": company_id,
                            "employer_name": company_name,
                            "connector": str(target["connector"] or ""),
                            "source_token": str(target["source_token"] or ""),
                            "warning_code": str(warning_code),
                            "details": {"external_job_id": external_id},
                        }
                    )

                self._ensure_company_alias(
                    connection,
                    company_id,
                    str(job.get("company") or ""),
                    source=str(target["target_id"] or ""),
                    now=now,
                )

            if complete_snapshot and valid_snapshot:
                missing_rows = connection.execute(
                    """
                    SELECT source_state_id, canonical_job_id, external_job_id,
                           absence_count, grace_attempts
                    FROM job_source_states
                    WHERE target_id=? AND lifecycle_state IN ('active', 'stale', 'unknown')
                    """,
                    (target_id,),
                ).fetchall()
                affected: set[str] = set()
                for missing in missing_rows:
                    external_id = str(missing["external_job_id"] or "")
                    if external_id in seen_external:
                        continue
                    canonical_id = str(missing["canonical_job_id"])
                    absence_count = int(missing["absence_count"] or 0) + 1
                    grace = max(1, int(missing["grace_attempts"] or absence_grace_attempts))
                    lifecycle = "closed" if absence_count >= grace else "stale"
                    connection.execute(
                        """
                        UPDATE job_source_states
                        SET absence_count=?, lifecycle_state=?, last_checked_at=?,
                            last_cycle_id=?, updated_at=?
                        WHERE source_state_id=?
                        """,
                        (absence_count, lifecycle, now, cycle_id, now, str(missing["source_state_id"])),
                    )
                    affected.add(canonical_id)
                    if lifecycle == "closed":
                        counts["closed"] += 1
                for canonical_id in affected:
                    self._recompute_lifecycle(connection, canonical_id, now=now)
            elif not valid_snapshot:
                # A failed or incomplete source check is unknown, not an
                # absence.  Never close a posting from an unhealthy source.
                unknown_rows = connection.execute(
                    """
                    SELECT DISTINCT canonical_job_id FROM job_source_states
                    WHERE target_id=? AND lifecycle_state IN ('active', 'stale')
                    """,
                    (target_id,),
                ).fetchall()
                for row in unknown_rows:
                    connection.execute(
                        """
                        UPDATE job_source_states
                        SET lifecycle_state='unknown', last_checked_at=?,
                            last_cycle_id=?, updated_at=?
                        WHERE target_id=? AND canonical_job_id=?
                        """,
                        (now, cycle_id, now, target_id, str(row["canonical_job_id"])),
                    )
                    self._recompute_lifecycle(connection, str(row["canonical_job_id"]), now=now)
            for event in quality_events:
                self._record_quality_event(
                    connection,
                    cycle_id=cycle_id,
                    task_id=task_id,
                    target_id=target_id,
                    **event,
                )
            return {**counts, "valid_snapshot": bool(valid_snapshot), "complete_snapshot": bool(complete_snapshot), "quality_warnings": [item["warning_code"] for item in quality_events]}

        return self._run_transaction(ingest)

    @staticmethod
    def _ensure_applicant_snapshot(
        connection,
        *,
        canonical_job_id: str,
        source_observation_id: str,
        snapshot: Mapping[str, Any],
        now: str,
    ) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO job_applicant_snapshots (
                snapshot_id, canonical_job_id, source_observation_id, source_ats,
                applicant_count_exact, applicant_count_min, applicant_count_max,
                applicant_count_label, posting_time, first_seen_at, last_verified_at,
                observed_at, apply_method, easy_apply_marker, freshness_status,
                provenance_url, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"applicant_snapshot_{uuid4().hex}",
                canonical_job_id,
                source_observation_id,
                str(snapshot.get("source_ats") or ""),
                snapshot.get("exact"),
                snapshot.get("min"),
                snapshot.get("max"),
                str(snapshot.get("label") or ""),
                str(snapshot.get("posting_time") or ""),
                str(snapshot.get("first_seen_at") or ""),
                str(snapshot.get("last_verified_at") or ""),
                str(snapshot.get("observed_at") or now),
                str(snapshot.get("apply_method") or ""),
                int(bool(snapshot.get("easy_apply_marker"))),
                str(snapshot.get("freshness_status") or "unknown"),
                str(snapshot.get("provenance_url") or ""),
                _json(snapshot.get("payload") or {}),
                now,
            ),
        )

    def record_attempt(
        self,
        *,
        task_id: str,
        cycle_id: str,
        target_id: str,
        attempt_number: int,
        status: str,
        complete_snapshot: bool,
        valid_snapshot: bool,
        credible_evidence: bool,
        request_count: int,
        credits_actual: int,
        jobs_found: int,
        state_before: str,
        state_after: str,
        reason: str = "",
        error_code: str = "",
        error_message: str = "",
        started_at: str = "",
        completed_at: str = "",
    ) -> None:
        started = str(started_at or utc_now_iso())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO acquisition_target_attempts (
                    attempt_id, task_id, cycle_id, target_id, attempt_number, status,
                    complete_snapshot, valid_snapshot, credible_evidence, request_count,
                    credits_actual, jobs_found, state_before, state_after, reason,
                    error_code, error_message, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"acq_attempt_{uuid4().hex}",
                    task_id,
                    cycle_id,
                    target_id,
                    max(1, int(attempt_number)),
                    status,
                    int(complete_snapshot),
                    int(valid_snapshot),
                    int(credible_evidence),
                    max(0, int(request_count)),
                    max(0, int(credits_actual)),
                    max(0, int(jobs_found)),
                    state_before,
                    state_after,
                    reason,
                    error_code,
                    error_message,
                    started,
                    str(completed_at or utc_now_iso()),
                ),
            )

    def complete_task(
        self, task_id: str, *, status: str, result: Mapping[str, Any], error_code: str = "", error_message: str = ""
    ) -> None:
        now = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE acquisition_tasks
                SET status=?, completed_at=?, complete_snapshot=?, valid_snapshot=?, credible_evidence=?,
                    requests_avoided=?, credits_avoided=?, jobs_observed=?, jobs_new=?, jobs_updated=?,
                    jobs_unchanged=?, jobs_closed=?, jobs_rejected=?, jobs_duplicates=?,
                    jobs_published=COALESCE(?, jobs_published),
                    reconciliation_json=?, quality_warnings_json=?,
                    error_code=?, error_message=?, updated_at=?
                WHERE task_id = ?
                """,
                (
                    status,
                    now,
                    int(bool(result.get("complete_snapshot"))),
                    int(bool(result.get("valid_snapshot"))),
                    int(bool(result.get("credible_evidence"))),
                    max(0, int(result.get("requests_avoided") or 0)),
                    max(0, int(result.get("credits_avoided") or 0)),
                    max(0, int(result.get("observed") or 0)),
                    max(0, int(result.get("new") or 0)),
                    max(0, int(result.get("updated") or 0)),
                    max(0, int(result.get("unchanged") or 0)),
                    max(0, int(result.get("closed") or 0)),
                    max(0, int(result.get("rejected") or 0)),
                    max(0, int(result.get("duplicates") or 0)),
                    (max(0, int(result.get("jobs_published") or 0)) if "jobs_published" in result else None),
                    _json(result.get("reconciliation") or {}),
                    _json(list(result.get("quality_warnings") or [])),
                    error_code,
                    error_message,
                    now,
                    task_id,
                ),
            )

    def complete_cycle(
        self, cycle_id: str, *, status: str, error_code: str = "", error_message: str = "", publication_id: str = ""
    ) -> None:
        now = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE acquisition_cycles
                SET status=?, lease_owner='', lease_expires_at='', completed_at=?,
                    publication_id=?, error_code=?, error_message=?,
                    jobs_observed=(SELECT COALESCE(SUM(jobs_observed),0) FROM acquisition_tasks WHERE cycle_id=?),
                    jobs_new=(SELECT COALESCE(SUM(jobs_new),0) FROM acquisition_tasks WHERE cycle_id=?),
                    jobs_updated=(SELECT COALESCE(SUM(jobs_updated),0) FROM acquisition_tasks WHERE cycle_id=?),
                    jobs_unchanged=(SELECT COALESCE(SUM(jobs_unchanged),0) FROM acquisition_tasks WHERE cycle_id=?),
                    jobs_closed=(SELECT COALESCE(SUM(jobs_closed),0) FROM acquisition_tasks WHERE cycle_id=?),
                    jobs_rejected=(SELECT COALESCE(SUM(jobs_rejected),0) FROM acquisition_tasks WHERE cycle_id=?),
                    jobs_duplicates=(SELECT COALESCE(SUM(jobs_duplicates),0) FROM acquisition_tasks WHERE cycle_id=?),
                    updated_at=?
                WHERE cycle_id=?
                """,
                (
                    status,
                    now,
                    publication_id,
                    error_code,
                    error_message,
                    cycle_id,
                    cycle_id,
                    cycle_id,
                    cycle_id,
                    cycle_id,
                    cycle_id,
                    cycle_id,
                    now,
                    cycle_id,
                ),
            )

    def publish_valid_snapshot(self, *, cycle_id: str, valid_target_ids: Iterable[str], valid_until: str = "") -> str:
        target_ids = tuple(str(item) for item in valid_target_ids if str(item).strip())
        if not target_ids:
            return ""
        now = utc_now_iso()
        publication_id = f"acq_publication_{uuid4().hex}"

        def publish(connection):
            existing = connection.execute(
                "SELECT publication_id FROM acquisition_publications WHERE cycle_id = ? LIMIT 1",
                (cycle_id,),
            ).fetchone()
            if existing is not None:
                existing_id = str(existing["publication_id"])
                published_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM acquisition_publication_jobs WHERE publication_id = ?",
                    (existing_id,),
                ).fetchone()["count"]
                connection.execute(
                    """
                    INSERT INTO acquisition_publication_head (head_id, publication_id, updated_at)
                    VALUES (1, ?, ?)
                    ON CONFLICT(head_id) DO UPDATE SET publication_id=excluded.publication_id, updated_at=excluded.updated_at
                    """,
                    (existing_id, now),
                )
                connection.execute(
                    "UPDATE acquisition_cycles SET jobs_published = ?, publication_id = ?, updated_at = ? WHERE cycle_id = ?",
                    (int(published_count or 0), existing_id, now, cycle_id),
                )
                return existing_id
            placeholders = ",".join("?" for _ in target_ids)
            rows = connection.execute(
                f"""
                SELECT DISTINCT j.canonical_job_id, c.canonical_name AS company,
                                j.title, j.location, j.canonical_url,
                                COALESCE(v.apply_url, '') AS apply_url,
                                j.lifecycle_state, j.current_version_id
                FROM canonical_jobs j
                JOIN canonical_companies c ON c.company_id = j.company_id
                LEFT JOIN job_posting_versions v ON v.version_id = j.current_version_id
                WHERE j.lifecycle_state != 'closed'
                  AND (
                    EXISTS (
                        SELECT 1 FROM job_source_observations o
                        WHERE o.canonical_job_id = j.canonical_job_id
                          AND o.target_id IN ({placeholders}) AND o.cycle_id = ?
                    )
                    OR EXISTS (
                        SELECT 1 FROM acquisition_publication_jobs previous_jobs
                        WHERE previous_jobs.canonical_job_id = j.canonical_job_id
                          AND previous_jobs.publication_id = (
                              SELECT publication_id FROM acquisition_publication_head WHERE head_id=1
                          )
                    )
                  )
                ORDER BY j.title, j.canonical_job_id
                """,
                (*target_ids, cycle_id),
            ).fetchall()
            snapshot = [_dict_row(row) for row in rows]
            connection.execute(
                """
                INSERT INTO acquisition_publications (
                    publication_id, cycle_id, status, snapshot_json, published_at, valid_until
                ) VALUES (?, ?, 'valid', ?, ?, ?)
                """,
                (publication_id, cycle_id, _json(snapshot), now, str(valid_until or "")),
            )
            connection.executemany(
                "INSERT INTO acquisition_publication_jobs (publication_id, canonical_job_id) VALUES (?, ?)",
                [(publication_id, str(row["canonical_job_id"])) for row in rows],
            )
            connection.execute(
                """
                INSERT INTO acquisition_publication_head (head_id, publication_id, updated_at)
                VALUES (1, ?, ?)
                ON CONFLICT(head_id) DO UPDATE SET publication_id=excluded.publication_id, updated_at=excluded.updated_at
                """,
                (publication_id, now),
            )
            connection.execute(
                "UPDATE acquisition_cycles SET jobs_published = ?, publication_id = ?, updated_at = ? WHERE cycle_id = ?",
                (len(rows), publication_id, now, cycle_id),
            )
            for target_id in target_ids:
                target_published = connection.execute(
                    """
                    SELECT COUNT(DISTINCT pj.canonical_job_id) AS count
                    FROM acquisition_publication_jobs pj
                    JOIN job_source_observations o ON o.canonical_job_id = pj.canonical_job_id
                    WHERE pj.publication_id = ? AND o.target_id = ? AND o.cycle_id = ?
                    """,
                    (publication_id, target_id, cycle_id),
                ).fetchone()["count"]
                connection.execute(
                    "UPDATE acquisition_tasks SET jobs_published = ?, updated_at = ? WHERE cycle_id = ? AND target_id = ?",
                    (int(target_published or 0), now, cycle_id, target_id),
                )
            return publication_id

        return self._run_transaction(publish)

    def publish_staging_snapshot(
        self,
        *,
        cycle_id: str,
        valid_target_ids: Iterable[str],
        valid_until: str = "",
    ) -> str:
        """Create a non-public publication candidate; do not move the public head."""

        target_ids = tuple(str(item) for item in valid_target_ids if str(item).strip())
        if not target_ids:
            return ""
        now = utc_now_iso()
        publication_id = f"acq_staging_{uuid4().hex}"

        def publish(connection):
            placeholders = ",".join("?" for _ in target_ids)
            rows = connection.execute(
                f"""
                SELECT DISTINCT j.canonical_job_id, c.canonical_name AS company,
                                j.title, j.location, j.canonical_url,
                                COALESCE(v.apply_url, '') AS apply_url,
                                j.lifecycle_state, j.current_version_id
                FROM canonical_jobs j
                JOIN canonical_companies c ON c.company_id = j.company_id
                LEFT JOIN job_posting_versions v ON v.version_id = j.current_version_id
                JOIN job_source_observations o ON o.canonical_job_id = j.canonical_job_id
                WHERE o.target_id IN ({placeholders}) AND o.cycle_id = ?
                  AND j.lifecycle_state IN ('active', 'stale', 'reposted')
                ORDER BY j.title, j.canonical_job_id
                """,
                (*target_ids, cycle_id),
            ).fetchall()
            snapshot = [_dict_row(row) for row in rows]
            connection.execute(
                """
                INSERT INTO acquisition_publications (
                    publication_id, cycle_id, status, snapshot_json, published_at, valid_until
                ) VALUES (?, ?, 'staging', ?, ?, ?)
                """,
                (publication_id, cycle_id, _json(snapshot), now, str(valid_until or "")),
            )
            connection.executemany(
                "INSERT INTO acquisition_publication_jobs (publication_id, canonical_job_id) VALUES (?, ?)",
                [(publication_id, str(row["canonical_job_id"])) for row in rows],
            )
            connection.execute(
                "UPDATE acquisition_cycles SET jobs_published=?, updated_at=? WHERE cycle_id=?",
                (len(rows), now, cycle_id),
            )
            for target_id in target_ids:
                target_published = connection.execute(
                    """
                    SELECT COUNT(DISTINCT pj.canonical_job_id) AS count
                    FROM acquisition_publication_jobs pj
                    JOIN job_source_observations o ON o.canonical_job_id = pj.canonical_job_id
                    WHERE pj.publication_id=? AND o.target_id=? AND o.cycle_id=?
                    """,
                    (publication_id, target_id, cycle_id),
                ).fetchone()["count"]
                connection.execute(
                    "UPDATE acquisition_tasks SET jobs_published=?, updated_at=? WHERE cycle_id=? AND target_id=?",
                    (int(target_published or 0), now, cycle_id, target_id),
                )
            return publication_id

        return self._run_transaction(publish)

    def get_staging_catalog(self, *, publication_id: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
        with self._connect() as connection:
            if publication_id:
                publication = connection.execute(
                    "SELECT publication_id, cycle_id, status, published_at, valid_until, snapshot_json "
                    "FROM acquisition_publications WHERE publication_id=? AND status='staging'",
                    (publication_id,),
                ).fetchone()
            else:
                publication = connection.execute(
                    "SELECT publication_id, cycle_id, status, published_at, valid_until, snapshot_json "
                    "FROM acquisition_publications WHERE status='staging' ORDER BY published_at DESC LIMIT 1"
                ).fetchone()
        if publication is None:
            return {"jobs": [], "total": 0, "publication": None, "freshness": "unpublished"}
        snapshot = _decode(publication["snapshot_json"], [])
        jobs = snapshot if isinstance(snapshot, list) else []
        start = max(0, int(offset))
        page = jobs[start : start + max(1, int(limit))]
        return {
            "jobs": page,
            "total": len(jobs),
            "publication": {
                "publication_id": str(publication["publication_id"] or ""),
                "cycle_id": str(publication["cycle_id"] or ""),
                "status": str(publication["status"] or "staging"),
                "published_at": str(publication["published_at"] or ""),
                "valid_until": str(publication["valid_until"] or ""),
            },
            "freshness": "staging",
        }

    def promote_staging_publication(self, publication_id: str) -> str:
        """Move one reviewed staging snapshot to the public valid head."""

        now = utc_now_iso()

        def promote(connection):
            row = connection.execute(
                "SELECT publication_id, status FROM acquisition_publications WHERE publication_id=?",
                (publication_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Staging publication '{publication_id}' not found.")
            if str(row["status"] or "") != "staging":
                raise ValueError("Only a staging publication can be promoted.")
            previous = connection.execute(
                "SELECT publication_id FROM acquisition_publication_head WHERE head_id=1"
            ).fetchone()
            previous_id = str(previous["publication_id"] or "") if previous is not None else ""
            connection.execute(
                "UPDATE acquisition_publications SET status='valid', previous_publication_id=? WHERE publication_id=?",
                (previous_id, publication_id),
            )
            connection.execute(
                """
                INSERT INTO acquisition_publication_head (head_id, publication_id, updated_at)
                VALUES (1, ?, ?)
                ON CONFLICT(head_id) DO UPDATE SET publication_id=excluded.publication_id,
                    updated_at=excluded.updated_at
                """,
                (publication_id, now),
            )
            return publication_id

        return self._run_transaction(promote)

    def list_cycles(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM acquisition_cycles ORDER BY scheduled_at DESC LIMIT ? OFFSET ?",
                (max(1, int(limit)), max(0, int(offset))),
            ).fetchall()
        return [_dict_row(row) for row in rows]

    def get_cycle(self, cycle_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM acquisition_cycles WHERE cycle_id = ?", (cycle_id,)).fetchone()
        if row is None:
            raise KeyError(f"Acquisition cycle '{cycle_id}' not found.")
        return _dict_row(row)

    def list_cycle_targets(self, cycle_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT t.*, a.task_id, a.status AS task_status, a.attempt_count,
                       a.complete_snapshot, a.valid_snapshot, a.credible_evidence,
                       a.requests_avoided, a.credits_avoided, a.jobs_observed,
                       a.jobs_new, a.jobs_updated, a.jobs_unchanged, a.jobs_closed,
                       a.jobs_rejected, a.jobs_duplicates, a.jobs_published, a.error_code AS task_error_code,
                       a.error_message AS task_error_message
                FROM acquisition_tasks a
                JOIN acquisition_targets t ON t.target_id = a.target_id
                WHERE a.cycle_id = ?
                ORDER BY t.target_kind, t.display_name
                """,
                (cycle_id,),
            ).fetchall()
            request_rows = connection.execute(
                "SELECT * FROM acquisition_requests WHERE cycle_id = ? ORDER BY started_at, request_id",
                (cycle_id,),
            ).fetchall()
        requests_by_target: dict[str, list[dict[str, Any]]] = {}
        for row in request_rows:
            payload = _dict_row(row)
            requests_by_target.setdefault(str(payload["target_id"]), []).append(payload)
        result = []
        for row in rows:
            payload = self._target_payload(_dict_row(row))
            target_requests = requests_by_target.get(str(payload["target_id"]), [])
            payload["task"] = {
                key: payload.pop(key)
                for key in list(payload)
                if key.startswith("task_")
                or key
                in {
                    "attempt_count",
                    "complete_snapshot",
                    "valid_snapshot",
                    "credible_evidence",
                    "requests_avoided",
                    "credits_avoided",
                    "jobs_observed",
                    "jobs_new",
                    "jobs_updated",
                    "jobs_unchanged",
                    "jobs_closed",
                    "jobs_rejected",
                    "jobs_duplicates",
                    "jobs_published",
                }
            }
            payload["task"]["reconciliation"] = _decode(payload["task"].pop("task_reconciliation_json", "{}"), {})
            payload["task"]["quality_warnings"] = _decode(payload["task"].pop("task_quality_warnings_json", "[]"), [])
            payload["requests"] = [self._request_payload(item) for item in target_requests]
            payload["detail_requests"] = payload["requests"]
            payload["requested_urls"] = [item["request_url"] for item in payload["requests"]]
            payload["request_count"] = len(payload["requests"])
            payload["redirect_count"] = sum(
                1 for item in payload["requests"] if bool((item.get("detail") or {}).get("redirected"))
            )
            payload["redirects"] = payload["redirect_count"]
            payload["request_modes"] = sorted({str(item.get("mode") or "direct") for item in payload["requests"]})
            payload["direct_proxy_mode"] = (
                payload["request_modes"][0] if len(payload["request_modes"]) == 1 else payload["request_modes"]
            )
            payload["reserved_credits"] = sum(int(item.get("credits_estimated") or 0) for item in payload["requests"])
            payload["actual_credits"] = sum(int(item.get("credits_actual") or 0) for item in payload["requests"])
            payload["jobs_per_request"] = (
                round(int(payload["task"].get("jobs_observed") or 0) / len(payload["requests"]), 2)
                if payload["requests"]
                else 0
            )
            payload["new_jobs_per_request"] = (
                round(int(payload["task"].get("jobs_new") or 0) / len(payload["requests"]), 2)
                if payload["requests"]
                else 0
            )
            for count_key in (
                "jobs_observed",
                "jobs_new",
                "jobs_updated",
                "jobs_unchanged",
                "jobs_closed",
                "jobs_rejected",
                "jobs_duplicates",
            ):
                payload[count_key] = int(payload["task"].get(count_key) or 0)
            payload["avoided_requests"] = int(payload["task"].get("requests_avoided") or 0)
            payload["avoided_credits"] = int(payload["task"].get("credits_avoided") or 0)
            payload["jobs_published"] = int(payload["task"].get("jobs_published") or 0)
            payload["valid_empty"] = bool(payload["task"].get("valid_snapshot")) and payload["jobs_observed"] == 0
            payload["failed_empty"] = not bool(payload["task"].get("valid_snapshot")) and payload["jobs_observed"] == 0
            payload["cost_per_new_publication"] = (
                round(payload["actual_credits"] / payload["jobs_new"], 2) if payload["jobs_new"] else 0
            )
            payload["yield_per_request"] = round(
                payload["jobs_observed"] / payload["request_count"], 2
            ) if payload["request_count"] else 0
            payload["cost_per_produced_job"] = round(
                payload["actual_credits"] / payload["jobs_observed"], 2
            ) if payload["jobs_observed"] else 0
            payload["last_productive_at"] = str(payload.get("last_success_at") or "")
            payload["consecutive_zero_yield_attempts"] = int(payload.get("zero_yield_streak") or 0)
            payload["productivity_timestamp"] = (
                payload.get("last_success_at") if payload.get("maturity_state") == "productive" else ""
            )
            payload["failure_reason"] = str(
                payload.get("task", {}).get("task_error_message") or payload.get("state_transition_reason") or ""
            )
            payload["freshness_status"] = self._freshness_status(payload.get("last_success_at"))
            result.append(payload)
        return result

    def get_cycle_source_metrics(self, cycle_id: str) -> list[dict[str, Any]]:
        """Report yield and reconciled cost for every requested source URL."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT r.target_id, r.request_url,
                       COUNT(*) AS request_count,
                       SUM(r.credits_actual) AS actual_credits,
                       SUM(r.jobs_returned) AS raw_jobs_returned,
                       SUM(r.credits_estimated) AS reserved_credits,
                       MAX(t.jobs_observed) AS jobs_observed,
                       MAX(t.jobs_new) AS jobs_new,
                       MAX(t.jobs_updated) AS jobs_updated,
                       MAX(t.jobs_rejected) AS jobs_rejected,
                       MAX(t.jobs_closed) AS jobs_closed,
                       MAX(t.jobs_duplicates) AS jobs_duplicates,
                       MAX(t.jobs_published) AS jobs_published
                FROM acquisition_requests r
                JOIN acquisition_tasks t ON t.task_id = r.task_id
                WHERE r.cycle_id = ?
                GROUP BY r.target_id, r.request_url
                ORDER BY r.target_id, r.request_url
                """,
                (cycle_id,),
            ).fetchall()
            redirect_rows = connection.execute(
                """
                SELECT target_id, request_url, COUNT(*) AS count
                FROM acquisition_requests
                WHERE cycle_id=? AND detail_json LIKE '%\"redirected\":true%'
                GROUP BY target_id, request_url
                """,
                (cycle_id,),
            ).fetchall()
        redirect_counts = {
            (str(row["target_id"]), str(row["request_url"])): int(row["count"] or 0)
            for row in redirect_rows
        }
        metrics = []
        for row in rows:
            payload = _dict_row(row)
            actual_credits = int(payload.get("actual_credits") or 0)
            jobs_new = int(payload.get("jobs_new") or 0)
            payload.update(
                {
                    "request_count": int(payload.get("request_count") or 0),
                    "actual_credits": actual_credits,
                    "reserved_credits": int(payload.get("reserved_credits") or 0),
                    "raw_jobs_returned": int(payload.get("raw_jobs_returned") or 0),
                    "jobs_observed": int(payload.get("jobs_observed") or 0),
                    "jobs_new": jobs_new,
                    "jobs_updated": int(payload.get("jobs_updated") or 0),
                    "jobs_rejected": int(payload.get("jobs_rejected") or 0),
                    "jobs_closed": int(payload.get("jobs_closed") or 0),
                    "jobs_duplicates": int(payload.get("jobs_duplicates") or 0),
                    "jobs_published": int(payload.get("jobs_published") or 0),
                    "cost_per_new_job": round(actual_credits / jobs_new, 2) if jobs_new else 0,
                    "cost_per_new_published_job": round(
                        actual_credits / int(payload.get("jobs_published") or 0), 2
                    )
                    if int(payload.get("jobs_published") or 0)
                    else 0,
                    "yield_per_request": round(
                        int(payload.get("jobs_observed") or 0) / int(payload.get("request_count") or 1), 2
                    ),
                    "cost_per_produced_job": round(
                        actual_credits / int(payload.get("jobs_observed") or 0), 2
                    ) if int(payload.get("jobs_observed") or 0) else 0,
                }
            )
            payload["redirect_count"] = redirect_counts.get(
                (str(payload.get("target_id") or ""), str(payload.get("request_url") or "")), 0
            )
            metrics.append(payload)
        return metrics

    def get_cycle_report(self, cycle_id: str) -> dict[str, Any]:
        cycle = self.get_cycle(cycle_id)
        targets = self.list_cycle_targets(cycle_id)
        source_metrics = self.get_cycle_source_metrics(cycle_id)
        with self._connect() as connection:
            request_counts = connection.execute(
                """
                SELECT
                    SUM(CASE WHEN status='uncertain' THEN 1 ELSE 0 END) AS uncertain,
                    SUM(CASE WHEN status IN ('dispatching', 'sent') AND completed_at='' THEN 1 ELSE 0 END) AS dispatching
                FROM acquisition_requests WHERE cycle_id=?
                """,
                (cycle_id,),
            ).fetchone()
            last_publication = connection.execute(
                """
                SELECT publication_id, cycle_id, status, published_at, valid_until
                FROM acquisition_publications
                WHERE status = 'valid'
                ORDER BY published_at DESC
                LIMIT 1
                """
            ).fetchone()
            rejection_rows = connection.execute(
                """
                SELECT reason_code, COUNT(*) AS count
                FROM acquisition_job_rejections
                WHERE cycle_id=?
                GROUP BY reason_code ORDER BY reason_code
                """,
                (cycle_id,),
            ).fetchall()
            redirect_count = connection.execute(
                """
                SELECT COUNT(*) AS count FROM acquisition_requests
                WHERE cycle_id=? AND detail_json LIKE '%\"redirected\":true%'
                """,
                (cycle_id,),
            ).fetchone()
            mode_rows = connection.execute(
                "SELECT mode, COUNT(*) AS count FROM acquisition_requests WHERE cycle_id=? GROUP BY mode",
                (cycle_id,),
            ).fetchall()
        rejection_reasons = {str(row["reason_code"]): int(row["count"] or 0) for row in rejection_rows}
        mode_counts = {str(row["mode"] or "direct"): int(row["count"] or 0) for row in mode_rows}
        observed_jobs = int(cycle.get("jobs_observed") or 0)
        actual_credits = int(cycle.get("actual_credits") or 0)
        report = {
            "contract_version": "phase_b_catalog_report_v1",
            "cycle": cycle,
            "targets": targets,
            "source_metrics": source_metrics,
            "metrics": {
                "request_count": int(cycle.get("actual_requests") or 0),
                "redirect_count": int(redirect_count["count"] or 0),
                "direct_proxy_mode": mode_counts,
                "reserved_credits": int(cycle.get("reserved_credits") or 0),
                "actual_credits": actual_credits,
                "reserved_cost": int(cycle.get("reserved_credits") or 0),
                "actual_cost": actual_credits,
                "observed": observed_jobs,
                "new": int(cycle.get("jobs_new") or 0),
                "updated": int(cycle.get("jobs_updated") or 0),
                "duplicate": int(cycle.get("jobs_duplicates") or 0),
                "rejected": int(cycle.get("jobs_rejected") or 0),
                "closed": int(cycle.get("jobs_closed") or 0),
                "published": int(cycle.get("jobs_published") or 0),
                "yield_per_request": round(
                    observed_jobs / int(cycle.get("actual_requests") or 1), 2
                ) if int(cycle.get("actual_requests") or 0) else 0,
                "cost_per_produced_job": round(actual_credits / observed_jobs, 2) if observed_jobs else 0,
                "last_productive_time": max(
                    (str(target.get("last_productive_at") or "") for target in targets),
                    default="",
                ),
                "consecutive_zero_yield_attempts": max(
                    (int(target.get("consecutive_zero_yield_attempts") or 0) for target in targets),
                    default=0,
                ),
            },
            "rejection_reasons": rejection_reasons,
            "controls": {
                "forecasted_requests": int(cycle.get("forecast_requests") or 0),
                "forecasted_credits": int(cycle.get("forecast_credits") or 0),
                "reserved_requests": int(cycle.get("reserved_requests") or 0),
                "reserved_credits": int(cycle.get("reserved_credits") or 0),
                "actual_requests": int(cycle.get("actual_requests") or 0),
                "actual_credits": int(cycle.get("actual_credits") or 0),
                "uncertain_requests": int(request_counts["uncertain"] or 0),
                "dispatching_requests": int(request_counts["dispatching"] or 0),
            },
            "publication": {
                "publication_id": str(cycle.get("publication_id") or ""),
                "published": bool(str(cycle.get("publication_id") or "")),
            },
            "last_valid_publication": _dict_row(last_publication) if last_publication is not None else None,
        }
        report["quality"] = self.get_quality_metrics(cycle_id)
        return report

    def get_quality_metrics(self, cycle_id: str = "") -> dict[str, Any]:
        """Return report-only quality counts by source dimensions."""
        where = "WHERE COALESCE(t.quarantined, 0)=0"
        if str(cycle_id or "").strip():
            where += " AND e.cycle_id=?"
        params: tuple[Any, ...] = (str(cycle_id),) if str(cycle_id or "").strip() else ()
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT e.warning_code, e.severity, e.connector, e.target_id, e.employer_name, e.source_token,
                       COUNT(*) AS count
                FROM acquisition_quality_events e
                LEFT JOIN acquisition_targets t ON t.target_id=e.target_id
                {where}
                GROUP BY e.warning_code, e.severity, e.connector, e.target_id, e.employer_name, e.source_token
                ORDER BY count DESC, e.warning_code
                """,
                params,
            ).fetchall()
        by_warning: dict[str, int] = {}
        dimensions: list[dict[str, Any]] = []
        for row in rows:
            warning = str(row["warning_code"] or "unknown")
            by_warning[warning] = by_warning.get(warning, 0) + int(row["count"] or 0)
            dimensions.append({
                "warning_code": warning,
                "severity": str(row["severity"] or "warning"),
                "connector": str(row["connector"] or ""),
                "target_id": str(row["target_id"] or ""),
                "employer_name": str(row["employer_name"] or ""),
                "source_token": str(row["source_token"] or ""),
                "count": int(row["count"] or 0),
            })
        return {"mode": "report_only", "event_count": sum(by_warning.values()), "by_warning": by_warning, "by_source": dimensions}

    def get_latest_report(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT cycle_id FROM acquisition_cycles ORDER BY scheduled_at DESC LIMIT 1"
            ).fetchone()
        return self.get_cycle_report(str(row["cycle_id"])) if row is not None else None

    def get_public_catalog(self, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        with self._connect() as connection:
            publication = connection.execute(
                """
                SELECT publication_id, cycle_id, status, published_at, valid_until, snapshot_json
                FROM acquisition_publications
                WHERE publication_id = COALESCE(
                    (SELECT publication_id FROM acquisition_publication_head WHERE head_id = 1),
                    (SELECT publication_id FROM acquisition_publications WHERE status = 'valid' ORDER BY published_at DESC LIMIT 1)
                ) AND status = 'valid'
                LIMIT 1
                """
            ).fetchone()
        if publication is None:
            return {
                "jobs": [],
                "total": 0,
                "publication": None,
                "freshness": "unpublished",
            }
        snapshot = _decode(publication["snapshot_json"], [])
        jobs = snapshot if isinstance(snapshot, list) else []
        start = max(0, int(offset))
        end = start + max(1, int(limit))
        return {
            "jobs": jobs[start:end],
            "total": len(jobs),
            "publication": {
                "publication_id": str(publication["publication_id"] or ""),
                "cycle_id": str(publication["cycle_id"] or ""),
                "published_at": str(publication["published_at"] or ""),
                "valid_until": str(publication["valid_until"] or ""),
            },
            "freshness": "valid",
        }

    def get_target_history(self, target_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            target = connection.execute(
                "SELECT * FROM acquisition_targets WHERE target_id = ?", (target_id,)
            ).fetchone()
            attempts = connection.execute(
                "SELECT * FROM acquisition_target_attempts WHERE target_id = ? ORDER BY started_at DESC",
                (target_id,),
            ).fetchall()
            requests = connection.execute(
                "SELECT * FROM acquisition_requests WHERE target_id = ? ORDER BY started_at DESC",
                (target_id,),
            ).fetchall()
        if target is None:
            raise KeyError(f"Acquisition target '{target_id}' not found.")
        return {
            "target": self._target_payload(_dict_row(target)),
            "attempts": [_dict_row(row) for row in attempts],
            "requests": [self._request_payload(_dict_row(row)) for row in requests],
        }

    def get_source_state_summary(self, target_id: str) -> dict[str, int]:
        """Return active/stale/unknown/closed source-state counts for reconciliation."""

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT lifecycle_state, COUNT(*) AS count FROM job_source_states WHERE target_id=? GROUP BY lifecycle_state",
                (str(target_id or ""),),
            ).fetchall()
        return {str(row["lifecycle_state"] or "unknown"): int(row["count"] or 0) for row in rows}

    # Admin Job Import dashboard -----------------------------------------

    @staticmethod
    def _admin_import_payload(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        payload = _dict_row(row) if hasattr(row, "keys") else dict(row)
        for field, default in (("source_ids_json", []), ("scope_json", {}), ("plan_json", {})):
            raw = payload.pop(field, "")
            decoded = _decode(raw, default)
            payload[field.removesuffix("_json")] = decoded
        return payload

    def create_job_import(
        self,
        *,
        idempotency_key: str,
        requested_by: str,
        source_ids: Iterable[str],
        scope: Mapping[str, Any],
        plan: Mapping[str, Any],
    ) -> dict[str, Any]:
        normalized_key = str(idempotency_key or "").strip()
        if not normalized_key:
            raise ValueError("idempotency_key is required")
        now = utc_now_iso()
        import_id = f"job_import_{uuid4().hex}"
        source_values = [str(item).strip() for item in source_ids if str(item).strip()]

        def write(connection):
            existing = connection.execute(
                "SELECT * FROM admin_job_imports WHERE idempotency_key=?",
                (normalized_key,),
            ).fetchone()
            if existing is not None:
                return self._admin_import_payload(existing)
            connection.execute(
                """
                INSERT INTO admin_job_imports (
                    import_id, idempotency_key, status, requested_by, source_ids_json,
                    scope_json, plan_json, created_at, updated_at
                ) VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, ?)
                """,
                (
                    import_id,
                    normalized_key,
                    str(requested_by or ""),
                    _json(source_values),
                    _json(dict(scope)),
                    _json(dict(plan)),
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO admin_job_audit_events (
                    event_id, import_id, actor_user_id, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, 'import_queued', ?, ?)
                """,
                (f"admin_audit_{uuid4().hex}", import_id, str(requested_by or ""), _json({"plan": dict(plan)}), now),
            )
            return self._admin_import_payload(
                connection.execute("SELECT * FROM admin_job_imports WHERE import_id=?", (import_id,)).fetchone()
            )

        return self._run_transaction(write) or {}

    def get_job_import(self, import_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM admin_job_imports WHERE import_id=?", (str(import_id or ""),)).fetchone()
        return self._admin_import_payload(row)

    def list_job_imports(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        self.reconcile_terminal_job_imports()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM admin_job_imports ORDER BY created_at DESC, import_id DESC LIMIT ? OFFSET ?",
                (max(1, min(200, int(limit))), max(0, int(offset))),
            ).fetchall()
        return [item for row in rows if (item := self._admin_import_payload(row)) is not None]

    def claim_next_job_import(self, *, lease_owner: str = "runr-worker") -> dict[str, Any] | None:
        now = utc_now_iso()

        def claim(connection):
            row = connection.execute(
                "SELECT * FROM admin_job_imports WHERE status='queued' ORDER BY created_at, import_id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            updated = connection.execute(
                """
                UPDATE admin_job_imports
                SET status='running', started_at=?, updated_at=?, error_code='', error_message=?
                WHERE import_id=? AND status='queued'
                """,
                (now, now, str(lease_owner or ""), str(row["import_id"])),
            )
            if updated.rowcount != 1:
                return None
            connection.execute(
                """
                INSERT INTO admin_job_audit_events (
                    event_id, import_id, actor_user_id, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, 'import_claimed', ?, ?)
                """,
                (f"admin_audit_{uuid4().hex}", str(row["import_id"]), str(lease_owner or ""), _json({}), now),
            )
            return self._admin_import_payload(
                connection.execute("SELECT * FROM admin_job_imports WHERE import_id=?", (str(row["import_id"]),)).fetchone()
            )

        return self._run_transaction(claim)

    def attach_job_import_cycle(self, import_id: str, cycle_id: str) -> None:
        now = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                "UPDATE admin_job_imports SET cycle_id=?, updated_at=? WHERE import_id=?",
                (str(cycle_id or ""), now, str(import_id or "")),
            )

    def complete_job_import(
        self,
        import_id: str,
        *,
        status: str,
        cycle_id: str = "",
        error_code: str = "",
        error_message: str = "",
    ) -> dict[str, Any] | None:
        now = utc_now_iso()
        finished = now if status in {"completed", "failed", "blocked", "needs_attention"} else ""
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE admin_job_imports
                SET status=?, cycle_id=CASE WHEN ? != '' THEN ? ELSE cycle_id END,
                    error_code=?, error_message=?, completed_at=CASE WHEN ? != '' THEN ? ELSE completed_at END,
                    updated_at=?
                WHERE import_id=?
                """,
                (
                    str(status or "needs_attention"),
                    str(cycle_id or ""),
                    str(cycle_id or ""),
                    str(error_code or ""),
                    str(error_message or "")[:500],
                    finished,
                    finished,
                    now,
                    str(import_id or ""),
                ),
            )
            connection.execute(
                """
                INSERT INTO admin_job_audit_events (
                    event_id, import_id, actor_user_id, event_type, payload_json, created_at
                ) VALUES (?, ?, '', 'import_completed', ?, ?)
                """,
                (
                    f"admin_audit_{uuid4().hex}",
                    str(import_id or ""),
                    _json({"status": str(status or ""), "cycle_id": str(cycle_id or ""), "error_code": str(error_code or "")}),
                    now,
                ),
            )
        return self.get_job_import(import_id)

    def reconcile_terminal_job_imports(self) -> int:
        """Close imports whose durable acquisition cycle already reached a terminal state."""

        now = utc_now_iso()

        def reconcile(connection) -> int:
            rows = connection.execute(
                """
                SELECT i.import_id, i.cycle_id, c.status AS cycle_status,
                       c.error_code AS cycle_error_code, c.error_message AS cycle_error_message
                FROM admin_job_imports i
                JOIN acquisition_cycles c ON c.cycle_id=i.cycle_id
                WHERE i.status='running'
                  AND c.status IN ('completed', 'degraded', 'failed', 'blocked', 'recovery_required')
                ORDER BY i.created_at, i.import_id
                """
            ).fetchall()
            for row in rows:
                cycle_status = str(row["cycle_status"] or "")
                import_status = {
                    "completed": "completed",
                    "failed": "failed",
                    "degraded": "needs_attention",
                    "blocked": "needs_attention",
                    "recovery_required": "needs_attention",
                }.get(cycle_status, "needs_attention")
                error_code = str(row["cycle_error_code"] or "")
                error_message = str(row["cycle_error_message"] or "")
                if import_status == "needs_attention" and not error_code:
                    error_code = "cycle_degraded"
                if import_status == "needs_attention" and not error_message:
                    error_message = "Acquisition cycle completed with one or more source errors."
                connection.execute(
                    """
                    UPDATE admin_job_imports
                    SET status=?, error_code=?, error_message=?, completed_at=?, updated_at=?
                    WHERE import_id=? AND status='running'
                    """,
                    (import_status, error_code, error_message[:500], now, now, str(row["import_id"])),
                )
                connection.execute(
                    """
                    INSERT INTO admin_job_audit_events (
                        event_id, import_id, actor_user_id, event_type, payload_json, created_at
                    ) VALUES (?, ?, '', 'import_reconciled', ?, ?)
                    """,
                    (
                        f"admin_audit_{uuid4().hex}",
                        str(row["import_id"]),
                        _json({"cycle_id": str(row["cycle_id"]), "cycle_status": cycle_status, "status": import_status}),
                        now,
                    ),
                )
            return len(rows)

        return int(self._run_transaction(reconcile) or 0)

    def requeue_stale_job_imports(self, *, stale_after_seconds: int = 900) -> int:
        """Return long-expired running imports to the durable worker queue."""

        now = utc_now_iso()
        cutoff = utc_plus_seconds(-max(60, int(stale_after_seconds)))

        def requeue(connection) -> int:
            rows = connection.execute(
                """
                SELECT i.import_id, i.cycle_id
                FROM admin_job_imports i
                JOIN acquisition_cycles c ON c.cycle_id=i.cycle_id
                WHERE i.status='running'
                  AND c.status='running'
                  AND c.lease_expires_at <= ?
                  AND i.updated_at <= ?
                ORDER BY i.created_at, i.import_id
                """,
                (now, cutoff),
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    UPDATE admin_job_imports
                    SET status='queued', started_at='', completed_at='',
                        error_code='stale_lease_reclaimed',
                        error_message='Worker lease expired; import returned to the durable queue.',
                        updated_at=?
                    WHERE import_id=? AND status='running'
                    """,
                    (now, str(row["import_id"])),
                )
                connection.execute(
                    """
                    INSERT INTO admin_job_audit_events (
                        event_id, import_id, actor_user_id, event_type, payload_json, created_at
                    ) VALUES (?, ?, '', 'import_requeued_stale_lease', ?, ?)
                    """,
                    (
                        f"admin_audit_{uuid4().hex}",
                        str(row["import_id"]),
                        _json({"cycle_id": str(row["cycle_id"]), "stale_after_seconds": max(60, int(stale_after_seconds))}),
                        now,
                    ),
                )
            return len(rows)

        return int(self._run_transaction(requeue) or 0)

    def _review_job_payload(self, row: Mapping[str, Any], *, rejected: bool = False) -> dict[str, Any]:
        payload = _dict_row(row) if hasattr(row, "keys") else dict(row)
        raw_payload = _decode(payload.pop("version_payload_json", payload.pop("detail_json", "{}")), {})
        if not isinstance(raw_payload, Mapping):
            raw_payload = {}
        payload["source_payload"] = dict(raw_payload)
        payload["rejected"] = bool(rejected)
        payload["review_state"] = "not_accepted" if rejected else "needs_review"
        decision = str(payload.get("decision") or "").strip()
        if decision in {"approved", "not_accepted"}:
            payload["review_state"] = decision
        if payload.get("is_live"):
            payload["review_state"] = "already_live"
        payload["is_publishable"] = bool(
            not rejected
            and decision == "approved"
            and str(payload.get("apply_url") or "").startswith("https://")
            and str(payload.get("lifecycle_state") or "") in {"active", "stale", "reposted"}
        )
        warnings: list[str] = []
        if not str(payload.get("description") or "").strip():
            warnings.append("description_missing")
        if not str(payload.get("location") or "").strip():
            warnings.append("location_missing")
        if not str(payload.get("company_profile_json") or "").strip():
            warnings.append("company_information_pending")
        payload["quality_warnings"] = warnings
        return payload

    def list_review_jobs(
        self,
        *,
        import_id: str = "",
        status: str = "needs_review",
        search: str = "",
        source_id: str = "",
        location: str = "",
        missing: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        normalized_import_id = str(import_id or "").strip()
        predicates = ["i.import_id = ?"] if normalized_import_id else ["i.import_id = (SELECT import_id FROM admin_job_imports WHERE cycle_id=o.cycle_id ORDER BY created_at DESC LIMIT 1)"]
        params: list[Any] = [normalized_import_id] if normalized_import_id else []
        if search:
            predicates.append("LOWER(c.canonical_name || ' ' || j.title || ' ' || j.location || ' ' || v.description || ' ' || v.payload_json) LIKE ?")
            params.append(f"%{str(search).casefold()}%")
        if source_id:
            predicates.append("o.target_id = ?")
            params.append(str(source_id))
        if location:
            predicates.append("LOWER(j.location) LIKE ?")
            params.append(f"%{str(location).casefold()}%")
        query = f"""
            SELECT j.canonical_job_id, j.company_id, c.canonical_name AS company,
                   c.provenance_url AS company_provenance_url, p.profile_json AS company_profile_json,
                   j.identity_key, j.title, j.location, j.canonical_url, j.lifecycle_state,
                   j.first_seen_at, j.last_seen_at, j.last_verified_at, j.current_version_id,
                   v.version_number, v.description, v.location AS version_location, v.apply_url,
                   v.source_observation_id, v.payload_json AS version_payload_json,
                   o.target_id AS source_id, o.external_job_id, o.original_url, o.source_ats,
                   o.observed_at, d.decision, d.reason_code, d.actor_user_id, d.created_at AS decision_at,
                   EXISTS (
                       SELECT 1 FROM acquisition_publication_jobs pj
                       JOIN acquisition_publication_head ph ON ph.publication_id=pj.publication_id AND ph.head_id=1
                       WHERE pj.canonical_job_id=j.canonical_job_id
                   ) AS is_live
            FROM job_source_observations o
            JOIN admin_job_imports i ON i.cycle_id=o.cycle_id
            JOIN canonical_jobs j ON j.canonical_job_id=o.canonical_job_id
            JOIN canonical_companies c ON c.company_id=j.company_id
            LEFT JOIN canonical_company_profiles p ON p.company_id=c.company_id
            LEFT JOIN job_posting_versions v ON v.version_id=j.current_version_id
            LEFT JOIN admin_job_review_decisions d
              ON d.import_id=i.import_id AND d.canonical_job_id=j.canonical_job_id
            WHERE {' AND '.join(predicates)}
            GROUP BY j.canonical_job_id, i.import_id
            ORDER BY COALESCE(v.created_at, o.observed_at) DESC, j.canonical_job_id
        """
        with self._connect() as connection:
            accepted_rows = connection.execute(query, tuple(params)).fetchall()
            rejection_predicates = ["i.import_id = ?"] if normalized_import_id else ["i.import_id = (SELECT import_id FROM admin_job_imports WHERE cycle_id=r.cycle_id ORDER BY created_at DESC LIMIT 1)"]
            rejection_params: list[Any] = [normalized_import_id] if normalized_import_id else []
            if search:
                rejection_predicates.append("LOWER(COALESCE(t.display_name, '') || ' ' || r.title || ' ' || r.reason_code) LIKE ?")
                rejection_params.append(f"%{str(search).casefold()}%")
            if source_id:
                rejection_predicates.append("r.target_id = ?")
                rejection_params.append(str(source_id))
            rejection_rows = connection.execute(
                f"""
                SELECT '' AS canonical_job_id, '' AS company_id, t.display_name AS company,
                       '' AS company_provenance_url, '' AS company_profile_json,
                       '' AS identity_key, r.title, '' AS location, '' AS canonical_url,
                       'rejected' AS lifecycle_state, r.observed_at AS first_seen_at,
                       r.observed_at AS last_seen_at, r.observed_at AS last_verified_at,
                       '' AS current_version_id, 0 AS version_number, '' AS description,
                       '' AS version_location, '' AS apply_url, '' AS source_observation_id,
                       r.detail_json, r.target_id AS source_id, r.external_job_id,
                       '' AS original_url, '' AS source_ats, r.observed_at, 'not_accepted' AS decision,
                       r.reason_code, '' AS actor_user_id, r.observed_at AS decision_at, 0 AS is_live
                FROM acquisition_job_rejections r
                JOIN admin_job_imports i ON i.cycle_id=r.cycle_id
                LEFT JOIN acquisition_targets t ON t.target_id=r.target_id
                WHERE {' AND '.join(rejection_predicates)}
                ORDER BY r.observed_at DESC, r.rejection_id
                """,
                tuple(rejection_params),
            ).fetchall()
        rows = [self._review_job_payload(row) for row in accepted_rows]
        rows.extend(self._review_job_payload(row, rejected=True) for row in rejection_rows)
        if missing:
            wanted = {item.strip().casefold() for item in str(missing).split(",") if item.strip()}
            rows = [
                row for row in rows
                if any(
                    (field == "description" and not str(row.get("description") or "").strip())
                    or (field == "location" and not str(row.get("location") or "").strip())
                    or (field in {"company", "company_information"} and not str(row.get("company_profile_json") or "").strip())
                    or (field in {"apply_url", "apply"} and not str(row.get("apply_url") or "").strip())
                    for field in wanted
                )
            ]
        if status and status != "all":
            rows = [row for row in rows if row.get("review_state") == status]
        start = max(0, int(offset))
        page = rows[start : start + max(1, min(200, int(limit)))]
        return {"jobs": page, "total": len(rows), "limit": max(1, int(limit)), "offset": start}

    @staticmethod
    def _inspection_value_present(value: Any) -> bool:
        if value is None or value == "":
            return False
        if isinstance(value, (list, tuple, set, dict)) and not value:
            return False
        if isinstance(value, Mapping) and str(value.get("state") or "").casefold() in {"unknown", "missing", "unavailable"}:
            return False
        return True

    @staticmethod
    def _inspection_value_state(value: Any) -> str:
        if value is None:
            return "null"
        if value == "":
            return "empty"
        if isinstance(value, list) and not value:
            return "empty_list"
        if isinstance(value, dict) and not value:
            return "empty_object"
        if isinstance(value, Mapping):
            explicit_state = str(value.get("state") or "").casefold()
            if explicit_state in {"unknown", "missing", "unavailable", "extraction_not_run", "conflict", "failed"}:
                return explicit_state
        return "present"

    @classmethod
    def _inspection_coverage(cls, values: Mapping[str, Any]) -> dict[str, Any]:
        missing = [key for key, value in values.items() if not cls._inspection_value_present(value)]
        total = len(values)
        present = total - len(missing)
        return {
            "present": present,
            "total": total,
            "missing_fields": missing,
            "field_states": {
                key: cls._inspection_value_state(value)
                for key, value in values.items()
            },
        }

    @staticmethod
    def _inspection_rows(rows: Iterable[Any], json_fields: Iterable[str] = ()) -> list[dict[str, Any]]:
        fields = tuple(json_fields)
        result: list[dict[str, Any]] = []
        for row in rows:
            item = _dict_row(row)
            for field in fields:
                decoded_key = field[:-5] if field.endswith("_json") else field
                item[decoded_key] = _decode(item.get(field), {} if field != "snapshot_json" else [])
            result.append(item)
        return result

    @staticmethod
    def _inspection_in_clause(column: str, values: Iterable[str]) -> tuple[str, tuple[str, ...]]:
        normalized = tuple(dict.fromkeys(str(value) for value in values if str(value).strip()))
        if not normalized:
            return "1=0", ()
        return f"{column} IN ({','.join('?' for _ in normalized)})", normalized

    def list_admin_job_inspections(
        self,
        *,
        search: str = "",
        function: str = "",
        subfunction: str = "",
        employment_type: str = "",
        workplace: str = "",
        location: str = "",
        language: str = "",
        seniority: str = "",
        source: str = "",
        freshness: str = "",
        completeness_state: str = "",
        warning_type: str = "",
        duplicate_state: str = "",
        application_method: str = "",
        publication_state: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List real canonical jobs for the admin data inspector."""

        limit_value = max(1, min(200, int(limit)))
        offset_value = max(0, int(offset))
        normalized_search = " ".join(str(search or "").casefold().split())
        predicates = []
        params: list[Any] = []
        if normalized_search:
            predicates.append(
                "LOWER(j.canonical_job_id || ' ' || c.canonical_name || ' ' || j.title || ' ' || "
                "j.location || ' ' || COALESCE(o.target_id, '') || ' ' || COALESCE(v.payload_json, '')) LIKE ?"
            )
            params.append(f"%{normalized_search}%")
        for value, field_name in ((function, "runr_function"), (subfunction, "runr_subfunction"), (employment_type, "employment_type"), (workplace, "workplace_arrangement"), (seniority, "experience"), (language, "languages")):
            normalized_value = " ".join(str(value or "").casefold().split())
            if normalized_value:
                predicates.append(
                    "EXISTS (SELECT 1 FROM acquisition_field_provenance fp WHERE fp.entity_kind='job' AND fp.entity_id=j.canonical_job_id AND fp.field_name=? AND LOWER(fp.normalized_value_json) LIKE ?)"
                )
                params.extend([field_name, f"%{normalized_value}%"])
        if str(location or "").strip():
            predicates.append("LOWER(j.location) LIKE ?")
            params.append(f"%{' '.join(str(location).casefold().split())}%")
        if str(source or "").strip():
            predicates.append("LOWER(COALESCE(t.connector, o.source_ats, '')) = ?")
            params.append(str(source).casefold().strip())
        if str(application_method or "").strip():
            predicates.append("LOWER(COALESCE(json_extract(v.payload_json, '$.application_method'), '')) = ?")
            params.append(str(application_method).casefold().strip())
        if str(completeness_state or "").strip():
            predicates.append("EXISTS (SELECT 1 FROM acquisition_completeness_reports cr WHERE cr.entity_kind='job' AND cr.entity_id=j.canonical_job_id AND cr.state=?)")
            params.append(str(completeness_state).strip())
        if str(warning_type or "").strip():
            predicates.append("EXISTS (SELECT 1 FROM acquisition_quality_events qe WHERE qe.canonical_job_id=j.canonical_job_id AND qe.warning_code=?)")
            params.append(str(warning_type).strip())
        if str(duplicate_state or "").strip():
            predicates.append("EXISTS (SELECT 1 FROM acquisition_duplicate_members dm JOIN acquisition_duplicate_clusters dc ON dc.cluster_id=dm.cluster_id WHERE dm.canonical_job_id=j.canonical_job_id AND dc.state=?)")
            params.append(str(duplicate_state).strip())
        if str(publication_state or "").strip().casefold() in {"published", "live"}:
            predicates.append("EXISTS (SELECT 1 FROM acquisition_publication_jobs pj JOIN acquisition_publication_head ph ON ph.publication_id=pj.publication_id AND ph.head_id=1 WHERE pj.canonical_job_id=j.canonical_job_id)")
        elif str(publication_state or "").strip().casefold() in {"unpublished", "not_published"}:
            predicates.append("NOT EXISTS (SELECT 1 FROM acquisition_publication_jobs pj JOIN acquisition_publication_head ph ON ph.publication_id=pj.publication_id AND ph.head_id=1 WHERE pj.canonical_job_id=j.canonical_job_id)")
        if str(freshness or "").strip().casefold() in {"fresh", "recent"}:
            predicates.append("datetime(COALESCE(j.last_seen_at, o.observed_at)) >= datetime('now', '-7 days')")
        elif str(freshness or "").strip().casefold() in {"stale", "old"}:
            predicates.append("datetime(COALESCE(j.last_seen_at, o.observed_at)) < datetime('now', '-7 days')")
        where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
        query = f"""
            SELECT j.canonical_job_id, j.company_id, c.canonical_name AS company,
                   j.title, j.location, j.canonical_url, j.lifecycle_state,
                   j.first_seen_at, j.last_seen_at, j.last_verified_at,
                   j.current_version_id, j.identity_key, j.identity_signature,
                   v.version_number, v.description, v.apply_url, v.payload_json AS version_payload_json,
                   o.target_id AS source_id, o.external_job_id, o.source_ats,
                   o.original_url, o.observed_at, t.connector, t.provider,
                   COALESCE((
                       SELECT d.decision FROM admin_job_review_decisions d
                       WHERE d.canonical_job_id=j.canonical_job_id
                       ORDER BY d.created_at DESC LIMIT 1
                   ), '') AS review_decision,
                   EXISTS (
                       SELECT 1 FROM acquisition_publication_jobs pj
                       JOIN acquisition_publication_head ph
                         ON ph.publication_id=pj.publication_id AND ph.head_id=1
                       WHERE pj.canonical_job_id=j.canonical_job_id
                   ) AS is_live
            FROM canonical_jobs j
            JOIN canonical_companies c ON c.company_id=j.company_id
            LEFT JOIN job_posting_versions v ON v.version_id=j.current_version_id
            LEFT JOIN job_source_observations o ON o.observation_id=(
                SELECT latest.source_observation_id
                FROM job_posting_versions latest
                WHERE latest.version_id=j.current_version_id
            )
            LEFT JOIN acquisition_targets t ON t.target_id=o.target_id
            {where}
            ORDER BY COALESCE(v.created_at, j.last_seen_at) DESC, j.canonical_job_id
            LIMIT ? OFFSET ?
        """
        summary_query = f"""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN json_extract(COALESCE(v.payload_json, '{{}}'), '$.application_destination.status') = 'verified' THEN 1 ELSE 0 END) AS apply_url_present,
                   SUM(CASE WHEN COALESCE(p.profile_json, '') = ''
                                  OR p.profile_json LIKE '%\"state\":\"unknown\"%'
                            THEN 1 ELSE 0 END) AS company_profiles_incomplete
            FROM canonical_jobs j
            JOIN canonical_companies c ON c.company_id=j.company_id
            LEFT JOIN job_posting_versions v ON v.version_id=j.current_version_id
            LEFT JOIN canonical_company_profiles p ON p.company_id=j.company_id
            LEFT JOIN job_source_observations o ON o.observation_id=(
                SELECT latest.source_observation_id
                FROM job_posting_versions latest
                WHERE latest.version_id=j.current_version_id
            )
            {where}
        """
        with self._connect() as connection:
            rows = connection.execute(query, (*params, limit_value, offset_value)).fetchall()
            summary_row = connection.execute(summary_query, tuple(params)).fetchone()
        jobs: list[dict[str, Any]] = []
        for row in rows:
            item = _dict_row(row)
            version_payload = _decode(item.pop("version_payload_json", "{}"), {})
            if not isinstance(version_payload, Mapping):
                version_payload = {}
            decision = str(item.pop("review_decision") or "").strip()
            live = bool(int(item.pop("is_live") or 0))
            item["state"] = "Published" if live else (decision.replace("_", " ").title() if decision else "Review")
            destination = version_payload.get("application_destination") if isinstance(version_payload.get("application_destination"), Mapping) else {}
            item["application_method"] = version_payload.get("application_method") or "unknown"
            item["application_classification"] = destination.get("classification") or "unknown"
            item["apply_status"] = "present" if destination.get("status") == "verified" else ("unresolved" if destination else "missing")
            item["posted_age_hours"] = posted_age_hours(
                version_payload.get("posted_at") or version_payload.get("datePosted")
            )
            item["source"] = str(item.get("connector") or item.get("source_id") or "Unknown")
            item["freshness"] = item.get("last_seen_at") or item.get("observed_at") or None
            jobs.append(item)
        total = int(summary_row["total"] or 0) if summary_row is not None else 0
        apply_present = int(summary_row["apply_url_present"] or 0) if summary_row is not None else 0
        company_profiles_incomplete = int(summary_row["company_profiles_incomplete"] or 0) if summary_row is not None else 0
        return {
            "jobs": jobs,
            "total": total,
            "limit": limit_value,
            "offset": offset_value,
            "summary": {
                "catalog_records": total,
                "apply_url_present": apply_present,
                "apply_url_missing_or_invalid": max(0, total - apply_present),
                "company_profiles_incomplete": company_profiles_incomplete,
            },
        }

    def get_admin_job_inspection(self, canonical_job_id: str) -> dict[str, Any] | None:
        """Compose one admin-only inspection record from canonical and raw tables."""

        job_id = str(canonical_job_id or "").strip()
        if not job_id:
            return None
        with self._connect() as connection:
            base_row = connection.execute(
                """
                SELECT j.*, c.canonical_name AS company_name, c.entity_kind,
                       c.provenance_url AS company_provenance_url,
                       p.profile_json, p.logo_source_url, p.logo_verified_at,
                       v.version_id, v.version_number, v.content_hash,
                       v.description AS version_description, v.location AS version_location,
                       v.apply_url AS version_apply_url, v.source_observation_id,
                       v.payload_json AS version_payload_json, v.created_at AS version_created_at
                FROM canonical_jobs j
                JOIN canonical_companies c ON c.company_id=j.company_id
                LEFT JOIN canonical_company_profiles p ON p.company_id=c.company_id
                LEFT JOIN job_posting_versions v ON v.version_id=j.current_version_id
                WHERE j.canonical_job_id=?
                """,
                (job_id,),
            ).fetchone()
            if base_row is None:
                return None
            base = _dict_row(base_row)
            company_id = str(base.get("company_id") or "")
            observations = connection.execute(
                "SELECT * FROM job_source_observations WHERE canonical_job_id=? ORDER BY observed_at DESC, observation_id DESC",
                (job_id,),
            ).fetchall()
            versions = connection.execute(
                "SELECT * FROM job_posting_versions WHERE canonical_job_id=? ORDER BY version_number DESC, created_at DESC",
                (job_id,),
            ).fetchall()
            external_ids = connection.execute(
                "SELECT * FROM canonical_job_external_ids WHERE canonical_job_id=? ORDER BY source_id, external_job_id",
                (job_id,),
            ).fetchall()
            aliases = connection.execute(
                "SELECT * FROM canonical_job_url_aliases WHERE canonical_job_id=? ORDER BY created_at DESC, url",
                (job_id,),
            ).fetchall()
            relationships = connection.execute(
                "SELECT * FROM canonical_job_relationships WHERE canonical_job_id=? OR related_job_id=? ORDER BY created_at DESC",
                (job_id, job_id),
            ).fetchall()
            source_states = connection.execute(
                "SELECT * FROM job_source_states WHERE canonical_job_id=? ORDER BY updated_at DESC",
                (job_id,),
            ).fetchall()
            observation_ids = [str(row["observation_id"] or "") for row in observations]
            cycle_ids = [str(row["cycle_id"] or "") for row in observations]
            task_ids = [str(row["task_id"] or "") for row in observations]
            target_ids = [str(row["target_id"] or "") for row in observations]
            external_job_ids = [str(row["external_job_id"] or "") for row in observations]
            cycle_where, cycle_params = self._inspection_in_clause("cycle_id", cycle_ids)
            task_where, task_params = self._inspection_in_clause("task_id", task_ids)
            target_where, target_params = self._inspection_in_clause("target_id", target_ids)
            external_where, external_params = self._inspection_in_clause("external_job_id", external_job_ids)
            requests = connection.execute(
                f"SELECT * FROM acquisition_requests WHERE {cycle_where} OR {task_where} OR {target_where} ORDER BY started_at DESC, request_id DESC",
                (*cycle_params, *task_params, *target_params),
            ).fetchall()
            attempts = connection.execute(
                f"SELECT * FROM acquisition_target_attempts WHERE {cycle_where} OR {task_where} OR {target_where} ORDER BY started_at DESC, attempt_id DESC",
                (*cycle_params, *task_params, *target_params),
            ).fetchall()
            tasks = connection.execute(
                f"SELECT * FROM acquisition_tasks WHERE {cycle_where} OR {target_where} ORDER BY created_at DESC, task_id DESC",
                (*cycle_params, *target_params),
            ).fetchall()
            cycles = connection.execute(
                f"SELECT * FROM acquisition_cycles WHERE {cycle_where} ORDER BY scheduled_at DESC, cycle_id DESC",
                cycle_params,
            ).fetchall()
            targets = connection.execute(
                f"SELECT * FROM acquisition_targets WHERE {target_where} ORDER BY target_id",
                target_params,
            ).fetchall()
            rejections = connection.execute(
                f"SELECT * FROM acquisition_job_rejections WHERE {cycle_where} OR {target_where} OR {external_where} ORDER BY observed_at DESC, rejection_id DESC",
                (*cycle_params, *target_params, *external_params),
            ).fetchall()
            decisions = connection.execute(
                "SELECT * FROM admin_job_review_decisions WHERE canonical_job_id=? ORDER BY created_at DESC, decision_id DESC",
                (job_id,),
            ).fetchall()
            imports = connection.execute(
                f"SELECT * FROM admin_job_imports WHERE {cycle_where} ORDER BY created_at DESC, import_id DESC",
                cycle_params,
            ).fetchall()
            import_ids = [str(row["import_id"] or "") for row in imports]
            import_where, import_params = self._inspection_in_clause("import_id", import_ids)
            audit_events = connection.execute(
                f"SELECT * FROM admin_job_audit_events WHERE {import_where} ORDER BY created_at DESC, event_id DESC",
                import_params,
            ).fetchall()
            publication_rows = connection.execute(
                """
                SELECT p.*, h.head_id AS current_head
                FROM acquisition_publications p
                JOIN acquisition_publication_jobs pj ON pj.publication_id=p.publication_id
                LEFT JOIN acquisition_publication_head h ON h.publication_id=p.publication_id
                WHERE pj.canonical_job_id=?
                ORDER BY p.published_at DESC, p.publication_id DESC
                """,
                (job_id,),
            ).fetchall()
            observation_placeholders = ",".join("?" for _ in observation_ids) or "''"
            observation_relationships = connection.execute(
                f"SELECT * FROM job_source_observation_relationships WHERE observation_id IN ({observation_placeholders}) OR related_observation_id IN ({observation_placeholders}) ORDER BY created_at DESC",
                (*observation_ids, *observation_ids),
            ).fetchall() if observation_ids else []
            quality_events = connection.execute(
                "SELECT * FROM acquisition_quality_events WHERE canonical_job_id=? ORDER BY created_at DESC, event_id DESC",
                (job_id,),
            ).fetchall()
            version_quality = connection.execute(
                "SELECT * FROM acquisition_version_quality WHERE canonical_job_id=? ORDER BY calculated_at DESC, version_id DESC",
                (job_id,),
            ).fetchall()
            field_provenance = connection.execute(
                "SELECT * FROM acquisition_field_provenance WHERE (entity_kind='job' AND entity_id=?) OR (entity_kind='company' AND entity_id=?) ORDER BY entity_kind, field_name, observed_at DESC",
                (job_id, company_id),
            ).fetchall()
            rule_outputs = connection.execute(
                "SELECT * FROM acquisition_rule_outputs WHERE (entity_kind='job' AND entity_id=?) ORDER BY created_at DESC",
                (job_id,),
            ).fetchall()
            company_urls = connection.execute(
                "SELECT * FROM canonical_company_urls WHERE company_id=? ORDER BY url_type, selected_primary DESC, updated_at DESC",
                (company_id,),
            ).fetchall()
            completeness_reports = connection.execute(
                "SELECT * FROM acquisition_completeness_reports WHERE entity_kind='job' AND entity_id=? ORDER BY calculated_at DESC",
                (job_id,),
            ).fetchall()
            duplicate_clusters = connection.execute(
                """
                SELECT c.*, m.canonical_job_id AS member_job_id, m.member_score, m.member_reasons_json
                FROM acquisition_duplicate_clusters c
                JOIN acquisition_duplicate_members m ON m.cluster_id=c.cluster_id
                WHERE m.canonical_job_id=?
                ORDER BY c.updated_at DESC
                """,
                (job_id,),
            ).fetchall()

        profile = _decode(base.get("profile_json"), {})
        profile_fields = profile.get("fields") if isinstance(profile, Mapping) else {}
        profile_fields = profile_fields if isinstance(profile_fields, Mapping) else {}
        company: dict[str, Any] = {
            "canonical_company_id": company_id,
            "name": base.get("company_name"),
            "entity_kind": base.get("entity_kind"),
            "provenance_url": base.get("company_provenance_url") or None,
            "profile_schema_version": profile.get("schema_version") if isinstance(profile, Mapping) else None,
            "profile_fields": dict(profile_fields),
        }
        for field in _COMPANY_PROFILE_FIELDS:
            value = profile_fields.get(field)
            company[field] = value.get("value") if isinstance(value, Mapping) else None
        company["logo_url"] = company.get("logo")

        current_payload = _decode(base.get("version_payload_json"), {})
        if not isinstance(current_payload, Mapping):
            current_payload = {}
        job: dict[str, Any] = dict(current_payload)
        job.update(
            {
                "canonical_job_id": job_id,
                "company_id": company_id,
                "company": base.get("company_name"),
                "title": base.get("title"),
                "location_raw": base.get("version_location") or base.get("location") or None,
                "canonical_url": base.get("canonical_url") or None,
                "lifecycle_state": base.get("lifecycle_state"),
                "first_seen_at": base.get("first_seen_at"),
                "last_seen_at": base.get("last_seen_at"),
                "last_verified_at": base.get("last_verified_at") or None,
                "current_version_id": base.get("current_version_id") or None,
                "posting_version": base.get("version_number"),
                "content_hash": base.get("content_hash") or None,
                "description": base.get("version_description") or current_payload.get("description") or None,
                "full_description": base.get("version_description") or current_payload.get("full_description") or None,
                "description_raw": current_payload.get("description_raw") or None,
                "description_html": current_payload.get("description_html") or None,
                "description_text": current_payload.get("description_text") or None,
                "apply_url": base.get("version_apply_url") or current_payload.get("apply_url") or None,
                "source_url": base.get("canonical_url") or None,
            }
        )

        target_items = self._inspection_rows(targets, ("config_json",))
        target_by_id = {str(item.get("target_id") or ""): item for item in target_items}
        connector = str((target_items[0] if target_items else {}).get("connector") or "").casefold()
        if not connector and observations:
            connector = str(observations[0]["source_ats"] or "").casefold()
        target = target_items[0] if target_items else {}
        normalized_current = normalize_job_for_ingestion(current_payload, target)
        job["application_destination"] = normalized_current.get("application_destination") or {}
        job["application_method"] = normalized_current.get("application_method") or "unknown"
        job["application_url"] = normalized_current.get("application_url") or ""
        job["job_detail_url"] = normalized_current.get("job_detail_url") or job.get("canonical_url") or ""
        job["normalized_source_metadata"] = normalized_current.get("normalized_source_metadata") or {}
        job["source_timestamps"] = normalized_current.get("source_timestamps") or {}
        if isinstance(job["normalized_source_metadata"], Mapping):
            job["posted_at"] = (((job["normalized_source_metadata"].get("fields") or {}).get("posted_at") or {}).get("value"))
        job["quality_warnings"] = normalized_current.get("quality_warnings") or []
        job["posted_age_hours"] = posted_age_hours_for_job(normalized_current)
        profile_website = str(company.get("website") or "")
        company_hosts = {hostname_for_url(profile_website)} if profile_website else set()
        target_hosts = {
            hostname_for_url(str(target.get(key) or ""))
            for key in ("canonical_target_url", "request_url", "provenance_url")
            if hostname_for_url(str(target.get(key) or ""))
        }
        ats_suffixes = {"greenhouse.io", "lever.co", "workdayjobs.com", "smartrecruiters.com", "personio.com", "recruitee.com", "ashbyhq.com"}
        portal_hosts = {"linkedin.com", "indeed.com", "glassdoor.com", "stepstone.de", "ziprecruiter.com", "monster.com", "careerbuilder.com"}
        source_urls = {str(base.get("canonical_url") or "").strip()}
        source_urls.update(str(row["original_url"] or "").strip() for row in observations)
        source_urls.update(str(row["url"] or "").strip() for row in aliases)
        candidates: list[dict[str, Any]] = []
        seen_candidates: set[str] = set()

        def add_candidate(value: Any, source: str, evidence: str, path: str = "") -> None:
            url = str(value or "").strip()
            if not url or not urlsplit(url).scheme.casefold() in {"http", "https"} or url in seen_candidates:
                return
            seen_candidates.add(url)
            host = hostname_for_url(url)
            url_type = classify_job_url(
                url,
                target={**target, "official_employer_hosts": list(company_hosts | target_hosts)},
                source_ats=connector,
            )
            classification = {
                "employer_application": "external_employer",
                "ats_application": "external_ats",
                "employer_job_detail": "listing_fallback",
                "ats_job_detail": "listing_fallback",
                "careers_index": "listing_fallback",
                "search_results": "listing_fallback",
                "portal_listing": "listing_fallback",
            }.get(url_type, "unknown")
            candidates.append(
                {
                    "url": url,
                    "source": source,
                    "path": path or None,
                    "classification": classification,
                    "url_type": url_type,
                    "verified_direct": url_type in DIRECT_APPLICATION_CLASSIFICATIONS,
                    "evidence": [evidence] if evidence else [],
                }
            )

        def walk(value: Any, path: str = "") -> None:
            if isinstance(value, Mapping):
                for key, child in value.items():
                    child_path = f"{path}.{key}" if path else str(key)
                    key_text = str(key).casefold()
                    if isinstance(child, str) and ("url" in key_text or "link" in key_text or key_text in {"href", "hostedurl", "absolute_url"}):
                        if not any(token in key_text for token in ("logo", "image", "website", "linkedin")):
                            add_candidate(child, str(key), f"raw_payload:{child_path}", child_path)
                    walk(child, child_path)
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, f"{path}[{index}]")

        add_candidate(base.get("canonical_url"), "canonical_url", "canonical_job.canonical_url")
        for row in observations:
            add_candidate(row["original_url"], "original_url", f"source_observation:{row['observation_id']}")
            add_candidate(row["apply_url"], "apply_url", f"source_observation:{row['observation_id']}")
            walk(_decode(row["payload_json"], {}), f"source_observation:{row['observation_id']}.payload")
        for row in versions:
            add_candidate(row["apply_url"], "apply_url", f"posting_version:{row['version_id']}")
            walk(_decode(row["payload_json"], {}), f"posting_version:{row['version_id']}.payload")
        for row in aliases:
            add_candidate(row["url"], "url_alias", f"url_alias:{row['alias_id']}")

        stored_apply = str(job.get("apply_url") or "").strip()
        direct_candidates = [item for item in candidates if item.get("verified_direct")]
        selected_apply = next((item for item in direct_candidates if item["url"] == stored_apply), None)
        selected_apply = selected_apply or (direct_candidates[0] if direct_candidates else None)
        audit_rows = self._inspection_rows(audit_events, ("payload_json",))
        resolution_audits = [item for item in audit_rows if isinstance(item.get("payload"), Mapping) and item["payload"].get("action") == "resolve_apply_url"]
        if selected_apply is not None:
            source_verified = bool(current_payload.get("employer_verified")) or connector in {"greenhouse", "lever"}
            apply_status = "verified" if source_verified and selected_apply["url"] == stored_apply else "unverified"
            apply_classification = selected_apply["classification"]
            resolved_url = selected_apply["url"]
            user_facing_url = resolved_url if apply_status == "verified" else None
            apply_evidence = list(selected_apply.get("evidence") or [])
            if source_verified:
                apply_evidence.append("phase_b_official_apply_destination_gate")
        elif candidates:
            apply_status = "unresolved"
            apply_classification = candidates[0]["classification"]
            resolved_url = None
            user_facing_url = candidates[0].get("url")
            apply_evidence = ["Only a job-detail, listing, portal, or unclassified URL candidate was found; it is not a verified direct-apply destination."]
        else:
            apply_status = "missing"
            apply_classification = "unknown"
            resolved_url = None
            user_facing_url = None
            apply_evidence = ["No application URL candidate was stored by the source."]
        apply_url = {
            "source_url": next(iter(source_urls - {""}), None),
            "candidate_urls": candidates,
            "resolved_url": resolved_url,
            "user_facing_url": user_facing_url,
            "status": apply_status,
            "classification": apply_classification,
            "url_type": (selected_apply or (candidates[0] if candidates else {})).get("url_type", "unknown"),
            "application_method": job.get("application_method") or "unknown",
            "warnings": list(dict.fromkeys(job.get("quality_warnings") or [])),
            "verified_at": (resolution_audits[0].get("created_at") if resolution_audits else (base.get("last_verified_at") or None)) if apply_status == "verified" else None,
            "evidence": list(dict.fromkeys(apply_evidence)),
        }

        observation_payloads = self._inspection_rows(observations, ("payload_json", "raw_payload_json"))
        version_payloads = self._inspection_rows(versions, ("payload_json",))
        request_payloads = self._inspection_rows(requests, ("detail_json",))
        rejection_payloads = self._inspection_rows(rejections, ("detail_json",))
        decision_payloads = self._inspection_rows(decisions)
        publication_payloads = self._inspection_rows(publication_rows, ("snapshot_json",))
        cycle_payloads = self._inspection_rows(cycles)
        task_payloads = self._inspection_rows(tasks)
        attempt_payloads = self._inspection_rows(attempts)
        audit_payloads = audit_rows
        import_payloads = self._inspection_rows(imports, ("source_ids_json", "scope_json", "plan_json"))
        source_state_payloads = self._inspection_rows(source_states)
        alias_payloads = self._inspection_rows(aliases)
        external_id_payloads = self._inspection_rows(external_ids)
        relationship_payloads = self._inspection_rows(relationships)
        observation_relationship_payloads = self._inspection_rows(observation_relationships)
        quality_event_payloads = self._inspection_rows(quality_events, ("details_json",))
        version_quality_payloads = [
            {**_dict_row(row), "report": _decode(row["report_json"], {})}
            for row in version_quality
        ]
        provenance_payloads = self._inspection_rows(field_provenance, ("raw_value_json", "normalized_value_json", "evidence_json"))
        rule_output_payloads = self._inspection_rows(rule_outputs, ("output_json",))
        company_url_payloads = self._inspection_rows(company_urls)
        company["urls"] = company_url_payloads
        company["field_provenance"] = [item for item in provenance_payloads if item.get("entity_kind") == "company"]
        job["field_provenance"] = [item for item in provenance_payloads if item.get("entity_kind") == "job"]
        job["rule_outputs"] = rule_output_payloads
        completeness_payloads = [
            {**_dict_row(row), "report": _decode(row["report_json"], {})}
            for row in completeness_reports
        ]
        duplicate_payloads = self._inspection_rows(duplicate_clusters, ("reasons_json", "review_history_json", "member_reasons_json"))

        latest_decision = decision_payloads[0] if decision_payloads else {}
        current_publication = next((item for item in publication_payloads if item.get("current_head")), None)
        admin = {
            "canonical_job_id": job_id,
            "canonical_company_id": company_id,
            "external_source_job_ids": external_id_payloads,
            "target_id": str(target.get("target_id") or (target_ids[0] if target_ids else "")) or None,
            "connector": connector or None,
            "provider": target.get("provider") or None,
            "source_observation_ids": observation_ids,
            "original_urls": list(dict.fromkeys(str(row["original_url"] or "") for row in observations if str(row["original_url"] or ""))),
            "first_seen_at": base.get("first_seen_at"),
            "last_seen_at": base.get("last_seen_at"),
            "last_verified_at": base.get("last_verified_at") or None,
            "posting_version_id": base.get("current_version_id") or None,
            "posting_version": base.get("version_number"),
            "content_hash": base.get("content_hash") or None,
            "acquisition_cycle_ids": cycle_ids,
            "acquisition_task_ids": task_ids,
            "acquisition_attempt_ids": [str(item.get("attempt_id") or "") for item in attempt_payloads],
            "acquisition_request_ids": [str(item.get("request_id") or "") for item in request_payloads],
            "request_count": len(request_payloads),
            "scrapeops_credits_estimated": sum(int(item.get("credits_estimated") or 0) for item in request_payloads),
            "scrapeops_credits_actual": sum(int(item.get("credits_actual") or 0) for item in request_payloads),
            "deduplication": {
                "identity_key": base.get("identity_key"),
                "identity_signature": base.get("identity_signature") or None,
                "result": "canonical",
                "relationship_count": len(relationship_payloads),
            },
            "review": latest_decision or None,
            "review_state": latest_decision.get("decision") or ("already_live" if current_publication else "needs_review"),
            "publication": current_publication,
            "publication_status": current_publication.get("status") if current_publication else None,
            "rejection_count": len(rejection_payloads),
        }

        raw = {
            "source_observations": observation_payloads,
            "posting_versions": version_payloads,
            "company_profile": profile if profile else None,
            "acquisition_cycles": cycle_payloads,
            "acquisition_tasks": task_payloads,
            "acquisition_attempts": attempt_payloads,
            "acquisition_requests": request_payloads,
            "rejections": rejection_payloads,
            "review_decisions": decision_payloads,
            "publication": current_publication,
            "publications": publication_payloads,
            "audit_events": audit_payloads,
            "imports": import_payloads,
            "targets": target_items,
            "source_states": source_state_payloads,
            "external_ids": external_id_payloads,
            "url_aliases": alias_payloads,
            "relationships": relationship_payloads,
            "observation_relationships": observation_relationship_payloads,
            "quality_events": quality_event_payloads,
            "version_quality": version_quality_payloads,
            "field_provenance": provenance_payloads,
            "rule_outputs": rule_output_payloads,
            "company_urls": company_url_payloads,
            "completeness_reports": completeness_payloads,
            "duplicate_clusters": duplicate_payloads,
        }
        job_fields = {
            key: job.get(key)
            for key in ("canonical_job_id", "company_id", "title", "company", "location_raw", "description", "posted_at", "apply_url", "source_url")
        }
        company_fields = {
            key: company.get(key)
            for key in ("canonical_company_id", "name", "website", "careers_page", "industry", "company_size", "headquarters", "founded_year", "company_stage", "funding_stage", "total_funding", "funding_year", "leadership_type", "benefits", "sponsorship", "logo_url")
        }
        admin_fields = {
            key: admin.get(key)
            for key in ("canonical_job_id", "canonical_company_id", "target_id", "connector", "provider", "source_observation_ids", "posting_version_id", "content_hash", "first_seen_at", "last_seen_at", "review_state", "publication_status")
        }
        source_fields = {
            "target_id": admin.get("target_id"),
            "source_observation_ids": observation_ids,
            "external_job_id": external_job_ids[0] if external_job_ids else "",
        }
        coverage = completeness_rules(job=job, company=company, source=source_fields, admin=admin)
        for category in ("job", "company", "source", "admin"):
            if category in coverage.get("categories", {}):
                coverage[category] = coverage["categories"][category]
        coverage["overall_percent"] = round(
            100 * int(coverage["overall"]["present"])
            / max(1, int(coverage["overall"]["total"])),
        )
        coverage["critical_checks"] = [
            {
                "name": item["name"].replace("_", " ").title(),
                "status": "pass" if item["status"] == "pass" else "warning",
                "detail": "Rule passed" if item["status"] == "pass" else "Report-only quality warning",
                "blocking": False,
            }
            for item in coverage.get("all_rules", [])
        ]
        return {
            "job": job,
            "company": company,
            "admin": admin,
            "completeness": coverage,
            "apply_url": apply_url,
            "raw": raw,
        }

    def list_admin_duplicate_clusters(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.*, m.canonical_job_id, m.member_score, m.member_reasons_json,
                       j.title, j.location, co.canonical_name AS company
                FROM acquisition_duplicate_clusters c
                JOIN acquisition_duplicate_members m ON m.cluster_id=c.cluster_id
                LEFT JOIN canonical_jobs j ON j.canonical_job_id=m.canonical_job_id
                LEFT JOIN canonical_companies co ON co.company_id=j.company_id
                ORDER BY c.updated_at DESC, c.cluster_id, m.canonical_job_id
                LIMIT ?
                """,
                (max(1, min(500, int(limit))),),
            ).fetchall()
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = _dict_row(row)
            cluster_id = str(item.pop("cluster_id"))
            member = {
                key: item.pop(key)
                for key in ("canonical_job_id", "member_score", "member_reasons_json", "title", "location", "company")
                if key in item
            }
            member["member_reasons"] = _decode(member.pop("member_reasons_json", "[]"), [])
            cluster = grouped.setdefault(cluster_id, {"cluster_id": cluster_id, **item, "members": []})
            cluster["reasons"] = _decode(cluster.pop("reasons_json", "[]"), [])
            cluster["review_history"] = _decode(cluster.pop("review_history_json", "[]"), [])
            cluster["members"].append(member)
        result = list(grouped.values())
        if result:
            cluster_ids = [str(item.get("cluster_id") or "") for item in result]
            placeholders = ",".join("?" for _ in cluster_ids)
            with self._connect() as connection:
                decision_rows = connection.execute(
                    f"SELECT * FROM acquisition_duplicate_decisions WHERE cluster_id IN ({placeholders}) ORDER BY created_at, decision_id",
                    tuple(cluster_ids),
                ).fetchall()
            decisions_by_cluster: dict[str, list[dict[str, Any]]] = {}
            for row in decision_rows:
                decision = _dict_row(row)
                decision["evidence"] = _decode(decision.pop("evidence_json", "{}"), {})
                decision["affected_ids"] = _decode(decision.pop("affected_ids_json", "[]"), [])
                decisions_by_cluster.setdefault(str(decision.get("cluster_id") or ""), []).append(decision)
            for item in result:
                item["decision_history"] = decisions_by_cluster.get(str(item.get("cluster_id") or ""), [])
                item["current_decision"] = item["decision_history"][-1] if item["decision_history"] else None
        return result

    def record_admin_duplicate_decision(
        self,
        cluster_id: str,
        *,
        decision: str,
        actor_user_id: str,
        reason: str,
        evidence: Mapping[str, Any],
        affected_ids: Iterable[str] | None = None,
        rule_version: str = "",
        merge_plan: Mapping[str, Any] | None = None,
        split_plan: Mapping[str, Any] | None = None,
        undo_plan: Mapping[str, Any] | None = None,
        supersedes_decision_id: str = "",
    ) -> dict[str, Any]:
        """Append an explicit duplicate annotation without merging or publishing.

        The decision table is an immutable event log.  The existing cluster row
        is only a current-state projection; members and all source/canonical
        records are intentionally untouched.
        """

        cluster_id = str(cluster_id or "").strip()
        target = str(decision or "").strip().casefold()
        if not cluster_id or not target:
            raise ValueError("cluster_id and decision are required")
        if not isinstance(evidence, Mapping) or not evidence:
            raise ValueError("evidence must be a non-empty object")
        if any(str(key).casefold() in {"raw_payload", "source_raw_payload", "payload_json"} for key in evidence):
            raise ValueError("raw payloads are not accepted in duplicate decisions")
        allowed = {"candidate", "confirmed_duplicate", "distinct", "ignored", "merged", "split", "undone"}
        if target not in allowed:
            raise ValueError(f"unsupported duplicate decision: {target}")
        now = utc_now_iso()
        with self._connect() as connection:
            cluster = connection.execute(
                "SELECT * FROM acquisition_duplicate_clusters WHERE cluster_id=?",
                (cluster_id,),
            ).fetchone()
            if cluster is None:
                raise KeyError(f"Duplicate cluster '{cluster_id}' not found.")
            members = connection.execute(
                "SELECT canonical_job_id FROM acquisition_duplicate_members WHERE cluster_id=? ORDER BY canonical_job_id",
                (cluster_id,),
            ).fetchall()
            member_ids = [str(row["canonical_job_id"] or "") for row in members if row["canonical_job_id"]]
            ids = [str(item).strip() for item in (affected_ids or member_ids) if str(item).strip()]
            if set(ids) != set(member_ids) and member_ids:
                raise ValueError("affected_ids must match the cluster members")
            previous = connection.execute(
                "SELECT * FROM acquisition_duplicate_decisions WHERE cluster_id=? ORDER BY created_at DESC, decision_id DESC LIMIT 1",
                (cluster_id,),
            ).fetchone()
            current_state = str((previous["decision"] if previous is not None else cluster["state"]) or "candidate").casefold()
            from backend.application.duplicate_decisions import ALLOWED_TRANSITIONS

            if target != "candidate" and target not in ALLOWED_TRANSITIONS.get(current_state, frozenset()):
                raise ValueError(f"cannot transition duplicate cluster from {current_state} to {target}")
            if target == "merged" and not isinstance(merge_plan, Mapping):
                raise ValueError("merged requires merge_plan; no merge was performed")
            if target == "split" and not isinstance(split_plan, Mapping):
                raise ValueError("split requires split_plan; no split was performed")
            decision_id = f"duplicate_decision_{uuid4().hex}"
            event = {
                "event_id": decision_id,
                "cluster_id": cluster_id,
                "from_state": current_state,
                "to_state": target,
                "actor": str(actor_user_id or ""),
                "reason": str(reason or ""),
                "evidence": dict(evidence),
                "affected_ids": ids,
                "rule_version": str(rule_version or UNIFIED_RULE_VERSION),
                "recorded_at": now,
                "merge_plan": dict(merge_plan) if isinstance(merge_plan, Mapping) else None,
                "split_plan": dict(split_plan) if isinstance(split_plan, Mapping) else None,
                "undo_plan": dict(undo_plan) if isinstance(undo_plan, Mapping) else None,
                "automatic_merge": False,
                "automatic_publish": False,
            }
            connection.execute(
                """
                INSERT INTO acquisition_duplicate_decisions (
                    decision_id, cluster_id, decision, actor_user_id, reason,
                    evidence_json, affected_ids_json, rule_version,
                    supersedes_decision_id, undone_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id, cluster_id, target, str(actor_user_id or ""), str(reason or ""),
                    _json(event), _json(ids), str(rule_version or UNIFIED_RULE_VERSION),
                    str(supersedes_decision_id or (previous["decision_id"] if previous is not None else "")),
                    now if target == "undone" else "", now,
                ),
            )
            history = _decode(cluster["review_history_json"], [])
            if not isinstance(history, list):
                history = []
            history.append(event)
            connection.execute(
                """
                UPDATE acquisition_duplicate_clusters
                SET state=?, review_history_json=?, rule_version=?, updated_at=?
                WHERE cluster_id=?
                """,
                (target, _json(history), str(rule_version or UNIFIED_RULE_VERSION), now, cluster_id),
            )
            rows = connection.execute(
                "SELECT * FROM acquisition_duplicate_decisions WHERE cluster_id=? ORDER BY created_at, decision_id",
                (cluster_id,),
            ).fetchall()
        events = [_dict_row(row) for row in rows]
        for item in events:
            item["evidence"] = _decode(item.pop("evidence_json", "{}"), {})
            item["affected_ids"] = _decode(item.pop("affected_ids_json", "[]"), [])
        return {
            "cluster_id": cluster_id,
            "decision": event,
            "history": events,
            "automatic_merge": False,
            "automatic_publish": False,
        }

    def undo_admin_duplicate_decision(
        self,
        cluster_id: str,
        *,
        actor_user_id: str,
        reason: str,
        evidence: Mapping[str, Any],
        rule_version: str = "",
    ) -> dict[str, Any]:
        with self._connect() as connection:
            prior = connection.execute(
                "SELECT decision_id, affected_ids_json FROM acquisition_duplicate_decisions WHERE cluster_id=? ORDER BY created_at DESC, decision_id DESC LIMIT 1",
                (str(cluster_id),),
            ).fetchone()
        if prior is None:
            raise ValueError("duplicate cluster has no decision to undo")
        return self.record_admin_duplicate_decision(
            cluster_id,
            decision="undone",
            actor_user_id=actor_user_id,
            reason=reason,
            evidence=evidence,
            affected_ids=_decode(prior["affected_ids_json"], []),
            rule_version=rule_version,
            undo_plan={
                "undo_of_decision_id": str(prior["decision_id"]),
                "preserve_source_observations": True,
                "preserve_posting_versions": True,
                "preserve_provenance": True,
                "automatic_merge": False,
                "automatic_publish": False,
            },
            supersedes_decision_id=str(prior["decision_id"]),
        )

    def list_admin_companies(self, *, limit: int = 100, search: str = "") -> list[dict[str, Any]]:
        normalized = " ".join(str(search or "").casefold().split())
        predicate = "WHERE LOWER(c.canonical_name || ' ' || COALESCE(c.provenance_url, '')) LIKE ?" if normalized else ""
        params: tuple[Any, ...] = (f"%{normalized}%",) if normalized else ()
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT c.*, p.profile_json, p.logo_source_url, p.logo_verified_at,
                       (SELECT COUNT(*) FROM canonical_jobs j WHERE j.company_id=c.company_id) AS job_count
                FROM canonical_companies c
                LEFT JOIN canonical_company_profiles p ON p.company_id=c.company_id
                {predicate}
                ORDER BY c.canonical_name LIMIT ?
                """,
                (*params, max(1, min(500, int(limit)))),
            ).fetchall()
            company_ids = [str(row["company_id"]) for row in rows]
            urls = []
            if company_ids:
                placeholders = ",".join("?" for _ in company_ids)
                urls = connection.execute(
                    f"SELECT * FROM canonical_company_urls WHERE company_id IN ({placeholders}) ORDER BY company_id, url_type, updated_at DESC",
                    tuple(company_ids),
                ).fetchall()
        urls_by_company: dict[str, list[dict[str, Any]]] = {}
        for row in urls:
            urls_by_company.setdefault(str(row["company_id"]), []).append(_dict_row(row))
        result = []
        for row in rows:
            item = _dict_row(row)
            item["profile"] = _decode(item.pop("profile_json", "{}"), {})
            item["urls"] = urls_by_company.get(str(item["company_id"]), [])
            result.append(item)
        return result

    def get_admin_company_detail(self, company_id: str) -> dict[str, Any] | None:
        company_id = str(company_id or "").strip()
        if not company_id:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT c.*, p.profile_json, p.logo_source_url, p.logo_verified_at,
                       (SELECT COUNT(*) FROM canonical_jobs j WHERE j.company_id=c.company_id) AS job_count
                FROM canonical_companies c
                LEFT JOIN canonical_company_profiles p ON p.company_id=c.company_id
                WHERE c.company_id=?
                """,
                (company_id,),
            ).fetchone()
            if row is None:
                return None
            urls = connection.execute(
                "SELECT * FROM canonical_company_urls WHERE company_id=? ORDER BY url_type, selected_primary DESC, updated_at DESC",
                (company_id,),
            ).fetchall()
            logos = connection.execute(
                "SELECT * FROM company_logo_enrichments WHERE company_id=? ORDER BY updated_at DESC",
                (company_id,),
            ).fetchall()
        result = _dict_row(row)
        result["profile"] = _decode(result.pop("profile_json", "{}"), {})
        result["urls"] = [_dict_row(item) for item in urls]
        result["logo_enrichments"] = []
        for item in logos:
            value = _dict_row(item)
            value["terms_metadata"] = _decode(value.pop("terms_metadata_json", "{}"), {})
            value["provenance"] = _decode(value.pop("provenance_json", "{}"), {})
            result["logo_enrichments"].append(value)
        return result

    def record_connector_capability_snapshot(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        snapshot_id = str(snapshot.get("snapshot_id") or f"capability_{uuid4().hex}")
        now = utc_now_iso()
        connector = str(snapshot.get("connector") or "").strip()
        if not connector:
            raise ValueError("connector is required")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO acquisition_connector_capability_snapshots (
                    snapshot_id, connector, target_id, capability_json,
                    raw_retention_json, observed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id, connector, str(snapshot.get("target_id") or ""),
                    _json(snapshot.get("capabilities") or snapshot.get("capability") or {}),
                    _json(snapshot.get("raw_retention") or snapshot.get("retention") or {}),
                    str(snapshot.get("observed_at") or now), now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM acquisition_connector_capability_snapshots WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
        result = _dict_row(row) if row is not None else dict(snapshot)
        result["capabilities"] = _decode(result.pop("capability_json", "{}"), {})
        result["raw_retention"] = _decode(result.pop("raw_retention_json", "{}"), {})
        return result

    def list_admin_connector_capabilities(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM acquisition_connector_capability_snapshots ORDER BY observed_at DESC, connector LIMIT ?",
                (max(1, min(1000, int(limit))),),
            ).fetchall()
        result = []
        for row in rows:
            item = _dict_row(row)
            item["capabilities"] = _decode(item.pop("capability_json", "{}"), {})
            item["raw_retention"] = _decode(item.pop("raw_retention_json", "{}"), {})
            result.append(item)
        return result

    def get_admin_rules_coverage(self) -> dict[str, Any]:
        with self._connect() as connection:
            field_rows = connection.execute(
                "SELECT entity_kind, field_name, state, COUNT(*) AS count FROM acquisition_field_provenance GROUP BY entity_kind, field_name, state ORDER BY entity_kind, field_name, state"
            ).fetchall()
            stage_rows = connection.execute(
                "SELECT stage_name, status, COUNT(*) AS count FROM acquisition_stage_results GROUP BY stage_name, status ORDER BY stage_name, status"
            ).fetchall()
            completeness = connection.execute(
                "SELECT state, COUNT(*) AS count FROM acquisition_completeness_reports GROUP BY state ORDER BY state"
            ).fetchall()
            warning_rows = connection.execute(
                "SELECT warning_code, severity, COUNT(*) AS count FROM acquisition_quality_events GROUP BY warning_code, severity ORDER BY warning_code, severity"
            ).fetchall()
        return {
            "rule_version": UNIFIED_RULE_VERSION,
            "field_states": [_dict_row(row) for row in field_rows],
            "stage_states": [_dict_row(row) for row in stage_rows],
            "completeness_states": [_dict_row(row) for row in completeness],
            "warnings": [_dict_row(row) for row in warning_rows],
            "report_only": True,
        }

    def list_admin_reprocessing_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM acquisition_reprocessing_runs ORDER BY created_at DESC LIMIT ?",
                (max(1, min(200, int(limit))),),
            ).fetchall()
        result = []
        for row in rows:
            item = _dict_row(row)
            for key in ("environment_json", "scope_json", "plan_json", "checkpoint_json", "counts_json", "backup_json", "error_json"):
                item[key[:-5]] = _decode(item.pop(key, "{}"), {})
            result.append(item)
        return result

    def get_admin_publication_read_model(self) -> dict[str, Any]:
        with self._connect() as connection:
            counts = connection.execute("SELECT status, COUNT(*) AS count FROM acquisition_publications GROUP BY status ORDER BY status").fetchall()
            head = connection.execute(
                "SELECT h.*, p.status, p.published_at, p.rule_version FROM acquisition_publication_head h LEFT JOIN acquisition_publications p ON p.publication_id=h.publication_id WHERE h.head_id=1"
            ).fetchone()
            jobs = connection.execute(
                "SELECT COUNT(*) AS count FROM acquisition_publication_jobs pj JOIN acquisition_publication_head h ON h.publication_id=pj.publication_id AND h.head_id=1"
            ).fetchone()
        return {"rule_version": UNIFIED_RULE_VERSION, "publication_states": [_dict_row(row) for row in counts], "current_head": _dict_row(head) if head else None, "current_job_count": int(jobs["count"] or 0) if jobs else 0, "automatic_promotion": False}

    def resolve_admin_job_apply_url(self, canonical_job_id: str, *, actor_user_id: str = "") -> dict[str, Any]:
        """Resolve only an employer/official-ATS candidate already in raw data."""

        inspection = self.get_admin_job_inspection(canonical_job_id)
        if inspection is None:
            raise KeyError(f"Canonical job '{canonical_job_id}' not found.")
        candidates = inspection.get("apply_url", {}).get("candidate_urls") or []
        candidate = next(
            (item for item in candidates if item.get("classification") in {"external_employer", "external_ats"}),
            None,
        )
        now = utc_now_iso()
        admin = inspection.get("admin") or {}
        import_ids = [str(item.get("import_id") or "") for item in (inspection.get("raw", {}).get("imports") or []) if item.get("import_id")]
        import_id = import_ids[0] if import_ids else ""
        with self._connect() as connection:
            if candidate is not None:
                current = connection.execute(
                    "SELECT * FROM job_posting_versions WHERE version_id=?",
                    (str(inspection["job"].get("current_version_id") or ""),),
                ).fetchone()
                if current is None:
                    raise ValueError("The canonical job has no current posting version to update.")
                payload = _decode(current["payload_json"], {})
                payload = dict(payload) if isinstance(payload, Mapping) else {}
                selected_url = str(candidate.get("url") or "")
                payload.update(
                    {
                        "apply_url": selected_url,
                        "apply_link": selected_url,
                        "user_facing_apply_url": selected_url,
                        "apply_url_resolution_status": "verified_official_ats" if candidate.get("classification") == "external_ats" else "verified_external_employer",
                        "apply_url_resolution": {
                            "resolved_url": selected_url,
                            "classification": candidate.get("classification"),
                            "resolved_at": now,
                            "source": candidate.get("source"),
                        },
                    }
                )
                self._ensure_version(
                    connection,
                    str(canonical_job_id),
                    title=str(current["title"] or inspection["job"].get("title") or ""),
                    description=str(current["description"] or inspection["job"].get("description") or ""),
                    location=str(current["location"] or inspection["job"].get("location_raw") or ""),
                    apply_url=selected_url,
                    content_hash=self._payload_hash(payload),
                    source_observation_id=str(current["source_observation_id"] or admin.get("source_observation_ids", [""])[0]),
                    payload=payload,
                    now=now,
                )
                result = {
                    "action": "resolve_apply_url",
                    "status": "resolved",
                    "resolved_url": selected_url,
                    "classification": candidate.get("classification"),
                    "evidence": candidate.get("evidence") or [],
                }
            else:
                result = {
                    "action": "resolve_apply_url",
                    "status": "failed",
                    "reason": "No employer or official ATS application candidate was found. Listing and portal URLs were not accepted.",
                }
            connection.execute(
                """
                INSERT INTO admin_job_audit_events (
                    event_id, import_id, actor_user_id, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, 'apply_url_resolution', ?, ?)
                """,
                (f"admin_audit_{uuid4().hex}", import_id, str(actor_user_id or ""), _json(result), now),
            )
        return self.get_admin_job_inspection(str(canonical_job_id)) or inspection

    def record_job_review_decision(
        self,
        *,
        import_id: str,
        canonical_job_id: str,
        decision: str,
        actor_user_id: str,
        reason_code: str = "",
    ) -> dict[str, Any]:
        normalized_decision = str(decision or "").strip().casefold()
        if normalized_decision in {"approve", "approved"}:
            normalized_decision = "approved"
        elif normalized_decision in {"reject", "rejected", "not_accepted"}:
            normalized_decision = "not_accepted"
        else:
            raise ValueError("Decision must be approve or reject.")
        now = utc_now_iso()
        import_payload = self.get_job_import(import_id)
        if not import_payload:
            raise KeyError(f"Import '{import_id}' not found.")
        with self._connect() as connection:
            exists = connection.execute(
                """
                SELECT 1 FROM job_source_observations
                WHERE cycle_id=? AND canonical_job_id=? LIMIT 1
                """,
                (str(import_payload.get("cycle_id") or ""), str(canonical_job_id)),
            ).fetchone()
            if exists is None:
                raise KeyError(f"Job '{canonical_job_id}' is not part of import '{import_id}'.")
            connection.execute(
                """
                INSERT INTO admin_job_review_decisions (
                    decision_id, import_id, canonical_job_id, decision, reason_code,
                    actor_user_id, created_at, undone_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '')
                ON CONFLICT(import_id, canonical_job_id) DO UPDATE SET
                    decision=excluded.decision, reason_code=excluded.reason_code,
                    actor_user_id=excluded.actor_user_id, created_at=excluded.created_at, undone_at=''
                """,
                (
                    f"admin_decision_{uuid4().hex}",
                    str(import_id),
                    str(canonical_job_id),
                    normalized_decision,
                    str(reason_code or ""),
                    str(actor_user_id or ""),
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO admin_job_audit_events (
                    event_id, import_id, actor_user_id, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, 'review_decision', ?, ?)
                """,
                (
                    f"admin_audit_{uuid4().hex}",
                    str(import_id),
                    str(actor_user_id or ""),
                    _json({"canonical_job_id": str(canonical_job_id), "decision": normalized_decision, "reason_code": str(reason_code or "")}),
                    now,
                ),
            )
        reviewed = self.list_review_jobs(import_id=import_id, status="all", limit=200, offset=0).get("jobs", [])
        return next(
            (item for item in reviewed if str(item.get("canonical_job_id") or "") == str(canonical_job_id)),
            {},
        )

    def undo_job_review_decision(self, *, import_id: str, canonical_job_id: str, actor_user_id: str) -> None:
        now = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                "UPDATE admin_job_review_decisions SET decision='', undone_at=?, actor_user_id=?, created_at=? WHERE import_id=? AND canonical_job_id=?",
                (now, str(actor_user_id or ""), now, str(import_id), str(canonical_job_id)),
            )
            connection.execute(
                """
                INSERT INTO admin_job_audit_events (
                    event_id, import_id, actor_user_id, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, 'review_decision_undone', ?, ?)
                """,
                (f"admin_audit_{uuid4().hex}", str(import_id), str(actor_user_id or ""), _json({"canonical_job_id": str(canonical_job_id)}), now),
            )

    def _publication_snapshot_rows(self, connection, canonical_job_ids: Iterable[str]) -> list[dict[str, Any]]:
        ids = tuple(dict.fromkeys(str(item) for item in canonical_job_ids if str(item).strip()))
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = connection.execute(
            f"""
            SELECT j.canonical_job_id, c.canonical_name AS company, j.title, j.location,
                   j.canonical_url, COALESCE(v.apply_url, '') AS apply_url,
                   j.lifecycle_state, j.current_version_id, v.description,
                   v.payload_json AS source_payload
            FROM canonical_jobs j
            JOIN canonical_companies c ON c.company_id=j.company_id
            LEFT JOIN job_posting_versions v ON v.version_id=j.current_version_id
            WHERE j.canonical_job_id IN ({placeholders})
            ORDER BY j.title, j.canonical_job_id
            """,
            ids,
        ).fetchall()
        result = []
        for row in rows:
            item = _dict_row(row)
            item["source_payload"] = _decode(item.get("source_payload"), {})
            result.append(item)
        return result

    def create_job_import_preview(self, import_id: str, *, actor_user_id: str = "") -> dict[str, Any]:
        import_payload = self.get_job_import(import_id)
        if not import_payload:
            raise KeyError(f"Import '{import_id}' not found.")
        cycle_id = str(import_payload.get("cycle_id") or "")
        if not cycle_id:
            raise ValueError("Import has not completed yet.")
        now = utc_now_iso()
        with self._connect() as connection:
            current = connection.execute(
                "SELECT publication_id FROM acquisition_publication_head WHERE head_id=1"
            ).fetchone()
            previous_publication_id = str(current["publication_id"] or "") if current is not None else ""
            current_ids = []
            if previous_publication_id:
                current_ids = [
                    str(row["canonical_job_id"])
                    for row in connection.execute(
                        """
                        SELECT pj.canonical_job_id
                        FROM acquisition_publication_jobs pj
                        WHERE pj.publication_id=?
                          AND EXISTS (
                              SELECT 1
                              FROM job_source_observations o
                              LEFT JOIN acquisition_targets t ON t.target_id=o.target_id
                              WHERE o.canonical_job_id=pj.canonical_job_id
                                AND COALESCE(t.quarantined, 0)=0
                                AND COALESCE(t.target_kind, '') <> 'fixture'
                          )
                        """,
                        (previous_publication_id,),
                    ).fetchall()
                ]
            approved_ids = [
                str(row["canonical_job_id"])
                for row in connection.execute(
                    """
                    SELECT d.canonical_job_id
                    FROM admin_job_review_decisions d
                    JOIN job_source_observations o ON o.canonical_job_id=d.canonical_job_id AND o.cycle_id=?
                    WHERE d.import_id=? AND d.decision='approved'
                    """,
                    (cycle_id, str(import_id)),
                ).fetchall()
            ]
            canonical_ids = tuple(dict.fromkeys([*current_ids, *approved_ids]))
            snapshot = self._publication_snapshot_rows(connection, canonical_ids)
            existing = connection.execute(
                "SELECT publication_id FROM acquisition_publications WHERE cycle_id=? AND status='staging' LIMIT 1",
                (cycle_id,),
            ).fetchone()
            publication_id = str(existing["publication_id"] or "") if existing is not None else f"acq_review_{uuid4().hex}"
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO acquisition_publications (
                        publication_id, cycle_id, status, snapshot_json, published_at,
                        valid_until, previous_publication_id
                    ) VALUES (?, ?, 'staging', ?, ?, '', ?)
                    """,
                    (publication_id, cycle_id, _json(snapshot), now, previous_publication_id),
                )
            else:
                connection.execute(
                    "UPDATE acquisition_publications SET snapshot_json=?, previous_publication_id=? WHERE publication_id=?",
                    (_json(snapshot), previous_publication_id, publication_id),
                )
                connection.execute("DELETE FROM acquisition_publication_jobs WHERE publication_id=?", (publication_id,))
            connection.executemany(
                "INSERT INTO acquisition_publication_jobs (publication_id, canonical_job_id) VALUES (?, ?)",
                [(publication_id, item) for item in canonical_ids],
            )
            connection.execute(
                "UPDATE admin_job_imports SET preview_publication_id=?, updated_at=? WHERE import_id=?",
                (publication_id, now, str(import_id)),
            )
            connection.execute(
                """
                INSERT INTO admin_job_audit_events (
                    event_id, import_id, actor_user_id, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, 'publication_preview_created', ?, ?)
                """,
                (
                    f"admin_audit_{uuid4().hex}",
                    str(import_id),
                    str(actor_user_id or ""),
                    _json({"publication_id": publication_id, "jobs": len(snapshot)}),
                    now,
                ),
            )
        return self.get_job_import_preview(publication_id) or {}

    def get_job_import_preview(self, publication_id: str = "") -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT publication_id, cycle_id, status, snapshot_json, published_at, valid_until, previous_publication_id FROM acquisition_publications WHERE publication_id=?",
                (str(publication_id or ""),),
            ).fetchone()
        if row is None:
            return None
        snapshot = _decode(row["snapshot_json"], [])
        return {
            "publication_id": str(row["publication_id"] or ""),
            "cycle_id": str(row["cycle_id"] or ""),
            "status": str(row["status"] or ""),
            "published_at": str(row["published_at"] or ""),
            "valid_until": str(row["valid_until"] or ""),
            "previous_publication_id": str(row["previous_publication_id"] or ""),
            "jobs": snapshot if isinstance(snapshot, list) else [],
            "total": len(snapshot) if isinstance(snapshot, list) else 0,
        }

    def publish_job_import_preview(self, publication_id: str, *, actor_user_id: str = "") -> str:
        promoted = self.promote_staging_publication(publication_id)
        now = utc_now_iso()
        with self._connect() as connection:
            import_row = connection.execute(
                "SELECT import_id FROM admin_job_imports WHERE preview_publication_id=?",
                (str(publication_id),),
            ).fetchone()
            import_id = str(import_row["import_id"] or "") if import_row is not None else ""
            if import_id:
                connection.execute(
                    "UPDATE admin_job_imports SET status='published', publication_id=?, updated_at=? WHERE import_id=?",
                    (str(publication_id), now, import_id),
                )
            connection.execute(
                """
                INSERT INTO admin_job_audit_events (
                    event_id, import_id, actor_user_id, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, 'publication_published', ?, ?)
                """,
                (f"admin_audit_{uuid4().hex}", import_id, str(actor_user_id or ""), _json({"publication_id": str(publication_id)}), now),
            )
        return promoted

    def undo_last_job_publication(self, *, actor_user_id: str = "") -> dict[str, Any]:
        now = utc_now_iso()

        def undo(connection):
            current = connection.execute(
                """
                SELECT p.publication_id, p.previous_publication_id
                FROM acquisition_publications p
                JOIN acquisition_publication_head h ON h.publication_id=p.publication_id AND h.head_id=1
                WHERE p.status='valid' LIMIT 1
                """
            ).fetchone()
            if current is None or not str(current["previous_publication_id"] or ""):
                return {"status": "nothing_to_undo"}
            previous_id = str(current["previous_publication_id"])
            previous = connection.execute(
                "SELECT publication_id, status FROM acquisition_publications WHERE publication_id=?",
                (previous_id,),
            ).fetchone()
            if previous is None:
                return {"status": "needs_attention", "reason": "previous_publication_missing"}
            connection.execute("UPDATE acquisition_publications SET status='undone' WHERE publication_id=?", (str(current["publication_id"]),))
            connection.execute(
                "UPDATE acquisition_publications SET status='valid' WHERE publication_id=?",
                (previous_id,),
            )
            connection.execute(
                "UPDATE acquisition_publication_head SET publication_id=?, updated_at=? WHERE head_id=1",
                (previous_id, now),
            )
            import_row = connection.execute(
                "SELECT import_id FROM admin_job_imports WHERE publication_id=? OR preview_publication_id=? ORDER BY created_at DESC LIMIT 1",
                (str(current["publication_id"]), str(current["publication_id"])),
            ).fetchone()
            import_id = str(import_row["import_id"] or "") if import_row is not None else ""
            connection.execute(
                """
                INSERT INTO admin_job_audit_events (
                    event_id, import_id, actor_user_id, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, 'publication_undone', ?, ?)
                """,
                (f"admin_audit_{uuid4().hex}", import_id, str(actor_user_id or ""), _json({"from": str(current["publication_id"]), "to": previous_id}), now),
            )
            return {"status": "undone", "restored_publication_id": previous_id, "undone_publication_id": str(current["publication_id"])}

        return self._run_transaction(undo)

    def list_job_import_audit_events(self, *, import_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
        predicates = []
        params: list[Any] = []
        if str(import_id or "").strip():
            predicates.append("import_id=?")
            params.append(str(import_id))
        sql = "SELECT * FROM admin_job_audit_events"
        if predicates:
            sql += " WHERE " + " AND ".join(predicates)
        sql += " ORDER BY created_at DESC, event_id DESC LIMIT ?"
        params.append(max(1, min(500, int(limit))))
        with self._connect() as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()
        result = []
        for row in rows:
            item = _dict_row(row)
            item["payload"] = _decode(item.pop("payload_json", "{}"), {})
            result.append(item)
        return result

    @staticmethod
    def _target_payload(row: dict[str, Any]) -> dict[str, Any]:
        row["enabled"] = _bool(row.get("enabled"))
        row["publication_enabled"] = _bool(row.get("publication_enabled"))
        row["quarantined"] = _bool(row.get("quarantined"))
        row["config"] = _decode(row.pop("config_json", "{}"), {})
        return row

    @staticmethod
    def _request_payload(row: dict[str, Any]) -> dict[str, Any]:
        row["credits_estimated"] = int(row.get("credits_estimated") or 0)
        row["credits_actual"] = int(row.get("credits_actual") or 0)
        row["direct_request"] = str(row.get("mode") or "") == "direct"
        row["detail"] = _decode(row.pop("detail_json", "{}"), {})
        return row

    @staticmethod
    def _freshness_status(last_success_at: Any) -> str:
        if not str(last_success_at or "").strip():
            return "stale"
        try:
            observed = datetime.fromisoformat(str(last_success_at).replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds() / 3600
        except ValueError:
            return "stale"
        if age_hours <= 30:
            return "healthy"
        if age_hours <= 48:
            return "degraded"
        return "stale"

    @staticmethod
    def _ensure_company(
        connection,
        name: str,
        entity_kind: str,
        now: str,
        *,
        provenance_url: str = "",
        aliases: Iterable[str] = (),
    ) -> str:
        normalized_name = company_name_key(name)
        row = connection.execute(
            "SELECT company_id FROM canonical_companies WHERE canonical_name = ? AND entity_kind = ?",
            (name, entity_kind),
        ).fetchone()
        if row is None and normalized_name:
            candidates = connection.execute(
                "SELECT company_id, canonical_name FROM canonical_companies WHERE entity_kind = ?",
                (entity_kind,),
            ).fetchall()
            row = next(
                (candidate for candidate in candidates if company_name_key(candidate["canonical_name"]) == normalized_name),
                None,
            )
        if row is None and normalized_name:
            alias_rows = connection.execute(
                "SELECT company_id FROM canonical_company_aliases WHERE alias_key=?",
                (normalized_name,),
            ).fetchall()
            if len(alias_rows) == 1:
                row = connection.execute(
                    "SELECT company_id FROM canonical_companies WHERE company_id=? AND entity_kind=?",
                    (str(alias_rows[0]["company_id"]), entity_kind),
                ).fetchone()
        if row is not None:
            if provenance_url:
                connection.execute(
                    "UPDATE canonical_companies SET provenance_url=?, updated_at=? "
                    "WHERE company_id=? AND provenance_url=''",
                    (provenance_url, now, str(row["company_id"])),
                )
            company_id = str(row["company_id"])
            for alias in aliases:
                SqliteAcquisitionStore._ensure_company_alias(connection, company_id, alias, source="target", now=now)
            return company_id
        company_id = f"canonical_company_{uuid4().hex}"
        connection.execute(
            """
            INSERT INTO canonical_companies (
                company_id, canonical_name, entity_kind, provenance_url, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (company_id, name, entity_kind, provenance_url, now, now),
        )
        for alias in aliases:
            SqliteAcquisitionStore._ensure_company_alias(connection, company_id, alias, source="target", now=now)
        return company_id

    @staticmethod
    def _ensure_company_alias(connection, company_id: str, alias: str, *, source: str, now: str) -> None:
        display = str(alias or "").strip()
        alias_key = company_name_key(display)
        if not alias_key:
            return
        owner = connection.execute(
            "SELECT company_id FROM canonical_company_aliases WHERE alias_key=?",
            (alias_key,),
        ).fetchone()
        if owner is not None and str(owner["company_id"]) != str(company_id):
            return
        connection.execute(
            """
            INSERT INTO canonical_company_aliases (
                alias_id, company_id, alias_key, alias_display, source, confidence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'verified', ?, ?)
            ON CONFLICT(alias_key) DO UPDATE SET
                company_id=excluded.company_id, alias_display=excluded.alias_display,
                source=excluded.source, updated_at=excluded.updated_at
            """,
            (f"company_alias_{uuid4().hex}", str(company_id), alias_key, display, str(source or ""), now, now),
        )

    @staticmethod
    def _record_quality_event(
        connection,
        *,
        cycle_id: str,
        task_id: str,
        target_id: str,
        canonical_job_id: str,
        company_id: str,
        employer_name: str,
        connector: str,
        source_token: str,
        warning_code: str,
        details: Mapping[str, Any] | None = None,
        severity: str = "warning",
    ) -> None:
        connection.execute(
            """
            INSERT INTO acquisition_quality_events (
                event_id, cycle_id, task_id, target_id, canonical_job_id, company_id,
                employer_name, connector, source_token, warning_code, severity, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"quality_event_{uuid4().hex}", str(cycle_id or ""), str(task_id or ""), str(target_id or ""),
                str(canonical_job_id or ""), str(company_id or ""), str(employer_name or ""),
                str(connector or ""), str(source_token or ""), str(warning_code or "unknown"),
                str(severity or "warning"), _json(dict(details or {})), utc_now_iso(),
            ),
        )

    @staticmethod
    def _persist_unified_mapping(
        connection,
        *,
        canonical_job_id: str,
        company_id: str,
        source_observation_id: str,
        execution_id: str,
        mapping: Mapping[str, Any],
        job: Mapping[str, Any],
        observed_at: str,
    ) -> None:
        """Persist the typed projection without rewriting source evidence."""

        rule_version = str(mapping.get("rule_version") or UNIFIED_RULE_VERSION)
        now = str(observed_at or utc_now_iso())
        fields = mapping.get("fields") if isinstance(mapping.get("fields"), Mapping) else {}
        provenance_sql = """
            INSERT OR IGNORE INTO acquisition_field_provenance (
                provenance_id, entity_kind, entity_id, field_name, source_observation_id,
                raw_value_json, normalized_value_json, state, source, source_field,
                extraction_method, evidence_json, confidence, observed_at, rule_version,
                selected, selection_reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        job_provenance_rows = []
        for field_name, record in fields.items():
            if not isinstance(record, Mapping):
                continue
            selected = int(str(record.get("state") or "unknown") in {"present", "inferred"})
            job_provenance_rows.append(
                (f"field_provenance_{uuid4().hex}", "job", canonical_job_id, str(field_name), source_observation_id,
                 _json(record.get("raw_value")), _json(record.get("normalized_value")), str(record.get("state") or "unknown"),
                 str(record.get("source") or ""), str(record.get("source_field") or ""),
                 str(record.get("extraction_method") or ""), _json(record.get("evidence")),
                 float(record.get("confidence") or 0), str(record.get("observed_at") or now), rule_version,
                 selected, "latest evidence-backed candidate" if selected else "no evidence-backed value", now)
            )
        if job_provenance_rows:
            connection.executemany(provenance_sql, job_provenance_rows)
        mapped_company_fields = mapping.get("company_fields") if isinstance(mapping.get("company_fields"), Mapping) else {}
        company_source = job.get("company") if isinstance(job.get("company"), Mapping) else {}
        company_values = {
            "company_identity": job.get("company") if not isinstance(job.get("company"), Mapping) else company_source.get("name") or company_source.get("canonical_name"),
            "website": company_source.get("website") if isinstance(company_source, Mapping) else job.get("website"),
            "careers_url": company_source.get("careers_page") if isinstance(company_source, Mapping) else job.get("careers_page"),
            "industry": company_source.get("industry") if isinstance(company_source, Mapping) else job.get("industry"),
            "company_size": company_source.get("company_size") if isinstance(company_source, Mapping) else job.get("company_size"),
            "headquarters": company_source.get("headquarters") if isinstance(company_source, Mapping) else job.get("headquarters"),
            "logo": company_source.get("logo_url") if isinstance(company_source, Mapping) else job.get("logo_url"),
        }
        company_provenance_rows = []
        for field_name, record in mapped_company_fields.items():
            if not isinstance(record, Mapping):
                continue
            value = record.get("raw_value")
            company_provenance_rows.append(
                (f"field_provenance_{uuid4().hex}", "company", company_id, str(field_name), source_observation_id,
                 _json(value), _json(record.get("normalized_value")), str(record.get("state") or "unknown"),
                 str(record.get("source") or ""), str(record.get("source_field") or ""),
                 str(record.get("extraction_method") or ""), _json(record.get("evidence")),
                 float(record.get("confidence") or 0), str(record.get("observed_at") or now), rule_version,
                 int(str(record.get("state") or "unknown") in {"present", "inferred"}),
                 "latest evidence-backed candidate" if str(record.get("state") or "unknown") in {"present", "inferred"} else "no evidence-backed value", now)
            )
        for field_name, value in company_values.items():
            known = value not in (None, "", [])
            company_provenance_rows.append(
                (f"field_provenance_{uuid4().hex}", "company", company_id, field_name, source_observation_id,
                 _json(value), _json(value), "present" if known else "unknown",
                 "source_observation" if known else "", f"company.{field_name}" if known else "",
                 "source_payload" if known else "not_available", _json(value if known else None),
                 0.9 if known else 0, now, rule_version, int(known),
                 "latest evidence-backed candidate" if known else "no evidence-backed value", now)
            )
        if company_provenance_rows:
            connection.executemany(provenance_sql, company_provenance_rows)
        output_payload = dict(mapping)
        connection.execute(
            """
            INSERT INTO acquisition_rule_outputs (
                output_id, execution_id, entity_kind, entity_id, source_observation_id,
                stage_name, rule_version, semantic_hash, output_json, created_at
            ) VALUES (?, ?, 'job', ?, ?, 'normalization', ?, ?, ?, ?)
            ON CONFLICT(entity_kind, entity_id, source_observation_id, stage_name, rule_version)
            DO UPDATE SET execution_id=excluded.execution_id, semantic_hash=excluded.semantic_hash,
                output_json=excluded.output_json
            """,
            (
                f"rule_output_{uuid4().hex}", str(execution_id or ""), canonical_job_id, source_observation_id,
                rule_version, hashlib.sha256(_json(output_payload).encode("utf-8")).hexdigest(),
                _json(output_payload), now,
            ),
        )
        company_urls = mapping.get("company_urls") if isinstance(mapping.get("company_urls"), list) else []
        for item in company_urls:
            if not isinstance(item, Mapping) or not item.get("canonical_url"):
                continue
            connection.execute(
                """
                INSERT INTO canonical_company_urls (
                    company_url_id, company_id, url_type, url, canonical_url, source,
                    source_observation_id, first_seen_at, last_seen_at, validation_status,
                    redirect_target, selected_primary, rule_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                ON CONFLICT(company_id, url_type, canonical_url) DO UPDATE SET
                    last_seen_at=excluded.last_seen_at, source_observation_id=excluded.source_observation_id,
                    updated_at=excluded.updated_at
                """,
                (
                    f"company_url_{uuid4().hex}", company_id, str(item.get("url_type") or "source"),
                    str(item.get("url") or ""), str(item.get("canonical_url") or ""), str(item.get("source") or ""),
                    source_observation_id, str(item.get("first_seen_at") or now), str(item.get("last_seen_at") or now),
                    str(item.get("validation_status") or "not_validated"), str(item.get("redirect_target") or ""),
                    rule_version, now, now,
                ),
            )
        timestamps = mapping.get("timestamps") if isinstance(mapping.get("timestamps"), Mapping) else {}
        timestamp_values = {
            "published_at": timestamps.get("published_at", {}).get("normalized_value") if isinstance(timestamps.get("published_at"), Mapping) else "",
            "source_updated_at": timestamps.get("updated_at", {}).get("normalized_value") if isinstance(timestamps.get("updated_at"), Mapping) else "",
            "closed_at": timestamps.get("closed_at", {}).get("normalized_value") if isinstance(timestamps.get("closed_at"), Mapping) else "",
        }
        connection.execute(
            """
            UPDATE canonical_jobs
            SET published_at=CASE WHEN ? != '' THEN ? ELSE published_at END,
                source_updated_at=CASE WHEN ? != '' THEN ? ELSE source_updated_at END,
                closed_at=CASE WHEN ? != '' THEN ? ELSE closed_at END,
                last_reprocessed_at=?, updated_at=?
            WHERE canonical_job_id=?
            """,
            (
                timestamp_values["published_at"], timestamp_values["published_at"],
                timestamp_values["source_updated_at"], timestamp_values["source_updated_at"],
                timestamp_values["closed_at"], timestamp_values["closed_at"], now, now, canonical_job_id,
            ),
        )
        report_fields: dict[str, Any] = {}
        for field_name, record in fields.items():
            if isinstance(record, Mapping):
                report_fields[field_name] = {
                    "state": str(record.get("state") or "unknown"),
                    "confidence": float(record.get("confidence") or 0),
                    "source": record.get("source"),
                }
        report = {
            "schema_version": "field_matrix_v1", "rule_version": rule_version, "report_only": True,
            "fields": report_fields,
            "rollup": {
                "present": sum(1 for item in report_fields.values() if item["state"] == "present"),
                "total": len(report_fields),
                "warnings": [name for name, item in report_fields.items() if item["state"] != "present"],
            },
        }
        overall_state = "complete" if report["rollup"]["warnings"] == [] else "warning"
        connection.execute(
            """
            INSERT INTO acquisition_completeness_reports (
                report_id, entity_kind, entity_id, rule_version, state, report_json, calculated_at
            ) VALUES (?, 'job', ?, ?, ?, ?, ?)
            ON CONFLICT(entity_kind, entity_id, rule_version) DO UPDATE SET
                state=excluded.state, report_json=excluded.report_json, calculated_at=excluded.calculated_at
            """,
            (f"completeness_{uuid4().hex}", canonical_job_id, rule_version, overall_state, _json(report), now),
        )

    @staticmethod
    def _ensure_company_profile(
        connection,
        company_id: str,
        source: Mapping[str, Any] | None,
        *,
        now: str,
        provenance_url: str = "",
    ) -> None:
        incoming = _company_profile_payload(source, provenance_url=provenance_url, verified_at=now)
        existing = connection.execute(
            "SELECT profile_json FROM canonical_company_profiles WHERE company_id = ?",
            (str(company_id),),
        ).fetchone()
        current = _decode(existing["profile_json"], {}) if existing is not None else {}
        current_fields = current.get("fields") if isinstance(current, Mapping) else {}
        if not isinstance(current_fields, Mapping):
            current_fields = {}
        merged_fields: dict[str, Any] = {}
        for field in _COMPANY_PROFILE_FIELDS:
            old = current_fields.get(field)
            new = incoming.get("fields", {}).get(field)
            old_known = isinstance(old, Mapping) and str(old.get("state") or "") == "known" and old.get("value") not in (None, "", [])
            new_known = isinstance(new, Mapping) and str(new.get("state") or "") == "known" and new.get("value") not in (None, "", [])
            merged_fields[field] = dict(new if new_known or not old_known else old)
        profile = {"schema_version": "phase_f_v1", "fields": merged_fields}
        logo = merged_fields.get("logo") if isinstance(merged_fields.get("logo"), Mapping) else {}
        logo_source_url = str(logo.get("value") or "") if str(logo.get("state") or "") == "known" else ""
        if existing is None:
            connection.execute(
                """
                INSERT INTO canonical_company_profiles (
                    company_id, profile_json, logo_source_url, logo_verified_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(company_id), _json(profile), logo_source_url, str(logo.get("verified_at") or ""), now, now),
            )
        else:
            connection.execute(
                """
                UPDATE canonical_company_profiles
                SET profile_json=?, logo_source_url=CASE WHEN ? != '' THEN ? ELSE logo_source_url END,
                    logo_verified_at=CASE WHEN ? != '' THEN ? ELSE logo_verified_at END,
                    updated_at=?
                WHERE company_id=?
                """,
                (
                    _json(profile),
                    logo_source_url,
                    logo_source_url,
                    str(logo.get("verified_at") or ""),
                    str(logo.get("verified_at") or ""),
                    now,
                    str(company_id),
                ),
            )

    @staticmethod
    def _find_existing_canonical(
        connection,
        *,
        identity_key: str,
        identity_signature: str = "",
        original_url: str,
        company_id: str,
        title: str,
        location: str,
    ):
        """Resolve URL aliases first, then a strong cross-source signature."""

        row = connection.execute(
            "SELECT * FROM canonical_jobs WHERE identity_key = ? AND lifecycle_state != 'closed'",
            (identity_key,),
        ).fetchone()
        if row is not None:
            return row
        if identity_signature:
            row = connection.execute(
                """
                SELECT * FROM canonical_jobs
                WHERE identity_signature = ? AND lifecycle_state != 'closed'
                ORDER BY first_seen_at, canonical_job_id
                LIMIT 1
                """,
                (identity_signature,),
            ).fetchone()
            if row is not None:
                return row
        row = connection.execute(
            """
            SELECT j.*
            FROM canonical_jobs j
            JOIN canonical_job_url_aliases a ON a.canonical_job_id = j.canonical_job_id
            WHERE a.url = ? AND j.lifecycle_state != 'closed'
            ORDER BY j.updated_at DESC
            LIMIT 1
            """,
            (original_url,),
        ).fetchone()
        if row is not None:
            return row
        # A strong employer/title/location signature consolidates different
        # official ATS URLs while excluding already-closed postings so a true
        # repost keeps a relationship and its historical provenance.
        return connection.execute(
            """
            SELECT * FROM canonical_jobs
            WHERE company_id = ? AND title = ? AND location = ?
              AND lifecycle_state != 'closed'
            ORDER BY first_seen_at, canonical_job_id
            LIMIT 1
            """,
            (company_id, title, location),
        ).fetchone()

    @staticmethod
    def _identity_key(company: str, title: str, location: str, url: str) -> str:
        stable_url = url.split("?", 1)[0].rstrip("/").casefold()
        if stable_url:
            return f"url:{stable_url}"
        return f"text:{company.casefold()}|{title.casefold()}|{location.casefold()}"

    @staticmethod
    def _identity_signature(company: str, title: str, location: str) -> str:
        """Stable candidate identity that does not depend on a URL primary key."""

        parts = (company, title, location)
        normalized = "|".join(" ".join(str(part or "").casefold().split()) for part in parts)
        return f"signature:v1:{normalized}"

    @staticmethod
    def _unique_identity_key(connection, base_key: str) -> str:
        candidate = str(base_key or "")
        if not candidate:
            candidate = "text:unknown"
        if connection.execute("SELECT 1 FROM canonical_jobs WHERE identity_key=?", (candidate,)).fetchone() is None:
            return candidate
        return f"{candidate}:repost:{uuid4().hex}"

    @staticmethod
    def _external_canonical(connection, source_id: str, external_job_id: str):
        return connection.execute(
            """
            SELECT j.* FROM canonical_job_external_ids e
            JOIN canonical_jobs j ON j.canonical_job_id = e.canonical_job_id
            WHERE e.source_id=? AND e.external_job_id=?
            LIMIT 1
            """,
            (source_id, external_job_id),
        ).fetchone()

    @staticmethod
    def _upsert_source_state(
        connection,
        *,
        target_id: str,
        canonical_job_id: str,
        external_job_id: str,
        cycle_id: str,
        observed_at: str,
        grace_attempts: int,
    ) -> None:
        connection.execute(
            """
            INSERT INTO job_source_states (
                source_state_id, target_id, canonical_job_id, external_job_id,
                lifecycle_state, absence_count, grace_attempts, last_seen_at,
                last_checked_at, last_cycle_id, updated_at
            ) VALUES (?, ?, ?, ?, 'active', 0, ?, ?, ?, ?, ?)
            ON CONFLICT(target_id, external_job_id) DO UPDATE SET
                canonical_job_id=excluded.canonical_job_id,
                lifecycle_state='active', absence_count=0,
                grace_attempts=excluded.grace_attempts,
                last_seen_at=excluded.last_seen_at,
                last_checked_at=excluded.last_checked_at,
                last_cycle_id=excluded.last_cycle_id,
                updated_at=excluded.updated_at
            """,
            (
                f"source_state_{uuid4().hex}",
                target_id,
                canonical_job_id,
                external_job_id,
                max(1, int(grace_attempts)),
                observed_at,
                observed_at,
                cycle_id,
                observed_at,
            ),
        )

    @staticmethod
    def _recompute_lifecycle(connection, canonical_job_id: str, *, now: str) -> str:
        states = connection.execute(
            "SELECT lifecycle_state FROM job_source_states WHERE canonical_job_id=?",
            (canonical_job_id,),
        ).fetchall()
        values = {str(row["lifecycle_state"] or "unknown") for row in states}
        if "active" in values:
            lifecycle = "active"
        elif "stale" in values:
            lifecycle = "stale"
        elif values and values <= {"closed"}:
            lifecycle = "closed"
        else:
            lifecycle = "unknown"
        connection.execute(
            "UPDATE canonical_jobs SET lifecycle_state=?, updated_at=? WHERE canonical_job_id=?",
            (lifecycle, now, canonical_job_id),
        )
        return lifecycle

    @staticmethod
    def _payload_hash(job: Mapping[str, Any]) -> str:
        return hashlib.sha256(_json(stable_content_payload(job)).encode("utf-8")).hexdigest()

    @staticmethod
    def _current_content_hash(connection, canonical_job_id: str) -> str:
        row = connection.execute(
            """
            SELECT COALESCE(NULLIF(q.stable_content_hash, ''), v.content_hash) AS stable_hash
            FROM job_posting_versions v
            LEFT JOIN acquisition_version_quality q ON q.version_id=v.version_id
            WHERE v.canonical_job_id = ?
            ORDER BY v.version_number DESC LIMIT 1
            """,
            (canonical_job_id,),
        ).fetchone()
        return str(row["stable_hash"] or "") if row is not None else ""

    @staticmethod
    def _ensure_version(
        connection,
        canonical_job_id: str,
        *,
        title: str,
        description: str,
        location: str,
        apply_url: str,
        content_hash: str,
        source_observation_id: str,
        payload: Mapping[str, Any],
        now: str,
        force_new_version: bool = False,
    ) -> None:
        current = connection.execute(
            """
            SELECT v.version_id, v.content_hash, v.version_number,
                   COALESCE(NULLIF(q.stable_content_hash, ''), v.content_hash) AS stable_hash
            FROM job_posting_versions v
            LEFT JOIN acquisition_version_quality q ON q.version_id=v.version_id
            WHERE v.canonical_job_id = ?
            ORDER BY v.version_number DESC LIMIT 1
            """,
            (canonical_job_id,),
        ).fetchone()
        if not force_new_version:
            existing_hash = connection.execute(
                """
                SELECT v.version_id
                FROM job_posting_versions v
                LEFT JOIN acquisition_version_quality q ON q.version_id=v.version_id
                WHERE v.canonical_job_id=?
                  AND COALESCE(NULLIF(q.stable_content_hash, ''), v.content_hash)=?
                ORDER BY v.version_number DESC, v.created_at DESC
                LIMIT 1
                """,
                (canonical_job_id, content_hash),
            ).fetchone()
            if existing_hash is not None:
                connection.execute(
                    "UPDATE canonical_jobs SET current_version_id = ? WHERE canonical_job_id = ?",
                    (str(existing_hash["version_id"]), canonical_job_id),
                )
                return
        if not force_new_version and current is not None and str(current["stable_hash"] or "") == content_hash:
            connection.execute(
                "UPDATE canonical_jobs SET current_version_id = ? WHERE canonical_job_id = ?",
                (str(current["version_id"]), canonical_job_id),
            )
            return
        version_id = f"posting_version_{uuid4().hex}"
        version_number = int(current["version_number"] or 0) + 1 if current is not None else 1
        connection.execute(
            """
            INSERT INTO job_posting_versions (
                version_id, canonical_job_id, version_number, content_hash, title,
                description, location, apply_url, source_observation_id, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version_id,
                canonical_job_id,
                version_number,
                content_hash,
                title,
                description,
                location,
                apply_url,
                source_observation_id,
                _json(dict(payload)),
                now,
            ),
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO acquisition_version_quality (
                version_id, canonical_job_id, stable_content_hash, redundant, report_json, calculated_at
            ) VALUES (?, ?, ?, 0, ?, ?)
            """,
            (
                version_id,
                canonical_job_id,
                content_hash,
                _json({
                    "warnings": list(payload.get("quality_warnings") or []),
                    "application": payload.get("application_destination") or {},
                    "normalized_metadata": payload.get("normalized_source_metadata") or {},
                    "completeness": payload.get("quality_completeness") or {},
                }),
                now,
            ),
        )
        connection.execute(
            "UPDATE canonical_jobs SET current_version_id = ? WHERE canonical_job_id = ?",
            (version_id, canonical_job_id),
        )


__all__ = ["SqliteAcquisitionStore"]
