"""Isolated live-provider verification through the complete controller cycle."""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .attempts import AttemptRecorder
from .engine import ControllerCycle, ExecutionEngine
from .execution import ExecutionProvider, ImplementationRunner, run_required_tests
from .linear_client import FakeLinearClient, RemoteIssue
from .poller import Poller
from .reconciler import Reconciler
from .state import StateStore
from .worktrees import GitWorktreeManager


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _initialize_fixture(repo: Path, provider_name: str) -> None:
    if (repo / ".git").is_dir():
        return
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "runr-verification@example.test")
    _git(repo, "config", "user.name", "Runr Verification")
    (repo / "docs").mkdir()
    (repo / "docs" / "INDEX.md").write_text("# Verification fixture\n", encoding="utf-8")
    (repo / "docs" / "subsystems.yaml").write_text(
        "subsystems:\n"
        "  - id: smoke\n"
        "    workstream: WS-1\n"
        "    owned_paths: [src/**]\n",
        encoding="utf-8",
    )
    skill_dir = repo / ".agents" / "skills" / "runr-provider-smoke"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# Runr provider smoke\n\n"
        "Implement the exact bounded ticket in the current worktree. "
        "Do not access Linear, commit, deploy, or change any undeclared path.\n",
        encoding="utf-8",
    )
    expected = f"Runr {provider_name} controller smoke passed."
    (repo / "verify.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "assert sys.version_info[:3] == (3, 12, 7), sys.version\n"
        f"assert Path('src/result.txt').read_text(encoding='utf-8').strip() == {expected!r}\n",
        encoding="utf-8",
    )
    (repo / "AGENTS.md").write_text(
        "Use only the ticket's allowed paths. Never commit or deploy.\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "test: initialize provider verification fixture")


def run_provider_verification(
    data_dir: Path,
    provider_name: str,
    provider: ExecutionProvider,
    *,
    run_id: str,
) -> dict[str, Any]:
    """Run or safely resume one deterministic isolated provider ticket."""

    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        raise ValueError("run-id may contain only letters, numbers, dots, underscores, and hyphens")
    runtime_root = data_dir / "verification" / run_id
    repo = runtime_root / "repo"
    state_root = runtime_root / "runtime"
    _initialize_fixture(repo, provider_name)
    store = StateStore(state_root / "state.db")
    expected = f"Runr {provider_name} controller smoke passed."
    issue = RemoteIssue(
        f"verification-{run_id}",
        f"VERIFY-{provider_name.upper().replace('_SUBSCRIPTION', '')}",
        "2026-09-17T00:00:00+00:00",
        f"Verify {provider_name} through the Runr controller",
        "isolated provider verification",
        lifecycle_state="Ready",
        payload={
            "title": f"Verify {provider_name} through the Runr controller",
            "acceptance_criteria": f"Create src/result.txt containing exactly: {expected}",
            "subsystem": "smoke",
            "allowed_paths": ["src/result.txt"],
            "required_reading": [".agents/skills/runr-provider-smoke/SKILL.md", "verify.py"],
            "required_tests": ["python verify.py"],
            "skill": "runr-provider-smoke",
        },
    )
    runner = ImplementationRunner(
        GitWorktreeManager(repo, state_root / "worktrees"),
        AttemptRecorder(store),
        state_root,
        test_runner=lambda worktree, tests: run_required_tests(
            worktree, tests, python_executable=Path(sys.executable)
        ),
    )
    engine = ExecutionEngine(
        store,
        repo,
        runner,
        {provider_name: provider},
        provider_order=(provider_name,),
        owner=f"verification-{run_id}",
    )
    cycle = ControllerCycle(Poller(store, FakeLinearClient([issue])), Reconciler(store), engine).run(
        now=datetime.now(timezone.utc)
    )
    with store.connect() as connection:
        approval = connection.execute(
            "SELECT approval_id, decision, tested_commit_sha FROM approvals ORDER BY requested_at DESC LIMIT 1"
        ).fetchone()
        attempt = connection.execute(
            "SELECT provider, model, outcome, session_id FROM attempts ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        checkpoint = connection.execute(
            "SELECT commit_sha, worktree, summary_json FROM checkpoints ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    worktree = Path(checkpoint["worktree"]) if checkpoint and checkpoint["worktree"] else None
    result_file = worktree / "src" / "result.txt" if worktree else None
    tests_passed = bool(result_file and result_file.is_file() and result_file.read_text(encoding="utf-8").strip() == expected)
    clean_worktree = bool(worktree and _git(worktree, "status", "--porcelain") == "")
    status = "awaiting_approval" if approval and approval["decision"] is None else "incomplete"
    return {
        "provider": provider_name,
        "model": provider.model,
        "run_id": run_id,
        "status": status,
        "processed_jobs": cycle.engine.processed,
        "tests_passed": tests_passed,
        "clean_worktree": clean_worktree,
        "commit_sha": checkpoint["commit_sha"] if checkpoint else None,
        "attempt_outcome": attempt["outcome"] if attempt else None,
        "approval_id": approval["approval_id"] if approval else None,
        "runtime_root": str(runtime_root),
    }
