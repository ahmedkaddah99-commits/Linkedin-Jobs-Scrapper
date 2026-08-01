from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


PREPARATION_STATE_CREATED = "created"
PREPARATION_STATE_PERMISSION_REQUIRED = "permission_required"
PREPARATION_STATE_PREPARING = "preparing"
PREPARATION_STATE_NEEDS_ATTENTION = "needs_attention"
PREPARATION_STATE_READY_FOR_REVIEW = "ready_for_review"
PREPARATION_STATE_ACTIVE = "active"
PREPARATION_STATE_CANCELLED = "cancelled"
PREPARATION_STATE_EXPIRED = "expired"

PREPARATION_STATES = {
    PREPARATION_STATE_CREATED,
    PREPARATION_STATE_PERMISSION_REQUIRED,
    PREPARATION_STATE_PREPARING,
    PREPARATION_STATE_NEEDS_ATTENTION,
    PREPARATION_STATE_READY_FOR_REVIEW,
    PREPARATION_STATE_ACTIVE,
    PREPARATION_STATE_CANCELLED,
    PREPARATION_STATE_EXPIRED,
}

PREPARATION_REPORT_TYPES = {
    "permission_required",
    "accepted",
    "rejected",
    "progress",
    "needs_attention",
    "ready_for_review",
}
PREPARATION_ACTIONS = {"activate", "cancel", "retry"}
PREPARATION_ERROR_CATEGORIES = {
    "",
    "permission_required",
    "permission_denied",
    "unsupported_ats",
    "field_unavailable",
    "document_unavailable",
    "validation_failed",
    "navigation_blocked",
    "extension_unavailable",
    "expired",
    "unknown",
}


class PreparationStateError(ValueError):
    pass


class PreparationAuthorizationError(PermissionError):
    pass


class PreparationFeatureDisabledError(RuntimeError):
    pass


@dataclass(slots=True)
class AssistedApplyPreparation:
    preparation_id: str
    user_id: str
    package_id: str
    job_id: str
    ats: str
    application_url: str
    state: str
    total_count: int
    completed_count: int
    error_category: str
    attempt_count: int
    session_id: str
    created_at: str
    updated_at: str
    expires_at: str
    started_at: str = ""
    ready_at: str = ""
    attention_at: str = ""
    cancelled_at: str = ""
    expired_at: str = ""
    last_report_id: str = ""

    def __post_init__(self) -> None:
        if self.state not in PREPARATION_STATES:
            raise ValueError(f"Unsupported preparation state: {self.state}")
        if self.error_category not in PREPARATION_ERROR_CATEGORIES:
            raise ValueError(f"Unsupported preparation error category: {self.error_category}")
        if min(self.total_count, self.completed_count, self.attempt_count) < 0:
            raise ValueError("Preparation counts cannot be negative.")
        if self.completed_count > self.total_count and self.total_count > 0:
            raise ValueError("Completed count cannot exceed total count.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AssistedApplyPreparation":
        return cls(
            preparation_id=str(payload.get("preparation_id") or ""),
            user_id=str(payload.get("user_id") or ""),
            package_id=str(payload.get("package_id") or ""),
            job_id=str(payload.get("job_id") or ""),
            ats=str(payload.get("ats") or ""),
            application_url=str(payload.get("application_url") or ""),
            state=str(payload.get("state") or PREPARATION_STATE_CREATED),
            total_count=int(payload.get("total_count") or 0),
            completed_count=int(payload.get("completed_count") or 0),
            error_category=str(payload.get("error_category") or ""),
            attempt_count=max(1, int(payload.get("attempt_count") or 1)),
            session_id=str(payload.get("session_id") or ""),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            expires_at=str(payload.get("expires_at") or ""),
            started_at=str(payload.get("started_at") or ""),
            ready_at=str(payload.get("ready_at") or ""),
            attention_at=str(payload.get("attention_at") or ""),
            cancelled_at=str(payload.get("cancelled_at") or ""),
            expired_at=str(payload.get("expired_at") or ""),
            last_report_id=str(payload.get("last_report_id") or ""),
        )


def transition_for_report(state: str, report_type: str) -> str:
    if report_type not in PREPARATION_REPORT_TYPES:
        raise PreparationStateError("Unsupported preparation report type.")
    allowed = {
        PREPARATION_STATE_CREATED: {"permission_required", "accepted", "rejected", "needs_attention"},
        PREPARATION_STATE_PERMISSION_REQUIRED: {"accepted", "rejected", "permission_required"},
        PREPARATION_STATE_PREPARING: {"progress", "needs_attention", "ready_for_review"},
        PREPARATION_STATE_NEEDS_ATTENTION: set(),
        PREPARATION_STATE_READY_FOR_REVIEW: set(),
        PREPARATION_STATE_ACTIVE: set(),
        PREPARATION_STATE_CANCELLED: set(),
        PREPARATION_STATE_EXPIRED: set(),
    }
    if report_type not in allowed.get(state, set()):
        raise PreparationStateError(f"Report '{report_type}' is invalid from state '{state}'.")
    return {
        "permission_required": PREPARATION_STATE_PERMISSION_REQUIRED,
        "accepted": PREPARATION_STATE_PREPARING,
        "rejected": PREPARATION_STATE_NEEDS_ATTENTION,
        "progress": PREPARATION_STATE_PREPARING,
        "needs_attention": PREPARATION_STATE_NEEDS_ATTENTION,
        "ready_for_review": PREPARATION_STATE_READY_FOR_REVIEW,
    }[report_type]


def transition_for_action(state: str, action: str) -> str:
    if action not in PREPARATION_ACTIONS:
        raise PreparationStateError("Unsupported preparation action.")
    if action == "activate" and state == PREPARATION_STATE_READY_FOR_REVIEW:
        return PREPARATION_STATE_ACTIVE
    if action == "cancel" and state not in {
        PREPARATION_STATE_ACTIVE, PREPARATION_STATE_CANCELLED, PREPARATION_STATE_EXPIRED,
    }:
        return PREPARATION_STATE_CANCELLED
    if action == "retry" and state in {PREPARATION_STATE_PERMISSION_REQUIRED, PREPARATION_STATE_NEEDS_ATTENTION, PREPARATION_STATE_EXPIRED}:
        return PREPARATION_STATE_CREATED
    raise PreparationStateError(f"Action '{action}' is invalid from state '{state}'.")
