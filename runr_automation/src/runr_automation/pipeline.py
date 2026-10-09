"""Composable end-to-end issue pipeline used by scheduler workers and fake verification."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .approvals import ActionContext, ApprovalManager
from .jobs.deduplicate import DeduplicationJob, IssueSummary
from .jobs.parallelize import DependencyPlanner
from .jobs.research import ResearchRequest, Researcher
from .queue import JobQueue
from .scope_router import ScopeManifest
from .state import StateStore


@dataclass(frozen=True)
class PipelineIssue:
    linear_id: str
    identifier: str
    title: str
    acceptance_criteria: str
    subsystem: str
    fingerprint: str


@dataclass(frozen=True)
class PipelineResult:
    status: str
    stages: tuple[str, ...]
    approval_id: str
    action_context: ActionContext


class AutomationPipeline:
    def __init__(self, store: StateStore, projection, *, read_path: Callable[[str], str]) -> None:
        self.store = store
        self.projection = projection
        self.researcher = Researcher(read_path)

    def run(
        self,
        issue: PipelineIssue,
        manifest: ScopeManifest,
        *,
        candidates: tuple[IssueSummary, ...],
        model: Callable[[str], str],
        implement: Callable[[], tuple[tuple[str, ...], str, str]],
        now: datetime,
    ) -> PipelineResult:
        stages: list[str] = []
        summary = IssueSummary(
            issue.identifier, issue.title, issue.acceptance_criteria, issue.subsystem, manifest.allowed_writes
        )
        dedup = DeduplicationJob(self.projection).run(summary, candidates, model)
        stages.append("deduplicate")
        if dedup.outcome != "clear":
            raise ValueError("issue is not dedup-clear")
        stages.append("scope")
        research = self.researcher.run(
            ResearchRequest(issue.identifier, manifest.allowed_reads, (), False, issue.fingerprint)
        )
        stages.append("research")
        DependencyPlanner().plan((issue.identifier,), (), {issue.identifier: manifest.allowed_writes})
        stages.append("parallelize")
        changed_paths, commit_sha, test_fingerprint = implement()
        stages.append("implement")
        manifest.validate_write_paths(changed_paths)
        stages.append("validate")
        queue = JobQueue(self.store)
        queue.record_analysis(
            issue.linear_id, "research", input_fingerprint=issue.fingerprint,
            result_fingerprint=research.result_fingerprint, tool_version="0.1.0", skill_version="1",
            next_reason_to_run="research inputs or cited premise changes",
        )
        scope_fingerprint = hashlib.sha256(repr(manifest).encode()).hexdigest()
        action = ActionContext(
            "predeployment", (issue.identifier,), commit_sha, issue.fingerprint, scope_fingerprint, test_fingerprint
        )
        approval_id = ApprovalManager(self.store).request(action, now=now, ttl_seconds=3600)
        return PipelineResult("awaiting_approval", tuple(stages), approval_id, action)
