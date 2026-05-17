import unittest

from backend.capabilities.networking import (
    build_relevant_people_discovery,
    build_target_contact_discovery,
    find_referral_contacts_for_company,
    merge_referral_contacts,
    parse_referral_contacts_csv,
)
from backend.capabilities.networking.outreach import company_names_safely_match
from backend.domain.models import JobRecord, ReferralContactRecord


class ReferralNetworkingTests(unittest.TestCase):
    def test_linkedin_csv_import_scans_to_real_header_and_skips_empty_rows(self):
        contacts = parse_referral_contacts_csv(
            "\n".join(
                [
                    "LinkedIn export",
                    "Downloaded by user",
                    "",
                    "First Name,Last Name,URL,Email Address,Company,Position,Connected On",
                    "",
                    'Sarah,"Muller, PhD",https://linkedin.com/in/sarah,,Stripe Inc.,Senior Engineer,15 Jan 2024',
                    ",,,,,,",
                    "Jonas,Weber,https://linkedin.com/in/jonas,,Google LLC,Product Manager,02 Mar 2023",
                    "",
                ]
            ),
            import_batch_id="import_1",
        )

        self.assertEqual(len(contacts), 2)
        self.assertEqual(contacts[0].name, "Sarah Muller, PhD")
        self.assertEqual(contacts[0].linkedin_url, "https://linkedin.com/in/sarah")
        self.assertEqual(contacts[0].companies[0]["company_name"], "Stripe Inc.")
        self.assertEqual(contacts[0].companies[0]["role_title"], "Senior Engineer")
        self.assertIn("connected on", contacts[0].metadata["import_source_row"])
        self.assertEqual(contacts[0].metadata["source_order"], 1)

    def test_linkedin_csv_import_ignores_multiline_linkedin_notes_before_header(self):
        contacts = parse_referral_contacts_csv(
            "\n".join(
                [
                    "Notes:,,,,,,",
                    '"When exporting your connection data, you may notice that',
                    "some of the email addresses are missing. You will only see email",
                    "addresses for connections who have allowed their connections",
                    "to see or download their email address using this setting",
                    "https://www.linkedin.com/psettings/privacy/email. You can",
                    'learn more here",,,,,,',
                    "",
                    "First Name,Last Name,URL,Email Address,Company,Position,Connected On",
                    "Amal,Khan,https://linkedin.com/in/amal,,Stripe Payments Europe,Finance Lead,29-Mar-21",
                    "Jonas,Weber,https://linkedin.com/in/jonas,,Google LLC,Product Manager,02-Mar-23",
                ]
            ),
            import_batch_id="import_notes",
        )

        self.assertEqual(len(contacts), 2)
        self.assertEqual(contacts[0].name, "Amal Khan")
        self.assertEqual(contacts[0].company, "Stripe Payments Europe")
        self.assertEqual(contacts[1].name, "Jonas Weber")

    def test_linkedin_csv_import_does_not_match_header_text_inside_quoted_notes(self):
        contacts = parse_referral_contacts_csv(
            "\n".join(
                [
                    "Notes:,,,,,,",
                    '"Ignore the example below because it is still part of the note:',
                    "First Name,Last Name,URL,Email Address,Company,Position,Connected On",
                    'End of example.",,,,,,',
                    "",
                    "First Name,Last Name,URL,Email Address,Company,Position,Connected On",
                    "Marvin,Jakwerth,https://www.linkedin.com/in/marvin-jakwerth,,Allianz Services,Senior Engagement Manager,13-Feb-26",
                    "Laura Marcela,Aristizabal,https://www.linkedin.com/in/laura-marcela,,AB InBev,Manager,02-Jan-25",
                ]
            ),
            import_batch_id="import_header_in_note",
        )

        self.assertEqual(len(contacts), 2)
        self.assertEqual(contacts[0].name, "Marvin Jakwerth")
        self.assertEqual(contacts[1].company, "AB InBev")

    def test_linkedin_csv_import_accepts_split_header_rows(self):
        contacts = parse_referral_contacts_csv(
            "\n".join(
                [
                    "Notes:,,,,,,",
                    '"LinkedIn export note",,,,,,',
                    "",
                    "First Name,Last Name,URL,Email",
                    "Address,Company,Position,Connected On",
                    "Marvin,Jakwerth,https://www.linkedin.com/in/marvin-jakwerth,,Allianz Services,Senior Engagement Manager,13-Feb-26",
                    "Laura Marcela,Aristizabal,https://www.linkedin.com/in/laura-marcela,,AB InBev,Manager,02-Jan-25",
                ]
            ),
            import_batch_id="import_split_header",
        )

        self.assertEqual(len(contacts), 2)
        self.assertEqual(contacts[0].name, "Marvin Jakwerth")
        self.assertEqual(contacts[0].company, "Allianz Services")
        self.assertEqual(contacts[1].name, "Laura Marcela Aristizabal")

    def test_linkedin_csv_import_has_no_connection_cap_and_preserves_upload_order(self):
        rows = [
            "First Name,Last Name,URL,Email Address,Company,Position,Connected On",
            *[
                f"First{i},Last{i},https://linkedin.com/in/person-{i},,Company {i},Role {i},01-Jan-24"
                for i in range(1705)
            ],
        ]

        contacts = parse_referral_contacts_csv("\n".join(rows), import_batch_id="import_large")

        self.assertEqual(len(contacts), 1705)
        self.assertEqual(contacts[0].name, "First0 Last0")
        self.assertEqual(contacts[999].name, "First999 Last999")
        self.assertEqual(contacts[-1].name, "First1704 Last1704")
        self.assertEqual(contacts[-1].metadata["source_order"], 1705)

    def test_reupload_marks_missing_linkedin_contacts_inactive(self):
        existing = parse_referral_contacts_csv(
            "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
            "Jane,Referrer,https://linkedin.com/in/jane,,ACME,Manager,01 Jan 2024\n"
            "Sam,Old,https://linkedin.com/in/sam,,Beta,Lead,02 Jan 2024\n",
            import_batch_id="import_old",
        )
        incoming = parse_referral_contacts_csv(
            "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
            "Jane,Referrer,https://linkedin.com/in/jane,,ACME GmbH,Director,03 Jan 2024\n",
            import_batch_id="import_new",
        )

        merged, summary = merge_referral_contacts(existing, incoming)

        self.assertEqual(summary["updated"], 1)
        self.assertEqual(summary["deactivated"], 1)
        by_name = {contact.name: contact for contact in merged}
        self.assertTrue(by_name["Jane Referrer"].is_active)
        self.assertFalse(by_name["Sam Old"].is_active)
        self.assertEqual(by_name["Sam Old"].inactive_reason, "missing_from_latest_linkedin_upload")

    def test_reupload_orders_linkedin_contacts_by_latest_upload_file(self):
        existing = parse_referral_contacts_csv(
            "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
            "Alpha,One,https://linkedin.com/in/alpha,,ACME,Manager,01 Jan 2024\n"
            "Beta,Two,https://linkedin.com/in/beta,,Beta,Lead,02 Jan 2024\n",
            import_batch_id="import_old",
        )
        incoming = parse_referral_contacts_csv(
            "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
            "Beta,Two,https://linkedin.com/in/beta,,Beta,Lead,02 Jan 2024\n"
            "Alpha,One,https://linkedin.com/in/alpha,,ACME,Manager,01 Jan 2024\n",
            import_batch_id="import_new",
        )

        merged, _ = merge_referral_contacts(existing, incoming)

        self.assertEqual([contact.name for contact in merged], ["Beta Two", "Alpha One"])

    def test_linkedin_csv_import_rejects_non_linkedin_table_headers(self):
        with self.assertRaisesRegex(ValueError, "Expected header row"):
            parse_referral_contacts_csv(
                "First Name,Last Name,URL,Company,Position\n"
                "Jane,Referrer,https://linkedin.com/in/jane,ACME,Manager\n",
                import_batch_id="import_bad",
            )

    def test_safe_company_matching_avoids_short_substring_false_positive(self):
        self.assertTrue(company_names_safely_match("Stripe", "Stripe Inc."))
        self.assertTrue(company_names_safely_match("Stripe", "Stripe Payments Europe"))
        self.assertFalse(company_names_safely_match("Meta", "Metabolic Health GmbH"))

    def test_referral_matching_returns_all_active_contacts_only(self):
        active_one = ReferralContactRecord.create(name="One", company="Stripe Inc.")
        active_two = ReferralContactRecord.create(name="Two", company="Stripe Payments Europe")
        inactive = ReferralContactRecord.create(name="Inactive", company="Stripe", is_active=False)

        matches = find_referral_contacts_for_company([active_one, inactive, active_two], "Stripe")

        self.assertEqual([contact.name for contact in matches], ["One", "Two"])

    def test_target_contact_discovery_builds_ranked_search_candidates(self):
        def fake_ai_provider(task, prompt, system_prompt):
            self.assertTrue(prompt)
            self.assertTrue(system_prompt)
            if task == "pass_one_queries":
                return {
                    "summary": "Broad first pass across manager, recruiting, and peer lanes.",
                    "query_plans": [
                        {
                            "query": 'site:linkedin.com/in "ACME GmbH" "Analytics Manager" "Berlin"',
                            "objective": "Find the likely manager in Berlin.",
                            "lane": "direct_hiring_chain",
                            "title_variants": ["Analytics Manager", "Data Science Manager"],
                            "rationale": "Start with the local analytics manager lane.",
                        },
                        {
                            "query": 'site:linkedin.com/in "ACME GmbH" "Talent Acquisition Partner" "Berlin"',
                            "objective": "Find recruiting ownership in Berlin.",
                            "lane": "recruiting",
                            "title_variants": ["Talent Acquisition Partner", "Data Recruiter"],
                            "rationale": "Search the recruiting lane early.",
                        },
                    ],
                }
            if task == "pass_two_queries":
                return {
                    "summary": "Second pass narrows to the Berlin analytics subgroup.",
                    "query_plans": [
                        {
                            "query": 'site:linkedin.com/in "ACME GmbH" "Analytics Manager" "Berlin" "DACH"',
                            "objective": "Narrow the manager lane to the Berlin DACH subgroup.",
                            "lane": "direct_hiring_chain",
                            "title_variants": ["Analytics Manager", "Data Science Manager"],
                            "rationale": "Pass 1 surfaced DACH and Berlin, so pass 2 keeps both.",
                        },
                        {
                            "query": 'site:linkedin.com/in "ACME GmbH" "Talent Acquisition Partner" "Berlin" analytics',
                            "objective": "Narrow the recruiting lane to analytics hiring in Berlin.",
                            "lane": "recruiting",
                            "title_variants": ["Talent Acquisition Partner", "Data Recruiter"],
                            "rationale": "Pass 1 showed the analytics lane clearly.",
                        },
                    ],
                }
            if task == "candidate_resolution":
                return {
                    "summary": "Resolved manager and recruiter candidates from the public evidence.",
                    "candidates": [
                        {
                            "role_label": "Likely Hiring Manager",
                            "person_name": "Jane Hiringmanager",
                            "current_title": "Analytics Manager",
                            "current_company": "ACME GmbH",
                            "location": "Berlin, Germany",
                            "seniority": "manager",
                            "lane": "direct_hiring_chain",
                            "confidence": "high",
                            "fit_score": 96,
                            "title_variants": ["Analytics Manager", "Data Science Manager"],
                            "why_this_person": "Search results converge on a Berlin analytics manager at the same company.",
                            "access_hint": "Closest lane to direct role ownership.",
                            "evidence": [
                                "Public profile snippet places Jane Hiringmanager in Berlin on the analytics team.",
                            ],
                            "source_urls": [
                                "https://www.linkedin.com/in/jane-hiringmanager",
                            ],
                            "source_titles": [
                                "Jane Hiringmanager - Analytics Manager - ACME GmbH | LinkedIn",
                            ],
                            "search_query": 'Jane Hiringmanager ACME GmbH Analytics Manager Berlin',
                            "follow_up_ask": "If you are open to it, I would value a quick perspective on the team priorities.",
                        },
                        {
                            "role_label": "Recruiter Or Talent Partner",
                            "person_name": "Mina Talent",
                            "current_title": "Talent Acquisition Partner",
                            "current_company": "ACME GmbH",
                            "location": "Berlin, Germany",
                            "seniority": "individual_contributor",
                            "lane": "recruiting",
                            "confidence": "medium",
                            "fit_score": 84,
                            "title_variants": ["Talent Acquisition Partner", "Data Recruiter"],
                            "why_this_person": "Public snippets tie Mina Talent to ACME hiring in Berlin.",
                            "access_hint": "Best lane for routing and recruiter-side visibility.",
                            "evidence": [
                                "Public profile snippet connects Mina Talent to Berlin recruiting at ACME GmbH.",
                            ],
                            "source_urls": [
                                "https://www.linkedin.com/in/mina-talent",
                            ],
                            "source_titles": [
                                "Mina Talent - Talent Acquisition Partner - ACME GmbH | LinkedIn",
                            ],
                            "search_query": 'Mina Talent ACME GmbH Talent Acquisition Partner Berlin',
                            "follow_up_ask": "If you are open to it, I would appreciate any advice on the best next step.",
                        },
                    ],
                }
            raise AssertionError(f"Unexpected AI task: {task}")

        def fake_search_provider(query, max_results=5, pass_index=1, lane="", objective=""):
            self.assertTrue(query)
            if "Jane Hiringmanager" in query or ("Analytics Manager" in query and "DACH" in query):
                return [
                    {
                        "title": "Jane Hiringmanager - Analytics Manager - ACME GmbH | LinkedIn",
                        "url": "https://www.linkedin.com/in/jane-hiringmanager",
                        "snippet": "Analytics Manager for ACME GmbH in Berlin, focused on DACH reporting.",
                    },
                    {
                        "title": "ACME analytics leadership in Berlin",
                        "url": "https://www.acme.example/teams/analytics-berlin",
                        "snippet": "Meet the Berlin analytics leadership team supporting DACH operations.",
                    },
                ][:max_results]
            if "Talent Acquisition Partner" in query:
                return [
                    {
                        "title": "Mina Talent - Talent Acquisition Partner - ACME GmbH | LinkedIn",
                        "url": "https://www.linkedin.com/in/mina-talent",
                        "snippet": "Talent Acquisition Partner at ACME GmbH in Berlin hiring across analytics roles.",
                    },
                ][:max_results]
            return [
                {
                    "title": "ACME analytics careers Berlin",
                    "url": "https://www.acme.example/careers/analytics-berlin",
                    "snippet": "Berlin analytics hiring and reporting team overview.",
                },
            ][:max_results]

        payload = build_target_contact_discovery(
            profile={
                "name": "Analyst User",
                "summary": "Analytics specialist who improves dashboards and reporting workflows.",
            },
            job=JobRecord(
                job_id="job_1",
                title="Senior Data Analyst",
                company="ACME GmbH",
                location_raw="Berlin, Germany",
                description_text="Reporting to Jane Hiringmanager on the analytics team.",
            ),
            search_provider=fake_search_provider,
            ai_provider=fake_ai_provider,
        )

        self.assertEqual(payload["discipline"], "data")
        self.assertEqual(payload["department_label"], "Data")
        self.assertGreaterEqual(len(payload["candidates"]), 4)
        self.assertEqual(payload["default_pass_count"], 2)
        self.assertEqual(len(payload["passes"]), 2)
        self.assertEqual(payload["provider"]["query_planner"], "ai")
        self.assertEqual(payload["provider"]["resolver"], "ai")
        self.assertEqual(payload["passes"][1]["pass_index"], 2)
        self.assertGreaterEqual(payload["passes"][1]["query_count"], 1)
        self.assertEqual(payload["candidates"][0]["role_label"], "Likely Hiring Manager")
        self.assertEqual(payload["candidates"][0]["resolved_name"], "Jane Hiringmanager")
        self.assertEqual(payload["candidates"][0]["resolved_in_pass"], 2)
        self.assertTrue(payload["candidates"][0]["evidence"])
        self.assertIn("linkedin.com/search/results/people", payload["candidates"][0]["linkedin_search_url"])
        self.assertIn("site:linkedin.com/in", payload["candidates"][0]["google_xray_query"])
        self.assertIn("[Name]", payload["candidates"][0]["connection_note"])

    def test_relevant_people_discovery_builds_workspace_ready_people_context(self):
        def fake_ai_provider(task, prompt, system_prompt):
            self.assertTrue(prompt)
            self.assertTrue(system_prompt)
            if task == "pass_one_queries":
                return {
                    "summary": "Broad first pass across manager, peer, and leadership lanes.",
                    "query_plans": [
                        {
                            "query": 'site:linkedin.com/in "ACME GmbH" "Analytics Manager" "Berlin"',
                            "objective": "Find the likely hiring manager in Berlin.",
                            "lane": "direct_hiring_chain",
                            "title_variants": ["Analytics Manager"],
                            "rationale": "Start with the direct manager lane.",
                        },
                        {
                            "query": 'site:linkedin.com/in "ACME GmbH" "Senior Data Analyst" "Berlin"',
                            "objective": "Find likely peers on the same team.",
                            "lane": "peer_context",
                            "title_variants": ["Senior Data Analyst"],
                            "rationale": "Search for team-level peers in the same discipline.",
                        },
                        {
                            "query": 'site:linkedin.com/in "ACME GmbH" "VP Analytics" "Germany"',
                            "objective": "Find nearby leadership for the function.",
                            "lane": "leadership",
                            "title_variants": ["VP Analytics"],
                            "rationale": "Search the closest leadership lane.",
                        },
                    ],
                }
            if task == "pass_two_queries":
                return {
                    "summary": "Second pass narrows to Berlin analytics leadership and team context.",
                    "query_plans": [
                        {
                            "query": 'site:linkedin.com/in "ACME GmbH" "Analytics Manager" "Berlin" "DACH"',
                            "objective": "Narrow the likely manager lane with the regional signal.",
                            "lane": "direct_hiring_chain",
                            "title_variants": ["Analytics Manager"],
                            "rationale": "Refine the manager lane with the DACH signal.",
                        },
                        {
                            "query": 'site:linkedin.com/in "ACME GmbH" "Senior Data Analyst" "Berlin" analytics',
                            "objective": "Refine the team-level peer lane.",
                            "lane": "peer_context",
                            "title_variants": ["Senior Data Analyst"],
                            "rationale": "Tighten team-level peer matching.",
                        },
                    ],
                }
            if task == "candidate_resolution":
                return {
                    "summary": "Resolved manager, peer, and executive candidates from public evidence.",
                    "candidates": [
                        {
                            "role_label": "Likely Hiring Manager",
                            "person_name": "Jane Hiringmanager",
                            "current_title": "Analytics Manager",
                            "current_company": "ACME GmbH",
                            "location": "Berlin, Germany",
                            "seniority": "manager",
                            "lane": "direct_hiring_chain",
                            "confidence": "high",
                            "fit_score": 96,
                            "title_variants": ["Analytics Manager"],
                            "why_this_person": "Public results converge on a Berlin analytics manager at the same company.",
                            "access_hint": "Closest lane to direct role ownership.",
                            "evidence": [
                                "Public profile snippet places Jane Hiringmanager in Berlin on the analytics team.",
                            ],
                            "source_urls": [
                                "https://www.linkedin.com/in/jane-hiringmanager",
                            ],
                            "source_titles": [
                                "Jane Hiringmanager - Analytics Manager - ACME GmbH | LinkedIn",
                            ],
                            "search_query": "Jane Hiringmanager ACME GmbH Analytics Manager Berlin",
                        },
                        {
                            "role_label": "Potential Colleague",
                            "person_name": "Leo Peer",
                            "current_title": "Senior Data Analyst",
                            "current_company": "ACME GmbH",
                            "location": "Berlin, Germany",
                            "seniority": "individual_contributor",
                            "lane": "peer_context",
                            "confidence": "medium",
                            "fit_score": 82,
                            "title_variants": ["Senior Data Analyst"],
                            "why_this_person": "Public snippets connect Leo Peer to the same analytics function in Berlin.",
                            "access_hint": "Likely same-team or adjacent-team context.",
                            "evidence": [
                                "Public profile snippet ties Leo Peer to analytics reporting in Berlin.",
                            ],
                            "source_urls": [
                                "https://www.linkedin.com/in/leo-peer",
                            ],
                            "source_titles": [
                                "Leo Peer - Senior Data Analyst - ACME GmbH | LinkedIn",
                            ],
                            "search_query": "Leo Peer ACME GmbH Senior Data Analyst Berlin",
                        },
                        {
                            "role_label": "Executive Sponsor",
                            "person_name": "Ava Leader",
                            "current_title": "VP Analytics Europe",
                            "current_company": "ACME GmbH",
                            "location": "Berlin, Germany",
                            "seniority": "executive",
                            "lane": "leadership",
                            "confidence": "medium",
                            "fit_score": 77,
                            "title_variants": ["VP Analytics Europe"],
                            "why_this_person": "Public results connect Ava Leader to the analytics function in Europe.",
                            "access_hint": "Broader leadership visibility.",
                            "evidence": [
                                "Public profile snippet connects Ava Leader to European analytics leadership at ACME GmbH.",
                            ],
                            "source_urls": [
                                "https://www.linkedin.com/in/ava-leader",
                            ],
                            "source_titles": [
                                "Ava Leader - VP Analytics Europe - ACME GmbH | LinkedIn",
                            ],
                            "search_query": "Ava Leader ACME GmbH VP Analytics Europe",
                        },
                    ],
                }
            raise AssertionError(f"Unexpected AI task: {task}")

        def fake_search_provider(query, max_results=5, pass_index=1, lane="", objective=""):
            self.assertTrue(query)
            lane_results = {
                "direct_hiring_chain": [
                    {
                        "title": "Jane Hiringmanager - Analytics Manager - ACME GmbH | LinkedIn",
                        "url": "https://www.linkedin.com/in/jane-hiringmanager",
                        "snippet": "Analytics Manager for ACME GmbH in Berlin, focused on DACH reporting.",
                    }
                ],
                "peer_context": [
                    {
                        "title": "Leo Peer - Senior Data Analyst - ACME GmbH | LinkedIn",
                        "url": "https://www.linkedin.com/in/leo-peer",
                        "snippet": "Senior Data Analyst at ACME GmbH in Berlin supporting analytics reporting.",
                    }
                ],
                "leadership": [
                    {
                        "title": "Ava Leader - VP Analytics Europe - ACME GmbH | LinkedIn",
                        "url": "https://www.linkedin.com/in/ava-leader",
                        "snippet": "VP Analytics Europe at ACME GmbH with regional leadership scope.",
                    }
                ],
            }
            return lane_results.get(lane, [])[:max_results]

        payload = build_relevant_people_discovery(
            profile={
                "name": "Analyst User",
                "summary": "Analytics specialist who improves dashboards and reporting workflows.",
            },
            job=JobRecord(
                job_id="job_1",
                title="Senior Data Analyst",
                company="ACME GmbH",
                location_raw="Berlin, Germany",
                description_text="Reporting to Jane Hiringmanager on the analytics team.",
            ),
            run_id="run_1",
            workspace_id="workspace_1",
            search_provider=fake_search_provider,
            ai_provider=fake_ai_provider,
        )

        self.assertEqual(payload["peopleDiscoveryStatus"], "completed")
        self.assertEqual(payload["runId"], "run_1")
        self.assertEqual(payload["workspaceId"], "workspace_1")
        self.assertEqual(payload["jobId"], "job_1")
        self.assertEqual(payload["contextExtraction"]["department"], "Data")
        self.assertGreaterEqual(len(payload["searchHypotheses"]), 3)
        self.assertEqual(payload["selectedPeople"], [])
        self.assertEqual(len(payload["categories"]["hiring_manager"]), 1)
        self.assertEqual(len(payload["categories"]["potential_colleague"]), 1)
        self.assertEqual(len(payload["categories"]["executive"]), 1)

        hiring_manager = payload["categories"]["hiring_manager"][0]
        self.assertEqual(hiring_manager["name"], "Jane Hiringmanager")
        self.assertEqual(hiring_manager["title"], "Analytics Manager")
        self.assertEqual(hiring_manager["company"], "ACME GmbH")
        self.assertEqual(hiring_manager["source"], "public_profile_search")
        self.assertGreaterEqual(hiring_manager["confidence"], 55)
        self.assertIn("Likely relevant because", hiring_manager["reasoningNote"])
        self.assertEqual(
            hiring_manager["profileUrl"],
            "https://www.linkedin.com/in/jane-hiringmanager",
        )
        self.assertIn("Jane Hiringmanager ACME GmbH Analytics Manager Berlin", hiring_manager["searchQueries"])

    def test_target_contact_discovery_runs_two_pass_fallback_without_ai(self):
        def fake_search_provider(query, max_results=5, pass_index=1, lane="", objective=""):
            return [
                {
                    "title": f"Search result for {lane or 'general'}",
                    "url": f"https://example.com/{pass_index}/{lane or 'general'}",
                    "snippet": f"{query} for Berlin operations at Example GmbH.",
                }
            ][:max_results]

        def failing_ai_provider(task, prompt, system_prompt):
            raise RuntimeError("intentional test fallback")

        payload = build_target_contact_discovery(
            profile={"summary": "Operations specialist focused on process improvement."},
            job=JobRecord(
                job_id="job_2",
                title="Operations Manager",
                company="Example GmbH",
                location_raw="Berlin, Germany",
                description_text="Operations leadership role for the Berlin site.",
            ),
            search_provider=fake_search_provider,
            ai_provider=failing_ai_provider,
        )

        self.assertEqual(payload["default_pass_count"], 2)
        self.assertEqual(len(payload["passes"]), 2)
        self.assertEqual(payload["provider"]["query_planner"], "heuristic_fallback")
        self.assertGreaterEqual(payload["passes"][0]["query_count"], 1)
        self.assertGreaterEqual(payload["passes"][1]["query_count"], 1)
        self.assertGreaterEqual(len(payload["candidates"]), 1)


if __name__ == "__main__":
    unittest.main()
