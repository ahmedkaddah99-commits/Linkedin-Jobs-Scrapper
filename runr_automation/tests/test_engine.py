import subprocess
from datetime import datetime, timezone
from pathlib import Path

from runr_automation.engine import ControllerCycle, ExecutionEngine
from runr_automation.execution import ImplementationRunner
from runr_automation.linear_client import FakeLinearClient, RemoteIssue
from runr_automation.poller import Poller
from runr_automation.providers.base import ProviderResult
from runr_automation.queue import JobQueue
from runr_automation.reconciler import Reconciler
from runr_automation.state import StateStore
from runr_automation.attempts import AttemptRecorder
from runr_automation.worktrees import GitWorktreeManager


class CapacityProvider:
    name = "codex"
    model = "codex-model"

    def run(self, prompt_path: Path, *, cwd: Path) -> ProviderResult:
        return ProviderResult(1, "429 capacity exhausted", "codex-session")


class SuccessfulProvider:
    name = "opencode_subscription"
    model = "opencode-model"

    def run(self, prompt_path: Path, *, cwd: Path) -> ProviderResult:
        target = cwd / "allowed" / "result.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("implemented\n", encoding="utf-8")
        return ProviderResult(0, "done", "opencode-session")


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "runr@example.test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Runr Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "subsystems.yaml").write_text(
        "subsystems:\n  - id: smoke\n    workstream: WS-1\n    owned_paths: [allowed/**]\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "branch", "predeployment/render-turso-r2"], cwd=repo, check=True, capture_output=True
    )
    return repo


def test_issue_runs_from_poll_to_scoped_commit_and_approval_with_capacity_failover(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    data_dir = tmp_path / "runtime"
    store = StateStore(data_dir / "state.db")
    issue = RemoteIssue(
        "linear-101",
        "RUN-101",
        "2026-09-17T10:00:00+00:00",
        "Write bounded artifact",
        "structured",
        lifecycle_state="Ready",
        payload={
            "title": "Write bounded artifact",
            "acceptance_criteria": "allowed/result.txt exists",
            "subsystem": "smoke",
            "allowed_paths": ["allowed/"],
            "required_reading": ["README.md"],
            "required_tests": ["focused-test"],
            "co_owners": [],
        },
    )
    poller = Poller(store, FakeLinearClient([issue]))
    runner = ImplementationRunner(
        GitWorktreeManager(repo, data_dir / "worktrees"),
        AttemptRecorder(store),
        data_dir,
        test_runner=lambda worktree, tests: tests == ("focused-test",),
    )
    engine = ExecutionEngine(
        store,
        repo,
        runner,
        {"codex": CapacityProvider(), "opencode_subscription": SuccessfulProvider()},
        provider_order=("codex", "opencode_subscription"),
        owner="worker-1",
    )

    cycle = ControllerCycle(poller, Reconciler(store), engine)
    cycle_result = cycle.run(now=datetime(2026, 9, 17, 10, tzinfo=timezone.utc))
    result = cycle_result.engine

    assert cycle_result.poll.recorded_events == 1
    assert cycle_result.reconcile.enqueued_jobs == 1
    assert result.awaiting_approval == 1
    assert result.failed == 0
    with store.connect() as connection:
        jobs = connection.execute("SELECT type, status FROM jobs ORDER BY rowid").fetchall()
        approval = connection.execute("SELECT * FROM approvals").fetchone()
        attempts = connection.execute("SELECT provider, outcome FROM attempts ORDER BY started_at").fetchall()
        circuit = connection.execute("SELECT * FROM provider_circuits WHERE provider_model='codex/codex-model'").fetchone()
    assert [tuple(row) for row in jobs] == [
        ("normalize", "complete"),
        ("deduplicate", "complete"),
        ("research", "complete"),
        ("parallelize", "complete"),
        ("implement", "complete"),
    ]
    assert approval["action"] == "predeployment"
    assert approval["decision"] is None
    assert [tuple(row) for row in attempts] == [
        ("codex", "capacity"),
        ("opencode_subscription", "implemented"),
    ]
    assert circuit["state"] == "open"

    rerun = engine.run_available(now=datetime(2026, 9, 17, 10, 1, tzinfo=timezone.utc))
    assert rerun.processed == 0
    assert JobQueue(store).claim("other", now=datetime(2026, 9, 17, 10, 1, tzinfo=timezone.utc), lease_seconds=30) is None


def test_external_verification_blocks_approval_after_local_tests_pass(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    data_dir = tmp_path / "runtime"
    store = StateStore(data_dir / "state.db")
    issue = RemoteIssue(
        "linear-external",
        "RUN-102",
        "2026-09-17T10:00:00+00:00",
        "Verify service topology",
        "structured",
        lifecycle_state="Ready",
        payload={
            "title": "Verify service topology",
            "acceptance_criteria": "the service topology is verified",
            "subsystem": "smoke",
            "allowed_paths": ["allowed/"],
            "required_tests": ["focused-test"],
            "external_verification": ["systemd-analyze verify runr.target"],
        },
    )
    poller = Poller(store, FakeLinearClient([issue]))
    runner = ImplementationRunner(
        GitWorktreeManager(repo, data_dir / "worktrees"),
        AttemptRecorder(store),
        data_dir,
        test_runner=lambda worktree, tests: tests == ("focused-test",),
    )
    engine = ExecutionEngine(
        store,
        repo,
        runner,
        {"opencode_subscription": SuccessfulProvider()},
        provider_order=("opencode_subscription",),
        owner="worker-external",
    )

    result = ControllerCycle(poller, Reconciler(store), engine).run(
        now=datetime(2026, 9, 17, 10, tzinfo=timezone.utc)
    ).engine

    assert result.awaiting_approval == 0
    assert result.external_blocked == 1
    with store.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0


def test_stale_job_is_completed_without_running_provider(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    data_dir = tmp_path / "runtime"
    store = StateStore(data_dir / "state.db")
    issue = RemoteIssue(
        "linear-stale", "RUN-STALE", "2026-09-17T10:00:00+00:00", "Current", "structured",
        payload={
            "title": "Current", "acceptance_criteria": "current", "subsystem": "smoke",
            "allowed_paths": ["allowed/result.txt"],
        },
    )
    Poller(store, FakeLinearClient([issue])).run_once()
    stale_job = JobQueue(store).enqueue("implement", "linear-stale", "obsolete-fingerprint")
    runner = ImplementationRunner(
        GitWorktreeManager(repo, data_dir / "worktrees"), AttemptRecorder(store), data_dir,
        test_runner=lambda *_: True,
    )
    engine = ExecutionEngine(
        store, repo, runner, {"opencode_subscription": SuccessfulProvider()},
        provider_order=("opencode_subscription",), owner="worker-stale",
    )

    result = engine.run_available(now=datetime(2026, 9, 17, 10, tzinfo=timezone.utc))

    assert result.processed == 1
    with store.connect() as connection:
        job = connection.execute("SELECT status FROM jobs WHERE job_id=?", (stale_job,)).fetchone()
        attempt_count = connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    assert job["status"] == "complete"
    assert attempt_count == 0
