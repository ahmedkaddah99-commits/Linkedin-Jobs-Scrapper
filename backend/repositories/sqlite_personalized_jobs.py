from __future__ import annotations

import json
import time
from threading import RLock
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.domain.models import utc_now_iso, utc_plus_seconds
from backend.domain.job_filter_source_cache import use_cached_source
from backend.database.connection import database_read_session, database_target_info
from backend.repositories.sqlite_core import _SqliteStore


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode(value: str | bytes | None, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return default
    return decoded


def _row_payload(row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _profile_status(profile: Mapping[str, Any]) -> str:
    fields = profile.get("fields") if isinstance(profile, Mapping) else {}
    if not isinstance(fields, Mapping) or not fields:
        return "absent"
    states = {str(item.get("state") or "unknown") for item in fields.values() if isinstance(item, Mapping)}
    if "conflicted" in states:
        return "conflicted"
    known = sum(
        1
        for item in fields.values()
        if isinstance(item, Mapping) and str(item.get("state") or "") == "known" and item.get("value") not in (None, "", [])
    )
    return "present" if known == len(fields) and known else "incomplete" if known else "absent"


def _customer_task_payload(row, *, include_lease: bool = True) -> dict[str, Any]:
    payload = _decode(row["payload_json"], {})
    result = _decode(row["result_json"], {})
    response = {
        "task_id": str(row["task_id"] or ""),
        "user_id": str(row["user_id"] or ""),
        "task_type": str(row["task_type"] or ""),
        "idempotency_key": str(row["idempotency_key"] or ""),
        "state": str(row["state"] or ""),
        "payload": payload if isinstance(payload, dict) else {},
        "result": result if isinstance(result, dict) else {},
        "error_code": str(row["error_code"] or ""),
        "error_message": str(row["error_message"] or ""),
        "attempt_count": int(row["attempt_count"] or 0),
        "max_attempts": int(row["max_attempts"] or 0),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
        "started_at": str(row["started_at"] or ""),
        "completed_at": str(row["completed_at"] or ""),
    }
    if include_lease:
        response.update(
            {
                "lease_owner": str(row["lease_owner"] or ""),
                "lease_token": str(row["lease_token"] or ""),
                "lease_expires_at": str(row["lease_expires_at"] or ""),
            }
        )
    return response


class SqlitePersonalizedJobsStore(_SqliteStore):
    """Persistence boundary for user state and read-only catalog projections."""

    # Bounded, store-local cache for the filter-capability aggregate. A
    # publication ID is only unique within one database, so sharing this cache
    # across store instances can return another database's capabilities.
    _FILTER_CAPABILITIES_CACHE_LIMIT = 8
    _DYNAMIC_CAPABILITY_SCAN_LIMIT = 5_000

    def __init__(self, db_path: Path, *, initialize: bool = True):
        super().__init__(db_path, initialize=initialize)
        self._filter_capabilities_cache: dict[str, dict[str, bool]] = {}
        self._feed_counts: dict[str, tuple[float, int]] = {}
        self._feed_counts_lock = RLock()

    def _cached_feed_count(self, key: str) -> int | None:
        with self._feed_counts_lock:
            cached = self._feed_counts.get(key)
            return cached[1] if cached and time.monotonic() - cached[0] < 120 else None

    def _remember_feed_count(self, key: str, total: int) -> None:
        with self._feed_counts_lock:
            if len(self._feed_counts) >= 512:
                self._feed_counts.pop(next(iter(self._feed_counts)))
            self._feed_counts[key] = (time.monotonic(), total)

    def list_profile_job_facts(self, version_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        ids = list(dict.fromkeys(str(v) for v in version_ids if v))
        if not ids:
            return {}
        placeholders = ','.join('?' for _ in ids)
        with self._connect() as connection:
            rows = self._fetch_read_rows(connection, f"""SELECT m.version_id,m.facts_json
                FROM profile_job_facts m
                JOIN job_posting_versions v ON v.version_id=m.version_id AND v.content_hash=m.content_hash
                JOIN canonical_jobs j ON j.canonical_job_id=m.canonical_job_id AND j.current_version_id=v.version_id
                LEFT JOIN job_description_intelligence d ON d.version_id=v.version_id AND d.content_hash=v.content_hash
                LEFT JOIN job_filter_intelligence f ON f.version_id=v.version_id AND f.content_hash=v.content_hash
                LEFT JOIN canonical_company_profiles p ON p.company_id=j.company_id
                WHERE m.version_id IN ({placeholders}) AND m.feature_version='profile_job_facts_v1'
                AND m.input_signature=COALESCE(d.updated_at,'') || '|' || COALESCE(f.generated_at,'') || '|' || COALESCE(json_extract(p.profile_json,'$.fields.industry'),'')""", ids)
        return {str(r['version_id']): _decode(r['facts_json'], {}) for r in rows}

    def get_preferences(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM personalized_search_preferences WHERE user_id = ?",
                (str(user_id),),
            ).fetchone()
        if row is None:
            return None
        payload = _decode(row["payload_json"], {})
        return {
            "user_id": str(row["user_id"]),
            "profile_id": str(row["profile_id"] or ""),
            "revision": int(row["revision"] or 1),
            "preferences": payload if isinstance(payload, dict) else {},
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

    def upsert_preferences(
        self,
        user_id: str,
        payload: Mapping[str, Any],
        *,
        profile_id: str = "",
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        user_id = str(user_id or "").strip()
        if not user_id:
            raise ValueError("user_id is required")
        normalized_payload = dict(payload)

        def write(connection):
            existing = connection.execute(
                "SELECT revision, created_at, profile_id FROM personalized_search_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            current_revision = int(existing["revision"] or 0) if existing is not None else 0
            if expected_revision is not None and current_revision != int(expected_revision):
                raise ValueError("preferences_revision_conflict")
            revision = current_revision + 1 if existing is not None else 1
            created_at = str(existing["created_at"] or now) if existing is not None else now
            resolved_profile_id = str(profile_id or (existing["profile_id"] if existing is not None else "") or "")
            connection.execute(
                """
                INSERT INTO personalized_search_preferences (
                    user_id, profile_id, revision, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    profile_id=excluded.profile_id,
                    revision=excluded.revision,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (user_id, resolved_profile_id, revision, _json(normalized_payload), created_at, now),
            )
            return {
                "user_id": user_id,
                "profile_id": resolved_profile_id,
                "revision": revision,
                "preferences": normalized_payload,
                "created_at": created_at,
                "updated_at": now,
            }

        return self._run_transaction(write)

    def get_default_saved_search(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM personalized_saved_searches WHERE user_id = ? AND is_default = 1",
                (str(user_id),),
            ).fetchone()
        if row is None:
            return None
        payload = _decode(row["payload_json"], {})
        return {
            "saved_search_id": str(row["saved_search_id"]),
            "user_id": str(row["user_id"]),
            "name": str(row["name"] or "Default search"),
            "filters": payload["filters"] if isinstance(payload, dict) and isinstance(payload.get("filters"), dict) else (payload if isinstance(payload, dict) else {}),
            "active_filter_set_id": str(payload.get("active_filter_set_id") or "") if isinstance(payload, dict) and isinstance(payload.get("filters"), dict) else "",
            "is_default": bool(int(row["is_default"] or 0)),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

    def list_filter_sets(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM personalized_filter_sets WHERE user_id = ? ORDER BY updated_at DESC",
                (str(user_id),),
            ).fetchall()
        return [{"filter_set_id": str(row["filter_set_id"]), "name": str(row["name"]),
                 "filters": _decode(row["payload_json"], {}), "updated_at": str(row["updated_at"])} for row in rows]

    def save_filter_set(self, user_id: str, name: str, filters: Mapping[str, Any], filter_set_id: str = "") -> dict[str, Any]:
        now = utc_now_iso()
        identifier = filter_set_id or f"filter_set_{uuid4().hex}"
        def write(connection):
            existing = connection.execute(
                "SELECT created_at FROM personalized_filter_sets WHERE filter_set_id = ? AND user_id = ?",
                (identifier, user_id),
            ).fetchone()
            if filter_set_id and existing is None:
                raise ValueError("filter set not found")
            connection.execute(
                "INSERT INTO personalized_filter_sets (filter_set_id, user_id, name, payload_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(filter_set_id) DO UPDATE SET "
                "name=excluded.name, payload_json=excluded.payload_json, updated_at=excluded.updated_at",
                (identifier, user_id, name, _json(dict(filters)), str(existing["created_at"]) if existing else now, now),
            )
            self._activate_filter_set(connection, user_id, identifier)
            return {"filter_set_id": identifier, "name": name, "filters": dict(filters), "updated_at": now}
        return self._run_transaction(write)

    @staticmethod
    def _activate_filter_set(connection, user_id: str, filter_set_id: str) -> dict[str, Any]:
        row = connection.execute(
            "SELECT name, payload_json FROM personalized_filter_sets WHERE user_id=? AND filter_set_id=?",
            (user_id, filter_set_id),
        ).fetchone()
        if row is None:
            raise ValueError("filter set not found")
        filters = _decode(row["payload_json"], {})
        now = utc_now_iso()
        payload = {"filters": filters, "active_filter_set_id": filter_set_id}
        connection.execute(
            "INSERT INTO personalized_saved_searches "
            "(saved_search_id, user_id, name, payload_json, is_default, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 1, ?, ?) ON CONFLICT(user_id) DO UPDATE SET "
            "name=excluded.name, payload_json=excluded.payload_json, is_default=1, updated_at=excluded.updated_at",
            (f"saved_search_{uuid4().hex}", user_id, row["name"], _json(payload), now, now),
        )
        return {"active_filter_set_id": filter_set_id, "name": str(row["name"]), "filters": filters, "is_default": True}

    def activate_filter_set(self, user_id: str, filter_set_id: str) -> dict[str, Any]:
        return self._run_transaction(lambda c: self._activate_filter_set(c, user_id, filter_set_id))

    def delete_filter_set(self, user_id: str, filter_set_id: str) -> bool:
        def write(connection):
            connection.execute(
                "DELETE FROM personalized_saved_searches WHERE user_id=? "
                "AND json_extract(payload_json, '$.active_filter_set_id')=?",
                (user_id, filter_set_id),
            )
            return connection.execute(
                "DELETE FROM personalized_filter_sets WHERE user_id = ? AND filter_set_id = ?",
                (user_id, filter_set_id),
            ).rowcount > 0
        return self._run_transaction(write)

    def upsert_default_saved_search(
        self,
        user_id: str,
        payload: Mapping[str, Any],
        *,
        name: str = "Default search",
    ) -> dict[str, Any]:
        now = utc_now_iso()
        user_id = str(user_id or "").strip()
        if not user_id:
            raise ValueError("user_id is required")
        normalized_payload = dict(payload)

        def write(connection):
            existing = connection.execute(
                "SELECT saved_search_id, created_at FROM personalized_saved_searches WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            saved_search_id = str(existing["saved_search_id"]) if existing is not None else f"saved_search_{uuid4().hex}"
            created_at = str(existing["created_at"] or now) if existing is not None else now
            connection.execute(
                """
                INSERT INTO personalized_saved_searches (
                    saved_search_id, user_id, name, payload_json, is_default, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    name=excluded.name,
                    payload_json=excluded.payload_json,
                    is_default=1,
                    updated_at=excluded.updated_at
                """,
                (saved_search_id, user_id, str(name or "Default search"), _json(normalized_payload), created_at, now),
            )
            return {
                "saved_search_id": saved_search_id,
                "user_id": user_id,
                "name": str(name or "Default search"),
                "filters": normalized_payload,
                "is_default": True,
                "created_at": created_at,
                "updated_at": now,
            }

        return self._run_transaction(write)

    def list_dispositions(self, user_id: str, *, states: Iterable[str] = ()) -> dict[str, dict[str, Any]]:
        state_values = tuple(str(state) for state in states if str(state).strip())
        sql = "SELECT * FROM personalized_job_dispositions WHERE user_id = ?"
        params: list[Any] = [str(user_id)]
        if state_values:
            placeholders = ",".join("?" for _ in state_values)
            sql += f" AND state IN ({placeholders})"
            params.extend(state_values)
        with self._connect() as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()
        return {str(row["canonical_job_id"]): _row_payload(row) for row in rows}

    def list_dispositions_for_jobs(self, user_id: str, canonical_job_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        job_ids = tuple(dict.fromkeys(str(item) for item in canonical_job_ids if str(item).strip()))
        if not job_ids:
            return {}
        placeholders = ",".join("?" for _ in job_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM personalized_job_dispositions WHERE user_id = ? AND canonical_job_id IN ({placeholders})",
                (str(user_id), *job_ids),
            ).fetchall()
        return {str(row["canonical_job_id"]): _row_payload(row) for row in rows}

    def set_disposition(
        self,
        user_id: str,
        canonical_job_id: str,
        *,
        state: str,
        source_of_change: str = "user",
        reason_code: str = "",
    ) -> dict[str, Any]:
        now = utc_now_iso()
        user_id = str(user_id or "").strip()
        canonical_job_id = str(canonical_job_id or "").strip()
        if not user_id or not canonical_job_id:
            raise ValueError("user_id and canonical_job_id are required")

        def write(connection):
            existing = connection.execute(
                "SELECT created_at FROM personalized_job_dispositions WHERE user_id = ? AND canonical_job_id = ?",
                (user_id, canonical_job_id),
            ).fetchone()
            created_at = str(existing["created_at"] or now) if existing is not None else now
            applied_at = now if state == "applied" else ""
            connection.execute(
                """
                INSERT INTO personalized_job_dispositions (
                    user_id, canonical_job_id, state, source_of_change,
                    reason_code, applied_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, canonical_job_id) DO UPDATE SET
                    state=excluded.state,
                    source_of_change=excluded.source_of_change,
                    reason_code=excluded.reason_code,
                    applied_at=CASE WHEN excluded.state='applied' THEN excluded.applied_at ELSE personalized_job_dispositions.applied_at END,
                    updated_at=excluded.updated_at
                """,
                (user_id, canonical_job_id, str(state), str(source_of_change or "user"), str(reason_code or ""), applied_at, created_at, now),
            )
            row = connection.execute(
                "SELECT * FROM personalized_job_dispositions WHERE user_id = ? AND canonical_job_id = ?",
                (user_id, canonical_job_id),
            ).fetchone()
            return _row_payload(row)

        result = self._run_transaction(write)
        with self._feed_counts_lock:
            self._feed_counts.clear()
        return result

    def record_event(
        self,
        user_id: str,
        *,
        event_name: str,
        canonical_job_id: str = "",
        reason_code: str = "",
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "event_id": f"personalized_event_{uuid4().hex}",
            "user_id": str(user_id),
            "canonical_job_id": str(canonical_job_id or ""),
            "event_name": str(event_name),
            "reason_code": str(reason_code or ""),
            "payload": dict(payload or {}),
            "occurred_at": utc_now_iso(),
        }
        if not event["user_id"] or not event["event_name"]:
            raise ValueError("user_id and event_name are required")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO personalized_job_events (
                    event_id, user_id, canonical_job_id, event_name,
                    reason_code, payload_json, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event["event_id"], event["user_id"], event["canonical_job_id"], event["event_name"], event["reason_code"], _json(event["payload"]), event["occurred_at"]),
            )
        return event

    def get_evaluation(
        self,
        user_id: str,
        canonical_job_id: str,
        *,
        job_version_id: str = "",
        preferences_revision: int = 0,
        evaluator_version: str = "phase_c_v1",
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM personalized_job_evaluations
                WHERE user_id = ? AND canonical_job_id = ? AND job_version_id = ?
                  AND preferences_revision = ? AND evaluator_version = ?
                """,
                (str(user_id), str(canonical_job_id), str(job_version_id or ""), int(preferences_revision), str(evaluator_version)),
            ).fetchone()
        if row is None:
            return None
        payload = _decode(row["payload_json"], {})
        return {
            "user_id": str(row["user_id"]),
            "canonical_job_id": str(row["canonical_job_id"]),
            "job_version_id": str(row["job_version_id"] or ""),
            "preferences_revision": int(row["preferences_revision"] or 0),
            "evaluator_version": str(row["evaluator_version"]),
            "state": str(row["state"]),
            "payload": payload if isinstance(payload, dict) else {},
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

    def list_evaluations_for_jobs(
        self,
        user_id: str,
        canonical_job_ids: Iterable[str],
        *,
        preferences_revision: int = 0,
        evaluator_version: str = "phase_e_v2",
    ) -> dict[str, dict[str, Any]]:
        job_ids = tuple(dict.fromkeys(str(item) for item in canonical_job_ids if str(item).strip()))
        if not job_ids:
            return {}
        placeholders = ",".join("?" for _ in job_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM personalized_job_evaluations
                WHERE user_id = ? AND preferences_revision = ? AND evaluator_version = ?
                  AND canonical_job_id IN ({placeholders})
                ORDER BY updated_at DESC
                """,
                (str(user_id), int(preferences_revision), str(evaluator_version), *job_ids),
            ).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            result.setdefault(str(row["canonical_job_id"]), _row_payload(row))
        return result

    def save_evaluation(
        self,
        user_id: str,
        canonical_job_id: str,
        *,
        job_version_id: str,
        preferences_revision: int,
        evaluator_version: str,
        state: str,
        payload: Mapping[str, Any],
    ) -> None:
        now = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO personalized_job_evaluations (
                    user_id, canonical_job_id, job_version_id, preferences_revision,
                    evaluator_version, state, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, canonical_job_id, job_version_id, preferences_revision, evaluator_version)
                DO UPDATE SET state=excluded.state, payload_json=excluded.payload_json, updated_at=excluded.updated_at
                """,
                (str(user_id), str(canonical_job_id), str(job_version_id or ""), int(preferences_revision), str(evaluator_version), str(state), _json(dict(payload)), now, now),
            )

    def get_description_intelligence(
        self,
        version_id: str,
        *,
        content_hash: str = "",
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM job_description_intelligence WHERE version_id = ?",
                (str(version_id or ""),),
            ).fetchone()
        if row is None:
            return None
        if content_hash and str(row["content_hash"] or "") != str(content_hash):
            return None
        return {
            "version_id": str(row["version_id"] or ""),
            "canonical_job_id": str(row["canonical_job_id"] or ""),
            "content_hash": str(row["content_hash"] or ""),
            "summary": _decode(row["summary_json"], {}),
            "structured_description": _decode(row["structured_json"], {}),
            "original_posting": _decode(row["original_json"], {}),
            "provider": str(row["provider"] or ""),
            "model": str(row["model"] or ""),
            "prompt_version": str(row["prompt_version"] or ""),
            "generated_at": str(row["generated_at"] or ""),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

    def save_description_intelligence(
        self,
        *,
        version_id: str,
        canonical_job_id: str,
        content_hash: str,
        summary: Mapping[str, Any],
        structured_description: Mapping[str, Any],
        original_posting: Mapping[str, Any],
        provider: str,
        model: str = "",
        prompt_version: str = "",
        generated_at: str = "",
    ) -> dict[str, Any]:
        now = utc_now_iso()
        generated = str(generated_at or now)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO job_description_intelligence (
                    version_id, canonical_job_id, content_hash, summary_json,
                    structured_json, original_json, provider, model,
                    prompt_version, generated_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(version_id) DO UPDATE SET
                    canonical_job_id=excluded.canonical_job_id,
                    content_hash=excluded.content_hash,
                    summary_json=excluded.summary_json,
                    structured_json=excluded.structured_json,
                    original_json=excluded.original_json,
                    provider=excluded.provider,
                    model=excluded.model,
                    prompt_version=excluded.prompt_version,
                    generated_at=excluded.generated_at,
                    updated_at=excluded.updated_at
                """,
                (
                    str(version_id or ""),
                    str(canonical_job_id or ""),
                    str(content_hash or ""),
                    _json(dict(summary)),
                    _json(dict(structured_description)),
                    _json(dict(original_posting)),
                    str(provider or ""),
                    str(model or ""),
                    str(prompt_version or ""),
                    generated,
                    now,
                    now,
                ),
            )
        return self.get_description_intelligence(version_id, content_hash=content_hash) or {}

    def get_intelligence_cache(self, key: Mapping[str, Any]) -> dict[str, Any] | None:
        columns = (
            "user_id", "canonical_job_id", "job_version_id", "profile_version_id",
            "cv_version_id", "evidence_version_id", "evaluator_version", "input_hash",
            "intelligence_kind",
        )
        where = " AND ".join(f"{column} = ?" for column in columns)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM job_intelligence_cache WHERE {where} LIMIT 1",
                tuple(str(key.get(column) or "") for column in columns),
            ).fetchone()
        if row is None:
            return None
        payload = _decode(row["payload_json"], {})
        result = _row_payload(row)
        result["payload"] = payload if isinstance(payload, dict) else {}
        return result

    def list_intelligence_cache_entries(
        self,
        canonical_job_ids: Iterable[str],
        *,
        user_id: str = "",
        intelligence_kind: str = "",
    ) -> list[dict[str, Any]]:
        ids = tuple(dict.fromkeys(str(item) for item in canonical_job_ids if str(item).strip()))
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        predicates = [f"canonical_job_id IN ({placeholders})"]
        params: list[Any] = list(ids)
        if user_id:
            predicates.append("user_id = ?")
            params.append(str(user_id))
        if intelligence_kind:
            predicates.append("intelligence_kind = ?")
            params.append(str(intelligence_kind))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM job_intelligence_cache WHERE " + " AND ".join(predicates) + " ORDER BY updated_at DESC",
                tuple(params),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = _row_payload(row)
            item["payload"] = _decode(row["payload_json"], {})
            result.append(item)
        return result

    @staticmethod
    def _intelligence_result(connection, cache_id: str, *, accepted: bool = False, reason: str = "") -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT c.*, q.state AS queue_state, q.attempts AS attempt_count,
                   q.lease_owner, q.lease_token, q.lease_expires_at, q.max_attempts
            FROM job_intelligence_cache c
            JOIN job_intelligence_queue q ON q.cache_id = c.cache_id
            WHERE c.cache_id=?
            """,
            (str(cache_id),),
        ).fetchone()
        if row is None:
            return {"cache_id": str(cache_id), "state": "missing", "accepted": False, "reason": reason or "missing"}
        result = _row_payload(row)
        result["payload"] = _decode(row["payload_json"], {})
        result["accepted"] = bool(accepted)
        if reason:
            result["reason"] = reason
        return result

    def enqueue_intelligence(self, key: Mapping[str, Any]) -> dict[str, Any]:
        required = ("cache_id", "canonical_job_id", "job_version_id", "evaluator_version", "input_hash", "intelligence_kind")
        missing = [name for name in required if not str(key.get(name) or "").strip()]
        if missing:
            raise ValueError(f"intelligence_key_missing:{','.join(missing)}")
        now = utc_now_iso()
        columns = (
            "cache_id", "user_id", "canonical_job_id", "job_version_id", "profile_version_id",
            "cv_version_id", "evidence_version_id", "evaluator_version", "input_hash", "intelligence_kind",
        )

        def write(connection):
            connection.execute(
                """
                INSERT INTO job_intelligence_cache (
                    cache_id, user_id, canonical_job_id, job_version_id, profile_version_id,
                    cv_version_id, evidence_version_id, evaluator_version, input_hash,
                    intelligence_kind, state, payload_json, created_at, updated_at, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '{}', ?, ?, '')
                ON CONFLICT(user_id, canonical_job_id, job_version_id, profile_version_id,
                    cv_version_id, evidence_version_id, evaluator_version, input_hash, intelligence_kind)
                DO NOTHING
                """,
                tuple(str(key.get(column) or "") for column in columns) + (now, now),
            )
            row = connection.execute(
                "SELECT * FROM job_intelligence_cache WHERE cache_id = ?",
                (str(key.get("cache_id") or ""),),
            ).fetchone()
            if row is None:
                raise RuntimeError("intelligence_cache_insert_failed")
            cache_id = str(key.get("cache_id") or "")
            existing_queue = connection.execute(
                "SELECT state FROM job_intelligence_queue WHERE cache_id=?",
                (cache_id,),
            ).fetchone()
            if existing_queue is None:
                connection.execute(
                    "INSERT INTO job_intelligence_queue (cache_id, state, attempts, requested_at, max_attempts) VALUES (?, 'queued', 0, ?, 3)",
                    (cache_id, now),
                )
            elif str(existing_queue["state"] or "") == "processing":
                pass
            elif str(existing_queue["state"] or "") == "completed" and str(row["state"] or "") == "available":
                pass
            else:
                connection.execute(
                    """
                    UPDATE job_intelligence_queue
                    SET state='queued', requested_at=?, completed_at='', last_error='',
                        lease_owner='', lease_token='', lease_expires_at=''
                    WHERE cache_id=?
                    """,
                    (now, cache_id),
                )
                connection.execute(
                    "UPDATE job_intelligence_cache SET state='pending', payload_json='{}', generated_at='', updated_at=? WHERE cache_id=?",
                    (now, cache_id),
                )
            return _row_payload(row)

        return self._run_transaction(write)

    def recover_stale_intelligence(
        self,
        *,
        now: str = "",
        max_attempts: int = 3,
    ) -> list[dict[str, Any]]:
        observed_at = str(now or utc_now_iso())
        default_max_attempts = max(1, int(max_attempts))

        def write(connection):
            rows = connection.execute(
                """
                SELECT cache_id, attempts, max_attempts
                FROM job_intelligence_queue
                WHERE state='processing' AND lease_expires_at!='' AND lease_expires_at<=?
                ORDER BY lease_expires_at, cache_id
                """,
                (observed_at,),
            ).fetchall()
            recovered: list[dict[str, Any]] = []
            for row in rows:
                cache_id = str(row["cache_id"])
                attempts = int(row["attempts"] or 0)
                attempt_limit = max(1, int(row["max_attempts"] or default_max_attempts))
                if attempts >= attempt_limit:
                    connection.execute(
                        """
                        UPDATE job_intelligence_queue
                        SET state='completed', completed_at=?, last_error='lease_expired_max_attempts',
                            lease_owner='', lease_token='', lease_expires_at=''
                        WHERE cache_id=? AND state='processing' AND attempts=?
                        """,
                        (observed_at, cache_id, attempts),
                    )
                    connection.execute(
                        "UPDATE job_intelligence_cache SET state='failed', updated_at=? WHERE cache_id=?",
                        (observed_at, cache_id),
                    )
                    recovered.append({"cache_id": cache_id, "state": "failed", "attempt_count": attempts})
                else:
                    connection.execute(
                        """
                        UPDATE job_intelligence_queue
                        SET state='queued', requested_at=?, last_error='lease_expired_requeued',
                            lease_owner='', lease_token='', lease_expires_at='', completed_at=''
                        WHERE cache_id=? AND state='processing' AND attempts=?
                        """,
                        (observed_at, cache_id, attempts),
                    )
                    connection.execute(
                        "UPDATE job_intelligence_cache SET state='pending', updated_at=? WHERE cache_id=?",
                        (observed_at, cache_id),
                    )
                    recovered.append({"cache_id": cache_id, "state": "queued", "attempt_count": attempts})
            return recovered

        return self._run_transaction(write)

    def claim_next_intelligence(
        self,
        *,
        worker_role: str = "customer",
        lease_owner: str = "runr-worker",
        lease_seconds: int = 300,
        max_attempts: int = 3,
    ) -> dict[str, Any] | None:
        if str(worker_role or "").strip().casefold() != "customer":
            return None
        now = utc_now_iso()
        owner = str(lease_owner or "runr-worker").strip() or "runr-worker"
        lease_token = f"intelligence_lease_{uuid4().hex}"
        lease_expires_at = utc_plus_seconds(max(1, int(lease_seconds)))
        attempt_limit = max(1, int(max_attempts))

        def write(connection):
            row = connection.execute(
                """
                SELECT c.*, q.attempts AS current_attempts FROM job_intelligence_cache c
                JOIN job_intelligence_queue q ON q.cache_id = c.cache_id
                WHERE q.state = 'queued' AND c.state = 'pending' AND q.attempts < q.max_attempts
                ORDER BY q.requested_at, q.cache_id LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            cache_id = str(row["cache_id"])
            next_attempt = int(row["current_attempts"] or 0) + 1
            updated = connection.execute(
                "UPDATE job_intelligence_queue SET state='processing', attempts=?, claimed_at=? WHERE cache_id=? AND state='queued' AND attempts<?",
                (next_attempt, now, cache_id, attempt_limit),
            )
            if updated.rowcount != 1:
                return None
            updated = connection.execute(
                """
                UPDATE job_intelligence_queue
                SET lease_owner=?, lease_token=?, lease_expires_at=?, max_attempts=?
                WHERE cache_id=? AND state='processing' AND attempts=?
                """,
                (owner, lease_token, lease_expires_at, attempt_limit, cache_id, next_attempt),
            )
            if updated.rowcount != 1:
                return None
            connection.execute("UPDATE job_intelligence_cache SET state='processing', updated_at=? WHERE cache_id=?", (now, cache_id))
            return self._intelligence_result(connection, cache_id, accepted=True)

        return self._run_transaction(write)

    def complete_intelligence(
        self,
        cache_id: str,
        *,
        state: str,
        payload: Mapping[str, Any],
        error: str = "",
        lease_owner: str = "",
        lease_token: str = "",
        attempt_count: int | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        normalized_state = str(state or "").strip().casefold()
        if normalized_state not in {"available", "failed"}:
            raise ValueError("intelligence_completion_state_must_be_available_or_failed")

        def write(connection):
            if not str(lease_owner or "").strip() or not str(lease_token or "").strip() or attempt_count is None:
                return self._intelligence_result(connection, str(cache_id), reason="missing_claim_fence")
            updated = connection.execute(
                """
                UPDATE job_intelligence_queue
                SET state='completed', completed_at=?, last_error=?, lease_owner='', lease_token='', lease_expires_at=''
                WHERE cache_id=? AND state='processing' AND lease_owner=? AND lease_token=? AND attempts=?
                """,
            (
                now,
                str(error or ""),
                str(cache_id),
                str(lease_owner),
                str(lease_token),
                max(1, int(attempt_count)),
            ),
            )
            if updated.rowcount != 1:
                return self._intelligence_result(connection, str(cache_id), reason="stale_claim")
            generated_at = now if normalized_state == "available" else ""
            connection.execute(
                "UPDATE job_intelligence_cache SET state=?, payload_json=?, updated_at=?, generated_at=? WHERE cache_id=?",
                (normalized_state, _json(dict(payload)), now, generated_at, str(cache_id)),
            )
            return self._intelligence_result(connection, str(cache_id), accepted=True)

        return self._run_transaction(write)

    def list_cached_descriptions(self, version_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        ids = tuple(dict.fromkeys(str(item) for item in version_ids if str(item).strip()))
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM job_description_intelligence WHERE version_id IN ({placeholders})",
                ids,
            ).fetchall()
        return {
            str(row["version_id"]): {
                "version_id": str(row["version_id"] or ""),
                "canonical_job_id": str(row["canonical_job_id"] or ""),
                "content_hash": str(row["content_hash"] or ""),
                "summary": _decode(row["summary_json"], {}),
                "structured_description": _decode(row["structured_json"], {}),
                "original_posting": _decode(row["original_json"], {}),
                "provider": str(row["provider"] or ""),
                "model": str(row["model"] or ""),
                "prompt_version": str(row["prompt_version"] or ""),
                "generated_at": str(row["generated_at"] or ""),
            }
            for row in rows
        }

    def get_company_profile(self, company_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM canonical_company_profiles WHERE company_id = ?",
                (str(company_id or ""),),
            ).fetchone()
        if row is None:
            return None
        return {
            "company_id": str(row["company_id"] or ""),
            "profile": _decode(row["profile_json"], {}),
            "profile_status": str(row["profile_status"] or "absent"),
            "logo_object_key": str(row["logo_object_key"] or ""),
            "logo_source_url": str(row["logo_source_url"] or ""),
            "logo_content_hash": str(row["logo_content_hash"] or ""),
            "logo_content_type": str(row["logo_content_type"] or ""),
            "logo_verified_at": str(row["logo_verified_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

    def upsert_company_profile(
        self,
        company_id: str,
        profile: Mapping[str, Any],
        *,
        logo_object_key: str = "",
        logo_source_url: str = "",
        logo_content_hash: str = "",
        logo_content_type: str = "",
        logo_verified_at: str = "",
    ) -> dict[str, Any]:
        company_id = str(company_id or "").strip()
        if not company_id:
            raise ValueError("company_id is required")
        now = utc_now_iso()
        profile_status = _profile_status(profile)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT created_at FROM canonical_company_profiles WHERE company_id = ?",
                (company_id,),
            ).fetchone()
            created_at = str(existing["created_at"] or now) if existing is not None else now
            connection.execute(
                """
                INSERT INTO canonical_company_profiles (
                    company_id, profile_json, profile_status, logo_object_key, logo_source_url,
                    logo_content_hash, logo_content_type, logo_verified_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_id) DO UPDATE SET
                    profile_json=excluded.profile_json,
                    profile_status=excluded.profile_status,
                    logo_object_key=CASE WHEN excluded.logo_object_key != '' THEN excluded.logo_object_key ELSE canonical_company_profiles.logo_object_key END,
                    logo_source_url=CASE WHEN excluded.logo_source_url != '' THEN excluded.logo_source_url ELSE canonical_company_profiles.logo_source_url END,
                    logo_content_hash=CASE WHEN excluded.logo_content_hash != '' THEN excluded.logo_content_hash ELSE canonical_company_profiles.logo_content_hash END,
                    logo_content_type=CASE WHEN excluded.logo_content_type != '' THEN excluded.logo_content_type ELSE canonical_company_profiles.logo_content_type END,
                    logo_verified_at=CASE WHEN excluded.logo_verified_at != '' THEN excluded.logo_verified_at ELSE canonical_company_profiles.logo_verified_at END,
                    updated_at=excluded.updated_at
                """,
                (
                    company_id,
                    _json(dict(profile)),
                    profile_status,
                    str(logo_object_key or ""),
                    str(logo_source_url or ""),
                    str(logo_content_hash or ""),
                    str(logo_content_type or ""),
                    str(logo_verified_at or ""),
                    created_at,
                    now,
                ),
            )
        return self.get_company_profile(company_id) or {"company_id": company_id, "profile": dict(profile)}

    def list_company_enrichment_targets(self, *, now: str, limit: int = 25) -> list[dict[str, Any]]:
        """Return distinct canonical companies, never one row per job."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.company_id, c.canonical_name, c.entity_kind,
                       COALESCE(
                           (SELECT u.canonical_url
                            FROM canonical_company_urls u
                            WHERE u.company_id=c.company_id AND u.url_type='homepage'
                              AND u.url_lifecycle IN ('validated', 'configured_official', 'discovered')
                            ORDER BY CASE u.url_lifecycle WHEN 'validated' THEN 0 WHEN 'configured_official' THEN 1 ELSE 2 END,
                                     u.selected_primary DESC, u.updated_at DESC
                            LIMIT 1),
                           c.provenance_url
                       ) AS provenance_url,
                       p.profile_json, p.logo_object_key, p.logo_source_url,
                       p.logo_content_hash, p.logo_content_type, p.logo_verified_at,
                       t.status AS enrichment_status, t.attempt_count,
                       t.last_success_at, t.next_attempt_at, t.last_error
                FROM canonical_companies c
                LEFT JOIN canonical_company_profiles p ON p.company_id = c.company_id
                LEFT JOIN company_enrichment_targets t ON t.company_id = c.company_id
                WHERE COALESCE(c.entity_kind, 'unknown') = 'employer'
                  AND (t.next_attempt_at IS NULL OR t.next_attempt_at = '' OR t.next_attempt_at <= ?)
                  AND (t.lease_expires_at IS NULL OR t.lease_expires_at = '' OR t.lease_expires_at <= ?)
                ORDER BY CASE WHEN t.last_success_at IS NULL OR t.last_success_at = '' THEN 0 ELSE 1 END,
                         t.last_success_at, c.company_id
                LIMIT ?
                """,
                (str(now), str(now), max(1, int(limit))),
            ).fetchall()
        return [_row_payload(row) for row in rows]

    def claim_company_enrichment_target(
        self,
        company_id: str,
        *,
        cycle_key: str,
        lease_owner: str,
        lease_expires_at: str,
        now: str,
    ) -> dict[str, Any] | None:
        """Atomically claim one company and create its cycle-idempotent attempt."""
        company_id = str(company_id or "").strip()
        cycle_key = str(cycle_key or "").strip()
        if not company_id or not cycle_key:
            raise ValueError("company_id and cycle_key are required")
        attempt_id = f"company_enrichment_{uuid4().hex}"
        idempotency_key = f"company:{company_id}:cycle:{cycle_key}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO company_enrichment_targets (
                    company_id, status, updated_at
                ) VALUES (?, 'pending', ?)
                ON CONFLICT(company_id) DO NOTHING
                """,
                (company_id, str(now)),
            )
            existing = connection.execute(
                "SELECT * FROM company_enrichment_attempts WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                return None
            claimed = connection.execute(
                """
                UPDATE company_enrichment_targets
                SET status='running', lease_owner=?, lease_expires_at=?,
                    attempt_count=attempt_count+1, last_attempt_at=?,
                    last_error='', updated_at=?
                WHERE company_id=?
                  AND (lease_expires_at='' OR lease_expires_at IS NULL OR lease_expires_at <= ?)
                """,
                (str(lease_owner), str(lease_expires_at), str(now), str(now), company_id, str(now)),
            )
            if claimed.rowcount != 1:
                return None
            connection.execute(
                """
                INSERT INTO company_enrichment_attempts (
                    attempt_id, company_id, cycle_key, idempotency_key, status, started_at
                ) VALUES (?, ?, ?, ?, 'running', ?)
                """,
                (attempt_id, company_id, cycle_key, idempotency_key, str(now)),
            )
            row = connection.execute(
                """
                SELECT c.company_id, c.canonical_name, c.entity_kind,
                       COALESCE(
                           (SELECT u.canonical_url
                            FROM canonical_company_urls u
                            WHERE u.company_id=c.company_id AND u.url_type='homepage'
                              AND u.url_lifecycle IN ('validated', 'configured_official', 'discovered')
                            ORDER BY CASE u.url_lifecycle WHEN 'validated' THEN 0 WHEN 'configured_official' THEN 1 ELSE 2 END,
                                     u.selected_primary DESC, u.updated_at DESC
                            LIMIT 1),
                           c.provenance_url
                       ) AS provenance_url,
                       p.profile_json, p.logo_object_key, p.logo_source_url,
                       p.logo_content_hash, p.logo_content_type, p.logo_verified_at,
                       ? AS attempt_id, ? AS cycle_key
                FROM canonical_companies c
                LEFT JOIN canonical_company_profiles p ON p.company_id = c.company_id
                WHERE c.company_id=?
                """,
                (attempt_id, cycle_key, company_id),
            ).fetchone()
        return _row_payload(row) if row is not None else None

    def finish_company_enrichment_attempt(
        self,
        attempt_id: str,
        *,
        status: str,
        request_count: int,
        cost_units: float,
        fields_available: int,
        fields_written: int,
        logo_cached: bool,
        yield_payload: Mapping[str, Any] | None = None,
        error_code: str = "",
        error_message: str = "",
        next_attempt_at: str = "",
        now: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE company_enrichment_attempts
                SET status=?, request_count=?, cost_units=?, fields_available=?, fields_written=?,
                    logo_cached=?, yield_json=?, error_code=?, error_message=?, finished_at=?
                WHERE attempt_id=?
                """,
                (
                    str(status), max(0, int(request_count)), max(0.0, float(cost_units)),
                    max(0, int(fields_available)), max(0, int(fields_written)), int(bool(logo_cached)),
                    _json(dict(yield_payload or {})), str(error_code or ""), str(error_message or "")[:1000],
                    str(now), str(attempt_id),
                ),
            )
            attempt = connection.execute(
                "SELECT company_id FROM company_enrichment_attempts WHERE attempt_id=?",
                (str(attempt_id),),
            ).fetchone()
            if attempt is None:
                raise KeyError(f"Company enrichment attempt '{attempt_id}' not found.")
            connection.execute(
                """
                UPDATE company_enrichment_targets
                SET status=?, lease_owner='', lease_expires_at='',
                    last_success_at=CASE WHEN ?='succeeded' THEN ? ELSE last_success_at END,
                    next_attempt_at=?, last_error=?, updated_at=?
                WHERE company_id=?
                """,
                (
                    "ready" if str(status) == "succeeded" else "failed",
                    str(status), str(now), str(next_attempt_at or ""),
                    str(error_message or "")[:1000], str(now), str(attempt["company_id"]),
                ),
            )
            row = connection.execute(
                "SELECT * FROM company_enrichment_attempts WHERE attempt_id=?",
                (str(attempt_id),),
            ).fetchone()
        return _row_payload(row) if row is not None else {}

    def list_company_enrichment_attempts(self, *, company_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT * FROM company_enrichment_attempts"
        params: list[Any] = []
        if str(company_id or "").strip():
            sql += " WHERE company_id=?"
            params.append(str(company_id).strip())
        sql += " ORDER BY started_at DESC, attempt_id DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self._connect() as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()
        return [_row_payload(row) for row in rows]

    def list_published_job_rows(self) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        with self._connect() as connection:
            publication = connection.execute(
                """
                SELECT p.publication_id, p.cycle_id, p.status, p.published_at, p.valid_until
                FROM acquisition_publications p
                JOIN acquisition_publication_head h ON h.publication_id = p.publication_id
                WHERE h.head_id = 1 AND p.status = 'valid'
                LIMIT 1
                """
            ).fetchone()
            if publication is None:
                return None, []
            rows = connection.execute(self._published_jobs_sql(), (str(publication["publication_id"]),)).fetchall()
        return _row_payload(publication), [_row_payload(row) for row in rows]

    def get_current_publication(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT p.publication_id, p.cycle_id, p.status, p.published_at, p.valid_until
                FROM acquisition_publications p
                JOIN acquisition_publication_head h ON h.publication_id = p.publication_id
                WHERE h.head_id = 1 AND p.status = 'valid' LIMIT 1
                """
            ).fetchone()
        return _row_payload(row) if row is not None else None

    def search_published_companies(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        term = str(query or "").strip().casefold()[:100]
        if not term:
            return []
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT c.company_id, c.canonical_name AS name, p.logo_object_key AS company_logo_object_key "
                "FROM canonical_companies c LEFT JOIN canonical_company_profiles p ON p.company_id=c.company_id "
                "WHERE c.entity_kind='employer' AND lower(c.canonical_name) LIKE ? ESCAPE '\\' "
                "AND EXISTS (SELECT 1 FROM canonical_jobs j "
                "JOIN acquisition_publication_jobs pj ON pj.canonical_job_id=j.canonical_job_id "
                "JOIN acquisition_publication_head h ON h.publication_id=pj.publication_id AND h.head_id=1 "
                "JOIN acquisition_publications pub ON pub.publication_id=h.publication_id AND pub.status='valid' "
                "WHERE j.company_id=c.company_id) "
                "ORDER BY CASE WHEN lower(c.canonical_name)=? THEN 0 "
                "WHEN lower(c.canonical_name) LIKE ? ESCAPE '\\' THEN 1 ELSE 2 END, c.canonical_name, c.company_id LIMIT ?",
                (f"%{escaped}%", term, f"{escaped}%", max(1, min(20, int(limit)))),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _feed_filter_sql(filters: Mapping[str, Any] | None) -> tuple[list[str], list[Any]]:
        filters = dict(filters or {})
        predicates: list[str] = []
        params: list[Any] = []
        search_terms = filters.get("search_text") or []
        for term in (search_terms if isinstance(search_terms, (list, tuple, set)) else [search_terms]):
            predicates.append("(LOWER(catalog.title) LIKE ? OR LOWER(catalog.company) LIKE ?)")
            params.extend((f"%{str(term).casefold()}%",) * 2)

        field_exprs = {
            "role": ["json_extract(catalog.filter_json, '$.role')", "catalog.title", "json_extract(catalog.version_payload_json, '$.role')", "json_extract(catalog.version_payload_json, '$.roles')", "json_extract(catalog.version_payload_json, '$.role_category')", "json_extract(catalog.version_payload_json, '$.job_category')", "json_extract(catalog.version_payload_json, '$.function')"],
            "category": ["json_extract(catalog.version_payload_json, '$.category')", "json_extract(catalog.version_payload_json, '$.categories')", "json_extract(catalog.version_payload_json, '$.job_category')", "json_extract(catalog.version_payload_json, '$.role_category')", "json_extract(catalog.version_payload_json, '$.function')"],
            "location": ["catalog.location", "catalog.version_location", "json_extract(catalog.version_payload_json, '$.location')"],
            "work_arrangement": ["json_extract(catalog.filter_json, '$.work_arrangement')", "json_extract(catalog.version_payload_json, '$.work_arrangement')", "json_extract(catalog.version_payload_json, '$.workplace')", "json_extract(catalog.version_payload_json, '$.workplace_type')", "json_extract(catalog.version_payload_json, '$.remote_type')"],
            "employment_type": ["json_extract(catalog.filter_json, '$.employment_type')", "json_extract(catalog.version_payload_json, '$.employment_type')", "json_extract(catalog.version_payload_json, '$.job_type')", "json_extract(catalog.version_payload_json, '$.type')"],
            "experience_level": ["json_extract(catalog.filter_json, '$.experience_level')", "json_extract(catalog.version_payload_json, '$.experience_level')", "json_extract(catalog.version_payload_json, '$.seniority')", "json_extract(catalog.version_payload_json, '$.level')"],
            "language": ["json_extract(catalog.version_payload_json, '$.languages')", "json_extract(catalog.version_payload_json, '$.language_requirements')", "json_extract(catalog.version_payload_json, '$.required_languages')"],
            "work_authorization": ["json_extract(catalog.version_payload_json, '$.work_authorization')", "json_extract(catalog.version_payload_json, '$.authorization')", "json_extract(catalog.version_payload_json, '$.work_permit')"],
            "sponsorship": ["json_extract(catalog.version_payload_json, '$.sponsorship')", "json_extract(catalog.version_payload_json, '$.visa_sponsorship')", "json_extract(catalog.version_payload_json, '$.sponsors_h1b')"],
            "company_stage": ["json_extract(catalog.version_payload_json, '$.company_stage')"],
            "education": ["json_extract(catalog.version_payload_json, '$.education')", "json_extract(catalog.version_payload_json, '$.education_level')", "json_extract(catalog.version_payload_json, '$.degree')", "json_extract(catalog.version_payload_json, '$.required_education')"],
            "preferred_major": ["json_extract(catalog.version_payload_json, '$.preferred_major')", "json_extract(catalog.version_payload_json, '$.preferred_majors')", "json_extract(catalog.version_payload_json, '$.major')", "json_extract(catalog.version_payload_json, '$.majors')"],
            "security_clearance": ["json_extract(catalog.version_payload_json, '$.security_clearance')", "json_extract(catalog.version_payload_json, '$.clearance')"],
            "lifting_requirement": ["json_extract(catalog.version_payload_json, '$.lifting_requirement')", "json_extract(catalog.version_payload_json, '$.physical_requirement')", "json_extract(catalog.version_payload_json, '$.lifting')"],
            "industry": ["json_extract(catalog.company_profile_json, '$.fields.industry.value')", "json_extract(catalog.version_payload_json, '$.industry')", "json_extract(catalog.version_payload_json, '$.company_industry')"],
            "company_size": ["json_extract(catalog.company_profile_json, '$.fields.company_size.value')", "json_extract(catalog.version_payload_json, '$.company_size')", "json_extract(catalog.version_payload_json, '$.size')"],
            "funding_stage": ["json_extract(catalog.company_profile_json, '$.fields.funding_stage.value')", "json_extract(catalog.version_payload_json, '$.funding_stage')"],
            "country": ["json_extract(catalog.version_payload_json, '$.country')", "json_extract(catalog.version_payload_json, '$.country_code')", "catalog.location"],
            "role_type": ["json_extract(catalog.filter_json, '$.role_type')", "json_extract(catalog.version_payload_json, '$.role_type')", "json_extract(catalog.version_payload_json, '$.management_role')"],
        }
        for field, requested in filters.items():
            values = [str(item).strip().casefold() for item in (requested if isinstance(requested, (list, tuple, set)) else [requested]) if str(item).strip()]
            if not values or field in {"include_hidden", "use_saved_search", "hidden_companies", "sort", "search_text"}:
                continue
            if field == "company":
                predicates.append("LOWER(catalog.company) IN (" + ",".join("?" for _ in values) + ")")
                params.extend(values)
            elif field == "role":
                clauses = []
                for value in values:
                    clauses.append("(EXISTS(SELECT 1 FROM json_each(catalog.filter_json, '$.roles') role WHERE LOWER(role.value) = ?) OR (json_type(catalog.filter_json, '$.roles') IS NULL AND (LOWER(COALESCE(json_extract(catalog.filter_json, '$.role'), '')) = ? OR LOWER(catalog.title) LIKE ? OR LOWER(COALESCE(json_extract(catalog.version_payload_json, '$.role'), json_extract(catalog.version_payload_json, '$.function'), '')) = ? OR EXISTS(SELECT 1 FROM json_each(catalog.version_payload_json, '$.roles') legacy_role WHERE LOWER(legacy_role.value) = ?))))")
                    params.extend((value, value, f"%{value}%", value, value))
                predicates.append("(" + " OR ".join(clauses) + ")")
            elif field == "skills_include":
                legacy = ["$.skills", "$.required_skills", "$.structured_description.skills"]
                clauses = []
                for value in values:
                    clauses.append("(EXISTS(SELECT 1 FROM json_each(catalog.filter_json, '$.skills') skill "
                                   "WHERE LOWER(skill.value) = ?) OR "
                                   + " OR ".join("LOWER(COALESCE(json_extract(catalog.version_payload_json, '"
                                                 + path + "'), '')) LIKE ?" for path in legacy) + ")")
                    params.extend([value, *(f"%{value}%" for _ in legacy)])
                predicates.append("(" + " OR ".join(clauses) + ")")
            elif field in {"work_arrangement", "employment_type", "experience_level", "role_type"}:
                source_fields = field_exprs[field][1:]
                candidates = [f"NULLIF(NULLIF(LOWER(CAST({expr} AS TEXT)), 'unknown'), '')" for expr in source_fields]
                candidates.append(field_exprs[field][0])
                selected = "LOWER(REPLACE(REPLACE(COALESCE(" + ",".join(candidates) + ",''),'-','_'),' ','_'))"
                synonyms = {"employment_type": {"vollzeit":"full_time", "teilzeit":"part_time", "praktikum":"internship", "werkstudent":"working_student"},
                            "work_arrangement": {"vor_ort":"onsite", "on_site":"onsite", "in_person":"onsite", "präsenz":"onsite"},
                            "experience_level": {"junior":"entry", "entry_level":"entry", "mid_level":"mid", "senior_level":"senior", "executive":"director"},
                            "role_type": {"individual_contributor":"ic", "people_manager":"manager"}}
                if field in synonyms:
                    selected = "CASE " + selected + " " + " ".join(f"WHEN '{original}' THEN '{mapped}'" for original,mapped in synonyms[field].items()) + " ELSE " + selected + " END"
                predicates.append("(" + " OR ".join(f"{selected} LIKE ?" for _ in values) + ")")
                params.extend(f"%{value.replace('-', '_').replace(' ', '_')}%" for value in values)
            elif field == "company_id":
                predicates.append("catalog.company_id IN (" + ",".join("?" for _ in values) + ")")
                params.extend(str(item).strip() for item in (requested if isinstance(requested, (list, tuple, set)) else [requested]) if str(item).strip())
            elif field in field_exprs:
                expressions = [f"LOWER(COALESCE({expr}, ''))" for expr in field_exprs[field]]
                predicates.append("(" + " OR ".join(" OR ".join(f"{expr} LIKE ?" for expr in expressions) for _ in values) + ")")
                params.extend(f"%{value.replace('-', ' ')}%" for value in values for _ in expressions)
            elif field in {"excluded_title", "excluded_industry", "skills_exclude"}:
                expressions = {
                    "excluded_title": ["catalog.title"],
                    "excluded_industry": ["json_extract(catalog.company_profile_json, '$.fields.industry.value')", "json_extract(catalog.version_payload_json, '$.industry')"],
                    "skills_exclude": ["json_extract(catalog.version_payload_json, '$.skills')", "json_extract(catalog.version_payload_json, '$.required_skills')", "json_extract(catalog.version_payload_json, '$.structured_description.skills')"],
                }[field]
                for value in values:
                    if field == "skills_exclude":
                        predicates.append("NOT EXISTS(SELECT 1 FROM json_each(catalog.filter_json, '$.skills') skill "
                                          "WHERE LOWER(skill.value) = ?)")
                        params.append(value)
                    for expr in expressions:
                        predicates.append(f"LOWER(COALESCE({expr}, '')) NOT LIKE ?")
                        params.append(f"%{value}%")
            elif field in {"required_experience_min", "required_experience_max"}:
                paths = ("$.experience_years_min", "$.structured_description.experience_years_min.value")
                amount = "COALESCE(" + ", ".join(f"CASE WHEN json_type(catalog.version_payload_json, '{path}') IN ('integer','real') THEN CAST(json_extract(catalog.version_payload_json, '{path}') AS REAL) END" for path in paths) + ", CASE WHEN json_type(catalog.filter_json, '$.required_experience_years') IN ('integer','real') THEN CAST(json_extract(catalog.filter_json, '$.required_experience_years') AS REAL) END)"
                operator = ">=" if field.endswith("_min") else "<="
                predicates.append(f"{amount} {operator} ?")
                params.append(float(values[0]))
            elif field in {"h1b_sponsorship", "exclude_security_clearance", "exclude_citizenship_required", "exclude_staffing_agency"}:
                if values[0] not in {"true", "1", "yes", "on"}:
                    continue
                if field == "h1b_sponsorship":
                    predicates.append("LOWER(COALESCE(json_extract(catalog.version_payload_json, '$.h1b_sponsorship'), json_extract(catalog.version_payload_json, '$.visa_sponsorship'), '')) IN ('true', 'yes', 'available', '1')")
                elif field == "exclude_security_clearance":
                    predicates.append("LOWER(COALESCE(json_extract(catalog.version_payload_json, '$.security_clearance'), json_extract(catalog.version_payload_json, '$.structured_description.security_clearance.value'), '')) NOT IN ('true', 'yes', 'required', 'secret', 'top_secret', 'ts_sci')")
                elif field == "exclude_citizenship_required":
                    predicates.append("LOWER(COALESCE(json_extract(catalog.version_payload_json, '$.citizenship_required'), json_extract(catalog.version_payload_json, '$.structured_description.citizenship_required.value'), '')) NOT IN ('true', 'yes', 'required', '1')")
                else:
                    predicates.append("LOWER(COALESCE(json_extract(catalog.company_profile_json, '$.fields.company_type.value'), json_extract(catalog.version_payload_json, '$.company_type'), '')) NOT IN ('staffing_agency', 'staffing agency', 'recruiter', 'recruitment agency')")
            elif field in {"salary_min", "salary_max"}:
                path = "$.salary.max" if field == "salary_min" else "$.salary.min"
                operator = ">=" if field == "salary_min" else "<="
                predicates.append(f"CAST(json_extract(catalog.version_payload_json, '{path}') AS REAL) {operator} ?")
                params.append(float(values[0]))
            elif field in {"funding_min", "funding_max"}:
                operator = ">=" if field == "funding_min" else "<="
                predicates.append(f"CAST(json_extract(catalog.company_profile_json, '$.fields.total_funding.value') AS REAL) {operator} ?")
                params.append(float(values[0]))
            elif field in {"founded_year_min", "founded_year_max", "funding_year_min", "funding_year_max"}:
                source = "founded_year" if field.startswith("founded") else "funding_year"
                path = "$.fields.founded_year.value" if source == "founded_year" else "$.fields.funding_year.value"
                operator = ">=" if field.endswith("_min") else "<="
                predicates.append(f"CAST(json_extract(catalog.company_profile_json, '{path}') AS INTEGER) {operator} ?")
                params.append(int(float(values[0])))
            elif field == "posted_within_days":
                cutoff = datetime.now(timezone.utc) - timedelta(days=int(float(values[0])))
                predicates.append("COALESCE(json_extract(catalog.version_payload_json, '$.posted_at'), json_extract(catalog.version_payload_json, '$.published_at'), json_extract(catalog.version_payload_json, '$.date_posted')) >= ?")
                params.append(cutoff.isoformat())
        for company in filters.get("hidden_companies") or []:
            predicates.append("LOWER(catalog.company) NOT LIKE ?")
            params.append(f"%{str(company).casefold()}%")
        return [use_cached_source(predicate) for predicate in predicates], params

    def _feed_scope_sql(self, roles: list[str] | None = None) -> str:
        return f"""
            SELECT catalog.*, COALESCE(d.state, 'none') AS user_state,
                   COALESCE(d.updated_at, '') AS user_state_updated_at
            FROM ({self._scope_sql_to_roles(self._published_jobs_sql(), roles)}) AS catalog
            LEFT JOIN personalized_job_dispositions d
              ON d.canonical_job_id = catalog.canonical_job_id AND d.user_id = ?
        """

    @staticmethod
    def _scope_sql_to_roles(sql: str, roles: list[str] | None) -> str:
        if roles is None:
            return sql
        placeholders = ','.join('?' for _ in roles)
        return sql.replace(
            'FROM acquisition_publication_jobs pj\n            JOIN canonical_jobs j ON j.canonical_job_id = pj.canonical_job_id',
            f'''FROM (SELECT DISTINCT canonical_job_id, version_id, content_hash
                FROM job_filter_roles INDEXED BY idx_job_filter_roles_role
                WHERE role IN ({placeholders})) selected_roles
            CROSS JOIN canonical_jobs j ON j.canonical_job_id = selected_roles.canonical_job_id
                AND j.current_version_id = selected_roles.version_id
            JOIN acquisition_publication_jobs pj ON pj.canonical_job_id = j.canonical_job_id''',
        ) + ' AND v.content_hash = selected_roles.content_hash'

    @staticmethod
    def _feed_candidate_sql(roles: list[str] | None = None) -> str:
        """Return filter/sort inputs without hydrating expensive job history."""

        sql = """
            SELECT j.canonical_job_id, j.company_id, c.canonical_name AS company,
                   j.title, j.location, j.first_seen_at, j.last_verified_at,
                   j.current_version_id, v.description,
                   v.location AS version_location,
                   v.payload_json AS version_payload_json,
                   p.profile_json AS company_profile_json,
                   CASE WHEN fi.content_hash = v.content_hash THEN fi.filters_json ELSE NULL END AS filter_json,
                   COALESCE(d.state, 'none') AS user_state
            FROM acquisition_publication_jobs pj
            JOIN canonical_jobs j ON j.canonical_job_id = pj.canonical_job_id
            JOIN canonical_companies c ON c.company_id = j.company_id
            LEFT JOIN job_posting_versions v ON v.version_id = j.current_version_id
            LEFT JOIN canonical_company_profiles p ON p.company_id = c.company_id
            LEFT JOIN job_filter_intelligence fi ON fi.version_id = v.version_id
            LEFT JOIN personalized_job_dispositions d
              ON d.canonical_job_id = j.canonical_job_id AND d.user_id = ?
            WHERE pj.publication_id = ? AND c.entity_kind = 'employer'
              AND COALESCE(CASE WHEN fi.content_hash = v.content_hash THEN json_extract(fi.filters_json, '$.collar') END, '') != 'blue'
        """
        return SqlitePersonalizedJobsStore._scope_sql_to_roles(sql, roles)

    @staticmethod
    def _feed_index_sql() -> str:
        """Return only fields required by the unfiltered newest feed."""

        return """
            SELECT j.canonical_job_id, j.first_seen_at, j.last_verified_at,
                   COALESCE(d.state, 'none') AS user_state
            FROM acquisition_publication_jobs pj
            JOIN canonical_jobs j ON j.canonical_job_id = pj.canonical_job_id
            JOIN canonical_companies c ON c.company_id = j.company_id
            LEFT JOIN job_filter_intelligence fi ON fi.version_id = j.current_version_id
            LEFT JOIN personalized_job_dispositions d
              ON d.canonical_job_id = j.canonical_job_id AND d.user_id = ?
            WHERE pj.publication_id = ? AND c.entity_kind = 'employer'
              AND (
                  COALESCE(json_extract(fi.filters_json, '$.collar'), '') != 'blue'
                  OR NOT EXISTS (
                      SELECT 1 FROM job_posting_versions v
                      WHERE v.version_id=j.current_version_id AND v.content_hash=fi.content_hash
                  )
              )
        """

    @staticmethod
    def _filter_capability_jobs_sql() -> str:
        return """
            SELECT c.canonical_name AS company,
                   j.last_verified_at,
                   v.payload_json AS version_payload_json,
                   p.profile_json AS company_profile_json
            FROM acquisition_publication_jobs pj
            JOIN canonical_jobs j ON j.canonical_job_id = pj.canonical_job_id
            JOIN canonical_companies c ON c.company_id = j.company_id
            LEFT JOIN job_posting_versions v ON v.version_id = j.current_version_id
            LEFT JOIN job_filter_intelligence fi ON fi.version_id = v.version_id
            LEFT JOIN canonical_company_profiles p ON p.company_id = c.company_id
            WHERE pj.publication_id = ? AND c.entity_kind = 'employer'
              AND COALESCE(CASE WHEN fi.content_hash = v.content_hash THEN json_extract(fi.filters_json, '$.collar') END, '') != 'blue'
        """

    def _hydrate_feed_page(
        self,
        connection,
        *,
        publication_id: str,
        user_id: str,
        canonical_job_ids: list[str],
    ) -> list[Any]:
        if not canonical_job_ids:
            return []
        placeholders = ",".join("?" for _ in canonical_job_ids)
        sql = f"""
            /* feed_page_hydration */
            SELECT hydrated.*, COALESCE(d.state, 'none') AS user_state,
                   COALESCE(d.updated_at, '') AS user_state_updated_at,
                   (SELECT e.payload_json FROM personalized_job_evaluations e
                    WHERE e.user_id = ? AND e.canonical_job_id = hydrated.canonical_job_id
                      AND e.job_version_id = hydrated.current_version_id
                      AND e.evaluator_version = 'phase_e_v2'
                    ORDER BY e.updated_at DESC LIMIT 1) AS evaluation_payload,
                   0.0 AS priority_score, 2147483647 AS competition_score
            FROM ({self._published_jobs_sql(compact_payload=True)}
                  AND j.canonical_job_id IN ({placeholders})) AS hydrated
            LEFT JOIN personalized_job_dispositions d
              ON d.canonical_job_id = hydrated.canonical_job_id AND d.user_id = ?
        """
        rows = self._fetch_read_rows(
            connection,
            sql,
            (str(user_id), str(publication_id), *canonical_job_ids, str(user_id)),
        )
        order = {job_id: index for index, job_id in enumerate(canonical_job_ids)}
        return sorted(rows, key=lambda row: order[str(row["canonical_job_id"])])

    @staticmethod
    def _priority_sql() -> str:
        fit = "COALESCE(CAST(json_extract(page.evaluation_payload, '$.match_intelligence.v2.score') AS REAL), CAST(json_extract(page.evaluation_payload, '$.match_intelligence.score') AS REAL), 50.0)"
        observed = "COALESCE(NULLIF(page.applicant_latest_observed_at, ''), NULLIF(page.last_verified_at, ''), NULLIF(page.first_seen_at, ''))"
        freshness = (
            "CASE WHEN " + observed + " IS NULL THEN 50.0 "
            "WHEN (julianday('now') - julianday(" + observed + ")) <= 0 THEN 100.0 "
            "WHEN (julianday('now') - julianday(" + observed + ")) * 24 >= 240 THEN 0.0 "
            "ELSE MAX(0.0, 100.0 - (((julianday('now') - julianday(" + observed + ")) * 24) / 2.4)) END"
        )
        competition = (
            "CASE WHEN page.applicant_latest_freshness_status = 'stale' THEN 50.0 "
            "WHEN page.applicant_latest_exact IS NOT NULL AND page.applicant_latest_exact <= 25 THEN 90.0 "
            "WHEN page.applicant_latest_exact IS NOT NULL AND page.applicant_latest_exact <= 75 THEN 75.0 "
            "WHEN page.applicant_latest_exact IS NOT NULL AND page.applicant_latest_exact <= 150 THEN 55.0 "
            "WHEN page.applicant_latest_exact IS NOT NULL AND page.applicant_latest_exact <= 300 THEN 35.0 "
            "WHEN page.applicant_latest_exact IS NOT NULL THEN 15.0 "
            "WHEN page.applicant_latest_min IS NOT NULL AND page.applicant_latest_min <= 25 THEN 90.0 "
            "WHEN page.applicant_latest_min IS NOT NULL AND page.applicant_latest_min <= 75 THEN 75.0 "
            "WHEN page.applicant_latest_min IS NOT NULL AND page.applicant_latest_min <= 150 THEN 55.0 "
            "WHEN page.applicant_latest_min IS NOT NULL AND page.applicant_latest_min <= 300 THEN 35.0 "
            "WHEN page.applicant_latest_min IS NOT NULL THEN 15.0 ELSE 50.0 END"
        )
        return f"(({fit} * 0.60) + ({freshness} * 0.20) + ({competition} * 0.20))"

    def query_published_jobs(
        self,
        user_id: str,
        *,
        filters: Mapping[str, Any] | None = None,
        limit: int = 25,
        cursor: Mapping[str, Any] | None = None,
        include_hidden: bool = False,
        hidden_only: bool = False,
        role_scoped: bool = False,
        include_total: bool = True,
    ) -> dict[str, Any]:
        limit = max(1, min(100, int(limit)))
        roles = None
        if role_scoped and not (filters or {}).get("role") and not (filters or {}).get("company_id"):
            return {'publication': None, 'rows': [], 'total': None, 'selection_required': True}
        if role_scoped and (filters or {}).get("role"):
            requested = (filters or {}).get('role') or []
            roles = sorted({str(role).strip().casefold() for role in
                            (requested if isinstance(requested, (list, tuple, set)) else [requested])
                            if str(role).strip()})
            if not roles:
                return {'publication': None, 'rows': [], 'total': None, 'selection_required': True}
            filters = {key: value for key, value in (filters or {}).items() if key != 'role'}
        # Keep ambient transactions on their original connection; ordinary
        # remote feeds use only bounded HTTP reads and share one time budget.
        read_context = (
            database_read_session(self.db_path)
            if self._active_transaction_connection is None
            and database_target_info(self.db_path)["target_backend"] == "libsql"
            else self._connect()
        )
        with read_context as connection:
            publication = connection.execute(
                """
                SELECT p.publication_id, p.cycle_id, p.status, p.published_at, p.valid_until
                FROM acquisition_publications p
                JOIN acquisition_publication_head h ON h.publication_id = p.publication_id
                WHERE h.head_id = 1 AND p.status = 'valid' LIMIT 1
                """
            ).fetchone()
            if publication is None:
                return {"publication": None, "rows": [], "total": 0}
            publication_payload = _row_payload(publication)
            count_key = _json([str(publication['publication_id']), str(user_id), roles,
                               {k: v for k, v in (filters or {}).items() if k != 'sort'},
                               include_hidden, hidden_only])
            cached_total = self._cached_feed_count(count_key) if role_scoped else None
            compute_total = include_total and cached_total is None
            search_terms = (filters or {}).get("search_text") or []
            if isinstance(search_terms, str):
                search_terms = [search_terms]
            search_candidates: set[str] | None = None
            if search_terms and not role_scoped:
                for raw_term in search_terms:
                    term = str(raw_term).strip().casefold()
                    if not term:
                        continue
                    pattern = f"%{term}%"
                    matches: set[str] = set()
                    companies = connection.execute(
                        "SELECT company_id FROM canonical_companies WHERE entity_kind='employer' AND lower(canonical_name) LIKE ?",
                        (pattern,),
                    ).fetchall()
                    for company in companies:
                        matches.update(str(row["canonical_job_id"]) for row in connection.execute(
                            "SELECT canonical_job_id FROM canonical_jobs WHERE company_id=?", (company["company_id"],)
                        ).fetchall())
                    matches.update(str(row["canonical_job_id"]) for row in connection.execute(
                        "SELECT canonical_job_id FROM canonical_jobs WHERE lower(title) LIKE ?", (pattern,)
                    ).fetchall())
                    search_candidates = matches if search_candidates is None else search_candidates & matches
                if not search_candidates:
                    return {"publication": publication_payload, "rows": [], "total": 0, "sort_mode": "newest"}
                filters = {key: value for key, value in (filters or {}).items() if key != "search_text"}
            predicates, filter_params = self._feed_filter_sql(filters)
            # Filters are applied to the outer ``page`` alias.  Keep the
            # catalog-qualified expressions for the scoped subquery builder,
            # then bind them to the visible query alias here.
            predicates = [predicate.replace("catalog.", "page.") for predicate in predicates]
            if hidden_only:
                predicates.append("page.user_state = 'hidden'")
            elif not include_hidden:
                predicates.append("page.user_state != 'hidden'")
            sort_mode = str((filters or {}).get("sort") or "newest").casefold()
            if sort_mode not in {"newest", "least_competitive"}:
                sort_mode = "newest"
            sort_expr = "COALESCE(NULLIF(page.last_verified_at, ''), NULLIF(page.first_seen_at, ''), '')"
            if sort_mode == "newest":
                has_catalog_filters = any(
                    key != "sort" and value not in (None, "", [], (), set())
                    for key, value in dict(filters or {}).items()
                )
                candidate_source = (
                    self._feed_candidate_sql(roles) if has_catalog_filters or role_scoped else self._feed_index_sql()
                )
                if search_candidates is not None:
                    candidate_source = candidate_source + " AND j.canonical_job_id IN (" + ",".join("?" for _ in search_candidates) + ")"
                predicates = [f"({item})" for item in predicates]
                count_where_sql = " AND ".join(predicates) if predicates else "1=1"
                # Materialize only the matching IDs and sort keys once. Text
                # Keep the count and requested page on the same matched IDs.
                candidate_params = [*(roles or []), str(user_id), str(publication["publication_id"]), *sorted(search_candidates or ()), *filter_params]
                cursor_params: list[Any] = []
                if cursor:
                    cursor_sort = str(cursor.get("sort") or "")
                    cursor_params = [cursor_sort, cursor_sort, str(cursor.get("canonical_job_id") or "")]
                cursor_where = (
                    "WHERE (page.sort_at < ? OR (page.sort_at = ? AND page.canonical_job_id < ?))"
                    if cursor else ""
                )
                match_sort = "COALESCE(NULLIF(page.last_verified_at, ''), NULLIF(page.first_seen_at, ''), '')"
                page_result = self._fetch_read_rows(
                    connection,
                    f"""
                    /* feed_page_ids */
                    WITH matches AS MATERIALIZED (
                        SELECT page.canonical_job_id, {match_sort} AS sort_at
                        FROM ({candidate_source}) AS page WHERE {count_where_sql}
                    ),
                    page_ids AS (
                        SELECT page.canonical_job_id, page.sort_at FROM matches AS page
                        {cursor_where}
                        ORDER BY page.sort_at DESC, page.canonical_job_id DESC LIMIT ?
                    )
                    {('SELECT page_ids.canonical_job_id, totals.total FROM (SELECT COUNT(*) AS total FROM matches) totals LEFT JOIN page_ids ON 1=1' if compute_total else 'SELECT page_ids.canonical_job_id, NULL AS total FROM page_ids')}
                    """,
                    (*candidate_params, *cursor_params, limit + 1),
                )
                total = int(page_result[0]["total"] or 0) if compute_total else cached_total
                if role_scoped and compute_total:
                    self._remember_feed_count(count_key, total)
                rows = self._hydrate_feed_page(
                    connection,
                    publication_id=str(publication["publication_id"]),
                    user_id=str(user_id),
                    canonical_job_ids=[str(row["canonical_job_id"]) for row in page_result if row["canonical_job_id"] is not None],
                )
                return {
                    "publication": publication_payload,
                    "rows": [_row_payload(row) for row in rows],
                    "total": total,
                    "sort_mode": sort_mode,
                }
            page_source = f"""
                SELECT scoped.*,
                       (SELECT e.payload_json FROM personalized_job_evaluations e
                        WHERE e.user_id = ? AND e.canonical_job_id = scoped.canonical_job_id
                          AND e.job_version_id = scoped.current_version_id
                          AND e.evaluator_version = 'phase_e_v2'
                        ORDER BY e.updated_at DESC LIMIT 1) AS evaluation_payload
                FROM ({self._feed_scope_sql(roles)}) AS scoped
            """
            if sort_mode in {"priority", "best"}:
                source = f"SELECT page.*, {self._priority_sql()} AS priority_score FROM ({page_source}) AS page"
                order_sql = "priority_score DESC, " + sort_expr + " DESC, page.canonical_job_id DESC"
            elif sort_mode == "least_competitive":
                competition_expr = "COALESCE(page.applicant_latest_exact, page.applicant_latest_min, 2147483647)"
                source = f"SELECT page.*, 0.0 AS priority_score, {competition_expr} AS competition_score FROM ({page_source}) AS page"
                order_sql = "competition_score ASC, " + sort_expr + " DESC, page.canonical_job_id DESC"
            else:
                source = f"SELECT page.*, 0.0 AS priority_score, 2147483647 AS competition_score FROM ({page_source}) AS page"
                order_sql = sort_expr + " DESC, page.canonical_job_id DESC"
            predicates = [f"({item})" for item in predicates]
            count_where_sql = " AND ".join(predicates) if predicates else "1=1"
            count_filter_params = list(filter_params)
            if cursor:
                if sort_mode in {"priority", "best"}:
                    predicates.append("(page.priority_score < ? OR (page.priority_score = ? AND page.canonical_job_id < ?))")
                    filter_params.extend([float(cursor.get("priority") or 0), float(cursor.get("priority") or 0), str(cursor.get("canonical_job_id") or "")])
                elif sort_mode == "least_competitive":
                    predicates.append(f"(page.competition_score > ? OR (page.competition_score = ? AND ({sort_expr} < ? OR ({sort_expr} = ? AND page.canonical_job_id < ?))))")
                    competition = int(cursor.get("competition") or 2147483647)
                    cursor_sort = str(cursor.get("sort") or "")
                    filter_params.extend([competition, competition, cursor_sort, cursor_sort, str(cursor.get("canonical_job_id") or "")])
                else:
                    predicates.append(f"({sort_expr} < ? OR ({sort_expr} = ? AND page.canonical_job_id < ?))")
                    filter_params.extend([str(cursor.get("sort") or ""), str(cursor.get("sort") or ""), str(cursor.get("canonical_job_id") or "")])
            where_sql = " AND ".join(predicates) if predicates else "1=1"
            count_sql = f"SELECT COUNT(*) AS total FROM ({source}) AS page WHERE {count_where_sql}"
            count_params = [str(user_id), *(roles or []), str(publication["publication_id"]), str(user_id), *count_filter_params]
            total = int(connection.execute(count_sql, tuple(count_params)).fetchone()["total"] or 0) if compute_total else cached_total
            if role_scoped and compute_total:
                self._remember_feed_count(count_key, total)
            rows_sql = f"SELECT page.* FROM ({source}) AS page WHERE {where_sql} ORDER BY {order_sql} LIMIT ?"
            rows_params = [str(user_id), *(roles or []), str(publication["publication_id"]), str(user_id), *filter_params, limit + 1]
            rows = connection.execute(rows_sql, tuple(rows_params)).fetchall()
        return {
            "publication": publication_payload,
            "rows": [_row_payload(row) for row in rows],
            "total": total,
            "sort_mode": sort_mode,
        }

    def list_hidden_published_jobs(self, user_id: str, *, limit: int = 25, cursor: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self.query_published_jobs(user_id, limit=limit, cursor=cursor, hidden_only=True, include_hidden=True)

    def get_published_company_page(self, company_id: str, user_id: str, *, limit: int = 25) -> dict[str, Any]:
        limit = max(1, min(50, int(limit)))
        with self._connect() as connection:
            publication_id = self._head_publication_id(connection)
            if not publication_id:
                return {"company": None, "rows": [], "total": 0}
            company = connection.execute(
                """
                SELECT c.*, p.profile_json AS company_profile_json,
                       p.logo_object_key, p.logo_source_url, p.logo_content_hash,
                       p.logo_content_type, p.logo_verified_at, p.updated_at AS profile_updated_at
                FROM canonical_companies c
                LEFT JOIN canonical_company_profiles p ON p.company_id = c.company_id
                WHERE c.company_id = ?
                """,
                (str(company_id),),
            ).fetchone()
            if company is None:
                return {"company": None, "rows": [], "total": 0}
            base = self._published_jobs_sql()
            scope = f"""
                SELECT catalog.*, COALESCE(d.state, 'none') AS user_state
                FROM ({base}) AS catalog
                LEFT JOIN personalized_job_dispositions d
                  ON d.canonical_job_id = catalog.canonical_job_id AND d.user_id = ?
                WHERE catalog.company_id = ? AND COALESCE(d.state, 'none') != 'hidden'
            """
            total = int(connection.execute(f"SELECT COUNT(*) AS total FROM ({scope})", (publication_id, user_id, company_id)).fetchone()["total"] or 0)
            rows = connection.execute(
                f"SELECT * FROM ({scope}) ORDER BY title, canonical_job_id LIMIT ?",
                (publication_id, user_id, company_id, limit + 1),
            ).fetchall()
        return {"company": _row_payload(company), "rows": [_row_payload(row) for row in rows], "total": total}

    def get_published_filter_capabilities(self, *, query_support_only: bool = False) -> dict[str, bool]:
        capability_exprs = {
            "salary": "json_extract(catalog.version_payload_json, '$.salary') IS NOT NULL",
            "language": "json_extract(catalog.version_payload_json, '$.languages') IS NOT NULL OR json_extract(catalog.version_payload_json, '$.language_requirements') IS NOT NULL",
            "work_authorization": "json_extract(catalog.version_payload_json, '$.work_authorization') IS NOT NULL",
            "sponsorship": "json_extract(catalog.version_payload_json, '$.sponsorship') IS NOT NULL",
            "industry": "json_extract(catalog.company_profile_json, '$.fields.industry.value') IS NOT NULL OR json_extract(catalog.version_payload_json, '$.industry') IS NOT NULL",
            "company_size": "json_extract(catalog.company_profile_json, '$.fields.company_size.value') IS NOT NULL OR json_extract(catalog.version_payload_json, '$.company_size') IS NOT NULL",
            "company_stage": "json_extract(catalog.version_payload_json, '$.company_stage') IS NOT NULL",
            "funding_stage": "json_extract(catalog.company_profile_json, '$.fields.funding_stage.value') IS NOT NULL OR json_extract(catalog.version_payload_json, '$.funding_stage') IS NOT NULL",
            "funding_range": "json_extract(catalog.company_profile_json, '$.fields.total_funding.value') IS NOT NULL",
            "founded_year": "json_extract(catalog.company_profile_json, '$.fields.founded_year.value') IS NOT NULL",
            "funding_year": "json_extract(catalog.company_profile_json, '$.fields.funding_year.value') IS NOT NULL",
            "education": "json_extract(catalog.version_payload_json, '$.education') IS NOT NULL",
            "preferred_major": "json_extract(catalog.version_payload_json, '$.preferred_major') IS NOT NULL",
            "security_clearance": "json_extract(catalog.version_payload_json, '$.security_clearance') IS NOT NULL",
            "lifting_requirement": "json_extract(catalog.version_payload_json, '$.lifting_requirement') IS NOT NULL",
            "posting_recency": "COALESCE(catalog.last_verified_at, '') != ''",
            "hidden_companies": "COALESCE(catalog.company, '') != ''",
        }
        if query_support_only:
            return {key: True for key in capability_exprs}
        with self._connect() as connection:
            head = connection.execute(
                "SELECT h.publication_id, h.updated_at FROM acquisition_publication_head h "
                "JOIN acquisition_publications p ON p.publication_id=h.publication_id "
                "WHERE h.head_id=1 AND p.status='valid'"
            ).fetchone()
            if head is None:
                return {key: False for key in capability_exprs}
            publication_id = str(head["publication_id"])
            cache_key = f"{publication_id}:{head['updated_at']}"
            cached = self._filter_capabilities_cache.get(cache_key)
            if cached is not None:
                return dict(cached)
            catalog_size = int(
                connection.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM acquisition_publication_jobs pj
                    JOIN canonical_jobs j ON j.canonical_job_id = pj.canonical_job_id
                    JOIN canonical_companies c ON c.company_id = j.company_id
                    WHERE pj.publication_id = ? AND c.entity_kind = 'employer'
                    """,
                    (publication_id,),
                ).fetchone()["total"]
                or 0
            )
            if catalog_size > self._DYNAMIC_CAPABILITY_SCAN_LIMIT:
                capabilities = {key: True for key in capability_exprs}
                self._cache_filter_capabilities(cache_key, capabilities)
                return dict(capabilities)
            capability_source = self._filter_capability_jobs_sql()
            result = connection.execute(
                "/* filter_capability_probe */ SELECT "
                + ", ".join(
                    f"EXISTS(SELECT 1 FROM ({capability_source}) AS catalog WHERE {expr} LIMIT 1) AS {key}"
                    for key, expr in capability_exprs.items()
                ),
                tuple(publication_id for _ in capability_exprs),
            ).fetchone()
        capabilities = {key: bool(int(result[key] or 0)) for key in capability_exprs}
        self._cache_filter_capabilities(cache_key, capabilities)
        return dict(capabilities)

    def _cache_filter_capabilities(self, cache_key: str, capabilities: Mapping[str, bool]) -> None:
        cache = self._filter_capabilities_cache
        while len(cache) >= self._FILTER_CAPABILITIES_CACHE_LIMIT:
            oldest_key = next(iter(cache))
            cache.pop(oldest_key, None)
        cache[cache_key] = dict(capabilities)

    def get_published_job_row(self, canonical_job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                self._published_jobs_sql() + " AND j.canonical_job_id = ? LIMIT 1",
                (str(self._head_publication_id(connection) or ""), str(canonical_job_id)),
            ).fetchone()
        return _row_payload(row) if row is not None else None

    def get_published_company_rows(self, company_id: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        with self._connect() as connection:
            publication_id = self._head_publication_id(connection)
            if not publication_id:
                return None, []
            company = connection.execute(
                """
                SELECT c.*, p.profile_json AS company_profile_json,
                       p.logo_object_key, p.logo_source_url, p.logo_content_hash,
                       p.logo_content_type, p.logo_verified_at, p.updated_at AS profile_updated_at
                FROM canonical_companies c
                LEFT JOIN canonical_company_profiles p ON p.company_id = c.company_id
                WHERE c.company_id = ?
                """,
                (str(company_id),),
            ).fetchone()
            if company is None:
                return None, []
            rows = connection.execute(
                self._published_jobs_sql() + " AND j.company_id = ? ORDER BY j.title, j.canonical_job_id",
                (str(publication_id), str(company_id)),
            ).fetchall()
        return _row_payload(company), [_row_payload(row) for row in rows]

    @staticmethod
    def _head_publication_id(connection) -> str:
        row = connection.execute(
            """
            SELECT p.publication_id
            FROM acquisition_publications p
            JOIN acquisition_publication_head h ON h.publication_id = p.publication_id
            WHERE h.head_id = 1 AND p.status = 'valid'
            LIMIT 1
            """
        ).fetchone()
        return str(row["publication_id"] or "") if row is not None else ""

    @staticmethod
    def _published_jobs_sql(*, compact_payload: bool = False) -> str:
        sql = """
            SELECT
                j.canonical_job_id, j.company_id, c.canonical_name AS company,
                c.entity_kind AS company_entity_kind, c.provenance_url AS company_provenance_url,
                p.profile_json AS company_profile_json,
                CASE WHEN fi.content_hash = v.content_hash THEN fi.filters_json ELSE NULL END AS filter_json,
                p.logo_object_key AS company_logo_object_key,
                p.logo_source_url AS company_logo_source_url,
                p.logo_content_type AS company_logo_content_type,
                p.logo_verified_at AS company_logo_verified_at,
                j.identity_key, j.title, j.location, j.canonical_url,
                j.lifecycle_state, j.first_seen_at, j.last_seen_at,
                j.last_verified_at, j.absence_count, j.current_version_id,
                v.version_number, v.content_hash, v.created_at AS version_created_at,
                v.description, v.location AS version_location,
                v.apply_url, v.source_observation_id, v.payload_json AS version_payload_json,
                (
                    SELECT o.external_job_id FROM job_source_observations o
                    WHERE o.canonical_job_id = j.canonical_job_id
                    ORDER BY o.observed_at DESC, o.observation_id DESC LIMIT 1
                ) AS source_job_id,
                (
                    SELECT o.source_ats FROM job_source_observations o
                    WHERE o.canonical_job_id = j.canonical_job_id
                    ORDER BY o.observed_at DESC LIMIT 1
                ) AS source_ats,
                (
                    SELECT o.original_url FROM job_source_observations o
                    WHERE o.canonical_job_id = j.canonical_job_id
                    ORDER BY o.observed_at DESC LIMIT 1
                ) AS observation_url,
                (
                    SELECT o.observed_at FROM job_source_observations o
                    WHERE o.observation_id = v.source_observation_id
                    LIMIT 1
                ) AS observation_observed_at,
                aps.source_ats AS applicant_latest_source_ats,
                aps.applicant_count_exact AS applicant_latest_exact,
                aps.applicant_count_min AS applicant_latest_min,
                aps.applicant_count_max AS applicant_latest_max,
                aps.applicant_count_label AS applicant_latest_label,
                aps.posting_time AS applicant_latest_posting_time,
                aps.first_seen_at AS applicant_latest_first_seen_at,
                aps.last_verified_at AS applicant_latest_last_verified_at,
                aps.observed_at AS applicant_latest_observed_at,
                aps.apply_method AS applicant_latest_apply_method,
                aps.easy_apply_marker AS applicant_latest_easy_apply_marker,
                 aps.freshness_status AS applicant_latest_freshness_status,
                 aps.provenance_url AS applicant_latest_provenance_url,
                 aps.apply_url AS applicant_latest_apply_url,
                 aps.source_provenance AS applicant_latest_source_provenance,
                (
                    SELECT COUNT(*) FROM job_applicant_snapshots s
                    WHERE s.canonical_job_id = j.canonical_job_id
                ) AS applicant_snapshot_count,
                (
                    SELECT s.applicant_count_exact FROM job_applicant_snapshots s
                    WHERE s.canonical_job_id = j.canonical_job_id
                    ORDER BY s.observed_at ASC, s.snapshot_id ASC LIMIT 1
                ) AS applicant_first_exact,
                (
                    SELECT s.applicant_count_min FROM job_applicant_snapshots s
                    WHERE s.canonical_job_id = j.canonical_job_id
                    ORDER BY s.observed_at ASC, s.snapshot_id ASC LIMIT 1
                ) AS applicant_first_min,
                (
                    SELECT s.applicant_count_max FROM job_applicant_snapshots s
                    WHERE s.canonical_job_id = j.canonical_job_id
                    ORDER BY s.observed_at ASC, s.snapshot_id ASC LIMIT 1
                ) AS applicant_first_max,
                (
                    SELECT s.applicant_count_label FROM job_applicant_snapshots s
                    WHERE s.canonical_job_id = j.canonical_job_id
                    ORDER BY s.observed_at ASC, s.snapshot_id ASC LIMIT 1
                ) AS applicant_first_label,
                (
                    SELECT s.observed_at FROM job_applicant_snapshots s
                    WHERE s.canonical_job_id = j.canonical_job_id
                    ORDER BY s.observed_at ASC, s.snapshot_id ASC LIMIT 1
                ) AS applicant_first_observed_at
            FROM acquisition_publication_jobs pj
            JOIN canonical_jobs j ON j.canonical_job_id = pj.canonical_job_id
            JOIN canonical_companies c ON c.company_id = j.company_id
            LEFT JOIN canonical_company_profiles p ON p.company_id = c.company_id
            LEFT JOIN job_posting_versions v ON v.version_id = j.current_version_id
            LEFT JOIN job_filter_intelligence fi ON fi.version_id = v.version_id
            LEFT JOIN job_applicant_snapshots aps
              ON aps.snapshot_id = (
                  SELECT latest.snapshot_id
                  FROM job_applicant_snapshots latest
                  WHERE latest.canonical_job_id = j.canonical_job_id
                  ORDER BY latest.observed_at DESC, latest.snapshot_id DESC
                  LIMIT 1
              )
            WHERE pj.publication_id = ?
              AND c.entity_kind = 'employer'
              AND COALESCE(CASE WHEN fi.content_hash = v.content_hash THEN json_extract(fi.filters_json, '$.collar') END, '') != 'blue'
        """
        if compact_payload:
            # Acquisition audit data stays in the immutable posting version.
            # Feed projections consume public job fields, not this history.
            sql = sql.replace(
                "v.payload_json AS version_payload_json",
                "json_remove(v.payload_json, '$.source_raw_payload', '$.unified_mapping', "
                "'$.field_provenance', '$.normalized_source_metadata', '$.content_fingerprint') "
                "AS version_payload_json",
            )
        return sql

    def enqueue_customer_task(
        self,
        *,
        user_id: str,
        task_type: str,
        idempotency_key: str,
        payload: Mapping[str, Any],
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        user_id = str(user_id or "").strip()
        task_type = str(task_type or "").strip()
        idempotency_key = str(idempotency_key or "").strip()
        if not user_id or not task_type or not idempotency_key:
            raise ValueError("user_id, task_type, and idempotency_key are required")
        now = utc_now_iso()
        bounded_attempts = max(1, min(5, int(max_attempts or 3)))

        def write(connection):
            existing = connection.execute(
                "SELECT * FROM customer_tasks WHERE user_id = ? AND idempotency_key = ?",
                (user_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                return _customer_task_payload(existing)
            task_id = f"customer_task_{uuid4().hex}"
            connection.execute(
                """
                INSERT INTO customer_tasks (
                    task_id, user_id, task_type, idempotency_key, state, payload_json,
                    attempt_count, max_attempts, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'queued', ?, 0, ?, ?, ?)
                """,
                (task_id, user_id, task_type, idempotency_key, _json(dict(payload)), bounded_attempts, now, now),
            )
            return _customer_task_payload(
                connection.execute("SELECT * FROM customer_tasks WHERE task_id = ?", (task_id,)).fetchone()
            )

        return self._run_transaction(write)

    def get_customer_task(self, task_id: str, *, user_id: str = "") -> dict[str, Any] | None:
        predicates = ["task_id = ?"]
        params: list[Any] = [str(task_id or "").strip()]
        if str(user_id or "").strip():
            predicates.append("user_id = ?")
            params.append(str(user_id).strip())
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM customer_tasks WHERE {' AND '.join(predicates)}",
                tuple(params),
            ).fetchone()
        return _customer_task_payload(row) if row is not None else None

    def recover_stale_customer_tasks(self, *, now: str = "", max_attempts: int = 3) -> list[dict[str, Any]]:
        now = str(now or utc_now_iso())
        bounded_attempts = max(1, min(5, int(max_attempts or 3)))

        def recover(connection):
            stale_rows = connection.execute(
                """
                SELECT task_id FROM customer_tasks
                WHERE state = 'running' AND lease_expires_at != '' AND lease_expires_at <= ?
                ORDER BY created_at, task_id
                """,
                (now,),
            ).fetchall()
            for row in stale_rows:
                current = connection.execute(
                    "SELECT attempt_count, max_attempts FROM customer_tasks WHERE task_id = ?",
                    (str(row["task_id"]),),
                ).fetchone()
                if current is None:
                    continue
                terminal = int(current["attempt_count"] or 0) >= min(
                    int(current["max_attempts"] or bounded_attempts), bounded_attempts
                )
                if terminal:
                    connection.execute(
                        """
                        UPDATE customer_tasks SET state = 'failed', error_code = 'lease_expired',
                               error_message = 'Customer task lease expired after the retry limit.',
                               lease_owner = '', lease_token = '', lease_expires_at = '',
                               completed_at = ?, updated_at = ?
                        WHERE task_id = ? AND state = 'running'
                        """,
                        (now, now, str(row["task_id"])),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE customer_tasks SET state = 'queued', error_code = 'lease_expired',
                               error_message = 'Customer task lease expired and was requeued.',
                               lease_owner = '', lease_token = '', lease_expires_at = '', updated_at = ?
                        WHERE task_id = ? AND state = 'running'
                        """,
                        (now, str(row["task_id"])),
                    )
            return [
                _customer_task_payload(item)
                for item in connection.execute(
                    "SELECT * FROM customer_tasks WHERE task_id IN ({}) ORDER BY created_at, task_id".format(
                        ",".join("?" for _ in stale_rows)
                    ),
                    tuple(str(row["task_id"]) for row in stale_rows),
                ).fetchall()
            ] if stale_rows else []

        return self._run_transaction(recover)

    def claim_next_customer_task(
        self,
        *,
        worker_role: str = "customer",
        lease_owner: str = "runr-worker",
        lease_seconds: int = 300,
        max_attempts: int = 3,
    ) -> dict[str, Any] | None:
        if str(worker_role or "").casefold() != "customer":
            return None
        now = utc_now_iso()
        lease_expires_at = utc_plus_seconds(max(1, int(lease_seconds or 300)))
        bounded_attempts = max(1, min(5, int(max_attempts or 3)))

        def claim(connection):
            row = connection.execute(
                """
                SELECT * FROM customer_tasks
                WHERE state = 'queued' AND attempt_count < MIN(max_attempts, ?)
                ORDER BY created_at, task_id LIMIT 1
                """,
                (bounded_attempts,),
            ).fetchone()
            if row is None:
                return None
            task_id = str(row["task_id"])
            lease_token = uuid4().hex
            connection.execute(
                """
                UPDATE customer_tasks SET state = 'running', attempt_count = attempt_count + 1,
                    lease_owner = ?, lease_token = ?, lease_expires_at = ?,
                    started_at = CASE WHEN started_at = '' THEN ? ELSE started_at END,
                    updated_at = ?
                WHERE task_id = ? AND state = 'queued'
                """,
                (str(lease_owner or "runr-worker"), lease_token, lease_expires_at, now, now, task_id),
            )
            claimed = connection.execute("SELECT * FROM customer_tasks WHERE task_id = ?", (task_id,)).fetchone()
            return _customer_task_payload(claimed)

        return self._run_transaction(claim)

    def complete_customer_task(
        self,
        task_id: str,
        *,
        state: str,
        result: Mapping[str, Any] | None = None,
        error_code: str = "",
        error_message: str = "",
        lease_owner: str = "",
        lease_token: str = "",
        attempt_count: int | None = None,
        retryable: bool = False,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        requested_state = "completed" if str(state or "").casefold() == "completed" else "failed"
        result_payload = dict(result or {})

        def finish(connection):
            current = connection.execute("SELECT * FROM customer_tasks WHERE task_id = ?", (str(task_id),)).fetchone()
            if current is None:
                raise KeyError(f"Customer task '{task_id}' was not found.")
            predicates = ["task_id = ?", "state = 'running'"]
            params: list[Any] = [str(task_id)]
            if lease_owner:
                predicates.append("lease_owner = ?")
                params.append(str(lease_owner))
            if lease_token:
                predicates.append("lease_token = ?")
                params.append(str(lease_token))
            if attempt_count is not None:
                predicates.append("attempt_count = ?")
                params.append(int(attempt_count))
            next_state = requested_state
            if requested_state == "failed" and retryable and int(current["attempt_count"] or 0) < int(current["max_attempts"] or 1):
                next_state = "queued"
            cursor = connection.execute(
                f"""
                UPDATE customer_tasks SET state = ?, result_json = ?, error_code = ?, error_message = ?,
                    lease_owner = '', lease_token = '', lease_expires_at = '',
                    completed_at = CASE WHEN ? = 'completed' OR ? = 'failed' THEN ? ELSE completed_at END,
                    updated_at = ?
                WHERE {' AND '.join(predicates)}
                """,
                (
                    next_state,
                    _json(result_payload),
                    str(error_code or ""),
                    str(error_message or ""),
                    next_state,
                    next_state,
                    now,
                    now,
                    *params,
                ),
            )
            updated = connection.execute("SELECT * FROM customer_tasks WHERE task_id = ?", (str(task_id),)).fetchone()
            return _customer_task_payload(updated)

        return self._run_transaction(finish)


__all__ = ["SqlitePersonalizedJobsStore"]
