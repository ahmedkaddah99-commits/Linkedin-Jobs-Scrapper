from __future__ import annotations

import json
import socket
import unittest
from unittest.mock import patch

from backend.enrichment.evaluation import (
    ALTERNATE_RULE_VERSION,
    ALLOWED_PROMOTION_RECOMMENDATIONS,
    DEFAULT_RULE_VERSION,
    OfflineTrialOrchestrator,
    TrialConfig,
    compare_replays,
    render_markdown_report,
    report_json,
)
from backend.enrichment.fixture import load_evaluation_fixture, load_golden_labels


class DeterministicTrialTests(unittest.TestCase):
    def test_configuration_is_fail_closed_and_trial_run_is_immutable(self):
        with self.assertRaises(ValueError):
            TrialConfig(allow_network=True)
        with self.assertRaises(ValueError):
            TrialConfig(allow_ai=True)

        run = OfflineTrialOrchestrator().run(partition="development")
        with self.assertRaises((AttributeError, TypeError)):
            run.rule_version = "production"
        with self.assertRaises((AttributeError, TypeError)):
            run.outputs += ()
        self.assertFalse(run.report["trial"]["network_called"])
        self.assertFalse(run.report["trial"]["production_writes"])
        self.assertFalse(run.report["trial"]["publication_changed"])

    def test_partitions_keep_blind_holdout_unlabeled(self):
        fixture = load_evaluation_fixture(include_blind_holdout=True)
        labels = load_golden_labels()
        self.assertTrue(fixture)
        self.assertTrue(all(case["fixture_id"] not in labels for case in fixture if case["split"] == "blind_holdout"))

        report = OfflineTrialOrchestrator().run().report
        self.assertEqual(report["partitions"]["development"]["golden_label_cases"], 18)
        self.assertEqual(report["partitions"]["calibration"]["golden_label_cases"], 5)
        self.assertEqual(report["partitions"]["blind_holdout"]["golden_label_cases"], 0)
        self.assertFalse(report["partitions"]["blind_holdout"]["metrics_available"])

    def test_measured_metrics_cover_all_requested_dimensions(self):
        report = OfflineTrialOrchestrator().run().report
        dimensions = report["dimensions"]
        self.assertEqual(set(dimensions), {"place_normalization", "company_profile", "occupation_function", "language_evidence"})
        self.assertEqual(dimensions["place_normalization"]["top_1_accuracy"], 1.0)
        self.assertEqual(dimensions["place_normalization"]["top_3_accuracy"], 1.0)
        self.assertEqual(dimensions["company_profile"]["precision"], 1.0)
        self.assertEqual(dimensions["occupation_function"]["macro_f1"], 1.0)
        self.assertEqual(dimensions["language_evidence"]["calibration"]["available"], False)
        self.assertEqual(dimensions["company_profile"]["false_positive_rate"], 0.0)
        self.assertIn("German", report["per_language"])
        self.assertIn("greenhouse", report["per_connector"])

    def test_adversarial_checks_and_promotion_are_reported(self):
        run = OfflineTrialOrchestrator().run()
        report = run.report
        self.assertTrue(report["adversarial"]["all_passed"])
        self.assertEqual(report["adversarial"]["missing_categories"], ())
        self.assertIn(report["promotion"]["recommendation"], ALLOWED_PROMOTION_RECOMMENDATIONS)
        self.assertEqual(report["promotion"]["recommendation"], "continue shadow evaluation")
        self.assertIn("blind holdout", " ".join(report["data_gaps"]))
        self.assertIn("confidence scores", " ".join(report["data_gaps"]))
        ambiguous_paris = next(
            output
            for output in run.outputs
            if output.fixture_id == "cal_unqualified_paris" and output.dimension == "place_normalization"
        )
        self.assertEqual(ambiguous_paris.predicted["place_state"], "ambiguous")
        self.assertEqual(ambiguous_paris.predicted["place_candidate_id"], "")

    def test_company_identity_collision_stays_separate_from_lowell_location(self):
        run = OfflineTrialOrchestrator().run()
        outputs = {(output.fixture_id, output.dimension): output for output in run.outputs}
        employer = outputs[("dev_lowell_employer_leeds", "company_profile")]
        location = outputs[("dev_lowell_massachusetts", "company_profile")]
        self.assertEqual(employer.predicted["company_candidate_id"], "fixture:company:lowell")
        self.assertEqual(location.predicted["company_identity_state"], "blocked_name_only")
        self.assertEqual(location.predicted["company_candidate_id"], "")

    def test_trial_does_not_open_network_sockets(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network is forbidden")):
            run = OfflineTrialOrchestrator().run(partition="development")
        self.assertTrue(run.outputs)
        self.assertFalse(run.report["trial"]["network_called"])

    def test_replay_compares_rule_versions_without_mutating_observations(self):
        orchestrator = OfflineTrialOrchestrator()
        baseline, candidate, replay = orchestrator.replay(
            baseline_rule_version=DEFAULT_RULE_VERSION,
            candidate_rule_version=ALTERNATE_RULE_VERSION,
        )
        self.assertEqual(baseline.observation_ids, candidate.observation_ids)
        self.assertEqual(replay.compared_outputs, 112)
        self.assertEqual(replay.changed_outputs, 1)
        self.assertEqual(replay.changes_by_dimension["occupation_function"], 1)
        self.assertIn("cal_contradictory_department_title", replay.changed_fixture_ids)
        self.assertEqual(compare_replays(baseline, baseline).changed_outputs, 0)

    def test_reports_are_serializable_and_human_readable(self):
        run = OfflineTrialOrchestrator().run()
        payload = json.loads(report_json(run))
        markdown = render_markdown_report(run)
        self.assertEqual(payload["schema_version"], "offline_deterministic_trial_report_v1")
        self.assertIn("## Dimension metrics", markdown)
        self.assertIn("continue shadow evaluation", markdown)
        self.assertIn("Remote Germany/EU/unrestricted", markdown)


if __name__ == "__main__":
    unittest.main()
