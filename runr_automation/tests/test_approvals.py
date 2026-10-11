from datetime import datetime, timedelta, timezone
from pathlib import Path

from runr_automation.approvals import ApprovalManager, ActionContext
from runr_automation.state import StateStore


def context(commit="abc", scope="scope-1"):
    return ActionContext("predeployment", ("RUN-5",), commit, "issue-1", scope, "tests-1")


def test_action_requires_matching_unexpired_approval(tmp_path: Path) -> None:
    manager = ApprovalManager(StateStore(tmp_path / "state.db"))
    now = datetime(2026, 9, 17, tzinfo=timezone.utc)
    approval_id = manager.request(context(), now=now, ttl_seconds=60)
    assert manager.authorized(context(), now=now) is False
    manager.decide(approval_id, approved=True, actor="local-user", reason=None)
    assert manager.authorized(context(), now=now + timedelta(seconds=30)) is True
    assert manager.authorized(context(), now=now + timedelta(seconds=61)) is False


def test_commit_issue_scope_or_test_change_invalidates_approval(tmp_path: Path) -> None:
    manager = ApprovalManager(StateStore(tmp_path / "state.db"))
    now = datetime(2026, 9, 17, tzinfo=timezone.utc)
    approval_id = manager.request(context(), now=now, ttl_seconds=60)
    manager.decide(approval_id, approved=True, actor="local-user", reason=None)

    assert manager.authorized(context(commit="changed"), now=now) is False
    assert manager.authorized(context(scope="changed"), now=now) is False
