from datetime import datetime, timedelta, timezone
from pathlib import Path

from runr_automation.queue import JobQueue
from runr_automation.state import StateStore


def test_enqueue_is_idempotent_and_crashed_lease_is_reclaimed(tmp_path: Path) -> None:
    queue = JobQueue(StateStore(tmp_path / "state.db"))
    job_id = queue.enqueue("research", "issue-1", "fingerprint-1")
    assert queue.enqueue("research", "issue-1", "fingerprint-1") == job_id
    now = datetime(2026, 9, 17, tzinfo=timezone.utc)

    first = queue.claim("worker-1", now=now, lease_seconds=30)
    assert first and first.job_id == job_id
    assert queue.claim("worker-2", now=now + timedelta(seconds=10), lease_seconds=30) is None
    reclaimed = queue.claim("worker-2", now=now + timedelta(seconds=31), lease_seconds=30)
    assert reclaimed and reclaimed.job_id == job_id
    assert reclaimed.attempt_count == 2


def test_analysis_stage_records_freshness_metadata(tmp_path: Path) -> None:
    queue = JobQueue(StateStore(tmp_path / "state.db"))

    queue.record_analysis(
        "issue-1",
        "deduplicate",
        input_fingerprint="input-1",
        result_fingerprint="result-1",
        tool_version="0.1.0",
        skill_version="1",
        next_reason_to_run="title or acceptance criteria changes",
    )

    stage = queue.analysis("issue-1", "deduplicate")
    assert stage["input_fingerprint"] == "input-1"
    assert stage["next_reason_to_run"] == "title or acceptance criteria changes"
