"""API for the user's editable Master CV.

This route family is deliberately separate from career evidence, career memory,
and work-experience APIs. A Master CV is a durable document owned by the user.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Mapping

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.master_cv import (
    add_bullet,
    add_entry,
    delete_bullet,
    delete_entry,
    export_document,
    get_bullet_guidance,
    get_document,
    improve_bullet,
    persist_document,
    select_relevant_bullets,
    update_bullet,
    update_document,
    update_entry,
)


def register_routes(registry: RouteRegistry) -> None:
    registry.exact("GET", ("master-cv",), _handle_get, auth_required=True, name="master_cv.get")
    registry.exact("PUT", ("master-cv",), _handle_update, auth_required=True, name="master_cv.update")
    registry.exact("GET", ("master-cv", "export"), _handle_export, auth_required=True, name="master_cv.export")
    registry.exact("POST", ("master-cv", "tailor"), _handle_tailor, auth_required=True, name="master_cv.tailor")
    registry.exact("POST", ("master-cv", "entries"), _handle_create_entry, auth_required=True, name="master_cv.entries.create")
    registry.prefix("PATCH", ("master-cv", "entries"), _handle_update_entry, auth_required=True, name="master_cv.entries.update")
    registry.prefix("DELETE", ("master-cv", "entries"), _handle_delete_entry, auth_required=True, name="master_cv.entries.delete")
    registry.prefix("POST", ("master-cv", "entries"), _handle_create_bullet, auth_required=True, name="master_cv.bullets.create")
    registry.prefix("PATCH", ("master-cv", "bullets"), _handle_update_bullet, auth_required=True, name="master_cv.bullets.update")
    registry.prefix("DELETE", ("master-cv", "bullets"), _handle_delete_bullet, auth_required=True, name="master_cv.bullets.delete")
    registry.prefix("GET", ("master-cv", "bullets"), _handle_guidance, auth_required=True, name="master_cv.bullets.guidance")
    registry.prefix("POST", ("master-cv", "bullets"), _handle_improve, auth_required=True, name="master_cv.bullets.improve")


def _body(context: ApiRouteContext) -> Mapping[str, Any]:
    payload = context.read_json_body()
    return payload if isinstance(payload, Mapping) else {}


def _load(context: ApiRouteContext) -> tuple[Any, dict[str, Any]]:
    user, _ = context.require_identity()
    document, created = get_document(user)
    if created:
        document = persist_document(context.application, user, document)
    return user, document


def _send_mutation_error(context: ApiRouteContext, error: Exception, *, missing_code: str) -> bool:
    if isinstance(error, KeyError):
        context.send_error(HTTPStatus.NOT_FOUND, missing_code, str(error))
        return True
    context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error", str(error))
    return True


def _handle_get(context: ApiRouteContext) -> bool | None:
    _, document = _load(context)
    context.send_json(document, status=HTTPStatus.OK)
    return True


def _handle_update(context: ApiRouteContext) -> bool | None:
    user, document = _load(context)
    try:
        updated = update_document(document, _body(context), user)
        context.send_json(persist_document(context.application, user, updated), status=HTTPStatus.OK)
    except Exception as error:
        return _send_mutation_error(context, error, missing_code="master_cv_not_found")
    return True


def _handle_export(context: ApiRouteContext) -> bool | None:
    _, document = _load(context)
    format_name = str((context.query.get("format") or ["json"])[0] or "json")
    try:
        context.send_json(export_document(document, format_name), status=HTTPStatus.OK)
    except ValueError as error:
        context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error", str(error))
    return True


def _handle_tailor(context: ApiRouteContext) -> bool | None:
    _, document = _load(context)
    payload = _body(context)
    try:
        result = select_relevant_bullets(document, str(payload.get("target_text") or ""), limit=int(payload.get("limit") or 5))
        context.send_json(result, status=HTTPStatus.OK)
    except ValueError as error:
        context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error", str(error))
    return True


def _handle_create_entry(context: ApiRouteContext) -> bool | None:
    user, document = _load(context)
    try:
        updated = add_entry(document, _body(context))
        context.send_json(persist_document(context.application, user, updated), status=HTTPStatus.CREATED)
    except Exception as error:
        return _send_mutation_error(context, error, missing_code="master_cv_entry_not_found")
    return True


def _handle_update_entry(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) != 3 or segments[:2] != ["master-cv", "entries"]:
        return False
    user, document = _load(context)
    try:
        updated = update_entry(document, segments[2], _body(context))
        context.send_json(persist_document(context.application, user, updated), status=HTTPStatus.OK)
    except Exception as error:
        return _send_mutation_error(context, error, missing_code="master_cv_entry_not_found")
    return True


def _handle_delete_entry(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) != 3 or segments[:2] != ["master-cv", "entries"]:
        return False
    user, document = _load(context)
    try:
        updated = delete_entry(document, segments[2])
        context.send_json(persist_document(context.application, user, updated), status=HTTPStatus.OK)
    except Exception as error:
        return _send_mutation_error(context, error, missing_code="master_cv_entry_not_found")
    return True


def _handle_create_bullet(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) != 4 or segments[:2] != ["master-cv", "entries"] or segments[3] != "bullets":
        return False
    user, document = _load(context)
    try:
        updated = add_bullet(document, segments[2], _body(context))
        context.send_json(persist_document(context.application, user, updated), status=HTTPStatus.CREATED)
    except Exception as error:
        return _send_mutation_error(context, error, missing_code="master_cv_entry_not_found")
    return True


def _handle_update_bullet(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) != 3 or segments[:2] != ["master-cv", "bullets"]:
        return False
    user, document = _load(context)
    try:
        updated = update_bullet(document, segments[2], _body(context))
        context.send_json(persist_document(context.application, user, updated), status=HTTPStatus.OK)
    except Exception as error:
        return _send_mutation_error(context, error, missing_code="master_cv_bullet_not_found")
    return True


def _handle_delete_bullet(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) != 3 or segments[:2] != ["master-cv", "bullets"]:
        return False
    user, document = _load(context)
    try:
        updated = delete_bullet(document, segments[2])
        context.send_json(persist_document(context.application, user, updated), status=HTTPStatus.OK)
    except Exception as error:
        return _send_mutation_error(context, error, missing_code="master_cv_bullet_not_found")
    return True


def _handle_guidance(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) != 5 or segments[:2] != ["master-cv", "bullets"] or segments[4] != "guidance":
        return False
    _, document = _load(context)
    try:
        context.send_json(get_bullet_guidance(document, segments[2]), status=HTTPStatus.OK)
    except KeyError as error:
        context.send_error(HTTPStatus.NOT_FOUND, "master_cv_bullet_not_found", str(error))
    return True


def _handle_improve(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) != 4 or segments[:2] != ["master-cv", "bullets"] or segments[3] != "improve":
        return False
    _, document = _load(context)
    try:
        context.send_json(improve_bullet(document, segments[2]), status=HTTPStatus.OK)
    except KeyError as error:
        context.send_error(HTTPStatus.NOT_FOUND, "master_cv_bullet_not_found", str(error))
    return True
