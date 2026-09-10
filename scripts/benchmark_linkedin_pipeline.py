"""Offline LinkedIn producer pipeline benchmark.

This benchmark runs the actual ``scripts/master_linkedin_jobs_catalog.py``
producer against synthetic fixtures with artificial network latency.  It is
designed to compare the sequential baseline and the pipelined optimizer while
consuming no paid provider credits.
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
from typing import Any, Callable

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
            pipeline_enabled=pipeline_enabled,
        )
        runner = CatalogRunner(config, transport=transport)
        started = time.perf_counter()
        started_cpu = time.process_time()
        metrics = runner.run()
        wall_time = time.perf_counter() - started
        cpu_time = time.process_time() - started_cpu
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
            "peak_rss_bytes": _peak_rss_bytes(),
            "requests": metrics.get("requests", 0),
            "detail_requests": metrics.get("detail_requests", 0),
            "detail_cache_hits": metrics.get("detail_cache_hits", 0),
            "detail_successes": metrics.get("detail_successes", 0),
            "jobs_written": metrics.get("jobs_written", 0),
            "companies_completed": metrics.get("companies_completed", 0),
            "companies_partial": metrics.get("companies_partial", 0),
            "run_outcome": metrics.get("run_outcome"),
            "transport_peak_in_flight": transport.peak_in_flight,
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
    parser.add_argument("--output", type=Path, help="write JSON report to this path")
    args = parser.parse_args(argv)
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
            )
        )
    results.append(
        run_benchmark(
            workload,
            pipeline_enabled=True,
            workers=args.workers,
            detail_workers=args.detail_workers,
            warm_cache=args.warm_cache,
        )
    )
    report = {
        "version": "linkedin-pipeline-benchmark-v1",
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "results": results,
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
