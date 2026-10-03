"""Rebind compatibility service for career profiles.

Compares preserved evidence in an unbound career profile against a new
workspace and baseline CV to surface matching experiences, missing
experiences, changed dates, possible duplicates, and conflicts.
"""

from __future__ import annotations

import re
from typing import Any

from backend.domain.models import (
    CAREER_PROFILE_STATUS_NOT_STARTED,
    CareerProfile,
    CompatibilityExperience,
    RebindCompatibilityReview,
    utc_now_iso,
)


def _normalize(text: str) -> str:
    return str(text or "").strip().lower()


def _tokenize(text: str) -> set[str]:
    """Break text into normalized word tokens for fuzzy matching."""
    cleaned = re.sub(r"[^a-z0-9\s]", " ", _normalize(text))
    return {token for token in cleaned.split() if len(token) > 1}


def _fuzzy_match_score(text_a: str, text_b: str) -> float:
    """Return a similarity score 0.0--1.0 based on token overlap."""
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _extract_preserved_experiences(profile: CareerProfile) -> list[dict[str, Any]]:
    """Extract preserved experiences from the profile's metadata."""
    metadata = dict(profile.metadata or {})
    preserved = metadata.get("preserved_experiences")
    if isinstance(preserved, list):
        return [dict(item) for item in preserved if isinstance(item, dict)]
    preserved = metadata.get("preserved_evidence")
    if isinstance(preserved, list):
        return [dict(item) for item in preserved if isinstance(item, dict)]
    return []


def _extract_new_experiences(
    workspace: Any, baseline_cv_asset_id: str
) -> list[dict[str, Any]]:
    """Extract experiences available from the new workspace context."""
    new_experiences: list[dict[str, Any]] = []

    # Extract from workspace profiles
    if hasattr(workspace, "profiles"):
        for profile_ref in workspace.profiles:
            settings = dict(getattr(profile_ref, "settings", {}))
            profile_sections = settings.get("sections") or settings.get("experiences") or []
            if isinstance(profile_sections, list):
                for section in profile_sections:
                    if isinstance(section, dict):
                        new_experiences.append({
                            "experience_id": str(section.get("id") or section.get("experience_id") or ""),
                            "title": str(section.get("title") or section.get("position") or ""),
                            "company": str(section.get("company") or section.get("organization") or ""),
                            "start_date": str(section.get("start_date") or section.get("startDate") or ""),
                            "end_date": str(section.get("end_date") or section.get("endDate") or ""),
                            "description": str(section.get("description") or section.get("summary") or ""),
                            "skills": [str(s) for s in (section.get("skills") or []) if str(s).strip()],
                        })

    # Extract from workspace settings
    settings = dict(getattr(workspace, "settings", {}))
    ws_experiences = settings.get("experiences") or settings.get("career_history") or []
    if isinstance(ws_experiences, list):
        for exp in ws_experiences:
            if isinstance(exp, dict):
                entry = {
                    "experience_id": str(exp.get("id") or exp.get("experience_id") or ""),
                    "title": str(exp.get("title") or exp.get("position") or ""),
                    "company": str(exp.get("company") or exp.get("organization") or ""),
                    "start_date": str(exp.get("start_date") or exp.get("startDate") or ""),
                    "end_date": str(exp.get("end_date") or exp.get("endDate") or ""),
                    "description": str(exp.get("description") or exp.get("summary") or ""),
                    "skills": [str(s) for s in (exp.get("skills") or []) if str(s).strip()],
                }
                if not any(
                    e.get("experience_id") == entry["experience_id"]
                    for e in new_experiences
                    if entry["experience_id"]
                ):
                    new_experiences.append(entry)

    # Fallback: baseline CV indicator
    if baseline_cv_asset_id and not new_experiences:
        new_experiences.append({
            "experience_id": f"cv_{baseline_cv_asset_id}",
            "title": "Baseline CV",
            "company": "",
            "start_date": "",
            "end_date": "",
            "description": "New baseline CV selected for rebinding",
            "skills": [],
        })

    return new_experiences



SIMILARITY_THRESHOLD = 0.45
CONFLICT_THRESHOLD = 0.70


def _make_experience(exp: dict[str, Any], source: str = "") -> CompatibilityExperience:
    """Build a CompatibilityExperience from a dict."""
    return CompatibilityExperience(
        experience_id=str(exp.get("experience_id") or ""),
        title=str(exp.get("title") or ""),
        company=str(exp.get("company") or ""),
        start_date=str(exp.get("start_date") or ""),
        end_date=str(exp.get("end_date") or ""),
        description=str(exp.get("description") or ""),
        skills=[str(s) for s in (exp.get("skills") or []) if str(s).strip()],
        source=source,
    )


def _build_exp_text(exp: dict[str, Any]) -> str:
    return " ".join([
        str(exp.get("title") or ""),
        str(exp.get("company") or ""),
        str(exp.get("description") or ""),
        " ".join(str(s) for s in (exp.get("skills") or []) if str(s).strip()),
    ])



def _compare_experiences(
    preserved: list[dict[str, Any]],
    new_experiences: list[dict[str, Any]],
) -> tuple[
    list[CompatibilityExperience],
    list[CompatibilityExperience],
    list[CompatibilityExperience],
    list[CompatibilityExperience],
    list[CompatibilityExperience],
]:
    """Compare preserved against new experiences.

    Returns (matching, missing, changed_dates, possible_duplicates, conflicts).
    """
    matching: list[CompatibilityExperience] = []
    missing: list[CompatibilityExperience] = []
    changed_dates: list[CompatibilityExperience] = []
    possible_duplicates: list[CompatibilityExperience] = []
    conflicts: list[CompatibilityExperience] = []
    matched_new_ids: set[str] = set()

    for preserved_exp in preserved:
        preserved_id = str(preserved_exp.get("experience_id") or "")
        if not preserved_id:
            preserved_id = f"preserved_{hash(str(preserved_exp))}"
        preserved_comp = _make_experience(preserved_exp, source="preserved")
        # Ensure ID is set
        preserved_comp = CompatibilityExperience(
            experience_id=preserved_id,
            title=preserved_comp.title,
            company=preserved_comp.company,
            start_date=preserved_comp.start_date,
            end_date=preserved_comp.end_date,
            description=preserved_comp.description,
            skills=preserved_comp.skills,
            source="preserved",
        )

        best_match: tuple[dict[str, Any] | None, float] = (None, 0.0)
        for new_exp in new_experiences:
            new_id = str(new_exp.get("experience_id") or "")
            if new_id in matched_new_ids:
                continue
            score = _fuzzy_match_score(
                _build_exp_text(preserved_exp), _build_exp_text(new_exp)
            )
            if score > best_match[1]:
                best_match = (new_exp, score)

        matched_new, score = best_match
        if matched_new is not None and score >= CONFLICT_THRESHOLD:
            _handle_strong_match(
                preserved_comp, matched_new, matching, changed_dates, matched_new_ids
            )
        elif matched_new is not None and score >= SIMILARITY_THRESHOLD:
            _handle_partial_match(
                preserved_comp, matched_new, conflicts, matched_new_ids
            )
        else:
            preserved_comp.match_status = "missing"
            preserved_comp.match_details = "Experience not found in new workspace"
            missing.append(preserved_comp)

    _find_duplicates(preserved, possible_duplicates)
    return matching, missing, changed_dates, possible_duplicates, conflicts



def _handle_strong_match(
    preserved_comp: CompatibilityExperience,
    matched_new: dict[str, Any],
    matching: list[CompatibilityExperience],
    changed_dates: list[CompatibilityExperience],
    matched_new_ids: set[str],
) -> None:
    new_start = str(matched_new.get("start_date") or "")
    new_end = str(matched_new.get("end_date") or "")
    date_changed = (
        _normalize(preserved_comp.start_date) != _normalize(new_start)
        or _normalize(preserved_comp.end_date) != _normalize(new_end)
    )
    if date_changed:
        new_comp = CompatibilityExperience(
            experience_id=str(matched_new.get("experience_id") or ""),
            title=str(matched_new.get("title") or ""),
            company=str(matched_new.get("company") or ""),
            start_date=new_start,
            end_date=new_end,
            description=str(matched_new.get("description") or ""),
            skills=[str(s) for s in (matched_new.get("skills") or []) if str(s).strip()],
            source="new",
            match_status="changed_date",
            match_details=(
                f"Dates changed: {preserved_comp.start_date}→{new_start}, "
                f"{preserved_comp.end_date}→{new_end}"
            ),
        )
        changed_dates.append(preserved_comp)
        changed_dates.append(new_comp)
    else:
        preserved_comp.match_status = "match"
        preserved_comp.match_details = "Experience found in new workspace"
        matching.append(preserved_comp)
    matched_new_ids.add(str(matched_new.get("experience_id") or ""))


def _handle_partial_match(
    preserved_comp: CompatibilityExperience,
    matched_new: dict[str, Any],
    conflicts: list[CompatibilityExperience],
    matched_new_ids: set[str],
) -> None:
    new_title = str(matched_new.get("title") or "")
    score = _fuzzy_match_score(
        _build_exp_text({"title": preserved_comp.title, "description": preserved_comp.description}),
        _build_exp_text(matched_new),
    )
    preserved_comp.match_status = "conflict"
    preserved_comp.match_details = (
        f"Partial match ({score:.0%}) with '{new_title}'. Review and confirm to proceed."
    )
    conflicts.append(preserved_comp)
    new_comp = CompatibilityExperience(
        experience_id=str(matched_new.get("experience_id") or ""),
        title=new_title,
        company=str(matched_new.get("company") or ""),
        start_date=str(matched_new.get("start_date") or ""),
        end_date=str(matched_new.get("end_date") or ""),
        description=str(matched_new.get("description") or ""),
        skills=[str(s) for s in (matched_new.get("skills") or []) if str(s).strip()],
        source="new",
        match_status="conflict",
        match_details=f"Partial match ({score:.0%}) with '{preserved_comp.title}'",
    )
    conflicts.append(new_comp)
    matched_new_ids.add(str(matched_new.get("experience_id") or ""))


def _find_duplicates(
    preserved: list[dict[str, Any]],
    possible_duplicates: list[CompatibilityExperience],
) -> None:
    seen_tokens: dict[str, str] = {}
    for exp in preserved:
        key = " ".join(sorted(_tokenize(
            str(exp.get("title", "")) + str(exp.get("description", ""))
        )))
        if not key:
            continue
        if key in seen_tokens and len(key) > 5:
            possible_duplicates.append(CompatibilityExperience(
                experience_id=str(exp.get("experience_id") or ""),
                title=str(exp.get("title") or ""),
                company=str(exp.get("company") or ""),
                start_date=str(exp.get("start_date") or ""),
                end_date=str(exp.get("end_date") or ""),
                description=str(exp.get("description") or ""),
                skills=[str(s) for s in (exp.get("skills") or []) if str(s).strip()],
                source="preserved",
                match_status="duplicate",
                match_details=f"Possible duplicate of experience '{seen_tokens[key]}'",
            ))
        seen_tokens[key] = str(exp.get("title") or str(exp.get("experience_id") or ""))



def _build_summary(review: RebindCompatibilityReview) -> None:
    """Build a human-readable summary of the compatibility review."""
    parts: list[str] = []
    if review.matching_experiences:
        parts.append(f"{len(review.matching_experiences)} matching experience(s) preserved.")
    if review.missing_experiences:
        parts.append(f"{len(review.missing_experiences)} experience(s) not found in new workspace.")
    if review.changed_dates:
        parts.append(f"{len(review.changed_dates)} date change(s) detected.")
    if review.possible_duplicates:
        parts.append(f"{len(review.possible_duplicates)} possible duplicate(s) found.")
    if review.conflicts:
        parts.append(f"{len(review.conflicts)} conflict(s) require your attention.")
    if not parts:
        parts.append("No preserved experiences found. Evidence will be carried forward as-is.")
    review.summary = " ".join(parts)


def perform_rebind_compatibility_review(
    profile: CareerProfile,
    workspace: Any,
    *,
    baseline_cv_asset_id: str = "",
) -> RebindCompatibilityReview:
    """Run a compatibility review for rebinding a profile to a new workspace."""
    review = RebindCompatibilityReview.create(
        profile_id=profile.profile_id,
        workspace_id=str(getattr(workspace, "id", "") or ""),
        baseline_cv_asset_id=baseline_cv_asset_id,
    )
    preserved_experiences = _extract_preserved_experiences(profile)
    new_experiences = _extract_new_experiences(workspace, baseline_cv_asset_id)
    (
        review.matching_experiences,
        review.missing_experiences,
        review.changed_dates,
        review.possible_duplicates,
        review.conflicts,
    ) = _compare_experiences(preserved_experiences, new_experiences)
    review.requires_confirmation = bool(review.conflicts)
    _build_summary(review)
    return review



def execute_rebind(
    profile: CareerProfile,
    workspace: Any,
    review: RebindCompatibilityReview,
    *,
    baseline_cv_asset_id: str = "",
    confirmed_conflicts: list[str] | None = None,
) -> CareerProfile:
    """Execute the rebind, preserving existing evidence in metadata."""
    confirmed_set = set(confirmed_conflicts or [])

    # Verify all conflicts are confirmed
    conflict_ids = {c.experience_id for c in review.conflicts}
    unresolved = conflict_ids - confirmed_set
    if unresolved:
        raise ValueError(
            f"Conflicts must be confirmed before rebinding. "
            f"Unconfirmed: {', '.join(sorted(unresolved))}"
        )

    metadata = dict(profile.metadata or {})
    preserved_experiences = _extract_preserved_experiences(profile)

    # Tag each preserved experience with its rebind status
    matching_ids = {e.experience_id for e in review.matching_experiences}
    missing_ids = {e.experience_id for e in review.missing_experiences}
    rebind_preserved: list[dict[str, Any]] = []
    for exp in preserved_experiences:
        entry = dict(exp)
        exp_id = str(exp.get("experience_id") or "")
        if exp_id in matching_ids:
            entry["rebind_status"] = "matched"
        elif exp_id in missing_ids:
            entry["rebind_status"] = "carried_forward"
        else:
            entry["rebind_status"] = "preserved"
        rebind_preserved.append(entry)

    metadata["preserved_experiences"] = rebind_preserved

    # Append to rebind history
    rebind_history: list[dict[str, Any]] = list(metadata.get("rebind_history") or [])
    rebind_history.append({
        "review_id": review.review_id,
        "previous_workspace_id": str(metadata.get("unbound_former_workspace_id") or ""),
        "new_workspace_id": str(getattr(workspace, "id", "") or ""),
        "rebound_at": utc_now_iso(),
        "matches": len(review.matching_experiences),
        "missing": len(review.missing_experiences),
        "changed_dates": len(review.changed_dates) // 2,
        "possible_duplicates": len(review.possible_duplicates),
        "conflicts_resolved": len(confirmed_set),
    })
    metadata["rebind_history"] = rebind_history

    # Clear unbound metadata
    metadata.pop("unbound_reason", None)
    metadata.pop("unbound_at", None)
    metadata.pop("unbound_former_workspace_id", None)

    profile.bound_workspace_id = str(getattr(workspace, "id", "") or "")
    profile.status = CAREER_PROFILE_STATUS_NOT_STARTED
    profile.metadata = metadata
    profile.updated_at = utc_now_iso()

    if baseline_cv_asset_id:
        profile.baseline_cv_asset_id = baseline_cv_asset_id
        profile.baseline_cv_extraction_date = utc_now_iso()

    return profile
