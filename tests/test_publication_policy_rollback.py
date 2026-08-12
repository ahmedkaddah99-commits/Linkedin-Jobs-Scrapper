from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.acquisition.manifest import load_phase_a_manifest
from backend.acquisition.publication import (
    RestorePublicationConfirmation,
    StalePublicationHeadError,
)
from backend.bootstrap import create_backend


class PublicationPolicyRollbackTests(unittest.TestCase):
    def _app(self):
        temporary_directory = tempfile.TemporaryDirectory()
        app = create_backend(Path(temporary_directory.name), storage_backend="sqlite")
        self._publication_test_directory = temporary_directory
        return app

    @staticmethod
    def _seed_cycle(store, target, suffix: str, job_number: int) -> tuple[str, str]:
        cycle = store.claim_due_cycle(
            window_key=f"publication-recovery:{suffix}",
            lease_owner="publication-test-worker",
            scheduled_at=f"2026-08-{10 + job_number:02d}T00:00:00+00:00",
        )
        assert cycle is not None
        cycle_id = str(cycle["cycle_id"])
        store.ensure_cycle_tasks(cycle_id, [target])
        task = store.claim_next_task(cycle_id=cycle_id, lease_owner="publication-test-worker")
        assert task is not None
        store.ingest_snapshot(
            cycle_id=cycle_id,
            task_id=str(task["task_id"]),
            target_id=str(target["target_id"]),
            jobs=[
                {
                    "job_id": f"publication-job-{job_number}",
                    "title": f"Publication job {job_number}",
                    "url": f"https://boards.greenhouse.io/n26/jobs/publication-job-{job_number}",
                    "location": "Berlin",
                    "description": "Publication rollback fixture",
                }
            ],
            complete_snapshot=True,
            valid_snapshot=True,
        )
        store.complete_task(
            str(task["task_id"]),
            status="completed",
            result={"complete_snapshot": True, "valid_snapshot": True, "observed": 1, "new": 1},
        )
        return cycle_id, str(target["target_id"])

    def _store_with_target(self):
        app = self._app()
        store = app.repositories.acquisition_store
        target = next(item for item in load_phase_a_manifest() if item["target_id"] == "n26_greenhouse")
        target = {**target, "enabled": True}
        store.ensure_targets(load_phase_a_manifest())
        return app, store, target

    def test_administrator_scheduled_system_and_restored_chains(self):
        app, store, target = self._store_with_target()
        try:
            cycle_one, target_id = self._seed_cycle(store, target, "scheduled", 1)
            scheduled = store.publish_valid_snapshot(
                cycle_id=cycle_one,
                valid_target_ids=[target_id],
                origin="scheduled",
                created_by="system",
                scheduled_run_id=cycle_one,
            )
            first = store.get_public_catalog()["publication"]
            self.assertEqual(first["origin"], "scheduled")
            self.assertEqual(first["created_by"], "system")
            self.assertEqual(first["scheduled_run_id"], cycle_one)
            self.assertEqual(first["previous_publication_id"], "")
            self.assertFalse(first["rollback_available"])
            self.assertEqual(first["rollback_reason"], "no_previous_publication")

            cycle_two, target_id = self._seed_cycle(store, target, "administrator", 2)
            administrator_staging = store.publish_staging_snapshot(
                cycle_id=cycle_two,
                valid_target_ids=[target_id],
                origin="administrator",
                created_by="admin-1",
            )
            staging_read = store.get_staging_catalog(publication_id=administrator_staging)["publication"]
            self.assertEqual(staging_read["origin"], "administrator")
            self.assertEqual(staging_read["created_by"], "admin-1")
            administrator = store.promote_staging_publication(
                administrator_staging,
                expected_previous_publication_id=scheduled,
                origin="administrator",
                created_by="admin-1",
            )
            self.assertEqual(store.get_public_catalog()["publication"]["origin"], "administrator")

            cycle_three, target_id = self._seed_cycle(store, target, "system", 3)
            system_staging = store.publish_staging_snapshot(
                cycle_id=cycle_three,
                valid_target_ids=[target_id],
                origin="system",
                created_by="system-worker",
            )
            system = store.promote_staging_publication(
                system_staging,
                expected_previous_publication_id=administrator,
                origin="system",
                created_by="system-worker",
            )
            self.assertEqual(store.get_public_catalog()["publication"]["origin"], "system")

            restored = store.restore_publication(
                RestorePublicationConfirmation.from_values(
                    target_publication_id=scheduled,
                    expected_head_publication_id=system,
                    actor_user_id="admin-1",
                    confirmation="restore_publication",
                )
            )
            current = store.get_public_catalog()["publication"]
            self.assertEqual(current["publication_id"], restored)
            self.assertEqual(current["origin"], "restored")
            self.assertEqual(current["created_by"], "admin-1")
            self.assertEqual(current["previous_publication_id"], system)
            self.assertTrue(current["rollback_available"])
            admin_read_model = store.get_admin_publication_read_model()
            self.assertEqual(admin_read_model["current_head"]["publication_id"], restored)
            self.assertEqual(admin_read_model["current_head"]["origin"], "restored")
            self.assertTrue(
                any(item["event_type"] == "publication_restored" for item in admin_read_model["audit_events"])
            )
            with store._connect() as connection:
                history = connection.execute(
                    "SELECT publication_id, previous_publication_id FROM acquisition_publications ORDER BY published_at"
                ).fetchall()
            self.assertEqual(
                {str(row["publication_id"]) for row in history}, {scheduled, administrator, system, restored}
            )
            self.assertEqual(
                next(row["previous_publication_id"] for row in history if row["publication_id"] == restored),
                system,
            )
        finally:
            self._publication_test_directory.cleanup()

    def test_restore_target_stale_head_authorization_typed_confirmation_and_immutable_history(self):
        app, store, target = self._store_with_target()
        try:
            cycle_one, target_id = self._seed_cycle(store, target, "restore-target", 4)
            target_publication = store.publish_valid_snapshot(cycle_id=cycle_one, valid_target_ids=[target_id])
            with self.assertRaises(PermissionError):
                RestorePublicationConfirmation.from_values(
                    target_publication_id=target_publication,
                    expected_head_publication_id=target_publication,
                    actor_user_id="",
                    confirmation="restore_publication",
                )
            with self.assertRaises(ValueError):
                RestorePublicationConfirmation.from_values(
                    target_publication_id=target_publication,
                    expected_head_publication_id=target_publication,
                    actor_user_id="admin-1",
                    confirmation="yes",
                )
            with self.assertRaises(KeyError):
                store.restore_publication(
                    RestorePublicationConfirmation.from_values(
                        target_publication_id="missing-publication",
                        expected_head_publication_id=target_publication,
                        actor_user_id="admin-1",
                        confirmation="restore_publication",
                    )
                )
            with self.assertRaises(StalePublicationHeadError):
                store.restore_publication(
                    RestorePublicationConfirmation.from_values(
                        target_publication_id=target_publication,
                        expected_head_publication_id="stale-head",
                        actor_user_id="admin-1",
                        confirmation="restore_publication",
                    )
                )
            restored = store.restore_publication(
                RestorePublicationConfirmation.from_values(
                    target_publication_id=target_publication,
                    expected_head_publication_id=target_publication,
                    actor_user_id="admin-1",
                    confirmation="restore_publication",
                )
            )
            with self.assertRaises(StalePublicationHeadError):
                store.restore_publication(
                    RestorePublicationConfirmation.from_values(
                        target_publication_id=target_publication,
                        expected_head_publication_id=target_publication,
                        actor_user_id="admin-1",
                        confirmation="restore_publication",
                    )
                )
            with store._connect() as connection:
                audit = connection.execute(
                    "SELECT * FROM publication_audit_events WHERE publication_id=?",
                    (restored,),
                ).fetchall()
                self.assertEqual(len(audit), 1)
                with self.assertRaises(sqlite3.DatabaseError):
                    connection.execute(
                        "UPDATE publication_audit_events SET event_type='changed' WHERE event_id=?",
                        (audit[0]["event_id"],),
                    )
                with self.assertRaises(sqlite3.DatabaseError):
                    connection.execute(
                        "DELETE FROM publication_audit_events WHERE event_id=?",
                        (audit[0]["event_id"],),
                    )
        finally:
            self._publication_test_directory.cleanup()

    def test_promote_stale_head_is_rejected_before_mutation(self):
        app, store, target = self._store_with_target()
        try:
            cycle_one, target_id = self._seed_cycle(store, target, "stale-publish-one", 5)
            first = store.publish_valid_snapshot(cycle_id=cycle_one, valid_target_ids=[target_id])
            cycle_two, target_id = self._seed_cycle(store, target, "stale-publish-two", 6)
            staging = store.publish_staging_snapshot(cycle_id=cycle_two, valid_target_ids=[target_id])
            with self.assertRaises(StalePublicationHeadError):
                store.promote_staging_publication(staging, expected_previous_publication_id="not-current")
            self.assertEqual(store.get_public_catalog()["publication"]["publication_id"], first)
            with store._connect() as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT status FROM acquisition_publications WHERE publication_id=?", (staging,)
                    ).fetchone()["status"],
                    "staging",
                )
        finally:
            self._publication_test_directory.cleanup()

    def test_preflight_reports_changes_lifecycle_apply_partial_source_and_report_only_completeness(self):
        app, store, target = self._store_with_target()
        try:
            cycle_id, _ = self._seed_cycle(store, target, "preflight", 7)
            old_snapshot = [
                {
                    "canonical_job_id": "job-a",
                    "title": "A",
                    "company": "Acme",
                    "location": "Berlin",
                    "apply_url": "https://acme.example/a",
                    "lifecycle_state": "active",
                },
                {
                    "canonical_job_id": "job-b",
                    "title": "B",
                    "company": "Acme",
                    "location": "Berlin",
                    "apply_url": "https://acme.example/b",
                    "lifecycle_state": "active",
                },
                {
                    "canonical_job_id": "job-c",
                    "title": "C",
                    "company": "Acme",
                    "location": "Berlin",
                    "apply_url": "https://acme.example/c",
                    "lifecycle_state": "active",
                },
                {
                    "canonical_job_id": "job-e",
                    "title": "E",
                    "company": "Acme",
                    "location": "Berlin",
                    "apply_url": "https://acme.example/e",
                    "lifecycle_state": "closed",
                },
            ]
            with store._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO acquisition_publications (
                        publication_id, cycle_id, status, snapshot_json, published_at, valid_until,
                        previous_publication_id
                    ) VALUES (?, ?, 'valid', ?, ?, '', '')
                    """,
                    ("preflight-old", "preflight-old-cycle", json.dumps(old_snapshot), "2026-08-01T00:00:00+00:00"),
                )
                connection.execute(
                    "UPDATE acquisition_tasks SET status='partial', complete_snapshot=0 WHERE cycle_id=?",
                    (cycle_id,),
                )
            new_snapshot = [
                {
                    "canonical_job_id": "job-a",
                    "title": "A changed",
                    "company": "Acme",
                    "location": "Berlin",
                    "apply_url": "https://acme.example/a",
                    "lifecycle_state": "active",
                },
                {
                    "canonical_job_id": "job-b",
                    "title": "B",
                    "company": "Acme",
                    "location": "Berlin",
                    "apply_url": "https://acme.example/b",
                    "lifecycle_state": "closed",
                },
                {
                    "canonical_job_id": "job-d",
                    "title": "D",
                    "company": "Acme",
                    "location": "",
                    "apply_url": "javascript:void(0)",
                    "lifecycle_state": "active",
                },
                {
                    "canonical_job_id": "job-e",
                    "title": "E",
                    "company": "Acme",
                    "location": "Berlin",
                    "apply_url": "https://acme.example/e",
                    "lifecycle_state": "active",
                },
            ]
            with store._connect() as connection:
                preflight = store._build_publication_preflight(
                    connection,
                    previous_publication_id="preflight-old",
                    next_snapshot=new_snapshot,
                    cycle_id=cycle_id,
                )
            self.assertEqual(preflight["additions"], ["job-d"])
            self.assertEqual(preflight["removals"], ["job-c"])
            self.assertEqual(preflight["changed_jobs"], ["job-a", "job-b", "job-e"])
            self.assertEqual(preflight["closed_jobs"], ["job-b"])
            self.assertEqual(preflight["reopened_jobs"], ["job-e"])
            self.assertEqual(preflight["broken_apply_destinations"], ["job-d"])
            self.assertEqual(len(preflight["partial_source_warnings"]), 1)
            self.assertIn("job-d", preflight["completeness_warnings"])
            self.assertEqual(preflight["blocker_count"], 0)
            self.assertGreater(preflight["warning_count"], 0)
            self.assertTrue(preflight["report_only"])
            self.assertFalse(preflight["missing_apply_is_blocker"])
        finally:
            self._publication_test_directory.cleanup()


if __name__ == "__main__":
    unittest.main()
