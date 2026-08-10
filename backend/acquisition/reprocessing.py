"""Safe, resumable reprocessing of preserved acquisition observations."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
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
MAX_BATCH_SIZE = 1000
DEFAULT_MAX_BATCHES = 100
DEFAULT_STALE_RUN_SECONDS = 30 * 60


class ReprocessingLeaseLost(RuntimeError):
    """Raised when another process reclaimed the durable reprocessing run."""


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


def _as_int(value: Any, *, default: int = 0, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(minimum, parsed)
    return min(parsed, maximum) if maximum is not None else parsed


def _timestamp_age_seconds(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())


def _lease_expiry(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(1, int(seconds)))).isoformat()


def _claim_run(
    connection,
    *,
    reprocessing_id: str,
    lease_token: str,
    lease_seconds: int,
    expected_statuses: tuple[str, ...],
    expected_updated_at: str = "",
) -> bool:
    if not expected_statuses:
        return False
    placeholders = ",".join("?" for _ in expected_statuses)
    where = f"reprocessing_id=? AND status IN ({placeholders})"
    parameters: list[Any] = [lease_token, _lease_expiry(lease_seconds), _now(), reprocessing_id, *expected_statuses]
    # Private/operator callers may not have the timestamp observed during the
    # initial read. They still must not overwrite a live owner lease. The
    # normal runner supplies ``expected_updated_at`` after checking staleness;
    # this guard protects direct callers and stale launchers that bypass it.
    if "running" in expected_statuses and not expected_updated_at:
        where += " AND (status != 'running' OR lease_expires_at = '' OR lease_expires_at <= ?)"
        parameters.append(_now())
    if expected_updated_at:
        where += " AND updated_at=?"
        parameters.append(expected_updated_at)
    changed = connection.execute(
        f"""
        UPDATE acquisition_reprocessing_runs
        SET status='running', lease_token=?, lease_expires_at=?, error_json='{{}}', completed_at='', updated_at=?
        WHERE {where}
        """,  # noqa: S608 - statuses are fixed internal values
        parameters,
    )
    return changed.rowcount == 1


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

    environment = _environment(db_path)
    # A local plan may bootstrap its disposable SQLite schema.  A remote plan
    # must be strictly read-only; migrations belong to deployment pre-deploy,
    # never to an admin GET or an operator's dry run.
    if environment.get("target_backend") == "sqlite":
        initialize_database(db_path)
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
        return {"status": "not_available", "reason": "database_file_missing", "recoverable": False}
    backup_dir = db_path.parent / "reprocessing_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{db_path.stem}.{reprocessing_id}.bak"
    shutil.copy2(db_path, backup_path)
    return {
        "status": "created",
        "path": str(backup_path.resolve()),
        "recoverable": True,
        "rollback_reference": {
            "kind": "sqlite_backup",
            "reprocessing_id": reprocessing_id,
            "path": str(backup_path.resolve()),
            "automatic_rollback": False,
        },
    }


def _start_run(connection, *, reprocessing_id: str, idempotency_key: str, plan: Mapping[str, Any], backup: Mapping[str, Any]) -> bool:
    now = _now()
    inserted = connection.execute(
        """
        INSERT OR IGNORE INTO acquisition_reprocessing_runs (
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
    if inserted.rowcount == 0:
        return False
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
    return True


def _rollback_reference(*, reprocessing_id: str, idempotency_key: str, backup: Mapping[str, Any]) -> dict[str, Any]:
    existing = backup.get("rollback_reference") if isinstance(backup.get("rollback_reference"), Mapping) else {}
    if existing:
        return dict(existing)
    return {
        "kind": "remote_additive_checkpoint",
        "reprocessing_id": reprocessing_id,
        "idempotency_key": idempotency_key,
        "automatic_rollback": False,
        "resume_from": "acquisition_reprocessing_runs.checkpoint_json",
        "operator_action": "resume with the same idempotency key; do not delete observations or versions",
    }


def _record_observation_failure(connection, row: Mapping[str, Any], *, execution_id: str, error: BaseException, now: str) -> str:
    observation_id = str(row.get("observation_id") or "")
    event_id = "quality_event_reprocess_failure_" + hashlib.sha256(
        _json([observation_id, UNIFIED_RULE_VERSION, "reprocessing_observation_failed"]).encode("utf-8")
    ).hexdigest()[:32]
    connection.execute(
        """
        INSERT OR IGNORE INTO acquisition_quality_events (
            event_id, cycle_id, task_id, target_id, canonical_job_id, company_id,
            employer_name, connector, source_token, warning_code, severity, details_json, created_at
        ) VALUES (?, ?, 'reprocessing', ?, ?, ?, ?, ?, ?, 'reprocessing_observation_failed', 'error', ?, ?)
        """,
        (
            event_id,
            execution_id,
            str(row.get("target_id") or ""),
            str(row.get("canonical_job_id") or ""),
            str(row.get("company_id") or ""),
            "",
            str(row.get("target_connector") or row.get("source_connector") or ""),
            str(row.get("source_token") or ""),
            _json(
                {
                    "observation_id": observation_id,
                    "exception_type": type(error).__name__,
                    "message": str(error),
                    "report_only": True,
                    "retryable_by_resume": True,
                }
            ),
            now,
        ),
    )
    return event_id


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
    failed_observation_ids: list[str],
    retry_failed: bool,
    lease_token: str,
    lease_seconds: int,
    remote_mode: str = "auto",
) -> tuple[str, dict[str, int], dict[str, int], list[str]] | None:
    """Process one batch inside an explicit transaction.

    The explicit transaction is important for remote libSQL: without it each
    statement can become an independent network round trip.
    """

    if getattr(connection, "backend", "sqlite") == "libsql" and remote_mode == "auto":
        try:
            # Fast path: one replayable transaction for the complete batch.
            # If any record fails, retry the same batch in isolated
            # transactions below so the failure remains report-only.
            return connection.transaction(
                lambda transaction_connection: _process_batch(
                    transaction_connection,
                    checkpoint=checkpoint,
                    batch_size=batch_size,
                    execution_id=execution_id,
                    totals=totals,
                    failed_observation_ids=failed_observation_ids,
                    retry_failed=retry_failed,
                    lease_token=lease_token,
                    lease_seconds=lease_seconds,
                    remote_mode="batch",
                )
            )
        except ReprocessingLeaseLost:
            raise
        except Exception:
            return _process_batch(
                connection,
                checkpoint=checkpoint,
                batch_size=batch_size,
                execution_id=execution_id,
                totals=totals,
                failed_observation_ids=failed_observation_ids,
                retry_failed=retry_failed,
                lease_token=lease_token,
                lease_seconds=lease_seconds,
                remote_mode="isolated",
            )

    limit = _as_int(batch_size, default=100, minimum=1, maximum=MAX_BATCH_SIZE)
    rows = []
    retry_ids = list(dict.fromkeys(str(item) for item in failed_observation_ids if str(item))) if retry_failed else []
    if retry_ids:
        placeholders = ",".join("?" for _ in retry_ids)
        rows.extend(
            connection.execute(
                f"""
                SELECT o.*, j.company_id, t.connector AS target_connector
                FROM job_source_observations o
                LEFT JOIN canonical_jobs j ON j.canonical_job_id=o.canonical_job_id
                LEFT JOIN acquisition_targets t ON t.target_id=o.target_id
                WHERE o.observation_id IN ({placeholders})
                ORDER BY o.observation_id LIMIT ?
                """,  # noqa: S608 - placeholders are generated from persisted IDs
                (*retry_ids, limit),
            ).fetchall()
        )
    remaining = max(0, limit - len(rows))
    if remaining:
        new_rows = connection.execute(
            """
            SELECT o.*, j.company_id, t.connector AS target_connector
            FROM job_source_observations o
            LEFT JOIN canonical_jobs j ON j.canonical_job_id=o.canonical_job_id
            LEFT JOIN acquisition_targets t ON t.target_id=o.target_id
            WHERE (? = '' OR o.observation_id > ?)
            ORDER BY o.observation_id LIMIT ?
            """,
            (checkpoint, checkpoint, remaining),
        ).fetchall()
        seen = {str(row["observation_id"]) for row in rows}
        rows.extend(row for row in new_rows if str(row["observation_id"]) not in seen)
    if not rows:
        return None
    batch_counts = {key: 0 for key in totals}
    unresolved_failures = set(failed_observation_ids)
    # SQLite supports savepoints reliably inside the local transaction. The
    # remote libSQL driver can replay a transaction and invalidate a named
    # savepoint, so each remote observation gets its own atomic transaction.
    # That keeps one bad observation report-only without rolling back healthy
    # observations in the same bounded batch.
    remote_per_observation_transactions = (
        getattr(connection, "backend", "sqlite") == "libsql" and remote_mode == "isolated"
    )
    supports_savepoints = getattr(connection, "backend", "sqlite") == "sqlite"
    for index, row in enumerate(rows):
        observation_id = str(row["observation_id"])
        savepoint = f"reprocess_observation_{index}"
        if supports_savepoints:
            connection.execute(f"SAVEPOINT {savepoint}")  # noqa: S608 - name is an internal integer
        try:
            if remote_per_observation_transactions:
                result = connection.transaction(
                    lambda transaction_connection: _process_observation(
                        transaction_connection, row, execution_id=execution_id, now=_now()
                    )
                )
            else:
                result = _process_observation(connection, row, execution_id=execution_id, now=_now())
        except Exception as exc:
            if remote_mode == "batch":
                raise
            if not supports_savepoints:
                observation_error = exc
                connection.transaction(
                    lambda transaction_connection: _record_observation_failure(
                        transaction_connection, row, execution_id=execution_id, error=observation_error, now=_now()
                    )
                )
            else:
                connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")  # noqa: S608 - name is an internal integer
                connection.execute(f"RELEASE SAVEPOINT {savepoint}")  # noqa: S608 - name is an internal integer
                _record_observation_failure(connection, row, execution_id=execution_id, error=exc, now=_now())
            unresolved_failures.add(observation_id)
            batch_counts["failed_observations"] = int(batch_counts.get("failed_observations") or 0) + 1
            batch_counts.setdefault("failure_references", 0)
            batch_counts["failure_references"] += 1
            continue
        else:
            if supports_savepoints:
                connection.execute(f"RELEASE SAVEPOINT {savepoint}")  # noqa: S608 - name is an internal integer
            unresolved_failures.discard(observation_id)
        for key in ("observations", "historical_repairs", "warnings", "fields"):
            batch_counts[key] += int(result.get(key) or 0)
    new_rows = [row for row in rows if str(row["observation_id"]) > checkpoint]
    next_checkpoint = str(new_rows[-1]["observation_id"]) if new_rows else checkpoint
    next_totals = dict(totals)
    for key, value in batch_counts.items():
        next_totals[key] = int(next_totals.get(key) or 0) + int(value or 0)
    next_totals["batches"] = int(next_totals.get("batches") or 0) + 1
    next_totals["failed_observations"] = len(unresolved_failures)
    checkpoint_payload = {
        "last_observation_id": next_checkpoint,
        "failed_observation_ids": sorted(unresolved_failures),
    }
    def finalize_batch(transaction_connection) -> None:
        transaction_connection.execute(
            """
            UPDATE acquisition_reprocessing_runs
            SET checkpoint_json=?, counts_json=?, lease_expires_at=?, updated_at=?
            WHERE reprocessing_id=? AND status='running' AND lease_token=?
            """,
            (_json(checkpoint_payload), _json(next_totals), _lease_expiry(lease_seconds), _now(), execution_id, lease_token),
        )
        if transaction_connection.execute("SELECT changes()").fetchone()[0] != 1:
            raise ReprocessingLeaseLost("reprocessing lease was lost before checkpoint commit")
        batch_error = {
            "failed_observations": sorted(unresolved_failures),
            "retryable_by_resume": bool(unresolved_failures),
        }
        _stage(
            transaction_connection, execution_id, "extraction", status="completed",
            metrics={"batch": next_totals["batches"], "observations": batch_counts["observations"], "failed_observations": len(unresolved_failures)},
            checkpoint=checkpoint_payload, error=batch_error if unresolved_failures else {},
        )
        _stage(
            transaction_connection, execution_id, "normalization", status="completed",
            metrics={"fields": batch_counts["fields"], "failed_observations": len(unresolved_failures)},
            checkpoint=checkpoint_payload, error=batch_error if unresolved_failures else {},
        )
        _stage(
            transaction_connection, execution_id, "canonical_field_merge", status="completed",
            metrics={"observations": batch_counts["observations"], "failed_observations": len(unresolved_failures)},
            checkpoint=checkpoint_payload, error=batch_error if unresolved_failures else {},
        )
        _stage(
            transaction_connection, execution_id, "quality_completeness", status="report_only",
            metrics={"warnings": batch_counts["warnings"], "failed_observations": len(unresolved_failures)},
            checkpoint=checkpoint_payload, error=batch_error if unresolved_failures else {},
        )

    if remote_per_observation_transactions:
        connection.transaction(finalize_batch)
    else:
        finalize_batch(connection)
    return next_checkpoint, batch_counts, next_totals, sorted(unresolved_failures)


def run_reprocessing(
    db_path: str | Path,
    *,
    apply: bool = False,
    batch_size: int = 100,
    idempotency_key: str = "",
    resume_id: str = "",
    scope: Mapping[str, Any] | None = None,
    allow_remote_additive_rollback: bool = False,
    max_batches: int = DEFAULT_MAX_BATCHES,
    stale_after_seconds: int = DEFAULT_STALE_RUN_SECONDS,
) -> dict[str, Any]:
    """Plan or execute the reprocessor with committed, bounded checkpoints.

    A bounded invocation ends in ``incomplete`` after ``max_batches`` committed
    batches.  The same idempotency key can then resume from the durable
    observation checkpoint.  A run that was killed while ``running`` is
    reclaimable after its checkpoint has been stale for ``stale_after_seconds``.
    """

    plan = build_reprocessing_plan(db_path, scope=scope)
    if not apply:
        return {"status": "planned", "plan": plan}
    environment = plan["environment"]
    if environment.get("target_backend") == "libsql" and not allow_remote_additive_rollback:
        return {"status": "blocked", "reason": "remote_requires_allow_remote_additive_rollback", "plan": plan}
    reprocessing_id = resume_id or f"reprocess_{uuid4().hex}"
    idempotency_key = idempotency_key or reprocessing_id

    max_batches = _as_int(max_batches, default=DEFAULT_MAX_BATCHES, minimum=1, maximum=10000)
    batch_size = _as_int(batch_size, default=100, minimum=1, maximum=MAX_BATCH_SIZE)
    stale_after_seconds = _as_int(stale_after_seconds, default=DEFAULT_STALE_RUN_SECONDS, minimum=1, maximum=7 * 24 * 60 * 60)

    backup: dict[str, Any] | None = None
    lease_token = uuid4().hex
    with database_session(db_path) as connection:
        existing = connection.execute(
            "SELECT * FROM acquisition_reprocessing_runs WHERE reprocessing_id=? OR idempotency_key=? ORDER BY created_at DESC LIMIT 1",
            (reprocessing_id, idempotency_key),
        ).fetchone()
        if existing is not None and str(existing["reprocessing_id"]) != reprocessing_id:
            reprocessing_id = str(existing["reprocessing_id"])
            idempotency_key = str(existing["idempotency_key"] or idempotency_key)
        if existing is not None:
            stored_backup = _decode(existing["backup_json"], {})
            backup = dict(stored_backup) if isinstance(stored_backup, Mapping) else {}
            stored_scope = _decode(existing["scope_json"], {})
            if dict(stored_scope or {}) != dict(scope or {}):
                return {
                    "status": "blocked",
                    "reason": "idempotency_scope_mismatch",
                    "reprocessing_id": reprocessing_id,
                    "idempotency_key": idempotency_key,
                    "stored_scope": stored_scope,
                    "requested_scope": dict(scope or {}),
                }
            status = str(existing["status"] or "")
            if status == "completed":
                return {
                    "status": "completed",
                    "reprocessing_id": reprocessing_id,
                    "idempotency_key": idempotency_key,
                    "idempotent_replay": True,
                    "counts": _decode(existing["counts_json"], {}),
                    "backup": backup,
                    "rollback_reference": _rollback_reference(reprocessing_id=reprocessing_id, idempotency_key=idempotency_key, backup=backup),
                }
            if status == "running":
                age = _timestamp_age_seconds(existing["updated_at"])
                if age is None or age < stale_after_seconds:
                    return {
                        "status": "in_progress",
                        "reprocessing_id": reprocessing_id,
                        "idempotency_key": idempotency_key,
                        "message": "an active or recently-started process owns this run; resume after its checkpoint is stale",
                        "checkpoint": _decode(existing["checkpoint_json"], {}),
                        "counts": _decode(existing["counts_json"], {}),
                        "backup": backup,
                        "rollback_reference": _rollback_reference(reprocessing_id=reprocessing_id, idempotency_key=idempotency_key, backup=backup),
                    }
                expected_statuses = ("running",)
                expected_updated_at = str(existing["updated_at"] or "")
            elif status in {"planned", "incomplete", "failed"}:
                expected_statuses = (status,)
                expected_updated_at = ""
            else:
                return {
                    "status": "blocked",
                    "reason": "unsupported_reprocessing_status",
                    "reprocessing_id": reprocessing_id,
                    "current_status": status,
                }
        else:
            if environment.get("target_backend") == "sqlite":
                backup = _backup_local(Path(db_path), reprocessing_id)
                if backup.get("status") != "created":
                    return {
                        "status": "blocked",
                        "reason": "local_backup_unavailable",
                        "reprocessing_id": reprocessing_id,
                        "backup": backup,
                    }
            else:
                backup = {
                    "status": "transaction_safe_additive",
                    "recoverable": False,
                    "automatic_rollback": False,
                    "rollback_reference": {
                        "kind": "remote_additive_checkpoint",
                        "reprocessing_id": reprocessing_id,
                        "idempotency_key": idempotency_key,
                        "resume_from": "acquisition_reprocessing_runs.checkpoint_json",
                        "operator_action": "resume with the same idempotency key; do not delete observations or versions",
                    },
                }
            inserted = _start_run(connection, reprocessing_id=reprocessing_id, idempotency_key=idempotency_key, plan=plan, backup=backup)
            if inserted:
                expected_statuses = ("running",)
                expected_updated_at = ""
            else:
                existing = connection.execute(
                    "SELECT * FROM acquisition_reprocessing_runs WHERE reprocessing_id=? OR idempotency_key=? ORDER BY created_at DESC LIMIT 1",
                    (reprocessing_id, idempotency_key),
                ).fetchone()
                if existing is None:
                    raise RuntimeError("reprocessing run was not inserted and could not be reloaded")
                reprocessing_id = str(existing["reprocessing_id"])
                idempotency_key = str(existing["idempotency_key"] or idempotency_key)
                stored_backup = _decode(existing["backup_json"], {})
                backup = dict(stored_backup) if isinstance(stored_backup, Mapping) else dict(backup)
                status = str(existing["status"] or "")
                if status == "completed":
                    return {
                        "status": "completed",
                        "reprocessing_id": reprocessing_id,
                        "idempotency_key": idempotency_key,
                        "idempotent_replay": True,
                        "counts": _decode(existing["counts_json"], {}),
                        "backup": backup,
                        "rollback_reference": _rollback_reference(reprocessing_id=reprocessing_id, idempotency_key=idempotency_key, backup=backup),
                    }
                if status == "running":
                    return {
                        "status": "in_progress",
                        "reprocessing_id": reprocessing_id,
                        "idempotency_key": idempotency_key,
                        "message": "another process claimed this idempotency key",
                        "checkpoint": _decode(existing["checkpoint_json"], {}),
                        "counts": _decode(existing["counts_json"], {}),
                        "backup": backup,
                        "rollback_reference": _rollback_reference(reprocessing_id=reprocessing_id, idempotency_key=idempotency_key, backup=backup),
                    }
                expected_statuses = (status,) if status in {"planned", "incomplete", "failed"} else ()
                expected_updated_at = ""

        if not _claim_run(
            connection,
            reprocessing_id=reprocessing_id,
            lease_token=lease_token,
            lease_seconds=stale_after_seconds,
            expected_statuses=expected_statuses,
            expected_updated_at=expected_updated_at,
        ):
            latest = connection.execute(
                "SELECT status, checkpoint_json, counts_json FROM acquisition_reprocessing_runs WHERE reprocessing_id=?",
                (reprocessing_id,),
            ).fetchone()
            return {
                "status": "in_progress",
                "reprocessing_id": reprocessing_id,
                "idempotency_key": idempotency_key,
                "message": "another process owns or reclaimed this reprocessing run",
                "checkpoint": _decode(latest["checkpoint_json"], {}) if latest else {},
                "counts": _decode(latest["counts_json"], {}) if latest else {},
                "backup": backup,
                "rollback_reference": _rollback_reference(reprocessing_id=reprocessing_id, idempotency_key=idempotency_key, backup=backup),
            }

    assert backup is not None
    totals: dict[str, int] = {
        "observations": 0,
        "historical_repairs": 0,
        "warnings": 0,
        "fields": 0,
        "batches": 0,
        "duplicate_clusters": 0,
        "failed_observations": 0,
        "failure_references": 0,
    }
    checkpoint = ""
    failed_observation_ids: list[str] = []
    with database_session(db_path) as connection:
        state = connection.execute(
            "SELECT status, lease_token, checkpoint_json, counts_json, backup_json FROM acquisition_reprocessing_runs WHERE reprocessing_id=?",
            (reprocessing_id,),
        ).fetchone()
        if state is not None:
            if str(state["status"] or "") != "running" or str(state["lease_token"] or "") != lease_token:
                raise ReprocessingLeaseLost("reprocessing lease was not retained after claim")
            checkpoint_payload = _decode(state["checkpoint_json"], {}) or {}
            checkpoint = str(checkpoint_payload.get("last_observation_id") or "")
            failed_observation_ids = [str(item) for item in checkpoint_payload.get("failed_observation_ids") or [] if str(item)]
            totals.update({key: _as_int(value) for key, value in (_decode(state["counts_json"], {}) or {}).items() if key in totals})
            stored_backup = _decode(state["backup_json"], {})
            if isinstance(stored_backup, Mapping):
                backup = dict(stored_backup)
    batches_this_call = 0
    retry_failed = bool(failed_observation_ids)
    try:
        while True:
            if batches_this_call >= max_batches:
                with database_session(db_path) as connection:
                    connection.execute(
                        "UPDATE acquisition_reprocessing_runs SET status='incomplete', counts_json=?, error_json=?, lease_token='', lease_expires_at='', updated_at=? WHERE reprocessing_id=? AND status='running' AND lease_token=?",
                        (_json(totals), _json({"type": "batch_limit_reached", "max_batches": max_batches, "resume_required": True}), _now(), reprocessing_id, lease_token),
                    )
                return {
                    "status": "incomplete",
                    "reason": "batch_limit_reached",
                    "reprocessing_id": reprocessing_id,
                    "idempotency_key": idempotency_key,
                    "counts": totals,
                    "checkpoint": {"last_observation_id": checkpoint, "failed_observation_ids": failed_observation_ids},
                    "batches_this_call": batches_this_call,
                    "resume_required": True,
                    "plan": plan,
                    "backup": backup,
                    "rollback_reference": _rollback_reference(reprocessing_id=reprocessing_id, idempotency_key=idempotency_key, backup=backup),
                }
            with database_session(db_path) as connection:
                if connection.backend == "libsql":
                    # Remote batches use a replayable batch transaction first;
                    # a failing batch automatically falls back to one atomic
                    # transaction per observation so failures stay report-only.
                    batch = _process_batch(
                        connection,
                        checkpoint=checkpoint,
                        batch_size=batch_size,
                        execution_id=reprocessing_id,
                        totals=totals,
                        failed_observation_ids=failed_observation_ids,
                        retry_failed=retry_failed,
                        lease_token=lease_token,
                        lease_seconds=stale_after_seconds,
                    )
                else:
                    batch = connection.transaction(
                        lambda transaction_connection: _process_batch(
                            transaction_connection,
                            checkpoint=checkpoint,
                            batch_size=batch_size,
                            execution_id=reprocessing_id,
                            totals=totals,
                            failed_observation_ids=failed_observation_ids,
                            retry_failed=retry_failed,
                            lease_token=lease_token,
                            lease_seconds=stale_after_seconds,
                        )
                    )
                if batch is None:
                    break
                checkpoint, _, next_totals, failed_observation_ids = batch
                totals = next_totals
                batches_this_call += 1
                retry_failed = False
    except ReprocessingLeaseLost as exc:
        return {
            "status": "in_progress",
            "reprocessing_id": reprocessing_id,
            "idempotency_key": idempotency_key,
            "message": str(exc),
            "checkpoint": {"last_observation_id": checkpoint, "failed_observation_ids": failed_observation_ids},
            "counts": totals,
            "resume_required": True,
            "plan": plan,
            "backup": backup,
            "rollback_reference": _rollback_reference(reprocessing_id=reprocessing_id, idempotency_key=idempotency_key, backup=backup),
        }
    except Exception as exc:
        with database_session(db_path) as connection:
            connection.execute(
                "UPDATE acquisition_reprocessing_runs SET status='failed', counts_json=?, error_json=?, lease_token='', lease_expires_at='', updated_at=? WHERE reprocessing_id=? AND status='running' AND lease_token=?",
                (_json(totals), _json({"type": type(exc).__name__, "message": str(exc), "report_only": True, "resume_required": True}), _now(), reprocessing_id, lease_token),
            )
        return {
            "status": "failed",
            "reprocessing_id": reprocessing_id,
            "idempotency_key": idempotency_key,
            "counts": totals,
            "checkpoint": {"last_observation_id": checkpoint, "failed_observation_ids": failed_observation_ids},
            "error": {"type": type(exc).__name__, "message": str(exc), "resume_required": True},
            "plan": plan,
            "backup": backup,
            "rollback_reference": _rollback_reference(reprocessing_id=reprocessing_id, idempotency_key=idempotency_key, backup=backup),
        }
    if failed_observation_ids:
        with database_session(db_path) as connection:
            connection.execute(
                "UPDATE acquisition_reprocessing_runs SET status='incomplete', counts_json=?, error_json=?, lease_token='', lease_expires_at='', updated_at=? WHERE reprocessing_id=? AND status='running' AND lease_token=?",
                (_json(totals), _json({"type": "observation_failures_pending", "failed_observations": failed_observation_ids, "resume_required": True}), _now(), reprocessing_id, lease_token),
            )
        return {
            "status": "incomplete",
            "reason": "observation_failures_pending",
            "reprocessing_id": reprocessing_id,
            "idempotency_key": idempotency_key,
            "counts": totals,
            "checkpoint": {"last_observation_id": checkpoint, "failed_observation_ids": failed_observation_ids},
            "batches_this_call": batches_this_call,
            "resume_required": True,
            "plan": plan,
            "backup": backup,
            "rollback_reference": _rollback_reference(reprocessing_id=reprocessing_id, idempotency_key=idempotency_key, backup=backup),
        }
    try:
        with database_session(db_path) as connection:
            def finalize(transaction_connection):
                now = _now()
                totals["duplicate_clusters"] = _store_duplicate_candidates(
                    transaction_connection, rule_version=UNIFIED_RULE_VERSION, now=now
                )
                for stage in ("source_registry", "immutable_observation", "identity_resolution", "publication_read_model"):
                    _stage(transaction_connection, reprocessing_id, stage, status="report_only", metrics={"mode": "reprocessing"})
                _stage(
                    transaction_connection, reprocessing_id, "identity_resolution", status="report_only",
                    metrics={"duplicate_clusters": totals["duplicate_clusters"], "automatic_merge": False},
                )
                _stage(
                    transaction_connection, reprocessing_id, "publication_read_model", status="report_only",
                    metrics={"automatic_promotion": False},
                )
                transaction_connection.execute(
                    "UPDATE acquisition_reprocessing_runs SET status='completed', counts_json=?, completed_at=?, lease_token='', lease_expires_at='', updated_at=? WHERE reprocessing_id=? AND status='running' AND lease_token=?",
                    (_json(totals), now, now, reprocessing_id, lease_token),
                )
                if transaction_connection.execute("SELECT changes()").fetchone()[0] != 1:
                    raise ReprocessingLeaseLost("reprocessing lease was lost during finalization")

            connection.transaction(finalize)
    except ReprocessingLeaseLost as exc:
        return {
            "status": "in_progress",
            "reprocessing_id": reprocessing_id,
            "idempotency_key": idempotency_key,
            "message": str(exc),
            "checkpoint": {"last_observation_id": checkpoint, "failed_observation_ids": failed_observation_ids},
            "counts": totals,
            "resume_required": True,
            "plan": plan,
            "backup": backup,
            "rollback_reference": _rollback_reference(reprocessing_id=reprocessing_id, idempotency_key=idempotency_key, backup=backup),
        }
    except Exception as exc:
        with database_session(db_path) as connection:
            connection.execute(
                "UPDATE acquisition_reprocessing_runs SET status='failed', counts_json=?, error_json=?, lease_token='', lease_expires_at='', updated_at=? WHERE reprocessing_id=? AND status='running' AND lease_token=?",
                (_json(totals), _json({"type": type(exc).__name__, "message": str(exc), "stage": "duplicate_or_finalize", "resume_required": True}), _now(), reprocessing_id, lease_token),
            )
        return {
            "status": "failed",
            "reprocessing_id": reprocessing_id,
            "idempotency_key": idempotency_key,
            "counts": totals,
            "checkpoint": {"last_observation_id": checkpoint, "failed_observation_ids": failed_observation_ids},
            "error": {"type": type(exc).__name__, "message": str(exc), "stage": "duplicate_or_finalize", "resume_required": True},
            "plan": plan,
            "backup": backup,
            "rollback_reference": _rollback_reference(reprocessing_id=reprocessing_id, idempotency_key=idempotency_key, backup=backup),
        }
    return {
        "status": "completed",
        "reprocessing_id": reprocessing_id,
        "idempotency_key": idempotency_key,
        "rule_version": UNIFIED_RULE_VERSION,
        "counts": totals,
        "plan": plan,
        "backup": backup,
        "rollback_reference": _rollback_reference(reprocessing_id=reprocessing_id, idempotency_key=idempotency_key, backup=backup),
    }


__all__ = ["DEFAULT_MAX_BATCHES", "DEFAULT_STALE_RUN_SECONDS", "MAX_BATCH_SIZE", "STAGES", "UNIFIED_RULE_VERSION", "build_reprocessing_plan", "run_reprocessing"]
