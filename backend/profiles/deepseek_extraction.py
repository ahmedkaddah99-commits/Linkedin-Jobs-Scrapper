"""DeepSeek text-only structured extraction fallback."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import requests

from backend.profiles.extraction_schema import _EXTRACTION_JSON_SCHEMA


MODEL_ID = "deepseek-chat"
PROVIDER_NAME = "deepseek"


def _strip_json_fences(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _parse_response(content: str) -> dict[str, Any]:
    parsed = json.loads(_strip_json_fences(content))
    if not isinstance(parsed, dict):
        raise ValueError("DeepSeek extraction response must be a JSON object.")
    extracted_text = str(parsed.get("extracted_text") or "").strip()
    confidence = max(0.0, min(1.0, float(parsed.get("confidence") or 0.0)))
    return {
        "text": extracted_text,
        "char_count": len(extracted_text),
        "method": "deepseek",
        "provider": PROVIDER_NAME,
        "model": MODEL_ID,
        "confidence": confidence,
        "status": "ready" if extracted_text else "failed",
        "warnings": [str(item) for item in (parsed.get("warnings") or [])],
        "pages": [],
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "layout_sections": [
            dict(item) for item in (parsed.get("layout_sections") or []) if isinstance(item, dict)
        ],
        "experience_details": [
            dict(item) for item in (parsed.get("experience_details") or []) if isinstance(item, dict)
        ],
        "evidence_items": [
            dict(item) for item in (parsed.get("evidence_items") or [])
            if isinstance(item, dict) and str(item.get("text") or "").strip()
        ],
    }


def extract_with_deepseek(
    file_name: str,
    text: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    """Structure already-extracted text with DeepSeek.

    DeepSeek is text-only here; OCR and native text extraction remain the
    responsibility of the local document extractor.
    """
    resolved_key = str(api_key or os.getenv("DEEPSEEK_API_KEY") or "").strip()
    resolved_model = str(model or os.getenv("DEEPSEEK_SOURCE_MODEL") or MODEL_ID).strip()
    source_text = str(text or "").strip()
    if not resolved_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured.")
    if not source_text:
        raise ValueError(f"No text available for DeepSeek extraction from {file_name}.")

    prompt = (
        "Extract factual career evidence from this document. Return only a valid JSON object "
        "matching the supplied schema. Do not invent facts. Use complete claims for evidence_items, "
        "and associate them with experience_details where possible.\n\n"
        f"Schema:\n{json.dumps(_EXTRACTION_JSON_SCHEMA, ensure_ascii=False)}\n\n"
        f"Document name: {file_name}\nDocument text:\n{source_text[:900000]}"
    )
    response = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={
            "Authorization": f"Bearer {resolved_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": resolved_model,
            "messages": [
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "stream": False,
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    choices = response.json().get("choices") or []
    if not choices:
        raise ValueError("DeepSeek extraction response missing choices.")
    content = str((choices[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise ValueError("DeepSeek extraction response was empty.")
    result = _parse_response(content)
    result["model"] = resolved_model
    return result


__all__ = ["extract_with_deepseek"]
