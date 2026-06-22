import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import create_backend
from backend.application.services import BackendValidationError, _scrapeops_account_state
from backend.capabilities.networking import build_empty_relevant_people_discovery
from backend.domain.phase0_contracts import normalize_candidate_asset_descriptor
from backend.domain.models import ArtifactRecord, JobRecord, StageDefinition
from backend.profiles.cv_text import load_cv_text
from backend.orchestration import BaseStage, StageOutcome
from backend.storage import build_private_object_key


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


class _CanRunExplodesStage(BaseStage):
    def can_run(self, context, definition) -> bool:
        raise RuntimeError("can_run exploded")

    def execute(self, context, definition) -> StageOutcome:
        return StageOutcome()


class _DocumentGenerationStage(BaseStage):
    def can_run(self, context, definition) -> bool:
        return bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))

    def execute(self, context, definition) -> StageOutcome:
        jobs = context.get_job_set(definition.input_keys[0])
        first_job_id = jobs[0].job_id if jobs else ""
        return StageOutcome(
            job_sets={definition.output_key or "generated_jobs": jobs},
            artifacts=[
                ArtifactRecord(
                    artifact_id=f"generated_{first_job_id}_cv",
                    artifact_type="cv_docx",
                    path=f"generated_docs/{first_job_id}_cv.docx",
                    metadata={"job_id": first_job_id},
                )
            ],
            metrics={"generated_jobs": len(jobs)},
        )


class _FailedDocumentGenerationStage(BaseStage):
    def can_run(self, context, definition) -> bool:
        return bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))

    def execute(self, context, definition) -> StageOutcome:
        jobs = [
            {
                **job.to_dict(),
                "cv_docx": "",
                "tailored_cv_docx": "",
                "doc_generation_error": "DeepSeek request timed out",
            }
            for job in context.get_job_set(definition.input_keys[0])
        ]
        return StageOutcome(
            job_sets={definition.output_key or "generated_jobs": jobs},
            metrics={"generated_jobs": len(jobs), "generation_errors": len(jobs)},
        )


class _NoArtifactDocumentGenerationStage(BaseStage):
    def can_run(self, context, definition) -> bool:
        return bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))

    def execute(self, context, definition) -> StageOutcome:
        jobs = [
            {
                **job.to_dict(),
                "cv_docx": "",
                "tailored_cv_docx": "",
                "doc_generation_error": "",
            }
            for job in context.get_job_set(definition.input_keys[0])
        ]
        return StageOutcome(
            job_sets={definition.output_key or "generated_jobs": jobs},
            metrics={"generated_jobs": len(jobs)},
        )


class _SeedTestCandidatesStage(BaseStage):
    def can_run(self, context, definition) -> bool:
        return True

    def execute(self, context, definition) -> StageOutcome:
        return StageOutcome(
            job_sets={
                definition.output_key: [
                    JobRecord(job_id="rejected_job", title="Rejected Role", company="ACME"),
                    JobRecord(job_id="accepted_job_1", title="Accepted Role One", company="ACME"),
                    JobRecord(job_id="accepted_job_2", title="Accepted Role Two", company="ACME"),
                ]
            }
        )


class _AcceptTestCandidatesStage(BaseStage):
    def can_run(self, context, definition) -> bool:
        return bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))

    def execute(self, context, definition) -> StageOutcome:
        jobs = context.get_job_set(definition.input_keys[0])
        return StageOutcome(job_sets={definition.output_key: jobs[1:]}, metrics={"approved": len(jobs[1:]), "rejected": 1})


class BackendApplicationTests(unittest.TestCase):
    def test_scrapeops_account_state_parses_nested_usage_payload(self):
        with (
            patch.dict("os.environ", {"SCRAPEOPS_API_KEY": "test_key"}, clear=False),
            patch(
                "backend.application.services.fetch_account_usage",
                return_value={
                    "results": {
                        "plan_api_credits": "100000",
                        "used_api_credits": "0",
                    }
                },
            ),
        ):
            state = _scrapeops_account_state()

        self.assertEqual(state["status"], "healthy")
        self.assertEqual(state["usage"]["limit"], 100000)
        self.assertEqual(state["usage"]["remaining"], 100000)

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
        app.registries.stage_registry.register("test.can_run_explodes", _CanRunExplodesStage())
        app.registries.stage_registry.register("applications.generate.documents", _DocumentGenerationStage())
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

    def _workspace_cv_asset_descriptor(self, *, asset_id: str, cv_path: Path, object_key: str = "") -> dict:
        return normalize_candidate_asset_descriptor(
            {
                "asset_id": asset_id,
                "asset_kind": "workspace_cv",
                "display_name": cv_path.name,
                "role": "workspace_cv",
                "path": str(cv_path.resolve()),
                "object_key": object_key,
                "mime_type": "text/plain",
                "extension": cv_path.suffix.lower().lstrip("."),
                "tags": ["workspace_cv"],
            }
        )

    def _create_builder_workspace_with_cv_snapshot(
        self,
        app,
        *,
        cv_path: Path,
        cv_text: str,
        workspace_name: str = "Builder Workspace",
        cv_generation_mode: str = "aggressive_customization",
    ):
        asset_id = "asset_workspace_cv_primary"
        object_key = build_private_object_key(
            namespace="users",
            owner_id="test_user",
            category="workspace_cv",
            object_id=asset_id,
            filename=cv_path.name,
        )
        app.object_storage.put(object_key, cv_path.read_bytes(), content_type="text/plain")
        workspace = app.create_workspace_from_scratch(
            {
                "name": workspace_name,
                "flow_id": "tailored_documents",
                "source_ids": ["linkedin_jobs"],
                "module_ids": [
                    "screening_filter",
                    "priority_ranking",
                    "tailored_document_generation",
                ],
                "workspace_cv_asset": self._workspace_cv_asset_descriptor(
                    asset_id=asset_id,
                    cv_path=cv_path,
                    object_key=object_key,
                ),
                "settings": {
                    "workspace_cv_asset_id": asset_id,
                    "cv_generation_mode": cv_generation_mode,
                    "keywords": ["analyst"],
                    "country_codes": ["DE"],
                    "geo_id": "101282230",
                    "experience_levels": [2, 3],
                    "stage4_max_jobs": 1,
                },
            }
        )
        workspace_payload = workspace.to_dict()
        workspace_payload["settings"] = {
            **dict(workspace_payload.get("settings") or {}),
            "workspace_cv_text": cv_text,
            "workspace_cv_asset_path": str(cv_path.resolve()),
            "workspace_cv_asset_display_name": cv_path.name,
            "workspace_cv_asset_extension": cv_path.suffix.lower().lstrip("."),
            "workspace_cv_asset_mime_type": "text/plain",
            "workspace_cv_asset_object_key": object_key,
        }
        return app.upsert_workspace(workspace_payload)

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
        cv_path = temp_dir / "workspace_cv.txt"
        cv_path.write_text("Primary workspace CV snapshot", encoding="utf-8")
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
                "workspace_cv_asset": self._workspace_cv_asset_descriptor(
                    asset_id="asset_workspace_cv_primary",
                    cv_path=cv_path,
                ),
                "settings": {
                    "workspace_cv_asset_id": "asset_workspace_cv_primary",
                    "keywords": ["analyst", "consultant"],
                    "work_arrangement": "remote",
                    "industry": "Healthcare",
                    "country_codes": ["DE"],
                    "geo_id": "101282230",
                    "manual_url_seed_list": ["https://company.example/jobs/1"],
                    "experience_levels": [2, 3],
                    "low_applicant_threshold": 60,
                    "stage4_max_jobs": 15,
                    "target_roles": ["Business Analyst", "Consultant"],
                    "linkedin_max_pages": 7,
                    "reuse_scrape_snapshot": True,
                    "page_fetch_sleep_seconds": 1.5,
                    "include_photo": False,
                    "cv_template": "modern",
                    "french_special_char_threshold": 9999,
                },
            }
        )
        workspace_payload = workspace.to_dict()
        workspace_payload["settings"] = {
            **dict(workspace_payload.get("settings") or {}),
            "workspace_cv_text": "Primary workspace CV snapshot",
            "workspace_cv_asset_path": str(cv_path.resolve()),
            "workspace_cv_asset_display_name": cv_path.name,
            "workspace_cv_asset_extension": "txt",
            "workspace_cv_asset_mime_type": "text/plain",
        }
        workspace = app.upsert_workspace(workspace_payload)
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
        self.assertEqual(run.run_plan.resolved_run_settings["work_arrangement"], "remote")
        self.assertEqual(run.run_plan.resolved_run_settings["industry"], "Healthcare")
        self.assertEqual(run.run_plan.resolved_run_settings["stage4_max_jobs"], 15)
        self.assertEqual(run.run_plan.resolved_run_settings["target_roles"], ["Business Analyst", "Consultant"])
        self.assertEqual(run.run_plan.resolved_run_settings["job_filtering_mode"], "Broader Match")
        self.assertEqual(run.run_plan.resolved_run_settings["linkedin_max_pages"], 7)
        self.assertTrue(run.run_plan.resolved_run_settings["reuse_scrape_snapshot"])
        self.assertEqual(run.run_plan.resolved_run_settings["page_fetch_sleep_seconds"], 1.5)
        self.assertFalse(run.run_plan.resolved_run_settings["include_photo"])
        self.assertEqual(run.run_plan.resolved_run_settings["cv_template"], "plain")
        self.assertEqual(run.run_plan.resolved_run_settings["french_special_char_threshold"], 9999)
        self.assertEqual(run.run_plan.resolved_run_settings["workspace_cv_asset_id"], "asset_workspace_cv_primary")
        self.assertEqual(run.run_plan.resolved_run_settings["workspace_cv_text"], "Primary workspace CV snapshot")
        self.assertTrue((temp_dir / "backend.sqlite3").exists())

    def test_builder_create_rejects_omitted_automation_modules(self):
        temp_dir = self._workspace_tempdir("builder_missing_modules")
        app = create_backend(temp_dir)
        cv_path = temp_dir / "workspace_cv.txt"
        cv_path.write_text("Workspace CV", encoding="utf-8")

        with self.assertRaises(BackendValidationError) as error_context:
            app.create_workspace_from_scratch(
                {
                    "name": "Missing Modules Workspace",
                    "flow_id": "tailored_documents",
                    "source_ids": ["linkedin_jobs"],
                    "workspace_cv_asset": self._workspace_cv_asset_descriptor(
                        asset_id="asset_workspace_cv_primary",
                        cv_path=cv_path,
                    ),
                    "settings": {
                        "workspace_cv_asset_id": "asset_workspace_cv_primary",
                        "keywords": ["analyst"],
                        "country_codes": ["DE"],
                    },
                }
            )

        self.assertEqual(error_context.exception.error_code, "workspace_validation_failed")
        self.assertIn(
            {
                "field": "module_ids",
                "code": "required",
                "message": "Enable at least one automation module for this workspace.",
            },
            error_context.exception.details["field_errors"],
        )

    def test_builder_create_requires_tailored_document_automation_module(self):
        temp_dir = self._workspace_tempdir("builder_missing_tailored_module")
        app = create_backend(temp_dir)
        cv_path = temp_dir / "workspace_cv.txt"
        cv_path.write_text("Workspace CV", encoding="utf-8")

        with self.assertRaises(BackendValidationError) as error_context:
            app.create_workspace_from_scratch(
                {
                    "name": "Missing Tailored Module Workspace",
                    "flow_id": "tailored_documents",
                    "source_ids": ["linkedin_jobs"],
                    "module_ids": ["screening_filter", "priority_ranking"],
                    "workspace_cv_asset": self._workspace_cv_asset_descriptor(
                        asset_id="asset_workspace_cv_primary",
                        cv_path=cv_path,
                    ),
                    "settings": {
                        "workspace_cv_asset_id": "asset_workspace_cv_primary",
                        "keywords": ["analyst"],
                        "country_codes": ["DE"],
                    },
                }
            )

        self.assertIn(
            {
                "field": "module_ids",
                "code": "required_module",
                "message": "Enable the tailored_document_generation module for tailored-document workspaces.",
            },
            error_context.exception.details["field_errors"],
        )

    def test_generic_workspace_upsert_cannot_bypass_builder_cv_validation(self):
        app, _ = self._create_app_with_test_workflow("builder_generic_upsert_missing_cv")

        with self.assertRaises(BackendValidationError) as error_context:
            app.upsert_workspace(
                {
                    "id": "malformed_builder_workspace",
                    "name": "Malformed Builder Workspace",
                    "workflow_template_id": "custom_template_v1",
                    "workspace_type": "custom",
                    "settings": {
                        "automation_flow": "tailored_documents",
                        "keywords": ["analyst"],
                        "country_codes": ["DE"],
                    },
                    "feature_flags": {
                        "screening_filter": True,
                        "priority_ranking": True,
                        "tailored_document_generation": True,
                    },
                    "sources": [{"id": "linkedin", "connector_id": "linkedin_jobs"}],
                    "metadata": {
                        "builder_mode": "scratch",
                        "automation_flow": "tailored_documents",
                        "source_ids": ["linkedin_jobs"],
                        "modules": [
                            "screening_filter",
                            "priority_ranking",
                            "tailored_document_generation",
                        ],
                    },
                }
            )

        self.assertEqual(error_context.exception.error_code, "workspace_validation_failed")
        self.assertIn(
            {
                "field": "workspace_cv_asset_id",
                "code": "required",
                "message": "Select a workspace CV before saving or running this workspace.",
            },
            error_context.exception.details["field_errors"],
        )

    def test_generic_workspace_upsert_rejects_mismatched_saved_sources(self):
        temp_dir = self._workspace_tempdir("builder_mismatched_sources")
        app = create_backend(temp_dir)
        cv_path = temp_dir / "workspace_cv.txt"
        cv_path.write_text("Workspace CV", encoding="utf-8")
        workspace = self._create_builder_workspace_with_cv_snapshot(
            app,
            cv_path=cv_path,
            cv_text="Workspace CV",
        )
        workspace_payload = workspace.to_dict()
        workspace_payload["sources"] = [{"id": "curated", "connector_id": "curated_job_urls"}]

        with self.assertRaises(BackendValidationError) as error_context:
            app.upsert_workspace(workspace_payload)

        self.assertIn(
            {
                "field": "source_ids",
                "code": "source_configuration_mismatch",
                "message": "Saved source_ids do not match the workspace connector configuration.",
            },
            error_context.exception.details["field_errors"],
        )

    def test_generic_workspace_upsert_rejects_mismatched_enabled_modules(self):
        temp_dir = self._workspace_tempdir("builder_mismatched_modules")
        app = create_backend(temp_dir)
        cv_path = temp_dir / "workspace_cv.txt"
        cv_path.write_text("Workspace CV", encoding="utf-8")
        workspace = self._create_builder_workspace_with_cv_snapshot(
            app,
            cv_path=cv_path,
            cv_text="Workspace CV",
        )
        workspace_payload = workspace.to_dict()
        workspace_payload["feature_flags"]["tailored_document_generation"] = False

        with self.assertRaises(BackendValidationError) as error_context:
            app.upsert_workspace(workspace_payload)

        self.assertIn(
            {
                "field": "module_ids",
                "code": "module_configuration_mismatch",
                "message": "Saved module_ids do not match the enabled workspace automation modules.",
            },
            error_context.exception.details["field_errors"],
        )

    def test_update_workspace_from_scratch_preserves_run_schedule(self):
        temp_dir = self._workspace_tempdir("builder_schedule_preserve")
        app = create_backend(temp_dir)
        cv_path = temp_dir / "workspace_cv_schedule.txt"
        cv_text = "Builder workspace schedule snapshot"
        cv_path.write_text(cv_text, encoding="utf-8")
        workspace = self._create_builder_workspace_with_cv_snapshot(
            app,
            cv_path=cv_path,
            cv_text=cv_text,
            workspace_name="Scheduled Builder Workspace",
        )

        scheduled_workspace = app.update_workspace_schedule(
            workspace.id,
            {"enabled": True, "interval_days": 4},
        )
        original_schedule = dict(scheduled_workspace.metadata.get("run_schedule") or {})

        updated_workspace = app.update_workspace_from_scratch(
            workspace.id,
            {
                "name": "Scheduled Builder Workspace Updated",
                "description": "Updated through application service",
                "flow_id": "tailored_documents",
                "source_ids": ["linkedin_jobs"],
                "workspace_cv_asset": self._workspace_cv_asset_descriptor(
                    asset_id="asset_workspace_cv_primary",
                    cv_path=cv_path,
                ),
                "module_ids": [
                    "screening_filter",
                    "priority_ranking",
                    "tailored_document_generation",
                ],
                "settings": {
                    **dict(workspace.settings or {}),
                    "keywords": ["consultant"],
                    "stage4_max_jobs": 2,
                },
            },
        )

        preserved_schedule = updated_workspace.metadata.get("run_schedule") or {}
        self.assertTrue(preserved_schedule.get("enabled"))
        self.assertEqual(preserved_schedule.get("interval_days"), 4)
        self.assertEqual(
            preserved_schedule.get("next_run_at"),
            original_schedule.get("next_run_at"),
        )

    def test_builder_can_update_existing_workspace(self):
        temp_dir = self._workspace_tempdir("builder_update")
        app = create_backend(temp_dir)
        cv_path = temp_dir / "workspace_cv.txt"
        cv_path.write_text("Workspace CV", encoding="utf-8")
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
                "workspace_cv_asset": self._workspace_cv_asset_descriptor(
                    asset_id="asset_workspace_cv_primary",
                    cv_path=cv_path,
                ),
                "settings": {
                    "workspace_cv_asset_id": "asset_workspace_cv_primary",
                    "keywords": ["analyst"],
                    "country_codes": ["DE"],
                    "geo_id": "101282230",
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
                "workspace_cv_asset": self._workspace_cv_asset_descriptor(
                    asset_id="asset_workspace_cv_primary",
                    cv_path=cv_path,
                ),
                "settings": {
                    "workspace_cv_asset_id": "asset_workspace_cv_primary",
                    "keywords": ["analyst", "consultant"],
                    "country_codes": ["DE"],
                    "geo_id": "101282230",
                    "manual_url_seed_list": ["https://company.example/jobs/2"],
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

    def test_builder_can_create_academic_jobs_workspace(self):
        temp_dir = self._workspace_tempdir("builder_academic_workspace")
        app = create_backend(temp_dir)
        cv_path = temp_dir / "academic_workspace_cv.txt"
        cv_path.write_text("Academic Workspace CV", encoding="utf-8")
        workspace = app.create_workspace_from_scratch(
            {
                "name": "Academic Search Workspace",
                "flow_id": "tailored_documents",
                "source_ids": ["academic_career_sites"],
                "module_ids": [
                    "screening_filter",
                    "priority_ranking",
                    "tailored_document_generation",
                ],
                "workspace_cv_asset": self._workspace_cv_asset_descriptor(
                    asset_id="asset_academic_workspace_cv",
                    cv_path=cv_path,
                ),
                "settings": {
                    "workspace_cv_asset_id": "asset_academic_workspace_cv",
                    "country_codes": ["DE"],
                    "academic_career_sites": ["Example University | https://university.example/jobs"],
                    "target_roles": ["PhD Researcher", "Postdoctoral Researcher"],
                    "posted_within_days": 7,
                    "stage4_max_jobs": 12,
                },
            }
        )

        self.assertEqual(workspace.metadata["source_ids"], ["academic_career_sites"])
        self.assertEqual(workspace.sources[0].connector_id, "academic_career_sites")
        self.assertEqual(
            workspace.settings["academic_career_sites"],
            [{"company_name": "Example University", "url": "https://university.example/jobs"}],
        )
        self.assertNotIn("company_career_sites", workspace.settings)
        self.assertEqual(workspace.settings["posted_within_days"], 7)

        workflow_template = app.get_workflow_template(workspace.workflow_template_id)
        self.assertTrue(
            any(
                stage.stage_id == "source_academic_career_sites"
                and stage.config.get("connector_id") == "academic_career_sites"
                for stage in workflow_template.stages
            )
        )

    def test_builder_queued_run_uses_snapshotted_workspace_cv_even_if_file_is_deleted(self):
        temp_dir = self._workspace_tempdir("builder_cv_snapshot_runtime")
        app = create_backend(temp_dir)
        cv_path = temp_dir / "workspace_cv.txt"
        cv_path.write_text("Workspace CV Snapshot Text", encoding="utf-8")
        workspace = self._create_builder_workspace_with_cv_snapshot(
            app,
            cv_path=cv_path,
            cv_text="Workspace CV Snapshot Text",
        )

        captured_cv_texts: list[str] = []

        def stage1_stub(stage_args, **_kwargs):
            captured_cv_texts.append(load_cv_text())
            return [
                {
                    "job_id": "builder_job_1",
                    "title": "Analyst",
                    "company": "ACME",
                    "link": "https://example.com/jobs/1",
                    "apply_link": "https://example.com/jobs/1",
                }
            ]

        def stage4_stub(stage4_args, *, config=None, jobs=None):
            captured_cv_texts.append(load_cv_text())
            return [
                {
                    **dict(job),
                    "cv_docx": str(temp_dir / "generated_docs" / "builder_job_1_CV.docx"),
                    "cv_pdf": str(temp_dir / "generated_docs" / "builder_job_1_CV.pdf"),
                }
                for job in (jobs or [])
            ]

        with patch("backend.adapters.stage_adapters.run_tailored_stage1_pipeline", side_effect=stage1_stub), patch(
            "backend.adapters.stage_adapters.run_tailored_stage2_pipeline",
            side_effect=lambda jobs, cli_args: (list(jobs), []),
        ), patch(
            "backend.adapters.stage_adapters.run_tailored_stage3_pipeline",
            side_effect=lambda jobs, cli_args: (list(jobs), []),
        ), patch(
            "backend.adapters.stage_adapters.run_tailored_stage4_pipeline",
            side_effect=stage4_stub,
        ):
            planned_run = app.start_run(workspace.id, execute=False, requested_by="test")
            self.assertEqual(planned_run.run_plan.resolved_run_settings["workspace_cv_text"], "Workspace CV Snapshot Text")

            cv_path.unlink()

            queued_run = app.resume_run(planned_run.id)
            self.assertEqual(queued_run.status, "queued")
            completed_run = app.process_next_queued_run(auto_retry_failed=False)

        self.assertEqual(completed_run.status, "completed")
        self.assertEqual(captured_cv_texts, ["Workspace CV Snapshot Text", "Workspace CV Snapshot Text"])

    def test_builder_standard_cv_mode_skips_tailoring_and_reuses_workspace_cv_path(self):
        temp_dir = self._workspace_tempdir("builder_standard_cv_mode")
        app = create_backend(temp_dir)
        cv_path = temp_dir / "workspace_cv.pdf"
        cv_path.write_bytes(b"%PDF-1.4 standard workspace cv")
        workspace = self._create_builder_workspace_with_cv_snapshot(
            app,
            cv_path=cv_path,
            cv_text="Workspace CV Snapshot Text",
            cv_generation_mode="standard_cv",
        )
        expected_cv_bytes = cv_path.read_bytes()
        cv_path.unlink()

        with patch(
            "backend.adapters.stage_adapters.run_tailored_stage1_pipeline",
            return_value=[
                {
                    "job_id": "builder_job_standard_1",
                    "title": "Analyst",
                    "company": "ACME",
                    "link": "https://example.com/jobs/1",
                    "apply_link": "https://example.com/jobs/1",
                }
            ],
        ), patch(
            "backend.adapters.stage_adapters.run_tailored_stage2_pipeline",
            side_effect=lambda jobs, cli_args: (list(jobs), []),
        ), patch(
            "backend.adapters.stage_adapters.run_tailored_stage3_pipeline",
            side_effect=lambda jobs, cli_args: (list(jobs), []),
        ), patch(
            "backend.adapters.stage_adapters.run_tailored_stage4_pipeline",
        ) as stage4_pipeline:
            with patch("backend.capabilities.tailored_documents.documents.save_json_file"), patch(
                "backend.capabilities.tailored_documents.documents.save_to_excel"
            ):
                run = app.start_run(workspace.id, execute=True, requested_by="test")

        self.assertEqual(run.status, "completed")
        stage4_pipeline.assert_not_called()

        generated_jobs = app.list_job_sets(run.id)["generated_jobs"]
        self.assertEqual(len(generated_jobs), 1)
        generated_job = generated_jobs[0].to_dict()
        self.assertEqual(generated_job["cv_generation_mode"], "standard_cv")
        applied_cv_path = Path(generated_job["applied_cv"])
        self.assertNotEqual(applied_cv_path, cv_path.resolve())
        self.assertEqual(applied_cv_path.read_bytes(), expected_cv_bytes)
        self.assertEqual(generated_job["document_asset_kind"], "applied_cv")

        artifacts = app.list_artifacts(run.id)
        applied_cv_artifact = next(
            artifact for artifact in artifacts if artifact.artifact_type == "applied_cv"
        )
        self.assertEqual(applied_cv_artifact.path, str(applied_cv_path))
        self.assertEqual(applied_cv_artifact.metadata["job_id"], "builder_job_standard_1")

    def test_builder_run_start_rejects_deleted_workspace_cv_asset(self):
        temp_dir = self._workspace_tempdir("builder_missing_cv_snapshot")
        app = create_backend(temp_dir)
        cv_path = temp_dir / "workspace_cv.txt"
        cv_path.write_text("Workspace CV Snapshot Text", encoding="utf-8")
        workspace = self._create_builder_workspace_with_cv_snapshot(
            app,
            cv_path=cv_path,
            cv_text="Workspace CV Snapshot Text",
        )
        cv_path.unlink()
        app.object_storage.delete(workspace.settings["workspace_cv_asset_object_key"])

        with patch("backend.adapters.stage_adapters.run_tailored_stage1_pipeline") as stage1_pipeline:
            with self.assertRaises(BackendValidationError) as error_context:
                app.start_run(workspace.id, execute=True, requested_by="test")

        self.assertEqual(error_context.exception.error_code, "run_preflight_failed")
        self.assertEqual(
            error_context.exception.details["field_errors"][0]["code"],
            "workspace_cv_asset_missing_file",
        )
        stage1_pipeline.assert_not_called()

    def test_builder_run_start_rejects_mismatched_workspace_cv_override(self):
        temp_dir = self._workspace_tempdir("builder_cv_override_mismatch")
        app = create_backend(temp_dir)
        cv_path = temp_dir / "workspace_cv.txt"
        cv_path.write_text("Workspace CV Snapshot Text", encoding="utf-8")
        workspace = self._create_builder_workspace_with_cv_snapshot(
            app,
            cv_path=cv_path,
            cv_text="Workspace CV Snapshot Text",
        )

        with self.assertRaises(BackendValidationError) as error_context:
            app.start_run(
                workspace.id,
                run_input_overrides={"workspace_cv_asset_id": "asset_stale_workspace_cv"},
                execute=False,
                requested_by="test",
            )

        self.assertEqual(error_context.exception.error_code, "run_preflight_failed")
        self.assertIn(
            {
                "field": "workspace_cv_asset_id",
                "code": "workspace_cv_asset_mismatch",
                "message": "Run workspace_cv_asset_id does not match the saved workspace CV.",
            },
            error_context.exception.details["field_errors"],
        )

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

        self.assertIn("academic_career_sites", connector_ids)
        self.assertIn("linkedin_jobs", connector_ids)
        self.assertIn("linkedin_search", connector_ids)
        self.assertIn("job_board_collection", connector_ids)
        self.assertIn("blue_collar_portals", connector_ids)
        self.assertIn("job_board_indeed", connector_ids)
        self.assertIn("tailored_application_documents", generation_ids)
        self.assertIn("white_collar_cv_generation", generation_ids)
        self.assertIn("blue_collar_role_cv_generation", generation_ids)
        self.assertIn("application_document_export", renderer_ids)
        self.assertIn("docx_pdf_renderer", renderer_ids)
        self.assertIn("blue_collar_package_renderer", renderer_ids)
        self.assertTrue(app.registries.stage_registry.contains("legacy.blue_collar.stage1"))
        self.assertTrue(app.registries.stage_registry.contains("legacy.white_collar.docs"))

    def test_missing_or_invalid_stage_definitions_fail_run_instead_of_leaving_it_running(self):
        app, _ = self._create_app_with_test_workflow("invalid_stage_failure")
        app.upsert_workflow_template(
            {
                "id": "invalid_stage_template_v1",
                "name": "Invalid Stage Template",
                "stages": [
                    StageDefinition(
                        stage_id="missing_stage",
                        stage_type="test.stage_does_not_exist",
                        name="Missing Stage",
                        output_key="missing_output",
                    ).to_dict()
                ],
            }
        )
        app.upsert_workspace(
            {
                "id": "invalid_stage_workspace",
                "name": "Invalid Stage Workspace",
                "workflow_template_id": "invalid_stage_template_v1",
                "workspace_type": "custom",
                "sources": [],
            }
        )

        run = app.start_run("invalid_stage_workspace", execute=True, requested_by="test")
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.current_stage_id, "missing_stage")
        self.assertEqual(len(run.stage_results), 1)
        self.assertEqual(run.stage_results[0].status, "failed")
        self.assertIn("test.stage_does_not_exist", run.last_error)

    def test_can_run_exceptions_fail_run_cleanly(self):
        app, _ = self._create_app_with_test_workflow("can_run_failure")
        app.upsert_workflow_template(
            {
                "id": "can_run_template_v1",
                "name": "Can Run Failure Template",
                "stages": [
                    StageDefinition(
                        stage_id="explode_in_can_run",
                        stage_type="test.can_run_explodes",
                        name="Explode In can_run",
                        output_key="exploded_output",
                    ).to_dict()
                ],
            }
        )
        app.upsert_workspace(
            {
                "id": "can_run_workspace",
                "name": "Can Run Workspace",
                "workflow_template_id": "can_run_template_v1",
                "workspace_type": "custom",
                "sources": [],
            }
        )

        run = app.start_run("can_run_workspace", execute=True, requested_by="test")
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.current_stage_id, "explode_in_can_run")
        self.assertEqual(len(run.stage_results), 1)
        self.assertEqual(run.stage_results[0].status, "failed")
        self.assertEqual(run.stage_results[0].error, "can_run exploded")

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

        target_contact_discovery = app.generate_target_contact_discovery(
            user_id=user.user_id,
            run_id=completed_run.id,
            job_id="job_1",
        )
        self.assertIn("candidates", target_contact_discovery)
        self.assertGreaterEqual(len(target_contact_discovery["candidates"]), 4)
        self.assertEqual(target_contact_discovery["job"]["job_id"], "job_1")

    def test_relevant_people_discovery_persists_selected_people_for_job_workspace(self):
        app, _ = self._create_app_with_test_workflow("relevant_people_workspace_context")
        user = app.upsert_user(
            {
                "email": "peoplefinder@example.com",
                "display_name": "People Finder User",
                "role": "admin",
                "metadata": {"profile": {"summary": "Operations and analytics professional."}},
            }
        )

        completed_run = app.start_run("custom_workspace", execute=True, requested_by="test")
        self.assertEqual(completed_run.status, "failed")
        completed_run = app.retry_run(completed_run.id)
        completed_run = app.process_next_queued_run(auto_retry_failed=True)
        self.assertEqual(completed_run.status, "completed")

        job = app.get_job_set(completed_run.id, "accepted_jobs")[0]
        discovery_payload = build_empty_relevant_people_discovery(
            job=job,
            run_id=completed_run.id,
            workspace_id="custom_workspace",
            status="completed",
        )
        discovery_payload["categories"] = {
            "hiring_manager": [
                {
                    "id": "person_hiring_manager_jane",
                    "category": "hiring_manager",
                    "name": "Jane Hiringmanager",
                    "title": "Analytics Manager",
                    "company": "ACME",
                    "location": "Berlin, Germany",
                    "profileUrl": "https://www.linkedin.com/in/jane-hiringmanager",
                    "source": "public_profile_search",
                    "confidence": 82,
                    "confidenceLabel": "High",
                    "reasoningNote": "Likely relevant because this person appears to lead the same function.",
                    "evidenceSnippets": ["Analytics Manager", "ACME", "Berlin"],
                    "caveats": [],
                    "searchQueries": ["ACME Analytics Manager Berlin LinkedIn"],
                    "discoveredSearchQuery": "ACME Analytics Manager Berlin LinkedIn",
                    "regionScopeCaveat": "",
                    "confidenceBreakdown": None,
                    "status": "unreviewed",
                }
            ],
            "potential_colleague": [],
            "executive": [],
        }

        with patch(
            "backend.application.services.build_relevant_people_discovery",
            return_value=discovery_payload,
        ):
            started = app.start_relevant_people_discovery(
                user_id=user.user_id,
                run_id=completed_run.id,
                job_id=job.job_id,
            )

        self.assertEqual(started["peopleDiscoveryStatus"], "completed")
        self.assertEqual(started["selectedPeople"], [])

        status_payload = app.get_relevant_people_discovery_status(
            user_id=user.user_id,
            run_id=completed_run.id,
            job_id=job.job_id,
        )
        self.assertEqual(status_payload["peopleDiscoveryStatus"], "completed")
        self.assertEqual(status_payload["selectedPeopleCount"], 0)

        updated = app.set_relevant_people_status(
            user_id=user.user_id,
            run_id=completed_run.id,
            job_id=job.job_id,
            person_id="person_hiring_manager_jane",
            status="confirmed",
        )
        self.assertEqual(updated["categories"]["hiring_manager"][0]["status"], "confirmed")
        self.assertEqual(len(updated["selectedPeople"]), 1)
        self.assertEqual(updated["selectedPeople"][0]["name"], "Jane Hiringmanager")

        workspace_payload = app.get_job_workspace(
            user_id=user.user_id,
            run_id=completed_run.id,
            job_id=job.job_id,
        )
        self.assertEqual(len(workspace_payload["selected_relevant_people"]), 1)
        self.assertEqual(
            workspace_payload["selected_relevant_people"][0]["id"],
            "person_hiring_manager_jane",
        )

    def test_referral_import_merges_companies_for_one_person(self):
        app, _ = self._create_app_with_test_workflow("referral_import")
        user = app.upsert_user(
            {
                "email": "imports@example.com",
                "display_name": "Import User",
                "role": "admin",
            }
        )

        import_payload = app.import_referral_contacts(
            user_id=user.user_id,
            csv_text=(
                "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
                "Jane,Referrer,https://linkedin.com/in/jane-referrer,,ACME,Engineering Manager,01 Jan 2024\n"
                "Jane,Referrer,https://linkedin.com/in/jane-referrer,,Beta,Director,01 Jan 2024\n"
            ),
        )
        self.assertEqual(import_payload["summary"]["created"], 1)
        self.assertEqual(import_payload["summary"]["updated"], 1)

        contacts = app.list_referral_contacts(user.user_id)
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0].name, "Jane Referrer")
        self.assertEqual(
            [entry["company_name"] for entry in contacts[0].companies],
            ["ACME", "Beta"],
        )
        self.assertEqual(contacts[0].source_kind, "linkedin_csv")

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

    def test_upsert_review_reuses_existing_review_for_same_job(self):
        app, _ = self._create_app_with_test_workflow("review_upsert_reuse")

        run = app.start_run("custom_workspace", execute=False, requested_by="test")
        self.assertEqual(run.status, "planned")
        app.upsert_job_set(
            run.id,
            "accepted_jobs",
            [{"job_id": "job_1", "title": "Analyst", "company": "ACME"}],
        )

        original = app.upsert_review(
            run_id=run.id,
            payload={
                "job_id": "job_1",
                "status": "waiting_review",
                "metadata": {"tracker_status": "applied"},
            },
        )
        placed_in_tracker_at = original.metadata.get("placed_in_tracker_at")
        self.assertTrue(placed_in_tracker_at)
        updated = app.upsert_review(
            run_id=run.id,
            payload={
                "job_id": "job_1",
                "decision": "approved",
                "status": "approved",
                "reviewer": "tester",
                "metadata": {"placed_in_tracker_at": "1900-01-01T00:00:00+00:00"},
            },
        )

        self.assertEqual(original.review_id, updated.review_id)
        self.assertEqual(updated.decision, "approved")
        self.assertEqual(updated.status, "approved")
        self.assertEqual(updated.metadata["tracker_status"], "applied")
        self.assertEqual(updated.metadata["placed_in_tracker_at"], placed_in_tracker_at)
        self.assertEqual(len(app.list_reviews(run_id=run.id)), 1)

    def test_document_generation_runs_auto_approve_generated_jobs(self):
        app, _ = self._create_app_with_test_workflow("auto_approve_generated_jobs")
        app.upsert_workflow_template(
            {
                "id": "auto_approve_template",
                "name": "Auto Approve Template",
                "description": "Auto-approve generated applications.",
                "stages": [
                    StageDefinition(
                        stage_id="seed_jobs",
                        stage_type="test.seed_jobs",
                        name="Seed Jobs",
                        output_key="accepted_jobs",
                    ).to_dict(),
                    StageDefinition(
                        stage_id="generate_documents",
                        stage_type="applications.generate.documents",
                        name="Generate Documents",
                        input_keys=["accepted_jobs"],
                        output_key="generated_jobs",
                    ).to_dict(),
                ],
                "default_run_settings": {"automation_flow": "tailored_documents"},
            }
        )
        app.upsert_workspace(
            {
                "id": "auto_approve_workspace",
                "name": "Auto Approve Workspace",
                "workflow_template_id": "auto_approve_template",
                "workspace_type": "custom",
                "settings": {"automation_flow": "tailored_documents"},
                "sources": [{"id": "manual_source", "connector_id": "curated_job_urls"}],
            }
        )

        run = app.start_run("auto_approve_workspace", execute=True, requested_by="test")
        self.assertEqual(run.status, "completed")

        reviews = app.list_reviews(run_id=run.id)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].job_id, "job_1")
        self.assertEqual(reviews[0].job_set_key, "generated_jobs")
        self.assertEqual(reviews[0].status, "approved")
        self.assertEqual(reviews[0].decision, "approved")
        self.assertEqual(reviews[0].reviewer, "system")
        self.assertTrue(reviews[0].metadata.get("auto_approved"))
        self.assertTrue(reviews[0].metadata.get("placed_in_tracker_at"))

    def test_document_generation_failure_does_not_complete_run(self):
        temp_dir = self._workspace_tempdir("document_generation_failure_blocks_completion")
        app = create_backend(temp_dir)
        app.registries.stage_registry.register("test.seed_jobs", _SeedJobsStage())
        app.registries.stage_registry.register(
            "applications.generate.documents",
            _FailedDocumentGenerationStage(),
        )
        app.upsert_workflow_template(
            {
                "id": "failed_documents_template",
                "name": "Failed Documents Template",
                "stages": [
                    StageDefinition(
                        stage_id="seed_jobs",
                        stage_type="test.seed_jobs",
                        name="Seed Jobs",
                        output_key="accepted_jobs",
                    ).to_dict(),
                    StageDefinition(
                        stage_id="generate_documents",
                        stage_type="applications.generate.documents",
                        name="Generate Documents",
                        input_keys=["accepted_jobs"],
                        output_key="generated_jobs",
                    ).to_dict(),
                ],
                "default_run_settings": {"automation_flow": "tailored_documents"},
            }
        )
        app.upsert_workspace(
            {
                "id": "failed_documents_workspace",
                "name": "Failed Documents Workspace",
                "workflow_template_id": "failed_documents_template",
                "settings": {"automation_flow": "tailored_documents"},
                "sources": [],
            }
        )

        run = app.start_run("failed_documents_workspace", execute=True, requested_by="test")

        self.assertEqual(run.status, "failed")
        self.assertIn("Document generation produced no usable documents", run.last_error)
        self.assertFalse(
            [
                artifact
                for artifact in app.list_artifacts(run.id)
                if str(artifact.artifact_id).startswith("generated_")
            ]
        )
        self.assertFalse(app.list_reviews(run_id=run.id))
        self.assertEqual(run.stage_results[-1].status, "failed")

    def test_document_generation_without_document_artifact_does_not_complete_run(self):
        temp_dir = self._workspace_tempdir("document_generation_no_artifact_blocks_completion")
        app = create_backend(temp_dir)
        app.registries.stage_registry.register("test.seed_jobs", _SeedJobsStage())
        app.registries.stage_registry.register(
            "applications.generate.documents",
            _NoArtifactDocumentGenerationStage(),
        )
        app.upsert_workflow_template(
            {
                "id": "no_artifact_documents_template",
                "name": "No Artifact Documents Template",
                "stages": [
                    StageDefinition(
                        stage_id="seed_jobs",
                        stage_type="test.seed_jobs",
                        name="Seed Jobs",
                        output_key="accepted_jobs",
                    ).to_dict(),
                    StageDefinition(
                        stage_id="generate_documents",
                        stage_type="applications.generate.documents",
                        name="Generate Documents",
                        input_keys=["accepted_jobs"],
                        output_key="generated_jobs",
                    ).to_dict(),
                ],
                "default_run_settings": {"automation_flow": "tailored_documents"},
            }
        )
        app.upsert_workspace(
            {
                "id": "no_artifact_documents_workspace",
                "name": "No Artifact Documents Workspace",
                "workflow_template_id": "no_artifact_documents_template",
                "settings": {"automation_flow": "tailored_documents"},
                "sources": [],
            }
        )

        run = app.start_run("no_artifact_documents_workspace", execute=True, requested_by="test")

        self.assertEqual(run.status, "failed")
        self.assertIn("Document generation produced no usable documents", run.last_error)
        self.assertFalse(
            [
                artifact
                for artifact in app.list_artifacts(run.id)
                if str(artifact.artifact_id).startswith("generated_")
            ]
        )
        self.assertFalse(app.list_reviews(run_id=run.id))
        self.assertEqual(run.stage_results[-1].status, "failed")

    def test_test_run_selects_one_surviving_job_and_adds_it_to_tracker(self):
        temp_dir = self._workspace_tempdir("test_run_single_survivor")
        app = create_backend(temp_dir)
        app.registries.stage_registry.register("test.seed_candidates", _SeedTestCandidatesStage())
        app.registries.stage_registry.register("test.accept_candidates", _AcceptTestCandidatesStage())
        app.registries.stage_registry.register("applications.generate.documents", _DocumentGenerationStage())
        app.upsert_workflow_template(
            {
                "id": "test_run_template",
                "name": "Test Run Template",
                "stages": [
                    StageDefinition(
                        stage_id="source_jobs",
                        stage_type="test.seed_candidates",
                        name="Source Jobs",
                        output_key="source_jobs",
                    ).to_dict(),
                    StageDefinition(
                        stage_id="screen_jobs",
                        stage_type="test.accept_candidates",
                        name="Screen Jobs",
                        input_keys=["source_jobs"],
                        output_key="accepted_jobs",
                    ).to_dict(),
                    StageDefinition(
                        stage_id="generate_documents",
                        stage_type="applications.generate.documents",
                        name="Generate Documents",
                        input_keys=["accepted_jobs"],
                        output_key="generated_jobs",
                    ).to_dict(),
                ],
                "default_run_settings": {"automation_flow": "tailored_documents"},
            }
        )
        app.upsert_workspace(
            {
                "id": "test_run_workspace",
                "name": "Test Run Workspace",
                "workflow_template_id": "test_run_template",
                "settings": {"automation_flow": "tailored_documents"},
                "sources": [],
            }
        )

        run = app.start_run(
            "test_run_workspace",
            execute=True,
            requested_by="test",
            run_input_overrides={"run_mode": "test", "test_run_job_limit": 1},
        )

        self.assertTrue(run.is_test_run)
        self.assertEqual([job.job_id for job in app.get_job_set(run.id, "accepted_jobs")], ["accepted_job_1"])
        self.assertEqual([job.job_id for job in app.get_job_set(run.id, "generated_jobs")], ["accepted_job_1"])
        reviews = app.list_reviews(run_id=run.id)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].job_id, "accepted_job_1")
        self.assertEqual(reviews[0].job_set_key, "generated_jobs")
        self.assertEqual(reviews[0].decision, "approved")
        self.assertEqual(reviews[0].status, "approved")
        self.assertTrue(reviews[0].metadata.get("auto_approved"))
        self.assertTrue(reviews[0].metadata.get("placed_in_tracker_at"))
        self.assertEqual(len(app.list_artifacts(run.id)), 1)

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

    def test_delete_run_removes_completed_run(self):
        app, _ = self._create_app_with_test_workflow("delete_completed_run")

        run = app.enqueue_run("custom_workspace", requested_by="test-delete", max_attempts=2)
        app.process_next_queued_run(auto_retry_failed=True)
        completed_run = app.process_next_queued_run(auto_retry_failed=True)
        self.assertEqual(completed_run.status, "completed")

        app.delete_run(completed_run.id)

        with self.assertRaises(KeyError):
            app.get_run(completed_run.id)

    def test_delete_job_removes_related_run_data(self):
        app, _ = self._create_app_with_test_workflow("delete_job")

        run = app.enqueue_run("custom_workspace", requested_by="test-delete", max_attempts=2)
        app.process_next_queued_run(auto_retry_failed=True)
        completed_run = app.process_next_queued_run(auto_retry_failed=True)
        self.assertEqual(completed_run.status, "completed")

        review = app.upsert_review(
            run_id=completed_run.id,
            payload={
                "job_id": "job_1",
                "decision": "approved",
                "reviewer": "tester",
                "job_set_key": "accepted_jobs",
                "status": "approved",
            },
        )
        self.assertEqual(review.job_id, "job_1")
        app.repositories.job_store.save_blob(
            completed_run.id,
            "stage2_rejected",
            [{"job_id": "job_1"}, {"job_id": "job_2"}],
        )

        app.delete_job(completed_run.id, "job_1")

        self.assertEqual(app.list_job_sets(completed_run.id), {})
        self.assertEqual(app.list_reviews(run_id=completed_run.id), [])
        self.assertEqual(app.list_artifacts(completed_run.id), [])
        self.assertEqual(
            app.repositories.job_store.load_blob(completed_run.id, "stage2_rejected", []),
            [{"job_id": "job_2"}],
        )

    def test_delete_job_removes_generated_document_containers_when_no_jobs_remain(self):
        app, temp_dir = self._create_app_with_test_workflow("delete_job_document_containers")

        run = app.enqueue_run("custom_workspace", requested_by="test-delete", max_attempts=2)
        app.process_next_queued_run(auto_retry_failed=True)
        completed_run = app.process_next_queued_run(auto_retry_failed=True)
        self.assertEqual(completed_run.status, "completed")

        docs_dir = temp_dir / "tracker_docs" / completed_run.id
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "job_1_CV.docx").write_bytes(b"docx-content")
        manifest_path = temp_dir / f"{completed_run.id}_documents.json"
        manifest_path.write_text("{}", encoding="utf-8")

        app.upsert_artifact(
            completed_run.id,
            {
                "artifact_id": "generated_docs_dir",
                "artifact_type": "stage5_docs_dir",
                "path": str(docs_dir),
                "metadata": {"status": "ready"},
            },
        )
        app.upsert_artifact(
            completed_run.id,
            {
                "artifact_id": "generated_documents_manifest",
                "artifact_type": "documents_json",
                "path": str(manifest_path),
                "metadata": {"status": "ready"},
            },
        )

        app.delete_job(completed_run.id, "job_1")

        self.assertEqual(app.list_job_sets(completed_run.id), {})
        self.assertEqual(app.list_artifacts(completed_run.id), [])

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

    def test_authenticate_access_token_uses_prefix_candidates(self):
        app, _ = self._create_app_with_test_workflow("auth_prefix_candidates")

        user = app.upsert_user(
            {
                "email": "prefix@example.com",
                "display_name": "Prefix User",
                "role": "editor",
                "allowed_workspace_ids": ["custom_workspace"],
            }
        )
        token, raw_token = app.issue_api_token(user_id=user.user_id, name="prefix-token")

        original_list_api_tokens = app.repositories.auth_repository.list_api_tokens

        def fail_if_full_scan(*args, **kwargs):
            if kwargs.get("active_only"):
                raise AssertionError("authenticate_access_token fell back to a full active-token scan")
            return original_list_api_tokens(*args, **kwargs)

        app.repositories.auth_repository.list_api_tokens = fail_if_full_scan
        self.addCleanup(setattr, app.repositories.auth_repository, "list_api_tokens", original_list_api_tokens)

        authenticated_user, authenticated_token = app.authenticate_access_token(raw_token)

        self.assertEqual(authenticated_user.user_id, user.user_id)
        self.assertEqual(authenticated_token.token_id, token.token_id)


if __name__ == "__main__":
    unittest.main()
