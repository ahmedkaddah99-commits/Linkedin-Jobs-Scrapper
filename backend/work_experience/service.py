"""Work experience service for career profiles.

Provides CRUD operations, extraction from candidate assets, and
merge-suggestion logic for work experience records.
"""

from __future__ import annotations

import re
from copy import deepcopy
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping

from backend.domain.models import (
    MERGE_SUGGESTION_STATUS_CONFIRMED,
    MERGE_SUGGESTION_STATUS_DISMISSED,
    MERGE_SUGGESTION_STATUS_PENDING,
    WORK_EXPERIENCE_SOURCE_KIND_EXTRACTED,
    WORK_EXPERIENCE_SOURCE_KIND_MANUAL,
    WORK_EXPERIENCE_STATUS_ACTIVE,
    WORK_EXPERIENCE_STATUS_MERGED,
    MergeSuggestion,
    WorkExperienceRecord,
    utc_now_iso,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_EXPERIENCES_KEY = "work_experiences"
_MERGE_SUGGESTIONS_KEY = "work_experience_merge_suggestions"


def _normalize(text: str) -> str:
    return str(text or "").strip().lower()


def _tokenize(text: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", _normalize(text))
    return {token for token in cleaned.split() if len(token) > 1}


def _fuzzy_score(text_a: str, text_b: str) -> float:
    normalized_a = _normalize(text_a)
    normalized_b = _normalize(text_b)
    if not normalized_a or not normalized_b:
        return 0.0
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    token_score = len(intersection) / len(union) if union else 0.0
    character_score = SequenceMatcher(None, normalized_a, normalized_b).ratio()
    return max(token_score, character_score)


def _read_experiences(profile_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    raw = profile_metadata.get(_EXPERIENCES_KEY)
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    return []


def _write_experiences(profile_metadata: dict[str, Any], experiences: list[dict[str, Any]]) -> None:
    profile_metadata[_EXPERIENCES_KEY] = list(experiences)


def _read_merge_suggestions(profile_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    raw = profile_metadata.get(_MERGE_SUGGESTIONS_KEY)
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    return []


def _write_merge_suggestions(profile_metadata: dict[str, Any], suggestions: list[dict[str, Any]]) -> None:
    profile_metadata[_MERGE_SUGGESTIONS_KEY] = list(suggestions)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def list_experiences(profile) -> list[WorkExperienceRecord]:
    """Return all active work experience records for a career profile."""
    metadata = dict(profile.metadata or {})
    raw = _read_experiences(metadata)
    records = [WorkExperienceRecord.from_dict(item) for item in raw]
    active = [r for r in records if r.status == WORK_EXPERIENCE_STATUS_ACTIVE]
    active.sort(key=lambda r: (r.sort_order, r.start_date or "9999", r.created_at or ""))
    return active


def get_experience(profile, experience_id: str) -> WorkExperienceRecord | None:
    metadata = dict(profile.metadata or {})
    raw = _read_experiences(metadata)
    for item in raw:
        if str(item.get("experience_id") or "") == experience_id:
            return WorkExperienceRecord.from_dict(item)
    return None


def create_experience(profile, payload: Mapping[str, Any]) -> WorkExperienceRecord:
    metadata = dict(profile.metadata or {})
    raw = _read_experiences(metadata)
    existing_sort = max((int(item.get("sort_order") or 0) for item in raw), default=-1)
    record = WorkExperienceRecord.create(
        profile_id=profile.profile_id,
        employer=str(payload.get("employer") or ""),
        job_title=str(payload.get("job_title") or ""),
        location=str(payload.get("location") or ""),
        start_date=str(payload.get("start_date") or ""),
        end_date=str(payload.get("end_date") or ""),
        employment_type=str(payload.get("employment_type") or ""),
        description=str(payload.get("description") or ""),
        source_kind=str(payload.get("source_kind") or WORK_EXPERIENCE_SOURCE_KIND_MANUAL),
        source_asset_ids=list(payload.get("source_asset_ids") or []),
        sort_order=existing_sort + 1,
    )
    raw.append(record.to_dict())
    _write_experiences(metadata, raw)
    profile.metadata = metadata
    profile.updated_at = utc_now_iso()
    return record


def update_experience(profile, experience_id: str, payload: Mapping[str, Any]) -> WorkExperienceRecord:
    metadata = dict(profile.metadata or {})
    raw = _read_experiences(metadata)
    updatable_fields = ("employer", "job_title", "location", "start_date", "end_date",
                        "employment_type", "description")
    for idx, item in enumerate(raw):
        if str(item.get("experience_id") or "") == experience_id:
            record = WorkExperienceRecord.from_dict(item)
            for field_name in updatable_fields:
                if field_name in payload:
                    setattr(record, field_name, str(payload[field_name] or "").strip())
            if "source_kind" in payload:
                record.source_kind = str(payload["source_kind"] or WORK_EXPERIENCE_SOURCE_KIND_MANUAL)
            if "source_asset_ids" in payload:
                record.source_asset_ids = [str(a).strip() for a in payload["source_asset_ids"] or [] if str(a).strip()]
            if "sort_order" in payload:
                record.sort_order = int(payload["sort_order"] or 0)
            if "status" in payload:
                status = str(payload["status"] or "").strip()
                if status:
                    record.status = status
            record.updated_at = utc_now_iso()
            raw[idx] = record.to_dict()
            _write_experiences(metadata, raw)
            profile.metadata = metadata
            profile.updated_at = utc_now_iso()
            return record
    raise KeyError(f"Work experience '{experience_id}' not found.")


def delete_experience(profile, experience_id: str) -> None:
    metadata = dict(profile.metadata or {})
    raw = _read_experiences(metadata)
    updated = [item for item in raw if str(item.get("experience_id") or "") != experience_id]
    if len(updated) == len(raw):
        raise KeyError(f"Work experience '{experience_id}' not found.")
    _write_experiences(metadata, updated)
    suggestions = _read_merge_suggestions(metadata)
    suggestions = [s for s in suggestions if experience_id not in (s.get("experience_ids") or [])]
    _write_merge_suggestions(metadata, suggestions)
    profile.metadata = metadata
    profile.updated_at = utc_now_iso()


# ---------------------------------------------------------------------------
# extraction from candidate assets
# ---------------------------------------------------------------------------

def _candidate_assets(user) -> dict[str, dict[str, Any]]:
    return {
        str(asset.get("asset_id") or ""): dict(asset)
        for asset in (user.metadata or {}).get("candidate_assets") or []
        if isinstance(asset, Mapping) and str(asset.get("asset_id") or "")
    }


def extract_experiences(profile, user, source_asset_ids: Iterable[str]) -> list[WorkExperienceRecord]:
    """Extract work experience records from candidate assets using heuristics."""
    selected_ids = [str(item).strip() for item in source_asset_ids if str(item).strip()]
    if not selected_ids:
        return []

    assets = _candidate_assets(user)
    missing = [aid for aid in selected_ids if aid not in assets]
    if missing:
        raise ValueError(f"Source assets not found: {', '.join(missing)}")

    extracted: list[WorkExperienceRecord] = []
    metadata = dict(profile.metadata or {})
    raw = _read_experiences(metadata)
    existing_sort = max((int(item.get("sort_order") or 0) for item in raw), default=-1)

    for asset_id in selected_ids:
        asset = assets[asset_id]
        asset_metadata = dict(asset.get("metadata") or {})
        source_text = str(asset_metadata.get("source_text") or asset_metadata.get("text") or "")
        if not source_text:
            continue

        experiences = _heuristic_parse_experiences(source_text)

        for exp_data in experiences:
            existing_sort += 1
            record = WorkExperienceRecord.create(
                profile_id=profile.profile_id,
                employer=exp_data.get("employer", ""),
                job_title=exp_data.get("job_title", ""),
                location=exp_data.get("location", ""),
                start_date=exp_data.get("start_date", ""),
                end_date=exp_data.get("end_date", ""),
                employment_type=exp_data.get("employment_type", ""),
                description=exp_data.get("description", ""),
                source_kind=WORK_EXPERIENCE_SOURCE_KIND_EXTRACTED,
                source_asset_ids=[asset_id],
                sort_order=existing_sort,
                metadata={"extraction_source_asset_id": asset_id},
            )
            extracted.append(record)
            raw.append(record.to_dict())

    _write_experiences(metadata, raw)
    profile.metadata = metadata
    profile.updated_at = utc_now_iso()
    return extracted


def _heuristic_parse_experiences(text: str) -> list[dict[str, Any]]:
    """Naive heuristic parser for work experience blocks in CV text."""
    results: list[dict[str, Any]] = []

    blocks = re.split(r"\n\s*\n|\n[-–—]{3,}\n", text)

    for block in blocks:
        block = block.strip()
        if len(block) < 20:
            continue

        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue

        entry: dict[str, Any] = {
            "employer": "",
            "job_title": "",
            "location": "",
            "start_date": "",
            "end_date": "",
            "employment_type": "",
            "description": "",
        }

        first_line = lines[0]
        at_match = re.match(r"(.+?)\s+at\s+(.+)", first_line, re.I)
        dash_match = re.match(r"(.+?)\s*[-–—]\s*(.+)", first_line)

        if at_match:
            entry["job_title"] = at_match.group(1).strip()
            entry["employer"] = at_match.group(2).strip()
        elif dash_match and len(lines) >= 2:
            entry["employer"] = dash_match.group(1).strip()
            entry["job_title"] = dash_match.group(2).strip()
        else:
            entry["employer"] = first_line.strip()

        date_pattern = re.compile(
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4})\s*[-–—]\s*"
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}|Present|Current)",
            re.I,
        )
        year_pattern = re.compile(r"(\d{4})\s*[-–—]\s*(\d{4}|Present|Current)", re.I)

        for line in lines[1:]:
            date_match = date_pattern.search(line) or year_pattern.search(line)
            if date_match:
                entry["start_date"] = date_match.group(1).strip()
                entry["end_date"] = date_match.group(2).strip()
                continue

            if re.search(r"(?:remote|hybrid|onsite|on-site)", line, re.I):
                loc_match = re.search(
                    r"(remote|hybrid|onsite|on-site|[\w\s]+,\s*\w{2})", line, re.I
                )
                if loc_match:
                    entry["location"] = loc_match.group(1).strip()

            for etype in ("full.time", "part.time", "contract", "freelance", "internship", "self.employed"):
                if re.search(etype, line, re.I):
                    entry["employment_type"] = etype.replace(".", "_")
                    break

        desc_lines = []
        for line in lines[1:]:
            if not date_pattern.search(line) and not year_pattern.search(line):
                desc_lines.append(line)
        entry["description"] = "\n".join(desc_lines).strip()

        if entry["employer"] or entry["job_title"]:
            results.append(entry)

    return results


# ---------------------------------------------------------------------------
# merge suggestions
# ---------------------------------------------------------------------------

MERGE_SIMILARITY_THRESHOLD = 0.55
MERGE_HIGH_CONFIDENCE_THRESHOLD = 0.80


def get_merge_suggestions(profile) -> list[MergeSuggestion]:
    """Generate merge suggestions for potentially duplicate work experiences."""
    experiences = list_experiences(profile)
    if len(experiences) < 2:
        return []

    metadata = dict(profile.metadata or {})
    raw = _read_merge_suggestions(metadata)

    existing = [
        MergeSuggestion.from_dict(item)
        for item in raw
        if item.get("status") == MERGE_SUGGESTION_STATUS_PENDING
    ]
    if existing:
        return existing

    suggestions: list[MergeSuggestion] = []
    seen_pairs: set[tuple[str, str]] = set()

    for i, exp_a in enumerate(experiences):
        for j, exp_b in enumerate(experiences):
            if j <= i:
                continue
            pair = (exp_a.experience_id, exp_b.experience_id)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            score = _compute_merge_score(exp_a, exp_b)
            if score >= MERGE_SIMILARITY_THRESHOLD:
                merged_record = _build_merged_record(exp_a, exp_b, score)
                reason = _merge_reason(exp_a, exp_b, score)
                suggestion = MergeSuggestion.create(
                    profile_id=profile.profile_id,
                    experience_ids=[exp_a.experience_id, exp_b.experience_id],
                    suggested_merged_record=merged_record,
                    match_score=score,
                    match_reason=reason,
                )
                suggestions.append(suggestion)
                raw.append(suggestion.to_dict())

    _write_merge_suggestions(metadata, raw)
    profile.metadata = metadata
    profile.updated_at = utc_now_iso()
    return suggestions


def _compute_merge_score(a: WorkExperienceRecord, b: WorkExperienceRecord) -> float:
    weighted_scores = [
        (_fuzzy_score(a.employer, b.employer), 0.45),
        (_fuzzy_score(a.job_title, b.job_title), 0.35),
    ]
    if a.location and b.location:
        weighted_scores.append((_fuzzy_score(a.location, b.location), 0.20))
    available_weight = sum(weight for _, weight in weighted_scores)
    weighted = sum(score * weight for score, weight in weighted_scores)
    return round(weighted / available_weight, 4) if available_weight else 0.0


def _build_merged_record(a: WorkExperienceRecord, b: WorkExperienceRecord, score: float) -> dict[str, Any]:
    merged = a.to_dict()
    merged.pop("experience_id", None)
    merged.pop("created_at", None)
    merged.pop("updated_at", None)
    merged.pop("sort_order", None)

    for field in ("employer", "job_title", "location", "start_date", "end_date",
                  "employment_type", "description"):
        val_a = getattr(a, field, "")
        val_b = getattr(b, field, "")
        if val_a and val_b:
            merged[field] = val_a if len(str(val_a)) >= len(str(val_b)) else val_b
        elif val_b:
            merged[field] = val_b

    merged["source_asset_ids"] = sorted(set(a.source_asset_ids + b.source_asset_ids))
    merged["source_kind"] = WORK_EXPERIENCE_SOURCE_KIND_EXTRACTED
    merged["_merge_source_ids"] = [a.experience_id, b.experience_id]
    merged["_merge_score"] = score
    return merged


def _merge_reason(a: WorkExperienceRecord, b: WorkExperienceRecord, score: float) -> str:
    parts: list[str] = []
    if _fuzzy_score(a.employer, b.employer) >= 0.7:
        parts.append("same employer")
    if _fuzzy_score(a.job_title, b.job_title) >= 0.7:
        parts.append("similar title")
    if a.location and b.location and _fuzzy_score(a.location, b.location) >= 0.7:
        parts.append("same location")
    detail = ", ".join(parts) if parts else "similar experience details"
    return f"{detail} (score {score:.0%})"


def confirm_merge(profile, suggestion_id: str) -> WorkExperienceRecord:
    """Execute a merge: create merged record and mark originals as merged."""
    metadata = dict(profile.metadata or {})
    suggestions_raw = _read_merge_suggestions(metadata)
    suggestion_dict = None
    for item in suggestions_raw:
        if str(item.get("suggestion_id") or "") == suggestion_id:
            suggestion_dict = item
            break

    if suggestion_dict is None:
        raise KeyError(f"Merge suggestion '{suggestion_id}' not found.")

    suggestion = MergeSuggestion.from_dict(suggestion_dict)
    if suggestion.status not in (MERGE_SUGGESTION_STATUS_PENDING, ""):
        raise ValueError(f"Merge suggestion '{suggestion_id}' is already {suggestion.status}.")

    experiences_raw = _read_experiences(metadata)
    source_ids = set(suggestion.experience_ids)

    merged_data = dict(suggestion.suggested_merged_record)
    merged_data.pop("_merge_source_ids", None)
    merged_data.pop("_merge_score", None)
    merged_data.pop("experience_id", None)

    merged = WorkExperienceRecord.create(
        profile_id=profile.profile_id,
        employer=str(merged_data.get("employer") or ""),
        job_title=str(merged_data.get("job_title") or ""),
        location=str(merged_data.get("location") or ""),
        start_date=str(merged_data.get("start_date") or ""),
        end_date=str(merged_data.get("end_date") or ""),
        employment_type=str(merged_data.get("employment_type") or ""),
        description=str(merged_data.get("description") or ""),
        source_kind=WORK_EXPERIENCE_SOURCE_KIND_EXTRACTED,
        source_asset_ids=list(merged_data.get("source_asset_ids") or []),
        sort_order=min(
            int(item.get("sort_order") or 0)
            for item in experiences_raw
            if item.get("experience_id") in source_ids
        ),
    )

    for idx, item in enumerate(experiences_raw):
        if item.get("experience_id") in source_ids:
            item["status"] = WORK_EXPERIENCE_STATUS_MERGED
            item["merged_into_id"] = merged.experience_id
            item["updated_at"] = utc_now_iso()

    experiences_raw.append(merged.to_dict())
    _write_experiences(metadata, experiences_raw)

    for item in suggestions_raw:
        if str(item.get("suggestion_id") or "") == suggestion_id:
            item["status"] = MERGE_SUGGESTION_STATUS_CONFIRMED
            item["updated_at"] = utc_now_iso()
    _write_merge_suggestions(metadata, suggestions_raw)

    profile.metadata = metadata
    profile.updated_at = utc_now_iso()
    return merged


def dismiss_merge_suggestion(profile, suggestion_id: str) -> None:
    """Dismiss a merge suggestion without executing it."""
    metadata = dict(profile.metadata or {})
    suggestions_raw = _read_merge_suggestions(metadata)
    for item in suggestions_raw:
        if str(item.get("suggestion_id") or "") == suggestion_id:
            item["status"] = MERGE_SUGGESTION_STATUS_DISMISSED
            item["updated_at"] = utc_now_iso()
            _write_merge_suggestions(metadata, suggestions_raw)
            profile.metadata = metadata
            profile.updated_at = utc_now_iso()
            return
    raise KeyError(f"Merge suggestion '{suggestion_id}' not found.")
