"""Consolidate and audit the Master-Company-Url CSV without changing its source.

The cleaner intentionally uses only the Python standard library. It performs no
network access and writes every requested artifact beneath an output directory.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import html
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit


DEFAULT_INPUT = Path("Company-Urls/Master-Company-Url/Master-Company-Url.csv")
DEFAULT_OUTPUT = Path("Company-Urls/Master-Company-Url/cleaned")

CANONICAL_COLUMNS = [
    "company_id",
    "companyenrich_id",
    "source_row_numbers",
    "merge_basis",
    "company_name",
    "legal_name",
    "website_url",
    "domain",
    "linkedin_company_url",
    "linkedin_slug",
    "linkedin_company_id",
    "linkedin_page_type",
    "headquarters_city",
    "headquarters_region",
    "headquarters_country",
    "headquarters_country_code",
    "headquarters_display",
    "locations_json",
    "industry",
    "industries_json",
    "categories_json",
    "company_type",
    "employee_count",
    "employee_count_range",
    "employee_count_source",
    "linkedin_follower_count",
    "founded_year",
    "revenue_range",
    "description",
    "seo_description",
    "tagline",
    "specialties_json",
    "keywords_json",
    "technologies_json",
    "subsidiaries_json",
    "naics_codes_json",
    "financial_json",
    "socials_json",
    "logo_url",
    "logo_source",
    "cover_image_url",
    "page_rank",
    "record_sources",
    "linkedin_page_valid",
    "enrichment_status",
    "last_enriched_at",
]

COLUMN_GROUPS: dict[str, list[str]] = {
    "company_name": ["company_name", "companyenrich_name", "companyenrich_match_name", "company"],
    "legal_name": ["companyenrich_legal_name"],
    "website_url": ["website", "website_url", "companyenrich_website", "companyenrich_domain", "companyenrich_match_domain", "domain"],
    "domain": ["website", "website_url", "companyenrich_website", "companyenrich_domain", "companyenrich_match_domain", "domain"],
    "linkedin_company_url": ["Company-LinkedIn-url", "linkedin_company_url"],
    "company_id": ["company_id"],
    "companyenrich_id": ["companyenrich_id"],
    "linkedin_company_id": ["linkedin_company_id"],
    "linkedin_slug": ["linkedin_slug"],
    "linkedin_page_type": ["linkedin_page_type"],
    "industry": ["industry", "companyenrich_industry", "sectors_active", "companyenrich_industries_json"],
    "industries_json": ["sectors_active", "industry", "companyenrich_industry", "companyenrich_industries_json"],
    "categories_json": ["companyenrich_categories_json"],
    "employee_count": ["associated_employee_count", "linkedin_associated_employee_count"],
    "employee_count_range": [
        "employee_count_range",
        "companyenrich_employees",
        "companyenrich_reported_employees",
        "linkedin_associated_employee_text",
    ],
    "headquarters_city": ["headquarters_city", "city", "companyenrich_location_json"],
    "headquarters_region": ["headquarters_region", "companyenrich_location_json"],
    "headquarters_country": ["headquarters_country", "companyenrich_location_json"],
    "headquarters_country_code": ["headquarters_country_code", "companyenrich_location_json"],
    "headquarters_display": ["headquarters_display", "companyenrich_location_json"],
    "locations_json": ["linkedin_locations", "companyenrich_location_json"],
    "linkedin_follower_count": ["linkedin_follower_count", "follower_count"],
    "company_type": ["company_type", "companyenrich_type"],
    "founded_year": ["founded_year", "companyenrich_founded_year"],
    "description": ["description", "companyenrich_description"],
    "seo_description": ["companyenrich_seo_description"],
    "logo_url": ["logo_linkedin_source_url", "companyenrich_logo_url"],
    "logo_source": ["companyenrich_logo_source", "logo_linkedin_source_url"],
    "cover_image_url": ["cover_linkedin_source_url"],
    "revenue_range": ["companyenrich_revenue"],
    "financial_json": ["companyenrich_financial_json"],
    "tagline": ["tagline"],
    "specialties_json": ["specialties"],
    "keywords_json": ["companyenrich_keywords_json"],
    "technologies_json": ["companyenrich_technologies_json"],
    "subsidiaries_json": ["companyenrich_subsidiaries_json"],
    "naics_codes_json": ["companyenrich_naics_codes_json"],
    "socials_json": ["companyenrich_socials_json"],
    "page_rank": ["companyenrich_page_rank"],
    "record_sources": ["Source", "scrape_source"],
    "linkedin_page_valid": ["page_valid"],
    "enrichment_status": ["companyenrich_enrichment_status", "companyenrich_match_status", "companyenrich_record_exists"],
    "last_enriched_at": [
        "company_enrichment_scraped_at",
        "companyenrich_lookup_at",
        "companyenrich_enriched_at",
        "companyenrich_updated_at",
    ],
}

AUDIT_COLUMNS = [
    "Source",
    "Company-LinkedIn-url",
    "linkedin_company_url",
    "website",
    "website_url",
    "scrape_source",
    "scrape_source_url",
    "scrape_http_status",
    "scrape_parser_version",
    "scrape_content_hash",
    "company_enrichment_scraped_at",
    "companyenrich_record_exists",
    "companyenrich_match_status",
    "companyenrich_match_domain",
    "companyenrich_match_name",
    "companyenrich_logo_source",
    "companyenrich_lookup_at",
    "companyenrich_enrichment_status",
    "companyenrich_enriched_at",
    "companyenrich_credit_cost",
    "companyenrich_updated_at",
    "companyenrich_error",
    "companyenrich_profile_json",
]

REMOVED_DERIVED_COLUMNS = ["people_url", "jobs_url", "posts_url"]
REQUIRED_CANONICAL_COLUMNS = {"company_id", "source_row_numbers", "merge_basis", "company_name"}

CONFLICT_FIELDS = {
    "company_name",
    "legal_name",
    "website_url",
    "domain",
    "linkedin_company_url",
    "company_id",
    "companyenrich_id",
    "industry",
    "employee_count",
    "employee_count_range",
    "headquarters_city",
    "headquarters_region",
    "headquarters_country",
    "headquarters_country_code",
    "linkedin_follower_count",
    "company_type",
    "founded_year",
}

TRACKING_QUERY_KEYS = {
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "ref",
    "referrer",
}

COMMON_MULTI_LABEL_SUFFIXES = {
    "co.uk",
    "org.uk",
    "ac.uk",
    "gov.uk",
    "com.au",
    "net.au",
    "org.au",
    "com.br",
    "com.cn",
    "com.hk",
    "com.mx",
    "com.sg",
    "com.tr",
    "co.in",
    "co.jp",
    "co.nz",
    "co.za",
}

GENERIC_NAME_PARTS = {
    "ag",
    "and",
    "company",
    "global",
    "group",
    "holding",
    "holdings",
    "international",
    "services",
}


@dataclass(frozen=True)
class Candidate:
    source_column: str
    source_value: str
    normalized_value: str
    source_row_number: str
    source_system: str
    timestamp: str
    confidence: float


@dataclass
class PreparedRow:
    values: dict[str, str]
    source_row_number: str
    input_index: int
    name_key: str
    linkedin_url: str
    linkedin_page_type: str
    companyenrich_id: str
    domain: str
    city_key: str
    country_key: str


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value)).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def is_nonempty(value: Any) -> bool:
    return bool(clean_text(value))


def normalize_name(value: Any) -> str:
    text = clean_text(value).casefold()
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def display_name(value: Any) -> str:
    return clean_text(value)


def parse_json_value(value: Any) -> Any | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def dedupe_json(value: Any) -> Any:
    if isinstance(value, list):
        result: list[Any] = []
        seen: set[str] = set()
        for item in value:
            normalized = dedupe_json(item)
            key = canonical_json(normalized)
            if key not in seen:
                seen.add(key)
                result.append(normalized)
        return result
    if isinstance(value, dict):
        return {str(key): dedupe_json(item) for key, item in value.items()}
    return value


def json_or_text(value: Any) -> Any | None:
    parsed = parse_json_value(value)
    if parsed is not None:
        return dedupe_json(parsed)
    text = clean_text(value)
    return text or None


def json_array(value: Any) -> list[Any]:
    parsed = json_or_text(value)
    if parsed is None:
        return []
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, str) and "," in parsed:
        return [clean_text(part) for part in parsed.split(",") if clean_text(part)]
    return [parsed]


def json_text(value: Any) -> str:
    parsed = json_or_text(value)
    return "" if parsed is None else canonical_json(dedupe_json(parsed))


def merge_json_arrays(values: Iterable[Any]) -> str:
    merged: list[Any] = []
    seen: set[str] = set()
    for value in values:
        for item in json_array(value):
            item = dedupe_json(item)
            key = canonical_json(item)
            if key not in seen:
                seen.add(key)
                merged.append(item)
    return canonical_json(merged) if merged else ""


def parse_int(value: Any) -> int | None:
    text = clean_text(value).replace(",", "")
    if not text or re.fullmatch(r"\d+", text) is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def parse_year(value: Any) -> int | None:
    number = parse_int(value)
    current_year = datetime.now(timezone.utc).year
    return number if number is not None and 1800 <= number <= current_year else None


def parse_float(value: Any) -> float | None:
    text = clean_text(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_bool(value: Any) -> bool | None:
    text = clean_text(value).casefold()
    if text in {"true", "1", "yes", "y", "valid", "succeeded"}:
        return True
    if text in {"false", "0", "no", "n", "invalid", "failed"}:
        return False
    return None


def parse_timestamp(value: Any) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_timestamp(value: Any) -> str:
    parsed = value if isinstance(value, datetime) else parse_timestamp(value)
    if parsed is None:
        return ""
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def hostname_from_value(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    candidate = text if re.match(r"^[a-z][a-z0-9+.-]*://", text, re.IGNORECASE) else f"https://{text}"
    try:
        hostname = urlsplit(candidate).hostname or ""
    except ValueError:
        return ""
    return hostname.casefold().rstrip(".")


def registrable_domain(hostname: str) -> str:
    host = hostname.casefold().strip(".")
    if not host or "." not in host:
        return host
    labels = host.split(".")
    suffix = ".".join(labels[-2:])
    return ".".join(labels[-3:]) if suffix in COMMON_MULTI_LABEL_SUFFIXES and len(labels) >= 3 else suffix


def normalize_domain(value: Any) -> str:
    return registrable_domain(hostname_from_value(value))


def normalize_url(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    candidate = text if re.match(r"^[a-z][a-z0-9+.-]*://", text, re.IGNORECASE) else f"https://{text}"
    try:
        parsed = urlsplit(candidate)
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        if not hostname or parsed.scheme.casefold() not in {"http", "https"}:
            return ""
        port = parsed.port
    except ValueError:
        return ""
    netloc = hostname
    if port is not None and not ((parsed.scheme.casefold() == "http" and port == 80) or (parsed.scheme.casefold() == "https" and port == 443)):
        netloc = f"{netloc}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "")
    if path == "/":
        path = ""
    else:
        path = path.rstrip("/")
    query_parts = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in TRACKING_QUERY_KEYS and not key.casefold().startswith("utm_")
    ]
    query = urlencode(sorted(query_parts))
    return urlunsplit(("https", netloc, path, query, ""))


def normalize_linkedin_url(value: Any) -> str:
    normalized = normalize_url(value)
    if not normalized:
        return ""
    parsed = urlsplit(normalized)
    hostname = parsed.hostname or ""
    if not (hostname == "linkedin.com" or hostname.endswith(".linkedin.com")):
        return ""
    segments = [unquote(part) for part in parsed.path.split("/") if part]
    if len(segments) < 2 or segments[0].casefold() not in {"company", "school"}:
        return ""
    page_type = segments[0].casefold()
    slug = quote(segments[1].strip(), safe="-._~")
    return f"https://www.linkedin.com/{page_type}/{slug}"


def linkedin_parts(value: Any) -> tuple[str, str, str]:
    normalized = normalize_linkedin_url(value)
    if not normalized:
        return "", "", ""
    parts = [part for part in urlsplit(normalized).path.split("/") if part]
    return normalized, parts[1], parts[0]


def source_system(column: str) -> str:
    lower = column.casefold()
    if lower.startswith("companyenrich_"):
        return "companyenrich"
    if "linkedin" in lower or column in {"Company-LinkedIn-url", "page_valid", "Source"}:
        return "linkedin"
    if lower.startswith("scrape_") or lower.startswith("company_enrichment_"):
        return "scraper"
    return "original"


def source_confidence(column: str) -> float:
    if column in {"company_name", "website", "Company-LinkedIn-url", "description"}:
        return 0.95
    if column in {"linkedin_company_url", "companyenrich_name", "companyenrich_website", "companyenrich_id"}:
        return 0.9
    if column.startswith("companyenrich_"):
        return 0.8
    return 0.75


def source_timestamp(row: dict[str, str]) -> str:
    timestamps = [
        row.get("companyenrich_updated_at", ""),
        row.get("companyenrich_enriched_at", ""),
        row.get("companyenrich_lookup_at", ""),
        row.get("company_enrichment_scraped_at", ""),
        row.get("scraped_at", ""),
    ]
    parsed = [parse_timestamp(value) for value in timestamps]
    valid = [value for value in parsed if value is not None]
    return format_timestamp(max(valid)) if valid else ""


def row_number(row: dict[str, str], fallback: int) -> str:
    value = clean_text(row.get("No", ""))
    return value or str(fallback)


def row_candidate(row: dict[str, str], column: str, transform: Callable[[Any], Any] = clean_text) -> Candidate | None:
    raw = row.get(column, "")
    if not is_nonempty(raw):
        return None
    transformed = transform(raw)
    if transformed is None or transformed == "":
        return None
    if isinstance(transformed, (dict, list)):
        normalized = canonical_json(dedupe_json(transformed))
        value = normalized
    else:
        value = str(transformed)
        normalized = value.casefold()
    return Candidate(
        source_column=column,
        source_value=str(raw),
        normalized_value=normalized,
        source_row_number=row["_source_row_number"],
        source_system=source_system(column),
        timestamp=source_timestamp(row),
        confidence=source_confidence(column),
    )


def candidates(rows: Sequence[dict[str, str]], columns: Sequence[str], transform: Callable[[Any], Any] = clean_text) -> list[Candidate]:
    result: list[Candidate] = []
    for row in rows:
        for column in columns:
            candidate = row_candidate(row, column, transform)
            if candidate is not None:
                result.append(candidate)
    return result


def choose_candidate(
    rows: Sequence[dict[str, str]],
    columns: Sequence[str],
    transform: Callable[[Any], Any] = clean_text,
    prefer_longest: bool = False,
) -> tuple[Any, Candidate | None, list[Candidate]]:
    all_candidates = candidates(rows, columns, transform)
    if not all_candidates:
        return "", None, []
    if prefer_longest:
        selected = max(all_candidates, key=lambda item: (len(item.normalized_value), item.confidence, item.timestamp))
    else:
        order = {column: index for index, column in enumerate(columns)}
        selected = min(
            all_candidates,
            key=lambda item: (
                order.get(item.source_column, len(order)),
                -item.confidence,
                item.timestamp == "",
                item.source_row_number,
            ),
        )
    transformed = transform(selected.source_value)
    return transformed, selected, all_candidates


def first_row_candidate(row: dict[str, str], columns: Sequence[str], transform: Callable[[Any], Any] = clean_text) -> Any:
    for column in columns:
        candidate = row_candidate(row, column, transform)
        if candidate is not None:
            return transform(candidate.source_value)
    return ""


def normalize_company_type(value: Any) -> str:
    text = clean_text(value)
    key = re.sub(r"[\s_-]+", " ", text.casefold())
    equivalents = {
        "public company": "public",
        "publicly held": "public",
        "private company": "private",
        "privately held": "private",
        "self owned": "self-owned",
        "self-owned": "self-owned",
        "non profit": "nonprofit",
        "non-profit": "nonprofit",
    }
    return equivalents.get(key, text)


def extract_location(value: Any) -> dict[str, Any] | None:
    parsed = parse_json_value(value)
    if isinstance(parsed, dict):
        return parsed
    return None


def location_value(rows: Sequence[dict[str, str]], field: str) -> tuple[str, Candidate | None, list[Candidate]]:
    explicit_columns = {
        "city": ["headquarters_city", "city"],
        "region": ["headquarters_region"],
        "country": ["headquarters_country"],
        "country_code": ["headquarters_country_code"],
        "display": ["headquarters_display"],
    }
    explicit, selected, all_candidates = choose_candidate(rows, explicit_columns[field])
    if explicit:
        return clean_text(explicit), selected, all_candidates
    location_candidates = candidates(rows, ["companyenrich_location_json"], lambda value: extract_location(value) or "")
    for candidate in location_candidates:
        parsed = extract_location(candidate.source_value) or {}
        location = parsed.get("location") if isinstance(parsed.get("location"), dict) else parsed
        country = location.get("country") if isinstance(location, dict) else None
        country_name = country.get("name") if isinstance(country, dict) else country
        country_code = country.get("code") if isinstance(country, dict) else ""
        values = {
            "city": location.get("city", "") if isinstance(location, dict) else "",
            "region": location.get("state", "") if isinstance(location, dict) else "",
            "country": country_name or "",
            "country_code": country_code or "",
            "display": location.get("address", "") if isinstance(location, dict) else "",
        }
        if clean_text(values[field]):
            return clean_text(values[field]), candidate, location_candidates
    return "", None, all_candidates + location_candidates


def prepare_row(row: dict[str, str], input_index: int) -> PreparedRow:
    source_number = row_number(row, input_index + 1)
    row["_source_row_number"] = source_number
    row["_input_index"] = str(input_index)
    name = first_row_candidate(row, ["company_name", "companyenrich_name", "companyenrich_match_name", "company"], display_name)
    linkedin = first_row_candidate(row, ["Company-LinkedIn-url", "linkedin_company_url"], normalize_linkedin_url)
    page_type = linkedin_parts(linkedin)[2] if linkedin else ""
    companyenrich_id = clean_text(row.get("companyenrich_id", ""))
    website = first_row_candidate(
        row,
        ["website", "website_url", "companyenrich_website", "companyenrich_domain", "companyenrich_match_domain", "domain"],
        normalize_url,
    )
    domain = normalize_domain(website)
    if not domain:
        for column in ["website", "website_url", "companyenrich_website", "companyenrich_domain", "companyenrich_match_domain", "domain"]:
            domain = normalize_domain(row.get(column, ""))
            if domain:
                break
    city = first_row_candidate(row, ["headquarters_city", "city"], normalize_name)
    country = first_row_candidate(row, ["headquarters_country_code", "headquarters_country"], normalize_name)
    return PreparedRow(
        values=row,
        source_row_number=source_number,
        input_index=input_index,
        name_key=normalize_name(name),
        linkedin_url=linkedin,
        linkedin_page_type=page_type,
        companyenrich_id=companyenrich_id,
        domain=domain,
        city_key=city,
        country_key=country,
    )


def compatible_members(members: Sequence[PreparedRow], identity_basis: str = "") -> bool:
    linkedin_urls = {row.linkedin_url for row in members if row.linkedin_url}
    companyenrich_ids = {row.companyenrich_id for row in members if row.companyenrich_id}
    domains = {row.domain for row in members if row.domain}
    page_types = {row.linkedin_page_type for row in members if row.linkedin_page_type}
    if "company" in page_types and "school" in page_types:
        return False
    if identity_basis in {"linkedin_url", "companyenrich_id"}:
        return True
    return len(linkedin_urls) <= 1 and len(companyenrich_ids) <= 1 and len(domains) <= 1


def generic_name(name_key: str) -> bool:
    parts = set(name_key.split())
    return len(name_key) < 8 or bool(parts & GENERIC_NAME_PARTS) and len(parts) <= 2


class DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.basis: dict[int, set[str]] = defaultdict(set)

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int, basis: str, rows: Sequence[PreparedRow]) -> bool:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            self.basis[root_left].add(basis)
            return True
        left_members = [index for index in range(len(rows)) if self.find(index) == root_left]
        right_members = [index for index in range(len(rows)) if self.find(index) == root_right]
        if not compatible_members([rows[index] for index in left_members + right_members], basis):
            return False
        if len(left_members) < len(right_members):
            root_left, root_right = root_right, root_left
        self.parent[root_right] = root_left
        self.basis[root_left].update(self.basis.pop(root_right, set()))
        self.basis[root_left].add(basis)
        return True


def group_indexes_by(rows: Sequence[PreparedRow], attribute: str) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        value = getattr(row, attribute)
        if value:
            groups[value].append(index)
    return dict(groups)


def deduplicate_rows(rows: Sequence[PreparedRow]) -> tuple[list[list[int]], list[dict[str, str]], dict[str, int]]:
    dsu = DisjointSet(len(rows))
    identity_groups = {
        "linkedin_url": group_indexes_by(rows, "linkedin_url"),
        "companyenrich_id": group_indexes_by(rows, "companyenrich_id"),
        "domain": group_indexes_by(rows, "domain"),
        "name": group_indexes_by(rows, "name_key"),
    }
    duplicate_counts = {key: sum(len(group) > 1 for group in groups.values()) for key, groups in identity_groups.items()}

    for key in ("linkedin_url", "companyenrich_id"):
        for value, indexes in identity_groups[key].items():
            for index in indexes[1:]:
                dsu.union(indexes[0], index, key, rows)

    for domain, indexes in identity_groups["domain"].items():
        for index in indexes[1:]:
            current = indexes[0]
            if rows[current].name_key and rows[index].name_key and rows[current].name_key == rows[index].name_key:
                dsu.union(current, index, "domain", rows)

    for name_key, indexes in identity_groups["name"].items():
        if generic_name(name_key):
            continue
        for index in indexes[1:]:
            current = indexes[0]
            left = rows[current]
            right = rows[index]
            same_location = bool(left.city_key and right.city_key and left.city_key == right.city_key)
            same_country = bool(left.country_key and right.country_key and left.country_key == right.country_key)
            if (same_location or (same_country and not left.city_key and not right.city_key)) and compatible_members([left, right], "name+location"):
                dsu.union(current, index, "name+location", rows)

    grouped: dict[int, list[int]] = defaultdict(list)
    for index in range(len(rows)):
        grouped[dsu.find(index)].append(index)
    groups = sorted((sorted(indexes) for indexes in grouped.values()), key=lambda indexes: indexes[0])
    possible = build_possible_duplicates(rows, groups, identity_groups)
    return groups, possible, duplicate_counts


def build_possible_duplicates(
    rows: Sequence[PreparedRow], groups: Sequence[Sequence[int]], identity_groups: dict[str, dict[str, list[int]]]
) -> list[dict[str, str]]:
    root_by_index = {index: group[0] for group in groups for index in group}
    possible: dict[tuple[str, ...], dict[str, str]] = {}

    for identity, grouped in (("shared_domain", identity_groups["domain"]), ("same_name_different_evidence", identity_groups["name"])):
        for value, indexes in grouped.items():
            roots = {root_by_index[index] for index in indexes}
            if len(roots) <= 1:
                continue
            rows_in_group = [rows[index] for index in indexes]
            key = (identity, value, *sorted(row.source_row_number for row in rows_in_group))
            possible[key] = {
                "candidate_company_id": f"review-{hashlib.sha256('|'.join(key).encode()).hexdigest()[:16]}",
                "source_row_numbers": json.dumps([row.source_row_number for row in rows_in_group]),
                "reason": identity,
                "normalized_name": value if identity == "same_name_different_evidence" else "",
                "domain": value if identity == "shared_domain" else "",
                "company_names": json.dumps(sorted({clean_text(row.values.get('company_name', '')) for row in rows_in_group if row.values.get('company_name')}), ensure_ascii=False),
                "linkedin_urls": json.dumps(sorted({row.linkedin_url for row in rows_in_group if row.linkedin_url})),
                "confidence": "0.55",
                "manual_review_required": "true",
            }

    blocks: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        if row.name_key:
            blocks[row.name_key[:6]].append(index)
    for indexes in blocks.values():
        if len(indexes) > 100:
            continue
        for offset, left_index in enumerate(indexes):
            for right_index in indexes[offset + 1 :]:
                left = rows[left_index]
                right = rows[right_index]
                if left.name_key == right.name_key or root_by_index[left_index] == root_by_index[right_index]:
                    continue
                similarity = difflib.SequenceMatcher(None, left.name_key, right.name_key).ratio()
                compatible_context = left.domain and left.domain == right.domain or left.country_key and left.country_key == right.country_key
                if similarity < 0.9 or not compatible_context:
                    continue
                source_numbers = sorted([left.source_row_number, right.source_row_number])
                key = ("similar_name", *source_numbers)
                possible[key] = {
                    "candidate_company_id": f"review-{hashlib.sha256('|'.join(key).encode()).hexdigest()[:16]}",
                    "source_row_numbers": json.dumps(source_numbers),
                    "reason": f"similar_name:{similarity:.2f}",
                    "normalized_name": "",
                    "domain": left.domain if left.domain == right.domain else "",
                    "company_names": json.dumps([clean_text(left.values.get("company_name", "")), clean_text(right.values.get("company_name", ""))], ensure_ascii=False),
                    "linkedin_urls": json.dumps([url for url in [left.linkedin_url, right.linkedin_url] if url]),
                    "confidence": f"{similarity:.2f}",
                    "manual_review_required": "true",
                }
    return list(possible.values())


def selected_value_for_field(canonical: dict[str, str], field: str) -> str:
    return canonical.get(field, "")


def candidate_was_selected(field: str, raw: str, selected: str) -> bool:
    if not selected:
        return False
    if field in {"website_url", "linkedin_company_url", "logo_url", "cover_image_url"}:
        return normalize_url(raw) == normalize_url(selected) or normalize_linkedin_url(raw) == selected
    if field == "domain":
        return normalize_domain(raw) == selected
    if field in {"company_name", "legal_name", "industry", "headquarters_city", "headquarters_region", "headquarters_country"}:
        return normalize_name(raw) == normalize_name(selected)
    if field in {"linkedin_follower_count", "employee_count"}:
        return str(parse_int(raw) or "") == selected
    if field == "founded_year":
        return str(parse_year(raw) or "") == selected
    if field.endswith("_json") or field == "locations_json":
        return bool(raw) and (json_text(raw) == selected or canonical_json(json_array(raw)) in selected)
    return clean_text(raw).casefold() == clean_text(selected).casefold()


def canonical_id(group_rows: Sequence[PreparedRow], companyenrich_id: str, linkedin_url: str, domain: str, name: str) -> str:
    existing = [clean_text(row.values.get("company_id", "")) for row in group_rows if is_nonempty(row.values.get("company_id", ""))]
    if existing:
        return existing[0]
    seed = companyenrich_id or linkedin_url or domain or normalize_name(name) or "|".join(row.source_row_number for row in group_rows)
    return f"canonical-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"


def consolidate_group(group_rows: Sequence[PreparedRow]) -> tuple[dict[str, str], dict[str, list[Candidate]], dict[str, str]]:
    rows = [row.values for row in group_rows]
    candidate_map: dict[str, list[Candidate]] = defaultdict(list)
    selected_sources: dict[str, str] = {}

    def choose(field: str, columns: Sequence[str], transform: Callable[[Any], Any] = clean_text, longest: bool = False) -> Any:
        value, selected, all_candidates = choose_candidate(rows, columns, transform, longest)
        candidate_map[field].extend(all_candidates)
        if selected:
            selected_sources[field] = f"{selected.source_column} (row {selected.source_row_number})"
        return value

    result = {column: "" for column in CANONICAL_COLUMNS}
    result["company_name"] = display_name(choose("company_name", COLUMN_GROUPS["company_name"], display_name))
    result["legal_name"] = display_name(choose("legal_name", COLUMN_GROUPS["legal_name"], display_name))

    website_columns = [
        "website",
        "website_url",
        "companyenrich_website",
        "companyenrich_domain",
        "companyenrich_match_domain",
        "domain",
    ]
    _, selected_website, website_candidates = choose_candidate(rows, website_columns, normalize_url)
    candidate_map["website_url"].extend(website_candidates)
    if selected_website:
        result["website_url"] = normalize_url(selected_website.source_value)
        selected_sources["website_url"] = f"{selected_website.source_column} (row {selected_website.source_row_number})"
    domain_candidates: list[Candidate] = []
    for row in rows:
        for column in ["website", "website_url", "companyenrich_website", "companyenrich_domain", "companyenrich_match_domain", "domain"]:
            candidate = row_candidate(row, column, normalize_domain)
            if candidate:
                domain_candidates.append(candidate)
    candidate_map["domain"].extend(domain_candidates)
    if selected_website:
        result["domain"] = normalize_domain(selected_website.source_value)
    elif domain_candidates:
        result["domain"] = domain_candidates[0].normalized_value
        selected_sources["domain"] = f"{domain_candidates[0].source_column} (row {domain_candidates[0].source_row_number})"

    linkedin_url, linkedin_selected, linkedin_candidates = choose_candidate(rows, COLUMN_GROUPS["linkedin_company_url"], normalize_linkedin_url)
    candidate_map["linkedin_company_url"].extend(linkedin_candidates)
    result["linkedin_company_url"] = linkedin_url
    if linkedin_selected:
        selected_sources["linkedin_company_url"] = f"{linkedin_selected.source_column} (row {linkedin_selected.source_row_number})"
    result["company_id"] = clean_text(choose("company_id", COLUMN_GROUPS["company_id"]))
    result["companyenrich_id"] = clean_text(choose("companyenrich_id", COLUMN_GROUPS["companyenrich_id"]))
    result["linkedin_company_id"] = clean_text(choose("linkedin_company_id", COLUMN_GROUPS["linkedin_company_id"]))
    _, slug, page_type = linkedin_parts(result["linkedin_company_url"])
    result["linkedin_page_type"] = page_type or clean_text(choose("linkedin_page_type", COLUMN_GROUPS["linkedin_page_type"]))
    result["linkedin_slug"] = slug

    for location_field, location_key in [
        ("headquarters_city", "city"),
        ("headquarters_region", "region"),
        ("headquarters_country", "country"),
        ("headquarters_country_code", "country_code"),
        ("headquarters_display", "display"),
    ]:
        location, selected_location, location_candidates = location_value(rows, location_key)
        candidate_map[location_field].extend(location_candidates)
        result[location_field] = clean_text(location)
        if location_field == "headquarters_country_code":
            result[location_field] = result[location_field].upper()
        if selected_location:
            selected_sources[location_field] = f"{selected_location.source_column} (row {selected_location.source_row_number})"
    location_values = [row.get("linkedin_locations", "") for row in rows] + [row.get("companyenrich_location_json", "") for row in rows]
    result["locations_json"] = merge_json_arrays(location_values)
    candidate_map["locations_json"].extend(candidates(rows, ["linkedin_locations", "companyenrich_location_json"], lambda value: json_array(value)))

    industry_candidates = candidates(rows, ["industry", "companyenrich_industry", "sectors_active"], clean_text)
    industry_json_candidates = candidates(rows, ["companyenrich_industries_json"], lambda value: json_array(value))
    candidate_map["industry"].extend(industry_candidates + industry_json_candidates)
    if industry_candidates:
        result["industry"] = industry_candidates[0].normalized_value
        selected_sources["industry"] = f"{industry_candidates[0].source_column} (row {industry_candidates[0].source_row_number})"
    elif industry_json_candidates:
        values = json_array(industry_json_candidates[0].source_value)
        result["industry"] = clean_text(values[0]) if values else ""
    industry_sources = ["sectors_active", "industry", "companyenrich_industry", "companyenrich_industries_json"]
    result["industries_json"] = merge_json_arrays([row.get(column, "") for row in rows for column in industry_sources])
    candidate_map["industries_json"].extend(candidates(rows, industry_sources, lambda value: json_array(value)))
    result["categories_json"] = merge_json_arrays([row.get("companyenrich_categories_json", "") for row in rows])
    candidate_map["categories_json"].extend(candidates(rows, ["companyenrich_categories_json"], lambda value: json_array(value)))

    exact_employee_candidates: list[Candidate] = []
    for row in rows:
        for column in ["associated_employee_count", "linkedin_associated_employee_count"]:
            candidate = row_candidate(row, column, parse_int)
            if candidate:
                exact_employee_candidates.append(candidate)
    candidate_map["employee_count"].extend(exact_employee_candidates)
    if exact_employee_candidates:
        selected_employee = exact_employee_candidates[0]
        result["employee_count"] = str(parse_int(selected_employee.source_value))
        selected_sources["employee_count"] = f"{selected_employee.source_column} (row {selected_employee.source_row_number})"
    range_candidates = candidates(rows, COLUMN_GROUPS["employee_count_range"], clean_text)
    candidate_map["employee_count_range"].extend(range_candidates)
    result["employee_count_range"] = range_candidates[0].normalized_value if range_candidates else ""
    source_names = []
    if exact_employee_candidates:
        source_names.append(source_system(exact_employee_candidates[0].source_column))
    if range_candidates:
        source_names.append(source_system(range_candidates[0].source_column))
    result["employee_count_source"] = "|".join(dict.fromkeys(source_names))

    follower_candidates = candidates(rows, COLUMN_GROUPS["linkedin_follower_count"], parse_int)
    candidate_map["linkedin_follower_count"].extend(follower_candidates)
    if follower_candidates:
        result["linkedin_follower_count"] = str(parse_int(follower_candidates[0].source_value))
        selected_sources["linkedin_follower_count"] = f"{follower_candidates[0].source_column} (row {follower_candidates[0].source_row_number})"
    year_candidates = candidates(rows, COLUMN_GROUPS["founded_year"], parse_year)
    candidate_map["founded_year"].extend(year_candidates)
    if year_candidates:
        result["founded_year"] = str(parse_year(year_candidates[0].source_value))
        selected_sources["founded_year"] = f"{year_candidates[0].source_column} (row {year_candidates[0].source_row_number})"

    type_candidates = candidates(rows, COLUMN_GROUPS["company_type"], normalize_company_type)
    candidate_map["company_type"].extend(type_candidates)
    result["company_type"] = type_candidates[0].normalized_value if type_candidates else ""

    description_candidates = candidates(rows, COLUMN_GROUPS["description"], display_name)
    candidate_map["description"].extend(description_candidates)
    if description_candidates:
        selected_description = max(description_candidates, key=lambda item: (len(item.normalized_value), item.confidence))
        result["description"] = display_name(selected_description.source_value)
        selected_sources["description"] = f"{selected_description.source_column} (row {selected_description.source_row_number})"
    seo_candidate = candidates(rows, ["companyenrich_seo_description"], display_name)
    candidate_map["seo_description"].extend(seo_candidate)
    if seo_candidate and normalize_name(seo_candidate[0].source_value) != normalize_name(result["description"]):
        result["seo_description"] = display_name(seo_candidate[0].source_value)

    logo_candidates = candidates(rows, ["logo_linkedin_source_url", "companyenrich_logo_url"], normalize_url)
    candidate_map["logo_url"].extend(logo_candidates)
    if logo_candidates:
        result["logo_url"] = normalize_url(logo_candidates[0].source_value)
        selected_sources["logo_url"] = f"{logo_candidates[0].source_column} (row {logo_candidates[0].source_row_number})"
    logo_source = candidates(rows, ["companyenrich_logo_source"], clean_text)
    candidate_map["logo_source"].extend(logo_source)
    result["logo_source"] = logo_source[0].normalized_value if logo_source else ("linkedin" if result["logo_url"] else "")
    cover = choose("cover_image_url", COLUMN_GROUPS["cover_image_url"], normalize_url)
    result["cover_image_url"] = normalize_url(cover)

    result["revenue_range"] = clean_text(choose("revenue_range", COLUMN_GROUPS["revenue_range"]))
    financial_candidates = candidates(rows, COLUMN_GROUPS["financial_json"], lambda value: json_or_text(value) or "")
    candidate_map["financial_json"].extend(financial_candidates)
    result["financial_json"] = json_text(financial_candidates[0].source_value) if financial_candidates else ""

    result["tagline"] = clean_text(choose("tagline", COLUMN_GROUPS["tagline"]))
    for field in ["specialties_json", "keywords_json", "technologies_json", "subsidiaries_json", "naics_codes_json", "socials_json"]:
        result[field] = merge_json_arrays([row.get(column, "") for row in rows for column in COLUMN_GROUPS[field]])
        candidate_map[field].extend(candidates(rows, COLUMN_GROUPS[field], lambda value: json_array(value)))
    page_rank_candidates = candidates(rows, COLUMN_GROUPS["page_rank"], parse_float)
    candidate_map["page_rank"].extend(page_rank_candidates)
    result["page_rank"] = str(parse_float(page_rank_candidates[0].source_value)) if page_rank_candidates else ""

    result["record_sources"] = merge_json_arrays([row.get(column, "") for row in rows for column in COLUMN_GROUPS["record_sources"]])
    record_candidates = candidates(rows, COLUMN_GROUPS["record_sources"], clean_text)
    candidate_map["record_sources"].extend(record_candidates)
    bool_candidates = candidates(rows, ["page_valid"], parse_bool)
    candidate_map["linkedin_page_valid"].extend(bool_candidates)
    if bool_candidates:
        result["linkedin_page_valid"] = "true" if parse_bool(bool_candidates[0].source_value) else "false"
    status_candidates = candidates(rows, ["companyenrich_enrichment_status", "companyenrich_match_status"], clean_text)
    candidate_map["enrichment_status"].extend(status_candidates)
    if status_candidates:
        result["enrichment_status"] = status_candidates[0].normalized_value
    elif any(parse_bool(row.get("companyenrich_record_exists", "")) for row in rows):
        result["enrichment_status"] = "record_exists"
    timestamp_candidates = []
    for row in rows:
        for column in COLUMN_GROUPS["last_enriched_at"]:
            candidate = row_candidate(row, column, format_timestamp)
            if candidate and parse_timestamp(candidate.source_value):
                timestamp_candidates.append(candidate)
    candidate_map["last_enriched_at"].extend(timestamp_candidates)
    if timestamp_candidates:
        latest = max(timestamp_candidates, key=lambda item: parse_timestamp(item.source_value) or datetime.min.replace(tzinfo=timezone.utc))
        result["last_enriched_at"] = format_timestamp(latest.source_value)

    if not result["company_id"]:
        result["company_id"] = canonical_id(group_rows, result["companyenrich_id"], result["linkedin_company_url"], result["domain"], result["company_name"])
    return result, candidate_map, selected_sources


def conflict_rows(
    group_rows: Sequence[PreparedRow], canonical: dict[str, str], candidate_map: dict[str, list[Candidate]], selected_sources: dict[str, str]
) -> list[dict[str, str]]:
    conflicts: list[dict[str, str]] = []
    for field in sorted(CONFLICT_FIELDS):
        field_candidates = candidate_map.get(field, [])
        distinct: dict[str, Candidate] = {}
        for candidate in field_candidates:
            key = candidate.normalized_value
            if key:
                distinct.setdefault(key, candidate)
        if len(distinct) <= 1:
            continue
        candidate_values = [candidate.source_value for candidate in distinct.values()]
        candidate_sources = [f"{candidate.source_row_number}:{candidate.source_column}" for candidate in distinct.values()]
        conflicts.append(
            {
                "candidate_company_id": canonical["company_id"],
                "source_row_numbers": json.dumps([row.source_row_number for row in group_rows]),
                "conflicting_field": field,
                "candidate_values": json.dumps(candidate_values, ensure_ascii=False),
                "candidate_sources": json.dumps(candidate_sources, ensure_ascii=False),
                "selected_value": canonical.get(field, ""),
                "selection_reason": selected_sources.get(field, "source precedence and validation rules"),
                "confidence": f"{max(candidate.confidence for candidate in distinct.values()):.2f}",
                "manual_review_required": "true" if field in {"domain", "linkedin_company_url", "companyenrich_id", "company_id"} else "false",
            }
        )
    return conflicts


def canonical_field_for_source(column: str) -> str:
    if column == "No":
        return "source_row_number"
    for canonical, source_columns in COLUMN_GROUPS.items():
        if column in source_columns:
            return canonical
    if column in AUDIT_COLUMNS:
        return f"audit.{column}"
    if column in REMOVED_DERIVED_COLUMNS:
        return f"derived_url.{column}"
    return f"source.{column}"


def provenance_selected(field: str, raw: str, canonical: dict[str, str], row_number_value: str) -> bool:
    if field == "source_row_number":
        return row_number_value in json.loads(canonical["source_row_numbers"])
    if field.startswith("audit.") or field.startswith("source.") or field.startswith("derived_url."):
        return False
    return candidate_was_selected(field, raw, canonical.get(field, ""))


def write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field, "") for field in fieldnames})


def profile_columns(fieldnames: Sequence[str], rows: Sequence[dict[str, str]]) -> list[dict[str, Any]]:
    columns = {column: [row.get(column, "") for row in rows] for column in fieldnames}
    fingerprints: dict[str, str] = {}
    for column, values in columns.items():
        normalized_values = [clean_text(value) for value in values]
        fingerprint = hashlib.sha256("\x1f".join(normalized_values).encode("utf-8")).hexdigest()
        fingerprints.setdefault(fingerprint, column)

    profile: list[dict[str, Any]] = []
    for index, column in enumerate(fieldnames, start=1):
        raw_values = columns[column]
        normalized_values = [clean_text(value) for value in raw_values]
        counts = Counter(value for value in normalized_values if value)
        repeated_values = {value: count for value, count in counts.items() if count > 1}
        exact_duplicate = fingerprints[hashlib.sha256("\x1f".join(normalized_values).encode("utf-8")).hexdigest()]
        equivalent_group = next((canonical for canonical, sources in COLUMN_GROUPS.items() if column in sources), "")
        profile.append(
            {
                "source_column_index": index,
                "source_column": column,
                "non_empty_count": sum(bool(value) for value in normalized_values),
                "empty_count": sum(not value for value in normalized_values),
                "unique_non_empty_count": len(counts),
                "repeated_distinct_value_count": len(repeated_values),
                "repeated_row_count": sum(count for count in repeated_values.values()),
                "max_value_length": max((len(value) for value in normalized_values), default=0),
                "completely_empty": "true" if not counts else "false",
                "exact_duplicate_of": "" if exact_duplicate == column else exact_duplicate,
                "semantic_equivalence_group": equivalent_group,
            }
        )
    return profile


def audit_rows(groups: Sequence[Sequence[int]], prepared: Sequence[PreparedRow], canonical_rows: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for canonical, group in zip(canonical_rows, groups):
        for index in group:
            row = prepared[index].values
            audit = {
                "canonical_company_id": canonical["company_id"],
                "source_row_number": prepared[index].source_row_number,
                "company_id": row.get("company_id", ""),
                "companyenrich_id": row.get("companyenrich_id", ""),
            }
            audit.update({column: row.get(column, "") for column in AUDIT_COLUMNS})
            output.append(audit)
    return output


def provenance_rows(
    fieldnames: Sequence[str],
    prepared: Sequence[PreparedRow],
    groups: Sequence[Sequence[int]],
    canonical_rows: Sequence[dict[str, str]],
    canonical_columns: Sequence[str],
) -> list[dict[str, str]]:
    canonical_by_index = {index: canonical for canonical, group in zip(canonical_rows, groups) for index in group}
    output: list[dict[str, str]] = []
    for row in prepared:
        canonical = canonical_by_index[row.input_index]
        for column in fieldnames:
            raw = row.values.get(column, "")
            if not is_nonempty(raw):
                continue
            field = canonical_field_for_source(column)
            selected_value = canonical.get(field, "") if field in canonical_columns else ""
            output.append(
                {
                    "company_id": canonical["company_id"],
                    "canonical_field": field,
                    "selected_value": selected_value,
                    "source_column": column,
                    "source_value": raw,
                    "source_system": source_system(column),
                    "source_row_number": row.source_row_number,
                    "source_timestamp": source_timestamp(row.values),
                    "was_selected": "true" if provenance_selected(field, raw, canonical, row.source_row_number) else "false",
                    "confidence": f"{source_confidence(column):.2f}",
                }
            )
    return output


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_outputs(
    input_path: Path,
    canonical_rows: Sequence[dict[str, str]],
    canonical_columns: Sequence[str],
    source_hash: str,
) -> None:
    if sha256_file(input_path) != source_hash:
        raise RuntimeError("Source CSV changed during cleaning; refusing to report success.")
    linkedin_values = [row["linkedin_company_url"] for row in canonical_rows if row["linkedin_company_url"]]
    if len(linkedin_values) != len(set(linkedin_values)):
        raise RuntimeError("Canonical LinkedIn URLs are not unique.")
    enrich_values = [row["companyenrich_id"] for row in canonical_rows if row["companyenrich_id"]]
    if len(enrich_values) != len(set(enrich_values)):
        raise RuntimeError("Canonical CompanyEnrich IDs are not unique.")
    exact_rows = [tuple(row[column] for column in canonical_columns) for row in canonical_rows]
    if len(exact_rows) != len(set(exact_rows)):
        raise RuntimeError("Exact duplicate canonical rows remain.")
    for row in canonical_rows:
        for column in canonical_columns:
            if column.endswith("_json") or column in {"locations_json", "financial_json", "record_sources"}:
                if row[column]:
                    try:
                        json.loads(row[column])
                    except json.JSONDecodeError as exc:
                        raise RuntimeError(f"Invalid JSON in {column}: {exc}") from exc
        for column in ["employee_count", "linkedin_follower_count", "founded_year"]:
            if row[column] and parse_int(row[column]) is None:
                raise RuntimeError(f"Non-numeric value in {column}: {row[column]}")


def build_report(
    output_path: Path,
    input_path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[dict[str, str]],
    canonical_rows: Sequence[dict[str, str]],
    canonical_columns: Sequence[str],
    groups: Sequence[Sequence[int]],
    conflicts: Sequence[dict[str, str]],
    possible: Sequence[dict[str, str]],
    duplicate_counts: dict[str, int],
    profiles: Sequence[dict[str, Any]],
    provenance_count: int,
    source_hash: str,
) -> None:
    empty_columns = [profile["source_column"] for profile in profiles if profile["completely_empty"] == "true"]
    merged_rows = sum(len(group) - 1 for group in groups)
    coverage_lines = []
    for column in canonical_columns:
        sources = COLUMN_GROUPS.get(column, [])
        before_count = sum(
            bool(clean_text(row.get(source, "")))
            for row in rows
            for source in sources
        )
        before_rows = sum(any(is_nonempty(row.get(source, "")) for source in sources) for row in rows)
        after_rows = sum(is_nonempty(row.get(column, "")) for row in canonical_rows)
        coverage_lines.append(
            f"| `{column}` | {before_count} source values | {before_rows / len(rows) * 100:.1f}% of input rows | {after_rows} canonical values | {after_rows / len(canonical_rows) * 100:.1f}% of canonical rows |"
        )

    lines = [
        "# Company consolidation report",
        "",
        f"- Input: `{input_path}`",
        f"- Output directory: `{output_path.parent}`",
        f"- Original rows: **{len(rows):,}**",
        f"- Original columns: **{len(fieldnames)}**",
        f"- Canonical rows: **{len(canonical_rows):,}**",
        f"- Canonical columns: **{len(canonical_columns)}**",
        f"- Automatically merged source rows: **{merged_rows:,}** across **{sum(len(group) > 1 for group in groups):,}** groups",
        f"- Uncertain cases sent to review: **{len(possible):,}**",
        f"- Non-empty source cells represented in provenance: **{provenance_count:,}**",
        f"- Source SHA-256 checked before and after processing: `{source_hash}`",
        "",
        "## Duplicate groups detected before merging",
        "",
        f"- LinkedIn URL groups: **{duplicate_counts['linkedin_url']:,}**",
        f"- Website domain groups: **{duplicate_counts['domain']:,}**",
        f"- CompanyEnrich ID groups: **{duplicate_counts['companyenrich_id']:,}**",
        f"- Company name groups: **{duplicate_counts['name']:,}**",
        "",
        "## Canonical field coverage",
        "",
        "| Canonical field | Source values | Input row coverage | Canonical values | Canonical row coverage |",
        "|---|---:|---:|---:|---:|",
        *coverage_lines,
        "",
        "## Removed empty columns",
        "",
        *(f"- `{column}`" for column in empty_columns),
        "",
        "## Canonical fields omitted as empty or unusable",
        "",
        *(f"- `{column}`" for column in CANONICAL_COLUMNS if column not in canonical_columns),
        "",
        "## Consolidated column groups",
        "",
    ]
    for canonical, sources in COLUMN_GROUPS.items():
        lines.append(f"- `{canonical}` <- {', '.join(f'`{source}`' for source in sources)}")
    lines.extend(
        [
            "",
            "## Columns relocated to the technical audit",
            "",
            *(f"- `{column}`" for column in AUDIT_COLUMNS),
            "",
            "## Assumptions and precedence rules",
            "",
            "- Display names prefer the LinkedIn-scraped `company_name`, then CompanyEnrich name, matched name, and the original name.",
            "- Original website URLs are preferred over enrichment URLs; domains are normalized to registrable domains for identity matching.",
            "- LinkedIn URLs are canonicalized to HTTPS `/company/` or `/school/` paths; company and school pages are never merged with each other.",
            "- Same-domain rows merge only when their normalized names agree. Same-name rows merge only with compatible city/location evidence.",
            "- Same CompanyEnrich IDs and same canonical LinkedIn URLs are strong automatic identity keys; conflicts are still written to the conflict report.",
            "- JSON arrays are parsed, deduplicated in source order, and emitted as valid compact JSON. Raw malformed values remain in provenance/audit output.",
            "- All non-empty source cells are represented in the provenance table; technical source fields are also retained in the audit table.",
            "- No network access, scraping, or enrichment API calls are performed.",
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def run_cleaning(input_path: Path = DEFAULT_INPUT, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    input_path = input_path.resolve()
    output_dir = output_dir.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    source_hash = sha256_file(input_path)
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = [dict(row) for row in reader]
    if not fieldnames:
        raise ValueError("Input CSV has no header")

    profiles = profile_columns(fieldnames, rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "company_column_profile.csv", profiles[0].keys(), profiles)

    prepared = [prepare_row(row, index) for index, row in enumerate(rows)]
    groups, possible, duplicate_counts = deduplicate_rows(prepared)
    canonical_rows: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []
    for group in groups:
        group_rows = [prepared[index] for index in group]
        canonical, candidate_map, selected_sources = consolidate_group(group_rows)
        canonical["source_row_numbers"] = json.dumps([row.source_row_number for row in group_rows])
        dsu_basis = []
        if len(group) == 1:
            dsu_basis = ["unique"]
        else:
            row_keys = {prepared[index].source_row_number for index in group}
            if any(row.linkedin_url and sum(row.linkedin_url == prepared[index].linkedin_url for index in group) > 1 for row in group_rows):
                dsu_basis.append("linkedin_url")
            if any(row.companyenrich_id and sum(row.companyenrich_id == prepared[index].companyenrich_id for index in group) > 1 for row in group_rows):
                dsu_basis.append("companyenrich_id")
            if any(row.domain and sum(row.domain == prepared[index].domain for index in group) > 1 for row in group_rows):
                dsu_basis.append("domain")
            if len(dsu_basis) == 0:
                dsu_basis.append("name+location")
        canonical["merge_basis"] = "|".join(dsu_basis)
        canonical_rows.append({column: canonical.get(column, "") for column in CANONICAL_COLUMNS})
        conflicts.extend(conflict_rows(group_rows, canonical, candidate_map, selected_sources))

    canonical_columns = [
        column
        for column in CANONICAL_COLUMNS
        if column in REQUIRED_CANONICAL_COLUMNS or any(is_nonempty(row.get(column, "")) for row in canonical_rows)
    ]
    write_csv(output_dir / "Master-Company-Url-canonical.csv", canonical_columns, canonical_rows)
    provenance_fieldnames = [
        "company_id",
        "canonical_field",
        "selected_value",
        "source_column",
        "source_value",
        "source_system",
        "source_row_number",
        "source_timestamp",
        "was_selected",
        "confidence",
    ]
    provenance = provenance_rows(fieldnames, prepared, groups, canonical_rows, canonical_columns)
    write_csv(output_dir / "company_field_provenance.csv", provenance_fieldnames, provenance)
    audit_fieldnames = ["canonical_company_id", "source_row_number", "company_id", "companyenrich_id", *AUDIT_COLUMNS]
    write_csv(output_dir / "company_enrichment_audit.csv", audit_fieldnames, audit_rows(groups, prepared, canonical_rows))
    conflict_fieldnames = [
        "candidate_company_id",
        "source_row_numbers",
        "conflicting_field",
        "candidate_values",
        "candidate_sources",
        "selected_value",
        "selection_reason",
        "confidence",
        "manual_review_required",
    ]
    write_csv(output_dir / "company_merge_conflicts.csv", conflict_fieldnames, conflicts)
    possible_fieldnames = [
        "candidate_company_id",
        "source_row_numbers",
        "reason",
        "normalized_name",
        "domain",
        "company_names",
        "linkedin_urls",
        "confidence",
        "manual_review_required",
    ]
    write_csv(output_dir / "company_possible_duplicates.csv", possible_fieldnames, possible)
    report_path = output_dir / "company_consolidation_report.md"
    build_report(
        report_path,
        input_path,
        fieldnames,
        rows,
        canonical_rows,
        canonical_columns,
        groups,
        conflicts,
        possible,
        duplicate_counts,
        profiles,
        len(provenance),
        source_hash,
    )

    validate_outputs(input_path, canonical_rows, canonical_columns, source_hash)
    input_nonempty_cells = sum(is_nonempty(row.get(column, "")) for row in rows for column in fieldnames)
    return {
        "input_path": str(input_path),
        "output_dir": str(output_dir),
        "original_rows": len(rows),
        "original_columns": len(fieldnames),
        "canonical_rows": len(canonical_rows),
        "canonical_columns": len(canonical_columns),
        "merged_rows": sum(len(group) - 1 for group in groups),
        "merge_groups": sum(len(group) > 1 for group in groups),
        "conflicts": len(conflicts),
        "possible_duplicates": len(possible),
        "provenance_rows": len(provenance),
        "input_nonempty_cells": input_nonempty_cells,
        "empty_columns": [profile["source_column"] for profile in profiles if profile["completely_empty"] == "true"],
        "duplicate_groups": duplicate_counts,
        "outputs": sorted(str(path) for path in output_dir.iterdir() if path.is_file()),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        summary = run_cleaning(args.input, args.output_dir)
    except Exception as exc:  # pragma: no cover - CLI boundary
        print(f"Cleaning failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
