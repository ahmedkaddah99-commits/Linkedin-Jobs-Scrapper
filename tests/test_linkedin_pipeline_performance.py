"""Correctness and performance regressions for the LinkedIn producer pipeline.

These tests assert that the pipelined search+detail execution path produces the
same durable output, request accounting, cache identity, retry accounting and
resume state as the sequential path, while keeping concurrency bounded.
"""

from __future__ import annotations

import csv
import json
import threading
import time
from pathlib import Path

import pytest

from scripts.master_linkedin_jobs_catalog import (
    COMPANY_MATCH_EXACT_PRIMARY,
    CatalogRunner,
    ResponseEnvelope,
    RunnerConfig,
    StateStore,
)


FIXTURES = Path(__file__).parent / "fixtures"


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


def write_pagination_report(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "endpoint": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
                "page_step": 10,
                "full_card_count": 10,
                "max_start": 10,
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


class ScriptedTransport:
    def __init__(self, *, detail_body: str | None = None, search_body: str | None = None) -> None:
        self.urls: list[tuple[str, str]] = []
        self.detail_body = detail_body or (FIXTURES / "linkedin_job_detail.html").read_text()
        self.search_body = search_body or (FIXTURES / "linkedin_job_search_company_scoped.html").read_text()

    def get(self, url: str, *, kind: str) -> ResponseEnvelope:
        self.urls.append((url, kind))
        if kind == "search":
            if "start=0" in url:
                body = self.search_body
            else:
                body = (FIXTURES / "linkedin_job_search_no_results.html").read_text()
            return ResponseEnvelope(200, body, "proxy-1", 0.01)
        return ResponseEnvelope(200, self.detail_body, "proxy-1", 0.01)


class SlowScriptedTransport(ScriptedTransport):
    """Adds deterministic per-request latency to force concurrency overlap."""

    def __init__(self, latency: float = 0.02, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.latency = latency
        self._lock = threading.Lock()
        self.peak_in_flight = 0
        self._in_flight = 0

    def get(self, url: str, *, kind: str) -> ResponseEnvelope:
        with self._lock:
            self._in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self._in_flight)
        try:
            time.sleep(self.latency)
            return super().get(url, kind=kind)
        finally:
            with self._lock:
                self._in_flight -= 1


class DetailFailureTransport(ScriptedTransport):
    def get(self, url: str, *, kind: str) -> ResponseEnvelope:
        if kind == "detail":
            self.urls.append((url, kind))
            return ResponseEnvelope(503, "temporary detail failure", "proxy-1", 0.01)
        return super().get(url, kind=kind)


def run_smoke(
    tmp_path: Path,
    *,
    pipeline_enabled: bool,
    transport: ScriptedTransport,
    mode: str = "smoke",
    now: object = None,
) -> tuple[dict[str, object], ScriptedTransport]:
    source = tmp_path / "companies.csv"
    write_source_csv(source, single_company_rows())
    pagination = tmp_path / "pagination.json"
    write_pagination_report(pagination)
    config = RunnerConfig(
        input_csv=source,
        output_dir=tmp_path / "output",
        pagination_report=pagination,
        mode=mode,  # type: ignore[arg-type]
        max_companies=1,
        pipeline_enabled=pipeline_enabled,
    )
    if now is None:
        metrics = CatalogRunner(config, transport=transport).run()
    else:
        metrics = CatalogRunner(config, transport=transport, now=now).run()
    return metrics, transport


def test_pipeline_matches_sequential_output(tmp_path: Path) -> None:
    sequential_metrics, sequential_transport = run_smoke(
        tmp_path, pipeline_enabled=False, transport=ScriptedTransport()
    )
    pipelined_metrics, pipelined_transport = run_smoke(
        tmp_path, pipeline_enabled=True, transport=ScriptedTransport()
    )

    assert sequential_metrics["jobs_written"] == pipelined_metrics["jobs_written"] == 2
    assert sequential_metrics["detail_successes"] == pipelined_metrics["detail_successes"] == 2
    assert sequential_metrics["run_outcome"] == pipelined_metrics["run_outcome"]
    assert sequential_metrics["run_status"] == pipelined_metrics["run_status"]
    assert sorted(url for url, kind in sequential_transport.urls if kind == "detail") == sorted(
        url for url, kind in pipelined_transport.urls if kind == "detail"
    )
    assert sorted(url for url, kind in sequential_transport.urls if kind == "search") == sorted(
        url for url, kind in pipelined_transport.urls if kind == "search"
    )


def test_pipeline_overlaps_search_and_detail_requests(tmp_path: Path) -> None:
    transport = SlowScriptedTransport(latency=0.02)
    metrics, _ = run_smoke(tmp_path, pipeline_enabled=True, transport=transport)

    assert metrics["jobs_written"] == 2
    # Search and detail must overlap: more than one request in flight at some point.
    assert transport.peak_in_flight >= 2


def test_sequential_does_not_interleave_search_and_detail(tmp_path: Path) -> None:
    transport = SlowScriptedTransport(latency=0.02)
    _, _ = run_smoke(tmp_path, pipeline_enabled=False, transport=transport)

    # Sequential mode finishes every search request before the detail phase
    # starts, so no detail request precedes a search request in the record.
    kinds = [kind for _, kind in transport.urls]
    last_search = max(index for index, kind in enumerate(kinds) if kind == "search")
    first_detail = min(index for index, kind in enumerate(kinds) if kind == "detail")
    assert last_search < first_detail


def test_pipeline_preserves_detail_cache_hits(tmp_path: Path) -> None:
    body = (FIXTURES / "linkedin_job_search_valid.html").read_text()
    first_metrics, _ = run_smoke(
        tmp_path,
        pipeline_enabled=True,
        transport=ScriptedTransport(search_body=body),
        mode="full",
        now=lambda: "2026-08-31T08:00:00Z",
    )
    second_transport = ScriptedTransport(search_body=body)
    second_metrics, _ = run_smoke(
        tmp_path,
        pipeline_enabled=True,
        transport=second_transport,
        mode="daily",
        now=lambda: "2026-08-31T12:00:00Z",
    )

    assert first_metrics["detail_successes"] == 2
    assert second_metrics["detail_successes"] == 0
    assert second_metrics["detail_cache_hits"] == 2
    assert second_metrics["detail_avoided_requests"] == 2
    assert not any(kind == "detail" for _, kind in second_transport.urls)


def test_pipeline_preserves_detail_retry_and_budget(tmp_path: Path) -> None:
    first_transport = DetailFailureTransport(search_body=(FIXTURES / "linkedin_job_search_valid.html").read_text())
    first_metrics, _ = run_smoke(
        tmp_path,
        pipeline_enabled=True,
        transport=first_transport,
        mode="full",
        now=lambda: "2026-08-31T08:00:00Z",
    )

    assert first_metrics["run_outcome"] == "PARTIAL"
    assert first_metrics["detail_failures"] == 2

    state = StateStore(tmp_path / "output" / "master_linkedin_jobs_state.db")
    with state.connection:
        state.connection.execute(
            "UPDATE detail_queue SET next_attempt_at='' WHERE run_id=? AND status='RETRY'",
            (first_metrics["run_id"],),
        )
    state.close()

    second_transport = ScriptedTransport(search_body=(FIXTURES / "linkedin_job_search_valid.html").read_text())
    second_metrics, _ = run_smoke(
        tmp_path,
        pipeline_enabled=True,
        transport=second_transport,
        mode="pilot",
        now=lambda: "2026-08-31T10:00:00Z",
    )

    assert second_metrics["detail_resumed"] == 2
    assert second_metrics["detail_successes"] == 2
    assert sum(kind == "detail" for _, kind in second_transport.urls) == 2


def test_pipeline_respects_request_accounting(tmp_path: Path) -> None:
    metrics, transport = run_smoke(tmp_path, pipeline_enabled=True, transport=ScriptedTransport())

    # Two search pages (start=0 plus one no-results) and two detail requests.
    assert sum(kind == "search" for _, kind in transport.urls) == 2
    assert sum(kind == "detail" for _, kind in transport.urls) == 2
    assert metrics["requests"] == 4
    assert metrics["detail_requests"] == 2
    assert metrics["jobs_written"] == 2
