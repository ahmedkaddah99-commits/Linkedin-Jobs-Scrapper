from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.acquisition.employer_coverage import (
    EndpointAttempt,
    EmployerCoverageReceipt,
    build_coverage_receipt,
    merge_receipts,
)
from scripts.audit_employer_coverage import _classify_from_payload, build_report
from scripts.master_employer_jobs_catalog import (
    EmployerCollectionResult,
    EmployerCompany,
    EmployerState,
    collect_company,
    run_collection,
)


def _company(company_id: str = "company-1") -> EmployerCompany:
    return EmployerCompany(
        canonical_company_id=company_id,
        company_name="Company One",
        website_url="https://company.example",
    )


def _complete_ats_result(jobs: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "company": {
            "canonical_company_id": "company-1",
            "company_name": "Company One",
            "website_url": "https://company.example",
        },
        "jobs": jobs or [],
        "targets": [
            {
                "url": "https://boards.greenhouse.io/company",
                "provider": "greenhouse",
                "discovery_method": "ats_signature",
                "status": "complete_with_jobs" if jobs else "confirmed_zero",
                "counts": {
                    "jobs_observed": len(jobs or []),
                    "jobs_accepted": len(jobs or []),
                    "requests": 1,
                    "pages": 1,
                    "detail_failures": 0,
                },
                "extraction_methods": ["ats_api"],
                "stop_reason": "pagination_complete",
                "complete_snapshot": True,
                "completeness_evidence": {
                    "complete_snapshot": True,
                    "pagination_complete": True,
                    "credible_evidence": True,
                },
            }
        ],
        "failures": [],
        "status": "completed" if jobs else "no_jobs",
        "outcome": "complete_with_jobs" if jobs else "confirmed_zero",
        "coverage": {
            "outcome": "complete_with_jobs" if jobs else "confirmed_zero",
            "stop_reason": "collection_completed",
            "completeness_evidence": {"complete_snapshot": True},
            "recheck_policy": {"recheck_required": False},
        },
    }


def test_receipt_for_complete_ats_with_jobs() -> None:
    result = _complete_ats_result(
        [{"job_id": "42", "title": "Engineer", "job_detail_url": "https://boards.greenhouse.io/company/jobs/42"}]
    )
    receipt = build_coverage_receipt(result, generation_id="gen-1", source_version="abc123")

    assert receipt.terminal_classification == "confirmed_complete"
    assert receipt.company_id == "company-1"
    assert receipt.connector_family == "ats_native"
    assert receipt.persisted_job_count == 1
    assert receipt.attempts[0].complete is True
    assert receipt.attempts[0].stop_reason == "pagination_complete"
    assert "gen-1" in receipt.to_json()


def test_receipt_for_confirmed_zero_ats() -> None:
    result = _complete_ats_result([])
    receipt = build_coverage_receipt(result)

    assert receipt.terminal_classification == "confirmed_complete"
    assert receipt.persisted_job_count == 0
    assert receipt.reasons == []


def test_receipt_for_incomplete_source_is_partial() -> None:
    result = {
        "company": {"canonical_company_id": "company-1", "company_name": "Company One", "website_url": "https://company.example"},
        "jobs": [{"job_id": "1", "title": "Engineer"}],
        "targets": [
            {
                "url": "https://company.example/careers",
                "provider": "generic_employer_site",
                "status": "partial",
                "counts": {"jobs_observed": 1, "jobs_accepted": 1, "requests": 1, "pages": 1, "detail_failures": 0},
                "extraction_methods": ["json_ld"],
                "stop_reason": "pagination_unverified",
                "complete_snapshot": False,
                "completeness_evidence": {"complete_snapshot": False},
            }
        ],
        "failures": [],
        "outcome": "partial",
        "coverage": {"outcome": "partial", "stop_reason": "collection_uncertain"},
    }
    receipt = build_coverage_receipt(result)

    assert receipt.terminal_classification == "partial"
    assert receipt.attempts[0].complete is False


def test_receipt_for_blocked_source() -> None:
    result = {
        "company": {"canonical_company_id": "company-1", "company_name": "Company One", "website_url": "https://company.example"},
        "jobs": [],
        "targets": [
            {
                "url": "https://company.example/careers",
                "provider": "generic_employer_site",
                "status": "blocked",
                "counts": {"jobs_observed": 0, "jobs_accepted": 0, "requests": 1, "pages": 0, "detail_failures": 0},
                "extraction_methods": [],
                "stop_reason": "challenge_page",
                "complete_snapshot": False,
            }
        ],
        "failures": [{"stage": "source", "error": "cf-chl- challenge page"}],
        "outcome": "blocked",
        "coverage": {"outcome": "blocked", "stop_reason": "challenge_page"},
    }
    receipt = build_coverage_receipt(result)

    assert receipt.terminal_classification == "blocked"
    assert "source:cf-chl- challenge page" in receipt.reasons


def test_receipt_for_request_budget_exhausted() -> None:
    result = {
        "company": {"canonical_company_id": "company-1", "company_name": "Company One", "website_url": "https://company.example"},
        "jobs": [],
        "targets": [],
        "failures": [{"stage": "company", "error": "RequestBudgetExceeded", "reason": "request_budget_exhausted", "max_requests": 8}],
        "outcome": "partial",
        "coverage": {"outcome": "partial", "stop_reason": "request_budget_exhausted", "request_budget_exhausted": True},
    }
    receipt = build_coverage_receipt(result)

    assert receipt.terminal_classification == "partial"
    assert "company:request_budget_exhausted" in receipt.reasons


def test_merge_receipts_current_generation_wins_and_preserves_history() -> None:
    complete = EmployerCoverageReceipt(
        company_id="c1",
        terminal_classification="confirmed_complete",
        endpoint_used="https://boards.greenhouse.io/c1",
        created_at="2026-09-01T00:00:00Z",
        generation_id="gen-old",
    )
    partial = EmployerCoverageReceipt(
        company_id="c1",
        terminal_classification="partial",
        endpoint_used="https://company.example/careers",
    )

    merged = merge_receipts(complete, partial)
    assert merged.terminal_classification == "partial"
    assert merged.last_confirmed_complete_at == "2026-09-01T00:00:00Z"
    assert merged.last_confirmed_complete_generation == "gen-old"

    # A newer complete scan simply wins.
    newer_complete = EmployerCoverageReceipt(
        company_id="c1",
        terminal_classification="confirmed_complete",
        generation_id="gen-new",
    )
    assert merge_receipts(partial, newer_complete) is newer_complete


def test_state_persists_and_retrieves_receipt(tmp_path: Path) -> None:
    state = EmployerState(tmp_path / "state.db")
    try:
        result = EmployerCollectionResult(
            company=_company(),
            jobs=[{"source_job_id": "42"}],
            status="completed",
            outcome="complete_with_jobs",
            targets=[
                {
                    "url": "https://boards.greenhouse.io/company",
                    "provider": "greenhouse",
                    "discovery_method": "ats_signature",
                    "status": "complete_with_jobs",
                    "counts": {"jobs_observed": 1, "jobs_accepted": 1, "requests": 1, "pages": 1, "detail_failures": 0},
                    "extraction_methods": ["ats_api"],
                    "stop_reason": "pagination_complete",
                    "complete_snapshot": True,
                    "completeness_evidence": {"complete_snapshot": True, "pagination_complete": True},
                }
            ],
            coverage={
                "outcome": "complete_with_jobs",
                "completeness_evidence": {"complete_snapshot": True},
                "recheck_policy": {"recheck_required": False},
            },
        )
        state.save(result, generation_id="gen-1", source_version="v1")
        receipt = state.coverage_receipt(_company())
    finally:
        state.close()

    assert receipt is not None
    assert receipt.terminal_classification == "confirmed_complete"
    assert receipt.attempts[0].connector_family == "ats_native"


def test_run_collection_saves_receipts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "companies.csv"
    source.write_text(
        "canonical_CompanyID,company_name,website_url\ncompany-1,Company One,https://company.example\n",
        encoding="utf-8",
    )

    def fake_collect(company, _fetcher, _limits):
        return EmployerCollectionResult(
            company=company,
            jobs=[{"source_job_id": "42", "source_provider": "greenhouse", "extraction_method": "ats_api"}],
            status="completed",
            outcome="complete_with_jobs",
            targets=[
                {
                    "url": "https://boards.greenhouse.io/company",
                    "provider": "greenhouse",
                    "discovery_method": "ats_signature",
                    "status": "complete_with_jobs",
                    "counts": {"jobs_observed": 1, "jobs_accepted": 1, "requests": 1, "pages": 1, "detail_failures": 0},
                    "extraction_methods": ["ats_api"],
                    "stop_reason": "pagination_complete",
                    "complete_snapshot": True,
                    "completeness_evidence": {"complete_snapshot": True, "pagination_complete": True},
                }
            ],
            coverage={
                "outcome": "complete_with_jobs",
                "completeness_evidence": {"complete_snapshot": True},
                "recheck_policy": {"recheck_required": False},
            },
        )

    monkeypatch.setattr("scripts.master_employer_jobs_catalog.requests_fetcher", lambda *_: lambda _url: None)
    monkeypatch.setattr("scripts.master_employer_jobs_catalog.collect_company", fake_collect)

    metrics = run_collection(input_csv=source, output_dir=tmp_path / "out", limit=1, resume=False)

    assert metrics["companies_processed"] == 1
    state = EmployerState(tmp_path / "out" / "master_employer_jobs_state.db")
    try:
        receipts = state.coverage_receipts()
        classifications = [r.terminal_classification for r in receipts]
    finally:
        state.close()
    assert classifications == ["confirmed_complete"]


def test_audit_report_classifies_missing_receipts_as_unknown(tmp_path: Path) -> None:
    state = EmployerState(tmp_path / "state.db")
    try:
        state.save(
            EmployerCollectionResult(
                company=_company(),
                status="discovery_failed",
                outcome="failed",
                coverage={"outcome": "failed"},
            )
        )
    finally:
        state.close()

    report = build_report(tmp_path / "state.db")

    assert report["classification_counts"]["failed"] == 1
    assert report["company_count"] == 1
    assert report["by_classification"]["failed"][0]["company_id"] == "company-1"


def test_multiple_connector_families_are_distinguished() -> None:
    def make_result(provider: str, method: str) -> dict[str, object]:
        return {
            "company": {"canonical_company_id": provider, "company_name": provider, "website_url": f"https://{provider}.example"},
            "jobs": [],
            "targets": [
                {
                    "url": f"https://{provider}.example/careers",
                    "provider": provider,
                    "status": "confirmed_zero",
                    "counts": {"jobs_observed": 0, "jobs_accepted": 0, "requests": 1, "pages": 1, "detail_failures": 0},
                    "extraction_methods": [method],
                    "stop_reason": "pagination_complete",
                    "complete_snapshot": True,
                }
            ],
            "failures": [],
            "outcome": "confirmed_zero",
            "coverage": {"outcome": "confirmed_zero"},
        }

    cases = [
        ("greenhouse", "ats_api", "ats_native"),
        ("workday", "ats_api", "ats_expansion"),
        ("generic_employer_site", "json_ld", "generic_direct"),
    ]
    for provider, method, expected_family in cases:
        receipt = build_coverage_receipt(make_result(provider, method))
        assert receipt.connector_family == expected_family, provider


def test_classify_from_payload_fallback() -> None:
    assert _classify_from_payload({"outcome": "blocked"}) == "blocked"
    assert _classify_from_payload({"outcome": "failed"}) == "failed"
    assert _classify_from_payload({"outcome": "complete_with_jobs"}) == "partial"
    assert _classify_from_payload({}) == "unknown"


def test_connector_family_fixtures(tmp_path: Path) -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "employer_coverage" / "connector_families.json"
    scenarios = json.loads(fixture_path.read_text(encoding="utf-8"))["scenarios"]
    failures: list[str] = []
    for scenario in scenarios:
        receipt = build_coverage_receipt(scenario["result"])
        if receipt.connector_family != scenario["family"]:
            failures.append(f"{scenario['name']}: expected family {scenario['family']}, got {receipt.connector_family}")
        if receipt.terminal_classification != scenario["expected_classification"]:
            failures.append(
                f"{scenario['name']}: expected classification {scenario['expected_classification']}, "
                f"got {receipt.terminal_classification}"
            )
    assert not failures, "\n".join(failures)


def test_crash_resume_preserves_completed_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "companies.csv"
    source.write_text(
        "canonical_CompanyID,company_name,website_url\n"
        "completed,Completed Co,https://completed.example\n"
        "stalling,Stalling Co,https://stalling.example\n",
        encoding="utf-8",
    )

    completed_event = {"set": False}

    def fake_collect(company, _fetcher, _limits):
        if company.canonical_company_id == "completed":
            completed_event["set"] = True
            return EmployerCollectionResult(
                company=company,
                jobs=[{"source_job_id": "42"}],
                status="completed",
                outcome="complete_with_jobs",
                targets=[
                    {
                        "url": "https://boards.greenhouse.io/completed",
                        "provider": "greenhouse",
                        "status": "complete_with_jobs",
                        "counts": {"jobs_observed": 1, "jobs_accepted": 1, "requests": 1, "pages": 1, "detail_failures": 0},
                        "extraction_methods": ["ats_api"],
                        "stop_reason": "pagination_complete",
                        "complete_snapshot": True,
                        "completeness_evidence": {"complete_snapshot": True},
                    }
                ],
                coverage={"outcome": "complete_with_jobs", "completeness_evidence": {"complete_snapshot": True}},
            )
        raise RuntimeError("simulated worker crash")

    monkeypatch.setattr("scripts.master_employer_jobs_catalog.requests_fetcher", lambda *_: lambda _url: None)
    monkeypatch.setattr("scripts.master_employer_jobs_catalog.collect_company", fake_collect)

    try:
        run_collection(input_csv=source, output_dir=tmp_path / "out", limit=2, resume=False)
    except RuntimeError:
        pass

    state = EmployerState(tmp_path / "out" / "master_employer_jobs_state.db")
    try:
        completed_receipt = state.coverage_receipt(
            EmployerCompany(canonical_company_id="completed", company_name="Completed Co", website_url="https://completed.example")
        )
        stalling_status = state.company_status(
            EmployerCompany(canonical_company_id="stalling", company_name="Stalling Co", website_url="https://stalling.example")
        )
    finally:
        state.close()

    assert completed_event["set"] is True
    assert completed_receipt is not None
    assert completed_receipt.terminal_classification == "confirmed_complete"
    # The crashed worker is checkpointed as collector_error by the existing
    # bounded worker wrapper; the important property is that the completed
    # sibling remains confirmed_complete in the same state file.
    assert stalling_status == "collector_error"
