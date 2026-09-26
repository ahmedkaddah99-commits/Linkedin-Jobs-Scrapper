import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "deploy/vps-observability/observe.py"
spec = importlib.util.spec_from_file_location("vps_observe", MODULE_PATH)
observe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observe)


def healthy_unit(unit):
    return {"query_ok": True, "ActiveState": "active" if unit.endswith(".timer") else "inactive", "UnitFileState": "enabled", "LoadState": "loaded"}


def receipts(tmp_path, status="succeeded", outcome="PARTIAL"):
    for source in observe.SOURCES:
        (tmp_path / f"{source}-latest.json").write_text(json.dumps({
            "status": status, "exit_code": 0 if status == "succeeded" else 1,
            "finished_at": "2026-09-26T02:00:00Z", "metrics": {"run_outcome": outcome},
        }))


def test_partial_is_not_hidden_by_successful_wrapper(tmp_path, monkeypatch):
    receipts(tmp_path)
    monkeypatch.setattr(observe, "unit_state", healthy_unit)
    data = observe.snapshot(tmp_path, now=observe.epoch("2026-09-26T03:00:00Z"))
    assert data["sources"]["linkedin"]["health"] == "degraded"
    assert data["sources"]["linkedin"]["reasons"] == ["collector_partial"]
    assert 'runr_acquisition_last_run_partial{source="linkedin"} 1' in observe.prometheus(data)


def test_mixed_stdout_reads_final_summary_and_redacts_payload(tmp_path):
    metrics = tmp_path / "metrics.json"
    metrics.write_text('log line\n{"jobs_written": 2, "description": "PRIVATE"}\n{\n"jobs_written": 5, "run_outcome": "PARTIAL"\n}\n')
    counts, outcome = observe.summarize(observe.json_objects(metrics))
    assert counts == {"jobs_written": 5}
    assert outcome == "partial"
    assert "PRIVATE" not in json.dumps(counts)


def test_employer_partial_company_statuses_are_not_wrapper_success():
    counts, outcome = observe.summarize([{"company_statuses": {"partial": 4}, "jobs_written": 2612}])
    assert outcome == "partial"
    assert counts["companies_partial_or_failed"] == 4


def test_publisher_degraded_and_no_change_are_distinct_from_failure():
    assert observe.summarize([{"status": "degraded", "report": {"jobs_published": 12}}]) == ({"jobs_published": 12}, "partial")
    assert observe.summarize([{"status": "no_changes"}]) == ({}, "completed")
    assert observe.summarize([{"status": "completed", "run_outcome": "PARTIAL"}])[1] == "partial"


def test_running_progress_cannot_be_taken_from_an_earlier_run(tmp_path, monkeypatch):
    receipts(tmp_path)
    def states(unit):
        state = healthy_unit(unit)
        if unit == 'runr-acquisition-publisher.service':
            state.update(ActiveState='activating', ExecMainStartTimestamp='Sat 2026-09-26 03:00:00 UTC')
        return state
    monkeypatch.setattr(observe, 'unit_state', states)
    progress = tmp_path / 'publisher-progress.json'
    progress.write_text(json.dumps({'phase': 'delivery', 'timestamp': '2026-09-26T02:00:00Z', 'counts': {'companies_completed': 8}}))
    now = observe.epoch('2026-09-26T03:02:00Z')
    assert observe.snapshot(tmp_path, now=now)['sources']['publisher']['progress'] == {}
    progress.write_text(json.dumps({'phase': 'identity_reconciliation', 'timestamp': '2026-09-26T03:01:00Z', 'counts': {'companies': 17601, 'secret': 'PRIVATE'}}))
    state = observe.snapshot(tmp_path, now=now)['sources']['publisher']
    assert state['running_elapsed_seconds'] == 120
    assert state['progress']['counts'] == {'companies': 17601}
    assert state['progress']['age_seconds'] == 60


def test_read_only_does_not_enable_timers(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(observe, "unit_state", lambda unit: {"query_ok": True, "ActiveState": "inactive", "UnitFileState": "disabled"})
    monkeypatch.setattr(observe, "command", lambda *args: calls.append(args))
    observe.snapshot(tmp_path)
    assert calls == []


def test_guard_repairs_only_dedicated_timers_and_respects_owner_pause(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(observe, "unit_state", lambda unit: {"query_ok": True, "ActiveState": "inactive", "UnitFileState": "disabled"})
    monkeypatch.setattr(observe, "command", lambda *args: (calls.append(args) or (0, "")))
    pause = tmp_path / "pause.json"
    now = observe.epoch("2026-09-26T03:00:00Z")
    data = observe.snapshot(tmp_path, enforce=True, pause_path=pause, now=now)
    assert len(data["repairs"]) == 3
    assert all("cycle" not in call[-1] and "export" not in call[-1] for call in calls)
    calls.clear()
    pause.write_text(json.dumps({"approved_by": "Ahmed Kaddah", "reason": "owner maintenance", "expires_at": "2026-09-26T04:00:00Z"}))
    data = observe.snapshot(tmp_path, enforce=True, pause_path=pause, now=now)
    assert data["paused"] and not calls
    data = observe.snapshot(tmp_path, enforce=True, pause_path=pause, now=now + 7200)
    assert not data["paused"] and len(calls) == 3


def test_missing_or_stale_receipts_and_failures_remain_visible(tmp_path, monkeypatch):
    monkeypatch.setattr(observe, "unit_state", healthy_unit)
    data = observe.snapshot(tmp_path)
    assert "receipt_missing" in data["sources"]["publisher"]["reasons"]
    receipts(tmp_path, status="failed", outcome="failed")
    data = observe.snapshot(tmp_path, now=observe.epoch("2026-09-28T02:00:00Z"))
    assert set(data["sources"]["publisher"]["reasons"]) == {"last_run_failed", "receipt_stale", "collector_failed"}
