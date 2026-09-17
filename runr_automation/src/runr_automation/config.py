"""Configuration defaults and environment overrides for local automation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml


def default_data_dir(environment: Mapping[str, str] | None = None) -> Path:
    values = environment if environment is not None else os.environ
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
    linear_team_id: str = ""
    poll_interval_seconds: int = 90
    poll_jitter_seconds: int = 15
    overlap_seconds: int = 120
    max_concurrent_issues: int = 2
    max_attempt_seconds: int = 45 * 60
    max_attempt_tokens: int = 80_000
    reserve_tokens: int = 12_000
    approval_ttl_seconds: int = 3600
    provider_order: tuple[str, ...] = ("codex", "opencode_subscription")
    codex_command: tuple[str, ...] = ()
    codex_model: str = "gpt-5.6-luna"
    opencode_subscription_command: tuple[str, ...] = ()
    opencode_subscription_model: str = "opencode-go/gpt-5.6-luna"
    openrouter_enabled: bool = False
    openrouter_max_usd_per_job: float = 0
    openrouter_max_usd_per_day: float = 0


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


def _command(value: object, name: str) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list) or not value or not all(isinstance(part, str) and part for part in value):
        raise ValueError(f"{name} must be a non-empty YAML list of arguments")
    return tuple(value)


def load_config(repo_root: str | Path, environment: Mapping[str, str] | None = None) -> AutomationConfig:
    values = environment if environment is not None else os.environ
    data_dir = default_data_dir(values)
    file_config: dict = {}
    config_path = data_dir / "config.yaml"
    if config_path.is_file():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{config_path} must contain a YAML mapping")
        file_config = loaded
    linear = file_config.get("linear") or {}
    execution = file_config.get("execution") or {}
    providers = file_config.get("providers") or {}
    codex = providers.get("codex") or {}
    opencode_subscription = providers.get("opencode_subscription") or {}
    openrouter = providers.get("openrouter") or {}
    approvals = file_config.get("approvals") or {}
    return AutomationConfig(
        repo_root=Path(repo_root).resolve(),
        data_dir=data_dir,
        state_db=data_dir / "state.db",
        linear_team_id=str(values.get("RUNR_LINEAR_TEAM_ID") or linear.get("team_id") or ""),
        poll_interval_seconds=_positive_int(
            "RUNR_AUTOMATION_POLL_INTERVAL_SECONDS", int(linear.get("poll_interval_seconds", 90)), values
        ),
        poll_jitter_seconds=_positive_int(
            "RUNR_AUTOMATION_POLL_JITTER_SECONDS", int(linear.get("poll_jitter_seconds", 15)), values
        ),
        overlap_seconds=int(linear.get("overlap_seconds", 120)),
        max_concurrent_issues=int(execution.get("max_concurrent_issues", 2)),
        max_attempt_seconds=int(execution.get("max_attempt_minutes", 45)) * 60,
        max_attempt_tokens=int(execution.get("max_attempt_tokens", 80_000)),
        reserve_tokens=int(execution.get("reserve_tokens", 12_000)),
        approval_ttl_seconds=int(approvals.get("expiry_minutes", 60)) * 60,
        provider_order=tuple(providers.get("order") or ("codex", "opencode_subscription")),
        codex_command=_command(codex.get("command"), "providers.codex.command"),
        codex_model=str(codex.get("model") or "gpt-5.6-luna"),
        opencode_subscription_command=_command(
            opencode_subscription.get("command"), "providers.opencode_subscription.command"
        ),
        opencode_subscription_model=str(
            opencode_subscription.get("model") or "opencode-go/gpt-5.6-luna"
        ),
        openrouter_enabled=bool(openrouter.get("enabled", False)),
        openrouter_max_usd_per_job=float(openrouter.get("max_usd_per_job", 0)),
        openrouter_max_usd_per_day=float(openrouter.get("max_usd_per_day", 0)),
    )
