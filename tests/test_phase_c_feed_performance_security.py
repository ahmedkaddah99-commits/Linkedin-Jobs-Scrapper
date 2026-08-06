import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.bootstrap import create_backend
from backend.application.acquisition_scheduler import PhaseAAcquisitionScheduler
from tests.test_phase_c_personalized_jobs import _seed_catalog


class PhaseCFeedPerformanceSecurityTests(unittest.TestCase):
    def _backend(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        import os

        os.environ.update({
            "RUNR_TEST_MODE": "1",
            "RUNR_ENV": "test",
            "DATABASE_BACKEND": "sqlite",
            "TURSO_DATABASE_URL": " ",
            "TURSO_AUTH_TOKEN": " ",
        })
        return create_backend(Path(temporary_directory.name), storage_backend="sqlite", test_mode=True)

    def test_two_users_round_trip_without_cross_user_state_or_evaluation_access(self):
        app = self._backend()
        _seed_catalog(app)

        app.save_personalized_preferences("user-a", {"target_roles": ["operations"]})
        app.save_personalized_preferences("user-b", {"target_roles": ["finance"]})
        app.save_personalized_saved_search("user-a", {"filters": {"location": ["Berlin"]}})
        app.save_personalized_saved_search("user-b", {"filters": {"location": ["Munich"]}})

        self.assertEqual(app.get_personalized_preferences("user-a")["preferences"]["target_roles"], ["operations"])
        self.assertEqual(app.get_personalized_preferences("user-b")["preferences"]["target_roles"], ["finance"])
        self.assertEqual(app.get_personalized_saved_search("user-a")["filters"]["location"], ["Berlin"])
        self.assertEqual(app.get_personalized_saved_search("user-b")["filters"]["location"], ["Munich"])

        app.set_personalized_job_state("user-a", "job-a", "saved")
        app.set_personalized_job_state("user-b", "job-a", "hidden")
        app.set_personalized_job_state("user-a", "job-a", "hidden")
        app.set_personalized_job_state("user-a", "job-a", "none")
        app.set_personalized_job_state("user-a", "job-a", "applied")
        app.report_personalized_job("user-a", "job-a", reason_code="wrong_role")
        app.report_personalized_job("user-b", "job-a", reason_code="wrong_location")

        refreshed_a = app.get_personalized_job_detail("user-a", "job-a")
        refreshed_b = app.get_personalized_job_detail("user-b", "job-a")
        self.assertEqual(refreshed_a["user_state"], "applied")
        self.assertEqual(refreshed_b["user_state"], "hidden")
        self.assertEqual(app.get_hidden_personalized_jobs("user-a")["jobs"], [])
        self.assertEqual(app.get_hidden_personalized_jobs("user-b")["jobs"][0]["user_state"], "hidden")

        app.repositories.personalized_jobs_store.save_evaluation(
            "user-a",
            "job-a",
            job_version_id="version-job-a",
            preferences_revision=1,
            evaluator_version="phase_e_v2",
            state="available",
            payload={"match_intelligence": {"state": "available", "score": 99}},
        )
        self.assertEqual(app.get_personalized_job_detail("user-a", "job-a")["match_intelligence"]["score"], 99)
        self.assertEqual(app.get_personalized_job_detail("user-b", "job-a")["match_intelligence"]["state"], "pending")

        with app.repositories.personalized_jobs_store._connect() as connection:
            events = connection.execute(
                "SELECT user_id, canonical_job_id, reason_code FROM personalized_job_events WHERE event_name = 'incorrect_filter_reported' ORDER BY user_id"
            ).fetchall()
            dispositions = connection.execute(
                "SELECT user_id, canonical_job_id, state FROM personalized_job_dispositions ORDER BY user_id"
            ).fetchall()
        self.assertEqual([(row["user_id"], row["reason_code"]) for row in events], [("user-a", "wrong_role"), ("user-b", "wrong_location")])
        self.assertEqual([(row["user_id"], row["state"]) for row in dispositions], [("user-a", "applied"), ("user-b", "hidden")])

    def test_get_paths_are_sql_bounded_and_never_acquire_or_enqueue_models(self):
        app = self._backend()
        _seed_catalog(app)
        store = app.repositories.personalized_jobs_store

        with (
            patch.object(PhaseAAcquisitionScheduler, "run_due_cycle", side_effect=AssertionError("GET started acquisition")),
            patch.object(store, "list_published_job_rows", side_effect=AssertionError("full publication scan")),
            patch.object(store, "enqueue_intelligence", side_effect=AssertionError("GET enqueued intelligence")),
            patch("backend.application.personalized_jobs_service.build_description_intelligence", side_effect=AssertionError("GET generated description")),
            patch("backend.application.personalized_jobs_service.build_match_intelligence", side_effect=AssertionError("GET generated match")),
        ):
            with patch.object(store, "query_published_jobs", side_effect=store.query_published_jobs) as query:
                page = app.get_personalized_jobs("user-a", limit=1, filters={"search_text": ["analyst"]})
                query.assert_called_once()
                self.assertEqual(query.call_args.kwargs["limit"], 1)
                self.assertLessEqual(len(page["jobs"]), 1)
            app.get_personalized_job_detail("user-a", "job-a")
            app.get_personalized_company_detail("user-a", "company-a")
            app.set_personalized_job_state("user-a", "job-a", "hidden")
            app.get_hidden_personalized_jobs("user-a", limit=1)

        public = app.get_personalized_job_detail("user-a", "job-a")
        serialized = repr(public).casefold()
        self.assertNotIn("source_ats", serialized)
        self.assertNotIn("observation_url", serialized)
        self.assertNotIn("provenance_url", serialized)
        self.assertEqual(public["apply_url"], "https://boards.greenhouse.io/acme/jobs/a")


if __name__ == "__main__":
    unittest.main()
