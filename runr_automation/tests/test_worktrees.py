from pathlib import Path

from runr_automation.worktrees import validate_changed_paths


def test_diff_outside_ticket_allowlist_is_rejected(tmp_path: Path) -> None:
    allowed = ("backend/", "runr_automation/tests/exact.py")
    escaped = validate_changed_paths(
        ("backend/a.py", "runr_automation/tests/exact.py", "frontend/app.ts"), allowed
    )
    assert escaped == ("frontend/app.ts",)


def test_path_prefix_does_not_allow_similarly_named_sibling() -> None:
    assert validate_changed_paths(("backend-secret/a.py",), ("backend/",)) == ("backend-secret/a.py",)
