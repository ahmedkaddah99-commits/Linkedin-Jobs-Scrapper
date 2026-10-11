"""Scoped provider execution inside issue-specific Git worktrees."""

from __future__ import annotations

import subprocess
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from .attempts import AttemptRecorder
from .providers.base import ProviderErrorKind, ProviderResult, classify_provider_error
from .scope_router import ScopeManifest
from .worktrees import GitWorktreeManager, PERMANENT_PREDEPLOYMENT_REF, validate_changed_paths


_TEST_EXECUTABLES = {"python", "python.exe", "node", "node.exe", "npm", "npm.cmd", "npx", "npx.cmd"}


def run_required_tests(
    worktree: Path,
    commands: tuple[str, ...],
    *,
    python_executable: Path,
    timeout_seconds: int = 900,
) -> bool:
    """Run only locally approved test executables without a command shell."""

    for command in commands:
        try:
            args = [part[1:-1] if len(part) >= 2 and part[0] == part[-1] == '"' else part for part in shlex.split(command, posix=False)]
        except ValueError:
            return False
        if not args:
            return False
        executable_name = Path(args[0]).name.casefold()
        if executable_name not in _TEST_EXECUTABLES:
            return False
        if executable_name in {"python", "python.exe"} or args[0].replace("/", "\\").casefold().endswith(
            ".venv\\scripts\\python.exe"
        ):
            args[0] = str(python_executable)
        try:
            completed = subprocess.run(
                args, cwd=worktree, capture_output=True, text=True, timeout=timeout_seconds, check=False
            )
        except (OSError, subprocess.SubprocessError):
            return False
        if completed.returncode:
            return False
    return True


class ExecutionProvider(Protocol):
    name: str
    model: str

    def run(self, prompt_path: Path, *, cwd: Path) -> ProviderResult: ...


@dataclass(frozen=True)
class TicketExecutionRequest:
    job_id: str
    issue_id: str
    identifier: str
    title: str
    acceptance_criteria: str
    fingerprint: str
    scope: ScopeManifest
    skill: str
    base_ref: str = PERMANENT_PREDEPLOYMENT_REF


@dataclass(frozen=True)
class TicketExecutionResult:
    status: str
    provider: str
    worktree: Path
    changed_paths: tuple[str, ...]
    commit_sha: str | None = None
    tests_passed: bool | None = None
    session_id: str | None = None
    escaped_paths: tuple[str, ...] = ()
    error_kind: ProviderErrorKind | None = None


def build_ticket_prompt(request: TicketExecutionRequest) -> str:
    reads = "\n".join(f"- {path}" for path in request.scope.allowed_reads)
    writes = "\n".join(f"- {path}" for path in request.scope.allowed_writes)
    tests = "\n".join(f"- {command}" for command in request.scope.required_tests) or "- none"
    return f"""# {request.identifier}: {request.title}

Invoke and follow the `{request.skill}` skill explicitly.

## Acceptance criteria

{request.acceptance_criteria}

## Allowed reads

{reads}

## Allowed writes

{writes}

## Required tests

{tests}

## Hard boundaries

- Work only in the current isolated worktree.
- Do not commit, deploy, access Linear, install packages, or clean up the worktree.
- Do not read or write outside the manifest above.
- If capacity is low or a required action is blocked, stop and report the exact state.
"""


class ImplementationRunner:
    def __init__(
        self,
        worktrees: GitWorktreeManager,
        attempts: AttemptRecorder,
        data_dir: Path,
        *,
        test_runner: Callable[[Path, tuple[str, ...]], bool],
    ) -> None:
        self.worktrees = worktrees
        self.attempts = attempts
        self.data_dir = data_dir
        self.test_runner = test_runner

    def run(self, request: TicketExecutionRequest, provider: ExecutionProvider) -> TicketExecutionResult:
        worktree, _ = self.worktrees.create(request.identifier, request.base_ref)
        prompt_dir = self.data_dir / "prompts"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = prompt_dir / f"{request.job_id}.md"
        prompt_path.write_text(build_ticket_prompt(request), encoding="utf-8")
        attempt_id = self.attempts.start(request.job_id, provider.name, provider.model)
        scoped_runner = getattr(provider, "run_implementation", None)
        if scoped_runner is None:
            result = provider.run(prompt_path, cwd=worktree)
        else:
            result = scoped_runner(request, prompt_path, cwd=worktree, test_runner=self.test_runner)
        session_id = result.session_id
        if result.returncode:
            kind = classify_provider_error(result.output)
            retryable = kind in {ProviderErrorKind.CAPACITY, ProviderErrorKind.TRANSIENT}
            changed_paths = self.worktrees.changed_paths(worktree)
            escaped = validate_changed_paths(changed_paths, request.scope.allowed_writes)
            if retryable and escaped:
                self.attempts.finish(
                    attempt_id,
                    "scope_escape",
                    usage=result.usage,
                    error=result.output,
                    session_id=session_id,
                )
                self.attempts.checkpoint(
                    request.job_id,
                    "scope_escape",
                    artifact_paths=changed_paths,
                    worktree=worktree,
                    session_id=session_id,
                    summary={"escaped_paths": escaped, "provider": provider.name},
                )
                return TicketExecutionResult(
                    "needs_review",
                    provider.name,
                    worktree,
                    changed_paths,
                    session_id=session_id,
                    escaped_paths=escaped,
                    error_kind=kind,
                )
            tests_passed = self.test_runner(worktree, request.scope.required_tests) if retryable else None
            commit_sha = self._commit(request, worktree, changed_paths) if retryable else None
            outcome = "capacity" if retryable else "failed"
            self.attempts.finish(
                attempt_id,
                outcome,
                usage=result.usage,
                error=result.output,
                session_id=session_id,
            )
            self.attempts.checkpoint(
                request.job_id,
                "provider_stop",
                artifact_paths=changed_paths,
                commit_sha=commit_sha,
                worktree=worktree,
                session_id=session_id,
                summary={
                    "provider": provider.name,
                    "error_kind": kind.value,
                    "tests_passed": tests_passed,
                },
            )
            return TicketExecutionResult(
                "waiting_for_capacity" if retryable else "failed",
                provider.name,
                worktree,
                changed_paths,
                commit_sha=commit_sha,
                tests_passed=tests_passed,
                session_id=session_id,
                error_kind=kind,
            )

        changed_paths = self.worktrees.changed_paths(worktree)
        escaped = validate_changed_paths(changed_paths, request.scope.allowed_writes)
        if escaped:
            self.attempts.finish(
                attempt_id,
                "scope_escape",
                usage=result.usage,
                session_id=session_id,
            )
            self.attempts.checkpoint(
                request.job_id,
                "scope_escape",
                artifact_paths=changed_paths,
                worktree=worktree,
                session_id=session_id,
                summary={"escaped_paths": escaped},
            )
            return TicketExecutionResult(
                "needs_review",
                provider.name,
                worktree,
                changed_paths,
                session_id=session_id,
                escaped_paths=escaped,
            )

        tests_passed = self.test_runner(worktree, request.scope.required_tests)
        if not tests_passed:
            self.attempts.finish(
                attempt_id,
                "tests_failed",
                usage=result.usage,
                session_id=session_id,
            )
            self.attempts.checkpoint(
                request.job_id,
                "tests_failed",
                artifact_paths=changed_paths,
                worktree=worktree,
                session_id=session_id,
                summary={"tests_passed": False},
            )
            return TicketExecutionResult(
                "failed", provider.name, worktree, changed_paths, tests_passed=False, session_id=session_id
            )

        commit_sha = self._commit(request, worktree, changed_paths)
        self.attempts.finish(
            attempt_id,
            "implemented",
            usage=result.usage,
            session_id=session_id,
        )
        self.attempts.checkpoint(
            request.job_id,
            "implemented",
            artifact_paths=changed_paths,
            commit_sha=commit_sha,
            worktree=worktree,
            session_id=session_id,
            summary={"tests_passed": True, "provider": provider.name},
        )
        return TicketExecutionResult(
            "implemented",
            provider.name,
            worktree,
            changed_paths,
            commit_sha=commit_sha,
            tests_passed=True,
            session_id=session_id,
        )

    @staticmethod
    def _commit(request: TicketExecutionRequest, worktree: Path, changed_paths: tuple[str, ...]) -> str:
        if not changed_paths:
            return subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=worktree, check=True, capture_output=True, text=True
            ).stdout.strip()
        subprocess.run(["git", "add", "--", *changed_paths], cwd=worktree, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"checkpoint({request.identifier}): validated implementation"],
            cwd=worktree,
            check=True,
            capture_output=True,
        )
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=worktree, check=True, capture_output=True, text=True
        ).stdout.strip()
