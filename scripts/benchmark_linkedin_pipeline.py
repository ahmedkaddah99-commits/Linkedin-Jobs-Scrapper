"""Offline LinkedIn producer pipeline benchmark.

This benchmark runs the actual ``scripts/master_linkedin_jobs_catalog.py``
producer against synthetic fixtures with artificial network latency.  It is
designed to compare the sequential baseline and the pipelined optimizer while
consuming no paid provider credits.

T37 extends every receipt with the evaluated contract revision, the LinkedIn
input profile, the effective provider limits, per-class failure counts, the
quality yield between lifecycle stages, and a non-waivable optimization
follow-up for any missed threshold or missing accepted-source configuration.
"""

from __future__ import annotations

import argparse
import ctypes
import csv
import json
import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.master_linkedin_jobs_catalog import (
    SEARCH_ENDPOINT,
    CatalogRunner,
    ResponseEnvelope,
    RunnerConfig,
)

FIXTURES = ROOT / "tests" / "fixtures"

BENCHMARK_CONTRACT = "runr.producer-throughput.v1"
BENCHMARK_REVISION = "T36"
BENCHMARK_OWNER = "acquisition"
BENCHMARK_WINDOW_SECONDS = 300
BENCHMARK_SOURCE = "linkedin"
LINKEDIN_BENCHMARK_REVISION = "T37"

# These are admission ceilings, not claims about measured provider capacity.
# The live profile is intentionally explicit about its approval requirement.
BENCHMARK_PROFILES: dict[str, dict[str, int]] = {
    "local-dry-run": {
        "cpu_seconds": 300,
        "rss_bytes": 1_073_741_824,
        "browser_requests": 0,
        "requests": 500,
        "concurrency": 8,
        "timeout_seconds": 30,
        "errors": 0,
    },
    "ci-fixture": {
        "cpu_seconds": 120,
        "rss_bytes": 1_073_741_824,
        "browser_requests": 0,
        "requests": 2_000,
        "concurrency": 16,
        "timeout_seconds": 30,
        "errors": 0,
    },
    "vps-authorized-live": {
        "cpu_seconds": 270,
        "rss_bytes": 2_147_483_648,
        "browser_requests": 500,
        "requests": 10_000,
        "concurrency": 32,
        "timeout_seconds": 45,
        "errors": 100,
    },
}

THROUGHPUT_COUNT_NAMES = (
    "discovered",
    "parsed",
    "complete",
    "accepted",
    "published",
    "duplicate",
    "failed",
)


def normalize_throughput_counts(values: Mapping[str, object]) -> dict[str, int]:
    """Return the common lifecycle counters with stable, non-negative values."""

    counts: dict[str, int] = {}
    for name in THROUGHPUT_COUNT_NAMES:
        try:
            value = int(values.get(name, 0) or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"throughput count {name!r} must be an integer") from exc
        if value < 0:
            raise ValueError(f"throughput count {name!r} must not be negative")
        counts[name] = value
    return counts


def benchmark_failure_count(metrics: Mapping[str, object]) -> int:
    """Collapse producer failure signals into the contract's error count."""

    observed_failures = []
    for name in ("detail_failures", "companies_partial", "companies_failed"):
        try:
            observed_failures.append(max(0, int(metrics.get(name, 0) or 0)))
        except (TypeError, ValueError):
            observed_failures.append(0)
    failure_count = max(observed_failures, default=0)
    run_outcome = str(metrics.get("run_outcome") or "").upper()
    run_status = str(metrics.get("run_status") or "").upper()
    if failure_count == 0 and (
        run_outcome in {"FAILURE", "FAILED", "PARTIAL"}
        or run_status in {"FAILED", "PARTIAL"}
    ):
        return 1
    return failure_count


def load_thresholds_override(path: Path) -> dict[str, int]:
    """Load operator-supplied ceiling overrides (parameterized threshold input)."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("threshold override file must be a JSON object")
    return dict(payload)


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def evaluate_benchmark_contract(
    *,
    profile: str,
    counts: Mapping[str, object],
    elapsed_seconds: float,
    cpu_seconds: float,
    rss_bytes: int | None,
    browser_requests: int,
    requests: int,
    concurrency: int,
    timeout_seconds: float,
    approval_status: str = "not-required",
    owner: str = BENCHMARK_OWNER,
    revision: str = BENCHMARK_REVISION,
    accepted_source: str | None = None,
    thresholds_override: Mapping[str, int] | None = None,
    minimum_accepted_per_window: int | None = None,
    failure_classes: Mapping[str, int] | None = None,
    input_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one run against the shared five-minute producer contract.

    The profile ceilings are admission ceilings and parameterized threshold
    inputs: ``thresholds_override`` may replace any ceiling for one evaluation.
    ``accepted``/``published`` counts are only honored when a declared
    ``accepted_source`` exists (the T32 publishable contract) and the run is
    explicitly approved; unsourced counts are zeroed and failed with a reason
    code instead of being counted from producer rows.

    The T37 receipt extensions identify the evaluated contract revision, the
    LinkedIn input profile, the effective provider limits, per-class failure
    counts, and the quality yield between lifecycle stages. A missed threshold
    or a missing accepted-source/throughput configuration always creates an
    optimization follow-up; it is never waived.
    """

    if profile not in BENCHMARK_PROFILES:
        raise ValueError(f"unknown benchmark profile: {profile}")
    if elapsed_seconds < 0 or cpu_seconds < 0:
        raise ValueError("elapsed and CPU seconds must not be negative")

    ceilings = dict(BENCHMARK_PROFILES[profile])
    thresholds: dict[str, Any] = {
        "profile_defaults": dict(BENCHMARK_PROFILES[profile]),
        "overrides": {},
        "minimum_accepted_per_window": minimum_accepted_per_window,
    }
    if thresholds_override is not None:
        unknown = set(thresholds_override) - set(ceilings)
        if unknown:
            raise ValueError(f"unknown threshold keys: {sorted(unknown)}")
        for name, value in thresholds_override.items():
            number = int(value)
            if number < 0:
                raise ValueError(f"threshold override {name!r} must not be negative")
            ceilings[name] = number
        thresholds["overrides"] = {name: int(value) for name, value in thresholds_override.items()}

    normalized_counts = normalize_throughput_counts(counts)
    source_declared = bool(accepted_source and accepted_source.strip())
    source_approved = source_declared and approval_status == "approved"
    zeroed_counts: list[str] = []
    if not source_approved:
        for name in ("accepted", "published"):
            if normalized_counts[name]:
                normalized_counts[name] = 0
                zeroed_counts.append(name)
    observed = {
        "cpu_seconds": round(cpu_seconds, 4),
        "rss_bytes": rss_bytes,
        "browser_requests": int(browser_requests),
        "requests": int(requests),
        "concurrency": int(concurrency),
        "timeout_seconds": float(timeout_seconds),
        "errors": normalized_counts["failed"],
    }
    reasons: list[str] = []
    for name, value in observed.items():
        ceiling = ceilings[name]
        if value is not None and value > ceiling:
            reasons.append(f"{name}_ceiling_exceeded")
    for current, previous in (
        ("parsed", "discovered"),
        ("complete", "parsed"),
        ("accepted", "complete"),
        ("published", "accepted"),
    ):
        if normalized_counts[current] > normalized_counts[previous]:
            reasons.append(f"{current}_exceeds_{previous}")
    if rss_bytes is None:
        reasons.append("rss_unavailable")
    if profile == "vps-authorized-live" and approval_status != "approved":
        reasons.append("approval_required")
    if zeroed_counts:
        reasons.append("accepted_counts_unsourced")
    if minimum_accepted_per_window is not None:
        throughput = normalized_counts["accepted"] * BENCHMARK_WINDOW_SECONDS / max(elapsed_seconds, 0.001)
        if throughput < minimum_accepted_per_window:
            reasons.append("accepted_throughput_below_minimum")
    info_codes: list[str] = []
    if rss_bytes is None:
        info_codes.append("rss_unavailable")
    if minimum_accepted_per_window is None:
        info_codes.append("accepted_throughput_threshold_unconfigured")
    if not reasons:
        reasons.append("within_profile_ceilings")

    passed = reasons == ["within_profile_ceilings"]

    follow_up_reasons = [] if passed else list(reasons)
    follow_up_actions: list[str] = []
    if not source_approved:
        follow_up_reasons.append("accepted_source_not_declared")
        follow_up_actions.append("declare-accepted-source")
    if minimum_accepted_per_window is None:
        follow_up_reasons.append("accepted_throughput_threshold_unconfigured")
        follow_up_actions.append("configure-accepted-throughput-threshold")

    return {
        "contract": BENCHMARK_CONTRACT,
        "contract_revision": BENCHMARK_REVISION,
        "benchmark_revision": revision,
        "window_seconds": BENCHMARK_WINDOW_SECONDS,
        "elapsed_seconds": round(elapsed_seconds, 4),
        "profile": profile,
        "owner": owner,
        "revision": revision,
        "approval": {
            "required": profile == "vps-authorized-live" or source_declared,
            "status": approval_status,
        },
        "accepted_source": accepted_source,
        "input_profile": dict(input_profile) if input_profile is not None else {},
        "provider_limits": {
            "max_requests": ceilings["requests"],
            "max_browser_requests": ceilings["browser_requests"],
            "max_concurrency": ceilings["concurrency"],
            "timeout_seconds": ceilings["timeout_seconds"],
            "max_errors": ceilings["errors"],
            "approval_status": approval_status,
        },
        "counts": normalized_counts,
        "counts_zeroed_by_source_guard": zeroed_counts,
        "failure_classes": dict(failure_classes) if failure_classes is not None else {},
        "quality_yield": {
            "parsed_over_discovered": _ratio(normalized_counts["parsed"], normalized_counts["discovered"]),
            "complete_over_discovered": _ratio(normalized_counts["complete"], normalized_counts["discovered"]),
            "accepted_over_complete": (
                _ratio(normalized_counts["accepted"], normalized_counts["complete"])
                if source_approved
                else None
            ),
            "published_over_accepted": (
                _ratio(normalized_counts["published"], normalized_counts["accepted"])
                if source_approved
                else None
            ),
            "accepted_counts_sourced": source_approved,
        },
        "thresholds": thresholds,
        "throughput_per_300_seconds": {
            name: round(value * BENCHMARK_WINDOW_SECONDS / max(elapsed_seconds, 0.001), 2)
            for name, value in normalized_counts.items()
        },
        "ceilings": ceilings,
        "observed": observed,
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "reason_codes": reasons,
        "info_codes": info_codes,
        "optimization_follow_up": {
            "required": bool(follow_up_reasons or follow_up_actions),
            "reason_codes": follow_up_reasons,
            "actions": follow_up_actions,
            "waived": False,
        },
    }


@dataclass
class BenchmarkWorkload:
    companies: int = 5
    pages_per_company: int = 2
    jobs_per_page: int = 5
    search_latency_seconds: float = 0.05
    detail_latency_seconds: float = 0.05
    company_id_start: int = 100000
    job_id_start: int = 1_000_000_000

    @property
    def total_jobs(self) -> int:
        return self.companies * self.pages_per_company * self.jobs_per_page

    @property
    def total_search_requests(self) -> int:
        # one extra empty-termination page per company
        return self.companies * (self.pages_per_company + 1)

    @property
    def total_detail_requests(self) -> int:
        return self.total_jobs


def _peak_rss_bytes() -> int | None:
    if os.name == "nt":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        get_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_memory_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        get_memory_info.restype = wintypes.BOOL
        process = ctypes.windll.kernel32.GetCurrentProcess()
        ok = get_memory_info(process, ctypes.byref(counters), ctypes.sizeof(counters))
        return int(counters.PeakWorkingSetSize) if ok else None
    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value * (1024 if sys.platform != "darwin" else 1)
    except (ImportError, AttributeError):
        return None


def _job_card_html(job_id: str, company_slug: str, title: str) -> str:
    return (
        '<li class="job-card-container" data-entity-urn="urn:li:jobPosting:{job_id}">\n'
        '  <a href="https://www.linkedin.com/company/{company_slug}">{company_slug}</a>\n'
        '  <a href="https://www.linkedin.com/jobs/view/{job_id}"></a>\n'
        '  <h3 class="base-search-card__title">{title}</h3>\n'
        '  <span class="job-search-card__location">Berlin, Germany</span>\n'
        '  <time datetime="2026-08-31">1 day ago</time>\n'
        '</li>\n'
    ).format(job_id=job_id, company_slug=company_slug, title=title)


def _search_page_html(company_slug: str, job_ids: list[str]) -> str:
    cards = "".join(
        _job_card_html(job_id, company_slug, f"Engineer {index + 1}")
        for index, job_id in enumerate(job_ids)
    )
    return (
        '<!DOCTYPE html><html><body><ul class="jobs-search__results-list">'
        f"{cards}</ul></body></html>"
    )


def _detail_page_html(job_id: str, company_slug: str) -> str:
    detail = (FIXTURES / "linkedin_job_detail.html").read_text(encoding="utf-8")
    return detail.replace("company/acme", f"company/{company_slug}").replace(
        "1234567890", job_id
    )


def _write_input_csv(path: Path, workload: BenchmarkWorkload) -> None:
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
        for index in range(workload.companies):
            company_id = str(workload.company_id_start + index)
            slug = f"company-{index}"
            writer.writerow(
                {
                    "canonical_CompanyID": f"C-{index:04d}",
                    "company_name": f"Company {index}",
                    "linkedin_company_url": f"https://www.linkedin.com/company/{slug}",
                    "linkedin_slug": slug,
                    "linkedin_company_id": company_id,
                }
            )


def _write_pagination_report(path: Path, workload: BenchmarkWorkload) -> None:
    max_start = workload.pages_per_company * 10
    path.write_text(
        json.dumps(
            {
                "endpoint": SEARCH_ENDPOINT,
                "page_step": 10,
                "full_card_count": workload.jobs_per_page,
                "max_start": max_start,
            }
        ),
        encoding="utf-8",
    )


class BenchmarkTransport:
    """Mock transport with configurable latency for offline replay."""

    def __init__(
        self,
        workload: BenchmarkWorkload,
        *,
        search_latency: float = 0.0,
        detail_latency: float = 0.0,
    ) -> None:
        self.workload = workload
        self.search_latency = search_latency
        self.detail_latency = detail_latency
        self.urls: list[tuple[str, str]] = []
        self._lock = threading.Lock()
        self._peak_in_flight = 0
        self._in_flight = 0

    def get(self, url: str, *, kind: str) -> ResponseEnvelope:
        with self._lock:
            self._in_flight += 1
            self._peak_in_flight = max(self._peak_in_flight, self._in_flight)
        try:
            self.urls.append((url, kind))
            if kind == "search":
                if self.search_latency:
                    time.sleep(self.search_latency)
                return self._search_response(url)
            if kind == "company":
                return ResponseEnvelope(200, "", "proxy-1", 0.0)
            if self.detail_latency:
                time.sleep(self.detail_latency)
            return self._detail_response(url)
        finally:
            with self._lock:
                self._in_flight -= 1

    def _search_response(self, url: str) -> ResponseEnvelope:
        params: dict[str, list[str]] = {}
        for key, value in [
            pair.split("=", 1) for pair in url.split("?", 1)[-1].split("&") if "=" in pair
        ]:
            params.setdefault(key, []).append(value)
        company_id = params.get("f_C", [""])[0]
        start = int(params.get("start", ["0"])[0])
        index = int(company_id) - self.workload.company_id_start
        slug = f"company-{index}"
        page_index = start // 10
        if page_index >= self.workload.pages_per_company:
            body = (FIXTURES / "linkedin_job_search_no_results.html").read_text(encoding="utf-8")
        else:
            base_job_id = self.workload.job_id_start + (
                index * self.workload.pages_per_company * self.workload.jobs_per_page
                + page_index * self.workload.jobs_per_page
            )
            job_ids = [str(base_job_id + offset) for offset in range(self.workload.jobs_per_page)]
            body = _search_page_html(slug, job_ids)
        return ResponseEnvelope(200, body, "proxy-1", self.search_latency)

    def _detail_response(self, url: str) -> ResponseEnvelope:
        job_id = url.rsplit("/", 1)[-1]
        # Derive company slug from job id range
        offset = int(job_id) - self.workload.job_id_start
        index = offset // (self.workload.pages_per_company * self.workload.jobs_per_page)
        slug = f"company-{index}"
        body = _detail_page_html(job_id, slug)
        return ResponseEnvelope(200, body, "proxy-1", self.detail_latency)

    @property
    def peak_in_flight(self) -> int:
        with self._lock:
            return self._peak_in_flight


def _warm_start_state(
    output_dir: Path,
    workload: BenchmarkWorkload,
    input_csv: Path,
    pagination: Path,
) -> None:
    """Populate the state DB by running a real cold collection first.

    The warm-up run persists job observations so the benchmark run in ``daily``
    mode exercises the detail cache-reuse path instead of re-fetching detail.
    """

    transport = BenchmarkTransport(
        workload,
        search_latency=0.0,
        detail_latency=0.0,
    )
    config = RunnerConfig(
        input_csv=input_csv,
        output_dir=output_dir,
        pagination_report=pagination,
        mode="full",
        pipeline_enabled=False,
    )
    CatalogRunner(config, transport=transport).run()


def run_benchmark(
    workload: BenchmarkWorkload,
    *,
    pipeline_enabled: bool = True,
    workers: int = 5,
    detail_workers: int = 5,
    warm_cache: bool = False,
    mode: str = "full",
    profile: str = "ci-fixture",
    owner: str = BENCHMARK_OWNER,
    revision: str = LINKEDIN_BENCHMARK_REVISION,
    approval_status: str = "not-required",
    timeout_seconds: float = 30.0,
    accepted_source: str | None = None,
    thresholds_override: Mapping[str, int] | None = None,
    minimum_accepted_per_window: int | None = None,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="runr-linkedin-bench-") as tmp:
        tmp_path = Path(tmp)
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        input_csv = tmp_path / "companies.csv"
        pagination = tmp_path / "pagination.json"
        _write_input_csv(input_csv, workload)
        _write_pagination_report(pagination, workload)
        if warm_cache:
            _warm_start_state(output_dir, workload, input_csv, pagination)
            mode = "daily"
        transport = BenchmarkTransport(
            workload,
            search_latency=workload.search_latency_seconds,
            detail_latency=workload.detail_latency_seconds,
        )
        config = RunnerConfig(
            input_csv=input_csv,
            output_dir=output_dir,
            pagination_report=pagination,
            mode=mode,  # type: ignore[arg-type]
            workers=workers,
            detail_workers=detail_workers,
            timeout=timeout_seconds,
            pipeline_enabled=pipeline_enabled,
        )
        runner = CatalogRunner(config, transport=transport)
        started = time.perf_counter()
        started_cpu = time.process_time()
        metrics = runner.run()
        wall_time = time.perf_counter() - started
        cpu_time = time.process_time() - started_cpu
        peak_rss_bytes = _peak_rss_bytes()
        return {
            "pipeline_enabled": pipeline_enabled,
            "workload": {
                "companies": workload.companies,
                "pages_per_company": workload.pages_per_company,
                "jobs_per_page": workload.jobs_per_page,
                "total_jobs": workload.total_jobs,
                "search_latency_seconds": workload.search_latency_seconds,
                "detail_latency_seconds": workload.detail_latency_seconds,
            },
            "wall_time_seconds": wall_time,
            "cpu_time_seconds": cpu_time,
            "peak_rss_bytes": peak_rss_bytes,
            "requests": metrics.get("requests", 0),
            "detail_requests": metrics.get("detail_requests", 0),
            "detail_cache_hits": metrics.get("detail_cache_hits", 0),
            "detail_successes": metrics.get("detail_successes", 0),
            "jobs_written": metrics.get("jobs_written", 0),
            "companies_completed": metrics.get("companies_completed", 0),
            "companies_partial": metrics.get("companies_partial", 0),
            "run_outcome": metrics.get("run_outcome"),
            "transport_peak_in_flight": transport.peak_in_flight,
            "benchmark_contract": evaluate_benchmark_contract(
                profile=profile,
                counts={
                    # The synthetic transport exposes every generated card;
                    # producer detail success is the parsed/complete stage.
                    # Without a T32-declared accepted source, accepted and
                    # published stay zero: producer rows are not publishable
                    # counts. Cache hits are repeat observations (duplicates).
                    "discovered": workload.total_jobs,
                    "parsed": metrics.get("detail_successes", 0),
                    "complete": metrics.get("detail_successes", 0),
                    "accepted": 0,
                    "published": 0,
                    "duplicate": metrics.get("detail_cache_hits", 0),
                    "failed": benchmark_failure_count(metrics),
                },
                elapsed_seconds=wall_time,
                cpu_seconds=cpu_time,
                rss_bytes=peak_rss_bytes,
                browser_requests=0,
                requests=int(metrics.get("requests", 0) or 0),
                concurrency=max(transport.peak_in_flight, workers, detail_workers),
                timeout_seconds=timeout_seconds,
                approval_status=approval_status,
                owner=owner,
                revision=revision,
                accepted_source=accepted_source,
                thresholds_override=thresholds_override,
                minimum_accepted_per_window=minimum_accepted_per_window,
                failure_classes={
                    "detail_failures": int(metrics.get("detail_failures", 0) or 0),
                    "companies_partial": int(metrics.get("companies_partial", 0) or 0),
                    "companies_failed": int(metrics.get("companies_failed", 0) or 0),
                },
                input_profile={
                    "source": BENCHMARK_SOURCE,
                    "fixture_transport": "synthetic-html",
                    "mode": mode,
                    "pipeline_enabled": pipeline_enabled,
                    "warm_cache": warm_cache,
                    "workers": workers,
                    "detail_workers": detail_workers,
                    "workload": {
                        "companies": workload.companies,
                        "pages_per_company": workload.pages_per_company,
                        "jobs_per_page": workload.jobs_per_page,
                        "total_jobs": workload.total_jobs,
                        "search_latency_seconds": workload.search_latency_seconds,
                        "detail_latency_seconds": workload.detail_latency_seconds,
                    },
                },
            ),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies", type=int, default=5)
    parser.add_argument("--pages-per-company", type=int, default=2)
    parser.add_argument("--jobs-per-page", type=int, default=5)
    parser.add_argument("--search-latency", type=float, default=0.05)
    parser.add_argument("--detail-latency", type=float, default=0.05)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--detail-workers", type=int, default=5)
    parser.add_argument("--compare", action="store_true", help="run sequential and pipelined back-to-back")
    parser.add_argument("--warm-cache", action="store_true", help="pre-seed state so the run exercises cache reuse")
    parser.add_argument("--profile", choices=tuple(BENCHMARK_PROFILES), default="ci-fixture")
    parser.add_argument("--owner", default=BENCHMARK_OWNER)
    parser.add_argument("--revision", default=LINKEDIN_BENCHMARK_REVISION)
    parser.add_argument(
        "--approval",
        dest="approval_status",
        choices=("not-required", "approved"),
        default="not-required",
        help="required for the vps-authorized-live profile",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--accepted-source",
        default=None,
        help="declared source for accepted/published counts (requires --approval approved)",
    )
    parser.add_argument(
        "--minimum-accepted",
        dest="minimum_accepted_per_window",
        type=int,
        default=None,
        help="minimum accepted jobs per 300-second window; operator sign-off required",
    )
    parser.add_argument(
        "--thresholds",
        type=Path,
        default=None,
        help="JSON file overriding the profile ceiling keys for this evaluation",
    )
    parser.add_argument("--output", type=Path, help="write JSON report to this path")
    args = parser.parse_args(argv)
    thresholds_override = load_thresholds_override(args.thresholds) if args.thresholds else None
    workload = BenchmarkWorkload(
        companies=args.companies,
        pages_per_company=args.pages_per_company,
        jobs_per_page=args.jobs_per_page,
        search_latency_seconds=args.search_latency,
        detail_latency_seconds=args.detail_latency,
    )
    results: list[dict[str, Any]] = []
    if args.compare:
        results.append(
            run_benchmark(
                workload,
                pipeline_enabled=False,
                workers=args.workers,
                detail_workers=args.detail_workers,
                warm_cache=args.warm_cache,
                profile=args.profile,
                owner=args.owner,
                revision=args.revision,
                approval_status=args.approval_status,
                timeout_seconds=args.timeout,
                accepted_source=args.accepted_source,
                thresholds_override=thresholds_override,
                minimum_accepted_per_window=args.minimum_accepted_per_window,
            )
        )
    results.append(
        run_benchmark(
            workload,
            pipeline_enabled=True,
            workers=args.workers,
            detail_workers=args.detail_workers,
            warm_cache=args.warm_cache,
            profile=args.profile,
            owner=args.owner,
            revision=args.revision,
            approval_status=args.approval_status,
            timeout_seconds=args.timeout,
            accepted_source=args.accepted_source,
            thresholds_override=thresholds_override,
            minimum_accepted_per_window=args.minimum_accepted_per_window,
        )
    )
    report = {
        "version": "linkedin-pipeline-benchmark-v3",
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "contract": {
            "name": BENCHMARK_CONTRACT,
            "contract_revision": BENCHMARK_REVISION,
            "benchmark_revision": args.revision,
            "source": BENCHMARK_SOURCE,
            "window_seconds": BENCHMARK_WINDOW_SECONDS,
            "profile": args.profile,
            "owner": args.owner,
            "revision": args.revision,
            "approval": args.approval_status,
            "accepted_source": args.accepted_source,
            "minimum_accepted_per_window": args.minimum_accepted_per_window,
            "ceilings": BENCHMARK_PROFILES[args.profile],
            "threshold_overrides": thresholds_override or {},
        },
        "results": results,
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if all(result["benchmark_contract"]["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
