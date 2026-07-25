"""Candidate evidence extraction capability (CP-009).

Converts reviewed source texts into traceable candidate evidence items
with full provenance, then runs deduplication and conflict detection.

Public API:
    extract_evidence_from_verified_sources  → extract evidence from reviewed texts
    deduplicate_evidence                     → group likely duplicates
    detect_and_apply_conflicts               → surface conflicting evidence
    build_evidence_summary                   → summarize evidence state

    run_evidence_pipeline                    → end-to-end: extract + dedupe + conflict
"""

from backend.capabilities.candidate_evidence.extraction import (
    build_evidence_summary,
    extract_evidence_from_source,
    extract_evidence_from_verified_sources,
)
from backend.capabilities.candidate_evidence.deduplication import (
    deduplicate_evidence,
    find_duplicate_groups,
    apply_duplicate_groups,
)
from backend.capabilities.candidate_evidence.conflict_detection import (
    detect_and_apply_conflicts,
    detect_conflicts,
    apply_conflicts,
)
from backend.capabilities.candidate_evidence.generation import (
    generate_evidence_outputs,
    get_confirmed_evidence,
    regenerate_evidence_output,
)
from backend.capabilities.candidate_evidence.migration import (
    clear_legacy_career_memory,
    has_legacy_career_memory,
    migrate_and_deduplicate,
    migrate_legacy_facts_to_evidence,
)

from backend.domain.candidate_evidence import CandidateEvidence

from typing import Any


def run_evidence_pipeline(
    profile_id: str,
    verified_texts: list[dict[str, Any]],
    *,
    dedupe_threshold: float = 0.75,
) -> dict[str, Any]:
    """Run the full evidence extraction pipeline: extract → deduplicate → detect conflicts.

    Args:
        profile_id: The career profile ID.
        verified_texts: Output from source_text_review.get_verified_texts().
        dedupe_threshold: Jaccard similarity threshold for duplicates (0.0-1.0).

    Returns:
        Dict with extraction, deduplication, and conflict summaries, plus full evidence list.
    """
    evidence = extract_evidence_from_verified_sources(profile_id, verified_texts)
    extraction_summary = build_evidence_summary(evidence)

    dedupe_summary = deduplicate_evidence(evidence, threshold=dedupe_threshold)

    # Re-run conflict detection on non-merged items only
    active = [ev for ev in evidence if not ev.is_merged]
    conflict_summary = detect_and_apply_conflicts(active)

    return {
        "profile_id": profile_id,
        "extraction": {
            "total_evidence": extraction_summary["total_evidence"],
            "by_type": extraction_summary["by_type"],
        },
        "deduplication": {
            "duplicate_groups": dedupe_summary["duplicate_groups"],
            "merged_items": dedupe_summary["merged_items"],
        },
        "conflicts": {
            "conflict_items": conflict_summary["conflict_items"],
        },
        "evidence": [ev.to_dict() for ev in evidence],
    }


__all__ = [
    "CandidateEvidence",
    "apply_conflicts",
    "apply_duplicate_groups",
    "build_evidence_summary",
    "clear_legacy_career_memory",
    "deduplicate_evidence",
    "detect_and_apply_conflicts",
    "detect_conflicts",
    "extract_evidence_from_source",
    "extract_evidence_from_verified_sources",
    "find_duplicate_groups",
    "generate_evidence_outputs",
    "get_confirmed_evidence",
    "has_legacy_career_memory",
    "migrate_and_deduplicate",
    "migrate_legacy_facts_to_evidence",
    "regenerate_evidence_output",
    "run_evidence_pipeline",
]
