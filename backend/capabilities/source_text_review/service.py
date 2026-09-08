"""Source text review service (CP-008).

Manages review, correction, and confirmation of extracted source texts
before they are promoted to verified evidence.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from backend.domain.source_text_review import (
    SOURCE_REVIEW_STATUS_CONFIRMED,
    SOURCE_REVIEW_STATUS_PENDING,
    SourceTextReview,
)

LOGGER = logging.getLogger(__name__)

# In-memory store keyed by "{profile_id}:{source_id}"
_reviews: dict[str, SourceTextReview] = {}

def _reset_reviews() -> None:
    """Clear the in-memory review store (for test isolation)."""
    _reviews.clear()


def _review_key(profile_id: str, source_id: str) -> str:
    return f"{profile_id}:{source_id}"


def get_source_review(profile_id: str, source_id: str) -> SourceTextReview | None:
    """Return the current review state for a source, or None."""
    return _reviews.get(_review_key(profile_id, source_id))


def get_or_create_review(
    profile_id: str,
    source_id: str,
    source_record: Mapping[str, Any],
) -> SourceTextReview:
    """Get existing review or create one from a source record."""
    key = _review_key(profile_id, source_id)
    if key in _reviews:
        return _reviews[key]
    review = SourceTextReview.from_source_record(
        source_id, source_record, profile_id=profile_id,
    )
    _reviews[key] = review
    return review


def list_reviews(profile_id: str) -> list[SourceTextReview]:
    """Return all reviews for a profile."""
    prefix = f"{profile_id}:"
    return [r for k, r in _reviews.items() if k.startswith(prefix)]


def save_correction(
    profile_id: str,
    source_id: str,
    corrected_text: str,
    *,
    changed_by: str = "user",
) -> SourceTextReview | None:
    """Save user correction and return updated review."""
    review = get_source_review(profile_id, source_id)
    if review is None:
        return None
    review.apply_correction(corrected_text, changed_by=changed_by)
    return review


def confirm_review(profile_id: str, source_id: str) -> SourceTextReview | None:
    """Confirm a reviewed source text, making it eligible for evidence."""
    review = get_source_review(profile_id, source_id)
    if review is None:
        return None
    review.confirm()
    return review


def reject_review(profile_id: str, source_id: str) -> SourceTextReview | None:
    """Reject a source text review."""
    review = get_source_review(profile_id, source_id)
    if review is None:
        return None
    review.reject()
    return review


def get_verified_texts(profile_id: str) -> list[dict[str, Any]]:
    """Return all confirmed source texts ready for evidence creation."""
    return [
        {
            "source_id": r.source_id,
            "file_name": r.file_name,
            "text": r.effective_text,
            "method": r.original_method,
            "confidence": r.original_confidence,
            "is_ocr": r.is_ocr,
            "correction_history": r.correction_history,
        }
        for r in list_reviews(profile_id)
        if r.is_verified
    ]


def count_pending_reviews(profile_id: str) -> int:
    """Return the number of sources still requiring review."""
    return sum(1 for r in list_reviews(profile_id) if r.requires_review)
