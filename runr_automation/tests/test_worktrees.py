from pathlib import Path
import subprocess

import pytest

from runr_automation.worktrees import GitWorktreeManager, validate_changed_paths


def test_diff_outside_ticket_allowlist_is_rejected(tmp_path: Path) -> None:
    allowed = ("backend/", "runr_automation/tests/exact.py")
    escaped = validate_changed_paths(
        ("backend/a.py", "runr_automation/tests/exact.py", "frontend/app.ts"), allowed
    )
    assert escaped == ("frontend/app.ts",)


def test_path_prefix_does_not_allow_similarly_named_sibling() -> None:
    assert validate_changed_paths(("backend-secret/a.py",), ("backend/",)) == ("backend-secret/a.py",)


def test_new_worktree_defaults_to_permanent_predeployment_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "runr@example.test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Runr Test"], cwd=repo, check=True)
    (repo / "marker.txt").write_text("deployment\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "deployment baseline"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "switch", "-c", "predeployment/render-turso-r2"], cwd=repo, check=True, capture_output=True)
    (repo / "marker.txt").write_text("predeployment\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "predeployment baseline"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "switch", "main"], cwd=repo, check=True, capture_output=True)

    worktree, _ = GitWorktreeManager(repo, tmp_path / "worktrees").create("RUN-900")

    assert (worktree / "marker.txt").read_text(encoding="utf-8") == "predeployment\n"


def test_worktree_rejects_a_non_predeployment_base(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    manager = GitWorktreeManager(repo, tmp_path / "worktrees")

    with pytest.raises(ValueError, match="permanent predeployment"):
        manager.create("RUN-901", base_ref="HEAD")
