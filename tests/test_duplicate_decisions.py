import json
import unittest

from backend.application.duplicate_decisions import (
    DUPLICATE_DECISION_API_CONTRACT,
    DUPLICATE_DECISION_PERSISTENCE_CONTRACT,
    DuplicateDecisionError,
    DuplicateDecisionService,
    InvalidTransitionError,
    SafetyValidationError,
)


class DuplicateDecisionServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = DuplicateDecisionService(
            clock=lambda: "2026-08-10T12:00:00+00:00",
            id_factory=iter(
                [
                    "decision_candidate",
                    "decision_confirm",
                    "decision_merge",
                    "decision_undo",
                    "decision_split",
                ]
            ).__next__,
        )
        self.affected_ids = ("canonical_job_berlin", "canonical_job_cairo")

    def _candidate(self):
        return self.service.create_candidate(
            cluster_id="cluster_1",
            affected_ids=self.affected_ids,
            actor="duplicate-detector",
            reason="same normalized title and company; review required",
            evidence={
                "source_observation_ids": ["observation_berlin", "observation_cairo"],
                "source_urls": [
                    "https://jobs.example.test/berlin",
                    "https://jobs.example.test/cairo",
                ],
                "confidence": 0.76,
            },
            rule_version="duplicate_rules_v2",
            occurred_at="2026-08-10T11:59:00+00:00",
            recorded_at="2026-08-10T11:59:01+00:00",
        )

    @staticmethod
    def _merge_plan():
        return {
            "operation": "plan_only",
            "automatic_merge": False,
            "survivor_id": "canonical_job_berlin",
            "absorbed_ids": ["canonical_job_cairo"],
            "preserved_observation_ids": ["observation_berlin", "observation_cairo"],
            "preserved_version_ids": ["version_berlin", "version_cairo"],
            "preserved_provenance_ids": ["provenance_berlin", "provenance_cairo"],
            "preserve_source_observations": True,
            "preserve_source_identities": True,
            "preserve_posting_versions": True,
            "preserve_provenance": True,
            "publication_action": "no_automatic_publication",
            "undo_actions": [
                "restore_canonical_job_cairo",
                "restore_previous_publication_relationship",
            ],
        }

    def test_candidate_is_typed_and_history_is_append_only(self):
        candidate = self._candidate()

        self.assertEqual(candidate.state, "candidate")
        self.assertEqual(candidate.affected_ids, self.affected_ids)
        self.assertEqual(candidate.history_sequence, 1)
        self.assertEqual(len(self.service.history("cluster_1")), 1)

        exported = self.service.to_persistence_record("cluster_1")
        persisted_cluster = exported["cluster"]
        self.assertEqual(persisted_cluster["state"], "candidate")
        self.assertEqual(persisted_cluster["rule_version"], "duplicate_rules_v2")
        self.assertEqual(json.loads(persisted_cluster["reasons_json"]), [candidate.reason])
        self.assertEqual(len(json.loads(persisted_cluster["review_history_json"])), 1)
        self.assertEqual(
            [row["canonical_job_id"] for row in exported["members"]],
            list(self.affected_ids),
        )

        # Public projections are defensive copies; callers cannot rewrite the
        # append-only history by mutating a returned evidence object.
        candidate.evidence["source_observation_ids"].clear()
        self.assertEqual(
            self.service.get("cluster_1").evidence["source_observation_ids"],
            ["observation_berlin", "observation_cairo"],
        )

    def test_confirmed_duplicate_merge_is_explicit_and_has_no_merge_side_effect(self):
        self._candidate()
        confirmed = self.service.decide(
            cluster_id="cluster_1",
            state="confirmed_duplicate",
            actor="admin_42",
            reason="same requisition verified by source evidence",
            evidence={"source_observation_ids": ["observation_berlin", "observation_cairo"]},
            rule_version="duplicate_rules_v2",
            expected_state="candidate",
            occurred_at="2026-08-10T12:01:00+00:00",
            recorded_at="2026-08-10T12:01:01+00:00",
        )
        merged = self.service.decide(
            cluster_id="cluster_1",
            state="merged",
            actor="admin_42",
            reason="same posting; retain the Berlin canonical record",
            evidence={"source_observation_ids": ["observation_berlin", "observation_cairo"]},
            rule_version="duplicate_rules_v2",
            merge_plan=self._merge_plan(),
            expected_state="confirmed_duplicate",
            occurred_at="2026-08-10T12:02:00+00:00",
            recorded_at="2026-08-10T12:02:01+00:00",
        )

        self.assertEqual(confirmed.state, "confirmed_duplicate")
        self.assertEqual(merged.state, "merged")
        self.assertEqual(self.service.get("cluster_1").state, "merged")
        self.assertEqual(
            [event.to_state for event in self.service.history("cluster_1")],
            ["candidate", "confirmed_duplicate", "merged"],
        )
        self.assertFalse(merged.merge_plan["automatic_merge"])
        self.assertEqual(merged.merge_plan["preserved_observation_ids"], ["observation_berlin", "observation_cairo"])

    def test_unsafe_merge_and_split_plans_are_rejected_without_state_change(self):
        self._candidate()
        self.service.decide(
            cluster_id="cluster_1",
            state="confirmed_duplicate",
            actor="admin_42",
            reason="needs review",
            evidence={"source_observation_ids": ["observation_berlin", "observation_cairo"]},
            rule_version="duplicate_rules_v2",
            occurred_at="2026-08-10T12:01:00+00:00",
            recorded_at="2026-08-10T12:01:01+00:00",
        )

        unsafe_merge = dict(self._merge_plan())
        unsafe_merge["automatic_merge"] = True
        with self.assertRaises(SafetyValidationError):
            self.service.decide(
                cluster_id="cluster_1",
                state="merged",
                actor="admin_42",
                reason="unsafe",
                evidence={"source_observation_ids": ["observation_berlin", "observation_cairo"]},
                rule_version="duplicate_rules_v2",
                merge_plan=unsafe_merge,
            )
        self.assertEqual(self.service.get("cluster_1").state, "confirmed_duplicate")

        with self.assertRaises(SafetyValidationError):
            self.service.decide(
                cluster_id="cluster_1",
                state="split",
                actor="admin_42",
                reason="unsafe split",
                evidence={"source_observation_ids": ["observation_berlin", "observation_cairo"]},
                rule_version="duplicate_rules_v2",
                split_plan={
                    "operation": "plan_only",
                    "automatic_merge": False,
                    "partitions": [["canonical_job_berlin"], ["canonical_job_cairo"]],
                    "preserve_source_observations": False,
                    "preserve_source_identities": True,
                    "preserve_posting_versions": True,
                    "preserve_provenance": True,
                    "publication_action": "no_automatic_publication",
                    "undo_actions": ["restore_previous_relationship"],
                },
            )
        self.assertEqual(len(self.service.history("cluster_1")), 2)

    def test_distinct_keeps_location_specific_requisitions_separate(self):
        self._candidate()
        distinct = self.service.decide(
            cluster_id="cluster_1",
            state="distinct",
            actor="admin_42",
            reason="separate requisitions with location-specific responsibilities",
            evidence={
                "source_observation_ids": ["observation_berlin", "observation_cairo"],
                "source_ids": ["req-berlin", "req-cairo"],
                "locations": ["Berlin", "Cairo"],
                "url_comparison": "different canonical posting URLs",
            },
            rule_version="duplicate_rules_v2",
            expected_state="candidate",
            occurred_at="2026-08-10T12:03:00+00:00",
            recorded_at="2026-08-10T12:03:01+00:00",
        )

        self.assertEqual(distinct.state, "distinct")
        self.assertEqual(distinct.affected_ids, self.affected_ids)
        self.assertNotIn("merged", [event.to_state for event in self.service.history("cluster_1")])
        self.assertEqual(self.service.to_persistence_record("cluster_1")["cluster"]["state"], "distinct")

    def test_split_and_undo_restore_the_prior_relationship_without_publishing(self):
        self._candidate()
        self.service.decide(
            cluster_id="cluster_1",
            state="confirmed_duplicate",
            actor="admin_42",
            reason="duplicate confirmed pending reversible review",
            evidence={"source_observation_ids": ["observation_berlin", "observation_cairo"]},
            rule_version="duplicate_rules_v2",
            occurred_at="2026-08-10T12:01:00+00:00",
            recorded_at="2026-08-10T12:01:01+00:00",
        )
        split = self.service.decide(
            cluster_id="cluster_1",
            state="split",
            actor="admin_42",
            reason="separate source identities after side-by-side review",
            evidence={"source_observation_ids": ["observation_berlin", "observation_cairo"]},
            rule_version="duplicate_rules_v2",
            split_plan={
                "operation": "plan_only",
                "automatic_merge": False,
                "partitions": [["canonical_job_berlin"], ["canonical_job_cairo"]],
                "preserve_source_observations": True,
                "preserve_source_identities": True,
                "preserve_posting_versions": True,
                "preserve_provenance": True,
                "publication_action": "no_automatic_publication",
                "undo_actions": ["restore_previous_relationship"],
            },
            occurred_at="2026-08-10T12:04:00+00:00",
            recorded_at="2026-08-10T12:04:01+00:00",
        )
        before_undo = self.service.plan_undo(
            "cluster_1",
            publication_relationship={
                "publication_id": "publication_head_1",
                "member_relationship": "held_for_review",
            },
        )
        self.assertEqual(self.service.get("cluster_1").state, "split")
        self.assertEqual(before_undo["restore_state"], "confirmed_duplicate")
        self.assertTrue(before_undo["preserve_source_observations"])
        self.assertFalse(before_undo["automatic_publish"])

        undone = self.service.undo(
            cluster_id="cluster_1",
            actor="admin_42",
            reason="undo split after corrected source comparison",
            evidence={"review_event": split.decision_id},
            rule_version="duplicate_rules_v2",
            publication_relationship={
                "publication_id": "publication_head_1",
                "member_relationship": "held_for_review",
            },
            occurred_at="2026-08-10T12:05:00+00:00",
            recorded_at="2026-08-10T12:05:01+00:00",
        )
        self.assertEqual(undone.state, "undone")
        self.assertEqual(undone.undo_of_decision_id, split.decision_id)
        self.assertEqual(undone.undo_plan["restore_state"], "confirmed_duplicate")
        self.assertEqual(
            undone.undo_plan["publication_relationship"]["publication_id"],
            "publication_head_1",
        )
        self.assertFalse(undone.undo_plan["automatic_merge"])
        self.assertFalse(undone.undo_plan["automatic_publish"])
        self.assertEqual(
            [event.to_state for event in self.service.history("cluster_1")],
            ["candidate", "confirmed_duplicate", "split", "undone"],
        )

    def test_invalid_expected_state_and_unknown_cluster_have_no_side_effect(self):
        self._candidate()
        with self.assertRaises(InvalidTransitionError):
            self.service.decide(
                cluster_id="cluster_1",
                state="distinct",
                actor="admin_42",
                reason="stale request",
                evidence={"source_observation_ids": ["observation_berlin", "observation_cairo"]},
                rule_version="duplicate_rules_v2",
                expected_state="confirmed_duplicate",
            )
        self.assertEqual(len(self.service.history("cluster_1")), 1)

        with self.assertRaises(DuplicateDecisionError) as context:
            self.service.get("missing_cluster")
        self.assertIn("Unknown duplicate cluster", str(context.exception))

    def test_contracts_keep_raw_evidence_admin_only_and_disable_automatic_operations(self):
        self.assertEqual(
            DUPLICATE_DECISION_PERSISTENCE_CONTRACT["cluster_table"],
            "acquisition_duplicate_clusters",
        )
        self.assertTrue(DUPLICATE_DECISION_PERSISTENCE_CONTRACT["append_only"])
        self.assertFalse(DUPLICATE_DECISION_PERSISTENCE_CONTRACT["automatic_merge"])
        self.assertFalse(DUPLICATE_DECISION_API_CONTRACT["automatic_merge"])
        self.assertEqual(
            DUPLICATE_DECISION_API_CONTRACT["raw_evidence"],
            "admin-only; reference observation/version IDs, do not publish payloads",
        )


if __name__ == "__main__":
    unittest.main()
