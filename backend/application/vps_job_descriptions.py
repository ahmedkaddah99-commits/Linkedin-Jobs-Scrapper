"""Shared posting-version descriptions generated on the acquisition VPS."""

from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from collections.abc import Callable, Mapping
from typing import Any

from backend.application.personalized_jobs_intelligence import build_preserved_original_posting


PROMPT_VERSION = "runr_description_v1"
OUTPUT_LANGUAGE = "en"
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"


class RateLimitError(RuntimeError):
    """Stop the current free-tier batch when OpenRouter has no capacity."""
SECTIONS = (
    "responsibilities", "required_qualifications", "preferred_qualifications",
    "benefits", "application_details",
)


def build_runr_description(
    row: Mapping[str, Any], generate: Callable[[str], Mapping[str, Any]],
) -> dict[str, Any]:
    """Transform the full employer posting; fail rather than silently substitute text."""
    original = build_preserved_original_posting(row)
    source = str(original.get("description_text") or original.get("description") or "").strip()
    if not source:
        raise ValueError("posting description is empty")
    prompt = (
        "Rewrite the full employer job posting into clear English sections. "
        "Preserve every stated condition, number, location, and language requirement. "
        "Classify a qualification as required only when the employer says it is required; "
        "otherwise put it under preferred if stated as optional. Do not invent facts. "
        "Return JSON with source_language (ISO 639-1), overview (short string), and arrays "
        "responsibilities, required_qualifications, preferred_qualifications, benefits, "
        "application_details. Each array item is an object with text (English) and "
        "source_excerpt (exact short quote from the original posting). Use [] when absent. "
        "Return only one valid JSON object.\n\n"
        f"Posting:\n{source}"
    )
    value = generate(prompt)
    if not isinstance(value, Mapping):
        raise ValueError("model response is not an object")
    return _normalize_description(row, original, value)


def build_runr_descriptions(
    rows: list[Mapping[str, Any]], generate: Callable[[str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Extract several posting versions in one free-tier request without mixing jobs."""
    if not rows or len(rows) > 5:
        raise ValueError("batch must contain between one and five postings")
    originals = [build_preserved_original_posting(row) for row in rows]
    postings = []
    for row, original in zip(rows, originals):
        version_id = str(row.get("current_version_id") or "")
        source = str(original.get("description_text") or original.get("description") or "").strip()
        if not version_id or not source:
            raise ValueError("posting version or description is empty")
        postings.append({"id": version_id, "title": str(row.get("title") or ""), "posting": source})
    ids = [posting["id"] for posting in postings]
    if len(set(ids)) != len(ids):
        raise ValueError("batch contains duplicate posting versions")
    prompt = (
        "For EACH employer job posting in the JSON array, rewrite the entire posting into clear English. "
        "Keep each job separate using its exact id. Preserve stated numbers, conditions, locations, "
        "and language requirements. A qualification is required only if the employer says so; "
        "put optional qualifications under preferred. Do not invent facts or omit supported details. "
        "Return one JSON object with a jobs array containing exactly one object per input id. "
        "Each object must have id, source_language (ISO 639-1), overview (short string), and "
        "responsibilities, required_qualifications, preferred_qualifications, benefits, "
        "application_details arrays. Each array item needs English text and an exact short "
        "source_excerpt from that same original posting. Use [] where absent. "
        "Return JSON only.\n\nPostings:\n" + json.dumps(postings, ensure_ascii=False)
    )
    response = generate(prompt)
    if not isinstance(response, Mapping) or not isinstance(response.get("jobs"), list):
        raise ValueError("model response missing jobs array")
    jobs = response["jobs"]
    if len(jobs) != len(rows) or any(not isinstance(job, Mapping) for job in jobs):
        raise ValueError("model response has wrong job count")
    by_id = {str(job.get("id") or ""): job for job in jobs}
    if len(by_id) != len(ids) or set(by_id) != set(ids):
        raise ValueError("model response has mismatched posting versions")
    return [
        _normalize_description(row, original, {**by_id[version_id], "_runr_model": response.get("_runr_model")})
        for row, original, version_id in zip(rows, originals, ids)
    ]


def _normalize_description(row: Mapping[str, Any], original: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
    required = ("source_language", "overview", *SECTIONS)
    for field in required:
        if field not in value:
            raise ValueError(f"model response missing field: {field}")
    summary: dict[str, Any] = {
        "source_language": str(value["source_language"] or "").strip().lower(),
        "output_language": OUTPUT_LANGUAGE,
        "overview": str(value["overview"] or "").strip(),
    }
    if not summary["source_language"] or not summary["overview"]:
        raise ValueError("model response has empty language or overview")
    for field in SECTIONS:
        items = value[field]
        if not isinstance(items, list):
            raise ValueError(f"model response has invalid array: {field}")
        normalized = []
        for item in items:
            if not isinstance(item, Mapping) or not str(item.get("text") or "").strip() or not str(item.get("source_excerpt") or "").strip():
                raise ValueError(f"model response has invalid item: {field}")
            normalized.append({
                "text": str(item["text"]).strip(),
                "source_excerpt": str(item["source_excerpt"]).strip(),
            })
        summary[field] = normalized
    return {
        "version_id": str(row.get("current_version_id") or ""),
        "canonical_job_id": str(row.get("canonical_job_id") or ""),
        "content_hash": str(row.get("content_hash") or ""),
        "summary": summary,
        "structured_description": {},
        "original_posting": original,
        "provider": "openrouter",
        "model": str(value.get("_runr_model") or os.getenv("RUNR_DESCRIPTION_MODEL", DEFAULT_MODEL)),
        "prompt_version": PROMPT_VERSION,
    }


def openrouter_generate(prompt: str) -> Mapping[str, Any]:
    """Call a schema-capable OpenRouter model from the VPS acquisition process."""
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("description_model_key_missing")
    model = os.getenv("RUNR_DESCRIPTION_MODEL", DEFAULT_MODEL)
    if not (model == "openrouter/free" or model.endswith(":free")):
        raise ValueError("description model must be free-tier")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "provider": {"require_parameters": True},
        "temperature": 0,
        "reasoning": {"effort": "none"},
        "max_tokens": 16384,
    }).encode("utf-8")
    request = Request(
        "https://openrouter.ai/api/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            payload = json.load(response)
    except HTTPError as exc:
        if exc.code == 429:
            raise RateLimitError("openrouter_rate_limited") from exc
        raise
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("model response content is not text")
    result = json.loads(content)
    if isinstance(result, dict):
        result["_runr_model"] = payload.get("model") or DEFAULT_MODEL
    return result
