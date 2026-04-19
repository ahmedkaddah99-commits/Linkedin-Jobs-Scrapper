from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Mapping

from .support import (
    cfg_bool,
    cfg_int,
    cfg_list,
    cfg_str,
    collect_jobs_from_portals,
    compact_whitespace,
    load_reusable_packages_config,
    load_json_file,
    resolve_path,
    save_json_file,
)


def make_job_signature(job: Dict) -> str:
    portal = compact_whitespace(str(job.get("portal") or "")).lower()
    job_id = compact_whitespace(str(job.get("job_id") or ""))
    if portal and job_id:
        return f"{portal}::{job_id}"

    title = compact_whitespace(str(job.get("title") or "")).lower()
    company = compact_whitespace(str(job.get("company") or "")).lower()
    city = compact_whitespace(str(job.get("city") or "")).lower()
    return f"{title}::{company}::{city}"


def deduplicate_jobs(jobs: List[Dict]) -> List[Dict]:
    by_signature: Dict[str, Dict] = {}
    for job in jobs:
        signature = make_job_signature(job)
        if not signature:
            continue
        if signature not in by_signature:
            by_signature[signature] = job
            continue

        existing = by_signature[signature]
        existing_desc_len = len(str(existing.get("description") or ""))
        new_desc_len = len(str(job.get("description") or ""))
        if new_desc_len > existing_desc_len:
            by_signature[signature] = job

    return list(by_signature.values())


def build_stage1_args(
    config: dict | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> SimpleNamespace:
    config = config or load_reusable_packages_config()
    payload = {
        "keywords": [str(item) for item in cfg_list(config, ("job_search", "keywords"), []) if str(item).strip()],
        "cities": [str(item) for item in cfg_list(config, ("job_search", "cities"), []) if str(item).strip()],
        "portals": [str(item) for item in cfg_list(config, ("job_search", "portals"), []) if str(item).strip()],
        "max_pages": max(1, cfg_int(config, ("job_search", "max_pages_per_source"), 2)),
        "radius_km": max(0, cfg_int(config, ("job_search", "radius_km"), 35)),
        "posted_within_days": max(0, cfg_int(config, ("job_search", "posted_within_days"), 14)),
        "max_jobs_total": max(1, cfg_int(config, ("job_search", "max_jobs_total"), 1200)),
        "timeout_seconds": max(5, cfg_int(config, ("runtime", "stage1", "request_timeout_seconds"), 25)),
        "arbeitsagentur_detail_fetch_limit": max(
            0,
            cfg_int(config, ("runtime", "stage1", "arbeitsagentur_detail_fetch_limit"), 20),
        ),
        "output": cfg_str(config, ("runtime", "stage1", "output_json"), "outputs/stage1_scraped_jobs.json"),
        "snapshot": cfg_str(config, ("runtime", "stage1", "snapshot_json"), "outputs/stage1_scrape_snapshot.json"),
        "source_log": cfg_str(config, ("runtime", "stage1", "source_log_json"), "outputs/stage1_source_log.json"),
        "reuse_snapshot": cfg_bool(config, ("runtime", "stage1", "reuse_snapshot"), False),
    }
    if overrides:
        payload.update({key: value for key, value in overrides.items() if value is not None})
    return SimpleNamespace(**payload)


def run_stage1_pipeline(args, *, config: dict | None = None) -> dict[str, Any]:
    _ = config
    keywords = [compact_whitespace(item) for item in args.keywords if compact_whitespace(item)]
    cities = [compact_whitespace(item) for item in args.cities if compact_whitespace(item)]
    portals = [compact_whitespace(item).lower() for item in args.portals if compact_whitespace(item)]

    if not keywords:
        raise ValueError("no keywords configured.")
    if not cities:
        raise ValueError("no target cities configured.")
    if not portals:
        raise ValueError("no portals configured.")

    output_path = resolve_path(args.output)
    snapshot_path = resolve_path(args.snapshot)
    source_log_path = resolve_path(args.source_log)

    if args.reuse_snapshot:
        if not snapshot_path.exists():
            raise FileNotFoundError(f"snapshot file not found: {snapshot_path}")
        raw_jobs = load_json_file(snapshot_path)
        if not isinstance(raw_jobs, list):
            raise ValueError(f"snapshot must be a list: {snapshot_path}")
        source_log = {
            "reused_snapshot": str(snapshot_path),
            "total_jobs_collected": len(raw_jobs),
        }
        print(f"[Stage1] reusing snapshot {snapshot_path} with {len(raw_jobs)} jobs")
    else:
        print(
            "[Stage1] starting scrape with "
            f"{len(portals)} portals, {len(keywords)} keywords, {len(cities)} cities, "
            f"max_pages={max(1, int(args.max_pages))}, max_jobs_total={max(1, int(args.max_jobs_total))}, "
            f"aa_detail_fetch_limit={max(0, int(args.arbeitsagentur_detail_fetch_limit))}"
        )
        raw_jobs, source_log = collect_jobs_from_portals(
            portals=portals,
            keywords=keywords,
            cities=cities,
            max_pages=max(1, int(args.max_pages)),
            posted_within_days=max(0, int(args.posted_within_days)),
            radius_km=max(0, int(args.radius_km)),
            timeout_seconds=max(5, int(args.timeout_seconds)),
            max_jobs_total=max(1, int(args.max_jobs_total)),
            arbeitsagentur_detail_fetch_limit=max(0, int(args.arbeitsagentur_detail_fetch_limit)),
        )
        save_json_file(snapshot_path, raw_jobs)
        print(f"[Stage1] saved scrape snapshot: {snapshot_path}")

    deduped_jobs = deduplicate_jobs(raw_jobs)
    if args.max_jobs_total > 0:
        deduped_jobs = deduped_jobs[: args.max_jobs_total]

    save_json_file(output_path, deduped_jobs)
    save_json_file(source_log_path, source_log)

    print("Stage 1 complete.")
    print(f"Raw jobs: {len(raw_jobs)}")
    print(f"Deduplicated jobs: {len(deduped_jobs)} -> {output_path}")
    print(f"Source log: {source_log_path}")
    return {
        "raw_jobs": raw_jobs,
        "jobs": deduped_jobs,
        "source_log": source_log,
        "output_path": str(output_path),
        "snapshot_path": str(snapshot_path),
        "source_log_path": str(source_log_path),
    }
