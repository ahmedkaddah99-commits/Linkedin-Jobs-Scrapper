"""Configuration defaults and environment overrides for local automation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml


DEFAULT_PROVIDER_ORDER = ("opencode_subscription", "openrouter", "codex")
DEFAULT_OPENROUTER_MODELS = (
    ("implementation", "openai/gpt-4.1-mini"),
    ("research", "openai/gpt-4.1-mini"),
    ("ticket_creation", "openai/gpt-4.1-mini"),
    ("deduplication", "openai/gpt-4.1-mini"),
    ("parallelization", "openai/gpt-4.1-mini"),
)


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
    provider_order: tuple[str, ...] = DEFAULT_PROVIDER_ORDER
    codex_command: tuple[str, ...] = ()
    codex_model: str = "gpt-5.6-luna"
    opencode_subscription_command: tuple[str, ...] = ()
    opencode_subscription_model: str = "opencode-go/gpt-5.6-luna"
    openrouter_enabled: bool = False
    openrouter_api_key_env: str = "OPENROUTER_API_KEY"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_models: tuple[tuple[str, str], ...] = DEFAULT_OPENROUTER_MODELS
    openrouter_max_tool_calls: int = 24
    openrouter_estimated_request_cost_usd: float = 0.01
    openrouter_max_usd_per_job: float = 0
    openrouter_max_usd_per_day: float = 0

    def openrouter_model(self, purpose: str) -> str:
        models = dict(self.openrouter_models)
        return models.get(purpose) or models["implementation"]


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


def _models(value: object, name: str) -> tuple[tuple[str, str], ...]:
    if value in (None, ""):
        return DEFAULT_OPENROUTER_MODELS
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a YAML mapping of purpose to model")
    defaults = dict(DEFAULT_OPENROUTER_MODELS)
    models = []
    for purpose, default in defaults.items():
        model = value.get(purpose, default)
        if not isinstance(model, str) or not model.strip():
            raise ValueError(f"{name}.{purpose} must be a non-empty model name")
        models.append((purpose, model.strip()))
    for purpose, model in value.items():
        if purpose not in defaults:
            if not isinstance(model, str) or not model.strip():
                raise ValueError(f"{name}.{purpose} must be a non-empty model name")
            models.append((str(purpose), model.strip()))
    return tuple(models)


def _positive_config_int(value: object, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return parsed


def _positive_config_float(value: object, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return parsed


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
        provider_order=tuple(providers.get("order") or DEFAULT_PROVIDER_ORDER),
        codex_command=_command(codex.get("command"), "providers.codex.command"),
        codex_model=str(codex.get("model") or "gpt-5.6-luna"),
        opencode_subscription_command=_command(
            opencode_subscription.get("command"), "providers.opencode_subscription.command"
        ),
        opencode_subscription_model=str(
            opencode_subscription.get("model") or "opencode-go/gpt-5.6-luna"
        ),
        openrouter_enabled=bool(openrouter.get("enabled", False)),
        openrouter_api_key_env=str(openrouter.get("api_key_env") or "OPENROUTER_API_KEY"),
        openrouter_base_url=str(openrouter.get("base_url") or "https://openrouter.ai/api/v1").rstrip("/"),
        openrouter_models=_models(openrouter.get("models"), "providers.openrouter.models"),
        openrouter_max_tool_calls=_positive_config_int(
            openrouter.get("max_tool_calls", 24), "providers.openrouter.max_tool_calls"
        ),
        openrouter_estimated_request_cost_usd=_positive_config_float(
            openrouter.get("estimated_request_cost_usd", 0.01),
            "providers.openrouter.estimated_request_cost_usd",
        ),
        openrouter_max_usd_per_job=float(openrouter.get("max_usd_per_job", 0)),
        openrouter_max_usd_per_day=float(openrouter.get("max_usd_per_day", 0)),
    )
