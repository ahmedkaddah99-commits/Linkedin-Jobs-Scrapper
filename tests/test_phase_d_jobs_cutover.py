import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.application.acquisition_scheduler import PhaseAAcquisitionScheduler
from backend.bootstrap import create_backend
from tests.test_phase_c_personalized_jobs import _seed_catalog


class PhaseDJobsCutoverTests(unittest.TestCase):
    def _backend(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        return create_backend(Path(temporary_directory.name), storage_backend="sqlite", test_mode=True)

    def test_real_catalog_projection_has_no_source_or_internal_provenance(self):
        app = self._backend()
        _seed_catalog(app)

        with patch.object(PhaseAAcquisitionScheduler, "run_due_cycle", side_effect=AssertionError("Jobs read acquired")):
            detail = app.get_personalized_job_detail("user-a", "job-a")

        serialized = repr(detail).casefold()
        self.assertNotIn("source_ats", serialized)
        self.assertNotIn("observation_url", serialized)
        self.assertNotIn("provenance_url", serialized)
        self.assertNotIn("canonical_url", serialized)
        self.assertIsNone(detail["apply_url"])
        self.assertEqual(detail["user_facing_url"], "https://boards.greenhouse.io/acme/jobs/a")

    def test_filters_and_saved_search_are_read_or_preference_actions(self):
        app = self._backend()
        _seed_catalog(app)

        with patch.object(PhaseAAcquisitionScheduler, "run_due_cycle", side_effect=AssertionError("Jobs action acquired")):
            app.save_personalized_saved_search("user-a", {"filters": {"location": ["Berlin"]}})
            result = app.get_personalized_jobs("user-a", filters={"location": ["Berlin"]})

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["jobs"][0]["posting_id"], "job-a")


if __name__ == "__main__":
    unittest.main()
