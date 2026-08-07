from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.api.routes.registry import ApiRouteContext, RouteRegistry


def register_routes(registry: RouteRegistry) -> None:
    registry.prefix("GET", ("admin", "job-import"), _handle_get, auth_required=True, name="admin.job_import.get")
    registry.prefix("POST", ("admin", "job-import"), _handle_post, auth_required=True, name="admin.job_import.post")


def _handle_get(context: ApiRouteContext) -> bool | None:
    if not context.segments[:2] == ("admin", "job-import"):
        return None
    context.require_admin()
    application = context.application
    segments = list(context.segments)
    query = context.query
    if segments == ["admin", "job-import", "overview"]:
        context.send_json(application.get_admin_job_import_overview())
        return True
    if segments == ["admin", "job-import", "sources"]:
        context.send_json({"sources": application.list_admin_job_import_sources()})
        return True
    if segments == ["admin", "job-import", "imports"]:
        context.send_json({"imports": application.list_admin_job_imports(limit=_int_query(query, "limit", 50, 200), offset=_int_query(query, "offset", 0, 100000))})
        return True
    if len(segments) == 4 and segments[2] == "imports":
        item = application.get_admin_job_import(segments[3])
        if item is None:
            return _error(context, 404, "import_not_found", "Import not found.")
        context.send_json(item)
        return True
    if segments == ["admin", "job-import", "review"]:
        context.send_json(
            application.list_admin_review_jobs(
                import_id=_query_value(query, "import_id"),
                status=_query_value(query, "status") or "needs_review",
                search=_query_value(query, "search"),
                source_id=_query_value(query, "source_id"),
                location=_query_value(query, "location"),
                missing=_query_value(query, "missing"),
                limit=_int_query(query, "limit", 50, 200),
                offset=_int_query(query, "offset", 0, 100000),
            )
        )
        return True
    if segments == ["admin", "job-import", "history"]:
        context.send_json({"events": application.list_admin_job_import_history(import_id=_query_value(query, "import_id"), limit=_int_query(query, "limit", 100, 500))})
        return True
    if len(segments) == 4 and segments[2] == "preview":
        preview = application.get_admin_job_import_preview(segments[3])
        if preview is None:
            return _error(context, 404, "preview_not_found", "Publication preview not found.")
        context.send_json(preview)
        return True
    return None


def _handle_post(context: ApiRouteContext) -> bool | None:
    if not context.segments[:2] == ("admin", "job-import"):
        return None
    admin = context.require_admin()
    actor_user_id = _actor_user_id(admin)
    application = context.application
    segments = list(context.segments)
    body = _body(context)
    try:
        if segments == ["admin", "job-import", "plan"]:
            context.send_json(
                application.plan_admin_job_import(
                    source_ids=[str(item) for item in body.get("source_ids") or []],
                    scope=dict(body.get("scope") or {}),
                )
            )
            return True
        if segments == ["admin", "job-import", "imports"]:
            idempotency_key = _text(body.get("idempotency_key"))
            if not idempotency_key:
                return _error(context, 400, "idempotency_key_required", "Start import requires an idempotency key.")
            context.send_json(
                application.start_admin_job_import(
                    requested_by=actor_user_id,
                    idempotency_key=idempotency_key,
                    source_ids=[str(item) for item in body.get("source_ids") or []],
                    scope=dict(body.get("scope") or {}),
                ),
                status=202,
            )
            return True
        if segments == ["admin", "job-import", "review", "decision"]:
            action = _text(body.get("decision") or body.get("action")).casefold()
            if action in {"undo", "undone"}:
                application.undo_admin_review_decision(
                    import_id=_text(body.get("import_id")),
                    canonical_job_id=_text(body.get("canonical_job_id")),
                    actor_user_id=actor_user_id,
                )
                context.send_json({"status": "undone"})
                return True
            context.send_json(
                application.decide_admin_review_job(
                    import_id=_text(body.get("import_id")),
                    canonical_job_id=_text(body.get("canonical_job_id")),
                    decision=action,
                    actor_user_id=actor_user_id,
                    reason_code=_text(body.get("reason_code")),
                )
            )
            return True
        if segments == ["admin", "job-import", "preview"]:
            context.send_json(application.preview_admin_job_import(_text(body.get("import_id")), actor_user_id=actor_user_id), status=202)
            return True
        if segments == ["admin", "job-import", "publish"]:
            publication_id = _text(body.get("publication_id"))
            context.send_json({"publication_id": application.publish_admin_job_import(publication_id, actor_user_id=actor_user_id), "status": "published"}, status=202)
            return True
        if segments == ["admin", "job-import", "undo"]:
            context.send_json(application.undo_admin_job_publication(actor_user_id=actor_user_id), status=202)
            return True
        if segments == ["admin", "job-import", "pause"]:
            paused = bool(body.get("paused", True))
            config_store = getattr(application.repositories, "config_store", None)
            if config_store is None:
                raise ValueError("Import pause control is unavailable.")
            config_store.set_value("acquisition.admin_imports.kill_switch", paused)
            config_store.set_value("acquisition.admin_imports.enabled", not paused)
            context.send_json({"paused": paused, "status": "Paused" if paused else "Ready"})
            return True
    except PermissionError as exc:
        return _error(context, 423, "imports_paused", str(exc))
    except KeyError as exc:
        return _error(context, 404, "job_import_not_found", str(exc))
    except ValueError as exc:
        return _error(context, 400, "invalid_job_import_request", str(exc))
    return None


def _actor_user_id(value: Any) -> str:
    user = value[0] if isinstance(value, tuple) else value
    if isinstance(user, Mapping):
        return _text(user.get("user_id") or user.get("id"))
    return _text(getattr(user, "user_id", "") or getattr(user, "id", ""))


def _body(context: ApiRouteContext) -> dict[str, Any]:
    value = context.read_json_body()
    return dict(value) if isinstance(value, Mapping) else {}


def _query_value(query: Mapping[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return _text(values[0]) if values else ""


def _int_query(query: Mapping[str, list[str]], key: str, default: int, maximum: int) -> int:
    try:
        value = int(_query_value(query, key) or default)
    except (TypeError, ValueError):
        value = default
    return max(0, min(maximum, value))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _error(context: ApiRouteContext, status: int, code: str, message: str) -> bool:
    context.send_error(status, code, message)
    return True


__all__ = ["register_routes"]
