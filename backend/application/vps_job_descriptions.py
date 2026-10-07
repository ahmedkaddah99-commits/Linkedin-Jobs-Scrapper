"""Shared posting-version descriptions generated on the acquisition VPS."""

from __future__ import annotations

import json
import math
import os
import re
from html import unescape
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from collections.abc import Callable, Mapping
from typing import Any

from backend.application.personalized_jobs_intelligence import build_preserved_original_posting


PROMPT_VERSION = "runr_description_v1"
PILOT_PROMPT_VERSION = "runr_description_nemo_v2"
GROUNDED_PROMPT_VERSION = "runr_description_nemo_v3"
NEMO_MODEL = "mistralai/mistral-nemo"
OUTPUT_LANGUAGE = "en"
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"


class RateLimitError(RuntimeError):
    """Stop the current free-tier batch when OpenRouter has no capacity."""
SECTIONS = (
    "responsibilities", "required_qualifications", "preferred_qualifications",
    "benefits", "application_details",
)

PILOT_ARRANGEMENTS = {"onsite", "hybrid", "remote"}
PILOT_EMPLOYMENT = {"full_time", "part_time", "contract", "temporary", "internship", "apprenticeship"}
PILOT_SENIORITY = {"entry", "mid", "senior", "lead", "director", "executive"}

PILOT_HEADINGS = {
    "responsibilities": {"responsibilities", "job responsibilities", "your responsibilities", "your tasks", "key duties", "key responsibilities", "main responsibilities", "what you will do", "what you'll work on", "your role", "role description"},
    "required_qualifications": {"qualifications", "job qualifications", "requirements", "required", "required qualifications", "minimum qualifications", "basic qualifications", "additional requirements", "what we are looking for", "the successful candidate will", "what you bring along", "must-have skills", "you have", "must have", "skills"},
    "preferred_qualifications": {"preferred", "preferred qualifications", "preferred additional skills", "nice to have", "nice-to-have skills", "nice if you have", "good to have"},
    "benefits": {"benefits", "what we offer", "we offer", "what we have to offer", "our benefits", "compensation"},
    "application_details": {"how to apply", "application process"},
}
PILOT_OTHER_HEADINGS = {"about us", "company description", "project description", "job description", "equal opportunity", "why join us", "what will help you succeed", "person specification", "hiscox values", "application deadline", "information about our talent acquisition process", "identity statement", "candidate ai usage policy", "work model", "commitment to non-discrimination", "what we value", "your way to us"}
PILOT_BENEFIT_SUBHEADINGS = {"professional & personal growth", "rofessional & personal growth", "flexible work-life balance", "embrace diversity & sustainability", "comprehensive benefits"}
PILOT_YEAR_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
PILOT_YEAR_NUMBER = r"(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
PILOT_YEAR_PATTERN = re.compile(rf"\b({PILOT_YEAR_NUMBER})(?:\s*[-–]\s*({PILOT_YEAR_NUMBER}))?\s*\+?\s*years?\b", re.IGNORECASE)


def _supported_experience_years(text: str) -> set[float]:
    """Return years explicitly tied to experience in one short source passage."""
    if not re.search(r"\bexperience\b", text, re.IGNORECASE):
        return set()
    values: set[float] = set()
    for match in PILOT_YEAR_PATTERN.finditer(text):
        for raw in match.groups():
            if raw:
                values.add(float(PILOT_YEAR_WORDS.get(raw.lower(), raw) if not raw.isdigit() else raw))
    return values


def _ambiguous_experience_years(text: str) -> bool:
    return bool(re.search(r"\bor\b", text, re.IGNORECASE) and len(list(PILOT_YEAR_PATTERN.finditer(text))) > 1)


def _validate_experience_sources(result: dict[str, Any]) -> None:
    structured = result["structured_description"]
    passages = structured["source_passages"]
    by_id = {passage["id"]: passage["text"] for passage in passages}
    for field in ("experience_years_min", "experience_years_max"):
        candidate = structured.get(field)
        if not isinstance(candidate, dict):
            continue
        value = float(candidate["value"])
        cited = " ".join(by_id.get(source_id, "") for source_id in candidate["source_ids"])
        cited_years = _supported_experience_years(cited)
        if value in cited_years and not _ambiguous_experience_years(cited):
            continue
        contexts = []
        for index, passage in enumerate(passages):
            ids = [passage["id"]]
            text = passage["text"]
            if PILOT_YEAR_PATTERN.search(text) and not re.search(r"\bexperience\b", text, re.IGNORECASE) and index + 1 < len(passages):
                ids.append(passages[index + 1]["id"])
                text += " " + passages[index + 1]["text"]
            if value in _supported_experience_years(text):
                contexts.append((ids, text))
        anchors = contexts
        if len(anchors) == 1:
            ids, text = anchors[0]
            if not _ambiguous_experience_years(text):
                candidate["source_ids"] = ids
                candidate["method"] = "source_reanchored"
                continue
        structured[field] = None
        structured["rejected_fields"].append(f"{field}:unsupported_or_ambiguous_source")


def supplement_explicit_sections(result: dict[str, Any]) -> dict[str, Any]:
    """Use exact English source items if Nemo omitted a whole labeled section."""
    _validate_experience_sources(result)
    summary = result["summary"]
    corrected_required = []
    for item in summary["required_qualifications"]:
        wording = item["text"]
        mixed = re.match(r"^(.+?),\s*((?:additional|any other) .+? (?:is|will be) a plus\.?$)", wording, re.IGNORECASE)
        degree = re.match(r"^(.+?degree required)\s*\((.+?) preferred\)\.?$", wording, re.IGNORECASE)
        ideal = re.match(r"^(.+?),\s*ideally with\s+(.+?)(?:\.\s+(.+))?$", wording, re.IGNORECASE)
        if mixed:
            corrected_required.append({**item, "text": mixed.group(1).strip() + "."})
            summary["preferred_qualifications"].append({**item, "text": mixed.group(2).strip()})
        elif degree:
            corrected_required.append({**item, "text": degree.group(1).strip() + "."})
            summary["preferred_qualifications"].append({**item, "text": "Degree in " + degree.group(2).strip() + " preferred."})
        elif ideal:
            corrected_required.append({**item, "text": ideal.group(1).strip() + "."})
            if ideal.group(3):
                summary["preferred_qualifications"].append({**item, "text": ideal.group(3).strip()})
            summary["preferred_qualifications"].append({**item, "text": "Ideally, experience with " + ideal.group(2).strip().rstrip(".") + "."})
        elif re.search(r"\bpreferred\b|\bnice to have\b|\bis a plus\b|\bwill also be considered\b", wording, re.IGNORECASE) and not re.search(r"\brequired\b", wording, re.IGNORECASE):
            summary["preferred_qualifications"].append(item)
        else:
            corrected_required.append(item)
    summary["required_qualifications"] = corrected_required
    passages = result["structured_description"]["source_passages"]
    found: dict[str, list[dict[str, Any]]] = {section: [] for section in SECTIONS}
    current: str | None = None
    for passage in passages:
        wording = re.sub(r"^\s*[*•-]\s*", "", passage["text"]).strip()
        if len(wording) < 2 or wording == ":":
            continue
        heading = wording.lower().strip(": ?* \t")
        matched = next((section for section, names in PILOT_HEADINGS.items() if heading in names), None)
        if matched is None and re.fullmatch(r"as a .+ you will", heading):
            matched = "responsibilities"
        if matched is None and re.fullmatch(r"what .+ offers", heading):
            matched = "benefits"
        if matched:
            current = matched
            continue
        inline = re.match(r"^(?:(?:qualifications|requirements)\s+)?(?:education|skills|experience(?=\s+\d))\s+(.+)$", wording, re.IGNORECASE)
        if not inline:
            inline = re.match(r"^Qualifications\s+Required Knowledge, Skills, and Experience:\s*(.+)$", wording, re.IGNORECASE)
        if inline:
            current = "required_qualifications"
            wording = inline.group(1).strip()
        if (heading in PILOT_OTHER_HEADINGS or heading.startswith("why join ") or wording.startswith("*All Telecommuters")
                or wording.startswith("This position is based") or heading.startswith("additional information ")
                or heading.startswith("more information about ")
                or re.search(r"equal opportunity employer|e-verify employer|drug-free workplace|by submitting your resume", heading)
                or (wording.endswith(":") and len(wording) < 90 and not (current == "benefits" and heading in PILOT_BENEFIT_SUBHEADINGS))):
            current = None
            continue
        if current == "benefits" and heading in PILOT_BENEFIT_SUBHEADINGS:
            continue
        if current and wording and not wording.startswith("#"):
            def add(section: str, text: str) -> None:
                previous = found[section][-1] if found[section] else None
                if previous and text[0].islower() and not previous["text"].endswith(".") and (text.startswith("and ") or len(text.split()) <= 3):
                    previous["text"] += " " + text
                    previous["source_ids"].append(passage["id"])
                else:
                    found[section].append({"text": text, "source_ids": [passage["id"]], "method": "source_boundary_fallback"})

            split_preferred = re.match(r"^(.+?);\s*(.+?\s+is preferred)\.?$", wording, re.IGNORECASE)
            split_ideal = re.match(r"^(.+?)\s+and ideally\s+(in|within|with)\s+(.+?)\.?$", wording, re.IGNORECASE)
            split_preferably = re.match(r"^(.+?),?\s+preferably\s+(in|within|with)\s+(.+?)\.?$", wording, re.IGNORECASE)
            if current == "required_qualifications" and split_preferred:
                add(current, split_preferred.group(1).strip())
                add("preferred_qualifications", split_preferred.group(2).strip() + ".")
                continue
            if current == "required_qualifications" and (split_ideal or split_preferably):
                match = split_ideal or split_preferably
                add(current, match.group(1).strip())
                add("preferred_qualifications", f"Experience {match.group(2)} {match.group(3).strip()} is preferred.")
                continue
            section = "preferred_qualifications" if current == "required_qualifications" and re.search(r"\bpreferred\b|\bhighly desirable\b|\bnice to have\b", wording, re.IGNORECASE) else current
            mixed_preference = re.match(r"^(.+?),\s*preferably\s+(.+?)\.\s*(.+)$", wording, re.IGNORECASE)
            if current == "required_qualifications" and mixed_preference:
                found[current].append({"text": mixed_preference.group(1).strip() + ".", "source_ids": [passage["id"]], "method": "source_boundary_fallback"})
                found["preferred_qualifications"].append({"text": "Experience " + mixed_preference.group(2).strip() + " is preferred.", "source_ids": [passage["id"]], "method": "source_boundary_fallback"})
                found[current].append({"text": mixed_preference.group(3).strip(), "source_ids": [passage["id"]], "method": "source_boundary_fallback"})
            else:
                add(section, wording)
    supplemented = []
    for section in SECTIONS:
        if found[section] and (not summary[section] or all(item.get("method") == "source_boundary_fallback" for item in summary[section])):
            summary[section] = found[section]
            supplemented.append(section)
    if not summary["benefits"]:
        for passage in passages:
            match = re.search(r"\bwe offer benefits such as,?\s*(.+)", passage["text"], re.IGNORECASE)
            if match:
                wording = re.sub(r"\s*\(all benefits.*", "", match.group(1), flags=re.IGNORECASE).strip(" .")
                if wording:
                    summary["benefits"] = [{"text": wording + ".", "source_ids": [passage["id"]], "method": "source_boundary_fallback"}]
                    supplemented.append("benefits")
                    break
    if result["structured_description"].get("salary") is None:
        for passage in passages:
            wording = passage["text"]
            amounts = re.search(r"([$€£])\s*([\d,]+(?:\.\d+)?)\s*(?:to|[-–])\s*\1\s*([\d,]+(?:\.\d+)?)", wording, re.IGNORECASE)
            period_match = re.search(r"\b(?:per\s+)?(hour|day|week|month|year)\b|\b(hourly|daily|weekly|monthly|annually|annual)\b", wording, re.IGNORECASE)
            if not amounts or not period_match:
                continue
            period = (period_match.group(1) or period_match.group(2)).lower()
            period = {"hourly": "hour", "daily": "day", "weekly": "week", "monthly": "month", "annually": "year", "annual": "year"}.get(period, period)
            value = {"min": float(amounts.group(2).replace(",", "")), "max": float(amounts.group(3).replace(",", "")),
                     "currency": {"$": "USD", "€": "EUR", "£": "GBP"}[amounts.group(1)], "period": period}
            if _pilot_salary(value):
                result["structured_description"]["salary"] = {"value": value, "source_ids": [passage["id"]], "method": "source_boundary_fallback"}
                break
    result["structured_description"]["supplemented_sections"] = supplemented
    return result


def pilot_passages(source: str) -> list[dict[str, str]]:
    """Split visible source boundaries without assigning meaning to headings."""
    from html import unescape

    source = unescape(source).replace("\r", "")
    source = re.sub(r"(?i)<br\s*/?>|</(?:p|li|div|h[1-6])>", "\n", source)
    source = re.sub(r"<[^>]+>", " ", source)
    source = re.sub(r"[•●▪]\s*", "\n", source)
    pieces: list[str] = []
    for line in source.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        # Only split very long flattened blocks at sentence boundaries.
        chunks = re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])", line) if len(line) > 450 else [line]
        pieces.extend(chunk.strip() for chunk in chunks if chunk.strip())
    return [{"id": f"p{i}", "text": piece} for i, piece in enumerate(pieces, 1)]


def _pilot_ids(value: Any, lookup: Mapping[str, str]) -> list[str] | None:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or item not in lookup for item in value):
        return None
    return list(dict.fromkeys(value))


def _pilot_number(value: Any) -> int | float | None:
    # Model output must be a JSON number; numeric strings are deliberately rejected.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 60:
        return None
    return value


def _pilot_salary(value: Any) -> bool:
    if not isinstance(value, Mapping) or value.get("period") not in {"hour", "day", "week", "month", "year"}:
        return False
    currency = value.get("currency")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        return False
    bounds = [value.get("min"), value.get("max")]
    if not any(bound is not None for bound in bounds):
        return False
    if any(bound is not None and (isinstance(bound, bool) or not isinstance(bound, (int, float)) or not math.isfinite(bound) or bound < 0) for bound in bounds):
        return False
    return bounds[0] is None or bounds[1] is None or bounds[0] <= bounds[1]


def build_pilot_description(
    row: Mapping[str, Any], generate: Callable[[str], Mapping[str, Any]],
    *, require_source_quotes: bool = False,
) -> dict[str, Any]:
    """Extract one posting; reject bad fields without retrying the whole job."""
    original = build_preserved_original_posting(row)
    source = str(original.get("description_text") or original.get("description") or "").strip()
    passages = pilot_passages(source)
    if not passages:
        raise ValueError("posting description is empty")
    lookup = {entry["id"]: entry["text"] for entry in passages}
    prompt_passages = passages
    if row.get('_translate_before_nemo'):
        from backend.application.description_translation import english_passages
        prompt_passages = english_passages(passages)
    prompt = (
        "Read this ONE employer job posting. Write the extracted facts in English. "
        "When original_text is provided, text is the English translation; extract from text but quote original_text for source_quote. "
        "Keep source IDs tied to the original passages, including German source text. "
        "Return one JSON object only with keys items and header_candidates. "
        "Follow this shape exactly: {\"items\":[{\"section\":\"responsibilities\",\"text\":\"One fact\",\"source_ids\":[\"p1\"]}],"
        "\"header_candidates\":{\"location\":null,\"work_arrangement\":{\"value\":\"remote\",\"source_ids\":[\"p2\"]},"
        "\"employment_type\":null,\"seniority\":null,\"experience_years_min\":{\"value\":1,\"source_ids\":[\"p3\"]},"
        "\"experience_years_max\":null,\"salary\":null}}. "
        "Repeat section in EVERY item, including consecutive items in the same section. "
        "Every non-null header candidate must be an object with value and nonempty source_ids. "
        "items is an array of short independently readable facts, each with section, text, source_ids. "
        "Allowed sections: responsibilities, required_qualifications, preferred_qualifications, benefits, application_details. "
        "A source ID may support multiple facts and sections. Do not invent or omit job facts. Ignore employer advertising and boilerplate. "
        "Qualifications in a profile/requirements section without preference wording are required. "
        "Preferred, ideally, nice to have, advantage, and 'we would like' make the associated item or following list preferred until context changes. "
        "Separate mixed required and preferred qualifications. Preserve numbers, licences, languages, conditions, and salary units. "
        "header_candidates has keys location, work_arrangement, employment_type, seniority, experience_years_min, experience_years_max, salary. "
        "Each candidate is null when absent, otherwise an object with value and source_ids. "
        "work_arrangement value is onsite, hybrid, or remote. employment_type value is full_time, part_time, contract, temporary, internship, or apprenticeship. "
        "seniority value is entry, mid, senior, lead, director, or executive. Do not infer seniority from years or title alone. "
        "experience_years_min and experience_years_max values must be JSON numbers, never strings. An unstated bound is null. "
        "For experience_years_min use the highest minimum across separate mandatory experience requirements, including different bullet points. "
        "Do not select preferred years, add years together, or confuse the upper end of a range with its required minimum. "
        "Explicit alternative qualification paths remain alternatives; use the lowest qualifying path minimum and preserve both paths in qualifications. "
        "salary value is an object with min, max (JSON numbers or null), currency (ISO code), and period (hour, day, week, month, year). "
        "If salary currency or period is unstated, return null. Use null for unsupported facts. "
        "Posting: " + json.dumps({"title": str(row.get("title") or ""), "passages": prompt_passages}, ensure_ascii=False)
    )
    if require_source_quotes:
        prompt = re.sub(r'("source_ids":\["p[123]"\])',
                        r'\1,"source_quote":"Verbatim original source excerpt"', prompt)
        prompt = ("MANDATORY: include source_quote in EVERY item and non-null header candidate. "
                  "Copy a contiguous excerpt verbatim from the original passage; never translate the quotation, "
                  "insert ellipses or combine separated excerpts. " + prompt)
        prompt = prompt.replace("Posting: ",
            "Every item and every non-null header candidate MUST include source_quote: an exact nonempty quotation "
            "from its cited original passage. Translate only the stated meaning. A source ID alone is insufficient evidence. "
            "Do not derive duties or requirements from the title, company name or knowledge of an occupation. "
            "If the text only names the employer or contains no actual job facts, return items=[] and null headers. Posting: ")
    response = generate(prompt)
    if not isinstance(response, Mapping) or not isinstance(response.get("items"), list):
        raise ValueError("model response missing items array")
    summary: dict[str, Any] = {section: [] for section in SECTIONS}
    rejected: list[str] = []
    for item in response["items"]:
        if not isinstance(item, Mapping):
            rejected.append("invalid_item")
            continue
        section = item.get("section")
        ids = _pilot_ids(item.get("source_ids"), lookup)
        wording = item.get("text")
        if section not in SECTIONS or not ids or not isinstance(wording, str) or not wording.strip():
            rejected.append("invalid_item")
            continue
        quote = item.get("source_quote")
        if require_source_quotes and (not isinstance(quote, str) or not quote.strip()
                or not any(" ".join(quote.split()) in " ".join(lookup[i].split()) for i in ids)):
            rejected.append("invalid_source_quote")
            continue
        fact = {"text": wording.strip(), "source_ids": ids}
        if require_source_quotes:
            fact["source_quote"] = quote.strip()
        summary[section].append(fact)
    candidates = response.get("header_candidates")
    if not isinstance(candidates, Mapping):
        candidates = {}
        rejected.append("missing_header_candidates")
    structured: dict[str, Any] = {"source_passages": passages, "rejected_fields": rejected}
    if row.get('_translate_before_nemo'):
        structured['translation_pipeline'] = 'argos_english_v1'
        structured['english_source_passages'] = prompt_passages
    for field in ("location", "work_arrangement", "employment_type", "seniority", "experience_years_min", "experience_years_max", "salary"):
        raw = candidates.get(field)
        structured[field] = None
        if raw is None:
            continue
        if not isinstance(raw, Mapping) or not _pilot_ids(raw.get("source_ids"), lookup):
            rejected.append(f"{field}:missing_source")
            continue
        if require_source_quotes:
            quote = raw.get("source_quote")
            ids = _pilot_ids(raw.get("source_ids"), lookup)
            if not isinstance(quote, str) or not quote.strip() or not any(
                    " ".join(quote.split()) in " ".join(lookup[i].split()) for i in ids):
                rejected.append(f"{field}:invalid_source_quote")
                continue
        value = raw.get("value")
        if field == "location":
            valid = isinstance(value, str) and bool(value.strip()) and value.strip().lower() not in {"remote", "hybrid", "onsite", "on-site"}
        elif field == "work_arrangement":
            valid = isinstance(value, str) and value in PILOT_ARRANGEMENTS
        elif field == "employment_type":
            valid = isinstance(value, str) and value in PILOT_EMPLOYMENT
        elif field == "seniority":
            valid = isinstance(value, str) and value in PILOT_SENIORITY
        elif field.startswith("experience_years_"):
            valid = _pilot_number(value) is not None
        else:
            valid = _pilot_salary(value)
        if valid:
            structured[field] = {"value": value, "source_ids": _pilot_ids(raw["source_ids"], lookup)}
        else:
            rejected.append(f"{field}:invalid_output")
    result = {
        "version_id": str(row.get("current_version_id") or ""),
        "canonical_job_id": str(row.get("canonical_job_id") or ""),
        "content_hash": str(row.get("content_hash") or ""),
        "summary": summary,
        "structured_description": structured,
        "original_posting": original,
        "provider": "openrouter",
        "model": str(response.get("_runr_model") or NEMO_MODEL),
        "prompt_version": GROUNDED_PROMPT_VERSION if require_source_quotes else PILOT_PROMPT_VERSION,
    }
    if row.get('_translate_before_nemo'):
        # Apply English-only experience validation and section boundaries to the
        # translation, retaining the original passage IDs and original text.
        structured['source_passages'] = prompt_passages
        try:
            result = supplement_explicit_sections(result)
        finally:
            structured['source_passages'] = passages
        from backend.application.description_translation import source_language
        rendered = ' '.join(item['text'] for section in SECTIONS for item in result['summary'][section])
        if len(rendered) >= 80 and source_language(rendered) != 'en':
            raise ValueError('description_output_not_english')
        return result
    return supplement_explicit_sections(result)



_RULE_HEADINGS = {
    "responsibilities": {
        "responsibilities", "your responsibilities", "what you will do", "your tasks", "duties",
        "aufgaben", "deine aufgaben", "ihre aufgaben", "tätigkeiten", "verantwortlichkeiten",
        "responsabilités", "missions", "responsabilidades", "funciones", "responsabilità", "mansioni",
    },
    "required_qualifications": {
        "requirements", "required qualifications", "must have", "what you need",
        "anforderungen", "voraussetzungen", "das bringst du mit", "das bringen sie mit",
        "exigences", "prérequis", "requisitos", "requisitos obligatorios", "requisiti", "requisiti richiesti",
    },
    "preferred_qualifications": {
        "preferred qualifications", "nice to have", "preferred", "bonus points",
        "wünschenswert", "von vorteil", "idealerweise", "nice-to-have",
        "souhaité", "souhaitable", "deseable", "valorables", "preferibile", "titoli preferenziali",
    },
    "benefits": {
        "benefits", "what we offer", "perks", "our offer",
        "benefits und vorteile", "wir bieten", "was wir bieten", "unsere benefits",
        "avantages", "ce que nous offrons", "beneficios", "ofrecemos", "benefit", "cosa offriamo",
    },
    "application_details": {
        "how to apply", "application process", "application details",
        "bewerbung", "bewerbungsprozess", "so bewirbst du dich",
        "candidature", "comment postuler", "cómo postular", "proceso de selección", "come candidarsi",
    },
}
_BULLET = re.compile(r"^(?:[-*•▪◦]|\d+[.)])\s+")
_TAG = re.compile(r"<[^>]+>")


def build_runr_description_rules(row: Mapping[str, Any]) -> dict[str, Any]:
    """Prepare a source-faithful reading view without a provider request.

    The rule pass preserves the source language. The free model can later
    replace this posting-version row with an English rewrite.
    """
    original = build_preserved_original_posting(row)
    source = str(original.get("description_text") or original.get("description") or "").strip()
    if not source:
        raise ValueError("posting description is empty")
    source = unescape(_TAG.sub(" ", source)) if "<" in source else unescape(source)
    grouped: dict[str, list[dict[str, str]]] = {section: [] for section in SECTIONS}
    intro: list[str] = []
    current: str | None = None
    language = "und"
    for raw in source.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        heading, separator, remainder = line.partition(":")
        candidate = (heading if separator else line).strip().casefold().rstrip(" -–")
        section = next((name for name, aliases in _RULE_HEADINGS.items() if candidate in aliases), None)
        if section:
            current = section
            if candidate in {"aufgaben", "deine aufgaben", "ihre aufgaben", "tätigkeiten", "verantwortlichkeiten", "anforderungen", "voraussetzungen", "bewerbung", "wir bieten", "was wir bieten"}:
                language = "de"
            elif candidate in {"responsabilités", "missions", "exigences", "prérequis", "avantages", "candidature"}:
                language = "fr"
            elif candidate in {"responsabilidades", "funciones", "requisitos", "beneficios", "ofrecemos"}:
                language = "es"
            elif candidate in {"responsabilità", "mansioni", "requisiti", "benefit", "come candidarsi"}:
                language = "it"
            line = remainder.strip() if separator else ""
            if not line:
                continue
        item = _BULLET.sub("", line).strip()
        if not item:
            continue
        if current:
            if item not in {entry["text"] for entry in grouped[current]}:
                grouped[current].append({"text": item, "source_excerpt": item})
        else:
            intro.append(item)
    overview_source = " ".join(intro) or next(
        (items[0]["text"] for items in grouped.values() if items), source
    )
    overview = overview_source[:400].rsplit(" ", 1)[0] if len(overview_source) > 400 else overview_source
    summary = {"source_language": language, "output_language": language, "overview": overview, **grouped}
    return {
        "version_id": str(row.get("current_version_id") or ""),
        "canonical_job_id": str(row.get("canonical_job_id") or ""),
        "content_hash": str(row.get("content_hash") or ""),
        "summary": summary,
        "structured_description": {},
        "original_posting": original,
        "provider": "runr_rules",
        "model": "",
        "prompt_version": PROMPT_VERSION,
    }


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
    if not (model == "openrouter/free" or model.endswith(":free") or model == NEMO_MODEL):
        raise ValueError("description model must be free-tier or the approved Nemo pilot")
    parameters = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "provider": {"require_parameters": True},
        "temperature": 0,
        "max_tokens": 16384,
    }
    if model != NEMO_MODEL:
        parameters["reasoning"] = {"effort": "none"}
    body = json.dumps(parameters).encode("utf-8")
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
        try:
            failure = json.load(exc)
            message = str((failure.get("error") or {}).get("message") or "")[:300]
        except (ValueError, AttributeError):
            message = ""
        raise RuntimeError(f"openrouter_http_{exc.code}: {message}") from exc
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("model response content is not text")
    result = json.loads(content)
    if isinstance(result, dict):
        result["_runr_model"] = payload.get("model") or DEFAULT_MODEL
    return result
