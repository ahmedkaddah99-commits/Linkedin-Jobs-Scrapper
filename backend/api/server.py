from __future__ import annotations

import json
import mimetypes
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from backend.bootstrap import create_backend
from backend.domain.models import (
    TOKEN_SCOPE_ARTIFACTS_READ,
    TOKEN_SCOPE_ARTIFACTS_WRITE,
    TOKEN_SCOPE_REVIEWS_READ,
    TOKEN_SCOPE_REVIEWS_WRITE,
    TOKEN_SCOPE_RUNS_READ,
    TOKEN_SCOPE_RUNS_WRITE,
    TOKEN_SCOPE_SECRETS_READ,
    TOKEN_SCOPE_SECRETS_WRITE,
    TOKEN_SCOPE_TEMPLATES_READ,
    TOKEN_SCOPE_TEMPLATES_WRITE,
    TOKEN_SCOPE_USERS_READ,
    TOKEN_SCOPE_USERS_WRITE,
    TOKEN_SCOPE_WORKER_EXECUTE,
    TOKEN_SCOPE_WORKSPACES_READ,
    TOKEN_SCOPE_WORKSPACES_WRITE,
)


def _json_bytes(payload) -> bytes:
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")


def _workspace_summary(workspace) -> dict:
    return {
        "id": workspace.id,
        "name": workspace.name,
        "workflow_template_id": workspace.workflow_template_id,
        "workspace_type": workspace.workspace_type,
        "feature_flags": workspace.feature_flags,
        "sources": [source.to_dict() for source in workspace.sources],
    }


def _workflow_template_summary(template) -> dict:
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "stages": [stage.to_dict() for stage in template.stages],
        "default_run_settings": dict(template.default_run_settings),
    }


def _component_summary(descriptor) -> dict:
    return {
        "id": descriptor.id,
        "kind": descriptor.kind,
        "name": descriptor.name,
        "description": descriptor.description,
        "metadata": dict(descriptor.metadata),
    }


def _run_summary(run) -> dict:
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "workflow_template_id": run.workflow_template_id,
        "status": run.status,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "queued_at": run.queued_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "attempt_count": run.attempt_count,
        "max_attempts": run.max_attempts,
        "current_stage_id": run.current_stage_id,
        "last_error": run.last_error,
        "stage_results": [result.to_dict() for result in run.stage_results],
        "final_job_set_keys": run.final_job_set_keys,
    }


def _workspace_option(workspace) -> dict:
    return {"id": workspace.id, "name": workspace.name, "workspace_type": workspace.workspace_type}


def _build_settings_payload(application, user) -> dict:
    workspaces = [workspace for workspace in application.list_workspaces() if application.user_can_access_workspace(user, workspace.id)]
    profile_options: dict[str, dict] = {}
    prompt_set_options: dict[str, dict] = {}
    for workspace in workspaces:
        for profile in workspace.profiles:
            profile_options.setdefault(profile.id, {"id": profile.id, "label": profile.label, "settings": dict(profile.settings)})
        for prompt_set in workspace.prompt_sets:
            prompt_set_options.setdefault(
                prompt_set.id,
                {"id": prompt_set.id, "family": prompt_set.family, "settings": dict(prompt_set.settings)},
            )

    metadata = dict(user.metadata or {})
    profile = dict(metadata.get("profile") or {})
    defaults = dict(metadata.get("defaults") or {})
    documents = dict(metadata.get("documents") or {})
    review_preferences = dict(metadata.get("review_preferences") or {})

    if not defaults.get("default_workspace_id") and workspaces:
        defaults["default_workspace_id"] = workspaces[0].id
    if not defaults.get("default_execution_mode"):
        defaults["default_execution_mode"] = "queued"
    if not defaults.get("default_profile_id") and profile_options:
        defaults["default_profile_id"] = next(iter(profile_options.keys()))
    if not defaults.get("default_prompt_set_id") and prompt_set_options:
        defaults["default_prompt_set_id"] = next(iter(prompt_set_options.keys()))
    if "max_jobs_per_run" not in defaults:
        defaults["max_jobs_per_run"] = 25

    if "generate_docx" not in documents:
        documents["generate_docx"] = True
    if "generate_pdf" not in documents:
        documents["generate_pdf"] = True
    if "export_tracker" not in documents:
        documents["export_tracker"] = True
    if "export_package" not in documents:
        documents["export_package"] = True
    if not documents.get("file_naming"):
        documents["file_naming"] = "workspace_job_title"

    if "require_review_before_use" not in review_preferences:
        review_preferences["require_review_before_use"] = True
    if not review_preferences.get("default_decision_state"):
        review_preferences["default_decision_state"] = "waiting_review"
    if "rejection_note_required" not in review_preferences:
        review_preferences["rejection_note_required"] = True
    if "auto_open_next_item" not in review_preferences:
        review_preferences["auto_open_next_item"] = True

    profile_section = {
        "name": str(profile.get("name") or user.display_name or user.email.split("@")[0]),
        "role_title": str(profile.get("role_title") or ""),
        "email": str(profile.get("email") or user.email),
        "location": str(profile.get("location") or ""),
        "website": str(profile.get("website") or ""),
        "avatar_url": str(profile.get("avatar_url") or ""),
        "summary": str(profile.get("summary") or ""),
        "competencies": [str(item) for item in profile.get("competencies") or [] if str(item).strip()],
        "recent_experience": [
            {
                "title": str(item.get("title") or ""),
                "company": str(item.get("company") or ""),
                "period": str(item.get("period") or ""),
            }
            for item in profile.get("recent_experience") or []
            if isinstance(item, dict)
        ],
    }

    return {
        "profile": profile_section,
        "defaults": defaults,
        "documents": documents,
        "review_preferences": review_preferences,
        "account": {
            "display_name": user.display_name,
            "email": user.email,
            "role": user.role,
            "allowed_workspace_ids": list(user.allowed_workspace_ids),
            "is_active": user.is_active,
        },
        "options": {
            "workspaces": [_workspace_option(workspace) for workspace in workspaces],
            "profiles": list(profile_options.values()),
            "prompt_sets": list(prompt_set_options.values()),
            "execution_modes": [
                {"id": "queued", "label": "Queued"},
                {"id": "planned", "label": "Planned"},
                {"id": "sync", "label": "Run Immediately"},
            ],
            "review_default_states": [
                {"id": "waiting_review", "label": "Waiting Review"},
                {"id": "approved", "label": "Approved"},
                {"id": "rejected", "label": "Rejected"},
            ],
            "document_naming_modes": [
                {"id": "workspace_job_title", "label": "Workspace + Job Title"},
                {"id": "company_job_title", "label": "Company + Job Title"},
                {"id": "run_artifact_id", "label": "Run + Artifact ID"},
            ],
        },
    }


def _collect_authorized_runs(application, user, *, workspace_id: str = "") -> tuple[dict[str, object], list[object]]:
    workspaces = {
        workspace.id: workspace
        for workspace in application.list_workspaces()
        if application.user_can_access_workspace(user, workspace.id)
    }
    runs = [
        run
        for run in application.list_runs(limit=1000, offset=0, status="", workspace_id=workspace_id)
        if application.user_can_access_workspace(user, run.workspace_id)
    ]
    return workspaces, runs


def _collect_review_queue_entries(application, user, *, workspace_id: str = "", run_id: str = "") -> list[dict]:
    workspaces, runs = _collect_authorized_runs(application, user, workspace_id=workspace_id)
    entries: list[dict] = []
    for run in runs:
        if run_id and run.id != run_id:
            continue
        job_sets = application.list_job_sets(run.id)
        review_records = application.list_reviews(run_id=run.id, limit=1000, offset=0)
        reviews_by_job: dict[str, object] = {}
        for review in review_records:
            reviews_by_job.setdefault(review.job_id, review)
        artifact_count = len(application.list_artifacts(run.id))
        workspace = workspaces.get(run.workspace_id)
        preferred_keys = run.final_job_set_keys or list(job_sets.keys())
        for set_key in preferred_keys:
            for job in job_sets.get(set_key, []):
                review = reviews_by_job.get(job.job_id)
                status = str((review.status if review else "") or "waiting_review")
                entries.append(
                    {
                        "review_id": review.review_id if review else "",
                        "run_id": run.id,
                        "workspace_id": run.workspace_id,
                        "workspace_name": workspace.name if workspace else run.workspace_id,
                        "job_set_key": set_key,
                        "job_id": job.job_id,
                        "title": job.title,
                        "company": job.company,
                        "source_label": job.portal or job.source_type or "unknown",
                        "source_type": job.source_type,
                        "status": status,
                        "decision": review.decision if review else "",
                        "reviewer": review.reviewer if review else "",
                        "notes": review.notes if review else "",
                        "artifact_status": "artifact_ready" if artifact_count else "no_artifact",
                        "artifact_count": artifact_count,
                        "apply_link": job.apply_link or job.link or job.source_url,
                        "location": job.location_raw,
                        "filter_status": job.filter_status,
                        "manual_approved": bool(job.manual_approved),
                        "updated_at": review.updated_at if review else run.updated_at,
                    }
                )
    entries.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return entries


def _collect_artifact_entries(application, user, *, workspace_id: str = "", run_id: str = "") -> list[dict]:
    workspaces, runs = _collect_authorized_runs(application, user, workspace_id=workspace_id)
    entries: list[dict] = []
    for run in runs:
        if run_id and run.id != run_id:
            continue
        workspace = workspaces.get(run.workspace_id)
        artifacts = application.list_artifacts(run.id)
        for artifact in artifacts:
            metadata = dict(artifact.metadata or {})
            entries.append(
                {
                    "artifact_id": artifact.artifact_id,
                    "artifact_type": artifact.artifact_type,
                    "path": artifact.path,
                    "file_name": Path(artifact.path).name or artifact.artifact_id,
                    "workspace_id": run.workspace_id,
                    "workspace_name": workspace.name if workspace else run.workspace_id,
                    "run_id": run.id,
                    "created_at": run.finished_at or run.updated_at,
                    "job_title": str(metadata.get("job_title") or ""),
                    "company": str(metadata.get("company") or ""),
                    "status": str(metadata.get("status") or ("ready" if artifact.path else "missing")),
                    "download_url": f"/v1/runs/{run.id}/artifacts/{artifact.artifact_id}/download",
                    "metadata": metadata,
                }
            )
    entries.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return entries


def _dashboard_payload(application, user) -> dict:
    workspaces, runs = _collect_authorized_runs(application, user)
    review_queue = _collect_review_queue_entries(application, user)
    workers = application.list_workers(limit=100, offset=0, status="")
    today_iso = datetime.now(timezone.utc).date().isoformat()
    completed_today = sum(
        1
        for run in runs
        if run.status == "completed" and str(run.finished_at or run.updated_at).startswith(today_iso)
    )
    recent_runs = []
    for run in sorted(runs, key=lambda item: str(item.updated_at or item.created_at), reverse=True)[:10]:
        workspace = workspaces.get(run.workspace_id)
        current_stage = run.current_stage_id or (run.stage_results[-1].stage_id if run.stage_results else "")
        recent_runs.append(
            {
                "id": run.id,
                "workspace_id": run.workspace_id,
                "workspace_name": workspace.name if workspace else run.workspace_id,
                "status": run.status,
                "current_stage": current_stage or "not_started",
                "attempt_count": run.attempt_count,
                "max_attempts": run.max_attempts,
                "updated_at": run.updated_at,
            }
        )
    return {
        "cards": [
            {"label": "Queued Runs", "value": sum(1 for run in runs if run.status == "queued")},
            {"label": "Running Workers", "value": sum(1 for worker in workers if worker.status == "running")},
            {
                "label": "Jobs Waiting Review",
                "value": sum(1 for item in review_queue if item["status"] in {"waiting_review", "pending"}),
            },
            {"label": "Completed Today", "value": completed_today},
        ],
        "recent_runs": recent_runs,
    }


def _extract_bearer_token(header_value: str) -> str:
    value = str(header_value or "").strip()
    if not value.lower().startswith("bearer "):
        return ""
    return value[7:].strip()


def _normalize_segments(raw_segments: list[str]) -> list[str]:
    if raw_segments[:1] == ["v1"]:
        return raw_segments[1:]
    return raw_segments


def _parse_int_param(query: dict[str, list[str]], name: str, *, default: int, minimum: int = 0, maximum: int = 1000) -> int:
    raw_value = str((query.get(name) or [str(default)])[0]).strip()
    try:
        value = int(raw_value)
    except Exception as exc:
        raise ValueError(f"{name} must be an integer") from exc
    return max(minimum, min(maximum, value))


def build_handler(application):
    class BackendApiHandler(BaseHTTPRequestHandler):
        def _cors_headers(self) -> dict[str, str]:
            origin = str(self.headers.get("Origin") or "").strip()
            return {
                "Access-Control-Allow-Origin": origin or "*",
                "Access-Control-Allow-Headers": "Authorization, Content-Type",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                "Access-Control-Max-Age": "600",
                "Vary": "Origin",
            }

        def _send_json(self, payload, status: int = 200, *, headers: dict[str, str] | None = None) -> None:
            body = _json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            merged_headers = self._cors_headers()
            merged_headers.update(headers or {})
            for key, value in merged_headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, status: int, code: str, message: str, *, details=None, headers: dict[str, str] | None = None) -> None:
            payload = {"error": {"code": code, "message": message}}
            if details is not None:
                payload["error"]["details"] = details
            self._send_json(payload, status=status, headers=headers)

        def _read_json_body(self):
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0:
                return {}
            raw = self.rfile.read(content_length)
            if not raw:
                return {}
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def _parse_request(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            segments = _normalize_segments([segment for segment in path.split("/") if segment])
            query = parse_qs(parsed.query)
            return path, segments, query

        def _pagination_meta(self, *, limit: int, offset: int, returned: int) -> dict[str, int]:
            return {"limit": int(limit), "offset": int(offset), "returned": int(returned)}

        def _send_file(self, file_path: str, *, download_name: str = "") -> None:
            target = Path(file_path)
            if not target.exists() or not target.is_file():
                raise KeyError(f"Artifact file '{file_path}' not found.")
            body = target.read_bytes()
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{download_name or target.name}"',
            )
            for key, value in self._cors_headers().items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _require_identity(self):
            token_value = _extract_bearer_token(self.headers.get("Authorization", ""))
            if not token_value:
                raise PermissionError("Missing bearer token.")
            return application.authenticate_access_token(token_value)

        def _require_scope(self, required_scope: str):
            user, token = self._require_identity()
            if not application.user_has_scope(token, required_scope):
                raise PermissionError(f"Missing scope: {required_scope}")
            return user, token

        def _require_workspace_access(self, *, workspace_id: str, required_scope: str):
            user, token = self._require_scope(required_scope)
            if not application.user_can_access_workspace(user, workspace_id):
                raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
            return user, token

        def _authorized_workspaces(self, user):
            return [workspace for workspace in application.list_workspaces() if application.user_can_access_workspace(user, workspace.id)]

        def _authorized_runs(self, user, *, limit: int, offset: int, status: str, workspace_id: str):
            runs = application.list_runs(limit=limit, offset=offset, status=status, workspace_id=workspace_id)
            return [run for run in runs if application.user_can_access_workspace(user, run.workspace_id)]

        def _send_unauthorized(self, message: str) -> None:
            self._send_error(
                status=HTTPStatus.UNAUTHORIZED,
                code="unauthorized",
                message=message,
                headers={"WWW-Authenticate": "Bearer"},
            )

        def do_OPTIONS(self):  # noqa: N802
            self.send_response(HTTPStatus.NO_CONTENT)
            for key, value in self._cors_headers().items():
                self.send_header(key, value)
            self.end_headers()

        def do_GET(self):  # noqa: N802
            try:
                _, segments, query = self._parse_request()

                if not segments:
                    self._send_json({"service": "unified-backend-api", "status": "ok"})
                    return
                if segments == ["health"]:
                    self._send_json({"status": "ok"})
                    return
                if segments == ["auth", "me"]:
                    user, token = self._require_identity()
                    self._send_json({"user": user.to_dict(), "token": token.to_public_dict()})
                    return
                if segments == ["dashboard"]:
                    user, _ = self._require_identity()
                    self._send_json(_dashboard_payload(application, user))
                    return
                if segments == ["settings"]:
                    user, _ = self._require_identity()
                    self._send_json(_build_settings_payload(application, user))
                    return
                if segments == ["users"]:
                    self._require_scope(TOKEN_SCOPE_USERS_READ)
                    limit = _parse_int_param(query, "limit", default=50, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    users = application.list_users()
                    paged_users = users[offset : offset + limit]
                    self._send_json(
                        {
                            "users": [user.to_dict() for user in paged_users],
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_users)),
                        }
                    )
                    return
                if segments[:1] == ["users"] and len(segments) == 2:
                    self._require_scope(TOKEN_SCOPE_USERS_READ)
                    self._send_json(application.get_user(segments[1]).to_dict())
                    return
                if segments[:1] == ["users"] and len(segments) == 3 and segments[2] == "tokens":
                    self._require_scope(TOKEN_SCOPE_USERS_READ)
                    limit = _parse_int_param(query, "limit", default=100, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    tokens = [
                        token.to_public_dict()
                        for token in application.list_api_tokens(
                            user_id=segments[1],
                            include_inactive=True,
                            limit=limit,
                            offset=offset,
                        )
                    ]
                    self._send_json(
                        {
                            "user_id": segments[1],
                            "tokens": tokens,
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(tokens)),
                        }
                    )
                    return
                if segments == ["tokens"]:
                    self._require_scope(TOKEN_SCOPE_USERS_READ)
                    user_id = str((query.get("user_id") or [""])[0]).strip()
                    include_inactive = str((query.get("include_inactive") or ["false"])[0]).strip().lower() in {"1", "true", "yes"}
                    limit = _parse_int_param(query, "limit", default=100, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    tokens = [
                        token.to_public_dict()
                        for token in application.list_api_tokens(
                            user_id=user_id,
                            include_inactive=include_inactive,
                            limit=limit,
                            offset=offset,
                        )
                    ]
                    self._send_json(
                        {
                            "tokens": tokens,
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(tokens)),
                        }
                    )
                    return
                if segments == ["secrets"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_SECRETS_READ)
                    workspace_id = str((query.get("workspace_id") or [""])[0])
                    limit = _parse_int_param(query, "limit", default=100, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    secrets = [
                        secret.to_public_dict()
                        for secret in application.list_secrets(workspace_id=workspace_id, limit=limit, offset=offset)
                    ]
                    self._send_json(
                        {
                            "secrets": secrets,
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(secrets)),
                        }
                    )
                    return
                if segments[:1] == ["secrets"] and len(segments) == 2:
                    user, _ = self._require_scope(TOKEN_SCOPE_SECRETS_READ)
                    secret = application.get_secret(segments[1])
                    if secret.workspace_id and not application.user_can_access_workspace(user, secret.workspace_id):
                        raise PermissionError(f"Workspace access denied for '{secret.workspace_id}'.")
                    self._send_json(secret.to_public_dict())
                    return
                if segments == ["workspaces"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_WORKSPACES_READ)
                    limit = _parse_int_param(query, "limit", default=50, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    workspaces = self._authorized_workspaces(user)
                    paged_workspaces = workspaces[offset : offset + limit]
                    self._send_json(
                        {
                            "workspaces": [_workspace_summary(item) for item in paged_workspaces],
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_workspaces)),
                        }
                    )
                    return
                if segments[:1] == ["workspaces"] and len(segments) == 2:
                    self._require_workspace_access(workspace_id=segments[1], required_scope=TOKEN_SCOPE_WORKSPACES_READ)
                    self._send_json(application.get_workspace(segments[1]).to_dict())
                    return
                if segments == ["workflow-templates"]:
                    self._require_scope(TOKEN_SCOPE_TEMPLATES_READ)
                    limit = _parse_int_param(query, "limit", default=50, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    templates = application.list_workflow_templates()
                    paged_templates = templates[offset : offset + limit]
                    self._send_json(
                        {
                            "workflow_templates": [_workflow_template_summary(item) for item in paged_templates],
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_templates)),
                        }
                    )
                    return
                if segments[:1] == ["workflow-templates"] and len(segments) == 2:
                    self._require_scope(TOKEN_SCOPE_TEMPLATES_READ)
                    self._send_json(application.get_workflow_template(segments[1]).to_dict())
                    return
                if segments == ["connectors"]:
                    self._require_scope(TOKEN_SCOPE_TEMPLATES_READ)
                    self._send_json({"connectors": [_component_summary(item) for item in application.list_connectors()]})
                    return
                if segments == ["generations"]:
                    self._require_scope(TOKEN_SCOPE_TEMPLATES_READ)
                    self._send_json({"generations": [_component_summary(item) for item in application.list_generations()]})
                    return
                if segments == ["renderers"]:
                    self._require_scope(TOKEN_SCOPE_TEMPLATES_READ)
                    self._send_json({"renderers": [_component_summary(item) for item in application.list_renderers()]})
                    return
                if segments == ["runs"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_RUNS_READ)
                    limit = _parse_int_param(query, "limit", default=50, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    status = str((query.get("status") or [""])[0])
                    workspace_id = str((query.get("workspace_id") or [""])[0])
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    runs = self._authorized_runs(user, limit=limit, offset=offset, status=status, workspace_id=workspace_id)
                    self._send_json(
                        {
                            "runs": [_run_summary(item) for item in runs],
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(runs)),
                        }
                    )
                    return
                if segments == ["review-queue"]:
                    user, _ = self._require_identity()
                    limit = _parse_int_param(query, "limit", default=100, maximum=1000)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    workspace_id = str((query.get("workspace_id") or [""])[0]).strip()
                    run_id = str((query.get("run_id") or [""])[0]).strip()
                    status = str((query.get("status") or [""])[0]).strip().lower()
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    entries = _collect_review_queue_entries(application, user, workspace_id=workspace_id, run_id=run_id)
                    if status:
                        entries = [item for item in entries if str(item.get("status") or "").lower() == status]
                    paged_entries = entries[offset : offset + limit]
                    self._send_json(
                        {
                            "items": paged_entries,
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_entries)),
                        }
                    )
                    return
                if segments == ["artifacts"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_ARTIFACTS_READ)
                    limit = _parse_int_param(query, "limit", default=100, maximum=1000)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    workspace_id = str((query.get("workspace_id") or [""])[0]).strip()
                    run_id = str((query.get("run_id") or [""])[0]).strip()
                    artifact_type = str((query.get("artifact_type") or [""])[0]).strip().lower()
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    entries = _collect_artifact_entries(application, user, workspace_id=workspace_id, run_id=run_id)
                    if artifact_type:
                        entries = [item for item in entries if str(item.get("artifact_type") or "").lower() == artifact_type]
                    paged_entries = entries[offset : offset + limit]
                    self._send_json(
                        {
                            "artifacts": paged_entries,
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_entries)),
                        }
                    )
                    return
                if segments[:1] == ["runs"] and len(segments) == 2:
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_READ)
                    self._send_json(run.to_dict())
                    return
                if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "jobs":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_READ)
                    job_sets = application.list_job_sets(segments[1])
                    self._send_json({"run_id": segments[1], "job_sets": {key: [job.to_dict() for job in jobs] for key, jobs in job_sets.items()}})
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "jobs":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_READ)
                    jobs = application.get_job_set(segments[1], segments[3])
                    self._send_json({"run_id": segments[1], "set_key": segments[3], "jobs": [job.to_dict() for job in jobs]})
                    return
                if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "artifacts":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_ARTIFACTS_READ)
                    artifacts = application.list_artifacts(segments[1])
                    self._send_json({"run_id": segments[1], "artifacts": [artifact.to_dict() for artifact in artifacts]})
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "artifacts":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_ARTIFACTS_READ)
                    self._send_json(application.get_artifact(segments[1], segments[3]).to_dict())
                    return
                if segments[:1] == ["runs"] and len(segments) == 5 and segments[2] == "artifacts" and segments[4] == "download":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_ARTIFACTS_READ)
                    artifact = application.get_artifact(segments[1], segments[3])
                    self._send_file(artifact.path, download_name=Path(artifact.path).name or artifact.artifact_id)
                    return
                if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "reviews":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_REVIEWS_READ)
                    limit = _parse_int_param(query, "limit", default=100, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    reviews = application.list_reviews(run_id=segments[1], limit=limit, offset=offset)
                    self._send_json(
                        {
                            "run_id": segments[1],
                            "reviews": [review.to_dict() for review in reviews],
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(reviews)),
                        }
                    )
                    return
                if segments == ["workers"]:
                    self._require_scope(TOKEN_SCOPE_WORKER_EXECUTE)
                    limit = _parse_int_param(query, "limit", default=50, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    status = str((query.get("status") or [""])[0]).strip()
                    workers = application.list_workers(limit=limit, offset=offset, status=status)
                    self._send_json(
                        {
                            "workers": [worker.to_dict() for worker in workers],
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(workers)),
                        }
                    )
                    return
                if segments[:1] == ["workers"] and len(segments) == 2:
                    self._require_scope(TOKEN_SCOPE_WORKER_EXECUTE)
                    self._send_json(application.get_worker(segments[1]).to_dict())
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "reviews":
                    review = application.get_review(segments[3])
                    run = application.get_run(review.run_id)
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_REVIEWS_READ)
                    if review.run_id != segments[1]:
                        self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Review not found for run.")
                        return
                    self._send_json(review.to_dict())
                    return

                self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Route not found.")
            except PermissionError as exc:
                if "Missing bearer token" in str(exc) or "Invalid or expired access token" in str(exc):
                    self._send_unauthorized(str(exc))
                else:
                    self._send_error(HTTPStatus.FORBIDDEN, "forbidden", str(exc))
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", str(exc))
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "bad_request", str(exc))
            except Exception as exc:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc))

        def do_POST(self):  # noqa: N802
            try:
                _, segments, _ = self._parse_request()
                payload = self._read_json_body()

                if segments == ["users"]:
                    self._require_scope(TOKEN_SCOPE_USERS_WRITE)
                    self._send_json(application.upsert_user(payload).to_dict(), status=HTTPStatus.CREATED)
                    return
                if segments[:1] == ["users"] and len(segments) == 3 and segments[2] == "tokens":
                    self._require_scope(TOKEN_SCOPE_USERS_WRITE)
                    token, raw_token = application.issue_api_token(
                        user_id=segments[1],
                        name=str(payload.get("name") or "api-token"),
                        scopes=[str(item) for item in payload.get("scopes") or [] if str(item).strip()],
                        expires_at=str(payload.get("expires_at") or ""),
                        metadata=dict(payload.get("metadata") or {}),
                    )
                    self._send_json({"token": token.to_public_dict(), "access_token": raw_token}, status=HTTPStatus.CREATED)
                    return
                if segments == ["secrets"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_SECRETS_WRITE)
                    workspace_id = str(payload.get("workspace_id") or "")
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    self._send_json(application.upsert_secret(payload).to_public_dict(), status=HTTPStatus.CREATED)
                    return
                if segments == ["workspaces"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_WORKSPACES_WRITE)
                    workspace_id = str(payload.get("id") or "")
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    self._send_json(application.upsert_workspace(payload).to_dict(), status=HTTPStatus.CREATED)
                    return
                if segments == ["workflow-templates"]:
                    self._require_scope(TOKEN_SCOPE_TEMPLATES_WRITE)
                    self._send_json(application.upsert_workflow_template(payload).to_dict(), status=HTTPStatus.CREATED)
                    return
                if segments == ["runs"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_RUNS_WRITE)
                    workspace_id = str(payload.get("workspace_id") or "").strip()
                    if not workspace_id:
                        raise ValueError("workspace_id is required")
                    if not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    execution_mode = str(payload.get("execution_mode") or "queued").strip().lower()
                    max_attempts = max(1, int(payload.get("max_attempts") or 1))
                    if execution_mode == "queued":
                        run = application.enqueue_run(
                            workspace_id,
                            run_input_overrides=dict(payload.get("run_input_overrides") or {}),
                            requested_by=f"api:{user.user_id}",
                            max_attempts=max_attempts,
                        )
                    elif execution_mode == "planned":
                        run = application.start_run(
                            workspace_id,
                            run_input_overrides=dict(payload.get("run_input_overrides") or {}),
                            execute=False,
                            requested_by=f"api:{user.user_id}",
                            max_attempts=max_attempts,
                        )
                    elif execution_mode == "sync":
                        run = application.start_run(
                            workspace_id,
                            run_input_overrides=dict(payload.get("run_input_overrides") or {}),
                            execute=True,
                            requested_by=f"api:{user.user_id}",
                            max_attempts=max_attempts,
                        )
                    else:
                        raise ValueError("execution_mode must be one of: queued, planned, sync")
                    self._send_json(run.to_dict(), status=HTTPStatus.CREATED)
                    return
                if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "cancel":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                    self._send_json(application.cancel_run(segments[1]).to_dict(), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "retry":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                    self._send_json(application.retry_run(segments[1]).to_dict(), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "resume":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                    self._send_json(application.resume_run(segments[1]).to_dict(), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "reviews":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_REVIEWS_WRITE)
                    self._send_json(application.upsert_review(run_id=segments[1], payload=payload).to_dict(), status=HTTPStatus.CREATED)
                    return
                if segments == ["workers", "process-next"]:
                    self._require_scope(TOKEN_SCOPE_WORKER_EXECUTE)
                    worker_id = str(payload.get("worker_id") or "api_worker")
                    lease_seconds = max(5, int(payload.get("lease_seconds") or 60))
                    run = application.process_next_queued_run(
                        auto_retry_failed=bool(payload.get("auto_retry_failed", True)),
                        worker_id=worker_id,
                        lease_seconds=lease_seconds,
                    )
                    if run is None:
                        self._send_json({"status": "idle"})
                        return
                    self._send_json({"status": "processed", "run": run.to_dict()}, status=HTTPStatus.OK)
                    return
                if segments == ["workers", "recover-stale"]:
                    self._require_scope(TOKEN_SCOPE_WORKER_EXECUTE)
                    recovered = application.recover_stale_workers()
                    self._send_json({"recovered_workers": [worker.to_dict() for worker in recovered]}, status=HTTPStatus.OK)
                    return

                self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Route not found.")
            except PermissionError as exc:
                if "Missing bearer token" in str(exc) or "Invalid or expired access token" in str(exc):
                    self._send_unauthorized(str(exc))
                else:
                    self._send_error(HTTPStatus.FORBIDDEN, "forbidden", str(exc))
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", str(exc))
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "bad_request", str(exc))
            except Exception as exc:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc))

        def do_PUT(self):  # noqa: N802
            try:
                _, segments, _ = self._parse_request()
                payload = self._read_json_body()

                if segments == ["settings"]:
                    user, _ = self._require_identity()
                    metadata = dict(user.metadata or {})

                    if "profile" in payload:
                        profile_payload = dict(payload.get("profile") or {})
                        metadata["profile"] = {
                            "name": str(profile_payload.get("name") or user.display_name or user.email.split("@")[0]),
                            "role_title": str(profile_payload.get("role_title") or ""),
                            "email": str(profile_payload.get("email") or user.email),
                            "location": str(profile_payload.get("location") or ""),
                            "website": str(profile_payload.get("website") or ""),
                            "avatar_url": str(profile_payload.get("avatar_url") or ""),
                            "summary": str(profile_payload.get("summary") or ""),
                            "competencies": [
                                str(item) for item in profile_payload.get("competencies") or [] if str(item).strip()
                            ],
                            "recent_experience": [
                                {
                                    "title": str(item.get("title") or ""),
                                    "company": str(item.get("company") or ""),
                                    "period": str(item.get("period") or ""),
                                }
                                for item in profile_payload.get("recent_experience") or []
                                if isinstance(item, dict)
                            ],
                        }

                    if "defaults" in payload:
                        defaults_payload = dict(payload.get("defaults") or {})
                        default_workspace_id = str(defaults_payload.get("default_workspace_id") or "")
                        if default_workspace_id and not application.user_can_access_workspace(user, default_workspace_id):
                            raise PermissionError(f"Workspace access denied for '{default_workspace_id}'.")
                        metadata["defaults"] = {
                            "default_workspace_id": default_workspace_id,
                            "default_execution_mode": str(defaults_payload.get("default_execution_mode") or "queued"),
                            "default_profile_id": str(defaults_payload.get("default_profile_id") or ""),
                            "default_prompt_set_id": str(defaults_payload.get("default_prompt_set_id") or ""),
                            "max_jobs_per_run": max(1, int(defaults_payload.get("max_jobs_per_run") or 25)),
                        }

                    if "documents" in payload:
                        documents_payload = dict(payload.get("documents") or {})
                        metadata["documents"] = {
                            "generate_docx": bool(documents_payload.get("generate_docx", True)),
                            "generate_pdf": bool(documents_payload.get("generate_pdf", True)),
                            "export_tracker": bool(documents_payload.get("export_tracker", True)),
                            "export_package": bool(documents_payload.get("export_package", True)),
                            "file_naming": str(documents_payload.get("file_naming") or "workspace_job_title"),
                        }

                    if "review_preferences" in payload:
                        review_payload = dict(payload.get("review_preferences") or {})
                        metadata["review_preferences"] = {
                            "require_review_before_use": bool(review_payload.get("require_review_before_use", True)),
                            "default_decision_state": str(review_payload.get("default_decision_state") or "waiting_review"),
                            "rejection_note_required": bool(review_payload.get("rejection_note_required", True)),
                            "auto_open_next_item": bool(review_payload.get("auto_open_next_item", True)),
                        }

                    if "account" in payload:
                        account_payload = dict(payload.get("account") or {})
                        user.display_name = str(account_payload.get("display_name") or user.display_name)
                        user.email = str(account_payload.get("email") or user.email)

                    user.metadata = metadata
                    user.updated_at = datetime.now(timezone.utc).isoformat()
                    application.repositories.auth_repository.upsert_user(user)
                    refreshed_user = application.get_user(user.user_id)
                    self._send_json(_build_settings_payload(application, refreshed_user), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["users"] and len(segments) == 2:
                    self._require_scope(TOKEN_SCOPE_USERS_WRITE)
                    payload["user_id"] = segments[1]
                    self._send_json(application.upsert_user(payload).to_dict(), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["secrets"] and len(segments) == 2:
                    user, _ = self._require_scope(TOKEN_SCOPE_SECRETS_WRITE)
                    payload["secret_id"] = segments[1]
                    workspace_id = str(payload.get("workspace_id") or "")
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    self._send_json(application.upsert_secret(payload).to_public_dict(), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["workspaces"] and len(segments) == 2:
                    self._require_workspace_access(workspace_id=segments[1], required_scope=TOKEN_SCOPE_WORKSPACES_WRITE)
                    payload["id"] = segments[1]
                    self._send_json(application.upsert_workspace(payload).to_dict(), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["workflow-templates"] and len(segments) == 2:
                    self._require_scope(TOKEN_SCOPE_TEMPLATES_WRITE)
                    payload["id"] = segments[1]
                    self._send_json(application.upsert_workflow_template(payload).to_dict(), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "jobs":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                    jobs = payload.get("jobs")
                    if not isinstance(jobs, list):
                        raise ValueError("jobs must be a list")
                    job_set = application.upsert_job_set(segments[1], segments[3], jobs)
                    self._send_json({"run_id": segments[1], "set_key": segments[3], "jobs": [job.to_dict() for job in job_set]})
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "artifacts":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_ARTIFACTS_WRITE)
                    payload["artifact_id"] = segments[3]
                    self._send_json(application.upsert_artifact(segments[1], payload).to_dict(), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "reviews":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_REVIEWS_WRITE)
                    self._send_json(application.upsert_review(run_id=segments[1], payload=payload, review_id=segments[3]).to_dict(), status=HTTPStatus.OK)
                    return

                self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Route not found.")
            except PermissionError as exc:
                if "Missing bearer token" in str(exc) or "Invalid or expired access token" in str(exc):
                    self._send_unauthorized(str(exc))
                else:
                    self._send_error(HTTPStatus.FORBIDDEN, "forbidden", str(exc))
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", str(exc))
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "bad_request", str(exc))
            except Exception as exc:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc))

        def do_DELETE(self):  # noqa: N802
            try:
                _, segments, _ = self._parse_request()

                if segments[:1] == ["users"] and len(segments) == 2:
                    self._require_scope(TOKEN_SCOPE_USERS_WRITE)
                    application.delete_user(segments[1])
                    self._send_json({"deleted": segments[1]}, status=HTTPStatus.OK)
                    return
                if segments[:1] == ["users"] and len(segments) == 4 and segments[2] == "tokens":
                    self._require_scope(TOKEN_SCOPE_USERS_WRITE)
                    self._send_json(application.revoke_api_token(segments[3]).to_public_dict(), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["secrets"] and len(segments) == 2:
                    self._require_scope(TOKEN_SCOPE_SECRETS_WRITE)
                    application.delete_secret(segments[1])
                    self._send_json({"deleted": segments[1]}, status=HTTPStatus.OK)
                    return
                if segments[:1] == ["workspaces"] and len(segments) == 2:
                    self._require_workspace_access(workspace_id=segments[1], required_scope=TOKEN_SCOPE_WORKSPACES_WRITE)
                    application.delete_workspace(segments[1])
                    self._send_json({"deleted": segments[1]}, status=HTTPStatus.OK)
                    return
                if segments[:1] == ["workflow-templates"] and len(segments) == 2:
                    self._require_scope(TOKEN_SCOPE_TEMPLATES_WRITE)
                    application.delete_workflow_template(segments[1])
                    self._send_json({"deleted": segments[1]}, status=HTTPStatus.OK)
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "jobs":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                    application.delete_job_set(segments[1], segments[3])
                    self._send_json({"deleted": segments[3], "run_id": segments[1]}, status=HTTPStatus.OK)
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "artifacts":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_ARTIFACTS_WRITE)
                    application.delete_artifact(segments[1], segments[3])
                    self._send_json({"deleted": segments[3], "run_id": segments[1]}, status=HTTPStatus.OK)
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "reviews":
                    review = application.get_review(segments[3])
                    run = application.get_run(review.run_id)
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_REVIEWS_WRITE)
                    application.delete_review(segments[3])
                    self._send_json({"deleted": segments[3], "run_id": segments[1]}, status=HTTPStatus.OK)
                    return

                self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Route not found.")
            except PermissionError as exc:
                if "Missing bearer token" in str(exc) or "Invalid or expired access token" in str(exc):
                    self._send_unauthorized(str(exc))
                else:
                    self._send_error(HTTPStatus.FORBIDDEN, "forbidden", str(exc))
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", str(exc))
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "bad_request", str(exc))
            except Exception as exc:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc))

        def log_message(self, format, *args):  # noqa: A003
            return

    return BackendApiHandler


def serve_api(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    data_dir: str = ".backend_data",
    storage_backend: str = "sqlite",
) -> None:
    application = create_backend(data_dir, storage_backend=storage_backend)
    server = ThreadingHTTPServer((host, int(port)), build_handler(application))
    print(f"Unified backend API listening on http://{host}:{port}")
    server.serve_forever()
