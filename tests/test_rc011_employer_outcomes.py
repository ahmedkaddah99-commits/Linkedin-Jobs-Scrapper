from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from scripts.master_employer_jobs_catalog import (
    CollectorLimits,
    EmployerCollectionResult,
    EmployerCompany,
    EmployerState,
    collect_company,
    load_employer_companies,
    run_collection,
)


def _company() -> EmployerCompany:
    return EmployerCompany(
        canonical_company_id="company-1",
        company_name="Company One",
        website_url="https://company.example",
    )


def _discovery(url: str = "https://company.example/careers", ats_type: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        primary_career_url=url,
        candidates=[SimpleNamespace(url=url, source="test", ats_type=ats_type)],
        crawl_status="found",
    )


def test_uncertain_empty_source_is_not_confirmed_zero(monkeypatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    monkeypatch.setattr(catalog, "discover_career_url", lambda **_: _discovery())
    monkeypatch.setattr(
        catalog,
        "fetch_generic_snapshot",
        lambda *_, **__: {
            "jobs": [],
            "status": "completed",
            "complete_snapshot": False,
            "credible_evidence": False,
            "request_url": "https://company.example/careers",
        },
    )
    monkeypatch.setattr(
        catalog,
        "fetch_browser_snapshot",
        lambda *_, **__: {
            "jobs": [],
            "status": "browser_failed",
            "error": "timeout",
            "complete_snapshot": False,
            "credible_evidence": False,
        },
    )

    result = collect_company(_company(), lambda _: SimpleNamespace(text="", final_url=""), CollectorLimits(max_targets=1))

    assert result.status != "no_jobs"
    assert result.outcome in {"failed", "partial"}
    assert result.coverage["completeness_evidence"]["complete_snapshot"] is False
    assert result.targets[0]["complete_snapshot"] is False


def test_complete_empty_ats_snapshot_confirms_zero_without_browser_fallback(monkeypatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    monkeypatch.setattr(catalog, "discover_career_url", lambda **_: _discovery(ats_type="greenhouse"))
    monkeypatch.setattr(
        catalog,
        "fetch_ats_snapshot",
        lambda *_, **__: {
            "jobs": [],
            "status": "completed",
            "complete_snapshot": True,
            "pagination_complete": True,
            "credible_evidence": True,
            "request_url": "https://boards.greenhouse.io/company",
            "pages_fetched": 1,
            "requests_made": 1,
            "stop_reason": "pagination_complete",
        },
    )
    monkeypatch.setattr(catalog, "fetch_generic_snapshot", lambda *_, **__: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(catalog, "fetch_browser_snapshot", lambda *_, **__: (_ for _ in ()).throw(AssertionError()))

    result = collect_company(_company(), lambda _: (_ for _ in ()).throw(AssertionError()), CollectorLimits(max_targets=1))

    assert result.status == "no_jobs"
    assert result.outcome == "confirmed_zero"
    assert result.targets[0]["stop_reason"] == "pagination_complete"


def test_partial_ats_result_continues_through_browser_fallback(monkeypatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    browser_calls: list[str] = []
    monkeypatch.setattr(catalog, "discover_career_url", lambda **_: _discovery(ats_type="greenhouse"))
    monkeypatch.setattr(
        catalog,
        "fetch_ats_snapshot",
        lambda *_, **__: {
            "jobs": [
                {
                    "job_id": "ats-1",
                    "title": "ATS Engineer",
                    "job_detail_url": "https://company.example/jobs/ats-1",
                    "location": "Berlin, Germany",
                }
            ],
            "status": "incomplete",
            "complete_snapshot": False,
            "pagination_complete": False,
            "credible_evidence": True,
            "stop_reason": "max_pages",
        },
    )
    monkeypatch.setattr(
        catalog,
        "fetch_generic_snapshot",
        lambda *_, **__: {
            "jobs": [],
            "status": "failed",
            "complete_snapshot": False,
            "credible_evidence": False,
            "error": "parser_failure",
        },
    )
    monkeypatch.setattr(
        catalog,
        "fetch_browser_snapshot",
        lambda url, **__: (
            browser_calls.append(url)
            or {
                "jobs": [
                    {
                        "job_id": "browser-1",
                        "title": "Browser Engineer",
                        "job_detail_url": "https://company.example/jobs/browser-1",
                        "location": "Hamburg, Germany",
                    }
                ],
                "status": "completed",
                "complete_snapshot": True,
                "credible_evidence": True,
                "transport": "browser",
                "stop_reason": "rendered_page_complete",
            }
        ),
    )

    result = collect_company(_company(), lambda _: SimpleNamespace(text="", final_url=""), CollectorLimits(max_targets=1))

    assert browser_calls == ["https://company.example/careers"]
    assert {job["source_job_id"] for job in result.jobs} == {"ats-1", "browser-1"}
    assert result.status == "partial"
    assert result.outcome == "partial"


def test_challenge_source_is_blocked_not_confirmed_zero(monkeypatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    monkeypatch.setattr(catalog, "discover_career_url", lambda **_: _discovery())
    monkeypatch.setattr(
        catalog,
        "fetch_generic_snapshot",
        lambda *_, **__: {
            "jobs": [],
            "status": "blocked",
            "complete_snapshot": False,
            "credible_evidence": False,
            "error": "cf-chl- challenge page",
            "stop_reason": "challenge_page",
        },
    )
    monkeypatch.setattr(
        catalog,
        "fetch_browser_snapshot",
        lambda *_, **__: {
            "jobs": [],
            "status": "blocked",
            "complete_snapshot": False,
            "credible_evidence": False,
            "error": "captcha",
            "stop_reason": "challenge_page",
        },
    )

    result = collect_company(_company(), lambda _: SimpleNamespace(text="", final_url=""), CollectorLimits(max_targets=1))

    assert result.status == "source_failed"
    assert result.outcome == "blocked"
    assert result.targets[0]["status"] == "blocked"


def test_duplicate_company_input_is_collected_once(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    source.write_text(
        "canonical_CompanyID,company_name,website_url\n"
        "company-1,Company One,https://company.example/\n"
        "company-1,Company One duplicate,https://company.example\n",
        encoding="utf-8",
    )

    companies, stats = load_employer_companies(source)

    assert len(companies) == 1
    assert stats["duplicate_rows"] == 1


def test_resume_rechecks_legacy_no_jobs_without_coverage_evidence(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "companies.csv"
    source.write_text(
        "canonical_CompanyID,company_name,website_url\ncompany-1,Company One,https://company.example\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    state = EmployerState(output_dir / "master_employer_jobs_state.db")
    try:
        state.save(EmployerCollectionResult(company=_company(), status="no_jobs"))
    finally:
        state.close()

    seen: list[str] = []

    def fake_collect(company, _fetcher, _limits):
        seen.append(company.canonical_company_id)
        return EmployerCollectionResult(company=company, status="no_jobs", outcome="confirmed_zero")

    monkeypatch.setattr("scripts.master_employer_jobs_catalog.requests_fetcher", lambda *_: lambda _url: None)
    monkeypatch.setattr("scripts.master_employer_jobs_catalog.collect_company", fake_collect)

    metrics = run_collection(input_csv=source, output_dir=output_dir, limit=1, resume=True)

    assert seen == ["company-1"]
    assert metrics["companies_skipped_resume"] == 0


def test_state_coverage_audit_marks_legacy_negative_rows_for_recheck(tmp_path: Path) -> None:
    state = EmployerState(tmp_path / "state.db")
    try:
        state.save(EmployerCollectionResult(company=_company(), status="no_jobs"))
        report = state.coverage_audit()
    finally:
        state.close()

    assert report["companies"] == 1
    assert report["status_counts"] == {"no_jobs": 1}
    assert report["legacy_unverified_negative_rows"] == 1
    assert report["recheck_disposition"]["recheck_required"] == 1


def test_uncertain_recheck_preserves_prior_job_observation(tmp_path: Path) -> None:
    state = EmployerState(tmp_path / "state.db")
    prior_job = {
        "canonical_company_id": "company-1",
        "source_job_id": "legacy-job",
        "first_seen_at": "2026-01-01T00:00:00Z",
        "source_raw_payload": {"fixture": "legacy"},
    }
    try:
        state.save(EmployerCollectionResult(company=_company(), jobs=[prior_job], status="completed"))
        state.save(EmployerCollectionResult(company=_company(), status="partial", outcome="partial"))
        assert state.job_count() == 1
        assert state.jobs()[0] == prior_job
    finally:
        state.close()
