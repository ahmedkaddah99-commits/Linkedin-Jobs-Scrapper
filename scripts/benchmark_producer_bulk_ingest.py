"""Benchmark legacy and set-based producer ingestion on deterministic fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import backend.repositories.sqlite_acquisition as acquisition_module
from backend.database.connection import DatabaseConnection
from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore
from scripts.publish_producer_states import SOURCE_EMPLOYER, _target


class _Measurements:
    def __init__(self) -> None:
        self.execute_calls = 0
        self.executemany_calls = 0
        self.transactions = 0
        self.read_seconds = 0.0
        self.write_seconds = 0.0
        self.transaction_seconds = 0.0
        self.normalization_seconds = 0.0


def _is_read(sql: str) -> bool:
    first = str(sql).lstrip().split(None, 1)
    return bool(first and first[0].upper() in {"SELECT", "PRAGMA", "EXPLAIN"})


@contextmanager
def _measure_database() -> Iterator[_Measurements]:
    measurements = _Measurements()
    original_execute = DatabaseConnection.execute
    original_executemany = DatabaseConnection.executemany
    original_transaction = DatabaseConnection.transaction
    original_normalize = acquisition_module.normalize_job_for_ingestion

    def execute(connection, sql, parameters=()):
        started = perf_counter()
        try:
            return original_execute(connection, sql, parameters)
        finally:
            elapsed = perf_counter() - started
            measurements.execute_calls += 1
            if _is_read(sql):
                measurements.read_seconds += elapsed
            else:
                measurements.write_seconds += elapsed

    def executemany(connection, sql, parameter_rows):
        started = perf_counter()
        try:
            return original_executemany(connection, sql, parameter_rows)
        finally:
            measurements.executemany_calls += 1
            measurements.write_seconds += perf_counter() - started

    def transaction(connection, callback):
        started = perf_counter()
        measurements.transactions += 1
        try:
            return original_transaction(connection, callback)
        finally:
            measurements.transaction_seconds += perf_counter() - started

    def normalize(*args, **kwargs):
        started = perf_counter()
        try:
            return original_normalize(*args, **kwargs)
        finally:
            measurements.normalization_seconds += perf_counter() - started

    DatabaseConnection.execute = execute
    DatabaseConnection.executemany = executemany
    DatabaseConnection.transaction = transaction
    acquisition_module.normalize_job_for_ingestion = normalize
    try:
        yield measurements
    finally:
        DatabaseConnection.execute = original_execute
        DatabaseConnection.executemany = original_executemany
        DatabaseConnection.transaction = original_transaction
        acquisition_module.normalize_job_for_ingestion = original_normalize


def _fixtures(company_count: int, jobs_per_company: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    targets: list[dict[str, object]] = []
    snapshots: list[dict[str, object]] = []
    for company_index in range(company_count):
        company_id = f"benchmark-company-{company_index:04d}"
        target = _target(
            {
                "canonical_company_id": company_id,
                "canonical_company_name": f"Benchmark Company {company_index:04d}",
                "website_url": f"https://company-{company_index}.example",
            },
            SOURCE_EMPLOYER,
        )
        targets.append(target)
        snapshots.append(
            {
                "cycle_id": "benchmark-cycle",
                "task_id": f"benchmark-task-{company_index:04d}",
                "target_id": target["target_id"],
                "source": SOURCE_EMPLOYER,
                "observed_at": "2026-09-30T01:00:00+00:00",
                "jobs": [
                    {
                        "job_id": f"job-{company_index:04d}-{job_index:02d}",
                        "title": f"Engineer {job_index}",
                        "location": "Berlin",
                        "url": f"https://company-{company_index}.example/jobs/{job_index}",
                        "application_url": f"https://company-{company_index}.example/jobs/{job_index}/apply",
                        "description": "Build reliable production services.",
                    }
                    for job_index in range(jobs_per_company)
                ],
                "complete_snapshot": True,
                "valid_snapshot": True,
                "closure_safe": True,
            }
        )
    return targets, snapshots


def _run_mode(
    output_dir: Path,
    mode: str,
    targets: list[dict[str, object]],
    snapshots: list[dict[str, object]],
) -> dict[str, object]:
    store = SqliteAcquisitionStore(output_dir / f"producer-{mode}.sqlite3")
    store.ensure_targets(targets)
    started = perf_counter()
    with _measure_database() as measured:
        if mode == "legacy":
            for snapshot in snapshots:
                store.ingest_snapshot(
                    **{key: value for key, value in snapshot.items() if key != "source"}
                )
        else:
            for offset in range(0, len(snapshots), 50):
                store.ingest_snapshots_bulk(snapshots[offset : offset + 50])
    elapsed = perf_counter() - started
    companies = len(snapshots)
    jobs = sum(len(snapshot["jobs"]) for snapshot in snapshots)
    statement_seconds = measured.read_seconds + measured.write_seconds
    commit_seconds = max(
        0.0,
        measured.transaction_seconds - statement_seconds - measured.normalization_seconds,
    )
    return {
        "elapsed_seconds": round(elapsed, 6),
        "companies_per_minute": round(companies * 60 / elapsed, 3),
        "jobs_per_minute": round(jobs * 60 / elapsed, 3),
        "database": {
            "transactions": measured.transactions,
            "execute_calls": measured.execute_calls,
            "executemany_calls": measured.executemany_calls,
            "statement_calls": measured.execute_calls + measured.executemany_calls,
        },
        "timing_seconds": {
            "normalization": round(measured.normalization_seconds, 6),
            "reads": round(measured.read_seconds, 6),
            "writes": round(measured.write_seconds, 6),
            "commits": round(commit_seconds, 6),
        },
    }


def run_benchmark(*, output_dir: Path, company_count: int = 100, jobs_per_company: int = 2) -> dict[str, Any]:
    if not 1 <= company_count <= 1000:
        raise ValueError("company_count must be between 1 and 1000")
    if not 1 <= jobs_per_company <= 5:
        raise ValueError("jobs_per_company must be between 1 and 5")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    targets, snapshots = _fixtures(company_count, jobs_per_company)
    legacy = _run_mode(output_dir, "legacy", targets, snapshots)
    bulk = _run_mode(output_dir, "bulk", targets, snapshots)
    legacy_calls = int(legacy["database"]["statement_calls"])
    bulk_calls = int(bulk["database"]["statement_calls"])
    return {
        "schema_version": "runr.producer-bulk-benchmark.v1",
        "workload": {
            "companies": company_count,
            "jobs": company_count * jobs_per_company,
            "jobs_per_company": jobs_per_company,
        },
        "modes": {"legacy": legacy, "bulk": bulk},
        "comparison": {
            "throughput_improvement_factor": round(
                float(bulk["companies_per_minute"]) / float(legacy["companies_per_minute"]), 3
            ),
            "statement_call_reduction_factor": round(legacy_calls / max(1, bulk_calls), 3),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--companies", type=int, default=100)
    parser.add_argument("--jobs-per-company", type=int, default=2)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = run_benchmark(
        output_dir=args.output_dir,
        company_count=args.companies,
        jobs_per_company=args.jobs_per_company,
    )
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.report:
        args.report.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
