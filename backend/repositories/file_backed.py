from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

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
    WORKER_STATUS_STOPPED,
    ApiTokenRecord,
    CareerProfile,

    ArtifactRecord,
    JobRecord,
    ReviewRecord,
    RunRecord,
    SecretRecord,
    UserRecord,
    WorkerRecord,
    WorkflowTemplate,
    WorkspaceDefinition,
    utc_now_iso,
)
from backend.orchestration.seeded_workspaces import DEFAULT_WORKFLOW_TEMPLATES, DEFAULT_WORKSPACES
from backend.repositories.contracts import BackendRepositories
from backend.security.auth import API_TOKEN_PREFIX_LENGTH

_APPLICATION_STATUS_HISTORY_SOURCES = {"manual", "gmail_sync", "auto_default"}
_FILE_BACKEND_LOCK = threading.RLock()


def _read_json(path: Path, default: Any):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _timestamp_is_after(value: str, threshold: str) -> bool:
    try:
        parsed = datetime.fromisoformat(str(value or "").strip())
        comparison = datetime.fromisoformat(str(threshold or "").strip())
    except (TypeError, ValueError):
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if comparison.tzinfo is None:
        comparison = comparison.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc) > comparison.astimezone(timezone.utc)


class FileWorkspaceRepository:
    def __init__(
        self,
        base_dir: Path,
        *,
        seeded_templates: Iterable[WorkflowTemplate] | None = None,
        seeded_workspaces: Iterable[WorkspaceDefinition] | None = None,
    ):
        self.base_dir = Path(base_dir)
        self.templates_path = self.base_dir / "workflow_templates.json"
        self.workspaces_path = self.base_dir / "workspaces.json"
        self._seeded_templates = list(seeded_templates or DEFAULT_WORKFLOW_TEMPLATES)
        self._seeded_workspaces = list(seeded_workspaces or DEFAULT_WORKSPACES)
        self._ensure_seed_data()

    def _ensure_seed_data(self) -> None:
        if not self.templates_path.exists():
            _write_json(self.templates_path, [template.to_dict() for template in self._seeded_templates])
        if not self.workspaces_path.exists():
            _write_json(self.workspaces_path, [workspace.to_dict() for workspace in self._seeded_workspaces])

    def list_workflow_templates(self) -> list[WorkflowTemplate]:
        payload = _read_json(self.templates_path, [])
        return [WorkflowTemplate.from_dict(item) for item in payload if isinstance(item, dict)]

    def get_workflow_template(self, template_id: str) -> WorkflowTemplate:
        for template in self.list_workflow_templates():
            if template.id == template_id:
                return template
        raise KeyError(f"Workflow template '{template_id}' not found.")

    def upsert_workflow_template(self, workflow_template: WorkflowTemplate) -> None:
        templates = {template.id: template for template in self.list_workflow_templates()}
        templates[workflow_template.id] = workflow_template
        _write_json(self.templates_path, [template.to_dict() for template in templates.values()])

    def delete_workflow_template(self, template_id: str) -> None:
        templates = {template.id: template for template in self.list_workflow_templates()}
        if template_id not in templates:
            raise KeyError(f"Workflow template '{template_id}' not found.")
        del templates[template_id]
        _write_json(self.templates_path, [template.to_dict() for template in templates.values()])

    def list_workspaces(self) -> list[WorkspaceDefinition]:
        payload = _read_json(self.workspaces_path, [])
        return [WorkspaceDefinition.from_dict(item) for item in payload if isinstance(item, dict)]

    def get_workspace(self, workspace_id: str) -> WorkspaceDefinition:
        for workspace in self.list_workspaces():
            if workspace.id == workspace_id:
                return workspace
        raise KeyError(f"Workspace '{workspace_id}' not found.")

    def upsert_workspace(self, workspace: WorkspaceDefinition) -> None:
        workspaces = {item.id: item for item in self.list_workspaces()}
        workspaces[workspace.id] = workspace
        _write_json(self.workspaces_path, [item.to_dict() for item in workspaces.values()])

    def delete_workspace(self, workspace_id: str) -> None:
        workspaces = {workspace.id: workspace for workspace in self.list_workspaces()}
        if workspace_id not in workspaces:
            raise KeyError(f"Workspace '{workspace_id}' not found.")
        del workspaces[workspace_id]
        _write_json(self.workspaces_path, [workspace.to_dict() for workspace in workspaces.values()])


class FileRunRepository:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.runs_dir = self.base_dir / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._recovery_lock = _FILE_BACKEND_LOCK

    def _run_path(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.json"

    def save(self, run: RunRecord) -> None:
        _write_json(self._run_path(run.id), run.to_dict())

    def save_recovery_transition_if_stale(
        self,
        run: RunRecord,
        *,
        expected_status: str,
        expected_updated_at: str,
        active_lease_after: str,
    ) -> bool:
        with self._recovery_lock:
            current_payload = _read_json(self._run_path(run.id), {})
            if not current_payload:
                return False
            current = RunRecord.from_dict(current_payload)
            if current.status != expected_status or current.updated_at != expected_updated_at:
                return False
            worker_payload = _read_json(self.base_dir / "workers.json", [])
            workers = [WorkerRecord.from_dict(item) for item in worker_payload if isinstance(item, dict)]
            if any(
                worker.current_run_id == run.id
                and worker.status not in {WORKER_STATUS_STALE, WORKER_STATUS_STOPPED}
                and (not worker.lease_expires_at or worker.lease_expires_at > active_lease_after)
                for worker in workers
            ):
                return False
            self.save(run)
            return True

    def get(self, run_id: str) -> RunRecord:
        payload = _read_json(self._run_path(run_id), {})
        if not payload:
            raise KeyError(f"Run '{run_id}' not found.")
        return RunRecord.from_dict(payload)

    def list_runs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str = "",
        workspace_id: str = "",
        hydrate_payload: bool = True,
    ) -> list[RunRecord]:
        run_files = sorted(self.runs_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        runs = [RunRecord.from_dict(_read_json(path, {})) for path in run_files]
        if status:
            runs = [run for run in runs if run.status == status]
        if workspace_id:
            runs = [run for run in runs if run.workspace_id == workspace_id]
        normalized_offset = max(0, int(offset))
        normalized_limit = max(1, int(limit))
        return runs[normalized_offset : normalized_offset + normalized_limit]

    def claim_next_queued(self) -> RunRecord | None:
        queued_runs = self.list_runs(limit=100000, status=RUN_STATUS_QUEUED)
        if not queued_runs:
            return None
        queued_runs.sort(key=lambda item: (item.queued_at or item.updated_at or item.created_at, item.created_at))
        run = queued_runs[0]
        now = utc_now_iso()
        run.status = RUN_STATUS_RUNNING
        run.started_at = now
        run.updated_at = now
        run.attempt_count += 1
        self.save(run)
        return run

    def delete(self, run_id: str) -> None:
        path = self._run_path(run_id)
        if not path.exists():
            raise KeyError(f"Run '{run_id}' not found.")
        path.unlink()


class FileJobStore:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)

    def _run_dir(self, run_id: str) -> Path:
        path = self.base_dir / "runs" / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_job_set(self, run_id: str, key: str, jobs: list[JobRecord]) -> None:
        payload = [job.to_dict() for job in jobs]
        _write_json(self._run_dir(run_id) / "job_sets" / f"{key}.json", payload)

    def load_job_set(self, run_id: str, key: str) -> list[JobRecord]:
        payload = _read_json(self._run_dir(run_id) / "job_sets" / f"{key}.json", [])
        return [JobRecord.from_mapping(item) for item in payload if isinstance(item, dict)]

    def list_job_set_keys(self, run_id: str) -> list[str]:
        job_sets_dir = self._run_dir(run_id) / "job_sets"
        if not job_sets_dir.exists():
            return []
        return sorted(path.stem for path in job_sets_dir.glob("*.json"))

    def load_all_job_sets(self, run_id: str) -> dict[str, list[JobRecord]]:
        return {key: self.load_job_set(run_id, key) for key in self.list_job_set_keys(run_id)}

    def load_job_sets_for_runs(self, run_ids: Iterable[str]) -> dict[str, dict[str, list[JobRecord]]]:
        return {
            normalized_run_id: self.load_all_job_sets(normalized_run_id)
            for run_id in run_ids
            if (normalized_run_id := str(run_id or "").strip())
        }

    def delete_job_set(self, run_id: str, key: str) -> None:
        path = self._run_dir(run_id) / "job_sets" / f"{key}.json"
        if path.exists():
            path.unlink()

    def save_blob(self, run_id: str, key: str, value: Any) -> None:
        _write_json(self._run_dir(run_id) / "data" / f"{key}.json", value)

    def load_blob(self, run_id: str, key: str, default=None):
        return _read_json(self._run_dir(run_id) / "data" / f"{key}.json", default)

    def list_blob_keys(self, run_id: str) -> list[str]:
        data_dir = self._run_dir(run_id) / "data"
        if not data_dir.exists():
            return []
        return sorted(path.stem for path in data_dir.glob("*.json"))

    def load_all_blobs(self, run_id: str) -> dict[str, Any]:
        return {key: self.load_blob(run_id, key, None) for key in self.list_blob_keys(run_id)}

    def delete_blob(self, run_id: str, key: str) -> None:
        path = self._run_dir(run_id) / "data" / f"{key}.json"
        if path.exists():
            path.unlink()

    def clear_run(self, run_id: str) -> None:
        for key in self.list_job_set_keys(run_id):
            self.delete_job_set(run_id, key)
        for key in self.list_blob_keys(run_id):
            self.delete_blob(run_id, key)


class FileArtifactStore:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)

    def _artifact_path(self, run_id: str) -> Path:
        return self.base_dir / "runs" / run_id / "artifacts.json"

    def save_artifacts(self, run_id: str, artifacts: list[ArtifactRecord]) -> None:
        _write_json(self._artifact_path(run_id), [artifact.to_dict() for artifact in artifacts])

    def load_artifacts(self, run_id: str) -> list[ArtifactRecord]:
        payload = _read_json(self._artifact_path(run_id), [])
        return [ArtifactRecord.from_dict(item) for item in payload if isinstance(item, dict)]

    def load_artifacts_for_runs(self, run_ids: Iterable[str]) -> dict[str, list[ArtifactRecord]]:
        return {
            normalized_run_id: self.load_artifacts(normalized_run_id)
            for run_id in run_ids
            if (normalized_run_id := str(run_id or "").strip())
        }

    def get_artifact(self, run_id: str, artifact_id: str) -> ArtifactRecord:
        for artifact in self.load_artifacts(run_id):
            if artifact.artifact_id == artifact_id:
                return artifact
        raise KeyError(f"Artifact '{artifact_id}' not found for run '{run_id}'.")

    def upsert_artifact(self, run_id: str, artifact: ArtifactRecord) -> None:
        artifacts = {item.artifact_id: item for item in self.load_artifacts(run_id)}
        artifacts[artifact.artifact_id] = artifact
        self.save_artifacts(run_id, list(artifacts.values()))

    def delete_artifact(self, run_id: str, artifact_id: str) -> None:
        artifacts = {item.artifact_id: item for item in self.load_artifacts(run_id)}
        if artifact_id not in artifacts:
            raise KeyError(f"Artifact '{artifact_id}' not found for run '{run_id}'.")
        del artifacts[artifact_id]
        self.save_artifacts(run_id, list(artifacts.values()))

    def clear_run(self, run_id: str) -> None:
        self.save_artifacts(run_id, [])


class FileReviewStore:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.reviews_dir = self.base_dir / "reviews"
        self.reviews_dir.mkdir(parents=True, exist_ok=True)
        self.status_history_path = self.base_dir / "application_status_history.json"

    def _review_path(self, review_id: str) -> Path:
        return self.reviews_dir / f"{review_id}.json"

    def _normalize_application_status_history_entry(
        self,
        *,
        review_id: Any,
        user_id: Any,
        from_status: Any,
        to_status: Any,
        changed_at: Any = "",
        source: Any = "manual",
    ) -> dict[str, str]:
        normalized_review_id = str(review_id or "").strip()
        if not normalized_review_id:
            raise ValueError("review_id is required for application status history.")
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            raise ValueError("user_id is required for application status history.")
        normalized_source = str(source or "manual").strip() or "manual"
        if normalized_source not in _APPLICATION_STATUS_HISTORY_SOURCES:
            raise ValueError(
                f"source must be one of: {sorted(_APPLICATION_STATUS_HISTORY_SOURCES)}"
            )
        return {
            "review_id": normalized_review_id,
            "user_id": normalized_user_id,
            "from_status": str(from_status or "").strip(),
            "to_status": str(to_status or "").strip(),
            "changed_at": str(changed_at or utc_now_iso()).strip(),
            "source": normalized_source,
        }

    def upsert_review(
        self,
        review: ReviewRecord,
        *,
        application_status_history: dict[str, Any] | None = None,
    ) -> None:
        review.updated_at = utc_now_iso()
        _write_json(self._review_path(review.review_id), review.to_dict())
        if application_status_history is not None:
            self.append_application_status_history(
                review_id=application_status_history.get("review_id") or review.review_id,
                user_id=application_status_history.get("user_id"),
                from_status=application_status_history.get("from_status"),
                to_status=application_status_history.get("to_status"),
                changed_at=application_status_history.get("changed_at") or review.updated_at,
                source=application_status_history.get("source") or "manual",
            )

    def get_review(self, review_id: str) -> ReviewRecord:
        payload = _read_json(self._review_path(review_id), {})
        if not payload:
            raise KeyError(f"Review '{review_id}' not found.")
        return ReviewRecord.from_dict(payload)

    def list_reviews(
        self,
        *,
        run_id: str = "",
        job_id: str = "",
        limit: int = 100,
    ) -> list[ReviewRecord]:
        review_files = sorted(self.reviews_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        reviews = [ReviewRecord.from_dict(_read_json(path, {})) for path in review_files]
        if run_id:
            reviews = [review for review in reviews if review.run_id == run_id]
        if job_id:
            reviews = [review for review in reviews if review.job_id == job_id]
        return reviews[: max(1, int(limit))]

    def list_reviews_for_runs(self, run_ids: Iterable[str]) -> dict[str, list[ReviewRecord]]:
        normalized_run_ids = {
            str(run_id or "").strip()
            for run_id in run_ids
            if str(run_id or "").strip()
        }
        result = {run_id: [] for run_id in normalized_run_ids}
        if not normalized_run_ids:
            return result
        for review in self.list_reviews(limit=100000):
            if review.run_id in result:
                result[review.run_id].append(review)
        return result

    def list_tracker_run_ids(self, run_ids: Iterable[str]) -> set[str]:
        normalized_run_ids = {str(run_id or "").strip() for run_id in run_ids if str(run_id or "").strip()}
        result: set[str] = set()
        reviews_by_run = self.list_reviews_for_runs(normalized_run_ids)
        for run_id, reviews in reviews_by_run.items():
            for review in reviews:
                metadata = dict(review.metadata or {})
                if review.decision == "approved" or str(metadata.get("tracker_status") or "").strip():
                    result.add(run_id)
                    break
        return result

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
        entry = self._normalize_application_status_history_entry(
            review_id=review_id,
            user_id=user_id,
            from_status=from_status,
            to_status=to_status,
            changed_at=changed_at,
            source=source,
        )
        history = _read_json(self.status_history_path, [])
        if not isinstance(history, list):
            history = []
        history.append(entry)
        _write_json(self.status_history_path, history)

    def list_application_status_history(
        self,
        *,
        review_id: str = "",
        user_id: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        history = _read_json(self.status_history_path, [])
        if not isinstance(history, list):
            return []
        rows = [item for item in history if isinstance(item, dict)]
        if review_id:
            rows = [item for item in rows if str(item.get("review_id") or "") == review_id]
        if user_id:
            rows = [item for item in rows if str(item.get("user_id") or "") == user_id]
        rows.sort(key=lambda item: (str(item.get("changed_at") or ""), str(item.get("review_id") or "")))
        normalized_offset = max(0, int(offset))
        normalized_limit = max(1, int(limit))
        return rows[normalized_offset : normalized_offset + normalized_limit]

    def delete_review(self, review_id: str) -> None:
        path = self._review_path(review_id)
        if not path.exists():
            raise KeyError(f"Review '{review_id}' not found.")
        path.unlink()


class FileAuthRepository:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.users_path = self.base_dir / "users.json"
        self.tokens_path = self.base_dir / "api_tokens.json"
        self.assisted_apply_connections_path = self.base_dir / "assisted_apply_connections.json"
        if not self.users_path.exists():
            _write_json(self.users_path, [])
        if not self.tokens_path.exists():
            _write_json(self.tokens_path, [])
        if not self.assisted_apply_connections_path.exists():
            _write_json(self.assisted_apply_connections_path, [])

    def list_users(self) -> list[UserRecord]:
        payload = _read_json(self.users_path, [])
        return [UserRecord.from_dict(item) for item in payload if isinstance(item, dict)]

    def get_user(self, user_id: str) -> UserRecord:
        for user in self.list_users():
            if user.user_id == user_id:
                return user
        raise KeyError(f"User '{user_id}' not found.")

    def get_user_by_email(self, email: str) -> UserRecord:
        normalized_email = str(email).strip().lower()
        for user in self.list_users():
            if user.email.strip().lower() == normalized_email:
                return user
        raise KeyError(f"User with email '{email}' not found.")

    def upsert_user(self, user: UserRecord) -> None:
        users = {item.user_id: item for item in self.list_users()}
        users[user.user_id] = user
        _write_json(self.users_path, [item.to_dict() for item in users.values()])

    def delete_user(self, user_id: str) -> None:
        with _FILE_BACKEND_LOCK:
            users = {item.user_id: item for item in self.list_users()}
            if user_id not in users:
                raise KeyError(f"User '{user_id}' not found.")
            del users[user_id]
            _write_json(self.users_path, [item.to_dict() for item in users.values()])
            tokens = [token for token in self.list_api_tokens() if token.user_id != user_id]
            _write_json(self.tokens_path, [token.to_storage_dict() for token in tokens])
            connections = [
                record
                for record in self.list_assisted_apply_connections()
                if record.user_id != user_id
            ]
            self._write_assisted_apply_connections(connections)

    def list_api_tokens(self, *, user_id: str = "", active_only: bool = False) -> list[ApiTokenRecord]:
        payload = _read_json(self.tokens_path, [])
        tokens = [ApiTokenRecord.from_dict(item) for item in payload if isinstance(item, dict)]
        if user_id:
            tokens = [token for token in tokens if token.user_id == user_id]
        if active_only:
            tokens = [token for token in tokens if token.is_active]
        return tokens

    def list_api_tokens_for_value(self, raw_token: str, *, active_only: bool = False) -> list[ApiTokenRecord]:
        normalized_token = str(raw_token or "").strip()
        if not normalized_token:
            return []
        candidate_prefix = normalized_token[:API_TOKEN_PREFIX_LENGTH]
        return [
            token
            for token in self.list_api_tokens(active_only=active_only)
            if token.token_prefix == candidate_prefix or normalized_token.startswith(token.token_prefix)
        ]

    def get_api_token(self, token_id: str) -> ApiTokenRecord:
        for token in self.list_api_tokens():
            if token.token_id == token_id:
                return token
        raise KeyError(f"API token '{token_id}' not found.")

    def upsert_api_token(self, token: ApiTokenRecord) -> None:
        tokens = {item.token_id: item for item in self.list_api_tokens()}
        tokens[token.token_id] = token
        _write_json(self.tokens_path, [item.to_storage_dict() for item in tokens.values()])

    def delete_api_token(self, token_id: str) -> None:
        tokens = {item.token_id: item for item in self.list_api_tokens()}
        if token_id not in tokens:
            raise KeyError(f"API token '{token_id}' not found.")
        del tokens[token_id]
        _write_json(self.tokens_path, [item.to_storage_dict() for item in tokens.values()])

    def _read_assisted_apply_connections(self) -> list[AssistedApplyConnectionRecord]:
        payload = _read_json(self.assisted_apply_connections_path, [])
        return [
            AssistedApplyConnectionRecord.from_dict(item)
            for item in payload
            if isinstance(item, dict)
        ]

    def _write_assisted_apply_connections(
        self,
        records: Iterable[AssistedApplyConnectionRecord],
    ) -> None:
        _write_json(
            self.assisted_apply_connections_path,
            [record.to_dict() for record in records],
        )

    def create_assisted_apply_connection(self, record: AssistedApplyConnectionRecord) -> None:
        with _FILE_BACKEND_LOCK:
            records = {item.request_id: item for item in self._read_assisted_apply_connections()}
            if record.request_id in records:
                raise ValueError(f"Assisted Apply connection '{record.request_id}' already exists.")
            records[record.request_id] = record
            self._write_assisted_apply_connections(records.values())

    def get_assisted_apply_connection(self, request_id: str) -> AssistedApplyConnectionRecord:
        normalized_request_id = str(request_id or "").strip()
        with _FILE_BACKEND_LOCK:
            for record in self._read_assisted_apply_connections():
                if record.request_id == normalized_request_id:
                    return record
        raise KeyError(f"Assisted Apply connection '{normalized_request_id}' not found.")

    def list_assisted_apply_connections(
        self,
        *,
        user_id: str = "",
        status: str = "",
    ) -> list[AssistedApplyConnectionRecord]:
        with _FILE_BACKEND_LOCK:
            records = self._read_assisted_apply_connections()
        if user_id:
            records = [record for record in records if record.user_id == user_id]
        if status:
            records = [record for record in records if record.status == status]
        return sorted(records, key=lambda record: (record.updated_at, record.request_id), reverse=True)

    def list_assisted_apply_connections_for_session_prefix(
        self,
        session_token_prefix: str,
    ) -> list[AssistedApplyConnectionRecord]:
        normalized_prefix = str(session_token_prefix or "").strip()
        if not normalized_prefix:
            return []
        return [
            record
            for record in self.list_assisted_apply_connections(status=ASSISTED_APPLY_STATUS_ACTIVE)
            if record.session_token_prefix == normalized_prefix
        ]

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
        with _FILE_BACKEND_LOCK:
            records = {item.request_id: item for item in self._read_assisted_apply_connections()}
            record = records.get(str(request_id or "").strip())
            if (
                record is None
                or record.status != ASSISTED_APPLY_STATUS_PENDING
                or bool(record.user_id)
                or not _timestamp_is_after(record.request_expires_at, authorized_at)
            ):
                return None
            record.status = ASSISTED_APPLY_STATUS_AUTHORIZED
            record.user_id = str(user_id or "").strip()
            record.authorization_code_prefix = str(authorization_code_prefix or "").strip()
            record.authorization_code_hash = str(authorization_code_hash or "").strip()
            record.authorization_code_expires_at = str(authorization_code_expires_at or "").strip()
            record.authorized_at = str(authorized_at or "").strip()
            record.updated_at = record.authorized_at
            self._write_assisted_apply_connections(records.values())
            return record

    def reject_assisted_apply_connection(
        self,
        request_id: str,
        *,
        user_id: str,
        rejected_at: str,
    ) -> AssistedApplyConnectionRecord | None:
        with _FILE_BACKEND_LOCK:
            records = {item.request_id: item for item in self._read_assisted_apply_connections()}
            record = records.get(str(request_id or "").strip())
            if (
                record is None
                or record.status != ASSISTED_APPLY_STATUS_PENDING
                or bool(record.user_id)
                or not _timestamp_is_after(record.request_expires_at, rejected_at)
            ):
                return None
            record.status = ASSISTED_APPLY_STATUS_REJECTED
            record.user_id = str(user_id or "").strip()
            record.rejected_at = str(rejected_at or "").strip()
            record.updated_at = record.rejected_at
            self._write_assisted_apply_connections(records.values())
            return record

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
        with _FILE_BACKEND_LOCK:
            records = {item.request_id: item for item in self._read_assisted_apply_connections()}
            record = records.get(str(request_id or "").strip())
            if (
                record is None
                or record.status != ASSISTED_APPLY_STATUS_AUTHORIZED
                or bool(record.code_consumed_at)
                or record.extension_origin != str(extension_origin or "").strip()
                or not _timestamp_is_after(record.authorization_code_expires_at, activated_at)
            ):
                return None
            record.status = ASSISTED_APPLY_STATUS_ACTIVE
            record.code_consumed_at = str(activated_at or "").strip()
            record.authorization_code_prefix = ""
            record.authorization_code_hash = ""
            record.session_token_prefix = str(session_token_prefix or "").strip()
            record.session_token_hash = str(session_token_hash or "").strip()
            record.session_expires_at = str(session_expires_at or "").strip()
            record.activated_at = str(activated_at or "").strip()
            record.last_used_at = record.activated_at
            record.updated_at = record.activated_at
            self._write_assisted_apply_connections(records.values())
            return record

    def expire_assisted_apply_connection(
        self,
        request_id: str,
        *,
        expected_status: str,
        expired_at: str,
    ) -> AssistedApplyConnectionRecord | None:
        with _FILE_BACKEND_LOCK:
            records = {item.request_id: item for item in self._read_assisted_apply_connections()}
            record = records.get(str(request_id or "").strip())
            if record is None or record.status != str(expected_status or "").strip():
                return None
            record.status = ASSISTED_APPLY_STATUS_EXPIRED
            record.expired_at = str(expired_at or "").strip()
            record.updated_at = record.expired_at
            record.authorization_code_prefix = ""
            record.authorization_code_hash = ""
            record.session_token_prefix = ""
            record.session_token_hash = ""
            self._write_assisted_apply_connections(records.values())
            return record

    def touch_assisted_apply_session(
        self,
        request_id: str,
        *,
        last_used_at: str,
    ) -> AssistedApplyConnectionRecord | None:
        with _FILE_BACKEND_LOCK:
            records = {item.request_id: item for item in self._read_assisted_apply_connections()}
            record = records.get(str(request_id or "").strip())
            if (
                record is None
                or record.status != ASSISTED_APPLY_STATUS_ACTIVE
                or not _timestamp_is_after(record.session_expires_at, last_used_at)
            ):
                return None
            record.last_used_at = str(last_used_at or "").strip()
            record.updated_at = record.last_used_at
            self._write_assisted_apply_connections(records.values())
            return record

    def revoke_assisted_apply_connection(
        self,
        request_id: str,
        *,
        user_id: str,
        revoked_at: str,
    ) -> AssistedApplyConnectionRecord | None:
        with _FILE_BACKEND_LOCK:
            records = {item.request_id: item for item in self._read_assisted_apply_connections()}
            record = records.get(str(request_id or "").strip())
            if (
                record is None
                or record.user_id != str(user_id or "").strip()
                or record.status not in {ASSISTED_APPLY_STATUS_AUTHORIZED, ASSISTED_APPLY_STATUS_ACTIVE}
            ):
                return None
            record.status = ASSISTED_APPLY_STATUS_REVOKED
            record.revoked_at = str(revoked_at or "").strip()
            record.updated_at = record.revoked_at
            record.authorization_code_prefix = ""
            record.authorization_code_hash = ""
            record.session_token_prefix = ""
            record.session_token_hash = ""
            self._write_assisted_apply_connections(records.values())
            return record

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
        with _FILE_BACKEND_LOCK:
            users = {item.user_id: item for item in self.list_users()}
            user = users.get(normalized_user_id)
            if user is None:
                raise KeyError(f"User '{normalized_user_id}' not found.")
            metadata = dict(user.metadata or {})
            stored = metadata.get(ASSISTED_APPLY_PREFERENCES_METADATA_KEY)
            current = AssistedApplyPreferences.from_stored(
                stored if isinstance(stored, dict) else None
            )
            if current.revision != int(expected_revision):
                return False
            metadata[ASSISTED_APPLY_PREFERENCES_METADATA_KEY] = preferences.to_dict()
            user.metadata = metadata
            user.updated_at = str(updated_at or "").strip()
            users[user.user_id] = user
            _write_json(self.users_path, [item.to_dict() for item in users.values()])
            return True


class FileSecretStore:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.secrets_path = self.base_dir / "secrets.json"
        if not self.secrets_path.exists():
            _write_json(self.secrets_path, [])

    def list_secrets(self, *, workspace_id: str = "") -> list[SecretRecord]:
        payload = _read_json(self.secrets_path, [])
        secrets = [SecretRecord.from_dict(item) for item in payload if isinstance(item, dict)]
        if workspace_id:
            secrets = [secret for secret in secrets if secret.workspace_id in {"", workspace_id}]
        return secrets

    def get_secret(self, secret_id: str) -> SecretRecord:
        for secret in self.list_secrets():
            if secret.secret_id == secret_id:
                return secret
        raise KeyError(f"Secret '{secret_id}' not found.")

    def upsert_secret(self, secret: SecretRecord) -> None:
        secrets = {item.secret_id: item for item in self.list_secrets()}
        secrets[secret.secret_id] = secret
        _write_json(self.secrets_path, [item.to_storage_dict() for item in secrets.values()])

    def delete_secret(self, secret_id: str) -> None:
        secrets = {item.secret_id: item for item in self.list_secrets()}
        if secret_id not in secrets:
            raise KeyError(f"Secret '{secret_id}' not found.")
        del secrets[secret_id]
        _write_json(self.secrets_path, [item.to_storage_dict() for item in secrets.values()])


class FileWorkerStore:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.workers_path = self.base_dir / "workers.json"
        self._worker_lock = _FILE_BACKEND_LOCK
        if not self.workers_path.exists():
            _write_json(self.workers_path, [])

    def list_workers(self, *, limit: int = 50, offset: int = 0, status: str = "") -> list[WorkerRecord]:
        with self._worker_lock:
            payload = _read_json(self.workers_path, [])
            workers = [WorkerRecord.from_dict(item) for item in payload if isinstance(item, dict)]
            workers.sort(key=lambda item: item.last_heartbeat_at, reverse=True)
            if status:
                workers = [worker for worker in workers if worker.status == status]
            normalized_offset = max(0, int(offset))
            normalized_limit = max(1, int(limit))
            return workers[normalized_offset : normalized_offset + normalized_limit]

    def list_expired_workers(self, *, expires_before: str) -> list[WorkerRecord]:
        with self._worker_lock:
            payload = _read_json(self.workers_path, [])
            workers = [WorkerRecord.from_dict(item) for item in payload if isinstance(item, dict)]
            return [
                worker
                for worker in workers
                if worker.lease_expires_at and worker.lease_expires_at <= expires_before and worker.current_run_id
            ]

    def get_worker(self, worker_id: str) -> WorkerRecord:
        for worker in self.list_workers(limit=100000):
            if worker.worker_id == worker_id:
                return worker
        raise KeyError(f"Worker '{worker_id}' not found.")

    def upsert_worker(self, worker: WorkerRecord) -> None:
        with self._worker_lock:
            workers = {item.worker_id: item for item in self.list_workers(limit=100000)}
            workers[worker.worker_id] = worker
            _write_json(self.workers_path, [item.to_dict() for item in workers.values()])

    def renew_worker_lease_if_owned(
        self,
        observed: WorkerRecord,
        renewed: WorkerRecord,
        *,
        run_attempt_count: int,
    ) -> bool:
        with self._worker_lock:
            workers = {item.worker_id: item for item in self.list_workers(limit=100000)}
            current = workers.get(observed.worker_id)
            if current is None:
                return False
            if (
                current.status != WORKER_STATUS_RUNNING
                or current.current_run_id != observed.current_run_id
                or current.last_heartbeat_at != observed.last_heartbeat_at
                or current.lease_expires_at != observed.lease_expires_at
            ):
                return False
            run_payload = _read_json(self.base_dir / "runs" / f"{observed.current_run_id}.json", {})
            if not run_payload:
                return False
            run = RunRecord.from_dict(run_payload)
            if run.status not in {RUN_STATUS_RUNNING, RUN_STATUS_CANCEL_REQUESTED} or run.attempt_count != max(
                1,
                int(run_attempt_count),
            ):
                return False
            workers[renewed.worker_id] = renewed
            _write_json(self.workers_path, [item.to_dict() for item in workers.values()])
            return True

    def mark_stale_if_expired(
        self,
        worker: WorkerRecord,
        *,
        expires_before: str,
        stale_at: str,
    ) -> bool:
        with self._worker_lock:
            workers = {item.worker_id: item for item in self.list_workers(limit=100000)}
            current = workers.get(worker.worker_id)
            if current is None:
                return False
            if (
                current.status != worker.status
                or current.current_run_id != worker.current_run_id
                or current.last_heartbeat_at != worker.last_heartbeat_at
                or current.lease_expires_at != worker.lease_expires_at
                or not current.lease_expires_at
                or current.lease_expires_at > expires_before
            ):
                return False
            current.status = WORKER_STATUS_STALE
            current.current_run_id = ""
            current.last_heartbeat_at = stale_at
            current.lease_expires_at = stale_at
            workers[current.worker_id] = current
            _write_json(self.workers_path, [item.to_dict() for item in workers.values()])
            return True

    def delete_worker(self, worker_id: str) -> None:
        with self._worker_lock:
            workers = {item.worker_id: item for item in self.list_workers(limit=100000)}
            if worker_id not in workers:
                raise KeyError(f"Worker '{worker_id}' not found.")
            del workers[worker_id]
            _write_json(self.workers_path, [item.to_dict() for item in workers.values()])


class FileAnalyticsStore:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.events_path = self.base_dir / "analytics_events.json"
        if not self.events_path.exists():
            _write_json(self.events_path, [])

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
        events = _read_json(self.events_path, [])
        if not isinstance(events, list):
            events = []
        events.append(
            {
                "event_id": str(event_id or "").strip(),
                "event_name": str(event_name or "").strip(),
                "occurred_at": str(occurred_at or utc_now_iso()).strip(),
                "user_id": str(user_id or "").strip(),
                "workspace_id": str(workspace_id or "").strip(),
                "run_id": str(run_id or "").strip(),
                "job_id": str(job_id or "").strip(),
                "review_id": str(review_id or "").strip(),
                "session_id": str(session_id or "").strip(),
                "route": str(route or "").strip(),
                "source": str(source or "").strip(),
                "payload_json": dict(payload or {}),
            }
        )
        _write_json(self.events_path, events)

    def query_rows(self, query: str, params: Iterable[Any] | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError("Analytics SQL queries require the sqlite storage backend.")

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
        normalized_event_name = str(event_name or "").strip().lower()
        normalized_user_id = str(user_id or "").strip().lower()
        normalized_occurred_from = str(occurred_from or "").strip()
        normalized_occurred_to = str(occurred_to or "").strip()
        events = _read_json(self.events_path, [])
        if not isinstance(events, list):
            events = []

        filtered_events = []
        for item in events:
            if not isinstance(item, dict):
                continue
            occurred_at = str(item.get("occurred_at") or "").strip()
            item_event_name = str(item.get("event_name") or "").strip().lower()
            item_user_id = str(item.get("user_id") or "").strip().lower()
            if normalized_event_name and normalized_event_name not in item_event_name:
                continue
            if normalized_user_id and normalized_user_id not in item_user_id:
                continue
            if normalized_occurred_from and occurred_at < normalized_occurred_from:
                continue
            if normalized_occurred_to and occurred_at >= normalized_occurred_to:
                continue
            filtered_events.append(
                {
                    "event_id": str(item.get("event_id") or ""),
                    "event_name": str(item.get("event_name") or ""),
                    "occurred_at": occurred_at,
                    "user_id": str(item.get("user_id") or ""),
                    "workspace_id": str(item.get("workspace_id") or ""),
                    "run_id": str(item.get("run_id") or ""),
                    "job_id": str(item.get("job_id") or ""),
                    "review_id": str(item.get("review_id") or ""),
                    "session_id": str(item.get("session_id") or ""),
                    "route": str(item.get("route") or ""),
                    "source": str(item.get("source") or ""),
                    "payload": dict(item.get("payload_json") or {}),
                }
            )

        filtered_events.sort(
            key=lambda entry: (str(entry.get("occurred_at") or ""), str(entry.get("event_id") or "")),
            reverse=True,
        )
        start = max(0, int(offset))
        stop = start + max(0, int(limit))
        return filtered_events[start:stop]

    def count_events(
        self,
        *,
        event_name: str = "",
        user_id: str = "",
        occurred_from: str = "",
        occurred_to: str = "",
    ) -> int:
        return len(
            self.list_events(
                limit=10_000_000,
                offset=0,
                event_name=event_name,
                user_id=user_id,
                occurred_from=occurred_from,
                occurred_to=occurred_to,
            )
        )


class FileConfigStore:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.config_path = self.base_dir / "app_config.json"

    def _read_all(self) -> dict[str, Any]:
        payload = _read_json(self.config_path, {})
        if not isinstance(payload, dict):
            return {}
        return dict(payload)

    def _write_all(self, payload: dict[str, Any]) -> None:
        _write_json(self.config_path, payload)

    def get_value(self, config_key: str, default: Any = None):
        payload = self._read_all()
        normalized_key = str(config_key or "").strip()
        if not normalized_key:
            return default
        return payload.get(normalized_key, default)

    def set_value(self, config_key: str, value: Any) -> None:
        normalized_key = str(config_key or "").strip()
        if not normalized_key:
            raise ValueError("config_key is required")
        payload = self._read_all()
        payload[normalized_key] = value
        self._write_all(payload)

    def delete_value(self, config_key: str) -> None:
        normalized_key = str(config_key or "").strip()
        if not normalized_key:
            raise ValueError("config_key is required")
        payload = self._read_all()
        if normalized_key in payload:
            del payload[normalized_key]
            self._write_all(payload)

    def list_values(self, *, prefix: str = "") -> dict[str, Any]:
        payload = self._read_all()
        normalized_prefix = str(prefix or "").strip()
        if not normalized_prefix:
            return payload
        return {
            key: value
            for key, value in payload.items()
            if str(key).startswith(normalized_prefix)
        }



class FileCareerProfileStore:
    """File-backed career profile persistence."""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.profiles_path = self.base_dir / "career_profiles.json"

    def _read_all(self) -> dict[str, dict[str, Any]]:
        payload = _read_json(self.profiles_path, {})
        if not isinstance(payload, dict):
            return {}
        return {str(key): dict(value) for key, value in payload.items() if isinstance(value, dict)}

    def _write_all(self, payload: dict[str, dict[str, Any]]) -> None:
        _write_json(self.profiles_path, payload)

    def list_profiles(self, *, user_id: str = "", limit: int = 50, offset: int = 0) -> list:
        from backend.domain.models import CareerProfile

        all_profiles = self._read_all()
        profiles = [CareerProfile.from_dict(p) for p in all_profiles.values()]
        if user_id:
            profiles = [p for p in profiles if p.user_id == user_id]
        profiles.sort(key=lambda p: p.updated_at, reverse=True)
        return profiles[max(0, int(offset)) : max(0, int(offset)) + max(1, int(limit))]

    def get_profile(self, profile_id: str) -> "CareerProfile":
        from backend.domain.models import CareerProfile

        all_profiles = self._read_all()
        payload = all_profiles.get(profile_id)
        if payload is None:
            raise KeyError(f"Career profile '{profile_id}' not found.")
        return CareerProfile.from_dict(payload)

    def upsert_profile(self, profile: "CareerProfile") -> None:
        all_profiles = self._read_all()
        all_profiles[profile.profile_id] = profile.to_dict()
        self._write_all(all_profiles)

    def list_profiles_by_workspace(self, workspace_id: str) -> list:
        from backend.domain.models import CareerProfile

        all_profiles = self._read_all()
        profiles = [CareerProfile.from_dict(p) for p in all_profiles.values()]
        return [p for p in profiles if p.bound_workspace_id == workspace_id]

    def delete_profile(self, profile_id: str) -> None:
        all_profiles = self._read_all()
        if profile_id not in all_profiles:
            raise KeyError(f"Career profile '{profile_id}' not found.")
        del all_profiles[profile_id]
        self._write_all(all_profiles)
