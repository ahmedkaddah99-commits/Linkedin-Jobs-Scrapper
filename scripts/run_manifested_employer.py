"""Run the employer collector through an RC-005 eligibility manifest."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.application.source_eligibility_manifest import (
    SOURCE_EMPLOYER,
    materialize_source_input,
    require_eligibility_manifest,
)
from scripts.master_employer_jobs_catalog import (
    _atomic_write,
    _is_accepted_job_page,
    _text,
    load_employer_companies,
    run_collection,
)

DEFAULT_DRY_RUN_MINUTES = 5
FAILED_COMPANY_STATUSES = frozenset({"failed", "discovery_failed", "source_failed", "collector_error"})


def build_dry_run_receipt(
    *,
    manifest: Mapping[str, Any],
    staged_input: Path,
    output_dir: Path,
    state_dir: Path | None,
    pilot_only: bool,
    duration_budget_seconds: int = DEFAULT_DRY_RUN_MINUTES * 60,
) -> dict[str, Any]:
    """Aggregate a bounded, read-only job-outcome receipt without collection.

    Reads the staged manifest cohort plus the durable employer state (never
    mutating either) and classifies every durable job row for the cohort into
    discovered / accepted / rejected / deduplicated / failed counts. The
    aggregation stops at ``duration_budget_seconds`` so the receipt always
    completes within its five-minute default budget.
    """

    started = time.monotonic()
    deadline = started + max(1, int(duration_budget_seconds))
    staged_input_present = Path(staged_input).is_file()
    companies: list[Any] = []
    load_stats: dict[str, int] = {}
    cohort_keys: set[str] = set()
    if staged_input_present:
        companies, load_stats = load_employer_companies(Path(staged_input))
        cohort_keys = {
            company.canonical_company_id or company.website_url for company in companies
        }
    state_path = (Path(state_dir) if state_dir is not None else output_dir) / "master_employer_jobs_state.db"
    counts = {
        "discovered": 0,
        "accepted": 0,
        "rejected": 0,
        "deduplicated": 0,
        "failed": 0,
    }
    state_present = state_path.is_file()
    company_status_counts: dict[str, int] = {}
    truncated = False
    if state_present:
        from scripts.master_employer_jobs_catalog import EmployerState

        state = EmployerState.open_existing(state_path)
        try:
            seen_identities: set[tuple[str, str, str, str]] = set()
            failed_companies = {
                company.canonical_company_id or company.website_url
                for company in companies
                if state.company_status(company) in FAILED_COMPANY_STATUSES
            }
            for company in companies:
                status = state.company_status(company)
                if status:
                    company_status_counts[status] = company_status_counts.get(status, 0) + 1
            for job in state.iter_jobs():
                if time.monotonic() >= deadline:
                    truncated = True
                    break
                company_id = _text(job.get("canonical_company_id"))
                if company_id and company_id not in cohort_keys:
                    continue
                counts["discovered"] += 1
                # Durable state already dedupes exact (company, provider,
                # tenant, identity) keys; this receipt-level identity instead
                # counts cross-provider/cross-tenant duplicates of the same
                # posting URL for one company. Rows without a URL dedupe by
                # their source job ID.
                job_url = _text(job.get("source_job_url"))
                if job_url:
                    normalized = (urlsplit(job_url).path or job_url).rstrip("/").casefold()
                    identity = (company_id, "url", normalized)
                else:
                    identity = (company_id, "id", _text(job.get("source_job_id")))
                if identity in seen_identities:
                    counts["deduplicated"] += 1
                    continue
                seen_identities.add(identity)
                provider = _text(job.get("source_provider"))
                if company_id in failed_companies:
                    counts["failed"] += 1
                elif _is_accepted_job_page(job, provider):
                    counts["accepted"] += 1
                else:
                    counts["rejected"] += 1
        finally:
            state.close()
    elapsed = time.monotonic() - started
    receipt: dict[str, Any] = {
        "mode": "dry_run",
        "dry_run": True,
        "eligibility_manifest_id": manifest.get("manifest_id", ""),
        "eligibility_manifest_hash": manifest.get("manifest_hash", ""),
        "pilot_only": pilot_only,
        "cohort_companies": len(companies),
        "cohort_duplicate_rows": load_stats.get("duplicate_rows", 0),
        "staged_input_present": staged_input_present,
        "state_path": str(state_path),
        "state_present": state_present,
        "job_receipt": counts,
        "company_status_counts": company_status_counts,
        "duration_budget_seconds": int(duration_budget_seconds),
        "elapsed_seconds": round(elapsed, 3),
        "duration_budget_exhausted": truncated,
        "truncated": truncated,
        "eligibility_source": SOURCE_EMPLOYER,
        "manifest_input": str(staged_input),
    }
    receipt_path = Path(output_dir) / "employer_dry_run_receipt.json"
    receipt["receipt_path"] = str(receipt_path)
    _atomic_write(receipt_path, lambda target: target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"))
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--state-dir",
        type=Path,
        help="directory containing the durable SQLite state; defaults to --output-dir",
    )
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--full", action="store_true")
    parser.add_argument(
        "--include-single-source",
        action="store_true",
        help="opt into website-only/LinkedIn-only expansion tasks; default is the dual-source pilot",
    )
    parser.add_argument("--company-id", default="")
    parser.add_argument("--company-ids", nargs="+", help="exact eligible canonical IDs for a bounded cohort")
    parser.add_argument("--max-job-links", type=int, default=25)
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--max-browser-requests", type=int, default=10)
    parser.add_argument("--max-targets", type=int, default=25)
    parser.add_argument(
        "--max-requests",
        type=int,
        default=0,
        help="Bound total HTTP/browser attempts for this company collection.",
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--dry-run-receipt",
        action="store_true",
        help="with --dry-run, aggregate the bounded five-minute dry-run receipt "
        "from the staged manifest input and existing durable state",
    )
    parser.add_argument(
        "--dry-run-minutes",
        type=int,
        default=DEFAULT_DRY_RUN_MINUTES,
        help="wall-clock budget for the dry-run receipt; default five minutes",
    )
    parser.add_argument(
        "--require-existing-state",
        action="store_true",
        help="fail instead of creating a missing restored state database",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.limit <= 0 and not args.full:
        parser.error("--limit must be positive; use --full for an unrestricted run")
    if args.max_requests < 0:
        parser.error("--max-requests must not be negative")
    if args.dry_run_minutes <= 0:
        parser.error("--dry-run-minutes must be positive")
    if args.dry_run_receipt and not args.dry_run:
        parser.error("--dry-run-receipt requires --dry-run")
    if args.company_id and args.company_ids:
        parser.error("use either --company-id or --company-ids")
    if args.company_ids and not args.full and len(set(args.company_ids)) > args.limit:
        parser.error("--limit must cover every requested company ID")
    pilot_only = not args.include_single_source
    manifest, tasks = require_eligibility_manifest(args.manifest, SOURCE_EMPLOYER, pilot_only=pilot_only)
    output_dir = args.output_dir.resolve()
    state_dir = args.state_dir.resolve() if args.state_dir is not None else None
    staged_input = output_dir / ".manifest_inputs" / f"{manifest['manifest_id']}-employer.csv"
    cohort = args.company_ids or ([args.company_id] if args.company_id else None)
    staged = materialize_source_input(
        manifest, SOURCE_EMPLOYER, staged_input, pilot_only=pilot_only, company_ids=cohort
    )
    if args.dry_run and args.dry_run_receipt:
        metrics = build_dry_run_receipt(
            manifest=manifest,
            staged_input=staged_input,
            output_dir=output_dir,
            state_dir=state_dir,
            pilot_only=pilot_only,
            duration_budget_seconds=args.dry_run_minutes * 60,
        )
    else:
        metrics = run_collection(
            input_csv=staged_input,
            output_dir=output_dir,
            limit=0 if args.full else args.limit,
            state_dir=state_dir,
            require_existing_state=args.require_existing_state,
            company_id=args.company_id,
            dry_run=args.dry_run,
            resume=args.resume,
            max_job_links=args.max_job_links,
            max_pages=args.max_pages,
            max_browser_requests=args.max_browser_requests,
            max_targets=args.max_targets,
            max_requests=args.max_requests or None,
            timeout_seconds=args.timeout,
        )
        metrics.update(
            {
                "eligibility_manifest_id": manifest["manifest_id"],
                "eligibility_manifest_hash": manifest["manifest_hash"],
                "eligibility_source": SOURCE_EMPLOYER,
                "eligibility_tasks": len(tasks),
                "manifest_input": staged,
                "pilot_only": pilot_only,
            }
        )
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
