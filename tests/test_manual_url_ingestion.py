import textwrap
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json

from backend.capabilities.tailored_documents.manual_urls import (
    extract_public_posted_age,
    extract_linkedin_job_id,
    is_valid_job_url,
    load_manual_urls,
    normalize_manual_urls,
)
from backend.capabilities.tailored_documents.workflow import run_manual_pipeline


class ManualUrlIngestionTests(unittest.TestCase):
    def test_extract_public_posted_age_parses_json_ld_date(self):
        posted_text, age_hours, posted_datetime = extract_public_posted_age("2026-05-25")

        self.assertEqual(posted_text, "2026-05-25")
        self.assertIsNotNone(age_hours)
        self.assertTrue(posted_datetime.startswith("2026-05-25T00:00:00"))

    def test_extract_linkedin_job_id(self):
        self.assertEqual(
            extract_linkedin_job_id("https://www.linkedin.com/jobs/view/1234567890/?trackingId=abc"),
            "1234567890",
        )

    def test_is_valid_job_url(self):
        self.assertTrue(is_valid_job_url("https://example.com/jobs/1"))
        self.assertFalse(is_valid_job_url("ftp://example.com/jobs/1"))
        self.assertFalse(is_valid_job_url("not-a-url"))

    def test_load_manual_urls_ignores_comments_and_dedupes(self):
        contents = textwrap.dedent(
            """
            # comment
            https://www.linkedin.com/jobs/view/1234567890/?utm_source=test

            https://www.linkedin.com/jobs/view/1234567890/
            invalid-url
            https://example.com/jobs/business-analyst
            """
        ).strip()

        temp_dir = Path("tests") / "_tmp_manual_ingestion"
        temp_dir.mkdir(parents=True, exist_ok=True)
        file_path = temp_dir / "manual_urls.txt"
        try:
            file_path.write_text(contents, encoding="utf-8")
            urls, invalid_entries = load_manual_urls(file_path)
        finally:
            if file_path.exists():
                file_path.unlink()
            if temp_dir.exists():
                temp_dir.rmdir()

        self.assertEqual(
            urls,
            [
                "https://www.linkedin.com/jobs/view/1234567890/?utm_source=test",
                "https://example.com/jobs/business-analyst",
            ],
        )
        self.assertEqual(len(invalid_entries), 1)
        self.assertEqual(invalid_entries[0]["error"], "invalid_url_format")

    def test_normalize_manual_urls_supports_inline_multiline_input(self):
        urls, invalid_entries = normalize_manual_urls(
            """
            https://example.com/jobs/alpha
            # ignore me
            invalid-url
            https://example.com/jobs/alpha
            https://example.com/jobs/beta
            """
        )
        self.assertEqual(
            urls,
            [
                "https://example.com/jobs/alpha",
                "https://example.com/jobs/beta",
            ],
        )
        self.assertEqual(len(invalid_entries), 1)
        self.assertEqual(invalid_entries[0]["url"], "invalid-url")

    def test_run_manual_pipeline_accepts_string_output_paths_for_inline_urls(self):
        with TemporaryDirectory() as temp_dir:
            output_path = str(Path(temp_dir) / "manual_jobs.json")
            failures_path = str(Path(temp_dir) / "manual_failures.json")
            cli_args = SimpleNamespace(
                manual_urls_inline=["https://example.com/jobs/alpha"],
                manual_url_seed_list=[],
                debug_enrich_blocks=False,
                use_proxy_fallback=False,
                manual_request_timeout_seconds=15,
                manual_output_json=output_path,
                manual_failures_json=failures_path,
            )
            fetched_job = {
                "job_id": "manual_alpha",
                "title": "Operations Analyst",
                "company": "Example Co",
                "source_url": "https://example.com/jobs/alpha",
                "apply_link": "https://example.com/jobs/alpha",
                "full_description": "Coordinate operations and improve internal workflows.",
            }

            with patch(
                "backend.capabilities.tailored_documents.workflow.fetch_manual_jobs_from_urls",
                return_value=([fetched_job], []),
            ):
                jobs, failures = run_manual_pipeline(cli_args)

            self.assertEqual(failures, [])
            self.assertEqual(jobs[0]["job_id"], "manual_alpha")
            self.assertTrue(Path(output_path).exists())
            self.assertTrue(Path(failures_path).exists())
            self.assertEqual(json.loads(Path(output_path).read_text(encoding="utf-8"))[0]["manual_approved"], True)


if __name__ == "__main__":
    unittest.main()
