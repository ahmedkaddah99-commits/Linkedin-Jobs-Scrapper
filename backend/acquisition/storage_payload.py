"""Compact durable job JSON after extraction, without changing semantic hashes."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

PAGE_HTML_FIELDS = ("source_page_html", "page_html", "source_html", "raw_html", "html")


def _without_page_html(record: Mapping[str, Any]) -> dict[str, Any]:
    cleaned = {key: value for key, value in record.items() if key not in PAGE_HTML_FIELDS}
    for key in ("source_raw_payload", "producer_record", "source_record", "observation_contract"):
        child = cleaned.get(key)
        if isinstance(child, Mapping):
            cleaned[key] = _without_page_html(child)
    return cleaned


def compact_job_payload(payload: Mapping[str, Any], *, normalized: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Keep unique source fields and one mapping; discard duplicated envelopes.

    Extraction must precede this call. A normalized application destination
    permits page HTML removal and is copied into raw inputs for reprocessing.
    Description HTML is deliberately distinct from whole-page HTML.
    """
    result = dict(payload)
    result.pop("content_fingerprint", None)
    mapping = result.get("unified_mapping")
    if isinstance(mapping, Mapping) and result.get("field_provenance") == mapping.get("fields"):
        result.pop("field_provenance", None)
    destination = (normalized or result).get("application_destination")
    if isinstance(destination, Mapping):
        result["application_destination"] = dict(destination)
        resolved = destination.get("resolved_url")
        if resolved:
            result["application_url"] = resolved
        for key in PAGE_HTML_FIELDS:
            result.pop(key, None)
    raw = result.get("source_raw_payload")
    if isinstance(raw, Mapping):
        raw = dict(raw)
        contract = raw.get("observation_contract")
        if isinstance(contract, Mapping):
            compact_contract = dict(contract)
            compact_contract.pop("normalized_mapping", None)
            original = compact_contract.get("source_record")
            if isinstance(original, Mapping) and all(key in result and result[key] == value for key, value in original.items()):
                compact_contract.pop("source_record", None)
            raw["observation_contract"] = compact_contract
        producer = raw.get("producer_record")
        if isinstance(producer, Mapping):
            # Retain conflicting source values as evidence; drop exact copies.
            producer = {key: value for key, value in producer.items() if key not in result or result[key] != value}
            if producer:
                raw["producer_record"] = producer
            else:
                raw.pop("producer_record", None)
        if isinstance(destination, Mapping):
            raw = _without_page_html(raw)
        raw = {key: value for key, value in raw.items() if key not in result or result[key] != value}
        if raw:
            result["source_raw_payload"] = raw
        else:
            result.pop("source_raw_payload", None)
    return result


DESCRIPTION_ALIASES = ("description", "description_raw", "description_html", "full_description")


def _compact_normalized_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _compact_normalized_value(item) for key, item in value.items()
                if key not in {"raw_value", "evidence"}}
    if isinstance(value, (list, tuple)):
        return [_compact_normalized_value(item) for item in value]
    return deepcopy(value)


def _compact_field_record(record: Any) -> Any:
    if not isinstance(record, Mapping):
        return deepcopy(record)
    result = _compact_normalized_value(record)
    # Legacy records sometimes contain only a raw value. Preserve the value
    # public_contract would have selected, without retaining its evidence body.
    from backend.acquisition.public_contract import _record_value
    value = _record_value(record)
    if value is not None:
        result["normalized_value"] = _compact_normalized_value(value)
    return result


def compact_catalog_payload(
    payload: Mapping[str, Any], *, normalized: Mapping[str, Any] | None = None,
    storage_evidence_key: str | None = None,
) -> dict[str, Any]:
    """Build a durable normalized projection after extraction.

    The caller must persist and verify the original evidence before supplying
    storage_evidence_key. Existing references alone never authorize discarding
    newly supplied raw evidence. Conflicting description forms remain inline.
    """
    result = deepcopy(compact_job_payload(payload, normalized=normalized))
    canonical = result.get("description_text")
    if canonical is None and isinstance(result.get("description"), str):
        canonical = result["description"]
        result["description_text"] = canonical
    if isinstance(canonical, str):
        for key in DESCRIPTION_ALIASES:
            if result.get(key) == canonical:
                result.pop(key, None)
    mapping = result.get("unified_mapping")
    if not isinstance(mapping, Mapping):
        mapping = result.get("normalized_mapping")
    if isinstance(mapping, Mapping):
        provenance = result.get("field_provenance")
        if provenance == mapping.get("fields"):
            result.pop("field_provenance", None)
        elif isinstance(provenance, Mapping):
            result["field_provenance"] = {key: _compact_field_record(value) for key, value in provenance.items()}
        compact = {key: deepcopy(value) for key, value in mapping.items()
                   if key in {"schema_version", "rule_version", "source_observation_id", "observed_at", "company_urls"}}
        for group in ("fields", "company_fields", "timestamps"):
            records = mapping.get(group)
            if isinstance(records, Mapping):
                compact[group] = {key: _compact_field_record(value) for key, value in records.items()}
        description = compact.get("fields", {}).get("description")
        if isinstance(description, dict) and isinstance(description.get("normalized_value"), Mapping):
            forms = description["normalized_value"]
            equivalents = {"clean_text": "description_text", "raw_html": "description_raw", "sanitized_html": "description_html"}
            description["normalized_value"] = {key: value for key, value in forms.items()
                if value is not None and value != result.get(equivalents.get(key, "")) and value != canonical}
            original_description = mapping.get("fields", {}).get("description", {})
            raw_description = original_description.get("raw_value") if isinstance(original_description, Mapping) else None
            if isinstance(raw_description, str) and raw_description and raw_description != canonical and raw_description not in forms.values() and raw_description not in [result.get(key) for key in DESCRIPTION_ALIASES]:
                description["normalized_value"]["source_description"] = raw_description
        result["unified_mapping"] = compact
        result.pop("normalized_mapping", None)
    if storage_evidence_key:
        result["storage_evidence_key"] = storage_evidence_key
        result.pop("source_raw_payload", None)
    return result


def hydrate_description_aliases(payload: Mapping[str, Any], canonical_description: str | None = None) -> dict[str, Any]:
    """Restore legacy description aliases for readers without overwriting conflicts."""
    result = deepcopy(dict(payload))
    canonical = canonical_description if canonical_description is not None else result.get("description_text")
    if isinstance(canonical, str):
        result.setdefault("description_text", canonical)
        for key in DESCRIPTION_ALIASES:
            result.setdefault(key, canonical)
    return result
