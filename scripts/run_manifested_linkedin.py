"""Run the LinkedIn collector through an RC-005 eligibility manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.application.source_eligibility_manifest import (
    SOURCE_LINKEDIN,
    materialize_source_input,
    require_eligibility_manifest,
)
from scripts.master_linkedin_jobs_catalog import CatalogRunner, RunnerConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--include-single-source",
        action="store_true",
        help="opt into website-only/LinkedIn-only expansion tasks; default is the dual-source pilot",
    )
    parser.add_argument("--pagination-report", type=Path, default=Path("Jobs-Urls/linkedin_endpoint_pagination_validation.json"))
    parser.add_argument("--filters-report", type=Path, default=Path("Jobs-Urls/linkedin_guest_endpoint_filter_validation.json"))
    parser.add_argument("--mode", choices=("validate", "smoke", "pilot", "full", "daily", "reconcile"), default="full")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--detail-workers", type=int, default=5)
    parser.add_argument("--per-proxy-concurrency", type=int, default=1)
    parser.add_argument("--min-workers", type=int, default=1)
    parser.add_argument("--max-workers", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retry-limit", type=int, default=2)
    parser.add_argument("--max-requests", type=int, default=0)
    parser.add_argument("--detail-refresh-hours", type=float, default=168.0)
    parser.add_argument("--volatile-refresh-hours", type=float, default=24.0)
    parser.add_argument("--company-id")
    parser.add_argument("--resume-run-id")
    parser.add_argument("--max-companies", type=int)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pilot_only = not args.include_single_source
    manifest, tasks = require_eligibility_manifest(args.manifest, SOURCE_LINKEDIN, pilot_only=pilot_only)
    output_dir = args.output_dir.resolve()
    staged_input = output_dir / ".manifest_inputs" / f"{manifest['manifest_id']}-linkedin.csv"
    staged = materialize_source_input(manifest, SOURCE_LINKEDIN, staged_input, pilot_only=pilot_only)
    config = RunnerConfig(
        input_csv=staged_input,
        output_dir=output_dir,
        pagination_report=args.pagination_report,
        filters_report=args.filters_report,
        mode=args.mode,
        workers=args.workers,
        detail_workers=args.detail_workers,
        per_proxy_concurrency=args.per_proxy_concurrency,
        min_workers=args.min_workers,
        max_workers=args.max_workers,
        timeout=args.timeout,
        retry_limit=args.retry_limit,
        max_requests=args.max_requests or None,
        detail_refresh_hours=args.detail_refresh_hours,
        volatile_refresh_hours=args.volatile_refresh_hours,
        company_id=args.company_id,
        resume_run_id=args.resume_run_id,
        fresh=args.fresh,
        dry_run=args.dry_run,
        max_companies=args.max_companies,
    )
    # The low-level producer creates its transport lazily. A dry-run must
    # validate the manifest without requiring provider credentials or making a
    # configuration lookup that could lead to a network call.
    runner = CatalogRunner(config, transport=object() if args.dry_run else None)
    metrics = runner.run()
    metrics.update(
        {
            "eligibility_manifest_id": manifest["manifest_id"],
            "eligibility_manifest_hash": manifest["manifest_hash"],
            "eligibility_source": SOURCE_LINKEDIN,
            "eligibility_tasks": len(tasks),
            "manifest_input": staged,
            "pilot_only": pilot_only,
        }
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
