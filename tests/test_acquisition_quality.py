from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend import create_backend
from backend.acquisition.quality import (
    DIRECT_APPLICATION_CLASSIFICATIONS,
    URL_ATS_APPLICATION,
    URL_ATS_JOB_DETAIL,
    URL_CAREERS_INDEX,
    URL_EMPLOYER_APPLICATION,
    URL_EMPLOYER_JOB_DETAIL,
    URL_SEARCH_RESULTS,
    classify_job_url,
    completeness_rules,
    extract_application_candidates_from_html,
    normalize_description,
    normalize_job_for_ingestion,
    normalize_source_timestamps,
    resolve_application_destination,
    source_employer_name,
    stable_content_payload,
)
from backend.acquisition.repair import repair_acquisition_catalog
from backend.application.personalized_jobs_intelligence import _deterministic_description


class AcquisitionQualityTests(unittest.TestCase):
    def setUp(self):
        self.target = {
            "connector": "greenhouse",
            "canonical_company_name": "N26",
            "canonical_target_url": "https://boards.greenhouse.io/n26",
            "official_employer_hosts": ["n26.com"],
            "source_token": "n26",
        }

    def test_source_branding_is_not_canonical_employer_identity(self):
        self.assertEqual(source_employer_name("N26 Greenhouse"), "N26")
        normalized = normalize_job_for_ingestion({
            "id": "j1",
            "title": "Engineer",
            "company": "N26 Greenhouse",
            "url": "https://boards.greenhouse.io/n26/jobs/j1",
            "description": "<p>Build systems</p>",
        }, self.target)
        self.assertEqual(normalized["company"], "N26")
        self.assertIn("source_labeled_employer_name_normalized", normalized["quality_warnings"])

    def test_url_taxonomy_distinguishes_direct_apply_detail_and_listings(self):
        self.assertEqual(classify_job_url("https://n26.com/careers/apply/123", target=self.target), URL_EMPLOYER_APPLICATION)
        self.assertEqual(classify_job_url("https://boards.greenhouse.io/n26/jobs/123/apply", target=self.target), URL_ATS_APPLICATION)
        self.assertEqual(classify_job_url("https://boards.greenhouse.io/n26/jobs/123", target=self.target), URL_ATS_JOB_DETAIL)
        self.assertEqual(classify_job_url("https://n26.com/careers", target=self.target), URL_CAREERS_INDEX)
        self.assertEqual(classify_job_url("https://n26.com/search?q=engineer", target=self.target), URL_SEARCH_RESULTS)
        self.assertTrue(DIRECT_APPLICATION_CLASSIFICATIONS == {URL_EMPLOYER_APPLICATION, URL_ATS_APPLICATION})

    def test_detail_only_route_is_truthfully_unresolved(self):
        destination = resolve_application_destination({
            "job_detail_url": "https://boards.greenhouse.io/n26/jobs/123",
            "apply_link": "https://boards.greenhouse.io/n26/jobs/123",
        }, self.target)
        self.assertEqual(destination["status"], "unresolved")
        self.assertEqual(destination["application_method"], "job_detail")
        self.assertFalse(destination["resolved_url"])
        self.assertEqual(destination["user_facing_url"], "https://boards.greenhouse.io/n26/jobs/123")

    def test_html_apply_link_is_recovered_without_promoting_detail_page(self):
        html = """
        <main><h1>Role</h1>
          <a href="/jobs/123">View job</a>
          <form action="https://boards.greenhouse.io/n26/jobs/123/applications" method="post">
            <button type="submit">Apply now</button>
          </form>
        </main>
        """
        candidates = extract_application_candidates_from_html(
            html,
            "https://n26.com/careers/jobs/123",
            target=self.target,
        )
        self.assertEqual(candidates[0]["source_field"], "html_form_action")
        destination = resolve_application_destination({
            "job_detail_url": "https://n26.com/careers/jobs/123",
            "source_page_html": html,
        }, self.target)
        self.assertEqual(destination["status"], "verified")
        self.assertEqual(destination["resolved_url"], "https://boards.greenhouse.io/n26/jobs/123/applications")
        self.assertEqual(destination["classification"], URL_ATS_APPLICATION)
        self.assertNotEqual(destination["job_detail_url"], destination["resolved_url"])

    def test_source_created_or_updated_is_not_posted_without_publication_field(self):
        greenhouse = normalize_source_timestamps({
            "source_ats": "greenhouse",
            "source_raw_payload": {"created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-08-09T00:00:00Z"},
        }, source_ats="greenhouse", provenance_url="https://boards.greenhouse.io/n26/jobs/1")
        self.assertIsNone(greenhouse["fields"]["source_posted_at"]["value"])
        self.assertEqual(greenhouse["timestamp_state"], "unknown_source_timestamp")
        explicit = normalize_source_timestamps({"datePosted": "2026-08-09T00:00:00Z"}, provenance_url="https://n26.com/jobs/1")
        self.assertEqual(explicit["timestamp_state"], "known")
        self.assertIsNotNone(explicit["fields"]["source_posted_at"]["value"])

    def test_relative_posting_age_is_inferred_from_first_observation_time(self):
        result = normalize_source_timestamps(
            {
                "posted_time_text": "1 day ago",
                "observed_at": "2026-08-10T12:00:00Z",
            },
            provenance_url="https://linkedin.com/jobs/view/1",
        )
        self.assertEqual(result["timestamp_state"], "estimated")
        self.assertEqual(result["timestamp_semantics"], "source_posted_age_estimate")
        self.assertEqual(result["fields"]["source_posted_at"]["state"], "inferred")
        self.assertEqual(result["fields"]["source_posted_at"]["value"], "2026-08-09T12:00:00+00:00")

    def test_description_decodes_entities_once_and_preserves_structure(self):
        result = normalize_description("<h2>Role</h2><ul><li>R&amp;D</li></ul><script>alert(1)</script><p>&amp;amp;</p>")
        self.assertIn("<h2>Role</h2>", result["sanitized_html"])
        self.assertIn("<ul>", result["sanitized_html"])
        self.assertNotIn("script", result["sanitized_html"])
        self.assertIn("R&D", result["plain_text"])
        self.assertIn("&amp;", result["sanitized_html"])
        self.assertEqual(result["decoding"], "html_entities_decoded_once")

    def test_stable_content_excludes_volatile_observation_fields(self):
        first = {"title": "Engineer", "description": "Build", "location": "Berlin", "applicant_count": 81, "run_timestamp": "a"}
        second = {**first, "applicant_count": 99, "run_timestamp": "b", "posted_age_hours": 3}
        self.assertEqual(stable_content_payload(first), stable_content_payload(second))

    def test_completeness_is_named_and_report_only(self):
        result = completeness_rules(job={"title": "Engineer"}, company={}, source={}, admin={})
        self.assertEqual(set(result["categories"]), {"job", "company", "source", "admin"})
        self.assertFalse(any(rule["blocking"] for rule in result["all_rules"]))
        self.assertEqual(result["shadow_validation"]["mode"], "report_only")

    def test_intelligence_exposes_field_provenance_and_missing_state(self):
        result = _deterministic_description({
            "description": "Responsibilities\n- Build APIs\n\nRequirements\n- Python",
            "source_observation_id": "observation-1",
            "observation_original_url": "https://n26.com/jobs/1",
            "observation_observed_at": "2026-08-10T10:00:00+00:00",
        })
        states = result["structured_description"]["extraction"]
        self.assertEqual(states["responsibilities"]["state"], "present")
        self.assertEqual(states["salary"]["state"], "missing")
        self.assertEqual(states["responsibilities"]["provenance"], "posting_text")
        self.assertEqual(states["responsibilities"]["source_observation_id"], "observation-1")
        self.assertEqual(states["responsibilities"]["source_url"], "https://n26.com/jobs/1")

    def test_repair_empty_catalog_is_dry_run_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            application = create_backend(Path(directory), storage_backend="sqlite", test_mode=True)
            store = application.repositories.acquisition_store
            first = repair_acquisition_catalog(store)
            second = repair_acquisition_catalog(store)
            self.assertEqual(first["mode"], "dry_run")
            self.assertTrue(first["idempotent"])
            self.assertEqual(first["counts"], second["counts"])


if __name__ == "__main__":
    unittest.main()
