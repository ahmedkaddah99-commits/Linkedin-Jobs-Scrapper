from __future__ import annotations

import unittest
from unittest.mock import Mock

from backend.connectors.ats_expansions import (
    build_capability_snapshot,
    build_capability_snapshots,
    measure_raw_retention,
    fetch_expansion_snapshot,
    run_fixture_snapshot,
)


class AtsExpansionContractTests(unittest.TestCase):
    def test_expansion_connectors_are_disabled_by_default_and_report_capabilities(self):
        snapshot = build_capability_snapshot("workday", "https://acme.wd1.myworkdayjobs.com/careers")

        self.assertEqual(snapshot["connector"], "workday")
        self.assertFalse(snapshot["enabled"])
        self.assertEqual(snapshot["state"], "disabled")
        self.assertEqual(snapshot["capabilities"]["locations"]["state"], "supported")
        self.assertEqual(snapshot["capabilities"]["salary"]["state"], "partial")
        self.assertEqual(snapshot["capabilities"]["logo"]["state"], "unsupported")
        self.assertEqual(snapshot["request_limits"]["max_requests"], 1)
        self.assertEqual(snapshot["request_limits"]["max_pages"], 1)

    def test_workday_fixture_has_stable_identity_typed_fields_and_retained_raw_evidence(self):
        payload = {
            "jobPostings": [
                {
                    "jobPostingId": "WD-42",
                    "title": "Senior Platform Engineer",
                    "externalUrl": "https://acme.wd1.myworkdayjobs.com/careers/job/WD-42",
                    "applicationUrl": "https://acme.wd1.myworkdayjobs.com/careers/job/WD-42/apply",
                    "jobPostingInfo": {
                        "jobFamily": "Engineering",
                        "team": "Platform",
                        "jobCategory": "Software",
                        "timeType": "Full time",
                        "remoteType": "Hybrid",
                        "locations": [{"name": "Berlin, DE"}],
                        "salary": {"min": 90000, "max": 110000, "currency": "EUR", "period": "year"},
                    },
                    "updatedOn": "2026-08-10T10:00:00Z",
                }
            ]
        }

        result = run_fixture_snapshot("workday", "https://acme.wd1.myworkdayjobs.com/careers", payload)
        replay = run_fixture_snapshot("workday", "https://acme.wd1.myworkdayjobs.com/careers", payload)
        job = result["jobs"][0]

        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["complete_snapshot"])
        self.assertEqual(job["external_id"], "WD-42")
        self.assertEqual(job["stable_external_id"], replay["jobs"][0]["stable_external_id"])
        self.assertEqual(job["source_department"], "Engineering")
        self.assertEqual(job["source_team"], "Platform")
        self.assertEqual(job["locations"], ["Berlin, DE"])
        self.assertEqual(job["salary"]["currency"], "EUR")
        self.assertEqual(job["application_method"], "direct_apply")
        self.assertEqual(job["application_status"], "verified")
        self.assertEqual(result["raw_retention"]["retention_rate"], 1.0)
        self.assertEqual(measure_raw_retention(result["jobs"])["retained"], 1)

    def test_all_expansion_fixtures_are_network_safe_and_preserve_connector_identity(self):
        fixtures = {
            "personio": (
                "https://acme.jobs.personio.de/job/42",
                {"position": [{"id": "personio-42", "name": "Operations Lead", "jobAdLink": "https://acme.jobs.personio.de/job/42", "applyUrl": "https://acme.jobs.personio.de/job/42/apply", "department": "Operations", "office": "Berlin"}]},
            ),
            "recruitee": (
                "https://acme.recruitee.com/o/42",
                {"offers": [{"id": "recruitee-42", "title": "Product Manager", "careers_url": "https://acme.recruitee.com/o/42", "apply_url": "https://acme.recruitee.com/o/42/apply", "department": "Product"}]},
            ),
            "smartrecruiters": (
                "https://careers.smartrecruiters.com/Acme",
                {"content": [{"id": "smart-42", "name": "Risk Analyst", "ref": "https://jobs.smartrecruiters.com/Acme/42", "applyUrl": "https://jobs.smartrecruiters.com/Acme/42/apply", "department": "Risk"}]},
            ),
        }

        def must_not_request(*_: object, **__: object) -> object:
            raise AssertionError("fixture execution performed network I/O")

        for connector, (target_url, payload) in fixtures.items():
            with self.subTest(connector=connector):
                result = fetch_expansion_snapshot(
                    target_url,
                    connector,
                    fixture_payload=payload,
                    requester=must_not_request,
                )
                self.assertEqual(result["status"], "completed")
                self.assertTrue(result["complete_snapshot"])
                self.assertEqual(result["requests_made"], 1)
                self.assertEqual(result["raw_retention"]["retained"], 1)
                self.assertTrue(result["jobs"][0]["stable_external_id"].startswith(f"{connector}:"))
                self.assertEqual(result["jobs"][0]["application_status"], "verified")

    def test_bounded_retry_recovers_but_keeps_snapshot_incomplete_when_more_pages_exist(self):
        responses = iter(
            [
                Mock(status_code=503),
                Mock(
                    status_code=200,
                    json=lambda: {
                        "content": [
                            {
                                "id": "smart-1",
                                "name": "Engineer",
                                "ref": "https://jobs.smartrecruiters.com/Acme/1",
                                "applyUrl": "https://jobs.smartrecruiters.com/Acme/1/apply",
                            }
                        ],
                        "totalFound": 2,
                    },
                ),
            ]
        )

        def requester(*_: object, **__: object) -> Mock:
            return next(responses)

        result = fetch_expansion_snapshot(
            "https://careers.smartrecruiters.com/Acme",
            "smartrecruiters",
            requester=requester,
            enabled=True,
            max_requests=3,
            max_pages=1,
            max_retries=2,
            page_size=1,
        )

        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["complete_snapshot"])
        self.assertEqual(result["requests_made"], 2)
        self.assertTrue(result["recovery"]["recovered"])
        self.assertEqual(result["recovery"]["retryable_failures"], 1)
        self.assertIn("bounded_page_limit_reached", result["warnings"])

    def test_application_destination_distinguishes_same_page_forms_from_careers_indexes(self):
        same_page = run_fixture_snapshot(
            "recruitee",
            "https://acme.recruitee.com/jobs",
            {
                "offers": [
                    {
                        "id": "same-page-1",
                        "title": "Support Engineer",
                        "job_detail_url": "https://acme.recruitee.com/o/1",
                        "application_url": "https://acme.recruitee.com/o/1",
                        "has_application_form": True,
                    }
                ]
            },
        )
        careers_index = run_fixture_snapshot(
            "recruitee",
            "https://acme.recruitee.com/jobs",
            {
                "offers": [
                    {
                        "id": "index-1",
                        "title": "Support Engineer",
                        "job_detail_url": "https://acme.recruitee.com/o/1",
                        "application_url": "https://acme.recruitee.com/jobs",
                    }
                ]
            },
        )

        self.assertEqual(same_page["jobs"][0]["application_method"], "same_page")
        self.assertEqual(same_page["jobs"][0]["application_status"], "verified")
        self.assertEqual(careers_index["jobs"][0]["application_method"], "unknown")
        self.assertEqual(careers_index["jobs"][0]["application_status"], "unsupported")
        self.assertIn("careers_index_not_apply_destination", careers_index["jobs"][0]["warnings"])

    def test_permanent_request_failure_is_report_only_and_does_not_emit_partial_jobs(self):
        response = Mock(status_code=503)

        result = fetch_expansion_snapshot(
            "https://careers.smartrecruiters.com/Acme",
            "smartrecruiters",
            requester=lambda *_args, **_kwargs: response,
            enabled=True,
            max_requests=1,
            max_retries=0,
        )

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["complete_snapshot"])
        self.assertEqual(result["jobs"], [])
        self.assertEqual(result["warnings"], ["http_503"])
        self.assertTrue(result["recovery"]["report_only"])

    def test_malformed_listing_isolated_without_making_snapshot_closure_safe(self):
        result = run_fixture_snapshot(
            "smartrecruiters",
            "https://careers.smartrecruiters.com/Acme",
            {
                "content": [
                    {
                        "id": "valid-1",
                        "name": "Engineer",
                        "ref": "https://jobs.smartrecruiters.com/Acme/1",
                        "applyUrl": "https://jobs.smartrecruiters.com/Acme/1/apply",
                    },
                    "malformed-listing",
                ]
            },
        )

        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["complete_snapshot"])
        self.assertEqual(len(result["jobs"]), 1)
        self.assertEqual(result["observation_failures"][0]["index"], 1)
        self.assertEqual(result["observation_failures"][0]["error_type"], "invalid_item")

    def test_capability_inventory_is_registered_for_every_expansion_connector(self):
        snapshots = build_capability_snapshots()

        self.assertEqual({snapshot["connector"] for snapshot in snapshots}, {"workday", "personio", "recruitee", "smartrecruiters"})
        self.assertTrue(all(snapshot["enabled"] for snapshot in snapshots))
        self.assertTrue(all(snapshot["production_registered"] for snapshot in snapshots))


if __name__ == "__main__":
    unittest.main()
