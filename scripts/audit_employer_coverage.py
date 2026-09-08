"""Audit employer checkpoint coverage without scraping or rewriting state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.master_employer_jobs_catalog import EmployerState


EXPECTED_LEGACY_STATE = {
    "records": 428,
    "no_jobs": 194,
    "discovery_failed": 146,
    "partial": 82,
    "source_failed": 5,
    "completed": 1,
}


def build_report(state_db: Path) -> dict[str, object]:
    state = EmployerState.open_existing(state_db)
    try:
        audit = state.coverage_audit()
    finally:
        state.close()
    return {
        "mode": "read_only_employer_coverage_audit",
        "state_db": str(state_db),
        "observed": audit,
        "expected_legacy_state": EXPECTED_LEGACY_STATE,
        "migration_disposition": {
            "no_jobs": {
                "expected": EXPECTED_LEGACY_STATE["no_jobs"],
                "disposition": "recheck_with_bounded_recovery_budget",
                "reason": "historical negative rows lack trustworthy completeness evidence until audited",
            },
            "discovery_failed": {
                "expected": EXPECTED_LEGACY_STATE["discovery_failed"],
                "disposition": "recheck_discovery_and_record_coverage",
            },
            "partial": {
                "expected": EXPECTED_LEGACY_STATE["partial"],
                "disposition": "resume_from_checkpoint_and_revalidate",
            },
            "source_failed": {
                "expected": EXPECTED_LEGACY_STATE["source_failed"],
                "disposition": "recheck_source_with_explicit_failure_outcome",
            },
            "completed": {
                "expected": EXPECTED_LEGACY_STATE["completed"],
                "disposition": "retain_jobs_and_timestamps_but_do_not_treat_as_master_coverage",
            },
            "legacy_jobs": {
                "expected": 2612,
                "disposition": "preserve_original_observations_and_provenance_during_revalidation",
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-db", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = build_report(args.state_db)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
