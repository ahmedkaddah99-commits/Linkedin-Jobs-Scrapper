"""Generate an offline employer coverage report from fixtures or a state database.

This script does not perform live acquisition.  It reads existing employer state
or the bundled connector-family fixtures and emits a machine-readable coverage
report with the five required classifications.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.acquisition.employer_coverage import build_coverage_receipt
from scripts.audit_employer_coverage import build_report
from scripts.master_employer_jobs_catalog import (
    EMPLOYER_OUTCOMES,
    LEGACY_STATUS_BY_OUTCOME,
    EmployerCollectionResult,
    EmployerCompany,
    EmployerState,
)


FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "employer_coverage" / "connector_families.json"


def _load_scenarios() -> list[dict[str, Any]]:
    if not FIXTURE_PATH.is_file():
        return []
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return payload.get("scenarios", [])


def _derive_status(outcome: str) -> str:
    outcome_norm = str(outcome or "").casefold()
    if outcome_norm in EMPLOYER_OUTCOMES:
        return LEGACY_STATUS_BY_OUTCOME.get(outcome_norm, "partial")
    return "unknown"


def _build_state_from_fixtures(state_db: Path) -> None:
    state_db.parent.mkdir(parents=True, exist_ok=True)
    state = EmployerState(state_db)
    try:
        for scenario in _load_scenarios():
            result = scenario["result"]
            company = result.get("company") or {}
            outcome = result.get("outcome", "")
            state.save(
                EmployerCollectionResult(
                    company=EmployerCompany(
                        canonical_company_id=company.get("canonical_company_id", ""),
                        company_name=company.get("company_name", ""),
                        website_url=company.get("website_url", ""),
                    ),
                    jobs=result.get("jobs", []),
                    targets=result.get("targets", []),
                    failures=result.get("failures", []),
                    status=_derive_status(outcome),
                    outcome=outcome,
                    coverage=result.get("coverage", {}),
                ),
                generation_id="offline-fixture-generation",
                source_version="fixture",
            )
            # Also save a standalone receipt so the report can demonstrate
            # receipt persistence even when the result payload is synthetic.
            receipt = build_coverage_receipt(result, generation_id="offline-fixture-generation", source_version="fixture")
            state.save_coverage_receipt(
                EmployerCollectionResult(
                    company=EmployerCompany(
                        canonical_company_id=company.get("canonical_company_id", ""),
                        company_name=company.get("company_name", ""),
                        website_url=company.get("website_url", ""),
                    ),
                    jobs=result.get("jobs", []),
                    targets=result.get("targets", []),
                    failures=result.get("failures", []),
                    status=result.get("status", ""),
                    outcome=result.get("outcome", ""),
                    coverage=result.get("coverage", {}),
                ),
                generation_id=receipt.generation_id,
                source_version=receipt.source_version,
            )
    finally:
        state.close()


def build_offline_report(*, from_fixtures: bool = False, state_db: Path | None = None) -> dict[str, Any]:
    if from_fixtures:
        if state_db is None:
            state_db = Path(".backend_test_tmp") / "employer_coverage_offline.db"
        _build_state_from_fixtures(state_db)
    if state_db is None:
        raise SystemExit("Provide --state-db or --from-fixtures")
    report = build_report(state_db)
    report["source"] = "fixture_synthesis" if from_fixtures else "existing_state"
    report["evidence_limitation"] = (
        "This report is synthesized from offline fixtures.  It does not claim "
        "universal live completeness or represent historical production state."
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-db", type=Path, help="Existing employer state database")
    parser.add_argument("--from-fixtures", action="store_true", help="Synthesize a state DB from bundled fixtures")
    parser.add_argument("--output", type=Path, help="JSON report output path")
    args = parser.parse_args(argv)

    report = build_offline_report(from_fixtures=args.from_fixtures, state_db=args.state_db)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
