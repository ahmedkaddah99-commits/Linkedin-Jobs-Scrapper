"""Domain model for Career Profile Evidence review (CP-010).

Tracks individual evidence items extracted from source texts. Users can verify,
edit, reject, or defer each item. Rejected evidence is excluded from generated material.
Original source content and user edits are preserved with full audit history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import uuid4

from backend.domain.models import utc_now_iso

# ── Evidence statuses ────────────────────────────────────────────────────────

EVIDENCE_STATUS_PENDING = "pending"
EVIDENCE_STATUS_VERIFIED = "verified"
EVIDENCE_STATUS_REJECTED = "rejected"
EVIDENCE_STATUS_DEFERRED = "deferred"

EVIDENCE_STATUSES = {
    EVIDENCE_STATUS_PENDING,
    EVIDENCE_STATUS_VERIFIED,
    EVIDENCE_STATUS_REJECTED,
    EVIDENCE_STATUS_DEFERRED,
}

# ── Evidence field types ─────────────────────────────────────────────────────

EVIDENCE_FIELD_EXPERIENCE = "experience"
EVIDENCE_FIELD_EDUCATION = "education"
EVIDENCE_FIELD_SKILL = "skill"
EVIDENCE_FIELD_CERTIFICATION = "certification"
EVIDENCE_FIELD_CONTACT = "contact"
EVIDENCE_FIELD_SUMMARY = "summary"
EVIDENCE_FIELD_LANGUAGE = "language"
EVIDENCE_FIELD_PROJECT = "project"
EVIDENCE_FIELD_OTHER = "other"

EVIDENCE_FIELD_TYPES = {
    EVIDENCE_FIELD_EXPERIENCE,
    EVIDENCE_FIELD_EDUCATION,
    EVIDENCE_FIELD_SKILL,
    EVIDENCE_FIELD_CERTIFICATION,
    EVIDENCE_FIELD_CONTACT,
    EVIDENCE_FIELD_SUMMARY,
    EVIDENCE_FIELD_LANGUAGE,
    EVIDENCE_FIELD_PROJECT,
    EVIDENCE_FIELD_OTHER,
}


@dataclass(slots=True)
class CareerProfileEvidence:
    """A single extracted evidence item for a career profile."""

    evidence_id: str
    profile_id: str
    source_id: str
    source_name: str = ""
    field_type: str = EVIDENCE_FIELD_OTHER
    extracted_text: str = ""
    edited_text: str = ""
    extraction_reason: str = ""
    extraction_confidence: float = 0.0
    status: str = EVIDENCE_STATUS_PENDING
    edit_history: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    # ── properties ───────────────────────────────────────────────────────

    @property
    def effective_text(self) -> str:
        """Return user-edited text if available, otherwise the original."""
        return self.edited_text if self.edited_text else self.extracted_text

    @property
    def is_edited(self) -> bool:
        """True when the user has changed the extracted text."""
        return bool(self.edited_text) and self.edited_text != self.extracted_text

    @property
    def is_usable(self) -> bool:
        """True when this evidence should be used in generated material."""
        return self.status == EVIDENCE_STATUS_VERIFIED

    @property
    def is_rejected(self) -> bool:
        """True when evidence has been explicitly rejected by the user."""
        return self.status == EVIDENCE_STATUS_REJECTED

    @property
    def is_deferred(self) -> bool:
        """True when evidence has been deferred for later review."""
        return self.status == EVIDENCE_STATUS_DEFERRED

    # ── actions ──────────────────────────────────────────────────────────

    def verify(self) -> None:
        """Mark evidence as verified — usable in generated material."""
        self.status = EVIDENCE_STATUS_VERIFIED
        self.updated_at = utc_now_iso()

    def reject(self) -> None:
        """Reject evidence — excluded from generated material.
        Original extracted text and any user edits are preserved."""
        self.status = EVIDENCE_STATUS_REJECTED
        self.updated_at = utc_now_iso()

    def defer(self) -> None:
        """Defer review for later (Ask me later)."""
        self.status = EVIDENCE_STATUS_DEFERRED
        self.updated_at = utc_now_iso()

    def edit(self, new_text: str, *, changed_by: str = "user") -> None:
        """Apply a user edit, preserving the original extracted text.
        Records the edit in edit_history for full auditability."""
        previous = self.edited_text or self.extracted_text
        self.edited_text = new_text
        self.edit_history.append({
            "timestamp": utc_now_iso(),
            "changed_by": changed_by,
            "previous_text": previous,
            "new_text": new_text,
            "char_diff": len(new_text) - len(previous),
        })
        self.updated_at = utc_now_iso()
        if self.status not in (EVIDENCE_STATUS_VERIFIED, EVIDENCE_STATUS_REJECTED):
            self.status = EVIDENCE_STATUS_PENDING

    # ── factory ──────────────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        *,
        profile_id: str,
        source_id: str,
        source_name: str = "",
        field_type: str = EVIDENCE_FIELD_OTHER,
        extracted_text: str = "",
        extraction_reason: str = "",
        extraction_confidence: float = 0.0,
    ) -> "CareerProfileEvidence":
        """Create a new pending evidence item from extracted data."""
        now = utc_now_iso()
        conf = max(0.0, min(1.0, float(extraction_confidence or 0.0)))
        return cls(
            evidence_id=f"ev_{uuid4().hex[:16]}",
            profile_id=str(profile_id).strip(),
            source_id=str(source_id).strip(),
            source_name=str(source_name).strip(),
            field_type=str(field_type).strip() or EVIDENCE_FIELD_OTHER,
            extracted_text=str(extracted_text),
            edited_text="",
            extraction_reason=str(extraction_reason).strip(),
            extraction_confidence=conf,
            status=EVIDENCE_STATUS_PENDING,
            edit_history=[],
            created_at=now,
            updated_at=now,
        )

    # ── serialisation ────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "profile_id": self.profile_id,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "field_type": self.field_type,
            "extracted_text": self.extracted_text,
            "edited_text": self.edited_text,
            "effective_text": self.effective_text,
            "extraction_reason": self.extraction_reason,
            "extraction_confidence": self.extraction_confidence,
            "status": self.status,
            "is_edited": self.is_edited,
            "is_usable": self.is_usable,
            "edit_history": list(self.edit_history),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CareerProfileEvidence":
        return cls(
            evidence_id=str(payload.get("evidence_id") or ""),
            profile_id=str(payload.get("profile_id") or ""),
            source_id=str(payload.get("source_id") or ""),
            source_name=str(payload.get("source_name") or ""),
            field_type=str(payload.get("field_type") or EVIDENCE_FIELD_OTHER),
            extracted_text=str(payload.get("extracted_text") or ""),
            edited_text=str(payload.get("edited_text") or ""),
            extraction_reason=str(payload.get("extraction_reason") or ""),
            extraction_confidence=float(payload.get("extraction_confidence") or 0.0),
            status=str(payload.get("status") or EVIDENCE_STATUS_PENDING),
            edit_history=[
                dict(e) for e in (payload.get("edit_history") or [])
                if isinstance(e, dict)
            ],
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )


__all__ = [
    "EVIDENCE_FIELD_CERTIFICATION",
    "EVIDENCE_FIELD_CONTACT",
    "EVIDENCE_FIELD_EDUCATION",
    "EVIDENCE_FIELD_EXPERIENCE",
    "EVIDENCE_FIELD_LANGUAGE",
    "EVIDENCE_FIELD_OTHER",
    "EVIDENCE_FIELD_PROJECT",
    "EVIDENCE_FIELD_SKILL",
    "EVIDENCE_FIELD_SUMMARY",
    "EVIDENCE_FIELD_TYPES",
    "EVIDENCE_STATUS_DEFERRED",
    "EVIDENCE_STATUS_PENDING",
    "EVIDENCE_STATUS_REJECTED",
    "EVIDENCE_STATUS_VERIFIED",
    "EVIDENCE_STATUSES",
    "CareerProfileEvidence",
]
