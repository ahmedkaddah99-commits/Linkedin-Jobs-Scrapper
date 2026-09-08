"""Reversible, persistence-neutral duplicate review decisions.

This module owns the decision state machine only.  It has no repository, API,
publication, or merge executor dependency and therefore cannot mutate a job,
observation, posting version, provenance row, or publication.

Integration contract
--------------------

The lead integration layer should load one duplicate cluster and all of its
``acquisition_duplicate_members`` rows, then create a service and call
``create_candidate`` for a new cluster or hydrate the service from the
persisted history before calling ``decide``/``undo``.  A successful decision
returns ``to_persistence_record()``.  In one repository transaction, the
adapter should update only the current cluster columns and append the returned
event to ``review_history_json``:

* ``acquisition_duplicate_clusters.cluster_id`` = ``cluster_id``
* ``state`` = ``state``
* ``reasons_json`` = ``reasons_json``
* ``review_history_json`` = ``review_history_json``
* ``rule_version`` = ``rule_version``
* ``updated_at`` = ``updated_at``

Members remain intact.  The adapter must verify that every member, source
observation, source identity, posting version, provenance row, and existing
publication relationship is preserved before committing a merge or split.
The service deliberately does not provide an execution method for those
operations.

The API adapter contract is a JSON request with ``state``, ``actor``,
``reason``, ``evidence``, ``rule_version``, and optional ``expected_state`` and
plan fields.  ``merged`` requires ``merge_plan``; ``split`` requires
``split_plan``; ``undone`` requires ``undo_plan`` or uses ``plan_undo``.  The
response should contain the current decision, the append-only ``history``, and
the persistence record.  Raw source payloads remain admin-only evidence and
are referenced by ID in ``evidence`` rather than copied into a public
response.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


DecisionState = Literal[
    "candidate",
    "confirmed_duplicate",
    "distinct",
    "ignored",
    "merged",
    "split",
    "undone",
]

DECISION_STATES: frozenset[str] = frozenset(
    {
        "candidate",
        "confirmed_duplicate",
        "distinct",
        "ignored",
        "merged",
        "split",
        "undone",
    }
)

# Reversal is explicit and append-only.  A correction creates another event;
# no previous event is edited or removed.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "candidate": frozenset({"confirmed_duplicate", "distinct", "ignored"}),
    "confirmed_duplicate": frozenset({"distinct", "merged", "split", "undone"}),
    "distinct": frozenset({"candidate", "confirmed_duplicate", "ignored", "undone"}),
    "ignored": frozenset({"candidate", "confirmed_duplicate", "distinct", "undone"}),
    "merged": frozenset({"split", "undone"}),
    "split": frozenset({"candidate", "confirmed_duplicate", "distinct", "ignored", "undone"}),
    "undone": frozenset({"candidate", "confirmed_duplicate", "distinct", "ignored"}),
}


class DuplicateDecisionError(ValueError):
    """Base error for invalid or unsafe duplicate decisions."""


class InvalidTransitionError(DuplicateDecisionError):
    """Raised when a requested state transition is not allowed."""


class SafetyValidationError(DuplicateDecisionError):
    """Raised when a decision would not prove preservation and reversibility."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_timestamp(value: str, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise SafetyValidationError(f"{field_name} is required.")
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SafetyValidationError(f"{field_name} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise SafetyValidationError(f"{field_name} must include a timezone.")
    return cleaned


def _required_text(value: Any, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise SafetyValidationError(f"{field_name} is required.")
    return cleaned


def _ids(values: Iterable[Any], field_name: str, *, minimum: int = 1) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise SafetyValidationError(f"{field_name} must be an array of IDs.")
    try:
        normalized = tuple(str(value or "").strip() for value in values)
    except TypeError as exc:
        raise SafetyValidationError(f"{field_name} must be an array of IDs.") from exc
    if len(normalized) < minimum:
        raise SafetyValidationError(f"{field_name} requires at least {minimum} ID(s).")
    if any(not value for value in normalized):
        raise SafetyValidationError(f"{field_name} cannot contain empty IDs.")
    if len(set(normalized)) != len(normalized):
        raise SafetyValidationError(f"{field_name} cannot contain duplicate IDs.")
    return normalized


def _evidence(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise SafetyValidationError("evidence must be a non-empty JSON object.")
    return deepcopy(dict(value))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_object(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SafetyValidationError(f"{field_name} must be a JSON object.")
    return deepcopy(dict(value))


def _protected_bool(plan: Mapping[str, Any], key: str) -> bool:
    return plan.get(key) is True


def _string_list(value: Any, field_name: str, *, minimum: int = 1) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise SafetyValidationError(f"{field_name} must be an array of strings.")
    try:
        items = tuple(str(item or "").strip() for item in value)
    except TypeError as exc:
        raise SafetyValidationError(f"{field_name} must be an array of strings.") from exc
    if len(items) < minimum or any(not item for item in items):
        raise SafetyValidationError(f"{field_name} must contain at least {minimum} non-empty value(s).")
    if len(items) != len(set(items)):
        raise SafetyValidationError(f"{field_name} cannot contain duplicate values.")
    return items


@dataclass(frozen=True, slots=True)
class DecisionEvent:
    """One immutable append-only state transition."""

    event_id: str
    cluster_id: str
    sequence: int
    from_state: str | None
    to_state: DecisionState
    actor: str
    reason: str
    evidence: dict[str, Any]
    occurred_at: str
    recorded_at: str
    rule_version: str
    affected_ids: tuple[str, ...]
    merge_plan: dict[str, Any] | None = None
    split_plan: dict[str, Any] | None = None
    undo_plan: dict[str, Any] | None = None
    undo_of_decision_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "cluster_id": self.cluster_id,
            "sequence": self.sequence,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "actor": self.actor,
            "reason": self.reason,
            "evidence": deepcopy(self.evidence),
            "occurred_at": self.occurred_at,
            "recorded_at": self.recorded_at,
            "rule_version": self.rule_version,
            "affected_ids": list(self.affected_ids),
            "merge_plan": deepcopy(self.merge_plan),
            "split_plan": deepcopy(self.split_plan),
            "undo_plan": deepcopy(self.undo_plan),
            "undo_of_decision_id": self.undo_of_decision_id,
        }


@dataclass(frozen=True, slots=True)
class DuplicateDecision:
    """Current decision projection for one duplicate cluster."""

    cluster_id: str
    state: DecisionState
    actor: str
    reason: str
    evidence: dict[str, Any]
    decided_at: str
    recorded_at: str
    rule_version: str
    affected_ids: tuple[str, ...]
    decision_id: str
    history_sequence: int
    merge_plan: dict[str, Any] | None = None
    split_plan: dict[str, Any] | None = None
    undo_plan: dict[str, Any] | None = None
    undo_of_decision_id: str | None = None

    @classmethod
    def from_event(cls, event: DecisionEvent) -> "DuplicateDecision":
        return cls(
            cluster_id=event.cluster_id,
            state=event.to_state,
            actor=event.actor,
            reason=event.reason,
            evidence=deepcopy(event.evidence),
            decided_at=event.occurred_at,
            recorded_at=event.recorded_at,
            rule_version=event.rule_version,
            affected_ids=tuple(event.affected_ids),
            decision_id=event.event_id,
            history_sequence=event.sequence,
            merge_plan=deepcopy(event.merge_plan),
            split_plan=deepcopy(event.split_plan),
            undo_plan=deepcopy(event.undo_plan),
            undo_of_decision_id=event.undo_of_decision_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "state": self.state,
            "actor": self.actor,
            "reason": self.reason,
            "evidence": deepcopy(self.evidence),
            "decided_at": self.decided_at,
            "recorded_at": self.recorded_at,
            "rule_version": self.rule_version,
            "affected_ids": list(self.affected_ids),
            "decision_id": self.decision_id,
            "history_sequence": self.history_sequence,
            "merge_plan": deepcopy(self.merge_plan),
            "split_plan": deepcopy(self.split_plan),
            "undo_plan": deepcopy(self.undo_plan),
            "undo_of_decision_id": self.undo_of_decision_id,
        }


@dataclass(frozen=True, slots=True)
class _ClusterHistory:
    current: DecisionEvent
    events: tuple[DecisionEvent, ...]


DUPLICATE_DECISION_PERSISTENCE_CONTRACT: dict[str, Any] = {
    "cluster_table": "acquisition_duplicate_clusters",
    "member_table": "acquisition_duplicate_members",
    "current_columns": {
        "cluster_id": "cluster_id",
        "state": "state",
        "reasons_json": "reasons_json",
        "review_history_json": "review_history_json",
        "rule_version": "rule_version",
        "updated_at": "updated_at",
    },
    "append_only": True,
    "immutable_tables": [
        "job_source_observations",
        "job_posting_versions",
        "acquisition_field_provenance",
        "acquisition_publication_jobs",
    ],
    "automatic_merge": False,
    "merge_execution": "integration-only; this service never executes merges",
}

DUPLICATE_DECISION_API_CONTRACT: dict[str, Any] = {
    "method": "POST",
    "path": "/admin/acquisition/duplicate-clusters/{cluster_id}/decisions",
    "request_required": ["state", "actor", "reason", "evidence", "rule_version"],
    "request_optional": ["expected_state", "affected_ids", "merge_plan", "split_plan", "undo_plan"],
    "response": ["decision", "history", "persistence"],
    "raw_evidence": "admin-only; reference observation/version IDs, do not publish payloads",
    "automatic_merge": False,
}


class DuplicateDecisionService:
    """In-memory decision service suitable for repository/API integration.

    The only state this class mutates is its own in-memory projection.  Every
    transition appends a new ``DecisionEvent`` and leaves prior events intact.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], str] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._clock = clock or _utc_now_iso
        self._id_factory = id_factory or (lambda: f"duplicate_decision_{uuid4().hex}")
        self._clusters: dict[str, _ClusterHistory] = {}

    def create_candidate(
        self,
        *,
        cluster_id: str,
        affected_ids: Iterable[Any],
        actor: str,
        reason: str,
        evidence: Mapping[str, Any],
        rule_version: str,
        occurred_at: str | None = None,
        recorded_at: str | None = None,
        decision_id: str | None = None,
    ) -> DuplicateDecision:
        """Register a detector candidate without attempting a merge."""

        normalized_cluster_id = _required_text(cluster_id, "cluster_id")
        if normalized_cluster_id in self._clusters:
            raise DuplicateDecisionError(f"Duplicate cluster '{normalized_cluster_id}' already exists.")
        event = self._make_event(
            cluster_id=normalized_cluster_id,
            sequence=1,
            from_state=None,
            to_state="candidate",
            actor=actor,
            reason=reason,
            evidence=evidence,
            rule_version=rule_version,
            affected_ids=_ids(affected_ids, "affected_ids", minimum=2),
            occurred_at=occurred_at,
            recorded_at=recorded_at,
            decision_id=decision_id,
        )
        self._clusters[normalized_cluster_id] = _ClusterHistory(current=event, events=(event,))
        return DuplicateDecision.from_event(event)

    # ``register_candidate`` reads naturally at an integration boundary and is
    # intentionally an alias, not a second implementation.
    register_candidate = create_candidate

    def get(self, cluster_id: str) -> DuplicateDecision:
        history = self._get_history(cluster_id)
        return DuplicateDecision.from_event(history.current)

    def history(self, cluster_id: str) -> list[DecisionEvent]:
        """Return defensive copies of the append-only event history."""

        return [self._copy_event(event) for event in self._get_history(cluster_id).events]

    def decide(
        self,
        *,
        cluster_id: str,
        state: DecisionState,
        actor: str,
        reason: str,
        evidence: Mapping[str, Any],
        rule_version: str,
        expected_state: str | None = None,
        affected_ids: Iterable[Any] | None = None,
        merge_plan: Mapping[str, Any] | None = None,
        split_plan: Mapping[str, Any] | None = None,
        undo_plan: Mapping[str, Any] | None = None,
        undo_of_decision_id: str | None = None,
        occurred_at: str | None = None,
        recorded_at: str | None = None,
        decision_id: str | None = None,
    ) -> DuplicateDecision:
        """Append one explicit decision; never execute the requested action."""

        history = self._get_history(cluster_id)
        current = history.current
        target_state = self._validate_state(state)
        if expected_state is not None and expected_state != current.to_state:
            raise InvalidTransitionError(
                f"Expected cluster '{cluster_id}' to be {expected_state}, found {current.to_state}."
            )
        allowed = ALLOWED_TRANSITIONS[current.to_state]
        if target_state not in allowed:
            raise InvalidTransitionError(f"Cannot transition '{current.to_state}' to '{target_state}'.")

        normalized_ids = tuple(current.affected_ids)
        if affected_ids is not None:
            submitted_ids = _ids(affected_ids, "affected_ids", minimum=2)
            if submitted_ids != normalized_ids:
                raise SafetyValidationError("affected_ids cannot change during a decision.")

        normalized_merge_plan = deepcopy(dict(merge_plan)) if merge_plan is not None else None
        normalized_split_plan = deepcopy(dict(split_plan)) if split_plan is not None else None
        normalized_undo_plan = deepcopy(dict(undo_plan)) if undo_plan is not None else None

        if target_state == "merged":
            if current.to_state != "confirmed_duplicate":
                raise InvalidTransitionError("Only a confirmed duplicate can receive a merge decision.")
            self._validate_merge_plan(normalized_merge_plan, normalized_ids)
        elif normalized_merge_plan is not None:
            raise SafetyValidationError("merge_plan is only valid for the merged state.")

        if target_state == "split":
            self._validate_split_plan(normalized_split_plan, normalized_ids)
        elif normalized_split_plan is not None:
            raise SafetyValidationError("split_plan is only valid for the split state.")

        if target_state == "undone":
            undo_id = _required_text(undo_of_decision_id or current.event_id, "undo_of_decision_id")
            if undo_id != current.event_id:
                raise SafetyValidationError("Only the current decision can be undone.")
            normalized_undo_plan = normalized_undo_plan or self.plan_undo(cluster_id)
            self._validate_undo_plan(normalized_undo_plan, current)
        elif normalized_undo_plan is not None or undo_of_decision_id is not None:
            raise SafetyValidationError("undo_plan is only valid for the undone state.")
        else:
            undo_id = None

        event = self._make_event(
            cluster_id=str(cluster_id),
            sequence=len(history.events) + 1,
            from_state=current.to_state,
            to_state=target_state,
            actor=actor,
            reason=reason,
            evidence=evidence,
            rule_version=rule_version,
            affected_ids=normalized_ids,
            merge_plan=normalized_merge_plan,
            split_plan=normalized_split_plan,
            undo_plan=normalized_undo_plan,
            undo_of_decision_id=undo_id,
            occurred_at=occurred_at,
            recorded_at=recorded_at,
            decision_id=decision_id,
        )
        self._clusters[str(cluster_id)] = _ClusterHistory(current=event, events=(*history.events, event))
        return DuplicateDecision.from_event(event)

    # Alias for callers that prefer state-machine terminology.
    transition = decide

    def undo(
        self,
        *,
        cluster_id: str,
        actor: str,
        reason: str,
        evidence: Mapping[str, Any],
        rule_version: str,
        expected_state: str | None = None,
        publication_relationship: Mapping[str, Any] | None = None,
        occurred_at: str | None = None,
        recorded_at: str | None = None,
        decision_id: str | None = None,
    ) -> DuplicateDecision:
        """Append an undo decision with a preservation-only restore plan."""

        plan = self.plan_undo(cluster_id, publication_relationship=publication_relationship)
        return self.decide(
            cluster_id=cluster_id,
            state="undone",
            actor=actor,
            reason=reason,
            evidence=evidence,
            rule_version=rule_version,
            expected_state=expected_state,
            undo_plan=plan,
            undo_of_decision_id=str(plan["undo_of_decision_id"]),
            occurred_at=occurred_at,
            recorded_at=recorded_at,
            decision_id=decision_id,
        )

    def plan_undo(
        self,
        cluster_id: str,
        *,
        publication_relationship: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build the adapter work plan without changing the current decision."""

        history = self._get_history(cluster_id)
        current = history.current
        if current.to_state == "candidate":
            raise InvalidTransitionError("A candidate has no prior decision to undo.")
        previous_state = history.events[-2].to_state if len(history.events) > 1 else "candidate"
        relationship = (
            deepcopy(dict(publication_relationship))
            if publication_relationship is not None
            else {
                "required": True,
                "source": "repository_snapshot_before_decision",
                "action": "restore_previous_relationship",
            }
        )
        return {
            "undo_of_decision_id": current.event_id,
            "restore_state": previous_state,
            "affected_ids": list(current.affected_ids),
            "preserve_source_observations": True,
            "preserve_source_identities": True,
            "preserve_posting_versions": True,
            "preserve_provenance": True,
            "publication_relationship": relationship,
            "actions": [
                "restore_previous_canonical_relationship",
                "restore_previous_publication_relationship",
                "retain_all_immutable_source_evidence",
            ],
            "automatic_merge": False,
            "automatic_publish": False,
        }

    def to_persistence_record(self, cluster_id: str) -> dict[str, Any]:
        """Return the exact adapter payload for existing duplicate tables."""

        history = self._get_history(cluster_id)
        current = DuplicateDecision.from_event(history.current)
        events = [event.to_dict() for event in history.events]
        reasons: list[str] = []
        for event in history.events:
            if event.reason not in reasons:
                reasons.append(event.reason)
        confidence = current.evidence.get("confidence", 0)
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            confidence = 0
        return {
            "cluster": {
                "cluster_id": current.cluster_id,
                "state": current.state,
                "confidence": float(confidence),
                "reasons_json": _json(reasons),
                "review_history_json": _json(events),
                "rule_version": current.rule_version,
                "updated_at": current.recorded_at,
            },
            "members": [
                {
                    "cluster_id": current.cluster_id,
                    "canonical_job_id": canonical_job_id,
                    "member_reasons_json": _json(["decision-service affected ID"]),
                }
                for canonical_job_id in current.affected_ids
            ],
            "current": current.to_dict(),
            "history": events,
            "immutable_preservation": {
                "source_observations": "retain",
                "source_identities": "retain",
                "posting_versions": "retain",
                "field_provenance": "retain",
                "publication": "explicit adapter decision required; never auto-publish",
            },
        }

    def response_payload(self, cluster_id: str) -> dict[str, Any]:
        """Return the proposed admin response shape without raw payloads."""

        persistence = self.to_persistence_record(cluster_id)
        return {
            "decision": persistence["current"],
            "history": persistence["history"],
            "persistence": persistence,
        }

    def _get_history(self, cluster_id: str) -> _ClusterHistory:
        normalized_cluster_id = _required_text(cluster_id, "cluster_id")
        try:
            return self._clusters[normalized_cluster_id]
        except KeyError as exc:
            raise DuplicateDecisionError(f"Unknown duplicate cluster '{normalized_cluster_id}'.") from exc

    @staticmethod
    def _validate_state(state: str) -> DecisionState:
        normalized = str(state or "").strip()
        if normalized not in DECISION_STATES:
            raise SafetyValidationError(f"Unsupported duplicate decision state '{normalized}'.")
        return normalized  # type: ignore[return-value]

    def _make_event(
        self,
        *,
        cluster_id: str,
        sequence: int,
        from_state: str | None,
        to_state: DecisionState,
        actor: str,
        reason: str,
        evidence: Mapping[str, Any],
        rule_version: str,
        affected_ids: tuple[str, ...],
        merge_plan: dict[str, Any] | None = None,
        split_plan: dict[str, Any] | None = None,
        undo_plan: dict[str, Any] | None = None,
        undo_of_decision_id: str | None = None,
        occurred_at: str | None = None,
        recorded_at: str | None = None,
        decision_id: str | None = None,
    ) -> DecisionEvent:
        occurred = _validate_timestamp(occurred_at or self._clock(), "occurred_at")
        recorded = _validate_timestamp(recorded_at or self._clock(), "recorded_at")
        return DecisionEvent(
            event_id=_required_text(decision_id or self._id_factory(), "decision_id"),
            cluster_id=_required_text(cluster_id, "cluster_id"),
            sequence=sequence,
            from_state=from_state,
            to_state=to_state,
            actor=_required_text(actor, "actor"),
            reason=_required_text(reason, "reason"),
            evidence=_evidence(evidence),
            occurred_at=occurred,
            recorded_at=recorded,
            rule_version=_required_text(rule_version, "rule_version"),
            affected_ids=affected_ids,
            merge_plan=deepcopy(merge_plan),
            split_plan=deepcopy(split_plan),
            undo_plan=deepcopy(undo_plan),
            undo_of_decision_id=undo_of_decision_id,
        )

    @staticmethod
    def _copy_event(event: DecisionEvent) -> DecisionEvent:
        return DecisionEvent(
            event_id=event.event_id,
            cluster_id=event.cluster_id,
            sequence=event.sequence,
            from_state=event.from_state,
            to_state=event.to_state,
            actor=event.actor,
            reason=event.reason,
            evidence=deepcopy(event.evidence),
            occurred_at=event.occurred_at,
            recorded_at=event.recorded_at,
            rule_version=event.rule_version,
            affected_ids=tuple(event.affected_ids),
            merge_plan=deepcopy(event.merge_plan),
            split_plan=deepcopy(event.split_plan),
            undo_plan=deepcopy(event.undo_plan),
            undo_of_decision_id=event.undo_of_decision_id,
        )

    @staticmethod
    def _validate_merge_plan(plan: Mapping[str, Any] | None, affected_ids: tuple[str, ...]) -> None:
        if plan is None:
            raise SafetyValidationError("merged decisions require merge_plan.")
        normalized = _json_object(plan, "merge_plan")
        if normalized.get("automatic_merge") is not False or normalized.get("operation") != "plan_only":
            raise SafetyValidationError("merge_plan must explicitly be non-automatic and plan_only.")
        survivor_id = _required_text(normalized.get("survivor_id"), "merge_plan.survivor_id")
        absorbed_ids = _string_list(normalized.get("absorbed_ids"), "merge_plan.absorbed_ids")
        if survivor_id not in affected_ids or any(value not in affected_ids for value in absorbed_ids):
            raise SafetyValidationError("merge_plan IDs must be members of affected_ids.")
        if survivor_id in absorbed_ids or set(absorbed_ids) | {survivor_id} != set(affected_ids):
            raise SafetyValidationError("merge_plan must partition affected_ids into one survivor and absorbed IDs.")
        for key in ("preserved_observation_ids", "preserved_version_ids", "preserved_provenance_ids"):
            _string_list(normalized.get(key), f"merge_plan.{key}")
        for key in ("preserve_source_observations", "preserve_source_identities", "preserve_posting_versions", "preserve_provenance"):
            if not _protected_bool(normalized, key):
                raise SafetyValidationError(f"merge_plan.{key} must be true.")
        _required_text(normalized.get("publication_action"), "merge_plan.publication_action")
        if normalized["publication_action"] == "automatic_publish":
            raise SafetyValidationError("A merge cannot automatically publish.")
        _string_list(normalized.get("undo_actions"), "merge_plan.undo_actions")

    @staticmethod
    def _validate_split_plan(plan: Mapping[str, Any] | None, affected_ids: tuple[str, ...]) -> None:
        if plan is None:
            raise SafetyValidationError("split decisions require split_plan.")
        normalized = _json_object(plan, "split_plan")
        if normalized.get("automatic_merge") is not False or normalized.get("operation") != "plan_only":
            raise SafetyValidationError("split_plan must explicitly be non-automatic and plan_only.")
        raw_partitions = normalized.get("partitions")
        if not isinstance(raw_partitions, Sequence) or isinstance(raw_partitions, (str, bytes)):
            raise SafetyValidationError("split_plan.partitions must be an array of ID arrays.")
        partitions = [_string_list(partition, "split_plan.partition") for partition in raw_partitions]
        if len(partitions) < 2:
            raise SafetyValidationError("split_plan requires at least two partitions.")
        flattened = [item for partition in partitions for item in partition]
        if len(flattened) != len(set(flattened)) or set(flattened) != set(affected_ids):
            raise SafetyValidationError("split_plan partitions must cover affected_ids exactly once.")
        for key in ("preserve_source_observations", "preserve_source_identities", "preserve_posting_versions", "preserve_provenance"):
            if not _protected_bool(normalized, key):
                raise SafetyValidationError(f"split_plan.{key} must be true.")
        _required_text(normalized.get("publication_action"), "split_plan.publication_action")
        if normalized["publication_action"] == "automatic_publish":
            raise SafetyValidationError("A split cannot automatically publish.")
        _string_list(normalized.get("undo_actions"), "split_plan.undo_actions")

    @staticmethod
    def _validate_undo_plan(plan: Mapping[str, Any], current: DecisionEvent) -> None:
        normalized = _json_object(plan, "undo_plan")
        if normalized.get("undo_of_decision_id") != current.event_id:
            raise SafetyValidationError("undo_plan must identify the current decision.")
        if normalized.get("restore_state") not in DECISION_STATES:
            raise SafetyValidationError("undo_plan.restore_state must be a known decision state.")
        submitted_ids = _ids(normalized.get("affected_ids"), "undo_plan.affected_ids", minimum=2)
        if submitted_ids != current.affected_ids:
            raise SafetyValidationError("undo_plan.affected_ids must match the current decision.")
        for key in ("preserve_source_observations", "preserve_source_identities", "preserve_posting_versions", "preserve_provenance"):
            if not _protected_bool(normalized, key):
                raise SafetyValidationError(f"undo_plan.{key} must be true.")
        if normalized.get("automatic_merge") is not False or normalized.get("automatic_publish") is not False:
            raise SafetyValidationError("undo_plan must not perform automatic merge or publication.")
        if not isinstance(normalized.get("publication_relationship"), Mapping):
            raise SafetyValidationError("undo_plan.publication_relationship is required.")
        _string_list(normalized.get("actions"), "undo_plan.actions")


__all__ = [
    "ALLOWED_TRANSITIONS",
    "DECISION_STATES",
    "DUPLICATE_DECISION_API_CONTRACT",
    "DUPLICATE_DECISION_PERSISTENCE_CONTRACT",
    "DecisionEvent",
    "DecisionState",
    "DuplicateDecision",
    "DuplicateDecisionError",
    "DuplicateDecisionService",
    "InvalidTransitionError",
    "SafetyValidationError",
]
