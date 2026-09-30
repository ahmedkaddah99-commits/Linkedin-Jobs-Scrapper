import unittest

from scripts.collect_linkedin_company_gaps import (
    completed_company_ids,
    linkedin_homepage,
    missing_collectible_fields,
    offered_fields,
)


class LinkedInCompanyGapCollectorTests(unittest.TestCase):
    def test_existing_linkedin_url_precedes_numeric_url_building(self):
        profile = {"fields": {"linkedin_company_url": {"value": "https://www.linkedin.com/company/acme/"}}}
        self.assertEqual(linkedin_homepage(profile, "123"), "https://www.linkedin.com/company/acme/")

    def test_numeric_id_builds_linkedin_company_homepage(self):
        self.assertEqual(linkedin_homepage({}, "12345"), "https://www.linkedin.com/company/12345/")

    def test_missing_fields_checks_both_profile_sections_and_logo_columns(self):
        profile = {
            "fields": {"industry": {"value": "unknown"}},
            "additional_fields": {"industry": {"value": "Software"}, "linkedin_company_url": {"value": "https://www.linkedin.com/company/acme"}},
        }
        missing = missing_collectible_fields(profile, logo_source_url="https://media.licdn.com/logo.png", logo_object_key="")
        self.assertNotIn("industry", missing)
        self.assertNotIn("linkedin_company_url", missing)
        self.assertNotIn("logo", missing)
        self.assertIn("description", missing)

    def test_offers_only_exposes_supported_nonempty_values(self):
        result = {
            "fields": {"industry": "Software", "website": "https://acme.example"},
            "extra_fields": {"linkedin_description": "Builds software.", "linkedin_lookup_status": "matched"},
            "logo_bytes": b"png",
            "logo_source_url": "https://media.licdn.com/logo.png",
        }
        offers = offered_fields(result)
        self.assertEqual(offers["description"], "Builds software.")
        self.assertEqual(offers["industry"], "Software")
        self.assertEqual(offers["website"], "https://acme.example")
        self.assertEqual(offers["logo"], "https://media.licdn.com/logo.png")

    def test_not_found_does_not_promote_constructed_linkedin_url(self):
        offers = offered_fields(
            {
                "provenance_url": "https://www.linkedin.com/company/12345/",
                "extra_fields": {"linkedin_lookup_status": "not_found"},
            }
        )
        self.assertNotIn("linkedin_company_url", offers)

    def test_completed_company_ids_ignores_corrupt_and_incomplete_rows(self):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.jsonl"
            path.write_text(
                '{"company_id":"done","event":"result"}\n'
                '{not-json}\n'
                '{"company_id":"pending","event":"attempting"}\n',
                encoding="utf-8",
            )
            self.assertEqual(completed_company_ids(path), {"done"})


if __name__ == "__main__":
    unittest.main()
