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
from scripts.benchmark_linkedin_pipeline import (
    BENCHMARK_PROFILES,
    BENCHMARK_WINDOW_SECONDS,
    BenchmarkWorkload,
    evaluate_benchmark_contract,
    run_benchmark,
)
from scripts.run_manifested_linkedin import build_dry_run_receipt


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


def test_five_minute_contract_has_lifecycle_counts_and_machine_reason_codes() -> None:
    result = evaluate_benchmark_contract(
        profile="ci-fixture",
        counts={
            "discovered": 10,
            "parsed": 10,
            "complete": 9,
            "accepted": 7,
            "published": 6,
            "duplicate": 1,
            "failed": 0,
        },
        elapsed_seconds=2.0,
        cpu_seconds=1.0,
        rss_bytes=64 * 1024 * 1024,
        browser_requests=0,
        requests=20,
        concurrency=4,
        timeout_seconds=30,
        accepted_source="approved-offline-source",
        approval_status="approved",
    )

    assert result["window_seconds"] == BENCHMARK_WINDOW_SECONDS == 300
    assert set(result["counts"]) == {
        "discovered", "parsed", "complete", "accepted", "published", "duplicate", "failed"
    }
    assert result["counts"]["accepted"] == 7
    assert result["counts"]["published"] == 6
    assert result["status"] == "PASS"
    assert result["passed"] is True
    assert result["reason_codes"] == ["within_profile_ceilings"]
    assert result["owner"] == "acquisition"
    assert result["revision"] == "T36"
    assert result["approval"]["status"] == "approved"
    assert result["accepted_source"] == "approved-offline-source"
    assert result["info_codes"] == ["accepted_throughput_threshold_unconfigured"]


def test_unsourced_accepted_counts_are_zeroed_and_failed() -> None:
    result = evaluate_benchmark_contract(
        profile="ci-fixture",
        counts={
            "discovered": 10,
            "parsed": 9,
            "complete": 8,
            "accepted": 7,
            "published": 6,
            "duplicate": 1,
            "failed": 1,
        },
        elapsed_seconds=2.0,
        cpu_seconds=1.0,
        rss_bytes=64 * 1024 * 1024,
        browser_requests=0,
        requests=20,
        concurrency=4,
        timeout_seconds=30,
    )

    assert result["status"] == "FAIL"
    assert "accepted_counts_unsourced" in result["reason_codes"]
    assert result["counts_zeroed_by_source_guard"] == ["accepted", "published"]
    assert result["counts"]["accepted"] == 0
    assert result["counts"]["published"] == 0


def test_accepted_source_requires_explicit_approval() -> None:
    result = evaluate_benchmark_contract(
        profile="ci-fixture",
        counts={
            "discovered": 5,
            "parsed": 5,
            "complete": 5,
            "accepted": 4,
            "published": 4,
            "duplicate": 0,
            "failed": 0,
        },
        elapsed_seconds=1.0,
        cpu_seconds=0.5,
        rss_bytes=64 * 1024 * 1024,
        browser_requests=0,
        requests=5,
        concurrency=2,
        timeout_seconds=30,
        accepted_source="undeclared-approval",
    )

    assert result["status"] == "FAIL"
    assert "accepted_counts_unsourced" in result["reason_codes"]
    assert result["counts"]["accepted"] == 0


def test_minimum_accepted_throughput_threshold_is_parameterized() -> None:
    base_counts = {
        "discovered": 6,
        "parsed": 6,
        "complete": 6,
        "accepted": 6,
        "published": 6,
        "duplicate": 0,
        "failed": 0,
    }
    passing = evaluate_benchmark_contract(
        profile="ci-fixture",
        counts=base_counts,
        elapsed_seconds=1.0,
        cpu_seconds=0.5,
        rss_bytes=64 * 1024 * 1024,
        browser_requests=0,
        requests=6,
        concurrency=2,
        timeout_seconds=30,
        accepted_source="approved-offline-source",
        approval_status="approved",
        minimum_accepted_per_window=300,
    )
    failing = evaluate_benchmark_contract(
        profile="ci-fixture",
        counts=dict(base_counts, accepted=0),
        elapsed_seconds=1.0,
        cpu_seconds=0.5,
        rss_bytes=64 * 1024 * 1024,
        browser_requests=0,
        requests=6,
        concurrency=2,
        timeout_seconds=30,
        accepted_source="approved-offline-source",
        approval_status="approved",
        minimum_accepted_per_window=300,
    )

    assert passing["status"] == "PASS"
    assert failing["status"] == "FAIL"
    assert "accepted_throughput_below_minimum" in failing["reason_codes"]


def test_profile_ceilings_are_parameterizable_threshold_inputs() -> None:
    defaults = [tuple(sorted(profile.items())) for profile in BENCHMARK_PROFILES.values()]
    assert len(set(defaults)) == len(defaults)

    overridden = evaluate_benchmark_contract(
        profile="local-dry-run",
        counts={name: 0 for name in ("discovered", "parsed", "complete", "accepted", "published", "duplicate", "failed")},
        elapsed_seconds=1.0,
        cpu_seconds=0.1,
        rss_bytes=2_048,
        browser_requests=0,
        requests=0,
        concurrency=1,
        timeout_seconds=1,
        thresholds_override={"rss_bytes": 1_024},
    )

    assert overridden["status"] == "FAIL"
    assert "rss_bytes_ceiling_exceeded" in overridden["reason_codes"]
    assert overridden["thresholds"]["overrides"] == {"rss_bytes": 1_024}
    assert overridden["thresholds"]["profile_defaults"]["rss_bytes"] > 1_024

    try:
        evaluate_benchmark_contract(
            profile="local-dry-run",
            counts={name: 0 for name in ("discovered", "parsed", "complete", "accepted", "published", "duplicate", "failed")},
            elapsed_seconds=1.0,
            cpu_seconds=0.1,
            rss_bytes=None,
            browser_requests=0,
            requests=0,
            concurrency=1,
            timeout_seconds=1,
            thresholds_override={"unknown_key": 5},
        )
    except ValueError as exc:
        assert "unknown threshold keys" in str(exc)
    else:
        raise AssertionError("unknown threshold override keys must be rejected")


def test_vps_profile_requires_explicit_approval() -> None:
    result = evaluate_benchmark_contract(
        profile="vps-authorized-live",
        counts={name: 0 for name in ("discovered", "parsed", "complete", "accepted", "published", "duplicate", "failed")},
        elapsed_seconds=1.0,
        cpu_seconds=1.0,
        rss_bytes=64 * 1024 * 1024,
        browser_requests=0,
        requests=0,
        concurrency=1,
        timeout_seconds=30,
    )

    assert result["status"] == "FAIL"
    assert result["passed"] is False
    assert result["reason_codes"] == ["approval_required"]
    assert set(BENCHMARK_PROFILES["vps-authorized-live"]) == {
        "cpu_seconds", "rss_bytes", "browser_requests", "requests",
        "concurrency", "timeout_seconds", "errors",
    }


def test_offline_pipeline_benchmark_emits_common_contract(tmp_path: Path) -> None:
    result = run_benchmark(
        BenchmarkWorkload(companies=1, pages_per_company=1, jobs_per_page=1)
    )

    contract = result["benchmark_contract"]
    assert contract["window_seconds"] == 300
    assert set(contract["counts"]) == {
        "discovered", "parsed", "complete", "accepted", "published", "duplicate", "failed"
    }
    # Producer rows are never counted as accepted/published without T32.
    assert contract["counts"]["accepted"] == 0
    assert contract["counts"]["published"] == 0
    assert contract["accepted_source"] is None
    assert contract["info_codes"] == ["accepted_throughput_threshold_unconfigured"]


def _duplicate_card_page(job_id: str) -> str:
    card = (
        '<li class="job-card-container" data-entity-urn="urn:li:jobPosting:{job_id}">'
        '<a href="https://www.linkedin.com/company/acme">Acme</a>'
        '<a href="https://www.linkedin.com/jobs/view/{job_id}"></a>'
        '<h3 class="base-search-card__title">Engineer</h3>'
        '<span class="job-search-card__location">Berlin, Germany</span>'
        '<time datetime="2026-08-31">1 day ago</time>'
        "</li>"
    ).format(job_id=job_id)
    return (
        '<html><body><ul class="jobs-search__results-list">'
        + card
        + card
        + "</ul></body></html>"
    )


def _publishable_detail_page() -> str:
    return (
        '<article class="top-card-layout">'
        '<h1 class="top-card-layout__title">Senior Engineer</h1>'
        '<h4 class="top-card-layout__second-subline">'
        '<a href="https://www.linkedin.com/company/acme">Acme</a>'
        "</h4>"
        '<div class="top-card-layout__first-subline"><span>Berlin, Germany</span></div>'
        '<a class="top-card-layout__cta--primary" '
        'data-tracking-control-name="public_jobs_apply-link-offsite" '
        'href="https://jobs.acme.example/apply/1234567890">Apply</a>'
        '<section class="show-more-less-html">'
        '<div class="description__text description__text--rich">'
        "<p>Build and operate reliable data systems that keep the customer "
        "catalog complete. You will design bounded collection pipelines, keep "
        "durable state snapshots consistent, and make identity resolution "
        "observable for every job the producer captures each day.</p>"
        "</div></section></article>"
    )


def test_receipt_classes_distinguish_parsed_cards_from_deduped_jobs(tmp_path: Path) -> None:
    """A search page repeating one job card parses twice but stores one job.

    The pipelined enqueue publishes every batched task to the workers, so one
    duplicated card is fetched twice; the durable catalog and observation
    tables deduplicate by ``(linkedin_company_id, linkedin_job_id)``. The
    receipt therefore reports parsed cards (2) separately from durable
    identity-resolved jobs (1) instead of trusting the write counter.
    """

    transport = ScriptedTransport(
        search_body=_duplicate_card_page("1234567890"),
        detail_body=_publishable_detail_page(),
    )
    metrics, _ = run_smoke(tmp_path, pipeline_enabled=True, transport=transport)

    # Pre-existing pipelined over-fetch: one duplicated card, two detail
    # requests. Owned by the producer library (not a T29 allowed path); the
    # receipt must still resolve the durable identity to exactly one job.
    assert metrics["jobs_written"] == 2
    assert sum(kind == "detail" for _, kind in transport.urls) == 2

    receipt = build_dry_run_receipt(
        metrics,
        tmp_path / "output" / "master_linkedin_jobs_state.db",
        {"max_requests": 0},
    )
    # parsed counts every card parsed from the page (2), while
    # identity_resolved counts durable deduplicated observations (1).
    assert receipt["parsed"] == metrics["valid_cards"] == 2
    assert receipt["identity_resolved"] == 1
    assert receipt["rejected"] == 0
    assert receipt["publishable"] == 1
