from __future__ import annotations

from http import HTTPStatus
from typing import Any, Mapping

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.application.rebind_service import (
    execute_rebind,
    perform_rebind_compatibility_review,
)
from backend.domain.models import (
    CAREER_PROFILE_STATUS_UNBOUND,
    CAREER_PROFILE_STATUSES,
    CareerProfile,
)


def register_routes(registry: RouteRegistry) -> None:
    registry.prefix("GET", ("career-profiles",), _handle_list_get, auth_required=True, name="career_profiles.list")
    registry.prefix("POST", ("career-profiles",), _handle_create, auth_required=True, name="career_profiles.create")
    registry.prefix(
        "GET", ("career-profiles", "{profile_id}"), _handle_get, auth_required=True, name="career_profiles.get"
    )
    registry.prefix(
        "PUT", ("career-profiles", "{profile_id}"), _handle_update, auth_required=True, name="career_profiles.update"
    )
    registry.prefix(
        "DELETE", ("career-profiles", "{profile_id}"), _handle_delete, auth_required=True, name="career_profiles.delete"
    )
    registry.prefix(
        "POST", ("career-profiles", "{profile_id}", "bind"), _handle_bind, auth_required=True, name="career_profiles.bind"
    )
    registry.prefix(
        "DELETE", ("career-profiles", "{profile_id}", "bind"), _handle_unbind, auth_required=True, name="career_profiles.unbind"
    )
    registry.prefix(
        "POST", ("career-profiles", "{profile_id}", "baseline-cv"), _handle_bind_baseline_cv, auth_required=True, name="career_profiles.bind_baseline_cv"
    )
    registry.prefix(
        "DELETE", ("career-profiles", "{profile_id}", "baseline-cv"), _handle_unbind_baseline_cv, auth_required=True, name="career_profiles.unbind_baseline_cv"
    )
    registry.prefix(
        "POST", ("career-profiles", "{profile_id}", "rebind-review"), _handle_rebind_review, auth_required=True, name="career_profiles.rebind_review"
    )
    registry.prefix(
        "POST", ("career-profiles", "{profile_id}", "rebind-confirm"), _handle_rebind_confirm, auth_required=True, name="career_profiles.rebind_confirm"
    )


def _career_profile_store(context: ApiRouteContext):
    store = getattr(context.application.repositories, "career_profile_store", None)
    if store is None:
        context.send_error(
            HTTPStatus.NOT_IMPLEMENTED, "career_profiles_disabled", "Career profile storage is not configured."
        )
        return None
    return store


def _handle_list_get(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if segments == ["career-profiles"]:
        store = _career_profile_store(context)
        if store is None:
            return True
        user, _ = context.require_identity()
        profiles = store.list_profiles(user_id=user.user_id)
        context.send_json([p.to_dict() for p in profiles], status=HTTPStatus.OK)
        return True
    return False



def _handle_create(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if segments == ["career-profiles"]:
        store = _career_profile_store(context)
        if store is None:
            return True
        user, _ = context.require_identity()
        payload = context.read_json_body()
        _validate_create_payload(context, payload)
        profile = CareerProfile.create(
            user_id=user.user_id,
            name=str(payload["name"]).strip(),
            description=str(payload.get("description") or "").strip(),
            preferred_language=str(payload.get("preferred_language") or "en").strip(),
            target_direction=str(payload.get("target_direction") or "").strip(),
        )
        store.upsert_profile(profile)
        context.send_json(profile.to_dict(), status=HTTPStatus.CREATED)
        return True
    return False


def _handle_get(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) == 2 and segments[0] == "career-profiles":
        store = _career_profile_store(context)
        if store is None:
            return True
        context.require_identity()
        try:
            profile = store.get_profile(segments[1])
        except KeyError:
            context.send_error(HTTPStatus.NOT_FOUND, "career_profile_not_found", f"Career profile '{segments[1]}' not found.")
            return True
        context.send_json(profile.to_dict(), status=HTTPStatus.OK)
        return True
    return False


def _handle_update(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) == 2 and segments[0] == "career-profiles":
        store = _career_profile_store(context)
        if store is None:
            return True
        context.require_identity()
        try:
            profile = store.get_profile(segments[1])
        except KeyError:
            context.send_error(HTTPStatus.NOT_FOUND, "career_profile_not_found", f"Career profile '{segments[1]}' not found.")
            return True
        payload = context.read_json_body()
        _apply_update_payload(profile, payload)
        store.upsert_profile(profile)
        context.send_json(profile.to_dict(), status=HTTPStatus.OK)
        return True
    return False


def _handle_delete(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) == 2 and segments[0] == "career-profiles":
        store = _career_profile_store(context)
        if store is None:
            return True
        context.require_identity()
        try:
            store.delete_profile(segments[1])
        except KeyError:
            context.send_error(HTTPStatus.NOT_FOUND, "career_profile_not_found", f"Career profile '{segments[1]}' not found.")
            return True
        context.send_no_content(status=HTTPStatus.NO_CONTENT)
        return True
    return False


def _validate_create_payload(context: ApiRouteContext, payload: Mapping[str, Any]) -> None:
    name = str(payload.get("name") or "").strip()
    if not name:
        context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error", "name is required.")
    if len(name) > 200:
        context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error", "name must be at most 200 characters.")


def _apply_update_payload(profile: CareerProfile, payload: Mapping[str, Any]) -> None:
    if "name" in payload:
        name = str(payload["name"] or "").strip()
        if name:
            profile.name = name
    if "description" in payload:
        profile.description = str(payload["description"] or "").strip()
    if "preferred_language" in payload:
        lang = str(payload["preferred_language"] or "").strip()
        if lang:
            profile.preferred_language = lang
    if "target_direction" in payload:
        profile.target_direction = str(payload["target_direction"] or "").strip()
    if "bound_workspace_id" in payload:
        profile.bound_workspace_id = str(payload["bound_workspace_id"] or "").strip()
    if "baseline_cv_asset_id" in payload:
        profile.baseline_cv_asset_id = str(payload["baseline_cv_asset_id"] or "").strip()
    if "baseline_cv_display_name" in payload:
        profile.baseline_cv_display_name = str(payload["baseline_cv_display_name"] or "").strip()
    if "baseline_cv_extraction_date" in payload:
        profile.baseline_cv_extraction_date = str(payload["baseline_cv_extraction_date"] or "").strip()
    if "baseline_cv_source_version" in payload:
        profile.baseline_cv_source_version = str(payload["baseline_cv_source_version"] or "").strip()
    if "status" in payload:
        status = str(payload["status"] or "").strip()
        if status in CAREER_PROFILE_STATUSES:
            profile.status = status
    from backend.domain.models import utc_now_iso
    profile.updated_at = utc_now_iso()



def _handle_bind(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) == 3 and segments[0] == "career-profiles" and segments[2] == "bind":
        store = _career_profile_store(context)
        if store is None:
            return True
        user, _ = context.require_identity()
        try:
            profile = store.get_profile(segments[1])
        except KeyError:
            context.send_error(HTTPStatus.NOT_FOUND, "career_profile_not_found", f"Career profile '{segments[1]}' not found.")
            return True
        if profile.user_id != user.user_id:
            context.send_error(HTTPStatus.FORBIDDEN, "forbidden", "You can only bind your own career profiles.")
            return True
        payload = context.read_json_body()
        workspace_id = str(payload.get("workspace_id") or "").strip()
        if not workspace_id:
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error", "workspace_id is required.")
            return True
        # Validate workspace exists
        workspace = None
        try:
            workspace = context.application.repositories.workspace_repository.get_workspace(workspace_id)
        except Exception:
            pass
        if workspace is None:
            context.send_error(HTTPStatus.NOT_FOUND, "workspace_not_found", f"Workspace '{workspace_id}' not found.")
            return True
        # Bind the workspace
        profile.bound_workspace_id = workspace_id
        from backend.domain.models import utc_now_iso
        profile.updated_at = utc_now_iso()
        store.upsert_profile(profile)
        context.send_json(profile.to_dict(), status=HTTPStatus.OK)
        return True
    return False


def _handle_unbind(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) == 3 and segments[0] == "career-profiles" and segments[2] == "bind":
        store = _career_profile_store(context)
        if store is None:
            return True
        user, _ = context.require_identity()
        try:
            profile = store.get_profile(segments[1])
        except KeyError:
            context.send_error(HTTPStatus.NOT_FOUND, "career_profile_not_found", f"Career profile '{segments[1]}' not found.")
            return True
        if profile.user_id != user.user_id:
            context.send_error(HTTPStatus.FORBIDDEN, "forbidden", "You can only unbind your own career profiles.")
            return True
        if not profile.bound_workspace_id:
            context.send_error(HTTPStatus.CONFLICT, "no_binding", "Career profile is not bound to any workspace.")
            return True
        profile.bound_workspace_id = ""
        from backend.domain.models import utc_now_iso
        profile.updated_at = utc_now_iso()
        store.upsert_profile(profile)
        context.send_json(profile.to_dict(), status=HTTPStatus.OK)
        return True
    return False


def _handle_bind_baseline_cv(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) == 3 and segments[0] == "career-profiles" and segments[2] == "baseline-cv":
        store = _career_profile_store(context)
        if store is None:
            return True
        user, _ = context.require_identity()
        try:
            profile = store.get_profile(segments[1])
        except KeyError:
            context.send_error(HTTPStatus.NOT_FOUND, "career_profile_not_found", f"Career profile '{segments[1]}' not found.")
            return True
        if profile.user_id != user.user_id:
            context.send_error(HTTPStatus.FORBIDDEN, "forbidden", "You can only modify your own career profiles.")
            return True
        payload = context.read_json_body()
        asset_id = str(payload.get("asset_id") or "").strip()
        if not asset_id:
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error", "asset_id is required.")
            return True
        # Resolve the workspace CV asset from user metadata
        user_metadata = dict(getattr(user, "metadata", None) or {})
        user_assets = user_metadata.get("candidate_assets", [])
        if not isinstance(user_assets, list):
            user_assets = []
        asset = None
        for candidate in user_assets:
            if str(candidate.get("asset_id") or "").strip() == asset_id:
                asset = candidate
                break
        if asset is None:
            context.send_error(HTTPStatus.NOT_FOUND, "asset_not_found", f"Workspace CV asset '{asset_id}' not found.")
            return True
        asset_kind = str(asset.get("asset_kind") or "").strip().lower()
        if asset_kind != "workspace_cv":
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_asset_kind", "Asset must be a workspace CV.")
            return True
        profile.baseline_cv_asset_id = asset_id
        profile.baseline_cv_display_name = str(asset.get("display_name") or "").strip()
        from backend.domain.models import utc_now_iso
        profile.baseline_cv_extraction_date = utc_now_iso()
        asset_metadata = dict(asset.get("metadata") or {})
        profile.baseline_cv_source_version = str(asset_metadata.get("content_sha256") or "").strip()
        profile.updated_at = utc_now_iso()
        store.upsert_profile(profile)
        context.send_json(profile.to_dict(), status=HTTPStatus.OK)
        return True
    return False


def _handle_unbind_baseline_cv(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) == 3 and segments[0] == "career-profiles" and segments[2] == "baseline-cv":
        store = _career_profile_store(context)
        if store is None:
            return True
        user, _ = context.require_identity()
        try:
            profile = store.get_profile(segments[1])
        except KeyError:
            context.send_error(HTTPStatus.NOT_FOUND, "career_profile_not_found", f"Career profile '{segments[1]}' not found.")
            return True
        if profile.user_id != user.user_id:
            context.send_error(HTTPStatus.FORBIDDEN, "forbidden", "You can only modify your own career profiles.")
            return True
        if not profile.baseline_cv_asset_id:
            context.send_error(HTTPStatus.CONFLICT, "no_baseline_cv", "Career profile does not have a baseline CV bound.")
            return True
        profile.baseline_cv_asset_id = ""
        profile.baseline_cv_display_name = ""
        profile.baseline_cv_extraction_date = ""
        profile.baseline_cv_source_version = ""
        from backend.domain.models import utc_now_iso
        profile.updated_at = utc_now_iso()
        store.upsert_profile(profile)
        context.send_json(profile.to_dict(), status=HTTPStatus.OK)
        return True
    return False


def _handle_rebind_review(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) == 3 and segments[0] == "career-profiles" and segments[2] == "rebind-review":
        store = _career_profile_store(context)
        if store is None:
            return True
        user, _ = context.require_identity()
        try:
            profile = store.get_profile(segments[1])
        except KeyError:
            context.send_error(HTTPStatus.NOT_FOUND, "career_profile_not_found",
                               f"Career profile '{segments[1]}' not found.")
            return True
        if profile.user_id != user.user_id:
            context.send_error(HTTPStatus.FORBIDDEN, "forbidden",
                               "You can only rebind your own career profiles.")
            return True
        payload = context.read_json_body()
        workspace_id = str(payload.get("workspace_id") or "").strip()
        if not workspace_id:
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error",
                               "workspace_id is required.")
            return True
        workspace = None
        try:
            workspace = context.application.repositories.workspace_repository.get_workspace(workspace_id)
        except Exception:
            pass
        if workspace is None:
            context.send_error(HTTPStatus.NOT_FOUND, "workspace_not_found",
                               f"Workspace '{workspace_id}' not found.")
            return True
        baseline_cv_asset_id = str(payload.get("baseline_cv_asset_id") or "").strip()
        review = perform_rebind_compatibility_review(
            profile, workspace, baseline_cv_asset_id=baseline_cv_asset_id,
        )
        context.send_json(review.to_dict(), status=HTTPStatus.OK)
        return True
    return False


def _handle_rebind_confirm(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) == 3 and segments[0] == "career-profiles" and segments[2] == "rebind-confirm":
        store = _career_profile_store(context)
        if store is None:
            return True
        user, _ = context.require_identity()
        try:
            profile = store.get_profile(segments[1])
        except KeyError:
            context.send_error(HTTPStatus.NOT_FOUND, "career_profile_not_found",
                               f"Career profile '{segments[1]}' not found.")
            return True
        if profile.user_id != user.user_id:
            context.send_error(HTTPStatus.FORBIDDEN, "forbidden",
                               "You can only rebind your own career profiles.")
            return True
        payload = context.read_json_body()
        workspace_id = str(payload.get("workspace_id") or "").strip()
        if not workspace_id:
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error",
                               "workspace_id is required.")
            return True
        workspace = None
        try:
            workspace = context.application.repositories.workspace_repository.get_workspace(workspace_id)
        except Exception:
            pass
        if workspace is None:
            context.send_error(HTTPStatus.NOT_FOUND, "workspace_not_found",
                               f"Workspace '{workspace_id}' not found.")
            return True
        baseline_cv_asset_id = str(payload.get("baseline_cv_asset_id") or "").strip()
        confirmed_conflicts = list(payload.get("confirmed_conflicts") or [])
        review = perform_rebind_compatibility_review(
            profile, workspace, baseline_cv_asset_id=baseline_cv_asset_id,
        )
        try:
            updated = execute_rebind(
                profile, workspace, review,
                baseline_cv_asset_id=baseline_cv_asset_id,
                confirmed_conflicts=confirmed_conflicts,
            )
            store.upsert_profile(updated)
            context.send_json(updated.to_dict(), status=HTTPStatus.OK)
        except ValueError as exc:
            context.send_error(HTTPStatus.CONFLICT, "rebind_conflict", str(exc))
        return True
    return False
