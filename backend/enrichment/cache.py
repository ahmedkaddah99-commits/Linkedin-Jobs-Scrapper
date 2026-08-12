"""Deterministic cache identity and retention helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping

from .contracts import EnrichmentRequest, ProviderMetadata, ProviderResult, RetentionPolicy


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def input_fingerprint(request: EnrichmentRequest) -> str:
    material = {
        "target_type": request.target_type,
        "field_path": request.field_path,
        "input": request.input,
        "context": request.context,
    }
    return hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()


def cache_key(
    request: EnrichmentRequest,
    metadata: ProviderMetadata,
    *,
    fingerprint: str | None = None,
) -> str:
    material = {
        "input_fingerprint": fingerprint or input_fingerprint(request),
        "provider_id": metadata.provider_id,
        "adapter_version": metadata.adapter_version,
        "dataset_version": metadata.dataset_version,
        "snapshot_version": metadata.snapshot_version,
        "rule_version": request.rule_version,
        "policy_version": request.policy_version,
    }
    return hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()


def expires_at(
    result: ProviderResult,
    *,
    retrieved_at: str,
    policy: RetentionPolicy,
) -> str:
    try:
        parsed = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (parsed + timedelta(seconds=policy.ttl_seconds(result.state))).isoformat()


def sanitize_result_payload(result: ProviderResult, *, raw_storage_permitted: bool) -> Mapping[str, Any]:
    """Return a cache-safe payload without persisting prohibited raw responses."""

    payload: dict[str, Any] = {
        "state": result.state,
        "candidates": [
            {
                "candidate_id": candidate.candidate_id,
                "normalized_value": candidate.normalized_value,
                "display_value": candidate.display_value,
                "provider_score": candidate.provider_score,
                "source_uri": candidate.source_uri,
                "source_record_id": candidate.source_record_id,
                "source_field": candidate.source_field,
                "reason": candidate.reason,
            }
            for candidate in result.candidates
        ],
        "request_count": result.request_count,
        "latency_ms": result.latency_ms,
        "cost_units": result.cost_units,
        "warnings": list(result.warnings),
    }
    if raw_storage_permitted and result.raw_storage_permitted:
        payload["raw_storage_permitted"] = True
    else:
        payload["raw_storage_permitted"] = False
    return payload
