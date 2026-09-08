from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

from scripts.master_employer_jobs_catalog import (
    EmployerCollectionResult,
    EmployerCompany,
    EmployerState,
    RequestAccounting,
    TransportGate,
    run_collection,
)


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

    def tracked_save(state, result):
        real_save(state, result)
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
