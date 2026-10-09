"""Subscription-first provider routing with paid-fallback budgets and circuits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class RoutingConfig:
    order: tuple[str, ...]
    openrouter_enabled: bool
    openrouter_max_usd_per_job: float
    openrouter_max_usd_per_day: float


class ProviderRouter:
    def __init__(self, config: RoutingConfig, *, available: dict[str, bool]) -> None:
        self.config = config
        self.available = available
        self.circuits: dict[str, tuple[str, datetime]] = {}

    def open_circuit(self, provider: str, reason: str, reopen_at: datetime) -> None:
        self.circuits[provider] = (reason, reopen_at)

    def choose(
        self,
        *,
        job_spend_usd: float,
        daily_spend_usd: float,
        now: datetime | None = None,
    ) -> str | None:
        current = now or datetime.now(timezone.utc)
        for provider in self.config.order:
            if not self.available.get(provider, False):
                continue
            circuit = self.circuits.get(provider)
            if circuit and circuit[1] > current:
                continue
            if provider in {"openrouter", "opencode_openrouter"}:
                if not self.config.openrouter_enabled:
                    continue
                if self.config.openrouter_max_usd_per_job <= 0 or self.config.openrouter_max_usd_per_day <= 0:
                    continue
                if job_spend_usd >= self.config.openrouter_max_usd_per_job:
                    continue
                if daily_spend_usd >= self.config.openrouter_max_usd_per_day:
                    continue
            return provider
        return None
