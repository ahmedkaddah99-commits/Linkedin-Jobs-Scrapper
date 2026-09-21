from __future__ import annotations

import pytest
from types import SimpleNamespace
from pathlib import Path

import backend.connectors.employer_site_fallbacks as _fallbacks
from scripts.master_employer_jobs_catalog import (
    CollectorLimits,
    EmployerCollectionResult,
    EmployerCompany,
    EmployerState,
    RequestBudgetExceeded,
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


def test_browser_tries_direct_then_proxy_with_remaining_budget(monkeypatch):
    import scripts.master_employer_jobs_catalog as catalog

    monkeypatch.setattr(catalog, "discover_career_url", lambda **_: _discovery())
    monkeypatch.setattr(catalog, "fetch_generic_snapshot", lambda *_, **__: {
        "jobs": [], "status": "completed", "complete_snapshot": False,
    })
    calls = []

    def browser(_url, **kwargs):
        calls.append((kwargs["proxy_url"], kwargs["max_requests"]))
        return {"jobs": [], "status": "browser_failed", "error": "timeout", "requests_made": 2}

    monkeypatch.setattr(catalog, "fetch_browser_snapshot", browser)
    result = collect_company(
        _company(), lambda _: SimpleNamespace(text="", final_url=""),
        CollectorLimits(max_targets=1, max_browser_requests=5, proxy_url="http://proxy.example:80"),
    )
    assert calls == [("", 5), ("http://proxy.example:80", 3)]
    assert result.outcome != "confirmed_zero"


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


def test_complete_authoritative_target_still_traverses_independent_source(monkeypatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    # T56 source-union contract: a complete authoritative ATS snapshot no longer
    # stops candidate fan-out; the independent main career site is still
    # traversed and its jobs are unioned with the ATS jobs.
    first_url = "https://boards.greenhouse.io/company"
    second_url = "https://company.example/careers"
    monkeypatch.setattr(
        catalog,
        "discover_career_url",
        lambda **_: SimpleNamespace(
            primary_career_url=first_url,
            candidates=[
                SimpleNamespace(url=first_url, source="ats_signature", ats_type="greenhouse"),
                SimpleNamespace(url=second_url, source="homepage_link", ats_type=""),
            ],
            crawl_status="found",
        ),
    )
    ats_calls: list[str] = []

    def fetch_ats(url, *_, **__):
        ats_calls.append(url)
        return {
            "jobs": [
                {
                    "id": 42,
                    "title": "Platform Engineer",
                    "absolute_url": "https://boards.greenhouse.io/company/jobs/42",
                    "content": "Work in Berlin, Germany.",
                    "location": {"name": "Berlin, Germany"},
                }
            ],
            "status": "completed",
            "complete_snapshot": True,
            "pagination_complete": True,
            "credible_evidence": True,
            "request_url": "https://boards-api.greenhouse.io/v1/boards/company/jobs?content=true",
        }

    monkeypatch.setattr(catalog, "fetch_ats_snapshot", fetch_ats)
    monkeypatch.setattr(
        catalog,
        "fetch_generic_snapshot",
        lambda url, **_: {
            "jobs": [
                {
                    "job_id": "careers-1",
                    "title": "Office Manager",
                    "job_detail_url": "https://company.example/jobs/office-manager",
                    "description": "Join our team in Hamburg, Germany.",
                    "location": "Hamburg, Germany",
                    "source_raw_payload": {"format": "html"},
                }
            ],
            "status": "completed",
            "complete_snapshot": True,
            "pagination_complete": True,
            "request_url": url,
            "resolved_url": url,
        },
    )

    result = collect_company(_company(), lambda _: None, CollectorLimits(max_targets=2))

    assert ats_calls == [first_url]
    assert {target["url"] for target in result.targets} == {first_url, second_url}
    assert result.outcome == "complete_with_jobs"
    assert len(result.jobs) == 2
    inventory = {entry["url"]: entry for entry in result.coverage["source_inventory"]}
    assert inventory[first_url]["traversal_status"] == "traversed"
    assert inventory[second_url]["traversal_status"] == "traversed"


def test_request_budget_is_a_partial_outcome_and_is_checkpointed(tmp_path: Path, monkeypatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    source = tmp_path / "companies.csv"
    source.write_text(
        "canonical_CompanyID,company_name,website_url\ncompany-1,Company One,https://company.example\n",
        encoding="utf-8",
    )

    def budgeted_collect(*_args, **_kwargs):
        raise RequestBudgetExceeded(8)

    monkeypatch.setattr(catalog, "collect_company", budgeted_collect)
    output_dir = tmp_path / "out"
    metrics = run_collection(
        input_csv=source,
        output_dir=output_dir,
        limit=1,
        resume=False,
        max_requests=8,
    )

    assert metrics["company_statuses"] == {"partial": 1}
    assert metrics["final_export_completed"] is True
    state = EmployerState(output_dir / "master_employer_jobs_state.db")
    try:
        result = state.company_payload(_company())
    finally:
        state.close()
    assert result is not None
    assert result["status"] == "partial"
    assert result["outcome"] == "partial"
    assert result["failures"] == [
        {
            "stage": "company",
            "error": "RequestBudgetExceeded",
            "reason": "request_budget_exhausted",
            "max_requests": 8,
        }
    ]
    assert result["coverage"]["stop_reason"] == "request_budget_exhausted"
    assert result["coverage"]["request_budget_exhausted"] is True


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


class _ScriptedBrowser:
    """Fake Chromium browser whose pages fail until configured failures drain.

    ``goto_failures_left`` raises a Playwright timeout before any observation
    is harvested; ``timeout_failures_left`` raises after harvesting, so tests
    can pin both the retry path (no jobs yet) and partial-failure preservation
    (jobs already observed).
    """

    def __init__(self, goto_failures: int, timeout_failures: int, launches: list[int]) -> None:
        self.goto_failures_left = goto_failures
        self.timeout_failures_left = timeout_failures
        self.launches = launches

    def new_context(self) -> "_ScriptedContext":
        return _ScriptedContext(self)

    def close(self) -> None:
        return None


class _ScriptedContext:
    def __init__(self, browser: _ScriptedBrowser) -> None:
        self._browser = browser

    def new_page(self) -> "_ScriptedPage":
        return _ScriptedPage(self._browser)

    def close(self) -> None:
        return None


class _ScriptedPage:
    def __init__(self, browser: _ScriptedBrowser) -> None:
        self._browser = browser
        self.handlers: dict[str, object] = {}

    def on(self, event: str, callback: object) -> None:
        self.handlers[event] = callback

    def route(self, _pattern: object, callback: object) -> None:
        self.route_callback = callback

    def goto(self, *_args: object, **_kwargs: object) -> None:
        if self._browser.goto_failures_left > 0:
            self._browser.goto_failures_left -= 1
            raise _fallbacks.PlaywrightTimeoutError("fixture timeout")
        self.route_callback(
            SimpleNamespace(
                request=SimpleNamespace(url="https://acme.example/careers", resource_type="document"),
                continue_=lambda: None,
                abort=lambda: None,
            )
        )
        response = SimpleNamespace(
            url="https://acme.example/api/jobs",
            headers={"content-type": "application/json"},
            request=SimpleNamespace(resource_type="xhr"),
            json=lambda: {"jobs": [{"id": "xhr-1", "title": "Backend Engineer", "url": "/jobs/xhr-1"}]},
        )
        self.handlers["response"](response)

    def wait_for_timeout(self, *_args: object) -> None:
        if self._browser.timeout_failures_left > 0:
            self._browser.timeout_failures_left -= 1
            raise _fallbacks.PlaywrightTimeoutError("fixture timeout")

    def content(self) -> str:
        return '<html><h1>Backend Engineer</h1><script type="application/json">{"jobs":[]}</script></html>'


class _ScriptedChromium:
    def __init__(self, goto_failures: int, timeout_failures: int, launches: list[int]) -> None:
        self._goto_failures = goto_failures
        self._timeout_failures = timeout_failures
        self._launches = launches

    def launch(self, **_kwargs: object) -> _ScriptedBrowser:
        self._launches.append(1)
        return _ScriptedBrowser(self._goto_failures, self._timeout_failures, self._launches)


class _ScriptedPlaywright:
    def __init__(self, goto_failures: int, timeout_failures: int, launches: list[int]) -> None:
        self.chromium = _ScriptedChromium(goto_failures, timeout_failures, launches)

    def __enter__(self) -> "_ScriptedPlaywright":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def _scripted_playwright_factory(goto_failures: int, timeout_failures: int, launches: list[int]):
    return lambda: _ScriptedPlaywright(goto_failures, timeout_failures, launches)


def test_reusable_browser_reuses_one_process_and_retries_within_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launches: list[int] = []
    monkeypatch.setattr(
        _fallbacks,
        "sync_playwright",
        _scripted_playwright_factory(goto_failures=1, timeout_failures=0, launches=launches),
    )
    session = _fallbacks.ReusableBrowser()
    try:
        first = session.fetch(
            "https://acme.example/careers",
            timeout_seconds=5,
            max_requests=5,
            retry_attempts=1,
        )
        second = session.fetch("https://acme.example/careers", timeout_seconds=5, max_requests=5)
    finally:
        launch_count = session.launch_count
        session.close()

    assert first["status"] == "completed"
    assert first["pages_fetched"] == 1
    assert second["status"] == "completed"
    assert launch_count == 1
    assert not session.is_running()


def test_reusable_browser_timeout_without_retry_reports_partial_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launches: list[int] = []
    monkeypatch.setattr(
        _fallbacks,
        "sync_playwright",
        _scripted_playwright_factory(goto_failures=0, timeout_failures=1, launches=launches),
    )
    session = _fallbacks.ReusableBrowser()
    try:
        result = session.fetch(
            "https://acme.example/careers",
            timeout_seconds=5,
            max_requests=5,
            retry_attempts=2,
        )
    finally:
        session.close()

    assert result["status"] == "partial"
    assert result["error"] == "timeout"
    assert len(result["jobs"]) == 1
    assert result["credible_evidence"] is True
    assert session.launch_count == 1


def test_dry_run_receipt_classifies_durable_jobs_without_collection(tmp_path: Path) -> None:
    from scripts.run_manifested_employer import build_dry_run_receipt

    output_dir = tmp_path / "out"
    output_dir.mkdir()
    staged = tmp_path / "staged.csv"
    staged.write_text(
        "canonical_CompanyID,company_name,website_url\n"
        "ok-co,OK Co,https://ok.example\n"
        "bad-co,Bad Co,https://bad.example\n",
        encoding="utf-8",
    )
    accepted_job = {
        "canonical_company_id": "ok-co",
        "source_provider": "generic",
        "source_job_id": "job-1",
        "source_job_url": "https://ok.example/jobs/1",
        "title": "Engineer",
        "source_raw_payload": {"format": "json-ld"},
    }
    duplicate_job = {**accepted_job, "source_provider": "ats_api", "source_job_id": "dup-ats"}
    rejected_job = {
        "canonical_company_id": "ok-co",
        "source_provider": "generic",
        "source_job_id": "no-title",
        "source_job_url": "https://ok.example/about",
        "source_raw_payload": {"format": "static"},
    }
    failed_job = {
        "canonical_company_id": "bad-co",
        "source_provider": "generic",
        "source_job_id": "bad-1",
        "source_job_url": "https://bad.example/jobs/1",
        "title": "Bad Co Engineer",
        "source_raw_payload": {"format": "json-ld"},
    }
    state = EmployerState(output_dir / "master_employer_jobs_state.db")
    try:
        state.save(
            EmployerCollectionResult(
                company=EmployerCompany(
                    canonical_company_id="ok-co",
                    company_name="OK Co",
                    website_url="https://ok.example",
                ),
                jobs=[accepted_job, duplicate_job, rejected_job],
                status="completed",
                outcome="complete_with_jobs",
            )
        )
        state.save(
            EmployerCollectionResult(
                company=EmployerCompany(
                    canonical_company_id="bad-co",
                    company_name="Bad Co",
                    website_url="https://bad.example",
                ),
                jobs=[failed_job],
                status="failed",
                outcome="source_failed",
            )
        )
    finally:
        state.close()

    receipt = build_dry_run_receipt(
        manifest={"manifest_id": "fixture-manifest", "manifest_hash": "hash"},
        staged_input=staged,
        output_dir=output_dir,
        state_dir=None,
        pilot_only=True,
        duration_budget_seconds=10,
    )

    assert receipt["job_receipt"] == {
        "discovered": 4,
        "accepted": 1,
        "rejected": 1,
        "deduplicated": 1,
        "failed": 1,
    }
    assert receipt["state_present"] is True
    assert receipt["cohort_companies"] == 2
    assert receipt["duration_budget_exhausted"] is False
    assert receipt["company_status_counts"] == {"completed": 1, "failed": 1}
    assert Path(receipt["receipt_path"]).is_file()


def test_dry_run_receipt_reports_zero_jobs_when_state_is_absent(tmp_path: Path) -> None:
    from scripts.run_manifested_employer import build_dry_run_receipt

    output_dir = tmp_path / "out"
    output_dir.mkdir()
    staged = tmp_path / "staged.csv"
    staged.write_text(
        "canonical_CompanyID,company_name,website_url\nok-co,OK Co,https://ok.example\n",
        encoding="utf-8",
    )

    receipt = build_dry_run_receipt(
        manifest={"manifest_id": "fixture-manifest", "manifest_hash": "hash"},
        staged_input=staged,
        output_dir=output_dir,
        state_dir=None,
        pilot_only=True,
        duration_budget_seconds=10,
    )

    assert receipt["state_present"] is False
    assert receipt["job_receipt"] == {
        "discovered": 0,
        "accepted": 0,
        "rejected": 0,
        "deduplicated": 0,
        "failed": 0,
    }


def test_main_dry_run_receipt_flag_produces_bounded_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.run_manifested_employer as wrapper

    manifest = {"manifest_id": "fixture-manifest", "manifest_hash": "fixture-hash"}
    output_dir = tmp_path / "exports" / "employer"
    staged = output_dir / ".manifest_inputs" / "fixture-manifest-employer.csv"

    def fake_materialize(_manifest, _source, path, **_kwargs):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "canonical_CompanyID,company_name,website_url\nok-co,OK Co,https://ok.example\n",
            encoding="utf-8",
        )
        return {"rows": 1}

    monkeypatch.setattr(
        wrapper,
        "require_eligibility_manifest",
        lambda *_args, **_kwargs: (manifest, [{"task_key": "fixture"}]),
    )
    monkeypatch.setattr(wrapper, "materialize_source_input", fake_materialize)

    exit_code = wrapper.main(
        [
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--output-dir",
            str(output_dir),
            "--dry-run",
            "--dry-run-receipt",
        ]
    )

    assert exit_code == 0
    receipt = (output_dir / "employer_dry_run_receipt.json").is_file()
    assert receipt is True
