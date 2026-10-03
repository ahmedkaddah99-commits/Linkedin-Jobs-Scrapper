"""Representative LinkedIn producer benchmark (offline, read-only).

Measures the producer's parse and SQLite write throughput against the shape of
the preserved historical state (188,206 jobs, 198,491 cards, 198,493 attempts)
without network or provider calls.  Network latency is simulated separately by
``benchmark_linkedin_pipeline.py`` so that CPU/parsing/DB work and I/O wait are
reported independently.

The historical state is opened read-only (or read from a read-only checkpoint
copy); writes are measured against a fresh temporary StateStore so no
historical original is modified.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.master_linkedin_jobs_catalog import (
    StateStore,
    SourceCompanyGroup,
    parse_job_detail,
    parse_search_page,
)
from scripts.benchmark_linkedin_pipeline import (
    BENCHMARK_CONTRACT,
    BENCHMARK_OWNER,
    BENCHMARK_PROFILES,
    BENCHMARK_REVISION,
    BENCHMARK_WINDOW_SECONDS,
    evaluate_benchmark_contract,
    load_thresholds_override,
)

FIXTURES = ROOT / "tests" / "fixtures"


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


def _ro_connect(path: Path) -> sqlite3.Connection:
    uri = "file:" + str(path.resolve()).replace("\\", "/") + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=30)


def report_cardinality(path: Path) -> dict[str, int]:
    connection = _ro_connect(path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        counts: dict[str, int] = {}
        for table in (
            "source_company_groups",
            "jobs",
            "job_company_observations",
            "search_pages",
            "search_cards",
            "detail_attempts",
            "detail_queue",
            "company_scans",
            "lifecycle_events",
            "ownership_exclusions",
        ):
            if table in tables:
                counts[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        counts["table_count"] = len(tables)
        return counts
    finally:
        connection.close()


def benchmark_parse(iterations: int) -> dict[str, Any]:
    search_body = (FIXTURES / "linkedin_job_search_valid.html").read_text(encoding="utf-8")
    detail_body = (FIXTURES / "linkedin_job_detail.html").read_text(encoding="utf-8")
    started = time.perf_counter()
    started_cpu = time.process_time()
    search_cards = 0
    detail_records = 0
    for _ in range(iterations):
        page = parse_search_page(search_body)
        search_cards += len(page.cards) + len(page.malformed_cards)
        detail = parse_job_detail("1234567890", detail_body)
        detail_records += 1 if detail.title or detail.linkedin_job_id else 0
    wall = time.perf_counter() - started
    cpu = time.process_time() - started_cpu
    return {
        "iterations": iterations,
        "search_cards_parsed": search_cards,
        "detail_records_parsed": detail_records,
        "wall_time_seconds": round(wall, 4),
        "cpu_time_seconds": round(cpu, 4),
        "parse_records_per_second": round((search_cards + detail_records) / wall, 2),
        "peak_rss_bytes": _peak_rss_bytes(),
    }


def _sample_catalog_rows(connection: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT row_json FROM job_company_observations LIMIT ?", (limit,)
    ).fetchall()
    return [json.loads(row[0]) for row in rows]


def benchmark_db_writes(rows: list[dict[str, Any]], *, batch_size: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="runr-linkedin-rep-") as tmp:
        store = StateStore(Path(tmp) / "state.db")
        run_id = "benchmark-run"
        store.start_run(run_id, mode="full", input_sha256="benchmark")
        group = SourceCompanyGroup(
            linkedin_company_id="22",
            primary_canonical_company_id="C-001",
            source_company_names=("Acme",),
            source_company_ids=("C-001",),
            source_company_urls=("https://www.linkedin.com/company/acme",),
            primary_slug="acme",
        )
        scan_id = store.start_company_scan(run_id, group)
        started = time.perf_counter()
        started_cpu = time.process_time()
        written = 0
        for index, row in enumerate(rows):
            normalized = dict(row)
            normalized["run_id"] = run_id
            normalized["company_scan_id"] = scan_id
            with store.batch():
                store.upsert_catalog_row(normalized)
                store.record_detail_attempt(run_id, str(row.get("linkedin_job_id") or index), status="SUCCESS")
            written += 1
        wall = time.perf_counter() - started
        cpu = time.process_time() - started_cpu
        store.close()
        return {
            "rows_written": written,
            "batch_size": batch_size,
            "wall_time_seconds": round(wall, 4),
            "cpu_time_seconds": round(cpu, 4),
            "writes_per_second": round(written / wall, 2),
            "peak_rss_bytes": _peak_rss_bytes(),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-db", type=Path, required=True, help="read-only historical LinkedIn state DB")
    parser.add_argument("--write-sample", type=int, default=50000, help="number of historical rows to re-write")
    parser.add_argument("--parse-iterations", type=int, default=20000, help="search+detail parse iterations")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--profile", choices=tuple(BENCHMARK_PROFILES), default="ci-fixture")
    parser.add_argument("--owner", default=BENCHMARK_OWNER)
    parser.add_argument("--revision", default=BENCHMARK_REVISION)
    parser.add_argument(
        "--approval",
        dest="approval_status",
        choices=("not-required", "approved"),
        default="not-required",
        help="required for the vps-authorized-live profile",
    )
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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    state_path = args.state_db
    if not state_path.is_file():
        raise SystemExit(f"state DB not found: {state_path}")

    cardinality = report_cardinality(state_path)
    parse = benchmark_parse(args.parse_iterations)

    connection = _ro_connect(state_path)
    try:
        sample_rows = _sample_catalog_rows(connection, args.write_sample)
    finally:
        connection.close()
    writes = benchmark_db_writes(sample_rows, batch_size=args.batch_size)

    benchmark_contract = evaluate_benchmark_contract(
        profile=args.profile,
        counts={
            # Parse/rewrite throughput is producer-side work. Accepted and
            # published remain zero without a T32-declared approved source;
            # historical rows are observations, not publishable counts.
            "discovered": parse["search_cards_parsed"],
            "parsed": parse["detail_records_parsed"],
            "complete": parse["detail_records_parsed"],
            "accepted": 0,
            "published": 0,
            "duplicate": 0,
            "failed": 0,
        },
        elapsed_seconds=float(parse["wall_time_seconds"]) + float(writes["wall_time_seconds"]),
        cpu_seconds=float(parse["cpu_time_seconds"]) + float(writes["cpu_time_seconds"]),
        rss_bytes=max(
            value for value in (parse.get("peak_rss_bytes"), writes.get("peak_rss_bytes"))
            if value is not None
        ) if parse.get("peak_rss_bytes") is not None or writes.get("peak_rss_bytes") is not None else None,
        browser_requests=0,
        requests=0,
        concurrency=1,
        timeout_seconds=30,
        approval_status=args.approval_status,
        owner=args.owner,
        revision=args.revision,
        accepted_source=args.accepted_source,
        thresholds_override=load_thresholds_override(args.thresholds) if args.thresholds else None,
        minimum_accepted_per_window=args.minimum_accepted_per_window,
    )

    report = {
        "version": "linkedin-representative-benchmark-v2",
        "contract": {
            "name": BENCHMARK_CONTRACT,
            "window_seconds": BENCHMARK_WINDOW_SECONDS,
            "profile": args.profile,
            "owner": args.owner,
            "revision": args.revision,
            "approval": args.approval_status,
            "accepted_source": args.accepted_source,
            "minimum_accepted_per_window": args.minimum_accepted_per_window,
            "ceilings": BENCHMARK_PROFILES[args.profile],
        },
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "state_db_bytes": state_path.stat().st_size,
        "cardinality": cardinality,
        "parse": parse,
        "db_writes": writes,
        "benchmark_contract": benchmark_contract,
        "note": "Offline, read-only against the preserved checkpoint copy. No network or provider calls.",
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
