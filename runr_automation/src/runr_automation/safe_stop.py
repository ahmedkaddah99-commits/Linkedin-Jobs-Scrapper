"""Conservative provider-capacity detection and durable worktree checkpoints."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .redaction import redact


@dataclass(frozen=True)
class UsagePolicy:
    reserve_tokens: int = 12_000
    max_attempt_tokens: int = 80_000
    max_attempt_seconds: int = 45 * 60
    minimum_remaining_ratio: float = 0.15


@dataclass(frozen=True)
class UsageSnapshot:
    used_tokens: int = 0
    elapsed_seconds: int = 0
    remaining_tokens: int | None = None
    total_token_allowance: int | None = None


def safe_stop_reason(policy: UsagePolicy, usage: UsageSnapshot) -> str | None:
    """Return a stop reason without pretending unknown subscription balances are known."""

    if usage.remaining_tokens is not None:
        if usage.remaining_tokens <= policy.reserve_tokens:
            return "provider_reserve"
        if usage.total_token_allowance:
            ratio = usage.remaining_tokens / usage.total_token_allowance
            if ratio <= policy.minimum_remaining_ratio:
                return "provider_remaining_ratio"
    if usage.used_tokens >= max(0, policy.max_attempt_tokens - policy.reserve_tokens):
        return "local_token_reserve"
    if usage.elapsed_seconds >= policy.max_attempt_seconds:
        return "local_time_limit"
    return None


@dataclass(frozen=True)
class SafeStopContext:
    job_id: str
    issue_identifier: str
    worktree: Path
    session_id: str | None
    allowed_paths: tuple[str, ...]


class WorktreeCheckpoint(Protocol):
    def validate_scope(self, context: SafeStopContext) -> tuple[str, ...]: ...

    def run_checkpoint_tests(self, context: SafeStopContext) -> bool: ...

    def commit_checkpoint(self, context: SafeStopContext, message: str) -> str: ...


@dataclass(frozen=True)
class SafeStopOutcome:
    status: str
    reason: str
    checkpoint_path: str
    commit_sha: str | None
    tests_passed: bool | None
    escaped_paths: tuple[str, ...] = ()


class SafeStopCoordinator:
    def __init__(self, data_dir: str | Path, worktree: WorktreeCheckpoint) -> None:
        self.checkpoint_dir = Path(data_dir) / "checkpoints"
        self.worktree = worktree

    def stop(self, context: SafeStopContext, *, reason: str) -> SafeStopOutcome:
        escaped = self.worktree.validate_scope(context)
        tests_passed: bool | None = None
        commit_sha: str | None = None
        status = "needs_review" if escaped else "waiting_for_capacity"
        if not escaped:
            tests_passed = self.worktree.run_checkpoint_tests(context)
            commit_sha = self.worktree.commit_checkpoint(
                context,
                f"checkpoint({context.issue_identifier}): safe stop before provider capacity",
            )
        path = self._write_handoff(context, reason, status, commit_sha, tests_passed, escaped)
        return SafeStopOutcome(status, reason, str(path), commit_sha, tests_passed, escaped)

    def _write_handoff(
        self,
        context: SafeStopContext,
        reason: str,
        status: str,
        commit_sha: str | None,
        tests_passed: bool | None,
        escaped: tuple[str, ...],
    ) -> Path:
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        path = self.checkpoint_dir / f"{context.job_id}-safe-stop.json"
        temporary = path.with_suffix(".tmp")
        payload = redact(
            {
                "version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "job_id": context.job_id,
                "issue": context.issue_identifier,
                "worktree": str(context.worktree),
                "session_id": context.session_id,
                "allowed_paths": context.allowed_paths,
                "reason": reason,
                "status": status,
                "commit_sha": commit_sha,
                "tests_passed": tests_passed,
                "escaped_paths": escaped,
                "next_action": "resume_provider_session_or_start_from_handoff",
            }
        )
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)
        return path
