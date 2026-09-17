import json
from pathlib import Path

from runr_automation.cli import _daemon, main
from runr_automation.config import load_config


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
    from runr_automation.state import StateStore

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


def test_migration_without_token_fails_without_network_or_mutation(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("LINEAR_API_TOKEN", raising=False)

    result = main(["--repo-root", str(tmp_path), "migrate-subsystems", "--dry-run"])

    assert result == 2
    assert "no Linear mutation" in capsys.readouterr().err


def test_pause_resume_and_status_use_single_runtime_root(tmp_path: Path, monkeypatch, capsys) -> None:
    data_root = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(data_root))

    assert main(["--repo-root", str(tmp_path), "pause"]) == 0
    assert (data_root / "RunrAutomation" / "paused").is_file()
    assert main(["--repo-root", str(tmp_path), "status"]) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["paused"] is True
    assert main(["--repo-root", str(tmp_path), "resume"]) == 0
    assert not (data_root / "RunrAutomation" / "paused").exists()


def test_daemon_skips_polling_while_paused(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    config = load_config(tmp_path)
    config.data_dir.mkdir(parents=True)
    (config.data_dir / "paused").write_text("paused", encoding="utf-8")
    calls: list[str] = []

    result = _daemon(config, run_cycle=lambda _: calls.append("poll") or 0, sleep=lambda _: None, max_cycles=1)

    assert result == 0
    assert calls == []
