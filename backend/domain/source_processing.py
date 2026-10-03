from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from backend.domain.models import utc_now_iso


SOURCE_STATUS_QUEUED = "queued"
SOURCE_STATUS_EMPTY = "empty"
SOURCE_STATUS_TIMEOUT = "timeout"


SOURCE_STATUS_PROCESSING = "processing"
SOURCE_STATUS_EXTRACTED = "extracted"
SOURCE_STATUS_NEEDS_REVIEW = "needs_review"
SOURCE_STATUS_FAILED = "failed"

SOURCE_PROCESSING_STATUSES = {
    SOURCE_STATUS_QUEUED,

    SOURCE_STATUS_PROCESSING,
    SOURCE_STATUS_EXTRACTED,
    SOURCE_STATUS_NEEDS_REVIEW,
    SOURCE_STATUS_FAILED,
    SOURCE_STATUS_EMPTY,
    SOURCE_STATUS_TIMEOUT,

}

# CP-039R: Terminal source statuses — processing ends here.
SOURCE_TERMINAL_STATUSES = {
    SOURCE_STATUS_EXTRACTED,
    SOURCE_STATUS_NEEDS_REVIEW,
    SOURCE_STATUS_FAILED,
    SOURCE_STATUS_EMPTY,
    SOURCE_STATUS_TIMEOUT,
}

# CP-039R: Source processing batch states exposed to the UI.
SOURCE_BATCH_STATUS_QUEUED = "queued"
SOURCE_BATCH_STATUS_PROCESSING = "processing"
SOURCE_BATCH_STATUS_COMPLETED = "completed"
SOURCE_BATCH_STATUS_TIMEOUT = "timeout"
SOURCE_BATCH_STATUS_FAILED = "failed"

SOURCE_BATCH_TERMINAL_STATUSES = {
    SOURCE_BATCH_STATUS_COMPLETED,
    SOURCE_BATCH_STATUS_TIMEOUT,
    SOURCE_BATCH_STATUS_FAILED,
}



EXTRACTION_METHOD_NATIVE = "native"
EXTRACTION_METHOD_OCR = "ocr"
EXTRACTION_METHOD_DOCX = "docx"
EXTRACTION_METHOD_PDF_NATIVE = "pdf_native"
EXTRACTION_METHOD_PDF_MIXED = "pdf_mixed"
EXTRACTION_METHOD_PDF_OCR = "pdf_ocr"
EXTRACTION_METHOD_IMAGE_OCR = "image_ocr"
EXTRACTION_METHOD_XLSX = "xlsx"
EXTRACTION_METHOD_PLAIN_TEXT = "plain_text"
EXTRACTION_METHOD_PLAIN_TEXT_FALLBACK = "plain_text_fallback"
EXTRACTION_METHOD_GEMINI = "gemini"

EXTRACTION_METHOD_NONE = "none"

OCR_METHODS = {
    EXTRACTION_METHOD_OCR,
    EXTRACTION_METHOD_PDF_OCR,
    EXTRACTION_METHOD_PDF_MIXED,
    EXTRACTION_METHOD_IMAGE_OCR,
}


def _map_extraction_status_to_source_status(
    extraction_status: str,
    method: str,
    confidence: float,
    warnings: list[str],
) -> str:
    if extraction_status == "failed":
        return SOURCE_STATUS_FAILED
    has_ocr_warnings = bool(
        method in OCR_METHODS
        and (
            confidence < 0.70
            or any("low" in str(w).lower() and "confidence" in str(w).lower() for w in warnings)
        )
    )
    if extraction_status == "partial" or has_ocr_warnings:
        return SOURCE_STATUS_NEEDS_REVIEW
    if extraction_status == "ready":
        return SOURCE_STATUS_EXTRACTED
    return SOURCE_STATUS_FAILED


@dataclass(slots=True)
class SourceTextRecord:
    source_id: str
    file_path: str = ""
    file_name: str = ""
    text: str = ""
    char_count: int = 0
    method: str = EXTRACTION_METHOD_NONE
    confidence: float = 0.0
    status: str = SOURCE_STATUS_PROCESSING
    is_ocr: bool = False
    provider: str = ""
    model: str = ""

    is_low_confidence_ocr: bool = False
    warnings: list[str] = field(default_factory=list)
    error: str = ""
    pages: list[dict[str, Any]] = field(default_factory=list)
    processed_at: str = ""

    # Structured fields extracted from text
    employer: str = ""
    role: str = ""
    dates: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    certificates: list[str] = field(default_factory=list)
    letter_paragraphs: list[str] = field(default_factory=list)
    layout_sections: list[dict[str, Any]] = field(default_factory=list)
    experience_details: list[dict[str, Any]] = field(default_factory=list)
    evidence_items: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "text": self.text,
            "char_count": self.char_count,
            "method": self.method,
            "provider": self.provider,
            "model": self.model,

            "confidence": self.confidence,
            "status": self.status,
            "is_ocr": self.is_ocr,
            "is_low_confidence_ocr": self.is_low_confidence_ocr,
            "warnings": list(self.warnings),
            "error": self.error,
            "pages": list(self.pages),
            "processed_at": self.processed_at,
            "employer": self.employer,
            "role": self.role,
            "dates": list(self.dates),
            "headings": list(self.headings),
            "bullets": list(self.bullets),
            "certificates": list(self.certificates),
            "letter_paragraphs": list(self.letter_paragraphs),
            "layout_sections": [dict(item) for item in self.layout_sections],
            "experience_details": [dict(item) for item in self.experience_details],
            "evidence_items": [dict(item) for item in self.evidence_items],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SourceTextRecord":
        return cls(
            source_id=str(payload.get("source_id") or ""),
            file_path=str(payload.get("file_path") or ""),
            file_name=str(payload.get("file_name") or ""),
            text=str(payload.get("text") or ""),
            char_count=int(payload.get("char_count") or 0),
            method=str(payload.get("method") or EXTRACTION_METHOD_NONE),
            provider=str(payload.get("provider") or ""),
            model=str(payload.get("model") or ""),

            confidence=float(payload.get("confidence") or 0.0),
            status=str(payload.get("status") or SOURCE_STATUS_PROCESSING),
            is_ocr=bool(payload.get("is_ocr")),
            is_low_confidence_ocr=bool(payload.get("is_low_confidence_ocr")),
            warnings=[str(w) for w in (payload.get("warnings") or [])],
            error=str(payload.get("error") or ""),
            pages=[dict(p) for p in (payload.get("pages") or []) if isinstance(p, dict)],
            processed_at=str(payload.get("processed_at") or ""),
            employer=str(payload.get("employer") or ""),
            role=str(payload.get("role") or ""),
            dates=[str(d) for d in (payload.get("dates") or [])],
            headings=[str(h) for h in (payload.get("headings") or [])],
            bullets=[str(b) for b in (payload.get("bullets") or [])],
            certificates=[str(c) for c in (payload.get("certificates") or [])],
            letter_paragraphs=[str(p) for p in (payload.get("letter_paragraphs") or [])],
            layout_sections=[dict(item) for item in (payload.get("layout_sections") or []) if isinstance(item, Mapping)],
            experience_details=[dict(item) for item in (payload.get("experience_details") or []) if isinstance(item, Mapping)],
            evidence_items=[dict(item) for item in (payload.get("evidence_items") or []) if isinstance(item, Mapping)],
        )


__all__ = [
    "EXTRACTION_METHOD_DOCX",
    "EXTRACTION_METHOD_GEMINI",

    "EXTRACTION_METHOD_IMAGE_OCR",
    "EXTRACTION_METHOD_NATIVE",
    "EXTRACTION_METHOD_NONE",
    "EXTRACTION_METHOD_OCR",
    "EXTRACTION_METHOD_PDF_MIXED",
    "EXTRACTION_METHOD_PDF_NATIVE",
    "EXTRACTION_METHOD_PDF_OCR",
    "EXTRACTION_METHOD_PLAIN_TEXT",
    "EXTRACTION_METHOD_PLAIN_TEXT_FALLBACK",
    "EXTRACTION_METHOD_XLSX",
    "OCR_METHODS",
    "SOURCE_BATCH_STATUS_COMPLETED",
    "SOURCE_BATCH_STATUS_FAILED",
    "SOURCE_BATCH_STATUS_PROCESSING",
    "SOURCE_BATCH_STATUS_QUEUED",
    "SOURCE_BATCH_STATUS_TIMEOUT",
    "SOURCE_BATCH_TERMINAL_STATUSES",
    "SOURCE_STATUS_EMPTY",
    "SOURCE_STATUS_QUEUED",
    "SOURCE_STATUS_TIMEOUT",
    "SOURCE_TERMINAL_STATUSES",


    "SOURCE_PROCESSING_STATUSES",
    "SOURCE_STATUS_EXTRACTED",
    "SOURCE_STATUS_FAILED",
    "SOURCE_STATUS_NEEDS_REVIEW",
    "SOURCE_STATUS_PROCESSING",
    "SourceTextRecord",
    "_map_extraction_status_to_source_status",
]
