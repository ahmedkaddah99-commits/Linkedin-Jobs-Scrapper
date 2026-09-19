import subprocess
from pathlib import Path
import sys

from runr_automation.attempts import AttemptRecorder
from runr_automation.execution import ImplementationRunner, TicketExecutionRequest, run_required_tests
from runr_automation.providers.base import ProviderResult
from runr_automation.queue import JobQueue
from runr_automation.scope_router import ScopeManifest
from runr_automation.state import StateStore
from runr_automation.worktrees import GitWorktreeManager


class WritingProvider:
    name = "codex"
    model = "test-model"

    def __init__(self, relative_path: str, output: str = "session id: session-1") -> None:
        self.relative_path = relative_path
        self.output = output

    def run(self, prompt_path: Path, *, cwd: Path) -> ProviderResult:
        assert prompt_path.is_file()
        assert "Allowed writes" in prompt_path.read_text(encoding="utf-8")
        target = cwd / self.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("implemented\n", encoding="utf-8")
        return ProviderResult(0, self.output, "session-1")


class PartialCapacityProvider(WritingProvider):
    def run(self, prompt_path: Path, *, cwd: Path) -> ProviderResult:
        super().run(prompt_path, cwd=cwd)
        return ProviderResult(1, "429 capacity exhausted", "session-capacity")


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "runr@example.test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Runr Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    return repo


def _request(job_id: str) -> TicketExecutionRequest:
    return TicketExecutionRequest(
        job_id=job_id,
        issue_id="linear-1",
        identifier="RUN-101",
        title="Write bounded artifact",
        acceptance_criteria="allowed/result.txt exists",
        fingerprint="fingerprint-1",
        scope=ScopeManifest(
            issue_id="linear-1",
            subsystem="test",
            co_owners=(),
            allowed_reads=("README.md",),
            allowed_writes=("allowed/",),
            denied_roots=("forbidden/**",),
            required_tests=("focused-test",),
        ),
        skill="runr-ticket-start",
    )


def test_runner_commits_only_scope_valid_tested_changes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    store = StateStore(tmp_path / "state.db")
    job_id = JobQueue(store).enqueue("implement", "linear-1", "fingerprint-1")
    runner = ImplementationRunner(
        GitWorktreeManager(repo, tmp_path / "worktrees"),
        AttemptRecorder(store),
        tmp_path,
        test_runner=lambda worktree, tests: tests == ("focused-test",),
    )

    result = runner.run(_request(job_id), WritingProvider("allowed/result.txt"))

    assert result.status == "implemented"
    assert result.tests_passed is True
    assert result.commit_sha
    assert result.changed_paths == ("allowed/result.txt",)
    assert subprocess.run(["git", "status", "--porcelain"], cwd=result.worktree, check=True, capture_output=True, text=True).stdout == ""
    with store.connect() as connection:
        checkpoint = connection.execute("SELECT * FROM checkpoints WHERE job_id=?", (job_id,)).fetchone()
    assert checkpoint["commit_sha"] == result.commit_sha
    assert checkpoint["resumable_provider_session_id"] == "session-1"


def test_runner_rejects_scope_escape_without_commit(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    store = StateStore(tmp_path / "state.db")
    job_id = JobQueue(store).enqueue("implement", "linear-1", "fingerprint-1")
    runner = ImplementationRunner(
        GitWorktreeManager(repo, tmp_path / "worktrees"),
        AttemptRecorder(store),
        tmp_path,
        test_runner=lambda *_: True,
    )

    result = runner.run(_request(job_id), WritingProvider("forbidden/result.txt"))

    assert result.status == "needs_review"
    assert result.commit_sha is None
    assert result.escaped_paths == ("forbidden/result.txt",)


def test_runner_checkpoints_scope_valid_partial_work_on_capacity_stop(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    store = StateStore(tmp_path / "state.db")
    job_id = JobQueue(store).enqueue("implement", "linear-1", "fingerprint-1")
    runner = ImplementationRunner(
        GitWorktreeManager(repo, tmp_path / "worktrees"),
        AttemptRecorder(store),
        tmp_path,
        test_runner=lambda *_: False,
    )

    result = runner.run(_request(job_id), PartialCapacityProvider("allowed/result.txt"))

    assert result.status == "waiting_for_capacity"
    assert result.commit_sha
    assert result.tests_passed is False
    assert subprocess.run(
        ["git", "status", "--porcelain"], cwd=result.worktree, check=True,
        capture_output=True, text=True,
    ).stdout == ""
    with store.connect() as connection:
        checkpoint = connection.execute("SELECT * FROM checkpoints WHERE job_id=?", (job_id,)).fetchone()
    assert checkpoint["commit_sha"] == result.commit_sha


def test_runner_blocks_commit_until_external_verification_is_supplied(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    store = StateStore(tmp_path / "state.db")
    job_id = JobQueue(store).enqueue("implement", "linear-1", "fingerprint-1")
    request = _request(job_id)
    request = TicketExecutionRequest(
        **{
            **request.__dict__,
            "scope": ScopeManifest(
                **{
                    **request.scope.__dict__,
                    "external_verification": ("systemd-analyze verify runr.target",),
                }
            ),
        }
    )
    runner = ImplementationRunner(
        GitWorktreeManager(repo, tmp_path / "worktrees"),
        AttemptRecorder(store),
        tmp_path,
        test_runner=lambda *_: True,
    )

    result = runner.run(request, WritingProvider("allowed/result.txt"))

    assert result.status == "external_verification_required"
    assert result.commit_sha is None
    prompt = (tmp_path / "prompts" / f"{job_id}.md").read_text(encoding="utf-8")
    assert "External verification" in prompt
    assert "systemd-analyze verify runr.target" in prompt
    with store.connect() as connection:
        checkpoint = connection.execute("SELECT * FROM checkpoints WHERE job_id=?", (job_id,)).fetchone()
    assert checkpoint["phase"] == "external_verification_required"


def test_required_tests_use_argument_lists_and_reject_unapproved_executables(tmp_path: Path) -> None:
    passing = f'"{sys.executable}" -c "print(123)"'
    markdown_wrapped = f'`"{sys.executable}" -c "print(123)"`'

    assert run_required_tests(tmp_path, (passing,), python_executable=Path(sys.executable)) is True
    assert run_required_tests(tmp_path, (markdown_wrapped,), python_executable=Path(sys.executable)) is True
    assert run_required_tests(tmp_path, ("curl https://example.com",), python_executable=Path(sys.executable)) is False
