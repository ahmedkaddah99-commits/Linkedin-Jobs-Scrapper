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
    classify_evidence_type,
)
from backend.domain.models import utc_now_iso

LOGGER = logging.getLogger(__name__)

# CP-039R: Bounded polling/backoff constants
DEFAULT_POLL_TIMEOUT_SECONDS = 120
DEFAULT_POLL_INITIAL_DELAY_SECONDS = 1.0
DEFAULT_POLL_MAX_DELAY_SECONDS = 8.0
DEFAULT_POLL_BACKOFF_FACTOR = 2.0
STRUCTURED_EXTRACTION_VERSION = "gemini-career-v2"



def _source_asset_content_key(asset_id: str, file_bytes: bytes) -> str:
    """Build a stable content key for idempotency checks."""
    h = sha256()
    h.update(asset_id.encode("utf-8"))
    h.update(file_bytes)
    return h.hexdigest()


def _stable_experience_id(source_id: str, experience: dict[str, Any], index: int) -> str:
    identity = "|".join((
        source_id,
        str(experience.get("employer") or "").strip().lower(),
        str(experience.get("role") or experience.get("job_title") or "").strip().lower(),
        str(experience.get("start_date") or experience.get("dates") or "").strip().lower(),
        str(experience.get("end_date") or "").strip().lower(),
        str(index),
    ))
    return "exp_" + sha256(identity.encode("utf-8")).hexdigest()[:16]


def _structured_experiences(
    record: SourceTextRecord,
    *,
    source_id: str,
    profile_id: str,
) -> list[dict[str, Any]]:
    experiences: list[dict[str, Any]] = []
    for index, raw in enumerate(record.experience_details):
        employer = str(raw.get("employer") or "").strip()
        role = str(raw.get("role") or raw.get("job_title") or "").strip()
        bullets = [str(item).strip() for item in (raw.get("bullets") or []) if str(item).strip()]
        if not employer and not role and not bullets:
            continue
        experiences.append({
            "experience_id": _stable_experience_id(source_id, raw, index),
            "profile_id": profile_id,
            "employer": employer,
            "job_title": role,
            "location": str(raw.get("location") or "").strip(),
            "start_date": str(raw.get("start_date") or "").strip(),
            "end_date": str(raw.get("end_date") or "").strip(),
            "dates": str(raw.get("dates") or "").strip(),
            "description": "\n".join(bullets),
            "source_kind": "extracted",
            "source_asset_ids": [source_id],
            "status": "active",
            "sort_order": index,
            "metadata": {"extraction_version": STRUCTURED_EXTRACTION_VERSION},
        })
    return experiences


def _match_structured_experience(
    item: dict[str, Any], experiences: list[dict[str, Any]],
) -> dict[str, Any] | None:
    employer = str(item.get("inferred_employer") or item.get("employer") or "").strip().lower()
    role = str(item.get("inferred_role") or item.get("role") or "").strip().lower()
    for experience in experiences:
        exp_employer = str(experience.get("employer") or "").strip().lower()
        exp_role = str(experience.get("job_title") or "").strip().lower()
        if (employer and employer == exp_employer) or (role and role == exp_role):
            return experience
    return experiences[0] if len(experiences) == 1 else None


def _structured_evidence(
    record: SourceTextRecord,
    *,
    source_id: str,
    source_asset: str,
    profile_id: str,
    batch_id: str,
    experiences: list[dict[str, Any]],
) -> list[CandidateEvidence]:
    raw_items = list(record.evidence_items)
    if not raw_items:
        for experience in record.experience_details:
            for bullet in experience.get("bullets") or []:
                text = str(bullet).strip()
                if text:
                    raw_items.append({
                        "text": text,
                        "inferred_employer": experience.get("employer", ""),
                        "inferred_role": experience.get("role", ""),
                        "dates": [
                            value for value in (
                                experience.get("start_date"), experience.get("end_date")
                            ) if value
                        ],
                        "location": experience.get("location", ""),
                    })

    evidence: list[CandidateEvidence] = []
    for raw in raw_items:
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        experience = _match_structured_experience(raw, experiences)
        if experiences and experience is None:
            # The guided review maps every claim to the work context it came
            # from. General profile text belongs elsewhere and must not create
            # an unresolvable review item.
            continue
        mapping = {}
        if experience is not None:
            mapping = {
                "experience_id": str(experience["experience_id"]),
                "company": str(experience.get("employer") or ""),
                "role": str(experience.get("job_title") or ""),
                "start_date": str(experience.get("start_date") or ""),
                "end_date": str(experience.get("end_date") or ""),
                "label": " at ".join(filter(None, (
                    str(experience.get("job_title") or ""),
                    str(experience.get("employer") or ""),
                ))),
            }
        evidence.append(CandidateEvidence.create(
            profile_id=profile_id,
            evidence_type=str(raw.get("evidence_type") or classify_evidence_type(text)),
            text=text,
            source_asset=source_asset,
            source_id=source_id,
            excerpt=text,
            location=str(raw.get("location") or raw.get("source_section") or "").strip(),
            confidence=record.confidence,
            inferred_employer=str(raw.get("inferred_employer") or raw.get("employer") or ""),
            inferred_role=str(raw.get("inferred_role") or raw.get("role") or ""),
            dates=[str(value) for value in (raw.get("dates") or []) if str(value).strip()],
            source_confidence=record.confidence,
            experience_mapping=mapping,
            metadata={
                "batch_id": batch_id,
                "extraction_version": STRUCTURED_EXTRACTION_VERSION,
            },
        ))
    return evidence


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
    all_experiences: list[dict[str, Any]] = []
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

            if record.provider != "gemini":
                source_status["status"] = SOURCE_STATUS_FAILED
                source_status["error"] = (
                    "Gemini structured extraction is temporarily unavailable. "
                    "Retry after provider quota or billing is available."
                )
                source_results.append(source_status)
                continue

            if record.status in (SOURCE_STATUS_EXTRACTED, "needs_review") and record.text.strip():
                experiences = _structured_experiences(
                    record, source_id=asset_id, profile_id=profile_id,
                )
                evidence_items = _structured_evidence(
                    record,
                    source_id=asset_id,
                    source_asset=file_name,
                    profile_id=profile_id,
                    batch_id=batch_id,
                    experiences=experiences,
                )
                if not evidence_items:
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
                    for evidence_item in evidence_items:
                        evidence_item.metadata.update({
                            "batch_id": batch_id,
                            "extraction_version": "local-fallback-v1",
                        })

                all_experiences.extend(experiences)

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
        "experiences": all_experiences,
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
