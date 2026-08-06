import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import requests

from backend.acquisition.manifest import load_phase_a_manifest
from backend.acquisition.phase_b import normalize_phase_b_jobs
from backend.api.routes import build_route_registry
from backend.api.routes.registry import ApiRouteContext
from backend.bootstrap import create_backend


class _Response:
    def __init__(self, url, payload):
        self.url = url
        self.status_code = 200
        self._payload = payload
        self.text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Handler:
    def __init__(self, body=None):
        self.body = body or {}
        self.payload = None
        self.admin_calls = 0

    def _require_admin(self):
        self.admin_calls += 1
        return object(), object()

    def _require_identity(self):
        return object(), object()

    def _read_json_body(self):
        return self.body

    def _send_json(self, payload, status=200, *, headers=None):
        self.payload = (status, payload)


class PhaseBCatalogTests(unittest.TestCase):
    def test_normalization_rejects_unverified_and_non_direct_application_methods(self):
        target = next(item for item in load_phase_a_manifest() if item["target_id"] == "n26_greenhouse")
        result = normalize_phase_b_jobs(
            [
                {
                    "id": "accepted",
                    "title": "Operations Analyst",
                    "absolute_url": "https://boards.greenhouse.io/n26/jobs/accepted",
                    "location": {"name": "Berlin"},
                },
                {
                    "id": "quick",
                    "title": "Operations Analyst",
                    "absolute_url": "https://example.invalid/quick",
                },
                {
                    "id": "email",
                    "title": "Operations Coordinator",
                    "absolute_url": "https://boards.greenhouse.io/n26/jobs/email",
                    "application_method": "email-only",
                },
            ],
            target,
        )
        self.assertEqual([job["job_id"] for job in result["accepted"]], ["accepted"])
        self.assertEqual(
            {item["reason"] for item in result["rejected"]},
            {"unverified_direct_apply_destination", "unsupported_application_method"},
        )

    def test_single_target_validation_is_durable_and_staging_only(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            app.repositories.config_store.set_value("acquisition.phase_a.kill_switch", False)
            app.repositories.config_store.set_value("acquisition.phase_b.controlled_validation_enabled", True)
            requests = []

            def requester(url, **kwargs):
                requests.append(url)
                return _Response(
                    url,
                    {
                        "jobs": [
                            {
                                "id": "n26-1",
                                "title": "Operations Analyst",
                                "absolute_url": "https://boards.greenhouse.io/n26/jobs/n26-1",
                                "location": {"name": "Berlin"},
                                "content": "Operate reporting systems.",
                            },
                            {
                                "id": "n26-quick",
                                "title": "Quick Apply Analyst",
                                "absolute_url": "https://boards.greenhouse.io/n26/jobs/n26-quick",
                                "content": "Quick Apply only.",
                            },
                        ]
                    },
                )

            app._acquisition_scheduler.requester = requester
            report = app.validate_phase_b_target("n26_greenhouse", validation_key="phase-b-test-1")

            self.assertEqual(report["cycle"]["status"], "completed")
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0], "https://boards-api.greenhouse.io/v1/boards/n26/jobs?content=true")
            self.assertEqual(report["source_metrics"][0]["request_url"], requests[0])
            self.assertEqual(report["source_metrics"][0]["jobs_published"], 1)
            self.assertEqual(report["source_metrics"][0]["cost_per_new_published_job"], 0)
            self.assertTrue(report["cycle"]["publication_id"].startswith("acq_staging_"))
            self.assertEqual(app.get_public_acquisition_catalog()["freshness"], "unpublished")
            staging = app.get_staging_acquisition_catalog()
            self.assertEqual(staging["freshness"], "staging")
            self.assertEqual(staging["total"], 1)
            self.assertEqual(staging["jobs"][0]["company"], "N26")
            self.assertEqual(
                staging["jobs"][0]["apply_url"],
                "https://boards.greenhouse.io/n26/jobs/n26-1",
            )

            with app.repositories.acquisition_store._connect() as connection:
                request_count = connection.execute("SELECT COUNT(*) FROM acquisition_requests").fetchone()[0]
                rejection_count = connection.execute("SELECT COUNT(*) FROM acquisition_job_rejections").fetchone()[0]
                canonical_count = connection.execute("SELECT COUNT(*) FROM canonical_jobs").fetchone()[0]
            self.assertEqual(request_count, 1)
            self.assertEqual(rejection_count, 1)
            self.assertEqual(canonical_count, 1)

            app.repositories.config_store.set_value("acquisition.phase_b.promotion_enabled", True)
            app.promote_staging_acquisition_catalog(staging["publication"]["publication_id"])
            self.assertEqual(app.get_public_acquisition_catalog()["total"], 1)

    def test_cross_source_dedupe_and_closed_repost_lifecycle(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            store = app.repositories.acquisition_store
            manifest = load_phase_a_manifest()
            target = next(item for item in manifest if item["target_id"] == "n26_greenhouse")
            store.ensure_targets(manifest)

            def run_cycle(cycle_key, jobs):
                cycle = store.claim_due_cycle(window_key=cycle_key, lease_owner="test", scheduled_at=cycle_key)
                task_target = {**target, "enabled": True}
                store.ensure_cycle_tasks(cycle["cycle_id"], [task_target])
                task = store.claim_next_task(cycle_id=cycle["cycle_id"], lease_owner="test")
                store.ingest_snapshot(
                    cycle_id=cycle["cycle_id"],
                    task_id=task["task_id"],
                    target_id=target["target_id"],
                    jobs=jobs,
                    complete_snapshot=True,
                    valid_snapshot=True,
                )
                return cycle["cycle_id"]

            first = {
                "job_id": "source-a",
                "title": "Operations Analyst",
                "url": "https://boards.greenhouse.io/n26/jobs/source-a",
                "location": "Berlin",
                "description": "Same role",
            }
            second = {**first, "job_id": "source-b", "url": "https://jobs.lever.co/n26/source-b"}
            run_cycle("cycle-a", [first])
            run_cycle("cycle-b", [second])
            for key in ("cycle-c", "cycle-d", "cycle-e"):
                run_cycle(key, [])
            reposted = {**first, "job_id": "source-c", "url": "https://boards.greenhouse.io/n26/jobs/source-c"}
            run_cycle("cycle-f", [reposted])

            with store._connect() as connection:
                canonical = connection.execute("SELECT canonical_job_id, lifecycle_state FROM canonical_jobs").fetchall()
                observations = connection.execute("SELECT COUNT(*) FROM job_source_observations").fetchone()[0]
                versions = connection.execute("SELECT COUNT(*) FROM job_posting_versions").fetchone()[0]
                relationships = connection.execute(
                    "SELECT COUNT(*) FROM canonical_job_relationships WHERE relationship_type='repost'"
                ).fetchone()[0]
            self.assertEqual(len(canonical), 2)
            self.assertEqual(sorted(row["lifecycle_state"] for row in canonical), ["closed", "reposted"])
            self.assertEqual(observations, 3)
            self.assertEqual(versions, 3)
            self.assertEqual(relationships, 1)

    def test_phase_b_validation_route_is_admin_only_and_never_a_user_route(self):
        registry = build_route_registry()
        application = Mock()
        handler = _Handler({"validation_key": "fixture"})
        context = ApiRouteContext(
            application=application,
            handler=handler,
            method="POST",
            segments=("admin", "acquisition", "targets", "n26_greenhouse", "validate"),
            query={},
        )
        self.assertTrue(registry.dispatch(context, auth_required=True))
        application.validate_phase_b_target.assert_called_once_with("n26_greenhouse", validation_key="fixture")
        self.assertFalse(
            registry.dispatch(
                ApiRouteContext(
                    application=application,
                    handler=handler,
                    method="POST",
                    segments=("personalized-jobs", "validate"),
                    query={},
                ),
                auth_required=True,
            )
        )

    def test_source_failure_keeps_previous_valid_public_catalog(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            app.repositories.config_store.set_value("acquisition.phase_a.kill_switch", False)
            app.repositories.config_store.set_value("acquisition.phase_b.controlled_validation_enabled", True)

            def successful_request(url, **kwargs):
                return _Response(
                    url,
                    {
                        "jobs": [
                            {
                                "id": "stable-1",
                                "title": "Operations Analyst",
                                "absolute_url": "https://boards.greenhouse.io/n26/jobs/stable-1",
                                "location": {"name": "Berlin"},
                            }
                        ]
                    },
                )

            app._acquisition_scheduler.requester = successful_request
            first = app.validate_phase_b_target("n26_greenhouse", validation_key="public-head-1")
            staging_id = first["cycle"]["publication_id"]
            app.repositories.config_store.set_value("acquisition.phase_b.promotion_enabled", True)
            app.promote_staging_acquisition_catalog(staging_id)
            self.assertEqual(app.get_public_acquisition_catalog()["total"], 1)

            def failed_request(url, **kwargs):
                raise requests.RequestException("source unavailable")

            app._acquisition_scheduler.requester = failed_request
            failed = app.validate_phase_b_target("n26_greenhouse", validation_key="public-head-2")
            self.assertEqual(failed["cycle"]["status"], "degraded")
            self.assertEqual(failed["cycle"]["publication_id"], "")
            catalog = app.get_public_acquisition_catalog()
            self.assertEqual(catalog["total"], 1)
            self.assertEqual(catalog["freshness"], "valid")
            with app.repositories.acquisition_store._connect() as connection:
                request = connection.execute(
                    "SELECT status FROM acquisition_requests ORDER BY started_at DESC LIMIT 1"
                ).fetchone()
                task = connection.execute(
                    "SELECT status FROM acquisition_tasks ORDER BY started_at DESC LIMIT 1"
                ).fetchone()
            self.assertEqual(request["status"], "failed")
            self.assertEqual(task["status"], "failed")


if __name__ == "__main__":
    unittest.main()
