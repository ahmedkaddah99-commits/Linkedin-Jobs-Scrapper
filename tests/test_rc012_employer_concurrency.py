from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

from scripts.master_employer_jobs_catalog import (
    EmployerCollectionResult,
    EmployerCompany,
    EmployerState,
    RequestAccounting,
    RequestBudgetExceeded,
    TransportGate,
    run_collection,
)
from scripts.benchmark_linkedin_pipeline import evaluate_benchmark_contract


def _company(identifier: str) -> EmployerCompany:
    return EmployerCompany(
        canonical_company_id=identifier,
        company_name=identifier,
        website_url=f"https://{identifier}.example",
    )


def _source(path: Path, *identifiers: str) -> None:
    path.write_text(
        "canonical_CompanyID,company_name,website_url\n"
        + "".join(f"{identifier},{identifier},https://{identifier}.example\n" for identifier in identifiers),
        encoding="utf-8",
    )


def test_budget_exhaustion_defers_untouched_companies_without_synthetic_scans(tmp_path, monkeypatch):
    import scripts.master_employer_jobs_catalog as catalog

    source = tmp_path / "companies.csv"
    _source(source, "first", "second", "third")
    attempted = []

    def collect(company, limits):
        attempted.append(company.canonical_company_id)
        with limits.transport_gate.http_request(company.website_url):
            pass
        return EmployerCollectionResult(company=company, status="no_jobs", outcome="confirmed_zero")

    monkeypatch.setattr(catalog, "_collect_company_worker", collect)
    result = run_collection(
        input_csv=source, output_dir=tmp_path / "out", limit=3, max_requests=1,
        company_concurrency=1, max_pending=1,
    )
    assert attempted == ["first"]
    assert result["requests"] == 1
    assert result["companies_processed"] == 1
    assert result["companies_deferred_budget"] == 2
    assert result["final_export_completed"] is True
    state = EmployerState(tmp_path / "out" / "master_employer_jobs_state.db")
    try:
        assert not state.company_status(_company("second"))
        assert not state.company_status(_company("third"))
    finally:
        state.close()
    resumed = run_collection(
        input_csv=source, output_dir=tmp_path / "out", limit=3, max_requests=2,
        company_concurrency=1, max_pending=1, recheck_budget=0,
    )
    assert attempted == ["first", "second", "third"]
    assert resumed["rechecks_skipped_budget"] == 1
    assert resumed["companies_processed"] == 2


def test_stalled_company_does_not_block_completed_checkpoint(tmp_path: Path, monkeypatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    source = tmp_path / "companies.csv"
    _source(source, "slow", "fast")
    output_dir = tmp_path / "out"
    slow_started = threading.Event()
    release_slow = threading.Event()
    fast_checkpointed = threading.Event()
    active_lock = threading.Lock()
    active_workers = 0
    peak_workers = 0
    real_save = EmployerState.save

    monkeypatch.setattr(
        catalog,
        "_build_network_clients",
        lambda *_args, **_kwargs: (lambda _url: None, lambda *_args, **_kwargs: None, ""),
    )

    def fake_collect(company, _fetcher, _limits):
        nonlocal active_workers, peak_workers
        with active_lock:
            active_workers += 1
            peak_workers = max(peak_workers, active_workers)
        if company.canonical_company_id == "slow":
            slow_started.set()
            assert release_slow.wait(timeout=5)
        with active_lock:
            active_workers -= 1
        return EmployerCollectionResult(company=company, status="no_jobs", outcome="confirmed_zero")

    def tracked_save(state, result, **kwargs):
        real_save(state, result, **kwargs)
        if result.company.canonical_company_id == "fast":
            fast_checkpointed.set()

    monkeypatch.setattr(catalog, "collect_company", fake_collect)
    monkeypatch.setattr(catalog.EmployerState, "save", tracked_save)

    result_box: list[dict[str, object]] = []

    def run() -> None:
        result_box.append(
            run_collection(
                input_csv=source,
                output_dir=output_dir,
                limit=2,
                resume=False,
                company_concurrency=2,
                max_pending=2,
            )
        )

    worker = threading.Thread(target=run)
    worker.start()
    assert slow_started.wait(timeout=5)
    assert fast_checkpointed.wait(timeout=5)
    release_slow.set()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert result_box[0]["companies_processed"] == 2
    assert result_box[0]["concurrency"]["company_workers"] == 2
    assert peak_workers == 2


def test_transport_accounting_counts_direct_and_proxy_attempts(monkeypatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    calls: list[str] = []

    class FakeSession:
        def __init__(self) -> None:
            self.proxies = {}

        def request(self, _method, _url, **_kwargs):
            calls.append("proxy" if self.proxies else "direct")
            return SimpleNamespace(
                status_code=429 if not self.proxies else 200,
                url="https://example.test/jobs",
                headers={"content-type": "text/html"},
                text="rate limited" if not self.proxies else "ok",
            )

        def close(self) -> None:
            return None

    sessions: list[FakeSession] = []
    monkeypatch.setattr(catalog.requests, "Session", lambda: sessions.append(FakeSession()) or sessions[-1])
    monkeypatch.setattr(catalog, "_webshare_proxy_url", lambda: "http://proxy.example:80")

    accounting = RequestAccounting()
    gate = TransportGate(accounting=accounting, http_concurrency=1, account_concurrency=1, per_origin_concurrency=1)
    _fetcher, request, _proxy = catalog._build_network_clients(2, transport_gate=gate)
    try:
        response = request("https://example.test/jobs")
    finally:
        request.close()

    snapshot = accounting.snapshot()
    assert response.status_code == 200
    assert calls == ["direct", "proxy"]
    assert snapshot["total_attempts"] == 2
    assert snapshot["by_transport"] == {"direct": 1, "webshare": 1}
    assert snapshot["by_kind"] == {"http_attempt": 2}
    assert snapshot["peak_inflight"] == 1


def test_transport_gate_stops_before_dispatch_when_request_budget_is_spent() -> None:
    accounting = RequestAccounting(max_attempts=1)
    gate = TransportGate(accounting=accounting, http_concurrency=1, account_concurrency=1)

    with gate.http_request("https://example.test/first"):
        pass

    try:
        with gate.http_request("https://example.test/second"):
            raise AssertionError("request budget should prevent entering the transport")
    except RequestBudgetExceeded as exc:
        assert exc.max_attempts == 1

    snapshot = accounting.snapshot()
    assert snapshot["total_attempts"] == 1
    assert snapshot["inflight"] == 0


def test_browser_process_gate_is_bounded() -> None:
    accounting = RequestAccounting()
    gate = TransportGate(accounting=accounting, browser_concurrency=1)
    entered = threading.Event()
    release = threading.Event()
    second_entered = threading.Event()

    def first() -> None:
        with gate.browser_process("https://one.example"):
            entered.set()
            assert release.wait(timeout=5)

    def second() -> None:
        assert entered.wait(timeout=5)
        with gate.browser_process("https://two.example"):
            second_entered.set()

    first_thread = threading.Thread(target=first)
    second_thread = threading.Thread(target=second)
    first_thread.start()
    second_thread.start()
    assert entered.wait(timeout=5)
    assert not second_entered.wait(timeout=0.05)
    release.set()
    first_thread.join(timeout=5)
    second_thread.join(timeout=5)
    assert second_entered.is_set()


def test_request_metrics_do_not_use_job_or_target_counts(tmp_path: Path, monkeypatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    source = tmp_path / "companies.csv"
    _source(source, "one")

    monkeypatch.setattr(
        catalog,
        "_build_network_clients",
        lambda *_args, **_kwargs: (lambda _url: None, lambda *_args, **_kwargs: None, ""),
    )
    monkeypatch.setattr(
        catalog,
        "collect_company",
        lambda company, _fetcher, _limits: EmployerCollectionResult(
            company=company,
            jobs=[{"source_job_id": "job-1", "source_provider": "generic", "extraction_method": "json_ld"}],
            targets=[{"counts": {"requests": 999}, "job_count": 999}],
            status="completed",
        ),
    )

    metrics = run_collection(input_csv=source, output_dir=tmp_path / "out", limit=1, resume=False)

    assert metrics["requests"] == 0
    assert metrics["request_accounting"]["total_attempts"] == 0


def test_common_contract_can_classify_employer_lifecycle_counts() -> None:
    result = evaluate_benchmark_contract(
        profile="local-dry-run",
        counts={
            "discovered": 3,
            "parsed": 3,
            "complete": 2,
            "accepted": 2,
            "published": 2,
            "duplicate": 1,
            "failed": 0,
        },
        elapsed_seconds=1.0,
        cpu_seconds=0.5,
        rss_bytes=32 * 1024 * 1024,
        browser_requests=0,
        requests=3,
        concurrency=1,
        timeout_seconds=30,
        accepted_source="approved-employer-source",
        approval_status="approved",
    )

    assert result["status"] == "PASS"
    assert result["window_seconds"] == 300
    assert result["counts"]["duplicate"] == 1


def test_employer_producer_rows_are_not_accepted_counts_without_a_declared_source() -> None:
    result = evaluate_benchmark_contract(
        profile="local-dry-run",
        counts={
            "discovered": 3,
            "parsed": 3,
            "complete": 2,
            "accepted": 2,
            "published": 2,
            "duplicate": 1,
            "failed": 0,
        },
        elapsed_seconds=1.0,
        cpu_seconds=0.5,
        rss_bytes=32 * 1024 * 1024,
        browser_requests=0,
        requests=3,
        concurrency=1,
        timeout_seconds=30,
    )

    assert result["status"] == "FAIL"
    assert "accepted_counts_unsourced" in result["reason_codes"]
    assert result["counts"]["accepted"] == 0
    assert result["counts"]["published"] == 0


class _SharedFakePage:
    active_lock = threading.Lock()
    active = 0
    peak = 0

    def __init__(self, navigation_seconds: float = 0.02) -> None:
        self._navigation_seconds = navigation_seconds
        self.handlers: dict[str, object] = {}

    def on(self, event: str, callback: object) -> None:
        self.handlers[event] = callback

    def route(self, _pattern: object, callback: object) -> None:
        self.route_callback = callback

    def goto(self, *_args: object, **_kwargs: object) -> None:
        with _SharedFakePage.active_lock:
            _SharedFakePage.active += 1
            _SharedFakePage.peak = max(_SharedFakePage.peak, _SharedFakePage.active)
        threading.Event().wait(self._navigation_seconds)
        with _SharedFakePage.active_lock:
            _SharedFakePage.active -= 1
        self.route_callback(
            SimpleNamespace(
                request=SimpleNamespace(url="https://acme.example/careers", resource_type="document"),
                continue_=lambda: None,
                abort=lambda: None,
            )
        )

    def content(self) -> str:
        return '<html><h1>Engineer</h1><script type="application/json">{"jobs":[]}</script></html>'

    def wait_for_timeout(self, *_args: object) -> None:
        return None


class _SharedFakeContext:
    def new_page(self) -> _SharedFakePage:
        return _SharedFakePage()


class _SharedFakeBrowser:
    def new_context(self) -> _SharedFakeContext:
        return _SharedFakeContext()

    def close(self) -> None:
        return None


def _shared_playwright_factory(launches: list[int]):
    class _SharedFakeChromium:
        def launch(self, **_kwargs: object):
            launches.append(1)
            return _SharedFakeBrowser()

    class _SharedFakePlaywright:
        def __init__(self) -> None:
            self.chromium = _SharedFakeChromium()

        def __enter__(self) -> "_SharedFakePlaywright":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    return lambda: _SharedFakePlaywright()


def test_reusable_browser_launches_one_process_for_many_fetches(monkeypatch) -> None:
    import backend.connectors.employer_site_fallbacks as fallbacks

    launches: list[int] = []
    monkeypatch.setattr(fallbacks, "sync_playwright", _shared_playwright_factory(launches))

    session = fallbacks.ReusableBrowser()
    try:
        for _ in range(4):
            result = session.fetch("https://acme.example/careers", timeout_seconds=5, max_requests=5)
            assert result["status"] == "completed"
    finally:
        session.close()

    assert session.launch_count == 1
    assert launches == [1]
    assert not session.is_running()


def test_reusable_browser_serializes_concurrent_host_navigations(monkeypatch) -> None:
    import backend.connectors.employer_site_fallbacks as fallbacks

    launches: list[int] = []
    monkeypatch.setattr(fallbacks, "sync_playwright", _shared_playwright_factory(launches))

    session = fallbacks.ReusableBrowser()
    results: list[dict[str, object]] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            results.append(
                session.fetch("https://acme.example/careers", timeout_seconds=5, max_requests=5)
            )
        except BaseException as exc:  # pragma: no cover - surfaced via assertions
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
    finally:
        session.close()

    assert not errors
    assert len(results) == 4
    assert all(result["status"] == "completed" for result in results)
    assert _SharedFakePage.peak == 1
    assert session.launch_count == 1


def test_per_host_request_budget_enforces_and_observes() -> None:
    from scripts.run_manifested_employer import (
        EmployerPerHostBudgetExceeded,
        PerHostRequestBudget,
    )

    budget = PerHostRequestBudget(2)
    assert budget.admit("https://one.example/first") == "one.example"
    assert budget.admit("https://one.example/second") == "one.example"
    try:
        budget.admit("https://one.example/third")
        raise AssertionError("per-host ceiling should prevent the third same-host request")
    except EmployerPerHostBudgetExceeded as exc:
        assert exc.host == "one.example"
        assert exc.max_requests_per_host == 2
    assert budget.admit("https://two.example/first") == "two.example"
    assert budget.snapshot() == {"one.example": 2, "two.example": 1}

    observer = PerHostRequestBudget(1, enforce=False)
    for _ in range(3):
        observer.admit("https://busy.example/jobs")
    assert observer.snapshot() == {"busy.example": 3}
    assert observer.exceeded_hosts() == ["busy.example"]


def test_employer_fixture_benchmark_distinguishes_lifecycle_stages(tmp_path: Path) -> None:
    import json as json_module

    from scripts.run_manifested_employer import (
        BENCHMARK_STAGE_NAMES,
        run_employer_fixture_benchmark,
    )

    receipt = run_employer_fixture_benchmark(
        output_dir=tmp_path,
        profile="local-dry-run",
        accepted_source="employer-durable-state",
        approval_status="approved",
    )

    assert list(receipt["stages"].keys()) == list(BENCHMARK_STAGE_NAMES)
    assert receipt["benchmark_revision"] == "T38"
    assert receipt["mode"] == "fixture_benchmark"
    assert receipt["window_seconds"] == 300
    assert receipt["elapsed_seconds"] <= receipt["window_seconds"]
    counts = receipt["counts"]
    assert counts["discovered"] >= counts["parsed"] >= counts["complete"]
    assert counts["complete"] >= counts["accepted"] >= counts["published"]
    assert counts["duplicate"] >= 1
    assert counts["accepted"] > 0
    assert counts["failed"] == 0
    attribution = receipt["low_yield_attribution"]
    assert attribution["attributed"] is True
    assert attribution["classes"]["missing_url"] >= 1
    assert attribution["classes"]["data_quality"] >= 2
    assert "discovery:no_career_target_found" in attribution["reason_codes"]["missing_url"]
    evaluation = receipt["contract_evaluation"]
    assert evaluation["status"] == "PASS"
    assert evaluation["window_seconds"] == 300
    assert evaluation["throughput_per_300_seconds"]["accepted"] > 0
    assert receipt["per_host_limits"] == {
        "max_requests_per_host": 25,
        "enforced": True,
    }
    assert receipt["per_host_observed"]["acme-full.example"] >= 1
    assert receipt["per_host_exceeded"] == []
    assert json_module.loads(Path(receipt["receipt_path"]).read_text(encoding="utf-8"))["counts"] == counts


def test_employer_fixture_benchmark_receipt_fails_without_declared_source(tmp_path: Path) -> None:
    from scripts.run_manifested_employer import run_employer_fixture_benchmark

    receipt = run_employer_fixture_benchmark(
        output_dir=tmp_path,
        profile="local-dry-run",
    )

    assert receipt["counts"]["accepted"] == 0
    assert receipt["counts"]["published"] == 0
    evaluation = receipt["contract_evaluation"]
    assert evaluation["status"] == "FAIL"
    assert "accepted_counts_unsourced" in evaluation["reason_codes"]
    assert evaluation["counts_zeroed_by_source_guard"] == ["accepted", "published"]
