"""Safe, resumable reprocessing of preserved acquisition observations."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.acquisition.quality import normalize_job_for_ingestion, stable_content_payload
from backend.acquisition.unified_mapping import UNIFIED_RULE_VERSION
from backend.database.connection import database_session, database_target_info
from backend.database.initialization import initialize_database
from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore


STAGES = (
    "source_registry", "immutable_observation", "extraction", "normalization",
    "identity_resolution", "canonical_field_merge", "quality_completeness", "publication_read_model",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _count(connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()  # noqa: S608 - table names are internal constants
    return int(row["count"] or 0) if row is not None else 0


def _environment(db_path: str | Path) -> dict[str, Any]:
    info = dict(database_target_info(db_path))
    info["database_path"] = str(Path(db_path).expanduser().resolve()) if info.get("target_backend") == "sqlite" else None
    info["configured_environment"] = str(os.environ.get("RUNR_ENV") or "development")
    info["database_url_present"] = bool(os.environ.get("TURSO_DATABASE_URL", "").strip())
    return info


def build_reprocessing_plan(db_path: str | Path, *, scope: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Read counts and expected mutations without creating a run or changing data."""

    initialize_database(db_path)
    environment = _environment(db_path)
    with database_session(db_path) as connection:
        counts = {
            "observations": _count(connection, "job_source_observations"),
            "source_records": _count(connection, "job_source_observations"),
            "canonical_jobs": _count(connection, "canonical_jobs"),
            "canonical_companies": _count(connection, "canonical_companies"),
            "duplicate_clusters": _count(connection, "acquisition_duplicate_clusters"),
            "semantic_versions": _count(connection, "job_posting_versions"),
            "application_classifications": _count(connection, "job_source_observations"),
            "normalized_fields": _count(connection, "acquisition_field_provenance"),
            "company_urls": _count(connection, "canonical_company_urls"),
            "logos": _count(connection, "company_logo_enrichments"),
            "completeness_states": _count(connection, "acquisition_completeness_reports"),
            "warnings": _count(connection, "acquisition_quality_events"),
            "publications": _count(connection, "acquisition_publications"),
        }
    return {
        "rule_version": UNIFIED_RULE_VERSION,
        "environment": environment,
        "scope": dict(scope or {}),
        "counts_before": counts,
        "expected_mutations": {
            "source_observations": "none; immutable rows are read only",
            "normalized_projections": "upsert one versioned output per observation and rule",
            "canonical_fields": "update only evidence-backed projections; never overwrite with unknown",
            "quality": "report-only completeness and warning rows",
            "duplicates": "candidate clusters only; no automatic merge",
            "publication": "read-model metrics only; no automatic publication promotion",
            "enrichment": "no network enrichment unless an enabled provider is explicitly invoked",
        },
        "stages": list(STAGES),
        "rollback": {
            "local_sqlite": "copy database before apply",
            "remote_libsql": "immutable observations plus transaction-safe additive projections; no destructive writes",
        },
    }


def _backup_local(db_path: Path, reprocessing_id: str) -> dict[str, Any]:
    if not db_path.exists():
        return {"status": "not_available", "reason": "database_file_missing"}
    backup_dir = db_path.parent / "reprocessing_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{db_path.stem}.{reprocessing_id}.bak"
    shutil.copy2(db_path, backup_path)
    return {"status": "created", "path": str(backup_path), "recoverable": True}


def _start_run(connection, *, reprocessing_id: str, idempotency_key: str, plan: Mapping[str, Any], backup: Mapping[str, Any]) -> None:
    now = _now()
    connection.execute(
        """
        INSERT INTO acquisition_reprocessing_runs (
            reprocessing_id, idempotency_key, status, rule_version, environment_json,
            scope_json, plan_json, checkpoint_json, counts_json, backup_json,
            started_at, created_at, updated_at
        ) VALUES (?, ?, 'running', ?, ?, ?, ?, '{}', '{}', ?, ?, ?, ?)
        """,
        (
            reprocessing_id, idempotency_key, UNIFIED_RULE_VERSION,
            _json(plan.get("environment") or {}), _json(plan.get("scope") or {}), _json(dict(plan)), _json(dict(backup)),
            now, now, now,
        ),
    )
    for stage in STAGES:
        connection.execute(
            """
            INSERT INTO acquisition_stage_results (
                stage_result_id, execution_id, stage_name, status, rule_version,
                started_at, created_at, updated_at
            ) VALUES (?, ?, ?, 'pending', ?, '', ?, ?)
            """,
            (f"stage_result_{uuid4().hex}", reprocessing_id, stage, UNIFIED_RULE_VERSION, now, now),
        )


def _stage(connection, execution_id: str, stage_name: str, *, status: str, metrics: Mapping[str, Any] | None = None, checkpoint: Mapping[str, Any] | None = None, error: Mapping[str, Any] | None = None) -> None:
    now = _now()
    connection.execute(
        """
        UPDATE acquisition_stage_results
        SET status=?, started_at=CASE WHEN started_at='' THEN ? ELSE started_at END,
            completed_at=CASE WHEN ? IN ('completed', 'failed', 'report_only') THEN ? ELSE completed_at END,
            metrics_json=?, checkpoint_json=?, error_json=?, updated_at=?
        WHERE execution_id=? AND stage_name=?
        """,
        (status, now, status, now, _json(dict(metrics or {})), _json(dict(checkpoint or {})), _json(dict(error or {})), now, execution_id, stage_name),
    )


def _store_duplicate_candidates(connection, *, rule_version: str, now: str) -> int:
    rows = connection.execute(
        """
        SELECT j.canonical_job_id, j.company_id, j.title, j.location,
               COALESCE(v.content_hash, '') AS semantic_hash
        FROM canonical_jobs j
        LEFT JOIN job_posting_versions v ON v.version_id=j.current_version_id
        WHERE j.lifecycle_state != 'closed'
        ORDER BY j.canonical_job_id
        """
    ).fetchall()
    grouped: dict[tuple[str, str, str, str], list[str]] = {}
    for row in rows:
        key = (
            str(row["company_id"] or ""),
            " ".join(str(row["title"] or "").casefold().split()),
            " ".join(str(row["location"] or "").casefold().split()),
            str(row["semantic_hash"] or ""),
        )
        if all(key):
            grouped.setdefault(key, []).append(str(row["canonical_job_id"]))
    created = 0
    for key, members in grouped.items():
        if len(members) < 2:
            continue
        cluster_key = hashlib.sha256(_json([rule_version, key, sorted(members)]).encode("utf-8")).hexdigest()[:32]
        cluster_id = f"duplicate_cluster_{cluster_key}"
        connection.execute(
            """
            INSERT INTO acquisition_duplicate_clusters (
                cluster_id, state, confidence, reasons_json, rule_version, created_at, updated_at
            ) VALUES (?, 'candidate', 0.98, ?, ?, ?, ?)
            ON CONFLICT(cluster_id) DO UPDATE SET updated_at=excluded.updated_at
            """,
            (cluster_id, _json(["same canonical company", "same normalized title", "compatible location", "same semantic description fingerprint"]), rule_version, now, now),
        )
        for member in members:
            connection.execute(
                """
                INSERT OR IGNORE INTO acquisition_duplicate_members (
                    cluster_id, canonical_job_id, member_score, member_reasons_json, created_at
                ) VALUES (?, ?, 0.98, ?, ?)
                """,
                (cluster_id, member, _json(["supporting evidence only; no automatic merge"]), now),
            )
        created += 1
    return created


def _process_observation(connection, row: Mapping[str, Any], *, execution_id: str, now: str) -> dict[str, int]:
    observation_id = str(row["observation_id"])
    stored_payload = _decode(row.get("raw_payload_json"), {})
    historical = False
    if not isinstance(stored_payload, Mapping) or not stored_payload:
        normalized_payload = _decode(row.get("payload_json"), {})
        stored_payload = normalized_payload.get("source_raw_payload") if isinstance(normalized_payload, Mapping) and isinstance(normalized_payload.get("source_raw_payload"), Mapping) else normalized_payload
        historical = True
    raw_job = dict(stored_payload) if isinstance(stored_payload, Mapping) else {}
    target = {
        "target_id": str(row.get("target_id") or ""), "connector": str(row.get("target_connector") or row.get("source_connector") or row.get("source_ats") or ""),
        "display_name": str(row.get("source_display_name") or ""), "source_token": str(row.get("source_token") or ""),
        "provenance_url": str(row.get("original_url") or ""), "canonical_target_url": str(row.get("original_url") or ""),
        "config": {},
    }
    normalized = normalize_job_for_ingestion(raw_job, target)
    normalized["source_observation_id"] = observation_id
    normalized["observed_at"] = str(row.get("observed_at") or now)
    mapping = normalized.get("unified_mapping") if isinstance(normalized.get("unified_mapping"), Mapping) else {}
    canonical_job_id = str(row.get("canonical_job_id") or "")
    company_row = connection.execute(
        "SELECT company_id FROM canonical_jobs WHERE canonical_job_id=?", (canonical_job_id,)
    ).fetchone()
    company_id = str(company_row["company_id"] or "") if company_row is not None else ""
    title = str(normalized.get("title") or row.get("external_job_id") or "")
    location = str(normalized.get("location") or normalized.get("location_raw") or "")
    if canonical_job_id:
        connection.execute(
            """
            UPDATE canonical_jobs
            SET title=CASE WHEN ? != '' THEN ? ELSE title END,
                location=CASE WHEN ? != '' THEN ? ELSE location END,
                canonical_url=CASE WHEN ? != '' THEN ? ELSE canonical_url END,
                last_reprocessed_at=?, updated_at=?
            WHERE canonical_job_id=?
            """,
            (title, title, location, location, str(normalized.get("job_detail_url") or ""), str(normalized.get("job_detail_url") or ""), str(row.get("observed_at") or now), now, canonical_job_id),
        )
        if canonical_job_id and company_id:
            SqliteAcquisitionStore._ensure_version(
                connection, canonical_job_id, title=title,
                description=str(normalized.get("description_text") or normalized.get("description") or ""),
                location=location, apply_url=str(normalized.get("application_url") or ""),
                content_hash=hashlib.sha256(_json(stable_content_payload(normalized)).encode("utf-8")).hexdigest(),
                source_observation_id=observation_id, payload=normalized, now=now,
            )
            SqliteAcquisitionStore._persist_unified_mapping(
                connection, canonical_job_id=canonical_job_id, company_id=company_id,
                source_observation_id=observation_id, execution_id=execution_id,
                mapping=mapping, job=normalized, observed_at=str(row.get("observed_at") or now),
            )
    warnings = list(normalized.get("quality_warnings") or [])
    if historical:
        warnings.append("raw_payload_not_available_for_historical_repair")
    for warning in sorted(set(str(item) for item in warnings if item)):
        connection.execute(
            """
            INSERT OR IGNORE INTO acquisition_quality_events (
                event_id, cycle_id, task_id, target_id, canonical_job_id, company_id,
                employer_name, connector, source_token, warning_code, severity, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'warning', ?, ?)
            """,
            (
                f"quality_event_reprocess_{hashlib.sha256(_json([observation_id, warning, UNIFIED_RULE_VERSION]).encode('utf-8')).hexdigest()[:32]}", execution_id, "reprocessing", str(row.get("target_id") or ""), canonical_job_id,
                company_id, str(normalized.get("company") or ""), str(row.get("source_connector") or ""), str(row.get("source_token") or ""),
                warning, _json({"observation_id": observation_id, "report_only": True}), now,
            ),
        )
    return {"observations": 1, "historical_repairs": int(historical), "warnings": len(set(warnings)), "fields": len(mapping.get("fields") or {})}


def _process_batch(
    connection,
    *,
    checkpoint: str,
    batch_size: int,
    execution_id: str,
    totals: Mapping[str, int],
) -> tuple[str, dict[str, int], dict[str, int]] | None:
    """Process one batch inside an explicit transaction.

    The explicit transaction is important for remote libSQL: without it each
    statement can become an independent network round trip.
    """

    rows = connection.execute(
        """
        SELECT o.*, j.company_id, t.connector AS target_connector
        FROM job_source_observations o
        JOIN canonical_jobs j ON j.canonical_job_id=o.canonical_job_id
        LEFT JOIN acquisition_targets t ON t.target_id=o.target_id
        WHERE (? = '' OR o.observation_id > ?)
        ORDER BY o.observation_id LIMIT ?
        """,
        (checkpoint, checkpoint, max(1, min(1000, int(batch_size)))),
    ).fetchall()
    if not rows:
        return None
    batch_counts = {key: 0 for key in totals}
    for row in rows:
        result = _process_observation(connection, row, execution_id=execution_id, now=_now())
        for key in ("observations", "historical_repairs", "warnings", "fields"):
            batch_counts[key] += int(result.get(key) or 0)
    next_checkpoint = str(rows[-1]["observation_id"])
    next_totals = dict(totals)
    for key, value in batch_counts.items():
        next_totals[key] = int(next_totals.get(key) or 0) + int(value or 0)
    next_totals["batches"] = int(next_totals.get("batches") or 0) + 1
    connection.execute(
        """
        UPDATE acquisition_reprocessing_runs
        SET checkpoint_json=?, counts_json=?, updated_at=?
        WHERE reprocessing_id=?
        """,
        (_json({"last_observation_id": next_checkpoint}), _json(next_totals), _now(), execution_id),
    )
    _stage(connection, execution_id, "extraction", status="completed", metrics={"batch": next_totals["batches"], "observations": batch_counts["observations"]}, checkpoint={"last_observation_id": next_checkpoint})
    _stage(connection, execution_id, "normalization", status="completed", metrics={"fields": batch_counts["fields"]}, checkpoint={"last_observation_id": next_checkpoint})
    _stage(connection, execution_id, "canonical_field_merge", status="completed", metrics={"observations": batch_counts["observations"]}, checkpoint={"last_observation_id": next_checkpoint})
    _stage(connection, execution_id, "quality_completeness", status="report_only", metrics={"warnings": batch_counts["warnings"]}, checkpoint={"last_observation_id": next_checkpoint})
    return next_checkpoint, batch_counts, next_totals


def run_reprocessing(
    db_path: str | Path,
    *,
    apply: bool = False,
    batch_size: int = 100,
    idempotency_key: str = "",
    resume_id: str = "",
    scope: Mapping[str, Any] | None = None,
    allow_remote_additive_rollback: bool = False,
) -> dict[str, Any]:
    """Plan or execute the reprocessor with committed batch checkpoints."""

    plan = build_reprocessing_plan(db_path, scope=scope)
    if not apply:
        return {"status": "planned", "plan": plan}
    environment = plan["environment"]
    if environment.get("target_backend") == "libsql" and not allow_remote_additive_rollback:
        return {"status": "blocked", "reason": "remote_requires_allow_remote_additive_rollback", "plan": plan}
    reprocessing_id = resume_id or f"reprocess_{uuid4().hex}"
    idempotency_key = idempotency_key or reprocessing_id
    db_file = Path(db_path)
    backup = _backup_local(db_file, reprocessing_id) if environment.get("target_backend") == "sqlite" else {"status": "transaction_safe_additive", "recoverable": True}
    with database_session(db_path) as connection:
        existing = connection.execute(
            "SELECT * FROM acquisition_reprocessing_runs WHERE reprocessing_id=? OR idempotency_key=? ORDER BY created_at DESC LIMIT 1",
            (reprocessing_id, idempotency_key),
        ).fetchone()
        if existing is None:
            _start_run(connection, reprocessing_id=reprocessing_id, idempotency_key=idempotency_key, plan=plan, backup=backup)
        elif str(existing["status"] or "") == "completed":
            return {"status": "completed", "reprocessing_id": str(existing["reprocessing_id"]), "idempotent_replay": True, "counts": _decode(existing["counts_json"], {})}
        elif str(existing["reprocessing_id"]) != reprocessing_id:
            reprocessing_id = str(existing["reprocessing_id"])
    totals: dict[str, int] = {"observations": 0, "historical_repairs": 0, "warnings": 0, "fields": 0, "batches": 0, "duplicate_clusters": 0}
    checkpoint = ""
    with database_session(db_path) as connection:
        existing = connection.execute("SELECT checkpoint_json, counts_json FROM acquisition_reprocessing_runs WHERE reprocessing_id=?", (reprocessing_id,)).fetchone()
        if existing is not None:
            checkpoint = str((_decode(existing["checkpoint_json"], {}) or {}).get("last_observation_id") or "")
            totals.update({key: int(value or 0) for key, value in (_decode(existing["counts_json"], {}) or {}).items() if key in totals})
    try:
        while True:
            with database_session(db_path) as connection:
                batch = connection.transaction(
                    lambda transaction_connection: _process_batch(
                        transaction_connection,
                        checkpoint=checkpoint,
                        batch_size=batch_size,
                        execution_id=reprocessing_id,
                        totals=totals,
                    )
                )
                if batch is None:
                    break
                checkpoint, _, next_totals = batch
                totals = next_totals
    except Exception as exc:
        with database_session(db_path) as connection:
            connection.execute(
                "UPDATE acquisition_reprocessing_runs SET status='failed', error_json=?, updated_at=? WHERE reprocessing_id=?",
                (_json({"type": type(exc).__name__, "message": str(exc), "report_only": True}), _now(), reprocessing_id),
            )
        raise
    with database_session(db_path) as connection:
        now = _now()
        totals["duplicate_clusters"] = _store_duplicate_candidates(connection, rule_version=UNIFIED_RULE_VERSION, now=now)
        for stage in ("source_registry", "immutable_observation", "identity_resolution", "publication_read_model"):
            _stage(connection, reprocessing_id, stage, status="report_only", metrics={"mode": "reprocessing"})
        _stage(connection, reprocessing_id, "identity_resolution", status="report_only", metrics={"duplicate_clusters": totals["duplicate_clusters"]})
        _stage(connection, reprocessing_id, "publication_read_model", status="report_only", metrics={"automatic_promotion": False})
        connection.execute(
            "UPDATE acquisition_reprocessing_runs SET status='completed', counts_json=?, completed_at=?, updated_at=? WHERE reprocessing_id=?",
            (_json(totals), now, now, reprocessing_id),
        )
    return {"status": "completed", "reprocessing_id": reprocessing_id, "rule_version": UNIFIED_RULE_VERSION, "counts": totals, "plan": plan, "backup": backup}


__all__ = ["STAGES", "UNIFIED_RULE_VERSION", "build_reprocessing_plan", "run_reprocessing"]
