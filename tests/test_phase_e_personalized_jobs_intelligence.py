import tempfile
import unittest
from pathlib import Path

from backend.bootstrap import create_backend
from tests.test_phase_c_personalized_jobs import _seed_catalog


class PhaseEPersonalizedJobsIntelligenceTests(unittest.TestCase):
    def _backend(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        import os

        os.environ.update(
            {
                "RUNR_TEST_MODE": "1",
                "RUNR_ENV": "test",
                "DATABASE_BACKEND": "sqlite",
                "TURSO_DATABASE_URL": " ",
                "TURSO_AUTH_TOKEN": " ",
            }
        )
        return create_backend(Path(temporary_directory.name), storage_backend="sqlite", test_mode=True)

    def test_description_bundle_and_both_match_versions_are_published(self):
        app = self._backend()
        _seed_catalog(app)
        pending = app.get_personalized_job_detail("user-a", "job-a")
        self.assertEqual(pending["description_intelligence"]["provider"], None)
        self.assertEqual(pending["match_intelligence"]["state"], "pending")
        result = app.get_personalized_job_detail("user-a", "job-a")
        self.assertEqual(result["description_intelligence"]["state"], "pending")
        self.assertEqual(result["match_intelligence"]["state"], "pending")
        self.assertIsNone(app.process_next_personalized_intelligence())

    def test_description_generation_is_cached_by_immutable_version(self):
        app = self._backend()
        _seed_catalog(app)
        first = app.get_personalized_job_detail("user-a", "job-a")
        self.assertEqual(first["match_intelligence"]["state"], "pending")
        second = app.get_personalized_job_detail("user-a", "job-a")

        third = app.get_personalized_job_detail("user-a", "job-a")
        self.assertEqual(second["runr_summary"], third["runr_summary"])
        with app.repositories.personalized_jobs_store._connect() as connection:
            rows = connection.execute(
                "SELECT version_id, COUNT(*) AS count FROM job_description_intelligence GROUP BY version_id"
            ).fetchall()
        self.assertEqual([(row["version_id"], row["count"]) for row in rows], [])
        with app.repositories.personalized_jobs_store._connect() as connection:
            cache_rows = connection.execute(
                "SELECT intelligence_kind, COUNT(*) AS count FROM job_intelligence_cache GROUP BY intelligence_kind"
            ).fetchall()
        self.assertEqual([(row["intelligence_kind"], row["count"]) for row in cache_rows], [])


if __name__ == "__main__":
    unittest.main()
