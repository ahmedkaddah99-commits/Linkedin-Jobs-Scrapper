"""Durable, provider-neutral, report-only enrichment operations.

This module is the orchestration boundary for enrichment plans and runs.  It
only exposes the null and offline fixture providers; provider results become
evidence and immutable proposals, never canonical or publication writes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from backend.database.connection import connect_database, database_session
from backend.domain.models import utc_now_iso

from .contracts import (
    EnrichmentRequest,
    ProviderBudget,
    ProviderExecutionContext,
    ProviderResultState,
    RetentionPolicy,
)
from .persistence import append_evidence
from .providers import (
    FixtureCompanyProvider,
    FixtureOccupationProvider,
    FixturePlaceProvider,
    NullProvider,
)


RUN_STATUSES = (
    "pending",
    "running",
    "paused",
    "completed",
    "partially_completed",
    "failed",
    "cancelled",
)
TERMINAL_RUN_STATUSES = frozenset({"completed", "partially_completed", "failed", "cancelled"})
RETRYABLE_STATES = frozenset({"retryable_error", "unavailable"})
APPROVED_PROVIDER_IDS = frozenset({"null", "fixture", "fixture_place", "fixture_company", "fixture_occupation"})
KNOWN_PROVIDER_IDS = tuple(sorted(APPROVED_PROVIDER_IDS | {"official_website", "live"}))
COMPANY_FIELDS = (
    "company_identity",
    "website",
    "headquarters",
    "industry",
    "company_size",
    "founded_year",
)
PLACE_FIELDS = ("place", "city", "country", "job_location")
OCCUPATION_FIELDS = ("occupation", "runr_function", "runr_subfunction")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _decode(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _row(row: Any) -> dict[str, Any] | None:
    return {key: row[key] for key in row.keys()} if row is not None else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_bool(value: Any) -> bool:
    return bool(int(value or 0))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalise_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [_text(item) for item in value if _text(item)]


def _provider_target_type(target_type: str, field_path: str) -> str:
    if target_type == "company":
        return "company"
    if field_path in PLACE_FIELDS:
        return "place"
    if field_path in OCCUPATION_FIELDS:
        return "occupation"
    if field_path in COMPANY_FIELDS:
        return "company"
    return target_type


def _provider_for(provider_id: str, target_type: str, field_path: str):
    provider_id = _text(provider_id).casefold()
    resolved_type = _provider_target_type(target_type, field_path)
    if provider_id == "null":
        return NullProvider()
    if provider_id == "fixture":
        return {
            "place": FixturePlaceProvider,
            "company": FixtureCompanyProvider,
            "occupation": FixtureOccupationProvider,
        }.get(resolved_type, lambda: None)()
    return {
        "fixture_place": FixturePlaceProvider,
        "fixture_company": FixtureCompanyProvider,
        "fixture_occupation": FixtureOccupationProvider,
    }.get(provider_id, lambda: None)()


def _provider_fields(provider_id: str, target_type: str) -> tuple[str, ...]:
    if provider_id == "fixture":
        if target_type == "company":
            return COMPANY_FIELDS
        if target_type in {"job", "posting"}:
            return COMPANY_FIELDS + PLACE_FIELDS + OCCUPATION_FIELDS
        resolved = _provider_target_type(target_type, "")
        return {"company": COMPANY_FIELDS, "place": PLACE_FIELDS, "occupation": OCCUPATION_FIELDS}.get(resolved, ())
    return {
        "fixture_company": COMPANY_FIELDS,
        "fixture_place": PLACE_FIELDS,
        "fixture_occupation": OCCUPATION_FIELDS,
    }.get(provider_id, ())


class EnrichmentOperationService:
    """SQLite-backed plan/run/review service with a report-only write boundary."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        # Test/replay seam only; API callers can select approved IDs, never
        # arbitrary provider instances.
        self.provider_overrides: dict[str, Any] = {}

    def _transaction(self, callback):
        connection = connect_database(self.db_path)
        try:
            return connection.transaction(callback)
        finally:
            connection.close()

    @staticmethod
    def _plan_payload(row: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(row)
        for key, default in (
            ("selected_records_json", []),
            ("query_snapshot_json", {}),
            ("selected_fields_json", []),
            ("exclusions_json", []),
        ):
            value[key.removesuffix("_json")] = _decode(value.pop(key, ""), default)
        value["report_only"] = _as_bool(value.get("report_only"))
        value["expected_cost"] = float(value.get("expected_cost_units") or 0)
        value["expected_request_count"] = int(value.get("expected_request_count") or 0)
        return value

    @staticmethod
    def _run_payload(row: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(row)
        value["retry_policy"] = _decode(value.pop("retry_policy_json", ""), {})
        value["cancellation_requested"] = _as_bool(value.get("cancellation_requested"))
        value["report_only"] = True
        return value

    @staticmethod
    def _item_payload(row: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(row)
        for key, default in (
            ("input_json", {}),
            ("existing_normalized_value_json", None),
            ("proposed_value_json", None),
        ):
            value[key.removesuffix("_json")] = _decode(value.pop(key, ""), default)
        return value

    @staticmethod
    def _proposal_state(connection, proposal_id: str) -> str:
        row = connection.execute(
            "SELECT action FROM enrichment_proposal_actions WHERE proposal_id=? ORDER BY created_at DESC, action_id DESC LIMIT 1",
            (proposal_id,),
        ).fetchone()
        if row is None:
            return "proposed"
        action = _text(row["action"])
        return {"accept": "accepted", "reject": "rejected", "undo": "proposed", "supersede": "superseded"}.get(
            action, "proposed"
        )

    def _audit(
        self,
        connection,
        *,
        event_type: str,
        actor_id: str = "",
        plan_id: str = "",
        run_id: str = "",
        run_item_id: str = "",
        proposal_id: str = "",
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO enrichment_operation_audit_events (
                event_id, plan_id, run_id, run_item_id, proposal_id,
                event_type, actor_id, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"enrichment_audit_{uuid4().hex}",
                plan_id,
                run_id,
                run_item_id,
                proposal_id,
                event_type,
                actor_id,
                _json(payload or {}),
                utc_now_iso(),
            ),
        )

    def _load_plan(self, connection, plan_id: str) -> dict[str, Any]:
        result = _row(
            connection.execute("SELECT * FROM enrichment_operation_plans WHERE plan_id=?", (plan_id,)).fetchone()
        )
        if result is None:
            raise KeyError(f"Enrichment plan '{plan_id}' not found.")
        return result

    def _load_run(self, connection, run_id: str) -> dict[str, Any]:
        result = _row(
            connection.execute("SELECT * FROM enrichment_operation_runs WHERE run_id=?", (run_id,)).fetchone()
        )
        if result is None:
            raise KeyError(f"Enrichment run '{run_id}' not found.")
        return result

    @staticmethod
    def _company_record(connection, company_id: str) -> dict[str, Any] | None:
        company = _row(
            connection.execute("SELECT * FROM canonical_companies WHERE company_id=?", (company_id,)).fetchone()
        )
        if company is None:
            return None
        profile_row = connection.execute(
            "SELECT profile_json FROM canonical_company_profiles WHERE company_id=?", (company_id,)
        ).fetchone()
        profile = _decode(profile_row["profile_json"], {}) if profile_row is not None else {}
        fields = profile.get("fields") if isinstance(profile, Mapping) else {}
        domain = _text(urlparse(_text(company.get("provenance_url"))).hostname).removeprefix("www.")
        return {
            "target_id": company_id,
            "input": {
                "name": _text(company.get("canonical_name")),
                "domain": domain,
                "provenance_url": _text(company.get("provenance_url")),
            },
            "existing_normalized": {
                key: value.get("value") if isinstance(value, Mapping) else value
                for key, value in (fields or {}).items()
            },
            "display_name": _text(company.get("canonical_name")),
        }

    @staticmethod
    def _job_record(connection, job_id: str) -> dict[str, Any] | None:
        job = _row(connection.execute("SELECT * FROM canonical_jobs WHERE canonical_job_id=?", (job_id,)).fetchone())
        if job is None:
            return None
        company = _row(
            connection.execute(
                "SELECT * FROM canonical_companies WHERE company_id=?", (job.get("company_id"),)
            ).fetchone()
        )
        version = _row(
            connection.execute(
                "SELECT * FROM job_posting_versions WHERE version_id=?", (job.get("current_version_id"),)
            ).fetchone()
        )
        payload = _decode(version.get("payload_json") if version else "", {})
        if not isinstance(payload, Mapping):
            payload = {}
        input_payload = {
            "title": _text(job.get("title")) or _text(payload.get("title")),
            "display": _text(job.get("location")) or _text(payload.get("location")),
            "location": _text(job.get("location")) or _text(payload.get("location")),
            "description": _text(payload.get("description") or payload.get("description_text")),
            "company": _text(company.get("canonical_name")) if company else "",
            "domain": _text(urlparse(_text(company.get("provenance_url")) if company else "").hostname).removeprefix(
                "www."
            ),
        }
        return {
            "target_id": job_id,
            "input": input_payload,
            "existing_normalized": {},
            "display_name": input_payload["title"],
        }

    def _import_record_ids(self, connection, import_id: str) -> list[str]:
        import_row = connection.execute(
            "SELECT cycle_id FROM admin_job_imports WHERE import_id=?", (import_id,)
        ).fetchone()
        if import_row is None:
            raise KeyError(f"Import '{import_id}' not found.")
        cycle_id = _text(import_row["cycle_id"])
        ids: set[str] = set()
        if cycle_id:
            for query in (
                "SELECT DISTINCT canonical_job_id FROM job_source_observations WHERE cycle_id=?",
                "SELECT DISTINCT apj.canonical_job_id FROM acquisition_publication_jobs apj JOIN acquisition_publications ap ON ap.publication_id=apj.publication_id WHERE ap.cycle_id=?",
            ):
                ids.update(_text(row["canonical_job_id"]) for row in connection.execute(query, (cycle_id,)).fetchall())
        ids.update(
            _text(row["canonical_job_id"])
            for row in connection.execute(
                "SELECT canonical_job_id FROM admin_job_review_decisions WHERE import_id=?", (import_id,)
            ).fetchall()
        )
        return sorted(item for item in ids if item)

    def _resolve_records(
        self,
        connection,
        *,
        scope_type: str,
        scope_id: str,
        target_type: str,
        supplied: Sequence[Any],
        record_ids: Sequence[Any],
    ) -> list[dict[str, Any]]:
        if scope_type == "company":
            if target_type != "company":
                raise ValueError("Company-scoped enrichment must target companies.")
            if supplied:
                records = [dict(item) for item in supplied if isinstance(item, Mapping)]
                if any(_text(item.get("target_id") or item.get("company_id")) != scope_id for item in records):
                    raise ValueError("Company-scoped selection crossed the company boundary.")
                if records:
                    return records
            record = self._company_record(connection, scope_id)
            if record is None:
                raise KeyError(f"Company '{scope_id}' not found.")
            return [record]

        if target_type not in {"job", "posting"}:
            raise ValueError("Import-scoped enrichment must target jobs.")
        allowed_ids = set(self._import_record_ids(connection, scope_id))
        selected = [
            _text(item.get("target_id") or item.get("canonical_job_id")) if isinstance(item, Mapping) else _text(item)
            for item in supplied
        ] or [_text(item) for item in record_ids]
        selected = [item for item in selected if item]
        if not selected:
            selected = sorted(allowed_ids)
        elif allowed_ids and not set(selected).issubset(allowed_ids):
            raise ValueError("Selected records must belong to the import snapshot.")
        elif not allowed_ids:
            raise ValueError("The import snapshot has no selected records.")
        records: list[dict[str, Any]] = []
        for target_id in dict.fromkeys(selected):
            record = self._job_record(connection, target_id)
            if record is not None:
                supplied_item = next(
                    (
                        item
                        for item in supplied
                        if isinstance(item, Mapping)
                        and _text(item.get("target_id") or item.get("canonical_job_id")) == target_id
                    ),
                    None,
                )
                if supplied_item:
                    record["input"] = dict(supplied_item.get("input") or record["input"])
                    record["existing_normalized"] = dict(supplied_item.get("existing_normalized") or {})
                records.append(record)
        if selected and not records:
            raise ValueError("No selected records belong to the import snapshot.")
        return records

    def create_plan(
        self,
        *,
        requested_by: str,
        scope_type: str = "",
        scope_id: str = "",
        target_type: str,
        selected_fields: Sequence[Any],
        provider_id: str = "null",
        selected_records: Sequence[Any] = (),
        record_ids: Sequence[Any] = (),
        query_snapshot: Mapping[str, Any] | None = None,
        exclusions: Sequence[Any] = (),
        policy_version: str = "enrichment_policy_v1",
        rule_version: str = "enrichment_foundation_v1",
        snapshot_version: str = "",
        expected_request_count: int | None = None,
        expected_cost: float = 0.0,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        scope_type = _text(scope_type).casefold()
        if not scope_type:
            scope_type = "company" if _text(scope_id) and target_type == "company" else "import"
        scope_id = _text(scope_id)
        target_type = _text(target_type).casefold()
        if scope_type not in {"import", "company"} or not scope_id:
            raise ValueError("An explicit import or company scope is required.")
        fields = _normalise_list(selected_fields)
        if not fields:
            raise ValueError("At least one selected field is required.")
        provider_id = _text(provider_id).casefold() or "null"
        if provider_id not in APPROVED_PROVIDER_IDS:
            raise ValueError("Only the null and approved offline fixture providers may be selected.")
        now = utc_now_iso()

        def write(connection):
            records = self._resolve_records(
                connection,
                scope_type=scope_type,
                scope_id=scope_id,
                target_type=target_type,
                supplied=selected_records,
                record_ids=record_ids,
            )
            snapshot = dict(query_snapshot or {})
            snapshot.update(
                {
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "selected_record_ids": [item["target_id"] for item in records],
                }
            )
            selected_json = [
                {
                    "target_id": _text(item.get("target_id")),
                    "input": dict(item.get("input") or {}),
                    "existing_normalized": dict(item.get("existing_normalized") or {}),
                    "display_name": _text(item.get("display_name")),
                }
                for item in records
            ]
            request_count = (
                len(records) * len(fields) if expected_request_count is None else max(0, int(expected_request_count))
            )
            material = {
                "scope_type": scope_type,
                "scope_id": scope_id,
                "target_type": target_type,
                "selected_records": selected_json,
                "selected_fields": fields,
                "provider_id": provider_id,
                "query_snapshot": snapshot,
                "policy_version": policy_version,
                "rule_version": rule_version,
                "snapshot_version": snapshot_version,
            }
            key = _text(idempotency_key) or f"plan:{hashlib.sha256(_json(material).encode()).hexdigest()}"
            existing = connection.execute(
                "SELECT * FROM enrichment_operation_plans WHERE idempotency_key=?", (key,)
            ).fetchone()
            if existing is not None:
                return self._plan_payload(existing)
            plan_id = f"enrichment_plan_{uuid4().hex}"
            connection.execute(
                """
                INSERT INTO enrichment_operation_plans (
                    plan_id, scope_type, scope_id, target_type, selected_records_json,
                    query_snapshot_json, selected_fields_json, provider_id,
                    expected_request_count, expected_cost_units, exclusions_json,
                    policy_version, rule_version, snapshot_version, report_only,
                    idempotency_key, requested_by, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 'planned', ?, ?)
                """,
                (
                    plan_id,
                    scope_type,
                    scope_id,
                    target_type,
                    _json(selected_json),
                    _json(snapshot),
                    _json(fields),
                    provider_id,
                    request_count,
                    max(0.0, float(expected_cost)),
                    _json(_normalise_list(exclusions)),
                    policy_version,
                    rule_version,
                    snapshot_version,
                    key,
                    _text(requested_by),
                    now,
                    now,
                ),
            )
            self._audit(
                connection,
                event_type="plan_created",
                actor_id=requested_by,
                plan_id=plan_id,
                payload={
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "selected_count": len(records),
                    "report_only": True,
                },
            )
            return self._plan_payload(
                connection.execute("SELECT * FROM enrichment_operation_plans WHERE plan_id=?", (plan_id,)).fetchone()
            )

        return self._transaction(write)

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        with database_session(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM enrichment_operation_plans WHERE plan_id=?", (_text(plan_id),)
            ).fetchone()
            return self._plan_payload(row) if row is not None else None

    def list_plans(self, *, scope_type: str = "", scope_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
        with database_session(self.db_path) as connection:
            predicates: list[str] = []
            params: list[Any] = []
            if _text(scope_type):
                predicates.append("scope_type=?")
                params.append(_text(scope_type))
            if _text(scope_id):
                predicates.append("scope_id=?")
                params.append(_text(scope_id))
            where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
            rows = connection.execute(
                f"SELECT * FROM enrichment_operation_plans {where} ORDER BY created_at DESC, plan_id DESC LIMIT ?",
                (*params, max(1, min(500, int(limit)))),
            ).fetchall()
            return [self._plan_payload(row) for row in rows]

    def start_run(
        self,
        *,
        plan_id: str,
        requested_by: str,
        idempotency_key: str = "",
        request_budget: int = 0,
        cost_budget: float = 0.0,
        retry_policy: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()

        def write(connection):
            plan = self._load_plan(connection, _text(plan_id))
            key = _text(idempotency_key) or f"run:{plan['plan_id']}"
            existing = connection.execute(
                "SELECT * FROM enrichment_operation_runs WHERE idempotency_key=?", (key,)
            ).fetchone()
            if existing is not None:
                if _text(existing["plan_id"]) != _text(plan["plan_id"]):
                    raise ValueError("Idempotency key is already used by another enrichment plan.")
                return self._run_payload(existing)
            policy = dict(retry_policy or {})
            policy["max_attempts"] = max(1, min(5, int(policy.get("max_attempts") or 2)))
            policy["retryable_states"] = sorted(RETRYABLE_STATES)
            run_id = f"enrichment_run_{uuid4().hex}"
            connection.execute(
                """
                INSERT INTO enrichment_operation_runs (
                    run_id, plan_id, scope_type, scope_id, target_type, provider_id,
                    status, request_budget, cost_budget_units, retry_policy_json,
                    idempotency_key, requested_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    plan["plan_id"],
                    plan["scope_type"],
                    plan["scope_id"],
                    plan["target_type"],
                    plan["provider_id"],
                    max(0, int(request_budget)),
                    max(0.0, float(cost_budget)),
                    _json(policy),
                    key,
                    _text(requested_by),
                    now,
                    now,
                ),
            )
            selected = _decode(plan["selected_records_json"], [])
            fields = _decode(plan["selected_fields_json"], [])
            for record in selected:
                for field_path in fields:
                    target_id = _text(record.get("target_id"))
                    item_id = f"enrichment_item_{uuid4().hex}"
                    connection.execute(
                        """
                        INSERT INTO enrichment_operation_run_items (
                            run_item_id, run_id, target_type, target_id, field_path,
                            input_json, existing_normalized_value_json, attempt_state, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                        """,
                        (
                            item_id,
                            run_id,
                            plan["target_type"],
                            target_id,
                            _text(field_path),
                            _json(record.get("input") or {}),
                            _json((record.get("existing_normalized") or {}).get(field_path)),
                            now,
                        ),
                    )
            self._audit(
                connection,
                event_type="run_created",
                actor_id=requested_by,
                plan_id=plan["plan_id"],
                run_id=run_id,
                payload={"item_count": len(selected) * len(fields), "report_only": True},
            )
            return self._run_payload(
                connection.execute("SELECT * FROM enrichment_operation_runs WHERE run_id=?", (run_id,)).fetchone()
            )

        return self._transaction(write)

    def get_run(self, run_id: str, *, include_items: bool = False) -> dict[str, Any] | None:
        with database_session(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM enrichment_operation_runs WHERE run_id=?", (_text(run_id),)
            ).fetchone()
            if row is None:
                return None
            result = self._run_payload(row)
            if include_items:
                result["items"] = [
                    self._item_payload(item)
                    for item in connection.execute(
                        "SELECT * FROM enrichment_operation_run_items WHERE run_id=? ORDER BY target_id, field_path",
                        (_text(run_id),),
                    ).fetchall()
                ]
            return result

    def list_runs(
        self, *, plan_id: str = "", scope_type: str = "", scope_id: str = "", status: str = "", limit: int = 100
    ) -> list[dict[str, Any]]:
        with database_session(self.db_path) as connection:
            predicates: list[str] = []
            params: list[Any] = []
            for key, value in (
                ("plan_id", plan_id),
                ("scope_type", scope_type),
                ("scope_id", scope_id),
                ("status", status),
            ):
                if _text(value):
                    predicates.append(f"{key}=?")
                    params.append(_text(value))
            where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
            rows = connection.execute(
                f"SELECT * FROM enrichment_operation_runs {where} ORDER BY created_at DESC, run_id DESC LIMIT ?",
                (*params, max(1, min(500, int(limit)))),
            ).fetchall()
            return [self._run_payload(row) for row in rows]

    def _claim_run(self, run_id: str, worker_id: str, lease_seconds: int) -> dict[str, Any]:
        now = _now()
        now_iso = now.isoformat()
        expiry = (now + timedelta(seconds=max(5, min(3600, int(lease_seconds))))).isoformat()

        def claim(connection):
            run = self._load_run(connection, _text(run_id))
            status = _text(run["status"])
            if status in TERMINAL_RUN_STATUSES or status == "paused":
                return self._run_payload(run)
            if _as_bool(run.get("cancellation_requested")):
                connection.execute(
                    "UPDATE enrichment_operation_runs SET status='cancelled', completed_at=?, updated_at=? WHERE run_id=?",
                    (now_iso, now_iso, run_id),
                )
                connection.execute(
                    "UPDATE enrichment_operation_run_items SET attempt_state='cancelled', updated_at=? WHERE run_id=? AND attempt_state IN ('pending','running','retryable_error')",
                    (now_iso, run_id),
                )
                self._audit(
                    connection, event_type="run_cancelled", actor_id=worker_id, plan_id=run["plan_id"], run_id=run_id
                )
                return self._run_payload(
                    connection.execute("SELECT * FROM enrichment_operation_runs WHERE run_id=?", (run_id,)).fetchone()
                )
            lease_expired = not _text(run.get("lease_expires_at")) or _text(run.get("lease_expires_at")) <= now_iso
            if status == "running" and not lease_expired and _text(run.get("lease_owner")) != _text(worker_id):
                return self._run_payload(run)
            connection.execute(
                """
                UPDATE enrichment_operation_runs
                SET status='running', lease_owner=?, lease_expires_at=?, started_at=CASE WHEN started_at='' THEN ? ELSE started_at END, updated_at=?
                WHERE run_id=?
                """,
                (_text(worker_id), expiry, now_iso, now_iso, run_id),
            )
            self._audit(
                connection,
                event_type="run_claimed",
                actor_id=worker_id,
                plan_id=run["plan_id"],
                run_id=run_id,
                payload={"lease_expires_at": expiry},
            )
            return self._run_payload(
                connection.execute("SELECT * FROM enrichment_operation_runs WHERE run_id=?", (run_id,)).fetchone()
            )

        return self._transaction(claim)

    def _update_item(self, run_item_id: str, **values: Any) -> None:
        values["updated_at"] = utc_now_iso()

        def write(connection):
            assignments = ", ".join(f"{key}=?" for key in values)
            connection.execute(
                f"UPDATE enrichment_operation_run_items SET {assignments} WHERE run_item_id=?",
                (*values.values(), run_item_id),
            )

        self._transaction(write)

    def _process_item(self, run: Mapping[str, Any], item: Mapping[str, Any], worker_id: str) -> None:
        run_id = _text(run["run_id"])
        item_id = _text(item["run_item_id"])
        policy = dict(run.get("retry_policy") or {})
        max_attempts = max(1, int(policy.get("max_attempts") or 2))
        retry_count = int(item.get("retry_count") or 0) + 1
        now = utc_now_iso()
        self._update_item(item_id, attempt_state="running", retry_count=retry_count, last_attempt_at=now)

        current = self.get_run(run_id) or {}
        if current.get("cancellation_requested"):
            self._update_item(item_id, attempt_state="cancelled", failure_reason="run_cancelled")
            return
        target_type = _text(item["target_type"])
        field_path = _text(item["field_path"])
        provider_id = _text(run["provider_id"])
        provider = self.provider_overrides.get(provider_id) or _provider_for(provider_id, target_type, field_path)
        if provider is None:
            state = "retryable_error" if retry_count < max_attempts else "unavailable"
            self._update_item(item_id, attempt_state=state, failure_reason="provider_unavailable")
            self._audit_item(
                run,
                item,
                worker_id,
                "item_unavailable",
                {"reason": "provider_unavailable", "retrying": state == "retryable_error"},
            )
            return
        request = EnrichmentRequest(
            target_type=_provider_target_type(target_type, field_path),
            target_id=_text(item["target_id"]),
            field_path=field_path,
            input=item.get("input") if isinstance(item.get("input"), Mapping) else _decode(item.get("input_json"), {}),
            policy_version="enrichment_policy_v1",
            rule_version="enrichment_foundation_v1",
        )
        capability = provider.capability(request)
        if not capability.supported and provider_id != "null":
            self._update_item(
                item_id, attempt_state="unsupported", failure_reason=capability.reason or "field_not_supported"
            )
            self._audit_item(run, item, worker_id, "item_unsupported", {"reason": capability.reason})
            return
        budget = ProviderBudget(
            max_requests=max(0, int(run.get("request_budget") or 0)),
            max_cost_units=max(0.0, float(run.get("cost_budget_units") or 0)),
        )
        try:
            result = provider.resolve(
                request,
                ProviderExecutionContext(
                    budget=budget,
                    retention_policy=RetentionPolicy(),
                    allow_network=False,
                    now_iso=now,
                ),
            )
        except Exception as exc:
            state = "retryable_error" if retry_count < max_attempts else "permanent_error"
            self._update_item(item_id, attempt_state=state, failure_reason=f"{type(exc).__name__}: {exc}")
            self._audit_item(
                run,
                item,
                worker_id,
                "item_attempt_failed",
                {"retry_count": retry_count, "reason": str(exc), "retrying": state == "retryable_error"},
            )
            return
        if result.request_count > budget.max_requests or result.cost_units > budget.max_cost_units:
            self._update_item(item_id, attempt_state="budget_exhausted", failure_reason="run_budget_exhausted")
            self._audit_item(run, item, worker_id, "item_budget_exhausted", {})
            return
        evidence_ids: list[str] = []

        def persist(connection):
            for evidence in result.evidence:
                evidence_ids.append(append_evidence(connection, evidence))
            if result.request_count or result.cost_units:
                connection.execute(
                    "UPDATE enrichment_provider_budgets SET requests_used=requests_used+?, cost_units_used=cost_units_used+?, updated_at=? WHERE provider_id=?",
                    (result.request_count, result.cost_units, utc_now_iso(), provider_id),
                )
                connection.execute(
                    "UPDATE enrichment_operation_runs SET requests_used=requests_used+?, cost_units_used=cost_units_used+?, updated_at=? WHERE run_id=?",
                    (result.request_count, result.cost_units, utc_now_iso(), run_id),
                )
            proposed = result.candidates[0].normalized_value if result.candidates else None
            confidence = (
                result.candidates[0].provider_score
                if result.candidates and result.candidates[0].provider_score is not None
                else (1.0 if result.state == ProviderResultState.MATCHED else 0.5 if result.candidates else None)
            )
            state = str(result.state)
            if state == "unavailable" and retry_count < max_attempts:
                state = "retryable_error"
            reason = ";".join(result.warnings)
            connection.execute(
                """
                UPDATE enrichment_operation_run_items
                SET attempt_state=?, evidence_id=?, proposed_value_json=?, confidence=?, failure_reason=?, updated_at=?
                WHERE run_item_id=?
                """,
                (
                    state,
                    evidence_ids[0] if evidence_ids else "",
                    _json(proposed),
                    confidence,
                    reason,
                    utc_now_iso(),
                    item_id,
                ),
            )
            if result.candidates and state in {ProviderResultState.MATCHED, ProviderResultState.AMBIGUOUS}:
                proposal_id = f"enrichment_proposal_{uuid4().hex}"
                connection.execute(
                    """
                    INSERT INTO enrichment_field_proposals (
                        proposal_id, run_item_id, run_id, target_type, target_id,
                        field_path, proposed_value_json, existing_normalized_value_json,
                        evidence_id, confidence, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        proposal_id,
                        item_id,
                        run_id,
                        target_type,
                        item["target_id"],
                        field_path,
                        _json(proposed),
                        _json(
                            item.get("existing_normalized_value")
                            if "existing_normalized_value" in item
                            else _decode(item.get("existing_normalized_value_json"), None)
                        ),
                        evidence_ids[0] if evidence_ids else "",
                        confidence,
                        utc_now_iso(),
                    ),
                )
                self._audit(
                    connection,
                    event_type="proposal_created",
                    actor_id=worker_id,
                    plan_id=run["plan_id"],
                    run_id=run_id,
                    run_item_id=item_id,
                    proposal_id=proposal_id,
                    payload={"evidence_ids": evidence_ids, "report_only": True},
                )
            self._audit(
                connection,
                event_type="item_completed",
                actor_id=worker_id,
                plan_id=run["plan_id"],
                run_id=run_id,
                run_item_id=item_id,
                payload={
                    "state": state,
                    "evidence_ids": evidence_ids,
                    "request_count": result.request_count,
                    "cost_units": result.cost_units,
                },
            )

        self._transaction(persist)

    def _audit_item(
        self,
        run: Mapping[str, Any],
        item: Mapping[str, Any],
        actor_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        def write(connection):
            self._audit(
                connection,
                event_type=event_type,
                actor_id=actor_id,
                plan_id=run["plan_id"],
                run_id=run["run_id"],
                run_item_id=item["run_item_id"],
                payload=payload,
            )

        self._transaction(write)

    def _finish_run(self, run_id: str, worker_id: str) -> dict[str, Any]:
        def finish(connection):
            run = self._load_run(connection, run_id)
            if _text(run["status"]) in TERMINAL_RUN_STATUSES:
                return self._run_payload(run)
            if _as_bool(run.get("cancellation_requested")):
                status = "cancelled"
                connection.execute(
                    "UPDATE enrichment_operation_run_items SET attempt_state='cancelled', updated_at=? WHERE run_id=? AND attempt_state IN ('pending','running','retryable_error')",
                    (utc_now_iso(), run_id),
                )
            else:
                states = [
                    _text(row["attempt_state"])
                    for row in connection.execute(
                        "SELECT attempt_state FROM enrichment_operation_run_items WHERE run_id=?", (run_id,)
                    ).fetchall()
                ]
                failures = [
                    state for state in states if state in {"permanent_error", "unavailable", "budget_exhausted"}
                ]
                pending = [state for state in states if state in {"pending", "running", "retryable_error"}]
                if pending:
                    status = "running"
                elif failures and len(failures) == len(states):
                    status = "failed"
                elif failures:
                    status = "partially_completed"
                else:
                    status = "completed"
            now = utc_now_iso()
            connection.execute(
                "UPDATE enrichment_operation_runs SET status=?, lease_owner='', lease_expires_at='', completed_at=CASE WHEN ? IN ('completed','partially_completed','failed','cancelled') THEN ? ELSE completed_at END, updated_at=? WHERE run_id=?",
                (status, status, now, now, run_id),
            )
            if status in TERMINAL_RUN_STATUSES:
                self._audit(
                    connection,
                    event_type="run_completed",
                    actor_id=worker_id,
                    plan_id=run["plan_id"],
                    run_id=run_id,
                    payload={"status": status, "report_only": True},
                )
            return self._run_payload(
                connection.execute("SELECT * FROM enrichment_operation_runs WHERE run_id=?", (run_id,)).fetchone()
            )

        return self._transaction(finish)

    def process_run(
        self, run_id: str, *, worker_id: str = "enrichment-worker", lease_seconds: int = 300
    ) -> dict[str, Any]:
        run = self._claim_run(run_id, worker_id, lease_seconds)
        if _text(run["status"]) in TERMINAL_RUN_STATUSES | {"paused"}:
            return self.get_result(run_id)
        if _text(run["status"]) == "running" and _text(run.get("lease_owner")) != _text(worker_id):
            return self.get_result(run_id)
        while True:
            current = self.get_run(run_id, include_items=True)
            if current is None:
                raise KeyError(f"Enrichment run '{run_id}' not found.")
            if current.get("cancellation_requested"):
                break
            pending = [
                item
                for item in current.get("items", [])
                if _text(item.get("attempt_state")) in {"pending", "retryable_error"}
            ]
            if not pending:
                break
            item = pending[0]
            policy = dict(current.get("retry_policy") or {})
            if int(item.get("retry_count") or 0) >= max(1, int(policy.get("max_attempts") or 2)):
                self._update_item(
                    item["run_item_id"], attempt_state="permanent_error", failure_reason="retry_limit_exhausted"
                )
                continue
            self._process_item(current, item, worker_id)
        return self._finish_run(run_id, worker_id)

    def process_next_run(self, *, worker_id: str = "enrichment-worker") -> dict[str, Any] | None:
        with database_session(self.db_path) as connection:
            row = connection.execute(
                "SELECT run_id FROM enrichment_operation_runs WHERE status IN ('pending','running') AND (status='pending' OR lease_expires_at='' OR lease_expires_at<=?) ORDER BY created_at, run_id LIMIT 1",
                (utc_now_iso(),),
            ).fetchone()
        return self.process_run(row["run_id"], worker_id=worker_id) if row is not None else None

    def cancel_run(self, run_id: str, *, actor_id: str, reason: str = "") -> dict[str, Any]:
        def cancel(connection):
            run = self._load_run(connection, run_id)
            if _text(run["status"]) in TERMINAL_RUN_STATUSES:
                return self._run_payload(run)
            now = utc_now_iso()
            if _text(run["status"]) in {"pending", "paused"}:
                connection.execute(
                    "UPDATE enrichment_operation_runs SET status='cancelled', completed_at=?, updated_at=? WHERE run_id=?",
                    (now, now, run_id),
                )
                connection.execute(
                    "UPDATE enrichment_operation_run_items SET attempt_state='cancelled', failure_reason=?, updated_at=? WHERE run_id=? AND attempt_state IN ('pending','running','retryable_error')",
                    (reason or "cancelled_by_reviewer", now, run_id),
                )
            else:
                connection.execute(
                    "UPDATE enrichment_operation_runs SET cancellation_requested=1, updated_at=? WHERE run_id=?",
                    (now, run_id),
                )
            self._audit(
                connection,
                event_type="run_cancel_requested",
                actor_id=actor_id,
                plan_id=run["plan_id"],
                run_id=run_id,
                payload={"reason": reason},
            )
            return self._run_payload(
                connection.execute("SELECT * FROM enrichment_operation_runs WHERE run_id=?", (run_id,)).fetchone()
            )

        return self._transaction(cancel)

    def pause_run(self, run_id: str, *, actor_id: str, reason: str = "") -> dict[str, Any]:
        def pause(connection):
            run = self._load_run(connection, run_id)
            if _text(run["status"]) not in {"pending", "running"}:
                return self._run_payload(run)
            now = utc_now_iso()
            connection.execute(
                "UPDATE enrichment_operation_runs SET status='paused', lease_owner='', lease_expires_at='', updated_at=? WHERE run_id=?",
                (now, run_id),
            )
            self._audit(
                connection,
                event_type="run_paused",
                actor_id=actor_id,
                plan_id=run["plan_id"],
                run_id=run_id,
                payload={"reason": reason},
            )
            return self._run_payload(
                connection.execute("SELECT * FROM enrichment_operation_runs WHERE run_id=?", (run_id,)).fetchone()
            )

        return self._transaction(pause)

    def get_result(self, run_id: str) -> dict[str, Any]:
        with database_session(self.db_path) as connection:
            run = self._load_run(connection, _text(run_id))
            result = self._run_payload(run)
            result["items"] = [
                self._item_payload(item)
                for item in connection.execute(
                    "SELECT * FROM enrichment_operation_run_items WHERE run_id=? ORDER BY target_id, field_path",
                    (run_id,),
                ).fetchall()
            ]
            proposals = []
            for proposal in connection.execute(
                "SELECT * FROM enrichment_field_proposals WHERE run_id=? ORDER BY created_at, proposal_id", (run_id,)
            ).fetchall():
                item = dict(proposal)
                item["proposed_value"] = _decode(item.pop("proposed_value_json", ""), None)
                item["existing_normalized_value"] = _decode(item.pop("existing_normalized_value_json", ""), None)
                item["current_state"] = self._proposal_state(connection, item["proposal_id"])
                item["actions"] = [
                    _row(action)
                    for action in connection.execute(
                        "SELECT * FROM enrichment_proposal_actions WHERE proposal_id=? ORDER BY created_at, action_id",
                        (item["proposal_id"],),
                    ).fetchall()
                ]
                proposals.append(item)
            result["proposals"] = proposals
            return result

    def _proposal(self, connection, proposal_id: str) -> dict[str, Any]:
        proposal = _row(
            connection.execute(
                "SELECT * FROM enrichment_field_proposals WHERE proposal_id=?", (proposal_id,)
            ).fetchone()
        )
        if proposal is None:
            raise KeyError(f"Enrichment proposal '{proposal_id}' not found.")
        return proposal

    def review_proposal(
        self,
        proposal_id: str,
        *,
        action: str,
        reviewer_id: str,
        reason: str = "",
        replacement_proposal_id: str = "",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        action = _text(action).casefold()
        if action not in {"accept", "reject", "undo", "supersede"}:
            raise ValueError("Proposal action must be accept, reject, undo, or supersede.")

        def review(connection):
            proposal = self._proposal(connection, proposal_id)
            if action == "supersede":
                replacement = self._proposal(connection, replacement_proposal_id)
                if replacement["run_item_id"] != proposal["run_item_id"]:
                    raise ValueError("A superseding proposal must target the same run item.")
            if idempotency_key:
                existing = connection.execute(
                    "SELECT * FROM enrichment_proposal_actions WHERE proposal_id=? AND idempotency_key=?",
                    (proposal_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    return self._proposal_view(connection, proposal_id)
            now = utc_now_iso()
            connection.execute(
                "INSERT INTO enrichment_proposal_actions (action_id, proposal_id, action, reviewer_id, reason, replacement_proposal_id, idempotency_key, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"enrichment_proposal_action_{uuid4().hex}",
                    proposal_id,
                    action,
                    _text(reviewer_id),
                    _text(reason),
                    _text(replacement_proposal_id),
                    _text(idempotency_key),
                    now,
                ),
            )
            self._audit(
                connection,
                event_type=f"proposal_{action}",
                actor_id=reviewer_id,
                plan_id="",
                run_id=proposal["run_id"],
                run_item_id=proposal["run_item_id"],
                proposal_id=proposal_id,
                payload={"reason": reason, "replacement_proposal_id": replacement_proposal_id, "report_only": True},
            )
            return self._proposal_view(connection, proposal_id)

        return self._transaction(review)

    def _proposal_view(self, connection, proposal_id: str) -> dict[str, Any]:
        proposal = self._proposal(connection, proposal_id)
        proposal["proposed_value"] = _decode(proposal.pop("proposed_value_json", ""), None)
        proposal["existing_normalized_value"] = _decode(proposal.pop("existing_normalized_value_json", ""), None)
        proposal["current_state"] = self._proposal_state(connection, proposal_id)
        proposal["actions"] = [
            _row(action)
            for action in connection.execute(
                "SELECT * FROM enrichment_proposal_actions WHERE proposal_id=? ORDER BY created_at, action_id",
                (proposal_id,),
            ).fetchall()
        ]
        return proposal

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        with database_session(self.db_path) as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM enrichment_field_proposals WHERE proposal_id=?", (_text(proposal_id),)
                ).fetchone()
                is None
            ):
                return None
            return self._proposal_view(connection, _text(proposal_id))

    def list_proposals(self, *, run_id: str = "", target_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
        with database_session(self.db_path) as connection:
            predicates: list[str] = []
            params: list[Any] = []
            if _text(run_id):
                predicates.append("run_id=?")
                params.append(_text(run_id))
            if _text(target_id):
                predicates.append("target_id=?")
                params.append(_text(target_id))
            where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
            rows = connection.execute(
                f"SELECT proposal_id FROM enrichment_field_proposals {where} ORDER BY created_at DESC, proposal_id DESC LIMIT ?",
                (*params, max(1, min(500, int(limit)))),
            ).fetchall()
            return [self._proposal_view(connection, row["proposal_id"]) for row in rows]

    def list_audit_events(
        self, *, plan_id: str = "", run_id: str = "", proposal_id: str = "", limit: int = 200
    ) -> list[dict[str, Any]]:
        with database_session(self.db_path) as connection:
            predicates: list[str] = []
            params: list[Any] = []
            if _text(plan_id):
                predicates.append("plan_id=?")
                params.append(_text(plan_id))
            if _text(run_id):
                predicates.append("run_id=?")
                params.append(_text(run_id))
            if _text(proposal_id):
                predicates.append("proposal_id=?")
                params.append(_text(proposal_id))
            where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
            rows = connection.execute(
                f"SELECT * FROM enrichment_operation_audit_events {where} ORDER BY created_at, event_id LIMIT ?",
                (*params, max(1, min(1000, int(limit)))),
            ).fetchall()
            result = []
            for row in rows:
                value = dict(row)
                value["payload"] = _decode(value.pop("payload_json", ""), {})
                result.append(value)
            return result

    def configure_provider_budget(
        self,
        provider_id: str,
        *,
        max_requests: int,
        max_cost_units: float,
        enabled: bool = True,
        actor_id: str = "",
    ) -> dict[str, Any]:
        provider_id = _text(provider_id).casefold()
        if provider_id not in APPROVED_PROVIDER_IDS:
            raise ValueError("Only null and offline fixture providers can be configured.")

        def write(connection):
            now = utc_now_iso()
            connection.execute(
                """
                INSERT INTO enrichment_provider_budgets (provider_id, configured, enabled, max_requests, max_cost_units, policy_state, updated_at)
                VALUES (?, 1, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_id) DO UPDATE SET enabled=excluded.enabled, max_requests=excluded.max_requests, max_cost_units=excluded.max_cost_units, updated_at=excluded.updated_at
                """,
                (
                    provider_id,
                    int(bool(enabled)),
                    max(0, int(max_requests)),
                    max(0.0, float(max_cost_units)),
                    "enabled" if enabled else "blocked_by_policy",
                    now,
                ),
            )
            self._audit(
                connection,
                event_type="provider_budget_configured",
                actor_id=actor_id,
                payload={
                    "provider_id": provider_id,
                    "max_requests": max_requests,
                    "max_cost_units": max_cost_units,
                    "enabled": enabled,
                },
            )
            return (
                _row(
                    connection.execute(
                        "SELECT * FROM enrichment_provider_budgets WHERE provider_id=?", (provider_id,)
                    ).fetchone()
                )
                or {}
            )

        return self._transaction(write)

    def list_provider_budgets(self) -> list[dict[str, Any]]:
        with database_session(self.db_path) as connection:
            return [
                _row(row) or {}
                for row in connection.execute(
                    "SELECT * FROM enrichment_provider_budgets ORDER BY provider_id"
                ).fetchall()
            ]

    def capabilities(
        self, *, target_type: str = "", selected_fields: Sequence[Any] = (), provider_id: str = ""
    ) -> dict[str, Any]:
        fields = _normalise_list(selected_fields)
        with database_session(self.db_path) as connection:
            budgets = {
                str(row["provider_id"]): dict(row)
                for row in connection.execute("SELECT * FROM enrichment_provider_budgets").fetchall()
            }
        providers = [provider_id] if _text(provider_id) else list(KNOWN_PROVIDER_IDS)
        entries = []
        for current in providers:
            current = _text(current).casefold()
            budget = budgets.get(current, {})
            configured = _as_bool(budget.get("configured")) if budget else False
            enabled = _as_bool(budget.get("enabled")) if budget else False
            if current not in APPROVED_PROVIDER_IDS:
                status = "blocked_by_policy" if current in {"official_website", "live"} else "unavailable"
            elif not configured:
                status = "unavailable"
            elif not enabled or _text(budget.get("policy_state")) == "blocked_by_policy":
                status = "blocked_by_policy"
            else:
                supported = True
                if fields and target_type:
                    supported = all(
                        field in _provider_fields(current, target_type)
                        or _provider_target_type(target_type, field) in {"company", "place", "occupation"}
                        and _provider_for(current, target_type, field) is not None
                        for field in fields
                    )
                exhausted = bool(
                    int(budget.get("max_requests") or 0) > 0
                    and int(budget.get("requests_used") or 0) >= int(budget.get("max_requests") or 0)
                ) or bool(
                    float(budget.get("max_cost_units") or 0) > 0
                    and float(budget.get("cost_units_used") or 0) >= float(budget.get("max_cost_units") or 0)
                )
                status = "budget_exhausted" if exhausted else "enabled" if supported else "unavailable"
            entries.append(
                {
                    "provider_id": current,
                    "configured": configured,
                    "enabled": enabled,
                    "status": status,
                    "max_requests": int(budget.get("max_requests") or 0),
                    "max_cost_units": float(budget.get("max_cost_units") or 0),
                    "requests_used": int(budget.get("requests_used") or 0),
                    "cost_units_used": float(budget.get("cost_units_used") or 0),
                    "network_allowed": False,
                    "report_only": True,
                }
            )
        return {
            "capabilities": entries,
            "target_type": _text(target_type),
            "selected_fields": fields,
            "external_request_budget_default": 0,
            "network_calls_allowed": False,
            "report_only": True,
        }


__all__ = [
    "APPROVED_PROVIDER_IDS",
    "EnrichmentOperationService",
    "RUN_STATUSES",
]
