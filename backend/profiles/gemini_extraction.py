"""Gemini Flash-Lite multimodal OCR and evidence extraction.

Uses the stable ``gemini-2.5-flash-lite`` model via the Google Gen AI SDK.
Provides a drop-in extraction function that returns the same dict shape as
:func:`backend.profiles.document_text.extract_document_text`.

Architecture
------------
* PDFs and images -> sent as raw bytes (multimodal) to Gemini.
* Textual sources (DOCX, TXT, HTML, etc.) -> sent as text input.
* Gemini returns structured JSON: extracted text, layout sections, detected
  experience details, confidence, and warnings.
* The caller is responsible for falling back to local extraction on failure.
"""

from __future__ import annotations

import json
import logging
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config.env_schema import get_env

LOGGER = logging.getLogger(__name__)

MODEL_ID = "gemini-2.5-flash-lite"
PROVIDER_NAME = "gemini"

_IMAGE_SUFFIXES = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}

_MIME_MAP: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
}

_EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "extracted_text": {
            "type": "string",
            "description": "Full extracted text content from the document or image.",
        },
        "layout_sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Section heading or label."},
                    "type": {
                        "type": "string",
                        "description": "Section type: heading, paragraph, list, table, caption, annotation, comment.",
                    },
                    "text": {"type": "string", "description": "Text content of this section."},
                },
                "required": ["title", "type", "text"],
            },
        },
        "experience_details": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "employer": {"type": "string", "description": "Employer or organization name."},
                    "role": {"type": "string", "description": "Job title or role."},
                    "location": {"type": "string", "description": "Location of this experience."},
                    "start_date": {"type": "string", "description": "Start date as written."},
                    "end_date": {"type": "string", "description": "End date as written."},
                    "dates": {"type": "string", "description": "Original date range or duration."},
                    "bullets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Bullet points describing responsibilities and achievements.",
                    },
                },
            },
        },
        "evidence_items": {
            "type": "array",
            "description": (
                "Meaningful candidate claims tied to an experience_details entry. "
                "Prefer complete achievements and responsibilities. Exclude names, contact "
                "details, headings, skill labels, standalone locations, standalone dates, "
                "and organization names."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Complete reviewable claim."},
                    "evidence_type": {
                        "type": "string",
                        "description": "achievement, metric, responsibility, project, leadership, stakeholder, challenge, tool, education, or motivation.",
                    },
                    "inferred_employer": {"type": "string"},
                    "inferred_role": {"type": "string"},
                    "dates": {"type": "array", "items": {"type": "string"}},
                    "location": {"type": "string"},
                    "source_section": {"type": "string"},
                },
                "required": ["text", "evidence_type"],
            },
        },
        "confidence": {
            "type": "number",
            "description": "Overall confidence score between 0.0 and 1.0 for the extraction quality.",
        },
        "warnings": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Any warnings about low-quality text, missing sections, or extraction issues.",
        },
    },
    "required": ["extracted_text", "confidence", "warnings"],
}



def _mime_type(file_name: str) -> str:
    suffix = Path(file_name or "").suffix.lower()
    if suffix in _MIME_MAP:
        return _MIME_MAP[suffix]
    guessed, _ = mimetypes.guess_type(file_name)
    return guessed or "application/octet-stream"


def _is_multimodal(file_name: str) -> bool:
    """Return True when the file should be sent as multimodal (bytes) to Gemini."""
    suffix = Path(file_name or "").suffix.lower()
    return suffix == ".pdf" or suffix in _IMAGE_SUFFIXES


def _build_client():
    """Build a Gemini client using ``GEMINI_API_KEY`` or ``GOOGLE_API_KEY``."""
    from google import genai

    api_key = get_env("GEMINI_API_KEY") or get_env("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY or GOOGLE_API_KEY environment variable is required "
            "for Gemini extraction."
        )
    return genai.Client(api_key=api_key)


def _gemini_extract_multimodal(
    client: Any, file_name: str, data: bytes, mime_type: str
) -> dict[str, Any]:
    """Send raw PDF/image bytes to Gemini as a multimodal input."""
    from google.genai import types

    prompt = (
        "Extract all text from this document or image. "
        "Return structured JSON with: extracted_text, layout_sections (title, type, text), "
        "experience_details (employer, role, location, start_date, end_date, dates, bullets), "
        "evidence_items (complete meaningful claims tied to an experience_details entry), "
        "confidence (0.0-1.0), and warnings. "
        "Do not create evidence items from names, contact details, headings, standalone "
        "locations, standalone dates, or organization names. "
        "Capture handwritten annotations, image-based comments, and any text visible in screenshots."
    )

    contents = [
        types.Part.from_bytes(data=data, mime_type=mime_type),
        prompt,
    ]

    response = client.models.generate_content(
        model=MODEL_ID,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=_EXTRACTION_JSON_SCHEMA,
            temperature=0.0,
        ),
    )

    return _parse_gemini_response(response, file_name)


def _gemini_extract_text(
    client: Any, file_name: str, text: str
) -> dict[str, Any]:
    """Send pre-parsed text to Gemini for structured extraction."""
    from google.genai import types

    if not text.strip():
        return {
            "text": "",
            "char_count": 0,
            "method": "gemini",
            "provider": PROVIDER_NAME,
            "model": MODEL_ID,
            "confidence": 0.0,
            "status": "failed",
            "warnings": ["No text content to send to Gemini."],
            "pages": [],
            "layout_sections": [],
            "experience_details": [],
            "evidence_items": [],
        }

    max_chars = 900_000
    truncated = text[:max_chars] if len(text) > max_chars else text
    truncation_warning = (
        [f"Text truncated from {len(text):,} to {max_chars:,} characters for Gemini input."]
        if len(text) > max_chars
        else []
    )

    prompt = (
        "Extract structured information from the following document text. "
        "Return JSON with: extracted_text (the full original text), "
        "layout_sections (title, type, text for each logical section), "
        "experience_details (employer, role, location, start_date, end_date, dates, bullets), "
        "evidence_items (complete meaningful claims tied to an experience_details entry), "
        "excluding names, contact details, headings, standalone locations/dates, "
        "confidence (0.0-1.0), and warnings."
    )

    response = client.models.generate_content(
        model=MODEL_ID,
        contents=[prompt, truncated],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=_EXTRACTION_JSON_SCHEMA,
            temperature=0.0,
        ),
    )

    result = _parse_gemini_response(response, file_name)
    if truncation_warning:
        result.setdefault("warnings", [])
        result["warnings"].extend(truncation_warning)
    return result



def _parse_gemini_response(response: Any, file_name: str) -> dict[str, Any]:
    """Convert a Gemini API response into the standard extraction dict shape."""
    extracted_at = datetime.now(timezone.utc).isoformat()
    status = "ready"
    warnings: list[str] = []
    confidence = 0.0
    extracted_text = ""
    layout_sections: list[dict[str, Any]] = []
    experience_details: list[dict[str, Any]] = []
    evidence_items: list[dict[str, Any]] = []

    try:
        raw_text = response.text if hasattr(response, "text") else ""
    except Exception:
        raw_text = ""

    if not raw_text:
        return {
            "text": "",
            "char_count": 0,
            "method": "gemini",
            "provider": PROVIDER_NAME,
            "model": MODEL_ID,
            "confidence": 0.0,
            "status": "failed",
            "warnings": ["Gemini returned an empty response."],
            "pages": [],
            "extracted_at": extracted_at,
            "layout_sections": [],
            "experience_details": [],
            "evidence_items": [],
        }

    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        extracted_text = raw_text.strip()
        warnings.append("Gemini did not return valid JSON; using raw text.")
        confidence = 0.5
        status = "partial"
    else:
        extracted_text = str(parsed.get("extracted_text") or raw_text).strip()
        layout_sections = [
            dict(section) for section in (parsed.get("layout_sections") or [])
            if isinstance(section, dict)
        ]
        experience_details = [
            dict(exp) for exp in (parsed.get("experience_details") or [])
            if isinstance(exp, dict)
        ]
        evidence_items = [
            dict(item) for item in (parsed.get("evidence_items") or [])
            if isinstance(item, dict) and str(item.get("text") or "").strip()
        ]
        confidence = max(0.0, min(1.0, float(parsed.get("confidence") or 0.0)))
        warnings = [str(w) for w in (parsed.get("warnings") or [])]

    pages: list[dict[str, Any]] = [
        {
            "page_number": 1,
            "method": "gemini",
            "status": status,
            "char_count": len(extracted_text),
            "confidence": confidence,
            "warnings": warnings,
        }
    ]

    if not extracted_text.strip():
        status = "failed"

    return {
        "text": extracted_text.strip(),
        "char_count": len(extracted_text.strip()),
        "method": "gemini",
        "provider": PROVIDER_NAME,
        "model": MODEL_ID,
        "confidence": confidence,
        "status": status,
        "warnings": warnings,
        "pages": pages,
        "extracted_at": extracted_at,
        "layout_sections": layout_sections,
        "experience_details": experience_details,
        "evidence_items": evidence_items,
    }


def extract_with_gemini(file_name: str, data: bytes) -> dict[str, Any]:
    """Extract text and structured fields from a document using Gemini Flash-Lite.

    Parameters
    ----------
    file_name : str
        Source file name (used to detect format via suffix).
    data : bytes
        Raw file bytes.

    Returns
    -------
    dict
        Same shape as :func:`extract_document_text`, with additional keys:
        ``provider``, ``model``, ``extracted_at``, ``layout_sections``,
        and ``experience_details``.

    Raises
    ------
    RuntimeError
        If ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY`` is not configured.
    google.genai.errors.APIError
        On Gemini API failures (callers should fall back to local extraction).
    """
    client = _build_client()
    extraction_started = datetime.now(timezone.utc).isoformat()

    if _is_multimodal(file_name):
        mime_type = _mime_type(file_name)
        result = _gemini_extract_multimodal(client, file_name, data, mime_type)
    else:
        from backend.profiles.document_text import extract_document_text

        local_extraction = extract_document_text(file_name, data, allow_ocr=False)
        local_text = str(local_extraction.get("text") or "")

        if not local_text.strip():
            return {
                **local_extraction,
                "provider": PROVIDER_NAME,
                "model": MODEL_ID,
                "extracted_at": extraction_started,
                "layout_sections": [],
                "experience_details": [],
                "evidence_items": [],
            }

        result = _gemini_extract_text(client, file_name, local_text)

    result.setdefault("provider", PROVIDER_NAME)
    result.setdefault("model", MODEL_ID)
    result.setdefault("extracted_at", extraction_started)
    result.setdefault("layout_sections", [])
    result.setdefault("experience_details", [])
    result.setdefault("evidence_items", [])

    return result


__all__ = ["MODEL_ID", "PROVIDER_NAME", "extract_with_gemini"]
