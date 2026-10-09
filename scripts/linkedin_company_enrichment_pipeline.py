"""Resumable LinkedIn company enrichment and identity-resolution pipeline.

The module is deliberately usable offline for parsing/scoring tests and online
only through the CLI's bounded/live modes. Credentials are loaded from the
project environment (``user_config/.env`` when present); none are embedded in
code, state, CSV, or reports.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html as html_module
import json
import os
import random
import re
import sqlite3
import sys
import threading
import time
import unicodedata
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional in production, not needed by pure functions
    load_dotenv = None


SOURCE_DEFAULT = Path(
    os.environ.get(
        "RUNR_COMPANY_CANONICAL_INPUT",
        "data/acquisition/inputs/company_registry_canonical.csv",
    )
)
NEW_COLUMNS = [
    "linkedin_company_id",
    "linkedin_company_id_status",
    "linkedin_company_id_confidence",
    "linkedin_company_id_source",
    "linkedin_company_id_validation_score",
    "linkedin_company_id_validation_reasons_json",
    "linkedin_company_id_resolved_at",
    "linkedin_company_id_validated_at",
    "linkedin_resolved_url",
    "linkedin_transport_used",
    "linkedin_transport_level",
    "linkedin_transport_status_classification",
    "linkedin_transport_fallback_reason",
    "linkedin_transport_scrapeops_credit_cost",
    "linkedin_transport_trace_json",
    "linkedin_company_access_status",
    "linkedin_display_name",
    "linkedin_tagline",
    "linkedin_description",
    "linkedin_industry",
    "linkedin_company_type",
    "linkedin_founded_year",
    "linkedin_website_url",
    "linkedin_website_domain",
    "website_domain_match",
    "linkedin_employee_count",
    "linkedin_employee_count_range",
    "linkedin_associated_employee_count",
    "linkedin_follower_count_observed_at",
    "linkedin_headquarters_display",
    "linkedin_specialties_json",
    "linkedin_logo_url",
    "linkedin_cover_image_url",
    "linkedin_has_services",
    "linkedin_has_products",
    "linkedin_has_life_page",
    "linkedin_has_people_page",
    "linkedin_has_jobs_page",
    "linkedin_jobs_url",
    "linkedin_has_jobs",
    "linkedin_job_validation_count",
    "linkedin_jobs_last_checked_at",
    "linkedin_current_jobs_count_observed",
    "is_linkedin_company_page",
    "is_showcase_page",
    "is_school_or_education_page",
    "is_staffing_or_recruiting_company",
    "staffing_detection_confidence",
    "staffing_detection_reasons_json",
    "is_nonprofit",
    "is_government_entity",
    "has_valid_website",
    "has_valid_linkedin_page",
    "has_validated_linkedin_company_id",
    "has_germany_location",
    "germany_location_count",
    "headquartered_in_germany",
    "has_current_linkedin_jobs",
    "linkedin_jobs_sampled",
    "normalized_employee_min",
    "normalized_employee_max",
    "company_size_bucket",
    "company_profile_completeness_score",
    "missing_company_fields_json",
    "company_relevance_score",
    "company_relevance_reasons_json",
    "career_url_candidate",
    "career_url_source",
    "field_provenance_json",
    "enrichment_conflicts_json",
]

LINKEDIN_PATH_RE = re.compile(r"^/(company|school|showcase)/([^/?#]+)", re.I)
F_C_PATTERNS = (
    re.compile(r"(?:[?&]|%3[fF])f_C(?:=|%3[dD])(\d+)", re.I),
    re.compile(r"(?:[?&]|%3[fF])f_c(?:=|%3[dD])(\d+)", re.I),
    re.compile(r"urn:li:(?:fsd_)?company:(\d+)", re.I),
    re.compile(r"(?:companyId|company_id)[\"'=: ]+(\d{3,})", re.I),
)
TRACKING_KEYS = {"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "trk", "trackingid"}
LEGAL_SUFFIXES = {
    "ag",
    "co",
    "company",
    "gmbh",
    "group",
    "holding",
    "holdings",
    "inc",
    "kg",
    "limited",
    "llc",
    "ltd",
    "plc",
    "se",
}
STAFFING_TERMS = {
    "staffing",
    "staffing and recruiting",
    "recruiting",
    "recruitment",
    "personaldienstleistung",
    "zeitarbeit",
    "temporary staffing",
    "executive search",
    "human resources services",
    "talent acquisition",
}
EDUCATION_TERMS = {"school", "education", "university", "college", "hochschule", "universität", "universitaet"}
NONPROFIT_TERMS = {"nonprofit", "non-profit", "charity", "foundation", "stiftung", "gemeinnützig"}
GOVERNMENT_TERMS = {"government", "minister", "municipal", "city of", "bundes", "landkreis", "verwaltung"}
GERMANY_TERMS = {"germany", "deutschland", "de", "berlin", "hamburg", "munich", "münchen", "köln", "cologne"}
NOT_FOUND_MARKERS = ("page not found", "profile not found", "this page doesn't exist", "this page doesn’t exist", "page isn’t available")
ALLOWED_STATUSES = {"VALIDATED", "HIGH_CONFIDENCE", "CANDIDATE", "AMBIGUOUS", "MISMATCH", "MISSING", "PAGE_NOT_FOUND", "NO_ID_EXPOSED", "ACCESS_UNRESOLVED"}
PLACEHOLDER_CANONICAL_IDS = {"", "/", "//", "-", "none", "null", "nan"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean_text(value: Any) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    text = "".join(char for char in text if char in "\n\t" or unicodedata.category(char) != "Cc")
    return " ".join(text.split()).strip()


def _strip_tracking(query: str) -> str:
    return urlencode(
        [(key, value) for key, value in parse_qsl(query, keep_blank_values=True) if key.casefold() not in TRACKING_KEYS and not key.casefold().startswith("utm_")],
        doseq=True,
    )


def normalize_linkedin_url(value: Any) -> str:
    raw = clean_text(value)
    if not raw:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*://", raw, re.I):
        raw = "https://" + raw
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    if host != "linkedin.com" and not host.endswith(".linkedin.com"):
        return ""
    match = LINKEDIN_PATH_RE.match(parsed.path or "")
    if not match:
        return ""
    page_type, slug = match.groups()
    slug = unquote(slug).casefold().strip()
    if not slug:
        return ""
    return f"https://www.linkedin.com/{page_type.casefold()}/{quote(slug, safe='-._~')}/"


def linkedin_slug(value: Any) -> str:
    normalized = normalize_linkedin_url(value)
    if not normalized:
        return ""
    match = LINKEDIN_PATH_RE.match(urlsplit(normalized).path)
    return unquote(match.group(2)) if match else ""


def linkedin_page_type(value: Any) -> str:
    normalized = normalize_linkedin_url(value)
    if not normalized:
        return ""
    match = LINKEDIN_PATH_RE.match(urlsplit(normalized).path)
    return match.group(1).casefold() if match else ""


def linkedin_identity(value: Any) -> str:
    normalized = normalize_linkedin_url(value)
    return normalized.casefold().rstrip("/") if normalized else ""


def extract_f_c_ids(value: str) -> set[str]:
    decoded = str(value or "")
    for _ in range(3):
        decoded = html_module.unescape(unquote(decoded))
    candidates: set[str] = set()
    for pattern in F_C_PATTERNS:
        candidates.update(pattern.findall(decoded))
    return {candidate for candidate in candidates if candidate.isdigit() and int(candidate) > 0}


def normalize_domain(value: Any) -> str:
    raw = clean_text(value).casefold()
    if not raw:
        return ""
    candidate = raw if "://" in raw else "https://" + raw
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return ""
    host = (parsed.hostname or "").casefold().removeprefix("www.").rstrip(".")
    if not host or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split(".")):
        return ""
    return host


def root_domain(value: Any) -> str:
    host = normalize_domain(value)
    labels = host.split(".") if host else []
    if len(labels) <= 2:
        return host
    if labels[-2] in {"co", "com", "org", "net", "gov", "ac"} and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def normalize_company_name(value: Any) -> str:
    text = clean_text(value).casefold().replace("&", " and ")
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    tokens = [token for token in text.split() if token not in LEGAL_SUFFIXES]
    return " ".join(tokens)


def name_similarity(left: Any, right: Any) -> float:
    from difflib import SequenceMatcher

    first = normalize_company_name(left)
    second = normalize_company_name(right)
    if not first or not second:
        return 0.0
    if first == second:
        return 1.0
    first_tokens = set(first.split())
    second_tokens = set(second.split())
    overlap = len(first_tokens & second_tokens) / max(len(first_tokens | second_tokens), 1)
    sequence = SequenceMatcher(None, first, second).ratio()
    return max(overlap, sequence)


def parse_integer(value: Any) -> int | None:
    match = re.search(r"(?<!\d)(\d[\d,\.]*)(?:\s*([KMBkmb]))?", clean_text(value))
    if not match:
        return None
    raw = match.group(1).replace(",", "")
    try:
        multiplier = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get((match.group(2) or "").casefold(), 1)
        return int(float(raw) * multiplier)
    except ValueError:
        return None


def parse_employee_range(value: Any) -> tuple[int | None, int | None]:
    text = clean_text(value).casefold().replace("–", "-").replace("—", "-")
    if not text:
        return None, None
    if text in {"over-10k", "10001+", "10001-"}:
        return 10001, None
    numbers = [int(number.replace(",", "")) for number in re.findall(r"\d[\d,]*", text)]
    if len(numbers) >= 2:
        return numbers[0], numbers[1]
    if len(numbers) == 1 and "over" in text:
        return numbers[0], None
    return None, None


def normalize_employee_bounds(value: Any) -> tuple[int | None, int | None, str]:
    lower, upper = parse_employee_range(value)
    if lower is None:
        return None, None, "UNKNOWN"
    if upper is None or lower >= 10001:
        return lower, None, "10001+"
    if lower == 1 and upper == 10:
        return lower, upper, "1-10"
    if lower <= 10 and upper <= 10:
        return lower, upper, "2-10"
    if lower <= 50:
        return lower, upper, "11-50"
    if lower <= 200:
        return lower, upper, "51-200"
    if lower <= 500:
        return lower, upper, "201-500"
    if lower <= 1000:
        return lower, upper, "501-1000"
    if lower <= 5000:
        return lower, upper, "1001-5000"
    return lower, upper, "5001-10000"


def _json_load(value: Any) -> Any:
    if not value:
        return None
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return None


def _first_json_ld(soup: BeautifulSoup) -> dict[str, Any]:
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        try:
            payload = json.loads(script.get_text(strip=True))
        except (TypeError, ValueError):
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        if isinstance(payload, dict) and isinstance(payload.get("@graph"), list):
            candidates.extend(payload["@graph"])
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            types = candidate.get("@type")
            values = types if isinstance(types, list) else [types]
            if any(str(value).casefold() in {"organization", "corporation", "educationalorganization", "collegeoruniversity"} for value in values):
                return candidate
    return {}


def _meta_map(soup: BeautifulSoup) -> dict[str, str]:
    result = {}
    for tag in soup.find_all("meta"):
        key = clean_text(tag.get("property") or tag.get("name") or tag.get("itemprop"))
        value = clean_text(tag.get("content"))
        if key and value:
            result[key.casefold()] = value
    return result


def _page_name(meta: Mapping[str, str], soup: BeautifulSoup) -> str:
    title = meta.get("og:title") or meta.get("twitter:title") or meta.get("title") or (soup.title.get_text(" ", strip=True) if soup.title else "")
    return re.sub(r"\s*[|·-]\s*linkedin(?:\s*[:|].*)?$", "", clean_text(title), flags=re.I).strip()


def _value_name(value: Any) -> str:
    if isinstance(value, dict):
        return clean_text(value.get("name") or value.get("value") or value.get("addressLocality"))
    return clean_text(value)


def _extract_locations(data: Mapping[str, Any], headquarters: dict[str, str]) -> list[dict[str, Any]]:
    locations = data.get("location") or data.get("locations") or []
    if isinstance(locations, dict):
        locations = [locations]
    if not isinstance(locations, list):
        locations = []
    result = []
    for item in locations:
        if not isinstance(item, dict):
            continue
        address = item.get("address") if isinstance(item.get("address"), dict) else item
        country = _value_name(address.get("addressCountry"))
        result.append({
            "city": _value_name(address.get("addressLocality") or item.get("city")),
            "region": _value_name(address.get("addressRegion") or item.get("region")),
            "country": country,
            "country_code": country_code(country),
            "postal_code": clean_text(address.get("postalCode")),
            "address": clean_text(address.get("streetAddress") or item.get("address")),
            "primary": bool(item.get("primary") or item.get("isHeadquarters")),
            "source": "linkedin",
        })
    if headquarters and not result:
        result.append({**headquarters, "primary": True, "source": "linkedin"})
    return result


def country_code(value: Any) -> str:
    text = clean_text(value).casefold()
    mappings = {
        "germany": "DE", "deutschland": "DE", "united states": "US", "usa": "US", "united kingdom": "GB", "uk": "GB",
        "france": "FR", "austria": "AT", "switzerland": "CH", "netherlands": "NL", "poland": "PL", "italy": "IT",
    }
    return text.upper() if len(text) == 2 and text.isalpha() else mappings.get(text, "")


def _extract_employee(data: Mapping[str, Any], visible: str) -> tuple[str, int | None, int | None, int | None]:
    employees = data.get("numberOfEmployees")
    if isinstance(employees, dict):
        value = parse_integer(employees.get("value"))
        lower = parse_integer(employees.get("minValue"))
        upper = parse_integer(employees.get("maxValue"))
        if lower is not None and upper is not None:
            return f"{lower}-{upper}", value, lower, upper
    employee_range = ""
    match = re.search(r"(\d[\d,]*)\s*[-–—]\s*(\d[\d,]*)\s+employees", visible, re.I)
    if match:
        employee_range = f"{int(match.group(1).replace(',', ''))}-{int(match.group(2).replace(',', ''))}"
    associated = None
    match = re.search(r"(\d[\d,.]*\s*[KMB]?)\s+(?:associated\s+)?employees?\s+on\s+LinkedIn", visible, re.I)
    if match:
        raw = match.group(1).replace(",", "")
        multiplier = 1
        if raw.casefold().endswith("k"):
            multiplier, raw = 1000, raw[:-1]
        elif raw.casefold().endswith("m"):
            multiplier, raw = 1_000_000, raw[:-1]
        try:
            associated = int(float(raw) * multiplier)
        except ValueError:
            associated = None
    return employee_range, None, None, associated


def parse_linkedin_page(html_text: str, requested_url: str, status_code: int = 200) -> dict[str, Any]:
    decoded = html_module.unescape(str(html_text or ""))
    soup = BeautifulSoup(decoded, "html.parser")
    meta = _meta_map(soup)
    data = _first_json_ld(soup)
    visible = clean_text(soup.get_text(" ", strip=True))
    title = _page_name(meta, soup)
    lower = decoded.casefold()
    page_type = linkedin_page_type(requested_url) or "company"
    not_found = status_code >= 400 or any(marker in lower for marker in NOT_FOUND_MARKERS)
    address = data.get("address") if isinstance(data.get("address"), dict) else {}
    headquarters = {
        "city": _value_name(address.get("addressLocality")),
        "region": _value_name(address.get("addressRegion")),
        "country": _value_name(address.get("addressCountry")),
        "country_code": country_code(_value_name(address.get("addressCountry"))),
        "address": clean_text(address.get("streetAddress")),
        "display": ", ".join(value for value in (_value_name(address.get("addressLocality")), _value_name(address.get("addressRegion")), _value_name(address.get("addressCountry"))) if value),
    }
    website = clean_text(data.get("url") or meta.get("og:url") or meta.get("linkedin:website"))
    if "linkedin.com" in website.casefold():
        website = ""
    employee_range, employee_count, employee_min, associated = _extract_employee(data, visible)
    if not employee_range and employee_min is not None:
        employee_range = f"{employee_min}-{parse_integer(data.get('numberOfEmployees', {}).get('maxValue')) or employee_min}" if isinstance(data.get("numberOfEmployees"), dict) else ""
    founded = data.get("foundingDate") or meta.get("founded") or ""
    founded_match = re.search(r"\b(18\d{2}|19\d{2}|20\d{2})\b", str(founded))
    locations = _extract_locations(data, headquarters)
    specialties = data.get("knowsAbout") or data.get("specialties") or meta.get("linkedin:specialties") or []
    if isinstance(specialties, str):
        specialties = [item.strip() for item in re.split(r"[,;|]", specialties) if item.strip()]
    links = [urljoin(requested_url, anchor.get("href")) for anchor in soup.find_all("a", href=True)]
    jobs_links = [url for url in links if "/jobs" in url.casefold() or "f_c=" in url.casefold()]
    career_links = [
        url for url in links
        if "linkedin.com" not in (urlsplit(url).hostname or "").casefold()
        and re.search(r"(?:career|careers|jobs|work[-_ ]?with[-_ ]?us|stellenangebote)", url, re.I)
    ]
    return {
        "page_valid": not not_found and bool(title or data),
        "page_type": page_type,
        "display_name": title or clean_text(data.get("name")),
        "tagline": clean_text(data.get("slogan") or data.get("tagline") or meta.get("linkedin:tagline")),
        "description": clean_text(data.get("description") or meta.get("og:description") or meta.get("description")),
        "website_url": website,
        "website_domain": root_domain(website),
        "industry": clean_text(data.get("industry") or meta.get("industry") or meta.get("linkedin:industry")),
        "company_type": clean_text(data.get("companyType") or data.get("organizationType") or meta.get("linkedin:company_type")),
        "founded_year": founded_match.group(1) if founded_match else "",
        "employee_count": employee_count,
        "employee_range": employee_range,
        "associated_employee_count": associated,
        "follower_count": parse_integer(re.search(r"([\d,.]+\s*[KMB]?)\s+followers", visible, re.I).group(1)) if re.search(r"([\d,.]+\s*[KMB]?)\s+followers", visible, re.I) else None,
        "headquarters": headquarters,
        "locations": locations,
        "specialties": list(dict.fromkeys(clean_text(item) for item in specialties if clean_text(item))),
        "logo_url": clean_text(data.get("logo") if isinstance(data.get("logo"), str) else meta.get("og:image")),
        "cover_image_url": next((url for url in re.findall(r"https://media\.licdn\.com/[^\"'\\ ]+", decoded) if "background" in decoded[max(0, decoded.find(url)-250):decoded.find(url)].casefold()), ""),
        "jobs_links": list(dict.fromkeys(jobs_links)),
        "has_services": bool(re.search(r"\bservices\b", visible, re.I)),
        "has_products": bool(re.search(r"\bproducts?\b", visible, re.I)),
        "has_life_page": any("life" in url.casefold() for url in links),
        "has_people_page": any("/people" in url.casefold() for url in links),
        "has_jobs_page": bool(jobs_links) or "/jobs" in requested_url.casefold(),
        "career_url_candidate": next(iter(dict.fromkeys(career_links)), ""),
        "raw_company_ids": sorted(extract_f_c_ids(decoded)),
    }


def extract_job_cards(html_text: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html_module.unescape(str(html_text or "")), "html.parser")
    cards = []
    for node in soup.select(".base-card, .base-search-card, [data-entity-urn], [data-company-urn]"):
        text = clean_text(node.get_text(" ", strip=True))
        if not text:
            continue
        urn = clean_text(node.get("data-company-urn") or node.get("data-entity-urn"))
        ids = sorted(extract_f_c_ids(str(node)))
        cards.append({"text": text[:500], "urn": urn, "company_id": ids[0] if len(ids) == 1 else ""})
    return cards


def extract_company_candidates(html_text: str) -> list[dict[str, str]]:
    """Extract conservative public-search candidates without choosing an identity."""
    soup = BeautifulSoup(html_module.unescape(str(html_text or "")), "html.parser")
    candidates: dict[str, dict[str, str]] = {}
    for anchor in soup.find_all("a", href=True):
        url = normalize_linkedin_url(urljoin("https://www.linkedin.com", anchor.get("href", "")))
        if not url:
            continue
        container = anchor.find_parent(class_=re.compile(r"result|card|entity", re.I)) or anchor.parent
        raw = str(container or anchor)
        ids = sorted(extract_f_c_ids(raw))
        candidates.setdefault(url, {
            "url": url,
            "slug": linkedin_slug(url),
            "company_id": ids[0] if len(ids) == 1 else "",
            "text": clean_text(container.get_text(" ", strip=True) if container else anchor.get_text(" ", strip=True))[:500],
        })
    return list(candidates.values())


def compare_job_cards(cards: Iterable[Mapping[str, Any]], expected_id: str, expected_name: str, expected_slug: str) -> dict[str, Any]:
    cards = list(cards)
    if not cards:
        return {"count": 0, "match_rate": None, "matched": 0, "sampled": False}
    matched = 0
    for card in cards[:10]:
        card_id = str(card.get("company_id") or "")
        text = normalize_company_name(card.get("text"))
        if card_id == expected_id or (expected_name and normalize_company_name(expected_name) in text) or (expected_slug and expected_slug.casefold() in str(card.get("text") or "").casefold()):
            matched += 1
    return {"count": len(cards), "match_rate": matched / min(len(cards), 10), "matched": matched, "sampled": True}


def identity_validation_score(evidence: Mapping[str, Any]) -> tuple[int, str, float]:
    score = 0
    reasons = {}
    if evidence.get("exact_page_see_all_id"):
        score += 50
        reasons["exact_page_see_all_id"] = True
    if evidence.get("slug_match"):
        score += 25
        reasons["slug_match"] = True
    if evidence.get("domain_match"):
        score += 25
        reasons["domain_match"] = True
    rate = evidence.get("job_card_company_match_rate")
    if isinstance(rate, (int, float)) and rate > 0:
        score += 15
        reasons["job_card_company_match_rate"] = rate
    if evidence.get("name_match"):
        score += 10
        reasons["name_match"] = True
    if evidence.get("headquarters_match"):
        score += 10
        reasons["headquarters_match"] = True
    if evidence.get("job_card_company_match_rate") == 0:
        score -= 60
        reasons["job_card_company_mismatch"] = True
    if evidence.get("domain_conflict"):
        score -= 50
        reasons["domain_conflict"] = True
    if evidence.get("different_organization"):
        score -= 40
        reasons["different_organization"] = True
    if evidence.get("multiple_incompatible_ids"):
        score -= 30
        reasons["multiple_incompatible_ids"] = True
    if evidence.get("severe_name_mismatch"):
        score -= 25
        reasons["severe_name_mismatch"] = True
    if score >= 80:
        status = "VALIDATED"
    elif score >= 65:
        status = "HIGH_CONFIDENCE"
    elif score >= 40:
        status = "CANDIDATE"
    else:
        status = "AMBIGUOUS"
    return score, status, max(0.0, min(1.0, score / 100))


def classify_page_status(*, page_valid: bool, ids: Iterable[str], score: int, mismatch: bool = False) -> str:
    candidates = set(ids)
    if not page_valid:
        return "PAGE_NOT_FOUND"
    if mismatch:
        return "MISMATCH"
    if len(candidates) > 1:
        return "AMBIGUOUS"
    if not candidates:
        return "NO_ID_EXPOSED"
    if score >= 80:
        return "VALIDATED"
    if score >= 65:
        return "HIGH_CONFIDENCE"
    if score >= 40:
        return "CANDIDATE"
    return "AMBIGUOUS"


def merge_existing_value(existing: Any, incoming: Any, *, source: str, high_confidence: bool = False) -> tuple[Any, bool, str]:
    if clean_text(existing):
        return existing, False, "existing_value_preserved"
    if incoming in (None, "", [], {}):
        return existing, False, "incoming_empty"
    return incoming, True, source if high_confidence else f"{source}_lower_confidence"


def detect_staffing(row: Mapping[str, Any], facts: Mapping[str, Any]) -> tuple[bool, str, list[str]]:
    haystack = " ".join(
        clean_text(value).casefold()
        for value in (
            row.get("company_name"), row.get("legal_name"), row.get("industry"), row.get("description"), facts.get("display_name"), facts.get("industry"), facts.get("description"),
            " ".join(facts.get("specialties") or []), _json_text(row.get("industries_json")), _json_text(row.get("categories_json")),
        )
    )
    reasons = sorted({term for term in STAFFING_TERMS if term in haystack})
    confidence = "HIGH" if len(reasons) >= 2 or "staffing and recruiting" in haystack else "MEDIUM" if reasons else "NONE"
    return bool(reasons), confidence, reasons


def _json_text(value: Any) -> str:
    parsed = _json_load(value)
    if parsed is None:
        return clean_text(value)
    return clean_text(json.dumps(parsed, ensure_ascii=False))


def germany_signals(row: Mapping[str, Any], facts: Mapping[str, Any]) -> tuple[bool, int, bool]:
    locations = list(facts.get("locations") or [])
    if row.get("locations_json"):
        parsed = _json_load(row.get("locations_json"))
        if isinstance(parsed, list):
            locations.extend(item for item in parsed if isinstance(item, dict))
    headquarters = facts.get("headquarters") or {}
    row_text = " ".join(clean_text(row.get(field)) for field in ("headquarters_city", "headquarters_region", "headquarters_country", "headquarters_country_code", "headquarters_display"))
    count = 0
    for location in locations:
        text = " ".join(clean_text(location.get(key)) for key in ("city", "region", "country", "country_code", "address"))
        if "germany" in text.casefold() or "deutschland" in text.casefold() or clean_text(location.get("country_code")).casefold() == "de":
            count += 1
    if "germany" in row_text.casefold() or "deutschland" in row_text.casefold() or clean_text(row.get("headquarters_country_code")).casefold() == "de":
        count = max(1, count)
    headquartered = "germany" in clean_text(headquarters.get("country")).casefold() or clean_text(headquarters.get("country_code")).casefold() == "de" or "germany" in row_text.casefold() or clean_text(row.get("headquarters_country_code")).casefold() == "de"
    return count > 0 or headquartered, count, headquartered


def app_relevance(row: Mapping[str, Any], facts: Mapping[str, Any], identity_status: str) -> dict[str, Any]:
    staffing, staffing_confidence, staffing_reasons = detect_staffing(row, facts)
    page_type = facts.get("page_type") or linkedin_page_type(row.get("linkedin_company_url"))
    page_name = clean_text(facts.get("display_name") or row.get("company_name"))
    education = page_type == "school" or any(term in page_name.casefold() for term in EDUCATION_TERMS) or any(term in clean_text(facts.get("industry")).casefold() for term in EDUCATION_TERMS)
    nonprofit = any(term in " ".join(clean_text(facts.get(key) or row.get(key)).casefold() for key in ("company_type", "industry", "description")) for term in NONPROFIT_TERMS)
    government = any(term in " ".join(clean_text(facts.get(key) or row.get(key)).casefold() for key in ("company_type", "industry", "description", "display_name")) for term in GOVERNMENT_TERMS)
    germany, germany_count, headquartered = germany_signals(row, facts)
    has_website = bool(normalize_domain(row.get("website_url") or facts.get("website_url")))
    has_page = bool(facts.get("page_valid"))
    has_jobs = bool(facts.get("job_validation_count") or facts.get("has_jobs"))
    size_value = row.get("employee_count_range") or facts.get("employee_range") or row.get("employee_count")
    employee_min, employee_max, bucket = normalize_employee_bounds(size_value)
    required = {
        "linkedin_company_id": identity_status in {"VALIDATED", "HIGH_CONFIDENCE"},
        "website_url": has_website,
        "description": bool(row.get("description") or facts.get("description")),
        "industry": bool(row.get("industry") or facts.get("industry")),
        "employee_size": bool(size_value),
        "locations": bool(row.get("locations_json") or facts.get("locations")),
        "logo": bool(row.get("logo_url") or facts.get("logo_url")),
        "company_type": bool(row.get("company_type") or facts.get("company_type")),
        "founded_year": bool(row.get("founded_year") or facts.get("founded_year")),
        "specialties": bool(facts.get("specialties")),
        "followers": bool(row.get("linkedin_follower_count") or facts.get("follower_count")),
    }
    completeness = round(sum(required.values()) / len(required) * 100, 2)
    reasons = []
    score = 50
    if identity_status == "VALIDATED":
        score += 20
        reasons.append("validated_linkedin_id")
    elif identity_status == "HIGH_CONFIDENCE":
        score += 10
        reasons.append("high_confidence_linkedin_id")
    if has_website:
        score += 10
    else:
        reasons.append("no_valid_website")
    if has_jobs:
        score += 10
        reasons.append("current_linkedin_jobs")
    if germany:
        score += 10
        reasons.append("germany_location")
    if staffing:
        reasons.append("staffing_or_recruiting_signal")
    if education:
        reasons.append("education_or_school_signal")
    if page_type == "showcase":
        reasons.append("showcase_page")
    if completeness < 50:
        reasons.append("incomplete_profile")
    return {
        "is_linkedin_company_page": page_type == "company",
        "is_showcase_page": page_type == "showcase",
        "is_school_or_education_page": education,
        "is_staffing_or_recruiting_company": staffing,
        "staffing_detection_confidence": staffing_confidence,
        "staffing_detection_reasons_json": json.dumps(staffing_reasons, ensure_ascii=False),
        "is_nonprofit": nonprofit,
        "is_government_entity": government,
        "has_valid_website": has_website,
        "has_valid_linkedin_page": has_page,
        "has_validated_linkedin_company_id": identity_status in {"VALIDATED", "HIGH_CONFIDENCE"},
        "has_germany_location": germany,
        "germany_location_count": germany_count,
        "headquartered_in_germany": headquartered,
        "has_current_linkedin_jobs": has_jobs,
        "linkedin_jobs_sampled": bool(facts.get("jobs_sampled")),
        "normalized_employee_min": employee_min or "",
        "normalized_employee_max": employee_max or "",
        "company_size_bucket": bucket,
        "company_profile_completeness_score": completeness,
        "missing_company_fields_json": json.dumps([key for key, present in required.items() if not present], ensure_ascii=False),
        "company_relevance_score": max(0, min(100, score)),
        "company_relevance_reasons_json": json.dumps(sorted(set(reasons)), ensure_ascii=False),
    }


@dataclass(frozen=True)
class FetchResponse:
    url: str
    final_url: str
    status_code: int
    content_type: str
    body: bytes
    attempts: int
    from_cache: bool = False
    transport_used: str = "webshare"
    transport_level: str = "webshare"
    status_classification: str = ""
    fallback_reason: str = ""
    webshare_attempts: int = 0
    scrapeops_attempts: int = 0
    scrapeops_credit_cost: float = 0.0
    scrapeops_estimated_credit_cost: float = 0.0
    scrapeops_credit_cost_basis: str = ""
    transport_trace: tuple[dict[str, Any], ...] = ()

    def transport_record(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "transport_used": self.transport_used,
            "transport_level": self.transport_level,
            "status_code": self.status_code,
            "attempt_count": self.attempts,
            "webshare_attempts": self.webshare_attempts,
            "scrapeops_attempts": self.scrapeops_attempts,
            "scrapeops_credit_cost": self.scrapeops_credit_cost,
            "scrapeops_estimated_credit_cost": self.scrapeops_estimated_credit_cost,
            "scrapeops_credit_cost_basis": self.scrapeops_credit_cost_basis,
            "fallback_reason": self.fallback_reason,
            "status_classification": self.status_classification or classify_transport_response(self),
            "from_cache": self.from_cache,
        }


TRANSPORT_ACCESS_FAILURES = {"blocked", "challenge", "rate_limited", "malformed", "network_error", "budget_exhausted"}


def classify_transport_response(response: FetchResponse) -> str:
    if response.status_classification:
        return response.status_classification
    status = int(response.status_code or 0)
    body = response.body.decode("utf-8", errors="replace")[:500_000].casefold()
    if status == 999:
        return "blocked"
    if status == 403:
        return "blocked"
    if status == 429:
        return "rate_limited"
    if status == 404:
        return "legitimate_not_found"
    if status <= 0:
        return "network_error"
    if status >= 500:
        return "network_error"
    if any(marker in body for marker in ("captcha", "security verification", "unusual traffic", "verify you are human", "checkpoint")):
        return "challenge"
    if status < 400 and len(body.strip()) >= 80 and ("<html" in body or "<!doctype" in body):
        return "valid_html"
    if status < 400 and body.strip():
        return "valid_no_data"
    return "malformed"


class HybridLinkedInFetcher:
    """Cheap Webshare-first transport with bounded ScrapeOps escalation."""

    def __init__(self, *, webshare: HttpFetcher, scrapeops: HttpFetcher | None = None, scrapeops_modes: Iterable[str] = ("basic",), fallback_enabled: bool = False, metrics: PipelineMetrics | None = None, max_scrapeops_attempts_per_company: int = 3, scrapeops_job_validation_fallback: bool = False):
        self.webshare = webshare
        self.scrapeops = scrapeops
        self.scrapeops_modes = tuple(scrapeops_modes)
        self.fallback_enabled = fallback_enabled
        self.metrics = metrics or PipelineMetrics()
        self.max_scrapeops_attempts_per_company = max(0, int(max_scrapeops_attempts_per_company))
        self.scrapeops_job_validation_fallback = scrapeops_job_validation_fallback
        self._company_key = ""
        self._company_scrapeops_attempts = 0

    def begin_company(self, company_key: str) -> None:
        self._company_key = str(company_key or "")
        self._company_scrapeops_attempts = 0

    def fetch(self, url: str, *, kind: str = "html") -> FetchResponse:
        try:
            webshare_response = self.webshare.fetch(url, kind=kind)
        except Exception:
            webshare_response = FetchResponse(
                url, url, 0, "", b"", 0,
                transport_used="webshare",
                transport_level="webshare",
                status_classification="network_error",
            )
        classification = classify_transport_response(webshare_response)
        if classification not in TRANSPORT_ACCESS_FAILURES:
            return webshare_response
        if (kind == "job_validation" and not self.scrapeops_job_validation_fallback) or not self.fallback_enabled or self.scrapeops is None:
            return replace(webshare_response, status_classification=classification)
        fallback_reason = f"webshare_{classification}"
        scrapeops_response = webshare_response
        trace = [webshare_response.transport_record()]
        for mode in self.scrapeops_modes:
            if self._company_scrapeops_attempts >= self.max_scrapeops_attempts_per_company:
                self.metrics.scrapeops_company_budget_exhausted += 1
                return replace(webshare_response, status_classification="budget_exhausted", fallback_reason="scrapeops_company_budget_exhausted", transport_trace=tuple(trace))
            self._company_scrapeops_attempts += 1
            self.metrics.scrapeops_fallback_attempts += 1
            if isinstance(self.scrapeops, ScrapeOpsFetcher):
                scrapeops_response = self.scrapeops.fetch(url, kind=kind, mode=mode, fallback_reason=fallback_reason)
            else:
                scrapeops_response = self.scrapeops.fetch(url, kind=kind)
            trace.append(scrapeops_response.transport_record())
            if classify_transport_response(scrapeops_response) not in TRANSPORT_ACCESS_FAILURES:
                return replace(scrapeops_response, fallback_reason=fallback_reason, transport_trace=tuple(trace))
        return replace(scrapeops_response, fallback_reason=fallback_reason, transport_trace=tuple(trace))


@dataclass
class PipelineMetrics:
    requests: int = 0
    successful_requests: int = 0
    status_429: int = 0
    status_403: int = 0
    status_999: int = 0
    timeouts: int = 0
    proxy_errors: int = 0
    retries: int = 0
    proxy_rotations: int = 0
    cache_hits: int = 0
    fetch_failures: int = 0
    job_validation_attempted: int = 0
    job_validation_successful: int = 0
    job_validation_no_jobs: int = 0
    scrapeops_requests: int = 0
    scrapeops_successful_requests: int = 0
    scrapeops_failed_requests: int = 0
    scrapeops_default_requests: int = 0
    scrapeops_residential_requests: int = 0
    scrapeops_js_requests: int = 0
    scrapeops_credits_used: float = 0.0
    scrapeops_budget_exhausted: bool = False
    scrapeops_company_budget_exhausted: int = 0
    scrapeops_fallback_attempts: int = 0


class HttpFetcher(Protocol):
    def fetch(self, url: str, *, kind: str = "html") -> FetchResponse: ...


class CachedWebshareFetcher:
    def __init__(self, state: "StateStore", *, timeout: float = 30, retries: int = 3, delay: float = 1.0, metrics: PipelineMetrics | None = None, use_cache: bool = True, rotate_each_request: bool = False):
        self.state = state
        self.timeout = timeout
        self.retries = max(0, retries)
        self.delay = max(0.0, delay)
        self.metrics = metrics or PipelineMetrics()
        self.use_cache = bool(use_cache)
        self.rotate_each_request = bool(rotate_each_request)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Runr LinkedIn company verifier/1.0", "Accept": "text/html,application/xhtml+xml"})
        self.proxy_pool = self._load_proxy_config()
        self.proxy_index = (threading.get_ident() or 0) % len(self.proxy_pool)
        self.proxies = self.proxy_pool[self.proxy_index]

    @staticmethod
    def _load_proxy_config(max_proxies: int = 12) -> list[dict[str, str]]:
        if load_dotenv:
            env_path = Path(__file__).resolve().parents[1] / "user_config" / ".env"
            if env_path.exists():
                load_dotenv(env_path, override=False)
        explicit = os.getenv("WEBSHARE_PROXY_URL") or os.getenv("WEBSHARE_PROXY") or ""
        api_key = os.getenv("WEBSHARE_API_KEY") or ""
        username = os.getenv("WEBSHARE_PROXY_USERNAME") or ""
        password = os.getenv("WEBSHARE_PROXY_PASSWORD") or ""
        host = os.getenv("WEBSHARE_PROXY_HOST") or "p.webshare.io"
        port = os.getenv("WEBSHARE_PROXY_PORT") or "80"
        if explicit:
            proxy = explicit
        elif api_key:
            try:
                response = requests.get(
                    "https://proxy.webshare.io/api/v2/proxy/list/",
                    headers={"Authorization": f"Token {api_key}"},
                    params={"mode": "direct", "page": 1, "page_size": 100},
                    timeout=20,
                )
                response.raise_for_status()
                proxies = response.json().get("results", [])
                proxy_values = []
                for selected in proxies:
                    if not (selected.get("valid") and selected.get("proxy_address") and selected.get("port") and selected.get("username") and selected.get("password")):
                        continue
                    proxy_values.append("http://{}:{}@{}:{}".format(
                        quote(str(selected["username"]), safe=""),
                        quote(str(selected["password"]), safe=""),
                        selected["proxy_address"],
                        selected["port"],
                    ))
                if proxy_values:
                    return [{"http": value, "https": value} for value in proxy_values[: max(1, int(max_proxies))]]
                proxy = ""
            except (requests.RequestException, ValueError, TypeError, KeyError):
                proxy = ""
        if not proxy and username and password:
            proxy = f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"
        if not proxy:
            raise RuntimeError("Webshare proxy configuration is missing; expected WEBSHARE_PROXY_URL or WEBSHARE_PROXY_USERNAME/WEBSHARE_PROXY_PASSWORD.")
        return [{"http": proxy, "https": proxy}]

    def _rotate_proxy(self) -> None:
        if len(self.proxy_pool) <= 1:
            return
        self.proxy_index = (self.proxy_index + 1) % len(self.proxy_pool)
        self.proxies = self.proxy_pool[self.proxy_index]
        self.metrics.proxy_rotations += 1

    def fetch(self, url: str, *, kind: str = "html") -> FetchResponse:
        cached = self.state.get_fetch(url) if getattr(self, "use_cache", True) else None
        if cached:
            self.metrics.cache_hits += 1
            return FetchResponse(**cached, from_cache=True)
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 2):
            if self.delay:
                time.sleep(self.delay)
            if self.rotate_each_request and len(self.proxy_pool) > 1:
                self._rotate_proxy()
            self.metrics.requests += 1
            try:
                response = self.session.get(url, proxies=self.proxies, timeout=self.timeout, allow_redirects=True)
                status = int(response.status_code)
                if status == 429:
                    self.metrics.status_429 += 1
                if status == 403:
                    self.metrics.status_403 += 1
                if status == 999:
                    self.metrics.status_999 += 1
                retryable = status in {408, 425, 429, 500, 502, 503, 504, 999}
                if status == 999 and attempt > 1:
                    retryable = False
                if retryable and attempt <= self.retries:
                    self.metrics.retries += 1
                    if status in {403, 429, 999}:
                        self._rotate_proxy()
                    retry_after = response.headers.get("Retry-After")
                    try:
                        wait = min(60.0, max(1.0, float(retry_after))) if retry_after else min(60.0, 2.0 ** (attempt - 1))
                    except ValueError:
                        wait = min(60.0, 2.0 ** (attempt - 1))
                    time.sleep(wait)
                    continue
                if status >= 400:
                    self.metrics.fetch_failures += 1
                    result = FetchResponse(url, str(response.url), status, response.headers.get("content-type", ""), bytes(response.content), attempt, transport_used="webshare", transport_level="webshare", webshare_attempts=attempt)
                    return replace(result, status_classification=classify_transport_response(result))
                result = FetchResponse(url, str(response.url), status, response.headers.get("content-type", ""), bytes(response.content), attempt, transport_used="webshare", transport_level="webshare", webshare_attempts=attempt)
                result = replace(result, status_classification=classify_transport_response(result))
                self.metrics.successful_requests += 1
                if "html" in result.content_type.casefold() or kind == "html":
                    self.state.put_fetch(result)
                return result
            except requests.Timeout as exc:
                self.metrics.timeouts += 1
                last_error = exc
            except requests.RequestException as exc:
                self.metrics.proxy_errors += 1
                last_error = exc
            if attempt <= self.retries:
                self.metrics.retries += 1
                time.sleep(min(60.0, 2.0 ** (attempt - 1)))
        self.metrics.fetch_failures += 1
        raise RuntimeError(f"fetch_failed:{url}:{last_error}") from last_error


class ScrapeOpsFetcher:
    """ScrapeOps transport using the project's supported request-mode helpers."""

    def __init__(self, state: "StateStore", *, metrics: PipelineMetrics | None = None, timeout: int = 30, retries: int = 0, max_credit_cost: float = 0.0, credit_budget: float = 0.0, default_mode: str = "basic", use_cache: bool = True):
        if load_dotenv:
            env_path = Path(__file__).resolve().parents[1] / "user_config" / ".env"
            if env_path.exists():
                load_dotenv(env_path, override=False)
        self.state = state
        self.metrics = metrics or PipelineMetrics()
        self.timeout = max(3, int(timeout))
        self.retries = max(0, min(int(retries), 2))
        self.max_credit_cost = max(0.0, float(max_credit_cost))
        self.credit_budget = max(0.0, float(credit_budget))
        self.default_mode = str(default_mode or "basic")
        self.use_cache = bool(use_cache)
        self.api_key = os.getenv("SCRAPEOPS_API_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError("SCRAPEOPS_API_KEY is missing; ScrapeOps fallback is unavailable.")
        from backend.integrations.scrapeops import (
            SCRAPEOPS_PROXY_ENDPOINT,
            billed_status_code,
            build_proxy_params,
            estimate_mode_native_credits,
            parse_proxy_response_envelope,
            scrapeops_request_with_retry,
        )
        self._endpoint = SCRAPEOPS_PROXY_ENDPOINT
        self._billed_status_code = billed_status_code
        self._build_proxy_params = build_proxy_params
        self._estimate_mode_native_credits = estimate_mode_native_credits
        self._parse_proxy_response_envelope = parse_proxy_response_envelope
        self._request_with_retry = scrapeops_request_with_retry

    @staticmethod
    def _level(mode: str) -> str:
        return {
            "basic": "default",
            "residential": "residential",
            "render_js": "js",
            "render_js_cheap": "js_cheap",
            "render_js_residential": "residential_js",
        }.get(mode, mode or "default")

    def _budget_allows(self, estimated: float) -> bool:
        if self.max_credit_cost and estimated > self.max_credit_cost:
            self.metrics.scrapeops_budget_exhausted = True
            return False
        if self.credit_budget and self.metrics.scrapeops_credits_used + estimated > self.credit_budget:
            self.metrics.scrapeops_budget_exhausted = True
            return False
        return True

    def fetch(self, url: str, *, kind: str = "html", mode: str = "", fallback_reason: str = "") -> FetchResponse:
        cached = self.state.get_fetch(url) if getattr(self, "use_cache", True) else None
        if cached:
            cached_response = FetchResponse(**cached, from_cache=True)
            cached_classification = classify_transport_response(cached_response)
            if cached_response.transport_used == "scrapeops" or cached_classification not in TRANSPORT_ACCESS_FAILURES:
                self.metrics.cache_hits += 1
                return cached_response

        normalized_mode = str(mode or self.default_mode or "basic").strip() or "basic"
        estimated = float(self._estimate_mode_native_credits(normalized_mode))
        if not self._budget_allows(estimated):
            return FetchResponse(
                url, url, 0, "", b"", 0,
                transport_used="scrapeops",
                transport_level=self._level(normalized_mode),
                status_classification="budget_exhausted",
                fallback_reason=fallback_reason or "scrapeops_budget_exhausted",
                scrapeops_estimated_credit_cost=estimated,
                scrapeops_credit_cost_basis="not_attempted",
            )

        self.metrics.scrapeops_requests += 1
        if normalized_mode == "basic":
            self.metrics.scrapeops_default_requests += 1
        elif normalized_mode == "residential":
            self.metrics.scrapeops_residential_requests += 1
        elif "render_js" in normalized_mode:
            self.metrics.scrapeops_js_requests += 1
        try:
            params = self._build_proxy_params(api_key=self.api_key, url=url, mode=normalized_mode)
            retry = self._request_with_retry(
                "GET",
                self._endpoint,
                timeout_seconds=self.timeout,
                max_retries=self.retries,
                params=params,
                headers={"User-Agent": "Runr LinkedIn company verifier/1.0", "Accept": "text/html,application/xhtml+xml"},
            )
            if retry.response is None:
                self.metrics.scrapeops_failed_requests += 1
                return FetchResponse(
                    url, url, 0, "", b"", retry.attempts,
                    transport_used="scrapeops",
                    transport_level=self._level(normalized_mode),
                    status_classification="network_error",
                    fallback_reason=fallback_reason,
                    scrapeops_attempts=retry.attempts,
                    scrapeops_estimated_credit_cost=estimated,
                    scrapeops_credit_cost_basis="billing_unknown",
                )
            envelope = self._parse_proxy_response_envelope(retry.response)
            status = int(envelope.target_status_code or retry.response.status_code or 0)
            body = envelope.body.encode("utf-8", errors="replace")
            content_type = str(envelope.payload.get("content_type") or retry.response.headers.get("content-type") or "text/html")
            billed = self._billed_status_code(status)
            actual_cost_known = envelope.billed_credits_actual is not None and billed
            cost = float(envelope.billed_credits_actual if actual_cost_known else (estimated if billed else 0.0))
            cost_basis = "actual" if actual_cost_known else ("estimated" if billed else "not_billed")
            self.metrics.scrapeops_credits_used += cost
            result = FetchResponse(
                url,
                url,
                status,
                content_type,
                body,
                retry.attempts,
                transport_used="scrapeops",
                transport_level=self._level(normalized_mode),
                status_classification="",
                fallback_reason=fallback_reason,
                scrapeops_attempts=retry.attempts,
                scrapeops_credit_cost=cost,
                scrapeops_estimated_credit_cost=estimated if billed else 0.0,
                scrapeops_credit_cost_basis=cost_basis,
            )
            classification = classify_transport_response(result)
            result = replace(result, status_classification=classification)
            if classification in {"valid_html", "valid_no_data", "legitimate_not_found"}:
                self.metrics.scrapeops_successful_requests += 1
                self.state.put_fetch(result)
            else:
                self.metrics.scrapeops_failed_requests += 1
            return result
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}:{str(exc)[:200]}"
            self.metrics.scrapeops_failed_requests += 1
            return FetchResponse(
                url, url, 0, "", b"", 1,
                transport_used="scrapeops",
                transport_level=self._level(normalized_mode),
                status_classification="network_error",
                fallback_reason=fallback_reason,
                scrapeops_attempts=1,
                scrapeops_estimated_credit_cost=estimated,
                scrapeops_credit_cost_basis="billing_unknown",
            )


class StateStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "enrichment_state.sqlite3"
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS company_state (
              company_key TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              result_json TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              last_error TEXT NOT NULL DEFAULT '',
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fetch_cache (
              url TEXT PRIMARY KEY,
              final_url TEXT NOT NULL,
              status_code INTEGER NOT NULL,
              content_type TEXT NOT NULL,
              body_zlib BLOB NOT NULL,
              attempts INTEGER NOT NULL,
              transport_used TEXT NOT NULL DEFAULT 'webshare',
              transport_level TEXT NOT NULL DEFAULT 'webshare',
              status_classification TEXT NOT NULL DEFAULT '',
              fallback_reason TEXT NOT NULL DEFAULT '',
              webshare_attempts INTEGER NOT NULL DEFAULT 0,
              scrapeops_attempts INTEGER NOT NULL DEFAULT 0,
              scrapeops_credit_cost REAL NOT NULL DEFAULT 0,
              scrapeops_estimated_credit_cost REAL NOT NULL DEFAULT 0,
              scrapeops_credit_cost_basis TEXT NOT NULL DEFAULT '',
              fetched_at TEXT NOT NULL
            );
            """
        )
        for column, definition in (
            ("transport_used", "TEXT NOT NULL DEFAULT 'webshare'"),
            ("transport_level", "TEXT NOT NULL DEFAULT 'webshare'"),
            ("status_classification", "TEXT NOT NULL DEFAULT ''"),
            ("fallback_reason", "TEXT NOT NULL DEFAULT ''"),
            ("webshare_attempts", "INTEGER NOT NULL DEFAULT 0"),
            ("scrapeops_attempts", "INTEGER NOT NULL DEFAULT 0"),
            ("scrapeops_credit_cost", "REAL NOT NULL DEFAULT 0"),
            ("scrapeops_estimated_credit_cost", "REAL NOT NULL DEFAULT 0"),
            ("scrapeops_credit_cost_basis", "TEXT NOT NULL DEFAULT ''"),
        ):
            existing_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(fetch_cache)").fetchall()}
            if column not in existing_columns:
                self.connection.execute(f"ALTER TABLE fetch_cache ADD COLUMN {column} {definition}")
        self.connection.commit()

    def get_state(self, company_key: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT status, result_json, attempts, last_error, updated_at FROM company_state WHERE company_key=?", (company_key,)).fetchone()
        if not row:
            return None
        return {"status": row[0], "result": json.loads(row[1]), "attempts": row[2], "last_error": row[3], "updated_at": row[4]}

    def put_state(self, company_key: str, status: str, result: Mapping[str, Any], *, attempts: int = 0, last_error: str = "") -> None:
        self.connection.execute(
            "INSERT INTO company_state(company_key,status,result_json,attempts,last_error,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(company_key) DO UPDATE SET status=excluded.status,result_json=excluded.result_json,attempts=excluded.attempts,last_error=excluded.last_error,updated_at=excluded.updated_at",
            (company_key, status, json.dumps(dict(result), ensure_ascii=False, sort_keys=True), attempts, last_error[:1000], utc_now()),
        )
        self.connection.commit()

    def get_fetch(self, url: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT final_url,status_code,content_type,body_zlib,attempts,transport_used,transport_level,status_classification,fallback_reason,webshare_attempts,scrapeops_attempts,scrapeops_credit_cost,scrapeops_estimated_credit_cost,scrapeops_credit_cost_basis FROM fetch_cache WHERE url=?", (url,)).fetchone()
        if not row:
            return None
        return {
            "url": url,
            "final_url": row[0],
            "status_code": row[1],
            "content_type": row[2],
            "body": zlib.decompress(row[3]),
            "attempts": row[4],
            "transport_used": row[5],
            "transport_level": row[6],
            "status_classification": row[7],
            "fallback_reason": row[8],
            "webshare_attempts": row[9],
            "scrapeops_attempts": row[10],
            "scrapeops_credit_cost": row[11],
            "scrapeops_estimated_credit_cost": row[12],
            "scrapeops_credit_cost_basis": row[13],
        }

    def put_fetch(self, response: FetchResponse) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO fetch_cache(url,final_url,status_code,content_type,body_zlib,attempts,transport_used,transport_level,status_classification,fallback_reason,webshare_attempts,scrapeops_attempts,scrapeops_credit_cost,scrapeops_estimated_credit_cost,scrapeops_credit_cost_basis,fetched_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (response.url, response.final_url, response.status_code, response.content_type, zlib.compress(response.body, 6), response.attempts, response.transport_used, response.transport_level, response.status_classification or classify_transport_response(response), response.fallback_reason, response.webshare_attempts, response.scrapeops_attempts, response.scrapeops_credit_cost, response.scrapeops_estimated_credit_cost, response.scrapeops_credit_cost_basis, utc_now()),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


def _field_value(row: Mapping[str, Any], column: str) -> Any:
    return row.get(column, "")


def _set_if_empty(row: dict[str, Any], field: str, value: Any, source: str, provenance: dict[str, Any], conflicts: list[dict[str, Any]]) -> None:
    if value in (None, "", [], {}):
        return
    if not clean_text(row.get(field)):
        row[field] = value
        provenance[field] = {"source": source, "observed_at": utc_now()}
    elif row[field] != value:
        conflicts.append({"field": field, "existing": row[field], "candidate": value, "source": source})


def merge_locations(row: dict[str, Any], locations: list[dict[str, Any]], provenance: dict[str, Any]) -> None:
    if not locations:
        return
    existing = _json_load(row.get("locations_json")) or []
    if not isinstance(existing, list):
        existing = []
    keys = {(clean_text(item.get("city")), clean_text(item.get("country")), clean_text(item.get("address"))) for item in existing if isinstance(item, dict)}
    for location in locations:
        key = (clean_text(location.get("city")), clean_text(location.get("country")), clean_text(location.get("address")))
        if key not in keys:
            existing.append(location)
            keys.add(key)
    row["locations_json"] = json.dumps(existing, ensure_ascii=False, separators=(",", ":"))
    provenance["locations_json"] = {"source": "linkedin_company_page", "observed_at": utc_now()}


def enrich_row(base: Mapping[str, Any], facts: Mapping[str, Any], *, job_evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    row = dict(base)
    provenance: dict[str, Any] = _json_load(row.get("field_provenance_json")) or {}
    conflicts: list[dict[str, Any]] = _json_load(row.get("enrichment_conflicts_json")) or []
    job_evidence = dict(job_evidence or {})
    source = "linkedin_company_page"
    page_type = facts.get("page_type") or linkedin_page_type(row.get("linkedin_company_url"))
    candidate_id = next(iter(facts.get("raw_company_ids") or []), "")
    existing_id = clean_text(row.get("linkedin_company_id"))
    effective_id = candidate_id or existing_id
    row["linkedin_company_id"] = effective_id
    row["linkedin_company_id_source"] = facts.get("id_source", "") or ("existing_master" if existing_id else "")
    row["linkedin_company_id_status"] = facts.get("id_status", "MISSING") if candidate_id else (row.get("linkedin_company_id_status") or ("CANDIDATE" if existing_id else "MISSING"))
    row["linkedin_company_id_confidence"] = facts.get("id_confidence", 0.0)
    row["linkedin_company_id_validation_score"] = facts.get("id_score", 0)
    row["linkedin_company_id_validation_reasons_json"] = json.dumps(facts.get("id_reasons", {}), ensure_ascii=False, sort_keys=True)
    row["linkedin_company_id_resolved_at"] = facts.get("resolved_at", "") if candidate_id else row.get("linkedin_company_id_resolved_at", "")
    row["linkedin_company_id_validated_at"] = facts.get("validated_at", "") if facts.get("id_status") in {"VALIDATED", "HIGH_CONFIDENCE"} else ""
    transport = dict(facts.get("transport") or {})
    row["linkedin_transport_used"] = transport.get("transport_used", "")
    row["linkedin_transport_level"] = transport.get("transport_level", "")
    row["linkedin_transport_status_classification"] = transport.get("status_classification", "")
    row["linkedin_transport_fallback_reason"] = transport.get("fallback_reason", "")
    row["linkedin_transport_scrapeops_credit_cost"] = transport.get("scrapeops_credit_cost", 0) or 0
    row["linkedin_transport_trace_json"] = json.dumps(facts.get("transport_trace", []), ensure_ascii=False, sort_keys=True)
    row["linkedin_company_access_status"] = facts.get("access_status", "")
    row["linkedin_display_name"] = facts.get("display_name", "") or row.get("linkedin_display_name", "")
    row["linkedin_tagline"] = facts.get("tagline", "") or row.get("linkedin_tagline", "")
    row["linkedin_description"] = facts.get("description", "") or row.get("linkedin_description", "")
    row["linkedin_industry"] = facts.get("industry", "") or row.get("linkedin_industry", "")
    row["linkedin_company_type"] = facts.get("company_type", "") or row.get("linkedin_company_type", "")
    row["linkedin_founded_year"] = facts.get("founded_year", "") or row.get("linkedin_founded_year", "")
    row["linkedin_website_url"] = facts.get("website_url", "") or row.get("linkedin_website_url", "")
    row["linkedin_website_domain"] = facts.get("website_domain", "") or row.get("linkedin_website_domain", "")
    row["website_domain_match"] = bool(row.get("domain") and facts.get("website_domain") and root_domain(row.get("domain")) == root_domain(facts.get("website_domain")))
    row["linkedin_employee_count"] = facts.get("employee_count") or row.get("linkedin_employee_count", "")
    row["linkedin_employee_count_range"] = facts.get("employee_range", "") or row.get("linkedin_employee_count_range", "")
    row["linkedin_associated_employee_count"] = facts.get("associated_employee_count") or row.get("linkedin_associated_employee_count", "")
    row["linkedin_follower_count_observed_at"] = utc_now() if facts.get("follower_count") is not None else row.get("linkedin_follower_count_observed_at", "")
    row["linkedin_headquarters_display"] = facts.get("headquarters", {}).get("display", "") or row.get("linkedin_headquarters_display", "")
    row["linkedin_specialties_json"] = json.dumps(facts.get("specialties", []), ensure_ascii=False) if facts.get("specialties") else row.get("linkedin_specialties_json", "")
    row["linkedin_logo_url"] = facts.get("logo_url", "") or row.get("linkedin_logo_url", "")
    row["linkedin_cover_image_url"] = facts.get("cover_image_url", "") or row.get("linkedin_cover_image_url", "")
    _set_if_empty(row, "career_url_candidate", facts.get("career_url_candidate"), "linkedin_company_page_external_link", provenance, conflicts)
    _set_if_empty(row, "career_url_source", "linkedin_company_page_external_link" if facts.get("career_url_candidate") else "", "linkedin_company_page", provenance, conflicts)
    for field, value in {
        "website_url": facts.get("website_url"),
        "domain": facts.get("website_domain"),
        "description": facts.get("description"),
        "industry": facts.get("industry"),
        "company_type": facts.get("company_type"),
        "founded_year": facts.get("founded_year"),
        "headquarters_display": facts.get("headquarters", {}).get("display"),
        "headquarters_city": facts.get("headquarters", {}).get("city"),
        "headquarters_region": facts.get("headquarters", {}).get("region"),
        "headquarters_country": facts.get("headquarters", {}).get("country"),
        "headquarters_country_code": facts.get("headquarters", {}).get("country_code"),
        "linkedin_follower_count": facts.get("follower_count"),
        "logo_url": facts.get("logo_url"),
        "logo_source": "LinkedIn",
    }.items():
        _set_if_empty(row, field, value, source, provenance, conflicts)
    merge_locations(row, facts.get("locations", []), provenance)
    row["linkedin_has_services"] = bool(facts.get("has_services"))
    row["linkedin_has_products"] = bool(facts.get("has_products"))
    row["linkedin_has_life_page"] = bool(facts.get("has_life_page"))
    row["linkedin_has_people_page"] = bool(facts.get("has_people_page"))
    row["linkedin_has_jobs_page"] = bool(facts.get("has_jobs_page"))
    row["linkedin_jobs_url"] = job_evidence.get("jobs_url") or next(iter(facts.get("jobs_links") or []), "")
    row["linkedin_has_jobs"] = bool(job_evidence.get("count", 0))
    row["linkedin_job_validation_count"] = job_evidence.get("count", 0)
    row["linkedin_jobs_last_checked_at"] = job_evidence.get("checked_at", "")
    row["linkedin_current_jobs_count_observed"] = job_evidence.get("count", "")
    row["has_current_linkedin_jobs"] = bool(job_evidence.get("count", 0))
    row["linkedin_jobs_sampled"] = bool(job_evidence.get("sampled"))
    staffing, staffing_confidence, staffing_reasons = detect_staffing(row, facts)
    row.update(app_relevance(row, facts | {"job_validation_count": job_evidence.get("count", 0), "jobs_sampled": job_evidence.get("sampled")}, row.get("linkedin_company_id_status", "MISSING")))
    row["is_staffing_or_recruiting_company"] = staffing
    row["staffing_detection_confidence"] = staffing_confidence
    row["staffing_detection_reasons_json"] = json.dumps(staffing_reasons, ensure_ascii=False)
    row["field_provenance_json"] = json.dumps(provenance, ensure_ascii=False, sort_keys=True)
    row["enrichment_conflicts_json"] = json.dumps(conflicts, ensure_ascii=False, sort_keys=True)
    return row


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field, "") for field in fieldnames})
    os.replace(temporary, path)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    if not fieldnames:
        raise ValueError(f"CSV has no header: {path}")
    return fieldnames, rows


def choose_stratified_sample(rows: list[dict[str, str]], limit: int, seed: int = 20260823) -> list[dict[str, str]]:
    if limit >= len(rows):
        return list(rows)
    rng = random.Random(seed)
    buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        location = " ".join(clean_text(row.get(key)) for key in ("headquarters_country", "headquarters_country_code", "headquarters_display", "locations_json"))
        bucket = "germany" if "germany" in location.casefold() or "deutschland" in location.casefold() or "\"DE\"" in location else "international"
        if not row.get("linkedin_company_url"):
            bucket += ":missing_url"
        elif not row.get("description") and not row.get("industry"):
            bucket += ":incomplete"
        elif "staff" in " ".join(str(row.get(key) or "") for key in ("company_name", "industry", "description")).casefold():
            bucket += ":staffing_candidate"
        else:
            bucket += ":regular"
        buckets[bucket].append(row)
    selected: list[dict[str, str]] = []
    per_bucket = max(1, limit // max(1, len(buckets)))
    for values in buckets.values():
        selected.extend(rng.sample(values, min(per_bucket, len(values))))
    remaining = [row for row in rows if row not in selected]
    if len(selected) < limit:
        selected.extend(rng.sample(remaining, min(limit - len(selected), len(remaining))))
    return selected[:limit]


def _status_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row.get("linkedin_company_id_status") or "MISSING") for row in rows)
    return dict(sorted(counts.items()))


def company_state_key(row: Mapping[str, Any], index: int) -> str:
    canonical_id = clean_text(row.get("canonical_CompanyID"))
    if canonical_id and canonical_id.casefold() not in PLACEHOLDER_CANONICAL_IDS:
        return canonical_id
    material = "\x1f".join(
        clean_text(row.get(field))
        for field in ("companyenrich_id", "source_row_numbers", "company_name", "linkedin_company_url", "domain")
    ) + f"\x1f{index}"
    return "row:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


class EnrichmentPipeline:
    def __init__(self, *, fetcher: HttpFetcher, state: StateStore, metrics: PipelineMetrics | None = None, job_geo_id: str = ""):
        self.fetcher = fetcher
        self.state = state
        self.metrics = metrics or PipelineMetrics()
        self.job_geo_id = job_geo_id

    def _fetch_page(self, url: str, *, kind: str = "company_page") -> tuple[dict[str, Any], FetchResponse]:
        response = self.fetcher.fetch(url, kind=kind)
        facts = parse_linkedin_page(response.body.decode("utf-8", errors="replace"), url, response.status_code)
        facts["requested_url"] = url
        facts["final_url"] = normalize_linkedin_url(response.final_url) or response.final_url
        facts["transport"] = response.transport_record()
        facts["transport_trace"] = list(response.transport_trace or (response.transport_record(),))
        return facts, response

    def _resolve_missing_url(self, row: Mapping[str, str], *, job_validation: bool) -> dict[str, Any]:
        name = clean_text(row.get("company_name"))
        if not name:
            return enrich_row(row, {"id_status": "MISSING", "page_type": "", "page_valid": False})
        search_url = "https://www.linkedin.com/search/results/companies/?keywords=" + quote(name)
        search_response = self.fetcher.fetch(search_url, kind="company_search")
        search_trace = list(search_response.transport_trace or (search_response.transport_record(),))
        if search_response.status_code >= 400:
            return enrich_row(row, {
                "id_status": "NO_ID_EXPOSED",
                "page_type": "",
                "page_valid": False,
                "id_source": "company_name_search",
                "id_reasons": {"search_status_code": search_response.status_code},
                "transport": search_response.transport_record(),
                "transport_trace": search_trace,
                "access_status": classify_transport_response(search_response),
            })
        candidates = extract_company_candidates(search_response.body.decode("utf-8", errors="replace"))
        scored: list[tuple[float, dict[str, Any]]] = []
        for candidate in candidates[:2]:
            candidate_facts, _ = self._fetch_page(candidate["url"])
            similarity = name_similarity(name, candidate_facts.get("display_name") or candidate.get("text"))
            candidate_facts["candidate_url"] = candidate["url"]
            candidate_facts["candidate_name_similarity"] = similarity
            scored.append((similarity, candidate_facts))
        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored or scored[0][0] < 0.75 or (len(scored) > 1 and scored[0][0] == scored[1][0]):
            return enrich_row(row, {
                "id_status": "NO_ID_EXPOSED",
                "page_type": "",
                "page_valid": bool(candidates),
                "id_source": "company_name_search",
                "id_reasons": {"candidate_count": len(candidates), "best_name_similarity": scored[0][0] if scored else 0.0},
                "transport": search_response.transport_record(),
                "transport_trace": search_trace,
                "access_status": classify_transport_response(search_response),
            })
        facts = scored[0][1]
        facts["transport_trace"] = search_trace + list(facts.get("transport_trace") or [])
        facts["raw_company_ids"] = sorted(facts.get("raw_company_ids") or [])
        candidate_id = next(iter(facts["raw_company_ids"]), "")
        evidence = {
            "exact_page_see_all_id": False,
            "slug_match": False,
            "domain_match": bool(row.get("domain") and facts.get("website_domain") and root_domain(row.get("domain")) == root_domain(facts.get("website_domain"))),
            "job_card_company_match_rate": None,
            "name_match": scored[0][0] >= 0.75,
            "headquarters_match": False,
            "multiple_incompatible_ids": len(facts["raw_company_ids"]) > 1,
            "severe_name_mismatch": scored[0][0] < 0.35,
        }
        score, status, confidence = identity_validation_score(evidence)
        if len(facts["raw_company_ids"]) > 1:
            status = "AMBIGUOUS"
        facts.update({
            "id_source": "company_name_search",
            "id_status": status if candidate_id else "NO_ID_EXPOSED",
            "id_score": score,
            "id_confidence": confidence,
            "id_reasons": evidence,
            "resolved_at": utc_now() if candidate_id else "",
            "validated_at": utc_now() if status in {"VALIDATED", "HIGH_CONFIDENCE"} else "",
        })
        result = enrich_row(row, facts)
        if facts.get("candidate_url"):
            result["linkedin_company_url"] = facts["candidate_url"]
            result["linkedin_resolved_url"] = facts["candidate_url"]
        return result

    def _resolve_row(self, row: Mapping[str, str], *, job_validation: bool = True) -> dict[str, Any]:
        begin_company = getattr(self.fetcher, "begin_company", None)
        if callable(begin_company):
            begin_company(company_state_key(row, 0))
        requested_url = normalize_linkedin_url(row.get("linkedin_company_url"))
        if not requested_url:
            return self._resolve_missing_url(row, job_validation=job_validation)
        page_facts, page_response = self._fetch_page(requested_url, kind="company_page")
        ids = set(page_facts.get("raw_company_ids") or [])
        id_source = "page_metadata" if ids else ""
        jobs_url = urljoin(requested_url, "jobs/")
        jobs_facts = {}
        jobs_response = None
        if page_facts.get("page_valid") or not ids:
            jobs_facts, jobs_response = self._fetch_page(jobs_url, kind="company_jobs")
            page_facts["transport_trace"].extend(jobs_facts.get("transport_trace") or [])
            ids.update(jobs_facts.get("raw_company_ids") or [])
            if jobs_facts.get("raw_company_ids"):
                id_source = "company_jobs_see_all"
        candidate_id = next(iter(ids), "") if len(ids) == 1 else ""
        job_evidence = {"jobs_url": jobs_url, "count": 0, "sampled": False, "checked_at": ""}
        if candidate_id and job_validation:
            self.metrics.job_validation_attempted += 1
            validation_url = f"https://www.linkedin.com/jobs/search/?f_C={candidate_id}"
            if self.job_geo_id:
                validation_url += f"&geoId={quote(self.job_geo_id)}"
            try:
                validation_response = self.fetcher.fetch(validation_url, kind="job_validation")
                cards = extract_job_cards(validation_response.body.decode("utf-8", errors="replace"))
                comparison = compare_job_cards(cards, candidate_id, row.get("company_name", ""), linkedin_slug(requested_url))
                job_evidence = {"jobs_url": validation_url, "count": comparison["count"], "match_rate": comparison["match_rate"], "sampled": True, "checked_at": utc_now()}
                page_facts["transport_trace"].append(validation_response.transport_record())
                if comparison["count"]:
                    self.metrics.job_validation_successful += 1
                else:
                    self.metrics.job_validation_no_jobs += 1
            except Exception:
                job_evidence["checked_at"] = utc_now()
        final_url = page_facts.get("final_url") or requested_url
        evidence = {
            "exact_page_see_all_id": bool(candidate_id and len(ids) == 1 and jobs_facts.get("raw_company_ids")),
            "slug_match": bool(linkedin_slug(final_url) == linkedin_slug(requested_url) and linkedin_slug(requested_url)),
            "domain_match": bool(row.get("domain") and page_facts.get("website_domain") and root_domain(row.get("domain")) == root_domain(page_facts.get("website_domain"))),
            "domain_conflict": bool(row.get("domain") and page_facts.get("website_domain") and root_domain(row.get("domain")) != root_domain(page_facts.get("website_domain"))),
            "job_card_company_match_rate": job_evidence.get("match_rate"),
            "name_match": name_similarity(row.get("company_name"), page_facts.get("display_name")) >= 0.75,
            "headquarters_match": bool(page_facts.get("headquarters", {}).get("country_code") and page_facts.get("headquarters", {}).get("country_code") == row.get("headquarters_country_code")),
            "multiple_incompatible_ids": len(ids) > 1,
            "severe_name_mismatch": bool(page_facts.get("display_name") and name_similarity(row.get("company_name"), page_facts.get("display_name")) < 0.35),
        }
        score, status, confidence = identity_validation_score(evidence)
        if len(ids) > 1:
            status = "AMBIGUOUS"
        if evidence["severe_name_mismatch"] or evidence["domain_conflict"]:
            status = "MISMATCH"
        page_classification = classify_transport_response(page_response)
        jobs_classification = classify_transport_response(jobs_response) if jobs_response is not None else ""
        if page_classification in TRANSPORT_ACCESS_FAILURES or (not candidate_id and jobs_classification in TRANSPORT_ACCESS_FAILURES):
            status = "ACCESS_UNRESOLVED"
        elif page_classification == "legitimate_not_found" or not page_facts.get("page_valid"):
            status = "PAGE_NOT_FOUND"
        page_facts.update({
            "raw_company_ids": sorted(ids),
            "id_source": id_source,
            "id_status": status if candidate_id else "NO_ID_EXPOSED",
            "id_score": score,
            "id_confidence": confidence,
            "id_reasons": evidence,
            "resolved_at": utc_now() if candidate_id else "",
            "validated_at": utc_now() if status in {"VALIDATED", "HIGH_CONFIDENCE"} else "",
            "job_validation_count": job_evidence.get("count", 0),
            "access_status": page_classification,
        })
        result = enrich_row(row, page_facts, job_evidence=job_evidence)
        result["linkedin_resolved_url"] = requested_url
        return result

    def run_rows(self, rows: list[dict[str, str]], *, limit: int | None = None, force: bool = False, job_validation: bool = True, checkpoint_path: Path | None = None, seed: int = 20260823) -> list[dict[str, Any]]:
        fieldnames = list(rows[0].keys()) if rows else []
        selected = choose_stratified_sample(rows, limit, seed) if limit else rows
        results = []
        for index, row in enumerate(selected):
            key = company_state_key(row, index)
            saved = None if force else self.state.get_state(key)
            if saved and saved["status"] in {"COMPLETE", "VALIDATED", "HIGH_CONFIDENCE", "CANDIDATE", "AMBIGUOUS", "MISMATCH", "MISSING", "PAGE_NOT_FOUND", "NO_ID_EXPOSED", "ACCESS_UNRESOLVED"}:
                enriched = saved["result"]
            else:
                try:
                    enriched = self._resolve_row(row, job_validation=job_validation)
                    status = enriched.get("linkedin_company_id_status") or "MISSING"
                    self.state.put_state(key, "COMPLETE" if status in ALLOWED_STATUSES else "FAILED", enriched)
                except Exception as exc:
                    enriched = enrich_row(row, {"id_status": "MISSING", "page_valid": False})
                    enriched["enrichment_error"] = str(exc)[:500]
                    self.state.put_state(key, "FAILED", enriched, attempts=1, last_error=str(exc))
            results.append(enriched)
            if checkpoint_path and (len(results) % 25 == 0 or len(results) == len(selected)):
                output_fields = fieldnames + [field for field in NEW_COLUMNS if field not in fieldnames]
                write_csv(checkpoint_path, output_fields, results)
        return results


def write_exception_files(output_dir: Path, rows: list[Mapping[str, Any]], *, seed: int = 20260823) -> dict[str, int]:
    base_columns = ["canonical_CompanyID", "company_name", "linkedin_company_url", "linkedin_resolved_url", "linkedin_company_id", "linkedin_company_id_status", "linkedin_company_id_confidence", "linkedin_company_id_source", "linkedin_company_id_validation_score", "linkedin_company_id_validation_reasons_json", "enrichment_conflicts_json"]
    all_columns = list(dict.fromkeys(base_columns + [key for row in rows for key in row.keys()]))
    counts = {}
    for status, name in (("AMBIGUOUS", "linkedin_company_ambiguous_review.csv"), ("MISMATCH", "linkedin_company_mismatch_review.csv")):
        selected = [row for row in rows if row.get("linkedin_company_id_status") == status]
        write_csv(output_dir / name, all_columns, selected)
        counts[status] = len(selected)
    unresolved_statuses = {"MISSING", "PAGE_NOT_FOUND", "NO_ID_EXPOSED", "ACCESS_UNRESOLVED"}
    unresolved = [row for row in rows if row.get("linkedin_company_id_status") in unresolved_statuses]
    write_csv(output_dir / "linkedin_company_unresolved_review.csv", all_columns, unresolved)
    for status in unresolved_statuses:
        counts[status] = sum(row.get("linkedin_company_id_status") == status for row in rows)
    validation_limit = min(250, len(rows))
    validation_sample = choose_stratified_sample([dict(row) for row in rows], validation_limit, seed) if validation_limit else []
    write_csv(output_dir / "linkedin_company_validation_sample.csv", all_columns, validation_sample)
    counts["validation_sample"] = len(validation_sample)
    return counts


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_output(path: Path, expected_rows: int) -> dict[str, Any]:
    fields, output_rows = read_csv(path)
    canonical_ids = [clean_text(row.get("canonical_CompanyID")) for row in output_rows]
    nonempty_ids = [value for value in canonical_ids if value]
    duplicate_ids = sorted({value for value in nonempty_ids if nonempty_ids.count(value) > 1})
    duplicate_non_placeholder_ids = [value for value in duplicate_ids if value.casefold() not in PLACEHOLDER_CANONICAL_IDS]
    if len(output_rows) != expected_rows:
        raise ValueError(f"output_row_count_mismatch:{len(output_rows)}:{expected_rows}")
    if duplicate_non_placeholder_ids:
        raise ValueError(f"duplicate_canonical_CompanyID:{duplicate_non_placeholder_ids[:5]}")
    return {
        "row_count": len(output_rows),
        "column_count": len(fields),
        "duplicate_canonical_CompanyID_count": len(duplicate_ids),
        "duplicate_non_placeholder_canonical_CompanyID_count": len(duplicate_non_placeholder_ids),
        "placeholder_canonical_CompanyID_count": sum(value.casefold() in PLACEHOLDER_CANONICAL_IDS for value in canonical_ids),
    }


def build_report(input_path: Path, output_path: Path, rows: list[Mapping[str, Any]], metrics: PipelineMetrics, *, runtime_seconds: float, sample: bool, input_rows: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    input_rows = input_rows or []
    ids = [str(row.get("linkedin_company_id") or "") for row in rows if row.get("linkedin_company_id")]
    resolved_with_scrapeops = sum(bool(row.get("linkedin_company_id")) and "scrapeops" in str(row.get("linkedin_transport_trace_json") or "") for row in rows)
    validated_with_scrapeops = sum(row.get("linkedin_company_id_status") in {"VALIDATED", "HIGH_CONFIDENCE"} and "scrapeops" in str(row.get("linkedin_transport_trace_json") or "") for row in rows)
    report = {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "sample_run": sample,
        "total_companies": len(rows),
        "linkedin_urls_present": sum(bool(row.get("linkedin_company_url")) for row in rows),
        "linkedin_urls_missing": sum(not bool(row.get("linkedin_company_url")) for row in rows),
        "linkedin_pages_valid": sum(bool(row.get("has_valid_linkedin_page")) for row in rows),
        "linkedin_pages_invalid": sum(not bool(row.get("has_valid_linkedin_page")) for row in rows),
        "linkedin_ids_already_present": sum(bool(row.get("linkedin_company_id")) for row in rows if row.get("linkedin_company_id_source") == "existing_master"),
        "linkedin_ids_resolved": len(ids),
        "linkedin_ids_validated": sum(row.get("linkedin_company_id_status") == "VALIDATED" for row in rows),
        "linkedin_ids_high_confidence": sum(row.get("linkedin_company_id_status") == "HIGH_CONFIDENCE" for row in rows),
        "linkedin_ids_candidate": sum(row.get("linkedin_company_id_status") == "CANDIDATE" for row in rows),
        "linkedin_ids_ambiguous": sum(row.get("linkedin_company_id_status") == "AMBIGUOUS" for row in rows),
        "linkedin_ids_mismatch": sum(row.get("linkedin_company_id_status") == "MISMATCH" for row in rows),
        "linkedin_ids_access_unresolved": sum(row.get("linkedin_company_id_status") == "ACCESS_UNRESOLVED" for row in rows),
        "linkedin_ids_missing": sum(not row.get("linkedin_company_id") for row in rows),
        "domains_matched": sum(row.get("website_domain_match") is True for row in rows),
        "domains_conflicted": sum(bool(_json_load(row.get("enrichment_conflicts_json"))) and "website_url" in _json_text(row.get("enrichment_conflicts_json")) for row in rows),
        "company_names_matched": sum(bool(row.get("linkedin_display_name")) and name_similarity(row.get("company_name"), row.get("linkedin_display_name")) >= 0.75 for row in rows),
        "company_names_conflicted": sum(bool(row.get("linkedin_display_name")) and name_similarity(row.get("company_name"), row.get("linkedin_display_name")) < 0.35 for row in rows),
        "job_validation_attempted": metrics.job_validation_attempted,
        "job_validation_successful": metrics.job_validation_successful,
        "job_validation_no_jobs": metrics.job_validation_no_jobs,
        "fields_filled": {field: sum(bool(row.get(field)) for row in rows) for field in ("website_url", "industry", "company_type", "employee_count", "employee_count_range", "linkedin_follower_count", "founded_year", "headquarters_display", "locations_json", "description", "logo_url", "linkedin_specialties_json")},
        "field_fill_rates_before_after": {
            field: {
                "before_count": sum(bool(row.get(field)) for row in input_rows),
                "after_count": sum(bool(row.get(field)) for row in rows),
                "before_rate": round(sum(bool(row.get(field)) for row in input_rows) / len(input_rows), 4) if input_rows else 0.0,
                "after_rate": round(sum(bool(row.get(field)) for row in rows) / len(rows), 4) if rows else 0.0,
            }
            for field in ("linkedin_company_url", "linkedin_company_id", "website_url", "industry", "company_type", "employee_count", "employee_count_range", "linkedin_follower_count", "founded_year", "headquarters_display", "locations_json", "description", "logo_url")
        },
        "staffing_companies_detected": sum(bool(row.get("is_staffing_or_recruiting_company")) for row in rows),
        "education_pages_detected": sum(bool(row.get("is_school_or_education_page")) for row in rows),
        "showcase_pages_detected": sum(bool(row.get("is_showcase_page")) for row in rows),
        "nonprofits_detected": sum(bool(row.get("is_nonprofit")) for row in rows),
        "companies_with_germany_location": sum(bool(row.get("has_germany_location")) for row in rows),
        "companies_with_current_linkedin_jobs": sum(bool(row.get("has_current_linkedin_jobs")) for row in rows),
        "completeness_score_distribution": dict(Counter(str(row.get("company_profile_completeness_score")) for row in rows)),
        "company_size_distribution": dict(Counter(str(row.get("company_size_bucket") or "UNKNOWN") for row in rows)),
        "industry_distribution": dict(Counter(str(row.get("industry") or "UNKNOWN") for row in rows).most_common(100)),
        "country_distribution": dict(Counter(str(row.get("headquarters_country") or "UNKNOWN") for row in rows).most_common(100)),
        "requests": metrics.requests,
        "successful_requests": metrics.successful_requests,
        "429s": metrics.status_429,
        "403s": metrics.status_403,
        "999s": metrics.status_999,
        "timeouts": metrics.timeouts,
        "proxy_errors": metrics.proxy_errors,
        "retries": metrics.retries,
        "proxy_rotations": metrics.proxy_rotations,
        "cache_hits": metrics.cache_hits,
        "fetch_failures": metrics.fetch_failures,
        "scrapeops_requests": metrics.scrapeops_requests,
        "scrapeops_successful_requests": metrics.scrapeops_successful_requests,
        "scrapeops_failed_requests": metrics.scrapeops_failed_requests,
        "scrapeops_default_requests": metrics.scrapeops_default_requests,
        "scrapeops_residential_requests": metrics.scrapeops_residential_requests,
        "scrapeops_js_requests": metrics.scrapeops_js_requests,
        "scrapeops_credits_used": metrics.scrapeops_credits_used,
        "scrapeops_budget_exhausted": metrics.scrapeops_budget_exhausted,
        "scrapeops_company_budget_exhausted": metrics.scrapeops_company_budget_exhausted,
        "scrapeops_fallback_attempts": metrics.scrapeops_fallback_attempts,
        "companies_resolved_without_scrapeops": sum(bool(row.get("linkedin_company_id")) and "scrapeops" not in str(row.get("linkedin_transport_trace_json") or "") for row in rows),
        "companies_resolved_with_scrapeops": resolved_with_scrapeops,
        "scrapeops_credits_per_success": round(metrics.scrapeops_credits_used / metrics.scrapeops_successful_requests, 3) if metrics.scrapeops_successful_requests else 0.0,
        "scrapeops_credits_per_resolved_company": round(metrics.scrapeops_credits_used / resolved_with_scrapeops, 3) if resolved_with_scrapeops else 0.0,
        "scrapeops_credits_per_validated_company": round(metrics.scrapeops_credits_used / validated_with_scrapeops, 3) if validated_with_scrapeops else 0.0,
        "runtime_seconds": round(runtime_seconds, 3),
        "status_distribution": _status_counts(rows),
    }
    return report


def run_pipeline(*, input_path: Path, output_path: Path, state_dir: Path, report_path: Path, limit: int | None = None, force: bool = False, job_validation: bool = True, seed: int = 20260823, transport: str = "webshare", scrapeops_fallback: bool = False, scrapeops_modes: Iterable[str] = ("basic",), scrapeops_credit_budget: float = 0.0, scrapeops_max_credit_cost: float = 0.0, max_scrapeops_attempts_per_company: int = 3, scrapeops_job_validation_fallback: bool = False, webshare_max_attempts: int = 2, webshare_timeout: float = 30.0, scrapeops_timeout: int = 30) -> dict[str, Any]:
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    if input_path == output_path:
        raise ValueError("source_overwrite_forbidden")
    start = time.monotonic()
    fieldnames, rows = read_csv(input_path)
    source_hash_before = file_sha256(input_path)
    report_input_rows = choose_stratified_sample(rows, limit, seed) if limit else rows
    state = StateStore(state_dir)
    metrics = PipelineMetrics()
    normalized_transport = str(transport or "webshare").casefold()
    if normalized_transport not in {"webshare", "scrapeops", "hybrid"}:
        state.close()
        raise ValueError(f"unsupported_transport:{transport}")
    webshare = CachedWebshareFetcher(state, timeout=max(3.0, float(webshare_timeout)), metrics=metrics, retries=max(0, int(webshare_max_attempts) - 1))
    normalized_modes = tuple(dict.fromkeys(str(mode).strip() for mode in scrapeops_modes if str(mode).strip())) or ("basic",)
    scrapeops = None
    scrapeops_error = ""
    if normalized_transport in {"scrapeops", "hybrid"} or scrapeops_fallback:
        try:
            scrapeops = ScrapeOpsFetcher(
                state,
                metrics=metrics,
                timeout=max(3, int(scrapeops_timeout)),
                max_credit_cost=scrapeops_max_credit_cost,
                credit_budget=scrapeops_credit_budget,
                default_mode=normalized_modes[0],
            )
        except RuntimeError as exc:
            scrapeops_error = str(exc)
            if normalized_transport == "scrapeops":
                state.close()
                raise
    if normalized_transport == "scrapeops":
        fetcher: HttpFetcher = scrapeops
    elif normalized_transport == "hybrid" or scrapeops_fallback:
        fetcher = HybridLinkedInFetcher(
            webshare=webshare,
            scrapeops=scrapeops,
            scrapeops_modes=normalized_modes,
            fallback_enabled=True,
            metrics=metrics,
            max_scrapeops_attempts_per_company=max_scrapeops_attempts_per_company,
            scrapeops_job_validation_fallback=scrapeops_job_validation_fallback,
        )
    else:
        fetcher = webshare
    pipeline = EnrichmentPipeline(fetcher=fetcher, state=state, metrics=metrics, job_geo_id=os.getenv("LINKEDIN_JOB_GEO_ID", ""))
    try:
        results = pipeline.run_rows(rows, limit=limit, force=force, job_validation=job_validation, checkpoint_path=output_path, seed=seed)
        output_fields = fieldnames + [field for field in NEW_COLUMNS if field not in fieldnames]
        write_csv(output_path, output_fields, results)
        output_integrity = validate_output(output_path, len(results))
        exceptions = write_exception_files(output_path.parent, results, seed=seed)
        report = build_report(input_path, output_path, results, metrics, runtime_seconds=time.monotonic() - start, sample=limit is not None, input_rows=report_input_rows)
        report["exception_counts"] = exceptions
        report["output_integrity"] = output_integrity
        report["source_sha256_before"] = source_hash_before
        report["source_sha256_after"] = file_sha256(input_path)
        report["source_unchanged"] = source_hash_before == report["source_sha256_after"]
        report["transport"] = normalized_transport
        report["scrapeops_fallback_enabled"] = bool(scrapeops_fallback or normalized_transport == "hybrid")
        report["scrapeops_modes"] = list(normalized_modes)
        report["scrapeops_configuration_error"] = scrapeops_error
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report
    finally:
        state.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=SOURCE_DEFAULT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None, help="Bounded deterministic sample size; omit for the full input.")
    parser.add_argument("--force", "--force-refresh", dest="force", action="store_true")
    parser.add_argument("--transport", choices=("webshare", "scrapeops", "hybrid"), default="hybrid")
    parser.add_argument("--scrapeops-fallback", action="store_true")
    parser.add_argument("--scrapeops-credit-budget", type=float, default=0.0)
    parser.add_argument("--scrapeops-max-credit-cost", type=float, default=0.0)
    parser.add_argument("--max-scrapeops-attempts-per-company", type=int, default=3)
    parser.add_argument("--scrapeops-residential-fallback", action="store_true")
    parser.add_argument("--scrapeops-js-fallback", action="store_true")
    parser.add_argument("--scrapeops-job-validation-fallback", action="store_true")
    parser.add_argument("--webshare-max-attempts", type=int, default=2)
    parser.add_argument("--no-job-validation", action="store_true")
    args = parser.parse_args(argv)
    input_path = args.input.resolve()
    output = (args.output or input_path.with_name(f"{input_path.stem}_linkedin_enriched.csv")).resolve()
    state_dir = (args.state_dir or input_path.parent / "linkedin_company_enrichment_state").resolve()
    report = (args.report or input_path.parent / "linkedin_company_enrichment_report.json").resolve()
    modes = ["basic"]
    if args.scrapeops_residential_fallback:
        modes.append("residential")
    if args.scrapeops_js_fallback:
        modes.append("render_js_residential")
    summary = run_pipeline(
        input_path=input_path,
        output_path=output,
        state_dir=state_dir,
        report_path=report,
        limit=args.limit,
        force=args.force,
        job_validation=not args.no_job_validation,
        transport=args.transport,
        scrapeops_fallback=args.scrapeops_fallback,
        scrapeops_modes=modes,
        scrapeops_credit_budget=args.scrapeops_credit_budget,
        scrapeops_max_credit_cost=args.scrapeops_max_credit_cost,
        max_scrapeops_attempts_per_company=args.max_scrapeops_attempts_per_company,
        scrapeops_job_validation_fallback=args.scrapeops_job_validation_fallback,
        webshare_max_attempts=args.webshare_max_attempts,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
