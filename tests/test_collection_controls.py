from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.acquisition.collection_controls import collection_metadata, infer_stop_reason
from backend.acquisition.manifest import load_phase_a_manifest
from backend.bootstrap import create_backend
from backend.api.routes import build_route_registry
from backend.api.routes.registry import ApiRouteContext
from backend.connectors.ats_router import fetch_ats_snapshot


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

    def _send_error(self, status, code, message, *, details=None, headers=None):
        self.payload = (status, {"error": code, "message": message})


def _greenhouse_job(job_id: str) -> dict[str, object]:
    return {
        "id": job_id,
        "title": f"Operations Analyst {job_id}",
        "absolute_url": f"https://boards.greenhouse.io/n26/jobs/{job_id}",
        "location": {"name": "Berlin, Germany"},
        "content": "Operate reliable reporting systems.",
    }


class CollectionControlsTests(unittest.TestCase):
    def test_validation_and_admin_authorization_contract(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            with self.assertRaises(ValueError):
                app.plan_admin_job_import(source_ids=["n26_greenhouse"], scope={"retrieval_mode": "unsafe"})
            with self.assertRaises(ValueError):
                app.plan_admin_job_import(source_ids=["n26_greenhouse"], scope={"max_jobs": -1})

        registry = build_route_registry()
        application = type("Application", (), {"list_admin_job_import_sources": lambda self: []})()
        handler = _AdminHandler()
        context = ApiRouteContext(
            application=application,
            handler=handler,
            method="GET",
            segments=("admin", "acquisition", "sources"),
            query={},
        )
        self.assertTrue(registry.dispatch(context, auth_required=True))
        self.assertEqual(handler.admin_calls, 1)

        handler = _AdminHandler({"source_ids": ["n26_greenhouse"], "scope": {"retrieval_mode": "unsafe"}})
        context = ApiRouteContext(
            application=app,
            handler=handler,
            method="POST",
            segments=("admin", "acquisition", "imports", "plan"),
            query={},
        )
        self.assertTrue(registry.dispatch(context, auth_required=True))
        self.assertEqual(handler.payload[0], 400)

    def test_bounded_custom_and_all_available_are_planned_from_capabilities(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")

            bounded = app.plan_admin_job_import(
                source_ids=["n26_greenhouse"],
                scope={},
            )
            custom = app.plan_admin_job_import(
                source_ids=["n26_greenhouse"],
                scope={"retrieval_mode": "custom", "max_jobs": 7, "max_pages": 2},
            )
            all_available = app.plan_admin_job_import(
                source_ids=["n26_greenhouse"],
                scope={"retrieval_mode": "all_available", "max_pages": 2, "max_requests": 2},
            )
            unsupported = app.plan_admin_job_import(
                source_ids=["siemens"],
                scope={"retrieval_mode": "all_available"},
            )

            self.assertEqual(bounded["scope"]["retrieval_mode"], "bounded")
            self.assertEqual(custom["scope"]["max_jobs"], 7)
            self.assertTrue(all_available["can_start"])
            self.assertFalse(unsupported["can_start"])
            self.assertIn("all_available_not_supported:siemens", unsupported["limit_errors"])
            source = next(item for item in app.list_admin_job_import_sources() if item["id"] == "siemens")
            self.assertFalse(source["all_available"]["available"])
            self.assertEqual(source["all_available"]["reason"], "reliable_pagination_unavailable")

    def test_max_jobs_caps_accepted_roles_and_has_no_publication_side_effect(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            app.repositories.config_store.set_value("acquisition.admin_imports.enabled", True)
            app.repositories.config_store.set_value("acquisition.admin_imports.kill_switch", False)
            app.repositories.config_store.set_value("acquisition.admin_imports.allow_proxy", True)
            app._acquisition_scheduler.requester = lambda url, **_: _Response(
                url,
                {"jobs": [_greenhouse_job(str(index)) for index in range(3)]},
            )

            queued = app.start_admin_job_import(
                requested_by="admin-fixture",
                idempotency_key="collection-cap-1",
                source_ids=["n26_greenhouse"],
                scope={"retrieval_mode": "custom", "max_jobs": 1},
            )
            processed = app.process_next_admin_job_import(worker_id="collection-worker")
            target = processed["report"]["targets"][0]
            collection = target["task"]["collection"]

            self.assertEqual(queued["scope"]["max_jobs"], 1)
            self.assertEqual(collection["requested_job_limit"], 1)
            self.assertEqual(collection["effective_job_limit"], 1)
            self.assertEqual(collection["observed_count"], 3)
            self.assertEqual(collection["accepted_count"], 1)
            self.assertEqual(collection["rejected_count"], 2)
            self.assertEqual(collection["stop_reason"], "accepted_job_limit")
            self.assertFalse(collection["complete_snapshot"])
            self.assertFalse(collection["closure_safe"])
            self.assertEqual(processed["report"]["cycle"]["publication_id"], "")
            self.assertEqual(app.get_public_acquisition_catalog()["freshness"], "unpublished")

    def test_legacy_full_source_import_is_not_all_available(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            plan = app.plan_admin_job_import(
                source_ids=["siemens"],
                scope={
                    "full_source_import": True,
                    "retrieval_mode": "bounded",
                    "country": "Germany",
                    "keywords": ["analyst"],
                },
            )
            self.assertEqual(plan["scope"]["retrieval_mode"], "bounded")
            self.assertTrue(plan["scope"]["full_source_import"])
            self.assertEqual(plan["scope"]["country"], "")
            self.assertIn("does not imply", plan["compatibility"]["full_source_import"])

    def test_stop_reason_contract_covers_provider_and_ceiling_paths(self):
        cases = {
            "accepted_job_limit": dict(scope={}, capability={}, fetched={}, accepted_cap_hit=True),
            "pagination_complete": dict(scope={}, capability={}, fetched={"pagination_complete": True}, accepted_cap_hit=False),
            "max_pages": dict(scope={"max_pages": 1}, capability={}, fetched={"pages_fetched": 1}, accepted_cap_hit=False),
            "max_requests": dict(scope={"max_requests": 1, "max_pages": 2}, capability={}, fetched={"pages_fetched": 1}, accepted_cap_hit=False, actual_requests=1),
            "max_credits": dict(scope={"max_credits": 1}, capability={}, fetched={}, accepted_cap_hit=False, actual_credits=1),
            "connector_safety_ceiling": dict(scope={}, capability={}, fetched={"connector_safety_ceiling_hit": True}, accepted_cap_hit=False),
            "global_request_ceiling": dict(scope={}, capability={}, fetched={"global_request_ceiling_hit": True}, accepted_cap_hit=False),
            "global_credit_ceiling": dict(scope={}, capability={}, fetched={"global_credit_ceiling_hit": True}, accepted_cap_hit=False),
            "connector_pagination_unsupported": dict(scope={"retrieval_mode": "all_available"}, capability={"reliable_pagination": False}, fetched={}, accepted_cap_hit=False),
            "provider_error": dict(scope={}, capability={}, fetched={"status": "failed"}, accepted_cap_hit=False),
            "no_snapshot_page": dict(scope={}, capability={}, fetched={"pages_fetched": 0}, accepted_cap_hit=False),
        }
        for expected, values in cases.items():
            actual = infer_stop_reason(**values)
            self.assertEqual(actual, expected, expected)
        self.assertEqual(
            infer_stop_reason(
                scope={}, capability={}, fetched={"pages_fetched": 0},
                accepted_count=0, accepted_cap_hit=False,
            ),
            "no_snapshot_page",
        )
        self.assertEqual(collection_metadata(scope={})["stop_reason"], "not_attempted")

    def test_connector_pagination_reports_page_and_request_ceiling_stops(self):
        payload = {"jobs": [{"id": str(index), "title": "Role", "absolute_url": f"https://boards.greenhouse.io/n26/jobs/{index}"} for index in range(100)]}
        page_limited = fetch_ats_snapshot(
            "https://boards.greenhouse.io/n26.json",
            "greenhouse",
            requester=lambda url, **_: _Response(url, payload),
            max_pages=1,
            max_requests=10,
        )
        request_limited = fetch_ats_snapshot(
            "https://boards.greenhouse.io/n26.json",
            "greenhouse",
            requester=lambda url, **_: _Response(url, payload),
            max_pages=2,
            max_requests=1,
        )
        self.assertEqual(page_limited["stop_reason"], "max_pages")
        self.assertEqual(request_limited["stop_reason"], "max_requests")
        self.assertFalse(page_limited["pagination_complete"])
        self.assertFalse(request_limited["complete_snapshot"])

    def test_incomplete_snapshot_never_closes_missing_jobs(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            store = app.repositories.acquisition_store
            target = next(item for item in load_phase_a_manifest() if item["target_id"] == "n26_greenhouse")
            store.ensure_targets([target])

            def ingest(cycle_key: str, jobs: list[dict[str, object]], *, closure_safe: bool):
                cycle = store.claim_due_cycle(window_key=cycle_key, lease_owner="test", scheduled_at="2026-08-10T00:00:00+00:00")
                store.ensure_cycle_tasks(cycle["cycle_id"], [{**target, "enabled": True}])
                task = store.claim_next_task(cycle_id=cycle["cycle_id"], lease_owner="test")
                return store.ingest_snapshot(
                    cycle_id=cycle["cycle_id"],
                    task_id=task["task_id"],
                    target_id=target["target_id"],
                    jobs=jobs,
                    complete_snapshot=True,
                    valid_snapshot=True,
                    closure_safe=closure_safe,
                )

            ingest("closure-safe-1", [_greenhouse_job("stable")], closure_safe=True)
            ingest("closure-unsafe-1", [], closure_safe=False)
            states = store.get_source_state_summary("n26_greenhouse")
            self.assertEqual(states.get("active"), 1)
            self.assertEqual(states.get("closed", 0), 0)

    def test_source_filter_returns_typed_source_value(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            store = app.repositories.acquisition_store
            target = next(item for item in load_phase_a_manifest() if item["target_id"] == "n26_greenhouse")
            store.ensure_targets([target])
            cycle = store.claim_due_cycle(window_key="source-filter-1", lease_owner="test", scheduled_at="2026-08-10T00:00:00+00:00")
            store.ensure_cycle_tasks(cycle["cycle_id"], [{**target, "enabled": True}])
            task = store.claim_next_task(cycle_id=cycle["cycle_id"], lease_owner="test")
            store.ingest_snapshot(
                cycle_id=cycle["cycle_id"],
                task_id=task["task_id"],
                target_id=target["target_id"],
                jobs=[_greenhouse_job("source-filter")],
                complete_snapshot=True,
                valid_snapshot=True,
                closure_safe=True,
            )
            result = store.list_admin_job_inspections(source="greenhouse")
            self.assertEqual(result["total"], 1)
            self.assertIsInstance(result["jobs"][0]["source"], str)
            self.assertEqual(result["jobs"][0]["source"], "greenhouse")

    def test_idempotency_and_audit_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            app.repositories.config_store.set_value("acquisition.admin_imports.enabled", True)
            app.repositories.config_store.set_value("acquisition.admin_imports.kill_switch", False)
            first = app.start_admin_job_import(
                requested_by="admin-fixture",
                idempotency_key="audit-idempotency-1",
                source_ids=["n26_greenhouse"],
                scope={"retrieval_mode": "bounded"},
            )
            replay = app.start_admin_job_import(
                requested_by="admin-fixture",
                idempotency_key="audit-idempotency-1",
                source_ids=["n26_greenhouse"],
                scope={"retrieval_mode": "custom", "max_jobs": 2},
            )
            self.assertEqual(first["import_id"], replay["import_id"])
            events = app.list_admin_job_import_history(import_id=first["import_id"])
            self.assertEqual([event["event_type"] for event in events], ["import_queued"])


if __name__ == "__main__":
    unittest.main()
