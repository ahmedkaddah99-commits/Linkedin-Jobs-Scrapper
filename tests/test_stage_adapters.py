import unittest
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from backend.adapters.stage_adapters import LinkedInAcquireStage, _tailored_document_artifacts
from backend.domain.models import StageDefinition


class StageAdapterTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
