from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Mapping

import requests

from backend.capabilities.tailored_documents.common import compact_whitespace, strip_json_fences


_SUMMARY_HEADER_PATTERN = re.compile(
    r"^(professional\s+summary|summary|profile|about\s+me|objective)$",
    re.IGNORECASE,
)
_SKILLS_HEADER_PATTERN = re.compile(
    r"^(skills|core\s+competencies|competencies|technical\s+skills|key\s+skills)$",
    re.IGNORECASE,
)
_EXPERIENCE_HEADER_PATTERN = re.compile(
    r"^(experience|work\s+experience|professional\s+experience|employment)$",
    re.IGNORECASE,
)
_EDUCATION_HEADER_PATTERN = re.compile(
    r"^(education|education\s+and\s+training|certifications?|training)$",
    re.IGNORECASE,
)
_LANGUAGES_HEADER_PATTERN = re.compile(
    r"^(languages|language\s+skills)$",
    re.IGNORECASE,
)
_SECTION_HEADER_PATTERN = re.compile(
    r"^(professional\s+summary|summary|profile|about\s+me|objective|"
    r"skills|core\s+competencies|competencies|technical\s+skills|key\s+skills|"
    r"experience|work\s+experience|professional\s+experience|employment|"
    r"education|education\s+and\s+training|certifications?|training|"
    r"languages|language\s+skills|projects?|publications?)$",
    re.IGNORECASE,
)
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_URL_PATTERN = re.compile(r"(https?://[^\s]+|www\.[^\s]+)", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"\+?\d[\d\s()./-]{7,}")
_DATE_TOKEN_PATTERN = re.compile(
    r"\b("
    r"(?:19|20)\d{2}|present|current|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r")\b",
    re.IGNORECASE,
)
_DEGREE_HINT_PATTERN = re.compile(
    r"\b("
    r"bachelor|master|mba|m\.?sc\.?|b\.?sc\.?|m\.?a\.?|b\.?a\.?|ph\.?d\.?|phd|"
    r"diploma|certificate|certification|apprenticeship|bootcamp|course"
    r")\b",
    re.IGNORECASE,
)
_INSTITUTION_HINT_PATTERN = re.compile(
    r"\b("
    r"university|college|school|institute|academy|hochschule|universitat|universite|polytechnic"
    r")\b",
    re.IGNORECASE,
)


def _nonempty_lines(cv_text: str) -> list[str]:
    return [compact_whitespace(line) for line in str(cv_text or "").splitlines() if compact_whitespace(line)]


def _classify_section_header(line: str) -> str | None:
    if _SUMMARY_HEADER_PATTERN.match(line):
        return "summary"
    if _SKILLS_HEADER_PATTERN.match(line):
        return "skills"
    if _EXPERIENCE_HEADER_PATTERN.match(line):
        return "experience"
    if _EDUCATION_HEADER_PATTERN.match(line):
        return "education"
    if _LANGUAGES_HEADER_PATTERN.match(line):
        return "languages"
    return None


def _collect_sections(cv_text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"_preamble": []}
    current_section = "_preamble"
    for line in _nonempty_lines(cv_text):
        detected_section = _classify_section_header(line)
        if detected_section:
            current_section = detected_section
            sections.setdefault(current_section, [])
            continue
        sections.setdefault(current_section, []).append(line)
    return sections


def _looks_like_section_header(line: str) -> bool:
    return bool(_SECTION_HEADER_PATTERN.match(compact_whitespace(line)))


def _looks_like_date_line(line: str) -> bool:
    return bool(_DATE_TOKEN_PATTERN.search(compact_whitespace(line)))


def _looks_like_contact_line(line: str) -> bool:
    text = compact_whitespace(line)
    return bool(
        _EMAIL_PATTERN.search(text)
        or _URL_PATTERN.search(text)
        or "linkedin" in text.lower()
        or "github" in text.lower()
        or _PHONE_PATTERN.search(text)
    )


def _strip_bullet_prefix(line: str) -> str:
    return re.sub(r"^\s*(?:[-*]|[•])+\s*", "", str(line or "")).strip()


def _split_inline_values(value: str) -> list[str]:
    text = compact_whitespace(value)
    if not text:
        return []
    if ":" in text and text.lower().split(":", 1)[0] in {"languages", "language skills", "skills", "competencies"}:
        text = text.split(":", 1)[1].strip()
    pieces = [item.strip(" .-") for item in re.split(r"[,;|]|(?:\s+[•]\s+)", text) if item.strip(" .-")]
    if len(pieces) <= 1:
        return [text]
    return pieces


def _dedupe_text_list(items: list[str], *, limit: int) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = compact_whitespace(item)
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(normalized)
        if len(cleaned) >= limit:
            break
    return cleaned


def _normalize_url(raw_url: str) -> str:
    url = compact_whitespace(raw_url)
    if not url:
        return ""
    if url.lower().startswith("www."):
        return f"https://{url}"
    return url


def _extract_contact_fields(lines: list[str]) -> dict[str, str]:
    email = ""
    linkedin_url = ""
    github_url = ""
    website = ""
    location = ""

    for line in lines[:12]:
        if not email:
            email_match = _EMAIL_PATTERN.search(line)
            if email_match:
                email = compact_whitespace(email_match.group(0))

        for raw_url in _URL_PATTERN.findall(line):
            url = _normalize_url(raw_url)
            lowered = url.lower()
            if "linkedin" in lowered and not linkedin_url:
                linkedin_url = url
            elif "github" in lowered and not github_url:
                github_url = url
            elif not website:
                website = url

        if location:
            continue
        if not _looks_like_contact_line(line):
            continue
        for chunk in re.split(r"[|/]|(?:\s+[•]\s+)", line):
            candidate = compact_whitespace(chunk)
            if not candidate:
                continue
            lowered = candidate.lower()
            if (
                _EMAIL_PATTERN.search(candidate)
                or _URL_PATTERN.search(candidate)
                or "linkedin" in lowered
                or "github" in lowered
                or _PHONE_PATTERN.search(candidate)
            ):
                continue
            if len(candidate) > 60 or len(candidate.split()) > 8:
                continue
            location = candidate
            break

    return {
        "email": email,
        "linkedin_url": linkedin_url,
        "github_url": github_url,
        "website": website,
        "location": location,
    }


def _parse_experience_heading(line: str) -> tuple[str, str, str]:
    text = compact_whitespace(_strip_bullet_prefix(line))
    if not text:
        return "", "", ""

    pipe_parts = [part.strip() for part in text.split("|") if part.strip()]
    if len(pipe_parts) >= 3 and _looks_like_date_line(pipe_parts[-1]):
        return pipe_parts[0], pipe_parts[1], pipe_parts[-1]
    if len(pipe_parts) >= 2:
        return pipe_parts[0], pipe_parts[1], ""

    dash_parts = [part.strip() for part in re.split(r"\s[-–—]\s", text) if part.strip()]
    if len(dash_parts) >= 3 and _looks_like_date_line(dash_parts[-1]):
        return dash_parts[0], " - ".join(dash_parts[1:-1]), dash_parts[-1]
    if len(dash_parts) >= 2 and _looks_like_date_line(dash_parts[-1]):
        return dash_parts[0], "", dash_parts[-1]

    lowered = text.lower()
    marker = " at "
    if marker in lowered:
        marker_index = lowered.find(marker)
        return text[:marker_index].strip(), text[marker_index + len(marker) :].strip(), ""

    return text, "", ""


def _looks_like_experience_heading(line: str, next_line: str = "") -> bool:
    text = compact_whitespace(line)
    if not text or _looks_like_section_header(text):
        return False
    if text.startswith(("-", "*", "•")) or len(text) > 110:
        return False
    if "|" in text or " at " in text.lower():
        return True
    return bool(next_line and _looks_like_date_line(next_line))


def _extract_recent_experience(lines: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def flush_current() -> None:
        nonlocal current
        if current is None:
            return
        title = compact_whitespace(str(current.get("title") or current.get("role") or ""))
        company = compact_whitespace(str(current.get("company") or ""))
        period = compact_whitespace(str(current.get("period") or ""))
        bullets = _dedupe_text_list(
            [compact_whitespace(item) for item in current.get("bullets") or []],
            limit=6,
        )
        if title or company or period or bullets:
            entries.append(
                {
                    "title": title,
                    "role": title,
                    "company": company,
                    "period": period,
                    "bullets": bullets,
                    "bulletsText": "\n".join(bullets),
                }
            )
        current = None

    for index, raw_line in enumerate(lines[:80]):
        line = compact_whitespace(raw_line)
        if not line:
            continue
        next_line = compact_whitespace(lines[index + 1]) if index + 1 < len(lines) else ""
        normalized_bullet = _strip_bullet_prefix(line)

        if current is None:
            if not _looks_like_experience_heading(line, next_line):
                continue
            title, company, period = _parse_experience_heading(line)
            current = {
                "title": title,
                "role": title,
                "company": company,
                "period": period,
                "bullets": [],
            }
            continue

        if _looks_like_experience_heading(line, next_line):
            flush_current()
            title, company, period = _parse_experience_heading(line)
            current = {
                "title": title,
                "role": title,
                "company": company,
                "period": period,
                "bullets": [],
            }
            continue

        if not current.get("period") and _looks_like_date_line(line) and len(line) <= 40:
            current["period"] = line
            continue

        if line.startswith(("-", "*", "•")):
            if normalized_bullet:
                current.setdefault("bullets", []).append(normalized_bullet)
            continue

        if not current.get("company") and len(line) <= 80 and not _looks_like_date_line(line):
            current["company"] = line
            continue

        if current.get("bullets"):
            current["bullets"][-1] = compact_whitespace(f"{current['bullets'][-1]} {line}")
            continue

        current.setdefault("bullets", []).append(line)

    flush_current()
    return entries[:8]


def _looks_like_education_heading(line: str) -> bool:
    text = compact_whitespace(line)
    if not text or _looks_like_section_header(text):
        return False
    if text.startswith(("-", "*", "•")) or len(text) > 120:
        return False
    return bool("|" in text or _DEGREE_HINT_PATTERN.search(text) or _INSTITUTION_HINT_PATTERN.search(text))


def _parse_education_heading(line: str) -> tuple[str, str, str]:
    text = compact_whitespace(_strip_bullet_prefix(line))
    if not text:
        return "", "", ""

    pipe_parts = [part.strip() for part in text.split("|") if part.strip()]
    if len(pipe_parts) >= 3 and _looks_like_date_line(pipe_parts[-1]):
        return pipe_parts[0], pipe_parts[1], pipe_parts[-1]
    if len(pipe_parts) >= 2:
        return pipe_parts[0], pipe_parts[1], ""

    dash_parts = [part.strip() for part in re.split(r"\s[-–—]\s", text) if part.strip()]
    if len(dash_parts) >= 3 and _looks_like_date_line(dash_parts[-1]):
        return dash_parts[0], " - ".join(dash_parts[1:-1]), dash_parts[-1]

    return text, "", ""


def _extract_education(lines: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def flush_current() -> None:
        nonlocal current
        if current is None:
            return
        degree_title = compact_whitespace(str(current.get("degree_title") or ""))
        institution = compact_whitespace(str(current.get("institution") or ""))
        period = compact_whitespace(str(current.get("period") or ""))
        details = _dedupe_text_list(
            [compact_whitespace(item) for item in current.get("details") or []],
            limit=6,
        )
        if degree_title or institution or period or details:
            items.append(
                {
                    "degree_title": degree_title,
                    "institution": institution,
                    "period": period,
                    "details": details,
                    "detailsText": "\n".join(details),
                }
            )
        current = None

    for raw_line in lines[:60]:
        line = compact_whitespace(raw_line)
        if not line:
            continue

        if current is None:
            degree_title, institution, period = _parse_education_heading(line)
            current = {
                "degree_title": degree_title,
                "institution": institution,
                "period": period,
                "details": [],
            }
            continue

        if _looks_like_education_heading(line) and current.get("degree_title"):
            flush_current()
            degree_title, institution, period = _parse_education_heading(line)
            current = {
                "degree_title": degree_title,
                "institution": institution,
                "period": period,
                "details": [],
            }
            continue

        if not current.get("period") and _looks_like_date_line(line):
            current["period"] = line
            continue

        if not current.get("institution") and _INSTITUTION_HINT_PATTERN.search(line):
            current["institution"] = line
            continue

        current.setdefault("details", []).append(_strip_bullet_prefix(line))

    flush_current()
    return items[:6]


def _normalize_string_list(raw_value: Any, *, limit: int) -> list[str]:
    values: list[str] = []
    if isinstance(raw_value, list):
        for item in raw_value:
            if isinstance(item, str):
                values.extend(_split_inline_values(item))
    elif isinstance(raw_value, str):
        values.extend(_split_inline_values(raw_value))
    return _dedupe_text_list(values, limit=limit)


def _normalize_multiline_notes(raw_value: Any, *, limit: int) -> list[str]:
    if isinstance(raw_value, list):
        return _dedupe_text_list(
            [_strip_bullet_prefix(str(item or "")) for item in raw_value if compact_whitespace(str(item or ""))],
            limit=limit,
        )
    if not isinstance(raw_value, str):
        return []
    return _dedupe_text_list(
        [
            _strip_bullet_prefix(line)
            for line in str(raw_value).splitlines()
            if compact_whitespace(_strip_bullet_prefix(line))
        ],
        limit=limit,
    )


def _normalize_experience_list(raw_value: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not isinstance(raw_value, list):
        return entries
    for item in raw_value:
        if not isinstance(item, Mapping):
            continue
        title = compact_whitespace(str(item.get("title") or item.get("role") or item.get("role_title") or ""))
        company = compact_whitespace(str(item.get("company") or ""))
        period = compact_whitespace(str(item.get("period") or ""))
        bullets = _normalize_multiline_notes(item.get("bullets"), limit=6)
        if not bullets:
            bullets = _normalize_multiline_notes(item.get("bulletsText") or "", limit=6)
        if title or company or period or bullets:
            entries.append(
                {
                    "title": title,
                    "role": title,
                    "company": company,
                    "period": period,
                    "bullets": bullets,
                    "bulletsText": "\n".join(bullets),
                }
            )
    return entries[:8]


def _normalize_education_list(raw_value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not isinstance(raw_value, list):
        return items
    for item in raw_value:
        if isinstance(item, str):
            degree_title = compact_whitespace(item)
            if degree_title:
                items.append(
                    {
                        "degree_title": degree_title,
                        "institution": "",
                        "period": "",
                        "details": [],
                        "detailsText": "",
                    }
                )
            continue
        if not isinstance(item, Mapping):
            continue
        degree_title = compact_whitespace(
            str(item.get("degree_title") or item.get("degree") or item.get("title") or "")
        )
        institution = compact_whitespace(str(item.get("institution") or item.get("school") or ""))
        period = compact_whitespace(str(item.get("period") or ""))
        details = _normalize_multiline_notes(item.get("details"), limit=6)
        if not details:
            details = _normalize_multiline_notes(item.get("thesis_bullets"), limit=6)
        thesis_title = compact_whitespace(str(item.get("thesis_title") or ""))
        if thesis_title:
            details = _dedupe_text_list([thesis_title, *details], limit=6)
        if not details:
            details = _normalize_multiline_notes(item.get("detailsText") or "", limit=6)
        if degree_title or institution or period or details:
            items.append(
                {
                    "degree_title": degree_title,
                    "institution": institution,
                    "period": period,
                    "details": details,
                    "detailsText": "\n".join(details),
                }
            )
    return items[:6]


def normalize_profile_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    return {
        "name": compact_whitespace(str(raw.get("name") or "")),
        "role_title": compact_whitespace(str(raw.get("role_title") or raw.get("headline") or "")),
        "email": compact_whitespace(str(raw.get("email") or "")),
        "location": compact_whitespace(str(raw.get("location") or "")),
        "website": _normalize_url(str(raw.get("website") or "")),
        "linkedin_url": _normalize_url(str(raw.get("linkedin_url") or raw.get("linkedin") or "")),
        "github_url": _normalize_url(str(raw.get("github_url") or raw.get("github") or "")),
        "summary": compact_whitespace(str(raw.get("summary") or "")),
        "competencies": _normalize_string_list(raw.get("competencies") or raw.get("skills") or [], limit=25),
        "languages": _normalize_string_list(raw.get("languages") or [], limit=15),
        "recent_experience": _normalize_experience_list(raw.get("recent_experience") or raw.get("experience") or []),
        "education": _normalize_education_list(raw.get("education") or []),
    }


def extract_cv_profile_fallback(cv_text: str) -> dict[str, Any]:
    sections = _collect_sections(cv_text)
    preamble_lines = list(sections.get("_preamble") or [])
    display_lines = [line for line in preamble_lines if not _looks_like_contact_line(line)]
    contact_fields = _extract_contact_fields(preamble_lines)

    summary = " ".join(sections.get("summary") or [])[:900].strip()
    if not summary and len(display_lines) > 2:
        summary = " ".join(display_lines[2:5]).strip()

    profile = {
        "name": display_lines[0] if display_lines else "",
        "role_title": display_lines[1] if len(display_lines) > 1 else "",
        "email": contact_fields["email"],
        "location": contact_fields["location"],
        "website": contact_fields["website"],
        "linkedin_url": contact_fields["linkedin_url"],
        "github_url": contact_fields["github_url"],
        "summary": summary,
        "competencies": _normalize_string_list(sections.get("skills") or [], limit=25),
        "languages": _normalize_string_list(sections.get("languages") or [], limit=15),
        "recent_experience": _extract_recent_experience(sections.get("experience") or []),
        "education": _extract_education(sections.get("education") or []),
    }
    return normalize_profile_payload(profile)


def _profile_extraction_schema() -> dict[str, Any]:
    return {
        "name": "text",
        "role_title": "text",
        "email": "text",
        "location": "text",
        "website": "text",
        "linkedin_url": "text",
        "github_url": "text",
        "summary": "text",
        "competencies": ["text"],
        "languages": ["text"],
        "recent_experience": [
            {
                "title": "text",
                "company": "text",
                "period": "text",
                "bullets": ["text"],
            }
        ],
        "education": [
            {
                "degree_title": "text",
                "institution": "text",
                "period": "text",
                "details": ["text"],
            }
        ],
    }


def _call_deepseek_profile_extraction(
    *,
    cv_text: str,
    api_key: str,
    model: str,
    timeout_seconds: int = 45,
) -> dict[str, Any]:
    prompt = f"""
Extract the candidate profile from this CV into JSON for direct UI population.

Return only a valid JSON object.
Do not wrap the response in markdown.
Do not invent facts not present in the CV.
If a field is unknown, return an empty string or an empty array.
Keep experience and education ordering as they appear in the CV.
Keep language proficiency values exactly when they are present.
Keep bullets factual and concise.

Required schema:
{json.dumps(_profile_extraction_schema(), indent=2, ensure_ascii=False)}

CV:
{cv_text[:18000]}
""".strip()

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You extract factual CV data into strict JSON for form population. "
                    "Return valid JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    session = requests.Session()
    session.trust_env = False
    response = session.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    body = response.json()
    choices = body.get("choices") or []
    if not choices:
        raise ValueError("DeepSeek response missing choices.")
    message = choices[0].get("message") or {}
    content = str(message.get("content") or "").strip()
    if not content:
        raise ValueError("DeepSeek response content is empty.")
    parsed = json.loads(strip_json_fences(content))
    if not isinstance(parsed, dict):
        raise ValueError("DeepSeek response must be a JSON object.")
    return normalize_profile_payload(parsed)


def extract_cv_profile(
    cv_text: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    normalized_text = str(cv_text or "").strip()
    resolved_api_key = str(api_key or os.getenv("DEEPSEEK_API_KEY") or "").strip()
    resolved_model = str(model or os.getenv("DEEPSEEK_CV_PROFILE_MODEL") or "deepseek-chat").strip()
    warnings: list[str] = []

    if resolved_api_key and normalized_text:
        try:
            return {
                "profile": _call_deepseek_profile_extraction(
                    cv_text=normalized_text,
                    api_key=resolved_api_key,
                    model=resolved_model,
                ),
                "provider": "deepseek",
                "model": resolved_model,
                "warnings": warnings,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            warnings.append(f"deepseek_failed:{compact_whitespace(str(exc))}")

    provider = "heuristic_fallback"
    if not resolved_api_key:
        warnings.append("deepseek_api_key_missing")
    return {
        "profile": extract_cv_profile_fallback(normalized_text),
        "provider": provider,
        "model": resolved_model,
        "warnings": warnings,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }


__all__ = [
    "extract_cv_profile",
    "extract_cv_profile_fallback",
    "normalize_profile_payload",
]
