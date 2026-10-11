from __future__ import annotations

import logging
from typing import Any

from backend.domain.job_identity import dedupe_job_records, load_existing_tracker_identity_keys
from backend.domain.pipeline_jobs import (
    FILTER_STATUS_BYPASSED_MANUAL_APPROVAL,
    FILTER_STATUS_PASSED_LINKEDIN_PIPELINE,
    SOURCE_TYPE_LINKEDIN_SEARCH,
    SOURCE_TYPE_MANUAL_URL,
    normalize_job_record,
)

from .acquisition import run_stage1_pipeline
from .common import save_json_file
from .documents import run_stage4_pipeline
from .manual_urls import fetch_manual_jobs_from_file, fetch_manual_jobs_from_urls, normalize_manual_urls
from .prioritization import run_stage3_pipeline
from .runtime import build_stage1_args, build_stage4_args
from .screening import run_stage2_pipeline


LOGGER = logging.getLogger(__name__)


def run_linkedin_pipeline(config: dict, cli_args) -> list[dict[str, Any]]:
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


def run_manual_pipeline(cli_args, *, usage_callback=None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    inline_urls = list(getattr(cli_args, "manual_urls_inline", None) or [])
    if not inline_urls:
        inline_urls = list(getattr(cli_args, "manual_url_seed_list", None) or [])

    if inline_urls:
        normalized_urls, invalid_entries = normalize_manual_urls(inline_urls)
        manual_jobs, failures = fetch_manual_jobs_from_urls(
            normalized_urls,
            invalid_entries=invalid_entries,
            debug_enrich_blocks=bool(cli_args.debug_enrich_blocks),
            use_proxy_fallback=bool(cli_args.use_proxy_fallback),
            request_timeout_seconds=int(cli_args.manual_request_timeout_seconds),
            logger=LOGGER,
            usage_callback=usage_callback,
        )
    else:
        manual_jobs, failures = fetch_manual_jobs_from_file(
            cli_args.manual_urls_file,
            debug_enrich_blocks=bool(cli_args.debug_enrich_blocks),
            use_proxy_fallback=bool(cli_args.use_proxy_fallback),
            request_timeout_seconds=int(cli_args.manual_request_timeout_seconds),
            logger=LOGGER,
            usage_callback=usage_callback,
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
    records = run_stage4_pipeline(stage4_args, config=config, jobs=final_jobs)
    for job in records:
        job["source_type"] = job.get("source_type") or SOURCE_TYPE_LINKEDIN_SEARCH
        job["filter_status"] = job.get("filter_status") or FILTER_STATUS_PASSED_LINKEDIN_PIPELINE
    return records


__all__ = [
    "merge_source_jobs",
    "run_linkedin_pipeline",
    "run_manual_pipeline",
    "run_mode_pipeline",
]
