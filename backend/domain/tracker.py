from __future__ import annotations

from backend.domain.models import ReviewRecord, utc_now_iso


PLACED_IN_TRACKER_AT_METADATA_KEY = "placed_in_tracker_at"


def review_is_actionable_tracker_item(review: ReviewRecord) -> bool:
    metadata = dict(review.metadata or {})
    if review.decision == "duplicate":
        return False
    return bool(
        review.decision == "approved"
        or str(metadata.get("tracker_status") or "").strip()
        or bool(metadata.get("email_confirmed") or False)
    )


def review_placed_in_tracker_at(review: ReviewRecord, *, include_legacy_fallback: bool = True) -> str:
    placed_at = str((review.metadata or {}).get(PLACED_IN_TRACKER_AT_METADATA_KEY) or "").strip()
    if placed_at:
        return placed_at
    if include_legacy_fallback and review_is_actionable_tracker_item(review):
        return str(review.created_at or "").strip()
    return ""


def ensure_review_placed_in_tracker_at(
    review: ReviewRecord,
    *,
    previously_actionable: bool = False,
    existing_placed_in_tracker_at: str = "",
    placed_at: str = "",
) -> str:
    metadata = dict(review.metadata or {})
    existing_placed_at = str(existing_placed_in_tracker_at or "").strip()
    if existing_placed_at:
        metadata[PLACED_IN_TRACKER_AT_METADATA_KEY] = existing_placed_at
        review.metadata = metadata
        return existing_placed_at

    if not review_is_actionable_tracker_item(review):
        metadata.pop(PLACED_IN_TRACKER_AT_METADATA_KEY, None)
        review.metadata = metadata
        return ""

    resolved_placed_at = str(placed_at or "").strip()
    if not resolved_placed_at and previously_actionable:
        resolved_placed_at = str(review.created_at or "").strip()
    resolved_placed_at = resolved_placed_at or utc_now_iso()
    metadata[PLACED_IN_TRACKER_AT_METADATA_KEY] = resolved_placed_at
    review.metadata = metadata
    return resolved_placed_at
