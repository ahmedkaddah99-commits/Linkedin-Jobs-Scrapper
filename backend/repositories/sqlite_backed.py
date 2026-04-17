from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from backend.domain.models import (
    RUN_STATUS_CANCEL_REQUESTED,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    ApiTokenRecord,
    ArtifactRecord,
    JobRecord,
    ReviewRecord,
    RunPlan,
    RunRecord,
    SecretRecord,
    StageResult,
    UserRecord,
    WorkerRecord,
    WorkflowTemplate,
    WorkspaceDefinition,
    utc_now_iso,
)
from backend.orchestration.seeded_workspaces import DEFAULT_WORKFLOW_TEMPLATES, DEFAULT_WORKSPACES


def _serialize(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _deserialize(payload: str | bytes | None, default: Any):
    if payload in (None, ""):
        return default
    try:
        return json.loads(payload)
    except Exception:
        return default


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


def _ensure_run_column(connection: sqlite3.Connection, column_name: str, column_sql: str) -> None:
    if column_name not in _table_columns(connection, "runs"):
        connection.execute(f"ALTER TABLE runs ADD COLUMN {column_name} {column_sql}")


def _apply_runtime_migration(connection: sqlite3.Connection) -> None:
    _ensure_run_column(connection, "requested_by", "TEXT NOT NULL DEFAULT ''")
    _ensure_run_column(connection, "queued_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_run_column(connection, "started_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_run_column(connection, "finished_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_run_column(connection, "current_stage_id", "TEXT NOT NULL DEFAULT ''")
    _ensure_run_column(connection, "last_error", "TEXT NOT NULL DEFAULT ''")
    _ensure_run_column(connection, "attempt_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_run_column(connection, "max_attempts", "INTEGER NOT NULL DEFAULT 1")
    _ensure_run_column(connection, "run_input_overrides_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_run_column(connection, "run_plan_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_run_column(connection, "metadata_json", "TEXT NOT NULL DEFAULT '{}'")

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS run_stage_results (
            run_id TEXT NOT NULL,
            sequence_no INTEGER NOT NULL,
            stage_id TEXT NOT NULL,
            stage_type TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            error TEXT NOT NULL DEFAULT '',
            metrics_json TEXT NOT NULL DEFAULT '{}',
            output_keys_json TEXT NOT NULL DEFAULT '[]',
            artifact_ids_json TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (run_id, sequence_no)
        );
        CREATE TABLE IF NOT EXISTS run_jobs (
            run_id TEXT NOT NULL,
            set_key TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            job_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            company TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL DEFAULT '',
            filter_status TEXT NOT NULL DEFAULT '',
            location_raw TEXT NOT NULL DEFAULT '',
            link TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            apply_link TEXT NOT NULL DEFAULT '',
            portal TEXT NOT NULL DEFAULT '',
            description_text TEXT NOT NULL DEFAULT '',
            manual_approved INTEGER NOT NULL DEFAULT 0,
            role_category_id TEXT NOT NULL DEFAULT '',
            role_category_name TEXT NOT NULL DEFAULT '',
            priority_rank INTEGER,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (run_id, set_key, ordinal)
        );
        CREATE TABLE IF NOT EXISTS workers (
            worker_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            host_name TEXT NOT NULL DEFAULT '',
            process_id INTEGER NOT NULL DEFAULT 0,
            current_run_id TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL,
            last_heartbeat_at TEXT NOT NULL,
            lease_expires_at TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_run_stage_results_run_sequence ON run_stage_results(run_id, sequence_no);
        CREATE INDEX IF NOT EXISTS idx_run_jobs_run_key_ordinal ON run_jobs(run_id, set_key, ordinal);
        CREATE INDEX IF NOT EXISTS idx_run_jobs_run_job_id ON run_jobs(run_id, job_id);
        CREATE INDEX IF NOT EXISTS idx_workers_status_lease ON workers(status, lease_expires_at);
        """
    )


class _SqliteStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    migration_id TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_templates (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    workflow_template_id TEXT NOT NULL,
                    workspace_type TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(workflow_template_id) REFERENCES workflow_templates(id)
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    workflow_template_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    queued_at TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT '',
                    current_stage_id TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT '',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 1,
                    run_input_overrides_json TEXT NOT NULL DEFAULT '{}',
                    run_plan_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_job_sets (
                    run_id TEXT NOT NULL,
                    set_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, set_key)
                );
                CREATE TABLE IF NOT EXISTS run_blobs (
                    run_id TEXT NOT NULL,
                    blob_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, blob_key)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    run_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    path TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, artifact_id)
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    review_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL,
                    is_active INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS api_tokens (
                    token_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_prefix TEXT NOT NULL,
                    is_active INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS secrets (
                    secret_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runs_updated_at ON runs(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_runs_status_updated_at ON runs(status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_runs_workspace_updated_at ON runs(workspace_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_workspaces_template_id ON workspaces(workflow_template_id);
                CREATE INDEX IF NOT EXISTS idx_reviews_run_updated_at ON reviews(run_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                CREATE INDEX IF NOT EXISTS idx_api_tokens_user_id ON api_tokens(user_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_secrets_workspace_id ON secrets(workspace_id, updated_at DESC);
                """
            )
            applied = {
                str(row["migration_id"])
                for row in connection.execute("SELECT migration_id FROM schema_migrations").fetchall()
            }
            if "001_runtime_normalization" not in applied:
                _apply_runtime_migration(connection)
                connection.execute(
                    "INSERT INTO schema_migrations (migration_id, applied_at) VALUES (?, ?)",
                    ("001_runtime_normalization", utc_now_iso()),
                )


class SqliteWorkspaceRepository(_SqliteStore):
    def __init__(
        self,
        db_path: Path,
        *,
        seeded_templates: Iterable[WorkflowTemplate] | None = None,
        seeded_workspaces: Iterable[WorkspaceDefinition] | None = None,
    ):
        self._seeded_templates = list(seeded_templates or DEFAULT_WORKFLOW_TEMPLATES)
        self._seeded_workspaces = list(seeded_workspaces or DEFAULT_WORKSPACES)
        super().__init__(db_path)
        self._ensure_seed_data()

    def _ensure_seed_data(self) -> None:
        with self._connect() as connection:
            template_count = connection.execute("SELECT COUNT(*) FROM workflow_templates").fetchone()[0]
            if template_count == 0:
                now = utc_now_iso()
                connection.executemany(
                    "INSERT INTO workflow_templates (id, name, description, payload_json, updated_at) VALUES (?, ?, ?, ?, ?)",
                    [
                        (item.id, item.name, item.description, _serialize(item.to_dict()), now)
                        for item in self._seeded_templates
                    ],
                )
            workspace_count = connection.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0]
            if workspace_count == 0:
                now = utc_now_iso()
                connection.executemany(
                    (
                        "INSERT INTO workspaces "
                        "(id, name, workflow_template_id, workspace_type, payload_json, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)"
                    ),
                    [
                        (
                            item.id,
                            item.name,
                            item.workflow_template_id,
                            item.workspace_type,
                            _serialize(item.to_dict()),
                            now,
                        )
                        for item in self._seeded_workspaces
                    ],
                )

    def list_workflow_templates(self) -> list[WorkflowTemplate]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM workflow_templates ORDER BY id").fetchall()
        return [WorkflowTemplate.from_dict(_deserialize(row["payload_json"], {})) for row in rows]

    def get_workflow_template(self, template_id: str) -> WorkflowTemplate:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM workflow_templates WHERE id = ?",
                (template_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Workflow template '{template_id}' not found.")
        return WorkflowTemplate.from_dict(_deserialize(row["payload_json"], {}))

    def upsert_workflow_template(self, workflow_template: WorkflowTemplate) -> None:
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO workflow_templates (id, name, description, payload_json, updated_at) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "name=excluded.name, description=excluded.description, "
                    "payload_json=excluded.payload_json, updated_at=excluded.updated_at"
                ),
                (
                    workflow_template.id,
                    workflow_template.name,
                    workflow_template.description,
                    _serialize(workflow_template.to_dict()),
                    utc_now_iso(),
                ),
            )

    def delete_workflow_template(self, template_id: str) -> None:
        with self._connect() as connection:
            row_count = connection.execute(
                "DELETE FROM workflow_templates WHERE id = ?",
                (template_id,),
            ).rowcount
        if row_count == 0:
            raise KeyError(f"Workflow template '{template_id}' not found.")

    def list_workspaces(self) -> list[WorkspaceDefinition]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM workspaces ORDER BY id").fetchall()
        return [WorkspaceDefinition.from_dict(_deserialize(row["payload_json"], {})) for row in rows]

    def get_workspace(self, workspace_id: str) -> WorkspaceDefinition:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM workspaces WHERE id = ?",
                (workspace_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Workspace '{workspace_id}' not found.")
        return WorkspaceDefinition.from_dict(_deserialize(row["payload_json"], {}))

    def upsert_workspace(self, workspace: WorkspaceDefinition) -> None:
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO workspaces "
                    "(id, name, workflow_template_id, workspace_type, payload_json, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "name=excluded.name, workflow_template_id=excluded.workflow_template_id, "
                    "workspace_type=excluded.workspace_type, payload_json=excluded.payload_json, "
                    "updated_at=excluded.updated_at"
                ),
                (
                    workspace.id,
                    workspace.name,
                    workspace.workflow_template_id,
                    workspace.workspace_type,
                    _serialize(workspace.to_dict()),
                    utc_now_iso(),
                ),
            )

    def delete_workspace(self, workspace_id: str) -> None:
        with self._connect() as connection:
            row_count = connection.execute(
                "DELETE FROM workspaces WHERE id = ?",
                (workspace_id,),
            ).rowcount
        if row_count == 0:
            raise KeyError(f"Workspace '{workspace_id}' not found.")


class SqliteRunRepository(_SqliteStore):
    def save(self, run: RunRecord) -> None:
        payload = run.to_dict()
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO runs ("
                    "id, workspace_id, workflow_template_id, status, requested_by, created_at, updated_at, "
                    "queued_at, started_at, finished_at, current_stage_id, last_error, attempt_count, max_attempts, "
                    "run_input_overrides_json, run_plan_json, metadata_json, payload_json"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "workspace_id=excluded.workspace_id, workflow_template_id=excluded.workflow_template_id, "
                    "status=excluded.status, requested_by=excluded.requested_by, created_at=excluded.created_at, "
                    "updated_at=excluded.updated_at, queued_at=excluded.queued_at, started_at=excluded.started_at, "
                    "finished_at=excluded.finished_at, current_stage_id=excluded.current_stage_id, "
                    "last_error=excluded.last_error, attempt_count=excluded.attempt_count, max_attempts=excluded.max_attempts, "
                    "run_input_overrides_json=excluded.run_input_overrides_json, run_plan_json=excluded.run_plan_json, "
                    "metadata_json=excluded.metadata_json, payload_json=excluded.payload_json"
                ),
                (
                    run.id,
                    run.workspace_id,
                    run.workflow_template_id,
                    run.status,
                    run.requested_by,
                    run.created_at,
                    run.updated_at,
                    run.queued_at,
                    run.started_at,
                    run.finished_at,
                    run.current_stage_id,
                    run.last_error,
                    int(run.attempt_count),
                    int(run.max_attempts),
                    _serialize(run.run_input_overrides),
                    _serialize(run.run_plan.to_dict() if run.run_plan else {}),
                    _serialize(run.metadata),
                    _serialize(payload),
                ),
            )
            connection.execute("DELETE FROM run_stage_results WHERE run_id = ?", (run.id,))
            if run.stage_results:
                connection.executemany(
                    (
                        "INSERT INTO run_stage_results ("
                        "run_id, sequence_no, stage_id, stage_type, status, started_at, finished_at, error, "
                        "metrics_json, output_keys_json, artifact_ids_json"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    [
                        (
                            run.id,
                            index,
                            result.stage_id,
                            result.stage_type,
                            result.status,
                            result.started_at,
                            result.finished_at,
                            result.error,
                            _serialize(result.metrics),
                            _serialize(result.output_keys),
                            _serialize(result.artifact_ids),
                        )
                        for index, result in enumerate(run.stage_results)
                    ],
                )

    def _run_from_row(self, row: sqlite3.Row, connection: sqlite3.Connection) -> RunRecord:
        payload = _deserialize(row["payload_json"], {})
        run = RunRecord.from_dict(payload if isinstance(payload, dict) else {})
        run.id = str(row["id"])
        run.workspace_id = str(row["workspace_id"])
        run.workflow_template_id = str(row["workflow_template_id"])
        run.status = str(row["status"])
        run.requested_by = str(row["requested_by"] or "")
        run.created_at = str(row["created_at"] or run.created_at)
        run.updated_at = str(row["updated_at"] or run.updated_at)
        run.queued_at = str(row["queued_at"] or "")
        run.started_at = str(row["started_at"] or "")
        run.finished_at = str(row["finished_at"] or "")
        run.current_stage_id = str(row["current_stage_id"] or "")
        run.last_error = str(row["last_error"] or "")
        run.attempt_count = int(row["attempt_count"] or 0)
        run.max_attempts = max(1, int(row["max_attempts"] or 1))
        run.run_input_overrides = dict(_deserialize(row["run_input_overrides_json"], run.run_input_overrides or {}))
        run_plan_payload = _deserialize(row["run_plan_json"], {})
        run.run_plan = RunPlan.from_dict(run_plan_payload) if isinstance(run_plan_payload, dict) and run_plan_payload else run.run_plan
        run.metadata = dict(_deserialize(row["metadata_json"], run.metadata or {}))
        stage_rows = connection.execute(
            (
                "SELECT stage_id, stage_type, status, started_at, finished_at, error, metrics_json, "
                "output_keys_json, artifact_ids_json "
                "FROM run_stage_results WHERE run_id = ? ORDER BY sequence_no"
            ),
            (run.id,),
        ).fetchall()
        if stage_rows:
            run.stage_results = [
                StageResult(
                    stage_id=str(stage_row["stage_id"]),
                    stage_type=str(stage_row["stage_type"]),
                    status=str(stage_row["status"]),
                    started_at=str(stage_row["started_at"]),
                    finished_at=str(stage_row["finished_at"]),
                    error=str(stage_row["error"] or ""),
                    metrics=dict(_deserialize(stage_row["metrics_json"], {})),
                    output_keys=[str(item) for item in _deserialize(stage_row["output_keys_json"], []) if str(item).strip()],
                    artifact_ids=[str(item) for item in _deserialize(stage_row["artifact_ids_json"], []) if str(item).strip()],
                )
                for stage_row in stage_rows
            ]
        return run

    def get(self, run_id: str) -> RunRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(f"Run '{run_id}' not found.")
            return self._run_from_row(row, connection)

    def list_runs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str = "",
        workspace_id: str = "",
    ) -> list[RunRecord]:
        query = "SELECT * FROM runs"
        where_parts: list[str] = []
        params: list[Any] = []
        if status:
            where_parts.append("status = ?")
            params.append(status)
        if workspace_id:
            where_parts.append("workspace_id = ?")
            params.append(workspace_id)
        if where_parts:
            query += " WHERE " + " AND ".join(where_parts)
        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, int(limit)), max(0, int(offset))])
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
            return [self._run_from_row(row, connection) for row in rows]

    def claim_next_queued(self) -> RunRecord | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                (
                    "SELECT * FROM runs "
                    "WHERE status = ? "
                    "ORDER BY CASE WHEN queued_at = '' THEN updated_at ELSE queued_at END ASC, created_at ASC "
                    "LIMIT 1"
                ),
                (RUN_STATUS_QUEUED,),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            run = self._run_from_row(row, connection)
            now = utc_now_iso()
            run.status = RUN_STATUS_RUNNING
            run.started_at = now
            run.updated_at = now
            run.attempt_count += 1
            connection.execute(
                (
                    "UPDATE runs SET status = ?, started_at = ?, updated_at = ?, attempt_count = ?, payload_json = ? "
                    "WHERE id = ?"
                ),
                (run.status, run.started_at, run.updated_at, run.attempt_count, _serialize(run.to_dict()), run.id),
            )
            connection.commit()
            return run

    def delete(self, run_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM run_stage_results WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM run_jobs WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM run_job_sets WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM run_blobs WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM artifacts WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM reviews WHERE run_id = ?", (run_id,))
            row_count = connection.execute("DELETE FROM runs WHERE id = ?", (run_id,)).rowcount
        if row_count == 0:
            raise KeyError(f"Run '{run_id}' not found.")


class SqliteJobStore(_SqliteStore):
    def save_job_set(self, run_id: str, key: str, jobs: list[JobRecord]) -> None:
        payload = [job.to_dict() for job in jobs]
        now = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO run_job_sets (run_id, set_key, payload_json, updated_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(run_id, set_key) DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at"
                ),
                (run_id, key, _serialize(payload), now),
            )
            connection.execute("DELETE FROM run_jobs WHERE run_id = ? AND set_key = ?", (run_id, key))
            if jobs:
                connection.executemany(
                    (
                        "INSERT INTO run_jobs ("
                        "run_id, set_key, ordinal, job_id, title, company, source_type, filter_status, location_raw, "
                        "link, source_url, apply_link, portal, description_text, manual_approved, role_category_id, "
                        "role_category_name, priority_rank, payload_json, updated_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    [
                        (
                            run_id,
                            key,
                            index,
                            job.job_id,
                            job.title,
                            job.company,
                            job.source_type,
                            job.filter_status,
                            job.location_raw,
                            job.link,
                            job.source_url,
                            job.apply_link,
                            job.portal,
                            job.description_text,
                            1 if job.manual_approved else 0,
                            job.role_category_id,
                            job.role_category_name,
                            job.priority_rank,
                            _serialize(job.to_dict()),
                            now,
                        )
                        for index, job in enumerate(jobs)
                    ],
                )

    def load_job_set(self, run_id: str, key: str) -> list[JobRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM run_jobs WHERE run_id = ? AND set_key = ? ORDER BY ordinal",
                (run_id, key),
            ).fetchall()
            if rows:
                return [JobRecord.from_mapping(_deserialize(row["payload_json"], {})) for row in rows]
            row = connection.execute(
                "SELECT payload_json FROM run_job_sets WHERE run_id = ? AND set_key = ?",
                (run_id, key),
            ).fetchone()
        if row is None:
            return []
        payload = _deserialize(row["payload_json"], [])
        return [JobRecord.from_mapping(item) for item in payload if isinstance(item, dict)]

    def list_job_set_keys(self, run_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                (
                    "SELECT DISTINCT set_key FROM ("
                    "SELECT set_key FROM run_job_sets WHERE run_id = ? "
                    "UNION ALL "
                    "SELECT set_key FROM run_jobs WHERE run_id = ?"
                    ") ORDER BY set_key"
                ),
                (run_id, run_id),
            ).fetchall()
        return [str(row["set_key"]) for row in rows]

    def load_all_job_sets(self, run_id: str) -> dict[str, list[JobRecord]]:
        return {key: self.load_job_set(run_id, key) for key in self.list_job_set_keys(run_id)}

    def delete_job_set(self, run_id: str, key: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM run_job_sets WHERE run_id = ? AND set_key = ?", (run_id, key))
            connection.execute("DELETE FROM run_jobs WHERE run_id = ? AND set_key = ?", (run_id, key))

    def save_blob(self, run_id: str, key: str, value: Any) -> None:
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO run_blobs (run_id, blob_key, payload_json, updated_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(run_id, blob_key) DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at"
                ),
                (run_id, key, _serialize(value), utc_now_iso()),
            )

    def load_blob(self, run_id: str, key: str, default=None):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM run_blobs WHERE run_id = ? AND blob_key = ?",
                (run_id, key),
            ).fetchone()
        if row is None:
            return default
        return _deserialize(row["payload_json"], default)

    def list_blob_keys(self, run_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT blob_key FROM run_blobs WHERE run_id = ? ORDER BY blob_key",
                (run_id,),
            ).fetchall()
        return [str(row["blob_key"]) for row in rows]

    def load_all_blobs(self, run_id: str) -> dict[str, Any]:
        return {key: self.load_blob(run_id, key, None) for key in self.list_blob_keys(run_id)}

    def delete_blob(self, run_id: str, key: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM run_blobs WHERE run_id = ? AND blob_key = ?",
                (run_id, key),
            )

    def clear_run(self, run_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM run_job_sets WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM run_jobs WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM run_blobs WHERE run_id = ?", (run_id,))


class SqliteArtifactStore(_SqliteStore):
    def save_artifacts(self, run_id: str, artifacts: list[ArtifactRecord]) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM artifacts WHERE run_id = ?", (run_id,))
            connection.executemany(
                "INSERT INTO artifacts (run_id, artifact_id, artifact_type, path, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        run_id,
                        artifact.artifact_id,
                        artifact.artifact_type,
                        artifact.path,
                        _serialize(artifact.metadata),
                        utc_now_iso(),
                    )
                    for artifact in artifacts
                ],
            )

    def load_artifacts(self, run_id: str) -> list[ArtifactRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT artifact_id, artifact_type, path, metadata_json FROM artifacts WHERE run_id = ? ORDER BY artifact_id",
                (run_id,),
            ).fetchall()
        return [
            ArtifactRecord(
                artifact_id=str(row["artifact_id"]),
                artifact_type=str(row["artifact_type"]),
                path=str(row["path"]),
                metadata=dict(_deserialize(row["metadata_json"], {})),
            )
            for row in rows
        ]

    def get_artifact(self, run_id: str, artifact_id: str) -> ArtifactRecord:
        with self._connect() as connection:
            row = connection.execute(
                (
                    "SELECT artifact_id, artifact_type, path, metadata_json "
                    "FROM artifacts WHERE run_id = ? AND artifact_id = ?"
                ),
                (run_id, artifact_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"Artifact '{artifact_id}' not found for run '{run_id}'.")
        return ArtifactRecord(
            artifact_id=str(row["artifact_id"]),
            artifact_type=str(row["artifact_type"]),
            path=str(row["path"]),
            metadata=dict(_deserialize(row["metadata_json"], {})),
        )

    def upsert_artifact(self, run_id: str, artifact: ArtifactRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO artifacts (run_id, artifact_id, artifact_type, path, metadata_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(run_id, artifact_id) DO UPDATE SET "
                    "artifact_type=excluded.artifact_type, path=excluded.path, metadata_json=excluded.metadata_json"
                ),
                (
                    run_id,
                    artifact.artifact_id,
                    artifact.artifact_type,
                    artifact.path,
                    _serialize(artifact.metadata),
                    utc_now_iso(),
                ),
            )

    def delete_artifact(self, run_id: str, artifact_id: str) -> None:
        with self._connect() as connection:
            row_count = connection.execute(
                "DELETE FROM artifacts WHERE run_id = ? AND artifact_id = ?",
                (run_id, artifact_id),
            ).rowcount
        if row_count == 0:
            raise KeyError(f"Artifact '{artifact_id}' not found for run '{run_id}'.")

    def clear_run(self, run_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM artifacts WHERE run_id = ?", (run_id,))


class SqliteReviewStore(_SqliteStore):
    def upsert_review(self, review: ReviewRecord) -> None:
        review.updated_at = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO reviews (review_id, run_id, job_id, status, updated_at, payload_json) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(review_id) DO UPDATE SET "
                    "run_id=excluded.run_id, job_id=excluded.job_id, status=excluded.status, "
                    "updated_at=excluded.updated_at, payload_json=excluded.payload_json"
                ),
                (
                    review.review_id,
                    review.run_id,
                    review.job_id,
                    review.status,
                    review.updated_at,
                    _serialize(review.to_dict()),
                ),
            )

    def get_review(self, review_id: str) -> ReviewRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM reviews WHERE review_id = ?",
                (review_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Review '{review_id}' not found.")
        return ReviewRecord.from_dict(_deserialize(row["payload_json"], {}))

    def list_reviews(
        self,
        *,
        run_id: str = "",
        job_id: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[ReviewRecord]:
        query = "SELECT payload_json FROM reviews"
        where_parts: list[str] = []
        params: list[Any] = []
        if run_id:
            where_parts.append("run_id = ?")
            params.append(run_id)
        if job_id:
            where_parts.append("job_id = ?")
            params.append(job_id)
        if where_parts:
            query += " WHERE " + " AND ".join(where_parts)
        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, int(limit)), max(0, int(offset))])
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [ReviewRecord.from_dict(_deserialize(row["payload_json"], {})) for row in rows]

    def delete_review(self, review_id: str) -> None:
        with self._connect() as connection:
            row_count = connection.execute(
                "DELETE FROM reviews WHERE review_id = ?",
                (review_id,),
            ).rowcount
        if row_count == 0:
            raise KeyError(f"Review '{review_id}' not found.")


class SqliteAuthRepository(_SqliteStore):
    def list_users(self) -> list[UserRecord]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM users ORDER BY email").fetchall()
        return [UserRecord.from_dict(_deserialize(row["payload_json"], {})) for row in rows]

    def get_user(self, user_id: str) -> UserRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT payload_json FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            raise KeyError(f"User '{user_id}' not found.")
        return UserRecord.from_dict(_deserialize(row["payload_json"], {}))

    def get_user_by_email(self, email: str) -> UserRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM users WHERE lower(email) = lower(?)",
                (email,),
            ).fetchone()
        if row is None:
            raise KeyError(f"User with email '{email}' not found.")
        return UserRecord.from_dict(_deserialize(row["payload_json"], {}))

    def upsert_user(self, user: UserRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO users (user_id, email, role, is_active, updated_at, payload_json) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(user_id) DO UPDATE SET "
                    "email=excluded.email, role=excluded.role, is_active=excluded.is_active, "
                    "updated_at=excluded.updated_at, payload_json=excluded.payload_json"
                ),
                (
                    user.user_id,
                    user.email,
                    user.role,
                    1 if user.is_active else 0,
                    utc_now_iso(),
                    _serialize(user.to_dict()),
                ),
            )

    def delete_user(self, user_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM api_tokens WHERE user_id = ?", (user_id,))
            row_count = connection.execute("DELETE FROM users WHERE user_id = ?", (user_id,)).rowcount
        if row_count == 0:
            raise KeyError(f"User '{user_id}' not found.")

    def list_api_tokens(
        self,
        *,
        user_id: str = "",
        active_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ApiTokenRecord]:
        query = "SELECT payload_json FROM api_tokens"
        where_parts: list[str] = []
        params: list[Any] = []
        if user_id:
            where_parts.append("user_id = ?")
            params.append(user_id)
        if active_only:
            where_parts.append("is_active = 1")
        if where_parts:
            query += " WHERE " + " AND ".join(where_parts)
        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, int(limit)), max(0, int(offset))])
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [ApiTokenRecord.from_dict(_deserialize(row["payload_json"], {})) for row in rows]

    def get_api_token(self, token_id: str) -> ApiTokenRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM api_tokens WHERE token_id = ?",
                (token_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"API token '{token_id}' not found.")
        return ApiTokenRecord.from_dict(_deserialize(row["payload_json"], {}))

    def upsert_api_token(self, token: ApiTokenRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO api_tokens (token_id, user_id, token_prefix, is_active, updated_at, payload_json) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(token_id) DO UPDATE SET "
                    "user_id=excluded.user_id, token_prefix=excluded.token_prefix, "
                    "is_active=excluded.is_active, updated_at=excluded.updated_at, payload_json=excluded.payload_json"
                ),
                (
                    token.token_id,
                    token.user_id,
                    token.token_prefix,
                    1 if token.is_active else 0,
                    utc_now_iso(),
                    _serialize(token.to_storage_dict()),
                ),
            )

    def delete_api_token(self, token_id: str) -> None:
        with self._connect() as connection:
            row_count = connection.execute("DELETE FROM api_tokens WHERE token_id = ?", (token_id,)).rowcount
        if row_count == 0:
            raise KeyError(f"API token '{token_id}' not found.")


class SqliteSecretStore(_SqliteStore):
    def list_secrets(self, *, workspace_id: str = "", limit: int = 100, offset: int = 0) -> list[SecretRecord]:
        query = "SELECT payload_json FROM secrets"
        params: list[Any] = []
        if workspace_id:
            query += " WHERE workspace_id IN ('', ?)"
            params.append(workspace_id)
        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, int(limit)), max(0, int(offset))])
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [SecretRecord.from_dict(_deserialize(row["payload_json"], {})) for row in rows]

    def get_secret(self, secret_id: str) -> SecretRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM secrets WHERE secret_id = ?",
                (secret_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Secret '{secret_id}' not found.")
        return SecretRecord.from_dict(_deserialize(row["payload_json"], {}))

    def upsert_secret(self, secret: SecretRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO secrets (secret_id, workspace_id, provider, updated_at, payload_json) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(secret_id) DO UPDATE SET "
                    "workspace_id=excluded.workspace_id, provider=excluded.provider, "
                    "updated_at=excluded.updated_at, payload_json=excluded.payload_json"
                ),
                (
                    secret.secret_id,
                    secret.workspace_id,
                    secret.provider,
                    utc_now_iso(),
                    _serialize(secret.to_storage_dict()),
                ),
            )

    def delete_secret(self, secret_id: str) -> None:
        with self._connect() as connection:
            row_count = connection.execute("DELETE FROM secrets WHERE secret_id = ?", (secret_id,)).rowcount
        if row_count == 0:
            raise KeyError(f"Secret '{secret_id}' not found.")


class SqliteWorkerStore(_SqliteStore):
    def list_workers(self, *, limit: int = 50, offset: int = 0, status: str = "") -> list[WorkerRecord]:
        query = "SELECT payload_json FROM workers"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY last_heartbeat_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, int(limit)), max(0, int(offset))])
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [WorkerRecord.from_dict(_deserialize(row["payload_json"], {})) for row in rows]

    def list_expired_workers(self, *, expires_before: str) -> list[WorkerRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                (
                    "SELECT payload_json FROM workers "
                    "WHERE lease_expires_at != '' AND lease_expires_at <= ? AND current_run_id != '' "
                    "ORDER BY lease_expires_at ASC"
                ),
                (expires_before,),
            ).fetchall()
        return [WorkerRecord.from_dict(_deserialize(row["payload_json"], {})) for row in rows]

    def get_worker(self, worker_id: str) -> WorkerRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM workers WHERE worker_id = ?",
                (worker_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Worker '{worker_id}' not found.")
        return WorkerRecord.from_dict(_deserialize(row["payload_json"], {}))

    def upsert_worker(self, worker: WorkerRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO workers ("
                    "worker_id, status, host_name, process_id, current_run_id, started_at, "
                    "last_heartbeat_at, lease_expires_at, metadata_json, payload_json"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(worker_id) DO UPDATE SET "
                    "status=excluded.status, host_name=excluded.host_name, process_id=excluded.process_id, "
                    "current_run_id=excluded.current_run_id, started_at=excluded.started_at, "
                    "last_heartbeat_at=excluded.last_heartbeat_at, lease_expires_at=excluded.lease_expires_at, "
                    "metadata_json=excluded.metadata_json, payload_json=excluded.payload_json"
                ),
                (
                    worker.worker_id,
                    worker.status,
                    worker.host_name,
                    int(worker.process_id),
                    worker.current_run_id,
                    worker.started_at,
                    worker.last_heartbeat_at,
                    worker.lease_expires_at,
                    _serialize(worker.metadata),
                    _serialize(worker.to_dict()),
                ),
            )

    def delete_worker(self, worker_id: str) -> None:
        with self._connect() as connection:
            row_count = connection.execute("DELETE FROM workers WHERE worker_id = ?", (worker_id,)).rowcount
        if row_count == 0:
            raise KeyError(f"Worker '{worker_id}' not found.")
