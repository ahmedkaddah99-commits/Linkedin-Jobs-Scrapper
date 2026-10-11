"""API routes for CV bullet suggestions (CP-036R).

REST endpoints for the CV bullet suggestion lifecycle.
"""

from __future__ import annotations

from http import HTTPStatus

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.capabilities.cv_bullet_suggestions import (
    accept_suggestion,
    edit_suggestion,
    generate_suggestions,
    get_accepted_bullets,
    get_suggestion,
    get_suggestions,
    reject_suggestion,
    replace_suggestion,
)
from backend.domain.cv_bullet_suggestion import (
    BULLET_SUGGESTION_ACTION_ACCEPT,
    BULLET_SUGGESTION_ACTION_EDIT,
    BULLET_SUGGESTION_ACTION_REJECT,
    BULLET_SUGGESTION_ACTION_REPLACE,
    BULLET_SUGGESTION_ACTIONS,
)


def register_routes(registry: RouteRegistry) -> None:
    registry.prefix(
        "POST",
        ("career-profiles", "{profile_id}", "cv-bullet-suggestions"),
        _handle_generate,
        auth_required=True,
        name="cv_bullet_suggestions.generate",
    )
    registry.prefix(
        "GET",
        ("career-profiles", "{profile_id}", "cv-bullet-suggestions"),
        _handle_list,
        auth_required=True,
        name="cv_bullet_suggestions.list",
    )
    registry.prefix(
        "GET",
        ("career-profiles", "{profile_id}", "cv-bullet-suggestions", "{suggestion_id}"),
        _handle_get,
        auth_required=True,
        name="cv_bullet_suggestions.get",
    )
    registry.prefix(
        "PUT",
        ("career-profiles", "{profile_id}", "cv-bullet-suggestions",
         "{suggestion_id}", "actions"),
        _handle_action,
        auth_required=True,
        name="cv_bullet_suggestions.action",
    )
    registry.prefix(
        "GET",
        ("career-profiles", "{profile_id}", "cv-bullet-suggestions-accepted"),
        _handle_accepted,
        auth_required=True,
        name="cv_bullet_suggestions.accepted",
    )


def _extract_params(context: ApiRouteContext) -> tuple[str, str]:
    segments = list(context.segments)
    profile_id = segments[1] if len(segments) > 1 else ""
    suggestion_id = segments[3] if len(segments) > 3 else ""
    return profile_id, suggestion_id


def _handle_generate(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if not (len(segments) >= 3 and segments[0] == "career-profiles"
            and segments[2] == "cv-bullet-suggestions"):
        return False
    profile_id = segments[1]
    user, _ = context.require_identity()
    payload = context.read_json_body()

    evidence_ids = list(payload.get("evidence_ids") or [])
    if not evidence_ids:
        context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                           "validation_error",
                           "At least one evidence_id is required.")
        return True

    baseline_cv_text = str(payload.get("baseline_cv_text") or "")
    if not baseline_cv_text.strip():
        context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                           "validation_error",
                           "baseline_cv_text is required.")
        return True

    try:
        suggestions = generate_suggestions(
            user,
            profile_id=profile_id,
            baseline_cv_text=baseline_cv_text,
            baseline_cv_version=str(payload.get("baseline_cv_version") or ""),
            baseline_cv_asset_id=str(payload.get("baseline_cv_asset_id") or ""),
            target_job_id=str(payload.get("target_job_id") or ""),
            target_job_title=str(payload.get("target_job_title") or ""),
            target_job_description=str(payload.get("target_job_description") or ""),
            evidence_ids=evidence_ids,
        )
        context.send_json(
            {"suggestions": [s.to_dict() for s in suggestions]},
            status=HTTPStatus.CREATED,
        )
    except ValueError as exc:
        context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                           "generation_error", str(exc))
    return True


def _handle_list(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if not (len(segments) >= 3 and segments[0] == "career-profiles"
            and segments[2] == "cv-bullet-suggestions") or (
                len(segments) == 4 and segments[3]):
        return False
    profile_id, _ = _extract_params(context)
    context.require_identity()
    target_job_id = str(context.read_query_param("target_job_id") or "")
    suggestions = get_suggestions(profile_id, target_job_id=target_job_id)
    context.send_json(
        {"suggestions": [s.to_dict() for s in suggestions]},
        status=HTTPStatus.OK,
    )
    return True


def _handle_get(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if not (len(segments) >= 4 and segments[0] == "career-profiles"
            and segments[2] == "cv-bullet-suggestions"):
        return False
    _, suggestion_id = _extract_params(context)
    context.require_identity()
    suggestion = get_suggestion(suggestion_id)
    if suggestion is None:
        context.send_error(HTTPStatus.NOT_FOUND, "suggestion_not_found",
                           f"CV bullet suggestion '{suggestion_id}' not found.")
        return True
    context.send_json(suggestion.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_action(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if not (len(segments) >= 6 and segments[0] == "career-profiles"
            and segments[2] == "cv-bullet-suggestions"
            and segments[4] == "actions"):
        return False
    _, suggestion_id = _extract_params(context)
    context.require_identity()
    payload = context.read_json_body()

    action = str(payload.get("action") or "").strip()
    if action not in BULLET_SUGGESTION_ACTIONS:
        context.send_error(
            HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error",
            f"action must be one of: {', '.join(sorted(BULLET_SUGGESTION_ACTIONS))}.")
        return True

    try:
        if action == BULLET_SUGGESTION_ACTION_ACCEPT:
            suggestion = accept_suggestion(suggestion_id)
        elif action == BULLET_SUGGESTION_ACTION_EDIT:
            suggestion = edit_suggestion(suggestion_id, payload)
        elif action == BULLET_SUGGESTION_ACTION_REJECT:
            suggestion = reject_suggestion(suggestion_id)
        elif action == BULLET_SUGGESTION_ACTION_REPLACE:
            suggestion = replace_suggestion(suggestion_id, payload)
        else:
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                               "validation_error", f"Unknown action: {action}")
            return True
        context.send_json(suggestion.to_dict(), status=HTTPStatus.OK)
    except ValueError as exc:
        context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                           "action_error", str(exc))
    return True


def _handle_accepted(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if not (len(segments) >= 3 and segments[0] == "career-profiles"
            and segments[2] == "cv-bullet-suggestions-accepted"):
        return False
    profile_id = segments[1]
    context.require_identity()
    target_job_id = str(context.read_query_param("target_job_id") or "")
    bullets = get_accepted_bullets(profile_id, target_job_id=target_job_id)
    context.send_json(
        {"accepted_bullets": [b.to_dict() for b in bullets]},
        status=HTTPStatus.OK,
    )
    return True
