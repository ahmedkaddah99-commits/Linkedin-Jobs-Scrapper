from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from backend.acquisition.producer_adapters import (
    OBSERVATION_SCHEMA_VERSION,
    IdempotentMemoryTransport,
    adapt_employer_job,
    adapt_linkedin_job,
    deliver_observation_batches,
    iter_employer_observations,
    iter_linkedin_observations,
    iter_observation_batches,
)
from scripts.master_employer_jobs_catalog import (
    CollectorLimits,
    EmployerCollectionResult,
    EmployerCompany,
    EmployerState,
    collect_company,
)
from scripts.master_linkedin_jobs_catalog import CATALOG_FIELDS, StateStore, parse_job_detail, parse_search_page


class _FixtureResponse:
    status_code = 200
    url = "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def json(self) -> dict[str, object]:
        return self.payload

    def raise_for_status(self) -> None:
        return None


class _FixtureFetcher:
    def __init__(self, requester) -> None:
        self.requester = requester

    def __call__(self, _url: str) -> object:
        raise AssertionError("the ATS fixture should satisfy collection without a second network path")


def test_employer_producer_fixture_reaches_contract_without_csv(tmp_path) -> None:
    company = EmployerCompany(
        canonical_company_id="company-acme",
        company_name="Acme GmbH",
        website_url="https://acme.example",
    )
    discovery = SimpleNamespace(
        candidates=[SimpleNamespace(url="https://boards.greenhouse.io/acme", ats_type="greenhouse", source="homepage")],
        primary_career_url="https://boards.greenhouse.io/acme",
        crawl_status="found",
    )
    payload = {
        "jobs": [
            {
                "id": 101,
                "title": "Backend Engineer",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/101",
                "application_url": "https://boards.greenhouse.io/acme/jobs/101/apply",
                "location": {"name": "Berlin, Germany"},
                "departments": [{"name": "Engineering"}],
                "content": "Build reliable systems.",
            }
        ],
        "meta": {"total": 1},
    }

    def requester(_url: str, **_kwargs: object) -> _FixtureResponse:
        return _FixtureResponse(payload)

    fetcher = _FixtureFetcher(requester)
    with patch("scripts.master_employer_jobs_catalog.discover_career_url", return_value=discovery):
        result = collect_company(
            company,
            fetcher,
            CollectorLimits(
                timeout_seconds=5,
                max_targets=1,
                max_pages=1,
                max_job_links=1,
                max_browser_requests=1,
            ),
        )

    assert result.status == "completed"
    assert result.jobs[0]["source_provider"] == "greenhouse"
    state = EmployerState(tmp_path / "employer.db")
    try:
        state.save(EmployerCollectionResult(company=company, jobs=result.jobs, status=result.status))
        observations = list(iter_employer_observations(state, cycle_id="cycle-employer", scan_id="scan-employer"))
    finally:
        state.close()

    observation = observations[0]
    assert observation.source == "employer_site"
    assert observation.canonical_company_id == "company-acme"
    assert observation.source_job_id == "101"
    assert observation.apply_type == "employer_ats"
    assert observation.source_metadata["employer_source"]["source_provider"] == "greenhouse"
    assert observation.source_metadata["employer_source"]["extraction_method"] == "ats_api"
    assert observation.source_record["source_job_url"] == "https://boards.greenhouse.io/acme/jobs/101"
    assert observation.normalized_mapping["source_observation_id"] == observation.observation_id


def test_linkedin_parser_and_durable_state_reach_contract_with_field_preservation(tmp_path) -> None:
    search = parse_search_page(
        """
        <ul><li class="base-card" data-entity-urn="urn:li:jobPosting:42">
          <a href="https://www.linkedin.com/company/acme">Acme</a>
          <a href="https://www.linkedin.com/jobs/view/42">Backend Engineer</a>
          <span class="base-search-card__title">Backend Engineer</span>
          <span class="job-search-card__location">Berlin, Germany</span>
          <time datetime="2026-09-01T10:00:00Z">1 day ago</time>
        </li></ul>
        """
    )
    detail = parse_job_detail(
        "42",
        """
        <div class="top-card-layout__second-subline"><a href="https://www.linkedin.com/company/acme">Acme</a></div>
        <h1 class="top-card-layout__title">Backend Engineer</h1>
        <div class="top-card-layout__first-subline"><span>Berlin, Germany</span></div>
        <div class="top-card-layout__entity-info"><span>42 applicants</span></div>
        <div class="description__text">Build reliable systems.</div>
        <a href="https://jobs.acme.example/42/apply" data-tracking-control-name="offsite-apply">Apply</a>
        <p>Easy Apply</p>
        """,
    )
    assert search.cards[0].linkedin_job_id == "42"
    assert detail.applicant_count == "42"
    assert detail.easy_apply_status == "true"

    row = {field: "" for field in CATALOG_FIELDS}
    row.update(
        {
            "canonical_company_id": "company-acme",
            "linkedin_company_id": "linkedin-acme",
            "source_company_name": "Acme",
            "source_company_url": "https://www.linkedin.com/company/acme",
            "source_company_ids": "linkedin-acme",
            "source_company_names": "Acme",
            "source_company_urls": "https://www.linkedin.com/company/acme",
            "observed_company_name": detail.company_name,
            "observed_company_url": detail.company_url,
            "linkedin_job_id": detail.linkedin_job_id,
            "job_title": detail.title or search.cards[0].title,
            "linkedin_job_url": search.cards[0].linkedin_job_url,
            "apply_url_raw": detail.apply_url_raw,
            "apply_url_canonical": detail.apply_url_canonical,
            "apply_url_source": detail.apply_url_source,
            "description": detail.description,
            "location": detail.location,
            "posted_at_estimated": search.cards[0].posted_at_estimated,
            "easy_apply_status": detail.easy_apply_status,
            "applicant_count": detail.applicant_count,
            "employment_type": "Full-time",
            "workplace_type": "Hybrid",
            "last_seen_at": "2026-09-06T10:00:00Z",
            "content_hash": "linkedin-content-hash",
            "company_match_status": "EXACT_PRIMARY_MATCH",
            "ownership_status": "EXACT_PRIMARY_MATCH",
            "location_classification": "GERMANY_CONFIRMED",
            "run_id": "run-linkedin",
            "company_scan_id": "scan-linkedin",
        }
    )
    state = StateStore(tmp_path / "linkedin.db")
    try:
        state.upsert_catalog_row(row)
        observations = list(
            iter_linkedin_observations(state, cycle_id="cycle-linkedin", run_id="run-linkedin")
        )
    finally:
        state.close()

    observation = observations[0]
    assert observation.source == "linkedin"
    assert observation.scan_id == "scan-linkedin"
    assert observation.apply_type == "linkedin_easy_apply"
    assert observation.source_metadata["application"] == {
        "easy_apply_status": "true",
        "applicant_count": "42",
    }
    assert observation.source_metadata["ownership"]["company_match_status"] == "EXACT_PRIMARY_MATCH"
    assert observation.canonical_employer["source_company_ids"] == ["linkedin-acme"]
    assert observation.source_record["linkedin_job_id"] == "42"


def test_missing_fields_are_unknown_and_zero_job_state_is_empty(tmp_path) -> None:
    missing = adapt_linkedin_job({"canonical_company_id": "company-acme", "linkedin_job_id": "42"}, cycle_id="cycle")
    assert missing.source_url == "unknown"
    assert missing.apply_url == "unknown"
    assert missing.apply_type == "unknown"
    assert missing.source_metadata["application"]["easy_apply_status"] == "unknown"

    state = EmployerState(tmp_path / "empty-employer.db")
    try:
        assert list(iter_employer_observations(state, cycle_id="cycle-empty")) == []
    finally:
        state.close()


def test_batches_are_bounded_and_replay_is_idempotent() -> None:
    first = adapt_linkedin_job(
        {
            "canonical_company_id": "company-acme",
            "linkedin_job_id": "42",
            "linkedin_job_url": "https://www.linkedin.com/jobs/view/42",
            "content_hash": "hash-42",
            "last_seen_at": "2026-09-06T10:00:00Z",
        },
        cycle_id="cycle",
        scan_id="scan",
    )
    second = adapt_linkedin_job(
        {
            "canonical_company_id": "company-acme",
            "linkedin_job_id": "43",
            "linkedin_job_url": "https://www.linkedin.com/jobs/view/43",
            "content_hash": "hash-43",
            "last_seen_at": "2026-09-06T10:00:00Z",
        },
        cycle_id="cycle",
        scan_id="scan",
    )
    batches = tuple(iter_observation_batches((first, second), max_batch_size=1))
    assert [len(batch.observations) for batch in batches] == [1, 1]
    assert all(batch.schema_version == OBSERVATION_SCHEMA_VERSION for batch in batches)

    transport = IdempotentMemoryTransport()
    first_receipt = deliver_observation_batches((batches[0],), transport)[0]
    replay_receipt = deliver_observation_batches((batches[0],), transport)[0]
    assert first_receipt.receipt_id == replay_receipt.receipt_id
    assert replay_receipt.duplicate_count == 1
    assert len(transport.observations) == 1

    employer = adapt_employer_job(
        {
            "canonical_company_id": "company-acme",
            "linkedin_job_id": "42",
            "linkedin_job_url": "https://www.linkedin.com/jobs/view/42",
            "content_hash": "hash-42",
            "last_seen_at": "2026-09-06T10:00:00Z",
        },
        cycle_id="cycle",
        scan_id="scan",
    )
    assert employer.idempotency_key != first.idempotency_key

    source_transport = IdempotentMemoryTransport()
    source_batch = tuple(iter_observation_batches((first, employer), max_batch_size=10))
    source_receipt = deliver_observation_batches(source_batch, source_transport)[0]
    assert source_receipt.accepted_count == 2
    assert len(source_transport.observations) == 2
