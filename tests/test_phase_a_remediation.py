from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.acquisition.manifest import load_phase_a_manifest
from backend.bootstrap import create_backend
from backend.testing import create_test_backend


class _Response:
    def __init__(self, *, url: str, payload=None, text: str = ""):
        self.url = url
        self.status_code = 200
        self._payload = payload
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _configure_single_target(app, target_id: str, *, publication_enabled: bool = False) -> None:
    for key, value in {
        "acquisition.phase_a.kill_switch": False,
        "acquisition.phase_a.global_enabled": True,
        "acquisition.phase_a.connector_validation_enabled": True,
        "acquisition.phase_a.scheduler_enabled": True,
        "acquisition.phase_a.publication_enabled": publication_enabled,
    }.items():
        app.repositories.config_store.set_value(key, value)
    for item in load_phase_a_manifest():
        app.repositories.config_store.set_value(
            f"acquisition.phase_a.target.{item['target_id']}.enabled",
            item["target_id"] == target_id,
        )


def _n26_request_count(store, cycle_id: str) -> int:
    with store._connect() as connection:
        return int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM acquisition_requests WHERE cycle_id=? AND target_id='n26_greenhouse'",
                (cycle_id,),
            ).fetchone()["count"]
        )


class PhaseARemediationTests(unittest.TestCase):
    def test_real_request_is_blocked_without_live_network_authorization(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_test_backend(temporary_directory)
            _configure_single_target(app, "n26_greenhouse")
            with patch("backend.connectors.ats_router.requests.get") as request:
                report = app.run_due_acquisition()
            self.assertEqual(report["cycle"]["status"], "degraded")
            request.assert_not_called()
            target = next(item for item in report["targets"] if item["target_id"] == "n26_greenhouse")
            self.assertEqual(target["requests"][0]["status"], "blocked")
            self.assertEqual(target["requests"][0]["error_code"], "dispatch_blocked")

    def test_test_bootstrap_rejects_remote_database_before_repository_creation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.dict(
                os.environ,
                {
                    "RUNR_ENV": "test",
                    "RUNR_TEST_MODE": "1",
                    "DATABASE_BACKEND": "turso",
                    "TURSO_DATABASE_URL": "libsql://redacted.example.turso.io",
                    "TURSO_AUTH_TOKEN": "redacted-token",
                },
                clear=False,
            ):
                with patch("backend.bootstrap._build_repositories") as build:
                    with self.assertRaisesRegex(RuntimeError, "remote/production|non-SQLite"):
                        create_test_backend(temporary_directory)
                build.assert_not_called()

    def test_test_bootstrap_rejects_live_network_authorization(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.dict(
                os.environ,
                {
                    "RUNR_ENV": "test",
                    "RUNR_TEST_MODE": "1",
                    "DATABASE_BACKEND": "sqlite",
                    "TURSO_DATABASE_URL": "",
                    "TURSO_AUTH_TOKEN": "",
                    "RUNR_ACQUISITION_LIVE_NETWORK_ENABLED": "true",
                },
                clear=False,
            ):
                with patch("backend.bootstrap._build_repositories") as build:
                    with self.assertRaisesRegex(RuntimeError, "live acquisition"):
                        create_test_backend(temporary_directory)
                build.assert_not_called()

    def test_keyboard_interrupt_after_dispatch_state_is_recovered_without_duplicate(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_test_backend(temporary_directory)
            _configure_single_target(app, "n26_greenhouse")
            scheduler = app._acquisition_scheduler

            def stop_after_state(name: str):
                if name == "after_durable_dispatch":
                    raise KeyboardInterrupt()

            scheduler.failure_injector = stop_after_state
            with self.assertRaises(KeyboardInterrupt):
                app.run_due_acquisition()

            store = app.repositories.acquisition_store
            with store._connect() as connection:
                before = connection.execute(
                    "SELECT * FROM acquisition_requests WHERE target_id='n26_greenhouse'"
                ).fetchone()
            self.assertEqual(before["status"], "dispatching")
            recovered = store.recover_dispatching_requests()
            self.assertEqual(len(recovered), 1)
            report = store.get_cycle_report(recovered[0]["cycle_id"])
            self.assertEqual(report["cycle"]["status"], "recovery_required")
            self.assertEqual(report["controls"]["uncertain_requests"], 1)
            self.assertEqual(_n26_request_count(store, recovered[0]["cycle_id"]), 1)
            scheduler.failure_injector = None
            scheduler.requester = lambda *args, **kwargs: self.fail("uncertain request was duplicated")
            self.assertIsNone(app.run_due_acquisition())

    def test_explicit_retry_and_release_keep_uncertain_reservations_attributable(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_test_backend(temporary_directory)
            store = app.repositories.acquisition_store
            target = next(item for item in load_phase_a_manifest() if item["target_id"] == "n26_greenhouse")
            store.ensure_targets([target])
            cycle = store.claim_due_cycle(
                window_key="remediation:retry",
                lease_owner="test",
                scheduled_at="2026-08-05T00:00:00+00:00",
            )
            store.ensure_cycle_tasks(cycle["cycle_id"], [{**target, "enabled": True}])
            task = store.claim_next_task(cycle_id=cycle["cycle_id"], lease_owner="test")
            request = store.reserve_request(
                cycle_id=cycle["cycle_id"],
                task_id=task["task_id"],
                target_id=target["target_id"],
                request_url=target["request_url"],
                idempotency_key="remediation:uncertain:1",
                request_limit=2,
            )
            store.mark_request_dispatching(request["request_id"])
            store.recover_dispatching_requests()
            decision = store.decide_uncertain_request(
                request["request_id"], decision="retry", reason="bounded operator retry"
            )
            self.assertEqual(decision["status"], "retry_authorized")
            retry_task = store.claim_next_task(cycle_id=cycle["cycle_id"], lease_owner="test")
            retry_request = store.reserve_request(
                cycle_id=cycle["cycle_id"],
                task_id=retry_task["task_id"],
                target_id=target["target_id"],
                request_url=target["request_url"],
                idempotency_key="remediation:uncertain:2",
                request_limit=2,
            )
            self.assertNotEqual(retry_request["request_id"], request["request_id"])
            with store._connect() as connection:
                reservation = connection.execute(
                    "SELECT status FROM acquisition_budget_reservations WHERE idempotency_key=?",
                    ("remediation:uncertain:1",),
                ).fetchone()
            self.assertEqual(reservation["status"], "retry_authorized")

    def test_failure_boundaries_preserve_explainable_state(self):
        boundary_names = (
            "before_dispatch",
            "during_external_call",
            "after_response_before_result_persistence",
            "during_observation_persistence",
        )
        for boundary in boundary_names:
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as temporary_directory:
                app = create_test_backend(temporary_directory)
                _configure_single_target(app, "n26_greenhouse")
                scheduler = app._acquisition_scheduler

                def requester(url, **kwargs):
                    if boundary == "during_external_call":
                        raise RuntimeError("fixture call interrupted")
                    return _Response(url=url, payload={"jobs": []})

                scheduler.requester = requester
                if boundary != "during_external_call":
                    scheduler.failure_injector = lambda name, expected=boundary: (
                        (_ for _ in ()).throw(RuntimeError("fixture boundary interrupted"))
                        if name == expected
                        else None
                    )
                if boundary == "during_observation_persistence":
                    scheduler.failure_injector = None
                    with patch.object(
                        app.repositories.acquisition_store,
                        "ingest_snapshot",
                        side_effect=RuntimeError("fixture persistence interrupted"),
                    ):
                        report = app.run_due_acquisition()
                else:
                    report = app.run_due_acquisition()
                expected_cycle_status = "degraded" if boundary == "before_dispatch" else "recovery_required"
                self.assertEqual(report["cycle"]["status"], expected_cycle_status)
                target = next(item for item in report["targets"] if item["target_id"] == "n26_greenhouse")
                expected_task_status = "blocked" if boundary == "before_dispatch" else "recovery_required"
                self.assertEqual(target["task"]["task_status"], expected_task_status)
                self.assertEqual(len(target["requests"]), 1)
                expected_request_statuses = {"blocked"} if boundary == "before_dispatch" else {"uncertain", "completed"}
                self.assertIn(target["requests"][0]["status"], expected_request_statuses)

    def test_publication_failure_marks_cycle_recovery_required(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_test_backend(temporary_directory)
            target = next(item for item in load_phase_a_manifest() if item["target_id"] == "n26_greenhouse")
            _configure_single_target(app, "n26_greenhouse", publication_enabled=True)
            scheduler = app._acquisition_scheduler
            scheduler.requester = lambda url, **kwargs: _Response(
                url=url,
                payload={
                    "jobs": [
                        {
                            "id": 1,
                            "title": "Fixture Role",
                            "absolute_url": "https://boards.greenhouse.io/n26/jobs/1",
                            "location": {"name": "Berlin"},
                        }
                    ]
                },
            )
            scheduler.failure_injector = lambda name: (
                (_ for _ in ()).throw(RuntimeError("publication interrupted"))
                if name == "during_publication_creation"
                else None
            )
            with patch.object(
                type(scheduler),
                "_configured_manifest",
                return_value=[{**target, "enabled": True, "publication_enabled": True}],
            ):
                with self.assertRaisesRegex(RuntimeError, "publication interrupted"):
                    app.run_due_acquisition()
            report = app.repositories.acquisition_store.get_latest_report()
            self.assertEqual(report["cycle"]["status"], "recovery_required")
            self.assertFalse(report["publication"]["published"])


if __name__ == "__main__":
    unittest.main()
