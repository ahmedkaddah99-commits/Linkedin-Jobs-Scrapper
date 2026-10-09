import json
from pathlib import Path

from runr_automation.attempts import AttemptRecorder
from runr_automation.queue import JobQueue
from runr_automation.state import StateStore


def test_attempt_errors_are_redacted_and_checkpoint_is_resumable(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    job_id = JobQueue(store).enqueue("implement", "issue-1", "fingerprint-1")
    recorder = AttemptRecorder(store)

    attempt_id = recorder.start(job_id, "codex", "gpt", session_id="session-1")
    recorder.finish(attempt_id, "capacity", error="Authorization: Bearer sk-secret")
    checkpoint_id = recorder.checkpoint(
        job_id,
        "implementation",
        artifact_paths=("backend/a.py",),
        commit_sha="abc123",
        worktree=tmp_path / "worktree",
        session_id="session-1",
        summary={"next_action": "resume", "api_token": "never-store-this"},
    )

    with store.connect() as connection:
        attempt = connection.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
        checkpoint = connection.execute(
            "SELECT * FROM checkpoints WHERE checkpoint_id=?", (checkpoint_id,)
        ).fetchone()
    assert attempt["redacted_error"] == "Authorization: Bearer [REDACTED]"
    assert checkpoint["resumable_provider_session_id"] == "session-1"
    assert json.loads(checkpoint["summary_json"])["api_token"] == "[REDACTED]"
