import os
import tempfile
import unittest
from pathlib import Path

from backend.application.personalized_jobs_intelligence import build_match_intelligence
from backend.bootstrap import create_backend
from tests.test_phase_c_personalized_jobs import _seed_catalog


class PhaseEAsyncIntelligenceTests(unittest.TestCase):
    def _backend(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        os.environ.update({"RUNR_TEST_MODE": "1", "RUNR_ENV": "test", "DATABASE_BACKEND": "sqlite", "TURSO_DATABASE_URL": " ", "TURSO_AUTH_TOKEN": " "})
        return create_backend(Path(temporary_directory.name), storage_backend="sqlite", test_mode=True)

    def test_get_returns_pending_without_creating_worker_work(self):
        app = self._backend()
        _seed_catalog(app)
        pending = app.get_personalized_job_detail("user-a", "job-a")
        self.assertEqual(pending["description_intelligence"]["state"], "pending")
        self.assertIsNone(pending["match_intelligence"]["v1"]["score"])
        with app.repositories.personalized_jobs_store._connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) AS n FROM job_intelligence_queue WHERE state='queued'").fetchone()["n"], 0)
        self.assertIsNone(app.process_next_personalized_intelligence())
        available = app.get_personalized_job_detail("user-a", "job-a")
        self.assertEqual(available["match_intelligence"]["state"], "pending")

    def test_profile_revision_changes_input_key_without_mutating_old_result(self):
        app = self._backend()
        _seed_catalog(app)
        app.get_personalized_job_detail("user-a", "job-a")
        first_keys = []
        with app.repositories.personalized_jobs_store._connect() as connection:
            first_keys = [row["cache_id"] for row in connection.execute("SELECT cache_id FROM job_intelligence_cache WHERE intelligence_kind='match'").fetchall()]
        app.save_personalized_preferences("user-a", {"target_roles": ["operations"]})
        app.get_personalized_job_detail("user-a", "job-a")
        with app.repositories.personalized_jobs_store._connect() as connection:
            current_keys = [row["cache_id"] for row in connection.execute("SELECT cache_id FROM job_intelligence_cache WHERE intelligence_kind='match'").fetchall()]
        self.assertEqual(first_keys, [])
        self.assertEqual(current_keys, [])

    def test_deterministic_fixture_exposes_formula_and_truthful_evidence(self):
        row = {"canonical_job_id": "job-fixture", "current_version_id": "version-fixture", "version_number": 1, "content_hash": "fixture-hash", "title": "Operations Analyst", "location": "Berlin"}
        intelligence = {"summary": {"essential_requirements": ["reporting"]}, "structured_description": {"skills": ["SQL"]}}
        profile = {"profile_id": "profile-fixture", "version_id": "profile-fixture:v1", "cv_version_id": "cv:v1", "evidence_version_id": "evidence:v1", "revision": 1, "text": "reporting and SQL", "evidence": [{"id": "e1", "text": "Built reporting in SQL", "status": "verified", "source": "cv"}], "preferences": {}}
        result = build_match_intelligence(row, intelligence, profile, evaluated_at="2026-08-06T00:00:00+00:00")
        self.assertEqual(result["v1"]["score"], 100)
        self.assertEqual(result["v2"]["score"], 90)
        self.assertEqual(result["v2"]["formula"]["evidence_coverage"], 0.2)
        self.assertEqual(result["difference"]["score_delta"], -10)

    def test_free_can_review_evidence_but_rewrite_requires_pro(self):
        app = self._backend()
        _seed_catalog(app)
        with self.assertRaises(PermissionError):
            app.improve_personalized_resume("user-a", "job-a", mode="rewrite", plan_id="free")
        review = app.improve_personalized_resume("user-a", "job-a", mode="review", plan_id="free")
        self.assertTrue(review["entitlement"]["available"])
        self.assertIn("v1_v2_difference", review["evidence"])
        queued = app.improve_personalized_resume("user-a", "job-a", mode="rewrite", plan_id="pro")
        self.assertEqual(queued["state"], "queued")
        self.assertTrue(queued["entitlement"]["available"])


if __name__ == "__main__":
    unittest.main()
