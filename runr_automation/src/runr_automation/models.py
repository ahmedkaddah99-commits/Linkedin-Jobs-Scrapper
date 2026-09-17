"""Typed records shared by the local controller components."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    FAILED = "failed"
    COMPLETE = "complete"


@dataclass(frozen=True)
class IssueRecord:
    linear_id: str
    identifier: str
    latest_remote_timestamp: str | None = None
    normalized_fingerprint: str | None = None
    subsystem: str | None = None
    lifecycle_state: str | None = None
    payload_json: str = "{}"
    observed_at: str | None = None


@dataclass(frozen=True)
class EventRecord:
    event_key: str
    payload_hash: str
    first_seen: str
    last_seen: str
    processed_state: str = "pending"


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    job_type: str
    issue_id: str | None
    desired_state_fingerprint: str
    status: JobStatus = JobStatus.QUEUED
    priority: int = 0
    attempt_count: int = 0
    next_retry: str | None = None
    lease_owner: str | None = None
    lease_expires_at: str | None = None


@dataclass(frozen=True)
class AttemptRecord:
    attempt_id: str
    job_id: str
    provider: str | None
    model: str | None
    session_id: str | None
    started_at: str
    ended_at: str | None = None
    outcome: str | None = None
    usage_json: str | None = None
    redacted_error: str | None = None


@dataclass(frozen=True)
class CheckpointRecord:
    checkpoint_id: str
    job_id: str
    phase: str
    artifact_paths_json: str = "[]"
    commit_sha: str | None = None
    worktree: str | None = None
    resumable_provider_session_id: str | None = None
    summary_json: str = "{}"
    created_at: str | None = None


@dataclass(frozen=True)
class DependencyEdge:
    predecessor: str
    successor: str
    kind: str
    evidence_hash: str
    linear_relation_id: str | None = None


@dataclass(frozen=True)
class WaveRecord:
    plan_version: str
    issue_id: str
    membership_json: str = "[]"
    conflict_resources_json: str = "[]"
    validity_fingerprint: str = ""


@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: str
    action: str
    target: str
    requested_at: str
    action_fingerprint: str
    decision: str | None = None
    actor: str | None = None
    expires_at: str | None = None
    tested_commit_sha: str | None = None


@dataclass(frozen=True)
class ProviderCircuitRecord:
    provider_model: str
    state: str
    failure_reason: str | None = None
    reopen_at: str | None = None


@dataclass(frozen=True)
class LockRecord:
    resource_key: str
    owner: str
    lease_expires_at: str


@dataclass(frozen=True)
class MigrationRecord:
    migration_id: str
    kind: str
    status: str
    started_at: str
    snapshot_path: str | None = None
    completed_at: str | None = None
    result_json: str = "{}"
