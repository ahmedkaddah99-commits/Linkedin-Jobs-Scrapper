from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from backend.acquisition.analytics import build_acquisition_analytics, parse_analytics_window
from backend.api.routes import build_route_registry
from backend.api.routes.registry import ApiRouteContext
from backend.database.initialization import initialize_database


class _Handler:
    def __init__(self):
        self.payload = None
        self.permissions = []

    def _require_acquisition_permission(self, permission):
        self.permissions.append(permission)
        return {"user_id": "analytics-admin"}, object()

    def _send_json(self, payload, status=200, *, headers=None):
        self.payload = (status, payload)


class AcquisitionAnalyticsTests(unittest.TestCase):
    def _window(self, *, start="2026-08-05T00:00:00Z", end="2026-08-12T00:00:00Z"):
        return parse_analytics_window(
            start=start,
            end=end,
            timezone_name="Europe/Berlin",
        )

    def test_window_is_timezone_aware_and_bounded(self):
        window = parse_analytics_window(
            range_key="24h",
            timezone_name="Europe/Berlin",
            now=datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(window.start.isoformat(), "2026-08-11T12:00:00+00:00")
        self.assertEqual(window.end.isoformat(), "2026-08-12T12:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "cannot exceed 30 days"):
            parse_analytics_window(
                start="2026-01-01T00:00:00Z",
                end="2026-02-01T00:00:01Z",
                timezone_name="UTC",
            )
        with self.assertRaisesRegex(ValueError, "supported IANA"):
            parse_analytics_window(range_key="7d", timezone_name="Not/AZone")

    def test_empty_database_returns_explicit_unknown_values_without_writes(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "analytics.sqlite3"
            initialize_database(path)
            before_connection = sqlite3.connect(path)
            before = before_connection.execute("SELECT COUNT(*) FROM acquisition_audit_events").fetchone()[0]
            before_connection.close()
            result = build_acquisition_analytics(path, window=self._window())
            after_connection = sqlite3.connect(path)
            after = after_connection.execute("SELECT COUNT(*) FROM acquisition_audit_events").fetchone()[0]
            after_connection.close()

        self.assertEqual(result["schema_version"], "acquisition_analytics_v1")
        self.assertTrue(result["read_only"])
        self.assertEqual(result["summary"]["observations_received"], 0)
        self.assertIsNone(result["quality"]["resolved_count"])
        self.assertIsNone(result["enrichment"]["cache"]["hit"])
        self.assertEqual(before, after)

    def test_aggregates_real_pipeline_rows_without_double_counting_versions(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "analytics.sqlite3"
            initialize_database(path)
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            try:
                connection.executescript(
                    """
                    INSERT INTO acquisition_targets (
                        target_id, target_kind, display_name, canonical_target_url,
                        request_url, connector, policy_version, maturity_state, enabled,
                        created_at, updated_at, last_attempt_at, last_success_at
                    ) VALUES ('source-a', 'official', 'Source A', 'https://example.test/jobs',
                              'https://example.test/jobs', 'fixture', 'v1', 'ready', 1,
                              '2026-08-01T00:00:00+00:00', '2026-08-11T00:00:00+00:00',
                              '2026-08-11T00:00:00+00:00', '2026-08-11T00:00:00+00:00');
                    INSERT INTO acquisition_cycles (
                        cycle_id, window_key, status, scheduled_at, started_at, completed_at,
                        created_at, updated_at, jobs_observed, jobs_new, jobs_updated
                    ) VALUES ('cycle-a', 'window-a', 'completed', '2026-08-11T00:00:00+00:00',
                              '2026-08-11T00:01:00+00:00', '2026-08-11T00:02:00+00:00',
                              '2026-08-11T00:00:00+00:00', '2026-08-11T00:02:00+00:00', 2, 1, 1);
                    INSERT INTO acquisition_tasks (
                        task_id, cycle_id, target_id, status, complete_snapshot, valid_snapshot,
                        created_at, updated_at, completed_at, jobs_observed, jobs_new, jobs_updated
                    ) VALUES ('task-a', 'cycle-a', 'source-a', 'completed', 1, 1,
                              '2026-08-11T00:00:00+00:00', '2026-08-11T00:02:00+00:00',
                              '2026-08-11T00:02:00+00:00', 2, 1, 1);
                    INSERT INTO acquisition_target_attempts (
                        attempt_id, task_id, cycle_id, target_id, attempt_number, status,
                        request_count, jobs_found, started_at, completed_at
                    ) VALUES ('attempt-a', 'task-a', 'cycle-a', 'source-a', 1, 'completed',
                              1, 2, '2026-08-11T00:01:00+00:00', '2026-08-11T00:02:00+00:00');
                    INSERT INTO acquisition_requests (
                        request_id, idempotency_key, cycle_id, task_id, target_id, request_url,
                        method, mode, request_kind, status, jobs_returned, started_at, completed_at,
                        latency_ms
                    ) VALUES ('request-a', 'request-key-a', 'cycle-a', 'task-a', 'source-a',
                              'https://example.test/jobs', 'GET', 'direct', 'collection', 'completed',
                              2, '2026-08-11T00:01:00+00:00', '2026-08-11T00:01:01+00:00', 100);
                    INSERT INTO canonical_companies (
                        company_id, canonical_name, entity_kind, created_at, updated_at
                    ) VALUES ('company-a', 'Company A', 'employer', '2026-08-10T00:00:00+00:00', '2026-08-10T00:00:00+00:00');
                    INSERT INTO canonical_jobs (
                        canonical_job_id, company_id, identity_key, title, location, lifecycle_state,
                        first_seen_at, last_seen_at, current_version_id, created_at, updated_at
                    ) VALUES ('job-a', 'company-a', 'identity-a', 'Job A', 'Berlin', 'active',
                              '2026-08-10T00:00:00+00:00', '2026-08-11T00:00:00+00:00', 'version-a-2',
                              '2026-08-10T00:00:00+00:00', '2026-08-11T00:00:00+00:00');
                    INSERT INTO job_source_observations (
                        observation_id, canonical_job_id, target_id, cycle_id, task_id, external_job_id,
                        observed_at
                    ) VALUES ('observation-a', 'job-a', 'source-a', 'cycle-a', 'task-a', 'external-a',
                              '2026-08-11T00:01:00+00:00'),
                             ('observation-b', 'job-a', 'source-a', 'cycle-a', 'task-a', 'external-b',
                              '2026-08-11T00:01:30+00:00');
                    INSERT INTO job_posting_versions (
                        version_id, canonical_job_id, version_number, content_hash, title,
                        source_observation_id, created_at
                    ) VALUES ('version-a-1', 'job-a', 1, 'hash-a', 'Job A', 'observation-a',
                              '2026-08-10T00:00:00+00:00'),
                             ('version-a-2', 'job-a', 2, 'hash-b', 'Job A', 'observation-b',
                              '2026-08-11T00:01:30+00:00');
                    INSERT INTO acquisition_quality_events (
                        event_id, cycle_id, task_id, target_id, canonical_job_id,
                        warning_code, severity, details_json, created_at
                    ) VALUES ('quality-a', 'cycle-a', 'task-a', 'source-a', 'job-a',
                              'missing_location', 'warning', '{}', '2026-08-11T00:01:00+00:00');
                    INSERT INTO admin_job_imports (
                        import_id, idempotency_key, status, cycle_id, created_at, updated_at
                    ) VALUES ('import-a', 'import-key-a', 'completed', 'cycle-a',
                              '2026-08-11T00:00:00+00:00', '2026-08-11T00:02:00+00:00');
                    INSERT INTO admin_job_review_decisions (
                        decision_id, import_id, canonical_job_id, decision, created_at
                    ) VALUES ('review-a', 'import-a', 'job-a', 'approved', '2026-08-11T00:03:00+00:00');
                    INSERT INTO acquisition_publications (
                        publication_id, cycle_id, status, snapshot_json, published_at,
                        previous_publication_id, preflight_json
                    ) VALUES ('publication-a', 'cycle-a', 'valid',
                              '[{"canonical_job_id":"job-a"}]', '2026-08-11T00:04:00+00:00', '',
                              '{"additions":["job-a"],"removals":[],"changed_jobs":[]}');
                    INSERT INTO acquisition_publication_jobs (publication_id, canonical_job_id)
                    VALUES ('publication-a', 'job-a');
                    INSERT INTO acquisition_publication_head (head_id, publication_id, updated_at)
                    VALUES (1, 'publication-a', '2026-08-11T00:04:00+00:00');
                    INSERT INTO enrichment_operation_runs (
                        run_id, plan_id, scope_type, target_type, provider_id, status,
                        idempotency_key, created_at, updated_at
                    ) VALUES ('enrichment-a', 'plan-a', 'import', 'job', 'fixture', 'completed',
                              'enrichment-key-a', '2026-08-11T00:05:00+00:00', '2026-08-11T00:06:00+00:00');
                    INSERT INTO enrichment_operation_run_items (
                        run_item_id, run_id, target_type, target_id, field_path,
                        attempt_state, confidence, updated_at
                    ) VALUES ('item-a', 'enrichment-a', 'job', 'job-a', 'place', 'matched', 0.9,
                              '2026-08-11T00:06:00+00:00');
                    """
                )
                connection.commit()
            finally:
                connection.close()

            result = build_acquisition_analytics(path, window=self._window())

        self.assertEqual(result["summary"]["observations_received"], 2)
        self.assertEqual(result["summary"]["new_canonical_jobs"], 1)
        self.assertEqual(result["summary"]["updated_jobs"], 1)
        self.assertEqual(result["summary"]["quality_findings_created"], 1)
        self.assertEqual(result["enrichment"]["state_totals"]["matched"], 1)
        self.assertEqual(result["publication"]["current_head"]["job_count"], 1)
        self.assertEqual(result["funnel"]["stages"][0]["count"], 1)
        self.assertEqual(result["sources"][0]["observations"], 2)

    def test_analytics_route_is_read_only_view_permission(self):
        handler = _Handler()
        application = Mock()
        application.get_admin_acquisition_analytics.return_value = {"schema_version": "acquisition_analytics_v1"}
        context = ApiRouteContext(
            application=application,
            handler=handler,
            method="GET",
            segments=("admin", "acquisition", "analytics"),
            query={"range": ["24h"], "timezone": ["UTC"]},
        )

        self.assertTrue(build_route_registry().dispatch(context, auth_required=True))
        self.assertEqual(handler.permissions, ["acquisition.view"])
        application.get_admin_acquisition_analytics.assert_called_once_with(
            range_key="24h", start="", end="", timezone_name="UTC"
        )


if __name__ == "__main__":
    unittest.main()
