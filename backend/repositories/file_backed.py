from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from backend.domain.models import (
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    ApiTokenRecord,
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

    def _run_path(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.json"

    def save(self, run: RunRecord) -> None:
        _write_json(self._run_path(run.id), run.to_dict())

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

    def _review_path(self, review_id: str) -> Path:
        return self.reviews_dir / f"{review_id}.json"

    def upsert_review(self, review: ReviewRecord) -> None:
        review.updated_at = utc_now_iso()
        _write_json(self._review_path(review.review_id), review.to_dict())

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
        if not self.users_path.exists():
            _write_json(self.users_path, [])
        if not self.tokens_path.exists():
            _write_json(self.tokens_path, [])

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
        users = {item.user_id: item for item in self.list_users()}
        if user_id not in users:
            raise KeyError(f"User '{user_id}' not found.")
        del users[user_id]
        _write_json(self.users_path, [item.to_dict() for item in users.values()])
        tokens = [token for token in self.list_api_tokens() if token.user_id != user_id]
        _write_json(self.tokens_path, [token.to_storage_dict() for token in tokens])

    def list_api_tokens(self, *, user_id: str = "", active_only: bool = False) -> list[ApiTokenRecord]:
        payload = _read_json(self.tokens_path, [])
        tokens = [ApiTokenRecord.from_dict(item) for item in payload if isinstance(item, dict)]
        if user_id:
            tokens = [token for token in tokens if token.user_id == user_id]
        if active_only:
            tokens = [token for token in tokens if token.is_active]
        return tokens

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
        if not self.workers_path.exists():
            _write_json(self.workers_path, [])

    def list_workers(self, *, limit: int = 50, offset: int = 0, status: str = "") -> list[WorkerRecord]:
        payload = _read_json(self.workers_path, [])
        workers = [WorkerRecord.from_dict(item) for item in payload if isinstance(item, dict)]
        workers.sort(key=lambda item: item.last_heartbeat_at, reverse=True)
        if status:
            workers = [worker for worker in workers if worker.status == status]
        normalized_offset = max(0, int(offset))
        normalized_limit = max(1, int(limit))
        return workers[normalized_offset : normalized_offset + normalized_limit]

    def list_expired_workers(self, *, expires_before: str) -> list[WorkerRecord]:
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
        workers = {item.worker_id: item for item in self.list_workers(limit=100000)}
        workers[worker.worker_id] = worker
        _write_json(self.workers_path, [item.to_dict() for item in workers.values()])

    def delete_worker(self, worker_id: str) -> None:
        workers = {item.worker_id: item for item in self.list_workers(limit=100000)}
        if worker_id not in workers:
            raise KeyError(f"Worker '{worker_id}' not found.")
        del workers[worker_id]
        _write_json(self.workers_path, [item.to_dict() for item in workers.values()])


@dataclass(slots=True)
class BackendRepositories:
    workspace_repository: Any
    run_repository: Any
    job_store: Any
    artifact_store: Any
    review_store: Any
    auth_repository: Any
    secret_store: Any
    worker_store: Any
