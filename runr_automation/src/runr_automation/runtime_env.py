"""Load local Runr secrets without modifying the parent process environment."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        if not separator or not key.strip():
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def load_runtime_environment(
    repo_root: str | Path,
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Merge local secret files, then let the real process environment win.

    The user-configured checkout file is supported for this deployment branch.
    The application-data secrets file is checked first so one-folder runtime
    deployments can keep secrets out of the repository entirely.
    """

    process = dict(environment if environment is not None else os.environ)
    local_app_data = process.get("LOCALAPPDATA")
    if local_app_data:
        runtime_secrets = Path(local_app_data) / "RunrAutomation" / "secrets.env"
    else:
        runtime_secrets = Path.home() / ".local" / "share" / "RunrAutomation" / "secrets.env"
    merged = _parse_env_file(Path(repo_root).resolve() / "user_config" / ".env")
    merged.update(_parse_env_file(runtime_secrets))
    merged.update(process)
    return merged
