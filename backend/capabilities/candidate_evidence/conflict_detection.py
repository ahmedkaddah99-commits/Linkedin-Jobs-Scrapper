"""Evidence conflict detection (CP-009).

Surfaces conflicting evidence items for review — for example,
different dates, employers, or contradictory metrics for the same
or similar claims.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from backend.domain.candidate_evidence import (
    CandidateEvidence,
    EVIDENCE_STATUS_NEEDS_REVIEW,
    EVIDENCE_STATUS_REJECTED,
    EVIDENCE_STATUS_MERGED,
)

LOGGER = logging.getLogger(__name__)

_NUMBER_RE = re.compile(r"(\d+(?:[.,]\d+)?)")
_DATE_RE = re.compile(r"\b(20\d{2})\b")


def _extract_numbers(text: str) -> set[str]:
    return {m.group(1) for m in _NUMBER_RE.finditer(text)}


def _extract_years(text: str) -> set[str]:
    return {m.group(1) for m in _DATE_RE.finditer(text)}


def _numeric_conflict(a_text: str, b_text: str) -> bool:
    """Two metric-type texts conflict if they have different numbers
    referring to the same domain."""
    nums_a = _extract_numbers(a_text)
    nums_b = _extract_numbers(b_text)
    if not nums_a or not nums_b:
        return False
    # If they share no numbers, they may conflict (talking about same thing differently)
    return not bool(nums_a & nums_b)


def _date_conflict(a_dates: list[str], b_dates: list[str]) -> bool:
    """Two evidence items conflict if their dates don't overlap."""
    years_a = set()
    years_b = set()
    for d in a_dates:
        years_a.update(_extract_years(d))
    for d in b_dates:
        years_b.update(_extract_years(d))
    if not years_a or not years_b:
        return False
    # No overlapping years = potential conflict
    return not bool(years_a & years_b)


def _employer_conflict(a_emp: str, b_emp: str) -> bool:
    """Conflict if both have different non-empty employers."""
    return bool(a_emp and b_emp and a_emp.lower() != b_emp.lower())


def detect_conflicts(
    evidence_items: list[CandidateEvidence],
) -> dict[str, list[str]]:
    """Detect conflicting evidence among active items.

    Returns dict mapping evidence_id -> list of conflicting evidence_ids.
    Only considers items that are needs_review or confirmed (not merged/rejected).
    """
    active = [
        ev for ev in evidence_items
        if ev.status not in (EVIDENCE_STATUS_REJECTED, EVIDENCE_STATUS_MERGED)
    ]
    conflicts: dict[str, list[str]] = {}

    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            a, b = active[i], active[j]

            # Only compare same evidence types
            if a.evidence_type != b.evidence_type:
                continue

            # Detect numeric conflicts for metrics
            if a.evidence_type == "metric" and _numeric_conflict(a.text, b.text):
                conflicts.setdefault(a.evidence_id, []).append(b.evidence_id)
                conflicts.setdefault(b.evidence_id, []).append(a.evidence_id)

            # Detect employer conflicts
            if _employer_conflict(a.inferred_employer, b.inferred_employer):
                conflicts.setdefault(a.evidence_id, []).append(b.evidence_id)
                conflicts.setdefault(b.evidence_id, []).append(a.evidence_id)

            # Detect date conflicts
            if _date_conflict(a.dates, b.dates):
                conflicts.setdefault(a.evidence_id, []).append(b.evidence_id)
                conflicts.setdefault(b.evidence_id, []).append(a.evidence_id)

    LOGGER.info("Detected %d evidence items with conflicts", len(conflicts))
    return conflicts


def apply_conflicts(
    evidence_items: list[CandidateEvidence],
    conflicts: dict[str, list[str]],
) -> list[CandidateEvidence]:
    """Apply conflict flags to evidence items."""
    ev_by_id = {ev.evidence_id: ev for ev in evidence_items}
    for ev_id, conflicting_ids in conflicts.items():
        ev = ev_by_id.get(ev_id)
        if ev is None:
            continue
        resolved = [cid for cid in conflicting_ids if cid in ev_by_id]
        if resolved:
            ev.mark_conflict(resolved)
    return evidence_items


def detect_and_apply_conflicts(
    evidence_items: list[CandidateEvidence],
) -> dict[str, Any]:
    """Run conflict detection and apply flags.

    Returns a summary dict with conflict info.
    """
    conflicts = detect_conflicts(evidence_items)
    apply_conflicts(evidence_items, conflicts)

    conflict_count = sum(1 for ev in evidence_items if ev.is_conflicting)
    return {
        "conflict_items": conflict_count,
        "conflicts": {
            eid: [cid for cid in cids]
            for eid, cids in conflicts.items()
        },
        "evidence": [ev.to_dict() for ev in evidence_items],
    }
