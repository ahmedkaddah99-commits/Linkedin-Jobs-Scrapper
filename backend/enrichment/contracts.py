"""Pure contracts for offline-first enrichment and normalization.

The contracts intentionally contain no database, HTTP, storage, or AI
dependency.  Providers return candidates and evidence; an orchestration layer
outside this module owns persistence and selection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Protocol
from uuid import uuid4


class ProviderResultState(StrEnum):
    MATCHED = "matched"
    NO_MATCH = "no_match"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"
    BLOCKED_BY_POLICY = "blocked_by_policy"
    BUDGET_EXHAUSTED = "budget_exhausted"
    RETRYABLE_ERROR = "retryable_error"
    PERMANENT_ERROR = "permanent_error"


PROVIDER_RESULT_STATES = frozenset(item.value for item in ProviderResultState)
VERSION_KINDS = frozenset(
    {
        "mapping_table",
        "provider_adapter",
        "dataset_snapshot",
        "policy",
        "rule",
        "model",
        "prompt",
    }
)


@dataclass(frozen=True, slots=True)
class LicenceMetadata:
    """License/terms metadata that must travel with derived evidence."""

    licence_id: str = ""
    licence_url: str = ""
    attribution: str = ""
    terms_url: str = ""
    raw_storage_permitted: bool = False


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """Separate retention rules for positive and negative cache results."""

    positive_seconds: int = 30 * 24 * 60 * 60
    negative_seconds: int = 24 * 60 * 60
    raw_response_allowed: bool = False
    max_evidence_excerpt_chars: int = 1000
    privacy_class: str = "job_public"
    retention_class: str = "enrichment_evidence"

    def ttl_seconds(self, state: str) -> int:
        return max(0, self.positive_seconds if state == ProviderResultState.MATCHED else self.negative_seconds)


@dataclass(slots=True)
class ProviderBudget:
    """Hard execution budget.  The safe default permits no external calls."""

    max_requests: int = 0
    max_cost_units: float = 0.0
    requests_used: int = 0
    cost_units_used: float = 0.0

    @property
    def remaining_requests(self) -> int:
        return max(0, self.max_requests - self.requests_used)

    @property
    def remaining_cost_units(self) -> float:
        return max(0.0, self.max_cost_units - self.cost_units_used)

    def consume(self, *, requests: int = 1, cost_units: float = 0.0) -> bool:
        requests = max(0, int(requests))
        cost_units = max(0.0, float(cost_units))
        if self.requests_used + requests > max(0, self.max_requests):
            return False
        if self.cost_units_used + cost_units > max(0.0, self.max_cost_units):
            return False
        self.requests_used += requests
        self.cost_units_used += cost_units
        return True


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    provider_id: str
    adapter_version: str
    dataset_version: str = ""
    snapshot_version: str = ""
    display_name: str = ""
    supported_target_types: tuple[str, ...] = ()
    supported_fields: tuple[str, ...] = ()
    licence: LicenceMetadata = field(default_factory=LicenceMetadata)
    documentation_url: str = ""
    network_required: bool = False
    default_cacheable: bool = True


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    supported: bool
    reason: str = ""
    network_required: bool = False
    offline: bool = True


@dataclass(frozen=True, slots=True)
class EnrichmentRequest:
    target_type: str
    target_id: str
    field_path: str
    input: Mapping[str, Any]
    context: Mapping[str, Any] = field(default_factory=dict)
    policy_version: str = "enrichment_policy_v1"
    rule_version: str = "enrichment_foundation_v1"
    request_id: str = field(default_factory=lambda: f"enrichment_request_{uuid4().hex}")


@dataclass(frozen=True, slots=True)
class EnrichmentCandidate:
    candidate_id: str
    normalized_value: Any
    display_value: str = ""
    provider_score: float | None = None
    source_uri: str = ""
    source_record_id: str = ""
    source_field: str = ""
    evidence_excerpt: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class EvidenceEnvelope:
    """A provider-independent, append-only evidence envelope."""

    target_type: str
    target_id: str
    field_path: str
    input_fingerprint: str
    normalized_candidate_value: Any
    candidate_id: str
    provider_id: str
    adapter_version: str
    dataset_version: str
    snapshot_version: str
    source_uri: str
    source_record_id: str
    source_field: str
    extraction_method: str
    observed_at: str
    retrieved_at: str
    licence: LicenceMetadata
    terms_url: str
    privacy_class: str
    retention_class: str
    rule_version: str
    result_state: str
    evidence_id: str = field(default_factory=lambda: f"enrichment_evidence_{uuid4().hex}")
    raw_value: Any = None
    raw_evidence_excerpt: str = ""
    raw_storage_permitted: bool = False
    content_hash: str = ""
    model_version: str = ""
    prompt_version: str = ""
    provider_score: float | None = None
    calibrated_confidence: float | None = None
    selected: bool = False
    conflict_group: str = ""
    reviewer_decision: str = ""
    reviewer_reason: str = ""
    reviewer_id: str = ""
    reviewed_at: str = ""
    superseded_evidence_id: str = ""
    request_count: int = 0
    latency_ms: float = 0.0
    cost_units: float = 0.0

    def __post_init__(self) -> None:
        if self.result_state not in PROVIDER_RESULT_STATES:
            raise ValueError(f"Unsupported provider result state: {self.result_state}")
        if self.calibrated_confidence is not None and not 0 <= self.calibrated_confidence <= 1:
            raise ValueError("calibrated_confidence must be between 0 and 1")
        if self.provider_score is not None and not 0 <= self.provider_score <= 1:
            raise ValueError("provider_score must be between 0 and 1")
        if self.raw_storage_permitted is False and self.raw_value is not None:
            raise ValueError("raw_value cannot be present when raw storage is prohibited")


@dataclass(frozen=True, slots=True)
class ProviderExecutionContext:
    budget: ProviderBudget = field(default_factory=ProviderBudget)
    retention_policy: RetentionPolicy = field(default_factory=RetentionPolicy)
    allow_network: bool = False
    now_iso: str = ""


@dataclass(frozen=True, slots=True)
class ProviderResult:
    state: str
    candidates: tuple[EnrichmentCandidate, ...] = ()
    evidence: tuple[EvidenceEnvelope, ...] = ()
    request_count: int = 0
    latency_ms: float = 0.0
    cost_units: float = 0.0
    raw_storage_permitted: bool = False
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.state not in PROVIDER_RESULT_STATES:
            raise ValueError(f"Unsupported provider result state: {self.state}")
        if self.request_count < 0 or self.latency_ms < 0 or self.cost_units < 0:
            raise ValueError("Provider execution metrics cannot be negative")


class EnrichmentProvider(Protocol):
    """A pure provider boundary; persistence is deliberately not a method."""

    def metadata(self) -> ProviderMetadata: ...

    def capability(self, request: EnrichmentRequest) -> ProviderCapability: ...

    def resolve(self, request: EnrichmentRequest, context: ProviderExecutionContext) -> ProviderResult: ...
