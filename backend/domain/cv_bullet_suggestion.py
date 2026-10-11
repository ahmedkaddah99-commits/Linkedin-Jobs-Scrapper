"""Domain model for CV bullet suggestions from verified evidence (CP-036R).

Generates role-specific CV bullet suggestions from baseline CV, job description,
and selected verified canonical evidence with persistent provenance and review
actions (Accept, Edit, Reject, Replace).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import uuid4

from backend.domain.models import utc_now_iso

# ---------------------------------------------------------------------------
# Suggestion status constants
# ---------------------------------------------------------------------------

BULLET_SUGGESTION_STATUS_PENDING = "pending"
BULLET_SUGGESTION_STATUS_ACCEPTED = "accepted"
BULLET_SUGGESTION_STATUS_EDITED = "edited"
BULLET_SUGGESTION_STATUS_REJECTED = "rejected"
BULLET_SUGGESTION_STATUS_REPLACED = "replaced"

BULLET_SUGGESTION_STATUSES = {
    BULLET_SUGGESTION_STATUS_PENDING,
    BULLET_SUGGESTION_STATUS_ACCEPTED,
    BULLET_SUGGESTION_STATUS_EDITED,
    BULLET_SUGGESTION_STATUS_REJECTED,
    BULLET_SUGGESTION_STATUS_REPLACED,
}

# Valid allowed status transitions
BULLET_SUGGESTION_TRANSITIONS: dict[str, set[str]] = {
    BULLET_SUGGESTION_STATUS_PENDING: {
        BULLET_SUGGESTION_STATUS_ACCEPTED,
        BULLET_SUGGESTION_STATUS_EDITED,
        BULLET_SUGGESTION_STATUS_REJECTED,
        BULLET_SUGGESTION_STATUS_REPLACED,
    },
    BULLET_SUGGESTION_STATUS_ACCEPTED: {
        BULLET_SUGGESTION_STATUS_EDITED,
        BULLET_SUGGESTION_STATUS_REJECTED,
        BULLET_SUGGESTION_STATUS_REPLACED,
    },
    BULLET_SUGGESTION_STATUS_EDITED: {
        BULLET_SUGGESTION_STATUS_ACCEPTED,
        BULLET_SUGGESTION_STATUS_REJECTED,
        BULLET_SUGGESTION_STATUS_REPLACED,
    },
    BULLET_SUGGESTION_STATUS_REJECTED: {
        BULLET_SUGGESTION_STATUS_ACCEPTED,
        BULLET_SUGGESTION_STATUS_EDITED,
        BULLET_SUGGESTION_STATUS_REPLACED,
    },
    BULLET_SUGGESTION_STATUS_REPLACED: {
        BULLET_SUGGESTION_STATUS_ACCEPTED,
        BULLET_SUGGESTION_STATUS_EDITED,
        BULLET_SUGGESTION_STATUS_REJECTED,
    },
}

# ---------------------------------------------------------------------------
# Action constants
# ---------------------------------------------------------------------------

BULLET_SUGGESTION_ACTION_ACCEPT = "accept"
BULLET_SUGGESTION_ACTION_EDIT = "edit"
BULLET_SUGGESTION_ACTION_REJECT = "reject"
BULLET_SUGGESTION_ACTION_REPLACE = "replace"

BULLET_SUGGESTION_ACTIONS = {
    BULLET_SUGGESTION_ACTION_ACCEPT,
    BULLET_SUGGESTION_ACTION_EDIT,
    BULLET_SUGGESTION_ACTION_REJECT,
    BULLET_SUGGESTION_ACTION_REPLACE,
}

# Supported edit fields for validated edits
SUPPORTED_EDIT_FIELDS = {"bullet_text", "linked_experience_id", "label"}



# ---------------------------------------------------------------------------
# CVBulletSuggestion
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CVBulletSuggestion:
    """A role-specific CV bullet suggestion generated from selected verified evidence.

    Every suggestion carries full provenance:
      - evidence_ids: the verified canonical evidence items used
      - source_ids: the original source asset IDs
      - baseline_cv_version: the baseline CV version at generation time
      - target_job_id / target_job_description: the target job context

    Supports review actions: Accept, Edit, Reject, Replace.
    Accepted bullets retain provenance in output history.
    Edit history preserves full audit trail.
    """

    suggestion_id: str
    profile_id: str = ""

    # Target context
    target_job_id: str = ""
    target_job_title: str = ""
    target_job_description: str = ""

    # Provenance
    baseline_cv_version: str = ""
    baseline_cv_asset_id: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)

    # Bullet content
    bullet_text: str = ""
    suggested_bullet_text: str = ""
    linked_experience_id: str = ""
    label: str = ""

    # Lifecycle
    status: str = BULLET_SUGGESTION_STATUS_PENDING

    # Audit
    edit_history: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_pending(self) -> bool:
        return self.status == BULLET_SUGGESTION_STATUS_PENDING

    @property
    def is_accepted(self) -> bool:
        return self.status == BULLET_SUGGESTION_STATUS_ACCEPTED

    @property
    def is_edited(self) -> bool:
        return self.status == BULLET_SUGGESTION_STATUS_EDITED

    @property
    def is_rejected(self) -> bool:
        return self.status == BULLET_SUGGESTION_STATUS_REJECTED

    @property
    def is_replaced(self) -> bool:
        return self.status == BULLET_SUGGESTION_STATUS_REPLACED

    @property
    def effective_text(self) -> str:
        """Return the current effective bullet text."""
        return self.bullet_text or self.suggested_bullet_text

    @property
    def has_been_edited(self) -> bool:
        """True when the user has modified the bullet text."""
        return bool(self.edit_history)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def can_transition_to(self, target_status: str) -> bool:
        allowed = BULLET_SUGGESTION_TRANSITIONS.get(self.status, set())
        return target_status in allowed

    def accept(self) -> None:
        """Accept the suggestion as-is. Provenance is retained."""
        self.status = BULLET_SUGGESTION_STATUS_ACCEPTED
        self.updated_at = utc_now_iso()

    def edit(self, new_text: str, *, changed_by: str = "user") -> None:
        """Apply a user edit, preserving original text and audit trail."""
        previous = self.bullet_text or self.suggested_bullet_text
        self.bullet_text = new_text
        self.status = BULLET_SUGGESTION_STATUS_EDITED
        self.edit_history.append({
            "timestamp": utc_now_iso(),
            "changed_by": changed_by,
            "previous_text": previous,
            "new_text": new_text,
            "char_diff": len(new_text) - len(previous),
        })
        self.updated_at = utc_now_iso()

    def reject(self) -> None:
        """Reject the suggestion. Provenance and original text preserved."""
        self.status = BULLET_SUGGESTION_STATUS_REJECTED
        self.updated_at = utc_now_iso()

    def replace(self, new_text: str, *, changed_by: str = "user") -> None:
        """Replace the suggestion with a completely different bullet."""
        previous = self.bullet_text or self.suggested_bullet_text
        self.bullet_text = new_text
        self.status = BULLET_SUGGESTION_STATUS_REPLACED
        self.edit_history.append({
            "timestamp": utc_now_iso(),
            "changed_by": changed_by,
            "previous_text": previous,
            "new_text": new_text,
            "char_diff": len(new_text) - len(previous),
            "action": "replace",
        })
        self.updated_at = utc_now_iso()


    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        profile_id: str,
        target_job_id: str = "",
        target_job_title: str = "",
        target_job_description: str = "",
        baseline_cv_version: str = "",
        baseline_cv_asset_id: str = "",
        evidence_ids: list[str] | None = None,
        source_ids: list[str] | None = None,
        bullet_text: str = "",
        linked_experience_id: str = "",
        label: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> "CVBulletSuggestion":
        now = utc_now_iso()
        return cls(
            suggestion_id=f"cvsug_{uuid4().hex[:16]}",
            profile_id=str(profile_id).strip(),
            target_job_id=str(target_job_id).strip(),
            target_job_title=str(target_job_title).strip(),
            target_job_description=str(target_job_description).strip(),
            baseline_cv_version=str(baseline_cv_version).strip(),
            baseline_cv_asset_id=str(baseline_cv_asset_id).strip(),
            evidence_ids=[str(e).strip() for e in (evidence_ids or []) if str(e).strip()],
            source_ids=[str(s).strip() for s in (source_ids or []) if str(s).strip()],
            bullet_text=str(bullet_text).strip(),
            suggested_bullet_text=str(bullet_text).strip(),
            linked_experience_id=str(linked_experience_id).strip(),
            label=str(label).strip(),
            status=BULLET_SUGGESTION_STATUS_PENDING,
            edit_history=[],
            created_at=now,
            updated_at=now,
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggestion_id": self.suggestion_id,
            "profile_id": self.profile_id,
            "target_job_id": self.target_job_id,
            "target_job_title": self.target_job_title,
            "target_job_description": self.target_job_description,
            "baseline_cv_version": self.baseline_cv_version,
            "baseline_cv_asset_id": self.baseline_cv_asset_id,
            "evidence_ids": list(self.evidence_ids),
            "source_ids": list(self.source_ids),
            "bullet_text": self.bullet_text,
            "suggested_bullet_text": self.suggested_bullet_text,
            "effective_text": self.effective_text,
            "linked_experience_id": self.linked_experience_id,
            "label": self.label,
            "status": self.status,
            "is_pending": self.is_pending,
            "is_accepted": self.is_accepted,
            "is_edited": self.is_edited,
            "is_rejected": self.is_rejected,
            "is_replaced": self.is_replaced,
            "has_been_edited": self.has_been_edited,
            "edit_history": list(self.edit_history),
            "available_actions": sorted(
                BULLET_SUGGESTION_TRANSITIONS.get(self.status, set())
            ),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }


    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CVBulletSuggestion":
        return cls(
            suggestion_id=str(payload.get("suggestion_id") or ""),
            profile_id=str(payload.get("profile_id") or ""),
            target_job_id=str(payload.get("target_job_id") or ""),
            target_job_title=str(payload.get("target_job_title") or ""),
            target_job_description=str(payload.get("target_job_description") or ""),
            baseline_cv_version=str(payload.get("baseline_cv_version") or ""),
            baseline_cv_asset_id=str(payload.get("baseline_cv_asset_id") or ""),
            evidence_ids=[
                str(e).strip()
                for e in (payload.get("evidence_ids") or [])
                if str(e).strip()
            ],
            source_ids=[
                str(s).strip()
                for s in (payload.get("source_ids") or [])
                if str(s).strip()
            ],
            bullet_text=str(payload.get("bullet_text") or ""),
            suggested_bullet_text=str(payload.get("suggested_bullet_text") or ""),
            linked_experience_id=str(payload.get("linked_experience_id") or ""),
            label=str(payload.get("label") or ""),
            status=str(payload.get("status") or BULLET_SUGGESTION_STATUS_PENDING),
            edit_history=[
                dict(e) for e in (payload.get("edit_history") or [])
                if isinstance(e, dict)
            ],
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
            metadata=dict(payload.get("metadata") or {}),
        )


__all__ = [
    "BULLET_SUGGESTION_ACTION_ACCEPT",
    "BULLET_SUGGESTION_ACTION_EDIT",
    "BULLET_SUGGESTION_ACTION_REJECT",
    "BULLET_SUGGESTION_ACTION_REPLACE",
    "BULLET_SUGGESTION_ACTIONS",
    "BULLET_SUGGESTION_STATUS_ACCEPTED",
    "BULLET_SUGGESTION_STATUS_EDITED",
    "BULLET_SUGGESTION_STATUS_PENDING",
    "BULLET_SUGGESTION_STATUS_REJECTED",
    "BULLET_SUGGESTION_STATUS_REPLACED",
    "BULLET_SUGGESTION_STATUSES",
    "BULLET_SUGGESTION_TRANSITIONS",
    "CVBulletSuggestion",
    "SUPPORTED_EDIT_FIELDS",
]

