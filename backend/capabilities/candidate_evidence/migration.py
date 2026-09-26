"""Migration adapter: convert legacy career_memory facts into CandidateEvidence items (CP-016, CP-032R).

Provides a read-and-convert path for existing stored "facts" in user.metadata["career_memory"]
so they become first-class CandidateEvidence items with proper provenance and lifecycle.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from backend.domain.candidate_evidence import (
    CandidateEvidence,
    CERTAINTY_CONFIRMED,
    CERTAINTY_ESTIMATED,
    CERTAINTY_UNCERTAIN,
    EVIDENCE_STATUS_CONFIRMED,
    EVIDENCE_STATUS_NEEDS_REVIEW,
    classify_evidence_type,
    compute_content_hash,
)
from backend.domain.models import utc_now_iso

LOGGER = logging.getLogger(__name__)

# Map legacy FACT_TYPES → evidence types
_LEGACY_TYPE_MAP: dict[str, str] = {
    "action": "achievement",
    "tool": "tool",
    "stakeholder": "stakeholder",
    "outcome": "achievement",
    "metric": "metric",
}

# Map legacy CERTAINTIES → evidence statuses
_CERTAINTY_STATUS_MAP: dict[str, str] = {
    "confirmed": EVIDENCE_STATUS_CONFIRMED,
    "estimated": EVIDENCE_STATUS_NEEDS_REVIEW,
    "uncertain": EVIDENCE_STATUS_NEEDS_REVIEW,
}

def _legacy_career_memory_store(user_metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Extract the legacy career_memory blob from user metadata."""
    if user_metadata is None:
        return {}
    metadata = dict(user_metadata)
    stored = dict(metadata.get("career_memory") or {})
    stored.setdefault("facts", [])
    stored.setdefault("outputs", [])
    stored.setdefault("source_signatures", {})
    return stored


def _latest_versions(records: list[dict[str, Any]], id_field: str) -> list[dict[str, Any]]:
    """Return the latest version of each record by id_field."""
    latest: dict[str, dict[str, Any]] = {}
    for raw_record in records:
        record = dict(raw_record)
        record_id = str(record.get(id_field) or "")
        if not record_id:
            continue
        if int(record.get("version") or 0) >= int(latest.get(record_id, {}).get("version") or 0):
            latest[record_id] = record
    return sorted(
        latest.values(),
        key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
        reverse=True,
    )

def migrate_legacy_facts_to_evidence(
    *,
    profile_id: str,
    user_metadata: Mapping[str, Any] | None,
) -> list[CandidateEvidence]:
    """Convert legacy career_memory facts to CandidateEvidence items.

    Only active facts are converted. Stale/deleted facts are skipped.
    Each evidence item retains its original fact_id as metadata for traceability.
    """
    stored = _legacy_career_memory_store(user_metadata)
    raw_facts: list[dict[str, Any]] = stored.get("facts") or []
    if not raw_facts:
        LOGGER.info("No legacy facts to migrate for profile %s", profile_id)
        return []

    latest_facts = _latest_versions(raw_facts, "fact_id")
    active_facts = [
        fact for fact in latest_facts if str(fact.get("status") or "active") == "active"
    ]

    evidence_items: list[CandidateEvidence] = []
    for fact in active_facts:
        value = str(fact.get("value") or "").strip()
        if not value:
            continue

        legacy_type = str(fact.get("type") or "action")
        evidence_type = _LEGACY_TYPE_MAP.get(legacy_type, "responsibility")
        legacy_certainty = str(fact.get("certainty") or "estimated")
        status = _CERTAINTY_STATUS_MAP.get(legacy_certainty, EVIDENCE_STATUS_NEEDS_REVIEW)

        sources = fact.get("sources") or []
        primary_source = sources[0] if sources else {}
        source_asset_id = str(primary_source.get("asset_id") or "")

        subject = dict(fact.get("subject") or {})
        employer = str(subject.get("company") or "")
        role = str(subject.get("role") or "")

        if evidence_type == "achievement":
            evidence_type = classify_evidence_type(value)

        evidence = CandidateEvidence(
            evidence_id=f"ev_migrated_{fact.get('fact_id', '')}",
            profile_id=profile_id,
            evidence_type=evidence_type,
            text=value,
            source_asset=source_asset_id,
            source_id=source_asset_id,
            excerpt=value,
            location=f"legacy_fact:{fact.get('fact_id', 'unknown')}",
            confidence=0.5,
            inferred_employer=employer,
            inferred_role=role,
            dates=[],
            status=status,
            source_confidence=0.5,
            created_at=str(fact.get("created_at") or utc_now_iso()),
            updated_at=str(fact.get("updated_at") or utc_now_iso()),
            version=int(fact.get("version") or 1),
            certainty=legacy_certainty if legacy_certainty in ("confirmed", "estimated", "uncertain") else "estimated",
            experience_mapping={
                "company": employer,
                "role": role,
                "project": str(subject.get("project") or ""),
            },
            metadata={
                "migrated_from": "career_memory",
                "legacy_fact_id": fact.get("fact_id", ""),
                "legacy_type": legacy_type,
                "legacy_certainty": legacy_certainty,
                "legacy_version": fact.get("version", 1),
            },
        )
        evidence_items.append(evidence)

    LOGGER.info(
        "Migrated %d legacy facts to evidence for profile %s",
        len(evidence_items), profile_id,
    )
    return evidence_items


def has_legacy_career_memory(user_metadata: Mapping[str, Any] | None) -> bool:
    """Check whether user metadata contains legacy career_memory data."""
    if user_metadata is None:
        return False
    stored = dict(user_metadata).get("career_memory")
    if not stored or not isinstance(stored, dict):
        return False
    facts = stored.get("facts") or []
    return bool(facts and isinstance(facts, list) and len(facts) > 0)


def clear_legacy_career_memory(user_metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Remove the legacy career_memory blob from user metadata.

    Returns a new metadata dict safe for persisting.
    """
    if user_metadata is None:
        return {}
    cleaned = dict(user_metadata)
    cleaned.pop("career_memory", None)
    return cleaned



def migrate_and_deduplicate(
    *,
    profile_id: str,
    user_metadata: Mapping[str, Any] | None,
    existing_evidence: list[CandidateEvidence] | None = None,
) -> dict[str, Any]:
    """Idempotent migration: convert legacy facts and deduplicate against existing canonical evidence.

    - Converts active legacy career_memory facts to CandidateEvidence items.
    - Skips any fact whose content_hash already exists in the canonical store.
    - Returns newly migrated items only (no duplicates).
    """
    legacy_evidence = migrate_legacy_facts_to_evidence(
        profile_id=profile_id,
        user_metadata=user_metadata,
    )
    if not legacy_evidence:
        return {"migrated": 0, "skipped": 0, "evidence": []}

    existing_hashes: set[str] = set()
    if existing_evidence:
        for ev in existing_evidence:
            h = ev.content_hash or compute_content_hash(ev.text)
            if h:
                existing_hashes.add(h)

    new_items: list[CandidateEvidence] = []
    skipped = 0
    for ev in legacy_evidence:
        h = ev.content_hash or compute_content_hash(ev.text)
        if h in existing_hashes:
            skipped += 1
            LOGGER.debug("Skipping duplicate legacy fact: %s", ev.text[:80])
            continue
        existing_hashes.add(h)
        new_items.append(ev)

    LOGGER.info(
        "Idempotent migration: %d new, %d skipped (duplicates) for profile %s",
        len(new_items), skipped, profile_id,
    )
    return {
        "migrated": len(new_items),
        "skipped": skipped,
        "evidence": [ev.to_dict() for ev in new_items],
    }


__all__ = [
    "clear_legacy_career_memory",
    "has_legacy_career_memory",
    "migrate_and_deduplicate",
    "migrate_legacy_facts_to_evidence",
]

