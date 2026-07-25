"""Canonical evidence generation (CP-032R).

Generates CV bullets and cover-letter narratives from confirmed
CandidateEvidence items. Replaces the legacy career_memory output
generation with canonical evidence-based generation.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import uuid4

from backend.domain.candidate_evidence import (
    CandidateEvidence,
    CERTAINTY_CONFIRMED,
    EVIDENCE_STATUS_CONFIRMED,
)
from backend.domain.models import utc_now_iso

LOGGER = logging.getLogger(__name__)

_NUMBER_PATTERN = re.compile(
    r"(?<!\w)(?:[$\u20ac\u00a3]\s*)?\d+(?:[.,]\d+)?(?:\s*%|\s*(?:hours?|days?|weeks?|months?|years?))?",
    re.I,
)

_PROMPT_LEAKAGE = ("what did", "please describe", "tell me about", "estimated impact")

_GENERATION_MODES = {"standard", "shorten", "technical"}


def get_confirmed_evidence(
    evidence_items: list[CandidateEvidence],
) -> list[CandidateEvidence]:
    """Return only confirmed, non-merged evidence items suitable for generation."""
    return [
        ev
        for ev in evidence_items
        if ev.is_confirmed and ev.is_certainty_confirmed
        and not ev.is_merged and not ev.is_rejected
    ]


def _compose_outputs(
    evidence_items: list[CandidateEvidence],
    *,
    mode: str = "standard",
) -> tuple[str, str, list[str]]:
    """Compose CV bullet and cover letter from confirmed evidence items."""
    eligible = [
        ev
        for ev in evidence_items
        if not (_NUMBER_PATTERN.search(ev.text) and ev.certainty != CERTAINTY_CONFIRMED)
    ]

    if not eligible:
        raise ValueError("At least one confirmed evidence item is required for generation.")

    # Group by type for balanced output
    by_type: dict[str, list[CandidateEvidence]] = {}
    for ev in eligible:
        by_type.setdefault(ev.evidence_type, []).append(ev)

    selected: list[CandidateEvidence] = []
    for t in ("achievement", "metric", "tool", "responsibility", "leadership", "stakeholder"):
        if t in by_type:
            selected.append(by_type[t][0])

    if not selected:
        selected = eligible[:2]

    evidence_ids = [ev.evidence_id for ev in selected]
    values = [ev.text.strip().rstrip(".") for ev in selected]

    if mode == "technical":
        tools = [ev.text.strip().rstrip(".") for ev in by_type.get("tool", [])]
        values = tools + [v for v in values if v not in tools]

    cv_bullet = "; ".join(values)
    if mode == "shorten" or len(cv_bullet) > 240:
        cv_bullet = cv_bullet[:237].rstrip(" ,;") + "..."
    cv_bullet = cv_bullet.rstrip(".") + "."

    # Build cover letter context from experience mapping
    experience = next(
        (ev.experience_mapping for ev in selected if ev.experience_mapping),
        {},
    )
    context = "In this work"
    if experience.get("company") and experience.get("role"):
        context = f"As {experience['role']} at {experience['company']}"

    cover_values = values[1:] + values[:1] if len(values) > 1 else values
    cover_letter = (
        f"{context}, I "
        + ". I also ".join(
            v[:1].lower() + v[1:] for v in cover_values
        )
        + "."
    )

    return cv_bullet, cover_letter, evidence_ids


def _quality_checks(
    cv_bullet: str,
    cover_letter: str,
    evidence_items: list[CandidateEvidence],
) -> dict[str, Any]:
    """Run quality gates on generated output."""
    combined = f"{cv_bullet}{cover_letter}"
    issues: list[dict[str, str]] = []

    if any(fragment in combined.casefold() for fragment in _PROMPT_LEAKAGE):
        issues.append({
            "code": "prompt_leakage",
            "message": "Questionnaire wording leaked into generated output.",
        })

    if len(cv_bullet) > 240:
        issues.append({
            "code": "bullet_too_long",
            "message": "The CV bullet exceeds 240 characters.",
        })

    if cv_bullet.casefold().strip(" .") == cover_letter.casefold().strip(" ."):
        issues.append({
            "code": "duplicated_outputs",
            "message": "CV and cover-letter outputs must use different wording.",
        })

    if not cv_bullet or not cover_letter:
        issues.append({
            "code": "missing_output",
            "message": "Both output formats are required.",
        })
    elif not cover_letter.endswith((".", "!", "?")):
        issues.append({
            "code": "grammar",
            "message": "The cover-letter narrative must end with sentence punctuation.",
        })

    return {"status": "passed" if not issues else "flagged", "issues": issues}


def generate_evidence_outputs(
    evidence_items: list[CandidateEvidence],
    *,
    mode: str = "standard",
) -> dict[str, Any]:
    """Generate CV bullet and cover letter from confirmed evidence."""
    if mode not in _GENERATION_MODES:
        mode = "standard"

    confirmed = get_confirmed_evidence(evidence_items)
    if not confirmed:
        raise ValueError("No confirmed evidence items available for generation.")

    cv_bullet, cover_letter, evidence_ids = _compose_outputs(confirmed, mode=mode)
    quality = _quality_checks(cv_bullet, cover_letter, confirmed)
    now = utc_now_iso()

    return {
        "output_id": f"output_{uuid4().hex[:16]}",
        "version": 1,
        "evidence_ids": evidence_ids,
        "mode": mode,
        "cv_bullet": cv_bullet,
        "cover_letter": cover_letter,
        "quality": quality,
        "created_at": now,
        "updated_at": now,
    }


def regenerate_evidence_output(
    existing_output: dict[str, Any],
    evidence_items: list[CandidateEvidence],
    *,
    action: str = "standard",
    cv_bullet: str = "",
    cover_letter: str = "",
) -> dict[str, Any]:
    """Regenerate or edit an existing output while preserving version history."""
    if action == "edit":
        confirmed = get_confirmed_evidence(evidence_items)
        new_cv = cv_bullet or str(existing_output.get("cv_bullet") or "")
        new_cl = cover_letter or str(existing_output.get("cover_letter") or "")
        evidence_ids = list(existing_output.get("evidence_ids") or [])
        quality = _quality_checks(new_cv, new_cl, confirmed)
    else:
        result = generate_evidence_outputs(evidence_items, mode=action)
        new_cv = result["cv_bullet"]
        new_cl = result["cover_letter"]
        evidence_ids = result["evidence_ids"]
        quality = result["quality"]

    now = utc_now_iso()
    return {
        **existing_output,
        "version": int(existing_output.get("version") or 1) + 1,
        "evidence_ids": evidence_ids,
        "cv_bullet": new_cv,
        "cover_letter": new_cl,
        "quality": quality,
        "updated_at": now,
    }


__all__ = [
    "generate_evidence_outputs",
    "get_confirmed_evidence",
    "regenerate_evidence_output",
]
