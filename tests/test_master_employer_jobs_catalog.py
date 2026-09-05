from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.master_employer_jobs_catalog import (
    CollectorLimits,
    EmployerCollectionResult,
    EmployerCompany,
    EmployerState,
    classify_germany,
    collect_company,
    load_employer_companies,
    run_collection,
)
from scripts.build_master_jobs_catalog import build_master_rows, write_master_jobs_csv


def _company() -> EmployerCompany:
    return EmployerCompany(
        canonical_company_id="canonical-acme",
        company_name="Acme GmbH",
        website_url="https://acme.example",
        linkedin_company_url="https://www.linkedin.com/company/acme",
        source_row_number=2,
    )


def _discovery(*, url: str, ats_type: str = "", source: str = "homepage_link") -> SimpleNamespace:
    return SimpleNamespace(
        homepage_url="https://acme.example",
        primary_career_url=url,
        candidates=[
            SimpleNamespace(url=url, ats_type=ats_type, source=source, confidence_score=0.9, evidence=[source])
        ],
        crawl_status="found",
        validation_evidence=[source],
    )


def test_load_employer_companies_maps_cleaned_master_columns(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["canonical_CompanyID", "company_name", "website_url", "linkedin_company_url"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "canonical_CompanyID": "canonical-acme",
                "company_name": "Acme GmbH",
                "website_url": "https://acme.example/",
                "linkedin_company_url": "https://de.linkedin.com/company/acme/?trk=jobs",
            }
        )

    companies, stats = load_employer_companies(source)

    assert companies == [_company()]
    assert stats == {"rows_read": 1, "rows_accepted": 1, "rows_rejected": 0}


def test_load_employer_companies_discards_placeholder_company_ids(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    source.write_text(
        "canonical_CompanyID,company_name,website_url\n//,Acme,https://acme.example\n",
        encoding="utf-8",
    )

    companies, _ = load_employer_companies(source)

    assert companies[0].canonical_company_id == ""


def test_collect_company_records_ats_api_method(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    monkeypatch.setattr(
        catalog,
        "discover_career_url",
        lambda **_: _discovery(url="https://boards.greenhouse.io/acme", ats_type="greenhouse", source="ats_signature"),
    )
    monkeypatch.setattr(
        catalog,
        "fetch_ats_snapshot",
        lambda *_, **__: {
            "jobs": [
                {
                    "id": 42,
                    "title": "Senior Analyst",
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/42",
                    "content": "Work in Berlin, Germany.",
                    "location": {"name": "Berlin, Germany"},
                    "application_url": "https://boards.greenhouse.io/acme/jobs/42/apply",
                }
            ],
            "status": "completed",
            "complete_snapshot": True,
            "pagination_complete": True,
            "request_url": "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
            "resolved_url": "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
        },
    )

    result = collect_company(_company(), lambda _: None, CollectorLimits(max_targets=1))

    assert len(result.jobs) == 1
    row = result.jobs[0]
    assert row["source_type"] == "employer_site"
    assert row["source_provider"] == "greenhouse"
    assert row["extraction_method"] == "ats_api"
    assert row["discovery_method"] == "ats_signature"
    assert row["source_job_id"] == "42"
    assert row["germany_classification"] == "GERMANY_CONFIRMED"


def test_collect_company_records_json_ld_method(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    monkeypatch.setattr(
        catalog,
        "discover_career_url",
        lambda **_: _discovery(url="https://acme.example/careers", source="sitemap"),
    )
    monkeypatch.setattr(
        catalog,
        "fetch_generic_snapshot",
        lambda *_, **__: {
            "jobs": [
                {
                    "job_id": "json-7",
                    "title": "Data Engineer",
                    "job_detail_url": "https://acme.example/careers/data-engineer",
                    "description": "Build data products.",
                    "location": "München, Deutschland",
                    "source_raw_payload": {"format": "json-ld"},
                }
            ],
            "status": "completed",
            "request_url": "https://acme.example/careers",
            "resolved_url": "https://acme.example/careers",
        },
    )

    result = collect_company(_company(), lambda _: None, CollectorLimits(max_targets=1))

    assert result.jobs[0]["source_provider"] == "generic_employer_site"
    assert result.jobs[0]["extraction_method"] == "json_ld"
    assert result.jobs[0]["discovery_method"] == "sitemap"
    assert result.jobs[0]["germany_classification"] == "GERMANY_CONFIRMED"


def test_collect_company_records_static_html_method(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    monkeypatch.setattr(
        catalog,
        "discover_career_url",
        lambda **_: _discovery(url="https://acme.example/jobs", source="common_path"),
    )
    monkeypatch.setattr(
        catalog,
        "fetch_generic_snapshot",
        lambda *_, **__: {
            "jobs": [
                {
                    "job_id": "html-9",
                    "title": "Office Manager",
                    "job_detail_url": "https://acme.example/jobs/office-manager",
                    "description": "Join our team.",
                    "location": "Hamburg, Germany",
                    "source_raw_payload": {"format": "html"},
                }
            ],
            "status": "completed",
            "request_url": "https://acme.example/jobs",
            "resolved_url": "https://acme.example/jobs",
        },
    )

    result = collect_company(_company(), lambda _: None, CollectorLimits(max_targets=1))

    assert result.jobs[0]["extraction_method"] == "static_html"
    assert result.jobs[0]["germany_classification"] == "GERMANY_CONFIRMED"


def test_collect_company_ignores_career_information_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    monkeypatch.setattr(
        catalog,
        "discover_career_url",
        lambda **_: _discovery(url="https://acme.example/careers", source="common_path"),
    )
    monkeypatch.setattr(
        catalog,
        "fetch_generic_snapshot",
        lambda *_, **__: {
            "jobs": [
                {
                    "job_id": "info-page",
                    "title": "Career Development",
                    "job_detail_url": "https://acme.example/career-development",
                    "description": "Learn about our people programs.",
                    "location": "",
                    "source_raw_payload": {"format": "html"},
                },
                {
                    "job_id": "terms-pdf",
                    "title": "",
                    "job_detail_url": "https://acme.example/terms-and-conditions.pdf",
                    "description": "",
                    "location": "",
                    "source_raw_payload": {"format": "html"},
                },
            ],
            "status": "completed",
            "request_url": "https://acme.example/careers",
            "resolved_url": "https://acme.example/careers",
        },
    )

    result = collect_company(_company(), lambda _: None, CollectorLimits(max_targets=1))

    assert result.jobs == []


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("Remote Germany", "GERMANY_REMOTE_ELIGIBLE"),
        ("Berlin, Germany; Remote Europe", "MULTI_LOCATION_INCLUDES_GERMANY"),
        ("Remote EU", "LOCATION_AMBIGUOUS"),
        ("London, United Kingdom", "NOT_GERMANY"),
        ("", "LOCATION_AMBIGUOUS"),
    ],
)
def test_classify_germany_preserves_location_evidence(location: str, expected: str) -> None:
    classification, evidence = classify_germany(location)

    assert classification == expected
    assert evidence


def test_master_projection_keeps_matching_linkedin_and_employer_rows(tmp_path: Path) -> None:
    linkedin_row = {
        "source_type": "linkedin",
        "source_provider": "linkedin",
        "source_job_id": "42",
        "source_job_url": "https://jobs.example/42",
        "job_title": "Senior Analyst",
    }
    employer_row = {
        "source_type": "employer_site",
        "source_provider": "greenhouse",
        "source_job_id": "42",
        "source_job_url": "https://jobs.example/42",
        "job_title": "Senior Analyst",
    }

    rows = build_master_rows([linkedin_row], [employer_row])
    output = tmp_path / "master_jobs.csv"
    write_master_jobs_csv(rows, output)

    assert len(rows) == 2
    assert [row["source_type"] for row in rows] == ["linkedin", "employer_site"]
    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        written = list(csv.DictReader(handle))
    assert len(written) == 2
    assert {row["source_provider"] for row in written} == {"linkedin", "greenhouse"}


def test_dry_run_validates_selection_without_fetching(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "companies.csv"
    source.write_text(
        "canonical_CompanyID,company_name,website_url\ncanonical-acme,Acme,https://acme.example\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "scripts.master_employer_jobs_catalog.requests_fetcher", lambda *_: pytest.fail("fetcher must not be created")
    )

    metrics = run_collection(input_csv=source, output_dir=tmp_path / "out", limit=1, dry_run=True)

    assert metrics["selected_companies"] == 1
    assert metrics["requests"] == 0
    assert metrics["dry_run"] is True


def test_collection_writes_actual_employer_rows_and_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "companies.csv"
    source.write_text(
        "canonical_CompanyID,company_name,website_url\ncanonical-acme,Acme,https://acme.example\n",
        encoding="utf-8",
    )
    expected = {
        "canonical_company_id": "canonical-acme",
        "source_company_name": "Acme",
        "source_company_url": "https://acme.example",
        "source_type": "employer_site",
        "source_provider": "greenhouse",
        "career_target_url": "https://boards.greenhouse.io/acme",
        "source_site_url": "https://boards.greenhouse.io/acme",
        "source_job_id": "42",
        "source_job_url": "https://boards.greenhouse.io/acme/jobs/42",
        "job_title": "Senior Analyst",
        "title_raw": "Senior Analyst",
        "description_html": "Work in Berlin, Germany.",
        "description": "Work in Berlin, Germany.",
        "description_text": "Work in Berlin, Germany.",
        "location": "Berlin, Germany",
        "location_raw": "Berlin, Germany",
        "germany_classification": "GERMANY_CONFIRMED",
        "germany_evidence": "explicit_country_city_or_postcode_signal",
        "discovery_method": "ats_signature",
        "extraction_method": "ats_api",
        "extraction_endpoint": "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
        "ats_tenant": "acme",
        "transport": "direct",
        "collection_status": "accepted",
    }
    collection = EmployerCollectionResult(company=_company(), jobs=[expected], status="completed")
    monkeypatch.setattr("scripts.master_employer_jobs_catalog.requests_fetcher", lambda *_: lambda _url: None)
    monkeypatch.setattr("scripts.master_employer_jobs_catalog.collect_company", lambda *_, **__: collection)

    metrics = run_collection(input_csv=source, output_dir=tmp_path / "out", limit=1, resume=False)

    output = tmp_path / "out" / "master_employer_jobs.csv"
    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["source_type"] == "employer_site"
    assert rows[0]["source_provider"] == "greenhouse"
    assert rows[0]["extraction_method"] == "ats_api"
    assert metrics["jobs_written"] == 1


def test_metrics_redact_proxy_configuration_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "companies.csv"
    source.write_text(
        "canonical_CompanyID,company_name,website_url\ncanonical-acme,Acme,https://acme.example\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("WEBSHARE_PROXY_URL", "https://user:secret@example.test:1234")
    monkeypatch.setenv("WEBSHARE_PROXY_USERNAME", "secret-user")
    monkeypatch.setenv("WEBSHARE_PROXY_PASSWORD", "secret-password")

    metrics = run_collection(input_csv=source, output_dir=tmp_path / "out", limit=1, dry_run=True)
    rendered = str(metrics)

    assert metrics["config"] == {
        "webshare_configured": "yes",
        "transport": "direct_then_webshare_fallback",
    }
    assert "secret" not in rendered
    assert "example.test" not in rendered


def test_master_projection_script_runs_directly_from_repository_root(tmp_path: Path) -> None:
    linkedin = tmp_path / "linkedin.csv"
    linkedin.write_text("linkedin_job_id,job_title\n42,Senior Analyst\n", encoding="utf-8")
    output = tmp_path / "master_jobs.csv"
    script = Path(__file__).resolve().parents[1] / "scripts" / "build_master_jobs_catalog.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--linkedin-csv",
            str(linkedin),
            "--employer-csv",
            str(tmp_path / "missing.csv"),
            "--output",
            str(output),
        ],
        cwd=script.parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert output.exists()


def test_collection_passes_explicit_page_bound_to_employer_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "companies.csv"
    source.write_text(
        "canonical_CompanyID,company_name,website_url\ncanonical-acme,Acme,https://acme.example\n",
        encoding="utf-8",
    )
    seen: dict[str, int] = {}
    collection = EmployerCollectionResult(company=_company(), jobs=[], status="no_jobs")

    def fake_collect(_company: EmployerCompany, _fetcher, limits: CollectorLimits) -> EmployerCollectionResult:
        seen["max_pages"] = limits.max_pages
        return collection

    monkeypatch.setattr("scripts.master_employer_jobs_catalog.requests_fetcher", lambda *_: lambda _url: None)
    monkeypatch.setattr("scripts.master_employer_jobs_catalog.collect_company", fake_collect)

    run_collection(input_csv=source, output_dir=tmp_path / "out", limit=1, resume=False, max_pages=2)

    assert seen["max_pages"] == 2


def test_master_projection_reads_large_employer_description_fields(tmp_path: Path) -> None:
    employer = tmp_path / "employer.csv"
    large_description = "<p>Requirement</p>" + (" useful detail " * 12_000)
    with employer.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_type", "description_html"])
        writer.writeheader()
        writer.writerow({"source_type": "employer_site", "description_html": large_description})

    from scripts.build_master_jobs_catalog import read_csv_rows

    rows = read_csv_rows(employer)

    assert rows[0]["description_html"] == large_description


def test_employer_state_can_start_a_clean_source_run(tmp_path: Path) -> None:
    state = EmployerState(tmp_path / "state.db")
    try:
        state.save(EmployerCollectionResult(company=_company(), jobs=[{"source_provider": "old"}], status="completed"))
        state.clear()
        assert state.jobs() == []
        assert state.company_status(_company()) == ""
    finally:
        state.close()


def test_expansion_ats_connector_is_enabled_and_records_ats_api(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    calls: dict[str, object] = {}
    monkeypatch.setattr(
        catalog,
        "discover_career_url",
        lambda **_: _discovery(
            url="https://company.myworkdayjobs.com/en-US/acme", ats_type="workday", source="ats_signature"
        ),
    )

    def fake_ats_snapshot(*args: object, **kwargs: object) -> dict[str, object]:
        calls.update(kwargs)
        return {
            "jobs": [
                {
                    "job_id": "workday-1",
                    "title": "Platform Engineer",
                    "job_detail_url": "https://company.myworkdayjobs.com/en-US/acme/job/workday-1",
                    "description": "Build platforms.",
                    "location": "Berlin, Germany",
                }
            ],
            "status": "completed",
            "request_url": "https://company.myworkdayjobs.com/wday/cxs/acme/en-US/acme/jobs",
            "resolved_url": "https://company.myworkdayjobs.com/en-US/acme",
        }

    monkeypatch.setattr(catalog, "fetch_ats_snapshot", fake_ats_snapshot)

    result = collect_company(_company(), lambda _: None, CollectorLimits(max_targets=1))

    assert calls["enabled"] is True
    assert result.jobs[0]["source_provider"] == "workday"
    assert result.jobs[0]["extraction_method"] == "ats_api"


def test_unsupported_ats_falls_through_to_generic_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    monkeypatch.setattr(
        catalog,
        "discover_career_url",
        lambda **_: _discovery(url="https://jobs.ashbyhq.com/acme", ats_type="ashby", source="ats_signature"),
    )
    monkeypatch.setattr(
        catalog,
        "fetch_ats_snapshot",
        lambda *_, **__: {"jobs": [], "status": "unsupported", "request_url": "https://jobs.ashbyhq.com/acme"},
    )
    monkeypatch.setattr(
        catalog,
        "fetch_generic_snapshot",
        lambda *_, **__: {
            "jobs": [
                {
                    "job_id": "ashby-1",
                    "title": "Product Engineer",
                    "job_detail_url": "https://jobs.ashbyhq.com/acme/ashby-1",
                    "description": "Build products.",
                    "location": "Berlin, Germany",
                    "source_raw_payload": {"format": "json-ld"},
                }
            ],
            "status": "completed",
            "request_url": "https://jobs.ashbyhq.com/acme",
            "resolved_url": "https://jobs.ashbyhq.com/acme",
        },
    )

    result = collect_company(_company(), lambda _: None, CollectorLimits(max_targets=1))

    assert len(result.jobs) == 1
    assert result.jobs[0]["source_provider"] == "ashby"
    assert result.jobs[0]["extraction_method"] == "json_ld"


def test_collect_company_uses_embedded_json_before_generic_html(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    monkeypatch.setattr(
        catalog,
        "discover_career_url",
        lambda **_: _discovery(url="https://acme.example/careers", source="homepage_link"),
    )
    html = """
    <script type="application/json" id="__INITIAL_STATE__">
      {"jobs":[{"id":"embedded-1","title":"Security Engineer","url":"/jobs/embedded-1","location":"Berlin, Germany"}]}
    </script>
    """
    fetch_result = SimpleNamespace(
        requested_url="https://acme.example/careers",
        final_url="https://acme.example/careers",
        text=html,
    )
    monkeypatch.setattr(
        catalog,
        "fetch_generic_snapshot",
        lambda *_args, **_kwargs: {
            "jobs": [
                {
                    "job_id": "generic-1",
                    "title": "Security Engineer",
                    "job_detail_url": "https://acme.example/jobs/embedded-1",
                    "location": "Berlin, Germany",
                    "source_raw_payload": {"format": "json-ld"},
                }
            ],
            "status": "completed",
            "request_url": "https://acme.example/careers",
            "resolved_url": "https://acme.example/careers",
        },
    )

    result = collect_company(_company(), lambda _: fetch_result, CollectorLimits(max_targets=1))

    assert len(result.jobs) == 1
    assert result.jobs[0]["extraction_method"] == "embedded_json"
    assert result.jobs[0]["source_job_id"] == "embedded-1"


def test_collect_company_uses_browser_xhr_after_direct_methods_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    monkeypatch.setattr(
        catalog,
        "discover_career_url",
        lambda **_: _discovery(url="https://acme.example/careers", source="common_path"),
    )
    direct_result = SimpleNamespace(
        requested_url="https://acme.example/careers",
        final_url="https://acme.example/careers",
        text="<html><body><div id='app'></div></body></html>",
    )
    monkeypatch.setattr(
        catalog,
        "fetch_generic_snapshot",
        lambda *_args, **_kwargs: {
            "jobs": [],
            "status": "completed",
            "request_url": "https://acme.example/careers",
            "resolved_url": "https://acme.example/careers",
        },
    )
    monkeypatch.setattr(
        catalog,
        "fetch_browser_snapshot",
        lambda *_args, **_kwargs: {
            "jobs": [
                {
                    "job_id": "xhr-1",
                    "title": "Frontend Engineer",
                    "job_detail_url": "https://acme.example/jobs/xhr-1",
                    "location": "Hamburg, Germany",
                    "source_endpoint": "https://acme.example/api/jobs",
                    "source_raw_payload": {"format": "xhr"},
                }
            ],
            "status": "completed",
            "request_url": "https://acme.example/careers",
            "resolved_url": "https://acme.example/careers",
            "transport": "browser",
        },
    )

    result = collect_company(_company(), lambda _: direct_result, CollectorLimits(max_targets=1))

    assert result.jobs[0]["extraction_method"] == "xhr"
    assert result.jobs[0]["transport"] == "browser"
    assert result.jobs[0]["extraction_endpoint"] == "https://acme.example/api/jobs"


def test_collect_company_merges_browser_jobs_with_direct_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    monkeypatch.setattr(
        catalog,
        "discover_career_url",
        lambda **_: _discovery(url="https://acme.example/careers", source="homepage_link"),
    )
    direct_result = SimpleNamespace(
        requested_url="https://acme.example/careers",
        final_url="https://acme.example/careers",
        text="<html><body>direct</body></html>",
    )
    monkeypatch.setattr(
        catalog,
        "fetch_generic_snapshot",
        lambda *_args, **_kwargs: {
            "jobs": [
                {
                    "job_id": "direct-1",
                    "title": "Direct Engineer",
                    "job_detail_url": "https://acme.example/jobs/direct-1",
                    "location": "Berlin, Germany",
                    "source_raw_payload": {"format": "json-ld"},
                }
            ],
            "status": "completed",
            "request_url": "https://acme.example/careers",
            "resolved_url": "https://acme.example/careers",
        },
    )
    browser_calls: list[str] = []

    def fake_browser(url: str, **_kwargs: object) -> dict[str, object]:
        browser_calls.append(url)
        return {
            "jobs": [
                {
                    "job_id": "browser-1",
                    "title": "Browser Engineer",
                    "job_detail_url": "https://acme.example/jobs/browser-1",
                    "location": "Hamburg, Germany",
                    "source_raw_payload": {"format": "browser-rendered"},
                }
            ],
            "status": "completed",
            "request_url": url,
            "resolved_url": url,
            "transport": "browser",
        }

    monkeypatch.setattr(catalog, "fetch_browser_snapshot", fake_browser)

    result = collect_company(_company(), lambda _: direct_result, CollectorLimits(max_targets=1))

    assert browser_calls == ["https://acme.example/careers"]
    assert {row["source_job_id"] for row in result.jobs} == {"direct-1", "browser-1"}


def test_collect_company_recovers_career_target_from_rendered_homepage(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    monkeypatch.setattr(
        catalog,
        "discover_career_url",
        lambda **_: SimpleNamespace(
            primary_career_url="",
            candidates=[],
            crawl_status="not_found",
        ),
    )
    homepage_snapshot = {
        "jobs": [],
        "status": "completed",
        "request_url": "https://acme.example",
        "resolved_url": "https://acme.example",
        "rendered_html": '<a href="/careers">Careers</a>',
        "transport": "browser",
    }
    career_snapshot = {
        "jobs": [
            {
                "job_id": "rendered-1",
                "title": "Operations Analyst",
                "job_detail_url": "https://acme.example/jobs/rendered-1",
                "location": "Berlin, Germany",
                "source_raw_payload": {"format": "browser-rendered"},
            }
        ],
        "status": "completed",
        "request_url": "https://acme.example/careers",
        "resolved_url": "https://acme.example/careers",
        "transport": "browser",
    }
    browser_calls: list[str] = []

    def fake_browser(url: str, **_kwargs: object) -> dict[str, object]:
        browser_calls.append(url)
        return homepage_snapshot if url == "https://acme.example" else career_snapshot

    monkeypatch.setattr(catalog, "fetch_browser_snapshot", fake_browser)

    result = collect_company(_company(), lambda _: None, CollectorLimits(max_targets=1))

    assert browser_calls == ["https://acme.example", "https://acme.example/careers"]
    assert result.jobs[0]["source_job_id"] == "rendered-1"
    assert result.jobs[0]["discovery_method"] == "browser_rendered_discovery"


def test_run_collection_flushes_master_projection_after_each_company(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "companies.csv"
    source.write_text(
        "canonical_CompanyID,company_name,website_url\n"
        "canonical-one,One,https://one.example\n"
        "canonical-two,Two,https://two.example\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    first_flush_seen: list[int] = []

    def fake_collect(company: EmployerCompany, _fetcher, _limits: CollectorLimits) -> EmployerCollectionResult:
        master_path = output_dir / "master_jobs.csv"
        if company.canonical_company_id == "canonical-two":
            with master_path.open("r", encoding="utf-8-sig", newline="") as handle:
                first_flush_seen.append(sum(1 for _ in csv.DictReader(handle)))
        return EmployerCollectionResult(
            company=company,
            jobs=[
                {
                    "canonical_company_id": company.canonical_company_id,
                    "source_type": "employer_site",
                    "source_provider": "generic_employer_site",
                    "source_job_id": company.canonical_company_id,
                    "source_job_url": f"{company.website_url}/jobs/1",
                    "job_title": "Analyst",
                    "extraction_method": "json_ld",
                }
            ],
            status="completed",
        )

    monkeypatch.setattr("scripts.master_employer_jobs_catalog.requests_fetcher", lambda *_: lambda _url: None)
    monkeypatch.setattr("scripts.master_employer_jobs_catalog.collect_company", fake_collect)

    run_collection(input_csv=source, output_dir=output_dir, limit=2, resume=False)

    assert first_flush_seen == [1]
    with (output_dir / "master_jobs.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        assert sum(1 for _ in csv.DictReader(handle)) == 2
