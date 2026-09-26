"""Evidence state model for CP-028: Make every evidence state visible.

Defines the unified evidence lifecycle: Draft -> Processing -> Needs review
-> Verified / Rejected -> Ready for tailoring -> Archived.

Every state carries an action-needed explanation so users always know what to do next.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import uuid4

from backend.domain.models import utc_now_iso


# ---------------------------------------------------------------------------
# Evidence state constants
# ---------------------------------------------------------------------------

EVIDENCE_STATE_DRAFT = "draft"
EVIDENCE_STATE_PROCESSING = "processing"
EVIDENCE_STATE_NEEDS_REVIEW = "needs_review"
EVIDENCE_STATE_VERIFIED = "verified"
EVIDENCE_STATE_REJECTED = "rejected"
EVIDENCE_STATE_READY_FOR_TAILORING = "ready_for_tailoring"
EVIDENCE_STATE_ARCHIVED = "archived"

EVIDENCE_STATES = {
    EVIDENCE_STATE_DRAFT,
    EVIDENCE_STATE_PROCESSING,
    EVIDENCE_STATE_NEEDS_REVIEW,
    EVIDENCE_STATE_VERIFIED,
    EVIDENCE_STATE_REJECTED,
    EVIDENCE_STATE_READY_FOR_TAILORING,
    EVIDENCE_STATE_ARCHIVED,
}

# Ordered lifecycle for display / timeline
EVIDENCE_STATE_ORDER = [
    EVIDENCE_STATE_DRAFT,
    EVIDENCE_STATE_PROCESSING,
    EVIDENCE_STATE_NEEDS_REVIEW,
    EVIDENCE_STATE_VERIFIED,
    EVIDENCE_STATE_REJECTED,
    EVIDENCE_STATE_READY_FOR_TAILORING,
    EVIDENCE_STATE_ARCHIVED,
]

# ---------------------------------------------------------------------------
# Action-needed explanations per state
# ---------------------------------------------------------------------------

EVIDENCE_ACTION_NEEDED: dict[str, str] = {
    EVIDENCE_STATE_DRAFT: (
        "This item has been saved but not yet submitted for processing. "
        "Click 'Start Processing' to begin extraction."
    ),
    EVIDENCE_STATE_PROCESSING: (
        "The system is currently extracting and analyzing this evidence. "
        "No action is needed - wait for processing to complete."
    ),
    EVIDENCE_STATE_NEEDS_REVIEW: (
        "Processing is complete but the results require human verification. "
        "Review the extracted data and either verify or reject."
    ),
    EVIDENCE_STATE_VERIFIED: (
        "This evidence has been verified and is accurate. "
        "It is ready for use in tailoring - no further action needed."
    ),
    EVIDENCE_STATE_REJECTED: (
        "This evidence was reviewed and rejected. "
        "You can re-submit for processing or archive it."
    ),
    EVIDENCE_STATE_READY_FOR_TAILORING: (
        "The evidence is structured and ready to be used for generating "
        "tailored documents. Proceed to generate output."
    ),
    EVIDENCE_STATE_ARCHIVED: (
        "This evidence has been archived and is no longer active. "
        "It is preserved for audit but will not appear in active workflows."
    ),
}

# ---------------------------------------------------------------------------
# Valid transitions (state machine)
# ---------------------------------------------------------------------------

EVIDENCE_TRANSITIONS: dict[str, set[str]] = {
    EVIDENCE_STATE_DRAFT: {EVIDENCE_STATE_PROCESSING, EVIDENCE_STATE_ARCHIVED},
    EVIDENCE_STATE_PROCESSING: {EVIDENCE_STATE_NEEDS_REVIEW, EVIDENCE_STATE_REJECTED},
    EVIDENCE_STATE_NEEDS_REVIEW: {EVIDENCE_STATE_VERIFIED, EVIDENCE_STATE_REJECTED, EVIDENCE_STATE_DRAFT},
    EVIDENCE_STATE_VERIFIED: {EVIDENCE_STATE_READY_FOR_TAILORING, EVIDENCE_STATE_ARCHIVED, EVIDENCE_STATE_NEEDS_REVIEW},
    EVIDENCE_STATE_REJECTED: {EVIDENCE_STATE_DRAFT, EVIDENCE_STATE_ARCHIVED},
    EVIDENCE_STATE_READY_FOR_TAILORING: {EVIDENCE_STATE_ARCHIVED, EVIDENCE_STATE_NEEDS_REVIEW},
    EVIDENCE_STATE_ARCHIVED: {EVIDENCE_STATE_DRAFT},
}

# ---------------------------------------------------------------------------
# Evidence entity kinds
# ---------------------------------------------------------------------------

EVIDENCE_KIND_SOURCE = "source"
EVIDENCE_KIND_EVIDENCE = "evidence"
EVIDENCE_KIND_TIMELINE_MAPPING = "timeline_mapping"
EVIDENCE_KIND_GENERATED_OUTPUT = "generated_output"

EVIDENCE_KINDS = {
    EVIDENCE_KIND_SOURCE,
    EVIDENCE_KIND_EVIDENCE,
    EVIDENCE_KIND_TIMELINE_MAPPING,
    EVIDENCE_KIND_GENERATED_OUTPUT,
}


# ---------------------------------------------------------------------------
# EvidenceRecord
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class EvidenceRecord:
    """A traceable piece of evidence that moves through the 7-state lifecycle."""

    evidence_id: str
    workspace_id: str
    run_id: str = ""
    kind: str = EVIDENCE_KIND_EVIDENCE
    state: str = EVIDENCE_STATE_DRAFT
    label: str = ""
    description: str = ""
    source_ref: str = ""
    source_type: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        workspace_id: str,
        run_id: str = "",
        kind: str = EVIDENCE_KIND_EVIDENCE,
        state: str = EVIDENCE_STATE_DRAFT,
        label: str = "",
        description: str = "",
        source_ref: str = "",
        source_type: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> "EvidenceRecord":
        now = utc_now_iso()
        return cls(
            evidence_id=f"ev_{uuid4().hex[:16]}",
            workspace_id=str(workspace_id).strip(),
            run_id=str(run_id).strip(),
            kind=str(kind or EVIDENCE_KIND_EVIDENCE).strip(),
            state=str(state or EVIDENCE_STATE_DRAFT).strip(),
            label=str(label).strip(),
            description=str(description).strip(),
            source_ref=str(source_ref).strip(),
            source_type=str(source_type).strip(),
            created_at=now,
            updated_at=now,
            metadata=dict(metadata or {}),
        )

    @property
    def action_needed(self) -> str:
        return EVIDENCE_ACTION_NEEDED.get(self.state, "")

    def can_transition_to(self, target_state: str) -> bool:
        allowed = EVIDENCE_TRANSITIONS.get(self.state, set())
        return target_state in allowed

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "workspace_id": self.workspace_id,
            "run_id": self.run_id,
            "kind": self.kind,
            "state": self.state,
            "label": self.label,
            "description": self.description,
            "source_ref": self.source_ref,
            "source_type": self.source_type,
            "action_needed": self.action_needed,
            "available_transitions": sorted(EVIDENCE_TRANSITIONS.get(self.state, set())),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceRecord":
        return cls(
            evidence_id=str(payload.get("evidence_id") or ""),
            workspace_id=str(payload.get("workspace_id") or ""),
            run_id=str(payload.get("run_id") or ""),
            kind=str(payload.get("kind") or EVIDENCE_KIND_EVIDENCE),
            state=str(payload.get("state") or EVIDENCE_STATE_DRAFT),
            label=str(payload.get("label") or ""),
            description=str(payload.get("description") or ""),
            source_ref=str(payload.get("source_ref") or ""),
            source_type=str(payload.get("source_type") or ""),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
            metadata=dict(payload.get("metadata") or {}),
        )



# ---------------------------------------------------------------------------
# EvidenceStateHistory -- preserves timestamps and state transitions
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class EvidenceStateHistory:
    """Immutable record of a single state transition."""

    history_id: str
    evidence_id: str
    from_state: str
    to_state: str
    reason: str = ""
    actor: str = ""
    occurred_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        evidence_id: str,
        from_state: str,
        to_state: str,
        reason: str = "",
        actor: str = "",
    ) -> "EvidenceStateHistory":
        return cls(
            history_id=f"evhist_{uuid4().hex[:16]}",
            evidence_id=str(evidence_id).strip(),
            from_state=str(from_state).strip(),
            to_state=str(to_state).strip(),
            reason=str(reason).strip(),
            actor=str(actor).strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "history_id": self.history_id,
            "evidence_id": self.evidence_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
            "actor": self.actor,
            "occurred_at": self.occurred_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceStateHistory":
        return cls(
            history_id=str(payload.get("history_id") or ""),
            evidence_id=str(payload.get("evidence_id") or ""),
            from_state=str(payload.get("from_state") or ""),
            to_state=str(payload.get("to_state") or ""),
            reason=str(payload.get("reason") or ""),
            actor=str(payload.get("actor") or ""),
            occurred_at=str(payload.get("occurred_at") or utc_now_iso()),
        )
