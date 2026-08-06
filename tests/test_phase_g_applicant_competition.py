import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.acquisition.phase_g import (
    PHASE_G_PRODUCTION_ACTIVATED,
    PRIORITY_FORMULA_VERSION,
    applicant_source_gate,
    build_priority,
    normalize_applicant_snapshot,
    parse_applicant_count,
    portal_audit_gate,
)
from backend.bootstrap import create_backend
from backend.acquisition.manifest import load_phase_a_manifest
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

    def test_applicant_sources_remain_blocked_during_initial_audit(self):
        target = {
            "target_kind": "ats_connector_validation",
            "connector": "greenhouse",
            "config": {
                "phase_g_applicant_audit": {
                    "authorization_documented": True,
                    "data_quality_documented": True,
                    "request_cost_documented": True,
                    "unattended_behavior_documented": True,
                    "observation_timestamp_documented": True,
                    "official_apply_destination_documented": True,
                    "no_candidate_data_documented": True,
                },
            },
        }
        gate = applicant_source_gate(target)
        self.assertFalse(PHASE_G_PRODUCTION_ACTIVATED)
        self.assertFalse(gate["approved"])
        self.assertIn("no_applicant_count_field", gate["missing"])
        self.assertIn("production_activation_disabled", gate["missing"])

    def test_snapshot_is_unknown_safe_and_does_not_retain_candidate_payload(self):
        snapshot = normalize_applicant_snapshot(
            {
                "job_id": "job-1",
                "apply_link": "https://jobs.example.test/1",
                "application_method": "direct_apply",
                "candidate_name": "must-not-persist",
            },
            observed_at="2026-08-07T10:00:00+00:00",
            source_ats="greenhouse",
            provenance_url="https://jobs.example.test/1",
        )
        self.assertIsNotNone(snapshot)
        self.assertIsNone(snapshot["exact"])
        self.assertIsNone(snapshot["min"])
        self.assertNotIn("candidate_name", snapshot["payload"])
        self.assertEqual(snapshot["apply_url"], "https://jobs.example.test/1")

    def test_priority_formula_uses_neutral_missing_competition(self):
        row = {"last_verified_at": "2026-08-07T10:00:00+00:00"}
        match = {"v2": {"score": 80}}
        competition = {"freshness": {"state": "pro_only"}}
        result = build_priority(row, match, competition)
        self.assertEqual(result["formula_version"], PRIORITY_FORMULA_VERSION)
        self.assertEqual(result["components"]["competition"], 50.0)
        self.assertEqual(result["components"]["competition_confidence"], "unknown")

    def test_blocked_applicant_evidence_is_not_persisted_during_ordinary_ingest(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite", test_mode=True)
            target = next(item for item in load_phase_a_manifest() if item["target_id"] == "n26_greenhouse")
            store = app.repositories.acquisition_store
            store.ensure_targets([target])
            cycle = store.claim_due_cycle(window_key="phase-g-blocked", lease_owner="test", scheduled_at="now")
            store.ensure_cycle_tasks(cycle["cycle_id"], [{**target, "enabled": True}])
            task = store.claim_next_task(cycle_id=cycle["cycle_id"], lease_owner="test")
            result = store.ingest_snapshot(
                cycle_id=cycle["cycle_id"],
                task_id=task["task_id"],
                target_id=target["target_id"],
                jobs=[{
                    "job_id": "job-with-unapproved-count",
                    "title": "Analyst",
                    "url": "https://boards.greenhouse.io/n26/jobs/1",
                    "apply_link": "https://boards.greenhouse.io/n26/jobs/1",
                    "applicant_count": "12 applicants",
                }],
                complete_snapshot=True,
                valid_snapshot=True,
                observed_at="2026-08-07T10:00:00+00:00",
            )
            self.assertEqual(result["applicant_snapshots_blocked"], 1)
            with store._connect() as connection:
                count = connection.execute("SELECT COUNT(*) FROM job_applicant_snapshots").fetchone()[0]
            self.assertEqual(count, 0)

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
            self.assertEqual(priority["jobs"][0]["priority"]["formula_version"], PRIORITY_FORMULA_VERSION)
            self.assertIn("competition", priority["jobs"][0]["priority"]["components"])


if __name__ == "__main__":
    unittest.main()
