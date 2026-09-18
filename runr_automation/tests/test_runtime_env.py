from pathlib import Path

from runr_automation.runtime_env import load_runtime_environment


def test_runtime_environment_reads_checkout_env_without_overriding_process_values(tmp_path: Path) -> None:
    env_file = tmp_path / "user_config" / ".env"
    env_file.parent.mkdir()
    env_file.write_text(
        "OPENROUTER_API_KEY=from-file\nLINEAR_API_TOKEN=linear-file\n# comment\n",
        encoding="utf-8",
    )

    values = load_runtime_environment(
        tmp_path,
        {"LOCALAPPDATA": str(tmp_path / "local"), "OPENROUTER_API_KEY": "from-process"},
    )

    assert values["OPENROUTER_API_KEY"] == "from-process"
    assert values["LINEAR_API_TOKEN"] == "linear-file"
