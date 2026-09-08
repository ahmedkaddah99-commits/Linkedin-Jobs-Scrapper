"""API routes for evidence recommendation (CP-018)."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Mapping

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.capabilities.evidence_recommendation import (
    generate_recommendations,
    get_recommendation,
    set_match_status,
)


def register_routes(registry: RouteRegistry) -> None:
    registry.prefix(
        "POST",
        ("career-profiles", "{profile_id}", "evidence-recommendations"),
        _handle_generate,
        auth_required=True,
        name="evidence_recommendation.generate",
    )
    registry.prefix(
        "GET",
        ("career-profiles", "{profile_id}", "evidence-recommendations", "{recommendation_id}"),
        _handle_get,
        auth_required=True,
        name="evidence_recommendation.get",
    )
    registry.prefix(
        "PUT",
        (
            "career-profiles",
            "{profile_id}",
            "evidence-recommendations",
            "{recommendation_id}",
            "matches",
            "{match_id}",
        ),
        _handle_set_match_status,
        auth_required=True,
        name="evidence_recommendation.set_match_status",
    )


def _extract_params(context: ApiRouteContext):
    segments = list(context.segments)
    profile_id = segments[1] if len(segments) > 1 else ""
    recommendation_id = segments[3] if len(segments) > 3 else ""
    match_id = segments[5] if len(segments) > 5 else ""
    return profile_id, recommendation_id, match_id


def _candidate_asset_map(context: ApiRouteContext) -> dict[str, dict[str, Any]]:
    user, _ = context.require_identity()
    user_metadata = dict(getattr(user, "metadata", None) or {})
    assets = user_metadata.get("candidate_assets") or []
    if not isinstance(assets, list):
        assets = []
    return {
        str(asset.get("asset_id") or ""): dict(asset)
        for asset in assets
        if isinstance(asset, Mapping) and str(asset.get("asset_id") or "")
    }


def _handle_generate(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) < 3 or segments[0] != "career-profiles" or segments[2] != "evidence-recommendations":
        return False
    profile_id = segments[1]
    user, _ = context.require_identity()
    payload = context.read_json_body()

    job_id = str(payload.get("job_id") or "")
    if not job_id:
        context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error", "job_id is required.")
        return True

    recommendation = generate_recommendations(
        user,
        job_id=job_id,
        job_title=str(payload.get("job_title") or ""),
        job_company=str(payload.get("job_company") or ""),
        profile_id=profile_id,
        requirements=list(payload.get("requirements") or []),
        candidate_asset_map=_candidate_asset_map(context),
    )
    context.send_json(recommendation.to_dict(), status=HTTPStatus.CREATED)
    return True


def _handle_get(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) < 4 or segments[0] != "career-profiles" or segments[2] != "evidence-recommendations":
        return False
    _, recommendation_id, _ = _extract_params(context)
    context.require_identity()
    recommendation = get_recommendation(recommendation_id)
    if recommendation is None:
        context.send_error(
            HTTPStatus.NOT_FOUND, "recommendation_not_found",
            f"Evidence recommendation '{recommendation_id}' not found.",
        )
        return True
    context.send_json(recommendation.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_set_match_status(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if (
        len(segments) < 6
        or segments[0] != "career-profiles"
        or segments[2] != "evidence-recommendations"
        or segments[4] != "matches"
    ):
        return False
    _, recommendation_id, match_id = _extract_params(context)
    context.require_identity()
    payload = context.read_json_body()
    status = str(payload.get("include_status") or "").strip()
    if not status:
        context.send_error(
            HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error",
            "include_status is required (included, excluded, or pending).",
        )
        return True
    try:
        updated = set_match_status(recommendation_id, match_id, status)
    except ValueError as exc:
        context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error", str(exc))
        return True
    if updated is None:
        context.send_error(
            HTTPStatus.NOT_FOUND, "match_not_found",
            f"Match '{match_id}' not found in recommendation '{recommendation_id}'.",
        )
        return True
    context.send_json(updated.to_dict(), status=HTTPStatus.OK)
    return True
