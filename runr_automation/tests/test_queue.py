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


def test_only_lease_owner_can_complete_or_wait_a_running_job(tmp_path: Path) -> None:
    queue = JobQueue(StateStore(tmp_path / "state.db"))
    job_id = queue.enqueue("implement", "issue-1", "fingerprint-1")
    now = datetime(2026, 9, 17, tzinfo=timezone.utc)
    assert queue.claim("worker-1", now=now, lease_seconds=30)

    try:
        queue.complete(job_id, "worker-2")
    except ValueError as exc:
        assert "lease owner" in str(exc)
    else:
        raise AssertionError("a different worker completed the job")

    queue.wait(job_id, "worker-1", next_retry=now + timedelta(minutes=5))
    with queue.store.connect() as connection:
        row = connection.execute("SELECT status, next_retry, lease_owner FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    assert tuple(row) == ("waiting", "2026-09-17T00:05:00+00:00", None)


def test_completing_stage_enqueues_next_stage_idempotently(tmp_path: Path) -> None:
    queue = JobQueue(StateStore(tmp_path / "state.db"))
    job_id = queue.enqueue("normalize", "issue-1", "fingerprint-1")
    now = datetime(2026, 9, 17, tzinfo=timezone.utc)
    assert queue.claim("worker-1", now=now, lease_seconds=30)

    next_job = queue.complete_and_enqueue(job_id, "worker-1", "deduplicate")

    assert next_job == queue.enqueue("deduplicate", "issue-1", "fingerprint-1")
    with queue.store.connect() as connection:
        statuses = connection.execute("SELECT type, status FROM jobs ORDER BY rowid").fetchall()
    assert [tuple(row) for row in statuses] == [("normalize", "complete"), ("deduplicate", "queued")]
