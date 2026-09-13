"""Tests that execute the real connector traversal paths.

These are not hand-built receipt dictionaries: they call ``fetch_ats_snapshot``
and ``collect_company`` with a fake transport that returns representative
multi-page source responses, and assert on pagination exhaustion, source-count
reconciliation, result caps, browser fallback, and complementary-partition
detection.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.connectors.ats_router import fetch_ats_snapshot
from scripts.master_employer_jobs_catalog import CollectorLimits, collect_company


class FakeResponse:
    def __init__(self, payload, url="", status_code=200):
        self._payload = payload
        self.url = url
        self.status_code = status_code
        self.headers = {"content-type": "application/json"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._payload


def _greenhouse_pages(total: int, page_size: int = 100):
    """Return a fake requester serving a Greenhouse board with ``total`` jobs."""

    def requester(url, **_kwargs):
        page = 1
        if "&page=" in url:
            page = int(url.rsplit("&page=", 1)[1])
        start = (page - 1) * page_size
        remaining = max(0, total - start)
        count = min(page_size, remaining)
        jobs = [
            {"id": start + i, "title": f"Job {start + i}", "absolute_url": f"https://boards.greenhouse.io/acme/jobs/{start + i}"}
            for i in range(count)
        ]
        return FakeResponse({"jobs": jobs, "meta": {"total": total}}, url=url)

    return requester


def test_greenhouse_pagination_exhaustion_and_source_count_reconciliation() -> None:
    snapshot = fetch_ats_snapshot(
        "https://boards.greenhouse.io/acme",
        "greenhouse",
        requester=_greenhouse_pages(total=250),
        max_pages=20,
    )

    assert len(snapshot["jobs"]) == 250
    assert snapshot["pagination_complete"] is True
    assert snapshot["complete_snapshot"] is True
    assert snapshot["pages_fetched"] == 3
    assert snapshot["source_reported_total"] == 250
    assert snapshot["stop_reason"] == "pagination_complete"


def test_greenhouse_result_cap_is_not_pagination_complete() -> None:
    snapshot = fetch_ats_snapshot(
        "https://boards.greenhouse.io/acme",
        "greenhouse",
        requester=_greenhouse_pages(total=250),
        max_pages=1,
    )

    assert len(snapshot["jobs"]) == 100
    assert snapshot["pagination_complete"] is False
    assert snapshot["complete_snapshot"] is False
    assert snapshot["stop_reason"] == "max_pages"


def test_greenhouse_empty_source_has_independent_zero_total() -> None:
    snapshot = fetch_ats_snapshot(
        "https://boards.greenhouse.io/acme",
        "greenhouse",
        requester=_greenhouse_pages(total=0),
        max_pages=20,
    )

    assert snapshot["jobs"] == []
    assert snapshot["pagination_complete"] is True
    assert snapshot["source_reported_total"] == 0


def test_lever_skip_pagination_exhausts_and_reconciles() -> None:
    postings = [{"id": f"p{i}", "text": f"Role {i}", "hostedUrl": f"https://jobs.lever.co/acme/p{i}"} for i in range(230)]

    def requester(url, **_kwargs):
        skip = 0
        if "&skip=" in url:
            skip = int(url.rsplit("&skip=", 1)[1])
        window = postings[skip : skip + 100]
        return FakeResponse(window, url=url)

    snapshot = fetch_ats_snapshot("https://jobs.lever.co/acme", "lever", requester=requester, max_pages=20)

    assert len(snapshot["jobs"]) == 230
    assert snapshot["pagination_complete"] is True
    assert snapshot["pages_fetched"] == 3


def test_collect_company_browser_fallback_merges_jobs(monkeypatch):
    import scripts.master_employer_jobs_catalog as catalog

    monkeypatch.setattr(
        catalog,
        "discover_career_url",
        lambda **_: SimpleNamespace(
            primary_career_url="https://co.example/careers",
            candidates=[SimpleNamespace(url="https://co.example/careers", source="homepage_link", ats_type="")],
            crawl_status="found",
        ),
    )
    monkeypatch.setattr(
        catalog,
        "fetch_generic_snapshot",
        lambda *_a, **_k: {"jobs": [], "status": "completed", "complete_snapshot": False, "credible_evidence": False},
    )
    monkeypatch.setattr(
        catalog,
        "fetch_browser_snapshot",
        lambda *_a, **_k: {
            "jobs": [
                {
                    "job_id": "xhr-1",
                    "title": "Frontend Engineer",
                    "job_detail_url": "https://co.example/jobs/xhr-1",
                    "location": "Hamburg, Germany",
                    "source_raw_payload": {"format": "xhr"},
                }
            ],
            "status": "completed",
            "complete_snapshot": False,
            "credible_evidence": True,
            "transport": "browser",
            "stop_reason": "pagination_unverified",
        },
    )

    from scripts.master_employer_jobs_catalog import EmployerCompany

    company = EmployerCompany(
        canonical_company_id="co-1", company_name="Co", website_url="https://co.example"
    )
    result = collect_company(company, lambda _: SimpleNamespace(text="<html></html>", final_url="https://co.example/careers"), CollectorLimits(max_targets=1))

    assert [job["source_job_id"] for job in result.jobs] == ["xhr-1"]
    assert result.jobs[0]["extraction_method"] == "xhr"
    # Browser-rendered pages do not prove pagination exhaustion.
    assert result.outcome == "partial"


def test_collect_company_records_complementary_partition_skipped(monkeypatch):
    import scripts.master_employer_jobs_catalog as catalog

    # Discovery surfaces two Greenhouse tenants; only the first is traversed and
    # completed, so the second is an unvisited complementary partition.
    monkeypatch.setattr(
        catalog,
        "discover_career_url",
        lambda **_: SimpleNamespace(
            primary_career_url="https://boards.greenhouse.io/co",
            candidates=[
                SimpleNamespace(url="https://boards.greenhouse.io/co", source="ats_signature", ats_type="greenhouse"),
                SimpleNamespace(url="https://boards.greenhouse.io/co-emea", source="ats_signature", ats_type="greenhouse"),
            ],
            crawl_status="found",
        ),
    )
    monkeypatch.setattr(
        catalog,
        "fetch_ats_snapshot",
        lambda *_a, **_k: {
            "jobs": [{"id": 1, "title": "Analyst", "absolute_url": "https://boards.greenhouse.io/co/jobs/1"}],
            "status": "completed",
            "complete_snapshot": True,
            "pagination_complete": True,
            "credible_evidence": True,
            "request_url": "https://boards-api.greenhouse.io/v1/boards/co/jobs?content=true",
            "pages_fetched": 1,
            "requests_made": 1,
            "source_reported_total": 1,
            "stop_reason": "pagination_complete",
        },
    )

    from scripts.master_employer_jobs_catalog import EmployerCompany

    company = EmployerCompany(
        canonical_company_id="co-1", company_name="Co", website_url="https://co.example"
    )
    result = collect_company(company, lambda _: None, CollectorLimits(max_targets=5))

    assert result.outcome == "complete_with_jobs"
    skipped = result.coverage["discovery"]["complementary_partitions_skipped"]
    assert [item["ats_type"] for item in skipped] == ["greenhouse"]
    assert "co-emea" in skipped[0]["url"]
