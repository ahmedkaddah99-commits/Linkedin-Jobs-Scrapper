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


def test_config_defaults_to_codex_last_and_exposes_openrouter_purpose_models(tmp_path: Path) -> None:
    config = load_config(tmp_path, {"LOCALAPPDATA": str(tmp_path / "local")})

    assert config.provider_order == ("opencode_subscription", "openrouter", "codex")
    assert config.openrouter_api_key_env == "OPENROUTER_API_KEY"
    assert config.openrouter_model("ticket_creation") == "openai/gpt-4.1-mini"


def test_user_config_customizes_speed_and_safe_stop_with_environment_precedence(tmp_path: Path) -> None:
    data_dir = tmp_path / "RunrAutomation"
    data_dir.mkdir()
    (data_dir / "config.yaml").write_text(
        """
linear:
  poll_interval_seconds: 20
  overlap_seconds: 180
  team_id: team-from-config
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
approvals:
  expiry_minutes: 30
""",
        encoding="utf-8",
    )
    environment = {
        "LOCALAPPDATA": str(tmp_path),
        "RUNR_AUTOMATION_POLL_INTERVAL_SECONDS": "15",
    }

    config = load_config(tmp_path, environment)

    assert config.poll_interval_seconds == 15
    assert config.overlap_seconds == 180
    assert config.linear_team_id == "team-from-config"
    assert config.max_concurrent_issues == 4
    assert config.max_attempt_seconds == 1500
    assert config.max_attempt_tokens == 60_000
    assert config.reserve_tokens == 9_000
    assert config.provider_order == ("codex", "opencode_subscription")
    assert config.openrouter_enabled is False
    assert config.openrouter_max_usd_per_job == 2.5
    assert config.openrouter_max_usd_per_day == 12
    assert config.approval_ttl_seconds == 1800


def test_provider_commands_and_models_are_loaded_as_argument_lists(tmp_path: Path) -> None:
    data_dir = tmp_path / "RunrAutomation"
    data_dir.mkdir()
    (data_dir / "config.yaml").write_text(
        """
providers:
  codex:
    command: [C:/tools/codex.exe, exec, "-"]
    model: gpt-codex
  opencode_subscription:
    command: [C:/tools/opencode.exe, run]
    model: opencode-go/gpt
""",
        encoding="utf-8",
    )

    config = load_config(tmp_path, {"LOCALAPPDATA": str(tmp_path)})

    assert config.codex_command == ("C:/tools/codex.exe", "exec", "-")
    assert config.codex_model == "gpt-codex"
    assert config.opencode_subscription_command == ("C:/tools/opencode.exe", "run")
    assert config.opencode_subscription_model == "opencode-go/gpt"
