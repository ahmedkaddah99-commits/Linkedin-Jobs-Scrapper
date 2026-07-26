"""Evidence review service (CP-040R).

One-at-a-time evidence review with:
- Auto-suggested mapping using dates, employer, role, project, and source
- Confirm/Edit/Reject actions that autosave and auto-advance
- Ambiguity handling with inline chooser/create
- Canonical readiness computed from evidence records
- Legacy memory-spike counters migrated/removed
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Mapping

from backend.domain.candidate_evidence import (
    CandidateEvidence,
    EVIDENCE_STATUS_CONFIRMED,
    EVIDENCE_STATUS_NEEDS_REVIEW,
    EVIDENCE_STATUS_REJECTED,
    EVIDENCE_STATUS_REVIEWED,
    compute_content_hash,
)
from backend.domain.models import utc_now_iso


# ── Constants ──────────────────────────────────────────────────────────
_REVIEW_CURSOR_KEY = "evidence_review_cursor"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Persistence helpers ────────────────────────────────────────────────


def _read_evidence(user) -> list[CandidateEvidence]:
    """Read canonical evidence items from user metadata."""
    metadata = dict(user.metadata or {})
    raw = list(metadata.get("candidate_evidence") or [])
    return [CandidateEvidence.from_dict(item) for item in raw if isinstance(item, dict)]


def _write_evidence(user, evidence_items: list[CandidateEvidence]) -> None:
    """Persist canonical evidence items to user metadata."""
    metadata = dict(user.metadata or {})
    metadata["candidate_evidence"] = [ev.to_dict() for ev in evidence_items]
    user.metadata = metadata
    user.updated_at = _now()


def _read_experiences(user) -> list[dict[str, Any]]:
    """Read work experiences from user metadata."""
    metadata = dict(user.metadata or {})
    raw = list(metadata.get("work_experiences") or [])
    return [dict(item) for item in raw if isinstance(item, dict)]


def _get_review_cursor(user) -> int:
    """Get the current review cursor index from user metadata."""
    metadata = dict(user.metadata or {})
    return int(metadata.get(_REVIEW_CURSOR_KEY) or 0)


def _set_review_cursor(user, index: int) -> None:
    """Set the review cursor index in user metadata."""
    metadata = dict(user.metadata or {})
    metadata[_REVIEW_CURSOR_KEY] = index
    user.metadata = metadata
    user.updated_at = _now()


# ── Legacy memory-spike migration ─────────────────────────────────────

_LEGACY_SPIKE_KEYS = {
    "memory_spike",
    "evidence_progress",
    "evidence_question_index",
    "evidence_completed_count",
    "evidence_review_index",
    "career_memory_progress",
    "career_memory_step",
    "career_memory_completed",
    "guided_flow_step",
    "guided_flow_progress",
    "question_step_index",
    "profile_build_step",
}


def remove_legacy_memory_spike(user) -> dict[str, Any]:
    """Remove legacy memory-spike counters and migrate orphaned data.

    Legacy memory-spike stored transient progress counters that are now
    redundant with canonical evidence statuses. This cleans them up.
    """
    removed_keys: list[str] = []
    migrated_count = 0

    if user.metadata is None:
        return {"removed_keys": [], "migrated_count": 0,
                "message": "No metadata to clean."}

    metadata = dict(user.metadata)

    for key in _LEGACY_SPIKE_KEYS:
        if key in metadata:
            removed_keys.append(key)
            metadata.pop(key, None)

    # Migrate orphaned spike evidence data
    spike_data = metadata.pop("evidence_spike_cache", None)
    if isinstance(spike_data, list):
        existing = _read_evidence(user)
        existing_hashes = {ev.content_hash for ev in existing if ev.content_hash}
        new_ev: list[CandidateEvidence] = []
        for raw in spike_data:
            if isinstance(raw, dict) and raw.get("text"):
                ev = CandidateEvidence.create(
                    profile_id=getattr(user, "profile_id", ""),
                    text=str(raw.get("text", "")),
                    evidence_type=str(raw.get("type") or raw.get("evidence_type") or ""),
                    source_asset=str(raw.get("source_asset") or raw.get("source_id") or ""),
                    inferred_employer=str(raw.get("employer") or ""),
                    inferred_role=str(raw.get("role") or ""),
                )
                if ev.content_hash not in existing_hashes:
                    existing_hashes.add(ev.content_hash)
                    migrated_count += 1
                    new_ev.append(ev)
        removed_keys.append("evidence_spike_cache")
        if new_ev:
            all_ev = existing + new_ev
            _write_evidence(user, all_ev)
            metadata["candidate_evidence"] = [ev.to_dict() for ev in all_ev]

    if removed_keys:
        user.metadata = metadata
        user.updated_at = _now()

    return {
        "removed_keys": removed_keys,
        "migrated_count": migrated_count,
        "message": (
            f"Removed {len(removed_keys)} legacy counter keys."
            f" Migrated {migrated_count} evidence items to canonical store."
        ),
    }


# ── Text utilities ─────────────────────────────────────────────────────


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


def _extract_year(text: str) -> int | None:
    match = re.search(r"(19|20)\d{2}", str(text or ""))
    return int(match.group(0)) if match else None


def _date_overlap_score(
    ev_start: str, ev_end: str, exp_start: str, exp_end: str,
) -> float:
    """Compute overlap score between evidence dates and experience dates."""
    ev_sy = _extract_year(ev_start)
    ev_ey = _extract_year(ev_end)
    exp_sy = _extract_year(exp_start)
    exp_ey = _extract_year(exp_end)

    if _normalize(ev_end) in ("present", "current"):
        ev_ey = 9999
    if _normalize(exp_end) in ("present", "current"):
        exp_ey = 9999

    any_evd = ev_sy is not None or ev_ey is not None
    any_exp = exp_sy is not None or exp_ey is not None
    if not any_evd or not any_exp:
        return 0.0

    if ev_sy is not None and ev_ey is None:
        ev_ey = ev_sy
    if exp_sy is not None and exp_ey is None:
        exp_ey = exp_sy
    if ev_ey is not None and ev_sy is None:
        ev_sy = ev_ey
    if exp_ey is not None and exp_sy is None:
        exp_sy = exp_ey

    if ev_sy is None or ev_ey is None or exp_sy is None or exp_ey is None:
        return 0.0

    overlap_start = max(ev_sy, exp_sy)
    overlap_end = min(ev_ey, exp_ey)
    if overlap_start > overlap_end:
        return 0.0

    overlap_span = overlap_end - overlap_start + 1
    evd_span = ev_ey - ev_sy + 1
    exp_span = exp_ey - exp_sy + 1
    if evd_span <= 0 or exp_span <= 0:
        return 0.0
    return min(1.0, overlap_span / max(evd_span, exp_span))


def _build_experience_label(exp: dict[str, Any]) -> str:
    """Build a human-readable label for an experience record."""
    parts = [str(exp.get("job_title") or exp.get("role") or "(untitled)")]
    employer = str(exp.get("employer") or exp.get("company") or "")
    if employer:
        parts.append(employer)
    label = " -- ".join(parts)
    start = str(exp.get("start_date") or "")
    end = str(exp.get("end_date") or "")
    if start or end:
        label += f" . {start}-{end}"
    return label


# ── Mapping suggestion engine ──────────────────────────────────────────


def suggest_mapping_for_evidence(
    evidence: CandidateEvidence, experiences: list[dict[str, Any]],
) -> dict[str, Any]:
    """Suggest the best experience mapping using employer, role, dates, source.

    Returns dict with suggested_mapping, is_ambiguous, alternatives, match_confidence.
    """
    if not experiences:
        return {
            "suggested_mapping": None,
            "is_ambiguous": False,
            "alternatives": [],
            "match_confidence": 0.0,
        }

    scored: list[tuple[dict[str, Any], float, list[str]]] = []
    for exp in experiences:
        total = 0.0
        count = 0.0
        reasons: list[str] = []

        ev_employer = evidence.inferred_employer or ""
        exp_employer = str(exp.get("employer") or exp.get("company") or "")
        if ev_employer and exp_employer:
            score = _fuzzy_score(ev_employer, exp_employer)
            if score > 0.4:
                total += score
                count += 1.0
                reasons.append(f"employer: {exp_employer}")

        ev_role = evidence.inferred_role or ""
        exp_role = str(exp.get("job_title") or exp.get("role") or "")
        if ev_role and exp_role:
            score = _fuzzy_score(ev_role, exp_role)
            if score > 0.3:
                total += score * 0.8
                count += 0.8
                reasons.append(f"role: {exp_role}")

        ev_dates = evidence.dates or []
        ev_start = ev_dates[0] if len(ev_dates) > 0 else ""
        ev_end = ev_dates[1] if len(ev_dates) > 1 else ""
        exp_start = str(exp.get("start_date") or "")
        exp_end = str(exp.get("end_date") or "")
        date_score = _date_overlap_score(ev_start, ev_end, exp_start, exp_end)
        if date_score > 0:
            total += date_score * 0.6
            count += 0.6
            reasons.append(f"dates: {exp_start}-{exp_end}")

        ev_source = (evidence.experience_mapping or {}).get("project", "")
        exp_context = str(exp.get("description") or "")[:200]
        if ev_source and exp_context:
            score = _fuzzy_score(ev_source, exp_context)
            if score > 0.2:
                total += score * 0.4
                count += 0.4
                reasons.append("project context")

        if count > 0:
            scored.append((exp, round(total / count, 2), reasons))

    scored.sort(key=lambda x: -x[1])
    if not scored:
        return {
            "suggested_mapping": None,
            "is_ambiguous": False,
            "alternatives": [],
            "match_confidence": 0.0,
        }

    best_exp, best_conf, best_reasons = scored[0]
    suggested = {
        "experience_id": str(best_exp.get("experience_id") or ""),
        "employer": str(best_exp.get("employer") or best_exp.get("company") or ""),
        "role": str(best_exp.get("job_title") or best_exp.get("role") or ""),
        "start_date": str(best_exp.get("start_date") or ""),
        "end_date": str(best_exp.get("end_date") or ""),
        "label": _build_experience_label(best_exp),
        "confidence": best_conf,
        "reason": "; ".join(best_reasons) if best_reasons else "Matched by text similarity.",
    }

    is_ambiguous = len(scored) > 1 and (scored[1][1] >= best_conf - 0.15)
    alternatives = []
    if is_ambiguous:
        for alt_exp, alt_conf, alt_reasons in scored[1:4]:
            if alt_conf >= best_conf - 0.20:
                alternatives.append({
                    "experience_id": str(alt_exp.get("experience_id") or ""),
                    "employer": str(alt_exp.get("employer") or alt_exp.get("company") or ""),
                    "role": str(alt_exp.get("job_title") or alt_exp.get("role") or ""),
                    "start_date": str(alt_exp.get("start_date") or ""),
                    "end_date": str(alt_exp.get("end_date") or ""),
                    "label": _build_experience_label(alt_exp),
                    "confidence": alt_conf,
                    "reason": "; ".join(alt_reasons),
                })

    return {
        "suggested_mapping": suggested,
        "is_ambiguous": is_ambiguous,
        "alternatives": alternatives,
        "match_confidence": best_conf,
    }


# ── Core review API ────────────────────────────────────────────────────


def get_next_review_item(user) -> dict[str, Any]:
    """Get the next evidence item awaiting review with suggested mapping."""
    remove_legacy_memory_spike(user)

    evidence_items = _read_evidence(user)
    experiences = _read_experiences(user)

    unreviewed = [
        ev for ev in evidence_items
        if ev.status in (EVIDENCE_STATUS_NEEDS_REVIEW, EVIDENCE_STATUS_REVIEWED)
        and not ev.is_merged and not ev.is_rejected
    ]

    if not unreviewed:
        return {"state": "complete",
                "message": "All evidence items have been reviewed."}

    cursor = _get_review_cursor(user)
    if cursor >= len(unreviewed):
        cursor = 0
        _set_review_cursor(user, cursor)

    current = unreviewed[cursor]

    provenance = {
        "source_asset": current.source_asset,
        "source_id": current.source_id,
        "excerpt": current.excerpt[:200] if current.excerpt else current.text[:200],
        "confidence": current.source_confidence,
        "location": current.location,
        "dates": list(current.dates),
        "inferred_employer": current.inferred_employer,
        "inferred_role": current.inferred_role,
    }

    mapping = suggest_mapping_for_evidence(current, experiences)

    total_count = len(evidence_items)
    reviewed_count = sum(
        1 for ev in evidence_items
        if ev.status in (EVIDENCE_STATUS_CONFIRMED, EVIDENCE_STATUS_REJECTED)
    )
    remaining = sum(
        1 for ev in unreviewed
        if ev.evidence_id != current.evidence_id
    ) + 1

    return {
        "state": "review",
        "evidence": current.to_dict(),
        "provenance": provenance,
        "suggested_mapping": mapping["suggested_mapping"],
        "is_ambiguous": mapping["is_ambiguous"],
        "alternatives": mapping["alternatives"],
        "match_confidence": mapping["match_confidence"],
        "progress": {
            "cursor": cursor + 1,
            "remaining": remaining,
            "total": total_count,
            "reviewed": reviewed_count,
        },
    }


def confirm_evidence(
    user,
    evidence_id: str,
    *,
    mapping: dict[str, str] | None = None,
    edited_text: str | None = None,
) -> dict[str, Any]:
    """Confirm evidence, apply mapping, and auto-advance cursor."""
    evidence_items = _read_evidence(user)
    found = None
    for ev in evidence_items:
        if ev.evidence_id == evidence_id:
            found = ev
            break

    if found is None:
        raise KeyError(f"Evidence item '{evidence_id}' not found.")

    if edited_text:
        found.text = edited_text.strip()
        found.content_hash = compute_content_hash(found.text)

    if mapping:
        found.experience_mapping = {
            "experience_id": str(mapping.get("experience_id") or ""),
            "company": str(mapping.get("employer") or mapping.get("company") or ""),
            "role": str(mapping.get("role") or mapping.get("job_title") or ""),
            "project": str(mapping.get("project") or ""),
        }
        for date_key in ("start_date", "end_date"):
            if mapping.get(date_key):
                found.experience_mapping[date_key] = str(mapping[date_key])
        if mapping.get("label"):
            found.experience_mapping["label"] = str(mapping["label"])

    found.confirm()
    _write_evidence(user, evidence_items)
    _set_review_cursor(user, _get_review_cursor(user) + 1)

    return {"evidence": found.to_dict(), "action": "confirmed"}


def reject_evidence(user, evidence_id: str) -> dict[str, Any]:
    """Reject evidence and auto-advance cursor."""
    evidence_items = _read_evidence(user)
    found = None
    for ev in evidence_items:
        if ev.evidence_id == evidence_id:
            found = ev
            break

    if found is None:
        raise KeyError(f"Evidence item '{evidence_id}' not found.")

    found.reject()
    _write_evidence(user, evidence_items)
    _set_review_cursor(user, _get_review_cursor(user) + 1)

    return {"evidence": found.to_dict(), "action": "rejected"}


def edit_evidence(
    user, evidence_id: str, updates: dict[str, Any],
) -> dict[str, Any]:
    """Edit evidence fields and auto-advance cursor."""
    evidence_items = _read_evidence(user)
    found = None
    for ev in evidence_items:
        if ev.evidence_id == evidence_id:
            found = ev
            break

    if found is None:
        raise KeyError(f"Evidence item '{evidence_id}' not found.")

    if "text" in updates:
        found.text = str(updates["text"]).strip()
        found.content_hash = compute_content_hash(found.text)
    if "evidence_type" in updates:
        found.evidence_type = str(updates["evidence_type"])
    if "inferred_employer" in updates:
        found.inferred_employer = str(updates["inferred_employer"]).strip()
    if "inferred_role" in updates:
        found.inferred_role = str(updates["inferred_role"]).strip()
    if "dates" in updates:
        found.dates = [str(d) for d in updates["dates"]]
    if "experience_mapping" in updates:
        found.experience_mapping = dict(updates["experience_mapping"])
    if "certainty" in updates:
        found.certainty = str(updates["certainty"])

    found.mark_reviewed()
    _write_evidence(user, evidence_items)
    _set_review_cursor(user, _get_review_cursor(user) + 1)

    return {"evidence": found.to_dict(), "action": "edited"}


# ── Canonical readiness ───────────────────────────────────────────────


def compute_canonical_readiness(user) -> dict[str, Any]:
    """Compute readiness from canonical evidence records only.

    Legacy counters excluded. Readiness is derived from confirmed/mapped counts.
    """
    remove_legacy_memory_spike(user)
    evidence_items = _read_evidence(user)

    total = len(evidence_items)
    confirmed = sum(1 for ev in evidence_items if ev.is_confirmed)
    rejected = sum(1 for ev in evidence_items if ev.is_rejected)
    needs_review = sum(
        1 for ev in evidence_items
        if ev.status == EVIDENCE_STATUS_NEEDS_REVIEW
    )
    merged = sum(1 for ev in evidence_items if ev.is_merged)
    mapped = sum(
        1 for ev in evidence_items
        if ev.experience_mapping and ev.experience_mapping.get("experience_id")
    )
    mapped_ready = sum(
        1 for ev in evidence_items
        if ev.is_confirmed
        and ev.experience_mapping
        and ev.experience_mapping.get("experience_id")
    )

    actionable = max(total - merged - rejected, 0)
    readiness_ratio = mapped_ready / max(actionable, 1)

    return {
        "total_evidence": total,
        "confirmed": confirmed,
        "rejected": rejected,
        "merged": merged,
        "needs_review": needs_review,
        "mapped": mapped,
        "mapped_ready": mapped_ready,
        "readiness_ratio": round(readiness_ratio, 2),
        "is_ready": readiness_ratio >= 0.9 and needs_review == 0,
        "computed_from": "canonical_evidence",
        "legacy_counters_excluded": True,
    }


def reset_review_state(user) -> dict[str, Any]:
    """Reset the review cursor and recompute readiness."""
    _set_review_cursor(user, 0)
    return {
        "cursor_reset": True,
        "readiness": compute_canonical_readiness(user),
    }


__all__ = [
    "compute_canonical_readiness",
    "confirm_evidence",
    "edit_evidence",
    "get_next_review_item",
    "reject_evidence",
    "remove_legacy_memory_spike",
    "reset_review_state",
    "suggest_mapping_for_evidence",
]
