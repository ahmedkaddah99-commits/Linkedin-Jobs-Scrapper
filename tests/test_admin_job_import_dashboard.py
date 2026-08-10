from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from backend.api.routes import build_route_registry
from backend.api.routes.registry import ApiRouteContext
from backend.bootstrap import create_backend
from backend.connectors.ats_router import fetch_ats_snapshot
from backend.connectors.company_career_sites import plan_company_site_scope


class _Response:
    def __init__(self, url: str, payload: object):
        self.url = url
        self.status_code = 200
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _AdminHandler:
    def __init__(self, body=None):
        self.body = body or {}
        self.payload = None
        self.admin_calls = 0

    def _require_admin(self):
        self.admin_calls += 1
        return {"id": "admin-fixture"}, object()

    def _read_json_body(self):
        return self.body

    def _send_json(self, payload, status=200, *, headers=None):
        self.payload = (status, payload)


class AdminJobImportDashboardTests(unittest.TestCase):
    def test_global_admin_entrypoint_is_not_rejected_by_locale_path(self):
        site = {"company_name": "Siemens Industry Software", "url": "https://www.siemens.com/en-us/company/jobs"}

        default_plan = plan_company_site_scope(
            company_sites=[site],
            target_country_codes=["Germany"],
        )
        admin_plan = plan_company_site_scope(
            company_sites=[site],
            target_country_codes=["Germany"],
            allow_foreign_entrypoints=True,
        )

        self.assertEqual(default_plan.selected_sites, [])
        self.assertEqual(default_plan.skipped_sites[0]["skip_reason"], "foreign_market_site")
        self.assertEqual(len(admin_plan.selected_sites), 1)
        self.assertEqual(admin_plan.selected_sites[0]["url"], "https://siemens.com/en-us/company/jobs")

    def test_siemens_is_available_for_admin_imports_and_cost_is_bounded(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            siemens = next(item for item in app.list_admin_job_import_sources() if item["id"] == "siemens")

            self.assertEqual(siemens["status"], "ready")
            self.assertEqual(siemens["reason"], "")

            plan = app.plan_admin_job_import(
                source_ids=["siemens"],
                scope={"country": "Germany", "max_credits": 1000},
            )
            self.assertTrue(plan["can_start"])
            self.assertTrue(plan["estimated_cost"]["known"])
            self.assertEqual(plan["estimated_cost"]["currency"], "ScrapeOps credits")

    def test_greenhouse_pagination_is_bounded_and_durable(self):
        calls = []
        first_page = [
            {
                "id": f"job-{index}",
                "title": f"Operations Analyst {index}",
                "absolute_url": f"https://boards.greenhouse.io/n26/jobs/{index}",
            }
            for index in range(100)
        ]

        def requester(url, **_kwargs):
            calls.append(url)
            if "page=2" in url:
                return _Response(url, {"meta": {"total": 101}, "jobs": [
                    {"id": "job-100", "title": "Operations Analyst 100", "absolute_url": "https://boards.greenhouse.io/n26/jobs/100"}
                ]})
            return _Response(url, {"meta": {"total": 101}, "jobs": first_page})

        result = fetch_ats_snapshot(
            "https://job-boards.greenhouse.io/n26",
            "greenhouse",
            requester=requester,
            max_pages=2,
        )

        self.assertEqual(result["pages_fetched"], 2)
        self.assertEqual(len(result["jobs"]), 101)
        self.assertEqual(calls, [
            "https://boards-api.greenhouse.io/v1/boards/n26/jobs?content=true",
            "https://boards-api.greenhouse.io/v1/boards/n26/jobs?content=true&page=2",
        ])

    def test_import_review_publish_undo_and_failed_import_are_offline_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            app.repositories.config_store.set_value("acquisition.admin_imports.enabled", True)
            app.repositories.config_store.set_value("acquisition.admin_imports.kill_switch", False)
            app.repositories.config_store.set_value("acquisition.admin_imports.allow_proxy", True)
            responses = {"job-1": True, "job-2": True}
            requests_seen = []

            def requester(url, **_kwargs):
                requests_seen.append(url)
                if not responses:
                    raise AssertionError("The fixture should not make an unexpected request.")
                job_id = next(iter(responses))
                include_job = responses[job_id]
                if job_id == "job-failed":
                    raise RuntimeError("fixture source outage")
                jobs = [
                    {
                        "id": job_id,
                        "title": f"Operations Analyst {job_id}",
                        "absolute_url": f"https://boards.greenhouse.io/n26/jobs/{job_id}",
                        "location": {"name": "Berlin, Germany"},
                        "content": "Own operational reporting and controls.",
                    },
                    {
                        "id": f"quick-{job_id}",
                        "title": "Quick Apply Analyst",
                        "absolute_url": f"https://boards.greenhouse.io/n26/jobs/quick-{job_id}",
                        "application_method": "quick_apply",
                    },
                ] if include_job else []
                return _Response(url, {"jobs": jobs})

            app._acquisition_scheduler.requester = requester

            plan = app.plan_admin_job_import(source_ids=["n26_greenhouse"], scope={"country": "Germany", "max_pages": 2})
            self.assertTrue(plan["can_start"])
            self.assertEqual(plan["maximum_requests"], 1)
            self.assertTrue(plan["review_first"])
            self.assertFalse(plan["publishes_automatically"])

            first = app.start_admin_job_import(
                requested_by="admin-fixture",
                idempotency_key="offline-import-1",
                source_ids=["n26_greenhouse"],
                scope={"country": "Germany"},
            )
            replay = app.start_admin_job_import(
                requested_by="admin-fixture",
                idempotency_key="offline-import-1",
                source_ids=["n26_greenhouse"],
                scope={"country": "Germany"},
            )
            self.assertEqual(first["import_id"], replay["import_id"])
            processed = app.process_next_admin_job_import(worker_id="fixture-worker")
            self.assertEqual(processed["import"]["status"], "completed")
            self.assertEqual(processed["report"]["cycle"]["status"], "completed")
            self.assertEqual(len(requests_seen), 1)

            review = app.list_admin_review_jobs(import_id=first["import_id"], status="all", limit=20)
            self.assertEqual(review["total"], 2)
            accepted = next(item for item in review["jobs"] if not item["rejected"])
            rejected = next(item for item in review["jobs"] if item["rejected"])
            self.assertEqual(rejected["review_state"], "not_accepted")
            self.assertEqual(rejected["reason_code"], "unsupported_application_method")

            decision = app.decide_admin_review_job(
                import_id=first["import_id"],
                canonical_job_id=accepted["canonical_job_id"],
                decision="approve",
                actor_user_id="admin-fixture",
            )
            self.assertEqual(decision["canonical_job_id"], accepted["canonical_job_id"])
            self.assertEqual(decision["review_state"], "approved")
            preview_one = app.preview_admin_job_import(first["import_id"], actor_user_id="admin-fixture")
            self.assertEqual(preview_one["total"], 1)
            publication_one = app.publish_admin_job_import(preview_one["publication_id"], actor_user_id="admin-fixture")
            self.assertEqual(app.get_public_acquisition_catalog()["total"], 1)

            responses.clear()
            responses["job-2"] = True
            second = app.start_admin_job_import(
                requested_by="admin-fixture",
                idempotency_key="offline-import-2",
                source_ids=["n26_greenhouse"],
                scope={"country": "Germany"},
            )
            app.process_next_admin_job_import(worker_id="fixture-worker")
            second_review = app.list_admin_review_jobs(import_id=second["import_id"], status="all", limit=20)
            second_job = next(item for item in second_review["jobs"] if not item["rejected"])
            app.decide_admin_review_job(
                import_id=second["import_id"],
                canonical_job_id=second_job["canonical_job_id"],
                decision="approved",
                actor_user_id="admin-fixture",
            )
            preview_two = app.preview_admin_job_import(second["import_id"], actor_user_id="admin-fixture")
            self.assertEqual(preview_two["previous_publication_id"], publication_one)
            app.publish_admin_job_import(preview_two["publication_id"], actor_user_id="admin-fixture")
            self.assertEqual(app.get_public_acquisition_catalog()["total"], 2)
            undone = app.undo_admin_job_publication(actor_user_id="admin-fixture")
            self.assertEqual(undone["status"], "undone")
            self.assertEqual(app.get_public_acquisition_catalog()["total"], 1)
            self.assertEqual(app.get_public_acquisition_catalog()["publication"]["publication_id"], publication_one)

            responses.clear()
            responses["job-failed"] = True
            failed = app.start_admin_job_import(
                requested_by="admin-fixture",
                idempotency_key="offline-import-failed",
                source_ids=["n26_greenhouse"],
                scope={"country": "Germany"},
            )
            failed_result = app.process_next_admin_job_import(worker_id="fixture-worker")
            self.assertEqual(failed_result["import"]["status"], "needs_attention")
            self.assertEqual(failed_result["report"]["cycle"]["status"], "degraded")
            self.assertEqual(app.get_public_acquisition_catalog()["total"], 1)
            self.assertEqual(app.get_admin_job_import(failed["import_id"])["publication_id"], "")

    def test_job_import_api_route_requires_admin_and_exposes_overview(self):
        registry = build_route_registry()
        application = Mock()
        application.get_admin_job_import_overview.return_value = {"imports": {"status": "Paused"}}
        handler = _AdminHandler()
        context = ApiRouteContext(
            application=application,
            handler=handler,
            method="GET",
            segments=("admin", "job-import", "overview"),
            query={},
        )

        self.assertTrue(registry.dispatch(context, auth_required=True))
        self.assertEqual(handler.admin_calls, 1)
        self.assertEqual(handler.payload, (200, {"imports": {"status": "Paused"}}))
        application.get_admin_job_import_overview.assert_called_once_with()

    def test_job_import_resume_switch_enables_imports(self):
        registry = build_route_registry()
        application = Mock()
        application.repositories.config_store = Mock()
        handler = _AdminHandler({"paused": False})
        context = ApiRouteContext(
            application=application,
            handler=handler,
            method="POST",
            segments=("admin", "job-import", "pause"),
            query={},
        )

        self.assertTrue(registry.dispatch(context, auth_required=True))
        application.repositories.config_store.set_value.assert_any_call("acquisition.admin_imports.kill_switch", False)
        application.repositories.config_store.set_value.assert_any_call("acquisition.admin_imports.enabled", True)
        application.repositories.config_store.set_value.assert_any_call("acquisition.admin_imports.allow_proxy", True)

    def test_admin_inspection_composes_canonical_job_company_provenance_and_apply_state(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            app.repositories.config_store.set_value("acquisition.admin_imports.enabled", True)
            app.repositories.config_store.set_value("acquisition.admin_imports.kill_switch", False)
            app.repositories.config_store.set_value("acquisition.admin_imports.allow_proxy", True)

            def requester(url, **_kwargs):
                return _Response(url, {"jobs": [{
                    "id": "job-inspection-1",
                    "title": "Senior Backend Engineer",
                    "absolute_url": "https://job-boards.greenhouse.io/n26/jobs/job-inspection-1",
                    "location": {"name": "Berlin, Germany"},
                    "content": "Build reliable payment services.",
                }]})

            app._acquisition_scheduler.requester = requester
            imported = app.start_admin_job_import(
                requested_by="admin-fixture",
                idempotency_key="inspection-import-1",
                source_ids=["n26_greenhouse"],
                scope={"country": "Germany"},
            )
            app.process_next_admin_job_import(worker_id="inspection-worker")

            listed = app.list_admin_job_inspections(search="N26", limit=10)
            self.assertEqual(listed["total"], 1)
            canonical_job_id = listed["jobs"][0]["canonical_job_id"]
            inspection = app.get_admin_job_inspection(canonical_job_id)
            self.assertIsNotNone(inspection)
            self.assertEqual(inspection["job"]["title"], "Senior Backend Engineer")
            self.assertEqual(inspection["company"]["name"], "N26")
            self.assertEqual(inspection["admin"]["target_id"], "n26_greenhouse")
            self.assertEqual(inspection["apply_url"]["classification"], "listing_fallback")
            self.assertEqual(inspection["apply_url"]["url_type"], "ats_job_detail")
            self.assertEqual(inspection["apply_url"]["status"], "unresolved")
            self.assertEqual(inspection["apply_url"]["application_method"], "job_detail")
            self.assertTrue(inspection["raw"]["source_observations"])
            self.assertTrue(inspection["raw"]["posting_versions"])
            self.assertTrue(inspection["raw"]["acquisition_requests"])

            resolved = app.resolve_admin_job_apply_url(canonical_job_id, actor_user_id="admin-fixture")
            self.assertEqual(resolved["apply_url"]["status"], "unresolved")
            self.assertTrue(any(
                event.get("event_type") == "apply_url_resolution"
                for event in resolved["raw"]["audit_events"]
            ))
            self.assertEqual(app.get_admin_job_import(imported["import_id"])["status"], "completed")


if __name__ == "__main__":
    unittest.main()
