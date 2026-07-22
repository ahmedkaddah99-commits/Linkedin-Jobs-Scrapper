"""Career Profile Evidence service (CP-010).

Manages the lifecycle of extracted evidence items: verify, edit, reject, defer.
Rejected evidence is excluded from generated material.
Original source content and user edits are always preserved.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from backend.domain.career_profile_evidence import (
    EVIDENCE_STATUS_DEFERRED,
    EVIDENCE_STATUS_PENDING,
    EVIDENCE_STATUS_REJECTED,
    EVIDENCE_STATUS_VERIFIED,
    CareerProfileEvidence,
)

LOGGER = logging.getLogger(__name__)

# In-memory store keyed by "{profile_id}:{evidence_id}"
_evidence_store: dict[str, CareerProfileEvidence] = {}


def _store_key(profile_id: str, evidence_id: str) -> str:
    return f"{profile_id}:{evidence_id}"


def get_evidence(profile_id: str, evidence_id: str) -> CareerProfileEvidence | None:
    """Return a single evidence item, or None."""
    return _evidence_store.get(_store_key(profile_id, evidence_id))


def create_evidence(
    *,
    profile_id: str,
    source_id: str,
    source_name: str = "",
    field_type: str = "",
    extracted_text: str = "",
    extraction_reason: str = "",
    extraction_confidence: float = 0.0,
) -> CareerProfileEvidence:
    """Create a new pending evidence item."""
    evidence = CareerProfileEvidence.create(
        profile_id=profile_id,
        source_id=source_id,
        source_name=source_name,
        field_type=field_type,
        extracted_text=extracted_text,
        extraction_reason=extraction_reason,
        extraction_confidence=extraction_confidence,
    )
    _evidence_store[_store_key(profile_id, evidence.evidence_id)] = evidence
    return evidence


def list_evidence(
    profile_id: str,
    *,
    status: str | None = None,
) -> list[CareerProfileEvidence]:
    """Return all evidence items for a profile, optionally filtered by status."""
    prefix = f"{profile_id}:"
    results = [e for k, e in _evidence_store.items() if k.startswith(prefix)]
    if status:
        results = [e for e in results if e.status == status]
    return results


def verify_evidence(profile_id: str, evidence_id: str) -> CareerProfileEvidence | None:
    """Mark evidence as verified. Returns updated item or None."""
    evidence = get_evidence(profile_id, evidence_id)
    if evidence is None:
        return None
    evidence.verify()
    return evidence


def reject_evidence(profile_id: str, evidence_id: str) -> CareerProfileEvidence | None:
    """Reject evidence so it is excluded from generated material."""
    evidence = get_evidence(profile_id, evidence_id)
    if evidence is None:
        return None
    evidence.reject()
    return evidence


def defer_evidence(profile_id: str, evidence_id: str) -> CareerProfileEvidence | None:
    """Defer evidence review (Ask me later)."""
    evidence = get_evidence(profile_id, evidence_id)
    if evidence is None:
        return None
    evidence.defer()
    return evidence


def edit_evidence(
    profile_id: str,
    evidence_id: str,
    new_text: str,
    *,
    changed_by: str = "user",
) -> CareerProfileEvidence | None:
    """Apply a user edit to the evidence text. Returns updated item or None."""
    evidence = get_evidence(profile_id, evidence_id)
    if evidence is None:
        return None
    evidence.edit(new_text, changed_by=changed_by)
    return evidence


def get_verified_evidence(profile_id: str) -> list[CareerProfileEvidence]:
    """Return all verified evidence ready for use in generated material."""
    return list_evidence(profile_id, status=EVIDENCE_STATUS_VERIFIED)


def count_evidence_by_status(profile_id: str) -> dict[str, int]:
    """Return counts of evidence items by status."""
    all_evidence = list_evidence(profile_id)
    counts: dict[str, int] = {
        EVIDENCE_STATUS_PENDING: 0,
        EVIDENCE_STATUS_VERIFIED: 0,
        EVIDENCE_STATUS_REJECTED: 0,
        EVIDENCE_STATUS_DEFERRED: 0,
    }
    for e in all_evidence:
        counts[e.status] = counts.get(e.status, 0) + 1
    return counts
