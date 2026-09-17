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


def test_user_config_customizes_speed_and_safe_stop_with_environment_precedence(tmp_path: Path) -> None:
    data_dir = tmp_path / "RunrAutomation"
    data_dir.mkdir()
    (data_dir / "config.yaml").write_text(
        """
linear:
  poll_interval_seconds: 20
execution:
  max_concurrent_issues: 4
  max_attempt_minutes: 25
  max_attempt_tokens: 60000
  reserve_tokens: 9000
providers:
  order: [codex, opencode_subscription]
  openrouter:
    enabled: false
    max_usd_per_job: 2.5
    max_usd_per_day: 12
""",
        encoding="utf-8",
    )
    environment = {
        "LOCALAPPDATA": str(tmp_path),
        "RUNR_AUTOMATION_POLL_INTERVAL_SECONDS": "15",
    }

    config = load_config(tmp_path, environment)

    assert config.poll_interval_seconds == 15
    assert config.max_concurrent_issues == 4
    assert config.max_attempt_seconds == 1500
    assert config.max_attempt_tokens == 60_000
    assert config.reserve_tokens == 9_000
    assert config.provider_order == ("codex", "opencode_subscription")
    assert config.openrouter_enabled is False
    assert config.openrouter_max_usd_per_job == 2.5
    assert config.openrouter_max_usd_per_day == 12
