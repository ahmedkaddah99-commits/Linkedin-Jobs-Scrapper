"""Test evidence-item model and migration (CP-016).

These tests verify that:
- The evidence-item model lifecycle works correctly.
- The legacy career_memory facts can be migrated to CandidateEvidence items.
- The evidence pipeline (extract -> deduplicate -> conflict) runs end-to-end.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.capabilities.candidate_evidence import (
    CandidateEvidence,
    build_evidence_summary,
    clear_legacy_career_memory,
    deduplicate_evidence,
    detect_and_apply_conflicts,
    has_legacy_career_memory,
    migrate_legacy_facts_to_evidence,
)
from backend.domain.candidate_evidence import (
    EVIDENCE_STATUS_CONFIRMED,
    EVIDENCE_STATUS_NEEDS_REVIEW,
    EVIDENCE_STATUS_CONFLICT,
    EVIDENCE_STATUS_MERGED,
)
from backend.domain.models import UserRecord

class EvidenceItemModelTests(unittest.TestCase):
    """Tests covering the CandidateEvidence model and lifecycle."""

    def test_evidence_creation_defaults(self):
        ev = CandidateEvidence.create(
            profile_id="prof_1",
            text="Built Python automation for weekly reporting.",
        )
        self.assertTrue(ev.evidence_id.startswith("ev_"))
        self.assertEqual(ev.profile_id, "prof_1")
        self.assertEqual(ev.status, EVIDENCE_STATUS_NEEDS_REVIEW)
        self.assertTrue(len(ev.content_hash) > 0)

    def test_evidence_lifecycle_transitions(self):
        ev = CandidateEvidence.create(
            profile_id="prof_1",
            text="Reduced manual review time by 40 percent.",
        )
        self.assertTrue(ev.needs_review)

        ev.mark_reviewed()
        self.assertEqual(ev.status, "reviewed")

        ev.confirm()
        self.assertTrue(ev.is_confirmed)

        ev.reject()
        self.assertEqual(ev.status, "rejected")

    def test_evidence_conflict_and_merge(self):
        ev = CandidateEvidence.create(
            profile_id="prof_1",
            text="Improved team output by 30%.",
        )
        ev.mark_conflict(["ev_other_1", "ev_other_2"])
        self.assertTrue(ev.is_conflicting)
        self.assertEqual(ev.conflicting_with, ["ev_other_1", "ev_other_2"])

        ev.mark_merged("ev_primary_1")
        self.assertTrue(ev.is_merged)
        self.assertEqual(ev.duplicate_group_id, "ev_primary_1")

    def test_evidence_to_dict_and_from_dict(self):
        ev = CandidateEvidence.create(
            profile_id="prof_1",
            evidence_type="achievement",
            text="Delivered a major platform migration.",
            source_asset="cv.pdf",
            excerpt="Delivered a major platform migration.",
            confidence=0.9,
            inferred_employer="ACME Corp",
            inferred_role="Senior Engineer",
        )
        d = ev.to_dict()
        self.assertEqual(d["text"], "Delivered a major platform migration.")
        self.assertEqual(d["inferred_employer"], "ACME Corp")

        restored = CandidateEvidence.from_dict(d)
        self.assertEqual(restored.evidence_id, ev.evidence_id)
        self.assertEqual(restored.text, ev.text)
        self.assertEqual(restored.status, ev.status)

    def test_evidence_summary(self):
        items = [
            CandidateEvidence.create(profile_id="p", text="Built a thing.", evidence_type="achievement"),
            CandidateEvidence.create(profile_id="p", text="Used Python.", evidence_type="tool"),
            CandidateEvidence.create(profile_id="p", text="Managed a team.", evidence_type="leadership"),
        ]
        items[0].confirm()
        summary = build_evidence_summary(items)
        self.assertEqual(summary["total_evidence"], 3)
        self.assertEqual(summary["by_type"]["achievement"], 1)
        self.assertEqual(summary["by_type"]["tool"], 1)
        self.assertEqual(summary["by_type"]["leadership"], 1)

    def test_evidence_deduplication(self):
        items = [
            CandidateEvidence.create(profile_id="p", text="Reduced costs by 20 percent."),
            CandidateEvidence.create(profile_id="p", text="Reduced costs by 20 percent."),
            CandidateEvidence.create(profile_id="p", text="Completely different thing."),
        ]
        result = deduplicate_evidence(items, threshold=0.75)
        self.assertEqual(result["merged_items"], 1)
        self.assertEqual(result["duplicate_groups"], 1)

    def test_evidence_conflict_detection(self):
        items = [
            CandidateEvidence.create(profile_id="p", evidence_type="metric",
                                     text="Revenue grew 15% at ACME.",
                                     inferred_employer="ACME"),
            CandidateEvidence.create(profile_id="p", evidence_type="metric",
                                     text="Revenue grew 25% at BetaCorp.",
                                     inferred_employer="BetaCorp"),
        ]
        result = detect_and_apply_conflicts(items)
        self.assertGreaterEqual(result["conflict_items"], 0)


class LegacyMigrationTests(unittest.TestCase):
    """Tests covering the migration from legacy career_memory to evidence items."""

    def setUp(self):
        self.legacy_metadata = {
            "career_memory": {
                "facts": [
                    {
                        "fact_id": "fact_abc123",
                        "type": "action",
                        "value": "Built Python automation for weekly application reporting.",
                        "certainty": "estimated",
                        "sources": [{"asset_id": "asset_cv", "page": 1}],
                        "subject": {"company": "ACME Corp", "role": "Engineer", "project": ""},
                        "created_by": "extraction",
                        "version": 1,
                        "status": "active",
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-01-01T00:00:00Z",
                    },
                    {
                        "fact_id": "fact_def456",
                        "type": "metric",
                        "value": "Reduced manual review time by 40 percent.",
                        "certainty": "confirmed",
                        "sources": [{"asset_id": "asset_cv", "page": 2}],
                        "subject": {"company": "ACME Corp", "role": "", "project": ""},
                        "created_by": "extraction",
                        "version": 1,
                        "status": "active",
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-01-01T00:00:00Z",
                    },
                    {
                        "fact_id": "fact_stale",
                        "type": "tool",
                        "value": "Used old tool.",
                        "certainty": "estimated",
                        "sources": [],
                        "subject": {},
                        "created_by": "extraction",
                        "version": 2,
                        "status": "stale",
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-01-01T00:00:00Z",
                    },
                ],
                "outputs": [],
                "source_signatures": {},
            }
        }

    def test_has_legacy_career_memory(self):
        self.assertTrue(has_legacy_career_memory(self.legacy_metadata))
        self.assertFalse(has_legacy_career_memory(None))
        self.assertFalse(has_legacy_career_memory({}))

    def test_migrate_legacy_facts_to_evidence(self):
        evidence = migrate_legacy_facts_to_evidence(
            profile_id="prof_test",
            user_metadata=self.legacy_metadata,
        )
        self.assertEqual(len(evidence), 2)
        for ev in evidence:
            self.assertIsInstance(ev, CandidateEvidence)
            self.assertEqual(ev.profile_id, "prof_test")
            self.assertIn("migrated_from", ev.metadata)
            self.assertEqual(ev.metadata["migrated_from"], "career_memory")
        types = {ev.evidence_type for ev in evidence}
        self.assertIn("metric", types)
        confirmed = [ev for ev in evidence if ev.is_confirmed]
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(confirmed[0].text, "Reduced manual review time by 40 percent.")

    def test_clear_legacy_career_memory(self):
        cleaned = clear_legacy_career_memory(self.legacy_metadata)
        self.assertNotIn("career_memory", cleaned)
        self.assertIn("career_memory", self.legacy_metadata)

    def test_migrate_empty_metadata(self):
        evidence = migrate_legacy_facts_to_evidence(
            profile_id="prof_empty",
            user_metadata={},
        )
        self.assertEqual(len(evidence), 0)


class CanonicalEvidenceE2ETests(unittest.TestCase):
    """End-to-end tests for canonical evidence lifecycle (CP-032R)."""

    def setUp(self):
        self.legacy_metadata = {
            "career_memory": {
                "facts": [
                    {"fact_id": "fact_e2e_001", "type": "action",
                     "value": "Built Python automation for weekly reporting.",
                     "certainty": "estimated",
                     "sources": [{"asset_id": "asset_cv", "page": 1}],
                     "subject": {"company": "ACME Corp", "role": "Engineer"},
                     "version": 1, "status": "active",
                     "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z"},
                    {"fact_id": "fact_e2e_002", "type": "metric",
                     "value": "Reduced manual review time by 40 percent.",
                     "certainty": "confirmed",
                     "sources": [{"asset_id": "asset_cv", "page": 2}],
                     "subject": {"company": "ACME Corp", "role": "Engineer"},
                     "version": 1, "status": "active",
                     "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-01T00:00:00Z"},
                ], "outputs": [], "source_signatures": {}
            }
        }

    def test_migrate_idempotent_no_duplicates(self):
        from backend.capabilities.candidate_evidence import migrate_and_deduplicate
        result1 = migrate_and_deduplicate(profile_id="p", user_metadata=self.legacy_metadata)
        self.assertEqual(result1["migrated"], 2)
        self.assertEqual(result1["skipped"], 0)
        existing = [CandidateEvidence.from_dict(ev) for ev in result1["evidence"]]
        result2 = migrate_and_deduplicate(profile_id="p", user_metadata=self.legacy_metadata, existing_evidence=existing)
        self.assertEqual(result2["migrated"], 0)
        self.assertEqual(result2["skipped"], 2)

    def test_migration_preserves_provenance(self):
        from backend.capabilities.candidate_evidence import migrate_and_deduplicate
        result = migrate_and_deduplicate(profile_id="p", user_metadata=self.legacy_metadata)
        self.assertEqual(len(result["evidence"]), 2)
        for ev_dict in result["evidence"]:
            ev = CandidateEvidence.from_dict(ev_dict)
            self.assertEqual(ev.profile_id, "p")
            self.assertIn("migrated_from", ev.metadata)
            self.assertIn("experience_mapping", ev_dict)
            self.assertIn("certainty", ev_dict)
            self.assertIn("version", ev_dict)

    def test_evidence_lifecycle_to_generation(self):
        from backend.capabilities.candidate_evidence import generate_evidence_outputs, get_confirmed_evidence
        ev1 = CandidateEvidence.create(text="Increased revenue 30%.", evidence_type="metric", certainty="confirmed")
        ev1.mark_reviewed()
        ev1.confirm()
        ev2 = CandidateEvidence.create(text="Led team of 12 engineers.", evidence_type="leadership")
        ev2.mark_reviewed()
        ev2.confirm()
        self.assertTrue(ev1.is_confirmed)
        self.assertTrue(ev2.is_confirmed)
        confirmed = get_confirmed_evidence([ev1, ev2])
        self.assertEqual(len(confirmed), 2)
        output = generate_evidence_outputs([ev1, ev2])
        self.assertIn("cv_bullet", output)
        self.assertEqual(output["quality"]["status"], "passed")

    def test_generation_requires_confirmed(self):
        from backend.capabilities.candidate_evidence import generate_evidence_outputs
        ev = CandidateEvidence.create(text="Unconfirmed claim.")
        with self.assertRaises(ValueError):
            generate_evidence_outputs([ev])

    def test_regenerate_versions(self):
        from backend.capabilities.candidate_evidence import generate_evidence_outputs, regenerate_evidence_output
        ev = CandidateEvidence.create(text="Delivered migration.", certainty="confirmed")
        ev.confirm()
        o1 = generate_evidence_outputs([ev])
        self.assertEqual(o1["version"], 1)
        o2 = regenerate_evidence_output(o1, [ev], action="shorten")
        self.assertEqual(o2["version"], 2)
        o3 = regenerate_evidence_output(o2, [ev], action="edit", cv_bullet="Edited.", cover_letter=o2["cover_letter"])
        self.assertEqual(o3["version"], 3)
        self.assertEqual(o3["cv_bullet"], "Edited.")

    def test_new_version_immutable(self):
        ev = CandidateEvidence.create(text="Original.", certainty="confirmed")
        ev.confirm()
        ev2 = ev.new_version(text="Corrected.")
        self.assertEqual(ev.version, 1)
        self.assertEqual(ev.text, "Original.")
        self.assertEqual(ev2.version, 2)
        self.assertEqual(ev2.text, "Corrected.")
        self.assertNotEqual(ev.evidence_id, ev2.evidence_id)

    def test_reload_after_migration(self):
        from backend.capabilities.candidate_evidence import migrate_and_deduplicate
        result = migrate_and_deduplicate(profile_id="p", user_metadata=self.legacy_metadata)
        reloaded = [CandidateEvidence.from_dict(ev) for ev in result["evidence"]]
        self.assertEqual(len(reloaded), 2)
        for ev in reloaded:
            d = ev.to_dict()
            r = CandidateEvidence.from_dict(d)
            self.assertEqual(r.evidence_id, ev.evidence_id)
            self.assertEqual(r.text, ev.text)
            self.assertEqual(r.version, ev.version)

    def test_duplicate_prevention_hash(self):
        from backend.domain.candidate_evidence import compute_content_hash
        ev1 = CandidateEvidence.create(text="Managed team of 5.")
        ev2 = CandidateEvidence.create(text="Managed team of 5.")
        self.assertEqual(ev1.content_hash, ev2.content_hash)
        ev3 = CandidateEvidence.create(text="Led team of 10.")
        self.assertNotEqual(ev1.content_hash, ev3.content_hash)

    def test_experience_mapping_roundtrip(self):
        from backend.capabilities.candidate_evidence import migrate_and_deduplicate
        result = migrate_and_deduplicate(profile_id="p", user_metadata=self.legacy_metadata)
        ev_dict = result["evidence"][0]
        ev = CandidateEvidence.from_dict(ev_dict)
        self.assertIn("company", ev.experience_mapping)
        self.assertEqual(ev.experience_mapping["company"], "ACME Corp")


if __name__ == "__main__":
    unittest.main()
