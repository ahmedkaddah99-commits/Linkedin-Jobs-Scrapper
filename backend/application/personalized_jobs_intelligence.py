"""Versioned job-description summaries and free match intelligence.

The catalog owns immutable posting versions.  This module deliberately keeps
derived output behind that boundary: a summary is generated once per posting
version, and user match output is keyed by the posting version, profile
revision, and evaluator version.

The optional Gemini provider is opt-in through ``PERSONALIZED_JOBS_SUMMARY_PROVIDER``.
The deterministic fallback is always available, grounded in the preserved
posting text, and is used when an AI provider is not configured or fails.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any


SUMMARY_PROMPT_VERSION = "phase_e_summary_v1"
MATCH_V1_VERSION = "phase_e_v1"
MATCH_V2_VERSION = "phase_e_v2"
TAILORED_DOCUMENT_VERSION = "phase_e_tailored_document_v1"
MATCH_EVALUATOR_NAME = "runr_match_intelligence"
INTELLIGENCE_CACHE_VERSION = "phase_e_cache_v1"

_BULLET_RE = re.compile(r"^(?:[-*•‣▪◦]|\d+[.)])\s+")
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#./-]*", re.IGNORECASE)
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "into", "is", "it", "of", "on", "or", "our", "the", "their",
    "this", "to", "with", "will", "you", "your", "we", "who", "must", "should",
    "required", "requirements", "preferred", "ability", "experience", "work", "role",
}
_SECTION_ALIASES = {
    "responsibilities": ("responsibilities", "what you will do", "what you'll do", "your impact", "duties"),
    "requirements": ("requirements", "what you bring", "qualifications", "must have", "who you are"),
    "preferred": ("preferred qualifications", "preferred", "nice to have", "bonus", "additional qualifications"),
    "skills": ("skills", "technical skills", "core skills", "key skills"),
    "education": ("education", "educational background", "degree"),
    "languages": ("languages", "language requirements", "language skills"),
    "authorization": ("authorization", "work authorization", "visa", "sponsorship", "right to work"),
    "benefits": ("benefits", "what we offer", "perks", "our offer"),
    "salary": ("salary", "compensation", "pay", "remuneration"),
    "workplace": ("workplace", "work arrangement", "working model", "location"),
    "employment": ("employment", "employment type", "commitment", "job type"),
    "seniority": ("seniority", "level", "experience level", "career level"),
    "experience": ("experience", "years of experience", "required experience", "professional experience"),
    "application": ("how to apply", "application", "applying", "application details", "process"),
}
_CONCEPT_GROUPS = (
    {"manage", "management", "managed", "lead", "leading", "leadership", "coordinate", "coordination"},
    {"analyse", "analyze", "analysis", "analytical", "insight", "reporting"},
    {"develop", "development", "build", "building", "implement", "implementation"},
    {"operate", "operations", "operational", "run", "running"},
    {"communicate", "communication", "stakeholder", "stakeholders", "collaborate", "collaboration"},
    {"test", "testing", "quality", "qa", "validation", "validate"},
    {"plan", "planning", "project", "projects", "program", "programs"},
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _payload(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row.get("version_payload_json")
    if isinstance(raw, Mapping):
        payload = dict(raw)
    else:
        try:
            decoded = json.loads(str(raw or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            decoded = {}
        payload = dict(decoded) if isinstance(decoded, Mapping) else {}
    nested = payload.get("job")
    if isinstance(nested, Mapping):
        payload = {**payload, **dict(nested)}
    return payload


def _value(payload: Mapping[str, Any], row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = payload.get(name)
        if value not in (None, "", []):
            return value
    for name in names:
        value = row.get(name)
        if value not in (None, "", []):
            return value
    return None


def _items(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    result: list[str] = []
    for item in values:
        if isinstance(item, Mapping):
            item = item.get("text") or item.get("label") or item.get("name") or item.get("value") or item.get("language")
        item_text = re.sub(r"\s+", " ", _text(item)).strip(" •-*\t")
        if item_text and item_text not in result:
            result.append(item_text)
    return result


def _list_from_payload(payload: Mapping[str, Any], *names: str) -> list[str]:
    for name in names:
        values = _items(payload.get(name))
        if values:
            return values
    return []


def _section_key(line: str) -> str | None:
    candidate = re.sub(r"[:\-]+$", "", _text(line)).casefold()
    candidate = re.sub(r"\s+", " ", candidate)
    if not candidate or len(candidate) > 80 or _BULLET_RE.match(candidate):
        return None
    for key, aliases in _SECTION_ALIASES.items():
        if candidate in aliases:
            return key
    return None


def _description_sections(description: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"overview": []}
    current = "overview"
    for raw_line in str(description or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        heading = _section_key(line)
        if heading:
            current = heading
            sections.setdefault(current, [])
            continue
        match = _BULLET_RE.match(line)
        item = _BULLET_RE.sub("", line, count=1).strip() if match else line
        if item:
            sections.setdefault(current, []).append(item)
    return {key: list(dict.fromkeys(values)) for key, values in sections.items()}


def _sentences(value: str, *, limit: int = 2) -> str:
    normalized = re.sub(r"\s+", " ", _text(value))
    if not normalized:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", normalized)
    return " ".join(parts[:limit]).strip()


def _first_nonempty(*values: Any) -> str | None:
    for value in values:
        text = _text(value)
        if text:
            return text
    return None


def _salary(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    raw = _value(payload, {}, "salary", "salary_range", "compensation", "pay")
    if not isinstance(raw, Mapping):
        return None
    result: dict[str, Any] = {}
    for output, names in {
        "min": ("min", "minimum", "min_salary", "lower"),
        "max": ("max", "maximum", "max_salary", "upper"),
    }.items():
        for name in names:
            if raw.get(name) not in (None, ""):
                try:
                    result[output] = float(raw[name])
                    break
                except (TypeError, ValueError):
                    continue
    currency = _first_nonempty(raw.get("currency"), raw.get("currency_code"))
    if currency:
        result["currency"] = currency.upper()
    return result or None


def _observation_context(row: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_observation_id": _text(
            row.get("source_observation_id") or row.get("observation_id")
            or payload.get("source_observation_id") or payload.get("observation_id")
        ) or None,
        "source_url": _text(
            row.get("observation_original_url") or row.get("source_url") or row.get("canonical_url")
            or payload.get("source_url") or payload.get("url")
        ) or None,
        "observed_at": _text(
            row.get("observation_observed_at") or row.get("observed_at") or payload.get("observed_at")
        ) or None,
    }


def _extraction_states(
    values: Mapping[str, Any],
    *,
    source: str = "posting_text",
    method: str = "deterministic_grounded",
    source_observation_id: str | None = None,
    source_url: str | None = None,
    observed_at: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Expose Value+State+provenance for every extracted field."""
    return {
        str(field): {
            "value": value,
            "state": "present" if value not in (None, "", []) else "missing",
            "provenance": source,
            "method": method,
            "source_observation_id": source_observation_id,
            "source_url": source_url,
            "observed_at": observed_at,
        }
        for field, value in values.items()
    }


def _deterministic_description(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = _payload(row)
    observation = _observation_context(row, payload)
    description = _text(row.get("description") or payload.get("description"))
    sections = _description_sections(description)
    responsibilities = sections.get("responsibilities") or _list_from_payload(payload, "responsibilities", "main_responsibilities")
    requirements = sections.get("requirements") or _list_from_payload(payload, "requirements", "essential_requirements", "job_requirements")
    preferred = sections.get("preferred") or _list_from_payload(payload, "preferred_qualifications", "preferred")
    skills = sections.get("skills") or _list_from_payload(payload, "skills", "required_skills")
    education = sections.get("education") or _list_from_payload(payload, "education", "education_requirements")
    languages = sections.get("languages") or _list_from_payload(payload, "languages", "language_requirements", "required_languages")
    authorization = _first_nonempty(
        _value(payload, row, "work_authorization", "authorization", "work_permit", "visa_requirement"),
        _sentences(" ".join(sections.get("authorization") or []), limit=1),
    )
    benefits = sections.get("benefits") or _list_from_payload(payload, "benefits", "perks")
    workplace = _first_nonempty(
        _value(payload, row, "work_arrangement", "workplace", "workplace_type", "remote_type"),
        _sentences(" ".join(sections.get("workplace") or []), limit=1),
    )
    employment = _first_nonempty(
        _value(payload, row, "employment_type", "employmentType", "commitment", "job_type"),
        _sentences(" ".join(sections.get("employment") or []), limit=1),
    )
    seniority = _first_nonempty(
        _value(payload, row, "seniority", "experience_level", "level"),
        _sentences(" ".join(sections.get("seniority") or []), limit=1),
    )
    years_experience = _first_nonempty(
        _value(payload, row, "years_experience", "experience_years", "minimum_experience"),
        _sentences(" ".join(sections.get("experience") or []), limit=1),
    )
    salary = _salary(payload) or (_sentences(" ".join(sections.get("salary") or []), limit=1) or None)
    application = sections.get("application") or _list_from_payload(payload, "application_details", "application_requirements", "how_to_apply")
    overview = _sentences(" ".join(sections.get("overview") or []), limit=2) or _sentences(description, limit=2)

    structured = {
        "responsibilities": responsibilities or None,
        "requirements": requirements or None,
        "skills": skills or None,
        "education": education or None,
        "languages": languages or None,
        "authorization": authorization,
        "benefits": benefits or None,
        "salary": salary,
        "workplace_arrangement": workplace,
        "employment_type": employment,
        "seniority": seniority,
        "years_experience": years_experience,
        "unknown_fields": [
            field for field, value in {
                "responsibilities": responsibilities,
                "requirements": requirements,
                "skills": skills,
                "education": education,
                "languages": languages,
                "authorization": authorization,
                "benefits": benefits,
                "salary": salary,
                "workplace_arrangement": workplace,
                "employment_type": employment,
                "seniority": seniority,
                "years_experience": years_experience,
            }.items() if not value
        ],
    }
    structured["extraction"] = _extraction_states({
        field: structured.get(field)
        for field in ("responsibilities", "requirements", "skills", "education", "languages", "authorization", "benefits", "salary", "workplace_arrangement", "employment_type", "seniority", "years_experience")
    }, **observation)
    summary = {
        "overview": overview or None,
        "main_responsibilities": responsibilities or None,
        "essential_requirements": requirements or None,
        "preferred_qualifications": preferred or None,
        "important_application_details": application or None,
        "unknown_fields": [
            field for field, value in {
                "overview": overview,
                "main_responsibilities": responsibilities,
                "essential_requirements": requirements,
                "preferred_qualifications": preferred,
                "important_application_details": application,
            }.items() if not value
        ],
    }
    summary["extraction"] = _extraction_states({
        field: summary.get(field)
        for field in ("overview", "main_responsibilities", "essential_requirements", "preferred_qualifications", "important_application_details")
    }, **observation)
    structured["extraction_fields"] = dict(structured["extraction"])
    summary["extraction_fields"] = dict(summary["extraction"])
    return {"summary": summary, "structured_description": structured, "provider": "deterministic_grounded", "model": "", "prompt_version": SUMMARY_PROMPT_VERSION}


def _normalize_ai_result(value: Any, fallback: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return dict(fallback)
    result = dict(fallback)
    for key in ("overview", "important_application_details"):
        text = _text(value.get(key))
        if text:
            result["summary"][key] = text
    for key in ("main_responsibilities", "essential_requirements", "preferred_qualifications"):
        items = _items(value.get(key))
        if items:
            result["summary"][key] = items
    structured = value.get("structured_description")
    if isinstance(structured, Mapping):
        for key in ("responsibilities", "requirements", "skills", "education", "languages", "benefits"):
            items = _items(structured.get(key))
            if items:
                result["structured_description"][key] = items
        for key in ("authorization", "workplace_arrangement"):
            text = _text(structured.get(key))
            if text:
                result["structured_description"][key] = text
        if isinstance(structured.get("salary"), Mapping):
            result["structured_description"]["salary"] = dict(structured["salary"])
    result["summary"]["unknown_fields"] = [key for key in ("overview", "main_responsibilities", "essential_requirements", "preferred_qualifications", "important_application_details") if not result["summary"].get(key)]
    result["structured_description"]["unknown_fields"] = [key for key in ("responsibilities", "requirements", "skills", "education", "languages", "authorization", "benefits", "salary", "workplace_arrangement", "employment_type", "seniority", "years_experience") if not result["structured_description"].get(key)]
    fallback_structured = fallback.get("structured_description") if isinstance(fallback.get("structured_description"), Mapping) else {}
    fallback_extraction = fallback_structured.get("extraction") if isinstance(fallback_structured, Mapping) else {}
    context = next(iter(fallback_extraction.values()), {}) if isinstance(fallback_extraction, Mapping) else {}
    result["summary"]["extraction"] = _extraction_states({
        key: result["summary"].get(key)
        for key in ("overview", "main_responsibilities", "essential_requirements", "preferred_qualifications", "important_application_details")
    }, method="gemini_grounded" if value else "deterministic_grounded")
    result["structured_description"]["extraction"] = _extraction_states({
        key: result["structured_description"].get(key)
        for key in ("responsibilities", "requirements", "skills", "education", "languages", "authorization", "benefits", "salary", "workplace_arrangement", "employment_type", "seniority", "years_experience")
    }, method="gemini_grounded" if value else "deterministic_grounded", source_observation_id=context.get("source_observation_id"), source_url=context.get("source_url"), observed_at=context.get("observed_at"))
    result["summary"]["extraction_fields"] = dict(result["summary"]["extraction"])
    result["structured_description"]["extraction_fields"] = dict(result["structured_description"]["extraction"])
    return result


def _try_gemini_summary(description: str, fallback: Mapping[str, Any]) -> dict[str, Any] | None:
    if os.getenv("PERSONALIZED_JOBS_SUMMARY_PROVIDER", "").strip().casefold() != "gemini":
        return None
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key or not description:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        schema = {
            "type": "object",
            "properties": {
                "overview": {"type": ["string", "null"]},
                "main_responsibilities": {"type": ["array", "null"], "items": {"type": "string"}},
                "essential_requirements": {"type": ["array", "null"], "items": {"type": "string"}},
                "preferred_qualifications": {"type": ["array", "null"], "items": {"type": "string"}},
                "important_application_details": {"type": ["array", "null"], "items": {"type": "string"}},
                "structured_description": {"type": "object"},
            },
            "required": ["overview", "main_responsibilities", "essential_requirements", "preferred_qualifications", "important_application_details", "structured_description"],
        }
        prompt = (
            "Summarize this employer job posting into the supplied JSON shape. "
            "Use only facts present in the posting. Do not infer salary, benefits, education, "
            "language, authorization, or workplace details. Use null when absent. Keep the "
            "original wording where a requirement needs to remain precise.\n\n"
            f"Schema:\n{json.dumps(schema, ensure_ascii=False)}\n\nPosting:\n{description[:180000]}"
)
        response = client.models.generate_content(
            model=os.getenv("PERSONALIZED_JOBS_SUMMARY_MODEL", "gemini-2.5-flash-lite"),
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=schema,
                temperature=0.0,
            ),
        )
        parsed = json.loads(str(getattr(response, "text", "") or "{}"))
        return _normalize_ai_result(parsed, fallback)
    except Exception:
        return None


def build_description_intelligence(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return a version-keyed summary bundle without changing original text."""
    fallback = _deterministic_description(row)
    payload = _payload(row)
    raw_description = row.get("description")
    if raw_description in (None, ""):
        raw_description = payload.get("description")
    original_description = str(raw_description) if raw_description is not None else ""
    ai_result = _try_gemini_summary(original_description, fallback)
    generated = ai_result or fallback
    original = {
        "version_id": _text(row.get("current_version_id")),
        "version_number": int(row.get("version_number") or 0) or None,
        "content_hash": _text(row.get("content_hash")),
        "title": _first_nonempty(row.get("title"), payload.get("title")),
        "location": _first_nonempty(row.get("version_location"), row.get("location"), payload.get("location")),
        "description": original_description,
        "description_raw": payload.get("description_raw") or original_description,
        "description_html": payload.get("description_html") or None,
        "description_text": payload.get("description_text") or original_description,
        "description_decoding": payload.get("description_decoding") or None,
        "canonical_url": _text(row.get("canonical_url")) or None,
        "apply_url": _text(row.get("apply_url")) or None,
        "observed_at": _text(row.get("observation_observed_at")) or None,
        "preserved": True,
    }
    return {
        "summary": generated["summary"],
        "structured_description": generated["structured_description"],
        "original_posting": original,
        "provider": "gemini" if ai_result else generated.get("provider", "deterministic_grounded"),
        "model": os.getenv("PERSONALIZED_JOBS_SUMMARY_MODEL", "gemini-2.5-flash-lite") if ai_result else "",
        "prompt_version": SUMMARY_PROMPT_VERSION,
    }


def build_preserved_original_posting(row: Mapping[str, Any]) -> dict[str, Any]:
    """Project the employer payload without generating or rewriting any text."""
    payload = _payload(row)
    raw_description = row.get("description")
    if raw_description in (None, ""):
        raw_description = payload.get("description")
    return {
        "version_id": _text(row.get("current_version_id")),
        "version_number": int(row.get("version_number") or 0) or None,
        "content_hash": _text(row.get("content_hash")),
        "title": _first_nonempty(row.get("title"), payload.get("title")),
        "location": _first_nonempty(row.get("version_location"), row.get("location"), payload.get("location")),
        "description": str(raw_description) if raw_description is not None else "",
        "description_raw": payload.get("description_raw") or (str(raw_description) if raw_description is not None else ""),
        "description_html": payload.get("description_html") or None,
        "description_text": payload.get("description_text") or (str(raw_description) if raw_description is not None else ""),
        "description_decoding": payload.get("description_decoding") or None,
        "canonical_url": _text(row.get("canonical_url")) or None,
        "apply_url": _text(row.get("apply_url")) or None,
        "observed_at": _text(row.get("observation_observed_at")) or None,
        "preserved": True,
    }


def _tokens(value: Any) -> set[str]:
    result: set[str] = set()
    for token in _TOKEN_RE.findall(_text(value).casefold().replace("&", " and ")):
        token = token.strip(".-")
        if len(token) > 1 and token not in _STOPWORDS:
            result.add(token)
    return result


def _concept_tokens(value: Any) -> set[str]:
    result = _tokens(value)
    for group in _CONCEPT_GROUPS:
        if result & group:
            result.update(group)
    return result


def _phrase_match(term: str, profile_text: str) -> bool:
    required = _tokens(term)
    if not required:
        return False
    profile_tokens = _tokens(profile_text)
    return required.issubset(profile_tokens) or _text(term).casefold() in _text(profile_text).casefold()


def _semantic_match(term: str, profile_text: str) -> float:
    required = _concept_tokens(term)
    available = _concept_tokens(profile_text)
    if not required or not available:
        return 0.0
    overlap = len(required & available) / max(1, len(required))
    phrase_similarity = SequenceMatcher(None, _text(term).casefold(), _text(profile_text).casefold()).ratio()
    return max(overlap, phrase_similarity if len(_tokens(term)) <= 2 else 0.0)


def _job_terms(structured: Mapping[str, Any], summary: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("skills", "languages", "education", "authorization"):
        values.extend(_items(structured.get(key)))
    values.extend(_items(summary.get("essential_requirements")))
    values.extend(_items(summary.get("preferred_qualifications")))
    if not values:
        values = list(_tokens(summary.get("overview")))
    return list(dict.fromkeys(value for value in values if _text(value)))[:40]


def _requirements(structured: Mapping[str, Any], summary: Mapping[str, Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for key, category, requiredness in (
        ("essential_requirements", "requirement", "essential"),
        ("education", "education", "essential"),
        ("languages", "language", "essential"),
        ("authorization", "authorization", "essential"),
        ("preferred_qualifications", "qualification", "preferred"),
    ):
        source = summary.get(key) if key in summary else structured.get(key)
        for text in _items(source):
            result.append({"text": text, "category": category, "requiredness": requiredness})
    return result


def _profile_context(user_id: str, preferences_record: Mapping[str, Any] | None, profile_store: Any = None) -> dict[str, Any]:
    preferences = dict((preferences_record or {}).get("preferences") or {})
    profile_id = _text((preferences_record or {}).get("profile_id") or preferences.get("profile_id"))
    profile = None
    if profile_store is not None:
        try:
            if profile_id and not profile_id.startswith("user:"):
                candidate = profile_store.get_profile(profile_id)
                if _text(getattr(candidate, "user_id", "")) == str(user_id):
                    profile = candidate
            if profile is None:
                candidates = profile_store.list_profiles(user_id=str(user_id), limit=10)
                profile = candidates[0] if candidates else None
        except (KeyError, TypeError, AttributeError):
            profile = None
    profile_payload = profile.to_dict() if profile is not None and hasattr(profile, "to_dict") else {}
    metadata = profile_payload.get("metadata") if isinstance(profile_payload.get("metadata"), Mapping) else {}
    text_parts: list[str] = []
    for key in ("target_roles", "keywords", "preferred_locations", "work_arrangements", "seniority_levels", "employment_types", "languages", "work_authorization", "sponsorship_requirement"):
        text_parts.extend(_items(preferences.get(key)))
    text_parts.extend(_items(profile_payload.get("name")))
    text_parts.extend(_items(profile_payload.get("description")))
    text_parts.extend(_items(profile_payload.get("target_direction")))
    for key in ("summary", "competencies", "skills", "languages", "recent_experience", "experience", "education", "projects", "evidence_items"):
        text_parts.extend(_items(metadata.get(key)))
    evidence: list[dict[str, Any]] = []
    for index, item in enumerate(metadata.get("evidence_items") or []):
        if not isinstance(item, Mapping):
            continue
        item_text = _text(item.get("text") or item.get("description") or item.get("label"))
        if item_text:
            evidence.append({"id": _text(item.get("evidence_id") or item.get("id")) or f"profile-evidence-{index + 1}", "text": item_text, "status": _text(item.get("state") or item.get("status")) or "unverified", "source": "profile_evidence"})
    for index, item in enumerate(metadata.get("recent_experience") or metadata.get("experience") or []):
        if isinstance(item, Mapping):
            item_text = " ".join(
                part
                for key in ("title", "role", "employer", "description", "bullets")
                for part in _items(item.get(key))
            )
            item_text = re.sub(r"\s+", " ", item_text).strip()
            evidence_id = _text(item.get("evidence_id") or item.get("id")) or f"profile-experience-{index + 1}"
        else:
            item_text = _text(item)
            evidence_id = f"profile-experience-{index + 1}"
        if item_text:
            evidence.append({"id": evidence_id, "text": item_text, "status": "unverified", "source": "profile_experience"})
    version_revision = int((preferences_record or {}).get("revision") or 0)
    profile_version_id = _text(metadata.get("profile_version_id")) or (
        f"{profile_id or 'profile'}:{_text(profile_payload.get('updated_at')) or 'unknown'}:r{version_revision}"
    )
    evidence_payload = [
        {key: item.get(key) for key in ("id", "text", "status", "source")}
        for item in evidence
    ]
    evidence_version_id = _text(metadata.get("evidence_version_id")) or hashlib.sha256(
        json.dumps(evidence_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    cv_version_id = _text(metadata.get("cv_version_id") or metadata.get("cv_hash") or metadata.get("source_cv_hash")) or profile_version_id
    return {
        "profile_id": profile_id or "unconfigured",
        "revision": version_revision,
        "version_id": profile_version_id,
        "cv_version_id": cv_version_id,
        "evidence_version_id": evidence_version_id,
        "updated_at": _text(profile_payload.get("updated_at")),
        "text": re.sub(r"\s+", " ", " ".join(text_parts)).strip(),
        "evidence": evidence,
        "preferences": preferences,
    }


def _cache_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_intelligence_cache_key(
    row: Mapping[str, Any],
    *,
    intelligence_kind: str,
    user_id: str = "",
    profile: Mapping[str, Any] | None = None,
    evaluator_version: str,
    description: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Build the complete immutable cache identity used by reads and workers."""
    profile = profile or {}
    job_version_id = _text(row.get("current_version_id"))
    base = {
        "cache_version": INTELLIGENCE_CACHE_VERSION,
        "user_id": _text(user_id) if intelligence_kind in {"match", "tailored_document"} else "",
        "canonical_job_id": _text(row.get("canonical_job_id")),
        "job_version_id": job_version_id,
        "profile_version_id": _text(profile.get("version_id")) if intelligence_kind in {"match", "tailored_document"} else "",
        "cv_version_id": _text(profile.get("cv_version_id")) if intelligence_kind in {"match", "tailored_document"} else "",
        "evidence_version_id": _text(profile.get("evidence_version_id")) if intelligence_kind in {"match", "tailored_document"} else "",
        "evaluator_version": _text(evaluator_version),
        "intelligence_kind": _text(intelligence_kind),
    }
    input_payload = {
        **base,
        "content_hash": _text(row.get("content_hash")),
        "title": _text(row.get("title")),
        "description": _text(row.get("description")),
        "profile_text": _text(profile.get("text")),
        "profile_evidence": profile.get("evidence") or [],
        "preferences": profile.get("preferences") or {},
        # Match identity must not change when a pending summary becomes
        # available.  The immutable posting version and summary evaluator
        # version are the relevant description inputs; generated payload
        # state is not.
        "description_intelligence": (
            {"prompt_version": _text((description or {}).get("prompt_version"))}
            if intelligence_kind in {"match", "tailored_document"}
            else (description or {})
        ),
    }
    base["input_hash"] = _cache_hash(input_payload)
    base["cache_id"] = _cache_hash(base)
    return base


def _requirement_result(requirement: Mapping[str, str], *, profile: Mapping[str, Any], version: str) -> tuple[bool, float, dict[str, Any] | None, str | None]:
    text = _text(requirement.get("text"))
    profile_text = _text(profile.get("text"))
    evidence = list(profile.get("evidence") or [])
    if version == "v1":
        quality = 1.0 if _phrase_match(text, profile_text) else 0.0
        evidence_match = next((item for item in evidence if _phrase_match(text, _text(item.get("text")))), None)
        matched = quality > 0
    else:
        quality = _semantic_match(text, profile_text)
        evidence_match = max(
            (
                evidence_item
                for evidence_item in evidence
                if _text(evidence_item.get("status")).casefold() in {"verified", "confirmed", "accepted"}
                and _semantic_match(text, _text(evidence_item.get("text"))) >= 0.45
            ),
            key=lambda item: _semantic_match(text, _text(item.get("text"))),
            default=None,
        )
        matched = quality >= (0.75 if len(_tokens(text)) > 2 else 0.6)
    if matched and evidence_match:
        return True, quality, {
            "requirement": text,
            "evidence_id": _text(evidence_match.get("id")),
            "evidence": _text(evidence_match.get("text")),
            "evidence_status": _text(evidence_match.get("status")) or "unverified",
            "source": _text(evidence_match.get("source")) or "profile",
        }, None
    if matched:
        return True, quality, None, text
    return False, quality, None, text


def _evaluate(
    row: Mapping[str, Any],
    intelligence: Mapping[str, Any],
    profile: Mapping[str, Any],
    *,
    version: str,
) -> dict[str, Any]:
    structured = intelligence.get("structured_description") or {}
    summary = intelligence.get("summary") or {}
    profile_text = _text(profile.get("text"))
    terms = _job_terms(structured, summary)
    matched_keywords: list[str] = []
    missing_keywords: list[str] = []
    for term in terms:
        matched = _phrase_match(term, profile_text) if version == "v1" else _semantic_match(term, profile_text) >= (0.75 if len(_tokens(term)) > 2 else 0.6)
        (matched_keywords if matched else missing_keywords).append(term)
    requirement_rows = _requirements(structured, summary)
    matched_requirements: list[str] = []
    unproven: list[str] = []
    apparent_non_matches: list[str] = []
    matched_evidence: list[dict[str, Any]] = []
    missing_evidence: list[dict[str, str]] = []
    weighted_total = 0.0
    weighted_matched = 0.0
    for requirement in requirement_rows:
        weight = 2.0 if requirement["requiredness"] == "essential" else 1.0
        weighted_total += weight
        matched, quality, evidence, unproven_text = _requirement_result(requirement, profile=profile, version=version)
        weighted_matched += weight * quality if matched else 0.0
        if matched:
            matched_requirements.append(requirement["text"])
            if evidence:
                matched_evidence.append(evidence)
            else:
                unproven.append(requirement["text"])
                missing_evidence.append({
                    "requirement": requirement["text"],
                    "reason": "No linked verified evidence supports this requirement.",
                })
        else:
            missing_keywords.append(requirement["text"])
            missing_evidence.append({
                "requirement": requirement["text"],
                "reason": "No matching profile evidence was found.",
            })
            if requirement["requiredness"] == "essential" and re.search(r"\b(must|required|need|degree|authorization|visa|fluent|native)\b", requirement["text"], re.IGNORECASE):
                apparent_non_matches.append(requirement["text"])
            elif unproven_text:
                unproven.append(unproven_text)
    keyword_total = len(terms)
    keyword_coverage = len(matched_keywords) / max(1, keyword_total)
    requirement_coverage = weighted_matched / max(1.0, weighted_total)
    evidence_coverage = len(matched_evidence) / max(1, len(requirement_rows))
    preference_fit = 0.0
    preference_checks = 0
    preferences = profile.get("preferences") or {}
    title = _text(row.get("title"))
    location = _text(row.get("location") or row.get("version_location"))
    for value, actual in ((preferences.get("target_roles"), title), (preferences.get("preferred_locations"), location)):
        wanted = _items(value)
        if wanted:
            preference_checks += 1
            if any(_phrase_match(item, actual) or _semantic_match(item, actual) >= 0.6 for item in wanted):
                preference_fit += 1.0
    preference_fit = preference_fit / max(1, preference_checks)
    if version == "v1":
        formula = {"requirement_coverage": 0.6, "keyword_coverage": 0.4}
        score = round(100 * (0.6 * requirement_coverage + 0.4 * keyword_coverage))
        explanation = "Exact keyword and explicit-requirement coverage; profile evidence is not used to raise the score."
        evaluator_version = MATCH_V1_VERSION
    else:
        formula = {"semantic_requirement_coverage": 0.45, "semantic_keyword_coverage": 0.25, "evidence_coverage": 0.2, "preference_fit": 0.1}
        semantic_keyword_coverage = sum(_semantic_match(term, profile_text) for term in terms) / max(1, keyword_total)
        score = round(100 * (0.45 * requirement_coverage + 0.25 * semantic_keyword_coverage + 0.2 * evidence_coverage + 0.1 * preference_fit))
        explanation = "Synonym-aware requirement matching plus verified profile evidence and preference fit. The final score is deterministic."
        evaluator_version = MATCH_V2_VERSION
    score = max(0, min(100, int(score)))
    all_missing = list(dict.fromkeys(missing_keywords))
    return {
        "score": score,
        "score_scale": "0-100",
        "matched_keywords": list(dict.fromkeys(matched_keywords)),
        "missing_keywords": all_missing,
        "matched_requirements": list(dict.fromkeys(matched_requirements)),
        "matched_evidence": matched_evidence,
        "missing_evidence": missing_evidence,
        "unproven_requirements": list(dict.fromkeys(unproven)),
        "apparent_non_matches": list(dict.fromkeys(apparent_non_matches)),
        "formula": formula,
        "explanation": explanation,
        "evaluator": {"name": MATCH_EVALUATOR_NAME, "version": evaluator_version},
        "profile_version": {"id": _text(profile.get("version_id")), "profile_id": _text(profile.get("profile_id")), "revision": int(profile.get("revision") or 0), "updated_at": _text(profile.get("updated_at")) or None},
        "job_version": {"canonical_job_id": _text(row.get("canonical_job_id")), "id": _text(row.get("current_version_id")), "number": int(row.get("version_number") or 0) or None, "content_hash": _text(row.get("content_hash"))},
        "status": "available" if profile_text else "needs_profile",
    }


def build_match_intelligence(row: Mapping[str, Any], intelligence: Mapping[str, Any], profile: Mapping[str, Any], *, evaluated_at: str | None = None) -> dict[str, Any]:
    v1 = _evaluate(row, intelligence, profile, version="v1")
    v2 = _evaluate(row, intelligence, profile, version="v2")
    delta = int(v2["score"]) - int(v1["score"])
    if delta > 0:
        difference = "v2 found additional semantic or evidence-aware support that exact ATS matching did not count."
    elif delta < 0:
        difference = "v2 discounted exact keyword overlap where the profile did not provide enough semantic or evidence support."
    else:
        difference = "Both evaluators reached the same score for this profile and job version."
    missing = list(dict.fromkeys(v2["missing_keywords"] + v2["unproven_requirements"]))
    suggestions = [f"Verify whether your profile can truthfully support: {item}." for item in missing[:6]]
    if not suggestions:
        suggestions = ["Keep your profile evidence current and specific to the responsibilities you can verify."]
    return {
        "state": "available",
        "v1": v1,
        "v2": v2,
        "difference": {"score_delta": delta, "summary": difference},
        "evaluator": {"name": MATCH_EVALUATOR_NAME, "versions": [MATCH_V1_VERSION, MATCH_V2_VERSION], "final_formula": "v1 exact coverage; v2 weighted semantic, evidence, and preference coverage"},
        "profile_version": v2["profile_version"],
        "job_version": v2["job_version"],
        "evaluated_at": evaluated_at or datetime.now(timezone.utc).isoformat(),
        "improve_resume": {"free_explanations": suggestions, "rewriting_available": False, "tailored_documents_available": False, "note": "Only truthful improvement explanations are available in Free match intelligence. Rewriting and tailored documents remain Runr Pro capabilities."},
    }


def build_tailored_document(row: Mapping[str, Any], profile: Mapping[str, Any], match: Mapping[str, Any]) -> dict[str, Any]:
    """Build a truthful, evidence-grounded tailored resume payload in the worker."""
    v2 = match.get("v2") if isinstance(match.get("v2"), Mapping) else {}
    evidence = [item for item in (v2.get("matched_evidence") or []) if isinstance(item, Mapping)]
    highlights = [_text(item.get("text")) for item in evidence if _text(item.get("text"))]
    return {
        "document_type": "tailored_resume",
        "state": "available",
        "label": "Generated tailored resume",
        "title": _text(row.get("title")),
        "summary": "Tailored only from matched, verified candidate evidence; review before sending.",
        "highlights": highlights[:8],
        "matched_keywords": list(v2.get("matched_keywords") or []),
        "missing_keywords": list(v2.get("missing_keywords") or []),
        "unproven_requirements": list(v2.get("unproven_requirements") or []),
        "guardrail": "Never claim unsupported experience, qualifications, authorization, salary, language, or requirements.",
        "evaluator_version": TAILORED_DOCUMENT_VERSION,
        "profile_version_id": _text(profile.get("version_id")),
        "job_version_id": _text(row.get("current_version_id")),
    }


__all__ = [
    "MATCH_EVALUATOR_NAME",
    "MATCH_V1_VERSION",
    "MATCH_V2_VERSION",
    "TAILORED_DOCUMENT_VERSION",
    "SUMMARY_PROMPT_VERSION",
    "build_description_intelligence",
    "build_preserved_original_posting",
    "build_match_intelligence",
    "build_tailored_document",
    "build_intelligence_cache_key",
    "_profile_context",
]
