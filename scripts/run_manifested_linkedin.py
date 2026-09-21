"""Run the LinkedIn collector through an RC-005 eligibility manifest."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.application.source_eligibility_manifest import (
    SOURCE_LINKEDIN,
    materialize_source_input,
    require_eligibility_manifest,
)
from scripts.benchmark_linkedin_pipeline import (
    BENCHMARK_OWNER,
    BENCHMARK_PROFILES,
    BENCHMARK_REVISION,
    BENCHMARK_WINDOW_SECONDS,
)
from scripts.master_linkedin_jobs_catalog import (
    LOCATION_GERMANY_CONFIRMED,
    LOCATION_MULTI_LOCATION_INCLUDES_GERMANY,
    LOCATION_REMOTE_GERMANY_ELIGIBLE,
    CatalogRunner,
    ResponseEnvelope,
    RunnerConfig,
    StateStore,
)

_DRY_RUN_STATE_DIRNAME = ".dry_run_state"
_DRY_RUN_RECEIPT_FILENAME = "dry_run_receipt.json"
_FIXTURE_JOBS_PER_COMPANY = 2
_FIXTURE_JOB_CARD_TEMPLATE = (
    '<li class="job-card-container" data-entity-urn="urn:li:jobPosting:{job_id}">'
    '<a href="{company_url}">{company_name}</a>'
    '<a href="https://www.linkedin.com/jobs/view/{job_id}"></a>'
    '<h3 class="base-search-card__title">Senior Engineer</h3>'
    '<span class="job-search-card__location">Berlin, Germany</span>'
    '<time datetime="2026-08-31">1 day ago</time>'
    "</li>"
)
_FIXTURE_SEARCH_PAGE_TEMPLATE = (
    '<html><body><ul class="jobs-search__results-list">{cards}</ul></body></html>'
)
_FIXTURE_NO_RESULTS_PAGE = (
    '<html><body><div class="jobs-search-no-results">No jobs found</div></body></html>'
)
_FIXTURE_DETAIL_PAGE_TEMPLATE = (
    '<article class="top-card-layout">'
    '  <h1 class="top-card-layout__title">Senior Engineer</h1>'
    '  <h4 class="top-card-layout__second-subline">'
    '    <a href="{company_url}">{company_name}</a>'
    "  </h4>"
    '  <div class="top-card-layout__first-subline">'
    "    <span>Berlin, Germany</span>"
    "    <span>Hybrid</span>"
    "  </div>"
    '  <div class="top-card-layout__entity-info">'
    "    <span>1 day ago</span>"
    "    <span>12 applicants</span>"
    "  </div>"
    '  <a class="top-card-layout__cta--primary" '
    'data-tracking-control-name="public_jobs_apply-link-offsite" '
    'href="https://jobs.{slug}.example/apply/{job_id}">Apply</a>'
    '  <section class="show-more-less-html">'
    '    <div class="description__text description__text--rich">'
    "      <p>Build and operate reliable data systems that keep the customer "
    "catalog complete. You will design bounded collection pipelines, keep "
    "durable state snapshots consistent, and make identity resolution "
    "observable for every job the producer captures each day.</p>"
    "    </div>"
    "  </section>"
    '  <ul class="description__job-criteria-list">'
    "    <li><h3>Employment type</h3><span>Full-time</span></li>"
    "    <li><h3>Job function</h3><span>Engineering</span></li>"
    "    <li><h3>Workplace type</h3><span>Hybrid</span></li>"
    "  </ul>"
    "</article>"
)
_FIXTURE_DESCRIPTION_MINIMUM_CHARS = 80
_PUBLISHABLE_LOCATION_CLASSES = frozenset(
    {
        LOCATION_GERMANY_CONFIRMED,
        LOCATION_REMOTE_GERMANY_ELIGIBLE,
        LOCATION_MULTI_LOCATION_INCLUDES_GERMANY,
    }
)
_PLACEHOLDER_VALUES = frozenset({"", "unknown", "n/a", "na", "none", "tbd", "tbd"})
_DEFAULT_FIXTURE_MAX_REQUESTS = 25


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value) if value else None


def _clean(value: object) -> str:
    return str(value or "").strip()


def _is_placeholder(value: object) -> bool:
    return _clean(value).lower() in _PLACEHOLDER_VALUES


def _fixture_job_ids(company_id: str) -> list[str]:
    base = int(company_id) * 1000
    return [str(base + offset) for offset in range(_FIXTURE_JOBS_PER_COMPANY)]


def _fixture_company_slug(company_url: str) -> str:
    parsed = urlsplit(company_url)
    return parsed.path.rstrip("/").rsplit("/", 1)[-1].lower()


def load_fixture_companies(
    staged_input: Path, company_id_filter: str | None = None
) -> list[dict[str, str]]:
    """Load the staged manifest cohort used to drive the offline fixture run."""

    companies: dict[str, dict[str, str]] = {}
    with Path(staged_input).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"canonical_CompanyID", "company_name", "linkedin_company_url", "linkedin_company_id"}
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"source CSV missing required columns: {', '.join(sorted(missing))}")
        for row in reader:
            company_id = _clean(row.get("linkedin_company_id"))
            company_url = _clean(row.get("linkedin_company_url"))
            if not company_id.isdigit() or int(company_id) == 0 or not company_url:
                continue
            if company_id_filter and company_id != str(company_id_filter):
                continue
            companies.setdefault(
                company_id,
                {
                    "canonical_CompanyID": _clean(row.get("canonical_CompanyID")),
                    "company_name": _clean(row.get("company_name")),
                    "linkedin_company_id": company_id,
                    "linkedin_company_url": company_url,
                },
            )
    return [companies[key] for key in sorted(companies, key=int)]


class DryRunFixtureTransport:
    """Deterministic offline transport backing the dry-run observable contract.

    It serves fixture search and detail pages for the staged manifest cohort,
    counts every response, and honours the caller-provided request budget by
    answering any request beyond it with ``request_budget_exhausted``. It never
    performs a network request and never requires provider credentials.
    """

    proxy_id = "fixture-dry-run"

    def __init__(self, companies: list[dict[str, str]], max_requests: int) -> None:
        self.companies = list(companies)
        self.max_requests = max(1, int(max_requests))
        self.request_count = 0
        self.search_pages = 0
        self.detail_pages = 0
        self.urls: list[tuple[str, str]] = []
        self._company_by_id = {company["linkedin_company_id"]: company for company in self.companies}
        self._company_by_job_id: dict[str, dict[str, str]] = {}
        for company in self.companies:
            for job_id in _fixture_job_ids(company["linkedin_company_id"]):
                self._company_by_job_id[job_id] = company

    def _budget_exhausted(self) -> ResponseEnvelope:
        return ResponseEnvelope(0, "", self.proxy_id, 0.0, "request_budget_exhausted")

    def _search(self, url: str) -> ResponseEnvelope:
        query = dict(parse_qsl(urlsplit(url).query))
        company_id = _clean(query.get("f_C"))
        if _clean(query.get("start", "0")) != "0":
            return ResponseEnvelope(200, _FIXTURE_NO_RESULTS_PAGE, self.proxy_id, 0.0)
        company = self._company_by_id.get(company_id)
        if company is None:
            return ResponseEnvelope(200, _FIXTURE_NO_RESULTS_PAGE, self.proxy_id, 0.0)
        cards = "".join(
            _FIXTURE_JOB_CARD_TEMPLATE.format(
                job_id=job_id,
                company_url=company["linkedin_company_url"],
                company_name=company["company_name"],
            )
            for job_id in _fixture_job_ids(company_id)
        )
        body = _FIXTURE_SEARCH_PAGE_TEMPLATE.format(cards=cards)
        return ResponseEnvelope(200, body, self.proxy_id, 0.0)

    def _detail(self, url: str) -> ResponseEnvelope:
        job_id = url.rstrip("/").rsplit("/", 1)[-1]
        company = self._company_by_job_id.get(job_id)
        if company is None:
            return ResponseEnvelope(404, "", self.proxy_id, 0.0)
        body = _FIXTURE_DETAIL_PAGE_TEMPLATE.format(
            company_url=company["linkedin_company_url"],
            company_name=company["company_name"],
            slug=_fixture_company_slug(company["linkedin_company_url"]),
            job_id=job_id,
        )
        return ResponseEnvelope(200, body, self.proxy_id, 0.0)

    def get(self, url: str, *, kind: str) -> ResponseEnvelope:
        if self.request_count >= self.max_requests:
            return self._budget_exhausted()
        self.request_count += 1
        self.urls.append((url, kind))
        if kind == "search":
            self.search_pages += 1
            return self._search(url)
        if kind == "detail":
            self.detail_pages += 1
            return self._detail(url)
        return ResponseEnvelope(404, "", self.proxy_id, 0.0)

    def close(self) -> None:
        return None


def _load_run_observations(state_path: Path, run_id: str) -> list[dict[str, Any]]:
    if not run_id or not state_path.is_file():
        return []
    store = StateStore(state_path)
    try:
        rows = store.connection.execute(
            "SELECT row_json FROM job_company_observations WHERE run_id=?", (run_id,)
        ).fetchall()
    finally:
        store.close()
    parsed: list[dict[str, Any]] = []
    for row in rows:
        try:
            record = json.loads(row[0])
        except (TypeError, ValueError):
            continue
        if isinstance(record, dict):
            parsed.append(record)
    return parsed


def _is_publishable_row(row: Mapping[str, Any]) -> bool:
    if not _clean(row.get("canonical_company_id")) or not _clean(row.get("linkedin_company_id")):
        return False
    if _clean(row.get("lifecycle_status")) != "active":
        return False
    if _is_placeholder(row.get("job_title")):
        return False
    if not _clean(row.get("apply_url_canonical")):
        return False
    if _clean(row.get("location_classification")) not in _PUBLISHABLE_LOCATION_CLASSES:
        return False
    description = re.sub(r"<[^>]+>", " ", str(row.get("description") or ""))
    meaningful = re.sub(r"[^0-9A-Za-z]+", "", description)
    return len(meaningful) >= _FIXTURE_DESCRIPTION_MINIMUM_CHARS


def build_dry_run_receipt(
    metrics: Mapping[str, Any],
    state_path: Path,
    limits: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify the dry-run pipeline outcome into bounded observable classes.

    The receipt distinguishes fetched responses, parsed job cards,
    identity-resolved durable observations, rejected records (with per-class
    components), and publishable job records. All counts come from the runner
    metrics and the dry-run state database; nothing is inferred or invented.
    """

    run_id = _clean(metrics.get("run_id"))
    observations = _load_run_observations(state_path, run_id) if run_id else []
    identity_rows = [
        row
        for row in observations
        if _clean(row.get("canonical_company_id")) and _clean(row.get("linkedin_company_id"))
    ]
    rejected_components = {
        "malformed_cards": int(metrics.get("malformed_cards", 0) or 0),
        "ownership_exclusions": int(metrics.get("ownership_exclusions", 0) or 0),
        "detail_failures": int(metrics.get("detail_failures", 0) or 0),
        "input_rows_rejected": int(metrics.get("rows_rejected", 0) or 0),
    }
    return {
        "schema_version": "linkedin_dry_run_receipt_v1",
        "dry_run": True,
        "pipeline_executed": not bool(metrics.get("dry_run", False)),
        "unit": "job_records",
        "fetched": int(metrics.get("requests", 0) or 0),
        "parsed": int(metrics.get("valid_cards", 0) or 0),
        "identity_resolved": len(identity_rows),
        "rejected": sum(rejected_components.values()),
        "rejected_components": rejected_components,
        "publishable": sum(1 for row in identity_rows if _is_publishable_row(row)),
        "limits": dict(limits),
        "run_id": run_id,
        "run_outcome": _clean(metrics.get("run_outcome")),
        "state_dir_isolated": True,
    }


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
    parser.add_argument(
        "--include-single-source",
        action="store_true",
        help="opt into website-only/LinkedIn-only expansion tasks; default is the dual-source pilot",
    )
    parser.add_argument(
        "--pagination-report",
        type=Path,
        default=None,
        help="validated pagination report path; falls back to RUNR_LINKEDIN_PAGINATION_REPORT",
    )
    parser.add_argument(
        "--filters-report",
        type=Path,
        default=None,
        help="validated filter report path; falls back to RUNR_LINKEDIN_FILTERS_REPORT",
    )
    parser.add_argument("--mode", choices=("validate", "smoke", "pilot", "full", "daily", "reconcile"), default="full")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--detail-workers", type=int, default=5)
    parser.add_argument("--per-proxy-concurrency", type=int, default=1)
    parser.add_argument("--min-workers", type=int, default=1)
    parser.add_argument("--max-workers", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retry-limit", type=int, default=2)
    parser.add_argument("--max-requests", type=int, default=0)
    parser.add_argument("--detail-refresh-hours", type=float, default=168.0)
    parser.add_argument("--volatile-refresh-hours", type=float, default=24.0)
    parser.add_argument("--company-id")
    parser.add_argument("--company-ids", nargs="+", help="exact eligible canonical IDs for a bounded cohort")
    parser.add_argument("--resume-run-id")
    parser.add_argument("--max-companies", type=int)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument(
        "--require-existing-state",
        action="store_true",
        help="fail instead of creating a missing restored state database",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--benchmark-profile",
        choices=tuple(BENCHMARK_PROFILES),
        help="attach the T36 five-minute benchmark profile to the machine-readable result",
    )
    parser.add_argument("--benchmark-owner", default=BENCHMARK_OWNER)
    parser.add_argument("--benchmark-revision", default=BENCHMARK_REVISION)
    parser.add_argument(
        "--benchmark-approval",
        choices=("not-required", "approved"),
        default="not-required",
    )
    return parser


def _dry_run_limits(args: argparse.Namespace, max_requests: int) -> dict[str, Any]:
    return {
        "max_requests": max_requests,
        "workers": args.workers,
        "detail_workers": args.detail_workers,
        "per_proxy_concurrency": args.per_proxy_concurrency,
        "timeout_seconds": args.timeout,
        "retry_limit": args.retry_limit,
    }


def _run_dry_run(
    args: argparse.Namespace,
    output_dir: Path,
    state_dir: Path | None,
    staged_input: Path,
    pagination_report: Path | None,
    filters_report: Path | None,
    max_companies: int | None,
) -> tuple[dict[str, object], dict[str, Any]]:
    """Execute the manifest-validated pipeline offline against fixture pages.

    The dry run validates the eligibility manifest and staged input, then
    executes the real producer end to end against ``DryRunFixtureTransport``.
    All state writes stay inside ``<output-dir>/.dry_run_state``; the durable
    state directory is validated but never written. When the staged cohort is
    unavailable the run falls back to the original validation-only contract
    and the receipt reports the pipeline as not executed.
    """

    limits = _dry_run_limits(args, args.max_requests if args.max_requests > 0 else _DEFAULT_FIXTURE_MAX_REQUESTS)
    if not staged_input.is_file():
        # Validation-only fallback: keep the original manifest/state guard
        # semantics without executing the fixture pipeline.
        config = RunnerConfig(
            input_csv=staged_input,
            output_dir=output_dir,
            state_dir=state_dir,
            pagination_report=pagination_report,
            filters_report=filters_report,
            mode=args.mode,
            workers=args.workers,
            detail_workers=args.detail_workers,
            per_proxy_concurrency=args.per_proxy_concurrency,
            min_workers=args.min_workers,
            max_workers=args.max_workers,
            timeout=args.timeout,
            retry_limit=args.retry_limit,
            max_requests=args.max_requests or None,
            detail_refresh_hours=args.detail_refresh_hours,
            volatile_refresh_hours=args.volatile_refresh_hours,
            company_id=args.company_id,
            resume_run_id=args.resume_run_id,
            fresh=args.fresh,
            require_existing_state=args.require_existing_state,
            dry_run=True,
            max_companies=max_companies,
        )
        runner = CatalogRunner(config, transport=object())
        metrics = runner.run()
        receipt = build_dry_run_receipt(
            metrics,
            (state_dir if state_dir is not None else output_dir) / "master_linkedin_jobs_state.db",
            limits,
        )
        return metrics, receipt
    if args.require_existing_state:
        durable_state_dir = state_dir if state_dir is not None else output_dir
        durable_state_path = durable_state_dir / "master_linkedin_jobs_state.db"
        if not durable_state_path.is_file():
            raise FileNotFoundError(f"LinkedIn state database not found: {durable_state_path}")
    max_requests = limits["max_requests"]
    transport = DryRunFixtureTransport(
        load_fixture_companies(staged_input, company_id_filter=args.company_id),
        max_requests=max_requests,
    )
    dry_state_dir = output_dir / _DRY_RUN_STATE_DIRNAME
    config = RunnerConfig(
        input_csv=staged_input,
        output_dir=output_dir,
        state_dir=dry_state_dir,
        pagination_report=pagination_report,
        filters_report=filters_report,
        mode=args.mode,
        workers=args.workers,
        detail_workers=args.detail_workers,
        per_proxy_concurrency=args.per_proxy_concurrency,
        min_workers=args.min_workers,
        max_workers=args.max_workers,
        timeout=args.timeout,
        retry_limit=args.retry_limit,
        max_requests=max_requests,
        detail_refresh_hours=args.detail_refresh_hours,
        volatile_refresh_hours=args.volatile_refresh_hours,
        company_id=args.company_id,
        resume_run_id=args.resume_run_id,
        fresh=False,
        require_existing_state=False,
        dry_run=False,
        max_companies=max_companies,
    )
    runner = CatalogRunner(config, transport=transport)
    metrics = runner.run()
    receipt = build_dry_run_receipt(metrics, dry_state_dir / "master_linkedin_jobs_state.db", limits)
    receipt["fixture_transport"] = {
        "search_pages": transport.search_pages,
        "detail_pages": transport.detail_pages,
        "requests_served": transport.request_count,
        "request_budget": transport.max_requests,
    }
    return metrics, receipt


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.company_id and args.company_ids:
        parser.error("use either --company-id or --company-ids")
    if args.company_ids and args.max_companies is not None:
        parser.error("--company-ids selects the exact cohort; do not combine with --max-companies")
    if args.max_requests < 0:
        parser.error("--max-requests must not be negative")
    pilot_only = not args.include_single_source
    manifest, tasks = require_eligibility_manifest(args.manifest, SOURCE_LINKEDIN, pilot_only=pilot_only)
    output_dir = args.output_dir.resolve()
    state_dir = args.state_dir.resolve() if args.state_dir is not None else None
    staged_input = output_dir / ".manifest_inputs" / f"{manifest['manifest_id']}-linkedin.csv"
    cohort = args.company_ids
    staged = materialize_source_input(
        manifest, SOURCE_LINKEDIN, staged_input, pilot_only=pilot_only, company_ids=cohort
    )
    pagination_report = args.pagination_report or _env_path("RUNR_LINKEDIN_PAGINATION_REPORT")
    filters_report = args.filters_report or _env_path("RUNR_LINKEDIN_FILTERS_REPORT")
    max_companies = staged["rows"] if args.company_ids else args.max_companies
    if args.dry_run:
        metrics, receipt = _run_dry_run(
            args,
            output_dir,
            state_dir,
            staged_input,
            pagination_report,
            filters_report,
            max_companies,
        )
        receipt_path = output_dir / _DRY_RUN_RECEIPT_FILENAME
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        metrics["dry_run_receipt"] = receipt
        metrics["dry_run_receipt"]["receipt_path"] = str(receipt_path)
    else:
        config = RunnerConfig(
            input_csv=staged_input,
            output_dir=output_dir,
            state_dir=state_dir,
            pagination_report=pagination_report,
            filters_report=filters_report,
            mode=args.mode,
            workers=args.workers,
            detail_workers=args.detail_workers,
            per_proxy_concurrency=args.per_proxy_concurrency,
            min_workers=args.min_workers,
            max_workers=args.max_workers,
            timeout=args.timeout,
            retry_limit=args.retry_limit,
            max_requests=args.max_requests or None,
            detail_refresh_hours=args.detail_refresh_hours,
            volatile_refresh_hours=args.volatile_refresh_hours,
            company_id=args.company_id,
            resume_run_id=args.resume_run_id,
            fresh=args.fresh,
            require_existing_state=args.require_existing_state,
            dry_run=args.dry_run,
            max_companies=staged["rows"] if args.company_ids else args.max_companies,
        )
        # The low-level producer creates its transport lazily. A non-dry-run
        # invocation uses the real Webshare transport configuration lookup.
        runner = CatalogRunner(config, transport=None)
        metrics = runner.run()
    metrics.update(
        {
            "eligibility_manifest_id": manifest["manifest_id"],
            "eligibility_manifest_hash": manifest["manifest_hash"],
            "eligibility_source": SOURCE_LINKEDIN,
            "eligibility_tasks": len(tasks),
            "manifest_input": staged,
            "pilot_only": pilot_only,
            "telemetry": _telemetry(SOURCE_LINKEDIN),
        }
    )
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
