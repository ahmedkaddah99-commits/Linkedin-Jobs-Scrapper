import argparse
import logging

from job_seeker_config import load_job_seeker_config, load_project_dotenv
from pipeline_runner import build_main_defaults, run_mode_pipeline


def main() -> int:
    load_project_dotenv()
    config = load_job_seeker_config()
    defaults = build_main_defaults(config)

    parser = argparse.ArgumentParser(
        description=(
            "Run the job automation pipeline in linkedin mode, manual_urls mode, or combined mode."
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
    parser.add_argument(
        "--german-special-char-threshold",
        type=int,
        default=defaults["german_special_char_threshold"],
    )
    parser.add_argument(
        "--french-special-char-threshold",
        type=int,
        default=defaults["french_special_char_threshold"],
    )
    parser.add_argument(
        "--spanish-special-char-threshold",
        type=int,
        default=defaults["spanish_special_char_threshold"],
    )
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

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        run_mode_pipeline(config, args)
    except Exception as exc:
        logging.getLogger(__name__).exception("Pipeline execution failed")
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
