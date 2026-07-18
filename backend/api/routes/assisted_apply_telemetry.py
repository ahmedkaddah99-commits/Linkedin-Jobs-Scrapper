"""AA-15: Privacy-safe adapter health telemetry endpoint.

Only accepts bounded aggregate events — never answers, PII, document content,
URLs, tokens, credentials, filenames, or raw markup.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Mapping

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.application.assisted_apply_telemetry_service import (
    AdapterHealthTelemetryService,
)

# Module-level telemetry store — shared across requests.
_telemetry_service = AdapterHealthTelemetryService()

# Bounded enum values — must match TypeScript types
_LIFECYCLE_STAGES = frozenset({
    "detect", "inspect", "match", "fill", "validate", "upload",
})
_AGGREGATE_OUTCOMES = frozenset({
    "success", "failure", "partial", "skipped",
})
_ERROR_CATEGORIES = frozenset({
    "none", "detection_failed", "inspection_failed", "matching_failed",
    "fill_rejected", "fill_mismatched", "validation_failed",
    "control_unavailable", "control_blocked", "mime_rejected",
    "portal_rejected", "existing_value", "unsupported_role", "unknown",
})
_TELEMETRY_KEYS = frozenset({
    "schemaVersion", "adapter", "adapterVersion",
    "lifecycleStage", "aggregateOutcome", "errorCategory",
})

_REMOTE_CONFIG_KEYS = frozenset({
    "schemaVersion", "batchIntervalSeconds", "sampleRate", "maxQueueSize",
})


def register_routes(registry: RouteRegistry) -> None:
    registry.exact(
        "POST",
        ("assisted-apply", "telemetry", "events"),
        _receive_telemetry_events,
        auth_required=False,
        name="assisted_apply.telemetry.events.receive",
    )
    registry.exact(
        "GET",
        ("assisted-apply", "telemetry", "operator-report"),
        _get_operator_report,
        auth_required=True,
        name="assisted_apply.telemetry.operator_report.get",
    )


def _read_bounded_telemetry_event(value: object) -> dict[str, Any]:
    """Validate a single bounded telemetry event payload."""
    if not isinstance(value, Mapping):
        raise ValueError("Each event must be a JSON object with exactly the bounded keys.")

    payload = dict(value)
    unknown_keys = sorted(str(key) for key in payload if key not in _TELEMETRY_KEYS)
    if unknown_keys:
        raise ValueError(
            "Unsupported telemetry keys: " + ", ".join(unknown_keys)
        )

    schema_version = payload.get("schemaVersion")
    if schema_version != 1:
        raise ValueError("Only telemetry schemaVersion 1 is accepted.")

    adapter = payload.get("adapter")
    if adapter not in ("greenhouse", "lever"):
        raise ValueError("adapter must be 'greenhouse' or 'lever'.")

    adapter_version = payload.get("adapterVersion")
    if not isinstance(adapter_version, str) or not adapter_version:
        raise ValueError("adapterVersion must be a non-empty string.")

    lifecycle_stage = payload.get("lifecycleStage")
    if lifecycle_stage not in _LIFECYCLE_STAGES:
        raise ValueError(f"Unknown lifecycleStage: {lifecycle_stage}")

    outcome = payload.get("aggregateOutcome")
    if outcome not in _AGGREGATE_OUTCOMES:
        raise ValueError(f"Unknown aggregateOutcome: {outcome}")

    error = payload.get("errorCategory")
    if error not in _ERROR_CATEGORIES:
        raise ValueError(f"Unknown errorCategory: {error}")

    return payload


def _receive_telemetry_events(context: ApiRouteContext) -> None:
    """Receive a batch of bounded telemetry events.

    Accepts either a single object or an array of event objects.
    Rejects any payload containing forbidden keys.
    """
    body = context.read_json_body()

    if isinstance(body, list):
        events = body
    elif isinstance(body, Mapping):
        events = [body]
    else:
        raise ValueError("Telemetry payload must be a JSON object or array.")

    validated: list[dict[str, Any]] = []
    for event in events:
        validated.append(_read_bounded_telemetry_event(event))

    _telemetry_service.record_events(validated)

    context.send_json(
        {"accepted": len(validated)},
        status=HTTPStatus.ACCEPTED,
    )


def _get_operator_report(context: ApiRouteContext) -> None:
    """Return an operator-facing report separating Greenhouse and Lever lifecycle regressions."""
    user, _ = context.require_clerk_identity()
    context.require_admin()

    report = _telemetry_service.get_operator_report()
    context.send_json(report, status=HTTPStatus.OK)
