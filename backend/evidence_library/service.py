"""Evidence library service for career profiles.

Provides CRUD operations and filtering for evidence items stored under
work experience records.  Evidence lives in profile.metadata, keyed by
the evidence_library namespace, so it follows the same persistence
pattern as work experiences and merge suggestions.
"""

from __future__ import annotations

from typing import Any, Mapping

from backend.domain.models import (
    EVIDENCE_SOURCE_KIND_MANUAL,
    EVIDENCE_TYPE_ACHIEVEMENT,
    EVIDENCE_VERIFICATION_STATE_UNVERIFIED,
    EvidenceRecord,
    utc_now_iso,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_EVIDENCE_KEY = "evidence_library"


def _read_evidence(profile_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    raw = profile_metadata.get(_EVIDENCE_KEY)
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    return []


def _write_evidence(profile_metadata: dict[str, Any], items: list[dict[str, Any]]) -> None:
    profile_metadata[_EVIDENCE_KEY] = list(items)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def list_evidence(
    profile,
    *,
    experience_id: str = "",
    evidence_type: str = "",
    verification_state: str = "",
    source: str = "",
) -> list[EvidenceRecord]:
    """Return all evidence items, optionally filtered."""
    metadata = dict(profile.metadata or {})
    raw = _read_evidence(metadata)
    records = [EvidenceRecord.from_dict(item) for item in raw]

    if experience_id:
        records = [r for r in records if r.experience_id == experience_id]
    if evidence_type:
        records = [r for r in records if r.evidence_type == evidence_type]
    if verification_state:
        records = [r for r in records if r.verification_state == verification_state]
    if source:
        records = [r for r in records if r.source == source]

    records.sort(key=lambda r: (r.sort_order, r.created_at or ""))
    return records


def get_evidence(profile, evidence_id: str) -> EvidenceRecord | None:
    metadata = dict(profile.metadata or {})
    raw = _read_evidence(metadata)
    for item in raw:
        if str(item.get("evidence_id") or "") == evidence_id:
            return EvidenceRecord.from_dict(item)
    return None


def create_evidence(profile, payload: Mapping[str, Any]) -> EvidenceRecord:
    metadata = dict(profile.metadata or {})
    raw = _read_evidence(metadata)

    experience_id = str(payload.get("experience_id") or "")
    if not experience_id:
        raise ValueError("experience_id is required to create evidence.")

    existing_sort = max(
        (int(item.get("sort_order") or 0) for item in raw if item.get("experience_id") == experience_id),
        default=-1,
    )

    record = EvidenceRecord.create(
        experience_id=experience_id,
        profile_id=profile.profile_id,
        action=str(payload.get("action") or ""),
        why_it_mattered=str(payload.get("why_it_mattered") or ""),
        tools=str(payload.get("tools") or ""),
        stakeholders=str(payload.get("stakeholders") or ""),
        challenge=str(payload.get("challenge") or ""),
        result=str(payload.get("result") or ""),
        metric=str(payload.get("metric") or ""),
        source=str(payload.get("source") or EVIDENCE_SOURCE_KIND_MANUAL),
        source_asset_ids=list(payload.get("source_asset_ids") or []),
        verification_state=str(payload.get("verification_state") or EVIDENCE_VERIFICATION_STATE_UNVERIFIED),
        evidence_type=str(payload.get("evidence_type") or EVIDENCE_TYPE_ACHIEVEMENT),
        sort_order=existing_sort + 1,
    )
    raw.append(record.to_dict())
    _write_evidence(metadata, raw)
    profile.metadata = metadata
    profile.updated_at = utc_now_iso()
    return record


def update_evidence(profile, evidence_id: str, payload: Mapping[str, Any]) -> EvidenceRecord:
    metadata = dict(profile.metadata or {})
    raw = _read_evidence(metadata)

    updatable_fields = (
        "action",
        "why_it_mattered",
        "tools",
        "stakeholders",
        "challenge",
        "result",
        "metric",
        "source",
        "verification_state",
        "evidence_type",
    )

    for idx, item in enumerate(raw):
        if str(item.get("evidence_id") or "") == evidence_id:
            record = EvidenceRecord.from_dict(item)
            for field_name in updatable_fields:
                if field_name in payload:
                    setattr(record, field_name, str(payload[field_name] or "").strip())
            if "source_asset_ids" in payload:
                record.source_asset_ids = [
                    str(a).strip() for a in payload["source_asset_ids"] or [] if str(a).strip()
                ]
            if "sort_order" in payload:
                record.sort_order = int(payload["sort_order"] or 0)
            record.updated_at = utc_now_iso()
            raw[idx] = record.to_dict()
            _write_evidence(metadata, raw)
            profile.metadata = metadata
            profile.updated_at = utc_now_iso()
            return record
    raise KeyError(f"Evidence item '{evidence_id}' not found.")


def delete_evidence(profile, evidence_id: str) -> None:
    metadata = dict(profile.metadata or {})
    raw = _read_evidence(metadata)
    updated = [item for item in raw if str(item.get("evidence_id") or "") != evidence_id]
    if len(updated) == len(raw):
        raise KeyError(f"Evidence item '{evidence_id}' not found.")
    _write_evidence(metadata, updated)
    profile.metadata = metadata
    profile.updated_at = utc_now_iso()
