import unittest

import manual_url_ingestion
import pipeline_runner
import stage1_scrape_enrich
import stage2_filter_local
import stage3_filter_ai
import stage4_docs_export
from backend.capabilities.tailored_documents import acquisition, documents
from backend.capabilities.tailored_documents.cv_structuring import ensure_structured_cv_fields
from backend.capabilities.tailored_documents.generation import generate_docs_for_job
from backend.capabilities.tailored_documents.linkedin_connector import build_scrape_requests_client, enrich_job
from backend.capabilities.tailored_documents.manual_urls import fetch_manual_jobs_from_file, load_manual_urls
from backend.capabilities.tailored_documents.prioritization import (
    run_stage3_pipeline,
    sort_and_rank_jobs,
    split_python_prefilter_language_chars,
)
from backend.capabilities.tailored_documents.rendering import create_cv_document
from backend.capabilities.tailored_documents.runtime import build_main_defaults
from backend.capabilities.tailored_documents.screening import detect_reasons, run_stage2_pipeline
from backend.capabilities.tailored_documents.workflow import run_mode_pipeline


class WhiteCollarWrapperTests(unittest.TestCase):
    def test_stage1_wrapper_reexports_backend_pipeline(self):
        self.assertIs(stage1_scrape_enrich.run_stage1_pipeline, acquisition.run_stage1_pipeline)
        self.assertIs(stage1_scrape_enrich.build_scrape_requests_client, build_scrape_requests_client)
        self.assertIs(stage1_scrape_enrich.enrich_job, enrich_job)

    def test_stage4_wrapper_reexports_backend_pipeline(self):
        self.assertIs(stage4_docs_export.run_stage4_pipeline, documents.run_stage4_pipeline)
        self.assertIs(stage4_docs_export.generate_docs_for_job, generate_docs_for_job)
        self.assertIs(stage4_docs_export.create_cv_document, create_cv_document)
        self.assertIs(stage4_docs_export.ensure_structured_cv_fields, ensure_structured_cv_fields)

    def test_stage2_wrapper_reexports_backend_pipeline(self):
        self.assertIs(stage2_filter_local.run_stage2_pipeline, run_stage2_pipeline)
        self.assertIs(stage2_filter_local.detect_reasons, detect_reasons)

    def test_stage3_wrapper_reexports_backend_pipeline(self):
        self.assertIs(stage3_filter_ai.run_stage3_pipeline, run_stage3_pipeline)
        self.assertIs(stage3_filter_ai.sort_and_rank_jobs, sort_and_rank_jobs)
        self.assertIs(
            stage3_filter_ai.split_python_prefilter_language_chars,
            split_python_prefilter_language_chars,
        )

    def test_manual_url_wrapper_reexports_backend_pipeline(self):
        self.assertIs(manual_url_ingestion.fetch_manual_jobs_from_file, fetch_manual_jobs_from_file)
        self.assertIs(manual_url_ingestion.load_manual_urls, load_manual_urls)

    def test_pipeline_runner_reexports_backend_pipeline(self):
        self.assertIs(pipeline_runner.build_main_defaults, build_main_defaults)
        self.assertIs(pipeline_runner.run_mode_pipeline, run_mode_pipeline)
        self.assertIs(pipeline_runner.run_stage2_pipeline, run_stage2_pipeline)
        self.assertIs(pipeline_runner.run_stage3_pipeline, run_stage3_pipeline)


if __name__ == "__main__":
    unittest.main()
