import unittest
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from backend.adapters.stage_adapters import (
    CompanyCareerSiteAcquisitionStage,
    LinkedInAcquireStage,
    TailoredPrioritizationStage,
    TailoredScreeningStage,
    _prepare_company_site_source_settings,
    _resolve_company_site_stage_limits,
    _tailored_document_artifacts,
)
from backend.domain.models import StageDefinition


class StageAdapterTests(unittest.TestCase):
    def test_deprecated_company_site_link_cap_setting_is_still_honored(self):
        with self.assertLogs("backend.adapters.stage_adapters", level="WARNING") as logs:
            limits = _resolve_company_site_stage_limits(
                SimpleNamespace(company_site_emergency_max_job_links_per_site=12),
            )

        self.assertEqual(limits["max_job_links_per_site"], 12)
        self.assertIn("deprecated", "\n".join(logs.output).lower())

    def test_linkedin_acquire_stage_persists_stage1_exclusions_as_run_data(self):
        with TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "stage1_output.json"
            excluded_path = Path(temp_dir) / "stage1_excluded.json"
            excluded_path.write_text(
                '[{"job_id": "rejected_1", "title": "Senior Engineer", "reason": "Title mismatch"}]',
                encoding="utf-8",
            )
            context = SimpleNamespace(
                run=SimpleNamespace(id="run_1"),
                registries=SimpleNamespace(connector_registry=SimpleNamespace(get=lambda _connector_id: None)),
            )
            definition = StageDefinition(
                stage_id="source_linkedin_search",
                stage_type="jobs.acquire.search_listings",
                name="Acquire Search Listings",
                output_key="source_linkedin_jobs",
            )

            with (
                patch("backend.adapters.stage_adapters._build_root_cli_args", return_value=({}, SimpleNamespace())),
                patch(
                    "backend.adapters.stage_adapters.build_tailored_stage1_args",
                    return_value=SimpleNamespace(output=str(output_path), excluded_output=str(excluded_path)),
                ),
                patch("backend.adapters.stage_adapters.runtime_cv_override", return_value=nullcontext()),
                patch(
                    "backend.adapters.stage_adapters.run_tailored_stage1_pipeline",
                    return_value=[{"job_id": "accepted_1", "title": "Engineer", "company": "ACME"}],
                ),
            ):
                outcome = LinkedInAcquireStage().execute(context, definition)

        self.assertEqual(outcome.metrics["jobs_found"], 1)
        self.assertEqual(len(outcome.job_sets["source_linkedin_jobs"]), 1)
        self.assertEqual(
            outcome.data["source_linkedin_search_rejected"],
            [{"job_id": "rejected_1", "title": "Senior Engineer", "reason": "Title mismatch"}],
        )
        artifact_types = [artifact.artifact_type for artifact in outcome.artifacts]
        self.assertIn("stage1_output", artifact_types)
        self.assertIn("stage1_excluded", artifact_types)

    def test_tailored_document_artifacts_emit_per_file_cv_entries_with_ats_metadata(self):
        artifacts = _tailored_document_artifacts(
            "run_1",
            "stage_4",
            output_json="stage4_documents.json",
            output_xlsx="final_jobs_with_docs.xlsx",
            records=[
                {
                    "job_id": "job_1",
                    "title": "Senior Analyst",
                    "company": "ACME",
                    "cv_docx": "generated_docs/job_1_CV.docx",
                    "cv_pdf": "generated_docs/job_1_CV.pdf",
                    "ats_score": 84,
                    "ats_target_score": 90,
                    "ats_attempt_count": 2,
                    "ats_max_attempts": 3,
                    "missing_requirements": ["SQL"],
                    "ats_stop_reason": "score_stalled",
                    "ats_export_gate": {
                        "target_score": 90,
                        "best_score": 84,
                        "attempt_count": 2,
                        "max_attempts": 3,
                        "gate_state": "blocked",
                        "can_export_final": False,
                        "export_anyway_allowed": True,
                        "missing_requirements": ["SQL"],
                        "last_warning": "We could not reach 90%. Best score reached: 84%. Review the missing requirements or continue anyway.",
                        "metadata": {"stop_reason": "score_stalled"},
                    },
                }
            ],
        )

        artifact_types = [artifact.artifact_type for artifact in artifacts]
        self.assertEqual(artifact_types[:2], ["documents_json", "documents_xlsx"])
        self.assertNotIn("docs_dir", artifact_types)

        docx_artifact = next(artifact for artifact in artifacts if artifact.artifact_type == "cv_docx")
        pdf_artifact = next(artifact for artifact in artifacts if artifact.artifact_type == "cv_pdf")

        self.assertEqual(docx_artifact.metadata["job_id"], "job_1")
        self.assertEqual(docx_artifact.metadata["ats_score"], 84)
        self.assertEqual(docx_artifact.metadata["ats_export_gate"]["gate_state"], "blocked")
        self.assertEqual(docx_artifact.metadata["ats_stop_reason"], "score_stalled")
        self.assertEqual(pdf_artifact.metadata["ats_export_gate"]["metadata"]["stop_reason"], "score_stalled")

    def test_tailored_document_artifacts_preserve_applied_cv_references(self):
        artifacts = _tailored_document_artifacts(
            "run_2",
            "stage_4",
            output_json="stage4_documents.json",
            output_xlsx="final_jobs_with_docs.xlsx",
            records=[
                {
                    "job_id": "job_standard_1",
                    "title": "Analyst",
                    "company": "ACME",
                    "cv_generation_mode": "standard_cv",
                    "applied_cv": "candidate_assets/workspace_cv.pdf",
                    "applied_cv_asset_id": "asset_workspace_cv",
                    "document_asset_kind": "applied_cv",
                    "document_display_name": "Applied Workspace CV",
                }
            ],
        )

        applied_cv_artifact = next(artifact for artifact in artifacts if artifact.artifact_type == "applied_cv")
        self.assertEqual(applied_cv_artifact.path, "candidate_assets/workspace_cv.pdf")
        self.assertEqual(applied_cv_artifact.metadata["cv_generation_mode"], "standard_cv")
        self.assertEqual(applied_cv_artifact.metadata["document_asset_kind"], "applied_cv")

    def test_tailored_screening_stage_translates_root_args_to_stage2_args(self):
        captured_args = []
        context = SimpleNamespace(
            run=SimpleNamespace(id="run_stage2"),
            get_job_dicts=lambda _key: [{"job_id": "job_1", "title": "Analyst", "company": "ACME"}],
        )
        definition = StageDefinition(
            stage_id="screen_jobs",
            stage_type="jobs.screen.filter",
            name="Screen Jobs",
            input_keys=["source_jobs"],
            output_key="screened_jobs",
        )
        cli_args = SimpleNamespace(
            stage1_output="stage1.json",
            stage2_output="stage2.json",
            stage2_rejected_output="stage2_rejected.json",
            german_special_char_threshold=9999,
            french_special_char_threshold=0,
            spanish_special_char_threshold=0,
            max_german_level="B2",
        )

        def fake_stage2(jobs, stage_args):
            captured_args.append(stage_args)
            return list(jobs), []

        with (
            patch("backend.adapters.stage_adapters._build_root_cli_args", return_value=({}, cli_args)),
            patch("backend.adapters.stage_adapters.run_tailored_stage2_pipeline", side_effect=fake_stage2),
        ):
            outcome = TailoredScreeningStage().execute(context, definition)

        self.assertEqual(outcome.metrics["approved"], 1)
        self.assertEqual(captured_args[0].output, "stage2.json")
        self.assertEqual(captured_args[0].rejected, "stage2_rejected.json")

    def test_tailored_prioritization_stage_translates_root_args_to_stage3_args(self):
        captured_args = []
        context = SimpleNamespace(
            run=SimpleNamespace(id="run_stage3"),
            get_job_dicts=lambda _key: [{"job_id": "job_1", "title": "Analyst", "company": "ACME"}],
        )
        definition = StageDefinition(
            stage_id="rank_jobs",
            stage_type="jobs.prioritize",
            name="Rank Jobs",
            input_keys=["screened_jobs"],
            output_key="ranked_jobs",
        )
        cli_args = SimpleNamespace(
            stage2_output="stage2.json",
            stage3_output="stage3.json",
            stage3_rejected_output="stage3_rejected.json",
            low_applicant_threshold=80,
            stage3_german_special_char_threshold=9999,
            stage3_french_special_char_threshold=0,
            stage3_spanish_special_char_threshold=0,
            stage3_max_german_level="B2",
        )

        def fake_stage3(jobs, stage_args):
            captured_args.append(stage_args)
            return list(jobs), []

        with (
            patch("backend.adapters.stage_adapters._build_root_cli_args", return_value=({}, cli_args)),
            patch("backend.adapters.stage_adapters.run_tailored_stage3_pipeline", side_effect=fake_stage3),
        ):
            outcome = TailoredPrioritizationStage().execute(context, definition)

        self.assertEqual(outcome.metrics["approved"], 1)
        self.assertEqual(captured_args[0].output, "stage3.json")
        self.assertEqual(captured_args[0].rejected, "stage3_rejected.json")

    def test_prepare_company_site_source_settings_merges_pasted_and_discovered_sites(self):
        definition = StageDefinition(
            stage_id="source_company_career_sites",
            stage_type="jobs.acquire.company_sites",
            name="Acquire Company Career Site Jobs",
            config={"site_settings_key": "company_career_sites", "discovered_site_paths": ["dummy.txt"]},
        )
        settings = {
            "company_career_sites": [
                {"company_name": "Manual", "url": "https://manual.example/jobs"},
                {"company_name": "Shared", "url": "https://shared.example/careers"},
            ]
        }

        with patch(
            "backend.adapters.stage_adapters.load_discovered_company_site_entries",
            return_value=[
                {"company_name": "Shared Duplicate", "url": "https://shared.example/careers"},
                {"company_name": "Saved", "url": "https://saved.example/careers"},
            ],
        ):
            normalized = _prepare_company_site_source_settings(settings, definition)

        self.assertEqual(
            normalized["company_career_sites"],
            [
                {"company_name": "Manual", "url": "https://manual.example/jobs"},
                {"company_name": "Shared", "url": "https://shared.example/careers"},
                {"company_name": "Saved", "url": "https://saved.example/careers"},
            ],
        )

    def test_company_career_site_stage_passes_proxy_fallback_flag(self):
        context = SimpleNamespace(
            run=SimpleNamespace(id="run_1"),
            logger=None,
            data={},
            registries=SimpleNamespace(connector_registry=SimpleNamespace(get=lambda _connector_id: None)),
        )
        definition = StageDefinition(
            stage_id="source_company_career_sites",
            stage_type="jobs.acquire.company_sites",
            name="Acquire Company Career Site Jobs",
            output_key="source_company_career_jobs",
            config={"connector_id": "company_career_sites"},
        )
        cli_args = SimpleNamespace(
            company_career_sites=[{"company_name": "Acme", "url": "https://careers.acme.example"}],
            keywords=["product owner"],
            company_site_request_timeout_seconds=30,
            company_site_max_jobs_per_site=10,
            posted_within_days=7,
            use_proxy_fallback=True,
        )

        with (
            patch("backend.adapters.stage_adapters._build_root_cli_args", return_value=({}, cli_args)),
            patch("backend.adapters.stage_adapters.scrape_company_career_sites", return_value=([], [])) as mock_scrape,
        ):
            outcome = CompanyCareerSiteAcquisitionStage().execute(context, definition)

        self.assertEqual(outcome.metrics["jobs_found"], 0)
        self.assertTrue(mock_scrape.call_args.kwargs["use_proxy_fallback"])
        self.assertEqual(mock_scrape.call_args.kwargs["posted_within_days"], 7)
        self.assertEqual(mock_scrape.call_args.kwargs["max_sites_per_run"], 10)
        self.assertEqual(mock_scrape.call_args.kwargs["run_credit_budget"], 150)
        self.assertEqual(mock_scrape.call_args.kwargs["max_job_links_per_site"], 25)

    def test_company_career_site_stage_persists_capped_sites_from_run_result(self):
        context = SimpleNamespace(
            run=SimpleNamespace(id="run_cap"),
            logger=None,
            data={},
            registries=SimpleNamespace(connector_registry=SimpleNamespace(get=lambda _connector_id: None)),
            update_run_progress=lambda **_kwargs: None,
        )
        definition = StageDefinition(
            stage_id="source_company_career_sites",
            stage_type="jobs.acquire.company_sites",
            name="Acquire Company Career Site Jobs",
            output_key="source_company_career_jobs",
            config={"connector_id": "company_career_sites"},
        )
        cli_args = SimpleNamespace(
            company_career_sites=[{"company_name": "Acme", "url": "https://careers.acme.example"}],
            keywords=[],
            company_site_request_timeout_seconds=30,
            company_site_max_jobs_per_site=0,
            company_site_max_job_links_per_site=2,
            posted_within_days=0,
            use_proxy_fallback=False,
        )

        def fake_scrape(**kwargs):
            kwargs["progress_callback"](
                {
                    "message": "capped",
                    "counters": {
                        "capped_sites": [
                            {"url": "https://careers.acme.example", "links_fetched": 2, "cap_value": 2}
                        ]
                    },
                }
            )
            return [], []

        with (
            patch("backend.adapters.stage_adapters._build_root_cli_args", return_value=({}, cli_args)),
            patch("backend.adapters.stage_adapters.scrape_company_career_sites", side_effect=fake_scrape),
        ):
            outcome = CompanyCareerSiteAcquisitionStage().execute(context, definition)

        self.assertEqual(
            outcome.data["capped_sites"],
            [{"url": "https://careers.acme.example", "links_fetched": 2, "cap_value": 2}],
        )


if __name__ == "__main__":
    unittest.main()
