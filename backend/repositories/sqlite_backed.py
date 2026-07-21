from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from backend.domain.assisted_apply import (
    ASSISTED_APPLY_PREFERENCES_METADATA_KEY,
    ASSISTED_APPLY_STATUS_ACTIVE,
    ASSISTED_APPLY_STATUS_AUTHORIZED,
    ASSISTED_APPLY_STATUS_EXPIRED,
    ASSISTED_APPLY_STATUS_PENDING,
    ASSISTED_APPLY_STATUS_REJECTED,
    ASSISTED_APPLY_STATUS_REVOKED,
    AssistedApplyConnectionRecord,
    AssistedApplyPreferences,
)
from backend.domain.models import (
    RUN_STATUS_CANCEL_REQUESTED,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    WORKER_STATUS_RUNNING,
    WORKER_STATUS_STALE,
    ApiTokenRecord,
    CareerProfile,

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
from backend.domain.job_identity import canonicalize_url
from backend.orchestration.seeded_workspaces import DEFAULT_WORKFLOW_TEMPLATES, DEFAULT_WORKSPACES
from backend.repositories.sqlite_core import _SqliteStore
from backend.repositories.document_payloads import (
    prepare_run_payload,
    prepare_user_payload,
    prepare_workspace_payload,
)
from backend.repositories.sqlite_migrations import (
    _insert_application_status_history_row,
    _normalize_application_status_history_entry,
    _upsert_candidate_asset,
    _upsert_candidate_document,
)
from backend.security.auth import API_TOKEN_PREFIX_LENGTH

_SITE_STATES = {"hot", "selected", "low_yield", "paused", "pending"}


def _serialize(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _deserialize(payload: str | bytes | None, default: Any):
    if payload in (None, ""):
        return default
    try:
        return json.loads(payload)
    except Exception:
        return default


def _assisted_apply_connection_from_row(row) -> AssistedApplyConnectionRecord:
    return AssistedApplyConnectionRecord.from_dict({key: row[key] for key in row.keys()})


def _document_text(
    connection,
    *,
    document_id: str = "",
    asset_id: str = "",
    workspace_id: str = "",
) -> str:
    if document_id:
        row = connection.execute(
            "SELECT source_text FROM candidate_documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        if row is not None and str(row["source_text"] or ""):
            return str(row["source_text"])
    if asset_id:
        row = connection.execute(
            "SELECT source_text FROM candidate_documents WHERE asset_id = ? AND source_text != '' "
            "ORDER BY updated_at DESC LIMIT 1",
            (asset_id,),
        ).fetchone()
        if row is not None:
            return str(row["source_text"] or "")
    if workspace_id:
        row = connection.execute(
            """
            SELECT d.source_text
            FROM workspace_document_bindings b
            JOIN candidate_documents d ON d.document_id = b.document_id
            WHERE b.workspace_id = ? AND b.binding_key = 'workspace_cv'
            LIMIT 1
            """,
            (workspace_id,),
        ).fetchone()
        if row is not None:
            return str(row["source_text"] or "")
    return ""


def _hydrate_workspace_payload(connection, payload: Mapping[str, Any]) -> dict[str, Any]:
    hydrated = dict(payload)
    settings = dict(hydrated.get("settings") or {})
    if not str(settings.get("workspace_cv_text") or ""):
        text = _document_text(
            connection,
            document_id=str(settings.get("workspace_cv_document_id") or ""),
            asset_id=str(settings.get("workspace_cv_asset_id") or ""),
            workspace_id=str(hydrated.get("id") or ""),
        )
        if text:
            settings["workspace_cv_text"] = text
    hydrated["settings"] = settings
    return hydrated


def _hydrate_run_payload(connection, payload: Mapping[str, Any]) -> dict[str, Any]:
    hydrated = dict(payload)
    run_plan = dict(hydrated.get("run_plan") or {})
    resolved = dict(run_plan.get("resolved_run_settings") or {})
    snapshot = _hydrate_workspace_payload(connection, dict(run_plan.get("workspace_snapshot") or {}))
    asset_id = str(
        resolved.get("workspace_cv_asset_id")
        or dict(snapshot.get("settings") or {}).get("workspace_cv_asset_id")
        or ""
    )
    if not str(resolved.get("workspace_cv_text") or ""):
        text = _document_text(
            connection,
            document_id=str(resolved.get("workspace_cv_document_id") or ""),
            asset_id=asset_id,
            workspace_id=str(hydrated.get("workspace_id") or ""),
        )
        if not text:
            binding = connection.execute(
                "SELECT document_id FROM run_document_bindings "
                "WHERE run_id = ? AND binding_key = 'workspace_cv'",
                (str(hydrated.get("id") or ""),),
            ).fetchone()
            if binding is not None:
                text = _document_text(connection, document_id=str(binding["document_id"] or ""))
        if text:
            resolved["workspace_cv_text"] = text
    run_plan["resolved_run_settings"] = resolved
    if snapshot:
        run_plan["workspace_snapshot"] = snapshot
    hydrated["run_plan"] = run_plan
    return hydrated


def _hydrate_user_payload(connection, payload: Mapping[str, Any]) -> dict[str, Any]:
    hydrated = dict(payload)
    user_id = str(hydrated.get("user_id") or "")
    metadata = dict(hydrated.get("metadata") or {})
    rows = connection.execute(
        """
        SELECT 'asset' AS row_kind, asset_id AS key_1, '' AS key_2, '' AS key_3,
               updated_at AS key_4, payload_json AS payload
        FROM candidate_assets
        WHERE user_id = ?
        UNION ALL
        SELECT 'document' AS row_kind, document_id AS key_1, asset_id AS key_2,
               document_kind AS key_3, updated_at AS key_4, source_text AS payload
        FROM candidate_documents
        WHERE user_id = ?
        ORDER BY row_kind, key_4, key_1
        """,
        (user_id, user_id),
    ).fetchall()
    document_text_by_asset: dict[str, str] = {}
    document_text_by_id: dict[str, str] = {}
    latest_workspace_cv_text = ""
    asset_payloads: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        if str(row["row_kind"]) == "asset":
            asset_payloads.append(
                (str(row["key_1"] or ""), dict(_deserialize(row["payload"], {})))
            )
            continue
        source_text = str(row["payload"] or "")
        document_id = str(row["key_1"] or "")
        asset_id = str(row["key_2"] or "")
        if document_id and source_text:
            document_text_by_id[document_id] = source_text
        if asset_id and source_text:
            document_text_by_asset[asset_id] = source_text
        if str(row["key_3"] or "") == "workspace_cv" and source_text:
            latest_workspace_cv_text = source_text
    assets: list[dict[str, Any]] = []
    for asset_id, asset in asset_payloads:
        text = document_text_by_asset.get(asset_id, "")
        if text:
            asset_metadata = dict(asset.get("metadata") or {})
            asset_metadata["source_text"] = text
            asset["metadata"] = asset_metadata
        assets.append(asset)
    if assets:
        metadata["candidate_assets"] = assets
    if not str(metadata.get("cv_text") or ""):
        text = document_text_by_id.get(
            str(metadata.get("cv_document_id") or ""),
            latest_workspace_cv_text,
        )
        if text:
            metadata["cv_text"] = text
    hydrated["metadata"] = metadata
    return hydrated


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
            rows = connection.execute(
                "SELECT owner_user_id, payload_json FROM workspaces ORDER BY id"
            ).fetchall()
        workspaces = []
        for row in rows:
            payload = _deserialize(row["payload_json"], {})
            payload["owner_user_id"] = str(row["owner_user_id"] or payload.get("owner_user_id") or "")
            workspaces.append(WorkspaceDefinition.from_dict(payload))
        return workspaces

    def get_workspace(self, workspace_id: str) -> WorkspaceDefinition:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT owner_user_id, payload_json FROM workspaces WHERE id = ?",
                (workspace_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Workspace '{workspace_id}' not found.")
            payload = _hydrate_workspace_payload(connection, _deserialize(row["payload_json"], {}))
            payload["owner_user_id"] = str(row["owner_user_id"] or payload.get("owner_user_id") or "")
            return WorkspaceDefinition.from_dict(payload)

    def upsert_workspace(self, workspace: WorkspaceDefinition) -> None:
        payload, document = prepare_workspace_payload(workspace.to_dict())
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO workspaces "
                    "(id, name, workflow_template_id, owner_user_id, workspace_type, payload_json, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "name=excluded.name, workflow_template_id=excluded.workflow_template_id, "
                    "owner_user_id=excluded.owner_user_id, workspace_type=excluded.workspace_type, "
                    "payload_json=excluded.payload_json, "
                    "updated_at=excluded.updated_at"
                ),
                (
                    workspace.id,
                    workspace.name,
                    workspace.workflow_template_id,
                    workspace.owner_user_id,
                    workspace.workspace_type,
                    _serialize(payload),
                    utc_now_iso(),
                ),
            )
            if document is not None:
                _upsert_candidate_document(
                    connection,
                    {**document, "document_kind": "workspace_cv"},
                )
                connection.execute(
                    """
                    INSERT INTO workspace_document_bindings (
                        workspace_id, binding_key, document_id, asset_id, object_key, updated_at
                    ) VALUES (?, 'workspace_cv', ?, ?, ?, ?)
                    ON CONFLICT(workspace_id, binding_key) DO UPDATE SET
                        document_id=excluded.document_id,
                        asset_id=excluded.asset_id,
                        object_key=excluded.object_key,
                        updated_at=excluded.updated_at
                    """,
                    (
                        workspace.id,
                        document["document_id"],
                        document["asset_id"],
                        document["object_key"],
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
        with self._connect() as connection:
            connection.execute("DELETE FROM workspace_document_bindings WHERE workspace_id = ?", (workspace_id,))


class SqliteRunRepository(_SqliteStore):
    def save(self, run: RunRecord) -> None:
        run.user_id = run.normalized_user_id
        payload, document = prepare_run_payload(run.to_dict())
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO runs ("
                    "id, workspace_id, workflow_template_id, status, requested_by, user_id, created_at, updated_at, "
                    "queued_at, started_at, finished_at, current_stage_id, last_error, attempt_count, max_attempts, "
                    "run_input_overrides_json, run_plan_json, metadata_json, payload_json"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "workspace_id=excluded.workspace_id, workflow_template_id=excluded.workflow_template_id, "
                    "status=excluded.status, requested_by=excluded.requested_by, user_id=excluded.user_id, "
                    "created_at=excluded.created_at, "
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
                    run.user_id,
                    run.created_at,
                    run.updated_at,
                    run.queued_at,
                    run.started_at,
                    run.finished_at,
                    run.current_stage_id,
                    run.last_error,
                    int(run.attempt_count),
                    int(run.max_attempts),
                    _serialize(payload.get("run_input_overrides") or {}),
                    _serialize(payload.get("run_plan") or {}),
                    _serialize(payload.get("metadata") or {}),
                    _serialize(payload),
                ),
            )
            if document is not None:
                _upsert_candidate_document(
                    connection,
                    {**document, "document_kind": "workspace_cv"},
                )
                connection.execute(
                    """
                    INSERT INTO run_document_bindings (
                        run_id, binding_key, document_id, asset_id, object_key, updated_at
                    ) VALUES (?, 'workspace_cv', ?, ?, ?, ?)
                    ON CONFLICT(run_id, binding_key) DO UPDATE SET
                        document_id=excluded.document_id,
                        asset_id=excluded.asset_id,
                        object_key=excluded.object_key,
                        updated_at=excluded.updated_at
                    """,
                    (
                        run.id,
                        document["document_id"],
                        document["asset_id"],
                        document["object_key"],
                        utc_now_iso(),
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
                        " ON CONFLICT(run_id, sequence_no) DO UPDATE SET "
                        "stage_id=excluded.stage_id, stage_type=excluded.stage_type, status=excluded.status, "
                        "started_at=excluded.started_at, finished_at=excluded.finished_at, error=excluded.error, "
                        "metrics_json=excluded.metrics_json, output_keys_json=excluded.output_keys_json, "
                        "artifact_ids_json=excluded.artifact_ids_json"
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

    def save_recovery_transition_if_stale(
        self,
        run: RunRecord,
        *,
        expected_status: str,
        expected_updated_at: str,
        active_lease_after: str,
    ) -> bool:
        run.user_id = run.normalized_user_id
        payload, _document = prepare_run_payload(run.to_dict())

        def transition(connection) -> bool:
            row_count = connection.execute(
                (
                    "UPDATE runs SET status = ?, updated_at = ?, queued_at = ?, started_at = ?, "
                    "finished_at = ?, current_stage_id = ?, last_error = ?, metadata_json = ?, payload_json = ? "
                    "WHERE id = ? AND status = ? AND updated_at = ? "
                    "AND NOT EXISTS ("
                    "SELECT 1 FROM workers "
                    "WHERE current_run_id = runs.id "
                    "AND status NOT IN ('stale', 'stopped') "
                    "AND (COALESCE(lease_expires_at, '') = '' OR lease_expires_at > ?)"
                    ")"
                ),
                (
                    run.status,
                    run.updated_at,
                    run.queued_at,
                    run.started_at,
                    run.finished_at,
                    run.current_stage_id,
                    run.last_error,
                    _serialize(payload.get("metadata") or {}),
                    _serialize(payload),
                    run.id,
                    expected_status,
                    expected_updated_at,
                    active_lease_after,
                ),
            ).rowcount
            if row_count != 1:
                return False
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
            return True

        return self._run_transaction(transition)

    def _run_from_row(
        self,
        row,
        connection,
        *,
        hydrate_documents: bool = True,
        stage_rows: list | None = None,
    ) -> RunRecord:
        raw_payload = _deserialize(row["payload_json"], {})
        payload = _hydrate_run_payload(connection, raw_payload) if hydrate_documents else raw_payload
        run = RunRecord.from_dict(payload if isinstance(payload, dict) else {})
        run.id = str(row["id"])
        run.workspace_id = str(row["workspace_id"])
        run.workflow_template_id = str(row["workflow_template_id"])
        run.status = str(row["status"])
        run.requested_by = str(row["requested_by"] or "")
        run.user_id = str(row["user_id"] or "")
        run.user_id = run.normalized_user_id
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
        raw_run_plan_payload = _deserialize(row["run_plan_json"], {})
        run_plan_payload = (
            _hydrate_run_payload(
                connection,
                {
                    "id": run.id,
                    "workspace_id": run.workspace_id,
                    "run_plan": raw_run_plan_payload,
                },
            ).get("run_plan", {})
            if hydrate_documents
            else raw_run_plan_payload
        )
        run.run_plan = RunPlan.from_dict(run_plan_payload) if isinstance(run_plan_payload, dict) and run_plan_payload else run.run_plan
        run.metadata = dict(_deserialize(row["metadata_json"], run.metadata or {}))
        resolved_stage_rows = stage_rows
        if resolved_stage_rows is None:
            resolved_stage_rows = connection.execute(
                (
                    "SELECT stage_id, stage_type, status, started_at, finished_at, error, metrics_json, "
                    "output_keys_json, artifact_ids_json "
                    "FROM run_stage_results WHERE run_id = ? ORDER BY sequence_no"
                ),
                (run.id,),
            ).fetchall()
        if resolved_stage_rows:
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
                for stage_row in resolved_stage_rows
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
            run_ids = [str(row["id"]) for row in rows]
            stage_rows_by_run: dict[str, list] = {run_id: [] for run_id in run_ids}
            if run_ids:
                placeholders = ",".join("?" for _ in run_ids)
                stage_rows = connection.execute(
                    (
                        "SELECT run_id, stage_id, stage_type, status, started_at, finished_at, error, "
                        "metrics_json, output_keys_json, artifact_ids_json "
                        f"FROM run_stage_results WHERE run_id IN ({placeholders}) "
                        "ORDER BY run_id, sequence_no"
                    ),
                    tuple(run_ids),
                ).fetchall()
                for stage_row in stage_rows:
                    stage_rows_by_run.setdefault(str(stage_row["run_id"]), []).append(stage_row)
            return [
                self._run_from_row(
                    row,
                    connection,
                    hydrate_documents=False,
                    stage_rows=stage_rows_by_run.get(str(row["id"]), []),
                )
                for row in rows
            ]

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
            normalized_payload, _document = prepare_run_payload(run.to_dict())
            connection.execute(
                (
                    "UPDATE runs SET status = ?, started_at = ?, updated_at = ?, attempt_count = ?, payload_json = ? "
                    "WHERE id = ?"
                ),
                (
                    run.status,
                    run.started_at,
                    run.updated_at,
                    run.attempt_count,
                    _serialize(normalized_payload),
                    run.id,
                ),
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
            connection.execute("DELETE FROM run_document_bindings WHERE run_id = ?", (run_id,))
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
                        " ON CONFLICT(run_id, set_key, ordinal) DO UPDATE SET "
                        "job_id=excluded.job_id, title=excluded.title, company=excluded.company, "
                        "source_type=excluded.source_type, filter_status=excluded.filter_status, "
                        "location_raw=excluded.location_raw, link=excluded.link, source_url=excluded.source_url, "
                        "apply_link=excluded.apply_link, portal=excluded.portal, "
                        "description_text=excluded.description_text, manual_approved=excluded.manual_approved, "
                        "role_category_id=excluded.role_category_id, role_category_name=excluded.role_category_name, "
                        "priority_rank=excluded.priority_rank, payload_json=excluded.payload_json, "
                        "updated_at=excluded.updated_at"
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
        return self.load_job_sets_for_runs([run_id]).get(run_id, {})

    def load_job_sets_for_runs(self, run_ids: Iterable[str]) -> dict[str, dict[str, list[JobRecord]]]:
        return self.load_run_read_snapshot(run_ids)["job_sets"]

    def load_run_read_snapshot(
        self,
        run_ids: Iterable[str],
        *,
        include_artifacts: bool = False,
        include_reviews: bool = False,
        include_blobs: bool = False,
        preserve_job_sets: bool = True,
        review_jobs_only: bool = False,
    ) -> dict[str, dict]:
        normalized_run_ids = list(dict.fromkeys(str(run_id or "").strip() for run_id in run_ids))
        normalized_run_ids = [run_id for run_id in normalized_run_ids if run_id]
        job_sets_by_run: dict[str, dict[str, list[JobRecord]]] = {
            run_id: {} for run_id in normalized_run_ids
        }
        artifacts_by_run: dict[str, list[ArtifactRecord]] = {
            run_id: [] for run_id in normalized_run_ids
        }
        reviews_by_run: dict[str, list[ReviewRecord]] = {
            run_id: [] for run_id in normalized_run_ids
        }
        blobs_by_run: dict[str, dict[str, Any]] = {
            run_id: {} for run_id in normalized_run_ids
        }
        snapshot = {
            "job_sets": job_sets_by_run,
            "artifacts": artifacts_by_run,
            "reviews": reviews_by_run,
            "blobs": blobs_by_run,
        }
        if not normalized_run_ids:
            return snapshot
        placeholders = ",".join("?" for _ in normalized_run_ids)
        if preserve_job_sets:
            job_select = (
                "SELECT 'job_set' AS row_kind, run_id, set_key AS key_1, "
                "'' AS key_2, '' AS key_3, payload_json "
                f"FROM run_job_sets WHERE run_id IN ({placeholders})"
            )
        else:
            review_filter = (
                "AND EXISTS ("
                "SELECT 1 FROM reviews "
                "WHERE reviews.run_id = run_jobs.run_id AND reviews.job_id = run_jobs.job_id"
                ") "
                if review_jobs_only
                else ""
            )
            job_select = (
                "SELECT 'job' AS row_kind, run_id, job_id AS key_1, "
                "'' AS key_2, '' AS key_3, payload_json "
                "FROM run_jobs "
                f"WHERE run_id IN ({placeholders}) {review_filter}"
                "AND rowid = ("
                "SELECT candidate.rowid FROM run_jobs AS candidate "
                "WHERE candidate.run_id = run_jobs.run_id AND candidate.job_id = run_jobs.job_id "
                "ORDER BY candidate.updated_at DESC, candidate.rowid DESC LIMIT 1"
                ")"
            )
        select_parts = [job_select]
        parameters: list[str] = list(normalized_run_ids)
        if include_artifacts:
            select_parts.append(
                (
                    "SELECT 'artifact' AS row_kind, run_id, artifact_id AS key_1, "
                    "artifact_type AS key_2, path AS key_3, metadata_json AS payload_json "
                    f"FROM artifacts WHERE run_id IN ({placeholders})"
                )
            )
            parameters.extend(normalized_run_ids)
        if include_reviews:
            select_parts.append(
                (
                    "SELECT 'review' AS row_kind, run_id, '' AS key_1, "
                    "'' AS key_2, '' AS key_3, payload_json "
                    f"FROM reviews WHERE run_id IN ({placeholders})"
                )
            )
            parameters.extend(normalized_run_ids)
        if include_blobs:
            select_parts.append(
                (
                    "SELECT 'blob' AS row_kind, run_id, blob_key AS key_1, "
                    "'' AS key_2, '' AS key_3, payload_json "
                    f"FROM run_blobs WHERE run_id IN ({placeholders})"
                )
            )
            parameters.extend(normalized_run_ids)
        with self._connect() as connection:
            rows = connection.execute(
                " UNION ALL ".join(select_parts) + " ORDER BY run_id, row_kind, key_1",
                tuple(parameters),
            ).fetchall()
        for row in rows:
            row_kind = str(row["row_kind"])
            run_id = str(row["run_id"])
            if row_kind == "job_set":
                payload = _deserialize(row["payload_json"], [])
                job_sets_by_run.setdefault(run_id, {})[str(row["key_1"])] = [
                    JobRecord.from_mapping(item)
                    for item in payload
                    if isinstance(item, dict)
                ]
            elif row_kind == "job":
                job_sets_by_run.setdefault(run_id, {}).setdefault("__all__", []).append(
                    JobRecord.from_mapping(_deserialize(row["payload_json"], {}))
                )
            elif row_kind == "artifact":
                artifacts_by_run.setdefault(run_id, []).append(
                    ArtifactRecord(
                        artifact_id=str(row["key_1"]),
                        artifact_type=str(row["key_2"]),
                        path=str(row["key_3"]),
                        metadata=dict(_deserialize(row["payload_json"], {})),
                    )
                )
            elif row_kind == "review":
                reviews_by_run.setdefault(run_id, []).append(
                    ReviewRecord.from_dict(_deserialize(row["payload_json"], {}))
                )
            elif row_kind == "blob":
                blobs_by_run.setdefault(run_id, {})[str(row["key_1"])] = _deserialize(
                    row["payload_json"],
                    None,
                )
        for reviews in reviews_by_run.values():
            reviews.sort(key=lambda review: str(review.updated_at or ""), reverse=True)
        return snapshot

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
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT blob_key, payload_json FROM run_blobs WHERE run_id = ? ORDER BY blob_key",
                (run_id,),
            ).fetchall()
        return {
            str(row["blob_key"]): _deserialize(row["payload_json"], None)
            for row in rows
        }

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
                (
                    "INSERT INTO artifacts (run_id, artifact_id, artifact_type, path, metadata_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(run_id, artifact_id) DO UPDATE SET "
                    "artifact_type=excluded.artifact_type, path=excluded.path, "
                    "metadata_json=excluded.metadata_json, created_at=excluded.created_at"
                ),
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
        return self.load_artifacts_for_runs([run_id]).get(run_id, [])

    def load_artifacts_for_runs(self, run_ids: Iterable[str]) -> dict[str, list[ArtifactRecord]]:
        normalized_run_ids = list(dict.fromkeys(str(run_id or "").strip() for run_id in run_ids))
        normalized_run_ids = [run_id for run_id in normalized_run_ids if run_id]
        result: dict[str, list[ArtifactRecord]] = {
            run_id: [] for run_id in normalized_run_ids
        }
        if not normalized_run_ids:
            return result
        placeholders = ",".join("?" for _ in normalized_run_ids)
        with self._connect() as connection:
            rows = connection.execute(
                (
                    "SELECT run_id, artifact_id, artifact_type, path, metadata_json "
                    f"FROM artifacts WHERE run_id IN ({placeholders}) ORDER BY run_id, artifact_id"
                ),
                tuple(normalized_run_ids),
            ).fetchall()
        for row in rows:
            result.setdefault(str(row["run_id"]), []).append(ArtifactRecord(
                artifact_id=str(row["artifact_id"]),
                artifact_type=str(row["artifact_type"]),
                path=str(row["path"]),
                metadata=dict(_deserialize(row["metadata_json"], {})),
            ))
        return result

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
    def upsert_review(
        self,
        review: ReviewRecord,
        *,
        application_status_history: dict[str, Any] | None = None,
    ) -> None:
        review.updated_at = utc_now_iso()
        history_entry = None
        if application_status_history is not None:
            history_entry = _normalize_application_status_history_entry(
                review_id=application_status_history.get("review_id") or review.review_id,
                user_id=application_status_history.get("user_id"),
                from_status=application_status_history.get("from_status"),
                to_status=application_status_history.get("to_status"),
                changed_at=application_status_history.get("changed_at") or review.updated_at,
                source=application_status_history.get("source") or "manual",
            )
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
            if history_entry is not None:
                _insert_application_status_history_row(connection, history_entry)

    def append_application_status_history(
        self,
        *,
        review_id: str,
        user_id: str,
        from_status: str,
        to_status: str,
        changed_at: str = "",
        source: str = "manual",
    ) -> None:
        entry = _normalize_application_status_history_entry(
            review_id=review_id,
            user_id=user_id,
            from_status=from_status,
            to_status=to_status,
            changed_at=changed_at,
            source=source,
        )
        with self._connect() as connection:
            _insert_application_status_history_row(connection, entry)

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

    def list_reviews_for_runs(self, run_ids: Iterable[str]) -> dict[str, list[ReviewRecord]]:
        normalized_run_ids = list(dict.fromkeys(str(run_id or "").strip() for run_id in run_ids))
        normalized_run_ids = [run_id for run_id in normalized_run_ids if run_id]
        result: dict[str, list[ReviewRecord]] = {
            run_id: [] for run_id in normalized_run_ids
        }
        if not normalized_run_ids:
            return result
        placeholders = ",".join("?" for _ in normalized_run_ids)
        with self._connect() as connection:
            rows = connection.execute(
                (
                    "SELECT run_id, payload_json FROM reviews "
                    f"WHERE run_id IN ({placeholders}) ORDER BY run_id, updated_at DESC"
                ),
                tuple(normalized_run_ids),
            ).fetchall()
        for row in rows:
            result.setdefault(str(row["run_id"]), []).append(
                ReviewRecord.from_dict(_deserialize(row["payload_json"], {}))
            )
        return result

    def list_application_status_history(
        self,
        *,
        review_id: str = "",
        user_id: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT review_id, user_id, from_status, to_status, changed_at, source "
            "FROM application_status_history"
        )
        where_parts: list[str] = []
        params: list[Any] = []
        if review_id:
            where_parts.append("review_id = ?")
            params.append(review_id)
        if user_id:
            where_parts.append("user_id = ?")
            params.append(user_id)
        if where_parts:
            query += " WHERE " + " AND ".join(where_parts)
        query += " ORDER BY changed_at ASC, rowid ASC LIMIT ? OFFSET ?"
        params.extend([max(1, int(limit)), max(0, int(offset))])
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [{key: row[key] for key in row.keys()} for row in rows]

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
            return [
                UserRecord.from_dict(_hydrate_user_payload(connection, _deserialize(row["payload_json"], {})))
                for row in rows
            ]

    def get_user(self, user_id: str) -> UserRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT payload_json FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if row is None:
                raise KeyError(f"User '{user_id}' not found.")
            return UserRecord.from_dict(
                _hydrate_user_payload(connection, _deserialize(row["payload_json"], {}))
            )

    def get_user_by_email(self, email: str) -> UserRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM users WHERE lower(email) = lower(?)",
                (email,),
            ).fetchone()
            if row is None:
                raise KeyError(f"User with email '{email}' not found.")
            return UserRecord.from_dict(
                _hydrate_user_payload(connection, _deserialize(row["payload_json"], {}))
            )

    def get_user_by_clerk_user_id(self, clerk_user_id: str) -> UserRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM users WHERE clerk_user_id = ?",
                (str(clerk_user_id or "").strip(),),
            ).fetchone()
            if row is None:
                raise KeyError(f"User with Clerk user id '{clerk_user_id}' not found.")
            return UserRecord.from_dict(
                _hydrate_user_payload(connection, _deserialize(row["payload_json"], {}))
            )

    def get_user_clerk_user_id(self, user_id: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT clerk_user_id FROM users WHERE user_id = ?",
                (str(user_id or "").strip(),),
            ).fetchone()
        if row is None:
            raise KeyError(f"User '{user_id}' not found.")
        return str(row["clerk_user_id"] or "").strip()

    def set_user_clerk_user_id(self, user_id: str, clerk_user_id: str) -> None:
        with self._connect() as connection:
            row_count = connection.execute(
                "UPDATE users SET clerk_user_id = ?, updated_at = ? WHERE user_id = ?",
                (
                    str(clerk_user_id or "").strip(),
                    utc_now_iso(),
                    str(user_id or "").strip(),
                ),
            ).rowcount
        if row_count == 0:
            raise KeyError(f"User '{user_id}' not found.")

    def list_user_rows_for_clerk_migration(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT user_id, email, role, is_active, updated_at, clerk_user_id, payload_json FROM users ORDER BY email"
            ).fetchall()
        return [{key: row[key] for key in row.keys()} for row in rows]

    def upsert_user(self, user: UserRecord) -> None:
        payload, assets, documents = prepare_user_payload(user.to_dict())
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
                    _serialize(payload),
                ),
            )
            if assets is not None:
                asset_ids = [str(asset.get("asset_id") or "") for asset in assets if str(asset.get("asset_id") or "")]
                if asset_ids:
                    placeholders = ",".join("?" for _ in asset_ids)
                    connection.execute(
                        f"DELETE FROM candidate_assets WHERE user_id = ? AND asset_id NOT IN ({placeholders})",
                        (user.user_id, *asset_ids),
                    )
                else:
                    connection.execute("DELETE FROM candidate_assets WHERE user_id = ?", (user.user_id,))
                for asset in assets:
                    _upsert_candidate_asset(connection, user_id=user.user_id, asset=asset)
            for document in documents:
                _upsert_candidate_document(connection, document)

    def delete_user(self, user_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM api_tokens WHERE user_id = ?", (user_id,))
            connection.execute("DELETE FROM assisted_apply_connections WHERE user_id = ?", (user_id,))
            connection.execute("DELETE FROM candidate_assets WHERE user_id = ?", (user_id,))
            connection.execute("DELETE FROM candidate_documents WHERE user_id = ?", (user_id,))
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

    def list_api_tokens_for_value(self, raw_token: str, *, active_only: bool = False) -> list[ApiTokenRecord]:
        normalized_token = str(raw_token or "").strip()
        if not normalized_token:
            return []
        candidate_prefix = normalized_token[:API_TOKEN_PREFIX_LENGTH]
        query = "SELECT payload_json FROM api_tokens WHERE token_prefix = ?"
        params: list[Any] = [candidate_prefix]
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY updated_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
            if not rows:
                legacy_query = "SELECT payload_json FROM api_tokens WHERE ? LIKE token_prefix || '%'"
                legacy_params: list[Any] = [normalized_token]
                if active_only:
                    legacy_query += " AND is_active = 1"
                legacy_query += " ORDER BY updated_at DESC"
                rows = connection.execute(legacy_query, tuple(legacy_params)).fetchall()
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

    def create_assisted_apply_connection(self, record: AssistedApplyConnectionRecord) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO assisted_apply_connections (
                        request_id, status, user_id, extension_id, extension_origin,
                        callback_url, client_state, pkce_challenge, installation_id,
                        extension_version, request_expires_at,
                        authorization_code_prefix, authorization_code_hash,
                        authorization_code_expires_at, authorized_at, code_consumed_at,
                        session_token_prefix, session_token_hash, session_expires_at,
                        activated_at, last_used_at, rejected_at, revoked_at, expired_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.request_id,
                        record.status,
                        record.user_id,
                        record.extension_id,
                        record.extension_origin,
                        record.callback_url,
                        record.client_state,
                        record.pkce_challenge,
                        record.installation_id,
                        record.extension_version,
                        record.request_expires_at,
                        record.authorization_code_prefix,
                        record.authorization_code_hash,
                        record.authorization_code_expires_at,
                        record.authorized_at,
                        record.code_consumed_at,
                        record.session_token_prefix,
                        record.session_token_hash,
                        record.session_expires_at,
                        record.activated_at,
                        record.last_used_at,
                        record.rejected_at,
                        record.revoked_at,
                        record.expired_at,
                        record.created_at,
                        record.updated_at,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Assisted Apply connection '{record.request_id}' already exists."
            ) from exc

    def get_assisted_apply_connection(self, request_id: str) -> AssistedApplyConnectionRecord:
        normalized_request_id = str(request_id or "").strip()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM assisted_apply_connections WHERE request_id = ?",
                (normalized_request_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Assisted Apply connection '{normalized_request_id}' not found.")
        return _assisted_apply_connection_from_row(row)

    def list_assisted_apply_connections(
        self,
        *,
        user_id: str = "",
        status: str = "",
    ) -> list[AssistedApplyConnectionRecord]:
        query = "SELECT * FROM assisted_apply_connections"
        where_parts: list[str] = []
        params: list[Any] = []
        if user_id:
            where_parts.append("user_id = ?")
            params.append(str(user_id).strip())
        if status:
            where_parts.append("status = ?")
            params.append(str(status).strip())
        if where_parts:
            query += " WHERE " + " AND ".join(where_parts)
        query += " ORDER BY updated_at DESC, request_id DESC"
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [_assisted_apply_connection_from_row(row) for row in rows]

    def list_assisted_apply_connections_for_session_prefix(
        self,
        session_token_prefix: str,
    ) -> list[AssistedApplyConnectionRecord]:
        normalized_prefix = str(session_token_prefix or "").strip()
        if not normalized_prefix:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM assisted_apply_connections "
                "WHERE session_token_prefix = ? AND status = ? ORDER BY updated_at DESC",
                (normalized_prefix, ASSISTED_APPLY_STATUS_ACTIVE),
            ).fetchall()
        return [_assisted_apply_connection_from_row(row) for row in rows]

    def authorize_assisted_apply_connection(
        self,
        request_id: str,
        *,
        user_id: str,
        authorization_code_prefix: str,
        authorization_code_hash: str,
        authorization_code_expires_at: str,
        authorized_at: str,
    ) -> AssistedApplyConnectionRecord | None:
        with self._connect() as connection:
            row_count = connection.execute(
                """
                UPDATE assisted_apply_connections
                SET status = ?, user_id = ?, authorization_code_prefix = ?,
                    authorization_code_hash = ?, authorization_code_expires_at = ?,
                    authorized_at = ?, updated_at = ?
                WHERE request_id = ? AND status = ? AND user_id = ''
                    AND request_expires_at > ?
                """,
                (
                    ASSISTED_APPLY_STATUS_AUTHORIZED,
                    str(user_id or "").strip(),
                    str(authorization_code_prefix or "").strip(),
                    str(authorization_code_hash or "").strip(),
                    str(authorization_code_expires_at or "").strip(),
                    str(authorized_at or "").strip(),
                    str(authorized_at or "").strip(),
                    str(request_id or "").strip(),
                    ASSISTED_APPLY_STATUS_PENDING,
                    str(authorized_at or "").strip(),
                ),
            ).rowcount
            if row_count != 1:
                return None
            row = connection.execute(
                "SELECT * FROM assisted_apply_connections WHERE request_id = ?",
                (str(request_id or "").strip(),),
            ).fetchone()
        return _assisted_apply_connection_from_row(row) if row is not None else None

    def reject_assisted_apply_connection(
        self,
        request_id: str,
        *,
        user_id: str,
        rejected_at: str,
    ) -> AssistedApplyConnectionRecord | None:
        with self._connect() as connection:
            row_count = connection.execute(
                """
                UPDATE assisted_apply_connections
                SET status = ?, user_id = ?, rejected_at = ?, updated_at = ?
                WHERE request_id = ? AND status = ? AND user_id = ''
                    AND request_expires_at > ?
                """,
                (
                    ASSISTED_APPLY_STATUS_REJECTED,
                    str(user_id or "").strip(),
                    str(rejected_at or "").strip(),
                    str(rejected_at or "").strip(),
                    str(request_id or "").strip(),
                    ASSISTED_APPLY_STATUS_PENDING,
                    str(rejected_at or "").strip(),
                ),
            ).rowcount
            if row_count != 1:
                return None
            row = connection.execute(
                "SELECT * FROM assisted_apply_connections WHERE request_id = ?",
                (str(request_id or "").strip(),),
            ).fetchone()
        return _assisted_apply_connection_from_row(row) if row is not None else None

    def activate_assisted_apply_connection(
        self,
        request_id: str,
        *,
        extension_origin: str,
        session_token_prefix: str,
        session_token_hash: str,
        session_expires_at: str,
        activated_at: str,
    ) -> AssistedApplyConnectionRecord | None:
        with self._connect() as connection:
            row_count = connection.execute(
                """
                UPDATE assisted_apply_connections
                SET status = ?, code_consumed_at = ?,
                    authorization_code_prefix = '', authorization_code_hash = '',
                    session_token_prefix = ?, session_token_hash = ?, session_expires_at = ?,
                    activated_at = ?, last_used_at = ?, updated_at = ?
                WHERE request_id = ? AND status = ? AND code_consumed_at = ''
                    AND extension_origin = ? AND authorization_code_expires_at > ?
                """,
                (
                    ASSISTED_APPLY_STATUS_ACTIVE,
                    str(activated_at or "").strip(),
                    str(session_token_prefix or "").strip(),
                    str(session_token_hash or "").strip(),
                    str(session_expires_at or "").strip(),
                    str(activated_at or "").strip(),
                    str(activated_at or "").strip(),
                    str(activated_at or "").strip(),
                    str(request_id or "").strip(),
                    ASSISTED_APPLY_STATUS_AUTHORIZED,
                    str(extension_origin or "").strip(),
                    str(activated_at or "").strip(),
                ),
            ).rowcount
            if row_count != 1:
                return None
            row = connection.execute(
                "SELECT * FROM assisted_apply_connections WHERE request_id = ?",
                (str(request_id or "").strip(),),
            ).fetchone()
        return _assisted_apply_connection_from_row(row) if row is not None else None

    def expire_assisted_apply_connection(
        self,
        request_id: str,
        *,
        expected_status: str,
        expired_at: str,
    ) -> AssistedApplyConnectionRecord | None:
        with self._connect() as connection:
            row_count = connection.execute(
                """
                UPDATE assisted_apply_connections
                SET status = ?, expired_at = ?, updated_at = ?,
                    authorization_code_prefix = '', authorization_code_hash = '',
                    session_token_prefix = '', session_token_hash = ''
                WHERE request_id = ? AND status = ?
                """,
                (
                    ASSISTED_APPLY_STATUS_EXPIRED,
                    str(expired_at or "").strip(),
                    str(expired_at or "").strip(),
                    str(request_id or "").strip(),
                    str(expected_status or "").strip(),
                ),
            ).rowcount
            if row_count != 1:
                return None
            row = connection.execute(
                "SELECT * FROM assisted_apply_connections WHERE request_id = ?",
                (str(request_id or "").strip(),),
            ).fetchone()
        return _assisted_apply_connection_from_row(row) if row is not None else None

    def touch_assisted_apply_session(
        self,
        request_id: str,
        *,
        last_used_at: str,
    ) -> AssistedApplyConnectionRecord | None:
        with self._connect() as connection:
            row_count = connection.execute(
                """
                UPDATE assisted_apply_connections
                SET last_used_at = ?, updated_at = ?
                WHERE request_id = ? AND status = ? AND session_expires_at > ?
                """,
                (
                    str(last_used_at or "").strip(),
                    str(last_used_at or "").strip(),
                    str(request_id or "").strip(),
                    ASSISTED_APPLY_STATUS_ACTIVE,
                    str(last_used_at or "").strip(),
                ),
            ).rowcount
            if row_count != 1:
                return None
            row = connection.execute(
                "SELECT * FROM assisted_apply_connections WHERE request_id = ?",
                (str(request_id or "").strip(),),
            ).fetchone()
        return _assisted_apply_connection_from_row(row) if row is not None else None

    def revoke_assisted_apply_connection(
        self,
        request_id: str,
        *,
        user_id: str,
        revoked_at: str,
    ) -> AssistedApplyConnectionRecord | None:
        with self._connect() as connection:
            row_count = connection.execute(
                """
                UPDATE assisted_apply_connections
                SET status = ?, revoked_at = ?, updated_at = ?,
                    authorization_code_prefix = '', authorization_code_hash = '',
                    session_token_prefix = '', session_token_hash = ''
                WHERE request_id = ? AND user_id = ? AND status IN (?, ?)
                """,
                (
                    ASSISTED_APPLY_STATUS_REVOKED,
                    str(revoked_at or "").strip(),
                    str(revoked_at or "").strip(),
                    str(request_id or "").strip(),
                    str(user_id or "").strip(),
                    ASSISTED_APPLY_STATUS_AUTHORIZED,
                    ASSISTED_APPLY_STATUS_ACTIVE,
                ),
            ).rowcount
            if row_count != 1:
                return None
            row = connection.execute(
                "SELECT * FROM assisted_apply_connections WHERE request_id = ?",
                (str(request_id or "").strip(),),
            ).fetchone()
        return _assisted_apply_connection_from_row(row) if row is not None else None

    def update_assisted_apply_preferences_metadata(
        self,
        user_id: str,
        *,
        expected_revision: int,
        preferences: AssistedApplyPreferences,
        updated_at: str,
    ) -> bool:
        if (
            preferences.schema_version != 1
            or preferences.revision != int(expected_revision) + 1
            or not preferences.require_legal_answer_confirmation
        ):
            raise ValueError("Invalid server-owned Assisted Apply preference revision.")
        normalized_user_id = str(user_id or "").strip()
        normalized_updated_at = str(updated_at or "").strip()

        def update(connection) -> bool:
            row = connection.execute(
                "SELECT payload_json FROM users WHERE user_id = ?",
                (normalized_user_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"User '{normalized_user_id}' not found.")
            previous_payload_json = str(row["payload_json"] or "{}")
            payload = _deserialize(previous_payload_json, {})
            metadata = dict(payload.get("metadata") or {})
            stored = metadata.get(ASSISTED_APPLY_PREFERENCES_METADATA_KEY)
            current = AssistedApplyPreferences.from_stored(
                stored if isinstance(stored, Mapping) else None
            )
            if current.revision != int(expected_revision):
                return False
            metadata[ASSISTED_APPLY_PREFERENCES_METADATA_KEY] = preferences.to_dict()
            payload["metadata"] = metadata
            payload["updated_at"] = normalized_updated_at
            row_count = connection.execute(
                "UPDATE users SET updated_at = ?, payload_json = ? "
                "WHERE user_id = ? AND payload_json = ?",
                (
                    normalized_updated_at,
                    _serialize(payload),
                    normalized_user_id,
                    previous_payload_json,
                ),
            ).rowcount
            return row_count == 1

        return self._run_transaction(update)

    def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM subscriptions WHERE subscription_id = ?",
                (str(subscription_id or "").strip(),),
            ).fetchone()
        if row is None:
            raise KeyError(f"Subscription '{subscription_id}' not found.")
        return {key: row[key] for key in row.keys()}

    def get_subscription_by_creem_id(self, creem_subscription_id: str) -> dict[str, Any]:
        normalized_subscription_id = str(creem_subscription_id or "").strip()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM subscriptions WHERE creem_subscription_id = ? OR subscription_id = ?",
                (normalized_subscription_id, normalized_subscription_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"Creem subscription '{creem_subscription_id}' not found.")
        return {key: row[key] for key in row.keys()}

    def get_current_subscription_by_user_id(self, user_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                (
                    "SELECT * FROM subscriptions WHERE user_id = ? "
                    "ORDER BY "
                    "CASE WHEN status IN ('active', 'on_trial', 'trialing', 'past_due', 'unpaid', 'paused', 'cancelled') THEN 0 ELSE 1 END, "
                    "updated_at DESC "
                    "LIMIT 1"
                ),
                (str(user_id or "").strip(),),
            ).fetchone()
        if row is None:
            raise KeyError(f"No subscription found for user '{user_id}'.")
        return {key: row[key] for key in row.keys()}

    def upsert_subscription(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        subscription_id = str(payload.get("subscription_id") or "").strip()
        if not subscription_id:
            raise ValueError("subscription_id is required")
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO subscriptions ("
                    "subscription_id, user_id, plan_id, status, billing_provider, creem_subscription_id, "
                    "creem_customer_id, creem_order_id, current_period_start, current_period_end, "
                    "cancelled_at, created_at, updated_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(subscription_id) DO UPDATE SET "
                    "user_id=excluded.user_id, plan_id=excluded.plan_id, status=excluded.status, "
                    "billing_provider=excluded.billing_provider, "
                    "creem_subscription_id=excluded.creem_subscription_id, "
                    "creem_customer_id=excluded.creem_customer_id, "
                    "creem_order_id=excluded.creem_order_id, "
                    "current_period_start=excluded.current_period_start, "
                    "current_period_end=excluded.current_period_end, "
                    "cancelled_at=excluded.cancelled_at, "
                    "updated_at=excluded.updated_at"
                ),
                (
                    subscription_id,
                    str(payload.get("user_id") or "").strip(),
                    str(payload.get("plan_id") or "none").strip() or "none",
                    str(payload.get("status") or "active").strip() or "active",
                    str(payload.get("billing_provider") or "creem").strip() or "creem",
                    str(payload.get("creem_subscription_id") or "").strip(),
                    str(payload.get("creem_customer_id") or "").strip(),
                    str(payload.get("creem_order_id") or "").strip(),
                    str(payload.get("current_period_start") or "").strip(),
                    str(payload.get("current_period_end") or "").strip(),
                    str(payload.get("cancelled_at") or "").strip(),
                    str(payload.get("created_at") or utc_now_iso()).strip(),
                    str(payload.get("updated_at") or utc_now_iso()).strip(),
                ),
            )
        return self.get_subscription(subscription_id)

    def cancel_subscriptions_for_user(self, user_id: str, *, cancelled_at: str = "") -> int:
        normalized_cancelled_at = str(cancelled_at or utc_now_iso()).strip()
        with self._connect() as connection:
            row_count = connection.execute(
                (
                    "UPDATE subscriptions SET status = 'cancelled', cancelled_at = ?, updated_at = ? "
                    "WHERE user_id = ? AND status != 'cancelled'"
                ),
                (
                    normalized_cancelled_at,
                    utc_now_iso(),
                    str(user_id or "").strip(),
                ),
            ).rowcount
        return int(row_count)

    def insert_subscription_event(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        event_id = str(payload.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("event_id is required")
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT OR REPLACE INTO subscription_events ("
                    "event_id, user_id, event_type, plan_id, previous_plan_id, billing_provider, "
                    "provider_event_name, occurred_at, payload_json"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    event_id,
                    str(payload.get("user_id") or "").strip(),
                    str(payload.get("event_type") or "").strip(),
                    str(payload.get("plan_id") or "").strip(),
                    str(payload.get("previous_plan_id") or "").strip(),
                    str(payload.get("billing_provider") or "creem").strip() or "creem",
                    str(payload.get("provider_event_name") or "").strip(),
                    str(payload.get("occurred_at") or utc_now_iso()).strip(),
                    _serialize(dict(payload.get("payload_json") or payload.get("payload") or {})),
                ),
            )
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM subscription_events WHERE event_id = ?", (event_id,)).fetchone()
        if row is None:
            raise KeyError(f"Subscription event '{event_id}' not found after insert.")
        event_payload = {key: row[key] for key in row.keys()}
        event_payload["payload_json"] = _deserialize(event_payload.get("payload_json"), {})
        return event_payload

    def get_quota_usage(self, user_id: str, quota_type: str, period: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                (
                    "SELECT count FROM quota_usage "
                    "WHERE user_id = ? AND quota_type = ? AND period = ?"
                ),
                (
                    str(user_id or "").strip(),
                    str(quota_type or "").strip(),
                    str(period or "").strip(),
                ),
            ).fetchone()
        return int(row["count"]) if row is not None else 0

    def list_quota_usage(self, user_id: str, period: str) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT quota_type, count FROM quota_usage WHERE user_id = ? AND period = ?",
                (
                    str(user_id or "").strip(),
                    str(period or "").strip(),
                ),
            ).fetchall()
        return {str(row["quota_type"]): int(row["count"]) for row in rows}

    def increment_quota_usage(self, user_id: str, quota_type: str, period: str, *, amount: int = 1) -> int:
        quota_row_id = "::".join(
            [
                str(user_id or "").strip(),
                str(quota_type or "").strip(),
                str(period or "").strip(),
            ]
        )
        increment_by = max(1, int(amount))
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO quota_usage (id, user_id, quota_type, period, count, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(user_id, quota_type, period) DO UPDATE SET "
                    "count = quota_usage.count + excluded.count, "
                    "updated_at = excluded.updated_at"
                ),
                (
                    quota_row_id,
                    str(user_id or "").strip(),
                    str(quota_type or "").strip(),
                    str(period or "").strip(),
                    increment_by,
                    utc_now_iso(),
                ),
            )
            row = connection.execute(
                (
                    "SELECT count FROM quota_usage "
                    "WHERE user_id = ? AND quota_type = ? AND period = ?"
                ),
                (
                    str(user_id or "").strip(),
                    str(quota_type or "").strip(),
                    str(period or "").strip(),
                ),
            ).fetchone()
        if row is None:
            raise KeyError("Quota usage row was not found after increment.")
        return int(row["count"])

    def reset_quota_usage(self, user_id: str, period: str) -> int:
        with self._connect() as connection:
            row_count = connection.execute(
                "DELETE FROM quota_usage WHERE user_id = ? AND period = ?",
                (
                    str(user_id or "").strip(),
                    str(period or "").strip(),
                ),
            ).rowcount
        return int(row_count)


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

    def renew_worker_lease_if_owned(
        self,
        observed: WorkerRecord,
        renewed: WorkerRecord,
        *,
        run_attempt_count: int,
    ) -> bool:
        with self._connect() as connection:
            row_count = connection.execute(
                (
                    "UPDATE workers SET status = ?, host_name = ?, process_id = ?, current_run_id = ?, "
                    "last_heartbeat_at = ?, lease_expires_at = ?, metadata_json = ?, payload_json = ? "
                    "WHERE worker_id = ? AND status = ? AND current_run_id = ? "
                    "AND last_heartbeat_at = ? AND lease_expires_at = ? "
                    "AND EXISTS ("
                    "SELECT 1 FROM runs WHERE id = ? AND status IN (?, ?) AND attempt_count = ?"
                    ")"
                ),
                (
                    renewed.status,
                    renewed.host_name,
                    int(renewed.process_id),
                    renewed.current_run_id,
                    renewed.last_heartbeat_at,
                    renewed.lease_expires_at,
                    _serialize(renewed.metadata),
                    _serialize(renewed.to_dict()),
                    observed.worker_id,
                    WORKER_STATUS_RUNNING,
                    observed.current_run_id,
                    observed.last_heartbeat_at,
                    observed.lease_expires_at,
                    observed.current_run_id,
                    RUN_STATUS_RUNNING,
                    RUN_STATUS_CANCEL_REQUESTED,
                    max(1, int(run_attempt_count)),
                ),
            ).rowcount
        return row_count == 1

    def mark_stale_if_expired(
        self,
        worker: WorkerRecord,
        *,
        expires_before: str,
        stale_at: str,
    ) -> bool:
        stale_worker = WorkerRecord.from_dict(worker.to_dict())
        stale_worker.status = WORKER_STATUS_STALE
        stale_worker.current_run_id = ""
        stale_worker.last_heartbeat_at = stale_at
        stale_worker.lease_expires_at = stale_at
        with self._connect() as connection:
            row_count = connection.execute(
                (
                    "UPDATE workers SET status = ?, current_run_id = ?, last_heartbeat_at = ?, "
                    "lease_expires_at = ?, metadata_json = ?, payload_json = ? "
                    "WHERE worker_id = ? AND status = ? AND current_run_id = ? "
                    "AND last_heartbeat_at = ? AND lease_expires_at = ? "
                    "AND lease_expires_at != '' AND lease_expires_at <= ?"
                ),
                (
                    stale_worker.status,
                    stale_worker.current_run_id,
                    stale_worker.last_heartbeat_at,
                    stale_worker.lease_expires_at,
                    _serialize(stale_worker.metadata),
                    _serialize(stale_worker.to_dict()),
                    worker.worker_id,
                    worker.status,
                    worker.current_run_id,
                    worker.last_heartbeat_at,
                    worker.lease_expires_at,
                    expires_before,
                ),
            ).rowcount
        return row_count == 1

    def delete_worker(self, worker_id: str) -> None:
        with self._connect() as connection:
            row_count = connection.execute("DELETE FROM workers WHERE worker_id = ?", (worker_id,)).rowcount
        if row_count == 0:
            raise KeyError(f"Worker '{worker_id}' not found.")


class SqliteAnalyticsStore(_SqliteStore):
    def record_scrapeops_usage(
        self,
        *,
        ledger_id: str,
        payload: dict[str, Any],
        user_id: str = "",
        workspace_id: str = "",
        run_id: str = "",
        route: str = "",
        source: str = "",
    ) -> None:
        record = dict(payload or {})
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO scrapeops_usage_ledger ("
                    "ledger_id, source_id, target_url, method, request_mode, target_status_code, "
                    "provider_status_code, latency_ms, billed_credits_actual, billed_credits_estimated, "
                    "usable_job_count, error_category, recorded_at, user_id, workspace_id, run_id, route, source"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    str(ledger_id or "").strip(),
                    str(record.get("source_id") or "").strip(),
                    str(record.get("target_url") or "").strip(),
                    str(record.get("method") or "scrapeops_proxy").strip() or "scrapeops_proxy",
                    str(record.get("request_mode") or "basic").strip() or "basic",
                    int(record.get("target_status_code") or 0),
                    int(record.get("provider_status_code") or 0),
                    max(0, int(record.get("latency_ms") or 0)),
                    None if record.get("billed_credits_actual") is None else int(record["billed_credits_actual"]),
                    max(0, int(record.get("billed_credits_estimated") or 0)),
                    max(0, int(record.get("usable_job_count") or 0)),
                    str(record.get("error_category") or "").strip(),
                    str(record.get("recorded_at") or utc_now_iso()).strip(),
                    str(user_id or "").strip(),
                    str(workspace_id or "").strip(),
                    str(run_id or "").strip(),
                    str(route or "").strip(),
                    str(source or "").strip(),
                ),
            )

    def get_spend_by_source(self, since: datetime | str) -> dict[str, int]:
        since_value = since.isoformat() if isinstance(since, datetime) else str(since or "").strip()
        with self._connect() as connection:
            rows = connection.execute(
                (
                    "SELECT source_id, COALESCE(SUM(billed_credits_actual), 0) AS billed_credits_actual "
                    "FROM scrapeops_usage_ledger WHERE recorded_at >= ? GROUP BY source_id"
                ),
                (since_value,),
            ).fetchall()
        return {str(row["source_id"] or ""): int(row["billed_credits_actual"] or 0) for row in rows}

    def emit_event(
        self,
        *,
        event_id: str,
        event_name: str,
        occurred_at: str,
        user_id: str = "",
        workspace_id: str = "",
        run_id: str = "",
        job_id: str = "",
        review_id: str = "",
        session_id: str = "",
        route: str = "",
        source: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO analytics_events ("
                    "event_id, event_name, occurred_at, user_id, workspace_id, run_id, job_id, "
                    "review_id, session_id, route, source, payload_json"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    str(event_id or "").strip(),
                    str(event_name or "").strip(),
                    str(occurred_at or utc_now_iso()).strip(),
                    str(user_id or "").strip(),
                    str(workspace_id or "").strip(),
                    str(run_id or "").strip(),
                    str(job_id or "").strip(),
                    str(review_id or "").strip(),
                    str(session_id or "").strip(),
                    str(route or "").strip(),
                    str(source or "").strip(),
                    _serialize(dict(payload or {})),
                ),
            )

    def query_rows(self, query: str, params: Iterable[Any] | None = None) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params or ())).fetchall()
        return [dict(row) for row in rows]

    def list_events(
        self,
        *,
        limit: int,
        offset: int,
        event_name: str = "",
        user_id: str = "",
        occurred_from: str = "",
        occurred_to: str = "",
    ) -> list[dict[str, Any]]:
        filters = []
        params: list[Any] = []
        normalized_event_name = str(event_name or "").strip().lower()
        normalized_user_id = str(user_id or "").strip().lower()
        normalized_occurred_from = str(occurred_from or "").strip()
        normalized_occurred_to = str(occurred_to or "").strip()

        if normalized_event_name:
            filters.append("LOWER(event_name) LIKE ?")
            params.append(f"%{normalized_event_name}%")
        if normalized_user_id:
            filters.append("LOWER(user_id) LIKE ?")
            params.append(f"%{normalized_user_id}%")
        if normalized_occurred_from:
            filters.append("occurred_at >= ?")
            params.append(normalized_occurred_from)
        if normalized_occurred_to:
            filters.append("occurred_at < ?")
            params.append(normalized_occurred_to)

        where_clause = f" WHERE {' AND '.join(filters)}" if filters else ""
        query = (
            "SELECT event_id, event_name, occurred_at, user_id, workspace_id, run_id, job_id, "
            "review_id, session_id, route, source, payload_json "
            f"FROM analytics_events{where_clause} "
            "ORDER BY occurred_at DESC, event_id DESC "
            "LIMIT ? OFFSET ?"
        )
        params.extend([int(limit), int(offset)])

        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()

        return [
            {
                "event_id": str(row["event_id"] or ""),
                "event_name": str(row["event_name"] or ""),
                "occurred_at": str(row["occurred_at"] or ""),
                "user_id": str(row["user_id"] or ""),
                "workspace_id": str(row["workspace_id"] or ""),
                "run_id": str(row["run_id"] or ""),
                "job_id": str(row["job_id"] or ""),
                "review_id": str(row["review_id"] or ""),
                "session_id": str(row["session_id"] or ""),
                "route": str(row["route"] or ""),
                "source": str(row["source"] or ""),
                "payload": _deserialize(row["payload_json"], {}),
            }
            for row in rows
        ]

    def count_events(
        self,
        *,
        event_name: str = "",
        user_id: str = "",
        occurred_from: str = "",
        occurred_to: str = "",
    ) -> int:
        filters = []
        params: list[Any] = []
        normalized_event_name = str(event_name or "").strip().lower()
        normalized_user_id = str(user_id or "").strip().lower()
        normalized_occurred_from = str(occurred_from or "").strip()
        normalized_occurred_to = str(occurred_to or "").strip()

        if normalized_event_name:
            filters.append("LOWER(event_name) LIKE ?")
            params.append(f"%{normalized_event_name}%")
        if normalized_user_id:
            filters.append("LOWER(user_id) LIKE ?")
            params.append(f"%{normalized_user_id}%")
        if normalized_occurred_from:
            filters.append("occurred_at >= ?")
            params.append(normalized_occurred_from)
        if normalized_occurred_to:
            filters.append("occurred_at < ?")
            params.append(normalized_occurred_to)

        where_clause = f" WHERE {' AND '.join(filters)}" if filters else ""
        query = f"SELECT COUNT(*) AS total FROM analytics_events{where_clause}"

        with self._connect() as connection:
            row = connection.execute(query, tuple(params)).fetchone()

        return int(row["total"] if row else 0)


class SqliteSourcePolicyStore(_SqliteStore):
    def ensure_sites(self, sites: Iterable[dict[str, Any]], *, site_type: str) -> None:
        rows = [
            (str(item.get("url") or "").strip(), str(site_type or "company").strip() or "company", utc_now_iso())
            for item in sites
            if str(item.get("url") or "").strip()
        ]
        if not rows:
            return
        with self._connect() as connection:
            connection.executemany(
                (
                    "INSERT INTO site_source_policy (site_url, site_type, site_state, updated_at) "
                    "VALUES (?, ?, 'pending', ?) ON CONFLICT(site_url) DO NOTHING"
                ),
                rows,
            )

    def set_site_state(self, site_url: str, site_state: str, *, site_type: str = "company") -> None:
        normalized_state = str(site_state or "").strip()
        if normalized_state not in _SITE_STATES:
            raise ValueError(f"site_state must be one of: {sorted(_SITE_STATES)}")
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO site_source_policy (site_url, site_type, site_state, updated_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(site_url) DO UPDATE SET site_type=excluded.site_type, "
                    "site_state=excluded.site_state, updated_at=excluded.updated_at"
                ),
                (str(site_url or "").strip(), str(site_type or "company").strip(), normalized_state, utc_now_iso()),
            )

    def mark_workspace_selected(self, site_urls: Iterable[str], *, site_type: str) -> dict[str, str]:
        normalized_urls = sorted({str(item or "").strip() for item in site_urls if str(item or "").strip()})
        if not normalized_urls:
            return {}
        normalized_site_type = str(site_type or "company").strip() or "company"

        def mark_selected(connection) -> dict[str, str]:
            transitions: dict[str, str] = {}
            for site_url in normalized_urls:
                row = connection.execute(
                    "SELECT site_state FROM site_source_policy WHERE site_url = ?",
                    (site_url,),
                ).fetchone()
                previous_state = str(row["site_state"] or "") if row else "pending"
                if previous_state not in {"pending", "paused"}:
                    continue
                connection.execute(
                    (
                        "INSERT INTO site_source_policy (site_url, site_type, site_state, updated_at) "
                        "VALUES (?, ?, 'selected', ?) ON CONFLICT(site_url) DO UPDATE SET "
                        "site_state='selected', updated_at=excluded.updated_at"
                    ),
                    (site_url, normalized_site_type, utc_now_iso()),
                )
                transitions[site_url] = f"{previous_state}->selected"
            return transitions

        return self._run_transaction(mark_selected)

    def filter_crawlable_sites(
        self,
        sites: Iterable[dict[str, Any]],
        *,
        explicitly_triggered_urls: Iterable[str] = (),
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        explicit_urls = {str(item or "").strip() for item in explicitly_triggered_urls if str(item or "").strip()}
        eligible: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        with self._connect() as connection:
            for site in sites:
                item = dict(site or {})
                site_url = str(item.get("url") or "").strip()
                row = connection.execute(
                    (
                        "SELECT site_state, consecutive_zero_yield_runs, last_jobs_found, last_crawled_at "
                        "FROM site_source_policy WHERE site_url = ?"
                    ),
                    (site_url,),
                ).fetchone()
                site_state = str(row["site_state"] or "pending") if row else "pending"
                item["site_state"] = site_state
                item["consecutive_zero_yield_runs"] = int(row["consecutive_zero_yield_runs"] or 0) if row else 0
                item["last_jobs_found"] = int(row["last_jobs_found"] or 0) if row else 0
                item["last_crawled_at"] = str(row["last_crawled_at"] or "") if row else ""
                if site_state in {"hot", "selected"} or site_url in explicit_urls:
                    eligible.append(item)
                else:
                    skipped.append(item)
        return eligible, skipped

    def record_site_yield(self, site_url: str, *, jobs_found: int) -> dict[str, Any]:
        normalized_url = str(site_url or "").strip()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT site_state, consecutive_zero_yield_runs FROM site_source_policy WHERE site_url = ?",
                (normalized_url,),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO site_source_policy (site_url, site_state, updated_at) VALUES (?, 'pending', ?)",
                    (normalized_url, utc_now_iso()),
                )
                previous_state = "pending"
                zeros = 0
            else:
                previous_state = str(row["site_state"] or "pending")
                zeros = int(row["consecutive_zero_yield_runs"] or 0)
            normalized_jobs_found = max(0, int(jobs_found or 0))
            if normalized_jobs_found > 0:
                next_state = "selected" if previous_state == "low_yield" else previous_state
                zeros = 0
            else:
                zeros += 1
                next_state = "low_yield" if zeros >= 3 and previous_state not in {"paused", "pending"} else previous_state
            connection.execute(
                (
                    "UPDATE site_source_policy SET site_state = ?, consecutive_zero_yield_runs = ?, "
                    "last_jobs_found = ?, last_crawled_at = ?, updated_at = ? WHERE site_url = ?"
                ),
                (next_state, zeros, normalized_jobs_found, utc_now_iso(), utc_now_iso(), normalized_url),
            )
        return {
            "site_url": normalized_url,
            "previous_state": previous_state,
            "site_state": next_state,
            "consecutive_zero_yield_runs": zeros,
            "jobs_found": normalized_jobs_found,
        }

    def get_site_policy(self, site_url: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                (
                    "SELECT site_url, site_type, site_state, consecutive_zero_yield_runs, "
                    "last_jobs_found, last_crawled_at, updated_at FROM site_source_policy WHERE site_url = ?"
                ),
                (str(site_url or "").strip(),),
            ).fetchone()
        return dict(row) if row else None

    def get_seen_job_urls(self, job_urls: Iterable[str], *, workspace_id: str = "") -> set[str]:
        normalized_urls = {
            canonicalize_url(str(item or "").strip()) or str(item or "").strip()
            for item in job_urls
            if str(item or "").strip()
        }
        normalized_urls = {item for item in normalized_urls if item}
        if not normalized_urls:
            return set()
        seen: set[str] = set()
        with self._connect() as connection:
            values = list(normalized_urls)
            for offset in range(0, len(values), 500):
                chunk = values[offset : offset + 500]
                placeholders = ",".join("?" for _ in chunk)
                params = list(chunk)
                query = f"SELECT job_url FROM site_job_url_history WHERE job_url IN ({placeholders})"
                rows = connection.execute(query, tuple(params)).fetchall()
                seen.update(str(row["job_url"] or "") for row in rows)
        return seen

    def get_cached_job_postings(self, job_urls: Iterable[str]) -> dict[str, dict[str, Any]]:
        normalized_urls = {
            canonicalize_url(str(item or "").strip()) or str(item or "").strip()
            for item in job_urls
            if str(item or "").strip()
        }
        normalized_urls = {item for item in normalized_urls if item}
        if not normalized_urls:
            return {}
        postings: dict[str, dict[str, Any]] = {}
        with self._connect() as connection:
            values = list(normalized_urls)
            for offset in range(0, len(values), 500):
                chunk = values[offset : offset + 500]
                placeholders = ",".join("?" for _ in chunk)
                rows = connection.execute(
                    (
                        "SELECT job_url, site_url, source_group_url, job_id, title, company, location_raw, "
                        "last_status, active_status, last_seen_at, last_verified_at, payload_json "
                        f"FROM site_job_url_history WHERE job_url IN ({placeholders})"
                    ),
                    tuple(chunk),
                ).fetchall()
                for row in rows:
                    if str(row["active_status"] or "").strip() == "inactive":
                        continue
                    job_url = str(row["job_url"] or "").strip()
                    if not job_url:
                        continue
                    payload = _deserialize(row["payload_json"], {})
                    if not isinstance(payload, dict):
                        payload = {}
                    posting = {
                        **payload,
                        "job_url": job_url,
                        "apply_link": str(payload.get("apply_link") or job_url),
                        "source_url": str(payload.get("source_url") or job_url),
                        "link": str(payload.get("link") or job_url),
                        "career_site_url": str(payload.get("career_site_url") or row["site_url"] or ""),
                        "job_id": str(payload.get("job_id") or row["job_id"] or ""),
                        "title": str(payload.get("title") or row["title"] or ""),
                        "company": str(payload.get("company") or row["company"] or ""),
                        "location_raw": str(payload.get("location_raw") or row["location_raw"] or ""),
                        "source_type": str(payload.get("source_type") or "company_career_site"),
                        "portal": str(payload.get("portal") or "company_career_site"),
                        "public_job_index_reused": True,
                        "public_job_index_last_seen_at": str(row["last_seen_at"] or ""),
                        "public_job_index_last_verified_at": str(row["last_verified_at"] or ""),
                        "public_job_index_last_status": str(row["last_status"] or ""),
                    }
                    postings[job_url] = posting
        return postings

    @staticmethod
    def _job_url_attempt_active_status(status: str) -> str:
        normalized_status = str(status or "").strip()
        if normalized_status in {"accepted", "cache_reused", "keyword_filtered", "old_posting"}:
            return "active"
        if normalized_status == "inactive":
            return "inactive"
        return "unknown"

    def record_job_url_attempts(
        self,
        records: Iterable[dict[str, Any]],
        *,
        run_id: str = "",
        workspace_id: str = "",
    ) -> None:
        now = utc_now_iso()
        rows = []
        for record in records:
            if not isinstance(record, dict):
                continue
            job_url = canonicalize_url(str(record.get("job_url") or "").strip()) or str(record.get("job_url") or "").strip()
            if not job_url:
                continue
            status = str(record.get("status") or record.get("last_status") or "").strip()
            payload = record.get("payload")
            if not isinstance(payload, dict):
                payload = {
                    key: value
                    for key, value in dict(record).items()
                    if key
                    not in {
                        "status",
                        "last_status",
                        "site_url",
                        "source_group_url",
                        "workspace_id",
                        "run_id",
                        "payload",
                    }
                }
            normalized_payload = {
                **dict(payload or {}),
                "job_url": job_url,
                "apply_link": str(dict(payload or {}).get("apply_link") or job_url),
                "source_url": str(dict(payload or {}).get("source_url") or job_url),
                "link": str(dict(payload or {}).get("link") or job_url),
            }
            active_status = self._job_url_attempt_active_status(status)
            last_verified_at = now if active_status == "active" else ""
            rows.append(
                (
                    job_url,
                    str(record.get("site_url") or "").strip(),
                    str(record.get("source_group_url") or record.get("site_url") or "").strip(),
                    str(workspace_id or record.get("workspace_id") or "").strip(),
                    str(run_id or record.get("run_id") or "").strip(),
                    str(normalized_payload.get("job_id") or record.get("job_id") or "").strip(),
                    str(normalized_payload.get("title") or record.get("title") or "").strip(),
                    str(normalized_payload.get("company") or record.get("company") or "").strip(),
                    str(normalized_payload.get("location_raw") or record.get("location_raw") or "").strip(),
                    status,
                    active_status,
                    now,
                    now,
                    last_verified_at,
                    _serialize(normalized_payload),
                )
            )
        if not rows:
            return
        with self._connect() as connection:
            connection.executemany(
                (
                    "INSERT INTO site_job_url_history ("
                    "job_url, site_url, source_group_url, workspace_id, run_id, job_id, title, company, "
                    "location_raw, last_status, active_status, first_seen_at, last_seen_at, last_verified_at, payload_json"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(job_url) DO UPDATE SET "
                    "site_url=excluded.site_url, "
                    "source_group_url=excluded.source_group_url, "
                    "workspace_id=excluded.workspace_id, "
                    "run_id=excluded.run_id, "
                    "job_id=excluded.job_id, "
                    "title=excluded.title, "
                    "company=excluded.company, "
                    "location_raw=excluded.location_raw, "
                    "last_status=excluded.last_status, "
                    "active_status=excluded.active_status, "
                    "last_seen_at=excluded.last_seen_at, "
                    "last_verified_at=CASE "
                    "WHEN excluded.last_verified_at != '' THEN excluded.last_verified_at "
                    "ELSE site_job_url_history.last_verified_at END, "
                    "payload_json=excluded.payload_json"
                ),
                rows,
            )


class SqliteConfigStore(_SqliteStore):
    def get_value(self, config_key: str, default: Any = None):
        normalized_key = str(config_key or "").strip()
        if not normalized_key:
            return default
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM app_config WHERE config_key = ?",
                (normalized_key,),
            ).fetchone()
        if row is None:
            return default
        return _deserialize(row["payload_json"], default)

    def set_value(self, config_key: str, value: Any) -> None:
        normalized_key = str(config_key or "").strip()
        if not normalized_key:
            raise ValueError("config_key is required")
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO app_config (config_key, updated_at, payload_json) VALUES (?, ?, ?) "
                    "ON CONFLICT(config_key) DO UPDATE SET updated_at=excluded.updated_at, payload_json=excluded.payload_json"
                ),
                (
                    normalized_key,
                    utc_now_iso(),
                    _serialize(value),
                ),
            )

    def delete_value(self, config_key: str) -> None:
        normalized_key = str(config_key or "").strip()
        if not normalized_key:
            raise ValueError("config_key is required")
        with self._connect() as connection:
            connection.execute("DELETE FROM app_config WHERE config_key = ?", (normalized_key,))

    def list_values(self, *, prefix: str = "") -> dict[str, Any]:
        normalized_prefix = str(prefix or "").strip()
        params: list[Any] = []
        query = "SELECT config_key, payload_json FROM app_config"
        if normalized_prefix:
            query += " WHERE config_key LIKE ?"
            params.append(f"{normalized_prefix}%")
        query += " ORDER BY config_key"
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return {
            str(row["config_key"] or ""): _deserialize(row["payload_json"], None)
            for row in rows
        }



class SqliteCareerProfileStore(_SqliteStore):
    """SQLite-backed career profile persistence."""

    def list_profiles(self, *, user_id: str = "", limit: int = 50, offset: int = 0) -> list:
        from backend.domain.models import CareerProfile

        query = "SELECT payload_json FROM career_profiles"
        params: list[Any] = []
        if user_id:
            query += " WHERE user_id = ?"
            params.append(user_id)
        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, int(limit)), max(0, int(offset))])
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [CareerProfile.from_dict(_deserialize(row["payload_json"], {})) for row in rows]

    def get_profile(self, profile_id: str) -> "CareerProfile":
        from backend.domain.models import CareerProfile

        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM career_profiles WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Career profile '{profile_id}' not found.")
        return CareerProfile.from_dict(_deserialize(row["payload_json"], {}))

    def upsert_profile(self, profile: "CareerProfile") -> None:
        from backend.domain.models import CareerProfile

        storage = profile.to_dict()
        with self._connect() as connection:
            connection.execute(
                (
                    "INSERT INTO career_profiles "
                    "(profile_id, user_id, name, description, preferred_language, "
                    "target_direction, bound_workspace_id, status, created_at, updated_at, metadata_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(profile_id) DO UPDATE SET "
                    "user_id=excluded.user_id, name=excluded.name, "
                    "description=excluded.description, preferred_language=excluded.preferred_language, "
                    "target_direction=excluded.target_direction, bound_workspace_id=excluded.bound_workspace_id, status=excluded.status, "
                    "updated_at=excluded.updated_at, metadata_json=excluded.metadata_json"
                ),
                (
                    profile.profile_id,
                    profile.user_id,
                    profile.name,
                    profile.description,
                    profile.preferred_language,
                    profile.target_direction,
                    profile.bound_workspace_id,
                    profile.status,
                    profile.created_at,
                    utc_now_iso(),
                    _serialize(profile.metadata),
                ),
            )

    def delete_profile(self, profile_id: str) -> None:
        with self._connect() as connection:
            row_count = connection.execute(
                "DELETE FROM career_profiles WHERE profile_id = ?", (profile_id,)
            ).rowcount
        if row_count == 0:
            raise KeyError(f"Career profile '{profile_id}' not found.")
