"""Durable stage execution from normalized issue events to local approval wait."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

from .approvals import ActionContext, ApprovalManager
from .execution import ExecutionProvider, ImplementationRunner, TicketExecutionRequest
from .queue import JobQueue
from .poller import PollResult, Poller
from .reconciler import ReconcileResult, Reconciler
from .scope_router import ScopeManifest, build_scope_manifest, load_registry
from .state import StateStore
from .tickets import normalize_ticket_payload


_NEXT_STAGE = {
    "normalize": "deduplicate",
    "deduplicate": "research",
    "research": "parallelize",
    "parallelize": "implement",
}


@dataclass(frozen=True)
class EngineResult:
    processed: int = 0
    awaiting_approval: int = 0
    waiting: int = 0
    failed: int = 0


@dataclass(frozen=True)
class CycleResult:
    poll: PollResult
    reconcile: ReconcileResult
    engine: EngineResult


class ControllerCycle:
    def __init__(self, poller: Poller, reconciler: Reconciler, engine: "ExecutionEngine") -> None:
        self.poller = poller
        self.reconciler = reconciler
        self.engine = engine

    def run(self, *, now: datetime | None = None) -> CycleResult:
        poll = self.poller.run_once()
        reconcile = self.reconciler.run_once()
        engine = self.engine.run_available(now=now)
        return CycleResult(poll, reconcile, engine)


@dataclass(frozen=True)
class IssueContext:
    linear_id: str
    identifier: str
    title: str
    acceptance_criteria: str
    fingerprint: str
    scope: ScopeManifest
    skill: str


class ExecutionEngine:
    def __init__(
        self,
        store: StateStore,
        repo_root: Path,
        runner: ImplementationRunner,
        providers: Mapping[str, ExecutionProvider],
        *,
        provider_order: tuple[str, ...],
        owner: str,
        lease_seconds: int = 300,
        approval_ttl_seconds: int = 3600,
    ) -> None:
        self.store = store
        self.repo_root = repo_root
        self.runner = runner
        self.providers = providers
        self.provider_order = provider_order
        self.owner = owner
        self.lease_seconds = lease_seconds
        self.approval_ttl_seconds = approval_ttl_seconds
        self.queue = JobQueue(store)

    def run_available(self, *, now: datetime | None = None) -> EngineResult:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        processed = awaiting = waiting = failed = 0
        while True:
            job = self.queue.claim(self.owner, now=current, lease_seconds=self.lease_seconds)
            if job is None:
                break
            processed += 1
            try:
                context = self._issue_context(job.issue_id)
                if job.desired_state_fingerprint != context.fingerprint:
                    self.queue.complete(job.job_id, self.owner)
                    continue
                if job.job_type in _NEXT_STAGE:
                    self._record_stage(context, job.job_type)
                    self.queue.complete_and_enqueue(job.job_id, self.owner, _NEXT_STAGE[job.job_type])
                    continue
                if job.job_type != "implement":
                    self.queue.fail(job.job_id, self.owner)
                    failed += 1
                    continue
                outcome = self._implement(job.job_id, context, current)
                if outcome == "awaiting_approval":
                    self.queue.complete(job.job_id, self.owner)
                    awaiting += 1
                elif outcome == "waiting":
                    self.queue.wait(job.job_id, self.owner, next_retry=current + timedelta(minutes=15))
                    waiting += 1
                else:
                    self.queue.fail(job.job_id, self.owner)
                    failed += 1
            except (KeyError, TypeError, ValueError, RuntimeError):
                self.queue.fail(job.job_id, self.owner)
                failed += 1
        return EngineResult(processed, awaiting, waiting, failed)

    def _issue_context(self, issue_id: str | None) -> IssueContext:
        if issue_id is None:
            raise ValueError("job has no issue")
        with self.store.connect() as connection:
            row = connection.execute("SELECT * FROM issues WHERE linear_id=?", (issue_id,)).fetchone()
        if row is None:
            raise ValueError(f"unknown issue: {issue_id}")
        payload = normalize_ticket_payload(json.loads(row["payload_json"]))
        required = ("title", "acceptance_criteria", "subsystem", "allowed_paths")
        missing = [name for name in required if payload.get(name) in (None, "", [])]
        if missing:
            raise ValueError(f"missing required ticket fields: {', '.join(missing)}")
        scope = build_scope_manifest(
            load_registry(str(self.repo_root / "docs" / "subsystems.yaml")),
            issue_id=issue_id,
            primary_subsystem=str(payload["subsystem"]),
            allowed_paths=tuple(payload["allowed_paths"]),
            required_reading=tuple(payload.get("required_reading") or ()),
            required_tests=tuple(payload.get("required_tests") or ()),
            co_owners=tuple(payload.get("co_owners") or ()),
            repo_root=self.repo_root,
        )
        return IssueContext(
            issue_id,
            row["identifier"],
            str(payload["title"]),
            str(payload["acceptance_criteria"]),
            row["normalized_fingerprint"],
            scope,
            str(payload.get("skill") or "runr-ticket-start"),
        )

    def _record_stage(self, context: IssueContext, stage: str) -> None:
        result = hashlib.sha256(f"{stage}:{context.fingerprint}".encode()).hexdigest()
        reasons = {
            "normalize": "structured ticket fields or fingerprint changes",
            "deduplicate": "title, acceptance criteria, subsystem, or paths change",
            "research": "required reading, research questions, or scope changes",
            "parallelize": "dependencies, resources, priority, or completion changes",
        }
        self.queue.record_analysis(
            context.linear_id,
            stage,
            input_fingerprint=context.fingerprint,
            result_fingerprint=result,
            tool_version="0.1.0",
            skill_version="1",
            next_reason_to_run=reasons[stage],
        )

    def _implement(self, job_id: str, context: IssueContext, now: datetime) -> str:
        request = TicketExecutionRequest(
            job_id,
            context.linear_id,
            context.identifier,
            context.title,
            context.acceptance_criteria,
            context.fingerprint,
            context.scope,
            context.skill,
        )
        attempted = False
        for name in self.provider_order:
            provider = self.providers.get(name)
            if provider is None or self._circuit_open(provider, now):
                continue
            attempted = True
            result = self.runner.run(request, provider)
            if result.status == "waiting_for_capacity":
                self._open_circuit(provider, now, result.error_kind.value if result.error_kind else "capacity")
                continue
            if result.status != "implemented" or not result.commit_sha:
                return "failed"
            scope_fingerprint = hashlib.sha256(repr(context.scope).encode()).hexdigest()
            test_fingerprint = hashlib.sha256(repr(context.scope.required_tests).encode()).hexdigest()
            ApprovalManager(self.store).request(
                ActionContext(
                    "predeployment",
                    (context.identifier,),
                    result.commit_sha,
                    context.fingerprint,
                    scope_fingerprint,
                    test_fingerprint,
                ),
                now=now,
                ttl_seconds=self.approval_ttl_seconds,
            )
            return "awaiting_approval"
        return "waiting" if attempted or self.provider_order else "failed"

    def _circuit_open(self, provider: ExecutionProvider, now: datetime) -> bool:
        key = f"{provider.name}/{provider.model}"
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT state, reopen_at FROM provider_circuits WHERE provider_model=?", (key,)
            ).fetchone()
        return bool(row and row["state"] == "open" and row["reopen_at"] and row["reopen_at"] > now.isoformat())

    def _open_circuit(self, provider: ExecutionProvider, now: datetime, reason: str) -> None:
        key = f"{provider.name}/{provider.model}"
        reopen = (now + timedelta(minutes=15)).isoformat()
        with self.store.connect() as connection:
            connection.execute(
                "INSERT INTO provider_circuits(provider_model, state, failure_reason, reopen_at) "
                "VALUES (?, 'open', ?, ?) ON CONFLICT(provider_model) DO UPDATE SET "
                "state='open', failure_reason=excluded.failure_reason, reopen_at=excluded.reopen_at",
                (key, reason, reopen),
            )
