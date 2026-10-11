"""Durable redacted provider attempts and resumable checkpoints."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .redaction import redact, redact_text
from .state import StateStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AttemptRecorder:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    def start(self, job_id: str, provider: str, model: str, *, session_id: str | None = None) -> str:
        attempt_id = uuid.uuid4().hex
        with self.store.connect() as connection:
            connection.execute(
                "INSERT INTO attempts(attempt_id, job_id, provider, model, session_id, started_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (attempt_id, job_id, provider, model, session_id, _now()),
            )
        return attempt_id

    def finish(
        self,
        attempt_id: str,
        outcome: str,
        *,
        usage: dict[str, Any] | None = None,
        error: str | None = None,
        session_id: str | None = None,
    ) -> None:
        with self.store.connect() as connection:
            cursor = connection.execute(
                "UPDATE attempts SET ended_at=?, outcome=?, usage_json=?, redacted_error=?, "
                "session_id=COALESCE(?, session_id) WHERE attempt_id=?",
                (
                    _now(),
                    outcome,
                    json.dumps(redact(usage or {}), sort_keys=True),
                    redact_text(error) if error else None,
                    session_id,
                    attempt_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"unknown attempt: {attempt_id}")

    def checkpoint(
        self,
        job_id: str,
        phase: str,
        *,
        artifact_paths: tuple[str, ...] = (),
        commit_sha: str | None = None,
        worktree: Path | None = None,
        session_id: str | None = None,
        summary: dict[str, Any] | None = None,
    ) -> str:
        fingerprint = f"{job_id}:{phase}:{commit_sha or ''}:{session_id or ''}"
        checkpoint_id = uuid.uuid5(uuid.NAMESPACE_URL, fingerprint).hex
        with self.store.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO checkpoints(checkpoint_id, job_id, phase, artifact_paths_json, "
                "commit_sha, worktree, resumable_provider_session_id, summary_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    checkpoint_id,
                    job_id,
                    phase,
                    json.dumps(artifact_paths),
                    commit_sha,
                    str(worktree) if worktree else None,
                    session_id,
                    json.dumps(redact(summary or {}), sort_keys=True),
                    _now(),
                ),
            )
        return checkpoint_id
