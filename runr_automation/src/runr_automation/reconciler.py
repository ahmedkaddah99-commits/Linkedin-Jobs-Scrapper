"""Determine which controller stages are invalidated by an issue edit."""

from __future__ import annotations

from dataclasses import dataclass

from .linear_client import RemoteIssue
from .state import StateStore


_MISSING = object()
_DEDUPLICATION_FIELDS = {
    "title",
    "goal",
    "acceptance_criteria",
    "subsystem",
    "allowed_paths",
    "co_owners",
    "entities",
    "dependency_evidence",
}
_RESEARCH_FIELDS = {
    "required_reading",
    "research_questions",
    "acceptance_criteria",
    "subsystem",
    "allowed_paths",
}
_PARALLELIZATION_FIELDS = {
    "blocking_relations",
    "scope_resources",
    "priority",
    "estimate",
    "lifecycle_state",
    "implementation_complete",
    "acceptance_criteria",
}


@dataclass(frozen=True)
class ReconcileResult:
    enqueued_jobs: int


def _field(issue: RemoteIssue, name: str):
    if name == "title":
        return issue.title
    if name == "lifecycle_state":
        return issue.lifecycle_state
    return issue.payload.get(name, _MISSING)


def invalidated_stages(previous: RemoteIssue, current: RemoteIssue) -> tuple[str, ...]:
    changed = {
        name
        for name in _DEDUPLICATION_FIELDS | _RESEARCH_FIELDS | _PARALLELIZATION_FIELDS
        if _field(previous, name) != _field(current, name)
    }
    stages = []
    if changed & _DEDUPLICATION_FIELDS:
        stages.append("deduplicate")
    if changed & _RESEARCH_FIELDS:
        stages.append("research")
    if changed & _PARALLELIZATION_FIELDS:
        stages.append("parallelize")
    return tuple(stages)


class Reconciler:
    """Convert durable pending events into deterministic normalize jobs."""

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def run_once(self) -> ReconcileResult:
        enqueued_jobs = 0
        with self.store.connect() as connection:
            events = connection.execute(
                "SELECT event_key, payload_hash FROM events WHERE processed_state = 'pending'"
            ).fetchall()
            for event in events:
                issue_id = event["event_key"].split(":", 1)[0]
                job_id = f"normalize:{event['event_key']}"
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO jobs(
                        job_id, type, issue_id, desired_state_fingerprint,
                        status, priority, attempt_count
                    ) VALUES (?, 'normalize', ?, ?, 'queued', 0, 0)
                    """,
                    (job_id, issue_id, event["payload_hash"]),
                )
                enqueued_jobs += cursor.rowcount
                connection.execute(
                    "UPDATE events SET processed_state = 'queued' WHERE event_key = ?",
                    (event["event_key"],),
                )
        return ReconcileResult(enqueued_jobs=enqueued_jobs)
