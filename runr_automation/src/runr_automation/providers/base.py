"""Provider contracts, discovery, execution, and failure classification."""

from __future__ import annotations

import shutil
import subprocess
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ..redaction import redact_text


class ProviderErrorKind(StrEnum):
    AUTHENTICATION = "authentication"
    CAPACITY = "rate_or_capacity"
    TRANSIENT = "transient"
    INVALID_OUTPUT = "invalid_output"
    TOOL_FAILURE = "tool_failure"
    PERMANENT = "permanent"


def classify_provider_error(message: str) -> ProviderErrorKind:
    text = message.casefold()
    if any(value in text for value in ("401", "unauthorized", "authentication", "invalid api key")):
        return ProviderErrorKind.AUTHENTICATION
    if any(value in text for value in ("429", "rate limit", "capacity", "quota")):
        return ProviderErrorKind.CAPACITY
    if any(value in text for value in ("timeout", "timed out", "connection reset", "temporarily unavailable")):
        return ProviderErrorKind.TRANSIENT
    if any(value in text for value in ("invalid json", "schema validation", "malformed output")):
        return ProviderErrorKind.INVALID_OUTPUT
    if any(value in text for value in ("tool failed", "command not found", "exit code")):
        return ProviderErrorKind.TOOL_FAILURE
    return ProviderErrorKind.PERMANENT


@dataclass(frozen=True)
class ProviderResult:
    returncode: int
    output: str
    session_id: str | None = None


class LocalCLIProvider:
    """Runs only an operator-configured command template; discovery never guesses arguments."""

    def __init__(
        self,
        name: str,
        executable: str,
        command: tuple[str, ...] = (),
        *,
        model: str = "",
        timeout_seconds: int | None = None,
    ) -> None:
        self.name = name
        self.executable = executable
        self.command = command
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def available(self) -> bool:
        return Path(self.executable).is_file() or shutil.which(self.executable) is not None

    def run(self, prompt_path: Path, *, cwd: Path) -> ProviderResult:
        if not self.available:
            raise RuntimeError(f"{self.name} executable is unavailable")
        if not self.command:
            raise RuntimeError(f"{self.name} command template is not configured; run doctor")
        args = [
            part.replace("{prompt_file}", str(prompt_path)).replace("{cwd}", str(cwd))
            for part in self.command
        ]
        completed = subprocess.run(
            args,
            cwd=cwd,
            input=prompt_path.read_text(encoding="utf-8") if "-" in args else None,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        output = redact_text(f"{completed.stdout}\n{completed.stderr}".strip())
        match = re.search(r'(?im)(?:session id:\s*|"sessionID"\s*:\s*")([A-Za-z0-9_-]+)', output)
        return ProviderResult(completed.returncode, output, match.group(1) if match else None)
