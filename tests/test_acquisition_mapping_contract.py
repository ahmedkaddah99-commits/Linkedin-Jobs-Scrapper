from __future__ import annotations

import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from backend.acquisition.quality import (
    DIRECT_APPLICATION_CLASSIFICATIONS,
    URL_ATS_APPLICATION,
    URL_ATS_JOB_DETAIL,
    URL_CAREERS_INDEX,
    URL_EMPLOYER_APPLICATION,
    URL_UNKNOWN,
    classify_job_url,
    normalize_job_for_ingestion,
    normalize_source_metadata,
    resolve_application_destination,
)
from backend.acquisition.unified_mapping import (
    APPLICATION_DESTINATIONS,
    EMPLOYMENT_TYPES,
    FUNCTION_TAXONOMY,
    WORKPLACE_ARRANGEMENTS,
    map_job_fields,
)
from backend.capabilities.tailored_documents.manual_urls import (
    extract_generic_location,
    extract_generic_locations,
    extract_jobposting_jsonld,
    fetch_generic_manual_job,
)
from backend.connectors.ats_router import fetch_ats_snapshot


class _ResponseFixture:
    def __init__(self, payload: object, *, url: str, text: str = "") -> None:
        self._payload = payload
        self.url = url
        self.status_code = 200
        self.encoding = "utf-8"
        self.text = text

    def json(self) -> object:
        return self._payload

    def raise_for_status(self) -> None:
        return None


GREENHOUSE_PAYLOAD = {
    "jobs": [
        {
            "id": 101,
            "title": "Backend Engineer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/101",
            "application_url": "https://boards.greenhouse.io/acme/jobs/101/apply",
            "location": {"name": "Berlin"},
            "departments": [{"id": 7, "name": "Engineering"}],
            "offices": [{"id": 8, "name": "Berlin HQ"}],
            "metadata": [{"name": "Requisition ID", "value": "REQ-101"}],
            "first_published_at": "2026-08-09T12:30:00Z",
            "updated_at": "2026-08-10T08:00:00Z",
            "content": "Build reliable APIs.",
        }
    ]
}

LEVER_PAYLOAD = [
    {
        "id": "lever-202",
        "text": "Data Analyst",
        "hostedUrl": "https://jobs.lever.co/acme/lever-202",
        "applyUrl": "https://jobs.lever.co/acme/lever-202/apply",
        "categories": {
            "location": "Munich",
            "department": "Data",
            "team": "Analytics",
            "commitment": "Full-time",
        },
        "workplaceType": "hybrid",
        "salaryRange": {"min": 70000, "max": 90000, "currency": "EUR"},
        "customFields": {"language": "German"},
        "createdAt": 1786348800000,
        "updatedAt": "2026-08-10T09:00:00Z",
        "descriptionPlain": "Explore product data.",
    }
]

JSON_LD_PAGE = """
<!doctype html>
<html>
  <head>
    <link rel="canonical" href="https://careers.acme.example/jobs/backend-engineer">
    <meta property="og:site_name" content="Acme Example">
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@graph": [{
          "@type": "Organization",
          "name": "Acme Example"
        }, {
          "@type": "JobPosting",
          "title": "Backend Engineer",
          "datePosted": "2026-08-08T10:15:00Z",
          "hiringOrganization": {"@type": "Organization", "name": "Acme Example"},
          "jobLocation": [
            {"@type": "Place", "address": {"addressLocality": "Berlin", "addressRegion": "BE", "addressCountry": "DE"}},
            {"@type": "Place", "address": {"addressLocality": "Munich", "addressRegion": "BY", "addressCountry": "DE"}}
          ],
          "description": "<p>Build and operate resilient services for customers.</p>"
        }]
      }
    </script>
  </head>
  <body>
    <form action="/jobs/backend-engineer/apply" method="post"><button>Apply now</button></form>
  </body>
</html>
"""

GENERIC_HTML_PAGE = """
<html>
  <head>
    <meta property="og:title" content="Operations Specialist">
    <meta property="og:site_name" content="Acme Example">
  </head>
  <body>
    <h1>Operations Specialist</h1>
    <div class="job-location">Hamburg, Germany</div>
    <section class="job-description">
      Coordinate vendors, improve internal workflows, and partner with engineering and finance
      teams to deliver reliable operations for customers across Europe.
    </section>
    <a href="/apply/operations-specialist">Apply for this role</a>
  </body>
</html>
"""


class AtsRouterContractTests(unittest.TestCase):
    def test_greenhouse_fixture_maps_structured_metadata_and_publication_timestamp(self):
        request_url = "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"

        def requester(url: str, **_: object) -> _ResponseFixture:
            self.assertEqual(url, request_url)
            return _ResponseFixture(GREENHOUSE_PAYLOAD, url=request_url)

        snapshot = fetch_ats_snapshot(
            "https://boards.greenhouse.io/acme",
            "greenhouse",
            requester=requester,
        )

        job = snapshot["jobs"][0]
        self.assertEqual(job["title"], "Backend Engineer")
        self.assertEqual(job["application_url"], "https://boards.greenhouse.io/acme/jobs/101/apply")
        self.assertEqual(job["location_collection"], ["Berlin"])
        self.assertEqual(job["department"], "Engineering")
        self.assertEqual(job["office"], "Berlin HQ")
        self.assertEqual(job["requisition_id"], "REQ-101")
        self.assertEqual(job["source_timestamps"]["timestamp_state"], "known")
        self.assertEqual(
            job["source_timestamps"]["fields"]["source_posted_at"]["value"],
            "2026-08-09T12:30:00+00:00",
        )

    def test_lever_fixture_preserves_categories_salary_and_lifecycle_without_inventing_posted_at(self):
        request_url = "https://api.lever.co/v0/postings/acme?mode=json"

        def requester(url: str, **_: object) -> _ResponseFixture:
            self.assertEqual(url, request_url)
            return _ResponseFixture(LEVER_PAYLOAD, url=request_url)

        snapshot = fetch_ats_snapshot("https://jobs.lever.co/acme", "lever", requester=requester)
        job = snapshot["jobs"][0]

        self.assertEqual(job["title"], "Data Analyst")
        self.assertEqual(job["location_collection"], ["Munich"])
        self.assertEqual(job["department"], "Data")
        self.assertEqual(job["team"], "Analytics")
        self.assertEqual(job["employment_type"], "Full-time")
        self.assertEqual(job["workplace_arrangement"], "hybrid")
        self.assertEqual(job["salary"]["currency"], "EUR")
        self.assertEqual(job["source_timestamps"]["timestamp_state"], "unknown_source_timestamp")
        self.assertIsNotNone(job["source_timestamps"]["fields"]["source_created_at"]["value"])
        self.assertEqual(
            job["source_timestamps"]["fields"]["source_updated_at"]["value"],
            "2026-08-10T09:00:00+00:00",
        )
        self.assertEqual(job["posted_at"], "")


class GenericCareerPageContractTests(unittest.TestCase):
    def test_jsonld_graph_and_multiple_locations_are_extracted_as_disjoint_values(self):
        soup = BeautifulSoup(JSON_LD_PAGE, "html.parser")
        payload = extract_jobposting_jsonld(soup)

        self.assertEqual(payload["title"], "Backend Engineer")
        self.assertEqual(
            extract_generic_locations(payload),
            ["Berlin, BE, DE", "Munich, BY, DE"],
        )
        self.assertEqual(extract_generic_location(payload), "Berlin, BE, DE; Munich, BY, DE")

    def test_jsonld_page_preserves_timestamps_locations_and_embedded_application(self):
        response = _ResponseFixture(
            {},
            url="https://careers.acme.example/jobs/backend-engineer",
            text=JSON_LD_PAGE,
        )
        with patch("backend.capabilities.tailored_documents.manual_urls.requests.get", return_value=response):
            record = fetch_generic_manual_job(response.url)

        self.assertEqual(record["title"], "Backend Engineer")
        self.assertEqual(record["company"], "Acme Example")
        self.assertEqual(record["location_collection"], ["Berlin, BE, DE", "Munich, BY, DE"])
        self.assertEqual(record["location_raw"], "Berlin, BE, DE; Munich, BY, DE")
        self.assertEqual(record["source_posted_at"], "2026-08-08T10:15:00Z")
        self.assertEqual(record["source_raw_payload"]["datePosted"], "2026-08-08T10:15:00Z")
        self.assertEqual(record["application_classification"], URL_EMPLOYER_APPLICATION)
        self.assertEqual(record["application_url"], "https://careers.acme.example/jobs/backend-engineer/apply")

        normalized = normalize_job_for_ingestion(
            record,
            {
                "connector": "career_site",
                "canonical_company_name": "Acme Example",
                "canonical_target_url": response.url,
                "official_employer_hosts": ["careers.acme.example"],
            },
        )
        self.assertEqual(normalized["source_timestamps"]["timestamp_state"], "known")
        self.assertEqual(
            normalized["normalized_source_metadata"]["fields"]["location_collection"]["value"],
            ["Berlin, BE, DE", "Munich, BY, DE"],
        )

    def test_generic_html_fallback_extracts_location_description_and_apply_link_without_jsonld(self):
        response = _ResponseFixture(
            {},
            url="https://careers.acme.example/jobs/operations-specialist",
            text=GENERIC_HTML_PAGE,
        )
        with patch("backend.capabilities.tailored_documents.manual_urls.requests.get", return_value=response):
            record = fetch_generic_manual_job(response.url)

        self.assertEqual(record["title"], "Operations Specialist")
        self.assertEqual(record["company"], "Acme Example")
        self.assertEqual(record["location_collection"], ["Hamburg, Germany"])
        self.assertIn("Coordinate vendors", record["description_text"])
        self.assertEqual(record["application_url"], "https://careers.acme.example/apply/operations-specialist")
        self.assertEqual(record["source_posted_at"], "")


class ApplicationDestinationContractTests(unittest.TestCase):
    TARGET = {
        "connector": "career_site",
        "canonical_target_url": "https://careers.acme.example/careers",
        "official_employer_hosts": ["careers.acme.example", "acme.example"],
    }

    def test_destination_variants_are_disjoint_and_truthful(self):
        cases = [
            (
                "employer direct",
                {"employer_application_url": "https://careers.acme.example/apply/1"},
                "verified",
                URL_EMPLOYER_APPLICATION,
                "direct_apply",
                "https://careers.acme.example/apply/1",
            ),
            (
                "ats direct",
                {"ats_application_url": "https://boards.greenhouse.io/acme/jobs/1/apply"},
                "verified",
                URL_ATS_APPLICATION,
                "direct_apply",
                "https://boards.greenhouse.io/acme/jobs/1/apply",
            ),
            (
                "detail only",
                {"source_ats": "lever", "job_detail_url": "https://jobs.lever.co/acme/1"},
                "unresolved",
                URL_ATS_JOB_DETAIL,
                "job_detail",
                "https://jobs.lever.co/acme/1",
            ),
            (
                "employer listing fallback",
                {"url": "https://careers.acme.example/careers"},
                "unresolved",
                URL_CAREERS_INDEX,
                "listing_fallback",
                "https://careers.acme.example/careers",
            ),
        ]
        for name, job, status, classification, method, user_facing_url in cases:
            with self.subTest(name=name):
                destination = resolve_application_destination(job, self.TARGET)
                self.assertEqual(destination["status"], status)
                self.assertEqual(destination["classification"], classification)
                self.assertEqual(destination["application_method"], method)
                self.assertEqual(destination["user_facing_url"], user_facing_url)
                self.assertEqual(
                    destination["resolved_url"],
                    user_facing_url if status == "verified" else "",
                )

    def test_embedded_form_is_direct_but_marked_as_embedded(self):
        destination = resolve_application_destination(
            {
                "job_detail_url": "https://careers.acme.example/jobs/1",
                "source_page_html": '<form action="/jobs/1/application"><button>Apply now</button></form>',
            },
            self.TARGET,
        )

        self.assertEqual(destination["status"], "verified")
        self.assertEqual(destination["classification"], URL_EMPLOYER_APPLICATION)
        self.assertEqual(destination["destination_type"], "embedded_apply")
        self.assertIn("html_form_action", {item["source_field"] for item in destination["candidate_urls"]})

    def test_url_taxonomy_keeps_unknown_external_url_distinct_from_supported_routes(self):
        self.assertEqual(
            classify_job_url("https://other.example/jobs/1", target=self.TARGET),
            URL_UNKNOWN,
        )
        self.assertIn(
            classify_job_url("https://careers.acme.example/apply/1", target=self.TARGET),
            DIRECT_APPLICATION_CLASSIFICATIONS,
        )
        self.assertEqual(
            classify_job_url("https://boards.greenhouse.io/acme/jobs/1", target=self.TARGET),
            URL_ATS_JOB_DETAIL,
        )


class UnifiedMappingContractTests(unittest.TestCase):
    def test_typed_taxonomies_and_normalized_values_are_explicit(self):
        mapping = map_job_fields(
            {
                "department": "Backend Engineering",
                "employment_type": "Vollzeit",
                "workplace_arrangement": "hybrid",
                "languages": [{"language": "German", "status": "required"}],
                "source_timestamps": {
                    "fields": {
                        "source_posted_at": {
                            "value": "2026-08-08T10:15:00+00:00",
                            "source_field": "source_posted_at",
                            "method": "source_field",
                            "semantic": "source_published",
                        }
                    }
                },
                "application_destination": {
                    "classification": URL_EMPLOYER_APPLICATION,
                    "resolved_url": "https://careers.acme.example/apply/1",
                    "status": "verified",
                },
            },
            observed_at="2026-08-10T10:00:00+00:00",
        )

        self.assertEqual(mapping["fields"]["runr_function"]["normalized_value"], "Engineering")
        self.assertEqual(mapping["fields"]["runr_subfunction"]["normalized_value"], "Backend Engineering")
        self.assertEqual(mapping["fields"]["employment_type"]["normalized_value"], "Full-time")
        self.assertEqual(mapping["fields"]["workplace_arrangement"]["normalized_value"], "Hybrid")
        self.assertEqual(mapping["fields"]["application_destination"]["normalized_value"]["destination_type"], "dedicated_apply")
        self.assertEqual(mapping["timestamps"]["published_at"]["state"], "present")
        self.assertEqual(set(mapping["function_taxonomy"]), set(FUNCTION_TAXONOMY))
        self.assertEqual(set(mapping["employment_taxonomy"]), set(EMPLOYMENT_TYPES))
        self.assertEqual(set(mapping["workplace_taxonomy"]), set(WORKPLACE_ARRANGEMENTS))
        self.assertEqual(set(mapping["application_taxonomy"]), set(APPLICATION_DESTINATIONS))

    def test_source_unsupported_is_distinct_from_source_unknown(self):
        greenhouse = normalize_source_metadata(
            {"department": "Engineering"},
            source_ats="greenhouse",
            provenance_url="https://boards.greenhouse.io/acme/jobs/1",
        )
        generic = normalize_source_metadata(
            {"department": "Engineering"},
            source_ats="career_site",
            provenance_url="https://careers.acme.example/jobs/1",
        )

        self.assertEqual(greenhouse["fields"]["department"]["state"], "present")
        self.assertEqual(greenhouse["fields"]["team"]["state"], "unsupported")
        self.assertEqual(greenhouse["fields"]["salary"]["state"], "unsupported")
        self.assertEqual(generic["fields"]["team"]["state"], "unknown")
        self.assertEqual(generic["fields"]["salary"]["state"], "unknown")


if __name__ == "__main__":
    unittest.main()
