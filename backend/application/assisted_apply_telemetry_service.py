"""AA-15: Privacy-safe adapter health telemetry storage.

Only stores bounded aggregate events — never answers, PII, document content,
URLs, tokens, credentials, filenames, or raw markup.
"""

from __future__ import annotations

from dataclasses import dataclass
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
