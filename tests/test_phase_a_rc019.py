import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.bootstrap import create_backend
from tests.test_phase_c_personalized_jobs import _seed_catalog


class IntelligenceRecoveryTests(unittest.TestCase):
    def _app(self, name: str):
        path = Path.cwd() / ".backend_test_tmp" / name
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        os.environ.update(
            {
                "RUNR_TEST_MODE": "1",
                "RUNR_ENV": "test",
                "DATABASE_BACKEND": "sqlite",
                "TURSO_DATABASE_URL": " ",
                "TURSO_AUTH_TOKEN": " ",
            }
        )
        return create_backend(path, storage_backend="sqlite", test_mode=True)

    @staticmethod
    def _key(cache_id: str = "rc019-cache") -> dict[str, str]:
        return {
            "cache_id": cache_id,
            "user_id": "user-1",
            "canonical_job_id": "job-1",
            "job_version_id": "job-version-1",
            "profile_version_id": "profile-1",
            "cv_version_id": "cv-1",
            "evidence_version_id": "evidence-1",
            "evaluator_version": "rc019",
            "input_hash": f"hash-{cache_id}",
            "intelligence_kind": "match",
        }

    def test_expired_claim_requeues_then_fails_at_attempt_limit(self):
        app = self._app("rc019_recovery")
        store = app.repositories.personalized_jobs_store
        store.enqueue_intelligence(self._key())

        first = store.claim_next_intelligence(
            lease_owner="worker-a",
            lease_seconds=300,
            max_attempts=2,
        )
        self.assertEqual(first["attempt_count"], 1)
        with store._connect() as connection:
            connection.execute(
                "UPDATE job_intelligence_queue SET lease_expires_at=? WHERE cache_id=?",
                ("2000-01-01T00:00:00+00:00", "rc019-cache"),
            )

        self.assertEqual(
            store.recover_stale_intelligence(now="2026-09-06T00:00:00+00:00"),
            [{"cache_id": "rc019-cache", "state": "queued", "attempt_count": 1}],
        )
        second = store.claim_next_intelligence(lease_owner="worker-b", max_attempts=2)
        self.assertEqual(second["attempt_count"], 2)
        stale_completion = store.complete_intelligence(
            "rc019-cache",
            state="available",
            payload={"value": "old-attempt"},
            lease_owner=first["lease_owner"],
            lease_token=first["lease_token"],
            attempt_count=first["attempt_count"],
        )
        self.assertFalse(stale_completion["accepted"])
        self.assertEqual(stale_completion["state"], "processing")
        with store._connect() as connection:
            connection.execute(
                "UPDATE job_intelligence_queue SET lease_expires_at=? WHERE cache_id=?",
                ("2000-01-01T00:00:00+00:00", "rc019-cache"),
            )

        self.assertEqual(
            store.recover_stale_intelligence(now="2026-09-06T00:00:00+00:00"),
            [{"cache_id": "rc019-cache", "state": "failed", "attempt_count": 2}],
        )
        self.assertIsNone(store.claim_next_intelligence(lease_owner="worker-c"))
        self.assertEqual(store.get_intelligence_cache(self._key())["state"], "failed")

    def test_completion_requires_current_owner_token_and_attempt(self):
        app = self._app("rc019_completion_fence")
        store = app.repositories.personalized_jobs_store
        store.enqueue_intelligence(self._key())
        claimed = store.claim_next_intelligence(lease_owner="worker-a")

        stale = store.complete_intelligence(
            "rc019-cache",
            state="available",
            payload={"value": "stale"},
            lease_owner="worker-b",
            lease_token=claimed["lease_token"],
            attempt_count=claimed["attempt_count"],
        )
        self.assertFalse(stale["accepted"])
        self.assertEqual(stale["state"], "processing")

        completed = store.complete_intelligence(
            "rc019-cache",
            state="available",
            payload={"value": "current"},
            lease_owner=claimed["lease_owner"],
            lease_token=claimed["lease_token"],
            attempt_count=claimed["attempt_count"],
        )
        self.assertTrue(completed["accepted"])
        self.assertEqual(completed["state"], "available")
        self.assertEqual(completed["queue_state"], "completed")

        replay = store.complete_intelligence(
            "rc019-cache",
            state="failed",
            payload={"value": "late"},
            lease_owner=claimed["lease_owner"],
            lease_token=claimed["lease_token"],
            attempt_count=claimed["attempt_count"],
        )
        self.assertFalse(replay["accepted"])
        self.assertEqual(replay["state"], "available")
        self.assertEqual(store.get_intelligence_cache(self._key())["payload"], {"value": "current"})

    def test_profile_change_supersedes_claimed_task_with_new_immutable_key(self):
        app = self._app("rc019_profile_change")
        _seed_catalog(app)
        app.enqueue_personalized_job_intelligence("user-a", "job-a")
        store = app.repositories.personalized_jobs_store
        old_claim = None
        while old_claim is None:
            candidate = store.claim_next_intelligence(lease_owner="worker-old")
            self.assertIsNotNone(candidate)
            if candidate["intelligence_kind"] == "match":
                old_claim = candidate
                break
            store.complete_intelligence(
                candidate["cache_id"],
                state="available",
                payload={},
                lease_owner=candidate["lease_owner"],
                lease_token=candidate["lease_token"],
                attempt_count=candidate["attempt_count"],
            )

        app.save_personalized_preferences("user-a", {"target_roles": ["operations"]})
        app.enqueue_personalized_job_intelligence("user-a", "job-a")
        with patch.object(type(store), "claim_next_intelligence", return_value=old_claim):
            result = app.process_next_personalized_intelligence(worker_id="worker-old")

        self.assertTrue(result["superseded"])
        self.assertTrue(result["accepted"])
        self.assertEqual(result["state"], "failed")
        old_cache = store.get_intelligence_cache(old_claim)
        self.assertEqual(old_cache["state"], "failed")
        with store._connect() as connection:
            queued_new = connection.execute(
                "SELECT COUNT(*) AS n FROM job_intelligence_queue WHERE state='queued'"
            ).fetchone()["n"]
        self.assertGreaterEqual(queued_new, 1)

    def test_read_only_detail_does_not_enqueue_and_explicit_precompute_is_bounded(self):
        app = self._app("rc019_bounded_precompute")
        _seed_catalog(app)
        app.get_personalized_job_detail("user-a", "job-a")
        store = app.repositories.personalized_jobs_store
        with store._connect() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) AS n FROM job_intelligence_queue").fetchone()["n"],
                0,
            )

        queued = app.enqueue_personalized_job_intelligence("user-a", "job-a")
        self.assertEqual(len(queued["queued_cache_ids"]), 3)
        with store._connect() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) AS n FROM job_intelligence_queue").fetchone()["n"],
                3,
            )


if __name__ == "__main__":
    unittest.main()
