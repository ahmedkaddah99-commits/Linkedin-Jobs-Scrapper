"""Capability-probed discovery for local subscription-backed provider CLIs."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


def _output(command: tuple[str, ...]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    return f"{completed.stdout}\n{completed.stderr}".strip()


def _which(name: str) -> str | None:
    return shutil.which(name)


@dataclass(frozen=True)
class ProviderProbe:
    which: Callable[[str], str | None] = _which
    home: Path = field(default_factory=Path.home)
    local_app_data: Path = field(
        default_factory=lambda: Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    )
    command_output: Callable[[tuple[str, ...]], str] = _output
    codex_candidates: Callable[[], tuple[Path, ...]] | None = None

    def vscode_codex_candidates(self) -> tuple[Path, ...]:
        if self.codex_candidates is not None:
            return self.codex_candidates()
        extension_root = self.home / ".vscode" / "extensions"
        return tuple(extension_root.glob("openai.chatgpt-*/bin/windows-x86_64/codex.exe"))


@dataclass(frozen=True)
class ProviderCommand:
    name: str
    argv: tuple[str, ...]
    model: str
    source: str
    version: str | None = None

    @property
    def executable(self) -> str:
        return self.argv[0]


def _version_key(text: str) -> tuple[int, ...]:
    match = re.search(r"\d+(?:\.\d+)+", text)
    return tuple(int(part) for part in match.group().split(".")) if match else ()


def _discover_codex(model: str, probe: ProviderProbe) -> ProviderCommand | None:
    candidates: list[tuple[str, str]] = []
    path_command = probe.which("codex")
    if path_command:
        candidates.append((path_command, "path"))
    candidates.extend((str(path), "vscode-extension") for path in probe.vscode_codex_candidates())
    available: list[tuple[tuple[int, ...], str, str, str]] = []
    for executable, source in dict.fromkeys(candidates):
        try:
            version = probe.command_output((executable, "--version"))
        except (OSError, subprocess.SubprocessError):
            continue
        key = _version_key(version)
        if key:
            available.append((key, executable, source, version.strip()))
    if not available:
        return None
    _, executable, source, version = max(available, key=lambda item: item[0])
    return ProviderCommand(
        "codex",
        (
            executable,
            "exec",
            "-s",
            "workspace-write",
            "-c",
            'model_reasoning_effort="high"',
            "--color",
            "never",
            "-C",
            "{cwd}",
            "-",
        ),
        model,
        source,
        version,
    )


def _desktop_opencode_version(probe: ProviderProbe) -> str | None:
    desktop = probe.local_app_data / "Programs" / "@opencode-aidesktop" / "OpenCode.exe"
    package = probe.home / ".config" / "opencode" / "node_modules" / "@opencode-ai" / "plugin" / "package.json"
    if not desktop.is_file() or not package.is_file():
        return None
    try:
        version = str(json.loads(package.read_text(encoding="utf-8"))["version"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None
    return version if re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", version) else None


def _discover_opencode(model: str, probe: ProviderProbe) -> ProviderCommand | None:
    executable = probe.which("opencode")
    if executable:
        return ProviderCommand(
            "opencode_subscription",
            (executable, "run", "--auto", "--model", model, "--dir", "{cwd}", "--format", "json", "--file", "{prompt_file}", "Execute the attached bounded ticket."),
            model,
            "path",
        )
    version = _desktop_opencode_version(probe)
    npx = probe.which("npx")
    if not version or not npx:
        return None
    command = (npx, "--yes", f"opencode-ai@{version}", "run")
    try:
        help_text = probe.command_output((*command, "--help"))
    except (OSError, subprocess.SubprocessError):
        return None
    if "opencode run" not in help_text.casefold():
        return None
    return ProviderCommand(
        "opencode_subscription",
        (*command, "--auto", "--model", model, "--dir", "{cwd}", "--format", "json", "--file", "{prompt_file}", "Execute the attached bounded ticket."),
        model,
        "desktop-shared-auth",
        version,
    )


def discover_providers(
    codex_command: tuple[str, ...],
    opencode_command: tuple[str, ...],
    codex_model: str,
    opencode_model: str,
    *,
    probe: ProviderProbe | None = None,
) -> dict[str, ProviderCommand]:
    """Return verified provider commands, preferring explicit operator configuration."""

    active_probe = probe or ProviderProbe()
    providers: dict[str, ProviderCommand] = {}
    if codex_command:
        providers["codex"] = ProviderCommand("codex", codex_command, codex_model, "configured")
    else:
        discovered = _discover_codex(codex_model, active_probe)
        if discovered:
            providers["codex"] = discovered
    if opencode_command:
        providers["opencode_subscription"] = ProviderCommand(
            "opencode_subscription", opencode_command, opencode_model, "configured"
        )
    else:
        discovered = _discover_opencode(opencode_model, active_probe)
        if discovered:
            providers["opencode_subscription"] = discovered
    return providers
