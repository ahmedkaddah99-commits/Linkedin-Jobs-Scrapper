from __future__ import annotations

import json

from scripts.publish_producer_states import _timing_event


def test_timing_event_records_action_duration_and_bounded_counts(tmp_path, monkeypatch):
    destination = tmp_path / "timings.jsonl"
    monkeypatch.setenv("RUNR_PUBLISHER_TIMING_FILE", str(destination))

    _timing_event("delivery_batch", duration_seconds=1.23456, companies=2, jobs=11)

    event = json.loads(destination.read_text(encoding="utf-8"))
    assert event["action"] == "delivery_batch"
    assert event["duration_seconds"] == 1.235
    assert event["counts"] == {"companies": 2, "jobs": 11}
    assert "timestamp" in event
