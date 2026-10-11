"""Focused regression tests for employer coverage evidence correctness.

These tests pin the exact defects called out in the handoff: expected totals
must come from independent source evidence, traversal counts must be measured
or unknown, a cap/missing partition/unresolved detail/contradiction can never
become confirmed complete, and an old complete scan never makes a newer scan
closure-safe.
"""

from __future__ import annotations

from backend.acquisition.employer_coverage import (
    EmployerCoverageReceipt,
    build_coverage_receipt,
    classify_legacy_result,
    merge_receipts,
)


def _result(
    *,
    provider: str = "greenhouse",
    status: str = "complete_with_jobs",
    outcome: str = "complete_with_jobs",
    observed: int = 3,
    accepted: int = 3,
    complete: bool = True,
    pagination_complete: bool = True,
    pending_detail: int = 0,
    stop_reason: str = "pagination_complete",
    expected_count: int | None = None,
    source_reported_total: int | None = None,
    extraction_methods: list[str] | None = None,
    coverage: dict | None = None,
) -> dict:
    return {
        "company": {"canonical_company_id": "co-1", "company_name": "Co", "website_url": "https://co.example"},
        "jobs": [{"source_job_id": str(i)} for i in range(accepted)],
        "targets": [
            {
                "url": "https://boards.greenhouse.io/co",
                "provider": provider,
                "discovery_method": "ats_signature",
                "status": status,
                "expected_count": expected_count,
                "counts": {
                    "jobs_observed": observed,
                    "jobs_accepted": accepted,
                    "requests": 1,
                    "pages": 1,
                    "detail_failures": pending_detail,
                    "source_reported_total": source_reported_total,
                },
                "extraction_methods": extraction_methods or ["ats_api"],
                "stop_reason": stop_reason,
                "complete_snapshot": complete,
                "completeness_evidence": {
                    "complete_snapshot": complete,
                    "pagination_complete": pagination_complete,
                    "credible_evidence": True,
                },
            }
        ],
        "failures": [],
        "status": status,
        "outcome": outcome,
        "coverage": coverage or {"outcome": outcome, "stop_reason": "collection_completed"},
    }


def test_expected_count_is_unknown_without_independent_source_total() -> None:
    receipt = build_coverage_receipt(_result(observed=7, accepted=7))

    assert receipt.attempts[0].expected_count is None
    assert receipt.attempts[0].observed_count == 7


def test_expected_count_uses_independent_source_total_not_observed() -> None:
    # Source reports 10 jobs; only 7 observed.  The receipt must record the
    # source total (10) independently and must NOT mark the scan complete.
    receipt = build_coverage_receipt(_result(observed=7, accepted=7, source_reported_total=10))

    assert receipt.attempts[0].expected_count == 10
    assert receipt.terminal_classification == "partial"


def test_reconciliation_accepts_matching_source_total() -> None:
    receipt = build_coverage_receipt(_result(observed=5, accepted=5, source_reported_total=5))

    assert receipt.attempts[0].expected_count == 5
    assert receipt.terminal_classification == "confirmed_complete"


def test_partition_counts_are_unknown_when_not_measured() -> None:
    receipt = build_coverage_receipt(_result())

    assert receipt.attempts[0].partitions_attempted is None
    assert receipt.attempts[0].partitions_completed is None


def test_generic_site_cannot_be_confirmed_complete_without_partition_proof() -> None:
    receipt = build_coverage_receipt(
        _result(
            provider="generic_employer_site",
            outcome="complete_with_jobs",
            complete=True,
            pagination_complete=True,
            extraction_methods=["json_ld"],
        )
    )

    assert receipt.attempts[0].partition_state == "unknown"
    assert receipt.terminal_classification == "partial"


def test_native_ats_is_flat_and_can_be_confirmed_complete() -> None:
    receipt = build_coverage_receipt(_result(provider="greenhouse"))

    assert receipt.attempts[0].partition_state == "flat"
    assert receipt.terminal_classification == "confirmed_complete"


def test_result_cap_cannot_be_confirmed_complete() -> None:
    receipt = build_coverage_receipt(
        _result(stop_reason="max_pages", complete=True, pagination_complete=False)
    )

    assert receipt.terminal_classification == "partial"


def test_pending_detail_cannot_be_confirmed_complete() -> None:
    receipt = build_coverage_receipt(_result(pending_detail=2))

    assert receipt.terminal_classification == "partial"


def test_complementary_partition_skipped_is_not_confirmed_complete() -> None:
    receipt = build_coverage_receipt(
        _result(
            coverage={
                "outcome": "complete_with_jobs",
                "stop_reason": "collection_completed",
                "discovery": {
                    "complementary_partitions_skipped": [
                        {"url": "https://boards.greenhouse.io/co-emea", "ats_type": "greenhouse"}
                    ]
                },
            }
        )
    )

    assert receipt.terminal_classification == "partial"


def test_budget_exhaustion_preserves_retryable_progress() -> None:
    result = {
        "company": {"canonical_company_id": "co-1", "company_name": "Co", "website_url": "https://co.example"},
        "jobs": [],
        "targets": [],
        "failures": [{"stage": "company", "error": "RequestBudgetExceeded", "reason": "request_budget_exhausted"}],
        "outcome": "partial",
        "coverage": {"outcome": "partial", "stop_reason": "request_budget_exhausted", "request_budget_exhausted": True},
    }

    receipt = build_coverage_receipt(result)

    assert receipt.terminal_classification == "partial"
    assert "request_budget_exhausted" in receipt.reasons


def test_old_complete_scan_never_makes_new_scan_closure_safe() -> None:
    old_complete = EmployerCoverageReceipt(
        company_id="co-1",
        terminal_classification="confirmed_complete",
        created_at="2026-09-01T00:00:00Z",
        generation_id="gen-old",
    )
    new_failed = EmployerCoverageReceipt(
        company_id="co-1",
        terminal_classification="failed",
        generation_id="gen-new",
    )

    merged = merge_receipts(old_complete, new_failed)

    assert merged.terminal_classification == "failed"
    assert merged.last_confirmed_complete_at == "2026-09-01T00:00:00Z"
    assert merged.last_confirmed_complete_generation == "gen-old"


def test_legacy_result_classification_never_confirms_complete() -> None:
    # Historical runs recorded no pagination/partition evidence, so even a
    # positive "completed" row is only partial.
    assert classify_legacy_result({"status": "completed", "jobs": [{"id": 1}]}) == "partial"
    # A browser timeout is a failure, not a confirmed zero.
    assert classify_legacy_result({"status": "no_jobs", "targets": [{"status": "browser_failed"}]}) == "failed"
    # A genuine empty returned page is a suspicious empty, not a confirmed zero.
    assert classify_legacy_result({"status": "no_jobs", "targets": [{"status": "completed"}]}) == "partial"
    assert classify_legacy_result({"status": "discovery_failed"}) == "failed"
    assert classify_legacy_result({"status": "source_failed"}) == "failed"
    assert classify_legacy_result({"status": "no_jobs", "targets": [{"status": "blocked"}]}) == "blocked"
