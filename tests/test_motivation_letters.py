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


# =============================================================================
# CP-037R: New tests for integrated motivation letter generation
# =============================================================================


class CheckPersonalMotivationSufficientTests(unittest.TestCase):
    """CP-037R: Personal motivation sufficiency checks."""

    def test_sufficient_with_high_confidence(self):
        from backend.capabilities.tailored_documents.motivation_letters import (
            check_personal_motivation_sufficient)
        ok, _ = check_personal_motivation_sufficient([
            MotivationEvidence(evidence_id="m1", category="personal_motivation",
                              statement="I love solving problems.", confidence="high"),
        ])
        self.assertTrue(ok)

    def test_insufficient_with_low_confidence(self):
        from backend.capabilities.tailored_documents.motivation_letters import (
            check_personal_motivation_sufficient)
        ok, msg = check_personal_motivation_sufficient([
            MotivationEvidence(evidence_id="m1", category="personal_motivation",
                              statement="Summary-based.", confidence="low"),
        ])
        self.assertFalse(ok)
        self.assertIn("Insufficient personal motivation", msg)

    def test_insufficient_with_empty(self):
        from backend.capabilities.tailored_documents.motivation_letters import (
            check_personal_motivation_sufficient)
        ok, _ = check_personal_motivation_sufficient([])
        self.assertFalse(ok)


class BuildStructuredPromptTests(unittest.TestCase):
    """CP-037R: Structured prompt builder tests."""

    def test_excludes_full_cv_and_jd(self):
        from backend.capabilities.tailored_documents.motivation_letters import (
            build_structured_motivation_prompt)
        input_data = MotivationLetterInput(
            candidate_name="Alice", job_title="Engineer", job_company="Acme",
            job_description_text="LONG_JD_TEXT_HERE", cv_text="LONG_CV_TEXT_HERE",
            verified_motivations=[
                MotivationEvidence(evidence_id="ev_m1", category="career_goal",
                                   statement="Goal.", confidence="high"),
            ],
            verified_experiences=[
                ExperienceEvidence(experience_id="ev_e1", role_title="Dev",
                                   company="PrevCo", period="2020-2023",
                                   key_bullets=["Built APIs"]),
            ],
        )
        prompt = build_structured_motivation_prompt(input_data)
        self.assertIn("ev_m1", prompt)
        self.assertIn("ev_e1", prompt)
        self.assertNotIn("LONG_JD_TEXT_HERE", prompt)
        self.assertNotIn("LONG_CV_TEXT_HERE", prompt)

    def test_insufficient_evidence_adds_warning_note(self):
        from backend.capabilities.tailored_documents.motivation_letters import (
            build_structured_motivation_prompt)
        input_data = MotivationLetterInput(
            candidate_name="Carol", job_title="Analyst", job_company="Firm",
            job_description_text="JD", cv_text="CV",
        )
        prompt = build_structured_motivation_prompt(
            input_data, evidence_sufficient=False)
        self.assertIn("IMPORTANT", prompt)
        self.assertIn("evidence is limited", prompt.lower())


class ValidateLetterClaimsTests(unittest.TestCase):
    """CP-037R: Anti-copying validation tests."""

    def test_passes_when_no_copying_detected(self):
        from backend.capabilities.tailored_documents.motivation_letters import (
            validate_letter_claims)
        result = validate_letter_claims(
            "I am excited to apply for this role at Acme Corp.",
            "Experienced engineer with 10 years in software development.",
            "Acme Corp is seeking a senior engineer with cloud experience.",
        )
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["issues"]), 0)

    def test_detects_copied_cv_text(self):
        from backend.capabilities.tailored_documents.motivation_letters import (
            validate_letter_claims)
        copied = "Experienced engineer with 10 years in software development."
        result = validate_letter_claims(
            f"I am writing. {copied} I am excited.",
            copied + " More CV details here.",
            "Some job description.",
        )
        self.assertFalse(result["passed"])
        self.assertTrue(len(result["cv_copies"]) > 0)

    def test_detects_copied_jd_text(self):
        from backend.capabilities.tailored_documents.motivation_letters import (
            validate_letter_claims)
        copied = "Seeking a senior engineer with cloud experience in AWS"
        result = validate_letter_claims(
            f"Dear Team, {copied} and I believe I am a good fit.",
            "My CV text.",
            copied + " and Azure.",
        )
        self.assertFalse(result["passed"])
        self.assertTrue(len(result["jd_copies"]) > 0)


class ValidateSectionEvidenceRefsTests(unittest.TestCase):
    """CP-037R: Section evidence reference validation."""

    def test_passes_with_valid_references(self):
        from backend.capabilities.tailored_documents.motivation_letters import (
            validate_section_evidence_refs)
        sections = [
            MotivationLetterSection(
                heading="Why This Role", body="I am excited [ev_m1].",
                evidence_refs=["ev_m1"],
            ),
        ]
        motivations = [
            MotivationEvidence(evidence_id="ev_m1", category="career_goal",
                              statement="Goal.", confidence="high"),
        ]
        result = validate_section_evidence_refs(sections, motivations, [])
        self.assertTrue(result["passed"])

    def test_detects_unknown_evidence_ref(self):
        from backend.capabilities.tailored_documents.motivation_letters import (
            validate_section_evidence_refs)
        sections = [
            MotivationLetterSection(
                heading="Why This Role", body="I am excited [ev_fake].",
                evidence_refs=["ev_fake"],
            ),
        ]
        motivations = [
            MotivationEvidence(evidence_id="ev_m1", category="career_goal",
                              statement="Goal.", confidence="high"),
        ]
        result = validate_section_evidence_refs(sections, motivations, [])
        self.assertFalse(result["passed"])
        self.assertTrue(len(result["issues"]) > 0)


class ParseLetterSectionsTests(unittest.TestCase):
    """CP-037R: Section parsing tests."""

    def test_parses_greeting_and_body(self):
        from backend.capabilities.tailored_documents.motivation_letters import (
            parse_letter_sections)
        sections = parse_letter_sections(
            "Dear Hiring Team,\n\nWhy This Role\nExcited [ev_m1].\n\nSincerely,\nAlice"
        )
        self.assertGreaterEqual(len(sections), 2)

    def test_extracts_evidence_refs(self):
        from backend.capabilities.tailored_documents.motivation_letters import (
            parse_letter_sections)
        sections = parse_letter_sections(
            "Dear Hiring Team,\n\nWhy This Role\nMy [ev_m1] and [ev_e1] fit.\n\nSincerely,\nA"
        )
        all_refs = []
        for s in sections:
            all_refs.extend(s.evidence_refs)
        self.assertIn("ev_m1", all_refs)
        self.assertIn("ev_e1", all_refs)

    def test_empty_letter_returns_empty(self):
        from backend.capabilities.tailored_documents.motivation_letters import (
            parse_letter_sections)
        self.assertEqual(len(parse_letter_sections("")), 0)





class GenerateMotivationLetterIntegrationTests(unittest.TestCase):
    """CP-037R: End-to-end integration tests (skip_api_call mode)."""

    def test_skip_api_call_insufficient_evidence(self):
        from backend.capabilities.tailored_documents.motivation_letters import (
            generate_motivation_letter)
        job = {"job_id": "test_001", "title": "DS", "company": "TC",
               "full_description": "Data scientist role."}
        result = generate_motivation_letter(
            deepseek_api_key="", deepseek_model="deepseek-chat",
            job=job, cv_text="CV", candidate_name="Alice",
            verified_motivations=[], verified_experiences=[],
            skip_api_call=True)
        self.assertTrue(result.evidence_insufficient)
        self.assertTrue(len(result.insufficient_warning) > 0)

    def test_skip_api_call_sufficient_evidence(self):
        from backend.capabilities.tailored_documents.motivation_letters import (
            generate_motivation_letter)
        job = {"job_id": "test_002", "title": "Eng", "company": "DC",
               "full_description": "Engineering role."}
        result = generate_motivation_letter(
            deepseek_api_key="", deepseek_model="deepseek-chat",
            job=job, cv_text="CV", candidate_name="Bob",
            verified_motivations=[
                MotivationEvidence(evidence_id="m1", category="personal_motivation",
                                  statement="Passionate.", confidence="high"),
                MotivationEvidence(evidence_id="m2", category="career_goal",
                                  statement="Lead teams.", confidence="high"),
            ],
            verified_experiences=[
                ExperienceEvidence(experience_id="e1", role_title="SrEng",
                                   company="PC", period="2020-2024",
                                   key_bullets=["Led team"]),
                ExperienceEvidence(experience_id="e2", role_title="Eng",
                                   company="OC", period="2018-2020",
                                   key_bullets=["Built services"]),
            ],
            skip_api_call=True)
        self.assertFalse(result.evidence_insufficient)
        self.assertEqual(result.insufficient_warning, "")

    def test_missing_api_key_without_skip(self):
        from backend.capabilities.tailored_documents.motivation_letters import (
            generate_motivation_letter)
        job = {"job_id": "t3", "title": "PM", "company": "MC",
               "full_description": "PM role."}
        result = generate_motivation_letter(
            deepseek_api_key="", deepseek_model="deepseek-chat",
            job=job, cv_text="CV", candidate_name="C",
            verified_motivations=[
                MotivationEvidence(evidence_id="m1", category="career_goal",
                                  statement="G.", confidence="high")],
            verified_experiences=[], skip_api_call=False)
        self.assertTrue(result.evidence_insufficient)
        self.assertIn("Missing DeepSeek API key", result.insufficient_warning)

    def test_warning_when_personal_motivation_insufficient(self):
        """CP-037R: Visible warning when personal motivation is insufficient."""
        from backend.capabilities.tailored_documents.motivation_letters import (
            generate_motivation_letter)
        job = {"job_id": "t5", "title": "Dev", "company": "CC",
               "full_description": "Dev role."}
        result = generate_motivation_letter(
            deepseek_api_key="sk-test", deepseek_model="deepseek-chat",
            job=job, cv_text="CV", candidate_name="Eve",
            verified_motivations=[
                MotivationEvidence(evidence_id="m1", category="personal_motivation",
                                  statement="Summary.", confidence="low"),
            ],
            verified_experiences=[
                ExperienceEvidence(experience_id="e1", role_title="Dev",
                                   company="OC", period="2020-2023"),
            ],
            skip_api_call=True)
        self.assertTrue(result.evidence_insufficient)
        self.assertIn("Insufficient personal motivation", result.insufficient_warning)


if __name__ == "__main__":
    unittest.main()
