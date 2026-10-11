from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore


class ProductCompletionWaveRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / ".backend_test_tmp" / "product_completion_wave"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = SqliteAcquisitionStore(self.root / "backend.sqlite3")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _cluster(self):
        with self.store._connect() as connection:
            connection.execute(
                """
                INSERT INTO acquisition_duplicate_clusters (
                    cluster_id, state, confidence, reasons_json, review_history_json,
                    rule_version, created_at, updated_at
                ) VALUES (?, 'candidate', 0.8, '[]', '[]', 'duplicate_v1', '2026-08-10T00:00:00Z', '2026-08-10T00:00:00Z')
                """,
                ("cluster-1",),
            )
            connection.execute(
                """
                INSERT INTO acquisition_duplicate_members (
                    cluster_id, canonical_job_id, member_score, member_reasons_json, created_at
                ) VALUES (?, ?, 0.8, '[]', '2026-08-10T00:00:00Z')
                """,
                ("cluster-1", "job-a"),
            )
            connection.execute(
                """
                INSERT INTO acquisition_duplicate_members (
                    cluster_id, canonical_job_id, member_score, member_reasons_json, created_at
                ) VALUES (?, ?, 0.8, '[]', '2026-08-10T00:00:00Z')
                """,
                ("cluster-1", "job-b"),
            )

    def test_duplicate_decision_is_append_only_and_undo_is_report_only(self):
        self._cluster()
        first = self.store.record_admin_duplicate_decision(
            "cluster-1",
            decision="confirmed_duplicate",
            actor_user_id="admin-1",
            reason="same official listing",
            evidence={"observation_ids": ["obs-a", "obs-b"]},
        )
        self.assertEqual(first["decision"]["to_state"], "confirmed_duplicate")
        second = self.store.undo_admin_duplicate_decision(
            "cluster-1",
            actor_user_id="admin-1",
            reason="reopened for review",
            evidence={"source": "admin_review"},
        )
        self.assertEqual(len(second["history"]), 2)
        self.assertEqual(second["decision"]["to_state"], "undone")
        with self.store._connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM acquisition_duplicate_decisions").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM acquisition_duplicate_members").fetchone()[0], 2)

    def test_capability_snapshots_are_idempotent_and_decoded_for_admin(self):
        snapshot = {
            "snapshot_id": "cap-1",
            "connector": "workday",
            "capabilities": {"title": {"state": "supported"}},
            "raw_retention": {"required": True, "admin_only": True},
            "observed_at": "2026-08-10T00:00:00Z",
        }
        self.store.record_connector_capability_snapshot(snapshot)
        self.store.record_connector_capability_snapshot(snapshot)
        rows = self.store.list_admin_connector_capabilities()
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["raw_retention"]["required"])

    def test_remote_projection_batches_preserve_observation_counts(self):
        target = {
            "target_id": "batch_source",
            "target_kind": "ats_connector_validation",
            "display_name": "Batch source",
            "canonical_target_url": "https://boards.greenhouse.io/batch",
            "request_url": "https://boards-api.greenhouse.io/v1/boards/batch/jobs",
            "provenance_url": "https://boards.greenhouse.io/batch",
            "connector": "greenhouse",
            "source_token": "batch",
            "maturity_state": "candidate",
            "enabled": True,
            "publication_enabled": False,
            "config": {},
        }
        self.store.ensure_targets([target])
        jobs = [
            {
                "job_id": f"batch-{index}",
                "title": f"Batch job {index}",
                "job_detail_url": f"https://boards.greenhouse.io/batch/jobs/{index}",
                "location": "Berlin",
                "company": "Batch source",
                "description": "A bounded projection test.",
                "source_ats": "greenhouse",
            }
            for index in range(26)
        ]
        with patch("backend.repositories.sqlite_acquisition.database_target_info", return_value={"target_backend": "libsql"}):
            result = self.store.ingest_snapshot(
                cycle_id="cycle-batch",
                task_id="task-batch",
                target_id="batch_source",
                jobs=jobs,
                complete_snapshot=True,
                valid_snapshot=True,
            )
        self.assertEqual(result["observed"], 26)
        self.assertEqual(result["rejected"], 0)
        self.assertEqual(result["stale_ignored"], 0)
        with self.store._connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM job_source_observations WHERE cycle_id=?", ("cycle-batch",)).fetchone()[0], 26)


if __name__ == "__main__":
    unittest.main()
