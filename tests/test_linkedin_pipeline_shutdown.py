"""Pipeline shutdown, resume, backpressure, and budget-safety regressions.

These tests exercise the LinkedIn producer's pipelined execution under stress:
bounded-queue backpressure, consumer failure, request-budget exhaustion,
graceful interruption, durable batch flushing at shutdown, restart with
unfinished details, and the global request limiter shared across search and
detail pools.
"""

from __future__ import annotations

import csv
import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from scripts.master_linkedin_jobs_catalog import (
    AdaptiveConcurrency,
    CatalogRunner,
    ResponseEnvelope,
    RunnerConfig,
    StateStore,
    WebshareProxy,
    WebshareTransport,
)


FIXTURES = Path(__file__).parent / "fixtures"

DETAIL_ENDPOINT = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"


def write_source_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fields = [
        "canonical_CompanyID",
        "company_name",
        "linkedin_company_url",
        "linkedin_slug",
        "linkedin_company_id",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_pagination_report(path: Path, max_start: int = 10) -> None:
    path.write_text(
        json.dumps(
            {
                "endpoint": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
                "page_step": 10,
                "full_card_count": 10,
                "max_start": max_start,
            }
        ),
        encoding="utf-8",
    )


def single_company_rows() -> list[dict[str, str]]:
    return [{
        "canonical_CompanyID": "C-001",
        "company_name": "Acme",
        "linkedin_company_url": "https://www.linkedin.com/company/acme",
        "linkedin_slug": "acme",
        "linkedin_company_id": "22",
    }]


def _job_card(job_id: str) -> str:
    return (
        '<li class="job-card-container" data-entity-urn="urn:li:jobPosting:{job_id}">'
        '<a href="https://www.linkedin.com/company/acme">Acme</a>'
        '<a href="https://www.linkedin.com/jobs/view/{job_id}"></a>'
        '<h3 class="base-search-card__title">Engineer</h3>'
        '<span class="job-search-card__location">Berlin, Germany</span>'
        '<time datetime="2026-08-31">1 day ago</time>'
        "</li>"
    ).format(job_id=job_id)


def _search_page(job_ids: list[str]) -> str:
    return (
        '<html><body><ul class="jobs-search__results-list">'
        + "".join(_job_card(job_id) for job_id in job_ids)
        + "</ul></body></html>"
    )


def _detail_page() -> str:
    return (FIXTURES / "linkedin_job_detail.html").read_text(encoding="utf-8")


def _no_results_page() -> str:
    return (FIXTURES / "linkedin_job_search_no_results.html").read_text(encoding="utf-8")


class ManyJobTransport:
    """Deterministic transport that returns ``job_ids`` cards on page 0."""

    def __init__(self, job_ids: list[str], *, detail_latency: float = 0.0) -> None:
        self.job_ids = job_ids
        self.detail_latency = detail_latency
        self.urls: list[tuple[str, str]] = []
        self._lock = threading.Lock()
        self.peak_in_flight = 0
        self._in_flight = 0

    def get(self, url: str, *, kind: str) -> ResponseEnvelope:
        with self._lock:
            self._in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self._in_flight)
        try:
            self.urls.append((url, kind))
            if kind == "search":
                if "start=0" in url:
                    body = _search_page(self.job_ids)
                else:
                    body = _no_results_page()
                return ResponseEnvelope(200, body, "proxy-1", 0.01)
            if self.detail_latency:
                time.sleep(self.detail_latency)
            return ResponseEnvelope(200, _detail_page(), "proxy-1", 0.01)
        finally:
            with self._lock:
                self._in_flight -= 1


class TransientDetailFailureTransport(ManyJobTransport):
    """Raises once for a specific detail URL to simulate a consumer crash."""

    def __init__(self, job_ids: list[str], *, failing_job_id: str) -> None:
        super().__init__(job_ids)
        self.failing_job_id = failing_job_id
        self.failed_once = False
        self.raised_count = 0

    def get(self, url: str, *, kind: str) -> ResponseEnvelope:
        if kind == "detail" and url.endswith(f"/{self.failing_job_id}") and not self.failed_once:
            self.failed_once = True
            self.raised_count += 1
            raise RuntimeError("transient detail consumer failure")
        return super().get(url, kind=kind)


class BudgetExhaustingTransport(ManyJobTransport):
    """Returns ``request_budget_exhausted`` for every detail request."""

    def get(self, url: str, *, kind: str) -> ResponseEnvelope:
        if kind == "detail":
            self.urls.append((url, kind))
            return ResponseEnvelope(0, "", "proxy-1", 0.0, "request_budget_exhausted")
        return super().get(url, kind=kind)


def _run(
    tmp_path: Path,
    *,
    transport: Any,
    pipeline_enabled: bool = True,
    detail_workers: int = 2,
    queue_size: int = 1000,
    mode: str = "smoke",
    max_companies: int = 1,
    resume_run_id: str | None = None,
    now: object = None,
) -> tuple[dict[str, object], Any]:
    source = tmp_path / "companies.csv"
    write_source_csv(source, single_company_rows())
    pagination = tmp_path / "pagination.json"
    write_pagination_report(pagination)
    config = RunnerConfig(
        input_csv=source,
        output_dir=tmp_path / "output",
        pagination_report=pagination,
        mode=mode,  # type: ignore[arg-type]
        max_companies=max_companies,
        pipeline_enabled=pipeline_enabled,
        detail_workers=detail_workers,
        pipeline_detail_queue_size=queue_size,
        resume_run_id=resume_run_id,
    )
    if now is None:
        metrics = CatalogRunner(config, transport=transport).run()
    else:
        metrics = CatalogRunner(config, transport=transport, now=now).run()
    return metrics, transport


def test_pipeline_backpressure_with_tiny_queue_completes_all_details(tmp_path: Path) -> None:
    job_ids = [str(2_000_000_000 + i) for i in range(40)]
    transport = ManyJobTransport(job_ids)
    metrics, _ = _run(tmp_path, transport=transport, queue_size=1, detail_workers=3)

    assert metrics["jobs_written"] == len(job_ids)
    assert metrics["run_outcome"] == "COMPLETE"
    assert sum(kind == "detail" for _, kind in transport.urls) == len(job_ids)


def test_pipeline_consumer_failure_does_not_lose_work_or_deadlock(tmp_path: Path) -> None:
    job_ids = ["1234567890", "1234567891", "1234567892"]
    transport = TransientDetailFailureTransport(job_ids, failing_job_id="1234567890")
    metrics, _ = _run(tmp_path, transport=transport, queue_size=2, detail_workers=2)

    assert transport.raised_count == 1
    assert metrics["jobs_written"] == len(job_ids)
    assert metrics["run_outcome"] == "COMPLETE"


def test_pipeline_budget_exhaustion_preserves_pending_details_for_resume(tmp_path: Path) -> None:
    job_ids = ["1234567890", "1234567891"]
    transport = BudgetExhaustingTransport(job_ids)
    metrics, _ = _run(tmp_path, transport=transport, detail_workers=2)

    assert metrics["run_outcome"] == "PARTIAL"
    assert metrics["jobs_written"] == 0
    state = StateStore(tmp_path / "output" / "master_linkedin_jobs_state.db")
    counts = state.detail_queue_counts(metrics["run_id"])
    # Both details failed on budget exhaustion and are still resumable.
    assert counts.get("retry", 0) == 2
    state.close()


def test_pipeline_pending_batches_are_durable_after_shutdown(tmp_path: Path) -> None:
    job_ids = [str(3_000_000_000 + i) for i in range(25)]
    transport = ManyJobTransport(job_ids)
    metrics, _ = _run(tmp_path, transport=transport, queue_size=1000, detail_workers=2)

    # Every enqueued detail was persisted and completed; the queue is fully drained.
    state = StateStore(tmp_path / "output" / "master_linkedin_jobs_state.db")
    counts = state.detail_queue_counts(metrics["run_id"])
    assert counts.get("pending", 0) == 0
    assert counts.get("retry", 0) == 0
    assert counts.get("done", 0) == len(job_ids)
    state.close()


def test_pipeline_resume_reprocesses_unfinished_details(tmp_path: Path) -> None:
    job_ids = ["1234567890", "1234567891"]
    # First run: detail requests fail with 503 so both remain RETRY.
    first_transport = ManyJobTransport(job_ids)
    original_get = first_transport.get

    class Failing(ManyJobTransport):
        def get(self, url: str, *, kind: str) -> ResponseEnvelope:
            if kind == "detail":
                self.urls.append((url, kind))
                return ResponseEnvelope(503, "temporary", "proxy-1", 0.01)
            return original_get(url, kind=kind)

    first_metrics, _ = _run(tmp_path, transport=Failing(job_ids), mode="full", now=lambda: "2026-08-31T08:00:00Z")
    assert first_metrics["run_outcome"] == "PARTIAL"

    state = StateStore(tmp_path / "output" / "master_linkedin_jobs_state.db")
    with state.connection:
        state.connection.execute(
            "UPDATE detail_queue SET next_attempt_at='' WHERE run_id=? AND status='RETRY'",
            (first_metrics["run_id"],),
        )
    state.close()

    # Second run: detail now succeeds; pending work is adopted and completed.
    second_transport = ManyJobTransport(job_ids)
    second_metrics, _ = _run(
        tmp_path,
        transport=second_transport,
        mode="pilot",
        now=lambda: "2026-08-31T10:00:00Z",
    )
    assert second_metrics["detail_resumed"] == 2
    assert second_metrics["detail_successes"] == 2
    assert second_metrics["jobs_written"] == 2


def test_pipeline_shared_limiter_caps_search_and_detail_in_flight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The single account limiter bounds combined search+detail in-flight work."""

    import scripts.master_linkedin_jobs_catalog as catalog_module

    job_ids = [str(4_000_000_000 + i) for i in range(20)]

    class FakeResponse:
        def __init__(self, text: str) -> None:
            self.text = text
            self.status_code = 200

    class FakeSession:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}
            self.trust_env = True

        def get(self, url: str, **_kwargs: object) -> object:
            time.sleep(0.005)
            if "seeMoreJobPostings/search" in url:
                text = _search_page(job_ids) if "start=0" in url else _no_results_page()
            else:
                text = _detail_page()
            return FakeResponse(text)

        def close(self) -> None:
            return None

    monkeypatch.setattr(catalog_module.requests, "Session", FakeSession)
    monkeypatch.setattr(
        catalog_module,
        "load_webshare_proxies",
        lambda: (WebshareProxy("p1", "http://p1:8080"), WebshareProxy("p2", "http://p2:8080")),
    )

    source = tmp_path / "companies.csv"
    write_source_csv(source, single_company_rows())
    pagination = tmp_path / "pagination.json"
    write_pagination_report(pagination)
    config = RunnerConfig(
        input_csv=source,
        output_dir=tmp_path / "output",
        pagination_report=pagination,
        mode="smoke",
        max_companies=1,
        pipeline_enabled=True,
        detail_workers=5,
        workers=2,
        min_workers=1,
        max_workers=2,
    )
    runner = CatalogRunner(config)
    metrics = runner.run()

    assert metrics["jobs_written"] == len(job_ids)
    # Search and detail share one limiter (the runner's adaptive limiter).
    assert runner.transport is not None
    assert runner.transport.request_limiter is runner.adaptive
    # The combined in-flight work never exceeded the account cap.
    assert runner.adaptive.peak_in_flight <= 2
    assert runner.adaptive.peak_in_flight == 2
