import unittest

from backend.capabilities.networking import (
    build_target_contact_discovery,
    find_referral_contacts_for_company,
    merge_referral_contacts,
    parse_referral_contacts_csv,
)
from backend.capabilities.networking.outreach import company_names_safely_match
from backend.domain.models import JobRecord, ReferralContactRecord


class ReferralNetworkingTests(unittest.TestCase):
    def test_linkedin_csv_import_scans_to_real_header_and_skips_empty_rows(self):
        contacts = parse_referral_contacts_csv(
            "\n".join(
                [
                    "LinkedIn export",
                    "Downloaded by user",
                    "",
                    "First Name,Last Name,URL,Email Address,Company,Position,Connected On",
                    "",
                    'Sarah,"Muller, PhD",https://linkedin.com/in/sarah,,Stripe Inc.,Senior Engineer,15 Jan 2024',
                    ",,,,,,",
                    "Jonas,Weber,https://linkedin.com/in/jonas,,Google LLC,Product Manager,02 Mar 2023",
                    "",
                ]
            ),
            import_batch_id="import_1",
        )

        self.assertEqual(len(contacts), 2)
        self.assertEqual(contacts[0].name, "Sarah Muller, PhD")
        self.assertEqual(contacts[0].linkedin_url, "https://linkedin.com/in/sarah")
        self.assertEqual(contacts[0].companies[0]["company_name"], "Stripe Inc.")
        self.assertEqual(contacts[0].companies[0]["role_title"], "Senior Engineer")
        self.assertIn("connected on", contacts[0].metadata["import_source_row"])
        self.assertEqual(contacts[0].metadata["source_order"], 1)

    def test_linkedin_csv_import_ignores_multiline_linkedin_notes_before_header(self):
        contacts = parse_referral_contacts_csv(
            "\n".join(
                [
                    "Notes:,,,,,,",
                    '"When exporting your connection data, you may notice that',
                    "some of the email addresses are missing. You will only see email",
                    "addresses for connections who have allowed their connections",
                    "to see or download their email address using this setting",
                    "https://www.linkedin.com/psettings/privacy/email. You can",
                    'learn more here",,,,,,',
                    "",
                    "First Name,Last Name,URL,Email Address,Company,Position,Connected On",
                    "Amal,Khan,https://linkedin.com/in/amal,,Stripe Payments Europe,Finance Lead,29-Mar-21",
                    "Jonas,Weber,https://linkedin.com/in/jonas,,Google LLC,Product Manager,02-Mar-23",
                ]
            ),
            import_batch_id="import_notes",
        )

        self.assertEqual(len(contacts), 2)
        self.assertEqual(contacts[0].name, "Amal Khan")
        self.assertEqual(contacts[0].company, "Stripe Payments Europe")
        self.assertEqual(contacts[1].name, "Jonas Weber")

    def test_linkedin_csv_import_does_not_match_header_text_inside_quoted_notes(self):
        contacts = parse_referral_contacts_csv(
            "\n".join(
                [
                    "Notes:,,,,,,",
                    '"Ignore the example below because it is still part of the note:',
                    "First Name,Last Name,URL,Email Address,Company,Position,Connected On",
                    'End of example.",,,,,,',
                    "",
                    "First Name,Last Name,URL,Email Address,Company,Position,Connected On",
                    "Marvin,Jakwerth,https://www.linkedin.com/in/marvin-jakwerth,,Allianz Services,Senior Engagement Manager,13-Feb-26",
                    "Laura Marcela,Aristizabal,https://www.linkedin.com/in/laura-marcela,,AB InBev,Manager,02-Jan-25",
                ]
            ),
            import_batch_id="import_header_in_note",
        )

        self.assertEqual(len(contacts), 2)
        self.assertEqual(contacts[0].name, "Marvin Jakwerth")
        self.assertEqual(contacts[1].company, "AB InBev")

    def test_linkedin_csv_import_accepts_split_header_rows(self):
        contacts = parse_referral_contacts_csv(
            "\n".join(
                [
                    "Notes:,,,,,,",
                    '"LinkedIn export note",,,,,,',
                    "",
                    "First Name,Last Name,URL,Email",
                    "Address,Company,Position,Connected On",
                    "Marvin,Jakwerth,https://www.linkedin.com/in/marvin-jakwerth,,Allianz Services,Senior Engagement Manager,13-Feb-26",
                    "Laura Marcela,Aristizabal,https://www.linkedin.com/in/laura-marcela,,AB InBev,Manager,02-Jan-25",
                ]
            ),
            import_batch_id="import_split_header",
        )

        self.assertEqual(len(contacts), 2)
        self.assertEqual(contacts[0].name, "Marvin Jakwerth")
        self.assertEqual(contacts[0].company, "Allianz Services")
        self.assertEqual(contacts[1].name, "Laura Marcela Aristizabal")

    def test_linkedin_csv_import_has_no_connection_cap_and_preserves_upload_order(self):
        rows = [
            "First Name,Last Name,URL,Email Address,Company,Position,Connected On",
            *[
                f"First{i},Last{i},https://linkedin.com/in/person-{i},,Company {i},Role {i},01-Jan-24"
                for i in range(1705)
            ],
        ]

        contacts = parse_referral_contacts_csv("\n".join(rows), import_batch_id="import_large")

        self.assertEqual(len(contacts), 1705)
        self.assertEqual(contacts[0].name, "First0 Last0")
        self.assertEqual(contacts[999].name, "First999 Last999")
        self.assertEqual(contacts[-1].name, "First1704 Last1704")
        self.assertEqual(contacts[-1].metadata["source_order"], 1705)

    def test_reupload_marks_missing_linkedin_contacts_inactive(self):
        existing = parse_referral_contacts_csv(
            "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
            "Jane,Referrer,https://linkedin.com/in/jane,,ACME,Manager,01 Jan 2024\n"
            "Sam,Old,https://linkedin.com/in/sam,,Beta,Lead,02 Jan 2024\n",
            import_batch_id="import_old",
        )
        incoming = parse_referral_contacts_csv(
            "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
            "Jane,Referrer,https://linkedin.com/in/jane,,ACME GmbH,Director,03 Jan 2024\n",
            import_batch_id="import_new",
        )

        merged, summary = merge_referral_contacts(existing, incoming)

        self.assertEqual(summary["updated"], 1)
        self.assertEqual(summary["deactivated"], 1)
        by_name = {contact.name: contact for contact in merged}
        self.assertTrue(by_name["Jane Referrer"].is_active)
        self.assertFalse(by_name["Sam Old"].is_active)
        self.assertEqual(by_name["Sam Old"].inactive_reason, "missing_from_latest_linkedin_upload")

    def test_reupload_orders_linkedin_contacts_by_latest_upload_file(self):
        existing = parse_referral_contacts_csv(
            "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
            "Alpha,One,https://linkedin.com/in/alpha,,ACME,Manager,01 Jan 2024\n"
            "Beta,Two,https://linkedin.com/in/beta,,Beta,Lead,02 Jan 2024\n",
            import_batch_id="import_old",
        )
        incoming = parse_referral_contacts_csv(
            "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
            "Beta,Two,https://linkedin.com/in/beta,,Beta,Lead,02 Jan 2024\n"
            "Alpha,One,https://linkedin.com/in/alpha,,ACME,Manager,01 Jan 2024\n",
            import_batch_id="import_new",
        )

        merged, _ = merge_referral_contacts(existing, incoming)

        self.assertEqual([contact.name for contact in merged], ["Beta Two", "Alpha One"])

    def test_linkedin_csv_import_rejects_non_linkedin_table_headers(self):
        with self.assertRaisesRegex(ValueError, "Expected header row"):
            parse_referral_contacts_csv(
                "First Name,Last Name,URL,Company,Position\n"
                "Jane,Referrer,https://linkedin.com/in/jane,ACME,Manager\n",
                import_batch_id="import_bad",
            )

    def test_safe_company_matching_avoids_short_substring_false_positive(self):
        self.assertTrue(company_names_safely_match("Stripe", "Stripe Inc."))
        self.assertTrue(company_names_safely_match("Stripe", "Stripe Payments Europe"))
        self.assertFalse(company_names_safely_match("Meta", "Metabolic Health GmbH"))

    def test_referral_matching_returns_all_active_contacts_only(self):
        active_one = ReferralContactRecord.create(name="One", company="Stripe Inc.")
        active_two = ReferralContactRecord.create(name="Two", company="Stripe Payments Europe")
        inactive = ReferralContactRecord.create(name="Inactive", company="Stripe", is_active=False)

        matches = find_referral_contacts_for_company([active_one, inactive, active_two], "Stripe")

        self.assertEqual([contact.name for contact in matches], ["One", "Two"])

    def test_target_contact_discovery_builds_ranked_search_candidates(self):
        payload = build_target_contact_discovery(
            profile={
                "name": "Analyst User",
                "summary": "Analytics specialist who improves dashboards and reporting workflows.",
            },
            job=JobRecord(
                job_id="job_1",
                title="Senior Data Analyst",
                company="ACME GmbH",
                location_raw="Berlin, Germany",
                description_text="Reporting to Jane Hiringmanager on the analytics team.",
            ),
        )

        self.assertEqual(payload["discipline"], "data")
        self.assertEqual(payload["department_label"], "Data")
        self.assertGreaterEqual(len(payload["candidates"]), 4)
        self.assertEqual(payload["candidates"][0]["role_label"], "Named Hiring Signal")
        self.assertIn("linkedin.com/search/results/people", payload["candidates"][0]["linkedin_search_url"])
        self.assertIn("site:linkedin.com/in", payload["candidates"][0]["google_xray_query"])
        self.assertIn("[Name]", payload["candidates"][0]["connection_note"])


if __name__ == "__main__":
    unittest.main()
