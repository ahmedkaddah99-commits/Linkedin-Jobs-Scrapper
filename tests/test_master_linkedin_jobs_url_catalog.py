from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.master_linkedin_jobs_url_catalog import (
    CSV_FIELDS,
    CatalogState,
    CompanyGroup,
    build_search_url,
    canonical_company_url,
    content_hash_for_job,
    load_company_groups,
    load_pagination_evidence,
    normalize_company_id,
    parse_detail_page,
    parse_search_page,
    reconcile_output_records,
    should_reuse_successful_work,
    validate_card_and_detail_ownership,
    validate_company_ownership,
    write_catalog_outputs,
)


REQUIRED_CSV_FIELDS = [
    "canonical_company_id",
    "linkedin_company_id",
    "source_company_name",
    "source_company_url",
    "source_company_ids",
    "source_company_names",
    "source_company_urls",
    "observed_company_name",
    "observed_company_url",
    "linkedin_job_id",
    "job_title",
    "linkedin_job_url",
    "apply_url",
    "apply_url_source",
    "description",
    "location",
    "posted_text",
    "posted_at_estimated",
    "easy_apply_status",
    "applicant_count",
    "employment_type",
    "workplace_type",
    "first_seen_at",
    "last_seen_at",
    "last_successful_company_scan_at",
    "lifecycle_status",
    "absence_count",
    "content_hash",
    "source_endpoint",
    "transport",
    "search_pagination_start",
    "search_status_code",
    "detail_status_code",
    "company_match_status",
    "company_match_reason",
    "run_id",
    "source_type",
    "source_provider",
    "career_target_url",
    "source_site_url",
    "source_job_id",
    "source_job_url",
    "discovery_method",
    "extraction_method",
    "extraction_endpoint",
    "ats_tenant",
]


DETAIL_HTML = """
<html><body>
  <h2 class="top-card-layout__title">Senior Analyst</h2>
  <a class="topcard__org-name-link" href="https://de.linkedin.com/company/acme/?trk=jobs">Acme GmbH</a>
  <span class="topcard__flavor--bullet">Berlin, Germany</span>
  <div class="show-more-less-html__markup">Analyze markets\nBuild reports</div>
  <a class="top-card-layout__cta--primary" href="https://jobs.acme.example/apply/42"
     data-tracking-control-name="public_jobs_apply-link-offsite">Apply</a>
  <span class="posted-time-ago__text">2 days ago</span>
  <ul class="description__job-criteria-list">
    <li><h3>Employment type</h3><span>Full-time</span></li>
    <li><h3>Workplace type</h3><span>Hybrid</span></li>
  </ul>
  <span class="num-applicants__caption">42 applicants</span>
</body></html>
"""


def _search_html(*, company_url: str = "https://www.linkedin.com/company/acme/", job_id: str = "1234567") -> str:
    return f"""
    <ul class="jobs-search__results-list">
      <li>
        <div class="base-search-card" data-entity-urn="urn:li:jobPosting:{job_id}">
          <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/{job_id}">Job</a>
          <h3 class="base-search-card__title">Senior Analyst</h3>
          <h4 class="base-search-card__subtitle"><a href="{company_url}">Acme GmbH</a></h4>
          <span class="job-search-card__location">Berlin, Germany</span>
          <time class="job-search-card__listdate">2 days ago</time>
        </div>
      </li>
    </ul>
    """


def _group() -> CompanyGroup:
    return CompanyGroup(
        linkedin_company_id="1043",
        source_company_ids=("canonical-1",),
        source_company_names=("Acme GmbH",),
        source_company_urls=("https://www.linkedin.com/company/acme",),
        allowed_company_urls=frozenset({"https://www.linkedin.com/company/acme"}),
        canonical_company_id="canonical-1",
        source_company_name="Acme GmbH",
        source_company_url="https://www.linkedin.com/company/acme",
    )


def test_canonical_company_url_keeps_only_company_identity_path() -> None:
    assert (
        canonical_company_url("https://de.linkedin.com/company/Acme/?trk=abc#jobs")
        == "https://www.linkedin.com/company/acme"
    )
    assert canonical_company_url("https://www.linkedin.com/in/person/") == ""


def test_load_company_groups_preserves_duplicate_source_mappings(tmp_path: Path) -> None:
    path = tmp_path / "companies.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["canonical_CompanyID", "company_name", "linkedin_company_url", "linkedin_company_id"],
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "canonical_CompanyID": "z",
                    "company_name": "Zed",
                    "linkedin_company_url": "https://www.linkedin.com/company/acme/",
                    "linkedin_company_id": "1043",
                },
                {
                    "canonical_CompanyID": "a",
                    "company_name": "Acme",
                    "linkedin_company_url": "https://de.linkedin.com/company/acme?trk=x",
                    "linkedin_company_id": "1043",
                },
                {
                    "canonical_CompanyID": "bad",
                    "company_name": "No ID",
                    "linkedin_company_url": "https://www.linkedin.com/company/no-id",
                    "linkedin_company_id": "",
                },
                {
                    "canonical_CompanyID": "bad-url",
                    "company_name": "Person",
                    "linkedin_company_url": "https://www.linkedin.com/in/person",
                    "linkedin_company_id": "999",
                },
            ]
        )

    groups, stats = load_company_groups(path)

    assert list(groups) == ["1043"]
    group = groups["1043"]
    assert group.source_company_ids == ("a", "z")
    assert group.source_company_names == ("Acme", "Zed")
    assert group.source_company_urls == ("https://www.linkedin.com/company/acme",)
    assert group.canonical_company_id == "a"
    assert stats["input_rows"] == 4
    assert stats["accepted_rows"] == 2
    assert stats["excluded_rows"] == 2


def test_build_search_url_always_has_germany_scope_and_company_filter() -> None:
    url = build_search_url("1043", 20)
    assert "location=Germany" in url
    assert "geoId=101282230" in url
    assert "f_C=1043" in url
    assert "start=20" in url


def test_parse_search_page_accepts_explicit_empty_result() -> None:
    result = parse_search_page(
        '<div class="jobs-search-no-results"><h1>No jobs found</h1></div>',
        company_id="1043",
        start=0,
    )
    assert result.classification == "legitimate_empty_result"
    assert result.cards == []
    assert result.usable is True


def test_parse_search_page_rejects_nonempty_page_with_missing_company_url() -> None:
    html = _search_html(company_url="")
    result = parse_search_page(html, company_id="1043", start=0)
    assert result.usable is False
    assert result.classification == "malformed_card"
    assert result.cards == []


def test_parse_detail_page_extracts_required_enrichment_fields() -> None:
    detail = parse_detail_page("1234567", DETAIL_HTML)
    assert detail["company_url"] == "https://www.linkedin.com/company/acme"
    assert detail["title"] == "Senior Analyst"
    assert detail["company_name"] == "Acme GmbH"
    assert detail["location"] == "Berlin, Germany"
    assert detail["apply_url"] == "https://jobs.acme.example/apply/42"
    assert detail["apply_url_source"] == "external"
    assert detail["applicant_count"] == 42
    assert detail["employment_type"] == "Full-time"
    assert detail["workplace_type"] == "Hybrid"


def test_company_ownership_rejects_card_or_detail_url_mismatch() -> None:
    allowed = {"https://www.linkedin.com/company/acme"}
    assert validate_company_ownership("https://de.linkedin.com/company/acme/?trk=jobs", allowed) == (
        True,
        "company_url_exact_match",
    )
    assert validate_company_ownership("https://www.linkedin.com/company/other", allowed) == (
        False,
        "company_url_mismatch",
    )
    assert validate_company_ownership("", allowed) == (False, "missing_company_url")


def test_card_and_detail_must_match_same_allowed_company_url() -> None:
    allowed = {
        "https://www.linkedin.com/company/acme",
        "https://www.linkedin.com/company/acme-holdings",
    }
    assert validate_card_and_detail_ownership(
        "https://www.linkedin.com/company/acme",
        "https://www.linkedin.com/company/acme-holdings",
        allowed,
    ) == (False, "card_detail_company_url_mismatch")


def test_successful_cached_work_is_reused_only_within_same_run() -> None:
    assert should_reuse_successful_work("run-1", "run-1", "complete") is True
    assert should_reuse_successful_work("run-1", "run-2", "complete") is False
    assert should_reuse_successful_work("run-1", "run-1", "failed") is False


def test_company_id_normalization_groups_zero_padded_ascii_ids_only() -> None:
    assert normalize_company_id("001043") == "1043"
    assert normalize_company_id("١٠٤٣") == ""
    assert normalize_company_id("0") == ""


def test_pagination_evidence_requires_expected_endpoint_and_terminal_boundary(tmp_path: Path) -> None:
    valid = {
        "endpoint": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
        "provider": {"name": "Webshare", "scrapeops_requests": 0},
        "calibration": {"Germany": {"observed_page_step_candidate": 10, "observed_full_card_count": 10}},
        "ceiling_scan": {
            "terminal_http_400_start": 1000,
            "max_confirmed_full_start": 990,
            "responses": [{"start": 990, "status_code": 200}, {"start": 1000, "status_code": 400}],
        },
    }
    path = tmp_path / "pagination.json"
    path.write_text(json.dumps(valid), encoding="utf-8")
    assert load_pagination_evidence(path) == (10, 1000)
    valid["endpoint"] = "https://example.test/search"
    path.write_text(json.dumps(valid), encoding="utf-8")
    with pytest.raises(RuntimeError, match="endpoint"):
        load_pagination_evidence(path)


def test_state_deduplicates_and_preserves_first_seen_while_hashing_changes(tmp_path: Path) -> None:
    state = CatalogState(tmp_path / "state.db")
    try:
        card = parse_search_page(_search_html(), company_id="1043", start=0).cards[0]
        detail = parse_detail_page("1234567", DETAIL_HTML)
        first = state.upsert_accepted_job(
            _group(),
            card,
            detail,
            observed_at="2026-08-31T10:00:00Z",
            run_id="run-1",
            search_start=0,
        )
        second_detail = {**detail, "description": "Changed description"}
        second = state.upsert_accepted_job(
            _group(),
            card,
            second_detail,
            observed_at="2026-08-31T11:00:00Z",
            run_id="run-2",
            search_start=0,
        )
        row = state.get_job("1043", "1234567")
    finally:
        state.close()

    assert first == "inserted"
    assert second == "updated"
    assert row["first_seen_at"] == "2026-08-31T10:00:00Z"
    assert row["last_seen_at"] == "2026-08-31T11:00:00Z"
    assert row["content_hash"] == content_hash_for_job(second_detail, card)


def test_accept_job_observation_commits_detail_job_and_observation_together(tmp_path: Path) -> None:
    state = CatalogState(tmp_path / "state.db")
    try:
        card = parse_search_page(_search_html(), company_id="1043", start=0).cards[0]
        detail = parse_detail_page("1234567", DETAIL_HTML)
        outcome = state.accept_job_observation(
            _group(),
            card,
            detail,
            observed_at="2026-08-31T10:00:00Z",
            run_id="run-1",
            search_start=0,
        )
        detail_attempts = state.connection.execute(
            "SELECT COUNT(*) FROM detail_attempts WHERE outcome='accepted'"
        ).fetchone()[0]
        observations = state.connection.execute(
            "SELECT COUNT(*) FROM job_observations WHERE observation_type='accepted'"
        ).fetchone()[0]
        job = state.get_job("1043", "1234567")
    finally:
        state.close()

    assert outcome == "inserted"
    assert detail_attempts == 1
    assert observations == 1
    assert job["linkedin_job_id"] == "1234567"


def test_content_hash_ignores_relative_posting_clock_drift() -> None:
    card = parse_search_page(_search_html(), company_id="1043", start=0).cards[0]
    detail = parse_detail_page("1234567", DETAIL_HTML)
    later_observation = {**detail, "posted_text": "3 days ago", "posted_at_estimated": "2026-08-29T10:00:00Z"}
    assert content_hash_for_job(detail, card) == content_hash_for_job(later_observation, card)


def test_inactive_marking_requires_complete_company_scan(tmp_path: Path) -> None:
    state = CatalogState(tmp_path / "state.db")
    try:
        card = parse_search_page(_search_html(), company_id="1043", start=0).cards[0]
        detail = parse_detail_page("1234567", DETAIL_HTML)
        state.upsert_accepted_job(
            _group(), card, detail, observed_at="2026-08-31T10:00:00Z", run_id="run-1", search_start=0
        )
        assert (
            state.finish_company_scan(
                "1043", complete=False, observed_job_ids=set(), scan_at="2026-08-31T11:00:00Z", run_id="run-2"
            )
            == 0
        )
        assert state.get_job("1043", "1234567")["lifecycle_status"] == "active"
        assert (
            state.finish_company_scan(
                "1043", complete=True, observed_job_ids=set(), scan_at="2026-08-31T12:00:00Z", run_id="run-3"
            )
            == 1
        )
        row = state.get_job("1043", "1234567")
    finally:
        state.close()

    assert row["lifecycle_status"] == "inactive"
    assert row["absence_count"] == 1


def test_state_persists_failed_page_and_accepted_detail_for_resume(tmp_path: Path) -> None:
    state = CatalogState(tmp_path / "state.db")
    try:
        state.record_search_page(
            "1043",
            0,
            status="failed",
            status_code=503,
            classification="http_503",
            cards=[],
            error="http_503",
            retry_at="2026-08-31T11:00:00Z",
            run_id="run-1",
        )
        failed = state.get_search_page("1043", 0)
        card = parse_search_page(_search_html(), company_id="1043", start=0).cards[0]
        detail = parse_detail_page("1234567", DETAIL_HTML)
        state.record_detail_attempt(
            "1043",
            "1234567",
            run_id="run-1",
            status_code=200,
            outcome="accepted",
            company_url=detail["company_url"],
            reason="company_url_exact_match",
            payload=detail,
            attempted_at="2026-08-31T10:00:00Z",
        )
        cached = state.successful_detail("1043", "1234567")
    finally:
        state.close()

    assert failed["status"] == "failed"
    assert failed["attempts"] == 1
    assert cached["company_url"] == "https://www.linkedin.com/company/acme"


def test_output_reconciliation_deduplicates_by_company_and_job_id(tmp_path: Path) -> None:
    csv_path = tmp_path / "catalog.csv"
    jsonl_path = tmp_path / "catalog.jsonl"
    csv_path.write_text(
        "\ufefflinkedin_company_id,linkedin_job_id,job_title\n1043,1234567,Old\n1043,1234567,Duplicate\n",
        encoding="utf-8",
    )
    jsonl_path.write_text(
        json.dumps({"linkedin_company_id": "1043", "linkedin_job_id": "1234567", "job_title": "Newest"}) + "\n",
        encoding="utf-8",
    )

    records = reconcile_output_records(csv_path, jsonl_path)

    assert records == [{"linkedin_company_id": "1043", "linkedin_job_id": "1234567", "job_title": "Newest"}]


def test_write_catalog_outputs_uses_requested_schema_and_utf8_bom(tmp_path: Path) -> None:
    assert CSV_FIELDS == REQUIRED_CSV_FIELDS
    state = CatalogState(tmp_path / "state.db")
    try:
        card = parse_search_page(_search_html(), company_id="1043", start=0).cards[0]
        detail = parse_detail_page("1234567", DETAIL_HTML)
        state.upsert_accepted_job(
            _group(), card, detail, observed_at="2026-08-31T10:00:00Z", run_id="run-1", search_start=0
        )
        csv_path = tmp_path / "nested" / "master_linkedin_jobs.csv"
        jsonl_path = tmp_path / "nested" / "master_linkedin_jobs.jsonl"
        write_catalog_outputs(state, csv_path, jsonl_path)
    finally:
        state.close()

    assert csv_path.read_bytes().startswith(b"\xef\xbb\xbf")
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == CSV_FIELDS
        row = next(reader)
    assert row["linkedin_company_id"] == "1043"
    assert row["linkedin_job_id"] == "1234567"
    assert row["transport"] == "webshare"
    assert "location=Germany" in row["source_endpoint"]
    assert "geoId=101282230" in row["source_endpoint"]
    assert "f_C=1043" in row["source_endpoint"]
    assert row["source_type"] == "linkedin"
    assert row["source_provider"] == "linkedin"
    assert row["discovery_method"] == "linkedin_guest_search"
    assert row["extraction_method"] == "linkedin_guest_search_and_detail_html"
    assert row["source_job_id"] == "1234567"
    assert row["source_job_url"] == row["linkedin_job_url"]
    assert row["extraction_endpoint"].endswith("/1234567")
