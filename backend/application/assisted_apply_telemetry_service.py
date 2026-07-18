"""AA-15: Privacy-safe adapter health telemetry storage and operator report generation.

Only stores bounded aggregate events — never answers, PII, document content,
URLs, tokens, credentials, filenames, or raw markup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AdapterHealthEvent:
    """A single bounded telemetry event — no sensitive data stored."""

    adapter: str
    adapter_version: str
    lifecycle_stage: str
    aggregate_outcome: str
    error_category: str
    recorded_at: str


@dataclass
class AdapterHealthOperatorReport:
    """Operator-facing report separating Greenhouse and Lever lifecycle regressions."""

    greenhouse: dict[str, int] = field(default_factory=dict)
    lever: dict[str, int] = field(default_factory=dict)
    total_events: int = 0
    error_events: int = 0
    error_rate: float = 0.0


class AdapterHealthTelemetryService:
    """In-memory telemetry store. Production deployments would use a persistent store."""

    def __init__(self) -> None:
        self._events: list[AdapterHealthEvent] = []

    def record_events(self, events: list[dict[str, Any]]) -> None:
        """Store validated bounded telemetry events."""
        now = datetime.now(timezone.utc).isoformat()
        for event in events:
            self._events.append(
                AdapterHealthEvent(
                    adapter=str(event["adapter"]),
                    adapter_version=str(event["adapterVersion"]),
                    lifecycle_stage=str(event["lifecycleStage"]),
                    aggregate_outcome=str(event["aggregateOutcome"]),
                    error_category=str(event["errorCategory"]),
                    recorded_at=now,
                )
            )

    def get_operator_report(self) -> dict[str, Any]:
        """Generate an operator report separating Greenhouse and Lever lifecycle stages."""
        report = AdapterHealthOperatorReport()

        greenhouse_counts: dict[str, int] = {}
        lever_counts: dict[str, int] = {}
        error_count = 0

        for event in self._events:
            stage = event.lifecycle_stage
            outcome_key = f"{stage}/{event.aggregate_outcome}"

            if event.adapter == "greenhouse":
                greenhouse_counts[outcome_key] = greenhouse_counts.get(outcome_key, 0) + 1
            else:
                lever_counts[outcome_key] = lever_counts.get(outcome_key, 0) + 1

            if event.error_category != "none":
                error_count += 1

        report.greenhouse = dict(sorted(greenhouse_counts.items()))
        report.lever = dict(sorted(lever_counts.items()))
        report.total_events = len(self._events)
        report.error_events = error_count
        report.error_rate = round(error_count / max(len(self._events), 1), 4)

        return {
            "adapter": {
                "greenhouse": report.greenhouse,
                "lever": report.lever,
            },
            "summary": {
                "totalEvents": report.total_events,
                "errorEvents": report.error_events,
                "errorRate": report.error_rate,
            },
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }
