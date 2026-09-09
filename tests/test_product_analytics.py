from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.application.product_analytics import (
    PRODUCT_ANALYTICS_EVENT_QUERY,
    build_product_analytics,
    load_product_analytics,
)


NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def event(name: str, occurred_at: str, user_id: str, **payload):
    return {
        "event_name": name,
        "occurred_at": occurred_at,
        "user_id": user_id,
        "run_id": payload.pop("run_id", ""),
        "job_id": payload.pop("job_id", ""),
        "source": payload.pop("source", "api"),
        "payload_json": {"analytics_environment": "production", **payload},
    }


class ProductAnalyticsTests(unittest.TestCase):
    def test_funnel_deduplicates_users_and_requires_backend_confirmed_outcome(self):
        rows = [
            event("user_signed_up", "2026-07-01T09:00:00+00:00", "usr_1"),
            event("user_signed_up", "2026-07-01T09:01:00+00:00", "usr_1"),
            event("profile_ready", "2026-07-01T09:10:00+00:00", "usr_1", source="worker"),
            event("job_relevant_viewed", "2026-07-01T09:11:00+00:00", "usr_1", job_id="job_1", source="frontend_first_party"),
            event("job_relevant_viewed", "2026-07-01T09:12:00+00:00", "usr_1", job_id="job_1", source="frontend_first_party"),
            event("job_saved", "2026-07-01T09:13:00+00:00", "usr_1", job_id="job_1", source="frontend_first_party"),
            event("cv_generation_completed", "2026-07-01T09:20:00+00:00", "usr_1", run_id="run_1", duration_ms=700, source="worker"),
            event("application_status_updated", "2026-07-01T09:21:00+00:00", "usr_1", to_status="Applied"),
            event("subscription_started", "2026-07-01T09:22:00+00:00", "usr_1", source="creem"),
            event("user_signed_up", "2026-08-01T09:00:00+00:00", "usr_2"),
            event("session_started", "2026-08-08T09:00:00+00:00", "usr_2", source="frontend_first_party"),
            event("application_status_updated", "2026-08-01T09:10:00+00:00", "usr_2", to_status="clicked_apply"),
            event("job_relevant_viewed", "2026-07-01T09:30:00+00:00", "usr_orphan", job_id="job_orphan"),
        ]

        projection = build_product_analytics(rows, now=NOW, environment="production")
        stages = {stage["stage"]: stage for stage in projection["funnel"]["stages"]}

        self.assertEqual(projection["funnel"]["denominator"]["unique_users"], 2)
        self.assertEqual(stages["signup"]["events"], 3)
        self.assertEqual(stages["signup"]["unique_users"], 2)
        self.assertEqual(stages["relevant_job"]["events"], 2)
        self.assertEqual(stages["relevant_job"]["unique_users"], 1)
        self.assertEqual(stages["confirmed_application_outcome"]["unique_users"], 1)
        self.assertEqual(stages["paid_conversion"]["unique_users"], 1)
        self.assertEqual(projection["funnel"]["orphan_stage_events"], 1)
        self.assertIn(
            {"band": "<1s", "events": 1, "unique_users": 1, "confirmed_outcome_users_after": 1},
            projection["latency_bands"],
        )

        retention = projection["retention"]["cohorts"]
        self.assertEqual(len(retention), 2)
        self.assertTrue(any(row["returned_d7"] == 1 for row in retention))
        self.assertTrue(all(row["return_d30_pct"] is not None for row in retention))

    def test_separates_environments_excludes_test_users_and_keeps_unknown_latency(self):
        rows = [
            event("user_signed_up", "2026-08-01T09:00:00+00:00", "usr_prod"),
            event("user_signed_up", "2026-08-01T09:00:00+00:00", "usr_stage", source="api", analytics_environment="staging"),
            event("frontend_api_request_slow", "2026-08-01T09:10:00+00:00", "usr_prod", path="/v1/personalized-jobs", duration_ms=25000),
            event("run_failed", "2026-08-01T09:11:00+00:00", "usr_prod", error_code="provider_timeout"),
            event("run_completed", "2026-08-01T09:12:00+00:00", "usr_prod", source="worker"),
            event("page_view", "2026-08-01T09:13:00+00:00", "usr_prod", source="frontend_first_party"),
            event("user_signed_up", "2026-08-01T09:00:00+00:00", "e2e-browser", analytics_excluded=True),
            {
                **event("user_signed_up", "2026-08-01T09:00:00+00:00", "usr_email"),
                "user_payload_json": {"email": "fixture@example.com"},
            },
        ]

        projection = build_product_analytics(rows, now=NOW, environment="production")
        environments = {row["environment"]: row for row in projection["by_environment"]}
        self.assertEqual(environments["production"]["signups"], 1)
        self.assertEqual(environments["staging"]["signups"], 1)
        self.assertEqual(projection["exclusions"]["excluded_events"], 2)
        self.assertEqual(projection["exclusions"]["excluded_users"], 2)
        self.assertEqual(projection["latency_bands"][0]["band"], "20s+")
        self.assertIn({"category": "provider_timeout", "events": 1, "unique_users": 1, "later_value_users": 1}, projection["failure_categories"])
        self.assertIn(
            {"band": "unknown", "events": 2, "unique_users": 1, "confirmed_outcome_users_after": 0},
            projection["latency_bands"],
        )

    def test_loader_uses_bounded_query_and_preserves_projection_contract(self):
        calls = []

        def query_rows(query, parameters):
            calls.append((query, tuple(parameters)))
            return [event("user_signed_up", "2026-09-01T09:00:00+00:00", "usr_1")]

        projection = load_product_analytics(query_rows, now=NOW, environment="production")

        self.assertEqual(len(calls), 1)
        self.assertIn("FROM analytics_events", calls[0][0])
        self.assertIn("LEFT JOIN users", calls[0][0])
        self.assertEqual(len(calls[0][1]), 2)
        self.assertEqual(calls[0][1][1], NOW.isoformat())
        self.assertEqual(projection["schema_version"], "product_analytics_v1")
        self.assertEqual(projection["funnel"]["denominator"]["unique_users"], 1)
        self.assertIn("analytics_events", PRODUCT_ANALYTICS_EVENT_QUERY)
