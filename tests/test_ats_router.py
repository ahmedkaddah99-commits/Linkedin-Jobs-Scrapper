import unittest
from unittest.mock import MagicMock, patch

from backend.connectors.ats_router import detect_ats, fetch_ats_jobs, fetch_ats_snapshot
from backend.connectors.company_career_sites import scrape_company_career_sites


class AtsRouterTests(unittest.TestCase):
    def test_detect_ats_classifies_supported_hosts_and_unknown_host(self):
        cases = {
            "https://boards.greenhouse.io/acme/jobs/1": "greenhouse",
            "https://jobs.lever.co/acme/role": "lever",
            "https://acme.wd1.myworkdayjobs.com/en-US/careers": "workday",
            "https://acme.jobs.personio.de/": "personio",
            "https://acme.recruitee.com/": "recruitee",
            "https://careers.smartrecruiters.com/Acme": "smartrecruiters",
            "https://careers.example.com/jobs": None,
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(detect_ats(url), expected)

    @patch("backend.connectors.ats_router.requests.get")
    def test_fetch_greenhouse_jobs_returns_normalized_records(self, mock_get):
        response = MagicMock()
        response.json.return_value = {
            "jobs": [
                {
                    "id": 123,
                    "title": "Product Analyst",
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
                    "location": {"name": "Berlin"},
                    "updated_at": "2026-05-26T00:00:00Z",
                }
            ]
        }
        mock_get.return_value = response

        jobs = fetch_ats_jobs("https://boards.greenhouse.io/acme", "greenhouse")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Product Analyst")
        self.assertEqual(jobs[0]["location"], "Berlin")
        self.assertEqual(jobs[0]["source_ats"], "greenhouse")
        self.assertEqual(jobs[0]["url"], "https://boards.greenhouse.io/acme/jobs/123")
        self.assertEqual(jobs[0]["source_timestamps"]["timestamp_state"], "unknown_source_timestamp")
        self.assertEqual(jobs[0]["posted_at"], "")

    @patch("backend.connectors.ats_router.requests.get")
    def test_fetch_lever_jobs_returns_normalized_records(self, mock_get):
        response = MagicMock()
        response.json.return_value = [
            {
                "id": "post-1",
                "text": "Business Analyst",
                "hostedUrl": "https://jobs.lever.co/acme/post-1",
                "categories": {"location": "Munich"},
                "createdAt": 1779753600000,
            }
        ]
        mock_get.return_value = response

        jobs = fetch_ats_jobs("https://jobs.lever.co/acme", "lever")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Business Analyst")
        self.assertEqual(jobs[0]["company"], "acme")
        self.assertEqual(jobs[0]["source_ats"], "lever")
        self.assertEqual(jobs[0]["source_timestamps"]["timestamp_state"], "unknown_source_timestamp")
        self.assertEqual(jobs[0]["posted_at"], "")

    def test_unimplemented_structured_ats_returns_empty_list(self):
        for ats in ("workday", "personio", "recruitee", "smartrecruiters"):
            with self.subTest(ats=ats):
                self.assertEqual(fetch_ats_jobs("https://example.invalid/jobs", ats), [])

    def test_fixture_softgarden_board_is_classified_and_report_only(self):
        self.assertEqual(detect_ats("https://acme.softgarden.io"), "softgarden")
        self.assertEqual(detect_ats("https://acme.softgarden.de/jobs"), "softgarden")

        snapshot = fetch_ats_snapshot("https://acme.softgarden.io/jobs", "softgarden")

        self.assertEqual(snapshot["status"], "unsupported")
        self.assertEqual(snapshot["reason_code"], "unsupported_ats")
        self.assertEqual(snapshot["jobs"], [])
        self.assertTrue(snapshot["host_policy"]["allowed"])
        self.assertFalse(snapshot["complete_snapshot"])

    def test_host_policy_mismatch_rejects_target_without_requests(self):
        snapshot = fetch_ats_snapshot("https://jobs.lever.co/acme", "greenhouse")

        self.assertEqual(snapshot["status"], "invalid_target")
        self.assertEqual(snapshot["reason_code"], "host_policy_mismatch")
        self.assertEqual(snapshot["jobs"], [])
        self.assertFalse(snapshot["credible_evidence"])
        self.assertFalse(snapshot["host_policy"]["allowed"])
        self.assertEqual(snapshot["host_policy"]["requested_ats"], "greenhouse")
        self.assertEqual(snapshot["host_policy"]["target_ats"], "lever")

    def test_unsupported_ats_reason_code_is_observable(self):
        snapshot = fetch_ats_snapshot("https://boards.example-ats.example/jobs", "unknownats")

        self.assertEqual(snapshot["status"], "invalid_target")
        self.assertEqual(snapshot["reason_code"], "host_policy_mismatch")

    @patch("backend.connectors.company_career_sites._collect_job_candidates_for_site")
    @patch("backend.connectors.company_career_sites.fetch_ats_jobs")
    def test_company_site_uses_ats_results_without_proxy_collection(self, mock_fetch_ats_jobs, mock_proxy_collection):
        mock_fetch_ats_jobs.return_value = [
            {
                "job_id": "greenhouse_1",
                "title": "Product Analyst",
                "company": "acme",
                "location": "Berlin",
                "location_raw": "Berlin",
                "url": "https://boards.greenhouse.io/acme/jobs/1",
                "link": "https://boards.greenhouse.io/acme/jobs/1",
                "source_url": "https://boards.greenhouse.io/acme/jobs/1",
                "apply_link": "https://boards.greenhouse.io/acme/jobs/1",
                "posted_at": "",
                "source_ats": "greenhouse",
            }
        ]

        jobs, failures = scrape_company_career_sites(
            company_sites=[{"company_name": "Acme GmbH", "url": "https://boards.greenhouse.io/acme"}],
            keywords=["product"],
        )

        self.assertEqual(failures, [])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Acme GmbH")
        self.assertEqual(jobs[0]["source_ats"], "greenhouse")
        mock_proxy_collection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
