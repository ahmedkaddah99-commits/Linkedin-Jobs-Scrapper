import shutil
import sqlite3
import unittest
from pathlib import Path

from backend.domain.models import (
    ApiTokenRecord,
    ArtifactRecord,
    JobRecord,
    ReviewRecord,
    RunRecord,
    SecretRecord,
    StageResult,
    UserRecord,
    WorkerRecord,
)
from backend.repositories.sqlite_backed import (
    SqliteAuthRepository,
    SqliteArtifactStore,
    SqliteJobStore,
    SqliteReviewStore,
    SqliteRunRepository,
    SqliteSecretStore,
    SqliteWorkerStore,
    SqliteWorkspaceRepository,
)


class SqliteRepositoryTests(unittest.TestCase):
    def _db_path(self, name: str) -> Path:
        path = Path.cwd() / ".backend_test_tmp" / name / "backend.sqlite3"
        if path.parent.exists():
            shutil.rmtree(path.parent, ignore_errors=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path.parent, ignore_errors=True))
        return path

    def test_workspace_repository_seeds_starter_templates_without_default_workspaces(self):
        db_path = self._db_path("sqlite_seed")
        repository = SqliteWorkspaceRepository(db_path)

        template_ids = {item.id for item in repository.list_workflow_templates()}
        workspace_ids = {item.id for item in repository.list_workspaces()}

        self.assertIn("search_apply_v1", template_ids)
        self.assertIn("board_package_v1", template_ids)
        self.assertEqual(workspace_ids, set())

    def test_run_job_artifact_and_review_persistence(self):
        db_path = self._db_path("sqlite_runtime")
        run_repository = SqliteRunRepository(db_path)
        job_store = SqliteJobStore(db_path)
        artifact_store = SqliteArtifactStore(db_path)
        review_store = SqliteReviewStore(db_path)
        auth_repository = SqliteAuthRepository(db_path)
        secret_store = SqliteSecretStore(db_path)
        worker_store = SqliteWorkerStore(db_path)

        run = RunRecord.create(
            workspace_id="custom_workspace",
            workflow_template_id="search_apply_v1",
            requested_by="test",
            max_attempts=2,
        )
        run.status = "queued"
        run.stage_results = [
            StageResult(
                stage_id="seed",
                stage_type="test.seed",
                status="completed",
                started_at="2026-01-01T00:00:00+00:00",
                finished_at="2026-01-01T00:00:01+00:00",
                metrics={"seeded": 1},
                output_keys=["accepted_jobs"],
            )
        ]
        run_repository.save(run)

        claimed_run = run_repository.claim_next_queued()
        self.assertIsNotNone(claimed_run)
        self.assertEqual(claimed_run.status, "running")
        self.assertEqual(claimed_run.attempt_count, 1)

        jobs = [
            JobRecord(job_id="job_1", title="Analyst", company="ACME"),
            JobRecord(job_id="job_2", title="Consultant", company="Beta"),
        ]
        job_store.save_job_set(run.id, "accepted_jobs", jobs)
        job_store.save_blob(run.id, "metrics", {"accepted": 2})

        artifacts = [
            ArtifactRecord(
                artifact_id="artifact_1",
                artifact_type="docx",
                path="generated_docs/file.docx",
                metadata={"job_id": "job_1"},
            )
        ]
        artifact_store.save_artifacts(run.id, artifacts)

        review = ReviewRecord.create(
            run_id=run.id,
            job_id="job_1",
            decision="approved",
            reviewer="tester",
            notes="Looks good",
        )
        review_store.upsert_review(review)
        user = UserRecord.create(email="admin@example.com", role="admin")
        auth_repository.upsert_user(user)
        token = ApiTokenRecord.create(
            user_id=user.user_id,
            name="admin-token",
            token_prefix="bkat_test",
            token_hash="123$abc$def",
            scopes=["admin"],
        )
        auth_repository.upsert_api_token(token)
        secret = SecretRecord.create(name="api_key", provider="stored", secret_value="value")
        secret_store.upsert_secret(secret)
        worker = WorkerRecord.create(worker_id="worker_a", status="idle", host_name="localhost", process_id=1234)
        worker_store.upsert_worker(worker)

        loaded_run = run_repository.get(run.id)
        loaded_jobs = job_store.load_job_set(run.id, "accepted_jobs")
        loaded_metrics = job_store.load_blob(run.id, "metrics", {})
        loaded_artifacts = artifact_store.load_artifacts(run.id)
        loaded_reviews = review_store.list_reviews(run_id=run.id)
        loaded_user = auth_repository.get_user(user.user_id)
        loaded_tokens = auth_repository.list_api_tokens(user_id=user.user_id)
        loaded_secret = secret_store.get_secret(secret.secret_id)
        loaded_workers = worker_store.list_workers()

        self.assertEqual(loaded_run.id, run.id)
        self.assertEqual(len(loaded_run.stage_results), 1)
        self.assertEqual(loaded_run.stage_results[0].stage_id, "seed")
        self.assertEqual([job.job_id for job in loaded_jobs], ["job_1", "job_2"])
        self.assertEqual(job_store.list_job_set_keys(run.id), ["accepted_jobs"])
        self.assertEqual(loaded_metrics["accepted"], 2)
        self.assertEqual(len(loaded_artifacts), 1)
        self.assertEqual(loaded_artifacts[0].artifact_id, "artifact_1")
        self.assertEqual(len(loaded_reviews), 1)
        self.assertEqual(loaded_reviews[0].decision, "approved")
        self.assertEqual(loaded_user.email, "admin@example.com")
        self.assertEqual(len(loaded_tokens), 1)
        self.assertEqual(loaded_secret.name, "api_key")
        self.assertEqual(len(loaded_workers), 1)
        self.assertEqual(loaded_workers[0].worker_id, "worker_a")

        with sqlite3.connect(db_path) as connection:
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
            self.assertIn("schema_migrations", tables)
            self.assertIn("run_stage_results", tables)
            self.assertIn("run_jobs", tables)
            self.assertIn("workers", tables)
            migration_rows = connection.execute("SELECT migration_id FROM schema_migrations").fetchall()
            self.assertEqual([row[0] for row in migration_rows], ["001_runtime_normalization"])
            run_job_rows = connection.execute(
                "SELECT COUNT(*) FROM run_jobs WHERE run_id = ? AND set_key = ?",
                (run.id, "accepted_jobs"),
            ).fetchone()[0]
            self.assertEqual(run_job_rows, 2)


if __name__ == "__main__":
    unittest.main()
