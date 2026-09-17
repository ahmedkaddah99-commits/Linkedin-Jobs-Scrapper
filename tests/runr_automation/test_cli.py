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
