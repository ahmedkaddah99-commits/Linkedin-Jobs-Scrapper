from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

from backend.capabilities.tailored_documents.runtime import build_main_defaults
from backend.capabilities.tailored_documents.workflow import run_mode_pipeline
from backend.config.job_seeker import (
    cfg_bool,
    cfg_float,
    cfg_int,
    cfg_str,
    load_job_seeker_config,
    load_project_dotenv,
)
from bc_automation.blue_collar_config import cfg_float as blue_cfg_float
from bc_automation.blue_collar_config import cfg_int as blue_cfg_int
from bc_automation.blue_collar_config import cfg_str as blue_cfg_str
from bc_automation.blue_collar_config import load_blue_collar_config


REPO_ROOT = Path(__file__).resolve().parents[2]

ROOT_STAGES = {
    1: ("Scrape + Enrich", REPO_ROOT / "stage1_scrape_enrich.py"),
    2: ("Local Filter", REPO_ROOT / "stage2_filter_local.py"),
    3: ("Priority Filter", REPO_ROOT / "stage3_filter_ai.py"),
    4: ("Docs + Export", REPO_ROOT / "stage4_docs_export.py"),
}

BLUE_COLLAR_STAGES = {
    1: ("Scrape Portals", REPO_ROOT / "bc_automation" / "stage1_scrape_blue_collar.py"),
    2: ("Python Filtering", REPO_ROOT / "bc_automation" / "stage2_filter_blue_collar.py"),
    3: ("Role Cluster Classification", REPO_ROOT / "bc_automation" / "stage3_classify_blue_collar.py"),
    4: ("Generate Reusable Role CVs", REPO_ROOT / "bc_automation" / "stage4_build_role_cvs.py"),
    5: ("Generate Per-Job Packages", REPO_ROOT / "bc_automation" / "stage5_generate_blue_collar_docs.py"),
}


def _build_legacy_main_parser(defaults: dict[str, object]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Legacy compatibility entrypoint for the tailored-document CLI flow. "
            "Prefer scratch workspaces through workspace_runner.py or the frontend."
        )
    )
    parser.add_argument("--mode", choices=["linkedin", "manual_urls", "combined"], required=True)
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    parser.add_argument("--keywords", nargs="*", default=defaults["keywords"])
    parser.add_argument("--geo-id", default=defaults["geo_id"])
    parser.add_argument("--time-posted-seconds", type=int, default=defaults["time_posted_seconds"])
    parser.add_argument("--experience-levels", nargs="*", type=int, default=defaults["experience_levels"])
    parser.add_argument("--forbidden-title-keywords", nargs="*", default=defaults["forbidden_title_keywords"])
    parser.add_argument("--max-pages", type=int, default=defaults["max_pages"])
    parser.add_argument("--max-enrich-jobs", type=int, default=defaults["max_enrich_jobs"])
    parser.add_argument("--ai-batch-size", type=int, default=defaults["ai_batch_size"])
    parser.add_argument("--stage1-output", default=defaults["stage1_output"])
    parser.add_argument("--stage1-excluded-output", default=defaults["stage1_excluded_output"])
    parser.add_argument("--scrape-snapshot-json", default=defaults["scrape_snapshot_json"])
    parser.add_argument(
        "--reuse-scrape-snapshot",
        action=argparse.BooleanOptionalAction,
        default=defaults["reuse_scrape_snapshot"],
    )
    parser.add_argument(
        "--debug-enrich-blocks",
        action=argparse.BooleanOptionalAction,
        default=defaults["debug_enrich_blocks"],
    )
    parser.add_argument("--page-fetch-sleep-seconds", type=float, default=defaults["page_fetch_sleep_seconds"])
    parser.add_argument(
        "--use-proxy-fallback",
        action=argparse.BooleanOptionalAction,
        default=defaults["use_proxy_fallback"],
    )
    parser.add_argument("--stage1-model", default=defaults["stage1_model"])
    parser.add_argument("--stage1-extra-prompt", default=defaults["stage1_extra_prompt"])
    parser.add_argument("--stage1-prompt-override", default=defaults["stage1_prompt_override"])

    parser.add_argument("--stage2-output", default=defaults["stage2_output"])
    parser.add_argument("--stage2-rejected-output", default=defaults["stage2_rejected_output"])
    parser.add_argument("--german-special-char-threshold", type=int, default=defaults["german_special_char_threshold"])
    parser.add_argument("--french-special-char-threshold", type=int, default=defaults["french_special_char_threshold"])
    parser.add_argument("--spanish-special-char-threshold", type=int, default=defaults["spanish_special_char_threshold"])
    parser.add_argument("--max-german-level", default=defaults["max_german_level"])

    parser.add_argument("--stage3-output", default=defaults["stage3_output"])
    parser.add_argument("--stage3-rejected-output", default=defaults["stage3_rejected_output"])
    parser.add_argument(
        "--stage3-german-special-char-threshold",
        type=int,
        default=defaults["stage3_german_special_char_threshold"],
    )
    parser.add_argument(
        "--stage3-french-special-char-threshold",
        type=int,
        default=defaults["stage3_french_special_char_threshold"],
    )
    parser.add_argument(
        "--stage3-spanish-special-char-threshold",
        type=int,
        default=defaults["stage3_spanish_special_char_threshold"],
    )
    parser.add_argument("--stage3-max-german-level", default=defaults["stage3_max_german_level"])
    parser.add_argument("--low-applicant-threshold", type=int, default=defaults["low_applicant_threshold"])

    parser.add_argument("--manual-urls-file", default=defaults["manual_urls_file"])
    parser.add_argument("--manual-output-json", default=defaults["manual_output_json"])
    parser.add_argument("--manual-failures-json", default=defaults["manual_failures_json"])
    parser.add_argument(
        "--manual-request-timeout-seconds",
        type=int,
        default=defaults["manual_request_timeout_seconds"],
    )
    parser.add_argument(
        "--dedupe-against-tracker",
        action=argparse.BooleanOptionalAction,
        default=defaults["dedupe_against_tracker"],
    )

    parser.add_argument("--stage4-input", default=defaults["stage4_input"])
    parser.add_argument("--stage4-checkpoint", default=defaults["stage4_checkpoint"])
    parser.add_argument("--stage4-model", default=defaults["stage4_model"])
    parser.add_argument("--stage4-fallback-model", default=defaults["stage4_fallback_model"])
    parser.add_argument("--stage4-extra-prompt", default=defaults["stage4_extra_prompt"])
    parser.add_argument("--stage4-prompt-override", default=defaults["stage4_prompt_override"])
    parser.add_argument("--stage4-sleep-seconds", type=float, default=defaults["stage4_sleep_seconds"])
    parser.add_argument("--stage4-retries", type=int, default=defaults["stage4_retries"])
    parser.add_argument("--stage4-retry-sleep", type=float, default=defaults["stage4_retry_sleep"])
    parser.add_argument("--stage4-max-jobs", type=int, default=defaults["stage4_max_jobs"])

    parser.add_argument("--output-json", default=defaults["output_json"])
    parser.add_argument("--output-xlsx", default=defaults["output_xlsx"])
    parser.add_argument("--docs-dir", default=defaults["docs_dir"])
    parser.add_argument("--excel-mode", choices=["new-sheet", "append-rows"], default=defaults["excel_mode"])
    parser.add_argument("--sheet-name", default=defaults["sheet_name"])
    parser.add_argument("--run-date", default=defaults["run_date"])
    parser.add_argument(
        "--force-regenerate",
        action=argparse.BooleanOptionalAction,
        default=defaults["force_regenerate"],
    )
    parser.add_argument("--candidate-name", default=defaults["candidate_name"])
    parser.add_argument("--candidate-email", default=defaults["candidate_email"])
    parser.add_argument("--profile-image", default=defaults["profile_image"])
    parser.add_argument("--cv-font", choices=["Calibri", "Arial"], default=defaults["cv_font"])
    parser.add_argument("--languages", nargs="*", default=defaults["languages"])
    return parser


def run_legacy_main(argv: Sequence[str] | None = None) -> int:
    load_project_dotenv()
    config = load_job_seeker_config()
    defaults = build_main_defaults(config)
    parser = _build_legacy_main_parser(defaults)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        run_mode_pipeline(config, args)
    except Exception as exc:
        logging.getLogger(__name__).exception("Legacy tailored-document CLI execution failed")
        print(f"ERROR: {exc}")
        return 1
    return 0


def _run_stage_sequence(
    *,
    stage_map: dict[int, tuple[str, Path]],
    start_stage: int,
    end_stage: int,
    python_executable: str,
    sleep_between: float,
    build_command,
    working_directory: Path,
) -> int:
    if start_stage > end_stage:
        print("ERROR: --start-stage cannot be greater than --end-stage")
        return 1

    for stage_number in range(start_stage, end_stage + 1):
        stage_name, script_path = stage_map[stage_number]
        if not script_path.exists():
            print(f"ERROR: Missing compatibility script for stage {stage_number}: {script_path}")
            return 1

        command = build_command(stage_number, python_executable, script_path)
        print(f"\n[Stage {stage_number}] {stage_name}")
        print(f"Command: {' '.join(command)}")
        started = time.time()
        result = subprocess.run(command, cwd=str(working_directory), check=False)
        duration = time.time() - started
        if result.returncode != 0:
            print(
                f"ERROR: Stage {stage_number} failed with exit code {result.returncode} "
                f"after {duration:.1f}s"
            )
            return result.returncode
        print(f"Stage {stage_number} completed in {duration:.1f}s")
        if stage_number < end_stage and sleep_between > 0:
            time.sleep(sleep_between)

    print("\nLegacy compatibility pipeline completed successfully.")
    return 0


def run_root_orchestrator(argv: Sequence[str] | None = None) -> int:
    config = load_job_seeker_config()
    default_start_stage = cfg_int(config, ("pipeline", "start_stage"), 1)
    default_end_stage = cfg_int(config, ("pipeline", "end_stage"), 4)
    default_python = cfg_str(config, ("pipeline", "python_executable"), "") or sys.executable
    default_sleep_between = cfg_float(config, ("pipeline", "sleep_between_seconds"), 2.0)
    default_force_stage3 = cfg_bool(config, ("pipeline", "force_stage3_reprocess"), False)
    default_force_stage4 = cfg_bool(config, ("pipeline", "force_stage4_regenerate"), False)

    parser = argparse.ArgumentParser(
        description=(
            "Legacy compatibility orchestrator for the tailored-document stage scripts. "
            "Prefer workspace_runner.py and workspace-driven runs."
        )
    )
    parser.add_argument("--start-stage", type=int, default=default_start_stage, choices=ROOT_STAGES.keys())
    parser.add_argument("--end-stage", type=int, default=default_end_stage, choices=ROOT_STAGES.keys())
    parser.add_argument("--python", default=default_python, help="Python executable to use for stage scripts.")
    parser.add_argument("--sleep-between", type=float, default=default_sleep_between, help="Seconds to wait between stages.")
    parser.add_argument(
        "--force-stage3",
        action=argparse.BooleanOptionalAction,
        default=default_force_stage3,
        help="Force Stage 3 to ignore its checkpoint and reprocess all jobs.",
    )
    parser.add_argument(
        "--force-stage4",
        action=argparse.BooleanOptionalAction,
        default=default_force_stage4,
        help="Force Stage 4 to ignore its checkpoint and regenerate all docs.",
    )
    parser.add_argument("--stage4-excel-mode", choices=["new-sheet", "append-rows"], default=None)
    parser.add_argument("--stage4-sheet-name", default=None)
    parser.add_argument("--stage4-run-date", default=None)
    parser.add_argument("--stage4-candidate-name", default=None)
    parser.add_argument("--stage4-candidate-email", default=None)
    parser.add_argument("--stage4-profile-image", default=None)
    args = parser.parse_args(argv)

    def build_command(stage_number: int, python_executable: str, script_path: Path) -> list[str]:
        command = [python_executable, str(script_path)]
        if stage_number == 3 and bool(args.force_stage3):
            command.append("--force-reprocess")
        if stage_number == 4:
            if bool(args.force_stage4):
                command.append("--force-regenerate")
            if args.stage4_excel_mode:
                command.extend(["--excel-mode", str(args.stage4_excel_mode)])
            if args.stage4_sheet_name:
                command.extend(["--sheet-name", str(args.stage4_sheet_name)])
            if args.stage4_run_date:
                command.extend(["--run-date", str(args.stage4_run_date)])
            if args.stage4_candidate_name:
                command.extend(["--candidate-name", str(args.stage4_candidate_name)])
            if args.stage4_candidate_email:
                command.extend(["--candidate-email", str(args.stage4_candidate_email)])
            if args.stage4_profile_image:
                command.extend(["--profile-image", str(args.stage4_profile_image)])
        return command

    return _run_stage_sequence(
        stage_map=ROOT_STAGES,
        start_stage=int(args.start_stage),
        end_stage=int(args.end_stage),
        python_executable=str(args.python),
        sleep_between=float(args.sleep_between),
        build_command=build_command,
        working_directory=REPO_ROOT,
    )


def run_blue_collar_orchestrator(argv: Sequence[str] | None = None) -> int:
    config = load_blue_collar_config()
    default_start_stage = blue_cfg_int(config, ("pipeline", "start_stage"), 1)
    default_end_stage = blue_cfg_int(config, ("pipeline", "end_stage"), 5)
    default_python = blue_cfg_str(config, ("pipeline", "python_executable"), "") or sys.executable
    default_sleep_between = blue_cfg_float(config, ("pipeline", "sleep_between_seconds"), 2.0)

    parser = argparse.ArgumentParser(
        description=(
            "Legacy compatibility orchestrator for reusable-package stage scripts. "
            "Prefer workspace_runner.py and workspace-driven runs."
        )
    )
    parser.add_argument("--start-stage", type=int, default=default_start_stage, choices=BLUE_COLLAR_STAGES.keys())
    parser.add_argument("--end-stage", type=int, default=default_end_stage, choices=BLUE_COLLAR_STAGES.keys())
    parser.add_argument("--python", default=default_python, help="Python executable for stage scripts.")
    parser.add_argument("--sleep-between", type=float, default=default_sleep_between)
    parser.add_argument(
        "--run-date",
        default="",
        help="Optional run date (YYYY-MM-DD) passed to stage 5 for deterministic output folders.",
    )
    args = parser.parse_args(argv)

    def build_command(stage_number: int, python_executable: str, script_path: Path) -> list[str]:
        command = [python_executable, str(script_path)]
        if stage_number == 5 and args.run_date:
            command.extend(["--run-date", str(args.run_date)])
        return command

    return _run_stage_sequence(
        stage_map=BLUE_COLLAR_STAGES,
        start_stage=int(args.start_stage),
        end_stage=int(args.end_stage),
        python_executable=str(args.python),
        sleep_between=float(args.sleep_between),
        build_command=build_command,
        working_directory=REPO_ROOT / "bc_automation",
    )


__all__ = [
    "run_blue_collar_orchestrator",
    "run_legacy_main",
    "run_root_orchestrator",
]
