"""Configuration defaults and environment overrides for local automation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


def default_data_dir(environment: Mapping[str, str] | None = None) -> Path:
    values = environment or os.environ
    if values.get("LOCALAPPDATA"):
        return Path(values["LOCALAPPDATA"]) / "RunrAutomation"
    if values.get("XDG_DATA_HOME"):
        return Path(values["XDG_DATA_HOME"]) / "RunrAutomation"
    return Path.home() / ".local" / "share" / "RunrAutomation"


@dataclass(frozen=True)
class AutomationConfig:
    repo_root: Path
    data_dir: Path
    state_db: Path
    poll_interval_seconds: int = 90
    poll_jitter_seconds: int = 15


def _positive_int(name: str, default: int, environment: Mapping[str, str]) -> int:
    raw = environment.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def load_config(repo_root: str | Path, environment: Mapping[str, str] | None = None) -> AutomationConfig:
    values = environment or os.environ
    data_dir = default_data_dir(values)
    return AutomationConfig(
        repo_root=Path(repo_root).resolve(),
        data_dir=data_dir,
        state_db=data_dir / "state.db",
        poll_interval_seconds=_positive_int(
            "RUNR_AUTOMATION_POLL_INTERVAL_SECONDS", 90, values
        ),
        poll_jitter_seconds=_positive_int(
            "RUNR_AUTOMATION_POLL_JITTER_SECONDS", 15, values
        ),
    )
