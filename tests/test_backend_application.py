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
                "workspace_type": "custom",
                "settings": {"dedupe_against_tracker": True},
                "feature_flags": {"manual_mode": True},
                "sources": [{"id": "manual_source", "connector_id": "curated_job_urls"}],
            }
        )
        return app, temp_dir

    def test_default_backend_starts_with_starter_templates_and_no_workspaces(self):
        temp_dir = self._workspace_tempdir("starter_templates")
        app = create_backend(temp_dir)
        self.assertTrue((temp_dir / "backend.sqlite3").exists())
        self.assertEqual(app.list_workspaces(), [])
        template_ids = {template.id for template in app.list_workflow_templates()}
        self.assertIn("search_apply_v1", template_ids)
        self.assertIn("board_package_v1", template_ids)

    def test_builder_can_create_workspace_and_dry_run_plan(self):
        temp_dir = self._workspace_tempdir("builder_dry_run")
        app = create_backend(temp_dir)
        workspace = app.create_workspace_from_scratch(
            {
                "name": "My Search Workspace",
                "flow_id": "tailored_documents",
                "source_ids": ["linkedin_jobs", "curated_job_urls"],
                "module_ids": [
                    "screening_filter",
                    "priority_ranking",
                    "tailored_document_generation",
                ],
                "prompt_family": "tailored_documents",
                "profile_label": "Primary Job Seeker Profile",
                "settings": {
                    "keywords": ["analyst", "consultant"],
                    "geo_id": "101282230",
                    "experience_levels": [2, 3],
                    "low_applicant_threshold": 60,
                    "stage4_max_jobs": 15,
                    "target_roles": ["Business Analyst", "Consultant"],
                },
            }
        )
        run = app.start_run(
            workspace.id,
            run_input_overrides={"manual_urls_file": "user_config/manual_job_urls.txt"},
            execute=False,
            requested_by="test",
        )
        self.assertEqual(run.status, "planned")
        self.assertIsNotNone(run.run_plan)
        self.assertEqual(run.run_plan.workflow_template_id, f"{workspace.id}_workflow")
        self.assertEqual(
            run.run_plan.resolved_run_settings["manual_urls_file"],
            "user_config/manual_job_urls.txt",
        )
        self.assertEqual(run.run_plan.resolved_run_settings["keywords"], ["analyst", "consultant"])
        self.assertEqual(run.run_plan.resolved_run_settings["stage4_max_jobs"], 15)
        self.assertEqual(run.run_plan.resolved_run_settings["target_roles"], ["Business Analyst", "Consultant"])
        self.assertTrue((temp_dir / "backend.sqlite3").exists())

    def test_builder_can_update_existing_workspace(self):
        temp_dir = self._workspace_tempdir("builder_update")
        app = create_backend(temp_dir)
        workspace = app.create_workspace_from_scratch(
            {
                "name": "My Search Workspace",
                "flow_id": "tailored_documents",
                "source_ids": ["linkedin_jobs"],
                "module_ids": [
                    "screening_filter",
                    "priority_ranking",
                    "tailored_document_generation",
                ],
                "settings": {
                    "keywords": ["analyst"],
                    "stage4_max_jobs": 10,
                },
            }
        )

        updated_workspace = app.update_workspace_from_scratch(
            workspace.id,
            {
                "name": "Updated Search Workspace",
                "description": "Updated description",
                "flow_id": "tailored_documents",
                "source_ids": ["linkedin_jobs", "curated_job_urls"],
                "module_ids": [
                    "screening_filter",
                    "priority_ranking",
                    "tailored_document_generation",
                ],
                "settings": {
                    "keywords": ["analyst", "consultant"],
                    "stage4_max_jobs": 20,
                    "low_applicant_threshold": 50,
                },
            },
        )

        self.assertEqual(updated_workspace.id, workspace.id)
        self.assertEqual(updated_workspace.name, "Updated Search Workspace")
        self.assertEqual(updated_workspace.description, "Updated description")
        self.assertEqual(updated_workspace.settings["keywords"], ["analyst", "consultant"])
        self.assertEqual(updated_workspace.settings["stage4_max_jobs"], 20)
        self.assertEqual(updated_workspace.metadata["source_ids"], ["linkedin_jobs", "curated_job_urls"])

    def test_file_storage_backend_can_still_be_requested(self):
        temp_dir = self._workspace_tempdir("file_storage_backend")
        app = create_backend(temp_dir, storage_backend="file")
        self.assertEqual(app.list_workspaces(), [])
        template_ids = {template.id for template in app.list_workflow_templates()}
        self.assertIn("search_apply_v1", template_ids)
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

        self.assertIn("linkedin_jobs", connector_ids)
        self.assertIn("job_board_collection", connector_ids)
        self.assertIn("job_board_indeed", connector_ids)
        self.assertIn("tailored_application_documents", generation_ids)
        self.assertIn("application_document_export", renderer_ids)

    def test_referral_contacts_and_outreach_drafts(self):
        app, _ = self._create_app_with_test_workflow("referrals_and_outreach")
        user = app.upsert_user(
            {
                "email": "networking@example.com",
                "display_name": "Networking User",
                "role": "admin",
                "metadata": {
                    "profile": {
                        "name": "Networking User",
                        "summary": "Product and operations specialist with experience improving internal tooling.",
                    }
                },
            }
        )

        completed_run = app.start_run("custom_workspace", execute=True, requested_by="test")
        self.assertEqual(completed_run.status, "failed")
        completed_run = app.retry_run(completed_run.id)
        completed_run = app.process_next_queued_run(auto_retry_failed=True)
        self.assertEqual(completed_run.status, "completed")

        contact = app.upsert_referral_contact(
            user_id=user.user_id,
            payload={
                "name": "Jane Referrer",
                "company": "ACME",
                "linkedin_url": "https://linkedin.com/in/jane-referrer",
                "relationship_note": "Worked together on automation rollout.",
                "can_refer": True,
            },
        )
        self.assertEqual(contact.company, "ACME")
        self.assertEqual(len(app.list_referral_contacts(user.user_id)), 1)

        referral_draft = app.generate_referral_outreach(
            user_id=user.user_id,
            run_id=completed_run.id,
            job_id="job_1",
            contact_id=contact.contact_id,
        )
        self.assertIn("Jane Referrer", referral_draft["message"])
        self.assertIn("Analyst", referral_draft["message"])

        hiring_manager_draft = app.generate_hiring_manager_outreach(
            user_id=user.user_id,
            run_id=completed_run.id,
            job_id="job_1",
        )
        self.assertIn("Analyst", hiring_manager_draft["message"])
        self.assertIn("hiring_manager", hiring_manager_draft)

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

    def test_delete_run_removes_queued_test_run(self):
        app, _ = self._create_app_with_test_workflow("delete_run")

        queued_run = app.enqueue_run("custom_workspace", requested_by="test-delete")
        self.assertEqual(queued_run.status, "queued")

        app.delete_run(queued_run.id)

        with self.assertRaises(KeyError):
            app.get_run(queued_run.id)

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
