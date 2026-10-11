"""Run the bounded, offline RC-002 acquisition baseline.

Every source response is loaded from ``tests/fixtures/rc002`` or an existing
local LinkedIn parser fixture.  The request guard raises if an adapter tries
to use the network.  This command measures the current adapter and SQLite
publication path; it does not estimate production capacity.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Iterator

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.bootstrap import create_backend
from backend.connectors.ats_expansions import fetch_expansion_snapshot, run_fixture_snapshot
from backend.connectors.ats_router import fetch_ats_snapshot
from backend.connectors.generic_jsonld import fetch_generic_snapshot
from scripts.master_linkedin_jobs_catalog import parse_job_detail, parse_search_page


DEFAULT_FIXTURE_DIR = ROOT / "tests" / "fixtures" / "rc002"
LINKEDIN_FIXTURE_DIR = ROOT / "tests" / "fixtures"
BENCHMARK_VERSION = "rc002-offline-v1"


class OfflineResponse:
    def __init__(self, *, payload: Any = None, text: str = "", url: str, status_code: int = 200) -> None:
        self._payload = payload
        self.text = text
        self.url = url
        self.status_code = status_code
        self.encoding = "utf-8"

    def json(self) -> Any:
        if isinstance(self._payload, BaseException):
            raise ValueError("fixture response has no JSON payload")
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            from requests import HTTPError

            raise HTTPError(f"fixture status {self.status_code}")


class FixtureRequester:
    """Deterministic requester used only for adapter calls in this command."""

    def __init__(self, responses: list[OfflineResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url: str, **kwargs: Any) -> OfflineResponse:
        self.calls.append({"url": url, "kwargs": kwargs})
        if not self.responses:
            raise AssertionError(f"fixture requester exhausted for {url}")
        return self.responses.pop(0)


@contextmanager
def network_block() -> Iterator[None]:
    original_request = requests.sessions.Session.request

    def forbidden_request(*_: Any, **__: Any) -> Any:
        raise AssertionError("RC-002 offline benchmark attempted a network request")

    requests.sessions.Session.request = forbidden_request
    try:
        yield
    finally:
        requests.sessions.Session.request = original_request


@contextmanager
def local_database_environment() -> Iterator[None]:
    keys = ("DATABASE_BACKEND", "RUNR_ENV", "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN")
    previous = {key: os.environ.get(key) for key in keys}
    os.environ["DATABASE_BACKEND"] = "sqlite"
    os.environ["RUNR_ENV"] = "test"
    os.environ.pop("TURSO_DATABASE_URL", None)
    os.environ.pop("TURSO_AUTH_TOKEN", None)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


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
        ok = get_memory_info(
            process, ctypes.byref(counters), ctypes.sizeof(counters)
        )
        return int(counters.PeakWorkingSetSize) if ok else None
    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value * (1024 if sys.platform != "darwin" else 1)
    except (ImportError, AttributeError):
        return None


def _tree_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _response_from_json(path: Path, *, url: str, status_code: int = 200) -> OfflineResponse:
    return OfflineResponse(payload=_load_json(path), url=url, status_code=status_code)


def _source_job_key(job: dict[str, Any]) -> str:
    return str(job.get("job_id") or job.get("external_job_id") or job.get("url") or "").strip()


def _is_accepted(job: dict[str, Any]) -> bool:
    return bool(str(job.get("title") or "").strip() and str(job.get("url") or job.get("job_detail_url") or "").strip())


def _fixture_source_jobs(fixture_dir: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    source_results: dict[str, dict[str, Any]] = {}
    all_jobs: list[dict[str, Any]] = []

    greenhouse_url = "https://boards.greenhouse.io/rc002-small"
    greenhouse_requester = FixtureRequester(
        [_response_from_json(fixture_dir / "greenhouse_payload.json", url="https://boards-api.greenhouse.io/v1/boards/rc002-small/jobs?content=true")]
    )
    greenhouse = fetch_ats_snapshot(greenhouse_url, "greenhouse", requester=greenhouse_requester)
    source_results["greenhouse_small"] = {
        **greenhouse,
        "request_count": len(greenhouse_requester.calls),
        "retry_count": 0,
        "detail_request_count": 0,
        "employer_size": "small",
    }
    all_jobs.extend(greenhouse["jobs"])

    lever_url = "https://jobs.lever.co/rc002-large"
    lever_payload = _load_json(fixture_dir / "lever_payload.json")
    large_job_count = int(
        _load_json(fixture_dir / "workload_profiles.json")["fixture_representative"]["size_mix"][
            "large_employer_fixture_jobs"
        ]
    )
    lever_template = dict(lever_payload[0])
    lever_jobs = []
    for index in range(large_job_count):
        job = deepcopy(lever_template)
        job_id = f"rc002-{3001 + index}"
        job["id"] = job_id
        job["text"] = f"Data Analyst {index + 1}"
        job["hostedUrl"] = f"https://jobs.lever.co/rc002-large/{job_id}"
        job["applyUrl"] = f"https://jobs.lever.co/rc002-large/{job_id}/apply"
        lever_jobs.append(job)
    lever_requester = FixtureRequester(
        [OfflineResponse(payload=lever_jobs, url="https://api.lever.co/v0/postings/rc002-large?mode=json")]
    )
    lever = fetch_ats_snapshot(lever_url, "lever", requester=lever_requester)
    source_results["lever_large"] = {
        **lever,
        "request_count": len(lever_requester.calls),
        "retry_count": 0,
        "detail_request_count": 0,
        "employer_size": "large",
    }
    all_jobs.extend(lever["jobs"])

    workday_url = "https://wd5.myworkdaysite.com/en-US/rc002/jobs"
    workday_success = _response_from_json(
        fixture_dir / "workday_payload.json",
        url="https://wd5.myworkdaysite.com/wday/cxs/wd5/jobs/rc002/jobs",
    )
    workday_requester = FixtureRequester(
        [OfflineResponse(url=workday_success.url, status_code=429), workday_success]
    )
    workday = fetch_expansion_snapshot(
        workday_url,
        "workday",
        requester=workday_requester,
        enabled=True,
        max_requests=2,
        max_pages=1,
        max_retries=1,
        sleep_fn=lambda _: None,
    )
    source_results["workday_rate_limited"] = {
        **workday,
        "request_count": len(workday_requester.calls),
        "retry_count": int(workday["recovery"]["retryable_failures"]),
        "detail_request_count": 0,
        "employer_size": "large",
    }
    all_jobs.extend(workday["jobs"])

    recruitee = run_fixture_snapshot(
        "recruitee",
        "https://rc002-recruitee.example.com/api/offers",
        _load_json(fixture_dir / "recruitee_payload.json"),
    )
    source_results["recruitee_fixture"] = {
        **recruitee,
        "request_count": 0,
        "retry_count": 0,
        "detail_request_count": 0,
        "employer_size": "small",
    }
    all_jobs.extend(recruitee["jobs"])

    listing_url = "https://careers.rc002-large.example.com/careers"
    detail_responses = {
        "https://careers.rc002-large.example.com/jobdetail/rc002-6001": OfflineResponse(
            text=(fixture_dir / "generic_job_valid.html").read_text(encoding="utf-8"),
            url=f"{listing_url}/jobdetail/rc002-6001",
        ),
        "https://careers.rc002-large.example.com/jobdetail/rc002-6002": OfflineResponse(
            text=(fixture_dir / "generic_job_malformed.html").read_text(encoding="utf-8"),
            url=f"{listing_url}/jobdetail/rc002-6002",
        ),
    }

    def generic_requester(url: str, **_: Any) -> OfflineResponse:
        if url.rstrip("/") == listing_url.rstrip("/"):
            return OfflineResponse(
                text=(fixture_dir / "generic_listing.html").read_text(encoding="utf-8"),
                url=listing_url,
            )
        return detail_responses[url]

    generic = fetch_generic_snapshot(
        listing_url,
        requester=generic_requester,
        max_job_links=2,
        allowed_hosts=("careers.rc002-large.example.com",),
    )
    generic_requests = list(generic["request_log"])
    source_results["generic_large"] = {
        **generic,
        "request_count": len(generic_requests),
        "retry_count": 0,
        "detail_request_count": max(0, len(generic_requests) - 1),
        "employer_size": "large",
    }
    all_jobs.extend(generic["jobs"])

    linkedin_search = parse_search_page((LINKEDIN_FIXTURE_DIR / "linkedin_job_search_company_scoped.html").read_text())
    linkedin_challenge = parse_search_page((LINKEDIN_FIXTURE_DIR / "linkedin_job_search_challenge.html").read_text())
    linkedin_detail = parse_job_detail(
        "1234567890", (LINKEDIN_FIXTURE_DIR / "linkedin_job_detail.html").read_text()
    )
    parser_summary = {
        "search_cards": len(linkedin_search.cards),
        "malformed_cards": len(linkedin_search.malformed_cards),
        "challenge_pages": int(not linkedin_challenge.is_usable),
        "detail_records": int(bool(linkedin_detail.title and linkedin_detail.linkedin_job_id)),
        "requests_measured": 0,
        "note": "Parser fixtures are local HTML and do not represent HTTP request throughput.",
    }
    return all_jobs, source_results, parser_summary


def _target(source_id: str, name: str, url: str, connector: str, *, publication_enabled: bool = True) -> dict[str, Any]:
    host = url.split("/", 3)[2]
    return {
        "target_id": source_id,
        "target_kind": "employer_career_site",
        "display_name": name,
        "canonical_company_name": name,
        "canonical_target_url": url,
        "request_url": url,
        "provenance_url": url,
        "official_employer_hosts": [host],
        "connector": connector,
        "provider": "rc002_fixture",
        "source_token": source_id,
        "policy_version": "rc002-offline-v1",
        "maturity_state": "ready",
        "enabled": True,
        "publication_enabled": publication_enabled,
        "max_direct_requests": 3,
        "request_mode": "fixture",
        "config": {"absence_grace_attempts": 2},
    }


def _install_trace_counter() -> tuple[dict[str, int], Callable[[], None]]:
    counts = {"total": 0, "write": 0}
    original_connect = sqlite3.connect

    def traced_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection = original_connect(*args, **kwargs)

        def trace(statement: str) -> None:
            normalized = statement.lstrip().upper()
            counts["total"] += 1
            if normalized.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP")):
                counts["write"] += 1

        connection.set_trace_callback(trace)
        return connection

    sqlite3.connect = traced_connect  # type: ignore[assignment]

    def restore() -> None:
        sqlite3.connect = original_connect  # type: ignore[assignment]

    return counts, restore


def _run_publication(root: Path, jobs: list[dict[str, Any]], source_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    with local_database_environment():
        app = create_backend(root, storage_backend="sqlite", test_mode=True)
        counts, restore_trace = _install_trace_counter()
        try:
            store = app.repositories.acquisition_store
            targets = [
                _target("greenhouse_small", "RC-002 Small Greenhouse", "https://boards.greenhouse.io/rc002-small", "greenhouse"),
                _target("lever_large", "RC-002 Large Lever", "https://jobs.lever.co/rc002-large", "lever"),
                _target("workday_rate_limited", "RC-002 Large Workday", "https://wd5.myworkdaysite.com/en-US/rc002/jobs", "workday"),
                _target("recruitee_fixture", "RC-002 Small Recruitee", "https://rc002-recruitee.example.com/api/offers", "recruitee"),
                _target("generic_large", "RC-002 Large Generic", "https://careers.rc002-large.example.com/careers", "career_site"),
            ]
            store.ensure_targets(targets)
            source_to_jobs: dict[str, list[dict[str, Any]]] = {key: [] for key in source_results}
            for job in jobs:
                source = str(job.get("source_ats") or "")
                mapping = {"greenhouse": "greenhouse_small", "lever": "lever_large", "workday": "workday_rate_limited", "recruitee": "recruitee_fixture", "generic_jsonld": "generic_large"}
                source_to_jobs.setdefault(mapping.get(source, "generic_large"), []).append(job)

            cycle = store.claim_due_cycle(
                window_key="rc002:offline:baseline",
                lease_owner="rc002-baseline",
                scheduled_at="2026-09-06T00:00:00+00:00",
            )
            if cycle is None:
                raise RuntimeError("offline baseline cycle was unexpectedly not claimable")
            cycle_id = str(cycle["cycle_id"])
            store.ensure_cycle_tasks(cycle_id, targets)
            valid_target_ids: list[str] = []
            ingest_results: dict[str, dict[str, Any]] = {}
            for target in targets:
                task = store.claim_next_task(cycle_id=cycle_id, lease_owner="rc002-baseline", lease_seconds=300)
                if task is None:
                    raise RuntimeError(f"offline baseline task missing for {target['target_id']}")
                source_id = str(target["target_id"])
                source = source_results[source_id]
                source_jobs = source_to_jobs.get(source_id, [])
                complete = bool(source.get("complete_snapshot"))
                valid = bool(complete and source.get("credible_evidence") and source_jobs)
                result = store.ingest_snapshot(
                    cycle_id=cycle_id,
                    task_id=str(task["task_id"]),
                    target_id=source_id,
                    jobs=source_jobs,
                    complete_snapshot=complete,
                    valid_snapshot=valid,
                    closure_safe=valid,
                    observed_at="2026-09-06T00:00:00+00:00",
                )
                task_status = "completed" if valid else "partial"
                store.complete_task(
                    str(task["task_id"]),
                    status=task_status,
                    result={
                        **result,
                        "complete_snapshot": complete,
                        "valid_snapshot": valid,
                        "credible_evidence": bool(source.get("credible_evidence")),
                    },
                )
                ingest_results[source_id] = {**result, "valid_snapshot": valid, "complete_snapshot": complete}
                if valid:
                    valid_target_ids.append(source_id)

            publication_id = store.publish_valid_snapshot(
                cycle_id=cycle_id,
                valid_target_ids=valid_target_ids,
                origin="scheduled",
                created_by="system",
                scheduled_run_id=cycle_id,
            )
            replay_publication_id = store.publish_valid_snapshot(
                cycle_id=cycle_id,
                valid_target_ids=valid_target_ids,
                origin="scheduled",
                created_by="system",
                scheduled_run_id=cycle_id,
            )
            with store._connect() as connection:
                db_counts = {
                    "canonical_jobs": connection.execute("SELECT COUNT(*) AS count FROM canonical_jobs").fetchone()["count"],
                    "observations": connection.execute("SELECT COUNT(*) AS count FROM job_source_observations").fetchone()["count"],
                    "publications": connection.execute("SELECT COUNT(*) AS count FROM acquisition_publications").fetchone()["count"],
                    "published_jobs": connection.execute("SELECT COUNT(*) AS count FROM acquisition_publication_jobs").fetchone()["count"],
                }
            return {
                "cycle_id": cycle_id,
                "publication_id": publication_id,
                "replay_publication_id": replay_publication_id,
                "replay_same_publication": publication_id == replay_publication_id,
                "valid_target_ids": valid_target_ids,
                "ingest_results": ingest_results,
                "db_counts": db_counts,
                "db_operations": counts,
                "database_path": str(root / "backend.sqlite3"),
            }
        finally:
            restore_trace()


def _checkpoint_recovery(root: Path, fixture_dir: Path) -> dict[str, Any]:
    checkpoint = _load_json(fixture_dir / "interrupted_run.json")
    path = root / "rc002-checkpoint.json"
    path.write_text(json.dumps(checkpoint, sort_keys=True, indent=2), encoding="utf-8")
    loaded = _load_json(path)
    completed = set(loaded["completed_source_ids"])
    remaining = [item for item in loaded["remaining_source_ids"] if item not in completed]
    return {
        "interrupted": True,
        "resumed": True,
        "checkpoint_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "checkpoint_bytes": path.stat().st_size,
        "completed_before_interrupt": len(completed),
        "remaining_after_resume": len(remaining),
        "replayed_completed_sources": 0,
        "recovery_point": "after source task 2",
        "recovery_time_seconds": 0.0,
        "note": "Local checkpoint read/resume drill; not a replacement-host recovery measurement.",
    }


def run_baseline(*, fixture_dir: Path = DEFAULT_FIXTURE_DIR) -> dict[str, Any]:
    fixture_dir = Path(fixture_dir)
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    with tempfile.TemporaryDirectory(prefix="runr-rc002-") as temporary_directory:
        root = Path(temporary_directory)
        with network_block():
            jobs, source_results, parser_summary = _fixture_source_jobs(fixture_dir)
            publication = _run_publication(root, jobs, source_results)
        recovery = _checkpoint_recovery(root, fixture_dir)
        storage_bytes = _tree_bytes(root)
        db_path = Path(publication["database_path"])
        unique_jobs_by_key = {
            _source_job_key(job): job
            for job in jobs
            if _source_job_key(job)
        }
        result = {
            "benchmark_version": BENCHMARK_VERSION,
            "status": "completed",
            "execution": {
                "mode": "offline_fixture_only",
                "python": sys.version.split()[0],
                "platform": sys.platform,
                "country_scope": "Germany",
                "fixture_directory_sha256": hashlib.sha256(
                    "".join(
                        f"{path.relative_to(fixture_dir)}:{hashlib.sha256(path.read_bytes()).hexdigest()}\n"
                        for path in sorted(fixture_dir.rglob("*"))
                        if path.is_file()
                    ).encode("utf-8")
                ).hexdigest(),
                "network_requests_allowed": False,
            },
            "workload_profiles": _load_json(fixture_dir / "workload_profiles.json"),
            "measured_runtime": {
                "companies": 5,
                "source_tasks": 5,
                "raw_jobs": len(jobs),
                "unique_jobs": len(unique_jobs_by_key),
                "accepted_jobs": sum(1 for job in unique_jobs_by_key.values() if _is_accepted(job)),
                "rejected_jobs": sum(1 for job in jobs if not _is_accepted(job)),
                "http_requests": sum(int(item.get("request_count") or 0) for item in source_results.values()),
                "browser_requests": 0,
                "detail_requests": sum(int(item.get("detail_request_count") or 0) for item in source_results.values()),
                "retries": sum(int(item.get("retry_count") or 0) for item in source_results.values()),
                "rate_limited_responses": 1,
                "wall_time_seconds": round(time.perf_counter() - started_wall, 6),
                "cpu_time_seconds": round(time.process_time() - started_cpu, 6),
                "peak_rss_bytes": _peak_rss_bytes(),
                "temporary_storage_bytes": storage_bytes,
                "database_bytes": db_path.stat().st_size if db_path.exists() else 0,
                "db_operations": publication["db_operations"],
            },
            "source_results": {
                key: {
                    "status": str(value.get("status") or ""),
                    "complete_snapshot": bool(value.get("complete_snapshot")),
                    "credible_evidence": bool(value.get("credible_evidence")),
                    "raw_jobs": len(value.get("jobs") or []),
                    "accepted_jobs": sum(1 for job in value.get("jobs") or [] if _is_accepted(job)),
                    "requests": int(value.get("request_count") or 0),
                    "detail_requests": int(value.get("detail_request_count") or 0),
                    "retries": int(value.get("retry_count") or 0),
                    "employer_size": value.get("employer_size"),
                    "warnings": list(value.get("warnings") or []),
                }
                for key, value in source_results.items()
            },
            "parser_fixtures": parser_summary,
            "publication": {
                "published_jobs": publication["db_counts"]["published_jobs"],
                "replay_same_publication": publication["replay_same_publication"],
                "duplicate_publications": int(publication["db_counts"]["publications"] != 1),
                "duplicate_logical_jobs": int(publication["db_counts"]["canonical_jobs"] != publication["db_counts"]["observations"]),
                "database_counts": publication["db_counts"],
            },
            "recovery": recovery,
            "external_cost": {
                "currency": "EUR",
                "offline_fixture_cost": 0.0,
                "measured_provider_cost": 0.0,
                "estimated_provider_cost": None,
                "monthly_budget": None,
                "status": "provider_pricing_and_account_limits_unknown",
            },
            "historical_aggregates": {
                "employer_state_records": 428,
                "employer_jobs": 2612,
                "linkedin_stored_jobs": 188206,
                "linkedin_source_groups": 11896,
                "linkedin_scans": 11921,
                "linkedin_detail_retry_rows": 576,
                "resolver_request_logs": 1475495,
                "resolver_status_999": 987057,
                "resolver_status_429": 328493,
                "source": "RC-001 plan and evidence artifacts; not a runtime measurement",
            },
        }
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-dir", type=Path, default=DEFAULT_FIXTURE_DIR)
    parser.add_argument("--output", type=Path, help="Write the JSON summary to this path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    summary = run_baseline(fixture_dir=args.fixture_dir)
    encoded = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
