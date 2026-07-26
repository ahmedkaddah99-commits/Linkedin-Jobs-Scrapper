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

# CP-041R: Import question service for integrated confirmation+question flow
try:
    from backend.evidence.question_service import (
        select_next_question,
        answer_question,
        skip_question,
        _detect_missing_details,
        _question_text,
        _make_question_id,
        _item_label,
        MISSING_METRIC,
        MISSING_OUTCOME,
        QUESTION_STATE_ASKED,
    )
    _HAS_QUESTION_SERVICE = True
except ImportError:
    _HAS_QUESTION_SERVICE = False



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
    # CP-041R: Do NOT advance cursor after confirm: the confirmed item
    # leaves the unreviewed list, so the cursor naturally points to
    # the next unreviewed item.
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
    # CP-041R: Do NOT advance cursor after reject: the rejected item
    # leaves the unreviewed list, so the cursor naturally points to
    # the next unreviewed item.
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


# ── CP-041R: Integrated confirmation + question flow ───────────────────


def _inspect_for_question(evidence: CandidateEvidence) -> dict[str, Any] | None:
    """Inspect a single confirmed evidence item for missing details.

    Returns exactly one highest-value missing-detail question, or None if
    the evidence is sufficiently complete.
    """
    if not _HAS_QUESTION_SERVICE:
        return None

    missing = _detect_missing_details(evidence)
    if not missing:
        return None

    # The guided journey asks only for details that materially improve a CV
    # claim. Tool/scope/date questions are optional context, and mapping is
    # handled by the inline experience chooser rather than another form.
    _priority_order = [MISSING_OUTCOME, MISSING_METRIC]

    for mt in _priority_order:
        if mt in missing:
            question_text = _question_text(evidence, mt)
            question_id = _make_question_id(evidence.evidence_id, mt)
            return {
                "question_id": question_id,
                "evidence_id": evidence.evidence_id,
                "evidence_type": evidence.evidence_type,
                "evidence_label": _item_label(evidence),
                "missing_type": mt,
                "question": question_text,
            }

    return None



def confirm_with_inspect(
    user,
    evidence_id: str,
    *,
    mapping: dict[str, str] | None = None,
    edited_text: str | None = None,
) -> dict[str, Any]:
    """CP-044R: Confirm evidence, inspect for missing details, auto-return next item.

    Flow:
    1. Confirm the evidence with mapping and/or edited text
    2. Inspect the canonical item for missing details
    3. If a missing detail is found -> return {state: "question", ...}
    4. If no missing detail -> return {state: "ready", ...} with readiness and actions
    """
    # Check if already confirmed before calling confirm_evidence (CP-041R idempotency)
    existing_items = _read_evidence(user)
    was_already_confirmed = any(
        ev.evidence_id == evidence_id and ev.is_confirmed
        for ev in existing_items
    )

    confirmed = confirm_evidence(
        user, evidence_id, mapping=mapping, edited_text=edited_text
    )

    evidence_items = _read_evidence(user)
    confirmed_ev = next(
        (ev for ev in evidence_items if ev.evidence_id == evidence_id), None
    )

    if confirmed_ev is None:
        return {
            "state": "confirmed",
            "evidence": confirmed["evidence"],
            "action": "confirmed",
            "readiness": compute_canonical_readiness(user),
        }


    # Skip question if evidence was already confirmed (idempotency)
    if was_already_confirmed:
        readiness = compute_canonical_readiness(user)
        result: dict[str, Any] = {
            "state": "ready" if readiness["is_ready"] else "review",
            "evidence": confirmed["evidence"],
            "action": "confirmed",
            "readiness": readiness,
        }
        if readiness["is_ready"]:
            result["primary_actions"] = build_ready_actions(user)
        else:
            result["next_review"] = try_get_next_review_item(user)
        return result

    question = _inspect_for_question(confirmed_ev) if _HAS_QUESTION_SERVICE else None

    readiness = compute_canonical_readiness(user)

    if question and not readiness["is_ready"]:
        _record_asked_question(user, question)
        return {
            "state": "question",
            "evidence": confirmed["evidence"],
            "action": "confirmed",
            "question": question,
            "readiness": readiness,
        }

    # CP-044R: After confirming (no question needed), auto-return next review item
    next_item = try_get_next_review_item(user)
    if next_item and next_item.get("state") == "review":
        return {
            "state": "review",
            "evidence": confirmed["evidence"],
            "action": "confirmed",
            "readiness": readiness,
            "next_review": next_item,
        }

    return {
        "state": "ready" if readiness["is_ready"] else "review",
        "evidence": confirmed["evidence"],
        "action": "confirmed",
        "readiness": readiness,
        **({"primary_actions": build_ready_actions(user)} if readiness["is_ready"] else {}),
    }



def _record_asked_question(user, question: dict[str, Any]) -> None:
    """Record a question as 'asked' in the evidence question history."""
    if not _HAS_QUESTION_SERVICE:
        return
    metadata = dict(user.metadata or {})
    history = list(metadata.get("evidence_question_history") or [])
    if not isinstance(history, list):
        history = []
    existing = any(
        str(h.get("question_id") or "") == question["question_id"] for h in history
        if isinstance(h, dict)
    )
    if not existing:
        from datetime import datetime, timezone
        history.append({
            "question_id": question["question_id"],
            "evidence_id": question["evidence_id"],
            "missing_type": question["missing_type"],
            "state": QUESTION_STATE_ASKED,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "asked_at": datetime.now(timezone.utc).isoformat(),
        })
        metadata["evidence_question_history"] = history
        user.metadata = metadata
        user.updated_at = _now()



def answer_enrich_evidence(
    user,
    question_id: str,
    answer_text: str,
    *,
    evidence_id: str | None = None,
) -> dict[str, Any]:
    """CP-041R: Answer a question and enrich the evidence record.

    1. Records the answer in question history
    2. Enriches the evidence record with the answer
    3. Recalculates readiness immediately
    4. Returns updated state
    """
    if _HAS_QUESTION_SERVICE:
        try:
            answer_question(user, question_id, {"answer_text": answer_text})
        except Exception:
            pass

    if evidence_id:
        evidence_items = _read_evidence(user)
        for ev in evidence_items:
            if ev.evidence_id == evidence_id:
                if answer_text.strip():
                    original = ev.text.rstrip(".")
                    appended = f"{original}. {answer_text.strip().rstrip('.')}."
                    ev.text = appended
                    ev.content_hash = compute_content_hash(ev.text)
                ev.updated_at = _now()
                _write_evidence(user, evidence_items)
                break

    readiness = compute_canonical_readiness(user)

    if readiness["is_ready"]:
        return {
            "state": "ready",
            "action": "answered",
            "readiness": readiness,
            "primary_actions": build_ready_actions(user),
        }

    # CP-044R: Return next review item inline (no separate fetch needed)
    next_item = try_get_next_review_item(user)
    if next_item and next_item.get("state") == "review":
        return {
            "state": "review",
            "action": "answered",
            "readiness": readiness,
            "next_review": next_item,
        }

    return {
        "state": "ready",
        "action": "answered",
        "readiness": readiness,
        "primary_actions": build_ready_actions(user),
    }



def build_ready_actions(user) -> list[dict[str, Any]]:
    """CP-041R: Build grounded primary actions for Ready state.

    Generates CV bullet and motivation-letter claim from confirmed/mapped
    evidence items. Every output retains its evidence IDs and never invents
    unsupported claims. Libraries/history are secondary.
    """
    evidence_items = _read_evidence(user)

    confirmed = [
        ev for ev in evidence_items
        if ev.is_confirmed and ev.experience_mapping and ev.experience_mapping.get("experience_id")
    ]

    if not confirmed:
        confirmed = [ev for ev in evidence_items if ev.is_confirmed]

    actions: list[dict[str, Any]] = []

    evidence_library = [
        {
            "evidence_id": ev.evidence_id,
            "text": ev.text,
            "evidence_type": ev.evidence_type,
            "employer": ev.inferred_employer or (ev.experience_mapping or {}).get("company", ""),
            "role": ev.inferred_role or (ev.experience_mapping or {}).get("role", ""),
            "dates": list(ev.dates),
            "experience_id": (ev.experience_mapping or {}).get("experience_id", ""),
        }
        for ev in confirmed
    ]

    if confirmed:
        sample = confirmed[0]
        company = sample.inferred_employer or (sample.experience_mapping or {}).get("company", "your role")
        role = sample.inferred_role or (sample.experience_mapping or {}).get("role", "")
        snippet = sample.text[:120].rstrip(".").strip() if sample.text else ""
        evidence_refs = [ev.evidence_id for ev in confirmed[:3]]

        cv_bullet = {
            "action": "cv_bullet",
            "label": "Generate CV Bullet",
            "description": f'Grounded CV bullet from: "{snippet}..."' if snippet else "Generate a CV bullet from your evidence",
            "evidence_ids": evidence_refs,
            "evidence_count": len(confirmed),
            "source": "canonical_evidence",
            "claim": f"{role} at {company}: {snippet}." if role and snippet else snippet,
        }
        actions.append(cv_bullet)

    if confirmed:
        motivations = [
            ev for ev in confirmed if ev.evidence_type in ("motivation", "achievement")
        ] or confirmed[:1]

        claim_ev = motivations[0]
        company = claim_ev.inferred_employer or (claim_ev.experience_mapping or {}).get("company", "")
        role = claim_ev.inferred_role or (claim_ev.experience_mapping or {}).get("role", "")

        motivation_letter = {
            "action": "motivation_letter",
            "label": "Generate Motivation Letter",
            "description": "Grounded motivation claim from confirmed evidence",
            "evidence_ids": [ev.evidence_id for ev in motivations[:2]],
            "evidence_count": len(confirmed),
            "source": "canonical_evidence",
            "claim": f"At {company} as {role}, I delivered measurable impact."
                if company and role else "I delivered measurable impact in my roles.",
        }
        actions.append(motivation_letter)

    if evidence_library:
        actions.append({
            "action": "evidence_library",
            "label": "View Evidence Library",
            "description": f"{len(evidence_library)} confirmed evidence items",
            "evidence_ids": [item["evidence_id"] for item in evidence_library],
            "evidence_count": len(evidence_library),
            "source": "canonical_evidence",
            "items": evidence_library[:5],
        })

    return actions


def skip_question_for_evidence(
    user,
    question_id: str,
) -> dict[str, Any]:
    """CP-041R: Skip a question — permanently exclude it.

    Returns readiness and advances to next state.
    """
    if _HAS_QUESTION_SERVICE:
        try:
            skip_question(user, question_id)
        except Exception:
            pass

    readiness = compute_canonical_readiness(user)

    if readiness["is_ready"]:
        return {
            "state": "ready",
            "action": "skipped",
            "readiness": readiness,
            "primary_actions": build_ready_actions(user),
        }

    # CP-044R: Return next review item inline (no separate fetch needed)
    next_item = try_get_next_review_item(user)
    if next_item and next_item.get("state") == "review":
        return {
            "state": "review",
            "action": "skipped",
            "readiness": readiness,
            "next_review": next_item,
        }

    return {
        "state": "review",
        "action": "skipped",
        "readiness": readiness,
    }




# ── CP-044R: Continuous journey helpers ────────────────────────────────


def try_get_next_review_item(user) -> dict[str, Any] | None:
    """CP-044R: Try to get next review item without side effects.

    Returns None if no more items to review (complete state).
    This is a read-only version — it does NOT advance the cursor.
    """
    evidence_items = _read_evidence(user)
    unreviewed = [
        ev for ev in evidence_items
        if ev.status in (EVIDENCE_STATUS_NEEDS_REVIEW, EVIDENCE_STATUS_REVIEWED)
        and not ev.is_merged and not ev.is_rejected
    ]
    # Mapping is an inline part of review.  Keep a confirmed item in this
    # journey until it has a canonical work-experience ID.
    if not unreviewed:
        unreviewed = [
            ev for ev in evidence_items
            if ev.is_confirmed
            and not ev.is_merged
            and not ev.is_rejected
            and not (ev.experience_mapping or {}).get("experience_id")
        ]
    if not unreviewed:
        return None
    cursor = _get_review_cursor(user)
    if cursor >= len(unreviewed):
        cursor = 0
    current = unreviewed[cursor]
    experiences = _read_experiences(user)
    mapping = suggest_mapping_for_evidence(current, experiences)
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


def _get_pending_question(user) -> dict[str, Any] | None:
    """Restore the single persisted unanswered question after a reload."""
    metadata = dict(user.metadata or {})
    history = metadata.get("evidence_question_history") or []
    pending = next(
        (
            item for item in history
            if isinstance(item, dict) and item.get("state") == QUESTION_STATE_ASKED
        ),
        None,
    )
    if pending is None:
        return None

    evidence = next(
        (ev for ev in _read_evidence(user) if ev.evidence_id == pending.get("evidence_id")),
        None,
    )
    if evidence is None:
        return None

    missing_type = str(pending.get("missing_type") or "")
    return {
        "question_id": str(pending.get("question_id") or ""),
        "evidence_id": evidence.evidence_id,
        "evidence_type": evidence.evidence_type,
        "evidence_label": _item_label(evidence),
        "missing_type": missing_type,
        "question": _question_text(evidence, missing_type),
    }


def get_journey_state(user) -> dict[str, Any]:
    """CP-044R: Full journey state — processing, review, ready, or complete.

    Returns the complete journey snapshot including readiness, next review
    item (if any), and ready actions (if ready).
    """
    readiness = compute_canonical_readiness(user)
    evidence_records = _read_evidence(user)
    metadata = dict(user.metadata or {})
    processing_state = dict(metadata.get("_evidence_processing_state") or {})
    has_legacy_extraction = bool(
        evidence_records
        and processing_state
        and any(
            (item.metadata or {}).get("extraction_version") != "gemini-career-v2"
            for item in evidence_records
        )
    )
    if has_legacy_extraction:
        return {
            "state": "processing",
            "evidence_items": [],
            "readiness": readiness,
            "requires_reprocessing": True,
            "processing_state": processing_state,
        }

    evidence_items = [item.to_dict() for item in evidence_records]

    if readiness["is_ready"]:
        return {
            "state": "ready",
            "evidence_items": evidence_items,
            "readiness": readiness,
            "primary_actions": build_ready_actions(user),
        }

    pending_question = _get_pending_question(user)
    if pending_question is not None:
        return {
            "state": "question",
            "evidence_items": evidence_items,
            "readiness": readiness,
            "question": pending_question,
        }

    next_item = try_get_next_review_item(user)
    if next_item is not None:
        return {
            "state": "review",
            "evidence_items": evidence_items,
            "readiness": readiness,
            "next_review": next_item,
        }

    # Never claim Ready unless canonical readiness agrees.  This fallback is a
    # recoverable review state for inconsistent/legacy records.
    if evidence_items:
        return {
            "state": "review",
            "evidence_items": evidence_items,
            "readiness": readiness,
            "next_review": None,
        }

    return {
        "state": "empty",
        "evidence_items": [],
        "readiness": readiness,
        "primary_actions": build_ready_actions(user),
    }


# CP-044R: Updated __all__ to include journey state functions
__all__ = [
    "answer_enrich_evidence",
    "build_ready_actions",
    "compute_canonical_readiness",
    "confirm_evidence",
    "confirm_with_inspect",
    "edit_evidence",
    "get_journey_state",
    "get_next_review_item",
    "reject_evidence",
    "remove_legacy_memory_spike",
    "reset_review_state",
    "skip_question_for_evidence",
    "suggest_mapping_for_evidence",
    "try_get_next_review_item",
]
