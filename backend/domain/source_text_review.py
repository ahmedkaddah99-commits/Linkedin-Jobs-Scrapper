"""Domain model for source text review and correction workflow (CP-008).

Tracks the review state of extracted source text before it becomes verified evidence.
Preserves original extraction alongside user corrections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from backend.domain.models import utc_now_iso


SOURCE_REVIEW_STATUS_PENDING = "pending"
SOURCE_REVIEW_STATUS_IN_PROGRESS = "in_progress"
SOURCE_REVIEW_STATUS_CONFIRMED = "confirmed"
SOURCE_REVIEW_STATUS_REJECTED = "rejected"

SOURCE_REVIEW_STATUSES = {
    SOURCE_REVIEW_STATUS_PENDING,
    SOURCE_REVIEW_STATUS_IN_PROGRESS,
    SOURCE_REVIEW_STATUS_CONFIRMED,
    SOURCE_REVIEW_STATUS_REJECTED,
}


@dataclass(slots=True)
class SourceTextReview:
    """Tracks a single source text review, corrections, and confirmation state."""

    source_id: str
    profile_id: str = ""
    file_name: str = ""
    file_path: str = ""
    original_text: str = ""
    original_confidence: float = 0.0
    original_method: str = ""
    original_provider: str = ""
    original_model: str = ""
    is_ocr: bool = False
    is_low_confidence_ocr: bool = False
    warnings: list[str] = field(default_factory=list)
    ocr_regions: list[dict[str, Any]] = field(default_factory=list)
    corrected_text: str = ""
    status: str = SOURCE_REVIEW_STATUS_PENDING
    correction_history: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "profile_id": self.profile_id,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "original_text": self.original_text,
            "original_confidence": self.original_confidence,
            "original_method": self.original_method,
            "original_provider": self.original_provider,
            "original_model": self.original_model,
            "is_ocr": self.is_ocr,
            "is_low_confidence_ocr": self.is_low_confidence_ocr,
            "warnings": list(self.warnings),
            "ocr_regions": list(self.ocr_regions),
            "corrected_text": self.corrected_text,
            "status": self.status,
            "correction_history": list(self.correction_history),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SourceTextReview":
        return cls(
            source_id=str(payload.get("source_id") or ""),
            profile_id=str(payload.get("profile_id") or ""),
            file_name=str(payload.get("file_name") or ""),
            file_path=str(payload.get("file_path") or ""),
            original_text=str(payload.get("original_text") or ""),
            original_confidence=float(payload.get("original_confidence") or 0.0),
            original_method=str(payload.get("original_method") or ""),
            original_provider=str(payload.get("original_provider") or ""),
            original_model=str(payload.get("original_model") or ""),
            is_ocr=bool(payload.get("is_ocr")),
            is_low_confidence_ocr=bool(payload.get("is_low_confidence_ocr")),
            warnings=[str(w) for w in (payload.get("warnings") or [])],
            ocr_regions=[
                dict(r) for r in (payload.get("ocr_regions") or []) if isinstance(r, dict)
            ],
            corrected_text=str(payload.get("corrected_text") or ""),
            status=str(payload.get("status") or SOURCE_REVIEW_STATUS_PENDING),
            correction_history=[
                dict(c) for c in (payload.get("correction_history") or []) if isinstance(c, dict)
            ],
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )

    @classmethod
    def from_source_record(
        cls,
        source_id: str,
        source_record: Mapping[str, Any],
        *,
        profile_id: str = "",
    ) -> "SourceTextReview":
        rec = source_record.to_dict() if hasattr(source_record, "to_dict") else dict(source_record)
        now = utc_now_iso()
        needs_review = (
            bool(rec.get("is_low_confidence_ocr"))
            or str(rec.get("status") or "") == "needs_review"
        )
        return cls(
            source_id=str(source_id or rec.get("source_id") or ""),
            profile_id=profile_id,
            file_name=str(rec.get("file_name") or ""),
            file_path=str(rec.get("file_path") or ""),
            original_text=str(rec.get("text") or ""),
            original_confidence=float(rec.get("confidence") or 0.0),
            original_method=str(rec.get("method") or ""),
            original_provider=str(rec.get("provider") or ""),
            original_model=str(rec.get("model") or ""),
            is_ocr=bool(rec.get("is_ocr")),
            is_low_confidence_ocr=bool(rec.get("is_low_confidence_ocr")),
            warnings=[str(w) for w in (rec.get("warnings") or [])],
            ocr_regions=[dict(p) for p in (rec.get("pages") or []) if isinstance(p, dict)],
            corrected_text="",
            status=SOURCE_REVIEW_STATUS_PENDING if needs_review else SOURCE_REVIEW_STATUS_CONFIRMED,
            correction_history=[],
            created_at=now,
            updated_at=now,
        )

    def record_correction(self, prev_text: str, new_text: str, *, by: str = "user") -> None:
        """Append a correction entry to the history."""
        self.correction_history.append({
            "timestamp": utc_now_iso(),
            "changed_by": by,
            "previous_text": prev_text,
            "new_text": new_text,
            "char_diff": len(new_text) - len(prev_text),
        })
        self.updated_at = utc_now_iso()

    def apply_correction(self, new_text: str, *, changed_by: str = "user") -> None:
        """Store the corrected text and record the change in history."""
        previous = self.corrected_text or self.original_text
        self.corrected_text = new_text
        self.status = SOURCE_REVIEW_STATUS_IN_PROGRESS
        self.record_correction(previous, new_text, by=changed_by)

    def confirm(self) -> None:
        """Mark the review as confirmed so the text can become evidence."""
        self.status = SOURCE_REVIEW_STATUS_CONFIRMED
        self.updated_at = utc_now_iso()

    def reject(self) -> None:
        """Mark the review as rejected."""
        self.status = SOURCE_REVIEW_STATUS_REJECTED
        self.updated_at = utc_now_iso()

    @property
    def effective_text(self) -> str:
        """Return the user-corrected text if available, otherwise the original."""
        return self.corrected_text if self.corrected_text else self.original_text

    @property
    def requires_review(self) -> bool:
        """True when this source must be reviewed before it can become evidence."""
        return self.is_low_confidence_ocr or self.status in (
            SOURCE_REVIEW_STATUS_PENDING, SOURCE_REVIEW_STATUS_IN_PROGRESS,
        )

    @property
    def is_verified(self) -> bool:
        """True when confirmed and ready for evidence creation."""
        return self.status == SOURCE_REVIEW_STATUS_CONFIRMED


__all__ = [
    "SOURCE_REVIEW_STATUS_CONFIRMED",
    "SOURCE_REVIEW_STATUS_IN_PROGRESS",
    "SOURCE_REVIEW_STATUS_PENDING",
    "SOURCE_REVIEW_STATUS_REJECTED",
    "SOURCE_REVIEW_STATUSES",
    "SourceTextReview",
]
