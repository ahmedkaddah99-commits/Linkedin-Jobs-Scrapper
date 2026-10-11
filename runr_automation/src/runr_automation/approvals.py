"""Fingerprint-bound local approvals for release and destructive actions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .state import StateStore


@dataclass(frozen=True)
class ActionContext:
    action: str
    targets: tuple[str, ...]
    tested_commit_sha: str
    issue_fingerprint: str
    scope_fingerprint: str
    test_result_fingerprint: str

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(self.__dict__, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


class ApprovalManager:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    def request(self, context: ActionContext, *, now: datetime, ttl_seconds: int) -> str:
        approval_id = hashlib.sha256(f"{context.fingerprint}:{now.isoformat()}".encode()).hexdigest()[:24]
        expires = now.astimezone(timezone.utc) + timedelta(seconds=ttl_seconds)
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO approvals(
                  approval_id, action, target, requested_at, expires_at,
                  action_fingerprint, tested_commit_sha
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (approval_id, context.action, json.dumps(context.targets), now.astimezone(timezone.utc).isoformat(),
                 expires.isoformat(), context.fingerprint, context.tested_commit_sha),
            )
        return approval_id

    def decide(self, approval_id: str, *, approved: bool, actor: str, reason: str | None) -> None:
        decision = "approved" if approved else f"rejected: {reason or 'no reason supplied'}"
        with self.store.connect() as connection:
            cursor = connection.execute(
                "UPDATE approvals SET decision=?, actor=? WHERE approval_id=? AND decision IS NULL",
                (decision, actor, approval_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"unknown or already decided approval: {approval_id}")

    def authorized(self, context: ActionContext, *, now: datetime) -> bool:
        with self.store.connect() as connection:
            row = connection.execute(
                """
                SELECT decision, expires_at FROM approvals
                WHERE action_fingerprint=? AND tested_commit_sha=?
                ORDER BY requested_at DESC LIMIT 1
                """,
                (context.fingerprint, context.tested_commit_sha),
            ).fetchone()
        return bool(row and row["decision"] == "approved" and row["expires_at"] > now.astimezone(timezone.utc).isoformat())
