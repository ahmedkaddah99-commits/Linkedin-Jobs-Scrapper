import argparse
import json
import os

from backend.config.job_seeker import (
    cfg_bool,
    cfg_float,
    cfg_int,
    cfg_list,
    cfg_str,
    load_job_seeker_config,
)
# Lazy import: from backend.domain.phase0_contracts import JOB_FILTERING_MODE_BROADER, JOB_FILTERING_MODE_STRICT
from backend.profiles.cv_text import load_cv_text

from .linkedin_connector import (
    build_clients,
    build_scrape_requests_client,
    enrich_job,
    fetch_initial_list,
    priority_sort_key,
    priority_tier,
)
from .snapshotting import (
    load_existing_job_signatures_from_excel,
    load_jobs_snapshot,
    make_job_signature,
    save_jobs_snapshot,
)
from .title_filter import filter_with_ai


DEFAULT_KEYWORDS = [
    "analyst",
    "consultant",
]

FORBIDDEN_WORDS = [
    "senior",
    "engineer",
    "sr",
    "sr.",
    "lead",
    "principal",
    "head",
    "director",
    "intern",
    "werkstudent",
]
DEFAULT_LOW_APPLICANT_THRESHOLD = int(os.getenv("STAGE1_LOW_APPLICANT_THRESHOLD", "80"))


def main() -> int:
    config = load_job_seeker_config()
    default_keywords = [str(item) for item in cfg_list(config, ("job_search", "keywords"), DEFAULT_KEYWORDS)]
    default_geo_id = cfg_str(config, ("job_search", "geo_id"), os.getenv("LINKEDIN_GEO_ID", "101282230"))
    default_time_posted_seconds = cfg_int(
        config,
        ("job_search", "time_posted_seconds"),
        int(os.getenv("LINKEDIN_TIME_POSTED_SECONDS", "86400")),
    )
    default_experience_levels = [int(item) for item in cfg_list(config, ("job_search", "experience_levels"), [2, 3])]
    default_forbidden_title_keywords = [
        str(item) for item in cfg_list(config, ("job_search", "forbidden_title_keywords"), FORBIDDEN_WORDS)
    ]
    default_max_pages = cfg_int(config, ("runtime", "stage1", "max_pages_per_keyword"), 5)
    default_output = cfg_str(config, ("outputs", "stage1_json"), "stage1_listing_acquisition.json")
    default_excluded_output = cfg_str(config, ("outputs", "stage1_excluded_json"), "deepseek_excluded_jobs.json")
    default_existing_jobs_excel = cfg_str(config, ("outputs", "stage4_xlsx"), "final_jobs_with_docs.xlsx")
    default_stage1_model = cfg_str(
        config,
        ("ai", "models", "stage1_title_filter"),
        os.getenv("DEEPSEEK_STAGE1_MODEL", "deepseek-chat"),
    )
    default_stage1_max_enrich_jobs = cfg_int(
        config,
        ("runtime", "stage1", "max_enrich_jobs"),
        int(os.getenv("STAGE1_MAX_ENRICH_JOBS", "50")),
    )
    default_stage1_ai_batch_size = cfg_int(
        config,
        ("runtime", "stage1", "ai_batch_size"),
        int(os.getenv("STAGE1_AI_BATCH_SIZE", "30")),
    )
    default_scrape_snapshot_json = cfg_str(
        config,
        ("runtime", "stage1", "scrape_snapshot_json"),
        "stage1_scrape_snapshot.json",
    )
    default_reuse_scrape_snapshot = cfg_bool(
        config,
        ("runtime", "stage1", "reuse_scrape_snapshot"),
        os.getenv("STAGE1_REUSE_SCRAPE_SNAPSHOT", "false").lower() in ("1", "true", "yes"),
    )
    default_stage1_extra_prompt = cfg_str(config, ("ai", "prompts", "stage1_extra_instructions"), "")
    default_stage1_prompt_override = cfg_str(config, ("ai", "prompts", "stage1_prompt_override"), "")
    default_low_applicant_threshold = cfg_int(
        config,
        ("runtime", "stage1", "low_applicant_threshold"),
        DEFAULT_LOW_APPLICANT_THRESHOLD,
    )
    default_debug_enrich_blocks = cfg_bool(
        config,
        ("runtime", "stage1", "debug_enrich_blocks"),
        False,
    )
    default_page_fetch_sleep_seconds = cfg_float(
        config,
        ("runtime", "stage1", "page_fetch_sleep_seconds"),
        float(os.getenv("STAGE1_PAGE_FETCH_SLEEP_SECONDS", "0")),
    )
    default_use_proxy_fallback = cfg_bool(
        config,
        ("runtime", "stage1", "use_proxy_fallback"),
        os.getenv("STAGE1_USE_PROXY_FALLBACK", "true").lower() in ("1", "true", "yes"),
    )

    parser = argparse.ArgumentParser(description="Stage 1: scrape, AI title-filter, and enrich jobs.")
    parser.add_argument("--max-pages", type=int, default=default_max_pages)
    parser.add_argument(
        "--max-enrich-jobs",
        type=int,
        default=default_stage1_max_enrich_jobs,
        help="Use -1 to enrich all approved jobs.",
    )
    parser.add_argument(
        "--ai-batch-size",
        type=int,
        default=default_stage1_ai_batch_size,
        help="Number of jobs per AI title-filter request.",
    )
    parser.add_argument("--keywords", nargs="*", default=default_keywords)
    parser.add_argument("--geo-id", default=default_geo_id, help="LinkedIn geoId to search in.")
    parser.add_argument(
        "--time-posted-seconds",
        type=int,
        default=default_time_posted_seconds,
        help="LinkedIn time-posted filter in seconds (0 disables filter).",
    )
    parser.add_argument(
        "--experience-levels",
        nargs="*",
        type=int,
        default=default_experience_levels,
        help="LinkedIn experience level codes, e.g. 2 3.",
    )
    parser.add_argument(
        "--forbidden-title-keywords",
        nargs="*",
        default=default_forbidden_title_keywords,
        help="Title keywords to exclude before AI filtering.",
    )
    parser.add_argument("--output", default=default_output)
    parser.add_argument("--excluded-output", default=default_excluded_output)
    parser.add_argument(
        "--existing-jobs-excel",
        default=default_existing_jobs_excel,
        help="Excel file path used to skip jobs whose title+company already exist across any sheet before AI filtering.",
    )
    parser.add_argument(
        "--model",
        default=default_stage1_model,
        help="DeepSeek model for Stage 1 title filtering (e.g., deepseek-chat).",
    )
    parser.add_argument(
        "--scrape-snapshot-json",
        default=default_scrape_snapshot_json,
        help="Path to Stage 1 scrape snapshot (saved before AI filtering).",
    )
    parser.add_argument(
        "--reuse-scrape-snapshot",
        action=argparse.BooleanOptionalAction,
        default=default_reuse_scrape_snapshot,
        help="Skip scraping and reuse jobs from --scrape-snapshot-json.",
    )
    parser.add_argument(
        "--stage1-extra-prompt",
        default=default_stage1_extra_prompt,
        help="Extra instructions appended to Stage 1 AI title-filter prompt.",
    )
    parser.add_argument(
        "--stage1-prompt-override",
        default=default_stage1_prompt_override,
        help="Optional full prompt override. Supports {{CV_SUMMARY}} and {{JOB_LIST}} placeholders.",
    )
    from backend.domain.phase0_contracts import JOB_FILTERING_MODE_BROADER, JOB_FILTERING_MODE_STRICT
    parser.add_argument(
        "--job-filtering-mode",
        default=JOB_FILTERING_MODE_BROADER,
        choices=[JOB_FILTERING_MODE_STRICT, JOB_FILTERING_MODE_BROADER],
        help="Saved workspace Stage 1 title filtering mode.",
    )
    parser.add_argument(
        "--job-filtering-target-phrases",
        nargs="*",
        default=[],
        help="Explicit target roles and keywords used by strict title filtering.",
    )
    parser.add_argument(
        "--low-applicant-threshold",
        type=int,
        default=default_low_applicant_threshold,
        help="Applicant count threshold separating low vs high applicant groups for prioritization.",
    )
    parser.add_argument(
        "--debug-enrich-blocks",
        action=argparse.BooleanOptionalAction,
        default=default_debug_enrich_blocks,
    )
    parser.add_argument(
        "--page-fetch-sleep-seconds",
        type=float,
        default=default_page_fetch_sleep_seconds,
        help="Sleep between paginated LinkedIn requests (seconds).",
    )
    parser.add_argument(
        "--use-proxy-fallback",
        action=argparse.BooleanOptionalAction,
        default=default_use_proxy_fallback,
        help="Use ScrapeOps proxy fallback when direct enrichment fails.",
    )
    args = parser.parse_args()

    try:
        run_stage1_pipeline(args)
    except Exception as exc:
        print(f"[Stage1] failed: {exc}")
        return 1
    return 0


def run_stage1_pipeline(args, *, usage_callback=None):
    from backend.domain.phase0_contracts import JOB_FILTERING_MODE_BROADER, JOB_FILTERING_MODE_STRICT
    scrapeops_api_key, deepseek_api_key, so_requests = build_clients()
    cv_summary = load_cv_text()
    proxy_health_confirmed = False

    def ensure_proxy_health() -> None:
        nonlocal proxy_health_confirmed
        if proxy_health_confirmed:
            return
        from backend.integrations.scrapeops import require_scrapeops_proxy_health

        require_scrapeops_proxy_health(scrapeops_api_key, usage_callback=usage_callback)
        proxy_health_confirmed = True

    print("[Stage1] starting pipeline")
    forbidden_title_words = [str(item).lower() for item in (args.forbidden_title_keywords or []) if str(item).strip()]
    if not forbidden_title_words:
        forbidden_title_words = [str(item).lower() for item in FORBIDDEN_WORDS]

    if args.reuse_scrape_snapshot:
        unique_jobs_list = load_jobs_snapshot(args.scrape_snapshot_json)
        print(
            f"[Stage1] reusing scrape snapshot: {args.scrape_snapshot_json} "
            f"({len(unique_jobs_list)} jobs)"
        )
    else:
        all_raw_jobs = []
        for keyword in args.keywords:
            all_raw_jobs.extend(
                fetch_initial_list(
                    keyword=keyword,
                    so_requests=so_requests,
                    max_pages=args.max_pages,
                    geo_id=args.geo_id,
                    time_posted_seconds=max(0, int(args.time_posted_seconds)),
                    experience_levels=args.experience_levels or [],
                    forbidden_title_words=forbidden_title_words,
                    page_fetch_sleep_seconds=max(0.0, float(args.page_fetch_sleep_seconds)),
                )
            )

        unique_jobs_list = list({job["job_id"]: job for job in all_raw_jobs}.values())
        print(f"[Stage1] unique jobs found: {len(unique_jobs_list)}")
        try:
            save_jobs_snapshot(args.scrape_snapshot_json, unique_jobs_list)
            print(f"[Stage1] saved scrape snapshot: {args.scrape_snapshot_json}")
        except Exception as exc:
            print(f"[Stage1] warning: failed to save scrape snapshot '{args.scrape_snapshot_json}': {exc}")

    if not unique_jobs_list:
        print("[Stage1] no jobs available before AI filter, exiting.")
        return []

    existing_job_signatures = load_existing_job_signatures_from_excel(args.existing_jobs_excel)
    if existing_job_signatures:
        before_excel_prefilter = len(unique_jobs_list)
        unique_jobs_list = [
            job
            for job in unique_jobs_list
            if make_job_signature(job.get("title", ""), job.get("company", "")) not in existing_job_signatures
        ]
        skipped_count = before_excel_prefilter - len(unique_jobs_list)
        print(
            f"[Stage1] Excel prefilter: skipped {skipped_count} jobs with duplicate title+company found in "
            f"{args.existing_jobs_excel}"
        )
    else:
        print(f"[Stage1] Excel prefilter: no existing title+company pairs found in {args.existing_jobs_excel}")

    if not unique_jobs_list:
        print("[Stage1] no new jobs left after Excel prefilter, exiting.")
        return []

    ai_approved_jobs, _ = filter_with_ai(
        jobs_list=unique_jobs_list,
        deepseek_api_key=deepseek_api_key,
        cv_summary=cv_summary,
        model=args.model,
        excluded_output=args.excluded_output,
        extra_instructions=args.stage1_extra_prompt,
        prompt_override=args.stage1_prompt_override,
        ai_batch_size=args.ai_batch_size,
        job_filtering_mode=getattr(args, "job_filtering_mode", JOB_FILTERING_MODE_BROADER),
        job_filtering_target_phrases=getattr(args, "job_filtering_target_phrases", []) or [],
        broader_keywords=getattr(args, "keywords", []) or [],
    )
    if not ai_approved_jobs:
        print("[Stage1] no jobs passed AI title filter, exiting.")
        return []

    if args.max_enrich_jobs >= 0:
        ai_approved_jobs = ai_approved_jobs[: args.max_enrich_jobs]
        print(f"[Stage1] enrichment capped to: {len(ai_approved_jobs)}")

    final_output = []
    total = len(ai_approved_jobs)
    print(f"[Stage1] enriching {total} jobs for easy-apply + full description")
    for index, job in enumerate(ai_approved_jobs, start=1):
        print(f"[Stage1] [{index}/{total}] {job['title']}")
        enrich = enrich_job(
            job_id=job["job_id"],
            so_requests=so_requests,
            scrapeops_api_key=scrapeops_api_key,
            debug_enrich_blocks=args.debug_enrich_blocks,
            use_proxy_fallback=args.use_proxy_fallback,
            usage_callback=usage_callback,
            proxy_health_check=ensure_proxy_health,
        )
        job["easy_apply_status"] = enrich["easy_apply_status"]
        job["full_description"] = enrich["description"]
        job["apply_link"] = enrich["apply_link"]
        job["apply_link_source"] = enrich["apply_link_source"]
        job["posted_time_text"] = enrich["posted_time_text"]
        job["posted_age_hours"] = enrich["posted_age_hours"]
        job["posted_datetime_estimated_utc"] = enrich["posted_datetime_estimated_utc"]
        job["applicant_count"] = enrich["applicant_count"]
        job["enrich_error"] = enrich["enrich_error"]
        job["enrich_status_code"] = enrich["status_code"]
        if enrich.get("title"):
            job["title"] = enrich["title"]
        if enrich.get("company"):
            job["company"] = enrich["company"]
        if enrich.get("location_raw"):
            job["location_raw"] = enrich["location_raw"]
        final_output.append(job)

        jd_ok = "OK" if job["full_description"] else "NO"
        print(
            f"[Stage1] result: EasyApply={job['easy_apply_status']} "
            f"| JD={jd_ok} | HTTP={job['enrich_status_code']}"
        )

    final_output.sort(key=lambda item: priority_sort_key(item, max(0, args.low_applicant_threshold)))
    for rank, job in enumerate(final_output, start=1):
        tier = priority_tier(job, max(0, args.low_applicant_threshold))
        tier_label = {
            1: "tier1_newest_non_easy_low_applicants",
            2: "tier2_newest_easy_low_applicants",
            3: "tier3_newest_non_easy_high_or_unknown_applicants",
            4: "tier4_newest_easy_high_or_unknown_applicants",
        }[tier]
        job["priority_rank"] = rank
        job["priority_tier"] = tier
        job["priority_bucket"] = tier_label
        job["priority_rule"] = (
            "1)newest+non_easy+low_applicants,"
            "2)newest+easy+low_applicants,"
            "3)newest+non_easy+high_or_unknown_applicants,"
            "4)newest+easy+high_or_unknown_applicants"
        )

    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(final_output, file, indent=4, ensure_ascii=False)

    print(f"[Stage1] done. saved {len(final_output)} jobs to {args.output}")
    print(f"[Stage1] excluded jobs file: {args.excluded_output}")
    return final_output


__all__ = [
    "build_scrape_requests_client",
    "enrich_job",
    "main",
    "run_stage1_pipeline",
]


if __name__ == "__main__":
    raise SystemExit(main())
