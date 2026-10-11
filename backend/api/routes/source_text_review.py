"""API routes for source text review and correction (CP-008)."""

from __future__ import annotations

from http import HTTPStatus

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.capabilities.source_text_review import (
    confirm_review,
    count_pending_reviews,
    get_or_create_review,
    get_source_review,
    get_verified_texts,
    list_reviews,
    reject_review,
    save_correction,
)


def register_routes(registry: RouteRegistry) -> None:
    registry.prefix(
        "GET",
        ("career-profiles", "{profile_id}", "sources", "{source_id}", "review"),
        _handle_get_review, auth_required=True, name="source_review.get",
    )
    registry.prefix(
        "PUT",
        ("career-profiles", "{profile_id}", "sources", "{source_id}", "review"),
        _handle_update_review, auth_required=True, name="source_review.update",
    )
    registry.prefix(
        "POST",
        ("career-profiles", "{profile_id}", "sources", "{source_id}", "confirm"),
        _handle_confirm_review, auth_required=True, name="source_review.confirm",
    )
    registry.prefix(
        "POST",
        ("career-profiles", "{profile_id}", "sources", "{source_id}", "reject"),
        _handle_reject_review, auth_required=True, name="source_review.reject",
    )
    registry.prefix(
        "GET",
        ("career-profiles", "{profile_id}", "sources"),
        _handle_list_sources, auth_required=True, name="source_review.list",
    )
    registry.prefix(
        "GET",
        ("career-profiles", "{profile_id}", "verified-texts"),
        _handle_verified_texts, auth_required=True, name="source_review.verified_texts",
    )



def _extract_params(context: ApiRouteContext):
    segments = list(context.segments)
    profile_id = segments[1] if len(segments) > 1 else ""
    source_id = segments[3] if len(segments) > 3 else ""
    return profile_id, source_id


def _require_source_record(context: ApiRouteContext, source_id: str):
    user, _ = context.require_identity()
    user_metadata = dict(getattr(user, "metadata", None) or {})
    assets = user_metadata.get("candidate_assets") or []
    if not isinstance(assets, list):
        assets = []
    for asset in assets:
        if str(asset.get("asset_id") or "").strip() == source_id:
            asset_metadata = dict(asset.get("metadata") or {})
            extraction = dict(asset_metadata.get("text_extraction") or {})
            return {
                "source_id": source_id,
                "file_name": str(asset.get("display_name") or ""),
                "file_path": str(asset.get("path") or ""),
                "text": str(asset_metadata.get("source_text") or ""),
                "char_count": int(asset_metadata.get("source_char_count") or 0),
                "method": str(extraction.get("method") or ""),
                "confidence": float(extraction.get("confidence") or 0.0),
                "provider": str(extraction.get("provider") or ""),
                "model": str(extraction.get("model") or ""),
                "is_ocr": bool(extraction.get("is_ocr")),
                "is_low_confidence_ocr": bool(extraction.get("is_low_confidence_ocr")),
                "warnings": list(extraction.get("warnings") or []),
                "pages": list(extraction.get("pages") or []),
                "status": str(extraction.get("status") or ""),
            }
    return None


def _handle_get_review(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) < 5:
        return False
    profile_id, source_id = _extract_params(context)
    source_record = _require_source_record(context, source_id)
    if source_record is None:
        context.send_error(HTTPStatus.NOT_FOUND, "source_not_found",
                           f"Source '{source_id}' not found.")
        return True
    review = get_or_create_review(profile_id, source_id, source_record)
    context.send_json(review.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_update_review(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) < 5:
        return False
    profile_id, source_id = _extract_params(context)
    existing = get_source_review(profile_id, source_id)
    if existing is None:
        context.send_error(HTTPStatus.NOT_FOUND, "review_not_found",
                           f"No review for source '{source_id}'.")
        return True
    payload = context.read_json_body()
    corrected_text = str(payload.get("corrected_text") or "")
    updated = save_correction(profile_id, source_id, corrected_text)
    if updated is None:
        context.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "save_failed", "")
        return True
    context.send_json(updated.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_confirm_review(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) < 5:
        return False
    profile_id, source_id = _extract_params(context)
    result = confirm_review(profile_id, source_id)
    if result is None:
        context.send_error(HTTPStatus.NOT_FOUND, "review_not_found",
                           f"No review for source '{source_id}'.")
        return True
    context.send_json(result.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_reject_review(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) < 5:
        return False
    profile_id, source_id = _extract_params(context)
    result = reject_review(profile_id, source_id)
    if result is None:
        context.send_error(HTTPStatus.NOT_FOUND, "review_not_found",
                           f"No review for source '{source_id}'.")
        return True
    context.send_json(result.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_list_sources(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) < 2 or segments[0] != "career-profiles":
        return False
    profile_id = segments[1]
    reviews = list_reviews(profile_id)
    pending = count_pending_reviews(profile_id)
    context.send_json({
        "reviews": [r.to_dict() for r in reviews],
        "pending_count": pending,
    }, status=HTTPStatus.OK)
    return True


def _handle_verified_texts(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) < 2 or segments[0] != "career-profiles":
        return False
    profile_id = segments[1]
    texts = get_verified_texts(profile_id)
    context.send_json({"verified_texts": texts}, status=HTTPStatus.OK)
    return True
