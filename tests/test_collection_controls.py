from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.acquisition.collection_controls import collection_metadata, infer_stop_reason
from backend.acquisition.manifest import load_phase_a_manifest
from backend.bootstrap import create_backend
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


def _greenhouse_job(job_id: str) -> dict[str, object]:
    return {
        "id": job_id,
        "title": f"Operations Analyst {job_id}",
        "absolute_url": f"https://boards.greenhouse.io/n26/jobs/{job_id}",
        "location": {"name": "Berlin, Germany"},
        "content": "Operate reliable reporting systems.",
    }


class CollectionControlsTests(unittest.TestCase):


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


if __name__ == "__main__":
    unittest.main()
