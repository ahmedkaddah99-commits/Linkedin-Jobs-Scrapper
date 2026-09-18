import json
from dataclasses import dataclass, field
from pathlib import Path

from runr_automation.safe_stop import (
    SafeStopContext,
    SafeStopCoordinator,
    UsagePolicy,
    UsageSnapshot,
    safe_stop_reason,
)


@dataclass
class FakeWorktree:
    escaped: tuple[str, ...] = ()
    tests_pass: bool = True
    calls: list[str] = field(default_factory=list)

    def validate_scope(self, context: SafeStopContext) -> tuple[str, ...]:
        self.calls.append("validate")
        return self.escaped

    def run_checkpoint_tests(self, context: SafeStopContext) -> bool:
        self.calls.append("tests")
        return self.tests_pass

    def commit_checkpoint(self, context: SafeStopContext, message: str) -> str:
        self.calls.append("commit")
        return "abc123"


def test_authoritative_remaining_credits_trigger_reserve_before_exhaustion() -> None:
    policy = UsagePolicy(reserve_tokens=10_000, max_attempt_tokens=80_000, max_attempt_seconds=2700)

    assert safe_stop_reason(policy, UsageSnapshot(remaining_tokens=9_999)) == "provider_reserve"


def test_unknown_provider_balance_uses_conservative_local_attempt_budget() -> None:
    policy = UsagePolicy(reserve_tokens=10_000, max_attempt_tokens=80_000, max_attempt_seconds=2700)

    assert safe_stop_reason(policy, UsageSnapshot(used_tokens=70_001)) == "local_token_reserve"
    assert safe_stop_reason(policy, UsageSnapshot(used_tokens=1_000, elapsed_seconds=60)) is None


def test_safe_stop_validates_tests_commits_and_writes_resumable_handoff(tmp_path: Path) -> None:
    worktree = FakeWorktree()
    coordinator = SafeStopCoordinator(tmp_path, worktree)
    context = SafeStopContext("job-1", "RUN-5", tmp_path / "worktree", "session-secret", ("backend/",))

    outcome = coordinator.stop(context, reason="provider_reserve")

    assert outcome.status == "waiting_for_capacity"
    assert outcome.commit_sha == "abc123"
    assert worktree.calls == ["validate", "tests", "commit"]
    payload = json.loads(Path(outcome.checkpoint_path).read_text(encoding="utf-8"))
    assert payload["next_action"] == "resume_provider_session_or_start_from_handoff"
    assert payload["session_id"] == "session-secret"


def test_scope_escape_never_commits_and_requires_review(tmp_path: Path) -> None:
    worktree = FakeWorktree(escaped=("forbidden.txt",))
    context = SafeStopContext("job-1", "RUN-5", tmp_path / "worktree", None, ("backend/",))

    outcome = SafeStopCoordinator(tmp_path, worktree).stop(context, reason="local_time_limit")

    assert outcome.status == "needs_review"
    assert outcome.commit_sha is None
    assert worktree.calls == ["validate"]
