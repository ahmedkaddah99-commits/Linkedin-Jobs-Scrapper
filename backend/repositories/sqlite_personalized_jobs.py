from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from backend.domain.models import utc_now_iso
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


class SqlitePersonalizedJobsStore(_SqliteStore):
    """Persistence boundary for user state and read-only catalog projections."""

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
            "filters": payload if isinstance(payload, dict) else {},
            "is_default": bool(int(row["is_default"] or 0)),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

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

        return self._run_transaction(write)

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

    def enqueue_intelligence(self, key: Mapping[str, Any]) -> dict[str, Any]:
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
            connection.execute(
                """
                INSERT INTO job_intelligence_queue (cache_id, state, attempts, requested_at)
                VALUES (?, 'queued', 0, ?)
                ON CONFLICT(cache_id) DO UPDATE SET
                    state = CASE WHEN job_intelligence_queue.state = 'completed' THEN job_intelligence_queue.state ELSE 'queued' END,
                    requested_at = CASE WHEN job_intelligence_queue.state = 'completed' THEN job_intelligence_queue.requested_at ELSE excluded.requested_at END,
                    last_error = CASE WHEN job_intelligence_queue.state = 'completed' THEN job_intelligence_queue.last_error ELSE '' END
                """,
                (str(key.get("cache_id") or ""), now),
            )
            return _row_payload(row)

        return self._run_transaction(write)

    def claim_next_intelligence(self) -> dict[str, Any] | None:
        now = utc_now_iso()

        def write(connection):
            row = connection.execute(
                """
                SELECT c.* FROM job_intelligence_cache c
                JOIN job_intelligence_queue q ON q.cache_id = c.cache_id
                WHERE q.state = 'queued' AND c.state = 'pending'
                ORDER BY q.requested_at, q.cache_id LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            cache_id = str(row["cache_id"])
            connection.execute(
                "UPDATE job_intelligence_queue SET state='processing', attempts=attempts+1, claimed_at=? WHERE cache_id=? AND state='queued'",
                (now, cache_id),
            )
            connection.execute("UPDATE job_intelligence_cache SET state='processing', updated_at=? WHERE cache_id=?", (now, cache_id))
            result = _row_payload(row)
            result["payload"] = _decode(row["payload_json"], {})
            return result

        return self._run_transaction(write)

    def complete_intelligence(self, cache_id: str, *, state: str, payload: Mapping[str, Any], error: str = "") -> None:
        now = utc_now_iso()
        generated_at = now if state == "available" else ""
        with self._connect() as connection:
            connection.execute(
                "UPDATE job_intelligence_cache SET state=?, payload_json=?, updated_at=?, generated_at=? WHERE cache_id=?",
                (str(state), _json(dict(payload)), now, generated_at, str(cache_id)),
            )
            connection.execute(
                "UPDATE job_intelligence_queue SET state=?, completed_at=?, last_error=? WHERE cache_id=?",
                ("completed" if state in {"available", "failed"} else "queued", now if state in {"available", "failed"} else "", str(error or ""), str(cache_id)),
            )

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
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT created_at FROM canonical_company_profiles WHERE company_id = ?",
                (company_id,),
            ).fetchone()
            created_at = str(existing["created_at"] or now) if existing is not None else now
            connection.execute(
                """
                INSERT INTO canonical_company_profiles (
                    company_id, profile_json, logo_object_key, logo_source_url,
                    logo_content_hash, logo_content_type, logo_verified_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_id) DO UPDATE SET
                    profile_json=excluded.profile_json,
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
                SELECT c.company_id, c.canonical_name, c.entity_kind, c.provenance_url,
                       p.profile_json, p.logo_object_key, p.logo_source_url,
                       p.logo_content_hash, p.logo_content_type, p.logo_verified_at,
                       t.status AS enrichment_status, t.attempt_count,
                       t.last_success_at, t.next_attempt_at, t.last_error
                FROM canonical_companies c
                LEFT JOIN canonical_company_profiles p ON p.company_id = c.company_id
                LEFT JOIN company_enrichment_targets t ON t.company_id = c.company_id
                WHERE (t.next_attempt_at IS NULL OR t.next_attempt_at = '' OR t.next_attempt_at <= ?)
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
                SELECT c.company_id, c.canonical_name, c.entity_kind, c.provenance_url,
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

    @staticmethod
    def _feed_filter_sql(filters: Mapping[str, Any] | None) -> tuple[list[str], list[Any]]:
        filters = dict(filters or {})
        predicates: list[str] = []
        params: list[Any] = []
        text_expr = "LOWER(COALESCE(catalog.title, '') || ' ' || COALESCE(catalog.company, '') || ' ' || COALESCE(catalog.location, '') || ' ' || COALESCE(catalog.version_location, '') || ' ' || COALESCE(catalog.description, '') || ' ' || COALESCE(catalog.version_payload_json, ''))"
        for term in filters.get("search_text") or []:
            predicates.append(f"{text_expr} LIKE ?")
            params.append(f"%{str(term).casefold()}%")

        field_exprs = {
            "role": ["catalog.title", "json_extract(catalog.version_payload_json, '$.role')", "json_extract(catalog.version_payload_json, '$.roles')", "json_extract(catalog.version_payload_json, '$.role_category')", "json_extract(catalog.version_payload_json, '$.job_category')", "json_extract(catalog.version_payload_json, '$.function')"],
            "category": ["json_extract(catalog.version_payload_json, '$.category')", "json_extract(catalog.version_payload_json, '$.categories')", "json_extract(catalog.version_payload_json, '$.job_category')", "json_extract(catalog.version_payload_json, '$.role_category')", "json_extract(catalog.version_payload_json, '$.function')"],
            "location": ["catalog.location", "catalog.version_location", "json_extract(catalog.version_payload_json, '$.location')"],
            "work_arrangement": ["json_extract(catalog.version_payload_json, '$.work_arrangement')", "json_extract(catalog.version_payload_json, '$.workplace')", "json_extract(catalog.version_payload_json, '$.workplace_type')", "json_extract(catalog.version_payload_json, '$.remote_type')"],
            "employment_type": ["json_extract(catalog.version_payload_json, '$.employment_type')", "json_extract(catalog.version_payload_json, '$.job_type')", "json_extract(catalog.version_payload_json, '$.type')"],
            "experience_level": ["json_extract(catalog.version_payload_json, '$.experience_level')", "json_extract(catalog.version_payload_json, '$.seniority')", "json_extract(catalog.version_payload_json, '$.level')"],
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
        }
        for field, requested in filters.items():
            values = [str(item).strip().casefold() for item in (requested if isinstance(requested, (list, tuple, set)) else [requested]) if str(item).strip()]
            if not values or field in {"include_hidden", "use_saved_search", "hidden_companies", "sort", "search_text"}:
                continue
            if field == "company":
                predicates.append("LOWER(catalog.company) IN (" + ",".join("?" for _ in values) + ")")
                params.extend(values)
            elif field in field_exprs:
                expressions = [f"LOWER(COALESCE({expr}, ''))" for expr in field_exprs[field]]
                predicates.append("(" + " OR ".join(" OR ".join(f"{expr} LIKE ?" for expr in expressions) for _ in values) + ")")
                params.extend(f"%{value.replace('-', ' ')}%" for value in values for _ in expressions)
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
        return predicates, params

    def _feed_scope_sql(self) -> str:
        return f"""
            SELECT catalog.*, COALESCE(d.state, 'none') AS user_state,
                   COALESCE(d.updated_at, '') AS user_state_updated_at
            FROM ({self._published_jobs_sql()}) AS catalog
            LEFT JOIN personalized_job_dispositions d
              ON d.canonical_job_id = catalog.canonical_job_id AND d.user_id = ?
        """

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
    ) -> dict[str, Any]:
        limit = max(1, min(100, int(limit)))
        with self._connect() as connection:
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
            if sort_mode not in {"newest", "priority", "best"}:
                sort_mode = "newest"
            sort_expr = "COALESCE(NULLIF(page.last_verified_at, ''), NULLIF(page.first_seen_at, ''), '')"
            page_source = f"""
                SELECT scoped.*,
                       (SELECT e.payload_json FROM personalized_job_evaluations e
                        WHERE e.user_id = ? AND e.canonical_job_id = scoped.canonical_job_id
                          AND e.job_version_id = scoped.current_version_id
                          AND e.evaluator_version = 'phase_e_v2'
                        ORDER BY e.updated_at DESC LIMIT 1) AS evaluation_payload
                FROM ({self._feed_scope_sql()}) AS scoped
            """
            if sort_mode in {"priority", "best"}:
                source = f"SELECT page.*, {self._priority_sql()} AS priority_score FROM ({page_source}) AS page"
                order_sql = "priority_score DESC, " + sort_expr + " DESC, page.canonical_job_id DESC"
            else:
                source = f"SELECT page.*, 0.0 AS priority_score FROM ({page_source}) AS page"
                order_sql = sort_expr + " DESC, page.canonical_job_id DESC"
            predicates = [f"({item})" for item in predicates]
            count_where_sql = " AND ".join(predicates) if predicates else "1=1"
            count_filter_params = list(filter_params)
            if cursor:
                if sort_mode in {"priority", "best"}:
                    predicates.append("(page.priority_score < ? OR (page.priority_score = ? AND page.canonical_job_id < ?))")
                    filter_params.extend([float(cursor.get("priority") or 0), float(cursor.get("priority") or 0), str(cursor.get("canonical_job_id") or "")])
                else:
                    predicates.append(f"({sort_expr} < ? OR ({sort_expr} = ? AND page.canonical_job_id < ?))")
                    filter_params.extend([str(cursor.get("sort") or ""), str(cursor.get("sort") or ""), str(cursor.get("canonical_job_id") or "")])
            where_sql = " AND ".join(predicates) if predicates else "1=1"
            count_sql = f"SELECT COUNT(*) AS total FROM ({source}) AS page WHERE {count_where_sql}"
            count_params = [str(user_id), str(publication["publication_id"]), str(user_id), *count_filter_params]
            total = int(connection.execute(count_sql, tuple(count_params)).fetchone()["total"] or 0)
            rows_sql = f"SELECT page.* FROM ({source}) AS page WHERE {where_sql} ORDER BY {order_sql} LIMIT ?"
            rows_params = [str(user_id), str(publication["publication_id"]), str(user_id), *filter_params, limit + 1]
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

    def get_published_filter_capabilities(self) -> dict[str, bool]:
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
        with self._connect() as connection:
            publication_id = self._head_publication_id(connection)
            if not publication_id:
                return {key: False for key in capability_exprs}
            result = connection.execute(
                "SELECT " + ", ".join(f"MAX(CASE WHEN {expr} THEN 1 ELSE 0 END) AS {key}" for key, expr in capability_exprs.items()) + f" FROM ({self._published_jobs_sql()}) AS catalog",
                (publication_id,),
            ).fetchone()
        return {key: bool(int(result[key] or 0)) for key in capability_exprs}

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
    def _published_jobs_sql() -> str:
        return """
            SELECT
                j.canonical_job_id, j.company_id, c.canonical_name AS company,
                c.entity_kind AS company_entity_kind, c.provenance_url AS company_provenance_url,
                p.profile_json AS company_profile_json,
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
            LEFT JOIN (
                SELECT * FROM (
                    SELECT s.*, ROW_NUMBER() OVER (
                        PARTITION BY s.canonical_job_id
                        ORDER BY s.observed_at DESC, s.snapshot_id DESC
                    ) AS snapshot_rank
                    FROM job_applicant_snapshots s
                ) ranked
                WHERE ranked.snapshot_rank = 1
            ) aps ON aps.canonical_job_id = j.canonical_job_id
            WHERE pj.publication_id = ?
        """


__all__ = ["SqlitePersonalizedJobsStore"]
