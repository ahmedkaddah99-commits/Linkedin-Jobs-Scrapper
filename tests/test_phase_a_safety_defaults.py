import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.acquisition.manifest import load_phase_a_manifest
from backend.bootstrap import create_backend
from backend.worker import WorkerService


class PhaseASafetyDefaultTests(unittest.TestCase):
    def test_disabled_scheduler_poll_is_distinct_and_creates_no_cycle(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            app.repositories.config_store.set_value("acquisition.phase_a.kill_switch", False)

            self.assertEqual(
                app.run_due_acquisition(),
                {"status": "scheduler_disabled", "reason": "phase_a_scheduler_disabled"},
            )
            self.assertEqual(app.list_acquisition_cycles(), [])

    def test_application_and_worker_defaults_cannot_contact_acquisition_sources(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            self.assertEqual(app.run_due_acquisition(), {"status": "kill_switch"})
            self.assertEqual(app.repositories.acquisition_store.list_targets(), [])

            worker = WorkerService(
                application=app,
                worker_id="phase_a_default_worker",
                poll_interval_seconds=0.01,
                scheduled_run_check_interval_seconds=0.01,
            )

            def stop_without_processing(**_kwargs):
                worker.stop()
                return None

            with patch("requests.sessions.Session.request", side_effect=AssertionError("unexpected network request")):
                with patch.object(WorkerService, "process_next", side_effect=stop_without_processing):
                    self.assertEqual(worker.run_loop(max_runs=1), 0)

    def test_manifest_and_default_gates_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            manifest = app._acquisition_scheduler._configured_manifest()
            self.assertTrue(all(not target["enabled"] for target in manifest))
            self.assertTrue(all(str(target.get("disabled_reason") or "").endswith("by_default") for target in manifest))
            self.assertTrue(all(not target["enabled"] for target in load_phase_a_manifest()))
            self.assertEqual(app.run_due_acquisition(), {"status": "kill_switch"})
            self.assertFalse(app.repositories.config_store.get_value("acquisition.phase_a.global_enabled", False))
            self.assertFalse(
                app.repositories.config_store.get_value("acquisition.phase_a.connector_validation_enabled", False)
            )

    def test_ai_enrichment_permission_is_fail_closed_even_when_acquisition_is_explicitly_enabled(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            app.repositories.config_store.set_value("acquisition.phase_a.kill_switch", False)
            app.repositories.config_store.set_value("acquisition.phase_a.global_enabled", True)
            app.repositories.config_store.set_value("acquisition.phase_a.scheduler_enabled", True)
            app.repositories.config_store.set_value("acquisition.phase_a.ai_enrichment_enabled", True)
            self.assertEqual(
                app.run_due_acquisition(),
                {"status": "disabled", "reason": "phase_a_ai_enrichment_not_implemented"},
            )


if __name__ == "__main__":
    unittest.main()
