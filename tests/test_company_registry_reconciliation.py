from __future__ import annotations

import json
from pathlib import Path
import unittest

from backend.application.company_registry_reconciliation import (
    MASTER_FIELD_MAPPING,
    read_master_csv,
    reconcile_master_rows,
)


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


def _fixture_report() -> dict:
    rows, _, _ = read_master_csv(FIXTURE_DIRECTORY / "rc003_company_registry.csv")
    registry = json.loads((FIXTURE_DIRECTORY / "rc003_application_registry.json").read_text(encoding="utf-8"))
    dispositions = json.loads(
        (FIXTURE_DIRECTORY / "rc003_shared_organization_dispositions.json").read_text(encoding="utf-8")
    )
    return reconcile_master_rows(
        rows,
        application_registry=registry,
        shared_organization_dispositions=dispositions,
    )


class CompanyRegistryReconciliationTests(unittest.TestCase):
    def test_field_mapping_and_unknown_columns_are_explicit(self):
        report = _fixture_report()
        mapping_targets = {item["application_target"] for item in MASTER_FIELD_MAPPING}

        self.assertTrue(report["read_only"])
        self.assertFalse(report["writes_application_tables"])
        self.assertFalse(report["allocates_application_ids"])
        self.assertIn("Column1", report["input_columns"])
        self.assertIn("Column1", report["unknown_input_columns"])
        self.assertTrue(any("canonical_company_urls" in target for target in mapping_targets))
        self.assertNotIn("linkedin_slug", report["unknown_input_columns"])
        self.assertEqual(len(report["field_mapping"]), len(report["input_columns"]))

    def test_master_namespace_stays_separate_from_application_namespace(self):
        report = _fixture_report()
        alpha = next(row for row in report["rows"] if row["master_canonical_id"] == "master-alpha")

        self.assertEqual(alpha["master_external_key"], "master-company:master-alpha")
        self.assertNotEqual(alpha["master_canonical_id"], alpha["application_company_id"])
        self.assertFalse(report["application_id_equality_proven"])

    def test_reviewed_strong_key_matches_without_allocating_or_replacing_id(self):
        report = _fixture_report()
        gamma = next(row for row in report["rows"] if row["canonical_name"] == "Gamma")
        delta = next(row for row in report["rows"] if row["canonical_name"] == "Delta")

        self.assertEqual(gamma["registry_decision"], "matched")
        self.assertEqual(gamma["application_company_id"], "canonical_company_app_gamma")
        self.assertEqual(delta["registry_decision"], "matched")
        self.assertEqual(delta["identity_state"], "present")

    def test_same_name_and_unreviewed_domain_never_auto_merge(self):
        report = _fixture_report()
        name_only = next(row for row in report["rows"] if row["canonical_name"] == "Acme" and not row["master_canonical_id"])
        alpha = next(row for row in report["rows"] if row["master_canonical_id"] == "master-alpha")

        self.assertEqual(name_only["registry_decision"], "review")
        self.assertTrue(name_only["review_required"])
        self.assertEqual(alpha["registry_decision"], "review")
        self.assertIn("domain:acme.example", alpha["identity_keys"] and [item["identity_key"] for item in alpha["identity_keys"]])

    def test_shared_organization_dispositions_are_explicit_and_no_first_choice_exists(self):
        report = _fixture_report()
        groups = {item["linkedin_org_id"]: item for item in report["shared_organization_dispositions"]}

        self.assertEqual(groups["100"]["disposition"], "same_entity_alias")
        self.assertEqual(groups["101"]["disposition"], "distinct_related_employers")
        self.assertEqual(groups["102"]["disposition"], "unresolved_conflict")
        unresolved_rows = [row for row in report["rows"] if row["linkedin_org_id"] == "102"]
        self.assertTrue(all(row["registry_decision"] == "quarantined" for row in unresolved_rows))
        self.assertTrue(all(not row["application_company_id"] for row in unresolved_rows))
        self.assertTrue(all("sort_order" in groups[key]["ownership_rule"] for key in groups))

    def test_school_and_showcase_urls_are_quarantined_and_not_organization_identities(self):
        report = _fixture_report()

        for page_type in ("school", "showcase"):
            page = next(row for row in report["rows"] if row["linkedin_page_type"] == page_type)
            self.assertEqual(page["registry_decision"], "quarantined")
            self.assertEqual(page["decision_reason"], "non_company_linkedin_page")
            self.assertFalse(any(item["identity_key"].startswith("linkedin-org:") for item in page["identity_keys"]))

    def test_duplicate_reviewed_domain_owners_remain_reviewable(self):
        rows = [{"canonical_CompanyID": "master-hosted", "company_name": "Hosted Employer", "website_url": "https://shared-host.example"}]
        registry = json.loads((FIXTURE_DIRECTORY / "rc003_application_registry.json").read_text(encoding="utf-8"))
        report = reconcile_master_rows(rows, application_registry=registry)
        result = report["rows"][0]

        self.assertEqual(result["registry_decision"], "review")
        self.assertEqual(
            result["candidate_application_company_ids"],
            ["canonical_company_app_acme", "canonical_company_app_gamma"],
        )
        self.assertFalse(result["application_company_id"])

    def test_missing_identity_and_missing_enrichment_are_separate(self):
        report = _fixture_report()
        unidentified = next(row for row in report["rows"] if row["canonical_name"] == "Unidentified")
        delta = next(row for row in report["rows"] if row["canonical_name"] == "Delta")

        self.assertEqual(unidentified["identity_state"], "missing")
        self.assertEqual(unidentified["enrichment_state"], "missing")
        self.assertEqual(delta["identity_state"], "present")
        self.assertNotEqual(delta["enrichment_state"], "missing")
        self.assertFalse(unidentified["eligible_for_acquisition_or_publication"])

    def test_rename_and_website_change_are_history_candidates(self):
        rows = [
            {"canonical_CompanyID": "master-1", "company_name": "Old Name", "website_url": "https://old.example"},
            {"canonical_CompanyID": "master-1", "company_name": "New Name", "website_url": "https://new.example"},
        ]
        report = reconcile_master_rows(rows)

        self.assertEqual(report["rename_and_alias_review"][0]["decision"], "preserve_id_review_alias")
        self.assertEqual(report["website_history_review"][0]["decision"], "append_url_occurrence_review_primary")
        self.assertEqual(report["rename_and_alias_review"][0]["master_canonical_id"], "master-1")

    def test_shared_review_annotation_must_cover_exact_master_ids(self):
        rows = [
            {"canonical_CompanyID": "master-a", "company_name": "A", "linkedin_company_id": "99"},
            {"canonical_CompanyID": "master-b", "company_name": "B", "linkedin_company_id": "99"},
        ]
        report = reconcile_master_rows(
            rows,
            shared_organization_dispositions={
                "99": {
                    "master_ids": ["master-a"],
                    "disposition": "same_entity_alias",
                }
            },
        )

        self.assertEqual(report["shared_organization_dispositions"][0]["disposition"], "unresolved_conflict")
        self.assertEqual(report["shared_organization_dispositions"][0]["reason"], "invalid_or_incomplete_review_annotation")

    def test_row_fingerprints_are_stable_when_input_order_changes(self):
        rows, _, _ = read_master_csv(FIXTURE_DIRECTORY / "rc003_company_registry.csv")
        forward = reconcile_master_rows(rows)
        reverse = reconcile_master_rows(reversed(rows))
        forward_by_fingerprint = sorted(row["row_fingerprint"] for row in forward["rows"])
        reverse_by_fingerprint = sorted(row["row_fingerprint"] for row in reverse["rows"])

        self.assertEqual(forward_by_fingerprint, reverse_by_fingerprint)


if __name__ == "__main__":
    unittest.main()
