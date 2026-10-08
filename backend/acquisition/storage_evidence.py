"""Private, content-addressed source evidence for explicit operator replay."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import zlib
from threading import RLock
from collections.abc import Mapping
from typing import Any

from backend.storage.base import ObjectNotFoundError, ObjectStorage
from backend.storage.factory import create_object_storage

MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
_ARCHIVE_LOCKS = tuple(RLock() for _ in range(64))
_COLLECTION_KEYS = frozenset({"observed_at", "observation_timestamp", "source_observation_id", "observation_id", "cycle_id", "task_id"})


def _semantic_payload(value: Any, *, company_urls: bool = False, normalized_mapping: bool = False) -> Any:
    if isinstance(value, Mapping):
        return {key: (item if key == "source_raw_payload" else _semantic_payload(item,
                    company_urls=normalized_mapping and key == 'company_urls',
                    normalized_mapping=normalized_mapping or key in ('unified_mapping', 'normalized_mapping')))
                for key, item in value.items()
                if key not in _COLLECTION_KEYS and not (company_urls and key in ('first_seen_at', 'last_seen_at'))}
    if isinstance(value, (list, tuple)):
        return [_semantic_payload(item, company_urls=company_urls, normalized_mapping=normalized_mapping) for item in value]
    return value


class CatalogEvidenceError(RuntimeError):
    """Cold evidence could not be preserved or restored."""


class CatalogEvidenceMissingError(CatalogEvidenceError):
    """The referenced evidence object is missing."""


class CatalogEvidenceCorruptError(CatalogEvidenceError):
    """Evidence does not match its bounded, authenticated envelope."""


def restore_catalog_evidence(reference: Mapping[str, Any], storage: ObjectStorage | None = None) -> dict[str, Any]:
    digest = str(reference.get("storage_evidence_sha256") or "")
    key = str(reference.get("storage_evidence_key") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or key != f"private/catalog/evidence/{digest}.json.gz":
        raise CatalogEvidenceCorruptError("Invalid catalog evidence reference")
    store = storage if storage is not None else create_object_storage()
    try:
        compressed = store.get(key)
    except ObjectNotFoundError:
        raise CatalogEvidenceMissingError("Catalog evidence object is missing") from None
    if len(compressed) > MAX_EVIDENCE_BYTES:
        raise CatalogEvidenceCorruptError("Catalog evidence exceeds size limit")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            body = stream.read(MAX_EVIDENCE_BYTES + 1)
        if len(body) > MAX_EVIDENCE_BYTES or hashlib.sha256(body).hexdigest() != digest:
            raise CatalogEvidenceCorruptError("Catalog evidence digest or size mismatch")
        for field, actual in (("storage_evidence_bytes", len(compressed)), ("storage_evidence_uncompressed_bytes", len(body))):
            if field in reference and reference[field] != actual:
                raise CatalogEvidenceCorruptError("Catalog evidence length mismatch")
        envelope = json.loads(body)
        if not isinstance(envelope, dict) or envelope.get("schema_version") != 1 or not isinstance(envelope.get("payload"), dict) or not isinstance(envelope.get("raw_payload"), dict):
            raise CatalogEvidenceCorruptError("Invalid catalog evidence envelope")
        return envelope
    except (OSError, EOFError, ValueError, UnicodeError, zlib.error):
        raise CatalogEvidenceCorruptError("Catalog evidence is not valid compressed JSON") from None


def archive_catalog_evidence(payload: Mapping[str, Any], raw_payload: Mapping[str, Any] | None = None, storage: ObjectStorage | None = None) -> dict[str, Any]:
    if storage is None and os.getenv('TURSO_DATABASE_URL') and os.getenv('OBJECT_STORAGE_BACKEND', 'local') == 'local':
        raise CatalogEvidenceError('Remote catalog evidence requires shared object storage')
    if raw_payload is None:
        source = payload.get("source_raw_payload")
        raw_payload = source if isinstance(source, Mapping) else _semantic_payload(payload)
    envelope = {"schema_version": 1, "payload": _semantic_payload(payload), "raw_payload": dict(raw_payload)}
    body = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(body) > MAX_EVIDENCE_BYTES:
        raise CatalogEvidenceError("Catalog evidence exceeds size limit")
    digest = hashlib.sha256(body).hexdigest()
    compressed = gzip.compress(body, compresslevel=9, mtime=0)
    reference = {
        "storage_evidence_key": f"private/catalog/evidence/{digest}.json.gz",
        "storage_evidence_sha256": digest,
        "storage_evidence_bytes": len(compressed),
        "storage_evidence_uncompressed_bytes": len(body),
        "storage_evidence_encoding": "gzip",
        "storage_evidence_schema_version": 1,
    }
    store = storage if storage is not None else create_object_storage()
    key = reference["storage_evidence_key"]
    # Concurrent rows can share a digest. Serialize their existence/write/read
    # sequence without an unbounded cache of object keys.
    with _ARCHIVE_LOCKS[int(digest[:2], 16) % len(_ARCHIVE_LOCKS)]:
        if store.exists(key):
            restore_catalog_evidence(reference, store)
        else:
            store.put(key, compressed, content_type="application/gzip", metadata={"sha256": digest})
            # A successful write must be durable and readable before SQL compaction.
            restore_catalog_evidence(reference, store)
    return reference
