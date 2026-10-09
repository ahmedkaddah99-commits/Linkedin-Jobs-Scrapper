from __future__ import annotations

from http import HTTPStatus
from typing import Any, Mapping

from backend.api.routes.registry import ApiRouteContext, RouteRegistry


_CREATE_REQUEST_KEYS = {
    "code_challenge",
    "extension_version",
    "installation_id",
    "state",
}
_EXCHANGE_KEYS = {
    "authorization_code",
    "code_verifier",
    "request_id",
}
_PREFERENCE_KEYS = {
    "permit_sensitive_autofill",
    "permit_demographic_autofill",
    "require_legal_answer_confirmation",
    "revision",
    "schema_version",
    "updated_at",
}


def register_routes(registry: RouteRegistry) -> None:
    registry.exact(
        "POST",
        ("assisted-apply", "extension", "connection-requests"),
        _create_extension_connection_request,
        auth_required=False,
        name="assisted_apply.extension.connection_requests.create",
    )
    registry.exact(
        "POST",
        ("assisted-apply", "extension", "token"),
        _exchange_extension_authorization,
        auth_required=False,
        name="assisted_apply.extension.token.exchange",
    )
    registry.exact(
        "POST",
        ("assisted-apply", "extension", "session", "verify"),
        _verify_extension_session,
        auth_required=False,
        name="assisted_apply.extension.session.verify",
    )
    registry.exact(
        "DELETE",
        ("assisted-apply", "extension", "session"),
        _delete_extension_session,
        auth_required=False,
        name="assisted_apply.extension.session.delete",
    )
    registry.exact(
        "PUT",
        ("assisted-apply", "extension", "preferences"),
        _update_extension_preferences,
        auth_required=False,
        name="assisted_apply.extension.preferences.update",
    )

    registry.exact(
        "GET",
        ("assisted-apply", "connection"),
        _get_web_connection,
        auth_required=True,
        name="assisted_apply.web.connection.get",
    )
    registry.prefix(
        "POST",
        ("assisted-apply", "connection-requests"),
        _handle_web_connection_action,
        auth_required=True,
        name="assisted_apply.web.connection_requests.action",
    )
    registry.exact(
        "PUT",
        ("assisted-apply", "preferences"),
        _update_web_preferences,
        auth_required=True,
        name="assisted_apply.web.preferences.update",
    )
    registry.prefix(
        "DELETE",
        ("assisted-apply", "sessions"),
        _delete_owned_web_session,
        auth_required=True,
        name="assisted_apply.web.sessions.delete",
    )


def _read_strict_object(
    context: ApiRouteContext,
    *,
    allowed_keys: set[str],
    label: str,
) -> dict[str, Any]:
    payload = context.read_json_body()
    unknown_keys = sorted(str(key) for key in payload if key not in allowed_keys)
    if unknown_keys:
        raise ValueError(f"Unsupported {label} keys: " + ", ".join(unknown_keys))
    return payload


def _read_preferences(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("preferences must be a JSON object.")
    preferences = dict(value)
    unknown_keys = sorted(str(key) for key in preferences if key not in _PREFERENCE_KEYS)
    if unknown_keys:
        raise ValueError(
            "Unsupported Assisted Apply preference keys: " + ", ".join(unknown_keys)
        )
    return preferences


def _single_query_value(context: ApiRouteContext, name: str) -> str:
    values = list(context.query.get(name) or [])
    if len(values) > 1:
        raise ValueError(f"{name} must be supplied exactly once.")
    return str(values[0] if values else "").strip()


def _session_payload(user: object, connection: object) -> dict[str, str]:
    return {
        "session_id": str(getattr(connection, "request_id", "") or ""),
        "user_id": str(getattr(user, "user_id", "") or ""),
        "expires_at": str(getattr(connection, "session_expires_at", "") or ""),
        "created_at": str(getattr(connection, "activated_at", "") or ""),
        "display_name": str(getattr(user, "display_name", "") or ""),
        "email": str(getattr(user, "email", "") or ""),
    }


def _authenticate_extension_session(context: ApiRouteContext):
    return context.application.authenticate_assisted_apply_session(
        raw_session=context.bearer_token(),
        extension_origin=context.request_client_origin(),
    )


def _create_extension_connection_request(context: ApiRouteContext) -> None:
    payload = _read_strict_object(
        context,
        allowed_keys=_CREATE_REQUEST_KEYS,
        label="connection request",
    )
    record = context.application.create_assisted_apply_connection_request(
        extension_origin=context.request_client_origin(),
        state=payload.get("state"),
        challenge=payload.get("code_challenge"),
        installation_id=payload.get("installation_id"),
        version=payload.get("extension_version"),
    )
    context.send_json(
        {
            "request_id": record.request_id,
            "expires_at": record.request_expires_at,
        },
        status=HTTPStatus.CREATED,
    )


def _exchange_extension_authorization(context: ApiRouteContext) -> None:
    payload = _read_strict_object(
        context,
        allowed_keys=_EXCHANGE_KEYS,
        label="authorization exchange",
    )
    connection, raw_session = context.application.exchange_assisted_apply_authorization(
        extension_origin=context.request_client_origin(),
        request_id=payload.get("request_id"),
        code=payload.get("authorization_code"),
        verifier=payload.get("code_verifier"),
    )
    user, authenticated_connection = context.application.authenticate_assisted_apply_session(
        raw_session=raw_session,
        extension_origin=context.request_client_origin(),
    )
    if authenticated_connection.request_id != connection.request_id:
        raise PermissionError("Assisted Apply session exchange did not bind to its request.")
    context.send_json(
        {
            "session_token": raw_session,
            "session": _session_payload(user, authenticated_connection),
            "preferences": context.application.get_assisted_apply_preferences(
                user.user_id
            ).to_dict(),
        },
        status=HTTPStatus.OK,
    )


def _verify_extension_session(context: ApiRouteContext) -> None:
    _read_strict_object(
        context,
        allowed_keys=set(),
        label="session verification",
    )
    user, connection = _authenticate_extension_session(context)
    context.send_json(
        {
            "session": _session_payload(user, connection),
            "preferences": context.application.get_assisted_apply_preferences(
                user.user_id
            ).to_dict(),
        },
        status=HTTPStatus.OK,
    )


def _delete_extension_session(context: ApiRouteContext) -> None:
    context.application.revoke_current_assisted_apply_session(
        raw_session=context.bearer_token(),
        extension_origin=context.request_client_origin(),
    )
    context.send_no_content()


def _update_extension_preferences(context: ApiRouteContext) -> None:
    user, _ = _authenticate_extension_session(context)
    payload = _read_strict_object(
        context,
        allowed_keys=_PREFERENCE_KEYS,
        label="Assisted Apply preference",
    )
    preferences = context.application.update_assisted_apply_preferences(
        user_id=user.user_id,
        preferences=payload,
    )
    context.send_json({"preferences": preferences.to_dict()}, status=HTTPStatus.OK)


def _get_web_connection(context: ApiRouteContext) -> None:
    user, _ = context.require_clerk_identity()
    request_id = _single_query_value(context, "request_id")
    if not request_id:
        context.send_json(
            {
                "request_state": "disconnected",
                "preferences": context.application.get_assisted_apply_preferences(
                    user.user_id
                ).to_dict(),
            },
            status=HTTPStatus.OK,
        )
        return
    context.send_json(
        context.application.get_assisted_apply_connection_dashboard(
            user_id=user.user_id,
            request_id=request_id,
        ),
        status=HTTPStatus.OK,
    )


def _handle_web_connection_action(context: ApiRouteContext) -> bool:
    segments = list(context.segments)
    if len(segments) != 4 or segments[:2] != ["assisted-apply", "connection-requests"]:
        return False
    request_id, action = segments[2], segments[3]
    if action not in {"approve", "reject"}:
        return False
    user, _ = context.require_clerk_identity()
    if action == "approve":
        payload = _read_strict_object(
            context,
            allowed_keys={"preferences"},
            label="connection approval",
        )
        completion_url = context.application.authorize_assisted_apply_connection(
            user_id=user.user_id,
            request_id=request_id,
            preferences=_read_preferences(payload.get("preferences")),
        )
        context.send_json({"completion_url": completion_url}, status=HTTPStatus.OK)
        return True

    _read_strict_object(context, allowed_keys=set(), label="connection rejection")
    record = context.application.reject_assisted_apply_connection(
        user_id=user.user_id,
        request_id=request_id,
    )
    context.send_json(
        {"request_id": record.request_id, "status": record.status},
        status=HTTPStatus.OK,
    )
    return True


def _update_web_preferences(context: ApiRouteContext) -> None:
    user, _ = context.require_clerk_identity()
    payload = _read_strict_object(
        context,
        allowed_keys=_PREFERENCE_KEYS,
        label="Assisted Apply preference",
    )
    preferences = context.application.update_assisted_apply_preferences(
        user_id=user.user_id,
        preferences=payload,
    )
    context.send_json({"preferences": preferences.to_dict()}, status=HTTPStatus.OK)


def _delete_owned_web_session(context: ApiRouteContext) -> bool:
    segments = list(context.segments)
    if len(segments) != 3 or segments[:2] != ["assisted-apply", "sessions"]:
        return False
    user, _ = context.require_clerk_identity()
    context.application.revoke_owned_assisted_apply_connection(
        user_id=user.user_id,
        request_id=segments[2],
    )
    context.send_no_content()
    return True
