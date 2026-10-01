from __future__ import annotations

import json
from types import SimpleNamespace

from backend.acquisition.job_page_evidence import generic_employer_non_job_reason
from backend.connectors.employer_site_fallbacks import extract_embedded_jobs
from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore
from scripts.master_employer_jobs_catalog import _is_accepted_job_page


def test_embedded_navigation_objects_are_not_jobs() -> None:
    html = '<script type="application/json" id="__NEXT_DATA__">' + json.dumps({
        "props": {"pageProps": {
            "menu": [{"id": "menu-item-156", "title": "Contact Us", "url": "/contact"}],
            "jobs": [{"id": "42", "title": "Data Engineer", "url": "/jobs/42",
                      "description": "Build and maintain data platforms for our engineering team. " * 2,
                      "applyUrl": "/jobs/42/apply"}],
        }}
    }) + "</script>"

    jobs = extract_embedded_jobs(html, "https://example.com/careers")

    assert [job["title"] for job in jobs] == ["Data Engineer"]


def test_json_ld_only_accepts_jobposting_type() -> None:
    html = '<script type="application/ld+json">' + json.dumps([
        {"@type": "WebPage", "title": "Company Service", "url": "https://example.com/jobs/service",
         "description": "Learn about all of the services we provide to our customers across the country. " * 2,
         "applicationUrl": "https://example.com/jobs/service/apply"},
        {"@type": "JobPosting", "title": "Data Engineer", "url": "https://example.com/jobs/42",
         "description": "Build and maintain our data systems for the engineering organization. " * 2,
         "applicationUrl": "https://example.com/jobs/42/apply"},
    ]) + "</script>"
    assert [job["title"] for job in extract_embedded_jobs(html, "https://example.com/careers")] == ["Data Engineer"]


def test_generic_collector_rejects_navigation_but_retains_job_detail() -> None:
    assert not _is_accepted_job_page({"title": "About Us", "job_detail_url": "https://example.com/about"}, "generic_employer_site")
    assert _is_accepted_job_page({"title": "Data Engineer", "job_detail_url": "https://example.com/jobs/42"}, "generic_employer_site")
    assert not generic_employer_non_job_reason({"title": "Data Engineer", "job_detail_url": "https://example.com/jobs/42"})
    assert not generic_employer_non_job_reason({"title": "Mechanic", "job_detail_url": "https://example.com/careers/2448/offer/mechanic"})
    assert not generic_employer_non_job_reason({"title": "Junior Electric Propulsion Engineer", "job_detail_url": "https://example.com/careers/junior-electric-propulsion-engineer"})
    assert generic_employer_non_job_reason({"title": "Students", "job_detail_url": "https://example.com/careers/students"})
    assert generic_employer_non_job_reason({"title": "Service", "job_detail_url": "https://bonava.de/service", "extraction_method": "embedded_json"})
    assert generic_employer_non_job_reason({"title": "New Homes", "job_detail_url": "https://bonava.de/jobs/new-homes", "extraction_method": "embedded_json"})
    assert not generic_employer_non_job_reason({"title": "Data Engineer", "job_detail_url": "https://example.com/jobs/42",
        "description": "Build and maintain data platforms for our engineering team. " * 2,
        "application_url": "https://example.com/jobs/42/apply", "extraction_method": "embedded_json"})


def test_publication_excludes_old_generic_navigation_rows_even_with_advisory_completeness() -> None:
    rows = [{
        "canonical_job_id": "job-navigation",
        "company_id": "company-1",
        "title": "Contact Us",
        "canonical_url": "https://example.com/contact",
        "source_ats": "generic_employer_site",
        "source_job_id": "menu-item-156",
            "version_payload_json": json.dumps({"extraction_method": "embedded_json", "source_provider": "generic_employer_site"}),
    }, {
        "canonical_job_id": "job-real",
        "company_id": "company-1",
        "title": "Data Engineer",
        "canonical_url": "https://example.com/jobs/42",
        "source_ats": "generic_employer_site",
        "source_job_id": "42",
        "apply_url": "https://example.com/jobs/42/apply",
        "version_description": "Build and maintain data platforms for our engineering team. " * 2,
        "version_payload_json": json.dumps({"extraction_method": "embedded_json", "source_provider": "generic_employer_site"}),
    }]
    policy = SimpleNamespace(missing_apply_is_blocker=False, completeness_mode="advisory")

    snapshot, rejected = SqliteAcquisitionStore._publication_rows_with_completeness(rows, policy=policy)

    assert [item["canonical_job_id"] for item in snapshot] == ["job-real"]
    assert [item["canonical_job_id"] for item in rejected] == ["job-navigation", "job-real"]
    assert rejected[0]["reasons"][0]["code"] == "generic_navigation_title"


def test_publication_excludes_obvious_navigation_title_without_employer_provenance() -> None:
    rows = [{
        "canonical_job_id": "old-page", "company_id": "company-1", "title": "About Us",
        "canonical_url": "https://example.com/about", "source_ats": "unknown",
        "version_payload_json": "{}",
    }]
    policy = SimpleNamespace(missing_apply_is_blocker=False, completeness_mode="advisory")
    snapshot, rejected = SqliteAcquisitionStore._publication_rows_with_completeness(rows, policy=policy)
    assert snapshot == []
    assert rejected[0]["reasons"][0]["code"] == "generic_navigation_title"


def test_publication_rejects_bonava_navigation_with_normalized_url() -> None:
    rows = [{
        "canonical_job_id": "bonava-service", "company_id": "bonava", "title": "Service",
        "canonical_url": "https://bonava.de/service", "source_ats": "generic_employer_site",
        "version_payload_json": json.dumps({
            "source_provider": "generic_employer_site", "extraction_method": "embedded_json",
            "source_job_url": "https://www.bonava.de/service", "description_text": "",
            "location_raw": "", "apply_url_canonical": "",
        }),
    }]
    policy = SimpleNamespace(missing_apply_is_blocker=False, completeness_mode="advisory")
    snapshot, rejected = SqliteAcquisitionStore._publication_rows_with_completeness(rows, policy=policy)
    assert snapshot == []
    assert rejected[0]["reasons"][0]["code"] == "unverified_generic_page"


def test_ats_named_employer_with_embedded_marketing_page_is_rejected() -> None:
    page = {"title": "A modern ATS that helps you manage your unique requirements at scale",
            "job_detail_url": "https://ashbyhq.com/enterprise",
            "source_raw_payload": {"format": "embedded-json"}}
    assert not _is_accepted_job_page(page, "ashby")
    rows = [{"canonical_job_id": "ashby-marketing", "company_id": "ashby", "title": page["title"],
             "canonical_url": page["job_detail_url"], "source_ats": "ashby",
             "version_payload_json": json.dumps({"source_provider": "ashby", "extraction_method": "embedded_json"})}]
    policy = SimpleNamespace(missing_apply_is_blocker=False, completeness_mode="advisory")
    snapshot, rejected = SqliteAcquisitionStore._publication_rows_with_completeness(rows, policy=policy)
    assert snapshot == []
    assert rejected[0]["reasons"][0]["code"] == "unverified_generic_page"
