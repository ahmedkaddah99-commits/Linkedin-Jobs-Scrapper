"""Eligibility gates and bounded compatible-wave scheduling."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    identifier: str
    dedup_state: str
    research_state: str
    plan_current: bool
    scope_valid: bool
    dependencies_ready: bool
    lifecycle_state: str
    wave: int | None
    compatible_with: frozenset[str]
    write_paths: tuple[str, ...]

    @property
    def eligible(self) -> bool:
        return (
            self.dedup_state == "clear"
            and self.research_state in {"current", "not_required"}
            and self.plan_current
            and self.scope_valid
            and self.dependencies_ready
            and self.lifecycle_state in {"Todo", "Ready"}
            and self.wave is not None
        )


class Scheduler:
    def __init__(self, max_concurrent: int) -> None:
        self.max_concurrent = max_concurrent

    def select(self, candidates: tuple[Candidate, ...]) -> tuple[Candidate, ...]:
        selected: list[Candidate] = []
        for candidate in candidates:
            if not candidate.eligible:
                continue
            if any(not self._compatible(candidate, existing) for existing in selected):
                continue
            selected.append(candidate)
            if len(selected) >= self.max_concurrent:
                break
        return tuple(selected)

    @staticmethod
    def _compatible(left: Candidate, right: Candidate) -> bool:
        return (
            left.wave == right.wave
            and right.identifier in left.compatible_with
            and left.identifier in right.compatible_with
            and not (set(left.write_paths) & set(right.write_paths))
        )
