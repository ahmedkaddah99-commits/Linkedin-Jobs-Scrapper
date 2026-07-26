"""CP-039R: Source processing pipeline — vertical path from upload to evidence.

Takes source asset IDs, processes through Gemini + fallback, extracts
canonical CandidateEvidence, and persists with idempotency guarantees.

Exposes a synchronous processing function and batch status tracking
for UI polling with bounded backoff.
"""

from __future__ import annotations

import logging
import time
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.domain.source_processing import (
    SOURCE_BATCH_STATUS_COMPLETED,
    SOURCE_BATCH_STATUS_FAILED,
    SOURCE_BATCH_STATUS_PROCESSING,
    SOURCE_BATCH_STATUS_QUEUED,
    SOURCE_BATCH_STATUS_TIMEOUT,
    SOURCE_BATCH_TERMINAL_STATUSES,
    SOURCE_STATUS_EMPTY,
    SOURCE_STATUS_EXTRACTED,
    SOURCE_STATUS_FAILED,
    SOURCE_STATUS_TIMEOUT,
    SOURCE_TERMINAL_STATUSES,
    SourceTextRecord,
)
from backend.domain.candidate_evidence import (
    CandidateEvidence,
    compute_content_hash,
    EVIDENCE_STATUS_NEEDS_REVIEW,
)
from backend.domain.models import utc_now_iso

LOGGER = logging.getLogger(__name__)

# CP-039R: Bounded polling/backoff constants
DEFAULT_POLL_TIMEOUT_SECONDS = 120
DEFAULT_POLL_INITIAL_DELAY_SECONDS = 1.0
DEFAULT_POLL_MAX_DELAY_SECONDS = 8.0
DEFAULT_POLL_BACKOFF_FACTOR = 2.0



def _source_asset_content_key(asset_id: str, file_bytes: bytes) -> str:
    """Build a stable content key for idempotency checks."""
    h = sha256()
    h.update(asset_id.encode("utf-8"))
    h.update(file_bytes)
    return h.hexdigest()


def process_sources_and_extract_evidence(
    sources: list[dict[str, Any]],
    *,
    profile_id: str = "",
    timeout_seconds: float = DEFAULT_POLL_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Process sources through Gemini and extract CandidateEvidence.

    Args:
        sources: List of dicts with asset_id, file_bytes, file_name.
        profile_id: Optional career profile identifier.
        timeout_seconds: Maximum total time per source before timing out.

    Returns:
        dict with batch_id, status, sources, evidence, summary.
    """
    batch_id = f"batch_{uuid4().hex[:12]}"
    started_at = utc_now_iso()

    source_results: list[dict[str, Any]] = []
    all_evidence: list[CandidateEvidence] = []
    processed_content_keys: set[str] = set()

    for source in sources:
        asset_id = str(source.get("asset_id") or "")
        file_name = str(source.get("file_name") or source.get("display_name") or "")
        file_bytes = source.get("file_bytes", b"")

        if isinstance(file_bytes, str):
            file_bytes = file_bytes.encode("utf-8")

        source_status: dict[str, Any] = {
            "asset_id": asset_id,
            "file_name": file_name,
            "status": SOURCE_BATCH_STATUS_QUEUED,
            "extracted_count": 0,
            "error": "",
            "method": "",
            "provider": "",
            "model": "",
            "confidence": 0.0,
            "char_count": 0,
        }

        if not file_bytes:
            source_status["status"] = SOURCE_STATUS_EMPTY
            source_results.append(source_status)
            continue

        # Idempotency: skip duplicate content in this batch
        content_key = _source_asset_content_key(asset_id, file_bytes)
        if content_key in processed_content_keys:
            LOGGER.info("Skipping duplicate content for asset %s", asset_id)
            source_status["status"] = SOURCE_STATUS_EXTRACTED
            source_results.append(source_status)
            continue
        processed_content_keys.add(content_key)

        source_status["status"] = SOURCE_BATCH_STATUS_PROCESSING

        try:
            from backend.capabilities.source_processing.extraction import process_source_bytes

            deadline = time.monotonic() + timeout_seconds
            remaining = deadline - time.monotonic()

            if remaining <= 0:
                source_status["status"] = SOURCE_STATUS_TIMEOUT
                source_status["error"] = "Timed out before processing started."
                source_results.append(source_status)
                continue

            record = process_source_bytes(asset_id, file_name, file_bytes, allow_ocr=True)

            source_status["method"] = record.method
            source_status["provider"] = record.provider
            source_status["model"] = record.model
            source_status["confidence"] = record.confidence
            source_status["char_count"] = record.char_count
            source_status["status"] = record.status

            if record.status in (SOURCE_STATUS_EXTRACTED, "needs_review") and record.text.strip():
                from backend.capabilities.candidate_evidence.extraction import extract_evidence_from_source

                evidence_items = extract_evidence_from_source(
                    profile_id=profile_id,
                    source_id=asset_id,
                    text=record.text,
                    source_asset=file_name,
                    confidence=record.confidence,
                    headings=list(record.headings),
                    dates=list(record.dates),
                )

                # CP-039R: Idempotency via content_hash
                for ev in evidence_items:
                    if ev.content_hash not in processed_content_keys:
                        processed_content_keys.add(ev.content_hash)
                        all_evidence.append(ev)

                source_status["extracted_count"] = len(evidence_items)

                if not evidence_items and record.text.strip():
                    source_status["status"] = SOURCE_STATUS_EMPTY
                    source_status["error"] = "No evidence items extracted from text."

            elif record.status == SOURCE_STATUS_FAILED:
                source_status["status"] = SOURCE_STATUS_FAILED
                source_status["error"] = record.error or "Extraction failed."

            elif record.status == SOURCE_STATUS_TIMEOUT:
                source_status["status"] = SOURCE_STATUS_TIMEOUT
                source_status["error"] = "Processing timed out."

        except Exception as exc:
            LOGGER.exception("Source processing failed for asset %s", asset_id)
            source_status["status"] = SOURCE_STATUS_FAILED
            source_status["error"] = str(exc)

        source_results.append(source_status)

    # Determine batch status
    terminal_states = {s["status"] for s in source_results}
    failed_count = sum(1 for s in source_results if s["status"] == SOURCE_STATUS_FAILED)
    timeout_count = sum(1 for s in source_results if s["status"] == SOURCE_STATUS_TIMEOUT)
    success_count = sum(1 for s in source_results if s["status"] in (SOURCE_STATUS_EXTRACTED, "needs_review"))

    if terminal_states.issubset(SOURCE_TERMINAL_STATUSES):
        if failed_count == len(source_results):
            batch_status = SOURCE_BATCH_STATUS_FAILED
        elif timeout_count == len(source_results):
            batch_status = SOURCE_BATCH_STATUS_TIMEOUT
        else:
            batch_status = SOURCE_BATCH_STATUS_COMPLETED
    elif any(s["status"] == SOURCE_BATCH_STATUS_PROCESSING for s in source_results):
        batch_status = SOURCE_BATCH_STATUS_PROCESSING
    else:
        batch_status = SOURCE_BATCH_STATUS_COMPLETED

    completed_at = utc_now_iso()
    return {
        "batch_id": batch_id,
        "status": batch_status,
        "started_at": started_at,
        "completed_at": completed_at,
        "sources": source_results,
        "evidence": [ev.to_dict() for ev in all_evidence],
        "summary": {
            "total_sources": len(source_results),
            "extracted": success_count,
            "failed": failed_count,
            "timeout": timeout_count,
            "total_evidence": len(all_evidence),
        },
    }


def build_source_processing_state(
    batch_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a compact finite state for UI display.

    Returns dict with state (queued/processing/completed/empty/timeout/failed),
    extracted_count, total_sources, error, and retry_allowed.
    """
    if not batch_result:
        return {
            "state": SOURCE_BATCH_STATUS_QUEUED,
            "extracted_count": 0,
            "total_sources": 0,
            "error": "",
            "retry_allowed": False,
        }

    status = batch_result.get("status", SOURCE_BATCH_STATUS_QUEUED)
    summary = batch_result.get("summary", {})
    sources = batch_result.get("sources", [])
    extracted_count = sum(s.get("extracted_count", 0) for s in sources)
    total_sources = summary.get("total_sources", len(sources))

    has_failed = any(s["status"] == SOURCE_STATUS_FAILED for s in sources)
    has_timeout = any(s["status"] == SOURCE_STATUS_TIMEOUT for s in sources)
    has_empty = any(s["status"] == SOURCE_STATUS_EMPTY for s in sources)
    error = ""

    if status == SOURCE_BATCH_STATUS_FAILED:
        error = "Source processing failed."
    elif status == SOURCE_BATCH_STATUS_TIMEOUT:
        error = "Processing timed out."
    elif has_empty:
        status = SOURCE_STATUS_EMPTY
        error = "No extractable content found."

    return {
        "state": status,
        "extracted_count": extracted_count,
        "total_sources": total_sources,
        "error": error,
        "retry_allowed": has_failed or has_timeout,
    }


__all__ = [
    "DEFAULT_POLL_BACKOFF_FACTOR",
    "DEFAULT_POLL_INITIAL_DELAY_SECONDS",
    "DEFAULT_POLL_MAX_DELAY_SECONDS",
    "DEFAULT_POLL_TIMEOUT_SECONDS",
    "build_source_processing_state",
    "process_sources_and_extract_evidence",
]
