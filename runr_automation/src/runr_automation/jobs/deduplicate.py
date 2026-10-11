"""Bounded duplicate candidate adjudication with mutation-safe schemas."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass(frozen=True)
class IssueSummary:
    identifier: str
    title: str
    acceptance_criteria: str
    subsystem: str
    allowed_paths: tuple[str, ...]


@dataclass(frozen=True)
class DeduplicationResult:
    outcome: str
    candidate_id: str | None
    confidence: float
    overlap: tuple[str, ...]
    differences: tuple[str, ...]


class DedupProjection(Protocol):
    def mark_duplicate(self, issue_id: str, candidate_id: str, evidence: DeduplicationResult) -> None: ...
    def mark_review(self, issue_id: str, evidence: str) -> None: ...


class DeduplicationJob:
    def __init__(self, projection: DedupProjection, *, max_candidates: int = 10) -> None:
        self.projection = projection
        self.max_candidates = max_candidates

    def run(
        self,
        issue: IssueSummary,
        candidates: tuple[IssueSummary, ...],
        model: Callable[[str], str],
    ) -> DeduplicationResult:
        bounded = tuple(candidate for candidate in candidates if self._plausible(issue, candidate))[: self.max_candidates]
        if not bounded:
            return DeduplicationResult("clear", None, 1.0, (), ())
        try:
            result = self._parse(model(self._prompt(issue, bounded)), {candidate.identifier for candidate in bounded})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            result = DeduplicationResult("possible_duplicate", bounded[0].identifier, 0.0, (), (str(exc),))
            self.projection.mark_review(issue.identifier, "Invalid deduplication model output")
            return result
        if result.outcome == "duplicate" and result.confidence >= 0.95 and result.candidate_id:
            self.projection.mark_duplicate(issue.identifier, result.candidate_id, result)
        elif result.outcome != "clear":
            self.projection.mark_review(issue.identifier, "Duplicate evidence requires human review")
        return result

    @staticmethod
    def _plausible(issue: IssueSummary, candidate: IssueSummary) -> bool:
        title_words = set(issue.title.casefold().split())
        other_words = set(candidate.title.casefold().split())
        return bool(title_words & other_words) and (
            issue.subsystem == candidate.subsystem or bool(set(issue.allowed_paths) & set(candidate.allowed_paths))
        )

    @staticmethod
    def _prompt(issue: IssueSummary, candidates: tuple[IssueSummary, ...]) -> str:
        return json.dumps({"issue": issue.__dict__, "candidates": [candidate.__dict__ for candidate in candidates]})

    @staticmethod
    def _parse(raw: str, candidate_ids: set[str]) -> DeduplicationResult:
        data = json.loads(raw)
        required = {"outcome", "candidate_id", "confidence", "overlap", "differences"}
        if set(data) != required or data["outcome"] not in {"clear", "possible_duplicate", "duplicate"}:
            raise ValueError("invalid deduplication schema")
        candidate_id = data["candidate_id"]
        if candidate_id is not None and candidate_id not in candidate_ids:
            raise ValueError("model selected an unbounded candidate")
        if not isinstance(data["confidence"], (int, float)) or not 0 <= data["confidence"] <= 1:
            raise ValueError("confidence must be between zero and one")
        if not isinstance(data["overlap"], list) or not isinstance(data["differences"], list):
            raise ValueError("evidence must be lists")
        return DeduplicationResult(
            data["outcome"], candidate_id, float(data["confidence"]), tuple(data["overlap"]), tuple(data["differences"])
        )
