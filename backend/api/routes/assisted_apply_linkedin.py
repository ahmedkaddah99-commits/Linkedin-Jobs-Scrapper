from __future__ import annotations

from http import HTTPStatus

from backend.api.routes.assisted_apply import _authenticate_extension_session, _read_strict_object
from backend.api.routes.registry import ApiRouteContext, RouteRegistry


def register_routes(registry: RouteRegistry) -> None:
    registry.exact(
        "POST",
        ("assisted-apply", "extension", "linkedin-connections"),
        _sync_linkedin_connections,
        auth_required=False,
        name="assisted_apply.extension.linkedin_connections.sync",
    )


def _sync_linkedin_connections(context: ApiRouteContext) -> None:
    user, _ = _authenticate_extension_session(context)
    payload = _read_strict_object(
        context,
        allowed_keys={"csv_text"},
        label="LinkedIn connections sync",
    )
    csv_text = str(payload.get("csv_text") or "")
    plan_id = context.application.get_user_plan_id(user.user_id)
    result = context.application.sync_linkedin_connections(
        user_id=user.user_id,
        csv_text=csv_text,
        plan_id=plan_id,
    )
    # The web app refreshes its own authenticated referral resource after the
    # sync. Do not send the full contact export through the extension bridge.
    result.pop("contacts", None)
    context.send_json(result, status=HTTPStatus.OK)
