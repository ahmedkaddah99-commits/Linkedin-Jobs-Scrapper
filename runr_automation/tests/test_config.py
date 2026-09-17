from pathlib import Path

from runr_automation.config import load_config


def test_config_uses_user_data_directory_and_environment_overrides(
    tmp_path: Path, monkeypatch
) -> None:
    local_app_data = tmp_path / "local-app-data"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("RUNR_AUTOMATION_POLL_INTERVAL_SECONDS", "30")

    config = load_config(tmp_path)

    assert config.data_dir == local_app_data / "RunrAutomation"
    assert config.state_db == local_app_data / "RunrAutomation" / "state.db"
    assert config.poll_interval_seconds == 30
