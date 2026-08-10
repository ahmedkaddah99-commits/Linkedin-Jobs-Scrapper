from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.acquisition import reprocessing
from backend.acquisition.reprocessing import build_reprocessing_plan, run_reprocessing
from backend.bootstrap import create_backend
from backend.database.connection import database_session


def _target() -> dict[str, object]:
    return {
        "target_id": "reprocessing_fixture",
        "target_kind": "fixture",
        "display_name": "Reprocessing fixture",
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


def _fixture(root: Path, count: int = 3):
    app = create_backend(root, storage_backend="sqlite")
    store = app.repositories.acquisition_store
    target = _target()
    store.ensure_targets([target])
    cycle = store.claim_due_cycle(window_key="reprocessing:fixture", lease_owner="test", scheduled_at="2026-08-10T00:00:00+00:00")
    store.ensure_cycle_tasks(cycle["cycle_id"], [target])
    task = store.claim_next_task(cycle_id=cycle["cycle_id"], lease_owner="test")
    jobs = [
        {
            "job_id": f"fixture-{index}",
            "title": "Backend Engineer",
            "url": f"https://jobs.example.com/{index}",
            "location": "Berlin",
            "description": f"Build service {index}",
            "company": {"name": "Example", "website": "https://example.com"},
        }
        for index in range(count)
    ]
    store.ingest_snapshot(
        cycle_id=cycle["cycle_id"],
        task_id=task["task_id"],
        target_id=target["target_id"],
        jobs=jobs,
        complete_snapshot=True,
        valid_snapshot=True,
    )
    return store, root / "backend.sqlite3"


class ReprocessingTests(unittest.TestCase):
    def test_bounded_resume_and_rollback_reference_are_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, db_path = _fixture(root)
            first = run_reprocessing(db_path, apply=True, idempotency_key="bounded-fixture", batch_size=1, max_batches=1)
            self.assertEqual(first["status"], "incomplete")
            self.assertEqual(first["reason"], "batch_limit_reached")
            self.assertEqual(first["counts"]["observations"], 1)
            self.assertEqual(first["rollback_reference"]["kind"], "sqlite_backup")
            self.assertTrue(Path(first["rollback_reference"]["path"]).exists())

            resumed = run_reprocessing(db_path, apply=True, idempotency_key="bounded-fixture", batch_size=1, max_batches=10)
            self.assertEqual(resumed["status"], "completed")
            self.assertEqual(resumed["counts"]["observations"], 3)
            replay = run_reprocessing(db_path, apply=True, idempotency_key="bounded-fixture", batch_size=1, max_batches=10)
            self.assertTrue(replay["idempotent_replay"])
            self.assertEqual(replay["counts"], resumed["counts"])
            with store._connect() as connection:
                run = connection.execute(
                    "SELECT status, checkpoint_json, backup_json FROM acquisition_reprocessing_runs WHERE idempotency_key=?",
                    ("bounded-fixture",),
                ).fetchone()
                raw_count = connection.execute("SELECT COUNT(*) AS count FROM job_source_observations").fetchone()["count"]
            self.assertEqual(run["status"], "completed")
            self.assertEqual(len(reprocessing._decode(run["checkpoint_json"], {}).get("failed_observation_ids", [])), 0)
            self.assertEqual(raw_count, 3)
            self.assertEqual(reprocessing._decode(run["backup_json"], {})["rollback_reference"]["kind"], "sqlite_backup")

    def test_one_observation_failure_does_not_rollback_healthy_rows_and_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, db_path = _fixture(root)
            with store._connect() as connection:
                failed_id = str(connection.execute("SELECT observation_id FROM job_source_observations ORDER BY observation_id LIMIT 1").fetchone()["observation_id"])

            original = reprocessing._process_observation
            failed_once = {"value": False}

            def fail_one(connection, row, **kwargs):
                if str(row["observation_id"]) == failed_id and not failed_once["value"]:
                    failed_once["value"] = True
                    raise RuntimeError("fixture observation failure")
                return original(connection, row, **kwargs)

            with patch.object(reprocessing, "_process_observation", side_effect=fail_one):
                first = run_reprocessing(db_path, apply=True, idempotency_key="failure-fixture", batch_size=3, max_batches=10)
            self.assertEqual(first["status"], "incomplete")
            self.assertEqual(first["reason"], "observation_failures_pending")
            self.assertEqual(first["counts"]["observations"], 2)
            self.assertEqual(first["counts"]["failed_observations"], 1)
            with store._connect() as connection:
                failure_events = connection.execute(
                    "SELECT COUNT(*) AS count FROM acquisition_quality_events WHERE warning_code='reprocessing_observation_failed'"
                ).fetchone()["count"]
            self.assertEqual(failure_events, 1)

            resumed = run_reprocessing(db_path, apply=True, idempotency_key="failure-fixture", batch_size=3, max_batches=10)
            self.assertEqual(resumed["status"], "completed")
            self.assertEqual(resumed["counts"]["observations"], 3)
            self.assertEqual(resumed["counts"]["failed_observations"], 0)
            self.assertEqual(resumed["counts"]["failure_references"], 1)
            with store._connect() as connection:
                failure_events = connection.execute(
                    "SELECT COUNT(*) AS count FROM acquisition_quality_events WHERE warning_code='reprocessing_observation_failed'"
                ).fetchone()["count"]
            self.assertEqual(failure_events, 1)

    def test_fresh_running_run_is_not_taken_by_a_second_process_and_stale_run_is_reclaimed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, db_path = _fixture(root, count=0)
            plan = build_reprocessing_plan(db_path)
            with database_session(db_path) as connection:
                reprocessing._start_run(
                    connection,
                    reprocessing_id="concurrent-fixture",
                    idempotency_key="concurrent-fixture",
                    plan=plan,
                    backup={"status": "transaction_safe_additive", "recoverable": False},
                )
            in_progress = run_reprocessing(db_path, apply=True, idempotency_key="concurrent-fixture", stale_after_seconds=3600)
            self.assertEqual(in_progress["status"], "in_progress")

            with database_session(db_path) as connection:
                connection.execute(
                    "UPDATE acquisition_reprocessing_runs SET updated_at=? WHERE reprocessing_id=?",
                    ("2020-01-01T00:00:00+00:00", "concurrent-fixture"),
                )
            reclaimed = run_reprocessing(db_path, apply=True, idempotency_key="concurrent-fixture", stale_after_seconds=1)
            self.assertEqual(reclaimed["status"], "completed")

    def test_direct_claim_cannot_overwrite_a_live_owner_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, db_path = _fixture(root, count=0)
            plan = build_reprocessing_plan(db_path)
            with database_session(db_path) as connection:
                reprocessing._start_run(
                    connection,
                    reprocessing_id="lease-guard-fixture",
                    idempotency_key="lease-guard-fixture",
                    plan=plan,
                    backup={"status": "transaction_safe_additive", "recoverable": False},
                )
                observed = connection.execute(
                    "SELECT updated_at FROM acquisition_reprocessing_runs WHERE reprocessing_id=?",
                    ("lease-guard-fixture",),
                ).fetchone()["updated_at"]
                self.assertTrue(
                    reprocessing._claim_run(
                        connection,
                        reprocessing_id="lease-guard-fixture",
                        lease_token="owner-token",
                        lease_seconds=3600,
                        expected_statuses=("running",),
                        expected_updated_at=observed,
                    )
                )
                self.assertFalse(
                    reprocessing._claim_run(
                        connection,
                        reprocessing_id="lease-guard-fixture",
                        lease_token="intruder-token",
                        lease_seconds=3600,
                        expected_statuses=("running",),
                    )
                )
                connection.execute(
                    "UPDATE acquisition_reprocessing_runs SET lease_expires_at=? WHERE reprocessing_id=?",
                    ("2020-01-01T00:00:00+00:00", "lease-guard-fixture"),
                )
                self.assertTrue(
                    reprocessing._claim_run(
                        connection,
                        reprocessing_id="lease-guard-fixture",
                        lease_token="stale-owner-token",
                        lease_seconds=3600,
                        expected_statuses=("running",),
                    )
                )

    def test_duplicate_finalize_failure_is_recorded_and_resume_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, db_path = _fixture(root, count=0)
            original = reprocessing._store_duplicate_candidates
            with patch.object(reprocessing, "_store_duplicate_candidates", side_effect=RuntimeError("fixture duplicate failure")):
                failed = run_reprocessing(db_path, apply=True, idempotency_key="duplicate-finalize-fixture", max_batches=10)
            self.assertEqual(failed["status"], "failed")
            with store._connect() as connection:
                status = connection.execute(
                    "SELECT status, error_json FROM acquisition_reprocessing_runs WHERE idempotency_key=?",
                    ("duplicate-finalize-fixture",),
                ).fetchone()
            self.assertEqual(status["status"], "failed")
            self.assertEqual(reprocessing._decode(status["error_json"], {})["stage"], "duplicate_or_finalize")

            with patch.object(reprocessing, "_store_duplicate_candidates", side_effect=original):
                resumed = run_reprocessing(db_path, apply=True, idempotency_key="duplicate-finalize-fixture", max_batches=10)
            self.assertEqual(resumed["status"], "completed")


if __name__ == "__main__":
    unittest.main()
