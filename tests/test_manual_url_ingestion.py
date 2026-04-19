import textwrap
import unittest
from pathlib import Path

from backend.capabilities.tailored_documents.manual_urls import (
    extract_linkedin_job_id,
    is_valid_job_url,
    load_manual_urls,
    normalize_manual_urls,
)


class ManualUrlIngestionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
