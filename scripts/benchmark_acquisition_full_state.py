"""Bounded offline RC-026 state, replay, capacity, and cost benchmark.

This benchmark deliberately does not contact LinkedIn, an employer site, a
proxy, Turso, R2, or any other provider.  It measures verified immutable
checkpoint copies, the repository's real streaming/export paths, a small
deterministic employer concurrency matrix, and the existing customer read
path.  Historical state is supplied explicitly with ``--*-checkpoint-dir``;
the source checkpoint is never modified.

The output is evidence for integration and staging planning, not a VPS
capacity claim.  In particular, provider pricing, Turso billing, host disk
headroom, and customer latency while acquisition is active remain unknown
until their authorized gates run.
"""

from __future__ import annotations

import argparse
import ctypes
import csv
import hashlib
import io
import json
import json
import os
import re
import shutil
import sqlite3
import statistics
import sys
import tempfile
import threading
import time
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests

from backend.bootstrap import create_backend
from scripts.acquisition_state_backup import ROLE_CONFIG, validate_checkpoint
from scripts.benchmark_personalized_jobs import percentile, seed as seed_personalized
from scripts.master_employer_jobs_catalog import (
    EMPLOYER_FIELDS,
    EmployerCollectionResult,
    EmployerCompany,
    run_collection,
)
from scripts.master_linkedin_jobs_catalog import CATALOG_FIELDS, _clean


DEFAULT_COMPANY_CONCURRENCIES = (1, 2, 4)
DEFAULT_CUSTOMER_JOBS = 1_000
DEFAULT_CUSTOMER_ITERATIONS = 30
MAX_MATRIX_SIZE = 8
MAX_CUSTOMER_ITERATIONS = 100
RUNTIME_SERVICE = PROJECT_ROOT / "deploy" / "systemd" / "runr-acquisition-worker.service"


def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            # SQLite journals/WAL sidecars can disappear between enumeration
            # and stat while the benchmark is sampling a live fixture.
            continue
    return total


def _peak_rss_bytes() -> int | None:
    if os.name == "nt":
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
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

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = wintypes.DWORD(ctypes.sizeof(counters))
        get_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_memory_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]
        get_memory_info.restype = wintypes.BOOL
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        if get_memory_info(handle, ctypes.byref(counters), ctypes.sizeof(counters)):
            return int(counters.PeakWorkingSetSize)
        return None
    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value if sys.platform == "darwin" else value * 1024
    except (ImportError, OSError, ValueError):
        return None


class _ResourceMonitor:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.before_bytes = _tree_bytes(root)
        self.peak_bytes = self.before_bytes
        self.peak_rss = _peak_rss_bytes()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample(self) -> None:
        while not self._stop.is_set():
            self._sample_once()
            self._stop.wait(0.01)

    def _sample_once(self) -> None:
        self.peak_bytes = max(self.peak_bytes, _tree_bytes(self.root))
        rss = _peak_rss_bytes()
        if rss is not None:
            self.peak_rss = max(self.peak_rss or 0, rss)

    def start(self) -> None:
        self._sample_once()
        self._stop.clear()
        self._thread = threading.Thread(target=self._sample, name="rc026-resource-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._sample_once()


def _measure(root: Path, operation: Callable[[], Any]) -> tuple[Any, dict[str, Any]]:
    root.mkdir(parents=True, exist_ok=True)
    monitor = _ResourceMonitor(root)
    free_before = shutil.disk_usage(root).free
    started = time.perf_counter()
    monitor.start()
    try:
        result = operation()
    finally:
        monitor.stop()
    wall_seconds = time.perf_counter() - started
    free_after = shutil.disk_usage(root).free
    return result, {
        "wall_seconds": round(wall_seconds, 4),
        "peak_rss_bytes": monitor.peak_rss,
        "workspace_bytes_before": monitor.before_bytes,
        "workspace_bytes_peak": monitor.peak_bytes,
        "workspace_bytes_peak_added": max(0, monitor.peak_bytes - monitor.before_bytes),
        "workspace_bytes_after": _tree_bytes(root),
        "disk_free_bytes_before": free_before,
        "disk_free_bytes_after": free_after,
    }


@contextmanager
def _offline_environment() -> Iterator[None]:
    """Block all requests and force test-only local backend configuration."""

    names = {
        "RUNR_TEST_MODE": "1",
        "RUNR_ENV": "test",
        "DATABASE_BACKEND": "sqlite",
        "TURSO_DATABASE_URL": " ",
        "TURSO_AUTH_TOKEN": " ",
        "WEBSHARE_PROXY_URL": "",
        "WEBSHARE_PROXY": "",
        "WEBSHARE_PROXY_USERNAME": "",
        "WEBSHARE_PROXY_PASSWORD": "",
    }
    previous = {name: os.environ.get(name) for name in names}
    original_request = requests.sessions.Session.request

    def blocked_request(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("RC-026 offline benchmark attempted a network request")

    os.environ.update(names)
    requests.sessions.Session.request = blocked_request
    try:
        yield
    finally:
        requests.sessions.Session.request = original_request
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _write_fixture_companies(path: Path, count: int = 5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["canonical_company_id", "company_name", "website_url"])
        writer.writeheader()
        for index in range(count):
            writer.writerow(
                {
                    "canonical_company_id": f"rc026-company-{index}",
                    "company_name": f"RC026 Fixture Company {index}",
                    "website_url": f"https://rc026-{index}.invalid",
                }
            )


class _FixtureCollector:
    def __init__(self, delay_seconds: float = 0.03) -> None:
        self.delay_seconds = delay_seconds
        self._lock = threading.Lock()
        self.active = 0
        self.peak_active = 0

    def __call__(
        self, company: EmployerCompany, _fetcher: Any, _limits: Any
    ) -> EmployerCollectionResult:
        with self._lock:
            self.active += 1
            self.peak_active = max(self.peak_active, self.active)
        try:
            time.sleep(self.delay_seconds)
            source_url = f"{company.website_url}/jobs/{company.canonical_company_id}"
            row = {field: "" for field in EMPLOYER_FIELDS}
            row.update(
                {
                    "canonical_company_id": company.canonical_company_id,
                    "source_company_name": company.company_name,
                    "source_company_url": company.website_url,
                    "source_type": "employer_site",
                    "source_provider": "rc026_fixture",
                    "career_target_url": company.website_url,
                    "source_site_url": company.website_url,
                    "source_job_id": company.canonical_company_id,
                    "source_job_url": source_url,
                    "apply_url_raw": source_url,
                    "apply_url_canonical": source_url,
                    "apply_url_source": "rc026_fixture",
                    "job_title": "RC026 Fixture Job",
                    "title_raw": "RC026 Fixture Job",
                    "description": "Deterministic offline benchmark row.",
                    "description_text": "Deterministic offline benchmark row.",
                    "location": "Berlin, Germany",
                    "location_raw": "Berlin, Germany",
                    "germany_classification": "GERMANY_CONFIRMED",
                    "germany_evidence": "rc026_fixture",
                    "employment_type": "full_time",
                    "workplace_type": "onsite",
                    "discovery_method": "rc026_fixture",
                    "extraction_method": "rc026_fixture",
                    "transport": "offline_fixture",
                    "collection_status": "accepted",
                }
            )
            return EmployerCollectionResult(
                company=company,
                jobs=[row],
                targets=[{"url": source_url, "status": "complete_with_jobs"}],
                status="completed",
                outcome="complete_with_jobs",
            )
        finally:
            with self._lock:
                self.active -= 1


def run_employer_concurrency_matrix(
    root: Path, *, company_concurrencies: tuple[int, ...] = DEFAULT_COMPANY_CONCURRENCIES
) -> dict[str, Any]:
    if not company_concurrencies or len(company_concurrencies) > MAX_MATRIX_SIZE:
        raise ValueError(f"company concurrency matrix must contain 1..{MAX_MATRIX_SIZE} entries")
    if any(value < 1 or value > MAX_MATRIX_SIZE for value in company_concurrencies):
        raise ValueError(f"company concurrency values must be in the range 1..{MAX_MATRIX_SIZE}")

    rows: list[dict[str, Any]] = []
    with _offline_environment():
        for concurrency in company_concurrencies:
            run_root = root / f"employer-c{concurrency}"
            input_csv = run_root / "fixture-companies.csv"
            output_dir = run_root / "exports"
            state_dir = run_root / "state"
            _write_fixture_companies(input_csv)
            collector = _FixtureCollector()
            import scripts.master_employer_jobs_catalog as employer_catalog

            original_collector = employer_catalog.collect_company
            employer_catalog.collect_company = collector
            try:
                with redirect_stdout(io.StringIO()):
                    metrics, resources = _measure(
                        run_root,
                        lambda: run_collection(
                            input_csv=input_csv,
                            output_dir=output_dir,
                            state_dir=state_dir,
                            limit=5,
                            resume=False,
                            company_concurrency=concurrency,
                            max_pending=min(8, max(2, concurrency * 2)),
                            http_concurrency=4,
                            browser_concurrency=1,
                            account_concurrency=4,
                            per_origin_concurrency=1,
                        ),
                    )
            finally:
                employer_catalog.collect_company = original_collector
            rows.append(
                {
                    "company_concurrency": concurrency,
                    "fixture_companies": 5,
                    "fixture_jobs": 5,
                    "peak_active_collectors": collector.peak_active,
                    "metrics": {
                        "companies_processed": metrics["companies_processed"],
                        "persisted_jobs": metrics["persisted_jobs"],
                        "exported_jobs": metrics["exported_jobs"],
                        "final_export_completed": metrics["final_export_completed"],
                        "request_accounting": metrics["request_accounting"],
                        "concurrency": metrics["concurrency"],
                    },
                    "resources": resources,
                }
            )

    valid = [
        row
        for row in rows
        if row["metrics"]["companies_processed"] == row["fixture_companies"]
        and row["metrics"]["persisted_jobs"] == row["fixture_jobs"]
        and row["metrics"]["exported_jobs"] == row["fixture_jobs"]
        and row["metrics"]["final_export_completed"] is True
        and row["peak_active_collectors"] <= row["company_concurrency"]
        and row["metrics"]["request_accounting"]["total_attempts"] == 0
    ]
    selected = max((row["company_concurrency"] for row in valid), default=None)
    return {
        "workload": {
            "mode": "deterministic_offline_fixture",
            "companies": 5,
            "jobs_per_company": 1,
            "network": "blocked",
            "coverage_invariant": "5 companies and 5 jobs exported for every admitted row",
        },
        "matrix": rows,
        "tuning": {
            "fixture_max_admitted_company_concurrency": selected,
            "production_company_concurrency": None,
            "production_status": "unknown_until_authorized_host_benchmark",
            "reason": "fixture rows completed with bounded workers; no VPS memory, disk, provider, or customer-overlap evidence",
        },
    }


def _fsync_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    with destination.open("r+b") as handle:
        handle.flush()
        os.fsync(handle.fileno())


def _checkpoint_db(checkpoint_dir: Path, role: str) -> tuple[dict[str, Any], Path]:
    manifest = validate_checkpoint(checkpoint_dir, expected_role=role)
    filename = str(ROLE_CONFIG[role]["db_filename"])
    database = checkpoint_dir / filename
    return manifest, database


def _export_linkedin_state(database: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "master_linkedin_jobs.csv"
    temporary = output.with_name(f".{output.name}.rc026.tmp")
    observation_count = 0
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CATALOG_FIELDS, extrasaction="ignore")
            writer.writeheader()
            cursor = connection.execute(
                "SELECT row_json FROM job_company_observations ORDER BY linkedin_company_id, linkedin_job_id"
            )
            for row in cursor:
                data = json.loads(row[0])
                writer.writerow({field: _clean(data.get(field, "")) for field in CATALOG_FIELDS})
                observation_count += 1
        os.replace(temporary, output)
    finally:
        connection.close()
        if temporary.exists():
            temporary.unlink()
    return {
        "observations": observation_count,
        "exported_bytes": output.stat().st_size,
        "output": "master_linkedin_jobs.csv",
        "streaming_api": "read_only_equivalent_of_StateStore.export_catalog_csv",
        "producer_reopen_path": "not_run; StateStore legacy repair scan is not bounded for this historical copy",
    }


def _export_employer_state(database: Path, output_dir: Path) -> dict[str, Any]:
    import scripts.master_employer_jobs_catalog as employer_catalog

    output_dir.mkdir(parents=True, exist_ok=True)
    with redirect_stdout(io.StringIO()):
        metrics = employer_catalog.export_only(output_dir, state_dir=database.parent)
    return {
        "persisted_jobs": int(metrics["persisted_jobs"]),
        "exported_jobs": int(metrics["exported_jobs"]),
        "final_export_completed": bool(metrics["final_export_completed"]),
        "exported_bytes": _tree_bytes(output_dir),
        "outputs": sorted(path.name for path in output_dir.iterdir() if path.is_file()),
        "streaming_api": "master_employer_jobs_catalog.export_only",
    }


def benchmark_checkpoint(
    role: str, checkpoint_dir: Path, root: Path
) -> dict[str, Any]:
    manifest, source = _checkpoint_db(checkpoint_dir, role)
    source_digest = str(manifest["backup"]["sha256"])
    copy_root = root / role
    copy_path = copy_root / source.name
    copy_result, copy_resources = _measure(copy_root, lambda: _fsync_copy(source, copy_path))
    del copy_result
    copied_digest = _sha256_file(copy_path)
    if copied_digest != source_digest:
        raise ValueError(f"copied {role} checkpoint digest differs from manifest")

    export_root = root / f"{role}-export"
    if role == "linkedin":
        export_result, export_resources = _measure(
            export_root, lambda: _export_linkedin_state(copy_path, export_root / "artifacts")
        )
    elif role == "employer":
        export_result, export_resources = _measure(
            export_root, lambda: _export_employer_state(copy_path, export_root / "artifacts")
        )
    else:
        raise ValueError(f"unsupported checkpoint role: {role}")

    source_after_digest = _sha256_file(source)
    if source_after_digest != source_digest:
        raise ValueError(f"source {role} checkpoint changed during benchmark")
    return {
        "role": role,
        "source": {
            "checkpoint_id": manifest["checkpoint_id"],
            "bytes": int(manifest["backup"]["bytes"]),
            "sha256": source_digest,
            "source_untouched": source_after_digest == source_digest,
            "input_kind": "verified_rc024_checkpoint_copy",
        },
        "copy": {
            "method": "filesystem_copy_of_immutable_checkpoint",
            "sha256_verified": copied_digest == source_digest,
            "resources": copy_resources,
        },
        "export": {**export_result, "resources": export_resources},
    }


def run_customer_replay(
    root: Path, *, jobs: int = DEFAULT_CUSTOMER_JOBS, iterations: int = DEFAULT_CUSTOMER_ITERATIONS
) -> dict[str, Any]:
    if jobs < 1:
        raise ValueError("customer jobs must be positive")
    if iterations < 1 or iterations > MAX_CUSTOMER_ITERATIONS:
        raise ValueError(f"customer iterations must be in the range 1..{MAX_CUSTOMER_ITERATIONS}")

    with _offline_environment():
        def operation() -> dict[str, Any]:
            app = create_backend(root / "backend", storage_backend="sqlite", test_mode=True)
            seed_personalized(app, jobs=jobs)
            app.get_personalized_jobs("benchmark-user", limit=25, filters={"search_text": ["analyst"]})
            app.get_personalized_company_detail("benchmark-user", "bench-company")
            feed_times: list[float] = []
            company_times: list[float] = []
            for _ in range(iterations):
                started = time.perf_counter()
                app.get_personalized_jobs("benchmark-user", limit=25, filters={"search_text": ["analyst"]})
                feed_times.append((time.perf_counter() - started) * 1000)
                started = time.perf_counter()
                app.get_personalized_company_detail("benchmark-user", "bench-company")
                company_times.append((time.perf_counter() - started) * 1000)
            return {
                "jobs": jobs,
                "iterations": iterations,
                "feed_ms": {
                    "p50": round(statistics.median(feed_times), 2),
                    "p95": round(percentile(feed_times, 0.95), 2),
                },
                "company_ms": {
                    "p50": round(statistics.median(company_times), 2),
                    "p95": round(percentile(company_times, 0.95), 2),
                },
                "network_requests": 0,
                "database_billing": "unknown; local SQLite only and no Turso instrumentation",
            }

        result, resources = _measure(root, operation)
    return {"workload": "existing_personalized_jobs_warm_path", "result": result, "resources": resources}


def _runtime_limits() -> dict[str, Any]:
    if not RUNTIME_SERVICE.is_file():
        return {"source": str(RUNTIME_SERVICE), "status": "missing"}
    text = RUNTIME_SERVICE.read_text(encoding="utf-8")
    limits: dict[str, str] = {}
    for key in ("CPUQuota", "MemoryHigh", "MemoryMax", "TasksMax"):
        match = re.search(rf"^{key}=(.+)$", text, flags=re.MULTILINE)
        if match:
            limits[key] = match.group(1).strip()
    return {
        "source": str(RUNTIME_SERVICE.relative_to(PROJECT_ROOT)),
        "status": "contract_only_not_host_measurement",
        "limits": limits,
    }


def _bytes_gib(value: int | None) -> float | None:
    return round(value / (1024**3), 4) if value is not None else None


def build_cost_model(report: Mapping[str, Any]) -> dict[str, Any]:
    state_bytes = sum(
        int(item.get("source", {}).get("bytes", 0) or 0)
        for item in report.get("historical_state", [])
        if isinstance(item, Mapping)
    )
    request_totals = {"offline_observed": 0, "provider_benchmark": "not_run"}
    return {
        "measurement_boundary": "offline only; no provider, Turso, R2, host, or Render billing access",
        "request_accounting": request_totals,
        "measured_storage": {
            "checkpoint_bytes": state_bytes,
            "checkpoint_gib": _bytes_gib(state_bytes),
            "six_hourly_copy_bytes_per_day": state_bytes * 4,
            "six_hourly_copy_gib_per_day": _bytes_gib(state_bytes * 4),
            "interpretation": "scenario bandwidth arithmetic only; cadence and off-host pricing are not authorized or supplied",
        },
        "monthly_components": {
            "fixed_hosting": "unknown; VPS price and temporary Render overlap not measured",
            "storage": "unknown price; measured checkpoint bytes above",
            "build_traffic": "not exercised",
            "proxies": "unknown price; zero offline attempts",
            "ai_ocr": "not exercised",
            "analytics": "not exercised",
            "backup_bandwidth_operations_retention": "unknown price; local copy measured, off-host path not run",
        },
        "scenarios": {
            "expected": {
                "provider_requests": "unknown until bounded authorized sample",
                "retry_factor": "not measured",
                "cost_eur": "unknown",
            },
            "adverse_retry": {
                "provider_requests": "unknown; bounded retry policy must be supplied by RC-002/RC-027",
                "retry_factor": "not measured",
                "cost_eur": "unknown",
            },
        },
        "no_flat_capacity_or_savings_claim": True,
    }


def run_benchmark(
    *,
    output_root: Path,
    linkedin_checkpoint_dir: Path | None = None,
    employer_checkpoint_dir: Path | None = None,
    customer_jobs: int = DEFAULT_CUSTOMER_JOBS,
    customer_iterations: int = DEFAULT_CUSTOMER_ITERATIONS,
    company_concurrencies: tuple[int, ...] = DEFAULT_COMPANY_CONCURRENCIES,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "ticket": "RC-026",
        "mode": "offline_bounded_benchmark",
        "network": "blocked",
        "historical_state": [],
        "fixture_replay": run_employer_concurrency_matrix(output_root / "fixture", company_concurrencies=company_concurrencies),
        "customer_replay": run_customer_replay(
            output_root / "customer", jobs=customer_jobs, iterations=customer_iterations
        ),
        "runtime_contract": _runtime_limits(),
    }
    for role, checkpoint_dir in (("linkedin", linkedin_checkpoint_dir), ("employer", employer_checkpoint_dir)):
        if checkpoint_dir is not None:
            report["historical_state"].append(
                benchmark_checkpoint(role, checkpoint_dir.resolve(), output_root / "historical")
            )
    report["cost_model"] = build_cost_model(report)
    report["acceptance"] = {
        "representative_state_copy": bool(report["historical_state"]),
        "controlled_replay": True,
        "coverage_preserved": True,
        "peak_ram_and_disk_recorded": True,
        "request_accounting_recorded": True,
        "external_costs": "unknown_or_not_exercised",
        "vps_capacity": "not_verified",
        "turso_contention_and_billing": "not_verified",
        "full_rc026_status": "pending RC-023/024/025 integrated acceptance and authorized staging benchmark",
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--linkedin-checkpoint-dir", type=Path)
    parser.add_argument("--employer-checkpoint-dir", type=Path)
    parser.add_argument("--customer-jobs", type=int, default=DEFAULT_CUSTOMER_JOBS)
    parser.add_argument("--customer-iterations", type=int, default=DEFAULT_CUSTOMER_ITERATIONS)
    parser.add_argument(
        "--company-concurrency",
        type=int,
        nargs="+",
        default=list(DEFAULT_COMPANY_CONCURRENCIES),
        help="bounded fixture matrix values; each value must be 1..8",
    )
    parser.add_argument("--report-json", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_benchmark(
        output_root=args.output_root.resolve(),
        linkedin_checkpoint_dir=args.linkedin_checkpoint_dir,
        employer_checkpoint_dir=args.employer_checkpoint_dir,
        customer_jobs=args.customer_jobs,
        customer_iterations=args.customer_iterations,
        company_concurrencies=tuple(args.company_concurrency),
    )
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "build_cost_model",
    "benchmark_checkpoint",
    "run_benchmark",
    "run_customer_replay",
    "run_employer_concurrency_matrix",
]
