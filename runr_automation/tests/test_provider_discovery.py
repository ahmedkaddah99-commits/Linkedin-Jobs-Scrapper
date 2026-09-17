from pathlib import Path

from runr_automation.providers.discovery import ProviderProbe, discover_providers


def test_discovery_prefers_newer_vscode_codex_over_stale_path_binary(tmp_path: Path) -> None:
    stale = tmp_path / "bin" / "codex.cmd"
    current = tmp_path / ".vscode" / "extensions" / "openai.chatgpt-26" / "bin" / "windows-x86_64" / "codex.exe"
    stale.parent.mkdir(parents=True)
    current.parent.mkdir(parents=True)
    stale.touch()
    current.touch()

    probe = ProviderProbe(
        which=lambda name: str(stale) if name == "codex" else None,
        codex_candidates=lambda: (current,),
        command_output=lambda command: (
            "codex-cli 0.50.0" if Path(command[0]) == stale else "codex-cli 0.154.0-alpha.6.2"
        ),
    )

    providers = discover_providers((), (), "gpt-5.6-luna", "opencode-go/gpt-5.6-luna", probe=probe)

    assert providers["codex"].executable == str(current)
    assert providers["codex"].source == "vscode-extension"


def test_discovery_uses_matching_desktop_opencode_cli_when_not_on_path(tmp_path: Path) -> None:
    plugin_package = tmp_path / ".config" / "opencode" / "node_modules" / "@opencode-ai" / "plugin" / "package.json"
    plugin_package.parent.mkdir(parents=True)
    plugin_package.write_text('{"version":"1.18.30"}', encoding="utf-8")
    desktop = tmp_path / "AppData" / "Local" / "Programs" / "@opencode-aidesktop" / "OpenCode.exe"
    desktop.parent.mkdir(parents=True)
    desktop.touch()

    probe = ProviderProbe(
        which=lambda name: "C:/npm/npx.cmd" if name == "npx" else None,
        home=tmp_path,
        local_app_data=tmp_path / "AppData" / "Local",
        command_output=lambda command: "opencode run [message..]",
    )

    providers = discover_providers((), (), "gpt-5.6-luna", "opencode-go/gpt-5.6-luna", probe=probe)

    command = providers["opencode_subscription"]
    assert command.argv[:4] == ("C:/npm/npx.cmd", "--yes", "opencode-ai@1.18.30", "run")
    assert command.source == "desktop-shared-auth"


def test_explicit_provider_command_wins_without_discovery() -> None:
    probe = ProviderProbe(which=lambda _: (_ for _ in ()).throw(AssertionError("discovery must not run")))

    providers = discover_providers(
        ("C:/tools/codex.exe", "exec", "-"),
        ("C:/tools/opencode.exe", "run"),
        "codex-model",
        "opencode-model",
        probe=probe,
    )

    assert providers["codex"].argv == ("C:/tools/codex.exe", "exec", "-")
    assert providers["codex"].source == "configured"
    assert providers["opencode_subscription"].source == "configured"
