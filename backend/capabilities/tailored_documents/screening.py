from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from backend.config.job_seeker import cfg_int, cfg_str, load_job_seeker_config

from .common import load_json_file, save_json_file
from .language_rules import (
    DEFAULT_FRENCH_SPECIAL_CHAR_THRESHOLD,
    DEFAULT_GERMAN_SPECIAL_CHAR_THRESHOLD,
    DEFAULT_SPANISH_SPECIAL_CHAR_THRESHOLD,
    detect_reasons,
    normalize_cefr_level,
)


def build_stage2_args(
    config: dict | None = None,
    overrides: dict[str, Any] | None = None,
) -> SimpleNamespace:
    config = config or load_job_seeker_config()
    payload = {
        "input": cfg_str(config, ("runtime", "stage2", "input_json"), "highly_curated_jobs.json"),
        "output": cfg_str(config, ("runtime", "stage2", "output_json"), "stage2_filtered_local.json"),
        "rejected": cfg_str(config, ("runtime", "stage2", "rejected_output_json"), "stage2_rejected_local.json"),
        "german_special_char_threshold": cfg_int(
            config,
            ("runtime", "stage2", "german_special_char_threshold"),
            DEFAULT_GERMAN_SPECIAL_CHAR_THRESHOLD,
        ),
        "french_special_char_threshold": cfg_int(
            config,
            ("runtime", "stage2", "french_special_char_threshold"),
            DEFAULT_FRENCH_SPECIAL_CHAR_THRESHOLD,
        ),
        "spanish_special_char_threshold": cfg_int(
            config,
            ("runtime", "stage2", "spanish_special_char_threshold"),
            DEFAULT_SPANISH_SPECIAL_CHAR_THRESHOLD,
        ),
        "max_german_level": cfg_str(config, ("runtime", "stage2", "max_german_level"), "B2"),
    }
    if overrides:
        payload.update({key: value for key, value in overrides.items() if value is not None})
    return SimpleNamespace(**payload)


def run_stage2_pipeline(
    jobs: list[dict[str, Any]] | None = None,
    cli_args=None,
    *,
    config: dict | None = None,
    args=None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active_args = args or cli_args
    if active_args is None:
        raise ValueError("stage2 args are required")

    if jobs is None:
        input_path = Path(active_args.input)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        jobs = load_json_file(input_path)

    approved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for job in jobs:
        reasons = detect_reasons(
            job,
            max(0, int(active_args.german_special_char_threshold)),
            max(0, int(active_args.french_special_char_threshold)),
            max(0, int(active_args.spanish_special_char_threshold)),
            active_args.max_german_level,
        )
        if reasons:
            rejected.append(
                {
                    **job,
                    "local_filter_reasons": reasons,
                    "local_filter_reason": " | ".join(reasons),
                    "filter_status": "rejected_stage2_local_filter",
                }
            )
        else:
            approved.append(dict(job))

    save_json_file(Path(active_args.output), approved)
    save_json_file(Path(active_args.rejected), rejected)
    return approved, rejected


def main() -> int:
    config = load_job_seeker_config()
    defaults = build_stage2_args(config)

    parser = argparse.ArgumentParser(
        description="Stage 2 local filtering: remove likely non-English jobs via language-specific local rules."
    )
    parser.add_argument("--input", default=defaults.input, help="Input JSON from Stage 1.")
    parser.add_argument("--output", default=defaults.output, help="Local-filtered approved jobs.")
    parser.add_argument("--rejected", default=defaults.rejected, help="Locally rejected jobs with reasons.")
    parser.add_argument(
        "--german-special-char-threshold",
        type=int,
        default=max(0, int(defaults.german_special_char_threshold)),
        help="Reject only if German special-character count in title/description is above this threshold.",
    )
    parser.add_argument(
        "--french-special-char-threshold",
        type=int,
        default=max(0, int(defaults.french_special_char_threshold)),
        help="Reject only if French special-character count in title/description is above this threshold.",
    )
    parser.add_argument(
        "--spanish-special-char-threshold",
        type=int,
        default=max(0, int(defaults.spanish_special_char_threshold)),
        help="Reject only if Spanish special-character count in title/description is above this threshold.",
    )
    parser.add_argument(
        "--max-german-level",
        default=defaults.max_german_level,
        help="Maximum accepted German CEFR level (A1, A2, B1, B2, C1, C2). Jobs requiring higher are rejected.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        return 1

    jobs = load_json_file(input_path)
    approved, rejected = run_stage2_pipeline(jobs, args)

    print(f"Stage 2 complete. Input: {len(jobs)}")
    print(f"Approved (local): {len(approved)} -> {args.output}")
    print(f"Rejected (local): {len(rejected)} -> {args.rejected}")
    print(f"German special-char threshold: {max(0, int(args.german_special_char_threshold))}")
    print(f"French special-char threshold: {max(0, int(args.french_special_char_threshold))}")
    print(f"Spanish special-char threshold: {max(0, int(args.spanish_special_char_threshold))}")
    print(f"Max German level: {normalize_cefr_level(args.max_german_level)}")
    return 0


__all__ = ["build_stage2_args", "detect_reasons", "main", "run_stage2_pipeline"]
