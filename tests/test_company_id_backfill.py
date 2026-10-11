from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from backend.application.company_id_backfill import (
    _deterministic_id,
    backfill_master_rows,
    read_csv_with_hash,
    write_backfill_outputs,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "rc004_company_id_backfill.csv"


class CompanyIdBackfillTests(unittest.TestCase):
    def _fixture(self) -> tuple[list[dict[str, str]], list[str], str]:
        return read_csv_with_hash(FIXTURE_PATH)

    def test_dry_run_accounts_for_retained_matched_new_provisional_quarantine_and_rejected(self):
        rows, _, source_hash = self._fixture()
        original = [dict(row) for row in rows]
        report = backfill_master_rows(rows, source_path=str(FIXTURE_PATH), input_sha256=source_hash)

        self.assertEqual(report["counts"]["retained"], 1)
        self.assertEqual(report["counts"]["matched_existing"], 1)
        self.assertEqual(report["counts"]["new"], 3)
        self.assertEqual(report["counts"]["provisional"], 1)
        self.assertEqual(report["counts"]["quarantined"], 3)
        self.assertEqual(report["counts"]["rejected"], 3)
        self.assertEqual(report["counts"]["duplicate_rows"], 1)
        self.assertEqual(report["counts"]["eligible_rows"], 5)
        self.assertEqual(rows, original)
        self.assertTrue(all(item["registry_record_key"] for item in report["mappings"]))
        self.assertTrue(
            all(
                item["proposed_canonical_id"]
                for item in report["mappings"]
                if item["eligible_for_identity_backfill"]
            )
        )
        self.assertIn("linkedin-org:700", report["identity_key_conflicts"])
        self.assertTrue(any(item["identity_key"] == "companyenrich:ce-new" for item in report["duplicate_identity_evidence"]))

    def test_existing_id_is_reused_and_shared_identity_is_never_assigned_by_first_row(self):
        rows, _, _ = self._fixture()
        report = backfill_master_rows(rows)
        matched = next(item for item in report["mappings"] if item["source_row_number"] == 3)
        conflicts = [item for item in report["mappings"] if item["original_canonical_id"] == "master-conflict-a"]
        missing_conflict = next(item for item in report["mappings"] if item["source_row_number"] == 10)

        self.assertEqual(matched["base_decision"], "matched_existing")
        self.assertEqual(matched["proposed_canonical_id"], "master-alpha")
        self.assertEqual(conflicts[0]["base_decision"], "quarantined")
        self.assertEqual(missing_conflict["base_decision"], "quarantined")
        self.assertFalse(missing_conflict["proposed_canonical_id"])
        self.assertTrue(missing_conflict["quarantine_record_key"])

    def test_reordering_and_richer_enrichment_keep_identity_mapping_stable(self):
        rows, _, _ = self._fixture()
        forward = backfill_master_rows(rows)
        reverse = backfill_master_rows(reversed(rows))
        forward_by_fingerprint = {
            item["row_fingerprint"]: item["proposed_canonical_id"] for item in forward["mappings"]
        }
        reverse_by_fingerprint = {
            item["row_fingerprint"]: item["proposed_canonical_id"] for item in reverse["mappings"]
        }
        self.assertEqual(forward_by_fingerprint, reverse_by_fingerprint)

        sparse = [{"canonical_CompanyID": "", "companyenrich_id": "ce-stable", "company_name": "Stable"}]
        richer = [{**sparse[0], "description": "Added later", "website_url": "https://stable.example"}]
        first_id = backfill_master_rows(sparse)["mappings"][0]["proposed_canonical_id"]
        richer_id = backfill_master_rows(richer)["mappings"][0]["proposed_canonical_id"]
        self.assertEqual(first_id, richer_id)

    def test_duplicate_rows_share_one_new_id_and_page_or_malformed_identity_is_not_eligible(self):
        rows, _, _ = self._fixture()
        report = backfill_master_rows(rows)
        new_rows = [item for item in report["mappings"] if item["anchor_identity_key"] == "companyenrich:ce-new"]
        bad_id = next(item for item in report["mappings"] if item["reason"] == "malformed_linkedin_company_id")
        school = next(item for item in report["mappings"] if item["reason"] == "non_company_linkedin_page")

        self.assertEqual({item["proposed_canonical_id"] for item in new_rows}, {new_rows[0]["proposed_canonical_id"]})
        self.assertEqual(new_rows[1]["decision"], "duplicate")
        self.assertFalse(bad_id["eligible_for_identity_backfill"])
        self.assertFalse(school["eligible_for_identity_backfill"])

    def test_hash_collision_is_quarantined(self):
        collision_id = _deterministic_id("companyenrich:collision")
        rows = [
            {
                "canonical_CompanyID": collision_id,
                "companyenrich_id": "company-owner",
                "company_name": "Existing Owner",
            },
            {
                "canonical_CompanyID": "",
                "companyenrich_id": "collision",
                "company_name": "Collision Candidate",
            },
        ]
        report = backfill_master_rows(rows)
        candidate = report["mappings"][1]

        self.assertEqual(candidate["base_decision"], "quarantined")
        self.assertEqual(candidate["reason"], "deterministic_id_collision")
        self.assertFalse(candidate["proposed_canonical_id"])

    def test_approved_manifest_writes_copy_after_manifest_and_preserves_source(self):
        rows, fieldnames, source_hash = self._fixture()
        dry_run = backfill_master_rows(rows, input_sha256=source_hash)
        approved = {
            "approval_status": "approved",
            "identity_key_to_canonical_id": dry_run["mapping_manifest"]["identity_key_to_canonical_id"],
        }
        approved_report = backfill_master_rows(rows, input_sha256=source_hash, approved_mappings=approved)
        source_bytes = FIXTURE_PATH.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            source_copy = Path(directory) / "source.csv"
            source_copy.write_bytes(source_bytes)
            output = Path(directory) / "backfilled.csv"
            manifest = Path(directory) / "mapping.json"
            written = write_backfill_outputs(
                rows,
                fieldnames,
                source_path=source_copy,
                output_path=output,
                manifest_path=manifest,
                report=approved_report,
            )
            self.assertTrue(output.exists())
            self.assertTrue(manifest.exists())
            self.assertFalse(written["backup_path"])
            self.assertEqual(source_copy.read_bytes(), source_bytes)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["approval_status"], "approved_applied")
            with output.open("r", encoding="utf-8-sig", newline="") as handle:
                output_rows = list(csv.DictReader(handle))
            self.assertEqual(output_rows[1]["canonical_CompanyID"], "master-alpha")
            self.assertTrue(output_rows[2]["canonical_CompanyID"].startswith("canonical-"))

            old_output = output.read_bytes()
            write_backfill_outputs(
                rows,
                fieldnames,
                source_path=source_copy,
                output_path=output,
                manifest_path=Path(directory) / "mapping-second.json",
                report=approved_report,
            )
            self.assertEqual(output.with_name("backfilled.csv.before-rc004.bak").read_bytes(), old_output)

    def test_write_rejects_input_path_and_unapproved_new_mapping(self):
        rows, fieldnames, source_hash = self._fixture()
        dry_run = backfill_master_rows(rows, input_sha256=source_hash)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.csv"
            source.write_bytes(FIXTURE_PATH.read_bytes())
            with self.assertRaises(ValueError):
                write_backfill_outputs(
                    rows,
                    fieldnames,
                    source_path=source,
                    output_path=source,
                    manifest_path=Path(directory) / "manifest.json",
                    report=dry_run,
                )
            approved_existing_only = {
                "approval_status": "approved",
                "identity_key_to_canonical_id": {"companyenrich:ce-alpha": "master-alpha"},
            }
            report = backfill_master_rows(rows, approved_mappings=approved_existing_only)
            with self.assertRaises(ValueError):
                write_backfill_outputs(
                    rows,
                    fieldnames,
                    source_path=source,
                    output_path=Path(directory) / "output.csv",
                    manifest_path=Path(directory) / "manifest.json",
                    report=report,
                )
            approved_all = {
                "approval_status": "approved",
                "identity_key_to_canonical_id": dry_run["mapping_manifest"]["identity_key_to_canonical_id"],
            }
            approved_report = backfill_master_rows(rows, input_sha256=source_hash, approved_mappings=approved_all)
            source.write_bytes(source.read_bytes() + b"\n")
            with self.assertRaises(ValueError):
                write_backfill_outputs(
                    rows,
                    fieldnames,
                    source_path=source,
                    output_path=Path(directory) / "changed-source.csv",
                    manifest_path=Path(directory) / "changed-source.json",
                    report=approved_report,
                )


if __name__ == "__main__":
    unittest.main()
