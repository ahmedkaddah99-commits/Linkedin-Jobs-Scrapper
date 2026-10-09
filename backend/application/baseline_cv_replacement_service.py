"""Baseline CV replacement preview and confirmation service (CP-034)."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from backend.domain.models import (
    BASELINE_CV_DIFF_CATEGORY_ADDED,
    BASELINE_CV_DIFF_CATEGORY_CHANGED_BULLETS,
    BASELINE_CV_DIFF_CATEGORY_CHANGED_COMPANY,
    BASELINE_CV_DIFF_CATEGORY_CHANGED_DATES,
    BASELINE_CV_DIFF_CATEGORY_CHANGED_TITLE,
    BASELINE_CV_DIFF_CATEGORY_MATCHING,
    BASELINE_CV_DIFF_CATEGORY_REMOVED,
    BASELINE_CV_REPLACEMENT_ACTION_ADD,
    BASELINE_CV_REPLACEMENT_ACTION_IGNORE,
    BASELINE_CV_REPLACEMENT_ACTION_NEEDS_REVIEW,
    BASELINE_CV_REPLACEMENT_ACTIONS,
    BaselineCVBulletDiff,
    BaselineCVExperienceDiff,
    BaselineCVReplacementPreview,
    CareerProfile,
    utc_now_iso,
)

SIMILARITY_THRESHOLD_CV = 0.25
BULLET_SIMILARITY_THRESHOLD = 0.25


def _normalize(text: str) -> str:
    return str(text or "").strip().lower()


def _tokenize(text: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9\\s]", " ", _normalize(text))
    return {token for token in cleaned.split() if len(token) > 0}


def _fuzzy_score(text_a: str, text_b: str) -> float:
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)



def _parse_bullets(text: str) -> list[str]:
    """Split description text into individual bullet points."""
    if not text:
        return []
    raw = text.strip()
    parts = re.split(r"\n\s*(?:[-•*]|\d+\.)\s*", raw)
    if len(parts) <= 1:
        parts = [line.strip() for line in raw.split("\n") if line.strip()]
    else:
        parts = [p.strip() for p in parts if p.strip()]
    return parts if parts else [raw]


def _extract_cv_experiences(cv_text: str) -> list[dict[str, Any]]:
    """Parse CV text into structured experience entries."""
    if not cv_text or not cv_text.strip():
        return []
    experiences: list[dict[str, Any]] = []
    lines = [line.strip() for line in cv_text.split("\n") if line.strip()]
    current_exp: dict[str, Any] | None = None
    date_pattern = re.compile(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|"
        r"January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\\s*\\d{4}"
        r"|\\d{4}\\s*[-–—to]+\\s*(\\d{4}|Present|Current|now)",
        re.IGNORECASE,
    )
    for line in lines:
        has_date = bool(date_pattern.search(line))
        if has_date:
            if current_exp:
                experiences.append(current_exp)
            current_exp = {
                "experience_id": f"exp_{uuid4().hex[:12]}",
                "title": "",
                "company": "",
                "start_date": "",
                "end_date": "",
                "description": "",
                "skills": [],
            }
            dates = date_pattern.findall(line)
            if dates:
                current_exp["start_date"] = str(dates[0]).strip()
                if len(dates) > 1:
                    current_exp["end_date"] = str(dates[1]).strip()
            remaining = date_pattern.sub("", line).strip(" ,-–—|")
            if remaining:
                parts_list = [p.strip() for p in re.split(r"\\s*[|@·•–—]+\\s*", remaining, maxsplit=1)]
                current_exp["title"] = parts_list[0] if parts_list else ""
                current_exp["company"] = parts_list[1] if len(parts_list) > 1 else ""
            continue
        if current_exp is not None:
            if not current_exp["company"] and not current_exp["title"]:
                parts_list = [p.strip() for p in re.split(r"\\s*[|@·•–—]+\\s*", line, maxsplit=1)]
                current_exp["title"] = parts_list[0] if parts_list else ""
                current_exp["company"] = parts_list[1] if len(parts_list) > 1 else ""
            else:
                if current_exp["description"]:
                    current_exp["description"] += " "
                current_exp["description"] += line
    if current_exp:
        experiences.append(current_exp)
    if not experiences and cv_text.strip():
        experiences.append({
            "experience_id": f"exp_{uuid4().hex[:12]}",
            "title": "CV Experience",
            "company": "",
            "start_date": "",
            "end_date": "",
            "description": cv_text.strip(),
            "skills": [],
        })

    return experiences


def _compare_bullets(
    old_bullets: list[str], new_bullets: list[str]
) -> list[BaselineCVBulletDiff]:
    """Compare bullet points between old and new experiences."""
    diffs: list[BaselineCVBulletDiff] = []
    matched_new: set[int] = set()
    matched_old: set[int] = set()

    for old_idx, old_b in enumerate(old_bullets):
        best_score = 0.0
        best_new_idx = -1
        for new_idx, new_b in enumerate(new_bullets):
            if new_idx in matched_new:
                continue
            score = _fuzzy_score(old_b, new_b)
            if score > best_score:
                best_score = score
                best_new_idx = new_idx

        if best_score >= BULLET_SIMILARITY_THRESHOLD and best_new_idx >= 0:
            matched_old.add(old_idx)
            matched_new.add(best_new_idx)
            new_b = new_bullets[best_new_idx]
            if _normalize(old_b) != _normalize(new_b):
                diffs.append(BaselineCVBulletDiff(
                    bullet_id=f"bullet_{uuid4().hex[:12]}",
                    text=new_b,
                    diff_category="changed",
                    old_text=old_b,
                    new_text=new_b,
                ))
            else:
                diffs.append(BaselineCVBulletDiff(
                    bullet_id=f"bullet_{uuid4().hex[:12]}",
                    text=new_b,
                    diff_category="unchanged",
                    old_text=old_b,
                    new_text=new_b,
                ))

    for old_idx, old_b in enumerate(old_bullets):
        if old_idx not in matched_old:
            diffs.append(BaselineCVBulletDiff(
                bullet_id=f"bullet_{uuid4().hex[:12]}",
                text=old_b,
                diff_category="removed",
                old_text=old_b,
                new_text="",
            ))

    for new_idx, new_b in enumerate(new_bullets):
        if new_idx not in matched_new:
            diffs.append(BaselineCVBulletDiff(
                bullet_id=f"bullet_{uuid4().hex[:12]}",
                text=new_b,
                diff_category="added",
                old_text="",
                new_text=new_b,
            ))

    return diffs


def _compute_experience_diffs(
    old_experiences: list[dict[str, Any]],
    new_experiences: list[dict[str, Any]],
) -> list[BaselineCVExperienceDiff]:
    """Compute diffs between old and new CV experiences."""
    diffs: list[BaselineCVExperienceDiff] = []
    matched_new_ids: set[str] = set()

    for old_exp in old_experiences:
        old_id = str(old_exp.get("experience_id") or "")
        old_title = str(old_exp.get("title") or "")
        old_company = str(old_exp.get("company") or "")

        best_match: tuple[dict[str, Any] | None, float] = (None, 0.0)
        for new_exp in new_experiences:
            new_id = str(new_exp.get("experience_id") or "")
            if new_id in matched_new_ids:
                continue
            score = _fuzzy_score(
                f"{old_title} {old_company}",
                f"{new_exp.get('title', '')} {new_exp.get('company', '')}",
            )
            if score > best_match[1]:
                best_match = (new_exp, score)

        matched_new_exp, score = best_match
        if matched_new_exp is not None and score >= SIMILARITY_THRESHOLD_CV:
            matched_new_ids.add(str(matched_new_exp.get("experience_id") or ""))
            diffs.append(_build_matched_diff(old_exp, matched_new_exp, score))
        else:
            bullet_diffs = _compare_bullets(
                _parse_bullets(old_exp.get("description", "")), []
            )
            diffs.append(BaselineCVExperienceDiff(
                diff_id=f"diff_{uuid4().hex[:12]}",
                diff_category=BASELINE_CV_DIFF_CATEGORY_REMOVED,
                old_experience_id=old_id,
                new_experience_id="",
                old_title=old_title,
                new_title="",
                old_company=old_company,
                new_company="",
                old_start_date=str(old_exp.get("start_date") or ""),
                new_start_date="",
                old_end_date=str(old_exp.get("end_date") or ""),
                new_end_date="",
                old_description=str(old_exp.get("description") or ""),
                new_description="",
                bullet_diffs=bullet_diffs,
                old_skills=list(old_exp.get("skills", [])),
                new_skills=[],
                suggested_action=BASELINE_CV_REPLACEMENT_ACTION_NEEDS_REVIEW,
                match_score=0.0,
            ))

    for new_exp in new_experiences:
        new_id = str(new_exp.get("experience_id") or "")
        if new_id not in matched_new_ids:
            bullet_diffs = _compare_bullets(
                [], _parse_bullets(new_exp.get("description", ""))
            )
            diffs.append(BaselineCVExperienceDiff(
                diff_id=f"diff_{uuid4().hex[:12]}",
                diff_category=BASELINE_CV_DIFF_CATEGORY_ADDED,
                old_experience_id="",
                new_experience_id=new_id,
                old_title="",
                new_title=str(new_exp.get("title") or ""),
                old_company="",
                new_company=str(new_exp.get("company") or ""),
                old_start_date="",
                new_start_date=str(new_exp.get("start_date") or ""),
                old_end_date="",
                new_end_date=str(new_exp.get("end_date") or ""),
                old_description="",
                new_description=str(new_exp.get("description") or ""),
                bullet_diffs=bullet_diffs,
                old_skills=[],
                new_skills=list(new_exp.get("skills", [])),
                suggested_action=BASELINE_CV_REPLACEMENT_ACTION_ADD,
                match_score=0.0,
            ))

    return diffs


def _build_matched_diff(
    old_exp: dict[str, Any], new_exp: dict[str, Any], score: float
) -> BaselineCVExperienceDiff:
    """Build a diff for matched experiences, categorizing the differences."""
    old_title = str(old_exp.get("title") or "")
    new_title = str(new_exp.get("title") or "")
    old_company = str(old_exp.get("company") or "")
    new_company = str(new_exp.get("company") or "")
    old_start = str(old_exp.get("start_date") or "")
    new_start = str(new_exp.get("start_date") or "")
    old_end = str(old_exp.get("end_date") or "")
    new_end = str(new_exp.get("end_date") or "")
    old_desc = str(old_exp.get("description") or "")
    new_desc = str(new_exp.get("description") or "")

    title_changed = _normalize(old_title) != _normalize(new_title) and old_title and new_title
    company_changed = _normalize(old_company) != _normalize(new_company) and old_company and new_company
    dates_changed = (
        _normalize(old_start) != _normalize(new_start)
        or _normalize(old_end) != _normalize(new_end)
    )
    bullets_changed = _normalize(old_desc) != _normalize(new_desc)

    old_bullets = _parse_bullets(old_desc)
    new_bullets = _parse_bullets(new_desc)
    bullet_diffs = _compare_bullets(old_bullets, new_bullets)

    if title_changed:
        diff_category = BASELINE_CV_DIFF_CATEGORY_CHANGED_TITLE
    elif company_changed:
        diff_category = BASELINE_CV_DIFF_CATEGORY_CHANGED_COMPANY
    elif dates_changed:
        diff_category = BASELINE_CV_DIFF_CATEGORY_CHANGED_DATES
    elif bullets_changed:
        diff_category = BASELINE_CV_DIFF_CATEGORY_CHANGED_BULLETS
    else:
        diff_category = BASELINE_CV_DIFF_CATEGORY_MATCHING

    if diff_category == BASELINE_CV_DIFF_CATEGORY_MATCHING:
        suggested_action = BASELINE_CV_REPLACEMENT_ACTION_IGNORE
    elif diff_category == BASELINE_CV_DIFF_CATEGORY_CHANGED_BULLETS:
        suggested_action = BASELINE_CV_REPLACEMENT_ACTION_ADD
    else:
        suggested_action = BASELINE_CV_REPLACEMENT_ACTION_NEEDS_REVIEW

    return BaselineCVExperienceDiff(
        diff_id=f"diff_{uuid4().hex[:12]}",
        diff_category=diff_category,
        old_experience_id=str(old_exp.get("experience_id") or ""),
        new_experience_id=str(new_exp.get("experience_id") or ""),
        old_title=old_title,
        new_title=new_title,
        old_company=old_company,
        new_company=new_company,
        old_start_date=old_start,
        new_start_date=new_start,
        old_end_date=old_end,
        new_end_date=new_end,
        old_description=old_desc,
        new_description=new_desc,
        bullet_diffs=bullet_diffs,
        old_skills=list(old_exp.get("skills", [])),
        new_skills=list(new_exp.get("skills", [])),
        suggested_action=suggested_action,
        match_score=score,
    )


def _build_summary(preview: BaselineCVReplacementPreview) -> None:
    """Build a human-readable summary for the replacement preview."""
    parts: list[str] = []
    matching = sum(
        1 for d in preview.experience_diffs
        if d.diff_category == BASELINE_CV_DIFF_CATEGORY_MATCHING
    )
    added = sum(
        1 for d in preview.experience_diffs
        if d.diff_category == BASELINE_CV_DIFF_CATEGORY_ADDED
    )
    removed = sum(
        1 for d in preview.experience_diffs
        if d.diff_category == BASELINE_CV_DIFF_CATEGORY_REMOVED
    )
    changed_title = sum(
        1 for d in preview.experience_diffs
        if d.diff_category == BASELINE_CV_DIFF_CATEGORY_CHANGED_TITLE
    )
    changed_dates = sum(
        1 for d in preview.experience_diffs
        if d.diff_category == BASELINE_CV_DIFF_CATEGORY_CHANGED_DATES
    )
    changed_bullets = sum(
        1 for d in preview.experience_diffs
        if d.diff_category == BASELINE_CV_DIFF_CATEGORY_CHANGED_BULLETS
    )
    changed_company = sum(
        1 for d in preview.experience_diffs
        if d.diff_category == BASELINE_CV_DIFF_CATEGORY_CHANGED_COMPANY
    )

    if matching:
        parts.append(f"{matching} matching experience(s).")
    if added:
        parts.append(f"{added} new experience(s) added.")
    if removed:
        parts.append(f"{removed} experience(s) removed.")
    if changed_title:
        parts.append(f"{changed_title} title change(s).")
    if changed_company:
        parts.append(f"{changed_company} company change(s).")
    if changed_dates:
        parts.append(f"{changed_dates} date change(s).")
    if changed_bullets:
        parts.append(f"{changed_bullets} experience(s) with bullet changes.")
    if not parts:
        parts.append("No changes detected between old and proposed CV.")

    parts.append(
        "Existing evidence, provenance, lifecycle, mappings, "
        "timestamps, and history are preserved."
    )

    preview.summary = " ".join(parts)


def preview_baseline_cv_replacement(
    profile: CareerProfile,
    old_cv_text: str,
    proposed_cv_text: str,
    proposed_asset_id: str = "",
    proposed_display_name: str = "",
    proposed_source_version: str = "",
) -> BaselineCVReplacementPreview:
    """Generate a non-mutating preview of a baseline CV replacement."""
    metadata = dict(profile.metadata or {})
    evidence_count = 0
    preserved = (
        metadata.get("preserved_experiences")
        or metadata.get("preserved_evidence")
        or []
    )
    if isinstance(preserved, list):
        evidence_count = len(preserved)

    preview = BaselineCVReplacementPreview.create(
        profile_id=profile.profile_id,
        old_baseline_cv_asset_id=profile.baseline_cv_asset_id,
        old_baseline_cv_display_name=profile.baseline_cv_display_name,
        old_baseline_cv_source_version=profile.baseline_cv_source_version,
        proposed_baseline_cv_asset_id=proposed_asset_id,
        proposed_baseline_cv_display_name=proposed_display_name,
        proposed_baseline_cv_source_version=proposed_source_version,
    )

    old_experiences = _extract_cv_experiences(old_cv_text)
    new_experiences = _extract_cv_experiences(proposed_cv_text)

    preview.experience_diffs = _compute_experience_diffs(
        old_experiences, new_experiences
    )
    preview.existing_evidence_count = evidence_count

    preserved_count = 1
    if profile.baseline_cv_extraction_date:
        preserved_count += 1
    if profile.updated_at:
        preserved_count += 1

    preview.preserved_timestamp_count = preserved_count
    preview.requires_confirmation = len(preview.experience_diffs) > 0
    _build_summary(preview)
    return preview


def confirm_baseline_cv_replacement(
    profile: CareerProfile,
    preview: BaselineCVReplacementPreview,
    *,
    accepted_actions: dict[str, str] | None = None,
) -> CareerProfile:
    """Atomically confirm a baseline CV replacement.

    Validates preview is not stale and applies the replacement.
    Existing evidence, provenance, lifecycle, mappings, and history
    are preserved. Only the baseline CV binding is updated.
    """
    if accepted_actions is None:
        accepted_actions = {}

    if preview.profile_id != profile.profile_id:
        raise ValueError("Preview does not belong to this profile.")

    if not preview.proposed_baseline_cv_asset_id:
        raise ValueError("Proposed CV asset ID is required.")

    diff_ids = {d.diff_id for d in preview.experience_diffs}
    for diff_id, action in accepted_actions.items():
        if diff_id not in diff_ids:
            raise ValueError(f"Unknown diff_id: {diff_id}")
        if action not in BASELINE_CV_REPLACEMENT_ACTIONS:
            raise ValueError(
                f"Invalid action '{action}' for diff '{diff_id}'. "
                f"Must be one of: {', '.join(sorted(BASELINE_CV_REPLACEMENT_ACTIONS))}"
            )

    metadata = dict(profile.metadata or {})

    replacement_history: list[dict[str, Any]] = list(
        metadata.get("baseline_cv_replacement_history") or []
    )
    replacement_history.append({
        "preview_id": preview.preview_id,
        "previous_baseline_cv_asset_id": preview.old_baseline_cv_asset_id,
        "new_baseline_cv_asset_id": preview.proposed_baseline_cv_asset_id,
        "replaced_at": utc_now_iso(),
        "accepted_actions": dict(accepted_actions),
        "diff_summary": {
            "total_diffs": len(preview.experience_diffs),
            "matching": sum(
                1 for d in preview.experience_diffs
                if d.diff_category == BASELINE_CV_DIFF_CATEGORY_MATCHING
            ),
            "added": sum(
                1 for d in preview.experience_diffs
                if d.diff_category == BASELINE_CV_DIFF_CATEGORY_ADDED
            ),
            "removed": sum(
                1 for d in preview.experience_diffs
                if d.diff_category == BASELINE_CV_DIFF_CATEGORY_REMOVED
            ),
            "changed": sum(
                1 for d in preview.experience_diffs
                if d.diff_category not in (
                    BASELINE_CV_DIFF_CATEGORY_MATCHING,
                    BASELINE_CV_DIFF_CATEGORY_ADDED,
                    BASELINE_CV_DIFF_CATEGORY_REMOVED,
                )
            ),
        },
    })
    metadata["baseline_cv_replacement_history"] = replacement_history

    accepted_facts: list[dict[str, Any]] = []
    for diff in preview.experience_diffs:
        action = accepted_actions.get(diff.diff_id, diff.suggested_action)
        accepted_facts.append({
            "diff_id": diff.diff_id,
            "diff_category": diff.diff_category,
            "action": action,
            "new_experience_id": diff.new_experience_id,
            "new_title": diff.new_title,
            "new_company": diff.new_company,
            "reference_cv_asset_id": preview.proposed_baseline_cv_asset_id,
        })
    metadata["baseline_cv_accepted_facts"] = accepted_facts

    profile.baseline_cv_asset_id = preview.proposed_baseline_cv_asset_id
    profile.baseline_cv_display_name = preview.proposed_baseline_cv_display_name
    profile.baseline_cv_source_version = preview.proposed_baseline_cv_source_version
    profile.baseline_cv_extraction_date = utc_now_iso()
    profile.metadata = metadata
    profile.updated_at = utc_now_iso()

    return profile
