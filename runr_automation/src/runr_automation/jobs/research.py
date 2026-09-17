"""Scope-bound internal research and fingerprint freshness."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ResearchRequest:
    issue_identifier: str
    allowed_reads: tuple[str, ...]
    research_questions: tuple[str, ...]
    external_required: bool
    input_fingerprint: str


@dataclass(frozen=True)
class ResearchResult:
    issue_identifier: str
    input_fingerprint: str
    repository_evidence: tuple[tuple[str, str], ...]
    external_sources: tuple[str, ...]
    result_fingerprint: str


class Researcher:
    def __init__(self, read_path: Callable[[str], str]) -> None:
        self.read_path = read_path

    def run(self, request: ResearchRequest) -> ResearchResult:
        evidence = tuple((path, self.read_path(path)) for path in request.allowed_reads)
        digest = hashlib.sha256(repr((request.input_fingerprint, evidence)).encode()).hexdigest()
        return ResearchResult(request.issue_identifier, request.input_fingerprint, evidence, (), digest)

    @staticmethod
    def is_current(result: ResearchResult, request: ResearchRequest) -> bool:
        return result.input_fingerprint == request.input_fingerprint
