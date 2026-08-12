"""Provider-neutral, inactive-by-default enrichment foundation."""

from .contracts import (
    EnrichmentCandidate,
    EnrichmentProvider,
    EnrichmentRequest,
    EvidenceEnvelope,
    LicenceMetadata,
    ProviderBudget,
    ProviderCapability,
    ProviderExecutionContext,
    ProviderMetadata,
    ProviderResult,
    ProviderResultState,
    RetentionPolicy,
    VERSION_KINDS,
)

__all__ = [
    "EnrichmentCandidate",
    "EnrichmentProvider",
    "EnrichmentRequest",
    "EvidenceEnvelope",
    "LicenceMetadata",
    "ProviderBudget",
    "ProviderCapability",
    "ProviderExecutionContext",
    "ProviderMetadata",
    "ProviderResult",
    "ProviderResultState",
    "RetentionPolicy",
    "VERSION_KINDS",
]
