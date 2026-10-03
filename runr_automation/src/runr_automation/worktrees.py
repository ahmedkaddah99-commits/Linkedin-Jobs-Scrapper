"""Issue worktree creation and exact diff-boundary validation."""

from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath


PERMANENT_PREDEPLOYMENT_REF = "predeployment/render-turso-r2"


def _normalized(path: str) -> str:
    raw = path.replace("\\", "/")
    directory = raw.endswith("/")
    while raw.startswith("./"):
        raw = raw[2:]
    value = PurePosixPath(raw).as_posix()
    if value.startswith("../") or value == "..":
        raise ValueError(f"path escapes repository: {path}")
    return value + "/" if directory else value


def validate_changed_paths(changed_paths: tuple[str, ...], allowed_paths: tuple[str, ...]) -> tuple[str, ...]:
    allowed = tuple(_normalized(path) for path in allowed_paths)
    escaped = []
    for raw in changed_paths:
        path = _normalized(raw)
        if not any(path == item.rstrip("/") or (item.endswith("/") and path.startswith(item)) for item in allowed):
            escaped.append(path)
    return tuple(escaped)


class GitWorktreeManager:
    def __init__(self, repo_root: Path, worktree_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.worktree_root = worktree_root.resolve()

    def create(
        self, issue_identifier: str, base_ref: str = PERMANENT_PREDEPLOYMENT_REF
    ) -> tuple[Path, str]:
        if base_ref != PERMANENT_PREDEPLOYMENT_REF:
            raise ValueError(
                "issue worktrees must be created from the permanent predeployment ref "
                f"{PERMANENT_PREDEPLOYMENT_REF}"
            )
        slug = issue_identifier.casefold().replace("_", "-")
        branch = f"runr-auto/{slug}"
        path = self.worktree_root / slug
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            current = subprocess.run(
                ["git", "branch", "--show-current"], cwd=path, check=True, capture_output=True, text=True
            ).stdout.strip()
            if current != branch:
                raise RuntimeError(f"worktree {path} belongs to {current}, expected {branch}")
            return path, branch
        subprocess.run(
            ["git", "worktree", "add", "-b", branch, str(path), base_ref],
            cwd=self.repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return path, branch

    def changed_paths(self, worktree: Path) -> tuple[str, ...]:
        result = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=worktree,
            check=True,
            capture_output=True,
        )
        entries = result.stdout.decode("utf-8", errors="replace").split("\0")
        return tuple(entry[3:] for entry in entries if len(entry) >= 4)
