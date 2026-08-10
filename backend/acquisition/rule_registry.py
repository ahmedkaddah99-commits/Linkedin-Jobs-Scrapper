"""Shared acquisition state and rule-version contracts.

The acquisition pipeline writes observations and posting versions once.  The
records produced from them are projections, so every projection must identify
the rule version and use the same field-state vocabulary.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


FIELD_STATES = (
    "present",
    "missing",
    "unknown",
    "unsupported",
    "invalid",
    "conflicting",
    "inferred",
)
FIELD_STATE_SET = frozenset(FIELD_STATES)
VALUE_FIELD_STATES = frozenset({"present", "inferred"})

FIELD_STATE_DESCRIPTIONS = {
    "present": "A source-backed value passed normalization.",
    "missing": "The source supports the field, but no value was supplied.",
    "unknown": "The observation does not establish whether the field exists.",
    "unsupported": "The source contract does not expose this field.",
    "invalid": "A value was supplied but failed deterministic validation.",
    "conflicting": "Available source values disagree and no value was selected.",
    "inferred": "A value was derived from source evidence rather than copied.",
}

# This is deliberately code-owned and small.  Migration 045 mirrors these
# rows into a durable registry so operators can query the contract without
# importing Python modules.
RULE_VERSION_REGISTRY: dict[str, dict[str, Any]] = {
    "unified_mapping_v1": {
        "rule_family": "unified_mapping",
        "schema_version": "unified_mapping_v1",
        "description": "Connector-independent acquisition field mapping.",
        "report_only": True,
    },
    "acquisition_quality_v1": {
        "rule_family": "acquisition_quality",
        "schema_version": "acquisition_quality_v1",
        "description": "Shared acquisition normalization and report-only quality rules.",
        "report_only": True,
    },
    "description_representations_v1": {
        "rule_family": "description_representations",
        "schema_version": "description_representations_v1",
        "description": "Raw, sanitized HTML, and plain-text description projections.",
        "report_only": True,
    },
    "application_destination_v1": {
        "rule_family": "application_destination",
        "schema_version": "application_destination_v1",
        "description": "Evidence-backed application URL classification.",
        "report_only": True,
    },
    "field_matrix_v1": {
        "rule_family": "completeness",
        "schema_version": "field_matrix_v1",
        "description": "Report-only field completeness matrix.",
        "report_only": True,
    },
}


def canonical_field_state(state: Any, *, default: str = "unknown") -> str:
    """Return the canonical state, accepting pre-Wave-1 compatibility names."""

    aliases = {
        "known": "present",
        "unsupported_by_source": "unsupported",
        "not_available": "unknown",
    }
    candidate = str(state or "").strip().casefold()
    candidate = aliases.get(candidate, candidate)
    return candidate if candidate in FIELD_STATE_SET else default


def value_is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (Mapping, list, tuple, set, frozenset)):
        return bool(value)
    return True


def field_state_for(
    value: Any = None,
    *,
    supported: bool | None = None,
    observed: bool = False,
    invalid: bool = False,
    conflicting: bool = False,
    inferred: bool = False,
) -> str:
    """Classify a field without collapsing absence into a sentinel value.

    ``supported=None`` means source capability is unknown.  A supported field
    with no value is ``missing``; an unsupported field is ``unsupported``;
    absence without capability evidence is ``unknown``.
    """

    if conflicting:
        return "conflicting"
    if invalid:
        return "invalid"
    if inferred and value_is_present(value):
        return "inferred"
    if value_is_present(value):
        return "present"
    if supported is False:
        return "unsupported"
    if supported is True or observed:
        return "missing"
    return "unknown"


def rule_version_metadata(rule_version: str) -> dict[str, Any] | None:
    metadata = RULE_VERSION_REGISTRY.get(str(rule_version or "").strip())
    return dict(metadata, rule_version=str(rule_version).strip()) if metadata else None


def registered_rule_versions() -> list[dict[str, Any]]:
    return [rule_version_metadata(version) for version in sorted(RULE_VERSION_REGISTRY)]


__all__ = [
    "FIELD_STATE_DESCRIPTIONS",
    "FIELD_STATE_SET",
    "FIELD_STATES",
    "RULE_VERSION_REGISTRY",
    "VALUE_FIELD_STATES",
    "canonical_field_state",
    "field_state_for",
    "registered_rule_versions",
    "rule_version_metadata",
    "value_is_present",
]
