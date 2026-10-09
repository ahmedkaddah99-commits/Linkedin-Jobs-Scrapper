"""A ticket worktree must not take its shared virtualenv with it."""

import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows directory junctions only")
def test_removing_worktree_detaches_venv_junction_without_deleting_target(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "runr@example.test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Runr Test"], cwd=repo, check=True)
    (repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=repo, check=True, capture_output=True)

    worktree = tmp_path / "ticket"
    subprocess.run(
        ["git", "worktree", "add", "-b", "ticket", str(worktree)],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    shared_venv = tmp_path / "shared-venv"
    shared_venv.mkdir()
    sentinel = shared_venv / "sentinel.txt"
    sentinel.write_text("keep\n", encoding="utf-8")
    junction_path = str(worktree / ".venv").replace("'", "''")
    target_path = str(shared_venv).replace("'", "''")
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"New-Item -ItemType Junction -Path '{junction_path}' -Target '{target_path}' | Out-Null",
        ],
        check=True,
        capture_output=True,
    )

    script = Path(__file__).resolve().parents[1] / "scripts" / "remove-worktree-safely.ps1"
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(script),
            "-RepositoryPath",
            str(repo),
            "-WorktreePath",
            str(worktree),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert not worktree.exists()
    assert sentinel.read_text(encoding="utf-8") == "keep\n"


@pytest.mark.skipif(os.name != "nt", reason="Windows worktree cleanup only")
def test_removal_refuses_shared_checkout(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    script = Path(__file__).resolve().parents[1] / "scripts" / "remove-worktree-safely.ps1"

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(script),
            "-RepositoryPath",
            str(repo),
            "-WorktreePath",
            str(repo),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert repo.is_dir()
