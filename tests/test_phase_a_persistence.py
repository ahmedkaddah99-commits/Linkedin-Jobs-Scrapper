import tempfile
import unittest
from pathlib import Path

from backend.acquisition.manifest import load_phase_a_manifest
from backend.bootstrap import create_backend


class PhaseAPersistenceTests(unittest.TestCase):
    def test_cycle_request_observation_version_and_publication_replay_are_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            store = app.repositories.acquisition_store
            manifest = load_phase_a_manifest()
            target = next(item for item in manifest if item["target_id"] == "n26_greenhouse")
            target = {**target, "enabled": True}
            store.ensure_targets(manifest)

            cycle = store.claim_due_cycle(
                window_key="fixture:2026-08-05",
                lease_owner="fixture-worker",
                scheduled_at="2026-08-05T00:00:00+00:00",
            )
            self.assertIsNotNone(cycle)
            cycle_id = cycle["cycle_id"]
            self.assertIsNone(
                store.claim_due_cycle(
                    window_key="fixture:2026-08-05",
                    lease_owner="second-worker",
                    scheduled_at="2026-08-05T00:00:00+00:00",
                )
            )
            store.ensure_cycle_tasks(cycle_id, [target])
            store.ensure_cycle_tasks(cycle_id, [target])
            task = store.claim_next_task(cycle_id=cycle_id, lease_owner="fixture-worker")
            self.assertIsNotNone(task)
            self.assertIsNone(store.claim_next_task(cycle_id=cycle_id, lease_owner="second-worker"))

            request = store.reserve_request(
                cycle_id=cycle_id,
                task_id=task["task_id"],
                target_id=target["target_id"],
                request_url=target["request_url"],
                idempotency_key="fixture:request:n26:1",
                request_limit=2,
            )
            retry = store.reserve_request(
                cycle_id=cycle_id,
                task_id=task["task_id"],
                target_id=target["target_id"],
                request_url=target["request_url"],
                idempotency_key="fixture:request:n26:1",
                request_limit=2,
            )
            self.assertEqual(request["request_id"], retry["request_id"])
            store.complete_request(request["request_id"], status="completed", credits_actual=0, jobs_returned=1)
            store.complete_request(request["request_id"], status="completed", credits_actual=99, jobs_returned=99)

            job = {
                "job_id": "fixture-job-1",
                "title": "Operations Analyst",
                "url": "https://boards.greenhouse.io/n26/jobs/fixture-job-1",
                "location": "Berlin",
                "description": "Fixture posting",
            }
            store.ingest_snapshot(
                cycle_id=cycle_id,
                task_id=task["task_id"],
                target_id=target["target_id"],
                jobs=[job],
                complete_snapshot=True,
                valid_snapshot=True,
            )
            store.ingest_snapshot(
                cycle_id=cycle_id,
                task_id=task["task_id"],
                target_id=target["target_id"],
                jobs=[job],
                complete_snapshot=True,
                valid_snapshot=True,
            )
            publication_id = store.publish_valid_snapshot(cycle_id=cycle_id, valid_target_ids=[target["target_id"]])
            replayed_publication_id = store.publish_valid_snapshot(
                cycle_id=cycle_id, valid_target_ids=[target["target_id"]]
            )
            self.assertEqual(publication_id, replayed_publication_id)
            store.complete_task(
                task["task_id"],
                status="completed",
                result={"complete_snapshot": True, "valid_snapshot": True, "observed": 1, "new": 1},
            )
            store.complete_cycle(cycle_id, status="completed", publication_id=publication_id)
            report = store.get_cycle_report(cycle_id)
            self.assertEqual(report["cycle"]["jobs_published"], 1)
            self.assertEqual(report["targets"][0]["jobs_published"], 1)
            self.assertFalse(report["targets"][0]["valid_empty"])
            self.assertFalse(report["targets"][0]["failed_empty"])

            with store._connect() as connection:
                counts = {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "acquisition_cycles",
                        "acquisition_tasks",
                        "acquisition_requests",
                        "acquisition_budget_reservations",
                        "canonical_jobs",
                        "canonical_job_url_aliases",
                        "job_source_observations",
                        "job_posting_versions",
                        "acquisition_publications",
                        "acquisition_publication_head",
                    )
                }
                actual = connection.execute(
                    "SELECT actual_requests, actual_credits FROM acquisition_cycles WHERE cycle_id = ?",
                    (cycle_id,),
                ).fetchone()

            self.assertEqual(counts, {table: 1 for table in counts})
            self.assertEqual((actual["actual_requests"], actual["actual_credits"]), (1, 0))


if __name__ == "__main__":
    unittest.main()
