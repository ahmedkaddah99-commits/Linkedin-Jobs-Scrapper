"""AA-15: Backend tests for privacy-safe adapter health telemetry.

Covers:
- Bounded event payload validation (rejects forbidden keys)
- Remote config data-only proof
"""

from __future__ import annotations

import json
import unittest

from backend.application.assisted_apply_telemetry_service import (
    AdapterHealthTelemetryService,
)


class AdapterHealthTelemetryServiceTests(unittest.TestCase):
    """Tests for the in-memory telemetry store."""

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
        self.assertEqual(len(self.service._events), 2)

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
