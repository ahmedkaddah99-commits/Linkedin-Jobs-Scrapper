import shutil
import sqlite3
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

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
    WorkspaceDefinition,
)
from backend.repositories.sqlite_backed import (
    SqliteAnalyticsStore,
    SqliteAuthRepository,
    SqliteArtifactStore,
    SqliteJobStore,
    SqliteReviewStore,
    SqliteRunRepository,
    SqliteSecretStore,
    SqliteSourcePolicyStore,
    SqliteWorkerStore,
    SqliteWorkspaceRepository,
)


class PanicException(BaseException):
    pass


PanicException.__module__ = "pyo3_runtime"


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

    def test_summary_list_reads_do_not_hydrate_document_text_or_issue_per_set_reads(self):
        db_path = self._db_path("sqlite_summary_reads")
        workspace_repository = SqliteWorkspaceRepository(db_path)
        run_repository = SqliteRunRepository(db_path)
        job_store = SqliteJobStore(db_path)
        artifact_store = SqliteArtifactStore(db_path)
        review_store = SqliteReviewStore(db_path)

        workspace = WorkspaceDefinition.from_dict(
            {
                "id": "summary_workspace",
                "name": "Summary Workspace",
                "workflow_template_id": "search_apply_v1",
                "workspace_type": "custom",
                "settings": {"workspace_cv_text": "Large CV body"},
            }
        )
        workspace_repository.upsert_workspace(workspace)
        run = RunRecord.create(
            workspace_id=workspace.id,
            workflow_template_id=workspace.workflow_template_id,
            requested_by="test",
        )
        run.stage_results = [
            StageResult(
                stage_id="seed",
                stage_type="test.seed",
                status="completed",
                started_at="",
                finished_at="",
            )
        ]
        run_repository.save(run)
        job_store.save_job_set(
            run.id,
            "first",
            [JobRecord(job_id="job_1", title="Analyst", company="ACME")],
        )
        job_store.save_job_set(
            run.id,
            "second",
            [
                JobRecord(job_id="job_1", title="Senior Analyst", company="ACME"),
                JobRecord(job_id="job_2", title="Engineer", company="Beta"),
            ],
        )
        artifact_store.save_artifacts(
            run.id,
            [ArtifactRecord(artifact_id="artifact_1", artifact_type="cv_pdf", path="cv.pdf")],
        )
        review = ReviewRecord.create(run_id=run.id, job_id="job_1", decision="approved")
        review_store.upsert_review(review)

        with patch(
            "backend.repositories.sqlite_backed._hydrate_workspace_payload",
            side_effect=AssertionError("workspace list must not hydrate document contents"),
        ), patch(
            "backend.repositories.sqlite_backed._hydrate_run_payload",
            side_effect=AssertionError("run list must not hydrate document contents"),
        ), patch.object(
            job_store,
            "load_job_set",
            side_effect=AssertionError("all job sets must load in one batch"),
        ):
            listed_workspaces = workspace_repository.list_workspaces()
            listed_runs = run_repository.list_runs(limit=10)
            job_sets = job_store.load_all_job_sets(run.id)

        self.assertEqual([item.id for item in listed_workspaces], [workspace.id])
        self.assertNotIn("workspace_cv_text", listed_workspaces[0].settings)
        self.assertEqual(listed_runs[0].stage_results[0].stage_id, "seed")
        self.assertEqual(set(job_sets), {"first", "second"})
        self.assertEqual(
            list(artifact_store.load_artifacts_for_runs([run.id])),
            [run.id],
        )
        self.assertEqual(
            [item.review_id for item in review_store.list_reviews_for_runs([run.id])[run.id]],
            [review.review_id],
        )
        read_snapshot = job_store.load_run_read_snapshot(
            [run.id],
            include_artifacts=True,
            include_reviews=True,
            preserve_job_sets=False,
        )
        jobs = read_snapshot["job_sets"][run.id]["__all__"]
        self.assertEqual(
            {job.job_id: job.title for job in jobs},
            {"job_1": "Senior Analyst", "job_2": "Engineer"},
        )

    def test_run_job_artifact_and_review_persistence(self):
        db_path = self._db_path("sqlite_runtime")
        run_repository = SqliteRunRepository(db_path)
        job_store = SqliteJobStore(db_path)
        artifact_store = SqliteArtifactStore(db_path)
        review_store = SqliteReviewStore(db_path)
        auth_repository = SqliteAuthRepository(db_path)
        secret_store = SqliteSecretStore(db_path)
        worker_store = SqliteWorkerStore(db_path)
        analytics_store = SqliteAnalyticsStore(db_path)

        run = RunRecord.create(
            workspace_id="custom_workspace",
            workflow_template_id="search_apply_v1",
            requested_by="test",
            max_attempts=2,
        )
        self.assertEqual(run.user_id, "")
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
        self.assertEqual(claimed_run.user_id, "")

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
        user = UserRecord.create(email="admin@example.com", role="admin")
        review_store.upsert_review(
            review,
            application_status_history={
                "user_id": user.user_id,
                "from_status": "Applied",
                "to_status": "Interviewing",
                "source": "manual",
            },
        )
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
        analytics_store.emit_event(
            event_id="evt_test_1",
            event_name="run_started",
            occurred_at="2026-01-01T00:00:00+00:00",
            user_id=user.user_id,
            workspace_id="custom_workspace",
            run_id=run.id,
            payload={"automation_flow": "tailored_documents"},
        )

        loaded_run = run_repository.get(run.id)
        loaded_jobs = job_store.load_job_set(run.id, "accepted_jobs")
        loaded_metrics = job_store.load_blob(run.id, "metrics", {})
        loaded_artifacts = artifact_store.load_artifacts(run.id)
        loaded_reviews = review_store.list_reviews(run_id=run.id)
        status_history = review_store.list_application_status_history(review_id=review.review_id)
        loaded_user = auth_repository.get_user(user.user_id)
        loaded_tokens = auth_repository.list_api_tokens(user_id=user.user_id)
        matched_tokens = auth_repository.list_api_tokens_for_value("bkat_test_token_value", active_only=True)
        loaded_secret = secret_store.get_secret(secret.secret_id)
        loaded_workers = worker_store.list_workers()
        analytics_rows = analytics_store.query_rows(
            "SELECT event_name, run_id FROM analytics_events WHERE event_id = ?",
            ("evt_test_1",),
        )

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
        self.assertEqual(
            status_history,
            [
                {
                    "review_id": review.review_id,
                    "user_id": user.user_id,
                    "from_status": "Applied",
                    "to_status": "Interviewing",
                    "changed_at": loaded_reviews[0].updated_at,
                    "source": "manual",
                }
            ],
        )
        self.assertEqual(loaded_user.email, "admin@example.com")
        self.assertEqual(len(loaded_tokens), 1)
        self.assertEqual(len(matched_tokens), 1)
        self.assertEqual(matched_tokens[0].token_id, token.token_id)
        self.assertEqual(loaded_secret.name, "api_key")
        self.assertEqual(len(loaded_workers), 1)
        self.assertEqual(loaded_workers[0].worker_id, "worker_a")
        self.assertEqual(analytics_rows, [{"event_name": "run_started", "run_id": run.id}])

        with closing(sqlite3.connect(db_path)) as connection:
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
            self.assertIn("schema_migrations", tables)
            self.assertIn("run_stage_results", tables)
            self.assertIn("run_jobs", tables)
            self.assertIn("workers", tables)
            self.assertIn("analytics_events", tables)
            self.assertIn("application_status_history", tables)
            migration_rows = connection.execute("SELECT migration_id FROM schema_migrations").fetchall()
            migration_ids = [row[0] for row in migration_rows]
            self.assertIn("001_runtime_normalization", migration_ids)
            self.assertIn("002_analytics_events", migration_ids)
            self.assertIn("003_application_status_history", migration_ids)
            self.assertIn("004_runs_user_id", migration_ids)
            run_job_rows = connection.execute(
                "SELECT COUNT(*) FROM run_jobs WHERE run_id = ? AND set_key = ?",
                (run.id, "accepted_jobs"),
            ).fetchone()[0]
            self.assertEqual(run_job_rows, 2)
            history_rows = connection.execute(
                "SELECT COUNT(*) FROM application_status_history WHERE review_id = ?",
                (review.review_id,),
            ).fetchone()[0]
            self.assertEqual(history_rows, 1)

    def test_scrapeops_usage_ledger_records_actual_credits_and_aggregates_by_source(self):
        db_path = self._db_path("sqlite_scrapeops_usage_ledger")
        analytics_store = SqliteAnalyticsStore(db_path)
        analytics_store.record_scrapeops_usage(
            ledger_id="usage_stepstone_1",
            payload={
                "source_id": "stepstone",
                "target_url": "https://www.stepstone.de/jobs",
                "method": "scrapeops_proxy",
                "request_mode": "residential",
                "target_status_code": 200,
                "provider_status_code": 200,
                "latency_ms": 125,
                "billed_credits_actual": 10,
                "billed_credits_estimated": 10,
                "usable_job_count": 2,
                "error_category": "",
                "recorded_at": "2026-05-27T12:00:00+00:00",
            },
        )
        analytics_store.record_scrapeops_usage(
            ledger_id="usage_stepstone_2",
            payload={
                "source_id": "stepstone",
                "target_url": "https://www.stepstone.de/jobs?page=2",
                "method": "scrapeops_proxy",
                "request_mode": "residential",
                "target_status_code": 200,
                "provider_status_code": 200,
                "latency_ms": 150,
                "billed_credits_actual": 7,
                "billed_credits_estimated": 10,
                "usable_job_count": 0,
                "error_category": "",
                "recorded_at": "2026-05-27T12:01:00+00:00",
            },
        )

        row = analytics_store.query_rows(
            "SELECT billed_credits_actual, billed_credits_estimated FROM scrapeops_usage_ledger "
            "WHERE ledger_id = ?",
            ("usage_stepstone_1",),
        )[0]
        spend = analytics_store.get_spend_by_source(datetime(2026, 5, 27, tzinfo=timezone.utc))

        self.assertEqual(row, {"billed_credits_actual": 10, "billed_credits_estimated": 10})
        self.assertEqual(spend, {"stepstone": 17})

        with closing(sqlite3.connect(db_path)) as connection:
            migrations = {
                value[0] for value in connection.execute("SELECT migration_id FROM schema_migrations").fetchall()
            }
        self.assertIn("007_scrapeops_usage_ledger", migrations)

    def test_site_source_policy_transitions_selected_low_yield_and_recovers(self):
        db_path = self._db_path("sqlite_site_source_policy")
        store = SqliteSourcePolicyStore(db_path)
        site_url = "https://careers.example.com/jobs"
        store.ensure_sites([{"url": site_url}], site_type="company")

        self.assertEqual(store.get_site_policy(site_url)["site_state"], "pending")
        transitions = store.mark_workspace_selected([site_url], site_type="company")
        self.assertEqual(transitions[site_url], "pending->selected")
        self.assertEqual(store.get_site_policy(site_url)["site_state"], "selected")

        for _ in range(3):
            store.record_site_yield(site_url, jobs_found=0)
        low_yield_policy = store.get_site_policy(site_url)
        self.assertEqual(low_yield_policy["site_state"], "low_yield")
        self.assertEqual(low_yield_policy["consecutive_zero_yield_runs"], 3)

        store.record_site_yield(site_url, jobs_found=2)
        recovered_policy = store.get_site_policy(site_url)
        self.assertEqual(recovered_policy["site_state"], "selected")
        self.assertEqual(recovered_policy["consecutive_zero_yield_runs"], 0)

        store.set_site_state(site_url, "paused")
        eligible, skipped = store.filter_crawlable_sites([{"url": site_url}])
        self.assertEqual(eligible, [])
        self.assertEqual(skipped[0]["site_state"], "paused")

        with closing(sqlite3.connect(db_path)) as connection:
            migrations = {
                value[0] for value in connection.execute("SELECT migration_id FROM schema_migrations").fetchall()
            }
        self.assertIn("008_site_source_policy", migrations)
        self.assertIn("009_site_job_url_history", migrations)

    def test_mark_workspace_selected_batches_urls_in_one_connection(self):
        db_path = self._db_path("sqlite_site_source_policy_batch")
        store = SqliteSourcePolicyStore(db_path)
        pending_url = "https://careers.example.com/jobs"
        paused_url = "https://jobs.example.edu/openings"
        hot_url = "https://hot.example.org/jobs"
        missing_url = "https://new.example.net/careers"
        bulk_urls = [f"https://bulk.example.net/jobs/{index:02d}" for index in range(25)]
        store.ensure_sites(
            [{"url": pending_url}, {"url": paused_url}, {"url": hot_url}],
            site_type="academic",
        )
        store.set_site_state(paused_url, "paused", site_type="academic")
        store.set_site_state(hot_url, "hot", site_type="academic")
        hot_updated_at = store.get_site_policy(hot_url)["updated_at"]
        selected_at = "2026-07-15T12:34:56+00:00"

        with (
            patch.object(store, "_run_transaction", wraps=store._run_transaction) as transaction,
            patch("backend.repositories.sqlite_backed.utc_now_iso", return_value=selected_at) as now,
        ):
            transitions = store.mark_workspace_selected(
                [pending_url, paused_url, hot_url, missing_url, *reversed(bulk_urls), pending_url],
                site_type="academic",
            )

        expected_selected_urls = sorted([pending_url, paused_url, missing_url, *bulk_urls])
        self.assertEqual(transaction.call_count, 1)
        self.assertEqual(now.call_count, len(expected_selected_urls))
        self.assertEqual(list(transitions), expected_selected_urls)
        self.assertEqual(
            {url: transitions[url] for url in (missing_url, paused_url, pending_url)},
            {
                missing_url: "pending->selected",
                paused_url: "paused->selected",
                pending_url: "pending->selected",
            },
        )
        self.assertTrue(all(transitions[url] == "pending->selected" for url in bulk_urls))
        self.assertEqual(store.get_site_policy(pending_url)["site_state"], "selected")
        self.assertEqual(store.get_site_policy(paused_url)["site_state"], "selected")
        self.assertEqual(store.get_site_policy(missing_url)["site_state"], "selected")
        self.assertEqual(store.get_site_policy(hot_url)["site_state"], "hot")
        self.assertEqual(store.get_site_policy(pending_url)["updated_at"], selected_at)
        self.assertEqual(store.get_site_policy(paused_url)["updated_at"], selected_at)
        self.assertEqual(store.get_site_policy(missing_url)["updated_at"], selected_at)
        self.assertEqual(store.get_site_policy(hot_url)["updated_at"], hot_updated_at)
        with closing(sqlite3.connect(db_path)) as connection:
            bulk_rows = connection.execute(
                "SELECT site_url, site_state, updated_at FROM site_source_policy "
                f"WHERE site_url IN ({','.join('?' for _ in bulk_urls)})",
                bulk_urls,
            ).fetchall()
        self.assertEqual(
            {(row[0], row[1], row[2]) for row in bulk_rows},
            {(url, "selected", selected_at) for url in bulk_urls},
        )

    def test_mark_workspace_selected_close_panic_does_not_mask_fatal_transaction_error(self):
        db_path = self._db_path("sqlite_source_policy_cleanup")
        store = SqliteSourcePolicyStore(db_path)
        fatal_error = KeyboardInterrupt("stop")
        connection = Mock()
        connection.execute.side_effect = fatal_error
        connection.transaction.side_effect = lambda callback: callback(connection)
        connection.close.side_effect = PanicException("close panic")

        with (
            patch("backend.repositories.sqlite_core.connect_database", return_value=connection),
            self.assertRaises(KeyboardInterrupt) as raised,
        ):
            store.mark_workspace_selected(
                ["https://jobs.example.edu/openings"],
                site_type="academic",
            )

        self.assertIs(raised.exception, fatal_error)
        connection.transaction.assert_called_once()
        connection.close.assert_called_once()

    def test_site_job_url_history_records_seen_urls(self):
        db_path = self._db_path("sqlite_site_job_url_history")
        store = SqliteSourcePolicyStore(db_path)
        store.record_job_url_attempts(
            [
                {
                    "site_url": "https://careers.example.com",
                    "job_url": "https://careers.example.com/jobs/123?utm_source=test",
                    "job_id": "job_123",
                    "title": "Product Analyst",
                    "company": "Example",
                    "status": "accepted",
                }
            ],
            run_id="run_1",
            workspace_id="workspace_1",
        )

        self.assertEqual(
            store.get_seen_job_urls(["https://careers.example.com/jobs/123"]),
            {"https://careers.example.com/jobs/123"},
        )
        self.assertEqual(
            store.get_seen_job_urls(["https://careers.example.com/jobs/123"], workspace_id="workspace_1"),
            {"https://careers.example.com/jobs/123"},
        )
        self.assertEqual(
            store.get_seen_job_urls(["https://careers.example.com/jobs/123"], workspace_id="workspace_2"),
            {"https://careers.example.com/jobs/123"},
        )
        cached = store.get_cached_job_postings(["https://careers.example.com/jobs/123"])
        self.assertEqual(cached["https://careers.example.com/jobs/123"]["title"], "Product Analyst")
        store.record_job_url_attempts(
            [
                {
                    "site_url": "https://careers.example.com",
                    "job_url": "https://careers.example.com/jobs/123",
                    "job_id": "job_123_copy",
                    "title": "Product Analyst Copy",
                    "company": "Example",
                    "status": "accepted",
                }
            ],
            run_id="run_2",
            workspace_id="workspace_2",
        )
        self.assertEqual(
            store.get_seen_job_urls(["https://careers.example.com/jobs/123"], workspace_id="workspace_1"),
            {"https://careers.example.com/jobs/123"},
        )
        self.assertEqual(
            store.get_seen_job_urls(["https://careers.example.com/jobs/123"], workspace_id="workspace_2"),
            {"https://careers.example.com/jobs/123"},
        )

        with closing(sqlite3.connect(db_path)) as connection:
            row = connection.execute(
                "SELECT run_id, workspace_id, last_status FROM site_job_url_history WHERE job_url = ?",
                ("https://careers.example.com/jobs/123",),
            ).fetchone()
            migrations = {
                value[0] for value in connection.execute("SELECT migration_id FROM schema_migrations").fetchall()
            }
        self.assertEqual(row, ("run_2", "workspace_2", "accepted"))
        self.assertIn("009_site_job_url_history", migrations)
        self.assertIn("010_site_job_url_history_workspace_scope", migrations)
        self.assertIn("011_site_job_url_history_public_index", migrations)

    def test_run_user_id_migration_backfills_existing_rows(self):
        db_path = self._db_path("sqlite_run_user_id_migration")
        with closing(sqlite3.connect(db_path)) as connection:
            connection.executescript(
                """
                CREATE TABLE schema_migrations (
                    migration_id TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                INSERT INTO schema_migrations (migration_id, applied_at) VALUES
                    ('001_runtime_normalization', '2026-01-01T00:00:00+00:00'),
                    ('002_analytics_events', '2026-01-01T00:00:00+00:00'),
                    ('003_application_status_history', '2026-01-01T00:00:00+00:00');
                CREATE TABLE runs (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    workflow_template_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    queued_at TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT '',
                    current_stage_id TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT '',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 1,
                    run_input_overrides_json TEXT NOT NULL DEFAULT '{}',
                    run_plan_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE run_stage_results (
                    run_id TEXT NOT NULL,
                    sequence_no INTEGER NOT NULL,
                    stage_id TEXT NOT NULL,
                    stage_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    output_keys_json TEXT NOT NULL DEFAULT '[]',
                    artifact_ids_json TEXT NOT NULL DEFAULT '[]',
                    PRIMARY KEY (run_id, sequence_no)
                );
                INSERT INTO runs (
                    id, workspace_id, workflow_template_id, status, requested_by, created_at, updated_at, payload_json
                ) VALUES (
                    'run_legacy',
                    'workspace_legacy',
                    'workflow_legacy',
                    'queued',
                    'api:user_legacy',
                    '2026-01-01T00:00:00+00:00',
                    '2026-01-01T00:00:00+00:00',
                    '{"id":"run_legacy","workspace_id":"workspace_legacy","workflow_template_id":"workflow_legacy","status":"queued","requested_by":"api:user_legacy"}'
                );
                """
            )
            connection.commit()

        run_repository = SqliteRunRepository(db_path)
        migrated_run = run_repository.get("run_legacy")
        self.assertEqual(migrated_run.user_id, "user_legacy")

        with closing(sqlite3.connect(db_path)) as connection:
            row = connection.execute("SELECT user_id FROM runs WHERE id = 'run_legacy'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "user_legacy")


if __name__ == "__main__":
    unittest.main()
