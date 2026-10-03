"""CV Bullet Suggestions service (CP-036R).

Generates role-specific CV bullet suggestions from baseline CV, job description,
and selected verified canonical evidence with persistent provenance and review
actions (Accept, Edit, Reject, Replace).
"""

from __future__ import annotations

import re
from typing import Any, Mapping
from uuid import uuid4

from backend.domain.cv_bullet_suggestion import (
    BULLET_SUGGESTION_ACTION_EDIT,
    BULLET_SUGGESTION_STATUS_ACCEPTED,
    BULLET_SUGGESTION_STATUS_EDITED,
    BULLET_SUGGESTION_STATUS_PENDING,
    CVBulletSuggestion,
    SUPPORTED_EDIT_FIELDS,
)
from backend.domain.candidate_evidence import EVIDENCE_STATUS_CONFIRMED

# In-memory store keyed by suggestion_id
_suggestions: dict[str, CVBulletSuggestion] = {}


def _reset_suggestions() -> None:
    """Clear the in-memory suggestion store (for test isolation)."""
    _suggestions.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_baseline_bullets(cv_text: str) -> list[dict[str, Any]]:
    """Parse baseline CV text into experience entries with bullets."""
    lines = [line.strip() for line in str(cv_text or "").splitlines() if line.strip()]
    entries: list[dict[str, Any]] = []
    current_label = ""
    current_bullets: list[str] = []

    for line in lines:
        bullet_match = re.match(r"^[\-*]\s+(.*)$", line)
        if bullet_match:
            current_bullets.append(bullet_match.group(1).strip())
        else:
            if current_label or current_bullets:
                entries.append({"label": current_label, "bullets": list(current_bullets)})
            current_label = line
            current_bullets = []

    if current_label or current_bullets:
        entries.append({"label": current_label, "bullets": list(current_bullets)})

    return entries


def _tokenize(value: str) -> set[str]:
    """Tokenize text for keyword matching."""
    tokens = re.findall(r"[A-Za-z0-9+#-]{3,}", str(value or "").casefold())
    return set(tokens)


def _bullet_relevance_score(
    bullet: str, evidence_texts: list[str], job_description: str,
) -> float:
    """Score how relevant a bullet is to selected evidence and job."""
    bullet_tokens = _tokenize(bullet)
    if not bullet_tokens:
        return 0.0

    evidence_tokens: set[str] = set()
    for text in evidence_texts:
        evidence_tokens |= _tokenize(text)

    job_tokens = _tokenize(job_description)
    evidence_overlap = len(bullet_tokens & evidence_tokens)
    job_overlap = len(bullet_tokens & job_tokens)

    total = len(bullet_tokens)
    return (evidence_overlap * 2.0 + job_overlap * 1.0) / max(total, 1)


def _verified_evidence_items(user) -> list[dict[str, Any]]:
    """Get confirmed/verified canonical evidence items for the user."""
    metadata = dict(getattr(user, "metadata", None) or {})
    evidence_list = list(metadata.get("candidate_evidence") or [])
    return [
        ev for ev in evidence_list
        if str(ev.get("status") or "") == EVIDENCE_STATUS_CONFIRMED
    ]


def _get_evidence_by_ids(user, evidence_ids: list[str]) -> list[dict[str, Any]]:
    """Retrieve verified evidence items by their IDs. Raises ValueError on issues."""
    available = {
        str(ev.get("evidence_id") or ""): dict(ev)
        for ev in _verified_evidence_items(user)
    }
    results: list[dict[str, Any]] = []
    missing: list[str] = []
    unverified: list[str] = []

    for eid in evidence_ids:
        if eid not in available:
            all_items_meta = dict(getattr(user, "metadata", None) or {})
            all_items = {
                str(ev.get("evidence_id") or ""): dict(ev)
                for ev in (all_items_meta.get("candidate_evidence") or [])
            }
            if eid in all_items:
                unverified.append(eid)
            else:
                missing.append(eid)
        else:
            results.append(available[eid])

    if missing or unverified:
        parts = []
        if missing:
            parts.append(f"not found: {', '.join(missing)}")
        if unverified:
            parts.append(f"not verified: {', '.join(unverified)}")
        raise ValueError(f"Evidence issues -- {'; '.join(parts)}")

    return results


def _source_ids_from_evidence(items: list[dict[str, Any]]) -> list[str]:
    """Extract unique source asset IDs from evidence items."""
    source_ids: set[str] = set()
    for item in items:
        sid = str(item.get("source_asset") or item.get("source_id") or "")
        if sid:
            source_ids.add(sid)
    return sorted(source_ids)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def generate_suggestions(
    user,
    *,
    profile_id: str,
    baseline_cv_text: str = "",
    baseline_cv_version: str = "",
    baseline_cv_asset_id: str = "",
    target_job_id: str = "",
    target_job_title: str = "",
    target_job_description: str = "",
    evidence_ids: list[str] | None = None,
) -> list[CVBulletSuggestion]:
    """Generate role-specific CV bullet suggestions from baseline CV, job
    description, and selected verified canonical evidence.

    Only selected verified evidence is eligible. Evidence beyond visible
    baseline bullets can be selected.

    Raises ValueError if no evidence selected, baseline CV missing, or
    invalid evidence IDs.
    """
    selected_evidence_ids = [
        str(e).strip() for e in (evidence_ids or []) if str(e).strip()
    ]
    if not selected_evidence_ids:
        raise ValueError("At least one verified evidence item must be selected.")

    if not baseline_cv_text.strip():
        raise ValueError("Baseline CV text is required to generate suggestions.")

    evidence_items = _get_evidence_by_ids(user, selected_evidence_ids)
    source_ids = _source_ids_from_evidence(evidence_items)
    evidence_texts = [str(item.get("text") or "") for item in evidence_items]

    baseline_entries = _parse_baseline_bullets(baseline_cv_text)
    suggestions: list[CVBulletSuggestion] = []

    for entry in baseline_entries:
        entry_label = entry["label"]
        for bullet in entry["bullets"]:
            score = _bullet_relevance_score(
                bullet, evidence_texts, target_job_description
            )
            suggestion = CVBulletSuggestion.create(
                profile_id=profile_id,
                target_job_id=target_job_id,
                target_job_title=target_job_title,
                target_job_description=target_job_description,
                baseline_cv_version=baseline_cv_version,
                baseline_cv_asset_id=baseline_cv_asset_id,
                evidence_ids=selected_evidence_ids,
                source_ids=source_ids,
                bullet_text=bullet,
                linked_experience_id="",
                label=entry_label,
                metadata={
                    "relevance_score": round(score, 4),
                    "generation_method": "baseline_plus_evidence",
                    "matching_evidence_count": len(evidence_items),
                },
            )
            suggestions.append(suggestion)

    if not suggestions:
        raise ValueError(
            "No bullet suggestions could be generated from the baseline CV."
        )

    for s in suggestions:
        _suggestions[s.suggestion_id] = s

    return suggestions


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def get_suggestions(
    profile_id: str, *, target_job_id: str = ""
) -> list[CVBulletSuggestion]:
    """Get all suggestions, optionally filtered by profile and job."""
    results = []
    for suggestion in _suggestions.values():
        if profile_id and suggestion.profile_id != profile_id:
            continue
        if target_job_id and suggestion.target_job_id != target_job_id:
            continue
        results.append(suggestion)
    results.sort(key=lambda s: s.created_at or "", reverse=True)
    return results


def get_suggestion(suggestion_id: str) -> CVBulletSuggestion | None:
    """Get a single suggestion by ID."""
    return _suggestions.get(suggestion_id)


# ---------------------------------------------------------------------------
# Review actions
# ---------------------------------------------------------------------------


def _validate_edit_payload(payload: Mapping[str, Any]) -> None:
    """Validate an edit payload for unsupported field changes."""
    known_unsupported = set(dict(payload).keys()) - SUPPORTED_EDIT_FIELDS
    if known_unsupported:
        raise ValueError(
            f"Unsupported edit fields: {', '.join(sorted(known_unsupported))}. "
            f"Only these fields can be edited: "
            f"{', '.join(sorted(SUPPORTED_EDIT_FIELDS))}."
        )


def accept_suggestion(suggestion_id: str) -> CVBulletSuggestion:
    """Accept a suggestion as-is. Provenance is retained."""
    suggestion = _suggestions.get(suggestion_id)
    if suggestion is None:
        raise ValueError(f"CV bullet suggestion '{suggestion_id}' not found.")
    suggestion.accept()
    return suggestion


def edit_suggestion(
    suggestion_id: str,
    payload: Mapping[str, Any],
    *,
    changed_by: str = "user",
) -> CVBulletSuggestion:
    """Apply a validated user edit. Unsupported edits blocked."""
    suggestion = _suggestions.get(suggestion_id)
    if suggestion is None:
        raise ValueError(f"CV bullet suggestion '{suggestion_id}' not found.")

    _validate_edit_payload(payload)

    new_text = str(payload.get("bullet_text") or "")
    if not new_text.strip():
        raise ValueError("bullet_text must be non-empty for edit action.")

    suggestion.edit(new_text, changed_by=changed_by)

    if "linked_experience_id" in payload:
        suggestion.linked_experience_id = str(payload["linked_experience_id"] or "")
    if "label" in payload:
        suggestion.label = str(payload["label"] or "")

    return suggestion


def reject_suggestion(suggestion_id: str) -> CVBulletSuggestion:
    """Reject a suggestion. Provenance preserved."""
    suggestion = _suggestions.get(suggestion_id)
    if suggestion is None:
        raise ValueError(f"CV bullet suggestion '{suggestion_id}' not found.")
    suggestion.reject()
    return suggestion


def replace_suggestion(
    suggestion_id: str,
    payload: Mapping[str, Any],
    *,
    changed_by: str = "user",
) -> CVBulletSuggestion:
    """Replace suggestion with a new bullet. Evidence provenance preserved."""
    suggestion = _suggestions.get(suggestion_id)
    if suggestion is None:
        raise ValueError(f"CV bullet suggestion '{suggestion_id}' not found.")

    new_text = str(payload.get("bullet_text") or "")
    if not new_text.strip():
        raise ValueError("bullet_text must be non-empty for replace action.")

    suggestion.replace(new_text, changed_by=changed_by)
    return suggestion


# ---------------------------------------------------------------------------
# Output history
# ---------------------------------------------------------------------------


def get_accepted_bullets(
    profile_id: str,
    *,
    target_job_id: str = "",
) -> list[CVBulletSuggestion]:
    """Get accepted/edited bullets retaining provenance for output history."""
    results = []
    for suggestion in _suggestions.values():
        if profile_id and suggestion.profile_id != profile_id:
            continue
        if target_job_id and suggestion.target_job_id != target_job_id:
            continue
        if suggestion.status in (
            BULLET_SUGGESTION_STATUS_ACCEPTED,
            BULLET_SUGGESTION_STATUS_EDITED,
        ):
            results.append(suggestion)
    results.sort(
        key=lambda s: s.updated_at or s.created_at or "", reverse=True
    )
    return results
