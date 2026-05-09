import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.capabilities.tailored_documents.cv_structuring import ensure_structured_cv_fields
from backend.capabilities.tailored_documents.generation import generate_docs_for_job
from backend.capabilities.tailored_documents.modes import resolve_cv_generation_prompt_settings


def _draft(summary: str, *, skill: str = "SQL", bullet: str = "Delivered reporting improvements.") -> dict:
    return {
        "cv_professional_summary": summary,
        "cv_professional_experience": [
            {
                "role_title": "Business Analyst",
                "company": "ACME",
                "period": "2022-2024",
                "bullets": [bullet, "Improved stakeholder reporting."],
            }
        ],
        "cv_education": [
            {
                "degree_title": "MSc Information Systems",
                "thesis_title": "Analytics Thesis",
                "thesis_bullets": ["Built dashboards."],
            }
        ],
        "cv_skills": [skill, "Stakeholder Management", "Requirements Gathering"],
        "tailored_cv": f"Professional Summary: {summary}",
    }


class TailoredDocumentGenerationTests(unittest.TestCase):
    def setUp(self):
        self.job = {
            "job_id": "job_1",
            "title": "Senior Analyst",
            "company": "ACME",
            "full_description": "Need SQL, stakeholder management, and dashboarding.",
        }
        self.cv_text = "\n".join(
            [
                "Professional Summary",
                "Trusted analyst with delivery experience.",
                "",
                "Professional Experience",
                "Business Analyst | ACME | 2022-2024",
                "- Baseline bullet one.",
                "- Baseline bullet two.",
                "",
                "Education",
                "MSc Information Systems",
                "Master Thesis: Analytics Thesis",
                "- Built baseline dashboards.",
                "",
                "Projects",
                "Insight Automation",
                "- Built a baseline workflow.",
            ]
        )

    @patch("backend.capabilities.tailored_documents.generation._improve_structured_cv_once")
    @patch("backend.capabilities.tailored_documents.generation._score_structured_cv_once")
    @patch("backend.capabilities.tailored_documents.generation._generate_structured_cv_once")
    def test_generate_docs_for_job_passes_after_first_score(
        self,
        generate_mock,
        score_mock,
        improve_mock,
    ):
        generate_mock.return_value = _draft("Strong first draft.")
        score_mock.return_value = {
            "score": 93,
            "missing_requirements": [],
            "improvement_actions": [],
            "rationale": "Strong fit.",
        }

        result = generate_docs_for_job(
            deepseek_api_key=None,
            deepseek_model="deepseek-chat",
            gemini_client=None,
            gemini_model="gemini-2.5-flash",
            cv_text=self.cv_text,
            job=self.job,
            candidate_name="Ahmed",
            cv_generation_mode="aggressive_customization",
            extra_instructions="",
            prompt_override="",
            retries=1,
            retry_sleep=0.0,
        )

        self.assertEqual(result["ats_attempt_count"], 1)
        self.assertEqual(result["ats_score"], 93)
        self.assertEqual(result["ats_gate_state"], "passed")
        self.assertTrue(result["ats_can_export_final"])
        self.assertFalse(result["ats_export_anyway_allowed"])
        self.assertEqual(result["ats_export_gate"]["gate_state"], "passed")
        improve_mock.assert_not_called()

    @patch("backend.capabilities.tailored_documents.generation._improve_structured_cv_once")
    @patch("backend.capabilities.tailored_documents.generation._score_structured_cv_once")
    @patch("backend.capabilities.tailored_documents.generation._generate_structured_cv_once")
    def test_generate_docs_for_job_stops_when_score_stalls_and_keeps_best_attempt(
        self,
        generate_mock,
        score_mock,
        improve_mock,
    ):
        first_draft = _draft("First ATS draft.", skill="SQL")
        second_draft = _draft("Second ATS draft.", skill="Python", bullet="Refined the wording.")
        generate_mock.return_value = first_draft
        improve_mock.return_value = second_draft
        score_mock.side_effect = [
            {
                "score": 84,
                "missing_requirements": ["SQL"],
                "improvement_actions": ["Make SQL evidence more explicit."],
                "rationale": "Close match.",
            },
            {
                "score": 84,
                "missing_requirements": ["Python"],
                "improvement_actions": ["Add more evidence."],
                "rationale": "No improvement.",
            },
        ]

        result = generate_docs_for_job(
            deepseek_api_key=None,
            deepseek_model="deepseek-chat",
            gemini_client=None,
            gemini_model="gemini-2.5-flash",
            cv_text=self.cv_text,
            job=self.job,
            candidate_name="Ahmed",
            cv_generation_mode="aggressive_customization",
            extra_instructions="",
            prompt_override="",
            retries=1,
            retry_sleep=0.0,
        )

        self.assertEqual(result["cv_professional_summary"], first_draft["cv_professional_summary"])
        self.assertEqual(result["ats_score"], 84)
        self.assertEqual(result["ats_attempt_count"], 2)
        self.assertEqual(result["ats_stop_reason"], "score_stalled")
        self.assertEqual(result["ats_missing_requirements"], ["SQL"])
        self.assertEqual(result["ats_gate_state"], "blocked")
        self.assertFalse(result["ats_can_export_final"])
        self.assertTrue(result["ats_export_anyway_allowed"])
        self.assertEqual(result["ats_export_gate"]["metadata"]["stop_reason"], "score_stalled")
        self.assertIn("Best score reached: 84%", result["ats_last_warning"])
        self.assertEqual(len(result["ats_attempt_history"]), 2)
        self.assertEqual(improve_mock.call_count, 1)

    @patch("backend.capabilities.tailored_documents.generation._improve_structured_cv_once")
    @patch("backend.capabilities.tailored_documents.generation._score_structured_cv_once")
    @patch("backend.capabilities.tailored_documents.generation._generate_structured_cv_once")
    def test_generate_docs_for_job_blocks_after_third_scored_attempt(
        self,
        generate_mock,
        score_mock,
        improve_mock,
    ):
        generate_mock.return_value = _draft("Draft one.", skill="Excel")
        improve_mock.side_effect = [
            _draft("Draft two.", skill="SQL"),
            _draft("Draft three.", skill="Dashboarding"),
        ]
        score_mock.side_effect = [
            {
                "score": 80,
                "missing_requirements": ["SQL"],
                "improvement_actions": ["Add SQL evidence."],
                "rationale": "Weak SQL coverage.",
            },
            {
                "score": 85,
                "missing_requirements": ["Dashboarding"],
                "improvement_actions": ["Highlight dashboard work."],
                "rationale": "Improved.",
            },
            {
                "score": 88,
                "missing_requirements": ["Leadership"],
                "improvement_actions": ["Clarify leadership scope."],
                "rationale": "Best attempt but under target.",
            },
        ]

        result = generate_docs_for_job(
            deepseek_api_key=None,
            deepseek_model="deepseek-chat",
            gemini_client=None,
            gemini_model="gemini-2.5-flash",
            cv_text=self.cv_text,
            job=self.job,
            candidate_name="Ahmed",
            cv_generation_mode="aggressive_customization",
            extra_instructions="",
            prompt_override="",
            retries=1,
            retry_sleep=0.0,
        )

        self.assertEqual(result["cv_professional_summary"], "Draft three.")
        self.assertEqual(result["ats_score"], 88)
        self.assertEqual(result["ats_attempt_count"], 3)
        self.assertEqual(result["ats_stop_reason"], "max_attempts_reached")
        self.assertEqual(result["ats_gate_state"], "blocked")
        self.assertTrue(result["ats_export_anyway_allowed"])
        self.assertEqual(result["ats_export_gate"]["best_score"], 88)
        self.assertIn("Best score reached: 88%", result["ats_export_gate"]["last_warning"])
        self.assertEqual(improve_mock.call_count, 2)

    def test_resolve_cv_generation_prompt_settings_uses_mode_specific_fields(self):
        settings = SimpleNamespace(
            light_customization_extra_prompt="Light extra",
            light_customization_prompt_override="Light override",
            aggressive_customization_extra_prompt="Aggressive extra",
            aggressive_customization_prompt_override="Aggressive override",
            stage4_extra_prompt="Legacy extra",
            stage4_prompt_override="Legacy override",
        )

        self.assertEqual(
            resolve_cv_generation_prompt_settings("light_customization", settings),
            ("Light extra", "Light override"),
        )
        self.assertEqual(
            resolve_cv_generation_prompt_settings("aggressive_customization", settings),
            ("Aggressive extra", "Aggressive override"),
        )
        self.assertEqual(
            resolve_cv_generation_prompt_settings(
                "aggressive_customization",
                SimpleNamespace(
                    aggressive_customization_extra_prompt="",
                    aggressive_customization_prompt_override="",
                    stage4_extra_prompt="Legacy extra",
                    stage4_prompt_override="Legacy override",
                ),
            ),
            ("Legacy extra", "Legacy override"),
        )

    @patch("backend.capabilities.tailored_documents.generation._score_structured_cv_once")
    @patch("backend.capabilities.tailored_documents.generation._generate_structured_cv_once")
    def test_light_mode_clamps_forbidden_changes_after_generation(self, generate_mock, score_mock):
        generate_mock.return_value = {
            "cv_professional_summary": "Light-mode summary tuned to the role.",
            "cv_professional_experience": [
                {
                    "role_title": "Senior Analyst",
                    "company": "Different Company",
                    "period": "2020-2021",
                    "bullets": ["Rewritten forbidden bullet."],
                }
            ],
            "cv_education": [
                {
                    "degree_title": "Renamed Degree",
                    "thesis_title": "Renamed Thesis",
                    "thesis_bullets": ["Forbidden education rewrite."],
                }
            ],
            "cv_skills": ["SQL", "Dashboarding", "Stakeholder Management"],
            "tailored_cv": "Light-mode summary tuned to the role.",
        }
        score_mock.return_value = {
            "score": 92,
            "missing_requirements": [],
            "improvement_actions": [],
            "rationale": "Looks good.",
        }

        result = generate_docs_for_job(
            deepseek_api_key=None,
            deepseek_model="deepseek-chat",
            gemini_client=None,
            gemini_model="gemini-2.5-flash",
            cv_text=self.cv_text,
            job=self.job,
            candidate_name="Ahmed",
            cv_generation_mode="light_customization",
            extra_instructions="",
            prompt_override="",
            retries=1,
            retry_sleep=0.0,
            payload_postprocessor=lambda payload: self._clamp_payload(payload, "light_customization"),
        )

        self.assertEqual(result["cv_professional_summary"], "Light-mode summary tuned to the role.")
        self.assertEqual(result["cv_skills"], ["SQL", "Dashboarding", "Stakeholder Management"])
        self.assertEqual(result["cv_professional_experience"][0]["role_title"], "Business Analyst")
        self.assertEqual(result["cv_professional_experience"][0]["company"], "ACME")
        self.assertEqual(result["cv_professional_experience"][0]["period"], "2022-2024")
        self.assertEqual(
            result["cv_professional_experience"][0]["bullets"],
            ["Baseline bullet one.", "Baseline bullet two."],
        )
        self.assertEqual(result["cv_education"][0]["degree_title"], "MSc Information Systems")
        self.assertEqual(result["cv_education"][0]["thesis_bullets"], ["Built baseline dashboards."])

    @patch("backend.capabilities.tailored_documents.generation._score_structured_cv_once")
    @patch("backend.capabilities.tailored_documents.generation._generate_structured_cv_once")
    def test_aggressive_mode_keeps_identity_but_allows_bullet_rewrites(self, generate_mock, score_mock):
        generate_mock.return_value = {
            "cv_professional_summary": "Aggressive summary tuned to the role.",
            "cv_professional_experience": [
                {
                    "role_title": "Business Analyst",
                    "company": "ACME",
                    "period": "2022-2024",
                    "bullets": [
                        "Rewritten aggressive bullet one.",
                        "Rewritten aggressive bullet two.",
                        "Extra bullet that should be discarded.",
                    ],
                }
            ],
            "cv_education": [
                {
                    "degree_title": "Renamed Degree",
                    "thesis_title": "Renamed Thesis",
                    "thesis_bullets": ["Forbidden education rewrite."],
                }
            ],
            "cv_skills": ["SQL", "Dashboarding", "Stakeholder Management"],
            "tailored_cv": "Aggressive summary tuned to the role.",
        }
        score_mock.return_value = {
            "score": 91,
            "missing_requirements": [],
            "improvement_actions": [],
            "rationale": "Looks good.",
        }

        result = generate_docs_for_job(
            deepseek_api_key=None,
            deepseek_model="deepseek-chat",
            gemini_client=None,
            gemini_model="gemini-2.5-flash",
            cv_text=self.cv_text,
            job=self.job,
            candidate_name="Ahmed",
            cv_generation_mode="aggressive_customization",
            extra_instructions="",
            prompt_override="",
            retries=1,
            retry_sleep=0.0,
            payload_postprocessor=lambda payload: self._clamp_payload(payload, "aggressive_customization"),
        )

        self.assertEqual(
            result["cv_professional_experience"][0]["bullets"],
            ["Rewritten aggressive bullet one.", "Rewritten aggressive bullet two."],
        )
        self.assertEqual(result["cv_professional_experience"][0]["role_title"], "Business Analyst")
        self.assertEqual(result["cv_education"][0]["degree_title"], "MSc Information Systems")
        self.assertEqual(result["cv_education"][0]["thesis_bullets"], ["Built baseline dashboards."])

    def _clamp_payload(self, payload, mode):
        normalized_payload = dict(payload)
        ensure_structured_cv_fields(
            normalized_payload,
            candidate_name="Ahmed",
            cv_text=self.cv_text,
            cv_generation_mode=mode,
        )
        return normalized_payload


if __name__ == "__main__":
    unittest.main()
