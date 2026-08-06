import tempfile
import unittest
from pathlib import Path

from backend.application.production_rollout import build_rollout_health, catalog_user_access
from backend.bootstrap import create_backend


class PhaseIProductionRolloutTests(unittest.TestCase):
    def _backend(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        return create_backend(Path(temporary_directory.name), storage_backend="sqlite", test_mode=True)

    def test_rollout_is_safe_by_default_and_catalog_access_is_open_before_gate(self):
        app = self._backend()
        status = app.get_production_rollout_status()
        self.assertEqual(status["stage"], "preflight")
        self.assertFalse(status["rollout_enabled"])
        self.assertEqual(status["rollout_history"], [])
        self.assertTrue(catalog_user_access(app.repositories.config_store, "user-a"))

    def test_cohort_gate_is_durable_and_excludes_users_outside_selected_cohort(self):
        app = self._backend()
        app.configure_production_rollout(
            {
                "user_cohort_gate_enabled": True,
                "internal_cohort_user_ids": ["internal-user"],
                "selected_cohort_user_ids": ["selected-user"],
            }
        )
        self.assertTrue(catalog_user_access(app.repositories.config_store, "internal-user"))
        self.assertFalse(catalog_user_access(app.repositories.config_store, "selected-user"))
        self.assertFalse(catalog_user_access(app.repositories.config_store, "other-user"))
        with self.assertRaisesRegex(PermissionError, "jobs_catalog_rollout_not_available"):
            app.get_personalized_jobs("other-user")
        app.repositories.config_store.set_value("acquisition.phase_i.stage", "selected_cohort")
        self.assertTrue(catalog_user_access(app.repositories.config_store, "selected-user"))

    def test_rollout_health_alerts_when_catalog_is_missing_or_failed(self):
        app = self._backend()
        health = build_rollout_health(app.repositories.config_store, app.repositories.acquisition_store)
        self.assertEqual(health["state"], "alerting")
        self.assertEqual(health["alerts"][0]["type"], "stale_catalog")

    def test_stage_advancement_requires_measured_source_evidence(self):
        app = self._backend()
        app.configure_production_rollout(
            {
                "production_source_id": "n26_greenhouse",
                "earlier_phases_accepted": True,
                "apply_quality_verified": True,
            }
        )
        with self.assertRaisesRegex(ValueError, "source_measured"):
            app.advance_production_rollout("one_source_production")


if __name__ == "__main__":
    unittest.main()
