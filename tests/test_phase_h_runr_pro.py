import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.api.server import _handle_creem_webhook_event, _subscription_response_payload
from backend.application.personalized_jobs_service import PersonalizedJobsService
from backend.bootstrap import create_backend
from backend.config.plans import (
    DEFAULT_PLAN_ID,
    get_plan,
    get_plan_for_product_id,
    get_runr_pro_product_ids,
    has_runr_pro_access,
    list_plans,
    normalize_plan_id,
)


CANONICAL_ENV = {
    "CREEM_API_KEY": "creem_test_fixture",
    "CREEM_WEBHOOK_SECRET": "whsec_fixture",
    "CREEM_RUNR_PRO_PRODUCT_ID": "prod_pro_monthly",
    "CREEM_RUNR_PRO_WEEKLY_PRODUCT_ID": "prod_pro_weekly",
    "CREEM_RUNR_PRO_MONTHLY_PRODUCT_ID": "prod_pro_monthly",
    "CREEM_RUNR_PRO_QUARTERLY_PRODUCT_ID": "prod_pro_quarterly",
    "CREEM_LAUNCH_PRODUCT_ID": "prod_legacy_launch",
    "CREEM_MOMENTUM_PRODUCT_ID": "prod_legacy_momentum",
    "CREEM_SCALE_PRODUCT_ID": "prod_legacy_scale",
}


class PhaseHRunrProTests(unittest.TestCase):
    def test_plan_catalog_is_canonical_and_contains_all_simplify_duration_offers(self):
        with patch.dict(os.environ, CANONICAL_ENV, clear=False):
            self.assertEqual([item["plan_id"] for item in list_plans()], ["free", "runr_pro"])
            plan = get_plan("runr_pro")
            self.assertEqual(plan["display_name"], "Runr Pro")
            self.assertEqual(
                [(offer["offer_id"], offer["amount"], offer["billing_period"]) for offer in plan["offers"]],
                [
                    ("one_week", 1999, "once"),
                    ("one_month", 3999, "every-month"),
                    ("three_months", 8999, "every-three-months"),
                ],
            )
            self.assertEqual(get_runr_pro_product_ids(), ["prod_pro_monthly", "prod_pro_weekly", "prod_pro_quarterly"])

    def test_legacy_plan_and_product_names_resolve_to_runr_pro_without_provider_migration(self):
        with patch.dict(os.environ, CANONICAL_ENV, clear=False):
            for raw_plan in ("free", "none"):
                self.assertEqual(normalize_plan_id(raw_plan), DEFAULT_PLAN_ID)
            for raw_plan in ("launch", "momentum", "scale", "pro", "business"):
                self.assertEqual(normalize_plan_id(raw_plan), "runr_pro")
            for product_id in (
                "prod_legacy_launch",
                "prod_legacy_momentum",
                "prod_legacy_scale",
                "prod_pro_weekly",
                "prod_pro_monthly",
                "prod_pro_quarterly",
            ):
                self.assertEqual(get_plan_for_product_id(product_id), "runr_pro")
            self.assertTrue(has_runr_pro_access("scale"))
            self.assertFalse(has_runr_pro_access("free"))

    def test_webhook_states_preserve_subscription_ids_and_change_only_entitlement(self):
        with patch.dict(os.environ, CANONICAL_ENV, clear=False), tempfile.TemporaryDirectory() as directory:
            app = create_backend(Path(directory), storage_backend="sqlite", test_mode=True)
            user = app.upsert_user({"email": "phase-h@example.com", "display_name": "Phase H"})
            base_object = {
                "id": "sub_legacy_preserved",
                "object": "subscription",
                "product": {"id": "prod_legacy_momentum", "name": "Momentum"},
                "customer": {"id": "cust_preserved", "email": user.email},
                "current_period_start_date": "2026-08-01T00:00:00Z",
                "current_period_end_date": "2026-09-01T00:00:00Z",
                "created_at": "2026-08-01T00:00:00Z",
                "updated_at": "2026-08-01T00:00:00Z",
                "metadata": {"user_id": user.user_id, "plan_id": "momentum"},
            }
            with patch("backend.api.server.update_user_plan_in_clerk"):
                for index, (event_name, provider_status, expected_plan) in enumerate(
                    (
                        ("subscription.active", "active", "runr_pro"),
                        ("subscription.scheduled_cancel", "scheduled_cancel", "runr_pro"),
                        ("subscription.past_due", "past_due", "runr_pro"),
                        ("subscription.paused", "paused", "free"),
                        ("subscription.resumed", "active", "runr_pro"),
                        ("subscription.canceled", "canceled", "free"),
                    ),
                    start=1,
                ):
                    payload_object = dict(base_object)
                    payload_object["status"] = provider_status
                    payload_object["updated_at"] = f"2026-08-01T00:00:0{index}Z"
                    result = _handle_creem_webhook_event(
                        app,
                        event_name=event_name,
                        payload={"id": f"evt_phase_h_{index}", "eventType": event_name, "object": payload_object},
                    )
                    self.assertEqual(result["status"], "ok")
                    response = _subscription_response_payload(
                        app,
                        user_id=user.user_id,
                        plan_id="free",
                    )
                    self.assertEqual(response["plan_id"], expected_plan)
                    subscription = app.repositories.auth_repository.get_current_subscription_by_user_id(user.user_id)
                    self.assertEqual(subscription["creem_subscription_id"], "sub_legacy_preserved")
                    self.assertEqual(subscription["creem_customer_id"], "cust_preserved")

    def test_phase_i_gate_requires_canonical_offers_and_reports_legacy_compatibility_ids(self):
        with patch.dict(os.environ, CANONICAL_ENV, clear=False), tempfile.TemporaryDirectory() as directory:
            app = create_backend(Path(directory), storage_backend="sqlite", test_mode=True)
            gate = app.get_production_rollout_status()["gates"]["creem_products_configured"]
            self.assertTrue(gate["passed"])
            self.assertEqual(gate["canonical_plan_id"], "runr_pro")
            self.assertEqual(gate["canonical_product_ids"], get_runr_pro_product_ids())
            self.assertEqual(
                gate["legacy_compatibility_product_ids"],
                ["prod_legacy_launch", "prod_legacy_momentum", "prod_legacy_scale"],
            )

    def test_scores_are_free_while_rewriting_and_tailoring_are_pro(self):
        result = PersonalizedJobsService._apply_plan_entitlements(
            {"v1": {"score": 40}, "v2": {"score": 60}},
            "free",
        )
        self.assertEqual(result["entitlements"]["match_scores"], {"free": True, "pro": True})
        self.assertFalse(result["improve_resume"]["rewriting_available"])
        self.assertFalse(result["improve_resume"]["tailored_documents_available"])


if __name__ == "__main__":
    unittest.main()
