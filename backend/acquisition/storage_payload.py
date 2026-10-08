"""Compact durable job JSON after extraction, without changing semantic hashes."""
from __future__ import annotations

from collections.abc import Mapping
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
