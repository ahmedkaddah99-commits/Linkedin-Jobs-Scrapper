"""Run the employer collector through an RC-005 eligibility manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.application.source_eligibility_manifest import (
    SOURCE_EMPLOYER,
    materialize_source_input,
    require_eligibility_manifest,
)
from scripts.master_employer_jobs_catalog import run_collection


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--full", action="store_true")
    parser.add_argument(
        "--include-single-source",
        action="store_true",
        help="opt into website-only/LinkedIn-only expansion tasks; default is the dual-source pilot",
    )
    parser.add_argument("--company-id", default="")
    parser.add_argument("--max-job-links", type=int, default=25)
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--max-browser-requests", type=int, default=10)
    parser.add_argument("--max-targets", type=int, default=25)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pilot_only = not args.include_single_source
    manifest, tasks = require_eligibility_manifest(args.manifest, SOURCE_EMPLOYER, pilot_only=pilot_only)
    output_dir = args.output_dir.resolve()
    staged_input = output_dir / ".manifest_inputs" / f"{manifest['manifest_id']}-employer.csv"
    staged = materialize_source_input(manifest, SOURCE_EMPLOYER, staged_input, pilot_only=pilot_only)
    metrics = run_collection(
        input_csv=staged_input,
        output_dir=output_dir,
        limit=0 if args.full else args.limit,
        company_id=args.company_id,
        dry_run=args.dry_run,
        resume=args.resume,
        max_job_links=args.max_job_links,
        max_pages=args.max_pages,
        max_browser_requests=args.max_browser_requests,
        max_targets=args.max_targets,
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
