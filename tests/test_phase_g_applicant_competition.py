import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.acquisition.phase_g import parse_applicant_count, portal_audit_gate
from backend.bootstrap import create_backend
from tests.test_phase_c_personalized_jobs import _seed_catalog


class PhaseGApplicantCompetitionTests(unittest.TestCase):
    def test_count_parser_preserves_exact_and_range_semantics(self):
        self.assertEqual(parse_applicant_count("123 applicants")["exact"], 123)
        self.assertEqual(
            parse_applicant_count("over 100 applicants"),
            {"exact": None, "min": 100, "max": None, "label": "over 100 applicants", "kind": "range"},
        )
        self.assertEqual(parse_applicant_count("100-200 applicants")["max"], 200)

    def test_portal_requires_authorization_blocking_cost_and_quality_audits(self):
        target = {"target_kind": "portal", "connector": "linkedin", "config": {}}
        self.assertFalse(portal_audit_gate(target)["approved"])
        target["config"] = {
            "phase_g_audit": {
                "status": "passed",
                "authorization_passed": True,
                "blocking_passed": True,
                "request_cost_passed": True,
                "data_quality_passed": True,
            }
        }
        self.assertTrue(portal_audit_gate(target)["approved"])
        self.assertTrue(portal_audit_gate({"target_kind": "ats_connector_validation", "connector": "greenhouse"})["approved"])

    def test_projection_redacts_exact_count_for_free_and_exposes_it_for_paid(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite", test_mode=True)
            _seed_catalog(app)
            now = datetime.now(timezone.utc)
            first = (now - timedelta(days=2)).isoformat()
            latest = now.isoformat()

            def write(connection):
                rows = [
                    ("snap-first", "job-a", "obs-first", 12, 12, 12, "12 applicants", first),
                    ("snap-latest", "job-a", "obs-latest", 40, 40, 40, "40 applicants", latest),
                ]
                connection.executemany(
                    """
                    INSERT INTO job_applicant_snapshots (
                        snapshot_id, canonical_job_id, source_observation_id, source_ats,
                        applicant_count_exact, applicant_count_min, applicant_count_max,
                        applicant_count_label, posting_time, first_seen_at, last_verified_at,
                        observed_at, apply_method, easy_apply_marker, freshness_status,
                        provenance_url, payload_json, created_at
                    ) VALUES (?, ?, ?, 'greenhouse', ?, ?, ?, ?, '', '', ?, ?, 'direct_apply', 0, 'fresh',
                              'https://boards.greenhouse.io/acme/jobs/a', ?, ?)
                    """,
                    [(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[7], json.dumps({}), row[7]) for row in rows],
                )

            app.repositories.acquisition_store._run_transaction(write)
            free = app.get_personalized_jobs("free-user")
            paid = app.get_personalized_jobs("paid-user", plan_id="pro")
            free_job = next(job for job in free["jobs"] if job["canonical_job_id"] == "job-a")
            paid_job = next(job for job in paid["jobs"] if job["canonical_job_id"] == "job-a")
            free_competition = free_job["applicant_intelligence"]
            paid_competition = paid_job["applicant_intelligence"]
            self.assertIsNone(free_competition["latest"]["count"])
            self.assertEqual(paid_competition["latest"]["count"], 40)
            self.assertEqual(paid_competition["pro"]["change"]["delta"], 28)
            self.assertEqual(paid_competition["pro"]["snapshot_count"], 2)
            self.assertEqual(paid_job["applicant_intelligence"]["apply_method"], "direct_apply")

            priority = app.get_personalized_jobs("paid-user", filters={"sort": "priority"}, plan_id="pro")
            self.assertEqual(priority["filters"]["sort"], "priority")
            self.assertIsNotNone(priority["jobs"][0]["priority"]["score"])
            self.assertIn("applicant_growth", priority["jobs"][0]["priority"]["components"])
            self.assertIn("sponsorship", priority["jobs"][0]["priority"]["components"])


if __name__ == "__main__":
    unittest.main()
