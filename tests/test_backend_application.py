import shutil
import unittest
from pathlib import Path

from backend import create_backend
from backend.domain.models import ArtifactRecord, JobRecord, StageDefinition
from backend.orchestration import BaseStage, StageOutcome


class _SeedJobsStage(BaseStage):
    def can_run(self, context, definition) -> bool:
        return True

    def execute(self, context, definition) -> StageOutcome:
        return StageOutcome(
            job_sets={
                definition.output_key or "accepted_jobs": [
                    JobRecord(job_id="job_1", title="Analyst", company="ACME"),
                ]
            },
            artifacts=[
                ArtifactRecord(
                    artifact_id="artifact_job_1",
                    artifact_type="docx",
                    path="generated_docs/job_1.docx",
                    metadata={"job_id": "job_1"},
                )
            ],
            metrics={"seeded_jobs": 1},
        )


class _FlakyStage(BaseStage):
    def can_run(self, context, definition) -> bool:
        return True

    def execute(self, context, definition) -> StageOutcome:
        if context.run.attempt_count < 2:
            raise RuntimeError("transient failure")
        return StageOutcome(data={definition.output_key or "flaky_data": {"status": "ok"}}, metrics={"retried": True})


class BackendApplicationTests(unittest.TestCase):
    def _workspace_tempdir(self, name: str) -> Path:
        path = Path.cwd() / ".backend_test_tmp" / name
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def _create_app_with_test_workflow(self, name: str):
        temp_dir = self._workspace_tempdir(name)
        app = create_backend(temp_dir)
        app.registries.stage_registry.register("test.seed_jobs", _SeedJobsStage())
        app.registries.stage_registry.register("test.flaky", _FlakyStage())
        app.upsert_workflow_template(
            {
                "id": "custom_template_v1",
                "name": "Custom Template",
                "description": "Test template",
                "stages": [
                    StageDefinition(
                        stage_id="seed_jobs",
                        stage_type="test.seed_jobs",
                        name="Seed Jobs",
                        output_key="accepted_jobs",
                    ).to_dict(),
                    StageDefinition(
                        stage_id="flaky_step",
                        stage_type="test.flaky",
                        name="Flaky Step",
                        output_key="flaky_data",
                    ).to_dict(),
                ],
                "default_run_settings": {"manual_urls_file": "user_config/manual_job_urls.txt"},
            }
        )
        app.upsert_workspace(
            {
                "id": "custom_workspace",
                "name": "Custom Workspace",
                "workflow_template_id": "custom_template_v1",
                "workspace_type": "white_collar",
                "settings": {"dedupe_against_tracker": True},
                "feature_flags": {"manual_mode": True},
                "sources": [{"id": "manual_source", "connector_id": "manual_url"}],
            }
        )
        return app, temp_dir

    def test_seeded_workspaces_are_available(self):
        temp_dir = self._workspace_tempdir("seeded_workspaces")
        app = create_backend(temp_dir)
        self.assertTrue((temp_dir / "backend.sqlite3").exists())
        workspace_ids = {workspace.id for workspace in app.list_workspaces()}
        self.assertIn("white_collar_linkedin", workspace_ids)
        self.assertIn("white_collar_manual_urls", workspace_ids)
        self.assertIn("white_collar_combined", workspace_ids)
        self.assertIn("blue_collar_default", workspace_ids)

    def test_dry_run_creates_run_plan_without_execution(self):
        temp_dir = self._workspace_tempdir("dry_run_plan")
        app = create_backend(temp_dir)
        run = app.start_run(
            "white_collar_combined",
            run_input_overrides={"manual_urls_file": "user_config/manual_job_urls.txt"},
            execute=False,
            requested_by="test",
        )
        self.assertEqual(run.status, "planned")
        self.assertIsNotNone(run.run_plan)
        self.assertEqual(run.run_plan.workflow_template_id, "white_collar_combined_v1")
        self.assertEqual(
            run.run_plan.resolved_run_settings["manual_urls_file"],
            "user_config/manual_job_urls.txt",
        )
        self.assertTrue((temp_dir / "backend.sqlite3").exists())

    def test_file_storage_backend_can_still_be_requested(self):
        temp_dir = self._workspace_tempdir("file_storage_backend")
        app = create_backend(temp_dir, storage_backend="file")
        workspace_ids = {workspace.id for workspace in app.list_workspaces()}
        self.assertIn("white_collar_linkedin", workspace_ids)
        self.assertTrue((temp_dir / "workflow_templates.json").exists())
        self.assertTrue((temp_dir / "workspaces.json").exists())

    def test_upsert_workflow_template_and_workspace_persist(self):
        app, _ = self._create_app_with_test_workflow("workspace_upsert")
        self.assertEqual(app.get_workflow_template("custom_template_v1").name, "Custom Template")
        self.assertEqual(app.get_workspace("custom_workspace").workflow_template_id, "custom_template_v1")
        self.assertTrue(app.get_workspace("custom_workspace").feature_flags["manual_mode"])

    def test_registry_components_are_listed(self):
        temp_dir = self._workspace_tempdir("registry_introspection")
        app = create_backend(temp_dir)

        connector_ids = {item.id for item in app.list_connectors()}
        generation_ids = {item.id for item in app.list_generations()}
        renderer_ids = {item.id for item in app.list_renderers()}

        self.assertIn("linkedin_search", connector_ids)
        self.assertIn("blue_collar_portals", connector_ids)
        self.assertIn("blue_collar_indeed", connector_ids)
        self.assertIn("white_collar_cv_generation", generation_ids)
        self.assertIn("docx_pdf_renderer", renderer_ids)

    def test_queue_worker_retry_and_resource_crud(self):
        app, _ = self._create_app_with_test_workflow("queue_worker_flow")

        run = app.enqueue_run(
            "custom_workspace",
            run_input_overrides={"manual_urls_file": "user_config/manual_job_urls.txt"},
            requested_by="test",
            max_attempts=2,
        )
        self.assertEqual(run.status, "queued")

        first_attempt = app.process_next_queued_run(auto_retry_failed=True)
        self.assertIsNotNone(first_attempt)
        self.assertEqual(first_attempt.status, "queued")
        self.assertEqual(first_attempt.attempt_count, 1)
        self.assertEqual([result.stage_id for result in first_attempt.stage_results], ["seed_jobs"])

        completed_run = app.process_next_queued_run(auto_retry_failed=True)
        self.assertIsNotNone(completed_run)
        self.assertEqual(completed_run.status, "completed")
        self.assertEqual(completed_run.attempt_count, 2)
        self.assertEqual(completed_run.final_job_set_keys, ["accepted_jobs"])

        job_sets = app.list_job_sets(completed_run.id)
        artifacts = app.list_artifacts(completed_run.id)
        self.assertEqual(list(job_sets.keys()), ["accepted_jobs"])
        self.assertEqual(job_sets["accepted_jobs"][0].job_id, "job_1")
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0].artifact_id, "artifact_job_1")

        review = app.upsert_review(
            run_id=completed_run.id,
            payload={
                "job_id": "job_1",
                "decision": "approved",
                "reviewer": "tester",
                "notes": "approved for send",
                "job_set_key": "accepted_jobs",
                "status": "approved",
            },
        )
        self.assertEqual(review.run_id, completed_run.id)
        self.assertEqual(review.decision, "approved")
        self.assertEqual(len(app.list_reviews(run_id=completed_run.id)), 1)

        updated_jobs = app.upsert_job_set(
            completed_run.id,
            "accepted_jobs",
            [{"job_id": "job_2", "title": "Consultant", "company": "Beta"}],
        )
        self.assertEqual(updated_jobs[0].job_id, "job_2")
        self.assertEqual(app.get_job_set(completed_run.id, "accepted_jobs")[0].job_id, "job_2")
        app.delete_review(review.review_id)
        self.assertEqual(app.list_reviews(run_id=completed_run.id), [])

    def test_resume_and_cancel_lifecycle(self):
        app, _ = self._create_app_with_test_workflow("resume_cancel")

        planned_run = app.start_run("custom_workspace", execute=False, requested_by="test")
        self.assertEqual(planned_run.status, "planned")

        queued_run = app.resume_run(planned_run.id)
        self.assertEqual(queued_run.status, "queued")

        cancelled_run = app.cancel_run(queued_run.id)
        self.assertEqual(cancelled_run.status, "cancelled")

        failed_run = app.enqueue_run("custom_workspace", requested_by="test", max_attempts=1)
        failed_result = app.process_next_queued_run(auto_retry_failed=False)
        self.assertEqual(failed_result.status, "failed")

        resumed_run = app.resume_run(failed_run.id)
        self.assertEqual(resumed_run.status, "queued")
        completed_run = app.process_next_queued_run(auto_retry_failed=False)
        self.assertEqual(completed_run.status, "completed")

    def test_auth_token_and_secret_resolution(self):
        app, _ = self._create_app_with_test_workflow("auth_secrets")

        user = app.upsert_user(
            {
                "email": "editor@example.com",
                "display_name": "Editor",
                "role": "editor",
                "allowed_workspace_ids": ["custom_workspace"],
            }
        )
        token, raw_token = app.issue_api_token(user_id=user.user_id, name="editor-token")
        authenticated_user, authenticated_token = app.authenticate_access_token(raw_token)

        self.assertEqual(authenticated_user.user_id, user.user_id)
        self.assertEqual(authenticated_token.token_id, token.token_id)
        self.assertTrue(app.user_can_access_workspace(authenticated_user, "custom_workspace"))

        secret = app.upsert_secret(
            {
                "name": "openai_api_key",
                "provider": "stored",
                "workspace_id": "custom_workspace",
                "secret_value": "super-secret-value",
            }
        )
        resolved = app.resolve_runtime_value({"api_key": f"${{secret:{secret.secret_id}}}"})
        self.assertEqual(resolved["api_key"], "super-secret-value")


if __name__ == "__main__":
    unittest.main()
