from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
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
