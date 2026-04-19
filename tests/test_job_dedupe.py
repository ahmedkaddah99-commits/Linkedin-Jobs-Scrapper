import unittest

from backend.domain.job_identity import canonicalize_url, dedupe_job_records, title_company_signature


class JobDedupeTests(unittest.TestCase):
    def test_canonicalize_url_removes_tracking_fields(self):
        canonical = canonicalize_url(
            "https://www.linkedin.com/jobs/view/12345/?utm_source=test&trk=public_jobs_topcard-title#section"
        )
        self.assertEqual(canonical, "https://linkedin.com/jobs/view/12345")

    def test_title_company_signature_normalizes_whitespace_and_case(self):
        signature = title_company_signature(" Business Analyst ", " ACME   GmbH ")
        self.assertEqual(signature, "business analyst||acme gmbh")

    def test_dedupe_job_records_drops_duplicate_url(self):
        kept, dropped = dedupe_job_records(
            [
                {
                    "job_id": "123",
                    "title": "Business Analyst",
                    "company": "ACME",
                    "apply_link": "https://example.com/jobs/1?utm_source=linkedin",
                },
                {
                    "job_id": "manual_1",
                    "title": "Business Analyst",
                    "company": "ACME",
                    "apply_link": "https://example.com/jobs/1",
                },
            ]
        )

        self.assertEqual(len(kept), 1)
        self.assertEqual(len(dropped), 1)
        self.assertIn("duplicate_identity:url:https://example.com/jobs/1", dropped[0]["dedupe_reason"])


if __name__ == "__main__":
    unittest.main()
