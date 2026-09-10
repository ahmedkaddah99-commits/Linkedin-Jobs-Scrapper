"""Audit employer checkpoint coverage without scraping or rewriting state.

Produces a machine-readable per-company coverage report that distinguishes:
- confirmed_complete
- partial
- blocked
- failed
- unknown
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.acquisition.employer_coverage import (
    COVERAGE_CLASSIFICATIONS,
    EmployerCoverageReceipt,
)
from scripts.master_employer_jobs_catalog import EmployerState


EXPECTED_LEGACY_STATE = {
    "records": 428,
    "no_jobs": 194,
    "discovery_failed": 146,
    "partial": 82,
    "source_failed": 5,
    "completed": 1,
}


def _receipt_from_state(state: EmployerState) -> list[EmployerCoverageReceipt]:
    return state.coverage_receipts()


def _classify_from_payload(payload: dict[str, Any]) -> str:
    """Fallback classification for companies without a persisted receipt."""

    coverage = payload.get("coverage") or {}
    outcome = str(coverage.get("outcome") or payload.get("outcome") or payload.get("status") or "").casefold()
    if outcome in {"blocked"}:
        return "blocked"
    if outcome in {"failed", "collector_error", "discovery_failed", "source_failed", "unsupported"}:
        return "failed"
    if outcome in {"complete_with_jobs", "confirmed_zero", "completed", "no_jobs"}:
        # Without a receipt we cannot prove completeness, so historical
        # complete-looking rows are reported as partial/unknown rather than
        # asserted complete.
        return "partial"
    if outcome in {"partial"}:
        return "partial"
    return "unknown"


def _receipts_for_all_companies(state: EmployerState) -> list[EmployerCoverageReceipt]:
    """Return receipts for all companies, synthesizing unknown ones when missing."""

    from backend.acquisition.employer_coverage import EndpointAttempt, build_coverage_receipt

    receipts = {r.company_id: r for r in state.coverage_receipts()}
    rows = state.connection.execute("SELECT company_key, payload_json FROM companies ORDER BY company_key").fetchall()
    for row in rows:
        key = str(row["company_key"])
        if key in receipts:
            continue
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        classification = _classify_from_payload(payload)
        company = payload.get("company") or {}
        attempts: list[EndpointAttempt] = []
        targets = payload.get("targets") or []
        if isinstance(targets, list) and len(targets) == 1:
            target = targets[0]
            if isinstance(target, dict):
                attempts.append(
                    EndpointAttempt(
                        url=str(target.get("url") or ""),
                        connector_family="generic_direct",
                        transport="direct",
                        pages_attempted=int(target.get("counts", {}).get("pages") or 0),
                        pages_completed=0,
                        partitions_attempted=1,
                        partitions_completed=0,
                        expected_count=None,
                        observed_count=int(target.get("counts", {}).get("jobs_observed") or 0),
                        accepted_count=int(target.get("counts", {}).get("jobs_accepted") or 0),
                        pending_detail_count=int(target.get("counts", {}).get("detail_failures") or 0),
                        complete=bool(target.get("complete_snapshot")),
                        stop_reason=str(target.get("stop_reason") or ""),
                    )
                )
        receipt = EmployerCoverageReceipt(
            company_id=key,
            company_name=str(company.get("company_name") or ""),
            website_url=str(company.get("website_url") or ""),
            endpoint_used=attempts[0].url if attempts else "",
            connector_family=attempts[0].connector_family if attempts else "",
            attempts=attempts,
            persisted_job_count=len(payload.get("jobs") or []),
            terminal_classification=classification,
            reasons=["no_coverage_receipt_available"],
        )
        receipts[key] = receipt
    return list(receipts.values())


def build_report(state_db: Path) -> dict[str, object]:
    state = EmployerState.open_existing(state_db)
    try:
        audit = state.coverage_audit()
        receipts = _receipts_for_all_companies(state)
    finally:
        state.close()

    classification_counts = Counter(r.terminal_classification for r in receipts)
    by_classification: dict[str, list[dict[str, Any]]] = {cls: [] for cls in COVERAGE_CLASSIFICATIONS}
    for receipt in receipts:
        by_classification[receipt.terminal_classification].append(receipt.to_dict())

    return {
        "mode": "read_only_employer_coverage_audit",
        "state_db": str(state_db),
        "generated_at": _utc_now(),
        "observed": audit,
        "company_count": len(receipts),
        "classification_counts": {cls: classification_counts.get(cls, 0) for cls in COVERAGE_CLASSIFICATIONS},
        "by_classification": by_classification,
        "expected_legacy_state": EXPECTED_LEGACY_STATE,
        "disposition": {
            "confirmed_complete": {
                "description": "Authoritative endpoint exhausted with no unvisited partitions, no pending details, and no active block.",
                "disposition": "eligible_for_publication_decision",
            },
            "partial": {
                "description": "Some evidence collected but completeness cannot be established.",
                "disposition": "recheck_with_bounded_recovery_budget",
            },
            "blocked": {
                "description": "Active challenge, CAPTCHA, rate limit, or access denial.",
                "disposition": "recheck_source_with_explicit_failure_outcome",
            },
            "failed": {
                "description": "Source error, unsupported ATS, or discovery failure.",
                "disposition": "recheck_source_with_explicit_failure_outcome",
            },
            "unknown": {
                "description": "No usable evidence or missing coverage receipt.",
                "disposition": "recheck_discovery_and_record_coverage",
            },
        },
    }


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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
