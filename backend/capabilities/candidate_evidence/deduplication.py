"""Evidence deduplication (CP-009).

Groups likely duplicate evidence items across sources so reviewers
can merge or discard redundant claims.
"""

from __future__ import annotations

import logging
from hashlib import sha256
from typing import Any
from uuid import uuid4

from backend.domain.candidate_evidence import CandidateEvidence, compute_content_hash

LOGGER = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.75   # Jaccard similarity to consider as duplicate
EXACT_HASH_MATCH = True       # Same content hash = automatic duplicate


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _token_set(text: str) -> set[str]:
    return {w for w in text.lower().replace(".", " ").split() if len(w) > 2}


def find_duplicate_groups(
    evidence_items: list[CandidateEvidence],
    *,
    threshold: float = SIMILARITY_THRESHOLD,
) -> dict[str, list[str]]:
    """Group evidence items by likely duplicates.

    Returns dict of group_id -> list of evidence_ids.
    Items with only one member are NOT placed in a group.
    """
    groups: dict[str, list[str]] = {}
    token_sets: dict[str, set[str]] = {}

    for ev in evidence_items:
        token_sets[ev.evidence_id] = _token_set(ev.text)

    ids = [ev.evidence_id for ev in evidence_items]
    grouped: set[str] = set()

    for i in range(len(ids)):
        if ids[i] in grouped:
            continue
        group: list[str] = [ids[i]]
        for j in range(i + 1, len(ids)):
            if ids[j] in grouped:
                continue

            # Exact hash match = automatic duplicate
            hash_match = (
                evidence_items[i].content_hash == evidence_items[j].content_hash
                if EXACT_HASH_MATCH
                else False
            )

            # Fuzzy match via Jaccard
            sim = _jaccard(token_sets[ids[i]], token_sets[ids[j]])

            if hash_match or sim >= threshold:
                group.append(ids[j])
                grouped.add(ids[j])

        if len(group) > 1:
            group_id = f"dup_{uuid4().hex[:12]}"
            groups[group_id] = group
            grouped.add(ids[i])

    LOGGER.info(
        "Found %d duplicate groups across %d evidence items",
        len(groups),
        len(evidence_items),
    )
    return groups


def apply_duplicate_groups(
    evidence_items: list[CandidateEvidence],
    groups: dict[str, list[str]],
) -> list[CandidateEvidence]:
    """Apply duplicate group assignments to evidence items.

    Returns the modified list (mutates in-place).
    For each group, keeps the longest text as primary and marks others as merged.
    """
    ev_by_id = {ev.evidence_id: ev for ev in evidence_items}

    for group_id, member_ids in groups.items():
        members = [ev_by_id[mid] for mid in member_ids if mid in ev_by_id]
        if not members:
            continue

        # Primary = longest text
        primary = max(members, key=lambda ev: len(ev.text))
        primary.assign_duplicate_group(group_id)

        for member in members:
            if member.evidence_id != primary.evidence_id:
                member.mark_merged(primary.evidence_id)

    return evidence_items


def deduplicate_evidence(
    evidence_items: list[CandidateEvidence],
    *,
    threshold: float = SIMILARITY_THRESHOLD,
) -> dict[str, Any]:
    """Run full deduplication: detect groups and apply assignments.

    Returns a summary dict with group info.
    """
    groups = find_duplicate_groups(evidence_items, threshold=threshold)
    apply_duplicate_groups(evidence_items, groups)

    merged_count = sum(1 for ev in evidence_items if ev.is_merged)
    return {
        "duplicate_groups": len(groups),
        "merged_items": merged_count,
        "groups": {
            gid: [mid for mid in mids]
            for gid, mids in groups.items()
        },
        "evidence": [ev.to_dict() for ev in evidence_items],
    }
