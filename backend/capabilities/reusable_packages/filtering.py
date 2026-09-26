from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any, Dict, List, Mapping

from .support import (
    cfg_bool,
    cfg_list,
    cfg_str,
    compact_whitespace,
    load_reusable_packages_config,
    load_json_file,
    resolve_path,
    save_json_file,
)


def normalize_token(value: str) -> str:
    normalized = compact_whitespace(value).lower()
    replacements = {
        "Ã¤": "ae",
        "Ã¶": "oe",
        "Ã¼": "ue",
        "ÃŸ": "ss",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return compact_whitespace(normalized)


def city_matches(location_raw: str, target_cities: List[str]) -> bool:
    location_token = normalize_token(location_raw)
    if not location_token:
        return False
    for city in target_cities:
        city_token = normalize_token(city)
        if city_token and city_token in location_token:
            return True
    return False


DRIVER_LICENSE_REQUIRED_PATTERNS = [
    re.compile(r"\b(driver'?s?\s+license|driving\s+license|fuehrerschein|f[Ã¼u]hrerschein)\b", re.IGNORECASE),
    re.compile(r"\b(klasse|class)\s*[bce1-9]+\b", re.IGNORECASE),
    re.compile(r"\b(lkw[-\s]?f[Ã¼u]hrerschein|cdl)\b", re.IGNORECASE),
]

SPECIAL_TRAINING_REQUIRED_PATTERNS = [
    re.compile(r"\b(staplerschein|forklift\s+certificate)\b", re.IGNORECASE),
    re.compile(r"\b(kranschein|welding\s+certificate|schwei[ÃŸs]erschein)\b", re.IGNORECASE),
    re.compile(r"\b(sachkunde|meisterbrief|ihk)\b", re.IGNORECASE),
    re.compile(r"\b(certification|zertifikat|certificate)\b", re.IGNORECASE),
    re.compile(r"\b(abgeschlossene\s+ausbildung|berufsausbildung|vocational\s+training)\b", re.IGNORECASE),
]

NEGATING_HINT_PATTERNS = [
    re.compile(r"\b(kein|keine|keinen|ohne|not required|nicht erforderlich)\b", re.IGNORECASE),
]

MANDATORY_HINT_PATTERNS = [
    re.compile(r"\b(required|mandatory|must|zwingend|erforderlich|voraussetzung|notwendig)\b", re.IGNORECASE),
]


def _looks_mandatory(text: str, match_start: int, match_end: int) -> bool:
    left = max(0, match_start - 70)
    right = min(len(text), match_end + 70)
    window = text[left:right]
    if any(pattern.search(window) for pattern in NEGATING_HINT_PATTERNS):
        return False
    if any(pattern.search(window) for pattern in MANDATORY_HINT_PATTERNS):
        return True
    return True


def find_requirement_reason(text: str, patterns: List[re.Pattern], label: str) -> str:
    source = text or ""
    for pattern in patterns:
        for match in pattern.finditer(source):
            if _looks_mandatory(source, match.start(), match.end()):
                return f"{label}: {compact_whitespace(match.group(0))}"
    return ""


def detect_reasons(
    job: Dict,
    target_cities: List[str],
    exclude_driver_license_required: bool,
    exclude_special_training_required: bool,
) -> List[str]:
    reasons: List[str] = []
    location_raw = str(job.get("location_raw") or "")
    text_blob = "\n".join(
        [
            str(job.get("title") or ""),
            str(job.get("description") or ""),
            str(job.get("snippet") or ""),
        ]
    )

    if not city_matches(location_raw, target_cities):
        reasons.append("City not in configured city filter")

    if exclude_driver_license_required:
        driver_reason = find_requirement_reason(text_blob, DRIVER_LICENSE_REQUIRED_PATTERNS, "Requires driver's license")
        if driver_reason:
            reasons.append(driver_reason)

    if exclude_special_training_required:
        training_reason = find_requirement_reason(
            text_blob,
            SPECIAL_TRAINING_REQUIRED_PATTERNS,
            "Requires special training/certification",
        )
        if training_reason:
            reasons.append(training_reason)

    return reasons


def build_stage2_args(
    config: dict | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> SimpleNamespace:
    config = config or load_reusable_packages_config()
    payload = {
        "input": cfg_str(config, ("runtime", "stage2", "input_json"), "outputs/stage1_scraped_jobs.json"),
        "output": cfg_str(config, ("runtime", "stage2", "output_json"), "outputs/stage2_filtered_jobs.json"),
        "rejected": cfg_str(config, ("runtime", "stage2", "rejected_output_json"), "outputs/stage2_rejected_jobs.json"),
        "cities": cfg_list(config, ("job_search", "cities"), []),
        "exclude_driver_license_required": cfg_bool(config, ("filters", "exclude_driver_license_required"), True),
        "exclude_special_training_required": cfg_bool(config, ("filters", "exclude_special_training_required"), True),
    }
    if overrides:
        payload.update({key: value for key, value in overrides.items() if value is not None})
    return SimpleNamespace(**payload)


def run_stage2_pipeline(args, *, config: dict | None = None, jobs: List[Dict] | None = None) -> dict[str, Any]:
    _ = config
    input_path = resolve_path(args.input)
    if jobs is None:
        if not input_path.exists():
            raise FileNotFoundError(f"input file not found: {input_path}")
        jobs = load_json_file(input_path)
        if not isinstance(jobs, list):
            raise ValueError("input JSON must be a list of jobs.")

    target_cities = [compact_whitespace(item) for item in args.cities if compact_whitespace(item)]
    if not target_cities:
        raise ValueError("--cities cannot be empty.")

    approved: List[Dict] = []
    rejected: List[Dict] = []
    for job in jobs:
        reasons = detect_reasons(
            job=job,
            target_cities=target_cities,
            exclude_driver_license_required=bool(args.exclude_driver_license_required),
            exclude_special_training_required=bool(args.exclude_special_training_required),
        )
        if reasons:
            rejected.append({**job, "stage2_filter_reasons": reasons, "stage2_filter_reason": " | ".join(reasons)})
        else:
            approved.append(job)

    output_path = resolve_path(args.output)
    rejected_path = resolve_path(args.rejected)
    save_json_file(output_path, approved)
    save_json_file(rejected_path, rejected)

    print("Stage 2 complete.")
    print("Note: language-based filtering is intentionally disabled.")
    print(f"Input jobs: {len(jobs)}")
    print(f"Approved jobs: {len(approved)} -> {output_path}")
    print(f"Rejected jobs: {len(rejected)} -> {rejected_path}")
    return {
        "approved_jobs": approved,
        "rejected_jobs": rejected,
        "output_path": str(output_path),
        "rejected_path": str(rejected_path),
    }
