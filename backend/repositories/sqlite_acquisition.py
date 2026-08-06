from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.domain.models import utc_now_iso, utc_plus_seconds
from backend.acquisition.phase_g import (
    is_portal_target,
    normalize_applicant_snapshot,
    portal_audit_gate,
)
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
    "industry",
    "company_size",
    "headquarters",
    "founded_year",
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
        "provenance": {"source": str(source or ""), "url": str(provenance_url or "")},
        "verified_at": str(verified_at or "") if known else "",
    }


def _company_profile_payload(source: Mapping[str, Any] | None, *, provenance_url: str, verified_at: str) -> dict[str, Any]:
    raw = dict(source or {})
    aliases = {
        "description": ("description", "company_description", "about"),
        "website": ("website", "company_website", "site"),
        "industry": ("industry", "company_industry"),
        "company_size": ("company_size", "size", "employees"),
        "headquarters": ("headquarters", "company_headquarters", "hq"),
        "founded_year": ("founded_year", "company_founded_year", "founded"),
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
                connection.execute(
                    """
                    INSERT INTO acquisition_targets (
                        target_id, target_kind, display_name, canonical_target_url,
                        provenance_url, request_url, connector, provider, source_token,
                        policy_version, maturity_state, enabled, publication_enabled,
                        max_direct_requests, request_mode, config_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        enabled=excluded.enabled,
                        publication_enabled=excluded.publication_enabled,
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
                        str(target.get("maturity_state") or "unproven"),
                        int(bool(target.get("enabled", False))),
                        int(bool(target.get("publication_enabled", False))),
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
                sql += " WHERE enabled = 1"
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
                "SELECT maturity_state, zero_yield_streak, last_state_transition_at "
                "FROM acquisition_targets WHERE target_id = ?",
                (target_id,),
            ).fetchone()
            if current is None:
                raise KeyError(f"Acquisition target '{target_id}' not found.")
            previous = str(current["maturity_state"] or "")
            streak = (
                int(current["zero_yield_streak"] or 0) if zero_yield_streak is None else max(0, int(zero_yield_streak))
            )
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
                    str(successful_at or (now if maturity_state in {"candidate", "productive"} else "")),
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
                INSERT INTO acquisition_job_rejections (
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
            target = connection.execute(
                "SELECT display_name, target_kind, connector, config_json, provenance_url FROM acquisition_targets WHERE target_id = ?", (target_id,)
            ).fetchone()
            if target is None:
                raise KeyError(f"Acquisition target '{target_id}' not found.")
            target_for_gate = {
                "target_id": target_id,
                "target_kind": str(target["target_kind"] or ""),
                "connector": str(target["connector"] or ""),
                "config": _decode(target["config_json"], {}),
            }
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
            }
            config = _decode(target.get("config_json"), {})
            company_name = str(
                target.get("canonical_company_name")
                or config.get("canonical_company_name")
                or target["display_name"]
                or target_id
            )
            entity_kind = "employer"
            company_id = self._ensure_company(
                connection,
                company_name,
                entity_kind,
                now,
                provenance_url=str(target.get("provenance_url") or ""),
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
            for job in job_rows:
                external_id = str(job.get("job_id") or job.get("external_job_id") or job.get("url") or "").strip()
                title = str(job.get("title") or "").strip()
                original_url = str(job.get("url") or job.get("link") or job.get("source_url") or "").strip()
                if not external_id or not title or not original_url:
                    counts["rejected"] += 1
                    continue
                if external_id in seen_external:
                    counts["duplicates"] += 1
                    continue
                seen_external.add(external_id)
                location = str(job.get("location") or job.get("location_raw") or "").strip()
                identity_key = self._identity_key(company_name, title, location, original_url)
                canonical = self._find_existing_canonical(
                    connection,
                    identity_key=identity_key,
                    original_url=original_url,
                    company_id=company_id,
                    title=title,
                    location=location,
                )
                canonical_was_new = canonical is None
                if canonical is None:
                    canonical_id = f"canonical_job_{uuid4().hex}"
                    connection.execute(
                        """
                        INSERT INTO canonical_jobs (
                            canonical_job_id, company_id, identity_key, title, location,
                            canonical_url, lifecycle_state, first_seen_at, last_seen_at,
                            last_verified_at, absence_count, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, 0, ?, ?)
                        """,
                        (
                            canonical_id,
                            company_id,
                            identity_key,
                            title,
                            location,
                            original_url,
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
                        SET title=?, location=?, canonical_url=?, lifecycle_state='active',
                            last_seen_at=?, last_verified_at=?, absence_count=0, updated_at=?
                        WHERE canonical_job_id = ?
                        """,
                        (title, location, original_url, now, now, now, canonical_id),
                    )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO canonical_job_url_aliases (
                        alias_id, canonical_job_id, url, source, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (f"job_alias_{uuid4().hex}", canonical_id, original_url, target_id, now),
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
                connection.execute(
                    """
                    INSERT OR IGNORE INTO job_source_observations (
                        observation_id, canonical_job_id, target_id, cycle_id, task_id,
                        external_job_id, original_url, apply_url, source_ats,
                        content_hash, payload_json, observed_at, active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
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
                    ),
                )
                self._ensure_version(
                    connection,
                    canonical_id,
                    title=title,
                    description=str(job.get("full_description") or job.get("description") or ""),
                    location=location,
                    apply_url=str(job.get("apply_link") or original_url),
                    content_hash=payload_hash,
                    source_observation_id=observation_id,
                    payload=job,
                    now=now,
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
                if applicant_snapshot is not None:
                    self._ensure_applicant_snapshot(
                        connection,
                        canonical_job_id=canonical_id,
                        source_observation_id=observation_id,
                        snapshot=applicant_snapshot,
                        now=now,
                    )
                counts["observed"] += 1

            if complete_snapshot and valid_snapshot:
                missing_rows = connection.execute(
                    """
                    SELECT canonical_job_id, external_job_id
                    FROM job_source_observations
                    WHERE target_id = ? AND active = 1
                    GROUP BY canonical_job_id, external_job_id
                    """,
                    (target_id,),
                ).fetchall()
                for missing in missing_rows:
                    if str(missing["external_job_id"]) in seen_external:
                        continue
                    canonical_id = str(missing["canonical_job_id"])
                    current = connection.execute(
                        "SELECT absence_count FROM canonical_jobs WHERE canonical_job_id = ?",
                        (canonical_id,),
                    ).fetchone()
                    absence_count = int(current["absence_count"] or 0) + 1 if current else 1
                    other_source = connection.execute(
                        """
                        SELECT 1 FROM job_source_observations
                        WHERE canonical_job_id = ? AND target_id != ? AND active = 1 LIMIT 1
                        """,
                        (canonical_id, target_id),
                    ).fetchone()
                    if other_source is not None:
                        lifecycle = "active"
                    elif absence_count == 1:
                        lifecycle = "stale"
                    elif absence_count == 2:
                        lifecycle = "possibly_closed"
                    else:
                        lifecycle = "closed"
                    connection.execute(
                        """
                        UPDATE canonical_jobs
                        SET absence_count=?, lifecycle_state=?, updated_at=?
                        WHERE canonical_job_id = ?
                        """,
                        (absence_count, lifecycle, now, canonical_id),
                    )
                    if lifecycle == "closed":
                        counts["closed"] += 1
            return {**counts, "valid_snapshot": bool(valid_snapshot), "complete_snapshot": bool(complete_snapshot)}

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
                JOIN job_source_observations o ON o.canonical_job_id = j.canonical_job_id
                WHERE o.target_id IN ({placeholders}) AND o.cycle_id = ? AND j.lifecycle_state = 'active'
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
            connection.execute(
                "UPDATE acquisition_publications SET status='valid' WHERE publication_id=?",
                (publication_id,),
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
            payload["requests"] = [self._request_payload(item) for item in target_requests]
            payload["detail_requests"] = payload["requests"]
            payload["requested_urls"] = [item["request_url"] for item in payload["requests"]]
            payload["request_count"] = len(payload["requests"])
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
                       MAX(t.jobs_observed) AS jobs_observed,
                       MAX(t.jobs_new) AS jobs_new,
                       MAX(t.jobs_updated) AS jobs_updated,
                       MAX(t.jobs_rejected) AS jobs_rejected,
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
        metrics = []
        for row in rows:
            payload = _dict_row(row)
            actual_credits = int(payload.get("actual_credits") or 0)
            jobs_new = int(payload.get("jobs_new") or 0)
            payload.update(
                {
                    "request_count": int(payload.get("request_count") or 0),
                    "actual_credits": actual_credits,
                    "raw_jobs_returned": int(payload.get("raw_jobs_returned") or 0),
                    "jobs_observed": int(payload.get("jobs_observed") or 0),
                    "jobs_new": jobs_new,
                    "jobs_updated": int(payload.get("jobs_updated") or 0),
                    "jobs_rejected": int(payload.get("jobs_rejected") or 0),
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
                }
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
        report = {
            "cycle": cycle,
            "targets": targets,
            "source_metrics": source_metrics,
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
        return report

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

    @staticmethod
    def _target_payload(row: dict[str, Any]) -> dict[str, Any]:
        row["enabled"] = _bool(row.get("enabled"))
        row["publication_enabled"] = _bool(row.get("publication_enabled"))
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
    ) -> str:
        row = connection.execute(
            "SELECT company_id FROM canonical_companies WHERE canonical_name = ? AND entity_kind = ?",
            (name, entity_kind),
        ).fetchone()
        if row is not None:
            if provenance_url:
                connection.execute(
                    "UPDATE canonical_companies SET provenance_url=?, updated_at=? "
                    "WHERE company_id=? AND provenance_url=''",
                    (provenance_url, now, str(row["company_id"])),
                )
            return str(row["company_id"])
        company_id = f"canonical_company_{uuid4().hex}"
        connection.execute(
            """
            INSERT INTO canonical_companies (
                company_id, canonical_name, entity_kind, provenance_url, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (company_id, name, entity_kind, provenance_url, now, now),
        )
        return company_id

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
        original_url: str,
        company_id: str,
        title: str,
        location: str,
    ):
        """Resolve URL aliases first, then a strong cross-source signature."""

        row = connection.execute(
            "SELECT * FROM canonical_jobs WHERE identity_key = ?",
            (identity_key,),
        ).fetchone()
        if row is not None:
            return row
        row = connection.execute(
            """
            SELECT j.*
            FROM canonical_jobs j
            JOIN canonical_job_url_aliases a ON a.canonical_job_id = j.canonical_job_id
            WHERE a.url = ?
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
    def _payload_hash(job: Mapping[str, Any]) -> str:
        return hashlib.sha256(_json(dict(job)).encode("utf-8")).hexdigest()

    @staticmethod
    def _current_content_hash(connection, canonical_job_id: str) -> str:
        row = connection.execute(
            "SELECT content_hash FROM job_posting_versions WHERE canonical_job_id = ? ORDER BY version_number DESC LIMIT 1",
            (canonical_job_id,),
        ).fetchone()
        return str(row["content_hash"] or "") if row is not None else ""

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
    ) -> None:
        current = connection.execute(
            "SELECT version_id, content_hash, version_number FROM job_posting_versions WHERE canonical_job_id = ? ORDER BY version_number DESC LIMIT 1",
            (canonical_job_id,),
        ).fetchone()
        if current is not None and str(current["content_hash"] or "") == content_hash:
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
            "UPDATE canonical_jobs SET current_version_id = ? WHERE canonical_job_id = ?",
            (version_id, canonical_job_id),
        )


__all__ = ["SqliteAcquisitionStore"]
