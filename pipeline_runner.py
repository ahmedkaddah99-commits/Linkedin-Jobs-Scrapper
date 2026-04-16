from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from job_dedupe import dedupe_job_records, load_existing_tracker_identity_keys
from job_models import (
    FILTER_STATUS_BYPASSED_MANUAL_APPROVAL,
    FILTER_STATUS_PASSED_LINKEDIN_PIPELINE,
    SOURCE_TYPE_LINKEDIN_SEARCH,
    SOURCE_TYPE_MANUAL_URL,
    normalize_job_record,
)
from job_seeker_config import cfg_bool, cfg_float, cfg_int, cfg_list, cfg_str


LOGGER = logging.getLogger(__name__)


def save_json_file(path_value: str | Path, payload: Any) -> None:
    path = Path(path_value).expanduser()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=4, ensure_ascii=False)


def build_stage1_args(config: dict, cli_args) -> SimpleNamespace:
    return SimpleNamespace(
        max_pages=int(cli_args.max_pages),
        max_enrich_jobs=int(cli_args.max_enrich_jobs),
        ai_batch_size=int(cli_args.ai_batch_size),
        keywords=list(cli_args.keywords),
        geo_id=cli_args.geo_id,
        time_posted_seconds=int(cli_args.time_posted_seconds),
        experience_levels=list(cli_args.experience_levels),
        forbidden_title_keywords=list(cli_args.forbidden_title_keywords),
        output=cli_args.stage1_output,
        excluded_output=cli_args.stage1_excluded_output,
        existing_jobs_excel=cli_args.output_xlsx,
        model=cli_args.stage1_model,
        scrape_snapshot_json=cli_args.scrape_snapshot_json,
        reuse_scrape_snapshot=bool(cli_args.reuse_scrape_snapshot),
        stage1_extra_prompt=cli_args.stage1_extra_prompt,
        stage1_prompt_override=cli_args.stage1_prompt_override,
        low_applicant_threshold=int(cli_args.low_applicant_threshold),
        debug_enrich_blocks=bool(cli_args.debug_enrich_blocks),
        page_fetch_sleep_seconds=float(cli_args.page_fetch_sleep_seconds),
        use_proxy_fallback=bool(cli_args.use_proxy_fallback),
    )


def build_stage4_args(cli_args) -> SimpleNamespace:
    return SimpleNamespace(
        input=cli_args.stage4_input,
        output_json=cli_args.output_json,
        output_xlsx=cli_args.output_xlsx,
        checkpoint=cli_args.stage4_checkpoint,
        docs_dir=cli_args.docs_dir,
        model=cli_args.stage4_model,
        fallback_model=cli_args.stage4_fallback_model,
        candidate_name=cli_args.candidate_name,
        candidate_email=cli_args.candidate_email,
        profile_image=cli_args.profile_image,
        cv_font=cli_args.cv_font,
        languages=list(cli_args.languages),
        stage4_extra_prompt=cli_args.stage4_extra_prompt,
        stage4_prompt_override=cli_args.stage4_prompt_override,
        sleep_seconds=float(cli_args.stage4_sleep_seconds),
        retries=int(cli_args.stage4_retries),
        retry_sleep=float(cli_args.stage4_retry_sleep),
        max_jobs=int(cli_args.stage4_max_jobs),
        excel_mode=cli_args.excel_mode,
        sheet_name=cli_args.sheet_name,
        run_date=cli_args.run_date,
        force_regenerate=bool(cli_args.force_regenerate),
    )


def run_stage2_pipeline(jobs: list[dict[str, Any]], cli_args) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from stage2_filter_local import detect_reasons as detect_stage2_reasons

    approved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for job in jobs:
        reasons = detect_stage2_reasons(
            job,
            int(cli_args.german_special_char_threshold),
            int(cli_args.french_special_char_threshold),
            int(cli_args.spanish_special_char_threshold),
            cli_args.max_german_level,
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

    save_json_file(cli_args.stage2_output, approved)
    save_json_file(cli_args.stage2_rejected_output, rejected)
    LOGGER.info("Stage 2 complete: approved=%s rejected=%s", len(approved), len(rejected))
    return approved, rejected


def run_stage3_pipeline(jobs: list[dict[str, Any]], cli_args) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from stage3_filter_ai import sort_and_rank_jobs, split_python_prefilter_language_chars

    approved, rejected = split_python_prefilter_language_chars(
        jobs,
        int(cli_args.stage3_german_special_char_threshold),
        int(cli_args.stage3_french_special_char_threshold),
        int(cli_args.stage3_spanish_special_char_threshold),
        cli_args.stage3_max_german_level,
    )
    approved = sort_and_rank_jobs(approved, int(cli_args.low_applicant_threshold))

    for job in approved:
        job["source_type"] = SOURCE_TYPE_LINKEDIN_SEARCH
        job["filter_status"] = FILTER_STATUS_PASSED_LINKEDIN_PIPELINE
    for job in rejected:
        job["source_type"] = SOURCE_TYPE_LINKEDIN_SEARCH
        job["filter_status"] = "rejected_stage3_prefilter"

    save_json_file(cli_args.stage3_output, approved)
    save_json_file(cli_args.stage3_rejected_output, rejected)
    LOGGER.info("Stage 3 complete: approved=%s rejected=%s", len(approved), len(rejected))
    return approved, rejected


def run_linkedin_pipeline(config: dict, cli_args) -> list[dict[str, Any]]:
    from stage1_scrape_enrich import run_stage1_pipeline

    stage1_args = build_stage1_args(config, cli_args)
    stage1_jobs = run_stage1_pipeline(stage1_args)
    if not stage1_jobs:
        save_json_file(cli_args.stage2_output, [])
        save_json_file(cli_args.stage2_rejected_output, [])
        save_json_file(cli_args.stage3_output, [])
        save_json_file(cli_args.stage3_rejected_output, [])
        return []

    stage2_jobs, _ = run_stage2_pipeline(stage1_jobs, cli_args)
    if not stage2_jobs:
        save_json_file(cli_args.stage3_output, [])
        save_json_file(cli_args.stage3_rejected_output, [])
        return []

    stage3_jobs, _ = run_stage3_pipeline(stage2_jobs, cli_args)
    return stage3_jobs


def run_manual_pipeline(cli_args) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from manual_url_ingestion import fetch_manual_jobs_from_file

    manual_jobs, failures = fetch_manual_jobs_from_file(
        cli_args.manual_urls_file,
        debug_enrich_blocks=bool(cli_args.debug_enrich_blocks),
        use_proxy_fallback=bool(cli_args.use_proxy_fallback),
        request_timeout_seconds=int(cli_args.manual_request_timeout_seconds),
        logger=LOGGER,
    )

    normalized_jobs = [
        normalize_job_record(
            record,
            source_type=record.get("source_type") or SOURCE_TYPE_MANUAL_URL,
            filter_status=FILTER_STATUS_BYPASSED_MANUAL_APPROVAL,
            manual_approved=True,
        )
        for record in manual_jobs
    ]
    for record in normalized_jobs:
        record["source_type"] = SOURCE_TYPE_MANUAL_URL
        record["filter_status"] = FILTER_STATUS_BYPASSED_MANUAL_APPROVAL
        record["manual_approved"] = True

    save_json_file(cli_args.manual_output_json, normalized_jobs)
    save_json_file(cli_args.manual_failures_json, failures)
    LOGGER.info("Manual ingestion complete: jobs=%s failures=%s", len(normalized_jobs), len(failures))
    return normalized_jobs, failures


def merge_source_jobs(
    linkedin_jobs: list[dict[str, Any]],
    manual_jobs: list[dict[str, Any]],
    *,
    tracker_excel_path: str,
    dedupe_against_tracker: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    merged_jobs, dropped_merge_duplicates = dedupe_job_records(
        [*linkedin_jobs, *manual_jobs],
        logger=LOGGER,
    )

    if not dedupe_against_tracker:
        return merged_jobs, dropped_merge_duplicates

    existing_keys = load_existing_tracker_identity_keys(tracker_excel_path)
    tracker_filtered_jobs, dropped_tracker_duplicates = dedupe_job_records(
        merged_jobs,
        existing_keys=existing_keys,
        logger=LOGGER,
    )
    return tracker_filtered_jobs, [*dropped_merge_duplicates, *dropped_tracker_duplicates]


def run_mode_pipeline(config: dict, cli_args) -> list[dict[str, Any]]:
    from stage4_docs_export import run_stage4_pipeline

    linkedin_jobs: list[dict[str, Any]] = []
    manual_jobs: list[dict[str, Any]] = []

    if cli_args.mode in {"linkedin", "combined"}:
        LOGGER.info("Running LinkedIn discovery pipeline")
        linkedin_jobs = run_linkedin_pipeline(config, cli_args)

    if cli_args.mode in {"manual_urls", "combined"}:
        LOGGER.info("Running manual URL ingestion pipeline from %s", cli_args.manual_urls_file)
        manual_jobs, _ = run_manual_pipeline(cli_args)

    dedupe_against_tracker = bool(cli_args.dedupe_against_tracker)
    final_jobs, dropped_jobs = merge_source_jobs(
        linkedin_jobs,
        manual_jobs,
        tracker_excel_path=cli_args.output_xlsx,
        dedupe_against_tracker=dedupe_against_tracker,
    )
    if dropped_jobs:
        LOGGER.info("Dropped %s duplicate jobs before stage 4", len(dropped_jobs))

    if cli_args.mode == "manual_urls" and not final_jobs:
        LOGGER.info("No valid manual jobs remain after dedupe; skipping stage 4.")
        save_json_file(cli_args.output_json, [])
        return []
    if cli_args.mode in {"linkedin", "combined"} and not final_jobs:
        LOGGER.info("No jobs remain after merge/dedupe; skipping stage 4.")
        save_json_file(cli_args.output_json, [])
        return []

    stage4_args = build_stage4_args(cli_args)
    save_json_file(cli_args.stage4_input, final_jobs)
    return run_stage4_pipeline(stage4_args, config=config, jobs=final_jobs)


def build_main_defaults(config: dict) -> dict[str, Any]:
    return {
        "keywords": [str(item) for item in cfg_list(config, ("job_search", "keywords"), []) if str(item).strip()],
        "geo_id": cfg_str(config, ("job_search", "linkedin_geo_id"), "101282230"),
        "time_posted_seconds": cfg_int(config, ("job_search", "time_posted_seconds"), 86400),
        "experience_levels": [
            int(level)
            for level in cfg_list(config, ("job_search", "experience_levels"), [1, 2, 3])
            if str(level).strip()
        ],
        "forbidden_title_keywords": [
            str(item)
            for item in cfg_list(config, ("job_search", "forbidden_title_keywords"), [])
            if str(item).strip()
        ],
        "max_pages": cfg_int(config, ("runtime", "stage1", "max_pages"), 400),
        "max_enrich_jobs": cfg_int(config, ("runtime", "stage1", "max_enrich_jobs"), 2000),
        "ai_batch_size": cfg_int(config, ("runtime", "stage1", "ai_filter_batch_size"), 30),
        "stage1_output": cfg_str(config, ("runtime", "stage1", "output_json"), "highly_curated_jobs.json"),
        "stage1_excluded_output": cfg_str(
            config,
            ("runtime", "stage1", "excluded_output_json"),
            "deepseek_excluded_jobs.json",
        ),
        "scrape_snapshot_json": cfg_str(
            config,
            ("runtime", "stage1", "scrape_snapshot_json"),
            "stage1_scrape_snapshot.json",
        ),
        "reuse_scrape_snapshot": cfg_bool(config, ("runtime", "stage1", "reuse_scrape_snapshot"), False),
        "debug_enrich_blocks": cfg_bool(config, ("runtime", "stage1", "debug_enrich_blocks"), True),
        "page_fetch_sleep_seconds": cfg_float(config, ("runtime", "stage1", "page_fetch_sleep_seconds"), 1.0),
        "use_proxy_fallback": cfg_bool(config, ("runtime", "stage1", "use_scrapeops_proxy_fallback"), False),
        "stage1_model": cfg_str(
            config,
            ("ai", "models", "stage1_title_filter_deepseek"),
            cfg_str(config, ("ai", "models", "stage1_title_filter"), "deepseek-chat"),
        ),
        "stage1_extra_prompt": cfg_str(config, ("ai", "prompts", "stage1_extra_instructions"), ""),
        "stage1_prompt_override": cfg_str(config, ("ai", "prompts", "stage1_prompt_override"), ""),
        "stage2_output": cfg_str(config, ("runtime", "stage2", "output_json"), "stage2_filtered_local.json"),
        "stage2_rejected_output": cfg_str(
            config,
            ("runtime", "stage2", "rejected_output_json"),
            "stage2_rejected_local.json",
        ),
        "german_special_char_threshold": cfg_int(
            config,
            ("runtime", "stage2", "german_special_char_threshold"),
            9999,
        ),
        "french_special_char_threshold": cfg_int(config, ("runtime", "stage2", "french_special_char_threshold"), 0),
        "spanish_special_char_threshold": cfg_int(config, ("runtime", "stage2", "spanish_special_char_threshold"), 0),
        "max_german_level": cfg_str(config, ("runtime", "stage2", "max_german_level"), "B2"),
        "stage3_output": cfg_str(config, ("runtime", "stage3", "output_json"), "stage3_filtered_ai.json"),
        "stage3_rejected_output": cfg_str(
            config,
            ("runtime", "stage3", "rejected_output_json"),
            "stage3_rejected_local.json",
        ),
        "stage3_german_special_char_threshold": cfg_int(
            config,
            ("runtime", "stage3", "german_special_char_threshold"),
            cfg_int(config, ("runtime", "stage2", "german_special_char_threshold"), 9999),
        ),
        "stage3_french_special_char_threshold": cfg_int(
            config,
            ("runtime", "stage3", "french_special_char_threshold"),
            cfg_int(config, ("runtime", "stage2", "french_special_char_threshold"), 0),
        ),
        "stage3_spanish_special_char_threshold": cfg_int(
            config,
            ("runtime", "stage3", "spanish_special_char_threshold"),
            cfg_int(config, ("runtime", "stage2", "spanish_special_char_threshold"), 0),
        ),
        "stage3_max_german_level": cfg_str(
            config,
            ("runtime", "stage3", "max_german_level"),
            cfg_str(config, ("runtime", "stage2", "max_german_level"), "B2"),
        ),
        "low_applicant_threshold": cfg_int(config, ("job_search", "priority", "low_applicant_threshold"), 80),
        "manual_urls_file": cfg_str(config, ("runtime", "manual_urls", "input_file"), "user_config/manual_job_urls.txt"),
        "manual_output_json": cfg_str(config, ("runtime", "manual_urls", "output_json"), "manual_url_jobs.json"),
        "manual_failures_json": cfg_str(
            config,
            ("runtime", "manual_urls", "failed_output_json"),
            "manual_url_failures.json",
        ),
        "manual_request_timeout_seconds": cfg_int(
            config,
            ("runtime", "manual_urls", "request_timeout_seconds"),
            45,
        ),
        "dedupe_against_tracker": cfg_bool(
            config,
            ("runtime", "manual_urls", "dedupe_against_tracker"),
            True,
        ),
        "stage4_input": cfg_str(config, ("runtime", "stage4", "input_json"), "stage3_filtered_ai.json"),
        "stage4_checkpoint": cfg_str(config, ("runtime", "stage4", "checkpoint_json"), "stage4_checkpoint.json"),
        "stage4_model": cfg_str(config, ("ai", "models", "stage4_docs_deepseek"), "deepseek-chat"),
        "stage4_fallback_model": cfg_str(config, ("ai", "models", "stage4_docs_fallback_gemini"), "gemini-2.5-flash"),
        "stage4_extra_prompt": cfg_str(config, ("ai", "prompts", "stage4_extra_instructions"), ""),
        "stage4_prompt_override": cfg_str(config, ("ai", "prompts", "stage4_prompt_override"), ""),
        "stage4_sleep_seconds": cfg_float(config, ("runtime", "stage4", "sleep_seconds"), 4.0),
        "stage4_retries": cfg_int(config, ("runtime", "stage4", "retries"), 3),
        "stage4_retry_sleep": cfg_float(config, ("runtime", "stage4", "retry_sleep_seconds"), 3.0),
        "stage4_max_jobs": cfg_int(config, ("runtime", "stage4", "max_jobs"), 0),
        "output_json": cfg_str(config, ("outputs", "stage4_json"), "stage4_documents.json"),
        "output_xlsx": cfg_str(config, ("outputs", "stage4_xlsx"), "final_jobs_with_docs.xlsx"),
        "docs_dir": cfg_str(config, ("outputs", "docs_dir"), "generated_docs"),
        "excel_mode": cfg_str(config, ("runtime", "stage4", "excel_mode"), "new-sheet"),
        "sheet_name": cfg_str(config, ("runtime", "stage4", "sheet_name"), ""),
        "run_date": cfg_str(config, ("runtime", "stage4", "run_date"), ""),
        "force_regenerate": cfg_bool(config, ("runtime", "stage4", "force_regenerate"), False),
        "candidate_name": cfg_str(config, ("candidate", "name"), ""),
        "candidate_email": cfg_str(config, ("candidate", "email"), ""),
        "profile_image": cfg_str(config, ("candidate", "profile_image_path"), ""),
        "cv_font": cfg_str(config, ("candidate", "cv_font"), "Calibri"),
        "languages": [str(item) for item in cfg_list(config, ("candidate", "languages"), []) if str(item).strip()],
    }
