from __future__ import annotations

from http import HTTPStatus
from collections.abc import Mapping

from backend.api.routes.assisted_apply import _authenticate_extension_session, _read_strict_object
from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.domain.assisted_apply_preparation import PreparationFeatureDisabledError


_CREATE_KEYS = {"package_id"}
_ACTION_KEYS = {"action"}
_REPORT_KEYS = {"preparation_id", "package_id", "message_id", "type", "result", "total", "completed", "error_category"}
_RESULT_KEYS = {"status", "stage", "completed", "total", "code"}
_EXTENSION_ACTION_KEYS = {"preparation_id", "package_id", "action"}


def register_routes(registry: RouteRegistry) -> None:
    registry.exact("POST", ("assisted-apply", "preparations"), _create, auth_required=True, name="assisted_apply.preparations.create")
    registry.prefix("GET", ("assisted-apply", "preparations"), _read, auth_required=True, name="assisted_apply.preparations.read")
    registry.prefix("POST", ("assisted-apply", "preparations"), _action, auth_required=True, name="assisted_apply.preparations.action")
    registry.exact("POST", ("assisted-apply", "extension", "preparations", "report"), _report, auth_required=False, name="assisted_apply.extension.preparations.report")
    registry.exact("POST", ("assisted-apply", "extension", "preparations", "action"), _extension_action, auth_required=False, name="assisted_apply.extension.preparations.action")


def _disabled(context: ApiRouteContext) -> bool:
    service = getattr(context.application, "_assisted_apply_preparation_service", None)
    if service is not None and not service.enabled:
        context.send_error(HTTPStatus.NOT_IMPLEMENTED, "assisted_apply_preparation_disabled", "Assisted Apply preparation status is disabled.")
        return True
    return False


def _create(context: ApiRouteContext) -> None:
    if _disabled(context):
        return
    user, _ = context.require_clerk_identity()
    payload = _read_strict_object(context, allowed_keys=_CREATE_KEYS, label="preparation")
    preparation = context.application.create_assisted_apply_preparation(
        user_id=user.user_id, package_id=str(payload.get("package_id") or "").strip(),
    )
    context.send_json(preparation.to_dict(), status=HTTPStatus.CREATED)


def _read(context: ApiRouteContext) -> None:
    if _disabled(context):
        return
    user, _ = context.require_clerk_identity()
    if len(context.segments) == 2:
        context.send_json({"preparations": [item.to_dict() for item in context.application.list_assisted_apply_preparations(user_id=user.user_id)]})
        return
    if len(context.segments) != 3:
        raise ValueError("Invalid preparation path.")
    preparation = context.application.get_assisted_apply_preparation(user_id=user.user_id, preparation_id=context.segments[2])
    context.send_json(preparation.to_dict())


def _action(context: ApiRouteContext) -> None:
    if _disabled(context):
        return
    if len(context.segments) != 4:
        raise ValueError("Preparation action path must include a preparation ID and action segment.")
    user, _ = context.require_clerk_identity()
    payload = _read_strict_object(context, allowed_keys=_ACTION_KEYS, label="preparation action")
    preparation = context.application.act_on_assisted_apply_preparation(
        user_id=user.user_id, preparation_id=context.segments[2], action=str(payload.get("action") or "").strip(),
    )
    context.send_json(preparation.to_dict())


def _report(context: ApiRouteContext) -> None:
    if _disabled(context):
        return
    payload = _read_strict_object(context, allowed_keys=_REPORT_KEYS, label="preparation report")
    result = payload.get("result") or {}
    if not isinstance(result, Mapping):
        raise ValueError("result must be an object when supplied.")
    unknown_result = sorted(str(key) for key in result if key not in _RESULT_KEYS)
    if unknown_result:
        raise ValueError("Unsupported preparation result keys: " + ", ".join(unknown_result))
    report_type = str(payload.get("type") or "").strip()
    total = payload.get("total", result.get("total", 0))
    completed = payload.get("completed", result.get("completed", 0))
    raw_code = str(payload.get("error_category") or result.get("code") or "").strip()
    known_categories = {"permission_required", "permission_denied", "unsupported_ats", "field_unavailable", "document_unavailable", "validation_failed", "navigation_blocked", "extension_unavailable", "expired", "unknown"}
    error_category = raw_code if raw_code in known_categories else ("unknown" if raw_code else "")
    preparation = context.application.report_assisted_apply_preparation(
        preparation_id=str(payload.get("preparation_id") or "").strip(),
        package_id=str(payload.get("package_id") or "").strip(),
        message_id=str(payload.get("message_id") or "").strip(),
        report_type=report_type,
        raw_session=context.bearer_token(),
        extension_origin=context.request_client_origin(),
        total_count=total,
        completed_count=completed,
        error_category=error_category,
    )
    context.send_json(preparation.to_dict())


def _extension_action(context: ApiRouteContext) -> None:
    if _disabled(context):
        return
    payload = _read_strict_object(context, allowed_keys=_EXTENSION_ACTION_KEYS, label="preparation action")
    preparation = context.application.act_on_assisted_apply_preparation_from_extension(
        preparation_id=str(payload.get("preparation_id") or "").strip(),
        package_id=str(payload.get("package_id") or "").strip(),
        action=str(payload.get("action") or "").strip(),
        raw_session=context.bearer_token(),
        extension_origin=context.request_client_origin(),
    )
    context.send_json(preparation.to_dict())
