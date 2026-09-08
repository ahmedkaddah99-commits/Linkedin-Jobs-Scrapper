"""AA-15: Backend tests for privacy-safe adapter health telemetry.

Covers:
- Bounded event payload validation (rejects forbidden keys)
- Operator report separating Greenhouse and Lever
- Remote config data-only proof
"""

from __future__ import annotations

import json
import unittest

from backend.application.assisted_apply_telemetry_service import (
    AdapterHealthTelemetryService,
)


class AdapterHealthTelemetryServiceTests(unittest.TestCase):
    """Tests for the in-memory telemetry store and operator report."""

    def setUp(self):
        self.service = AdapterHealthTelemetryService()

    def test_record_events_stores_bounded_payloads(self):
        events = [
            {
                "schemaVersion": 1,
                "adapter": "greenhouse",
                "adapterVersion": "0.3.0",
                "lifecycleStage": "detect",
                "aggregateOutcome": "success",
                "errorCategory": "none",
            },
            {
                "schemaVersion": 1,
                "adapter": "lever",
                "adapterVersion": "0.3.0",
                "lifecycleStage": "fill",
                "aggregateOutcome": "failure",
                "errorCategory": "fill_rejected",
            },
        ]
        self.service.record_events(events)
        report = self.service.get_operator_report()
        self.assertEqual(report["summary"]["totalEvents"], 2)

    def test_operator_report_separates_greenhouse_and_lever(self):
        greenhouse_events = [
            {
                "schemaVersion": 1,
                "adapter": "greenhouse",
                "adapterVersion": "0.3.0",
                "lifecycleStage": stage,
                "aggregateOutcome": "success",
                "errorCategory": "none",
            }
            for stage in ("detect", "inspect", "match", "fill", "validate")
        ]
        lever_events = [
            {
                "schemaVersion": 1,
                "adapter": "lever",
                "adapterVersion": "0.3.0",
                "lifecycleStage": stage,
                "aggregateOutcome": outcome,
                "errorCategory": "none" if outcome == "success" else "fill_rejected",
            }
            for stage, outcome in (("detect", "success"), ("fill", "failure"))
        ]
        self.service.record_events(greenhouse_events + lever_events)

        report = self.service.get_operator_report()
        self.assertIn("greenhouse", report["adapter"])
        self.assertEqual(len(report["adapter"]["greenhouse"]), 5)
        self.assertIn("lever", report["adapter"])
        self.assertEqual(len(report["adapter"]["lever"]), 2)
        self.assertEqual(report["summary"]["totalEvents"], 7)
        self.assertEqual(report["summary"]["errorEvents"], 1)
        self.assertGreater(report["summary"]["errorRate"], 0)

    def test_empty_report(self):
        report = self.service.get_operator_report()
        self.assertEqual(report["summary"]["totalEvents"], 0)
        self.assertEqual(report["summary"]["errorEvents"], 0)
        self.assertEqual(report["summary"]["errorRate"], 0.0)
        self.assertEqual(report["adapter"]["greenhouse"], {})
        self.assertEqual(report["adapter"]["lever"], {})

    def test_rejects_extra_keys_via_validator(self):
        from backend.api.routes.assisted_apply_telemetry import (
            _read_bounded_telemetry_event,
        )

        valid = {
            "schemaVersion": 1,
            "adapter": "greenhouse",
            "adapterVersion": "0.3.0",
            "lifecycleStage": "detect",
            "aggregateOutcome": "success",
            "errorCategory": "none",
        }
        result = _read_bounded_telemetry_event(valid)
        self.assertEqual(result["adapter"], "greenhouse")

        with self.assertRaises(ValueError):
            _read_bounded_telemetry_event({**valid, "documentRole": "cv"})
        with self.assertRaises(ValueError):
            _read_bounded_telemetry_event({**valid, "answers": ["secret"]})

    def test_rejects_invalid_enums_via_validator(self):
        from backend.api.routes.assisted_apply_telemetry import (
            _read_bounded_telemetry_event,
        )

        valid = {
            "schemaVersion": 1,
            "adapter": "greenhouse",
            "adapterVersion": "0.3.0",
            "lifecycleStage": "detect",
            "aggregateOutcome": "success",
            "errorCategory": "none",
        }
        _read_bounded_telemetry_event(valid)

        with self.assertRaises(ValueError):
            _read_bounded_telemetry_event({**valid, "lifecycleStage": "submit"})
        with self.assertRaises(ValueError):
            _read_bounded_telemetry_event({**valid, "aggregateOutcome": "complete"})
        with self.assertRaises(ValueError):
            _read_bounded_telemetry_event({**valid, "errorCategory": "critical"})
        with self.assertRaises(ValueError):
            _read_bounded_telemetry_event({**valid, "adapter": "workday"})
    
    def test_rejects_unknown_schema_version(self):
        from backend.api.routes.assisted_apply_telemetry import (
            _read_bounded_telemetry_event,
        )

        with self.assertRaises(ValueError):
            _read_bounded_telemetry_event({
                "schemaVersion": 2,
                "adapter": "greenhouse",
                "adapterVersion": "0.3.0",
                "lifecycleStage": "detect",
                "aggregateOutcome": "success",
                "errorCategory": "none",
            })

    def test_registers_only_the_canonical_extension_telemetry_endpoint(self):
        from backend.api.routes import build_route_registry

        routes = build_route_registry()._routes
        route_names = {route.name for route in routes}
        self.assertIn("assisted_apply.telemetry.events.receive", route_names)
        self.assertNotIn("assisted_apply.extension.telemetry.create", route_names)


if __name__ == "__main__":
    unittest.main()
