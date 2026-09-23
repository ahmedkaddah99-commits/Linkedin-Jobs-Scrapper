"""Run the employer collector through an RC-005 eligibility manifest."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.application.source_eligibility_manifest import (
    SOURCE_EMPLOYER,
    materialize_source_input,
    require_eligibility_manifest,
)
from backend.connectors.company_career_discovery import (
    FetchResult,
    detect_ats_type,
    discover_career_url,
)
from backend.connectors.employer_site_fallbacks import (
    extract_embedded_jobs,
    extract_payload_jobs,
)
from scripts.benchmark_linkedin_pipeline import (
    BENCHMARK_OWNER,
    BENCHMARK_PROFILES,
    BENCHMARK_REVISION,
    BENCHMARK_WINDOW_SECONDS,
    evaluate_benchmark_contract,
)
from scripts.master_employer_jobs_catalog import (
    _atomic_write,
    _first_value,
    _is_accepted_job_page,
    _text,
    classify_germany,
    load_employer_companies,
    run_collection,
)

DEFAULT_DRY_RUN_MINUTES = 5
FAILED_COMPANY_STATUSES = frozenset({"failed", "discovery_failed", "source_failed", "collector_error"})

EMPLOYER_BENCHMARK_REVISION = "T38"
EMPLOYER_BENCHMARK_SOURCE = "employer"
EMPLOYER_BENCHMARK_RECEIPT_NAME = "employer_benchmark_receipt.json"
EMPLOYER_FIXTURE_BENCHMARK_RECEIPT_NAME = "employer_fixture_benchmark_receipt.json"
DEFAULT_PER_HOST_REQUESTS = 10
DEFAULT_FIXTURE_PER_HOST_REQUESTS = 25
LOW_YIELD_CLASSES = ("data_quality", "missing_url", "provider_blocking", "code_failure")
BENCHMARK_STAGE_NAMES = (
    "career_discovery",
    "ats_routing",
    "parsing",
    "identity",
    "completeness",
    "dedupe",
    "delivery",
)
MISSING_URL_DISCOVERY_REASONS = frozenset(
    {
        "career_url_found_failure",
        "invalid_homepage_or_domain",
        "missing_homepage_or_domain",
        "no_career_target_found",
        "no_target_found",
        "unsafe_homepage",
    }
)
PROVIDER_BLOCKING_MARKERS = (
    "403",
    "429",
    "access denied",
    "blocked",
    "captcha",
    "challenge",
    "forbidden",
    "rate limit",
    "timeout",
)
CODE_FAILURE_MARKERS = (
    "collector_error",
    "parser_failure",
    "request_budget_exhausted",
    "per_host_limit_exceeded",
)
NEUTRAL_DISCOVERY_REASONS = frozenset(
    {
        "career_url_found",
        "found",
        "low_confidence",
        "not_observed",
    }
)
NEUTRAL_STOP_REASONS = frozenset(
    {
        "collection_completed",
        "completed",
        "complete",
        "pagination_complete",
        "rendered_page_complete",
    }
)


class EmployerPerHostBudgetExceeded(RuntimeError):
    """Raised before dispatch when one host exceeds its benchmark ceiling."""

    def __init__(self, host: str, max_requests_per_host: int) -> None:
        super().__init__(f"per_host_limit_exceeded:{host}:{max_requests_per_host}")
        self.host = host
        self.max_requests_per_host = max_requests_per_host


class PerHostRequestBudget:
    """Thread-safe per-host admission ceiling shared by benchmark fetchers.

    ``enforce=False`` turns the budget into an observer that still records
    per-host attempts and reports exceeded hosts without aborting discovery.
    """

    def __init__(self, max_requests_per_host: int, *, enforce: bool = True) -> None:
        self._lock = threading.Lock()
        self._max_requests_per_host = max(1, int(max_requests_per_host))
        self._enforce = bool(enforce)
        self._counts: dict[str, int] = {}

    @property
    def max_requests_per_host(self) -> int:
        return self._max_requests_per_host

    @property
    def enforced(self) -> bool:
        return self._enforce

    def admit(self, url: str) -> str:
        host = (urlsplit(str(url)).hostname or "").casefold() or "unknown"
        with self._lock:
            count = self._counts.get(host, 0)
            if self._enforce and count >= self._max_requests_per_host:
                raise EmployerPerHostBudgetExceeded(host, self._max_requests_per_host)
            self._counts[host] = count + 1
        return host

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(sorted(self._counts.items()))

    def exceeded_hosts(self) -> list[str]:
        with self._lock:
            return sorted(
                host for host, count in self._counts.items() if count > self._max_requests_per_host
            )


def build_dry_run_receipt(
    *,
    manifest: Mapping[str, Any],
    staged_input: Path,
    output_dir: Path,
    state_dir: Path | None,
    pilot_only: bool,
    duration_budget_seconds: int = DEFAULT_DRY_RUN_MINUTES * 60,
) -> dict[str, Any]:
    """Aggregate a bounded, read-only job-outcome receipt without collection.

    Reads the staged manifest cohort plus the durable employer state (never
    mutating either) and classifies every durable job row for the cohort into
    discovered / accepted / rejected / deduplicated / failed counts. The
    aggregation stops at ``duration_budget_seconds`` so the receipt always
    completes within its five-minute default budget.
    """

    started = time.monotonic()
    deadline = started + max(1, int(duration_budget_seconds))
    staged_input_present = Path(staged_input).is_file()
    companies: list[Any] = []
    load_stats: dict[str, int] = {}
    cohort_keys: set[str] = set()
    if staged_input_present:
        companies, load_stats = load_employer_companies(Path(staged_input))
        cohort_keys = {
            company.canonical_company_id or company.website_url for company in companies
        }
    state_path = (Path(state_dir) if state_dir is not None else output_dir) / "master_employer_jobs_state.db"
    counts = {
        "discovered": 0,
        "accepted": 0,
        "rejected": 0,
        "deduplicated": 0,
        "failed": 0,
    }
    state_present = state_path.is_file()
    company_status_counts: dict[str, int] = {}
    truncated = False
    if state_present:
        from scripts.master_employer_jobs_catalog import EmployerState

        state = EmployerState.open_existing(state_path)
        try:
            seen_identities: set[tuple[str, str, str, str]] = set()
            failed_companies = {
                company.canonical_company_id or company.website_url
                for company in companies
                if state.company_status(company) in FAILED_COMPANY_STATUSES
            }
            for company in companies:
                status = state.company_status(company)
                if status:
                    company_status_counts[status] = company_status_counts.get(status, 0) + 1
            for job in state.iter_jobs():
                if time.monotonic() >= deadline:
                    truncated = True
                    break
                company_id = _text(job.get("canonical_company_id"))
                if company_id and company_id not in cohort_keys:
                    continue
                counts["discovered"] += 1
                # Durable state already dedupes exact (company, provider,
                # tenant, identity) keys; this receipt-level identity instead
                # counts cross-provider/cross-tenant duplicates of the same
                # posting URL for one company. Rows without a URL dedupe by
                # their source job ID.
                job_url = _text(job.get("source_job_url"))
                if job_url:
                    normalized = (urlsplit(job_url).path or job_url).rstrip("/").casefold()
                    identity = (company_id, "url", normalized)
                else:
                    identity = (company_id, "id", _text(job.get("source_job_id")))
                if identity in seen_identities:
                    counts["deduplicated"] += 1
                    continue
                seen_identities.add(identity)
                provider = _text(job.get("source_provider"))
                if company_id in failed_companies:
                    counts["failed"] += 1
                elif _is_accepted_job_page(job, provider):
                    counts["accepted"] += 1
                else:
                    counts["rejected"] += 1
        finally:
            state.close()
    elapsed = time.monotonic() - started
    receipt: dict[str, Any] = {
        "mode": "dry_run",
        "dry_run": True,
        "eligibility_manifest_id": manifest.get("manifest_id", ""),
        "eligibility_manifest_hash": manifest.get("manifest_hash", ""),
        "pilot_only": pilot_only,
        "cohort_companies": len(companies),
        "cohort_duplicate_rows": load_stats.get("duplicate_rows", 0),
        "staged_input_present": staged_input_present,
        "state_path": str(state_path),
        "state_present": state_present,
        "job_receipt": counts,
        "company_status_counts": company_status_counts,
        "duration_budget_seconds": int(duration_budget_seconds),
        "elapsed_seconds": round(elapsed, 3),
        "duration_budget_exhausted": truncated,
        "truncated": truncated,
        "eligibility_source": SOURCE_EMPLOYER,
        "manifest_input": str(staged_input),
    }
    receipt_path = Path(output_dir) / "employer_dry_run_receipt.json"
    receipt["receipt_path"] = str(receipt_path)
    _atomic_write(receipt_path, lambda target: target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"))
    return receipt


def _peak_rss_bytes() -> int | None:
    if os.name == "nt":
        import ctypes
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

        try:
            counters = Counters()
            counters.cb = ctypes.sizeof(Counters)
            get_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
            get_memory_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
            get_memory_info.restype = wintypes.BOOL
            process = ctypes.windll.kernel32.GetCurrentProcess()
            ok = get_memory_info(process, ctypes.byref(counters), ctypes.sizeof(counters))
            return int(counters.PeakWorkingSetSize) if ok else None
        except (AttributeError, OSError, ValueError):
            return None
    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value * 1024
    except (ImportError, AttributeError):
        return None


def _is_provider_blocking_reason(reason: str) -> bool:
    lowered = str(reason or "").casefold()
    return any(marker in lowered for marker in PROVIDER_BLOCKING_MARKERS)


def _is_code_failure_reason(reason: str) -> bool:
    lowered = str(reason or "").casefold()
    return any(marker in lowered for marker in CODE_FAILURE_MARKERS)


def attribute_low_yield(
    *,
    discovery_reason_codes: Mapping[str, int] | None = None,
    target_stop_reasons: Mapping[str, int] | None = None,
    company_status_counts: Mapping[str, int] | None = None,
    jobs_missing_title: int = 0,
    jobs_missing_location: int = 0,
    jobs_missing_target_url: int = 0,
) -> dict[str, Any]:
    """Attribute employer yield loss to data quality, missing URLs, provider blocking, or code failure.

    Every signal is counted into exactly one deterministic class so a low
    accepted-jobs rate is explainable instead of anonymous. Job-level quality
    signals (missing title, ambiguous location, missing target URL) dominate
    over company-level status classes because they describe the rows that were
    actually rejected.
    """

    classes: dict[str, int] = {name: 0 for name in LOW_YIELD_CLASSES}
    reason_codes: dict[str, list[str]] = {name: [] for name in LOW_YIELD_CLASSES}

    def add(class_name: str, reason: str) -> None:
        classes[class_name] += 1
        if reason not in reason_codes[class_name]:
            reason_codes[class_name].append(reason)

    for status, count in sorted((company_status_counts or {}).items()):
        if status not in FAILED_COMPANY_STATUSES and status != "blocked" and not _is_provider_blocking_reason(status):
            continue
        for _ in range(max(0, int(count))):
            if status == "collector_error" or _is_code_failure_reason(status):
                add("code_failure", f"company_status:{status}")
            elif status == "discovery_failed":
                add("missing_url", f"company_status:{status}")
            elif _is_provider_blocking_reason(status) or status in {"source_failed", "failed"}:
                add("provider_blocking", f"company_status:{status}")
            else:
                add("data_quality", f"company_status:{status}")
    for reason, count in sorted((discovery_reason_codes or {}).items()):
        if reason in NEUTRAL_DISCOVERY_REASONS:
            continue
        for _ in range(max(0, int(count))):
            if reason in MISSING_URL_DISCOVERY_REASONS:
                add("missing_url", f"discovery:{reason}")
            elif _is_provider_blocking_reason(reason):
                add("provider_blocking", f"discovery:{reason}")
            else:
                add("code_failure", f"discovery:{reason}")
    for reason, count in sorted((target_stop_reasons or {}).items()):
        if reason in NEUTRAL_STOP_REASONS:
            continue
        for _ in range(max(0, int(count))):
            if _is_provider_blocking_reason(reason):
                add("provider_blocking", f"target:{reason}")
            else:
                add("code_failure", f"target:{reason}")
    for _ in range(max(0, int(jobs_missing_title))):
        add("data_quality", "job:title_missing")
    for _ in range(max(0, int(jobs_missing_location))):
        add("data_quality", "job:location_missing_or_ambiguous")
    for _ in range(max(0, int(jobs_missing_target_url))):
        add("missing_url", "job:target_url_missing")
    return {
        "classes": classes,
        "reason_codes": {name: sorted(reasons) for name, reasons in reason_codes.items() if reasons},
        "attributed": any(classes.values()),
    }


def _fixture_homepage_html(slug: str, *, with_careers: bool = True, with_ats: bool = True) -> str:
    links = []
    if with_careers:
        links.append('<a href="/careers">Careers</a>')
    if with_ats:
        links.append(f'<a href="https://boards.greenhouse.io/{slug}">Jobs on Greenhouse</a>')
    links.append('<a href="/privacy">Privacy</a>')
    return f"<!DOCTYPE html><html><body>{''.join(links)}</body></html>"


def _fixture_site_job(slug: str, index: int, *, location: str = "Berlin, Germany") -> dict[str, Any]:
    return {
        "id": f"site-{slug}-{index}",
        "title": f"Site Engineer {index}",
        "url": f"/jobs/{slug}-site-{index}",
        "location": location,
        "description": "Fixture role for the employer five-minute benchmark.",
    }


def _fixture_ats_job(slug: str, index: int, *, location: str = "Berlin, Germany", absolute_url: str = "") -> dict[str, Any]:
    return {
        "id": f"gh-{slug}-{index}",
        "title": f"ATS Engineer {index}",
        "absolute_url": absolute_url or f"https://boards.greenhouse.io/{slug}/jobs/{index}",
        "content": "Fixture ATS role for the employer five-minute benchmark.",
        "location": {"name": location},
    }


def _fixture_careers_html(jobs: list[Mapping[str, Any]]) -> str:
    payload = json.dumps({"jobs": list(jobs)}, ensure_ascii=False)
    return (
        '<!DOCTYPE html><html><body><script type="application/json">'
        f"{payload}</script></body></html>"
    )


def _fixture_fetcher(
    slug: str, budget: PerHostRequestBudget, homepage_html: str, careers_html: str, ats_payload: str
):
    careers_host = f"{slug}.example"

    def fetch(url: str) -> FetchResult:
        budget.admit(url)
        parsed = urlsplit(url)
        host = (parsed.hostname or "").casefold()
        path = parsed.path or "/"
        if host == careers_host and path in ("", "/") and homepage_html:
            return FetchResult(url, url, 200, "text/html", homepage_html)
        if host == careers_host and path == "/careers" and careers_html:
            return FetchResult(url, url, 200, "text/html", careers_html)
        if host == "boards.greenhouse.io" and path == f"/{slug}" and ats_payload:
            return FetchResult(url, url, 200, "application/json", ats_payload)
        return FetchResult(url, url, 404, "", "")

    return fetch


def run_employer_fixture_benchmark(
    *,
    output_dir: Path,
    profile: str = "local-dry-run",
    accepted_source: str = "",
    approval_status: str = "not-required",
    per_host_requests: int = DEFAULT_FIXTURE_PER_HOST_REQUESTS,
    window_seconds: int = BENCHMARK_WINDOW_SECONDS,
    revision: str = EMPLOYER_BENCHMARK_REVISION,
    owner: str = BENCHMARK_OWNER,
    eligibility_manifest_id: str = "",
) -> dict[str, Any]:
    """Run the offline, bounded employer five-minute fixture benchmark.

    Four deterministic fixture employers drive the real career-discovery,
    ATS-routing, parsing, identity, completeness, dedupe, and delivery stages
    with no network access: every fetch is answered from canned fixture pages
    through an injected fetcher whose per-host attempts honor
    ``PerHostRequestBudget``. The measured lifecycle counts are evaluated
    against the shared five-minute producer contract.
    """

    started = time.monotonic()
    stage_timings: dict[str, float] = {}
    stage_last = time.monotonic()

    def mark_stage(name: str) -> None:
        nonlocal stage_last
        now = time.monotonic()
        stage_timings[name] = round(max(0.0, now - stage_last), 6)
        stage_last = now

    company_scenarios = (
        ("acme-full", {"with_careers": True, "with_ats": True}),
        ("beta-site", {"with_careers": True, "with_ats": False}),
        ("gamma-none", {"with_careers": False, "with_ats": False}),
        ("delta-quality", {"with_careers": True, "with_ats": False, "missing_location": True}),
    )
    budget = PerHostRequestBudget(per_host_requests, enforce=True)
    discovery_results: dict[str, Any] = {}
    discovery_failures = 0
    for slug, scenario in company_scenarios:
        homepage_html = _fixture_homepage_html(
            slug,
            with_careers=scenario["with_careers"],
            with_ats=scenario["with_ats"],
        )
        site_jobs: list[dict[str, Any]] = []
        if scenario["with_careers"]:
            site_jobs = [
                _fixture_site_job(
                    slug,
                    index,
                    location="" if scenario.get("missing_location") else "Berlin, Germany",
                )
                for index in range(1, 4)
            ]
        ats_jobs: list[dict[str, Any]] = []
        if scenario["with_ats"]:
            ats_jobs = [
                _fixture_ats_job(
                    slug,
                    index,
                    absolute_url=f"https://{slug}.example/jobs/{slug}-site-1" if index == 1 else "",
                )
                for index in range(1, 4)
            ]
        careers_html = _fixture_careers_html(site_jobs) if site_jobs else ""
        ats_payload = json.dumps({"jobs": ats_jobs}, ensure_ascii=False) if ats_jobs else ""
        fetcher = _fixture_fetcher(slug, budget, homepage_html, careers_html, ats_payload)
        try:
            discovery_results[slug] = {
                "scenario": scenario,
                "site_jobs": site_jobs,
                "ats_jobs": ats_jobs,
                "discovery": discover_career_url(
                    homepage_url=f"https://{slug}.example",
                    company_name=slug,
                    fetch=fetcher,
                    shallow_crawl_pages=0,
                    request_timeout_seconds=5,
                ),
            }
        except Exception:
            discovery_failures += 1
    mark_stage("career_discovery")

    routed_candidates = 0
    for fixture in discovery_results.values():
        for candidate in fixture["discovery"].candidates:
            if detect_ats_type(candidate.url):
                routed_candidates += 1
    mark_stage("ats_routing")

    parsed_rows: dict[str, list[dict[str, Any]]] = {}
    parse_failures = 0
    for slug, fixture in discovery_results.items():
        rows: list[dict[str, Any]] = []
        scenario = fixture["scenario"]
        if scenario["with_ats"]:
            try:
                rows.extend(
                    extract_payload_jobs(
                        {"jobs": fixture["ats_jobs"]},
                        f"https://boards.greenhouse.io/{slug}",
                        format_name="ats_api",
                        source_endpoint=f"https://boards.greenhouse.io/{slug}",
                    )
                )
            except Exception:
                parse_failures += 1
        if scenario["with_careers"]:
            try:
                rows.extend(
                    extract_embedded_jobs(
                        _fixture_careers_html(fixture["site_jobs"]),
                        f"https://{slug}.example/careers",
                    )
                )
            except Exception:
                parse_failures += 1
        annotated: list[dict[str, Any]] = []
        for row in rows:
            normalized = dict(row)
            normalized["source_raw_payload"] = {"format": "embedded-json"}
            hostname = (urlsplit(str(row.get("job_detail_url") or "")).hostname or "").casefold()
            normalized["source_provider"] = "greenhouse" if "greenhouse" in hostname else "generic"
            normalized["canonical_company_id"] = slug
            normalized["source_job_id"] = _text(row.get("job_id"))
            normalized["source_job_url"] = _text(row.get("job_detail_url"))
            annotated.append(normalized)
        parsed_rows[slug] = annotated
    mark_stage("parsing")

    classified = 0
    germany_eligible = 0
    jobs_missing_location = 0
    jobs_missing_title = 0
    complete_rows: list[dict[str, Any]] = []
    for rows in parsed_rows.values():
        for row in rows:
            classified += 1
            title = _text(row.get("title"))
            if not title:
                jobs_missing_title += 1
            location = _text(row.get("location"))
            classification, evidence = classify_germany(location)
            if classification == "LOCATION_AMBIGUOUS":
                jobs_missing_location += 1
            else:
                germany_eligible += 1
            detail_url = _text(row.get("job_detail_url"))
            if title and detail_url and classification != "LOCATION_AMBIGUOUS":
                complete_rows.append(row)
    mark_stage("identity")

    complete_count = len(complete_rows)
    mark_stage("completeness")

    union_rows: list[dict[str, Any]] = []
    duplicate_count = 0
    seen_union: set[tuple[str, str]] = set()
    for slug, rows in parsed_rows.items():
        for row in rows:
            detail_url = _text(row.get("job_detail_url"))
            identity = (slug, (urlsplit(detail_url).path or detail_url).rstrip("/").casefold())
            if identity in seen_union:
                duplicate_count += 1
                continue
            seen_union.add(identity)
            union_rows.append(dict(row, canonical_company_id=slug))
    mark_stage("dedupe")

    accepted_identities: set[tuple[str, str]] = set()
    accepted_count = 0
    for row in complete_rows:
        provider = _text(row.get("source_provider"))
        if _is_accepted_job_page(row, provider):
            accepted_count += 1
            detail_url = _text(row.get("job_detail_url"))
            accepted_identities.add(
                (
                    _text(row.get("canonical_company_id")),
                    (urlsplit(detail_url).path or detail_url).rstrip("/").casefold(),
                )
            )
    published_count = 0
    with tempfile.TemporaryDirectory(prefix="runr-t38-benchmark-") as delivery_dir:
        from scripts.master_employer_jobs_catalog import EmployerCollectionResult, EmployerCompany, EmployerState, export_catalogs_from_state

        state = EmployerState(Path(delivery_dir) / "master_employer_jobs_state.db")
        try:
            for slug, scenario in ((slug, dict(scenario)) for slug, scenario in company_scenarios):
                company = EmployerCompany(
                    canonical_company_id=slug,
                    company_name=slug,
                    website_url=f"https://{slug}.example",
                )
                jobs = [row for row in union_rows if _text(row.get("canonical_company_id")) == slug]
                if jobs:
                    result = EmployerCollectionResult(
                        company=company,
                        jobs=jobs,
                        status="completed",
                        outcome="complete_with_jobs",
                    )
                else:
                    result = EmployerCollectionResult(
                        company=company,
                        status="no_jobs",
                        outcome="confirmed_zero",
                    )
                state.save(result)
                for row in jobs:
                    provider = _text(row.get("source_provider"))
                    identity = (
                        slug,
                        (urlsplit(_text(row.get("job_detail_url"))).path or _text(row.get("job_detail_url"))).rstrip("/").casefold(),
                    )
                    if identity in accepted_identities:
                        published_count += 1
            export_metrics = export_catalogs_from_state(
                state,
                Path(delivery_dir) / "export",
                metrics={"persisted_jobs": len(union_rows), "exported_jobs": len(union_rows)},
            )
        finally:
            state.close()
    exported_count = int(export_metrics.get("exported_jobs", 0) or 0)
    published_count = min(published_count, accepted_count, exported_count) if exported_count else 0
    mark_stage("delivery")

    elapsed = max(0.0001, time.monotonic() - started)
    counts = {
        "discovered": sum(len(rows) for rows in parsed_rows.values()),
        "parsed": sum(len(rows) for rows in parsed_rows.values()),
        "complete": complete_count,
        "accepted": accepted_count,
        "published": published_count,
        "duplicate": duplicate_count,
        "failed": discovery_failures + parse_failures,
    }
    cpu_seconds = round(time.process_time(), 4)
    rss_bytes = _peak_rss_bytes()
    evaluation = evaluate_benchmark_contract(
        profile=profile,
        counts=counts,
        elapsed_seconds=elapsed,
        cpu_seconds=cpu_seconds,
        rss_bytes=rss_bytes,
        browser_requests=0,
        requests=sum(budget.snapshot().values()),
        concurrency=1,
        timeout_seconds=5.0,
        accepted_source=accepted_source or None,
        approval_status=approval_status,
        revision=revision,
        owner=owner,
    )
    attribution = attribute_low_yield(
        discovery_reason_codes=_discovery_reason_counts(discovery_results),
        jobs_missing_title=jobs_missing_title,
        jobs_missing_location=jobs_missing_location,
    )
    counts = dict(evaluation["counts"])
    stages = {
        name: {
            "elapsed_seconds": stage_timings.get(name, 0.0),
        }
        for name in BENCHMARK_STAGE_NAMES
    }
    stages["career_discovery"]["employers"] = len(company_scenarios)
    stages["career_discovery"]["discovery_failures"] = discovery_failures
    stages["ats_routing"]["routed_ats_candidates"] = routed_candidates
    stages["parsing"]["parse_failures"] = parse_failures
    stages["identity"]["classified_rows"] = classified
    stages["identity"]["germany_eligible_rows"] = germany_eligible
    stages["completeness"]["complete_rows"] = complete_count
    stages["dedupe"]["union_rows"] = len(union_rows)
    stages["dedupe"]["duplicates_removed"] = duplicate_count
    stages["delivery"]["persisted_rows"] = len(union_rows)
    stages["delivery"]["exported_rows"] = exported_count
    stages["delivery"]["published_rows"] = published_count
    receipt: dict[str, Any] = {
        "mode": "fixture_benchmark",
        "benchmark_revision": revision,
        "source": EMPLOYER_BENCHMARK_SOURCE,
        "window_seconds": int(window_seconds),
        "profile": profile,
        "owner": owner,
        "stages": stages,
        "per_host_limits": {
            "max_requests_per_host": budget.max_requests_per_host,
            "enforced": budget.enforced,
        },
        "per_host_observed": budget.snapshot(),
        "per_host_exceeded": budget.exceeded_hosts(),
        "counts": counts,
        "low_yield_attribution": attribution,
        "contract_evaluation": evaluation,
        "eligibility_manifest_id": eligibility_manifest_id,
        "receipt_path": "",
    }
    receipt["elapsed_seconds"] = round(elapsed, 4)
    receipt_path = Path(output_dir) / EMPLOYER_FIXTURE_BENCHMARK_RECEIPT_NAME
    receipt["receipt_path"] = str(receipt_path)
    _atomic_write(
        receipt_path,
        lambda target: target.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        ),
    )
    return receipt


def _discovery_reason_counts(discovery_results: Mapping[str, Any]) -> dict[str, int]:
    reasons: dict[str, int] = {}
    for fixture in discovery_results.values():
        result = fixture["discovery"]
        reason = str(getattr(result, "reason_code", "") or getattr(result, "crawl_status", ""))
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
    return reasons


def _scan_benchmark_lifecycle(
    *,
    staged_input: Path,
    state_path: Path,
    deadline: float,
) -> dict[str, Any]:
    """Bounded durable-state scan producing employer lifecycle and attribution signals."""

    from scripts.master_employer_jobs_catalog import EmployerState

    scan: dict[str, Any] = {
        "counts": {
            "discovered": 0,
            "parsed": 0,
            "complete": 0,
            "accepted": 0,
            "published": 0,
            "duplicate": 0,
            "failed": 0,
        },
        "company_status_counts": {},
        "discovery_reason_codes": {},
        "target_stop_reasons": {},
        "jobs_missing_title": 0,
        "jobs_missing_location": 0,
        "jobs_missing_target_url": 0,
        "truncated": False,
    }
    staged_input_present = Path(staged_input).is_file()
    scan["staged_input_present"] = staged_input_present
    companies: list[Any] = []
    if staged_input_present:
        companies, _load_stats = load_employer_companies(Path(staged_input))
    scan["cohort_companies"] = len(companies)
    cohort_keys = {
        company.canonical_company_id or company.website_url for company in companies
    }
    state_present = state_path.is_file()
    scan["state_present"] = state_present
    if not state_present:
        return scan
    state = EmployerState.open_existing(state_path)
    try:
        company_status_counts: dict[str, int] = {}
        for company in companies:
            status = state.company_status(company)
            if status:
                company_status_counts[status] = company_status_counts.get(status, 0) + 1
        scan["company_status_counts"] = company_status_counts
        for company in companies:
            receipt = state.coverage_receipt(company)
            if receipt is None:
                continue
            classification = str(receipt.terminal_classification or "")
            if classification == "blocked":
                scan["target_stop_reasons"]["blocked"] = (
                    scan["target_stop_reasons"].get("blocked", 0) + 1
                )
            for attempt in receipt.attempts:
                stop_reason = _text(getattr(attempt, "stop_reason", ""))
                if stop_reason:
                    scan["target_stop_reasons"][stop_reason] = (
                        scan["target_stop_reasons"].get(stop_reason, 0) + 1
                    )
            for entry in receipt.source_inventory:
                deferred = _text(entry.get("deferred_reason"))
                if deferred:
                    scan["target_stop_reasons"][deferred] = (
                        scan["target_stop_reasons"].get(deferred, 0) + 1
                    )
        seen_identities: set[tuple[str, str, str]] = set()
        failed_companies = {
            company.canonical_company_id or company.website_url
            for company in companies
            if state.company_status(company) in FAILED_COMPANY_STATUSES
        }
        counts = scan["counts"]
        for job in state.iter_jobs():
            if time.monotonic() >= deadline:
                scan["truncated"] = True
                break
            company_id = _text(job.get("canonical_company_id"))
            if company_id and company_id not in cohort_keys:
                continue
            counts["discovered"] += 1
            job_url = _text(job.get("source_job_url"))
            if job_url:
                normalized = (urlsplit(job_url).path or job_url).rstrip("/").casefold()
                identity = (company_id, "url", normalized)
            else:
                identity = (company_id, "id", _text(job.get("source_job_id")))
            if identity in seen_identities:
                counts["duplicate"] += 1
                continue
            seen_identities.add(identity)
            title = _first_value(job, ("job_title", "title"))
            if not _text(title):
                scan["jobs_missing_title"] += 1
                counts["failed"] += 1
                continue
            counts["parsed"] += 1
            detail_url = _text(job.get("source_job_url")) or _text(job.get("apply_url_canonical"))
            location = _text(_first_value(job, ("location", "location_raw")))
            if location:
                classification, _evidence = classify_germany(location)
            else:
                classification = str(_text(job.get("germany_classification")) or "LOCATION_AMBIGUOUS")
            if classification == "LOCATION_AMBIGUOUS":
                scan["jobs_missing_location"] += 1
                counts["failed"] += 1
                continue
            if not detail_url and not _text(job.get("source_job_id")):
                scan["jobs_missing_target_url"] += 1
                counts["failed"] += 1
                continue
            counts["complete"] += 1
            provider = _text(job.get("source_provider"))
            if company_id in failed_companies:
                counts["failed"] += 1
            elif _is_accepted_job_page(job, provider):
                counts["accepted"] += 1
    finally:
        state.close()
    return scan


def build_employer_benchmark_receipt(
    *,
    mode: str,
    metrics: Mapping[str, Any],
    manifest: Mapping[str, Any],
    staged_input: Path,
    output_dir: Path,
    state_dir: Path | None,
    profile: str,
    accepted_source: str,
    approval_status: str,
    per_host_requests: int,
    window_seconds: int,
    elapsed_seconds: float,
    timeout_seconds: float = 30.0,
    revision: str = EMPLOYER_BENCHMARK_REVISION,
    owner: str = BENCHMARK_OWNER,
) -> dict[str, Any]:
    """Evaluate one employer run against the shared five-minute producer contract.

    The durable cohort state (never mutated) supplies the lifecycle counts and
    the low-yield attribution; the run metrics supply the transport accounting
    (per-host attempts, browser requests, concurrency). The receipt is written
    atomically next to the other employer artifacts.
    """

    state_path = (Path(state_dir) if state_dir is not None else Path(output_dir)) / "master_employer_jobs_state.db"
    scan = _scan_benchmark_lifecycle(
        staged_input=staged_input,
        state_path=state_path,
        deadline=time.monotonic() + max(1, int(window_seconds)),
    )
    accounting = dict(metrics.get("request_accounting") or {})
    concurrency_info = dict(metrics.get("concurrency") or {})
    cpu_seconds = round(time.process_time(), 4)
    rss_bytes = _peak_rss_bytes()
    counts = dict(scan["counts"])
    published_override = metrics.get("exported_jobs")
    if published_override is not None:
        counts["published"] = min(int(published_override or 0), counts["accepted"])
    evaluation = evaluate_benchmark_contract(
        profile=profile,
        counts=counts,
        elapsed_seconds=max(0.0001, float(elapsed_seconds)),
        cpu_seconds=cpu_seconds,
        rss_bytes=rss_bytes,
        browser_requests=int(accounting.get("browser_navigations", 0) or 0),
        requests=int(accounting.get("total_attempts", 0) or 0),
        concurrency=int(concurrency_info.get("company_workers", 1) or 1),
        timeout_seconds=float(timeout_seconds),
        accepted_source=accepted_source or None,
        approval_status=approval_status,
        revision=revision,
        owner=owner,
    )
    attribution = attribute_low_yield(
        discovery_reason_codes=scan["discovery_reason_codes"],
        target_stop_reasons=scan["target_stop_reasons"],
        company_status_counts=scan["company_status_counts"],
        jobs_missing_title=scan["jobs_missing_title"],
        jobs_missing_location=scan["jobs_missing_location"],
        jobs_missing_target_url=scan["jobs_missing_target_url"],
    )
    counts = dict(evaluation["counts"])
    per_host_observed = {
        str(host): int(count)
        for host, count in sorted((accounting.get("by_origin") or {}).items())
    }
    receipt: dict[str, Any] = {
        "mode": mode,
        "benchmark_revision": revision,
        "source": EMPLOYER_BENCHMARK_SOURCE,
        "window_seconds": int(window_seconds),
        "elapsed_seconds": round(max(0.0, float(elapsed_seconds)), 4),
        "profile": profile,
        "owner": owner,
        "eligibility_manifest_id": manifest.get("manifest_id", ""),
        "eligibility_manifest_hash": manifest.get("manifest_hash", ""),
        "pilot_only": bool(metrics.get("pilot_only", True)),
        "cohort_companies": scan.get("cohort_companies", 0),
        "staged_input_present": scan.get("staged_input_present", False),
        "state_present": scan.get("state_present", False),
        "truncated": scan.get("truncated", False),
        "counts": counts,
        "company_status_counts": scan["company_status_counts"],
        "per_host_limits": {
            "max_requests_per_host": max(1, int(per_host_requests)),
            "enforced": False,
        },
        "per_host_observed": per_host_observed,
        "per_host_exceeded": sorted(
            host
            for host, count in per_host_observed.items()
            if count > max(1, int(per_host_requests))
        ),
        "resource_peaks": {"max_rss_bytes": rss_bytes, "cpu_seconds": cpu_seconds},
        "low_yield_attribution": attribution,
        "contract_evaluation": evaluation,
        "receipt_path": "",
    }
    receipt_path = Path(output_dir) / EMPLOYER_BENCHMARK_RECEIPT_NAME
    receipt["receipt_path"] = str(receipt_path)
    _atomic_write(
        receipt_path,
        lambda target: target.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        ),
    )
    return receipt


TELEMETRY_SCHEMA_VERSION = "runr.producer.telemetry.v1"
TELEMETRY_KEYS = frozenset(
    {"schema_version", "source", "emitted_at", "source_version", "resource_peaks", "reason_code"}
)
RESOURCE_PEAK_KEYS = frozenset({"max_rss_bytes", "cpu_seconds"})


def _resource_peaks() -> dict[str, float | int | None]:
    peaks: dict[str, float | int | None] = {"max_rss_bytes": None, "cpu_seconds": None}
    try:
        import resource
    except ImportError:
        return peaks
    usage = resource.getrusage(resource.RUSAGE_SELF)
    if usage.ru_maxrss:
        peaks["max_rss_bytes"] = int(usage.ru_maxrss) * 1024
    peaks["cpu_seconds"] = round(float(usage.ru_utime) + float(usage.ru_stime), 3)
    return peaks


def _telemetry(source: str) -> dict[str, object]:
    return {
        "schema_version": TELEMETRY_SCHEMA_VERSION,
        "source": source,
        "emitted_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "source_version": os.environ.get("RUNR_SOURCE_VERSION", ""),
        "resource_peaks": _resource_peaks(),
        "reason_code": "ok",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--state-dir",
        type=Path,
        help="directory containing the durable SQLite state; defaults to --output-dir",
    )
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--full", action="store_true")
    parser.add_argument(
        "--include-single-source",
        action="store_true",
        help="opt into website-only/LinkedIn-only expansion tasks; default is the dual-source pilot",
    )
    parser.add_argument("--company-id", default="")
    parser.add_argument("--company-ids", nargs="+", help="exact eligible canonical IDs for a bounded cohort")
    parser.add_argument("--max-job-links", type=int, default=25)
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--max-browser-requests", type=int, default=10)
    parser.add_argument("--max-targets", type=int, default=25)
    parser.add_argument(
        "--max-requests",
        type=int,
        default=0,
        help="Bound total HTTP/browser attempts for this company collection.",
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--dry-run-receipt",
        action="store_true",
        help="with --dry-run, aggregate the bounded five-minute dry-run receipt "
        "from the staged manifest input and existing durable state",
    )
    parser.add_argument(
        "--dry-run-minutes",
        type=int,
        default=DEFAULT_DRY_RUN_MINUTES,
        help="wall-clock budget for the dry-run receipt; default five minutes",
    )
    parser.add_argument(
        "--require-existing-state",
        action="store_true",
        help="fail instead of creating a missing restored state database",
    )
    parser.add_argument(
        "--benchmark-profile",
        choices=tuple(BENCHMARK_PROFILES),
        help="attach the T36 five-minute benchmark profile to the machine-readable result",
    )
    parser.add_argument("--benchmark-owner", default=BENCHMARK_OWNER)
    parser.add_argument("--benchmark-revision", default=EMPLOYER_BENCHMARK_REVISION)
    parser.add_argument(
        "--benchmark-approval",
        choices=("not-required", "approved"),
        default="not-required",
    )
    parser.add_argument(
        "--benchmark-accepted-source",
        default="",
        help="declare the accepted-jobs source so accepted/published counts are honored",
    )
    parser.add_argument(
        "--benchmark-receipt",
        action="store_true",
        help="evaluate the run against the shared five-minute producer contract and "
        "write the employer benchmark receipt",
    )
    parser.add_argument(
        "--benchmark-fixture",
        action="store_true",
        help="run the offline bounded employer fixture benchmark instead of collecting",
    )
    parser.add_argument(
        "--benchmark-window",
        type=int,
        default=BENCHMARK_WINDOW_SECONDS,
        help="five-minute contract window for the benchmark receipt; default 300 seconds",
    )
    parser.add_argument(
        "--per-host-requests",
        type=int,
        default=None,
        help="per-host request admission ceiling for benchmark receipts; "
        "default 10 for authorized runs, 25 for the fixture benchmark",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.limit <= 0 and not args.full:
        parser.error("--limit must be positive; use --full for an unrestricted run")
    if args.max_requests < 0:
        parser.error("--max-requests must not be negative")
    if args.dry_run_minutes <= 0:
        parser.error("--dry-run-minutes must be positive")
    if args.dry_run_receipt and not args.dry_run:
        parser.error("--dry-run-receipt requires --dry-run")
    if args.benchmark_window <= 0:
        parser.error("--benchmark-window must be positive")
    if args.per_host_requests is not None and args.per_host_requests <= 0:
        parser.error("--per-host-requests must be positive")
    if args.benchmark_fixture and args.dry_run:
        parser.error("--benchmark-fixture runs its own offline fixture and cannot combine with --dry-run")
    if args.benchmark_fixture and args.benchmark_receipt:
        parser.error("--benchmark-fixture writes its own receipt and cannot combine with --benchmark-receipt")
    if args.company_id and args.company_ids:
        parser.error("use either --company-id or --company-ids")
    if args.company_ids and not args.full and len(set(args.company_ids)) > args.limit:
        parser.error("--limit must cover every requested company ID")
    pilot_only = not args.include_single_source
    manifest, tasks = require_eligibility_manifest(args.manifest, SOURCE_EMPLOYER, pilot_only=pilot_only)
    output_dir = args.output_dir.resolve()
    state_dir = args.state_dir.resolve() if args.state_dir is not None else None
    staged_input = output_dir / ".manifest_inputs" / f"{manifest['manifest_id']}-employer.csv"
    cohort = args.company_ids or ([args.company_id] if args.company_id else None)
    staged = materialize_source_input(
        manifest, SOURCE_EMPLOYER, staged_input, pilot_only=pilot_only, company_ids=cohort
    )
    if args.benchmark_fixture:
        receipt = run_employer_fixture_benchmark(
            output_dir=output_dir,
            profile=args.benchmark_profile or "local-dry-run",
            accepted_source=args.benchmark_accepted_source,
            approval_status=args.benchmark_approval,
            per_host_requests=args.per_host_requests or DEFAULT_FIXTURE_PER_HOST_REQUESTS,
            window_seconds=args.benchmark_window,
            eligibility_manifest_id=manifest.get("manifest_id", ""),
        )
        metrics = {
            "mode": "fixture_benchmark",
            "dry_run": True,
            "eligibility_source": SOURCE_EMPLOYER,
            "eligibility_manifest_id": manifest["manifest_id"],
            "eligibility_manifest_hash": manifest["manifest_hash"],
            "eligibility_tasks": len(tasks),
            "manifest_input": staged,
            "pilot_only": pilot_only,
            "employer_benchmark_receipt": receipt,
        }
        metrics["telemetry"] = _telemetry(SOURCE_EMPLOYER)
        print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    run_started = time.monotonic()
    if args.dry_run and args.dry_run_receipt:
        metrics = build_dry_run_receipt(
            manifest=manifest,
            staged_input=staged_input,
            output_dir=output_dir,
            state_dir=state_dir,
            pilot_only=pilot_only,
            duration_budget_seconds=args.dry_run_minutes * 60,
        )
    else:
        metrics = run_collection(
            input_csv=staged_input,
            output_dir=output_dir,
            limit=0 if args.full else args.limit,
            state_dir=state_dir,
            require_existing_state=args.require_existing_state,
            company_id=args.company_id,
            dry_run=args.dry_run,
            resume=args.resume,
            max_job_links=args.max_job_links,
            max_pages=args.max_pages,
            max_browser_requests=args.max_browser_requests,
            max_targets=args.max_targets,
            max_requests=args.max_requests or None,
            timeout_seconds=args.timeout,
        )
        metrics.update(
            {
                "eligibility_manifest_id": manifest["manifest_id"],
                "eligibility_manifest_hash": manifest["manifest_hash"],
                "eligibility_source": SOURCE_EMPLOYER,
                "eligibility_tasks": len(tasks),
                "manifest_input": staged,
                "pilot_only": pilot_only,
            }
        )
    metrics["telemetry"] = _telemetry(SOURCE_EMPLOYER)
    if args.benchmark_receipt:
        receipt = build_employer_benchmark_receipt(
            mode="dry_run_benchmark" if args.dry_run else "authorized_run_benchmark",
            metrics=metrics,
            manifest=manifest,
            staged_input=staged_input,
            output_dir=output_dir,
            state_dir=state_dir,
            profile=args.benchmark_profile or "local-dry-run",
            accepted_source=args.benchmark_accepted_source,
            approval_status=args.benchmark_approval,
            per_host_requests=args.per_host_requests or DEFAULT_PER_HOST_REQUESTS,
            window_seconds=args.benchmark_window,
            elapsed_seconds=(
                float(metrics.get("elapsed_seconds", 0.0))
                if args.dry_run
                else max(0.0001, time.monotonic() - run_started)
            ),
            timeout_seconds=float(args.timeout),
        )
        metrics["employer_benchmark_receipt"] = receipt
    if args.benchmark_profile:
        metrics["benchmark_profile"] = {
            "contract": "runr.producer-throughput.v1",
            "window_seconds": BENCHMARK_WINDOW_SECONDS,
            "profile": args.benchmark_profile,
            "owner": args.benchmark_owner,
            "revision": args.benchmark_revision,
            "approval": {
                "required": args.benchmark_profile == "vps-authorized-live",
                "status": args.benchmark_approval,
            },
            "ceilings": BENCHMARK_PROFILES[args.benchmark_profile],
        }
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
