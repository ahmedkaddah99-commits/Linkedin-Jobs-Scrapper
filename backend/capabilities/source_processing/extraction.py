from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from backend.domain.source_processing import (
    OCR_METHODS,
    SOURCE_STATUS_EXTRACTED,
    SOURCE_STATUS_FAILED,
    SOURCE_STATUS_NEEDS_REVIEW,
    SOURCE_STATUS_PROCESSING,
    SourceTextRecord,
    _map_extraction_status_to_source_status,
    utc_now_iso,
)
from backend.profiles.document_text import extract_document_text
from backend.capabilities.source_processing.structure_parser import parse_structured_fields

LOGGER = logging.getLogger(__name__)
LOW_OCR_CONFIDENCE_THRESHOLD = 0.70


def process_source(source_id: str, file_path: str, *, allow_ocr: bool = True) -> SourceTextRecord:
    """Process a single source file and return a SourceTextRecord."""
    file_name = Path(file_path).name if file_path else ""
    record = SourceTextRecord(
        source_id=source_id,
        file_path=file_path,
        file_name=file_name,
        status=SOURCE_STATUS_PROCESSING,
        processed_at=utc_now_iso(),
    )

    try:
        data = Path(file_path).read_bytes()
    except Exception as exc:
        record.status = SOURCE_STATUS_FAILED
        record.error = f"Failed to read file: {exc}"
        record.processed_at = utc_now_iso()
        return record

    try:
        extraction = _extract_gemini_then_deepseek_or_local(file_name, data, allow_ocr=allow_ocr)
    except Exception as exc:
        record.status = SOURCE_STATUS_FAILED
        record.error = f"Extraction failed: {exc}"
        record.processed_at = utc_now_iso()
        return record

    text = str(extraction.get("text") or "")
    record.text = text
    record.char_count = int(extraction.get("char_count") or 0)
    record.method = str(extraction.get("method") or "none")
    record.confidence = float(extraction.get("confidence") or 0)
    record.warnings = [str(w) for w in (extraction.get("warnings") or [])]
    record.pages = [dict(p) for p in (extraction.get("pages") or []) if isinstance(p, dict)]
    record.provider = str(extraction.get("provider") or "")
    record.model = str(extraction.get("model") or "")
    record.layout_sections = [
        dict(item) for item in (extraction.get("layout_sections") or [])
        if isinstance(item, dict)
    ]
    record.experience_details = [
        dict(item) for item in (extraction.get("experience_details") or [])
        if isinstance(item, dict)
    ]
    record.evidence_items = [
        dict(item) for item in (extraction.get("evidence_items") or [])
        if isinstance(item, dict)
    ]


    extraction_status = str(extraction.get("status") or "failed")
    record.is_ocr = record.method in OCR_METHODS
    record.is_low_confidence_ocr = record.is_ocr and record.confidence < LOW_OCR_CONFIDENCE_THRESHOLD

    record.status = _map_extraction_status_to_source_status(
        extraction_status, record.method, record.confidence, record.warnings,
    )

    if record.is_low_confidence_ocr and record.status != SOURCE_STATUS_FAILED:
        record.status = SOURCE_STATUS_NEEDS_REVIEW
        if not any("low confidence" in w.lower() for w in record.warnings):
            record.warnings.append(
                f"OCR confidence is low ({record.confidence:.0%}); results may not be reliable."
            )

    # Parse structured fields
    if text.strip():
        try:
            structured = parse_structured_fields(text)
        except Exception:
            structured = {}
        record.employer = str(structured.get("employer") or "")
        record.role = str(structured.get("role") or "")
        record.dates = [str(d) for d in (structured.get("dates") or [])]
        record.headings = [str(h) for h in (structured.get("headings") or [])]
        record.bullets = [str(b) for b in (structured.get("bullets") or [])]
        record.certificates = [str(c) for c in (structured.get("certificates") or [])]
        record.letter_paragraphs = [str(p) for p in (structured.get("letter_paragraphs") or [])]

    record.processed_at = utc_now_iso()

    return record


def _extract_gemini_then_deepseek_or_local(
    file_name: str, data: bytes, *, allow_ocr: bool = True
) -> dict[str, Any]:
    """Use Gemini first, then optionally structure local text with DeepSeek."""
    try:
        from backend.profiles.gemini_extraction import extract_with_gemini

        gemini_result = extract_with_gemini(file_name, data)
        if gemini_result.get("status") != "failed":
            LOGGER.info(
                "Gemini extracted %d chars from %s (confidence=%.2f)",
                gemini_result.get("char_count", 0),
                file_name,
                gemini_result.get("confidence", 0.0),
            )
            return gemini_result
        LOGGER.warning(
            "Gemini extraction succeeded but returned no text for %s; falling back.",
            file_name,
        )
    except Exception as exc:
        LOGGER.warning(
            "Gemini extraction failed for %s (%s); falling back to local extraction.",
            file_name,
            exc,
        )

    local_result = extract_document_text(file_name, data, allow_ocr=allow_ocr)
    local_text = str(local_result.get("text") or "").strip()
    if local_text and (os.getenv("DEEPSEEK_API_KEY") or "").strip():
        try:
            from backend.profiles.deepseek_extraction import extract_with_deepseek

            return extract_with_deepseek(file_name, local_text)
        except Exception as exc:
            LOGGER.warning(
                "DeepSeek text extraction failed for %s (%s); using local extraction.",
                file_name,
                exc,
            )
    return local_result


def run_source_processing_pipeline(
    sources: list[dict[str, Any]],
    *,
    allow_ocr: bool = True,
) -> list[SourceTextRecord]:
    """Process a list of source file dicts.

    Each source must have source_id and file_path.
    Returns a list of SourceTextRecord with per-source status and extracted content.
    """
    results: list[SourceTextRecord] = []
    for source in sources:
        source_id = str(source.get("source_id") or "")
        file_path = str(source.get("file_path") or "")

        if not source_id:
            source_id = f"source_{Path(file_path).stem}" if file_path else "source_unknown"

        if not file_path or not Path(file_path).exists():
            record = SourceTextRecord(
                source_id=source_id,
                file_path=file_path,
                file_name=Path(file_path).name if file_path else "",
                status=SOURCE_STATUS_FAILED,
                error="Source file does not exist." if file_path else "No file path provided.",
                processed_at=utc_now_iso(),
            )
            results.append(record)
            continue

        record = process_source(source_id, file_path, allow_ocr=allow_ocr)
        results.append(record)

    return results


def process_source_bytes(source_id: str, file_name: str, data: bytes, *, allow_ocr: bool = True) -> SourceTextRecord:
    """Process source file bytes through Gemini with local/DeepSeek fallback.

    Writes bytes to a temp file for disk-based processing, then cleans up.
    """
    import tempfile, os
    suffix = Path(file_name).suffix if file_name else ".bin"
    tmp_path = None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.write(tmp_fd, data)
        os.close(tmp_fd)
        return process_source(source_id, tmp_path, allow_ocr=allow_ocr)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def build_source_processing_summary(results: list[SourceTextRecord]) -> dict[str, Any]:
    """Build a summary dict from SourceTextRecord results."""
    total = len(results)
    return {
        "total_sources": total,
        "extracted": sum(1 for r in results if r.status == SOURCE_STATUS_EXTRACTED),
        "needs_review": sum(1 for r in results if r.status == SOURCE_STATUS_NEEDS_REVIEW),
        "failed": sum(1 for r in results if r.status == SOURCE_STATUS_FAILED),
        "processing": sum(1 for r in results if r.status == SOURCE_STATUS_PROCESSING),
        "ocr_sources": sum(1 for r in results if r.is_ocr),
        "low_confidence_ocr": sum(1 for r in results if r.is_low_confidence_ocr),
        "total_characters": sum(r.char_count for r in results),
        "results": [r.to_dict() for r in results],
    }
