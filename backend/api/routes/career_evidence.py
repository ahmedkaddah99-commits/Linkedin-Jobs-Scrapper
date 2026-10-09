from __future__ import annotations

from http import HTTPStatus

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.evidence.service import (
    confirm_link, create_evidence, delete_evidence,
    dismiss_link_suggestion, get_evidence, link_evidence_to_target,
    list_evidence, list_links_for_evidence,
    suggest_links_for_evidence, suggest_links_for_profile, update_evidence,
)


def register_routes(registry: RouteRegistry) -> None:
    registry.prefix("GET", ("career-profiles", "{profile_id}", "evidence"),
                    _handle_list, auth_required=True, name="career_evidence.list")
    registry.prefix("POST", ("career-profiles", "{profile_id}", "evidence"),
                    _handle_create, auth_required=True, name="career_evidence.create")
    registry.prefix("GET", ("career-profiles", "{profile_id}", "evidence", "{evidence_id}"),
                    _handle_get, auth_required=True, name="career_evidence.get")
    registry.prefix("PUT", ("career-profiles", "{profile_id}", "evidence", "{evidence_id}"),
                    _handle_update, auth_required=True, name="career_evidence.update")
    registry.prefix("DELETE", ("career-profiles", "{profile_id}", "evidence", "{evidence_id}"),
                    _handle_delete, auth_required=True, name="career_evidence.delete")
    registry.prefix("GET", ("career-profiles", "{profile_id}", "evidence", "{evidence_id}", "links"),
                    _handle_list_links, auth_required=True, name="career_evidence.links.list")
    registry.prefix("POST", ("career-profiles", "{profile_id}", "evidence", "{evidence_id}", "links"),
                    _handle_create_link, auth_required=True, name="career_evidence.links.create")
    registry.prefix("POST", ("career-profiles", "{profile_id}", "evidence", "{evidence_id}",
                    "links", "{link_id}", "confirm"),
                    _handle_confirm_link, auth_required=True, name="career_evidence.links.confirm")
    registry.prefix("DELETE", ("career-profiles", "{profile_id}", "evidence", "{evidence_id}",
                    "links", "{link_id}"),
                    _handle_dismiss_link, auth_required=True, name="career_evidence.links.dismiss")
    registry.prefix("POST", ("career-profiles", "{profile_id}", "evidence", "{evidence_id}", "suggest-links"),
                    _handle_suggest_links, auth_required=True, name="career_evidence.suggest_links")
    registry.prefix("POST", ("career-profiles", "{profile_id}", "evidence", "suggest-all"),
                    _handle_suggest_all, auth_required=True, name="career_evidence.suggest_all")



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


def _save_profile(context: ApiRouteContext, profile) -> None:
    store = getattr(context.application.repositories, "career_profile_store", None)
    if store is not None:
        store.upsert_profile(profile)


def _handle_list(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    context.send_json([e.to_dict() for e in list_evidence(profile)], status=HTTPStatus.OK)
    return True


def _handle_create(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    record = create_evidence(profile, context.read_json_body())
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
        context.send_error(HTTPStatus.NOT_FOUND, "evidence_not_found",
                           f"Evidence item '{evidence_id}' not found.")
        return True
    context.send_json(record.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_update(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    evidence_id = context.segment_params.get("evidence_id", "")
    try:
        record = update_evidence(profile, evidence_id, context.read_json_body())
    except KeyError:
        context.send_error(HTTPStatus.NOT_FOUND, "evidence_not_found",
                           f"Evidence item '{evidence_id}' not found.")
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
        context.send_error(HTTPStatus.NOT_FOUND, "evidence_not_found",
                           f"Evidence item '{evidence_id}' not found.")
        return True
    _save_profile(context, profile)
    context.send_no_content(status=HTTPStatus.NO_CONTENT)
    return True



def _handle_list_links(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    evidence_id = context.segment_params.get("evidence_id", "")
    if get_evidence(profile, evidence_id) is None:
        context.send_error(HTTPStatus.NOT_FOUND, "evidence_not_found",
                           f"Evidence item '{evidence_id}' not found.")
        return True
    links = list_links_for_evidence(profile, evidence_id)
    context.send_json([l.to_dict() for l in links], status=HTTPStatus.OK)
    return True


def _handle_create_link(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    evidence_id = context.segment_params.get("evidence_id", "")
    payload = context.read_json_body()
    try:
        link = link_evidence_to_target(
            profile, evidence_id,
            target_type=str(payload.get("target_type") or "unassigned"),
            target_id=str(payload.get("target_id") or ""),
            target_label=str(payload.get("target_label") or ""),
            is_primary=bool(payload.get("is_primary") or False),
            is_suggested=bool(payload.get("is_suggested") or False),
            confidence=float(payload.get("confidence") or 0.0),
            suggestion_reason=str(payload.get("suggestion_reason") or ""),
        )
    except KeyError:
        context.send_error(HTTPStatus.NOT_FOUND, "evidence_not_found",
                           f"Evidence item '{evidence_id}' not found.")
        return True
    _save_profile(context, profile)
    context.send_json(link.to_dict(), status=HTTPStatus.CREATED)
    return True


def _handle_confirm_link(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    evidence_id = context.segment_params.get("evidence_id", "")
    link_id = context.segment_params.get("link_id", "")
    if get_evidence(profile, evidence_id) is None:
        context.send_error(HTTPStatus.NOT_FOUND, "evidence_not_found",
                           f"Evidence item '{evidence_id}' not found.")
        return True
    try:
        link = confirm_link(profile, link_id)
    except KeyError:
        context.send_error(HTTPStatus.NOT_FOUND, "link_not_found",
                           f"Evidence link '{link_id}' not found.")
        return True
    _save_profile(context, profile)
    context.send_json(link.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_dismiss_link(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    evidence_id = context.segment_params.get("evidence_id", "")
    link_id = context.segment_params.get("link_id", "")
    if get_evidence(profile, evidence_id) is None:
        context.send_error(HTTPStatus.NOT_FOUND, "evidence_not_found",
                           f"Evidence item '{evidence_id}' not found.")
        return True
    try:
        dismiss_link_suggestion(profile, link_id)
    except KeyError:
        context.send_error(HTTPStatus.NOT_FOUND, "link_not_found",
                           f"Evidence link '{link_id}' not found.")
        return True
    _save_profile(context, profile)
    context.send_no_content(status=HTTPStatus.NO_CONTENT)
    return True


def _handle_suggest_links(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    evidence_id = context.segment_params.get("evidence_id", "")
    try:
        suggestions = suggest_links_for_evidence(profile, evidence_id)
    except KeyError:
        context.send_error(HTTPStatus.NOT_FOUND, "evidence_not_found",
                           f"Evidence item '{evidence_id}' not found.")
        return True
    _save_profile(context, profile)
    context.send_json([s.to_dict() for s in suggestions], status=HTTPStatus.OK)
    return True


def _handle_suggest_all(context: ApiRouteContext) -> bool | None:
    profile = _get_profile(context)
    if profile is None:
        return True
    suggestions = suggest_links_for_profile(profile)
    _save_profile(context, profile)
    context.send_json([s.to_dict() for s in suggestions], status=HTTPStatus.OK)
    return True
