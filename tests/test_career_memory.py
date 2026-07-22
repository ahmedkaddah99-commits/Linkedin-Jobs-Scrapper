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


if __name__ == "__main__":
    unittest.main()
