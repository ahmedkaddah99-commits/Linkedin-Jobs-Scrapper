import unittest

from backend.domain.phase0_contracts import (
    PHASE0_CONTRACT_VERSION,
    normalize_candidate_asset_descriptor,
    normalize_mail_connection_contract,
    normalize_referral_relationship,
    normalize_rejected_job_review,
    normalize_workspace_configuration_v2,
    phase0_contract_catalog,
)


class Phase0ContractsTests(unittest.TestCase):
    def test_workspace_configuration_v2_normalizes_legacy_builder_settings(self):
        payload = {
            "source_ids": ["linkedin_search", "curated_urls", "company_career_sites"],
            "profile_label": "Primary Job Seeker Profile",
            "settings": {
                "target_roles": ["Business Analyst", "Consultant"],
                "geo_id": "101282230",
                "time_posted_seconds": 172800,
                "experience_levels": [2, 3],
                "manual_url_seed_list": "https://company.example/jobs/1\nhttps://company.example/jobs/1\nhttps://company.example/jobs/2",
                "company_career_sites": "Acme | https://careers.acme.com/jobs\nContoso | https://jobs.contoso.com",
                "forbidden_title_keywords": ["Senior", "Senior", "Director"],
                "languages": ["English - C1", "German - B1/B2"],
                "french_special_char_threshold": 0,
                "spanish_special_char_threshold": 9999,
                "cv_template": "modern",
                "include_photo": False,
                "linkedin_max_pages": 7,
                "candidate_name": "Ahmed",
                "candidate_email": "ahmed@example.com",
                "stage1_extra_prompt": "Favor hybrid roles.",
                "stage4_prompt_override": "Use my custom document prompt.",
            },
        }

        normalized = normalize_workspace_configuration_v2(payload)

        self.assertEqual(normalized["schema_version"], "workspace_configuration_v2")
        self.assertEqual(normalized["cv_binding"]["profile_label"], "Primary Job Seeker Profile")
        self.assertEqual(normalized["targeting"]["keywords"], ["business analyst", "consultant"])
        self.assertEqual(
            normalized["location_preferences"]["legacy_source_locations"]["linkedin_geo_id"],
            "101282230",
        )
        self.assertTrue(normalized["source_configuration"]["linkedin_search"]["enabled"])
        self.assertTrue(normalized["source_configuration"]["curated_urls"]["enabled"])
        self.assertTrue(normalized["source_configuration"]["company_career_sites"]["enabled"])
        self.assertEqual(
            normalized["source_configuration"]["curated_urls"]["urls"],
            ["https://company.example/jobs/1", "https://company.example/jobs/2"],
        )
        self.assertEqual(len(normalized["source_configuration"]["company_career_sites"]["companies"]), 2)
        self.assertEqual(
            normalized["filter_preferences"]["forbidden_title_keywords"],
            ["senior", "director"],
        )
        self.assertFalse(normalized["filter_preferences"]["language_preferences"]["allow_french"])
        self.assertTrue(normalized["filter_preferences"]["language_preferences"]["allow_spanish"])
        self.assertFalse(normalized["document_preferences"]["include_photo"])
        self.assertEqual(normalized["technical_runtime"]["linkedin_max_pages"], 7)
        self.assertEqual(normalized["legacy_passthrough"]["candidate_name"], "Ahmed")
        self.assertEqual(normalized["legacy_passthrough"]["candidate_email"], "ahmed@example.com")
        self.assertEqual(len(normalized["prompt_preferences"]["stage_overrides"]), 2)

    def test_candidate_asset_descriptor_normalizes_artifact_payload(self):
        normalized = normalize_candidate_asset_descriptor(
            {
                "artifact_id": "artifact_123",
                "artifact_type": "cv_docx",
                "file_name": "Role_CV.docx",
                "workspace_id": "workspace_1",
                "run_id": "run_1",
                "path": "generated_docs/Role_CV.docx",
                "download_url": "/v1/runs/run_1/artifacts/artifact_123/download",
                "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "metadata": {"job_id": "job_1", "tags": ["cv", "generated"]},
            }
        )

        self.assertEqual(normalized["asset_id"], "artifact_123")
        self.assertEqual(normalized["asset_kind"], "cv_docx")
        self.assertEqual(normalized["display_name"], "Role_CV.docx")
        self.assertEqual(normalized["source"]["run_id"], "run_1")
        self.assertEqual(normalized["metadata"]["job_id"], "job_1")
        self.assertEqual(normalized["metadata"]["tags"], ["cv", "generated"])

    def test_rejected_job_review_infers_reason_code(self):
        normalized = normalize_rejected_job_review(
            {
                "job_id": "job_1",
                "run_id": "run_1",
                "workspace_id": "workspace_1",
                "status": "rejected",
                "notes": "Rejected because the role requires German C1.",
                "filter_status": "language_filter",
                "apply_link": "https://company.example/jobs/1",
            }
        )

        self.assertEqual(normalized["rejection"]["reason_code"], "language_mismatch")
        self.assertEqual(normalized["links"]["job_posting"], "https://company.example/jobs/1")
        self.assertTrue(normalized["override"]["requeue_supported"])

    def test_mail_connection_contract_normalizes_legacy_imap_and_google_shapes(self):
        legacy = normalize_mail_connection_contract(
            {
                "provider_id": "gmail",
                "email_address": "candidate@example.com",
                "password_secret_id": "secret_pwd_1",
                "folder": "INBOX",
                "max_messages": 25,
                "connected_at": "2026-04-20T09:00:00+00:00",
            }
        )
        oauth = normalize_mail_connection_contract(
            {
                "provider": "gmail",
                "auth_strategy": "google_oauth",
                "account_email": "candidate@example.com",
                "refresh_token_secret_id": "secret_refresh_1",
                "access_token_secret_id": "secret_access_1",
                "authorization_state": "authorized",
                "connected_at": "2026-04-20T09:10:00+00:00",
            }
        )

        self.assertEqual(legacy["auth_strategy"], "legacy_imap_password")
        self.assertEqual(legacy["connection_status"], "connected")
        self.assertEqual(legacy["token_refs"]["legacy_password_secret_id"], "secret_pwd_1")
        self.assertEqual(oauth["auth_strategy"], "google_oauth")
        self.assertEqual(oauth["connection_status"], "connected")
        self.assertEqual(oauth["token_refs"]["refresh_token_secret_id"], "secret_refresh_1")

    def test_referral_relationship_normalizes_flat_contact_to_person_with_companies(self):
        normalized = normalize_referral_relationship(
            {
                "contact_id": "contact_1",
                "name": "Jane Referrer",
                "company": "ACME API",
                "linkedin_url": "https://linkedin.com/in/jane-referrer",
                "relationship_note": "Former teammate",
                "can_refer": True,
                "created_at": "2026-04-20T08:00:00+00:00",
            }
        )

        self.assertEqual(normalized["person_id"], "contact_1")
        self.assertEqual(normalized["person"]["full_name"], "Jane Referrer")
        self.assertEqual(len(normalized["companies"]), 1)
        self.assertEqual(normalized["companies"][0]["company_name"], "ACME API")
        self.assertTrue(normalized["companies"][0]["can_refer"])
        self.assertEqual(normalized["matching"]["company_aliases"], ["ACME API"])

    def test_phase0_contract_catalog_exposes_all_contracts(self):
        catalog = phase0_contract_catalog()

        self.assertEqual(catalog["version"], PHASE0_CONTRACT_VERSION)
        self.assertIn("workspace_configuration_v2", catalog)
        self.assertIn("candidate_asset_descriptor", catalog)
        self.assertIn("rejected_job_review", catalog)
        self.assertIn("mail_connection", catalog)
        self.assertIn("referral_relationship", catalog)


if __name__ == "__main__":
    unittest.main()
