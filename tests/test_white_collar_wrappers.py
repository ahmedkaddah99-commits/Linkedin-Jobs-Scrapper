import unittest

import stage1_scrape_enrich
import stage4_docs_export
from backend.capabilities.white_collar import acquisition, documents
from backend.capabilities.white_collar.cv_structuring import ensure_structured_cv_fields
from backend.capabilities.white_collar.generation import generate_docs_for_job
from backend.capabilities.white_collar.linkedin_connector import build_scrape_requests_client, enrich_job
from backend.capabilities.white_collar.rendering import create_cv_document


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


if __name__ == "__main__":
    unittest.main()
