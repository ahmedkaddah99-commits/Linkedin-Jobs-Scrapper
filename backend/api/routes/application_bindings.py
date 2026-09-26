"""API routes for job application bindings (CP-017).

Connect a career profile to a specific job application.
"""

from __future__ import annotations

from http import HTTPStatus

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.capabilities.profile_matching.application_binding import (
    create_application_binding,
    delete_application_binding,
    get_application_binding,
    list_application_bindings,
)


def register_routes(registry: RouteRegistry) -> None:
    registry.prefix(
        "GET", ("career-profiles", "{profile_id}", "application-bindings"),
        _handle_list, auth_required=True, name="application_bindings.list",
    )
    registry.prefix(
        "POST", ("career-profiles", "{profile_id}", "application-bindings"),
        _handle_create, auth_required=True, name="application_bindings.create",
    )
    registry.prefix(
        "GET", ("career-profiles", "{profile_id}", "application-bindings", "{binding_id}"),
        _handle_get, auth_required=True, name="application_bindings.get",
    )
    registry.prefix(
        "DELETE", ("career-profiles", "{profile_id}", "application-bindings", "{binding_id}"),
        _handle_delete, auth_required=True, name="application_bindings.delete",
    )


def _get_profile(context: ApiRouteContext):
    store = getattr(context.application.repositories, "career_profile_store", None)
    if store is None:
        context.send_error(
            HTTPStatus.NOT_IMPLEMENTED, "career_profiles_disabled",
            "Career profile storage is not configured.",
        )
        return None
    profile_id = context.segment_params.get("profile_id", "")
    try:
        profile = store.get_profile(profile_id)
    except KeyError:
        context.send_error(
            HTTPStatus.NOT_FOUND, "career_profile_not_found",
            f"Career profile '{profile_id}' not found.",
        )
        return None
    user, _ = context.require_identity()
    if profile.user_id != user.user_id:
        context.send_error(
            HTTPStatus.FORBIDDEN, "forbidden",
            "You can only access your own career profiles.",
        )
        return None
    return profile


def _save_profile(context: ApiRouteContext, profile) -> None:
    store = getattr(context.application.repositories, "career_profile_store", None)
    if store is not None:
        store.upsert_profile(profile)


def _handle_list(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    bindings = list_application_bindings(profile)
    context.send_json([b.to_dict() for b in bindings], status=HTTPStatus.OK)
    return True


def _handle_create(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    payload = context.read_json_body()

    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        context.send_error(
            HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error",
            "job_id is required.",
        )
        return True

    binding = create_application_binding(
        profile,
        job_id=job_id,
        run_id=str(payload.get("run_id") or "").strip(),
        job_title=str(payload.get("job_title") or "").strip(),
        company=str(payload.get("company") or "").strip(),
        location=str(payload.get("location") or "").strip(),
        target_role=str(payload.get("target_role") or "").strip(),
        application_type=str(payload.get("application_type") or "").strip(),
        description_text=str(payload.get("description_text") or "").strip(),
    )
    _save_profile(context, profile)
    context.send_json(binding.to_dict(), status=HTTPStatus.CREATED)
    return True


def _handle_get(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    binding_id = context.segment_params.get("binding_id", "")
    binding = get_application_binding(profile, binding_id)
    if binding is None:
        context.send_error(
            HTTPStatus.NOT_FOUND, "application_binding_not_found",
            f"Application binding '{binding_id}' not found.",
        )
        return True
    context.send_json(binding.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_delete(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    binding_id = context.segment_params.get("binding_id", "")
    try:
        delete_application_binding(profile, binding_id)
    except KeyError:
        context.send_error(
            HTTPStatus.NOT_FOUND, "application_binding_not_found",
            f"Application binding '{binding_id}' not found.",
        )
        return True
    _save_profile(context, profile)
    context.send_no_content(status=HTTPStatus.NO_CONTENT)
    return True
