r"""Local warm-path benchmark for the bounded personalized Jobs/Company GETs.

Run with ``.venv\Scripts\python.exe scripts\benchmark_personalized_jobs.py``.
The benchmark is deterministic and never contacts a provider.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.bootstrap import create_backend
from backend.domain.models import utc_now_iso


def seed(app, *, jobs: int = 1000) -> None:
    now = utc_now_iso()
    store = app.repositories.acquisition_store

    def write(connection):
        connection.execute(
            "INSERT INTO canonical_companies VALUES (?, ?, ?, ?, ?, ?)",
            ("bench-company", "Benchmark Labs", "employer", "https://benchmark.example", now, now),
        )
        for index in range(jobs):
            job_id = f"bench-job-{index:05d}"
            version_id = f"bench-version-{index:05d}"
            title = "Operations Analyst" if index % 2 else "Finance Analyst"
            payload = {
                "title": title,
                "location": "Berlin" if index % 3 else "Munich",
                "description": "Analyse reporting and operate a resilient process.",
                "category": "operations" if index % 2 else "finance",
                "work_arrangement": "remote" if index % 4 else "onsite",
                "employment_type": "full_time",
                "experience_level": "entry",
                "salary": {"min": 50000, "max": 70000, "currency": "EUR"},
            }
            apply_url = f"https://jobs.example/benchmark/{index}"
            connection.execute(
                "INSERT INTO canonical_jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (job_id, "bench-company", f"url:{job_id}", title, payload["location"], apply_url, "active", now, now, now, 0, version_id, now, now, f"signature:{job_id}"),
            )
            connection.execute(
                "INSERT INTO job_posting_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (version_id, job_id, 1, f"hash-{job_id}", title, payload["description"], payload["location"], apply_url, f"obs-{job_id}", json.dumps(payload), now),
            )
        connection.execute(
            "INSERT INTO acquisition_publications VALUES (?, ?, ?, ?, ?, ?)",
            ("bench-publication", "bench-cycle", "valid", "[]", now, ""),
        )
        connection.executemany(
            "INSERT INTO acquisition_publication_jobs VALUES (?, ?)",
            [("bench-publication", f"bench-job-{index:05d}") for index in range(jobs)],
        )
        connection.execute("INSERT INTO acquisition_publication_head VALUES (?, ?, ?)", (1, "bench-publication", now))

    store._run_transaction(write)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = min(len(ordered) - 1, round((len(ordered) - 1) * fraction))
    return ordered[position]


def main() -> None:
    os.environ.update({"RUNR_TEST_MODE": "1", "RUNR_ENV": "test", "DATABASE_BACKEND": "sqlite", "TURSO_DATABASE_URL": " ", "TURSO_AUTH_TOKEN": " "})
    with tempfile.TemporaryDirectory(prefix="runr-phase-c-bench-") as directory:
        app = create_backend(Path(directory), storage_backend="sqlite", test_mode=True)
        seed(app)
        app.get_personalized_jobs("benchmark-user", limit=25, filters={"search_text": ["analyst"]})
        app.get_personalized_company_detail("benchmark-user", "bench-company")
        feed_times: list[float] = []
        company_times: list[float] = []
        for _ in range(30):
            started = time.perf_counter()
            app.get_personalized_jobs("benchmark-user", limit=25, filters={"search_text": ["analyst"]})
            feed_times.append((time.perf_counter() - started) * 1000)
            started = time.perf_counter()
            app.get_personalized_company_detail("benchmark-user", "bench-company")
            company_times.append((time.perf_counter() - started) * 1000)
        print(json.dumps({
            "jobs": 1000,
            "iterations": len(feed_times),
            "feed_ms": {"p50": round(statistics.median(feed_times), 2), "p95": round(percentile(feed_times, .95), 2)},
            "company_ms": {"p50": round(statistics.median(company_times), 2), "p95": round(percentile(company_times, .95), 2)},
        }, indent=2))


if __name__ == "__main__":
    main()
