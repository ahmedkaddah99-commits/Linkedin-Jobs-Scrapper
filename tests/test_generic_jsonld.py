from __future__ import annotations

import unittest
from unittest.mock import Mock

from backend.connectors.generic_jsonld import fetch_generic_snapshot


class GenericJsonLdConnectorTests(unittest.TestCase):
    def test_bounded_html_listing_retains_raw_evidence_and_never_closes_partial_source(self):
        responses = {
            "https://jobs.example.com/jobs": Mock(
                status_code=200,
                url="https://jobs.example.com/jobs",
                text='<a href="/externaljobs/JobDetail/42">Engineer</a><a href="/externaljobs/JobDetail/43">Analyst</a>',
            ),
            "https://jobs.example.com/externaljobs/JobDetail/42": Mock(
                status_code=200,
                url="https://jobs.example.com/externaljobs/JobDetail/42",
                text='<meta property="og:title" content="Platform Engineer"><div class="article__content__view__field"><span class="article__content__view__field__label">Job ID</span><span class="article__content__view__field__value">42</span></div><div class="article__content__view__field"><span class="article__content__view__field__label">Location(s)</span><span class="article__content__view__field__value">Berlin - Germany</span></div><a href="/externaljobs/ApplicationMethods?folderId=42">Apply</a><main>Build reliable systems.</main>',
            ),
            "https://jobs.example.com/externaljobs/JobDetail/43": Mock(
                status_code=200,
                url="https://jobs.example.com/externaljobs/JobDetail/43",
                text='<meta property="og:title" content="Data Analyst"><div>Analyze data.</div>',
            ),
        }

        def requester(url: str, **_: object) -> Mock:
            return responses[url]

        result = fetch_generic_snapshot("https://jobs.example.com/jobs", requester=requester, max_job_links=2, allowed_hosts=["example.com"])

        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["complete_snapshot"])
        self.assertTrue(result["credible_evidence"])
        self.assertEqual(len(result["jobs"]), 2)
        self.assertTrue(all(item["source_raw_payload"] for item in result["jobs"]))
        first = result["jobs"][0]
        self.assertEqual(first["title"], "Platform Engineer")
        self.assertTrue(first["apply_link"].endswith("ApplicationMethods?folderId=42"))
        self.assertEqual(first["location"], "Berlin - Germany")


if __name__ == "__main__":
    unittest.main()
