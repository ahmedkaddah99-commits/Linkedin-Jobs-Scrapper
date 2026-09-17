import json
from pathlib import Path

from tools.runr_automation.cli import main


def test_doctor_reports_local_paths_without_credentials(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))

    result = main(["--repo-root", str(tmp_path), "doctor"])

    assert result == 0
    report = json.loads(capsys.readouterr().out)
    assert report["repo_root"] == str(tmp_path.resolve())
    assert report["state_db"].endswith("RunrAutomation\\state.db") or report["state_db"].endswith(
        "RunrAutomation/state.db"
    )
    assert "token" not in report
    assert "secret" not in report


def test_reconcile_command_processes_local_pending_events(tmp_path: Path, monkeypatch, capsys) -> None:
    local_app_data = tmp_path / "local-app-data"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    from tools.runr_automation.state import StateStore

    store = StateStore(local_app_data / "RunrAutomation" / "state.db")
    with store.connect() as connection:
        connection.execute(
            "INSERT INTO issues(linear_id, identifier, observed_at) VALUES (?, ?, ?)",
            ("linear-1", "RUN-1", "2026-09-17T10:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO events(event_key, payload_hash, first_seen, last_seen) VALUES (?, ?, ?, ?)",
            (
                "linear-1:2026-09-17T10:00:00+00:00:fingerprint",
                "fingerprint",
                "2026-09-17T10:00:00+00:00",
                "2026-09-17T10:00:00+00:00",
            ),
        )

    assert main(["--repo-root", str(tmp_path), "reconcile"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["enqueued_jobs"] == 1
