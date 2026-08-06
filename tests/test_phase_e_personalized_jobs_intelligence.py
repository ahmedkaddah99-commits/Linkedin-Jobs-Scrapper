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
        result = app.get_personalized_job_detail("user-a", "job-a")

        self.assertEqual(result["runr_summary"]["overview"], "operations role")
        self.assertEqual(result["original_posting"]["description"], "operations role")
        self.assertEqual(result["original_posting"]["content_hash"], "hash-job-a")
        self.assertEqual(result["description_version"]["id"], "version-job-a")
        self.assertIn("responsibilities", result["structured_description"])
        self.assertIn("v1", result["match_intelligence"])
        self.assertIn("v2", result["match_intelligence"])
        self.assertIsInstance(result["match_intelligence"]["v1"]["score"], int)
        self.assertIsInstance(result["match_intelligence"]["v2"]["score"], int)
        self.assertEqual(result["match_intelligence"]["v1"]["job_version"]["id"], "version-job-a")
        self.assertEqual(result["match_intelligence"]["v2"]["evaluator"]["version"], "phase_e_v2")

    def test_description_generation_is_cached_by_immutable_version(self):
        app = self._backend()
        _seed_catalog(app)
        first = app.get_personalized_job_detail("user-a", "job-a")
        second = app.get_personalized_job_detail("user-a", "job-a")

        self.assertEqual(first["runr_summary"], second["runr_summary"])
        with app.repositories.personalized_jobs_store._connect() as connection:
            rows = connection.execute(
                "SELECT version_id, COUNT(*) AS count FROM job_description_intelligence GROUP BY version_id"
            ).fetchall()
        self.assertEqual([(row["version_id"], row["count"]) for row in rows], [("version-job-a", 1)])


if __name__ == "__main__":
    unittest.main()
