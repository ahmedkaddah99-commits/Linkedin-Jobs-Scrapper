import argparse
import subprocess
import sys
import time
from pathlib import Path

from job_seeker_config import cfg_bool, cfg_float, cfg_int, cfg_str, load_job_seeker_config

STAGES = {
    1: ("Scrape + Enrich", "stage1_scrape_enrich.py"),
    2: ("Local Filter", "stage2_filter_local.py"),
    3: ("AI Filter", "stage3_filter_ai.py"),
    4: ("Docs + Excel Export", "stage4_docs_export.py"),
}


def main() -> int:
    config = load_job_seeker_config()
    default_start_stage = cfg_int(config, ("pipeline", "start_stage"), 1)
    default_end_stage = cfg_int(config, ("pipeline", "end_stage"), 4)
    default_python = cfg_str(config, ("pipeline", "python_executable"), "") or sys.executable
    default_sleep_between = cfg_float(config, ("pipeline", "sleep_between_seconds"), 2.0)
    default_force_stage3 = cfg_bool(config, ("pipeline", "force_stage3_reprocess"), False)
    default_force_stage4 = cfg_bool(config, ("pipeline", "force_stage4_regenerate"), False)

    if default_start_stage not in STAGES:
        default_start_stage = 1
    if default_end_stage not in STAGES:
        default_end_stage = 4

    parser = argparse.ArgumentParser(
        description="Run the full job pipeline stage-by-stage with controlled sequencing."
    )
    parser.add_argument("--start-stage", type=int, default=default_start_stage, choices=STAGES.keys())
    parser.add_argument("--end-stage", type=int, default=default_end_stage, choices=STAGES.keys())
    parser.add_argument(
        "--python",
        default=default_python,
        help="Python executable to use for stage scripts.",
    )
    parser.add_argument(
        "--sleep-between",
        type=float,
        default=default_sleep_between,
        help="Seconds to wait between stages.",
    )
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
    parser.add_argument(
        "--stage4-excel-mode",
        choices=["new-sheet", "append-rows"],
        default=None,
        help="Stage 4 Excel mode override.",
    )
    parser.add_argument(
        "--stage4-sheet-name",
        default=None,
        help="Stage 4 sheet name override.",
    )
    parser.add_argument(
        "--stage4-run-date",
        default=None,
        help="Stage 4 run date override (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--stage4-candidate-name",
        default=None,
        help="Stage 4 candidate name override.",
    )
    parser.add_argument(
        "--stage4-candidate-email",
        default=None,
        help="Stage 4 candidate email override.",
    )
    parser.add_argument(
        "--stage4-profile-image",
        default=None,
        help="Stage 4 profile image path override.",
    )
    args = parser.parse_args()

    if args.start_stage > args.end_stage:
        print("ERROR: --start-stage cannot be greater than --end-stage")
        return 1

    for stage_number in range(args.start_stage, args.end_stage + 1):
        stage_name, script_name = STAGES[stage_number]
        script_path = Path(script_name)
        if not script_path.exists():
            print(f"ERROR: Missing script for stage {stage_number}: {script_path}")
            return 1

        cmd = [args.python, str(script_path)]
        if stage_number == 3 and args.force_stage3:
            cmd.append("--force-reprocess")
        if stage_number == 4:
            if args.force_stage4:
                cmd.append("--force-regenerate")
            if args.stage4_excel_mode:
                cmd.extend(["--excel-mode", args.stage4_excel_mode])
            if args.stage4_sheet_name:
                cmd.extend(["--sheet-name", args.stage4_sheet_name])
            if args.stage4_run_date:
                cmd.extend(["--run-date", args.stage4_run_date])
            if args.stage4_candidate_name:
                cmd.extend(["--candidate-name", args.stage4_candidate_name])
            if args.stage4_candidate_email:
                cmd.extend(["--candidate-email", args.stage4_candidate_email])
            if args.stage4_profile_image:
                cmd.extend(["--profile-image", args.stage4_profile_image])

        print(f"\n[Stage {stage_number}] {stage_name}")
        print(f"Command: {' '.join(cmd)}")
        started = time.time()
        result = subprocess.run(cmd, check=False)
        duration = time.time() - started

        if result.returncode != 0:
            print(
                f"ERROR: Stage {stage_number} failed with exit code {result.returncode} "
                f"after {duration:.1f}s"
            )
            return result.returncode

        print(f"Stage {stage_number} completed in {duration:.1f}s")
        if stage_number < args.end_stage and args.sleep_between > 0:
            time.sleep(args.sleep_between)

    print("\nPipeline completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
