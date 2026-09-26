"""Persistence helpers for append-only enrichment evidence and inactive versions."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from typing import Any

from backend.database.connection import DatabaseConnection
from backend.domain.models import utc_now_iso

from .cache import expires_at, sanitize_result_payload
from .contracts import EvidenceEnvelope, ProviderResult, RetentionPolicy, VERSION_KINDS


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def append_evidence(connection: DatabaseConnection, evidence: EvidenceEnvelope) -> str:
    """Append one evidence row without permitting raw storage accidentally."""

    raw_allowed = bool(evidence.raw_storage_permitted and evidence.licence.raw_storage_permitted)
    raw_value = evidence.raw_value if raw_allowed else None
    excerpt = evidence.raw_evidence_excerpt if raw_allowed else ""
    if raw_allowed:
        excerpt = excerpt[:1000]
    connection.execute(
        """
        INSERT INTO enrichment_evidence (
            evidence_id, target_type, target_id, field_path, input_fingerprint,
            raw_value_json, raw_evidence_excerpt, raw_storage_permitted,
            normalized_candidate_json, candidate_id, provider_id, adapter_version,
            dataset_version, snapshot_version, source_uri, source_record_id,
            source_field, extraction_method, observed_at, retrieved_at,
            licence_id, licence_url, attribution, terms_url, privacy_class,
            retention_class, content_hash, rule_version, model_version,
            prompt_version, provider_score, calibrated_confidence, result_state,
            selected, conflict_group, reviewer_decision, reviewer_reason,
            reviewer_id, reviewed_at, superseded_evidence_id, request_count,
            latency_ms, cost_units, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?)
        """,
        (
            evidence.evidence_id,
            evidence.target_type,
            evidence.target_id,
            evidence.field_path,
            evidence.input_fingerprint,
            _json(raw_value),
            excerpt,
            int(raw_allowed),
            _json(evidence.normalized_candidate_value),
            evidence.candidate_id,
            evidence.provider_id,
            evidence.adapter_version,
            evidence.dataset_version,
            evidence.snapshot_version,
            evidence.source_uri,
            evidence.source_record_id,
            evidence.source_field,
            evidence.extraction_method,
            evidence.observed_at,
            evidence.retrieved_at,
            evidence.licence.licence_id,
            evidence.licence.licence_url,
            evidence.licence.attribution,
            evidence.terms_url,
            evidence.privacy_class,
            evidence.retention_class,
            evidence.content_hash,
            evidence.rule_version,
            evidence.model_version,
            evidence.prompt_version,
            evidence.provider_score,
            evidence.calibrated_confidence,
            evidence.result_state,
            int(evidence.selected),
            evidence.conflict_group,
            evidence.reviewer_decision,
            evidence.reviewer_reason,
            evidence.reviewer_id,
            evidence.reviewed_at,
            evidence.superseded_evidence_id,
            evidence.request_count,
            evidence.latency_ms,
            evidence.cost_units,
            utc_now_iso(),
        ),
    )
    return evidence.evidence_id


def register_version(
    connection: DatabaseConnection,
    *,
    version_kind: str,
    version_key: str,
    version_value: str,
    metadata: Mapping[str, Any] | None = None,
    active: bool = False,
) -> str:
    """Register a version; inactive is the safe default."""

    if version_kind not in VERSION_KINDS:
        raise ValueError(f"Unsupported enrichment version kind: {version_kind}")
    version_id = f"enrichment_version_{version_kind}_{version_key}_{version_value}".replace(" ", "_")
    connection.execute(
        """
        INSERT OR IGNORE INTO enrichment_version_registry (
            version_id, version_kind, version_key, version_value, is_active,
            metadata_json, created_at, activated_at, deactivated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, '', '')
        """,
        (version_id, version_kind, version_key, version_value, int(active), _json(metadata or {}), utc_now_iso()),
    )
    return version_id


def activate_version(connection: DatabaseConnection, version_id: str) -> None:
    """Explicitly activate one version while preserving all registry rows."""

    row = connection.execute(
        "SELECT version_kind FROM enrichment_version_registry WHERE version_id = ?",
        (version_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown enrichment version: {version_id}")
    now = utc_now_iso()
    connection.execute(
        "UPDATE enrichment_version_registry SET is_active=0, deactivated_at=? WHERE version_kind=? AND is_active=1",
        (now, str(row["version_kind"])),
    )
    connection.execute(
        "UPDATE enrichment_version_registry SET is_active=1, activated_at=? WHERE version_id=?",
        (now, version_id),
    )


def list_versions(connection: DatabaseConnection, *, version_kind: str = "") -> list[dict[str, Any]]:
    if version_kind:
        rows = connection.execute(
            "SELECT * FROM enrichment_version_registry WHERE version_kind=? ORDER BY created_at, version_id",
            (version_kind,),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM enrichment_version_registry ORDER BY created_at, version_id"
        ).fetchall()
    return [dict(row) for row in rows]


def put_cache_entry(
    connection: DatabaseConnection,
    *,
    cache_key: str,
    input_fingerprint: str,
    provider_id: str,
    adapter_version: str,
    dataset_version: str,
    rule_version: str,
    policy_version: str,
    result: ProviderResult,
    retrieved_at: str,
    policy: RetentionPolicy,
) -> None:
    payload = sanitize_result_payload(result, raw_storage_permitted=policy.raw_response_allowed)
    connection.execute(
        """
        INSERT INTO enrichment_cache_entries (
            cache_key, input_fingerprint, provider_id, adapter_version,
            dataset_version, rule_version, policy_version, result_state,
            result_json, raw_storage_permitted, observed_at, retrieved_at,
            expires_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET
            result_state=excluded.result_state,
            result_json=excluded.result_json,
            raw_storage_permitted=excluded.raw_storage_permitted,
            observed_at=excluded.observed_at,
            retrieved_at=excluded.retrieved_at,
            expires_at=excluded.expires_at,
            updated_at=excluded.updated_at
        """,
        (
            cache_key,
            input_fingerprint,
            provider_id,
            adapter_version,
            dataset_version,
            rule_version,
            policy_version,
            result.state,
            _json(payload),
            int(bool(payload.get("raw_storage_permitted"))),
            retrieved_at,
            retrieved_at,
            expires_at(result, retrieved_at=retrieved_at, policy=policy),
            utc_now_iso(),
            utc_now_iso(),
        ),
    )


def get_cache_entry(connection: DatabaseConnection, cache_key: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM enrichment_cache_entries WHERE cache_key=?",
        (cache_key,),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    try:
        result["result"] = json.loads(str(result.get("result_json") or "{}"))
    except (TypeError, ValueError):
        result["result"] = {}
    return result


__all__ = [
    "activate_version",
    "append_evidence",
    "get_cache_entry",
    "list_versions",
    "put_cache_entry",
    "register_version",
]
