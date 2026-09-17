"""Durable local state for the Runr automation controller."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 3


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    """Own a SQLite database and apply its schema migrations on startup."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _migrate(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            current = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0]
            if current < 1:
                self._apply_v1(connection)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (1, _utc_now()),
                )
                current = 1
            if current < 2:
                self._apply_v2(connection)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (2, _utc_now()),
                )
                current = 2
            if current < 3:
                self._apply_v3(connection)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (3, _utc_now()),
                )

    @staticmethod
    def _apply_v1(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS issues (
                linear_id TEXT PRIMARY KEY,
                identifier TEXT NOT NULL,
                latest_remote_timestamp TEXT,
                normalized_fingerprint TEXT,
                subsystem TEXT,
                lifecycle_state TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}',
                observed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                event_key TEXT PRIMARY KEY,
                payload_hash TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                processed_state TEXT NOT NULL DEFAULT 'pending'
            );

            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                issue_id TEXT,
                desired_state_fingerprint TEXT NOT NULL,
                status TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 0,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                next_retry TEXT,
                lease_owner TEXT,
                lease_expires_at TEXT,
                FOREIGN KEY(issue_id) REFERENCES issues(linear_id)
            );

            CREATE TABLE IF NOT EXISTS attempts (
                attempt_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                session_id TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                outcome TEXT,
                usage_json TEXT,
                redacted_error TEXT,
                FOREIGN KEY(job_id) REFERENCES jobs(job_id)
            );

            CREATE TABLE IF NOT EXISTS checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                phase TEXT NOT NULL,
                artifact_paths_json TEXT NOT NULL DEFAULT '[]',
                commit_sha TEXT,
                worktree TEXT,
                resumable_provider_session_id TEXT,
                summary_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(job_id)
            );

            CREATE TABLE IF NOT EXISTS dependency_edges (
                predecessor TEXT NOT NULL,
                successor TEXT NOT NULL,
                kind TEXT NOT NULL,
                evidence_hash TEXT NOT NULL,
                linear_relation_id TEXT,
                PRIMARY KEY(predecessor, successor, kind),
                FOREIGN KEY(predecessor) REFERENCES issues(linear_id),
                FOREIGN KEY(successor) REFERENCES issues(linear_id)
            );

            CREATE TABLE IF NOT EXISTS waves (
                plan_version TEXT NOT NULL,
                issue_id TEXT NOT NULL,
                membership_json TEXT NOT NULL DEFAULT '[]',
                conflict_resources_json TEXT NOT NULL DEFAULT '[]',
                validity_fingerprint TEXT NOT NULL,
                PRIMARY KEY(plan_version, issue_id),
                FOREIGN KEY(issue_id) REFERENCES issues(linear_id)
            );

            CREATE TABLE IF NOT EXISTS approvals (
                approval_id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                target TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                decision TEXT,
                actor TEXT,
                expires_at TEXT,
                action_fingerprint TEXT NOT NULL,
                tested_commit_sha TEXT
            );

            CREATE TABLE IF NOT EXISTS provider_circuits (
                provider_model TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                failure_reason TEXT,
                reopen_at TEXT
            );

            CREATE TABLE IF NOT EXISTS locks (
                resource_key TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                lease_expires_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS migrations (
                migration_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                snapshot_path TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                result_json TEXT NOT NULL DEFAULT '{}'
            );
            """
        )

    @staticmethod
    def _apply_v2(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS controller_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    @staticmethod
    def _apply_v3(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_stages (
                issue_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                last_run_at TEXT NOT NULL,
                input_fingerprint TEXT NOT NULL,
                result_fingerprint TEXT NOT NULL,
                tool_version TEXT NOT NULL,
                skill_version TEXT NOT NULL,
                next_reason_to_run TEXT NOT NULL,
                PRIMARY KEY(issue_id, stage)
            )
            """
        )
