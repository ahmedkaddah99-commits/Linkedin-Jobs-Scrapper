from __future__ import annotations

from http import HTTPStatus

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.career_memory import (
    confirm_fact,
    extract_facts,
    generate_outputs,
    get_career_memory_state,
    next_question,
    regenerate_output,
)


def register_routes(registry: RouteRegistry) -> None:
    registry.prefix("GET", ("career-memory",), _handle_get, auth_required=True, name="career_memory.get")
    registry.prefix("POST", ("career-memory",), _handle_post, auth_required=True, name="career_memory.post")


def _handle_get(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if segments == ["career-memory"]:
        user, _ = context.require_identity()
        context.send_json(get_career_memory_state(user), status=HTTPStatus.OK)
        return True
    return False


def _handle_post(context: ApiRouteContext) -> bool | None:
    application = context.application
    segments = list(context.segments)
    payload = context.read_json_body()
    user, _ = context.require_identity()

    if segments == ["career-memory", "facts", "extract"]:
        context.send_json(
            extract_facts(application, user, payload.get("source_asset_ids") or []),
            status=HTTPStatus.OK,
        )
        return True
    if segments == ["career-memory", "questions", "next"]:
        context.send_json(next_question(user), status=HTTPStatus.OK)
        return True
    if len(segments) == 4 and segments[:2] == ["career-memory", "facts"] and segments[3] == "confirm":
        context.send_json(
            confirm_fact(application, user, segments[2], payload),
            status=HTTPStatus.OK,
        )
        return True
    if segments == ["career-memory", "outputs", "generate"]:
        context.send_json(generate_outputs(application, user, payload), status=HTTPStatus.CREATED)
        return True
    if len(segments) == 4 and segments[:2] == ["career-memory", "outputs"] and segments[3] == "regenerate":
        context.send_json(
            regenerate_output(application, user, segments[2], payload),
            status=HTTPStatus.OK,
        )
        return True
    return False
