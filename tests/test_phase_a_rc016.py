from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.acquisition.manifest import load_phase_a_manifest
from backend.bootstrap import create_backend
from backend.repositories.sqlite_acquisition import AcquisitionLeaseLostError
from backend.testing import create_test_backend


def _target(store, target_id: str) -> dict:
    target = next(item for item in load_phase_a_manifest() if item["target_id"] == target_id)
    store.ensure_targets([target])
    return {**target, "enabled": True}


def test_expired_cycle_is_coalesced_and_stale_task_completion_is_fenced() -> None:
    with tempfile.TemporaryDirectory() as directory:
        app = create_backend(Path(directory), storage_backend="sqlite")
        store = app.repositories.acquisition_store
        target = _target(store, "n26_greenhouse")
        first = store.claim_due_cycle(
            window_key="fixture:day-1",
            lease_owner="worker-a",
            scheduled_at="2026-09-05T00:00:00+00:00",
            lease_seconds=60,
            manifest_version="v1",
            scope_key="phase_a:global",
        )
        store.ensure_cycle_tasks(first["cycle_id"], [target])
        old_task = store.claim_next_task(
            cycle_id=first["cycle_id"],
            lease_owner="worker-a",
            cycle_lease_token=first["lease_token"],
        )
        with store._connect() as connection:
            connection.execute(
                "UPDATE acquisition_cycles SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE cycle_id=?",
                (first["cycle_id"],),
            )
            connection.execute(
                "UPDATE acquisition_tasks SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE task_id=?",
                (old_task["task_id"],),
            )

        second = store.claim_due_cycle(
            window_key="fixture:day-2",
            lease_owner="worker-b",
            scheduled_at="2026-09-06T00:00:00+00:00",
            manifest_version="v1",
            scope_key="phase_a:global",
        )
        assert second["cycle_id"] == first["cycle_id"]
        assert second["lease_token"] != first["lease_token"]
        reclaimed = store.claim_next_task(
            cycle_id=second["cycle_id"],
            lease_owner="worker-b",
            cycle_lease_token=second["lease_token"],
        )
        assert reclaimed["attempt_count"] == 2

        with pytest.raises(AcquisitionLeaseLostError):
            store.complete_task(
                old_task["task_id"],
                status="completed",
                result={"complete_snapshot": True},
                lease_owner="worker-a",
                lease_token=old_task["lease_token"],
                attempt_count=old_task["attempt_count"],
            )

        store.complete_task(
            reclaimed["task_id"],
            status="completed",
            result={"complete_snapshot": True},
            lease_owner="worker-b",
            lease_token=reclaimed["lease_token"],
            attempt_count=reclaimed["attempt_count"],
        )
        store.complete_cycle(
            second["cycle_id"],
            status="completed",
            lease_owner="worker-b",
            lease_token=second["lease_token"],
        )


def test_active_scope_coalesces_next_interval_and_heartbeat_requires_current_token() -> None:
    with tempfile.TemporaryDirectory() as directory:
        app = create_backend(Path(directory), storage_backend="sqlite")
        store = app.repositories.acquisition_store
        cycle = store.claim_due_cycle(
            window_key="fixture:active-day",
            lease_owner="worker-a",
            scheduled_at="2026-09-06T00:00:00+00:00",
            scope_key="phase_a:global",
        )
        assert store.claim_due_cycle(
            window_key="fixture:next-day",
            lease_owner="worker-b",
            scheduled_at="2026-09-07T00:00:00+00:00",
            scope_key="phase_a:global",
        ) is None
        assert store.heartbeat_cycle(
            cycle["cycle_id"],
            lease_owner="worker-a",
            lease_token=cycle["lease_token"],
        )
        assert not store.heartbeat_cycle(
            cycle["cycle_id"],
            lease_owner="worker-a",
            lease_token="stale-token",
        )


def test_retry_checkpoint_uses_bounded_backoff_and_retry_budget() -> None:
    with tempfile.TemporaryDirectory() as directory:
        app = create_backend(Path(directory), storage_backend="sqlite")
        store = app.repositories.acquisition_store
        target = _target(store, "qonto_lever")
        cycle = store.claim_due_cycle(
            window_key="fixture:retry",
            lease_owner="worker-a",
            scheduled_at="2026-09-06T00:00:00+00:00",
            scope_key="phase_a:retry",
        )
        store.ensure_cycle_tasks(cycle["cycle_id"], [target])
        task = store.claim_next_task(
            cycle_id=cycle["cycle_id"],
            lease_owner="worker-a",
            cycle_lease_token=cycle["lease_token"],
            max_attempts=2,
        )
        retry = store.retry_task(
            task["task_id"],
            lease_owner="worker-a",
            lease_token=task["lease_token"],
            attempt_count=task["attempt_count"],
            error_code="transient_fixture",
            error_message="temporary provider failure",
        )
        assert retry["status"] == "retry"
        assert retry["next_attempt_at"]
        assert store.claim_next_task(
            cycle_id=cycle["cycle_id"],
            lease_owner="worker-a",
            cycle_lease_token=cycle["lease_token"],
            max_attempts=2,
        ) is None
        with store._connect() as connection:
            connection.execute(
                "UPDATE acquisition_tasks SET next_attempt_at='2000-01-01T00:00:00+00:00' WHERE task_id=?",
                (task["task_id"],),
            )
        retry_attempt = store.claim_next_task(
            cycle_id=cycle["cycle_id"],
            lease_owner="worker-a",
            cycle_lease_token=cycle["lease_token"],
            max_attempts=2,
        )
        terminal = store.retry_task(
            retry_attempt["task_id"],
            lease_owner="worker-a",
            lease_token=retry_attempt["lease_token"],
            attempt_count=retry_attempt["attempt_count"],
            error_code="transient_fixture",
        )
        assert terminal["status"] == "failed"
        assert terminal["next_attempt_at"] == ""


def test_kill_switch_pauses_one_cycle_and_next_worker_resumes_pending_task() -> None:
    with tempfile.TemporaryDirectory() as directory:
        app = create_test_backend(directory)
        for key, value in {
            "acquisition.phase_a.kill_switch": False,
            "acquisition.phase_a.global_enabled": True,
            "acquisition.phase_a.connector_validation_enabled": True,
            "acquisition.phase_a.scheduler_enabled": True,
        }.items():
            app.repositories.config_store.set_value(key, value)
        for target in load_phase_a_manifest():
            app.repositories.config_store.set_value(
                f"acquisition.phase_a.target.{target['target_id']}.enabled",
                target["target_id"] in {"n26_greenhouse", "qonto_lever"},
            )

        calls: list[str] = []

        class Response:
            status_code = 200
            text = ""

            def __init__(self, url: str):
                self.url = url

            def raise_for_status(self):
                return None

            def json(self):
                return {"jobs": []}

        def requester(url, **kwargs):
            calls.append(url)
            if len(calls) == 1:
                app.repositories.config_store.set_value("acquisition.phase_a.kill_switch", True)
            return Response(url)

        app._acquisition_scheduler.requester = requester
        first = app.run_due_acquisition()
        assert first["cycle"]["status"] == "partial"
        assert len(calls) == 1
        assert any(item["task"]["task_status"] == "pending" for item in first["targets"])

        app.repositories.config_store.set_value("acquisition.phase_a.kill_switch", False)
        second = app.run_due_acquisition(
        )
        assert second["cycle"]["status"] in {"completed", "degraded"}
        assert len(calls) == 2
