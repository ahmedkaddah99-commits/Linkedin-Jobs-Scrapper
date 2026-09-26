from __future__ import annotations

from http import HTTPStatus

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.work_experience import (
    confirm_merge,
    create_experience,
    delete_experience,
    dismiss_merge_suggestion,
    extract_experiences,
    get_experience,
    get_merge_suggestions,
    list_experiences,
    update_experience,
)


def register_routes(registry: RouteRegistry) -> None:
    registry.prefix("GET", ("career-profiles", "{profile_id}", "experiences"),
                    _handle_list, auth_required=True, name="work_experiences.list")
    registry.prefix("POST", ("career-profiles", "{profile_id}", "experiences"),
                    _handle_create, auth_required=True, name="work_experiences.create")
    registry.prefix("GET", ("career-profiles", "{profile_id}", "experiences", "{experience_id}"),
                    _handle_get, auth_required=True, name="work_experiences.get")
    registry.prefix("PUT", ("career-profiles", "{profile_id}", "experiences", "{experience_id}"),
                    _handle_update, auth_required=True, name="work_experiences.update")
    registry.prefix("DELETE", ("career-profiles", "{profile_id}", "experiences", "{experience_id}"),
                    _handle_delete, auth_required=True, name="work_experiences.delete")
    registry.prefix("POST", ("career-profiles", "{profile_id}", "experiences", "extract"),
                    _handle_extract, auth_required=True, name="work_experiences.extract")
    registry.prefix("GET", ("career-profiles", "{profile_id}", "experiences", "merge-suggestions"),
                    _handle_merge_suggestions, auth_required=True, name="work_experiences.merge_suggestions")
    registry.prefix("POST", ("career-profiles", "{profile_id}", "experiences", "merge-suggestions",
                    "{suggestion_id}", "confirm"),
                    _handle_confirm_merge, auth_required=True, name="work_experiences.confirm_merge")

    registry.prefix("POST", ("career-profiles", "{profile_id}", "experiences", "merge-suggestions",
                    "{suggestion_id}", "dismiss"),
                    _handle_dismiss_merge, auth_required=True, name="work_experiences.dismiss_merge")

def _get_profile(context: ApiRouteContext):
    store = getattr(context.application.repositories, "career_profile_store", None)
    if store is None:
        context.send_error(HTTPStatus.NOT_IMPLEMENTED, "career_profiles_disabled",
                           "Career profile storage is not configured.")
        return None
    profile_id = context.segment_params.get("profile_id", "")
    try:
        profile = store.get_profile(profile_id)
    except KeyError:
        context.send_error(HTTPStatus.NOT_FOUND, "career_profile_not_found",
                           f"Career profile '{profile_id}' not found.")
        return None
    user, _ = context.require_identity()
    if profile.user_id != user.user_id:
        context.send_error(HTTPStatus.FORBIDDEN, "forbidden",
                           "You can only access your own career profiles.")
        return None
    return profile


def _handle_list(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    experiences = list_experiences(profile)
    context.send_json([e.to_dict() for e in experiences], status=HTTPStatus.OK)
    return True


def _handle_create(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    payload = context.read_json_body()
    record = create_experience(profile, payload)
    _save_profile(context, profile)
    context.send_json(record.to_dict(), status=HTTPStatus.CREATED)
    return True


def _handle_get(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    experience_id = context.segment_params.get("experience_id", "")
    record = get_experience(profile, experience_id)
    if record is None:
        context.send_error(HTTPStatus.NOT_FOUND, "work_experience_not_found",
                           f"Work experience '{experience_id}' not found.")
        return True
    context.send_json(record.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_update(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    experience_id = context.segment_params.get("experience_id", "")
    payload = context.read_json_body()
    try:
        record = update_experience(profile, experience_id, payload)
    except KeyError:
        context.send_error(HTTPStatus.NOT_FOUND, "work_experience_not_found",
                           f"Work experience '{experience_id}' not found.")
        return True
    _save_profile(context, profile)
    context.send_json(record.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_delete(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    experience_id = context.segment_params.get("experience_id", "")
    try:
        delete_experience(profile, experience_id)
    except KeyError:
        context.send_error(HTTPStatus.NOT_FOUND, "work_experience_not_found",
                           f"Work experience '{experience_id}' not found.")
        return True
    _save_profile(context, profile)
    context.send_no_content(status=HTTPStatus.NO_CONTENT)
    return True


def _handle_extract(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    payload = context.read_json_body()
    source_ids = payload.get("source_asset_ids") or []
    user, _ = context.require_identity()
    try:
        records = extract_experiences(profile, user, source_ids)
    except ValueError as exc:
        context.send_error(HTTPStatus.BAD_REQUEST, "extraction_failed", str(exc))
        return True
    _save_profile(context, profile)
    context.send_json([r.to_dict() for r in records], status=HTTPStatus.CREATED)
    return True


def _handle_merge_suggestions(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    suggestions = get_merge_suggestions(profile)
    _save_profile(context, profile)
    context.send_json([s.to_dict() for s in suggestions], status=HTTPStatus.OK)
    return True


def _handle_confirm_merge(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    suggestion_id = context.segment_params.get("suggestion_id", "")
    try:
        merged = confirm_merge(profile, suggestion_id)
    except KeyError:
        context.send_error(HTTPStatus.NOT_FOUND, "merge_suggestion_not_found",
                           f"Merge suggestion '{suggestion_id}' not found.")
        return True
    except ValueError as exc:
        context.send_error(HTTPStatus.CONFLICT, "merge_conflict", str(exc))
        return True
    _save_profile(context, profile)
    context.send_json(merged.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_dismiss_merge(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    suggestion_id = context.segment_params.get("suggestion_id", "")
    try:
        dismiss_merge_suggestion(profile, suggestion_id)
    except KeyError:
        context.send_error(HTTPStatus.NOT_FOUND, "merge_suggestion_not_found",
                           f"Merge suggestion '{suggestion_id}' not found.")
        return True
    _save_profile(context, profile)
    context.send_no_content(status=HTTPStatus.NO_CONTENT)
    return True


def _save_profile(context: ApiRouteContext, profile) -> None:
    store = getattr(context.application.repositories, "career_profile_store", None)
    if store is not None:
        store.upsert_profile(profile)