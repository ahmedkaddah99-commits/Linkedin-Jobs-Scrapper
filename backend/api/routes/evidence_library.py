from __future__ import annotations

from http import HTTPStatus

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.evidence_library import (
    create_evidence,
    delete_evidence,
    get_evidence,
    list_evidence,
    update_evidence,
)


def register_routes(registry: RouteRegistry) -> None:
    registry.prefix(
        "GET",
        ("career-profiles", "{profile_id}", "experiences", "{experience_id}", "evidence"),
        _handle_list,
        auth_required=True,
        name="evidence_library.list",
    )
    registry.prefix(
        "POST",
        ("career-profiles", "{profile_id}", "experiences", "{experience_id}", "evidence"),
        _handle_create,
        auth_required=True,
        name="evidence_library.create",
    )
    registry.prefix(
        "GET",
        ("career-profiles", "{profile_id}", "experiences", "{experience_id}", "evidence", "{evidence_id}"),
        _handle_get,
        auth_required=True,
        name="evidence_library.get",
    )
    registry.prefix(
        "PUT",
        ("career-profiles", "{profile_id}", "experiences", "{experience_id}", "evidence", "{evidence_id}"),
        _handle_update,
        auth_required=True,
        name="evidence_library.update",
    )
    registry.prefix(
        "DELETE",
        ("career-profiles", "{profile_id}", "experiences", "{experience_id}", "evidence", "{evidence_id}"),
        _handle_delete,
        auth_required=True,
        name="evidence_library.delete",
    )


def _get_profile(context: ApiRouteContext):
    store = getattr(context.application.repositories, "career_profile_store", None)
    if store is None:
        context.send_error(
            HTTPStatus.NOT_IMPLEMENTED,
            "career_profiles_disabled",
            "Career profile storage is not configured.",
        )
        return None
    profile_id = context.segment_params.get("profile_id", "")
    try:
        profile = store.get_profile(profile_id)
    except KeyError:
        context.send_error(
            HTTPStatus.NOT_FOUND,
            "career_profile_not_found",
            f"Career profile '{profile_id}' not found.",
        )
        return None
    user, _ = context.require_identity()
    if profile.user_id != user.user_id:
        context.send_error(
            HTTPStatus.FORBIDDEN,
            "forbidden",
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

    experience_id = context.segment_params.get("experience_id", "")
    evidence_type = (context.query.get("evidence_type") or [""])[0]
    verification_state = (context.query.get("verification_state") or [""])[0]
    source = (context.query.get("source") or [""])[0]

    records = list_evidence(
        profile,
        experience_id=experience_id,
        evidence_type=evidence_type,
        verification_state=verification_state,
        source=source,
    )
    context.send_json([r.to_dict() for r in records], status=HTTPStatus.OK)
    return True


def _handle_create(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True

    experience_id = context.segment_params.get("experience_id", "")
    payload = context.read_json_body()
    payload = dict(payload)
    payload["experience_id"] = experience_id

    try:
        record = create_evidence(profile, payload)
    except ValueError as exc:
        context.send_error(HTTPStatus.BAD_REQUEST, "validation_error", str(exc))
        return True

    _save_profile(context, profile)
    context.send_json(record.to_dict(), status=HTTPStatus.CREATED)
    return True


def _handle_get(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True

    evidence_id = context.segment_params.get("evidence_id", "")
    record = get_evidence(profile, evidence_id)
    if record is None:
        context.send_error(
            HTTPStatus.NOT_FOUND,
            "evidence_not_found",
            f"Evidence item '{evidence_id}' not found.",
        )
        return True
    context.send_json(record.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_update(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True

    evidence_id = context.segment_params.get("evidence_id", "")
    payload = context.read_json_body()

    try:
        record = update_evidence(profile, evidence_id, payload)
    except KeyError:
        context.send_error(
            HTTPStatus.NOT_FOUND,
            "evidence_not_found",
            f"Evidence item '{evidence_id}' not found.",
        )
        return True

    _save_profile(context, profile)
    context.send_json(record.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_delete(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True

    evidence_id = context.segment_params.get("evidence_id", "")

    try:
        delete_evidence(profile, evidence_id)
    except KeyError:
        context.send_error(
            HTTPStatus.NOT_FOUND,
            "evidence_not_found",
            f"Evidence item '{evidence_id}' not found.",
        )
        return True

    _save_profile(context, profile)
    context.send_no_content(status=HTTPStatus.NO_CONTENT)
    return True
