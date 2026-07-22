import unittest

from backend.capabilities.tailored_documents.motivation_letters import (
    ExperienceEvidence,
    MotivationEvidence,
    MotivationLetterInput,
    MotivationLetterResult,
    MotivationLetterSection,
    assess_evidence_sufficiency,
    build_evidence_from_profile,
    build_motivation_prompt,
    generate_motivation_letter_for_job,
)



class AssessEvidenceSufficiencyTests(unittest.TestCase):

    def test_sufficient_when_motivation_and_experience_present(self):
        motivations = [
            MotivationEvidence(
                evidence_id="m1", category="career_goal",
                statement="I want to work in AI.", confidence="high",
            ),
            MotivationEvidence(
                evidence_id="m2", category="industry_interest",
                statement="Passionate about fintech.", confidence="high",
            ),
        ]
        experiences = [
            ExperienceEvidence(
                experience_id="e1", role_title="Analyst",
                company="ACME", period="2020-2023",
                key_bullets=["Led data projects"],
            ),
            ExperienceEvidence(
                experience_id="e2", role_title="Consultant",
                company="Contoso", period="2018-2020",
                key_bullets=["Advised clients on strategy"],
            ),
        ]
        is_sufficient, warnings = assess_evidence_sufficiency(motivations, experiences)
        self.assertTrue(is_sufficient)
        self.assertEqual(len(warnings), 0)

    def test_insufficient_when_no_motivations(self):
        motivations = []
        experiences = [
            ExperienceEvidence(
                experience_id="e1", role_title="Analyst",
                company="ACME", period="2020-2023",
                key_bullets=["Led data projects"],
            ),
        ]
        is_sufficient, warnings = assess_evidence_sufficiency(motivations, experiences)
        self.assertFalse(is_sufficient)
        self.assertTrue(len(warnings) > 0)

    def test_warns_when_below_minimum_experience(self):
        motivations = [
            MotivationEvidence(
                evidence_id="m1", category="career_goal",
                statement="I want to work in AI.", confidence="high",
            ),
        ]
        experiences = [
            ExperienceEvidence(
                experience_id="e1", role_title="Analyst",
                company="ACME", period="2020-2023",
                key_bullets=["Led data projects"],
            ),
        ]


class BuildMotivationPromptTests(unittest.TestCase):

    def test_returns_non_empty_string(self):
        input_data = MotivationLetterInput(
            candidate_name="Alice", job_title="Data Analyst",
            job_company="Tech Corp", job_description_text="Analyze data.",
            cv_text="Experienced analyst...",
        )
        prompt = build_motivation_prompt(input_data)
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 100)
        self.assertIn("Alice", prompt)

    def test_includes_evidence_when_provided(self):
        input_data = MotivationLetterInput(
            candidate_name="Bob", job_title="Engineer",
            job_company="BigCo", job_description_text="Build things.",
            cv_text="CV here...",
            verified_motivations=[
                MotivationEvidence(
                    evidence_id="ev_motivation_1", category="career_goal",
                    statement="I love engineering.", confidence="high",
                ),
            ],
            verified_experiences=[
                ExperienceEvidence(
                    experience_id="ev_exp_1", role_title="Engineer",
                    company="PrevCo", period="2020-2023",
                    key_bullets=["Built APIs"],
                ),
            ],
        )
        prompt = build_motivation_prompt(input_data)
        self.assertIn("ev_motivation_1", prompt)
        self.assertIn("ev_exp_1", prompt)

    def test_includes_company_context(self):
        input_data = MotivationLetterInput(
            candidate_name="Carol", job_title="PM",
            job_company="Innovate Inc", job_description_text="Manage products.",
            cv_text="CV...", company_context="Innovate Inc just raised Series B.",
        )
        prompt = build_motivation_prompt(input_data)
        self.assertIn("Series B", prompt)

    def test_includes_role_requirements(self):
        input_data = MotivationLetterInput(
            candidate_name="Dan", job_title="Analyst",
            job_company="Firm", job_description_text="Need an analyst.",
            cv_text="CV...",
            role_requirements=["SQL proficiency", "Stakeholder management"],
        )
        prompt = build_motivation_prompt(input_data)
        self.assertIn("SQL proficiency", prompt)

    def test_german_output_language(self):
        input_data = MotivationLetterInput(
            candidate_name="Frank", job_title="Entwickler",
            job_company="Firma", job_description_text="Entwickle Software.",
            cv_text="CV...", output_language="German",
        )
        prompt = build_motivation_prompt(input_data)
        self.assertIn("German", prompt)



class BuildEvidenceFromProfileTests(unittest.TestCase):

    def test_extracts_motivations_from_career_goal(self):
        profile = {
            "career_goal": "Transition into product management.",
            "recent_experience": [],
        }
        motivations, experiences = build_evidence_from_profile(profile)
        self.assertEqual(len(motivations), 1)
        self.assertEqual(motivations[0].category, "career_goal")

    def test_extracts_motivation_reason(self):
        profile = {
            "motivation": "I enjoy solving complex problems.",
            "recent_experience": [],
        }
        motivations, experiences = build_evidence_from_profile(profile)
        self.assertEqual(len(motivations), 1)
        self.assertEqual(motivations[0].category, "personal_motivation")

    def test_falls_back_to_summary_for_motivation(self):
        profile = {
            "summary": "Experienced analyst with a passion for insights.",
            "recent_experience": [],
        }
        motivations, experiences = build_evidence_from_profile(profile)
        self.assertEqual(len(motivations), 1)
        self.assertEqual(motivations[0].confidence, "low")

    def test_builds_experiences_from_profile(self):
        profile = {
            "recent_experience": [
                {
                    "title": "Data Analyst", "company": "ACME Corp",
                    "period": "2020-2023",
                    "bullets": ["Built dashboards", "Automated reporting"],
                },
                {
                    "role": "Junior Analyst", "company": "Startup Inc",
                    "period": "2018-2020",
                    "bullets": ["Cleaned datasets"],
                },
            ],
        }
        motivations, experiences = build_evidence_from_profile(profile)
        self.assertEqual(len(experiences), 2)
        self.assertEqual(experiences[0].role_title, "Data Analyst")
        self.assertEqual(experiences[1].role_title, "Junior Analyst")

    def test_limits_bullets_to_4(self):
        profile = {
            "recent_experience": [
                {
                    "title": "Manager", "company": "BigCo",
                    "period": "2023-now",
                    "bullets": ["a", "b", "c", "d", "e", "f"],
                },
            ],
        }
        motivations, experiences = build_evidence_from_profile(profile)
        self.assertEqual(len(experiences[0].key_bullets), 4)

    def test_empty_profile_returns_empty_lists(self):
        motivations, experiences = build_evidence_from_profile({})
        self.assertEqual(len(motivations), 0)
        self.assertEqual(len(experiences), 0)


class MotivationLetterResultTests(unittest.TestCase):

    def test_to_dict_includes_all_fields(self):
        result = MotivationLetterResult(
            job_id="job_123", candidate_name="Alice",
            letter_text="Dear Hiring Team...",
            sections=[
                MotivationLetterSection(
                    heading="Why This Role",
                    body="I am excited about this role.",
                    evidence_refs=["m1", "e1"],
                ),
            ],
            motivation_evidence_count=2,
            experience_evidence_count=3,
            evidence_insufficient=False,
        )
        d = result.to_dict()
        self.assertEqual(d["job_id"], "job_123")
        self.assertEqual(len(d["sections"]), 1)
        self.assertEqual(d["sections"][0]["evidence_refs"], ["m1", "e1"])

    def test_evidence_insufficient_flag_and_warning(self):
        result = MotivationLetterResult(
            job_id="j1", candidate_name="Bob", letter_text="...",
            evidence_insufficient=True,
            insufficient_warning="Not enough motivation evidence.",
        )
        d = result.to_dict()
        self.assertTrue(d["evidence_insufficient"])
        self.assertEqual(d["insufficient_warning"], "Not enough motivation evidence.")


class GenerateMotivationLetterForJobTests(unittest.TestCase):

    def test_missing_api_key_returns_insufficient_result(self):
        job = {
            "job_id": "test_123", "title": "Test Role",
            "company": "Test Corp",
            "full_description": "A test job description.",
        }
        result = generate_motivation_letter_for_job(
            deepseek_api_key="", deepseek_model="deepseek-chat",
            job=job, cv_text="Test CV text.",
            candidate_name="Test Candidate",
        )
        self.assertIsInstance(result, MotivationLetterResult)
        self.assertEqual(result.job_id, "test_123")
        self.assertTrue(result.evidence_insufficient)


class MotivationLetterInputTests(unittest.TestCase):

    def test_default_values(self):
        input_data = MotivationLetterInput(
            candidate_name="Alice", job_title="Engineer",
            job_company="Acme", job_description_text="Build things.",
            cv_text="My CV.",
        )
        self.assertEqual(input_data.verified_motivations, [])
        self.assertEqual(input_data.verified_experiences, [])
        self.assertEqual(input_data.output_language, "English")


class MotivationLetterSectionTests(unittest.TestCase):

    def test_to_dict_serializes_correctly(self):
        section = MotivationLetterSection(
            heading="Why This Role", body="I am passionate.",
            evidence_refs=["ev_m1", "ev_e1"],
        )
        d = section.to_dict()
        self.assertEqual(d["heading"], "Why This Role")
        self.assertEqual(d["evidence_refs"], ["ev_m1", "ev_e1"])


if __name__ == "__main__":
    unittest.main()
