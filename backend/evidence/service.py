"""Evidence service for career profiles (CP-014).

Manages evidence items extracted from CV/supporting sources and their
links to work experiences, projects, education, or certifications.
Provides link suggestion based on employer, dates, role, and source context.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from backend.domain.models import (
    EVIDENCE_LINK_TARGET_UNASSIGNED,
    EVIDENCE_LINK_TARGET_WORK_EXPERIENCE,
    EVIDENCE_STATUS_AMBIGUOUS,
    EVIDENCE_STATUS_LINKED,
    EVIDENCE_STATUS_UNLINKED,
    EvidenceItem,
    EvidenceLink,
    utc_now_iso,
)

# Keys for profile metadata storage
_EVIDENCE_KEY = "evidence_items"
_LINKS_KEY = "evidence_links"


def _normalize(text: str) -> str:
    return str(text or "").strip().lower()


def _tokenize(text: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", _normalize(text))
    return {token for token in cleaned.split() if len(token) > 1}


def _fuzzy_score(text_a: str, text_b: str) -> float:
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _read_evidence(profile_metadata: dict) -> list[dict]:
    raw = profile_metadata.get(_EVIDENCE_KEY)
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    return []


def _write_evidence(profile_metadata: dict, evidence: list[dict]) -> None:
    profile_metadata[_EVIDENCE_KEY] = list(evidence)


def _read_links(profile_metadata: dict) -> list[dict]:
    raw = profile_metadata.get(_LINKS_KEY)
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    return []


def _write_links(profile_metadata: dict, links: list[dict]) -> None:
    profile_metadata[_LINKS_KEY] = list(links)



# ---------------------------------------------------------------------------
# CRUD: evidence items
# ---------------------------------------------------------------------------


def list_evidence(profile) -> list[EvidenceItem]:
    metadata = dict(profile.metadata or {})
    raw = _read_evidence(metadata)
    records = [EvidenceItem.from_dict(item) for item in raw]
    records.sort(key=lambda r: (r.sort_order, r.created_at or ""))
    return records


def get_evidence(profile, evidence_id: str) -> EvidenceItem | None:
    metadata = dict(profile.metadata or {})
    for item in _read_evidence(metadata):
        if str(item.get("evidence_id") or "") == evidence_id:
            return EvidenceItem.from_dict(item)
    return None


def create_evidence(profile, payload: Mapping[str, Any]) -> EvidenceItem:
    metadata = dict(profile.metadata or {})
    raw = _read_evidence(metadata)
    existing_sort = max((int(item.get("sort_order") or 0) for item in raw), default=-1)
    record = EvidenceItem.create(
        profile_id=profile.profile_id,
        text=str(payload.get("text") or ""),
        fact_type=str(payload.get("fact_type") or ""),
        certainty=str(payload.get("certainty") or ""),
        source_asset_ids=list(payload.get("source_asset_ids") or []),
        source_context=str(payload.get("source_context") or ""),
        extracted_employer=str(payload.get("extracted_employer") or ""),
        extracted_role=str(payload.get("extracted_role") or ""),
        extracted_start_date=str(payload.get("extracted_start_date") or ""),
        extracted_end_date=str(payload.get("extracted_end_date") or ""),
        sort_order=existing_sort + 1,
    )
    raw.append(record.to_dict())
    _write_evidence(metadata, raw)
    profile.metadata = metadata
    profile.updated_at = utc_now_iso()
    return record


def update_evidence(profile, evidence_id: str, payload: Mapping[str, Any]) -> EvidenceItem:
    metadata = dict(profile.metadata or {})
    raw = _read_evidence(metadata)
    updatable = (
        "text", "fact_type", "certainty", "source_context",
        "extracted_employer", "extracted_role",
        "extracted_start_date", "extracted_end_date",
    )
    for idx, item in enumerate(raw):
        if str(item.get("evidence_id") or "") == evidence_id:
            record = EvidenceItem.from_dict(item)
            for field in updatable:
                if field in payload:
                    setattr(record, field, str(payload[field] or "").strip())
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
    raw_links = _read_links(metadata)
    links = [l for l in raw_links if str(l.get("evidence_id") or "") != evidence_id]
    _write_links(metadata, links)
    profile.metadata = metadata
    profile.updated_at = utc_now_iso()



# ---------------------------------------------------------------------------
# Evidence Links CRUD
# ---------------------------------------------------------------------------


def list_links_for_evidence(profile, evidence_id: str) -> list[EvidenceLink]:
    metadata = dict(profile.metadata or {})
    raw = _read_links(metadata)
    records = [
        EvidenceLink.from_dict(item)
        for item in raw
        if str(item.get("evidence_id") or "") == evidence_id
    ]
    records.sort(key=lambda r: (r.sort_order, r.created_at or ""))
    return records


def link_evidence_to_target(
    profile,
    evidence_id: str,
    *,
    target_type: str = EVIDENCE_LINK_TARGET_UNASSIGNED,
    target_id: str = "",
    target_label: str = "",
    is_primary: bool = False,
    is_suggested: bool = False,
    confidence: float = 0.0,
    suggestion_reason: str = "",
) -> EvidenceLink:
    evidence = get_evidence(profile, evidence_id)
    if evidence is None:
        raise KeyError(f"Evidence item '{evidence_id}' not found.")
    metadata = dict(profile.metadata or {})
    raw_links = _read_links(metadata)
    link = EvidenceLink.create(
        evidence_id=evidence_id,
        profile_id=profile.profile_id,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        confidence=confidence,
        suggestion_reason=suggestion_reason,
        is_suggested=is_suggested,
        is_primary=is_primary,
        sort_order=len(raw_links),
    )
    raw_links.append(link.to_dict())
    _write_links(metadata, raw_links)
    _recompute_evidence_status(profile, evidence, metadata)
    profile.metadata = metadata
    profile.updated_at = utc_now_iso()
    return link


def confirm_link(profile, link_id: str) -> EvidenceLink:
    metadata = dict(profile.metadata or {})
    raw_links = _read_links(metadata)
    for idx, item in enumerate(raw_links):
        if str(item.get("link_id") or "") == link_id:
            link = EvidenceLink.from_dict(item)
            link.is_suggested = False
            link.updated_at = utc_now_iso()
            raw_links[idx] = link.to_dict()
            _write_links(metadata, raw_links)
            profile.metadata = metadata
            profile.updated_at = utc_now_iso()
            return link
    raise KeyError(f"Evidence link '{link_id}' not found.")


def dismiss_link_suggestion(profile, link_id: str) -> None:
    metadata = dict(profile.metadata or {})
    raw_links = _read_links(metadata)
    target_link = None
    for item in raw_links:
        if str(item.get("link_id") or "") == link_id:
            target_link = EvidenceLink.from_dict(item)
            break
    if target_link is None:
        raise KeyError(f"Evidence link '{link_id}' not found.")
    updated_links = [item for item in raw_links if str(item.get("link_id") or "") != link_id]
    _write_links(metadata, updated_links)
    evidence = get_evidence(profile, target_link.evidence_id)
    if evidence is not None:
        _recompute_evidence_status(profile, evidence, metadata)
    profile.metadata = metadata
    profile.updated_at = utc_now_iso()



# ---------------------------------------------------------------------------
# Status recomputation
# ---------------------------------------------------------------------------


def _recompute_evidence_status(profile, evidence: EvidenceItem, metadata: dict) -> None:
    raw_evidence = _read_evidence(metadata)
    raw_links = _read_links(metadata)
    evd_links = [
        EvidenceLink.from_dict(l)
        for l in raw_links
        if str(l.get("evidence_id") or "") == evidence.evidence_id
    ]
    confirmed = [l for l in evd_links if not l.is_suggested]
    suggested = [l for l in evd_links if l.is_suggested]
    assigned = [l for l in confirmed if l.target_type != EVIDENCE_LINK_TARGET_UNASSIGNED]

    if not evd_links:
        evidence.status = EVIDENCE_STATUS_UNLINKED
    elif suggested and not confirmed:
        evidence.status = EVIDENCE_STATUS_AMBIGUOUS
    elif len(assigned) >= 1:
        evidence.status = EVIDENCE_STATUS_LINKED
    else:
        evidence.status = EVIDENCE_STATUS_UNLINKED

    evidence.linked_target_count = len(assigned)
    evidence.updated_at = utc_now_iso()

    for idx, item in enumerate(raw_evidence):
        if str(item.get("evidence_id") or "") == evidence.evidence_id:
            raw_evidence[idx] = evidence.to_dict()
            break
    _write_evidence(metadata, raw_evidence)


def profile_all_evidence_resolved(profile) -> bool:
    evidence_items = list_evidence(profile)
    if not evidence_items:
        return True
    return all(item.status == EVIDENCE_STATUS_LINKED for item in evidence_items)


# ---------------------------------------------------------------------------
# Link suggestion engine
# ---------------------------------------------------------------------------


def suggest_links_for_profile(profile) -> list[EvidenceLink]:
    all_suggestions: list[EvidenceLink] = []
    for evd in list_evidence(profile):
        if evd.needs_resolution:
            all_suggestions.extend(suggest_links_for_evidence(profile, evd.evidence_id))
    return all_suggestions


def suggest_links_for_evidence(profile, evidence_id: str) -> list[EvidenceLink]:
    evidence = get_evidence(profile, evidence_id)
    if evidence is None:
        raise KeyError(f"Evidence item '{evidence_id}' not found.")

    metadata = dict(profile.metadata or {})
    raw_links = _read_links(metadata)
    raw_links = [
        l for l in raw_links
        if str(l.get("evidence_id") or "") != evidence_id
        or not EvidenceLink.from_dict(l).is_suggested
    ]
    _write_links(metadata, raw_links)

    from backend.work_experience.service import list_experiences
    experiences = list_experiences(profile)
    suggestions: list[EvidenceLink] = []

    if not experiences:
        link = EvidenceLink.create(
            evidence_id=evidence_id, profile_id=profile.profile_id,
            target_type=EVIDENCE_LINK_TARGET_UNASSIGNED,
            target_label="Unassigned", confidence=1.0,
            suggestion_reason="No work experiences found; evidence left unassigned.",
            is_suggested=True,
        )
        suggestions.append(link)
        raw_links.append(link.to_dict())
    else:
        matched = False
        for exp in experiences:
            score, reasons = _match_evidence_to_experience(evidence, exp)
            if score > 0.1:
                matched = True
                label = _build_target_label(exp)
                link = EvidenceLink.create(
                    evidence_id=evidence_id, profile_id=profile.profile_id,
                    target_type=EVIDENCE_LINK_TARGET_WORK_EXPERIENCE,
                    target_id=exp.experience_id, target_label=label,
                    confidence=round(score, 2),
                    suggestion_reason="; ".join(reasons) if reasons else "Matched by employer/role/dates.",
                    is_suggested=True, is_primary=(len(suggestions) == 0),
                    sort_order=len(suggestions),
                )
                suggestions.append(link)
                raw_links.append(link.to_dict())
        if not matched:
            link = EvidenceLink.create(
                evidence_id=evidence_id, profile_id=profile.profile_id,
                target_type=EVIDENCE_LINK_TARGET_UNASSIGNED,
                target_label="Unassigned", confidence=0.0,
                suggestion_reason="No matching work experience found.",
                is_suggested=True,
            )
            suggestions.append(link)
            raw_links.append(link.to_dict())

    _write_links(metadata, raw_links)
    _recompute_evidence_status(profile, evidence, metadata)
    profile.metadata = metadata
    profile.updated_at = utc_now_iso()
    return suggestions



# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------


def _match_evidence_to_experience(evidence: EvidenceItem, experience) -> tuple[float, list[str]]:
    reasons: list[str] = []
    total = 0.0
    count = 0.0

    if evidence.extracted_employer and experience.employer:
        score = _fuzzy_score(evidence.extracted_employer, experience.employer)
        if score > 0.5:
            total += score
            count += 1.0
            reasons.append(f"employer match ({experience.employer})")
    elif evidence.source_context and experience.employer:
        score = _fuzzy_score(evidence.source_context, experience.employer)
        if score > 0.3:
            total += score * 0.5
            count += 0.5
            reasons.append(f"source context mentions employer ({experience.employer})")

    if evidence.extracted_role and experience.job_title:
        score = _fuzzy_score(evidence.extracted_role, experience.job_title)
        if score > 0.3:
            total += score * 0.7
            count += 0.7
            reasons.append(f"role match ({experience.job_title})")

    date_score = _date_overlap_score(evidence, experience)
    if date_score > 0:
        total += date_score * 0.6
        count += 0.6
        reasons.append(
            f"date overlap ({evidence.extracted_start_date}\u2013{evidence.extracted_end_date}"
            f" vs {experience.start_date}\u2013{experience.end_date})"
        )

    if count == 0:
        return 0.0, []
    return round(total / count, 2), reasons


def _date_overlap_score(evidence: EvidenceItem, experience) -> float:
    evd_start = (evidence.extracted_start_date or "").strip().lower()
    evd_end = (evidence.extracted_end_date or "").strip().lower()
    exp_start = (experience.start_date or "").strip().lower()
    exp_end = (experience.end_date or "").strip().lower()

    if not evd_start and not evd_end and not exp_start and not exp_end:
        return 0.0

    def _year(text: str) -> int | None:
        match = re.search(r"(19|20)\d{2}", text)
        return int(match.group(0)) if match else None

    evd_sy = _year(evd_start)
    evd_ey = _year(evd_end)
    exp_sy = _year(exp_start)
    exp_ey = _year(exp_end)

    if evd_end in ("present", "current"):
        evd_ey = 9999
    if exp_end in ("present", "current"):
        exp_ey = 9999

    any_evd = evd_sy is not None or evd_ey is not None
    any_exp = exp_sy is not None or exp_ey is not None
    if not any_evd or not any_exp:
        return 0.0

    if evd_sy is not None and evd_ey is None:
        evd_ey = evd_sy
    if exp_sy is not None and exp_ey is None:
        exp_ey = exp_sy
    if evd_ey is not None and evd_sy is None:
        evd_sy = evd_ey
    if exp_ey is not None and exp_sy is None:
        exp_sy = exp_ey

    if evd_sy is None or evd_ey is None or exp_sy is None or exp_ey is None:
        return 0.0

    overlap_start = max(evd_sy, exp_sy)
    overlap_end = min(evd_ey, exp_ey)
    if overlap_start > overlap_end:
        return 0.0

    overlap_span = overlap_end - overlap_start + 1
    evd_span = evd_ey - evd_sy + 1
    exp_span = exp_ey - exp_sy + 1

    if evd_span <= 0 or exp_span <= 0:
        return 0.0
    return min(1.0, overlap_span / max(evd_span, exp_span))


def _build_target_label(experience) -> str:
    """Build readable label like 'Operations Manager -- Company A . 2022-2024'."""
    parts = [experience.job_title or "(untitled)"]
    if experience.employer:
        parts.append(experience.employer)
    label = " -- ".join(parts)
    date_parts = []
    start = experience.start_date or ""
    end = experience.end_date or ""
    if start or end:
        date_parts.append(f"{start}-{end}")
    if experience.location:
        date_parts.append(experience.location)
    if date_parts:
        label += " . " + " . ".join(date_parts)
    return label
