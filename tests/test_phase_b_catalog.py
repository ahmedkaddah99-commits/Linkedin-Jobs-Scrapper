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
from backend.connectors.bounded_probe import fetch_bounded_probe


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
    def test_normalization_keeps_listing_records_and_reports_missing_apply_routes(self):
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
                {
                    "id": "listing-only",
                    "title": "Operations Coordinator",
                    "url": "https://boards.greenhouse.io/n26/jobs/listing-only",
                },
            ],
            target,
        )
        self.assertEqual([job["job_id"] for job in result["accepted"]], ["accepted", "quick", "listing-only"])
        self.assertEqual(
            {item["reason"] for item in result["rejected"]},
            {"unsupported_application_method"},
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
            self.assertEqual(report["metrics"]["request_count"], 1)
            self.assertEqual(report["metrics"]["direct_proxy_mode"], {"direct": 1})
            self.assertEqual(report["rejection_reasons"], {"unsupported_application_method": 1})
            self.assertTrue(report["cycle"]["publication_id"].startswith("acq_staging_"))
            self.assertEqual(app.get_public_acquisition_catalog()["freshness"], "unpublished")
            staging = app.get_staging_acquisition_catalog()
            self.assertEqual(staging["freshness"], "staging")
            self.assertEqual(staging["total"], 1)
            self.assertEqual(staging["jobs"][0]["company"], "N26")
            self.assertEqual(staging["jobs"][0]["apply_url"], "")
            self.assertEqual(
                staging["jobs"][0]["canonical_url"],
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

    def test_source_ids_aliases_cross_source_duplicate_replay_and_immutable_versions(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            store = app.repositories.acquisition_store
            targets = [
                {
                    "target_id": "acme-source-a",
                    "target_kind": "employer_career_site",
                    "display_name": "Acme A",
                    "canonical_company_name": "Acme",
                    "canonical_target_url": "https://jobs.acme.example/a",
                    "request_url": "https://jobs.acme.example/a",
                    "official_employer_hosts": ["jobs.acme.example"],
                    "enabled": True,
                    "config": {"absence_grace_attempts": 2},
                },
                {
                    "target_id": "acme-source-b",
                    "target_kind": "employer_career_site",
                    "display_name": "Acme B",
                    "canonical_company_name": "Acme",
                    "canonical_target_url": "https://careers.acme.example/b",
                    "request_url": "https://careers.acme.example/b",
                    "official_employer_hosts": ["careers.acme.example"],
                    "enabled": True,
                    "config": {"absence_grace_attempts": 2},
                },
            ]
            store.ensure_targets(targets)

            def ingest(cycle_key, target, job):
                cycle = store.claim_due_cycle(window_key=cycle_key, lease_owner="fixture", scheduled_at=cycle_key)
                store.ensure_cycle_tasks(cycle["cycle_id"], [{**target, "enabled": True}])
                task = store.claim_next_task(cycle_id=cycle["cycle_id"], lease_owner="fixture")
                first = store.ingest_snapshot(
                    cycle_id=cycle["cycle_id"],
                    task_id=task["task_id"],
                    target_id=target["target_id"],
                    jobs=[job],
                    complete_snapshot=True,
                    valid_snapshot=True,
                )
                replay = store.ingest_snapshot(
                    cycle_id=cycle["cycle_id"],
                    task_id=task["task_id"],
                    target_id=target["target_id"],
                    jobs=[job],
                    complete_snapshot=True,
                    valid_snapshot=True,
                )
                return first, replay

            first_job = {
                "job_id": "acme-a-1",
                "title": "Operations Analyst",
                "location": "Berlin",
                "url": "https://jobs.acme.example/a/1",
                "apply_link": "https://jobs.acme.example/a/1/apply",
                "description": "Operate reporting systems.",
            }
            second_job = {
                **first_job,
                "job_id": "acme-b-9",
                "url": "https://careers.acme.example/b/9",
                "apply_link": "https://careers.acme.example/b/9/apply",
            }
            ingest("acme-a-1", targets[0], first_job)
            ingest("acme-b-1", targets[1], second_job)

            with store._connect() as connection:
                counts = {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "canonical_jobs",
                        "canonical_job_url_aliases",
                        "canonical_job_external_ids",
                        "job_source_observations",
                        "job_source_observation_relationships",
                        "job_posting_versions",
                    )
                }
                version_id = connection.execute(
                    "SELECT version_id FROM job_posting_versions LIMIT 1"
                ).fetchone()[0]

            self.assertEqual(counts["canonical_jobs"], 1)
            self.assertEqual(counts["canonical_job_url_aliases"], 2)
            self.assertEqual(counts["canonical_job_external_ids"], 2)
            self.assertEqual(counts["job_source_observations"], 2)
            self.assertEqual(counts["job_source_observation_relationships"], 1)
            self.assertEqual(counts["job_posting_versions"], 2)
            with store._connect() as connection:
                with self.assertRaisesRegex(Exception, "immutable"):
                    connection.execute(
                        "UPDATE job_posting_versions SET title='mutated' WHERE version_id=?",
                        (version_id,),
                    )

    def test_source_aware_absence_grace_keeps_cross_source_job_active_then_closes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            store = app.repositories.acquisition_store
            targets = [
                {
                    "target_id": "source-a",
                    "target_kind": "employer_career_site",
                    "display_name": "Source A",
                    "canonical_company_name": "Acme",
                    "canonical_target_url": "https://a.acme.example",
                    "request_url": "https://a.acme.example",
                    "official_employer_hosts": ["a.acme.example"],
                    "enabled": True,
                    "config": {"absence_grace_attempts": 2},
                },
                {
                    "target_id": "source-b",
                    "target_kind": "employer_career_site",
                    "display_name": "Source B",
                    "canonical_company_name": "Acme",
                    "canonical_target_url": "https://b.acme.example",
                    "request_url": "https://b.acme.example",
                    "official_employer_hosts": ["b.acme.example"],
                    "enabled": True,
                    "config": {"absence_grace_attempts": 2},
                },
            ]
            store.ensure_targets(targets)

            def cycle(key, target, jobs, valid=True):
                item = store.claim_due_cycle(window_key=key, lease_owner="fixture", scheduled_at=key)
                store.ensure_cycle_tasks(item["cycle_id"], [{**target, "enabled": True}])
                task = store.claim_next_task(cycle_id=item["cycle_id"], lease_owner="fixture")
                store.ingest_snapshot(
                    cycle_id=item["cycle_id"], task_id=task["task_id"], target_id=target["target_id"],
                    jobs=jobs, complete_snapshot=valid, valid_snapshot=valid,
                )

            job = {
                "job_id": "a-1", "title": "Operations Analyst", "location": "Berlin",
                "url": "https://a.acme.example/1", "apply_link": "https://a.acme.example/1/apply",
            }
            cycle("state-a-1", targets[0], [job])
            cycle("state-b-1", targets[1], [{**job, "job_id": "b-1", "url": "https://b.acme.example/1", "apply_link": "https://b.acme.example/1/apply"}])
            cycle("state-a-2", targets[0], [])
            with store._connect() as connection:
                lifecycle = connection.execute("SELECT lifecycle_state FROM canonical_jobs").fetchone()[0]
            self.assertEqual(lifecycle, "active")
            cycle("state-b-2", targets[1], [])
            with store._connect() as connection:
                lifecycle = connection.execute("SELECT lifecycle_state FROM canonical_jobs").fetchone()[0]
            self.assertEqual(lifecycle, "stale")
            cycle("state-a-3", targets[0], [])
            cycle("state-b-3", targets[1], [])
            with store._connect() as connection:
                lifecycle = connection.execute("SELECT lifecycle_state FROM canonical_jobs").fetchone()[0]
            self.assertEqual(lifecycle, "closed")

    def test_empty_direct_probe_does_not_escalate_or_call_proxy(self):
        calls = []

        class EmptyResponse:
            status_code = 200
            text = "Welcome to the company"
            url = "https://example.org/about"

        def requester(url, **kwargs):
            calls.append((url, kwargs))
            return EmptyResponse()

        result = fetch_bounded_probe("https://example.org/about", requester=requester)
        self.assertEqual(result["jobs"], [])
        self.assertFalse(result["credible_evidence"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["allow_redirects"], False)

    def test_credible_empty_listing_counts_as_zero_yield_not_productive(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_backend(Path(temporary_directory), storage_backend="sqlite")
            app.repositories.config_store.set_value("acquisition.phase_a.kill_switch", False)
            app.repositories.config_store.set_value("acquisition.phase_b.controlled_validation_enabled", True)

            def requester(url, **kwargs):
                return _Response(url, {"jobs": []})

            app._acquisition_scheduler.requester = requester
            report = app.validate_phase_b_target("n26_greenhouse", validation_key="empty-ats-1")
            target = report["targets"][0]
            self.assertEqual(target["consecutive_zero_yield_attempts"], 1)
            self.assertEqual(target["last_productive_at"], "")


if __name__ == "__main__":
    unittest.main()
