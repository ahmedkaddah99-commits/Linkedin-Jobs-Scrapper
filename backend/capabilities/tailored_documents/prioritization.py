from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from backend.config.job_seeker import cfg_bool, cfg_int, cfg_str, load_job_seeker_config

from .common import load_json_file, save_json_file
from .language_rules import (
    DEFAULT_FRENCH_SPECIAL_CHAR_THRESHOLD,
    DEFAULT_GERMAN_SPECIAL_CHAR_THRESHOLD,
    DEFAULT_SPANISH_SPECIAL_CHAR_THRESHOLD,
    detect_reasons,
    normalize_cefr_level,
)


def _config_language_lines(config: dict) -> list[str]:
    candidate = config.get("candidate") if isinstance(config, dict) else {}
    if not isinstance(candidate, dict):
        return []
    raw_languages = candidate.get("languages")
    if isinstance(raw_languages, str):
        return [item.strip() for item in raw_languages.replace(",", "\n").splitlines() if item.strip()]
    if isinstance(raw_languages, (list, tuple, set)):
        return [str(item).strip() for item in raw_languages if str(item).strip()]
    return []


def build_stage3_args(
    config: dict | None = None,
    overrides: dict[str, Any] | None = None,
) -> SimpleNamespace:
    config = config or load_job_seeker_config()
    payload = {
        "input": cfg_str(config, ("runtime", "stage3", "input_json"), "stage2_filtered_local.json"),
        "output": cfg_str(config, ("runtime", "stage3", "output_json"), "stage3_filtered_ai.json"),
        "rejected": cfg_str(config, ("runtime", "stage3", "rejected_output_json"), "stage3_rejected_local.json"),
        "checkpoint": cfg_str(config, ("runtime", "stage3", "checkpoint_json"), "stage3_checkpoint.json"),
        "force_reprocess": cfg_bool(config, ("runtime", "stage3", "force_reprocess"), False),
        "low_applicant_threshold": cfg_int(config, ("job_search", "priority", "low_applicant_threshold"), 80),
        "stage3_german_special_char_threshold": cfg_int(
            config,
            ("runtime", "stage3", "german_special_char_threshold"),
            cfg_int(
                config,
                ("runtime", "stage2", "german_special_char_threshold"),
                DEFAULT_GERMAN_SPECIAL_CHAR_THRESHOLD,
            ),
        ),
        "stage3_french_special_char_threshold": cfg_int(
            config,
            ("runtime", "stage3", "french_special_char_threshold"),
            cfg_int(
                config,
                ("runtime", "stage2", "french_special_char_threshold"),
                DEFAULT_FRENCH_SPECIAL_CHAR_THRESHOLD,
            ),
        ),
        "stage3_spanish_special_char_threshold": cfg_int(
            config,
            ("runtime", "stage3", "spanish_special_char_threshold"),
            cfg_int(
                config,
                ("runtime", "stage2", "spanish_special_char_threshold"),
                DEFAULT_SPANISH_SPECIAL_CHAR_THRESHOLD,
            ),
        ),
        "stage3_max_german_level": cfg_str(
            config,
            ("runtime", "stage3", "max_german_level"),
            cfg_str(config, ("runtime", "stage2", "max_german_level"), "B2"),
        ),
        "stage3_extra_prompt": "",
        "stage3_prompt_override": "",
        "languages": _config_language_lines(config),
    }
    if overrides:
        payload.update({key: value for key, value in overrides.items() if value is not None})
    return SimpleNamespace(**payload)


def split_python_prefilter_language_chars(
    jobs: list[dict[str, Any]],
    german_special_char_threshold: int,
    french_special_char_threshold: int,
    spanish_special_char_threshold: int,
    max_german_level: str,
    profile_languages: Any = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    approved_jobs: list[dict[str, Any]] = []
    rejected_jobs: list[dict[str, Any]] = []

    for job in jobs:
        reasons = detect_reasons(
            job,
            german_special_char_threshold,
            french_special_char_threshold,
            spanish_special_char_threshold,
            max_german_level,
            profile_languages,
        )
        if reasons:
            rejected_jobs.append(
                {
                    **job,
                    "stage3_filter_reasons": reasons,
                    "stage3_filter_reason": " | ".join(reasons),
                    "stage3_python_prefilter": "local_language_rules",
                }
            )
        else:
            approved_jobs.append(job)

    return approved_jobs, rejected_jobs


def coerce_applicant_count(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        import re

        digits = re.sub(r"[^\d]", "", str(value))
        return int(digits) if digits else None


def priority_tier(job: dict[str, Any], low_applicant_threshold: int) -> int:
    easy = job.get("easy_apply_status") is True
    applicants = coerce_applicant_count(job.get("applicant_count"))
    low_applicants = applicants is not None and applicants <= low_applicant_threshold

    if low_applicants and not easy:
        return 1
    if low_applicants and easy:
        return 2
    if not low_applicants and not easy:
        return 3
    return 4


def priority_sort_key(job: dict[str, Any], low_applicant_threshold: int):
    posted_age = job.get("posted_age_hours")
    posted_missing = posted_age is None
    posted_value = float(posted_age) if not posted_missing else float("inf")

    applicants = coerce_applicant_count(job.get("applicant_count"))
    applicants_missing = applicants is None
    applicants_value = applicants if applicants is not None else 10**9

    return (
        priority_tier(job, low_applicant_threshold),
        1 if posted_missing else 0,
        posted_value,
        1 if applicants_missing else 0,
        applicants_value,
        str(job.get("job_id", "")),
    )


def sort_and_rank_jobs(jobs: list[dict[str, Any]], low_applicant_threshold: int) -> list[dict[str, Any]]:
    ordered = sorted(jobs, key=lambda item: priority_sort_key(item, low_applicant_threshold))
    for index, job in enumerate(ordered, start=1):
        tier = priority_tier(job, low_applicant_threshold)
        tier_label = {
            1: "tier1_newest_non_easy_low_applicants",
            2: "tier2_newest_easy_low_applicants",
            3: "tier3_newest_non_easy_high_or_unknown_applicants",
            4: "tier4_newest_easy_high_or_unknown_applicants",
        }[tier]
        job["priority_rank"] = index
        job["priority_tier"] = tier
        job["priority_bucket"] = tier_label
        job["priority_rule"] = (
            "1)newest+non_easy+low_applicants,"
            "2)newest+easy+low_applicants,"
            "3)newest+non_easy+high_or_unknown_applicants,"
            "4)newest+easy+high_or_unknown_applicants"
        )
    return ordered


def run_stage3_pipeline(
    jobs: list[dict[str, Any]] | None = None,
    cli_args=None,
    *,
    config: dict | None = None,
    args=None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active_args = args or cli_args
    if active_args is None:
        raise ValueError("stage3 args are required")

    if jobs is None:
        input_path = Path(active_args.input)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        raw_jobs = load_json_file(input_path)
        if not isinstance(raw_jobs, list):
            raise ValueError("Input JSON must be a list of jobs.")
        jobs = raw_jobs

    approved, rejected = split_python_prefilter_language_chars(
        jobs,
        max(0, int(active_args.stage3_german_special_char_threshold)),
        max(0, int(active_args.stage3_french_special_char_threshold)),
        max(0, int(active_args.stage3_spanish_special_char_threshold)),
        active_args.stage3_max_german_level,
        getattr(active_args, "languages", []),
    )
    approved = sort_and_rank_jobs(approved, max(0, int(active_args.low_applicant_threshold)))
    save_json_file(Path(active_args.output), approved)
    save_json_file(Path(active_args.rejected), rejected)
    return approved, rejected


def main() -> int:
    config = load_job_seeker_config()
    defaults = build_stage3_args(config)

    parser = argparse.ArgumentParser(
        description="Stage 3 local filtering and prioritization on top of stage2-filtered jobs."
    )
    parser.add_argument("--input", default=defaults.input, help="Input JSON file from Stage 2.")
    parser.add_argument("--output", default=defaults.output, help="Approved jobs output.")
    parser.add_argument("--rejected", default=defaults.rejected, help="Rejected jobs output.")
    parser.add_argument("--checkpoint", default=defaults.checkpoint, help="Deprecated compatibility flag. No longer used.")
    parser.add_argument(
        "--low-applicant-threshold",
        type=int,
        default=defaults.low_applicant_threshold,
        help="Applicant count threshold for priority tiers.",
    )
    parser.add_argument("--stage3-extra-prompt", default="", help="Deprecated compatibility flag. No longer used.")
    parser.add_argument("--stage3-prompt-override", default="", help="Deprecated compatibility flag. No longer used.")
    parser.add_argument(
        "--force-reprocess",
        action=argparse.BooleanOptionalAction,
        default=defaults.force_reprocess,
        help="Deprecated compatibility flag. No longer used.",
    )
    parser.add_argument(
        "--german-special-char-threshold",
        type=int,
        default=max(0, int(defaults.stage3_german_special_char_threshold)),
        help="Reject only if German special-character count in title/description is above this threshold.",
    )
    parser.add_argument(
        "--french-special-char-threshold",
        type=int,
        default=max(0, int(defaults.stage3_french_special_char_threshold)),
        help="Reject only if French special-character count in title/description is above this threshold.",
    )
    parser.add_argument(
        "--spanish-special-char-threshold",
        type=int,
        default=max(0, int(defaults.stage3_spanish_special_char_threshold)),
        help="Reject only if Spanish special-character count in title/description is above this threshold.",
    )
    parser.add_argument(
        "--max-german-level",
        default=defaults.stage3_max_german_level,
        help="Maximum accepted German CEFR level (A1, A2, B1, B2, C1, C2). Jobs requiring higher are rejected.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        return 1

    raw_jobs = load_json_file(input_path)
    if not isinstance(raw_jobs, list):
        print("ERROR: Input JSON must be a list of jobs.")
        return 1

    approved_jobs, python_rejected = run_stage3_pipeline(raw_jobs, args)
    print("Stage 3 complete (local Python prefilter active).")
    print(f"Approved: {len(approved_jobs)} -> {args.output}")
    print(f"Rejected by Python prefilter: {len(python_rejected)} -> {args.rejected}")
    print(f"German special-char threshold: {max(0, int(args.german_special_char_threshold))}")
    print(f"French special-char threshold: {max(0, int(args.french_special_char_threshold))}")
    print(f"Spanish special-char threshold: {max(0, int(args.spanish_special_char_threshold))}")
    print(f"Max German level: {normalize_cefr_level(args.max_german_level)}")
    return 0


__all__ = [
    "build_stage3_args",
    "coerce_applicant_count",
    "detect_reasons",
    "main",
    "priority_sort_key",
    "priority_tier",
    "run_stage3_pipeline",
    "sort_and_rank_jobs",
    "split_python_prefilter_language_chars",
]
