"""Durable idempotent job queue with reclaimable leases."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from .models import JobRecord, JobStatus
from .state import StateStore


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class JobQueue:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    def enqueue(self, job_type: str, issue_id: str, fingerprint: str, *, priority: int = 0) -> str:
        job_id = self._job_id(job_type, issue_id, fingerprint)
        with self.store.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO issues(linear_id, identifier, observed_at) VALUES (?, ?, ?)",
                (issue_id, issue_id, _iso(datetime.now(timezone.utc))),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO jobs(
                    job_id, type, issue_id, desired_state_fingerprint, status, priority, attempt_count
                ) VALUES (?, ?, ?, ?, 'queued', ?, 0)
                """,
                (job_id, job_type, issue_id, fingerprint, priority),
            )
        return job_id

    @staticmethod
    def _job_id(job_type: str, issue_id: str, fingerprint: str) -> str:
        return hashlib.sha256(f"{job_type}:{issue_id}:{fingerprint}".encode()).hexdigest()[:32]

    @staticmethod
    def _transition(connection, job_id: str, owner: str, status: str, *, next_retry: str | None = None):
        cursor = connection.execute(
            "UPDATE jobs SET status=?, next_retry=?, lease_owner=NULL, lease_expires_at=NULL "
            "WHERE job_id=? AND status='running' AND lease_owner=?",
            (status, next_retry, job_id, owner),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"job is not running for lease owner {owner}: {job_id}")

    def complete(self, job_id: str, owner: str) -> None:
        with self.store.connect() as connection:
            self._transition(connection, job_id, owner, "complete")

    def wait(self, job_id: str, owner: str, *, next_retry: datetime) -> None:
        with self.store.connect() as connection:
            self._transition(connection, job_id, owner, "waiting", next_retry=_iso(next_retry))

    def fail(self, job_id: str, owner: str) -> None:
        with self.store.connect() as connection:
            self._transition(connection, job_id, owner, "failed")

    def release(self, job_id: str, owner: str) -> None:
        with self.store.connect() as connection:
            self._transition(connection, job_id, owner, "queued")

    def complete_and_enqueue(self, job_id: str, owner: str, next_type: str) -> str:
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT issue_id, desired_state_fingerprint, priority FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None or row["issue_id"] is None:
                raise ValueError(f"job is unknown or has no issue: {job_id}")
            self._transition(connection, job_id, owner, "complete")
            next_job_id = self._job_id(next_type, row["issue_id"], row["desired_state_fingerprint"])
            connection.execute(
                "INSERT OR IGNORE INTO jobs(job_id, type, issue_id, desired_state_fingerprint, status, priority, attempt_count) "
                "VALUES (?, ?, ?, ?, 'queued', ?, 0)",
                (next_job_id, next_type, row["issue_id"], row["desired_state_fingerprint"], row["priority"]),
            )
        return next_job_id

    def claim(self, owner: str, *, now: datetime, lease_seconds: int) -> JobRecord | None:
        now_text = _iso(now)
        expires = _iso(now + timedelta(seconds=lease_seconds))
        with self.store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM jobs
                WHERE (status IN ('queued', 'waiting') AND (next_retry IS NULL OR next_retry <= ?))
                   OR (status = 'running' AND lease_expires_at < ?)
                ORDER BY priority DESC, rowid ASC LIMIT 1
                """,
                (now_text, now_text),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE jobs SET status='running', lease_owner=?, lease_expires_at=?, attempt_count=attempt_count+1 "
                "WHERE job_id=?",
                (owner, expires, row["job_id"]),
            )
            updated = connection.execute("SELECT * FROM jobs WHERE job_id=?", (row["job_id"],)).fetchone()
        return JobRecord(
            updated["job_id"], updated["type"], updated["issue_id"], updated["desired_state_fingerprint"],
            JobStatus(updated["status"]), updated["priority"], updated["attempt_count"], updated["next_retry"],
            updated["lease_owner"], updated["lease_expires_at"],
        )

    def record_analysis(
        self,
        issue_id: str,
        stage: str,
        *,
        input_fingerprint: str,
        result_fingerprint: str,
        tool_version: str,
        skill_version: str,
        next_reason_to_run: str,
    ) -> None:
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_stages VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(issue_id, stage) DO UPDATE SET
                  last_run_at=excluded.last_run_at, input_fingerprint=excluded.input_fingerprint,
                  result_fingerprint=excluded.result_fingerprint, tool_version=excluded.tool_version,
                  skill_version=excluded.skill_version, next_reason_to_run=excluded.next_reason_to_run
                """,
                (issue_id, stage, _iso(datetime.now(timezone.utc)), input_fingerprint, result_fingerprint,
                 tool_version, skill_version, next_reason_to_run),
            )

    def analysis(self, issue_id: str, stage: str):
        with self.store.connect() as connection:
            return connection.execute(
                "SELECT * FROM analysis_stages WHERE issue_id=? AND stage=?", (issue_id, stage)
            ).fetchone()

    def retry(self, job_id: str) -> None:
        with self.store.connect() as connection:
            cursor = connection.execute(
                "UPDATE jobs SET status='queued', next_retry=NULL, lease_owner=NULL, lease_expires_at=NULL "
                "WHERE job_id=? AND status IN ('failed', 'waiting')",
                (job_id,),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"job is unknown or not retryable: {job_id}")
