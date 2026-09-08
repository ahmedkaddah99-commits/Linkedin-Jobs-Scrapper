from __future__ import annotations

import json
import os
import socket
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.bootstrap import create_backend
from backend.api.routes.enrichment_admin import _handle_get, _handle_post
from backend.api.routes.registry import ApiRouteContext
from backend.database.connection import database_session
from backend.enrichment.contracts import ProviderResult, ProviderResultState
from backend.enrichment.operations import EnrichmentOperationService
from backend.enrichment.providers import FixturePlaceProvider
from backend.domain.models import utc_now_iso
from tests.test_phase_f_company_profiles import _seed_catalog


class _RetryOnceProvider:
    def __init__(self):
        self.calls = 0
        self.delegate = FixturePlaceProvider()

    def metadata(self):
        return self.delegate.metadata()

    def capability(self, request):
        return self.delegate.capability(request)

    def resolve(self, request, context):
        self.calls += 1
        if self.calls == 1:
            return ProviderResult(state=ProviderResultState.RETRYABLE_ERROR, warnings=("fixture_retry",))
        return self.delegate.resolve(request, context)


class EnrichmentOperationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        os.environ.update(
            {
                "RUNR_TEST_MODE": "1",
                "RUNR_ENV": "test",
                "DATABASE_BACKEND": "sqlite",
                "TURSO_DATABASE_URL": "",
                "TURSO_AUTH_TOKEN": "",
                "OBJECT_STORAGE_BACKEND": "local",
            }
        )
        self.app = create_backend(Path(self.tempdir.name), storage_backend="sqlite", test_mode=True)
        _seed_catalog(self.app)
        self.store = self.app._enrichment_operation_service
        assert isinstance(self.store, EnrichmentOperationService)
        self.app.repositories.acquisition_store._run_transaction(
            lambda connection: connection.execute(
                """
                INSERT INTO admin_job_imports (
                    import_id, idempotency_key, status, cycle_id, created_at, updated_at
                ) VALUES (?, ?, 'completed', ?, ?, ?)
                """,
                ("import-a", "import-key-a", "cycle-f", utc_now_iso(), utc_now_iso()),
            )
        )

    def _import_plan(self, *, provider: str = "fixture", key: str = "import-plan"):
        return self.store.create_plan(
            requested_by="admin-1",
            scope_type="import",
            scope_id="import-a",
            target_type="job",
            selected_fields=["place"],
            provider_id=provider,
            selected_records=[
                {
                    "target_id": "job-a",
                    "input": {"display": "Paris, France", "country_code": "FR"},
                    "existing_normalized": {"place": {"city": "Old Paris"}},
                }
            ],
            query_snapshot={"query": "Paris", "captured_at": "2026-08-12T00:00:00+00:00"},
            exclusions=["already_confirmed"],
            policy_version="policy_test_v1",
            rule_version="rules_test_v1",
            snapshot_version="snapshot_test_v1",
            expected_cost=0.25,
            idempotency_key=key,
        )

    def test_plan_run_result_is_durable_idempotent_and_network_free(self):
        plan = self._import_plan()
        repeated_plan = self._import_plan()
        self.assertEqual(plan["plan_id"], repeated_plan["plan_id"])
        self.assertEqual(plan["scope_type"], "import")
        self.assertEqual(plan["scope_id"], "import-a")
        self.assertEqual(plan["expected_request_count"], 1)
        self.assertTrue(plan["report_only"])
        self.assertEqual(plan["query_snapshot"]["selected_record_ids"], ["job-a"])

        run = self.store.start_run(plan_id=plan["plan_id"], requested_by="admin-1", idempotency_key="run-key")
        repeated_run = self.store.start_run(plan_id=plan["plan_id"], requested_by="admin-1", idempotency_key="run-key")
        self.assertEqual(run["run_id"], repeated_run["run_id"])
        self.assertEqual(run["status"], "pending")

        with patch.object(socket, "socket", side_effect=AssertionError("network is forbidden")):
            result = self.store.process_run(run["run_id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["requests_used"], 0)
        detailed = self.store.get_result(run["run_id"])
        self.assertEqual(len(detailed["proposals"]), 1)
        self.assertEqual(detailed["proposals"][0]["target_id"], "job-a")
        self.assertEqual(detailed["proposals"][0]["current_state"], "proposed")

        budgets = self.store.list_provider_budgets()
        self.assertTrue(budgets)
        self.assertTrue(all(int(item["max_requests"]) == 0 for item in budgets))

    def test_company_scope_cannot_cross_company_and_legacy_batch_boundary_is_closed(self):
        plan = self.store.create_plan(
            requested_by="admin-1",
            scope_type="company",
            scope_id="company-a",
            target_type="company",
            selected_fields=["website"],
            provider_id="fixture",
            selected_records=[{"target_id": "company-a", "input": {"name": "Example", "domain": "example.com"}}],
            idempotency_key="company-plan",
        )
        self.assertEqual(plan["scope_type"], "company")
        self.assertEqual(plan["selected_records"][0]["target_id"], "company-a")
        with self.assertRaises(ValueError):
            self.store.create_plan(
                requested_by="admin-1",
                scope_type="company",
                scope_id="company-a",
                target_type="company",
                selected_fields=["website"],
                provider_id="fixture",
                selected_records=[{"target_id": "company-b", "input": {"name": "Other", "domain": "example.com"}}],
                idempotency_key="company-cross-boundary",
            )
        with self.assertRaises(ValueError):
            self.app.run_admin_company_enrichment()

    def test_review_is_append_only_and_does_not_change_publication(self):
        with database_session(self.app.repositories.acquisition_store.db_path) as connection:
            before_head = connection.execute(
                "SELECT publication_id FROM acquisition_publication_head WHERE head_id=1"
            ).fetchone()["publication_id"]
            before_observation = connection.execute(
                "SELECT payload_json FROM job_posting_versions WHERE version_id='version-job-a'"
            ).fetchone()["payload_json"]
            before_evidence = int(
                connection.execute("SELECT COUNT(*) AS count FROM enrichment_evidence").fetchone()["count"]
            )

        plan = self._import_plan(key="review-plan")
        run = self.store.start_run(plan_id=plan["plan_id"], requested_by="admin-1", idempotency_key="review-run")
        self.store.process_run(run["run_id"])
        proposal_id = self.store.get_result(run["run_id"])["proposals"][0]["proposal_id"]
        accepted = self.store.review_proposal(
            proposal_id, action="accept", reviewer_id="reviewer-1", reason="verified", idempotency_key="review-1"
        )
        self.assertEqual(accepted["current_state"], "accepted")
        rejected = self.store.review_proposal(
            proposal_id, action="reject", reviewer_id="reviewer-2", reason="not sufficient", idempotency_key="review-2"
        )
        self.assertEqual(rejected["current_state"], "rejected")
        undone = self.store.review_proposal(
            proposal_id, action="undo", reviewer_id="reviewer-1", reason="undo review", idempotency_key="review-3"
        )
        self.assertEqual(undone["current_state"], "proposed")

        with database_session(self.app.repositories.acquisition_store.db_path) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT publication_id FROM acquisition_publication_head WHERE head_id=1"
                ).fetchone()["publication_id"],
                before_head,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT payload_json FROM job_posting_versions WHERE version_id='version-job-a'"
                ).fetchone()["payload_json"],
                before_observation,
            )
            self.assertEqual(
                int(connection.execute("SELECT COUNT(*) AS count FROM enrichment_evidence").fetchone()["count"]),
                before_evidence + 1,
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE enrichment_field_proposals SET field_path='changed' WHERE proposal_id=?", (proposal_id,)
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM enrichment_field_proposals WHERE proposal_id=?", (proposal_id,))

        self.assertEqual(len(undone["actions"]), 3)

    def test_active_lease_blocks_a_second_worker(self):
        plan = self._import_plan(key="lease-plan")
        run = self.store.start_run(plan_id=plan["plan_id"], requested_by="admin-1", idempotency_key="lease-run")
        claimed = self.store._claim_run(run["run_id"], "worker-a", lease_seconds=300)
        self.assertEqual(claimed["status"], "running")
        self.assertEqual(claimed["lease_owner"], "worker-a")

        blocked = self.store.process_run(run["run_id"], worker_id="worker-b")
        self.assertEqual(blocked["status"], "running")
        self.assertEqual(blocked["items"][0]["attempt_state"], "pending")

        completed = self.store.process_run(run["run_id"], worker_id="worker-a")
        self.assertEqual(completed["status"], "completed")

    def test_retry_pause_cancel_and_capability_states(self):
        plan = self._import_plan(key="retry-plan")
        self.store.provider_overrides["fixture"] = _RetryOnceProvider()
        run = self.store.start_run(
            plan_id=plan["plan_id"],
            requested_by="admin-1",
            idempotency_key="retry-run",
            retry_policy={"max_attempts": 2},
        )
        result = self.store.process_run(run["run_id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.store.get_result(run["run_id"])["items"][0]["retry_count"], 2)

        paused_plan = self._import_plan(key="paused-plan")
        paused_run = self.store.start_run(
            plan_id=paused_plan["plan_id"], requested_by="admin-1", idempotency_key="paused-run"
        )
        self.assertEqual(self.store.pause_run(paused_run["run_id"], actor_id="admin-1")["status"], "paused")
        self.assertEqual(self.store.process_run(paused_run["run_id"])["status"], "paused")

        cancelled_plan = self._import_plan(provider="null", key="cancel-plan")
        cancelled_run = self.store.start_run(
            plan_id=cancelled_plan["plan_id"], requested_by="admin-1", idempotency_key="cancel-run"
        )
        cancelled = self.store.cancel_run(cancelled_run["run_id"], actor_id="admin-1", reason="operator requested")
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.store.get_result(cancelled["run_id"])["items"][0]["attempt_state"], "cancelled")

        capabilities = self.store.capabilities(target_type="company", selected_fields=["website"])
        by_id = {item["provider_id"]: item for item in capabilities["capabilities"]}
        self.assertEqual(by_id["fixture"]["status"], "enabled")
        self.assertEqual(by_id["official_website"]["status"], "blocked_by_policy")
        self.store.configure_provider_budget(
            "fixture", max_requests=1, max_cost_units=1, enabled=True, actor_id="admin-1"
        )
        self.store._transaction(
            lambda connection: connection.execute(
                "UPDATE enrichment_provider_budgets SET requests_used=1 WHERE provider_id='fixture'"
            )
        )
        self.assertEqual(
            {item["provider_id"]: item for item in self.store.capabilities()["capabilities"]}["fixture"]["status"],
            "budget_exhausted",
        )

    def test_enrichment_route_rejects_unauthorized_access(self):
        class UnauthorizedHandler:
            def _require_admin(self):
                raise PermissionError("Admin access required.")

            def _send_json(self, *args, **kwargs):
                raise AssertionError("unauthorized route must not send a success response")

            def _send_error(self, *args, **kwargs):
                raise AssertionError("authorization is enforced before route handling")

        context = ApiRouteContext(
            application=self.app,
            handler=UnauthorizedHandler(),
            method="GET",
            segments=("admin", "enrichment", "capabilities"),
            query={},
        )
        with self.assertRaises(PermissionError):
            _handle_get(context)

    def test_admin_plan_route_is_available_and_report_only(self):
        class AdminHandler:
            def __init__(self):
                self.payload = {
                    "scope_type": "import",
                    "import_id": "import-a",
                    "target_type": "job",
                    "selected_fields": ["place"],
                    "provider_id": "fixture",
                    "selected_records": [
                        {"target_id": "job-a", "input": {"display": "Paris, France", "country_code": "FR"}}
                    ],
                    "idempotency_key": "route-plan",
                }
                self.sent = None

            def _require_admin(self):
                return (type("User", (), {"user_id": "admin-route"})(), object())

            def _read_json_body(self):
                return self.payload

            def _send_json(self, value, status=200, **kwargs):
                self.sent = (value, status)

            def _send_error(self, status, code, message, **kwargs):
                raise AssertionError(f"unexpected route error {status} {code}: {message}")

        handler = AdminHandler()
        context = ApiRouteContext(
            application=self.app,
            handler=handler,
            method="POST",
            segments=("admin", "enrichment", "plans"),
            query={},
        )
        self.assertTrue(_handle_post(context))
        self.assertEqual(handler.sent[1], 201)
        self.assertTrue(handler.sent[0]["report_only"])
        self.assertEqual(handler.sent[0]["scope_id"], "import-a")


if __name__ == "__main__":
    unittest.main()
