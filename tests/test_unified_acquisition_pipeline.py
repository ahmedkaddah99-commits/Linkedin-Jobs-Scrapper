import tempfile
import unittest
from pathlib import Path

from backend.acquisition.reprocessing import run_reprocessing
from backend.acquisition.unified_mapping import map_job_fields
from backend.acquisition.quality import normalize_job_for_ingestion
from backend.bootstrap import create_backend


class UnifiedAcquisitionPipelineTests(unittest.TestCase):
    def test_mapping_preserves_raw_company_fields_and_normalizes_user_filters(self):
        mapping = map_job_fields(
            {
                "title": "Senior Backend Engineer",
                "department": "Engineering",
                "employment_type": "Full-time",
                "workplace_arrangement": "Hybrid",
                "languages": [{"language": "German", "status": "required"}],
                "experience_requirements": "5+ years",
                "description_text": "Required languages: German",
                "company": {
                    "name": "Example GmbH",
                    "website": "https://example.com/",
                    "headcount": "10,001+ employees",
                    "associated_members": "532,620 associated members",
                    "logo_url": "https://example.com/logo.png",
                },
            },
            observed_at="2026-08-10T10:00:00+00:00",
        )
        self.assertEqual(mapping["fields"]["runr_function"]["normalized_value"], "Engineering")
        self.assertEqual(mapping["fields"]["employment_type"]["normalized_value"], "Full-time")
        self.assertEqual(mapping["fields"]["workplace_arrangement"]["normalized_value"], "Hybrid")
        self.assertEqual(mapping["experience"]["minimum_years"], 5)
        self.assertEqual(mapping["languages"][0]["language"], "German")
        self.assertEqual(mapping["company_fields"]["headcount"]["raw_value"], "10,001+ employees")
        self.assertEqual(mapping["company_fields"]["associated_members"]["raw_value"], "532,620 associated members")
        self.assertEqual(mapping["company_fields"]["logo_url"]["normalized_value"], "https://example.com/logo.png")
        self.assertIsNone(mapping["company_fields"]["industry"]["normalized_value"])

    def test_application_destination_taxonomy_is_deterministic(self):
        normalized = map_job_fields(
            {
                "title": "Engineer",
                "url": "https://jobs.example.com/engineer",
                "application_destination": {
                    "classification": "ats_application",
                    "resolved_url": "https://apply.example.com/engineer",
                    "status": "verified",
                },
            },
        )
        self.assertEqual(normalized["application_destination"]["destination_type"], "dedicated_apply")

    def test_reprocessing_is_safe_resumable_and_does_not_merge_false_duplicates(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            app = create_backend(root, storage_backend="sqlite")
            store = app.repositories.acquisition_store
            target = {
                "target_id": "fixture_source",
                "target_kind": "fixture",
                "display_name": "Fixture source",
                "canonical_target_url": "https://jobs.example.com",
                "provenance_url": "https://jobs.example.com",
                "request_url": "https://jobs.example.com/jobs",
                "connector": "career_site",
                "provider": "fixture",
                "source_token": "fixture",
                "policy_version": "test",
                "maturity_state": "ready",
                "enabled": True,
                "publication_enabled": False,
                "max_direct_requests": 1,
                "request_mode": "direct",
                "config": {},
            }
            store.ensure_targets([target])
            with store._connect() as connection:
                quarantined_target = connection.execute(
                    "SELECT enabled, publication_enabled, maturity_state, quarantined, quarantine_reason "
                    "FROM acquisition_targets WHERE target_id = ?",
                    (target["target_id"],),
                ).fetchone()
            self.assertEqual(quarantined_target["enabled"], 0)
            self.assertEqual(quarantined_target["publication_enabled"], 0)
            self.assertEqual(quarantined_target["maturity_state"], "quarantined")
            self.assertEqual(quarantined_target["quarantined"], 1)
            self.assertEqual(quarantined_target["quarantine_reason"], "fixture_or_test_target")
            self.assertEqual(store.list_targets(include_disabled=False), [])
            cycle = store.claim_due_cycle(window_key="fixture:unified", lease_owner="test", scheduled_at="2026-08-10T00:00:00+00:00")
            store.ensure_cycle_tasks(cycle["cycle_id"], [target])
            task = store.claim_next_task(cycle_id=cycle["cycle_id"], lease_owner="test")
            jobs = [
                {"job_id": "a", "title": "Backend Engineer", "url": "https://jobs.example.com/a", "location": "Berlin", "description": "Build APIs", "company": {"name": "Example", "website": "https://example.com", "headcount": "10,001+ employees"}},
                {"job_id": "b", "title": "Backend Engineer", "url": "https://jobs.example.com/b", "location": "Berlin", "description": "Build analytics pipelines", "company": {"name": "Example", "website": "https://example.com", "headcount": "10,001+ employees"}},
            ]
            store.ingest_snapshot(cycle_id=cycle["cycle_id"], task_id=task["task_id"], target_id=target["target_id"], jobs=jobs, complete_snapshot=True, valid_snapshot=True)
            with store._connect() as connection:
                before_raw = connection.execute("SELECT observation_id, raw_payload_json FROM job_source_observations ORDER BY observation_id").fetchall()
                before_versions = connection.execute("SELECT COUNT(*) AS count FROM job_posting_versions").fetchone()["count"]

            db_path = root / "backend.sqlite3"
            first = run_reprocessing(db_path, apply=True, idempotency_key="unified-test-1", batch_size=1)
            self.assertEqual(first["status"], "completed")
            with store._connect() as connection:
                after_first_versions = connection.execute("SELECT COUNT(*) AS count FROM job_posting_versions").fetchone()["count"]
                after_raw = connection.execute("SELECT observation_id, raw_payload_json FROM job_source_observations ORDER BY observation_id").fetchall()
                clusters = connection.execute("SELECT COUNT(*) AS count FROM acquisition_duplicate_clusters").fetchone()["count"]
            self.assertEqual([(row["observation_id"], row["raw_payload_json"]) for row in before_raw], [(row["observation_id"], row["raw_payload_json"]) for row in after_raw])
            self.assertGreaterEqual(after_first_versions, before_versions)
            self.assertEqual(clusters, 0)

            second = run_reprocessing(db_path, apply=True, idempotency_key="unified-test-2", batch_size=1)
            self.assertEqual(second["status"], "completed")
            with store._connect() as connection:
                after_second_versions = connection.execute("SELECT COUNT(*) AS count FROM job_posting_versions").fetchone()["count"]
            self.assertEqual(after_second_versions, after_first_versions)


if __name__ == "__main__":
    unittest.main()
