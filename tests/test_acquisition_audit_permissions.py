from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.acquisition.audit import redact_acquisition_audit_payload
from backend.acquisition.permissions import (
    ACQUISITION_PERMISSIONS,
    default_acquisition_permissions_for_role,
    has_acquisition_permission,
    require_acquisition_permission,
)
from backend.api.routes import build_route_registry
from backend.api.routes.registry import ApiRouteContext
from backend.database.initialization import initialize_database
from backend.domain.models import ROLE_ADMIN, ROLE_EDITOR, ROLE_REVIEWER, ROLE_VIEWER, TOKEN_SCOPE_ADMIN
from backend.repositories.sqlite_acquisition_audit import SqliteAcquisitionAuditStore
from backend.security.auth import build_token_scope_set
from backend.application.services import BackendApplication


class AcquisitionAuditPermissionsTests(unittest.TestCase):
    def _store(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "backend.sqlite3"
        initialize_database(path)
        return SqliteAcquisitionAuditStore(path), path

    def test_every_permission_and_existing_admin_compatibility(self):
        self.assertEqual(len(ACQUISITION_PERMISSIONS), 11)
        self.assertTrue(
            all(
                has_acquisition_permission(role=ROLE_ADMIN, scopes=[], permission=permission)
                for permission in ACQUISITION_PERMISSIONS
            )
        )
        self.assertTrue(
            has_acquisition_permission(
                role=ROLE_VIEWER,
                scopes=[TOKEN_SCOPE_ADMIN],
                permission="acquisition.publish",
            )
        )
        self.assertFalse(
            has_acquisition_permission(
                role=ROLE_VIEWER,
                scopes=["acquisition.view"],
                permission="acquisition.publish",
            )
        )
        self.assertTrue(set(ACQUISITION_PERMISSIONS).issubset(set(build_token_scope_set(ROLE_ADMIN))))
        for permission in ACQUISITION_PERMISSIONS:
            with self.assertRaises(PermissionError):
                require_acquisition_permission(role="unassigned", scopes=[], permission=permission)

    def test_redaction_removes_secrets_credentials_tokens_and_personal_data(self):
        payload = redact_acquisition_audit_payload(
            {
                "provider": "greenhouse",
                "api_key": "fixture-api-key",
                "credentials": {"username": "operator", "password": "pw"},
                "request": "Authorization=Bearer abc-token",
                "contact": "owner@example.com +49 170 1234567",
                "nested": [{"source_text": "private posting text"}],
            }
        )
        serialized = repr(payload)
        self.assertNotIn("fixture-api-key", serialized)
        self.assertNotIn("abc-token", serialized)
        self.assertNotIn("owner@example.com", serialized)
        self.assertNotIn("1234567", serialized)
        self.assertNotIn("private posting text", serialized)
        self.assertEqual(payload["provider"], "greenhouse")

    def test_role_matrix_and_no_secret_in_serialized_event_payload(self):
        self.assertEqual(
            default_acquisition_permissions_for_role(ROLE_VIEWER),
            frozenset({"acquisition.view", "acquisition.preview"}),
        )
        self.assertIn("acquisition.review", default_acquisition_permissions_for_role(ROLE_REVIEWER))
        self.assertIn("acquisition.collect", default_acquisition_permissions_for_role(ROLE_EDITOR))
        store, path = self._store()
        store.append_event(
            event="provider_changed",
            payload={"api_key": "secret-value", "token": "access-value", "operator_email": "a@example.com"},
        )
        connection = sqlite3.connect(path)
        try:
            serialized = connection.execute("SELECT payload_json FROM acquisition_audit_events").fetchone()[0]
        finally:
            connection.close()
        self.assertNotIn("secret-value", serialized)
        self.assertNotIn("access-value", serialized)
        self.assertNotIn("a@example.com", serialized)

    def test_query_filters_pagination_and_entity_timeline(self):
        store, _ = self._store()
        store.append_event(
            event="import_started",
            actor="admin-1",
            entity_type="import",
            entity_id="import-1",
            operation_id="operation-1",
            occurred_at="2026-08-12T10:00:00+00:00",
        )
        store.append_event(
            event="review_decision",
            actor="reviewer-1",
            entity_type="job",
            entity_id="job-1",
            operation_id="operation-1",
            occurred_at="2026-08-12T10:01:00+00:00",
        )
        store.append_event(
            event="publication_published",
            actor="admin-1",
            entity_type="job",
            entity_id="job-1",
            operation_id="operation-2",
            occurred_at="2026-08-12T10:02:00+00:00",
        )
        page = store.query_events(
            actor="admin-1",
            entity_type="job",
            limit=1,
            offset=0,
            occurred_from="2026-08-12T10:00:00+00:00",
            occurred_to="2026-08-12T11:00:00+00:00",
        )
        self.assertEqual(page["pagination"], {"limit": 1, "offset": 0, "returned": 1, "total": 1, "has_more": False})
        self.assertEqual(page["events"][0]["event"], "publication_published")
        timeline = store.entity_timeline("job", "job-1", limit=10)
        self.assertEqual([item["event"] for item in timeline["events"]], ["publication_published", "review_decision"])

    def test_append_only_and_hash_chain(self):
        store, path = self._store()
        first = store.append_event(event="import_started", entity_type="import", entity_id="i-1")
        second = store.append_event(event="review_decision", entity_type="import", entity_id="i-1")
        self.assertEqual(second["previous_event_hash"], first["event_hash"])
        connection = sqlite3.connect(path)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute(
                    "UPDATE acquisition_audit_events SET event='tampered' WHERE event_id=?", (first["event_id"],)
                )
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute("DELETE FROM acquisition_audit_events WHERE event_id=?", (first["event_id"],))
        finally:
            connection.close()

    def test_legacy_admin_audit_is_bridged(self):
        store, path = self._store()
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                """
                INSERT INTO admin_job_audit_events
                    (event_id, import_id, actor_user_id, event_type, payload_json, created_at)
                VALUES ('legacy-1', 'import-legacy', 'admin-1', 'review_decision',
                        '{"canonical_job_id":"job-legacy","api_key":"must-not-cross"}', '2026-08-12T10:00:00+00:00')
                """
            )
            connection.commit()
        finally:
            connection.close()
        result = store.query_events(entity_type="job", entity_id="job-legacy")
        self.assertEqual(result["pagination"]["total"], 1)
        self.assertEqual(result["events"][0]["event_id"], "legacy_admin:legacy-1")
        self.assertNotIn("must-not-cross", repr(result["events"][0]))

    def test_publish_route_requires_publish_permission(self):
        class Handler:
            def __init__(self):
                self.permissions = []
                self.payload = None

            def _require_identity(self):
                return {"user_id": "publisher-1"}, object()

            def _require_acquisition_permission(self, permission):
                self.permissions.append(permission)
                if permission != "acquisition.publish":
                    raise PermissionError(permission)
                return {"user_id": "publisher-1"}, object()

            def _read_json_body(self):
                return {"publication_id": "publication-1"}

            def _send_json(self, payload, status=200, *, headers=None):
                self.payload = (status, payload)

        handler = Handler()
        application = Mock()
        application.publish_admin_job_import.return_value = "publication-1"
        context = ApiRouteContext(
            application=application,
            handler=handler,
            method="POST",
            segments=("admin", "acquisition", "publication", "publish"),
            query={},
        )
        self.assertTrue(build_route_registry().dispatch(context, auth_required=True))
        self.assertEqual(handler.permissions, ["acquisition.publish"])

    def test_operation_integration_points_emit_unified_events(self):
        audit_store = Mock()
        events = []
        audit_store.append_event.side_effect = lambda **kwargs: events.append(kwargs)
        acquisition_store = Mock()
        acquisition_store.record_job_review_decision.return_value = {"decision_id": "decision-1"}
        acquisition_store.record_admin_duplicate_decision.return_value = {"decision_id": "duplicate-1"}
        acquisition_store.undo_admin_duplicate_decision.return_value = {"decision_id": "duplicate-2"}
        acquisition_store.create_job_import_preview.return_value = {"publication_id": "publication-1", "total": 1}
        acquisition_store.publish_job_import_preview.return_value = "publication-1"
        acquisition_store.undo_last_job_publication.return_value = {"undone_publication_id": "publication-1"}
        acquisition_store.db_path = "audit-integration.sqlite3"
        app = BackendApplication.__new__(BackendApplication)
        app.repositories = SimpleNamespace(
            acquisition_store=acquisition_store,
            acquisition_audit_store=audit_store,
        )
        app._admin_job_import_service = Mock()
        app._admin_job_import_service.plan_import.return_value = {"plan_id": "plan-1"}
        app._admin_job_import_service.start_import.return_value = {"import_id": "import-1"}
        app._admin_job_import_service.process_next_import.return_value = {
            "import_id": "import-1",
            "status": "completed",
        }
        app._production_rollout_service = Mock()
        app._production_rollout_service.configure.return_value = {"status": "configured"}
        app._production_rollout_service.advance.return_value = {"status": "advanced"}
        with patch.object(
            BackendApplication,
            "run_due_company_enrichment",
            return_value={"status": "completed", "processed": 1},
        ):
            app.plan_admin_job_import(source_ids=["source-1"], scope={})
            app.start_admin_job_import(
                requested_by="actor-1", idempotency_key="op-1", source_ids=["source-1"], scope={}
            )
            app.process_next_admin_job_import(worker_id="worker-1")
            app.decide_admin_review_job(
                canonical_job_id="job-1", import_id="import-1", actor_user_id="reviewer-1", decision="approve"
            )
            app.run_admin_company_enrichment(cycle_key="enrichment-1")
            with patch(
                "backend.acquisition.reprocessing.run_reprocessing",
                return_value={"run_id": "reprocess-1", "status": "completed"},
            ):
                app.run_admin_reprocessing(idempotency_key="reprocess-op")
            app.record_admin_duplicate_decision("cluster-1", actor_user_id="reviewer-1", decision="keep")
            app.undo_admin_duplicate_decision("cluster-1", actor_user_id="reviewer-1")
            app.preview_admin_job_import("import-1", actor_user_id="actor-1")
            app.publish_admin_job_import("publication-1", actor_user_id="actor-1")
            app.undo_admin_job_publication(actor_user_id="actor-1")
            with patch("backend.connectors.ats_expansions.build_capability_snapshots", return_value=[]):
                app.record_admin_connector_capability_snapshots()
            app.configure_production_rollout({"stage": "shadow"})
            app.advance_production_rollout("shadow")

        event_names = {event["event"] for event in events}
        self.assertTrue(
            {
                "import_queued",
                "import_processed",
                "review_decision",
                "enrichment_completed",
                "reprocessing_completed",
                "duplicate_decision",
                "duplicate_decision_undone",
                "publication_preview_created",
                "publication_published",
                "publication_rollback",
                "provider_capabilities_changed",
                "policy_changed",
            }.issubset(event_names),
            event_names,
        )


if __name__ == "__main__":
    unittest.main()
