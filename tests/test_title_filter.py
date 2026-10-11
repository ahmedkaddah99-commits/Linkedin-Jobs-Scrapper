import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.capabilities.tailored_documents.title_filter import filter_with_ai
from backend.domain.phase0_contracts import JOB_FILTERING_MODE_BROADER, JOB_FILTERING_MODE_STRICT


class TitleFilterTests(unittest.TestCase):
    @staticmethod
    def _job(job_id: str, title: str, company: str = "Acme") -> dict:
        return {
            "job_id": job_id,
            "title": title,
            "company": company,
        }

    def test_strict_match_uses_normalized_title_phrase_containment_without_ai(self):
        jobs = [
            self._job("1", "Senior Project-Manager"),
            self._job("2", "Program Manager"),
            self._job("3", "AI Consultant"),
        ]

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "backend.capabilities.tailored_documents.title_filter.call_deepseek_title_filter"
        ) as ai_call:
            approved, excluded = filter_with_ai(
                jobs_list=jobs,
                deepseek_api_key="test-key",
                cv_summary="Consulting and AI background",
                model="test-model",
                excluded_output=str(Path(temp_dir) / "strict_excluded.json"),
                job_filtering_mode=JOB_FILTERING_MODE_STRICT,
                job_filtering_target_phrases=["Project Manager"],
                broader_keywords=["project manager", "program manager", "delivery manager"],
            )

        self.assertEqual([job["job_id"] for job in approved], ["1"])
        self.assertEqual([job["job_id"] for job in excluded], ["2", "3"])
        ai_call.assert_not_called()

    def test_broader_match_requires_title_connection_before_ai_screening(self):
        jobs = [
            self._job("1", "Program Manager"),
            self._job("2", "AI Consultant"),
            self._job("3", "Delivery Manager"),
        ]

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "backend.capabilities.tailored_documents.title_filter.call_deepseek_title_filter",
            return_value={
                "approved_ids": ["1"],
                "excluded": [{"id": "3", "reason": "Not relevant"}],
            },
        ) as ai_call:
            approved, excluded = filter_with_ai(
                jobs_list=jobs,
                deepseek_api_key="test-key",
                cv_summary="Consulting and AI background",
                model="test-model",
                excluded_output=str(Path(temp_dir) / "broader_excluded.json"),
                job_filtering_mode=JOB_FILTERING_MODE_BROADER,
                job_filtering_target_phrases=["Project Manager"],
                broader_keywords=["project manager", "program manager", "delivery manager"],
            )

        self.assertEqual([job["job_id"] for job in approved], ["1"])
        self.assertEqual([job["job_id"] for job in excluded], ["2", "3"])
        self.assertEqual(excluded[0]["reason"], "Title has no clear connection to saved target roles or keywords.")
        self.assertEqual(excluded[1]["reason"], "Not relevant")
        self.assertEqual(ai_call.call_count, 1)
        self.assertIn("Broad CV relevance alone is not enough.", ai_call.call_args.kwargs["prompt"])


if __name__ == "__main__":
    unittest.main()
