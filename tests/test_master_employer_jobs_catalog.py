from __future__ import annotations

import csv
import json
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
    main as employer_main,
    run_collection,
)
from scripts.build_master_jobs_catalog import build_master_rows, main as combined_main, write_master_jobs_csv


def _company() -> EmployerCompany:
    return EmployerCompany(
        canonical_company_id="canonical-acme",
        company_name="Acme GmbH",
        website_url="https://acme.example",
        linkedin_company_url="https://www.linkedin.com/company/acme",
        source_row_number=2,
    )


def _company_with_id(company_id: str, name: str) -> EmployerCompany:
    return EmployerCompany(
        canonical_company_id=company_id,
        company_name=name,
        website_url=f"https://{company_id}.example",
        linkedin_company_url=f"https://www.linkedin.com/company/{company_id}",
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
    employer = tmp_path / "employer.csv"
    employer.write_text("source_job_id,job_title\nemployer-1,Employer\n", encoding="utf-8")
    output = tmp_path / "master_jobs.csv"
    script = Path(__file__).resolve().parents[1] / "scripts" / "build_master_jobs_catalog.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--linkedin-csv",
            str(linkedin),
            "--employer-csv",
            str(employer),
            "--output",
            str(output),
            "--linkedin-generation-id",
            "linkedin-generation-1",
            "--employer-generation-id",
            "employer-generation-1",
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


def test_run_collection_saves_two_company_checkpoints_and_exports_once_after_collection(
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
    events: list[tuple[str, str]] = []

    def fake_collect(company: EmployerCompany, _fetcher, _limits: CollectorLimits) -> EmployerCollectionResult:
        events.append(("collect", company.canonical_company_id))
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
    import scripts.master_employer_jobs_catalog as catalog

    real_export = catalog.export_catalogs_from_state

    def tracked_export(*args: object, **kwargs: object) -> dict[str, object]:
        events.append(("export", "final"))
        return real_export(*args, **kwargs)

    monkeypatch.setattr(catalog, "export_catalogs_from_state", tracked_export)
    monkeypatch.setattr(catalog, "_flush_master_projection", lambda *_: pytest.fail("legacy flush must not run"))

    metrics = run_collection(input_csv=source, output_dir=output_dir, limit=2, resume=False)

    assert events == [("collect", "canonical-one"), ("collect", "canonical-two"), ("export", "final")]
    assert metrics["companies_processed"] == 2
    assert metrics["companies_skipped_resume"] == 0
    assert metrics["persisted_jobs"] == 2
    assert metrics["exported_jobs"] == 2
    assert metrics["final_export_completed"] is True
    state = EmployerState(output_dir / "master_employer_jobs_state.db")
    try:
        assert state.job_count() == 2
        assert [row["canonical_company_id"] for row in state.jobs()] == ["canonical-one", "canonical-two"]
    finally:
        state.close()
    with (output_dir / "master_employer_jobs.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        assert sum(1 for _ in csv.DictReader(handle)) == 2
    assert not (output_dir / "master_jobs.csv").exists()


def test_progress_job_counts_do_not_load_all_state_jobs_after_each_company(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "companies.csv"
    source.write_text(
        "canonical_CompanyID,company_name,website_url\n"
        "canonical-one,One,https://one.example\n"
        "canonical-two,Two,https://two.example\n",
        encoding="utf-8",
    )
    def fake_collect(company: EmployerCompany, _fetcher, _limits: CollectorLimits) -> EmployerCollectionResult:
        return EmployerCollectionResult(
            company=company,
            jobs=[
                {
                    "canonical_company_id": company.canonical_company_id,
                    "source_job_id": company.canonical_company_id,
                    "extraction_method": "json_ld",
                    "source_provider": "generic_employer_site",
                }
            ],
            status="completed",
        )

    monkeypatch.setattr("scripts.master_employer_jobs_catalog.requests_fetcher", lambda *_: lambda _url: None)
    monkeypatch.setattr("scripts.master_employer_jobs_catalog.collect_company", fake_collect)
    monkeypatch.setattr(EmployerState, "jobs", lambda _self: pytest.fail("jobs() must not power progress metrics"))

    metrics = run_collection(input_csv=source, output_dir=tmp_path / "out", limit=2, resume=False)

    assert metrics["persisted_jobs"] == 2


def test_resume_metrics_separate_skipped_companies_from_processed_companies(
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
    state = EmployerState(output_dir / "master_employer_jobs_state.db")
    try:
        state.save(EmployerCollectionResult(company=_company_with_id("canonical-one", "One"), status="completed"))
    finally:
        state.close()

    seen: list[str] = []

    def fake_collect(company: EmployerCompany, _fetcher, _limits: CollectorLimits) -> EmployerCollectionResult:
        seen.append(company.canonical_company_id)
        return EmployerCollectionResult(company=company, status="no_jobs")

    monkeypatch.setattr("scripts.master_employer_jobs_catalog.requests_fetcher", lambda *_: lambda _url: None)
    monkeypatch.setattr("scripts.master_employer_jobs_catalog.collect_company", fake_collect)

    metrics = run_collection(input_csv=source, output_dir=output_dir, limit=2, resume=True)

    assert seen == ["canonical-two"]
    assert metrics["companies_processed"] == 1
    assert metrics["companies_skipped_resume"] == 1


def test_interrupted_collection_keeps_checkpoints_and_existing_snapshots(
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
    output_dir.mkdir()
    snapshots = {
        "master_employer_jobs.csv": "old employer snapshot\n",
        "master_employer_jobs.jsonl": "old employer jsonl\n",
        "master_employer_jobs_metrics.json": "{\"old\": true}\n",
        "master_jobs.csv": "old combined snapshot\n",
    }
    for name, content in snapshots.items():
        (output_dir / name).write_text(content, encoding="utf-8")

    calls = 0

    def interrupted_collect(company: EmployerCompany, _fetcher, _limits: CollectorLimits) -> EmployerCollectionResult:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt()
        return EmployerCollectionResult(
            company=company,
            jobs=[
                {
                    "canonical_company_id": company.canonical_company_id,
                    "source_job_id": "one",
                    "extraction_method": "json_ld",
                    "source_provider": "generic_employer_site",
                }
            ],
            status="completed",
        )

    monkeypatch.setattr("scripts.master_employer_jobs_catalog.requests_fetcher", lambda *_: lambda _url: None)
    monkeypatch.setattr("scripts.master_employer_jobs_catalog.collect_company", interrupted_collect)

    with pytest.raises(KeyboardInterrupt):
        run_collection(input_csv=source, output_dir=output_dir, limit=2, resume=False)

    state = EmployerState(output_dir / "master_employer_jobs_state.db")
    try:
        assert state.company_status(_company_with_id("canonical-one", "One")) == "completed"
    finally:
        state.close()
    assert {name: (output_dir / name).read_text(encoding="utf-8") for name in snapshots} == snapshots
    assert not list(output_dir.glob(".*.tmp"))


def test_export_only_uses_authoritative_state_without_network_or_legacy_employer_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "out"
    state = EmployerState(output_dir / "master_employer_jobs_state.db")
    state_job = {"canonical_company_id": "state-company", "source_type": "employer_site", "source_job_id": "state-job"}
    try:
        state.save(EmployerCollectionResult(company=_company_with_id("state-company", "State"), jobs=[state_job], status="completed"))
    finally:
        state.close()
    (output_dir / "master_employer_jobs.csv").write_text(
        "canonical_company_id,source_job_id\nlegacy-company,legacy-job\n", encoding="utf-8"
    )
    (output_dir / "master_jobs.csv").write_text("old combined\n", encoding="utf-8")
    import scripts.master_employer_jobs_catalog as catalog

    for name in ("_build_network_clients", "load_project_dotenv", "collect_company"):
        monkeypatch.setattr(catalog, name, lambda *args, _name=name, **kwargs: pytest.fail(f"{_name} must not run"))

    metrics = employer_main(["--export-only", "--output-dir", str(output_dir)])

    assert metrics == 0
    with (output_dir / "master_employer_jobs.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["source_job_id"] for row in rows] == ["state-job"]
    assert (output_dir / "master_jobs.csv").read_text(encoding="utf-8") == "old combined\n"


def test_export_only_returns_clear_error_for_missing_or_invalid_state(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    assert employer_main(["--export-only", "--output-dir", str(output_dir)]) == 2
    assert "state database not found" in capsys.readouterr().err

    (output_dir / "master_employer_jobs_state.db").write_text("not sqlite", encoding="utf-8")
    assert employer_main(["--export-only", "--output-dir", str(output_dir)]) == 2
    assert "export-only failed" in capsys.readouterr().err


def test_export_only_succeeds_with_zero_job_state_and_missing_linkedin_source(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    state = EmployerState(output_dir / "master_employer_jobs_state.db")
    state.close()

    assert employer_main(["--export-only", "--output-dir", str(output_dir)]) == 0
    with (output_dir / "master_employer_jobs.csv").open(encoding="utf-8-sig", newline="") as handle:
        assert list(csv.DictReader(handle)) == []
    metrics = json.loads((output_dir / "master_employer_jobs_metrics.json").read_text(encoding="utf-8"))
    assert metrics["generation_id"].startswith("employer-")
    assert metrics["exported_jobs"] == 0
    assert not (output_dir / "master_jobs.csv").exists()


def test_export_only_keeps_all_snapshots_when_temporary_validation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "out"
    state = EmployerState(output_dir / "master_employer_jobs_state.db")
    try:
        state.save(
            EmployerCollectionResult(
                company=_company(),
                jobs=[
                    {
                        "canonical_company_id": "canonical-acme",
                        "source_type": "employer_site",
                        "source_job_id": "state-job",
                        "extraction_method": "json_ld",
                        "source_provider": "generic_employer_site",
                    }
                ],
                status="completed",
            )
        )
    finally:
        state.close()
    (output_dir / "master_linkedin_jobs.csv").write_text(
        "linkedin_job_id,job_title,source_type\nlinkedin-job,LinkedIn Job,linkedin\n", encoding="utf-8"
    )
    snapshots = {
        "master_employer_jobs.csv": "old employer\n",
        "master_employer_jobs.jsonl": "old jsonl\n",
        "master_employer_jobs_metrics.json": "{\"old\": true}\n",
        "master_jobs.csv": "old combined\n",
    }
    for name, content in snapshots.items():
        (output_dir / name).write_text(content, encoding="utf-8")
    import scripts.master_employer_jobs_catalog as catalog

    def reject_validation(*_args: object, **_kwargs: object) -> None:
        raise ValueError("synthetic validation failure")

    monkeypatch.setattr(catalog, "_validate_employer_temps", reject_validation)

    assert employer_main(["--export-only", "--output-dir", str(output_dir)]) == 2
    assert {name: (output_dir / name).read_text(encoding="utf-8") for name in snapshots} == snapshots
    assert not list(output_dir.glob(".*.tmp"))


def test_employer_export_rolls_back_when_promotion_is_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "out"
    state = EmployerState(output_dir / "master_employer_jobs_state.db")
    try:
        state.save(EmployerCollectionResult(company=_company(), jobs=[{"source_job_id": "job-1"}], status="completed"))
    finally:
        state.close()
    snapshots = {
        "master_employer_jobs.csv": "old employer\n",
        "master_employer_jobs.jsonl": "old jsonl\n",
        "master_employer_jobs_metrics.json": '{"old": true}\n',
    }
    for name, content in snapshots.items():
        (output_dir / name).write_text(content, encoding="utf-8")

    import scripts.master_employer_jobs_catalog as catalog

    calls = 0
    real_replace = catalog.os.replace

    def interrupt_on_second_replace(source: object, target: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise KeyboardInterrupt()
        real_replace(source, target)

    monkeypatch.setattr(catalog.os, "replace", interrupt_on_second_replace)
    state = EmployerState.open_existing(output_dir / "master_employer_jobs_state.db")
    try:
        with pytest.raises(KeyboardInterrupt):
            catalog.export_catalogs_from_state(state, output_dir, metrics={"persisted_jobs": 1})
    finally:
        state.close()

    assert {name: (output_dir / name).read_text(encoding="utf-8") for name in snapshots} == snapshots
    assert not list(output_dir.glob(".*.tmp"))


def test_combined_export_requires_linkedin_input_and_preserves_employer_artifacts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    employer = output_dir / "master_employer_jobs.csv"
    employer.write_text("source_job_id,job_title,source_type\nemployer-1,Employer,employer_site\n", encoding="utf-8")
    employer_metrics = output_dir / "master_employer_jobs_metrics.json"
    employer_metrics.write_text('{"generation_id":"employer-generation-1"}\n', encoding="utf-8")

    assert combined_main(
        [
            "--linkedin-csv",
            str(output_dir / "master_linkedin_jobs.csv"),
            "--employer-csv",
            str(employer),
            "--linkedin-generation-id",
            "linkedin-generation-1",
            "--employer-generation-id",
            "employer-generation-1",
            "--output",
            str(output_dir / "master_jobs.csv"),
        ]
    ) == 2
    assert "LinkedIn source CSV not found" in capsys.readouterr().err
    assert employer.read_text(encoding="utf-8") == "source_job_id,job_title,source_type\nemployer-1,Employer,employer_site\n"
    assert not (output_dir / "master_jobs.csv").exists()


def test_combined_export_rejects_corrupt_linkedin_input_and_missing_generation_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    linkedin = output_dir / "master_linkedin_jobs.csv"
    linkedin.write_text("not,a,valid,source\n", encoding="utf-8")
    employer = output_dir / "master_employer_jobs.csv"
    employer.write_text("source_job_id,job_title,source_type\nemployer-1,Employer,employer_site\n", encoding="utf-8")

    assert combined_main(
        ["--linkedin-csv", str(linkedin), "--employer-csv", str(employer), "--linkedin-generation-id", "li-1", "--output", str(output_dir / "master_jobs.csv")]
    ) == 2
    assert "employer generation ID is required" in capsys.readouterr().err

    assert combined_main(
        [
            "--linkedin-csv",
            str(linkedin),
            "--employer-csv",
            str(employer),
            "--linkedin-generation-id",
            "li-1",
            "--employer-generation-id",
            "emp-1",
            "--output",
            str(output_dir / "master_jobs.csv"),
        ]
    ) == 2
    assert "missing an identity field" in capsys.readouterr().err


def test_combined_export_streams_sources_and_records_generation_ids(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    linkedin = output_dir / "master_linkedin_jobs.csv"
    linkedin.parent.mkdir()
    linkedin.write_text("linkedin_job_id,job_title,source_type\nli-1,LinkedIn,linkedin\n", encoding="utf-8")
    employer = output_dir / "master_employer_jobs.csv"
    employer.write_text("source_job_id,job_title,source_type\nemployer-1,Employer,employer_site\n", encoding="utf-8")

    assert combined_main(
        [
            "--linkedin-csv",
            str(linkedin),
            "--employer-csv",
            str(employer),
            "--linkedin-generation-id",
            "li-generation-1",
            "--employer-generation-id",
            "employer-generation-1",
            "--output",
            str(output_dir / "master_jobs.csv"),
        ]
    ) == 0
    with (output_dir / "master_jobs.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["source_job_id"] for row in rows] == ["li-1", "employer-1"]
    manifest = json.loads((output_dir / "master_jobs_manifest.json").read_text(encoding="utf-8"))
    assert manifest["inputs"]["linkedin"]["generation_id"] == "li-generation-1"
    assert manifest["inputs"]["employer"]["generation_id"] == "employer-generation-1"


REAL_LINKEDIN_PRODUCER_FIELDS = (
    "company_scan_status",
    "detail_last_refreshed_at",
    "inactive_confirmed_at",
    "inactive_reason",
    "location_classification",
    "location_classification_reason",
    "ownership_alias_status",
    "ownership_status",
    "query_partition_type",
    "query_partition_value",
)


def test_master_projection_preserves_all_real_linkedin_producer_fields() -> None:
    from scripts import build_master_jobs_catalog as projection

    source_row = {
        "source_type": "linkedin",
        "linkedin_job_id": "linkedin-42",
        **{field: f"producer-{field}" for field in REAL_LINKEDIN_PRODUCER_FIELDS},
    }

    rows = projection.build_master_rows([source_row], [])

    assert set(REAL_LINKEDIN_PRODUCER_FIELDS).issubset(projection.MASTER_FIELDS)
    assert {field: rows[0][field] for field in REAL_LINKEDIN_PRODUCER_FIELDS} == {
        field: f"producer-{field}" for field in REAL_LINKEDIN_PRODUCER_FIELDS
    }


def test_master_projection_maps_legacy_linkedin_fields_without_losing_source_identity() -> None:
    from scripts import build_master_jobs_catalog as projection

    rows = projection.build_master_rows(
        [
            {
                "source_type": "linkedin",
                "linkedin_job_id": "legacy-42",
                "linkedin_job_url": "https://www.linkedin.com/jobs/view/legacy-42",
                "apply_url": "https://jobs.example/apply/legacy-42",
                "description": "Legacy description",
            }
        ],
        [],
    )

    assert rows[0]["source_job_id"] == "legacy-42"
    assert rows[0]["apply_url_raw"] == "https://jobs.example/apply/legacy-42"
    assert rows[0]["apply_url_canonical"] == "https://jobs.example/apply/legacy-42"
    assert rows[0]["description_text"] == "Legacy description"


def test_production_projection_main_uses_incremental_csv_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import inspect
    from scripts import build_master_jobs_catalog as projection

    linkedin = tmp_path / "linkedin.csv"
    linkedin.write_text(
        "linkedin_job_id,job_title,source_type\n"
        + "\n".join(f"linkedin-{index},Job {index},linkedin" for index in range(5000))
        + "\n",
        encoding="utf-8",
    )
    employer = tmp_path / "employer.csv"
    employer.write_text("source_job_id,job_title,source_type\nemployer-1,Employer,employer_site\n", encoding="utf-8")
    output = tmp_path / "master_jobs.csv"

    assert inspect.isgeneratorfunction(projection.iter_csv_rows)
    monkeypatch.setattr(projection, "build_master_rows", lambda *_: pytest.fail("large path must not materialize rows"))

    assert (
        projection.main(
            [
                "--linkedin-csv",
                str(linkedin),
                "--employer-csv",
                str(employer),
                "--output",
                str(output),
                "--linkedin-generation-id",
                "linkedin-generation-1",
                "--employer-generation-id",
                "employer-generation-1",
            ]
        )
        == 0
    )
    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 5001
    assert rows[0]["source_job_id"] == "linkedin-0"
    assert rows[-1]["source_job_id"] == "employer-1"
