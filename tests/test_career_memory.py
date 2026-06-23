import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.career_memory import (
    confirm_fact,
    extract_facts,
    generate_outputs,
    get_career_memory_state,
    next_question,
    regenerate_output,
)
from backend.domain.models import UserRecord


class CareerMemoryTests(unittest.TestCase):
    def setUp(self):
        self.repository = MagicMock()
        self.application = SimpleNamespace(
            repositories=SimpleNamespace(auth_repository=self.repository)
        )
        self.user = UserRecord.create(
            email="candidate@example.com",
            metadata={
                "candidate_assets": [
                    {
                        "asset_id": "asset_cv",
                        "metadata": {
                            "content_sha256": "signature-v1",
                            "source_text": (
                                "Built Python automation for weekly application reporting.\n"
                                "Reduced manual review time by 40 percent across the recruiting team."
                            ),
                        },
                    }
                ]
            },
        )

    def _confirm(self, fact_id: str, value: str, fact_type: str):
        return confirm_fact(
            self.application,
            self.user,
            fact_id,
            {"value": value, "type": fact_type, "certainty": "confirmed"},
        )

    def test_generation_uses_confirmed_metrics_and_keeps_outputs_distinct(self):
        extracted = extract_facts(self.application, self.user, ["asset_cv"])
        metric = next(fact for fact in extracted["active_facts"] if fact["type"] == "metric")
        self._confirm(metric["fact_id"], metric["value"], "metric")

        payload = generate_outputs(self.application, self.user, {"mode": "standard"})
        output = payload["output"]

        self.assertIn("40 percent", f"{output['cv_bullet']} {output['cover_letter']}")
        self.assertNotEqual(output["cv_bullet"], output["cover_letter"])
        self.assertEqual(output["quality"]["status"], "passed")
        self.assertFalse(
            {"prompt_leakage", "unconfirmed_metric", "unsupported_phrase"}
            & {issue["code"] for issue in output["quality"]["issues"]}
        )

    def test_unconfirmed_numeric_fact_is_excluded_from_output(self):
        extract_facts(self.application, self.user, ["asset_cv"])
        payload = generate_outputs(self.application, self.user, {"mode": "standard"})
        combined = f"{payload['output']['cv_bullet']} {payload['output']['cover_letter']}"
        self.assertNotIn("40 percent", combined)

    def test_output_edit_is_versioned_and_does_not_mutate_facts(self):
        extract_facts(self.application, self.user, ["asset_cv"])
        generated = generate_outputs(self.application, self.user, {"mode": "standard"})
        before = list(get_career_memory_state(self.user)["fact_history"])

        edited = regenerate_output(
            self.application,
            self.user,
            generated["output"]["output_id"],
            {
                "action": "edit",
                "cv_bullet": "Invented unsupported synergy claim.",
                "cover_letter": generated["output"]["cover_letter"],
            },
        )

        self.assertEqual(before, get_career_memory_state(self.user)["fact_history"])
        self.assertEqual(edited["output"]["version"], 2)
        self.assertIn(
            "unsupported_phrase",
            {issue["code"] for issue in edited["output"]["quality"]["issues"]},
        )
        self.assertEqual(
            generated["output"]["fact_ids"],
            edited["output"]["fact_ids"],
        )

    def test_source_change_stales_previous_version_and_creates_active_version(self):
        first = extract_facts(self.application, self.user, ["asset_cv"])
        original = first["active_facts"][0]
        self.user.metadata["candidate_assets"][0]["metadata"]["content_sha256"] = "signature-v2"

        second = extract_facts(self.application, self.user, ["asset_cv"])
        versions = [
            fact
            for fact in second["fact_history"]
            if fact["fact_id"] == original["fact_id"]
        ]

        self.assertEqual([fact["version"] for fact in versions], [1, 2, 3])
        self.assertEqual([fact["status"] for fact in versions], ["active", "stale", "active"])

    def test_missing_outcome_question_creates_a_new_fact_instead_of_retyping_an_action(self):
        extract_facts(self.application, self.user, ["asset_cv"])
        question = next_question(self.user)
        if question["expected_type"] == "metric":
            metric = next(
                fact
                for fact in get_career_memory_state(self.user)["active_facts"]
                if fact["fact_id"] == question["fact_id"]
            )
            self._confirm(metric["fact_id"], metric["value"], "metric")
            question = next_question(self.user)

        self.assertEqual(question["expected_type"], "outcome")
        self.assertEqual(question["fact_id"], "")


if __name__ == "__main__":
    unittest.main()
