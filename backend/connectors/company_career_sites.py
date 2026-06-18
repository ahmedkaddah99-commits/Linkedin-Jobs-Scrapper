from __future__ import annotations

import logging
import os
import re
import time
from fnmatch import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from backend.capabilities.tailored_documents.manual_urls import (
    DEFAULT_HEADERS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    fetch_and_normalize_manual_job,
    is_valid_job_url,
)
from backend.connectors.ats_router import detect_ats, fetch_ats_jobs
from backend.connectors.company_career_discovery import detect_ats_type
from backend.domain.job_identity import canonicalize_url, compact_whitespace, dedupe_job_records
from backend.integrations.scrapeops import (
    SCRAPEOPS_POLICY_VERSION,
    SCRAPEOPS_PROXY_ENDPOINT,
    SCRAPEOPS_REQUEST_MODES,
    ScrapeOpsOutOfCreditsError,
    ScrapeOpsProxyUnavailableError,
    ScrapeOpsRequestError,
    billed_status_code,
    build_proxy_params,
    build_proxy_usage_record,
    estimate_mode_native_credits,
    estimate_mode_runner_credits,
    normalize_scrapeops_country_code,
    parse_proxy_response_envelope,
    raise_for_failure,
    request_mode_label,
    require_scrapeops_proxy_health,
    sanitize_scrapeops_text,
    sanitize_url_for_logs,
)


LOGGER = logging.getLogger(__name__)
DIRECT_JOB_LINK_HINTS = (
    "/job/",
    "/jobs/view/",
    "/jobs/details/",
    "/job-details/",
    "/job-detail/",
    "/position/",
    "/positions/",
    "/vacancy/",
    "/vacancies/",
    "/offer/",
    "/offers/",
    "/stellenanzeige/",
    "/stellenangebot/",
)
LISTING_LINK_HINTS = (
    "/career",
    "/careers",
    "/jobs",
    "/karriere",
    "/jobangebote",
    "/stellenangebote",
    "/stellenanzeigen",
    "all jobs",
    "open positions",
    "job search",
    "stellenanzeigen",
    "stellenangebote",
)
IGNORED_LINK_HINTS = (
    "mailto:",
    "javascript:",
    "/privacy",
    "/terms",
    "/cookie",
    "/cookies",
    "/contact",
    "/about",
    "/news",
    "/blog",
    "/press",
    "/login",
    "/signin",
    "/sign-in",
)

REGULAR_COMPANY_SITE_FILES = (
    Path("user_config") / "discovered_regular_company_career_sites.txt",
)
ACADEMIC_CAREER_SITE_FILES = (
    Path("user_config") / "discovered_phd_university_career_sites.txt",
)
DISCOVERED_COMPANY_SITE_FILES = (
    *REGULAR_COMPANY_SITE_FILES,
    *ACADEMIC_CAREER_SITE_FILES,
    Path("user_config") / "discovered_company_career_sites.txt",
)
ACTIVE_COMPANY_SITE_ACCESS_METHOD = "scrapeops_proxy"
LEGACY_DIRECT_SCRAPER_STATUS = "inactive"
LOCALITY_MODE_LOCAL_PREFERRED = "local_preferred"
LOCALITY_MODE_STRICT_LOCAL_ONLY = "strict_local_only"
DEFAULT_SITE_REQUEST_MODES = ("basic", "render_js_cheap")
DEFAULT_JOB_DETAIL_REQUEST_MODES = ("basic",)
DEFAULT_MAX_JOB_LINKS_PER_SITE = 25
RUN_CREDIT_BUDGET_EXHAUSTED_MESSAGE = "This run reached its runner-credit budget before the next company-site request."
JOB_HINT_WORDS = {
    "job",
    "jobs",
    "karriere",
    "career",
    "careers",
    "vacancy",
    "vacancies",
    "opening",
    "openings",
    "position",
    "positions",
    "role",
    "roles",
    "bewerbung",
    "bewerben",
}
JOB_HINT_PHRASES = (
    "job search",
    "all jobs",
    "open positions",
    "stellenanzeige",
    "stellenanzeigen",
    "stellenangebot",
    "stellenangebote",
    "work with us",
    "work-with-us",
)
NON_JOB_CAREER_PAGE_HINTS = (
    "/about",
    "/benefits",
    "/bistro",
    "/blog",
    "/candidate-profile",
    "/contact",
    "/culture",
    "/dei",
    "/diversity",
    "/education",
    "/events",
    "/faq",
    "/graduates",
    "/how-to-apply",
    "/internship",
    "/life-at",
    "/locations",
    "/login",
    "/markenkraftstoffe",
    "/museum",
    "/people",
    "/press",
    "/privacy",
    "/students",
    "/talent-community",
    "/team",
    "/working-with-us",
    "candidate profile",
    "company culture",
    "diversity",
    "how to apply",
    "life at",
    "locations",
    "student",
    "students",
    "talent community",
    "tankstellen",
    "tankstellenmuseum",
    "working with us",
)
GLOBAL_URL_HINTS = (
    "/global",
    "/worldwide",
    "/international",
)
COUNTRY_URL_TOKENS = {
    "DE": {"de", "de-de", "germany", "deutschland", "german"},
    "GB": {"gb", "uk", "en-gb", "united-kingdom", "britain", "england"},
    "NL": {"nl", "netherlands", "nederland"},
    "AT": {"at", "austria", "osterreich", "österreich"},
    "CH": {"ch", "switzerland", "schweiz", "suisse"},
    "BE": {"be", "belgium", "belgie", "belgique"},
    "LU": {"lu", "luxembourg"},
    "FR": {"fr", "france", "fr-fr"},
    "ES": {"es", "spain", "espana", "españa"},
    "HK": {"hk", "hong-kong"},
    "PL": {"pl", "poland", "polska"},
    "SE": {"se", "sweden", "sverige"},
    "TH": {"th", "thailand"},
    "US": {"us", "usa", "united-states", "america"},
}


@dataclass(frozen=True, slots=True)
class PageFetchResult:
    requested_url: str
    final_url: str
    status_code: int
    text: str
    used_proxy: bool = False
    request_mode: str = "basic"
    request_mode_label: str = "Basic Proxy"
    billed_native_credits: int = 0
    billed_runner_credits: int = 0


@dataclass(frozen=True, slots=True)
class CompanySiteScopePlan:
    selected_sites: list[dict[str, Any]]
    skipped_sites: list[dict[str, Any]]
    stats: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SiteCandidateCollection:
    candidates: list[dict[str, Any]]
    discovered_count: int
    followed_count: int
    skipped_count: int
    skipped_reasons: list[dict[str, Any]]
    link_cap_hit: bool = False


class CompanySiteRunCreditBudgetExhausted(RuntimeError):
    pass


def _discovery_path_variants(path_value: Any) -> list[Path]:
    path = Path(path_value)
    variants = [path]
    if path.suffix.lower() == ".txt":
        variants.append(path.with_suffix(".live.txt"))
    deduped: list[Path] = []
    seen = set()
    for variant in variants:
        normalized = str(variant)
        if normalized in seen:
            continue
        deduped.append(variant)
        seen.add(normalized)
    return deduped


def _same_host_family(candidate_url: str, base_url: str) -> bool:
    candidate_host = (urlparse(candidate_url).netloc or "").lower().split(":")[0]
    base_host = (urlparse(base_url).netloc or "").lower().split(":")[0]
    if not candidate_host or not base_host:
        return False
    return candidate_host == base_host or candidate_host.endswith(f".{base_host}") or base_host.endswith(f".{candidate_host}")


def _normalize_keywords(raw_keywords: Any) -> list[str]:
    if isinstance(raw_keywords, str):
        values = [item.strip() for item in raw_keywords.split(",") if item.strip()]
    elif isinstance(raw_keywords, (list, tuple, set)):
        values = [str(item).strip() for item in raw_keywords if str(item).strip()]
    else:
        return []
    deduped: list[str] = []
    seen = set()
    for value in values:
        lowered = value.lower()
        if lowered in seen:
            continue
        deduped.append(lowered)
        seen.add(lowered)
    return deduped


def _has_any_hint(haystack: str, hints: tuple[str, ...]) -> bool:
    lowered = haystack.lower()
    return any(token in lowered for token in hints)


def _normalize_country_codes(raw_value: Any) -> list[str]:
    if isinstance(raw_value, str):
        values = [item.strip().upper() for item in raw_value.replace(",", "\n").splitlines() if item.strip()]
    elif isinstance(raw_value, (list, tuple, set)):
        values = [str(item).strip().upper() for item in raw_value if str(item).strip()]
    else:
        return []
    deduped: list[str] = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        deduped.append(value)
        seen.add(value)
    return deduped


def _normalize_city_names(raw_value: Any) -> list[str]:
    if isinstance(raw_value, str):
        values = [item.strip() for item in raw_value.replace(",", "\n").splitlines() if item.strip()]
    elif isinstance(raw_value, (list, tuple, set)):
        values = [compact_whitespace(str(item)) for item in raw_value if compact_whitespace(str(item))]
    else:
        return []
    deduped: list[str] = []
    seen = set()
    for value in values:
        lowered = value.casefold()
        if lowered in seen:
            continue
        deduped.append(value)
        seen.add(lowered)
    return deduped


def _normalized_text_tokens(value: str) -> str:
    lowered = sanitize_scrapeops_text(value).casefold()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    return f"-{lowered.strip('-')}-" if lowered.strip("-") else ""


def _word_token_set(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", sanitize_scrapeops_text(value).casefold()))


def _has_job_link_hint(value: str) -> bool:
    haystack = sanitize_scrapeops_text(value).casefold()
    if any(phrase in haystack for phrase in JOB_HINT_PHRASES):
        return True
    return bool(_word_token_set(haystack).intersection(JOB_HINT_WORDS))


def _country_tokens(country_codes: list[str]) -> dict[str, set[str]]:
    return {code: set(COUNTRY_URL_TOKENS.get(code, {code.lower()})) for code in country_codes}


def _locality_signal_for_text(
    value: str,
    *,
    target_country_codes: list[str],
    target_cities: list[str],
) -> dict[str, Any]:
    normalized = _normalized_text_tokens(value)
    matched_target_cities: list[str] = []
    matched_target_countries: list[str] = []
    matched_foreign_countries: list[str] = []
    for city in target_cities:
        city_token = _normalized_text_tokens(city)
        if city_token and city_token in normalized:
            matched_target_cities.append(city)
    target_tokens = _country_tokens(target_country_codes)
    for code, tokens in target_tokens.items():
        if any(f"-{token}-" in normalized for token in tokens):
            matched_target_countries.append(code)
    for code, tokens in COUNTRY_URL_TOKENS.items():
        if code in target_country_codes:
            continue
        if any(f"-{token}-" in normalized for token in tokens):
            matched_foreign_countries.append(code)
    is_global = any(token in value.lower() for token in GLOBAL_URL_HINTS)
    if matched_target_cities or matched_target_countries:
        return {
            "signal": "local",
            "matched_target_cities": matched_target_cities,
            "matched_target_countries": matched_target_countries,
            "matched_foreign_countries": matched_foreign_countries,
            "is_global": is_global,
        }
    if matched_foreign_countries:
        return {
            "signal": "foreign",
            "matched_target_cities": [],
            "matched_target_countries": [],
            "matched_foreign_countries": matched_foreign_countries,
            "is_global": is_global,
        }
    if is_global:
        return {
            "signal": "global",
            "matched_target_cities": [],
            "matched_target_countries": [],
            "matched_foreign_countries": [],
            "is_global": True,
        }
    return {
        "signal": "unknown",
        "matched_target_cities": [],
        "matched_target_countries": [],
        "matched_foreign_countries": [],
        "is_global": False,
    }


def _site_locality_signal(
    site_url: str,
    *,
    target_country_codes: list[str],
    target_cities: list[str],
) -> dict[str, Any]:
    return _locality_signal_for_text(
        f"{urlparse(site_url).netloc} {(urlparse(site_url).path or '').replace('/', ' ')}",
        target_country_codes=target_country_codes,
        target_cities=target_cities,
    )


def _candidate_locality_signal(
    *,
    label: str,
    url: str,
    target_country_codes: list[str],
    target_cities: list[str],
) -> dict[str, Any]:
    return _locality_signal_for_text(
        f"{label} {urlparse(url).netloc} {(urlparse(url).path or '').replace('/', ' ')}",
        target_country_codes=target_country_codes,
        target_cities=target_cities,
    )


def _normalize_locality_mode(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == LOCALITY_MODE_STRICT_LOCAL_ONLY:
        return LOCALITY_MODE_STRICT_LOCAL_ONLY
    return LOCALITY_MODE_LOCAL_PREFERRED


def _normalize_request_modes(raw_value: Any, default_modes: tuple[str, ...]) -> tuple[str, ...]:
    raw_items = raw_value if isinstance(raw_value, (list, tuple, set)) else default_modes
    normalized: list[str] = []
    for item in raw_items:
        mode = str(item or "").strip()
        if not mode or mode not in SCRAPEOPS_REQUEST_MODES or mode in normalized:
            continue
        normalized.append(mode)
    return tuple(normalized or list(default_modes))


def _matches_domain_pattern(pattern: str, host: str) -> bool:
    normalized_pattern = str(pattern or "").strip().lower()
    normalized_host = str(host or "").strip().lower().split(":")[0]
    if not normalized_pattern or not normalized_host:
        return False
    if "://" in normalized_pattern:
        normalized_pattern = (urlparse(normalized_pattern).netloc or "").lower()
    normalized_pattern = normalized_pattern.lstrip(".")
    if "*" in normalized_pattern:
        return fnmatch(normalized_host, normalized_pattern) or fnmatch(f".{normalized_host}", normalized_pattern)
    return (
        normalized_host == normalized_pattern
        or normalized_host.endswith(f".{normalized_pattern}")
        or normalized_pattern in normalized_host
    )


def _matches_text_pattern(pattern: str, value: str) -> bool:
    normalized_pattern = str(pattern or "").strip().casefold()
    normalized_value = str(value or "").strip().casefold()
    if not normalized_pattern or not normalized_value:
        return False
    if "*" in normalized_pattern:
        return fnmatch(normalized_value, normalized_pattern)
    return normalized_pattern in normalized_value


def _normalize_domain_policies(raw_value: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_value, (list, tuple)):
        return []
    policies: list[dict[str, Any]] = []
    for item in raw_value:
        if not isinstance(item, dict) or not bool(item.get("is_active", True)):
            continue
        domain_pattern = str(item.get("domain_pattern") or "").strip()
        company_name_pattern = str(item.get("company_name_pattern") or "").strip()
        if not domain_pattern and not company_name_pattern:
            continue
        try:
            priority = int(item.get("priority") or 100)
        except (TypeError, ValueError):
            priority = 100
        policies.append(
            {
                **item,
                "domain_pattern": domain_pattern,
                "company_name_pattern": company_name_pattern,
                "priority": max(0, priority),
            }
        )
    policies.sort(key=lambda policy: (int(policy.get("priority") or 0), str(policy.get("policy_id") or "")))
    return policies


def _select_domain_policy(
    *,
    site_url: str,
    company_name: str,
    domain_policies: list[dict[str, Any]],
) -> dict[str, Any]:
    host = (urlparse(site_url).netloc or "").lower()
    for policy in domain_policies:
        domain_pattern = str(policy.get("domain_pattern") or "")
        company_name_pattern = str(policy.get("company_name_pattern") or "")
        if domain_pattern and _matches_domain_pattern(domain_pattern, host):
            return policy
        if company_name_pattern and _matches_text_pattern(company_name_pattern, company_name):
            return policy
    return {}


def plan_company_site_scope(
    *,
    company_sites: Any,
    target_country_codes: Any = None,
    target_cities: Any = None,
    locality_mode: str = LOCALITY_MODE_LOCAL_PREFERRED,
    max_sites_per_run: int = -1,
    domain_policies: Any = None,
) -> CompanySiteScopePlan:
    parsed_sites = parse_company_site_entries(company_sites, limit=None)
    normalized_country_codes = _normalize_country_codes(target_country_codes)
    normalized_target_cities = _normalize_city_names(target_cities)
    normalized_locality_mode = _normalize_locality_mode(locality_mode)
    normalized_domain_policies = _normalize_domain_policies(domain_policies)
    ranked_sites: list[tuple[int, dict[str, Any]]] = []
    skipped_sites: list[dict[str, Any]] = []
    foreign_skipped = 0
    for entry in parsed_sites:
        site_policy = _select_domain_policy(
            site_url=str(entry.get("url") or ""),
            company_name=str(entry.get("company_name") or ""),
            domain_policies=normalized_domain_policies,
        )
        site_country_codes = normalized_country_codes
        if str(site_policy.get("country_code") or "").strip():
            site_country_codes = _normalize_country_codes([site_policy.get("country_code")])
        site_locality_mode = _normalize_locality_mode(site_policy.get("locality_mode") or normalized_locality_mode)
        signal = _site_locality_signal(
            str(entry.get("url") or ""),
            target_country_codes=site_country_codes,
            target_cities=normalized_target_cities,
        )
        enriched_entry = {
            **entry,
            "locality_signal": signal["signal"],
            "matched_target_countries": list(signal.get("matched_target_countries") or []),
            "matched_target_cities": list(signal.get("matched_target_cities") or []),
            "matched_foreign_countries": list(signal.get("matched_foreign_countries") or []),
            "domain_policy_id": str(site_policy.get("policy_id") or ""),
        }
        if site_country_codes and signal["signal"] == "foreign":
            skipped_sites.append(
                {
                    **enriched_entry,
                    "skip_reason": "foreign_market_site",
                }
            )
            foreign_skipped += 1
            continue
        score = {
            "local": 0,
            "global": 1,
            "unknown": 2,
        }.get(signal["signal"], 3)
        if site_locality_mode == LOCALITY_MODE_STRICT_LOCAL_ONLY and signal["signal"] == "unknown":
            score = 2
        ranked_sites.append((score, enriched_entry))

    ranked_sites.sort(
        key=lambda item: (
            item[0],
            str(item[1].get("company_name") or "").casefold(),
            str(item[1].get("url") or "").casefold(),
        )
    )
    selected_sites = [item for _, item in ranked_sites]
    truncated_sites = 0
    normalized_site_limit = int(max_sites_per_run or 0)
    if normalized_site_limit > 0 and len(selected_sites) > normalized_site_limit:
        kept_sites = selected_sites[:normalized_site_limit]
        overflow_sites = selected_sites[normalized_site_limit:]
        truncated_sites = len(overflow_sites)
        selected_sites = kept_sites
        skipped_sites.extend(
            [
                {
                    **entry,
                    "skip_reason": "plan_company_site_limit",
                }
                for entry in overflow_sites
            ]
        )

    local_site_count = sum(1 for item in selected_sites if str(item.get("locality_signal") or "") == "local")
    global_site_count = sum(1 for item in selected_sites if str(item.get("locality_signal") or "") == "global")
    unknown_site_count = sum(1 for item in selected_sites if str(item.get("locality_signal") or "") == "unknown")
    return CompanySiteScopePlan(
        selected_sites=selected_sites,
        skipped_sites=skipped_sites,
        stats={
            "policy_version": SCRAPEOPS_POLICY_VERSION,
            "target_country_codes": list(normalized_country_codes),
            "target_cities": list(normalized_target_cities),
            "locality_mode": normalized_locality_mode,
            "input_site_count": len(parsed_sites),
            "selected_site_count": len(selected_sites),
            "skipped_site_count": len(skipped_sites),
            "foreign_site_skipped_count": foreign_skipped,
            "plan_site_limit_applied_count": truncated_sites,
            "local_site_count": local_site_count,
            "global_site_count": global_site_count,
            "unknown_site_count": unknown_site_count,
        },
    )


def estimate_company_site_runner_credit_range(
    *,
    site_count: int,
    locality_mode: str,
    has_target_country: bool,
    run_credit_budget: int = -1,
) -> dict[str, Any]:
    normalized_site_count = max(0, int(site_count))
    normalized_locality_mode = _normalize_locality_mode(locality_mode)
    if normalized_site_count == 0:
        return {
            "min_runner_credits": 0,
            "likely_runner_credits": 0,
            "max_runner_credits": 0,
            "confidence": "high",
        }
    base_min = normalized_site_count * estimate_mode_runner_credits("basic")
    likely_multiplier = 6 if has_target_country else 8
    max_multiplier = 16 if normalized_locality_mode == LOCALITY_MODE_STRICT_LOCAL_ONLY else 20
    estimate = {
        "min_runner_credits": base_min,
        "likely_runner_credits": normalized_site_count * likely_multiplier,
        "max_runner_credits": normalized_site_count * max_multiplier,
        "confidence": "medium",
    }
    if int(run_credit_budget or 0) > 0:
        estimate["max_runner_credits"] = min(int(run_credit_budget), int(estimate["max_runner_credits"]))
        estimate["likely_runner_credits"] = min(int(run_credit_budget), int(estimate["likely_runner_credits"]))
    return estimate


def _looks_like_direct_job_link(url: str, label: str = "") -> bool:
    haystack = f"{label} {url}".lower()
    if _has_any_hint(haystack, DIRECT_JOB_LINK_HINTS):
        return True
    path = (urlparse(url).path or "").lower()
    path_segments = [segment for segment in re.split(r"/+", path) if segment]
    if len(path_segments) >= 2:
        parent_segment = path_segments[-2]
        leaf_segment = path_segments[-1]
        if parent_segment in {
            "job",
            "jobs",
            "position",
            "positions",
            "opening",
            "openings",
            "offer",
            "offers",
            "role",
            "roles",
            "stelle",
            "stellen",
            "posting",
            "postings",
            "vacancy",
            "vacancies",
        } and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,}", leaf_segment):
            return True
    return bool(re.search(r"(?:^|[-_/])(job|req|position|offer|stelle|posting)[-_]?[a-z0-9]{2,}", path))


def _looks_like_non_job_career_content(url: str, label: str = "") -> bool:
    if _looks_like_direct_job_link(url, label):
        return False
    haystack = f"{label} {url}".lower()
    return any(token in haystack for token in NON_JOB_CAREER_PAGE_HINTS)


def _looks_like_listing_link(url: str, label: str = "") -> bool:
    if _looks_like_direct_job_link(url, label):
        return False
    if _looks_like_non_job_career_content(url, label):
        return False
    haystack = f"{label} {url}".lower()
    if _has_any_hint(haystack, LISTING_LINK_HINTS):
        return True
    if not detect_ats_type(url):
        return False
    normalized_path = re.sub(r"/{2,}", "/", (urlparse(url).path or "/")).rstrip("/")
    return normalized_path.count("/") <= 2


def _job_like_link_score(text: str, href: str) -> int:
    haystack = f"{text} {href}".lower()
    score = 0
    if _looks_like_non_job_career_content(href, text):
        return 0
    if _has_job_link_hint(haystack):
        score += 1
    if detect_ats_type(href):
        score += 2
    if _looks_like_listing_link(href, text):
        score += 1
    if _looks_like_direct_job_link(href, text):
        score += 4
    return score


def parse_company_site_entries(raw_value: Any, *, limit: int | None = None) -> list[dict[str, str]]:
    if isinstance(raw_value, str):
        raw_entries = [
            line.strip()
            for line in raw_value.replace(",", "\n").splitlines()
            if line.strip()
        ]
    elif isinstance(raw_value, (list, tuple, set)):
        raw_entries = []
        for item in raw_value:
            if isinstance(item, str):
                raw_entries.extend(
                    [line.strip() for line in item.replace(",", "\n").splitlines() if line.strip()]
                )
            else:
                raw_entries.append(item)
    else:
        return []

    max_entries = None if limit is None else max(0, int(limit))
    parsed_entries: list[dict[str, str]] = []
    seen_urls = set()
    for entry in raw_entries:
        company_name = ""
        url = ""
        if isinstance(entry, dict):
            company_name = compact_whitespace(
                str(
                    entry.get("company_name")
                    or entry.get("company")
                    or entry.get("name")
                    or entry.get("Company name")
                    or ""
                )
            )
            url = compact_whitespace(
                str(
                    entry.get("url")
                    or entry.get("career_site_url")
                    or entry.get("primary_career_url")
                    or entry.get("career_url")
                    or ""
                )
            )
        else:
            text = compact_whitespace(str(entry))
            if not text:
                continue
            if "|" in text:
                left, right = [compact_whitespace(part) for part in text.split("|", 1)]
                if is_valid_job_url(right):
                    company_name, url = left, right
                elif is_valid_job_url(left):
                    company_name, url = right, left
                else:
                    company_name, url = left, right
            else:
                url = text
        if not is_valid_job_url(url):
            continue
        normalized_url = canonicalize_url(url) or url
        if normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        parsed_entries.append(
            {
                "company_name": company_name,
                "url": normalized_url,
            }
        )
        if max_entries is not None and len(parsed_entries) >= max_entries:
            break
    return parsed_entries


def load_discovered_company_site_entries(paths: Any = None) -> list[dict[str, str]]:
    source_paths = paths or DISCOVERED_COMPANY_SITE_FILES
    entries: list[dict[str, str]] = []
    seen_urls = set()

    for path_value in source_paths:
        for path in _discovery_path_variants(path_value):
            if not path.exists() or not path.is_file():
                continue
            parsed_entries = parse_company_site_entries(path.read_text(encoding="utf-8"), limit=None)
            for entry in parsed_entries:
                url = entry.get("url") or ""
                if not url or url in seen_urls:
                    continue
                entries.append(entry)
                seen_urls.add(url)

    return entries


def extract_company_job_links_from_html(
    *,
    page_url: str,
    homepage_url: str = "",
    html: str,
    max_links: int = 20,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[int, dict[str, Any]]] = []
    seen = set()
    normalized_page_url = canonicalize_url(page_url) or page_url
    base_homepage_url = homepage_url or page_url

    for anchor in soup.select("a[href]"):
        raw_href = compact_whitespace(str(anchor.get("href") or ""))
        if not raw_href:
            continue
        lower_href = raw_href.lower()
        if any(token in lower_href for token in IGNORED_LINK_HINTS):
            continue
        href = urljoin(page_url, raw_href)
        if not is_valid_job_url(href):
            continue
        normalized_href = canonicalize_url(href) or href
        if normalized_href == normalized_page_url:
            continue
        if not detect_ats_type(normalized_href) and not _same_host_family(normalized_href, base_homepage_url):
            continue
        if normalized_href in seen:
            continue

        text = compact_whitespace(anchor.get_text(" ", strip=True))
        if _looks_like_non_job_career_content(normalized_href, text):
            continue
        score = _job_like_link_score(text, normalized_href)
        if score <= 0:
            continue

        seen.add(normalized_href)
        candidates.append(
            (
                score,
                {
                    "url": normalized_href,
                    "label": text or normalized_href,
                    "is_listing_page": _looks_like_listing_link(normalized_href, text),
                },
            )
        )

    candidates.sort(key=lambda item: (-item[0], item[1]["label"].lower()))
    normalized_max_links = int(max_links or 0)
    if normalized_max_links <= 0:
        return [payload for _, payload in candidates]
    return [payload for _, payload in candidates[: max(1, normalized_max_links)]]


def _fetch_page_content_direct_inactive(
    url: str,
    *,
    request_timeout_seconds: int,
) -> PageFetchResult:
    """Inactive legacy direct-fetch path preserved for future experiments.

    Live company-site acquisition uses ScrapeOps only.
    """
    requested_url = canonicalize_url(url) or compact_whitespace(url)
    timeout_seconds = max(5, int(request_timeout_seconds))
    response = requests.get(
        requested_url,
        headers=DEFAULT_HEADERS,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return PageFetchResult(
        requested_url=requested_url,
        final_url=response.url or requested_url,
        status_code=int(response.status_code),
        text=response.text,
        used_proxy=False,
    )


def _fetch_page_content(
    url: str,
    *,
    request_timeout_seconds: int,
    request_mode: str = "basic",
    country_code: str = "",
    company_name: str = "",
    request_stage: str = "fetch_company_site",
    usage_callback=None,
    proxy_health_check=None,
) -> PageFetchResult:
    requested_url = canonicalize_url(url) or compact_whitespace(url)
    timeout_seconds = max(5, int(request_timeout_seconds))
    scrapeops_api_key = os.getenv("SCRAPEOPS_API_KEY", "").strip()
    if not scrapeops_api_key:
        raise RuntimeError(
            "SCRAPEOPS_API_KEY is required for company career site acquisition. "
            "The legacy direct scraper is inactive."
        )

    proxy_params = build_proxy_params(
        api_key=scrapeops_api_key,
        url=requested_url,
        mode=request_mode,
        country_code=country_code,
    )
    sanitized_target_url = sanitize_url_for_logs(requested_url)
    domain = (urlparse(requested_url).netloc or "").lower()
    if callable(proxy_health_check):
        proxy_health_check()
    else:
        require_scrapeops_proxy_health(scrapeops_api_key)
    response = None
    request_started = time.perf_counter()
    try:
        response = requests.get(
            SCRAPEOPS_PROXY_ENDPOINT,
            params=proxy_params,
            headers=DEFAULT_HEADERS,
            timeout=max(10, timeout_seconds),
        )
    except requests.RequestException as exc:
        safe_message = sanitize_scrapeops_text(str(exc)) or "ScrapeOps request failed."
        if callable(usage_callback):
            usage_callback(
                {
                    **build_proxy_usage_record(
                        source_id=company_name or domain,
                        target_url=requested_url,
                        request_mode=request_mode,
                        target_status_code=0,
                        provider_status_code=0,
                        latency_ms=round((time.perf_counter() - request_started) * 1000),
                        billed_credits_actual=0,
                        billed_credits_estimated=0,
                        error_category="network_error",
                    ),
                    "target_url": sanitized_target_url,
                    "domain": domain,
                    "status_code": 0,
                    "billed": False,
                    "request_mode": request_mode,
                    "request_mode_label": request_mode_label(request_mode),
                    "native_credits": 0,
                    "runner_credits": 0,
                    "request_stage": request_stage,
                    "company_name": company_name,
                    "error_category": "network_error",
                    "error_message": safe_message,
                }
            )
        raise RuntimeError(f"scrapeops: {safe_message}") from exc

    envelope = parse_proxy_response_envelope(response)
    response.status_code = envelope.target_status_code
    response._content = envelope.body.encode(response.encoding or "utf-8")
    billed = billed_status_code(envelope.target_status_code)
    estimated_credits = estimate_mode_native_credits(request_mode) if billed else 0
    actual_credits = envelope.billed_credits_actual if billed else 0
    accounted_credits = actual_credits if actual_credits is not None else estimated_credits
    native_credits = accounted_credits
    runner_credits = accounted_credits
    failure: ScrapeOpsRequestError | None = None
    if response.status_code >= 400:
        try:
            raise_for_failure(response, fallback_message="ScrapeOps request failed.")
        except ScrapeOpsRequestError as exc:
            failure = exc
    if callable(usage_callback):
        usage_callback(
            {
                **build_proxy_usage_record(
                    source_id=company_name or domain,
                    target_url=requested_url,
                    request_mode=request_mode,
                    target_status_code=envelope.target_status_code,
                    provider_status_code=envelope.provider_status_code,
                    latency_ms=round((time.perf_counter() - request_started) * 1000),
                    billed_credits_actual=actual_credits,
                    billed_credits_estimated=estimated_credits,
                    error_category=failure.failure.category if failure else "",
                ),
                "target_url": sanitized_target_url,
                "domain": domain,
                "status_code": envelope.target_status_code,
                "billed": billed,
                "request_mode": request_mode,
                "request_mode_label": request_mode_label(request_mode),
                "native_credits": native_credits,
                "runner_credits": runner_credits,
                "request_stage": request_stage,
                "company_name": company_name,
                "error_category": failure.failure.category if failure else "",
                "error_message": str(failure) if failure else "",
            }
        )
    if failure is not None:
        if isinstance(failure, ScrapeOpsOutOfCreditsError):
            raise failure
        raise RuntimeError(f"scrapeops: {failure}") from failure

    return PageFetchResult(
        requested_url=requested_url,
        final_url=requested_url,
        status_code=int(response.status_code),
        text=response.text,
        used_proxy=True,
        request_mode=request_mode,
        request_mode_label=request_mode_label(request_mode),
        billed_native_credits=native_credits,
        billed_runner_credits=runner_credits,
    )


def _collect_candidate_links_for_page(
    page_url: str,
    *,
    homepage_url: str,
    request_timeout_seconds: int,
    max_links: int,
    request_mode: str,
    country_code: str,
    company_name: str,
    usage_callback=None,
    proxy_health_check=None,
) -> list[dict[str, Any]]:
    fetch_result = _fetch_page_content(
        page_url,
        request_timeout_seconds=request_timeout_seconds,
        request_mode=request_mode,
        country_code=country_code,
        company_name=company_name,
        request_stage="fetch_company_site",
        usage_callback=usage_callback,
        proxy_health_check=proxy_health_check,
    )

    links = extract_company_job_links_from_html(
        page_url=fetch_result.final_url or page_url,
        homepage_url=homepage_url,
        html=fetch_result.text,
        max_links=max_links,
    )
    return links


def _dedupe_candidate_links(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen_urls = set()
    for candidate in candidates:
        normalized_url = canonicalize_url(str(candidate.get("url") or "")) or str(candidate.get("url") or "")
        if not normalized_url or normalized_url in seen_urls:
            continue
        deduped.append({**candidate, "url": normalized_url})
        seen_urls.add(normalized_url)
    return deduped


def _expand_listing_page_candidates(
    candidate: dict[str, Any],
    *,
    homepage_url: str,
    request_timeout_seconds: int,
    max_links: int,
    request_mode: str,
    country_code: str,
    company_name: str,
    usage_callback=None,
    proxy_health_check=None,
) -> list[dict[str, Any]]:
    nested_links = _collect_candidate_links_for_page(
        str(candidate.get("url") or ""),
        homepage_url=homepage_url,
        request_timeout_seconds=request_timeout_seconds,
        max_links=max_links,
        request_mode=request_mode,
        country_code=country_code,
        company_name=company_name,
        usage_callback=usage_callback,
        proxy_health_check=proxy_health_check,
    )
    direct_links = [
        item for item in nested_links
        if _looks_like_direct_job_link(str(item.get("url") or ""), str(item.get("label") or ""))
    ]
    return direct_links


def _collect_job_candidates_for_site(
    *,
    site_url: str,
    request_timeout_seconds: int,
    company_name: str,
    request_modes: tuple[str, ...],
    country_code: str,
    locality_mode: str,
    target_country_codes: list[str],
    target_cities: list[str],
    max_job_links_per_site: int,
    usage_callback=None,
    should_spend_request_mode=None,
    proxy_health_check=None,
) -> SiteCandidateCollection:
    last_error: Exception | None = None
    initial_candidates: list[dict[str, Any]] = []
    initial_request_attempted = False
    initial_budget_blocked = False
    for request_mode in request_modes or DEFAULT_SITE_REQUEST_MODES:
        if callable(should_spend_request_mode) and not should_spend_request_mode(request_mode):
            initial_budget_blocked = True
            continue
        initial_request_attempted = True
        try:
            initial_candidates = _collect_candidate_links_for_page(
                site_url,
                homepage_url=site_url,
                request_timeout_seconds=request_timeout_seconds,
                max_links=max_job_links_per_site + 1,
                request_mode=request_mode,
                country_code=country_code,
                company_name=company_name,
                usage_callback=usage_callback,
                proxy_health_check=proxy_health_check,
            )
        except Exception as exc:
            if isinstance(exc, ScrapeOpsProxyUnavailableError):
                raise
            last_error = exc
            continue
        if initial_candidates:
            break
    if not initial_request_attempted and initial_budget_blocked:
        raise CompanySiteRunCreditBudgetExhausted(RUN_CREDIT_BUDGET_EXHAUSTED_MESSAGE)
    if last_error is not None and not initial_candidates:
        raise last_error
    if not initial_candidates:
        return SiteCandidateCollection(
            candidates=[],
            discovered_count=0,
            followed_count=0,
            skipped_count=0,
            skipped_reasons=[],
        )

    direct_candidates = [
        candidate for candidate in initial_candidates
        if not bool(candidate.get("is_listing_page"))
        and _looks_like_direct_job_link(str(candidate.get("url") or ""), str(candidate.get("label") or ""))
    ]
    listing_candidates = [candidate for candidate in initial_candidates if bool(candidate.get("is_listing_page"))]
    collected_candidates = _dedupe_candidate_links(direct_candidates)
    skipped_reasons: list[dict[str, Any]] = []

    for candidate in listing_candidates:
        if len(collected_candidates) >= max(1, int(max_job_links_per_site)) + 1:
            break
        expanded_candidates: list[dict[str, Any]] = []
        expanded_request_attempted = False
        expanded_budget_blocked = False
        for request_mode in request_modes or DEFAULT_SITE_REQUEST_MODES:
            if callable(should_spend_request_mode) and not should_spend_request_mode(request_mode):
                expanded_budget_blocked = True
                continue
            expanded_request_attempted = True
            try:
                expanded_candidates = _expand_listing_page_candidates(
                    candidate,
                    homepage_url=site_url,
                    request_timeout_seconds=request_timeout_seconds,
                    max_links=max_job_links_per_site + 1,
                    request_mode=request_mode,
                    country_code=country_code,
                    company_name=company_name,
                    usage_callback=usage_callback,
                    proxy_health_check=proxy_health_check,
                )
            except Exception as exc:
                if isinstance(exc, ScrapeOpsProxyUnavailableError):
                    raise
                continue
            if expanded_candidates:
                break
        if not expanded_request_attempted and expanded_budget_blocked:
            raise CompanySiteRunCreditBudgetExhausted(RUN_CREDIT_BUDGET_EXHAUSTED_MESSAGE)
        for expanded_candidate in _dedupe_candidate_links(expanded_candidates):
            if len(collected_candidates) >= max(1, int(max_job_links_per_site)) + 1:
                break
            if any(existing.get("url") == expanded_candidate.get("url") for existing in collected_candidates):
                continue
            collected_candidates.append(expanded_candidate)

    discovered_candidates = _dedupe_candidate_links(collected_candidates)
    followed_candidates: list[dict[str, Any]] = []
    for candidate in discovered_candidates:
        signal = _candidate_locality_signal(
            label=str(candidate.get("label") or ""),
            url=str(candidate.get("url") or ""),
            target_country_codes=target_country_codes,
            target_cities=target_cities,
        )
        if target_country_codes and signal["signal"] == "foreign":
            skipped_reasons.append(
                {
                    "url": str(candidate.get("url") or ""),
                    "reason": "foreign_market_candidate",
                }
            )
            continue
        followed_candidates.append(
            {
                **candidate,
                "locality_signal": signal["signal"],
                "matched_target_cities": list(signal.get("matched_target_cities") or []),
                "matched_target_countries": list(signal.get("matched_target_countries") or []),
            }
        )

    discovered_count = len(discovered_candidates)
    capped_candidates = followed_candidates
    link_cap_hit = False
    normalized_ceiling = max(1, int(max_job_links_per_site))
    if len(capped_candidates) > normalized_ceiling:
        link_cap_hit = True
        overflow = capped_candidates[normalized_ceiling:]
        capped_candidates = capped_candidates[:normalized_ceiling]
        skipped_reasons.extend(
            [
                {
                    "url": str(item.get("url") or ""),
                    "reason": "company_site_max_job_links_per_site",
                }
                for item in overflow
            ]
        )

    return SiteCandidateCollection(
        candidates=capped_candidates,
        discovered_count=discovered_count,
        followed_count=len(capped_candidates),
        skipped_count=max(0, discovered_count - len(capped_candidates)),
        skipped_reasons=skipped_reasons,
        link_cap_hit=link_cap_hit,
    )


def _normalize_company_job_with_modes(
    candidate_url: str,
    *,
    scrapeops_api_key: str,
    request_timeout_seconds: int,
    job_detail_request_modes: tuple[str, ...],
    country_code: str,
    company_name: str,
    usage_callback=None,
    should_spend_request_mode=None,
    proxy_health_check=None,
) -> dict[str, Any]:
    last_error: Exception | None = None
    request_attempted = False
    budget_blocked = False
    for request_mode in job_detail_request_modes or DEFAULT_JOB_DETAIL_REQUEST_MODES:
        if callable(should_spend_request_mode) and not should_spend_request_mode(request_mode):
            budget_blocked = True
            continue
        request_attempted = True
        try:
            job = fetch_and_normalize_manual_job(
                candidate_url,
                scrapeops_api_key=scrapeops_api_key,
                force_scrapeops=True,
                request_timeout_seconds=request_timeout_seconds,
                scrapeops_mode=request_mode,
                scrapeops_country_code=country_code,
                usage_callback=usage_callback,
                usage_stage="normalize_company_job",
                usage_company_name=company_name,
                proxy_health_check=proxy_health_check,
            )
        except Exception as exc:
            last_error = exc
            if isinstance(exc, (ScrapeOpsOutOfCreditsError, ScrapeOpsProxyUnavailableError)):
                raise
            continue
        title = compact_whitespace(str(job.get("title") or ""))
        description = compact_whitespace(str(job.get("full_description") or ""))
        if title or description:
            return job
        last_error = RuntimeError("Normalized job payload was empty.")
    if not request_attempted and budget_blocked:
        raise CompanySiteRunCreditBudgetExhausted(RUN_CREDIT_BUDGET_EXHAUSTED_MESSAGE)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Unable to normalize company job.")


def _job_is_within_public_posting_window(job: dict[str, Any], posted_within_days: int) -> bool:
    normalized_days = max(0, int(posted_within_days or 0))
    if normalized_days <= 0:
        return True
    posted_age_hours = job.get("posted_age_hours")
    if posted_age_hours in (None, ""):
        return True
    try:
        return float(posted_age_hours) <= normalized_days * 24
    except (TypeError, ValueError):
        return True


def scrape_company_career_sites(
    *,
    company_sites: Any,
    keywords: Any = None,
    request_timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    max_jobs_per_site: int = 0,
    use_proxy_fallback: bool = False,
    target_country_codes: Any = None,
    target_cities: Any = None,
    posted_within_days: int = 0,
    locality_mode: str = LOCALITY_MODE_LOCAL_PREFERRED,
    site_request_modes: tuple[str, ...] = DEFAULT_SITE_REQUEST_MODES,
    job_detail_request_modes: tuple[str, ...] = DEFAULT_JOB_DETAIL_REQUEST_MODES,
    domain_policies: Any = None,
    max_sites_per_run: int = -1,
    run_credit_budget: int = -1,
    max_job_links_per_site: int = DEFAULT_MAX_JOB_LINKS_PER_SITE,
    usage_callback=None,
    logger=None,
    progress_callback=None,
    should_cancel=None,
    yield_callback=None,
    seen_job_url_lookup=None,
    cached_job_lookup=None,
    job_url_history_callback=None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active_logger = logger or LOGGER
    scope_plan = plan_company_site_scope(
        company_sites=company_sites,
        target_country_codes=target_country_codes,
        target_cities=target_cities,
        locality_mode=locality_mode,
        max_sites_per_run=max_sites_per_run,
        domain_policies=domain_policies,
    )
    parsed_sites = list(scope_plan.selected_sites)
    normalized_keywords = _normalize_keywords(keywords)
    normalized_country_codes = _normalize_country_codes(target_country_codes)
    normalized_target_cities = _normalize_city_names(target_cities)
    normalized_locality_mode = _normalize_locality_mode(locality_mode)
    normalized_domain_policies = _normalize_domain_policies(domain_policies)
    base_site_request_modes = _normalize_request_modes(site_request_modes, DEFAULT_SITE_REQUEST_MODES)
    base_job_detail_request_modes = _normalize_request_modes(job_detail_request_modes, DEFAULT_JOB_DETAIL_REQUEST_MODES)
    scrapeops_api_key = os.getenv("SCRAPEOPS_API_KEY", "").strip()
    collected_jobs: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    processed_sites = 0
    failed_sites = 0
    discovered_candidates_total = 0
    followed_candidates_total = 0
    skipped_candidates_total = 0
    link_cap_hits = 0
    capped_sites: list[dict[str, Any]] = []
    keyword_filtered_jobs = 0
    incremental_skipped_job_urls = 0
    public_index_reused_job_urls = 0
    runner_credits_consumed = 0
    native_credits_consumed = 0
    billed_request_count = 0
    request_count = 0
    explicit_job_cap = max(0, int(max_jobs_per_site or 0))
    normalized_run_credit_budget = max(0, int(run_credit_budget or 0))
    proxy_health_confirmed = False

    def ensure_proxy_health() -> None:
        nonlocal proxy_health_confirmed
        if proxy_health_confirmed:
            return
        require_scrapeops_proxy_health(scrapeops_api_key, usage_callback=on_usage_event)
        proxy_health_confirmed = True

    def should_spend_request_mode(request_mode: str) -> bool:
        if normalized_run_credit_budget <= 0:
            return True
        return runner_credits_consumed + estimate_mode_runner_credits(request_mode) <= normalized_run_credit_budget

    def on_usage_event(event: dict[str, Any]) -> None:
        nonlocal request_count, billed_request_count, runner_credits_consumed, native_credits_consumed
        request_count += 1
        if bool(event.get("billed")):
            billed_request_count += 1
            runner_credits_consumed += int(event.get("runner_credits") or 0)
            native_credits_consumed += int(event.get("native_credits") or 0)
        if callable(usage_callback):
            usage_callback(event)

    def emit_progress(
        *,
        company_name: str = "",
        site_url: str = "",
        message: str = "",
        active_locality_mode: str = "",
        domain_policy_id: str = "",
    ) -> None:
        if not callable(progress_callback):
            return
        recent_failures = failures[-3:] if failures else []
        progress_callback(
            {
                "message": message,
                "counters": {
                    "policy_version": SCRAPEOPS_POLICY_VERSION,
                    "input_sites": int(scope_plan.stats.get("input_site_count") or len(parsed_sites)),
                    "total_sites": len(parsed_sites),
                    "processed_sites": processed_sites,
                    "skipped_sites": int(scope_plan.stats.get("skipped_site_count") or 0),
                    "failed_sites": failed_sites,
                    "jobs_found": len(collected_jobs),
                    "candidate_jobs_discovered": discovered_candidates_total,
                    "candidate_jobs_followed": followed_candidates_total,
                    "candidate_jobs_skipped": skipped_candidates_total,
                    "incremental_skipped_job_urls": incremental_skipped_job_urls,
                    "public_index_reused_job_urls": public_index_reused_job_urls,
                    "keyword_filtered_jobs": keyword_filtered_jobs,
                    "legacy_jobs_per_site_cap": explicit_job_cap,
                    "legacy_jobs_per_site_cap_active": explicit_job_cap > 0,
                    "company_site_max_job_links_per_site": int(max_job_links_per_site),
                    "link_cap_hits": link_cap_hits,
                    "capped_sites": list(capped_sites),
                    "runner_credits_consumed": runner_credits_consumed,
                    "native_credits_consumed": native_credits_consumed,
                    "billed_request_count": billed_request_count,
                    "request_count": request_count,
                    "run_credit_budget": normalized_run_credit_budget,
                    "locality_mode": normalized_locality_mode,
                    "request_timeout_seconds": int(request_timeout_seconds),
                },
                "current_item": {
                    "company_name": company_name,
                    "site_url": site_url,
                    "access_method": ACTIVE_COMPANY_SITE_ACCESS_METHOD,
                    "locality_mode": active_locality_mode or normalized_locality_mode,
                    "target_country_codes": list(normalized_country_codes),
                    "domain_policy_id": domain_policy_id,
                },
                "recent_failures": recent_failures,
            }
        )

    def job_url_from_record(record: dict[str, Any]) -> str:
        raw_url = (
            str(record.get("apply_link") or "").strip()
            or str(record.get("source_url") or "").strip()
            or str(record.get("link") or "").strip()
            or str(record.get("url") or "").strip()
        )
        return canonicalize_url(raw_url) or raw_url

    def seen_job_urls_for_site(site_url: str, job_urls: list[str]) -> set[str]:
        normalized_urls = [canonicalize_url(url) or url for url in job_urls if str(url or "").strip()]
        if not normalized_urls or not callable(seen_job_url_lookup):
            return set()
        try:
            raw_seen = seen_job_url_lookup(site_url, normalized_urls)
        except TypeError:
            raw_seen = seen_job_url_lookup(normalized_urls)
        return {canonicalize_url(str(url or "")) or str(url or "") for url in raw_seen or [] if str(url or "").strip()}

    def cached_job_postings_for_site(site_url: str, job_urls: list[str]) -> dict[str, dict[str, Any]]:
        normalized_urls = [canonicalize_url(url) or url for url in job_urls if str(url or "").strip()]
        if not normalized_urls or not callable(cached_job_lookup):
            return {}
        try:
            raw_postings = cached_job_lookup(site_url, normalized_urls)
        except TypeError:
            raw_postings = cached_job_lookup(normalized_urls)
        if not isinstance(raw_postings, dict):
            return {}
        postings: dict[str, dict[str, Any]] = {}
        for raw_url, raw_payload in raw_postings.items():
            normalized_url = canonicalize_url(str(raw_url or "")) or str(raw_url or "")
            if not normalized_url or not isinstance(raw_payload, dict):
                continue
            payload = dict(raw_payload)
            if not compact_whitespace(str(payload.get("title") or "")):
                continue
            postings[normalized_url] = payload
        return postings

    def record_job_url_history(site_url: str, attempts: list[dict[str, Any]]) -> None:
        if not attempts or not callable(job_url_history_callback):
            return
        normalized_attempts = []
        for attempt in attempts:
            job_url = canonicalize_url(str(attempt.get("job_url") or "").strip()) or str(attempt.get("job_url") or "").strip()
            if not job_url:
                continue
            normalized_attempts.append({**attempt, "site_url": site_url, "job_url": job_url})
        if not normalized_attempts:
            return
        try:
            job_url_history_callback(site_url, normalized_attempts)
        except TypeError:
            job_url_history_callback(normalized_attempts)

    emit_progress(message="Preparing company career site discovery.")

    for site in parsed_sites:
        if callable(should_cancel) and should_cancel():
            raise RuntimeError("Run cancellation requested.")
        if normalized_run_credit_budget > 0 and runner_credits_consumed >= normalized_run_credit_budget:
            raise CompanySiteRunCreditBudgetExhausted(RUN_CREDIT_BUDGET_EXHAUSTED_MESSAGE)
        company_name = site.get("company_name") or ""
        site_url = site.get("url") or ""
        site_jobs_found = 0
        site_domain_policy = _select_domain_policy(
            site_url=site_url,
            company_name=company_name,
            domain_policies=normalized_domain_policies,
        )
        site_policy_id = str(site_domain_policy.get("policy_id") or "").strip()
        site_locality_mode = _normalize_locality_mode(
            site_domain_policy.get("locality_mode") or normalized_locality_mode
        )
        active_site_request_modes = _normalize_request_modes(
            site_domain_policy.get("site_request_modes"),
            base_site_request_modes,
        )
        active_job_detail_request_modes = _normalize_request_modes(
            site_domain_policy.get("job_detail_request_modes"),
            base_job_detail_request_modes,
        )
        site_target_country_codes = normalized_country_codes
        if str(site_domain_policy.get("country_code") or "").strip():
            site_target_country_codes = _normalize_country_codes([site_domain_policy.get("country_code")])
        site_country_code = normalize_scrapeops_country_code(
            str(site_domain_policy.get("country_code") or "").strip()
            or (site_target_country_codes[0] if len(site_target_country_codes) == 1 else "")
        )
        emit_progress(
            company_name=company_name,
            site_url=site_url,
            message=f"Scanning {company_name or site_url}",
            active_locality_mode=site_locality_mode,
            domain_policy_id=site_policy_id,
        )

        def on_site_usage_event(event: dict[str, Any]) -> None:
            enriched_event = dict(event or {})
            if site_policy_id:
                enriched_event["domain_policy_id"] = site_policy_id
            on_usage_event(enriched_event)

        ats = detect_ats(site_url)
        routed_jobs = fetch_ats_jobs(site_url, ats) if ats else []
        if routed_jobs:
            active_logger.info(
                "ATS route used for %s: %s jobs returned via %s API, 0 proxy credits consumed.",
                site_url,
                len(routed_jobs),
                ats,
            )
            for job in routed_jobs:
                candidate = dict(job)
                candidate_url = job_url_from_record(candidate)
                if company_name:
                    candidate["company"] = company_name
                searchable = " ".join(
                    [
                        compact_whitespace(str(candidate.get("title") or "")),
                        compact_whitespace(str(candidate.get("company") or "")),
                        compact_whitespace(str(candidate.get("full_description") or ""))[:1200],
                    ]
                ).lower()
                if normalized_keywords and not any(keyword in searchable for keyword in normalized_keywords):
                    keyword_filtered_jobs += 1
                    record_job_url_history(
                        site_url,
                        [
                            {
                                "job_url": candidate_url,
                                "job_id": str(candidate.get("job_id") or ""),
                                "title": str(candidate.get("title") or ""),
                                "company": str(candidate.get("company") or company_name or ""),
                                "status": "keyword_filtered",
                                "payload": candidate,
                            }
                        ],
                    )
                    continue
                if not _job_is_within_public_posting_window(candidate, posted_within_days):
                    record_job_url_history(
                        site_url,
                        [
                            {
                                "job_url": candidate_url,
                                "job_id": str(candidate.get("job_id") or ""),
                                "title": str(candidate.get("title") or ""),
                                "company": str(candidate.get("company") or company_name or ""),
                                "status": "old_posting",
                                "payload": candidate,
                            }
                        ],
                    )
                    continue
                candidate["source_type"] = "company_career_site"
                candidate["portal"] = "company_career_site"
                candidate["manual_approved"] = False
                candidate["career_site_url"] = site_url
                candidate["career_site_company_name"] = company_name
                candidate["company_site_locality_mode"] = site_locality_mode
                if site_policy_id:
                    candidate["company_site_domain_policy_id"] = site_policy_id
                collected_jobs.append(candidate)
                site_jobs_found += 1
                record_job_url_history(
                    site_url,
                    [
                        {
                            "job_url": candidate_url,
                            "job_id": str(candidate.get("job_id") or ""),
                            "title": str(candidate.get("title") or ""),
                            "company": str(candidate.get("company") or company_name or ""),
                            "status": "accepted",
                            "payload": candidate,
                        }
                    ],
                )
            if callable(yield_callback):
                yield_callback(site_url, site_jobs_found)
            processed_sites += 1
            emit_progress(
                company_name=company_name,
                site_url=site_url,
                message=f"Completed {company_name or site_url} via {ats} API",
                active_locality_mode=site_locality_mode,
                domain_policy_id=site_policy_id,
            )
            continue

        try:
            candidate_collection = _collect_job_candidates_for_site(
                site_url=site_url,
                request_timeout_seconds=request_timeout_seconds,
                company_name=company_name,
                request_modes=active_site_request_modes,
                country_code=site_country_code,
                locality_mode=site_locality_mode,
                target_country_codes=site_target_country_codes,
                target_cities=normalized_target_cities,
                max_job_links_per_site=max_job_links_per_site,
                usage_callback=on_site_usage_event,
                should_spend_request_mode=should_spend_request_mode,
                proxy_health_check=ensure_proxy_health,
            )
        except CompanySiteRunCreditBudgetExhausted as exc:
            failures.append(
                {
                    "company_name": company_name,
                    "url": site_url,
                    "error": str(exc),
                    "stage": "fetch_company_site",
                }
            )
            failed_sites += 1
            processed_sites += 1
            emit_progress(
                company_name=company_name,
                site_url=site_url,
                message=str(exc),
                active_locality_mode=site_locality_mode,
                domain_policy_id=site_policy_id,
            )
            raise RuntimeError(str(exc)) from exc
        except ScrapeOpsProxyUnavailableError:
            raise
        except ScrapeOpsOutOfCreditsError as exc:
            failures.append(
                {
                    "company_name": company_name,
                    "url": site_url,
                    "error": str(exc),
                    "stage": "fetch_company_site",
                }
            )
            failed_sites += 1
            processed_sites += 1
            emit_progress(
                company_name=company_name,
                site_url=site_url,
                message="ScrapeOps is out of credits.",
                active_locality_mode=site_locality_mode,
                domain_policy_id=site_policy_id,
            )
            raise RuntimeError(str(exc)) from exc
        except Exception as exc:
            failures.append(
                {
                    "company_name": company_name,
                    "url": site_url,
                    "error": sanitize_scrapeops_text(str(exc)),
                    "stage": "fetch_company_site",
                }
            )
            failed_sites += 1
            processed_sites += 1
            emit_progress(
                company_name=company_name,
                site_url=site_url,
                message=f"Failed to fetch {company_name or site_url}",
                active_locality_mode=site_locality_mode,
                domain_policy_id=site_policy_id,
            )
            continue

        discovered_candidates_total += int(candidate_collection.discovered_count)
        followed_candidates_total += int(candidate_collection.followed_count)
        skipped_candidates_total += int(candidate_collection.skipped_count)
        if candidate_collection.link_cap_hit:
            link_cap_hits += 1
            capped_site = {
                "url": site_url,
                "links_fetched": int(max_job_links_per_site),
                "cap_value": int(max_job_links_per_site),
            }
            capped_sites.append(capped_site)
            active_logger.info(
                "Job link cap reached for %s: retrieved %s links, cap is %s. Additional jobs on this site "
                "were not fetched. Increase company_site_max_job_links_per_site to fetch more.",
                site_url,
                int(max_job_links_per_site),
                int(max_job_links_per_site),
            )
        for skipped in candidate_collection.skipped_reasons:
            failures.append(
                {
                    "company_name": company_name,
                    "url": str(skipped.get("url") or site_url),
                    "error": str(skipped.get("reason") or "candidate_skipped"),
                    "stage": "company_site_candidate_filter",
                }
            )

        candidate_links = list(candidate_collection.candidates)
        if explicit_job_cap > 0 and len(candidate_links) > explicit_job_cap:
            skipped_candidates_total += len(candidate_links) - explicit_job_cap
            failures.extend(
                [
                    {
                        "company_name": company_name,
                        "url": str(item.get("url") or site_url),
                        "error": "explicit_jobs_per_site_cap",
                        "stage": "company_site_candidate_filter",
                    }
                    for item in candidate_links[explicit_job_cap:]
                ]
            )
            candidate_links = candidate_links[:explicit_job_cap]

        candidate_links_before_index_reuse = len(candidate_links)
        cached_postings = cached_job_postings_for_site(
            site_url,
            [str(item.get("url") or "") for item in candidate_links],
        )
        if cached_postings:
            fresh_candidate_links = []
            for item in candidate_links:
                candidate_url = canonicalize_url(str(item.get("url") or "")) or str(item.get("url") or "")
                candidate_label = str(item.get("label") or "")
                cached_job = dict(cached_postings.get(candidate_url) or {})
                if not cached_job:
                    fresh_candidate_links.append(item)
                    continue
                public_index_reused_job_urls += 1
                if not compact_whitespace(str(cached_job.get("title") or "")):
                    cached_job["title"] = candidate_label
                if company_name and not compact_whitespace(str(cached_job.get("company") or "")):
                    cached_job["company"] = company_name
                cached_job["source_type"] = "company_career_site"
                cached_job["portal"] = "company_career_site"
                cached_job["manual_approved"] = False
                cached_job["career_site_url"] = site_url
                cached_job["career_site_company_name"] = company_name
                cached_job["company_site_locality_mode"] = site_locality_mode
                cached_job["public_job_index_reused"] = True
                if site_policy_id:
                    cached_job["company_site_domain_policy_id"] = site_policy_id
                searchable = " ".join(
                    [
                        compact_whitespace(str(cached_job.get("title") or "")),
                        compact_whitespace(str(cached_job.get("company") or "")),
                        compact_whitespace(str(cached_job.get("full_description") or ""))[:1200],
                        candidate_label,
                    ]
                ).lower()
                if normalized_keywords and not any(keyword in searchable for keyword in normalized_keywords):
                    keyword_filtered_jobs += 1
                    record_job_url_history(
                        site_url,
                        [
                            {
                                "job_url": candidate_url,
                                "job_id": str(cached_job.get("job_id") or ""),
                                "title": str(cached_job.get("title") or candidate_label or ""),
                                "company": str(cached_job.get("company") or company_name or ""),
                                "status": "keyword_filtered",
                                "payload": cached_job,
                            }
                        ],
                    )
                    continue
                if not _job_is_within_public_posting_window(cached_job, posted_within_days):
                    record_job_url_history(
                        site_url,
                        [
                            {
                                "job_url": candidate_url,
                                "job_id": str(cached_job.get("job_id") or ""),
                                "title": str(cached_job.get("title") or candidate_label or ""),
                                "company": str(cached_job.get("company") or company_name or ""),
                                "status": "old_posting",
                                "payload": cached_job,
                            }
                        ],
                    )
                    continue
                collected_jobs.append(cached_job)
                site_jobs_found += 1
                record_job_url_history(
                    site_url,
                    [
                        {
                            "job_url": candidate_url,
                            "job_id": str(cached_job.get("job_id") or ""),
                            "title": str(cached_job.get("title") or candidate_label or ""),
                            "company": str(cached_job.get("company") or company_name or ""),
                            "status": "cache_reused",
                            "payload": cached_job,
                        }
                    ],
                )
            candidate_links = fresh_candidate_links

        if not candidate_links:
            if callable(yield_callback):
                yield_callback(site_url, site_jobs_found)
            if candidate_links_before_index_reuse:
                active_logger.info("No uncached job posting links required detail fetches for %s.", site_url)
            else:
                failures.append(
                    {
                        "company_name": company_name,
                        "url": site_url,
                        "error": "No job posting links discovered from the career site entry point.",
                        "stage": "discover_company_jobs",
                    }
                )
                failed_sites += 1
            processed_sites += 1
            emit_progress(
                company_name=company_name,
                site_url=site_url,
                message=(
                    f"Completed {company_name or site_url} from indexed postings"
                    if candidate_links_before_index_reuse
                    else f"No jobs found on {company_name or site_url}"
                ),
                active_locality_mode=site_locality_mode,
                domain_policy_id=site_policy_id,
            )
            continue

        for candidate in candidate_links:
            if callable(should_cancel) and should_cancel():
                raise RuntimeError("Run cancellation requested.")
            candidate_url = str(candidate.get("url") or "")
            candidate_label = str(candidate.get("label") or "")
            try:
                job = _normalize_company_job_with_modes(
                    candidate_url,
                    scrapeops_api_key=scrapeops_api_key,
                    request_timeout_seconds=request_timeout_seconds,
                    job_detail_request_modes=active_job_detail_request_modes,
                    country_code=site_country_code,
                    company_name=company_name,
                    usage_callback=on_site_usage_event,
                    should_spend_request_mode=should_spend_request_mode,
                    proxy_health_check=ensure_proxy_health,
                )
            except CompanySiteRunCreditBudgetExhausted as exc:
                failures.append(
                    {
                        "company_name": company_name,
                        "url": candidate_url,
                        "error": str(exc),
                        "stage": "normalize_company_job",
                    }
                )
                emit_progress(
                    company_name=company_name,
                    site_url=site_url,
                    message=str(exc),
                    active_locality_mode=site_locality_mode,
                    domain_policy_id=site_policy_id,
                )
                raise RuntimeError(str(exc)) from exc
            except ScrapeOpsProxyUnavailableError:
                raise
            except ScrapeOpsOutOfCreditsError as exc:
                failures.append(
                    {
                        "company_name": company_name,
                        "url": candidate_url,
                        "error": str(exc),
                        "stage": "normalize_company_job",
                    }
                )
                emit_progress(
                    company_name=company_name,
                    site_url=site_url,
                    message="ScrapeOps is out of credits.",
                    active_locality_mode=site_locality_mode,
                    domain_policy_id=site_policy_id,
                )
                raise RuntimeError(str(exc)) from exc
            except Exception as exc:
                failures.append(
                    {
                        "company_name": company_name,
                        "url": candidate_url,
                        "error": sanitize_scrapeops_text(str(exc)),
                        "stage": "normalize_company_job",
                    }
                )
                record_job_url_history(
                    site_url,
                    [
                        {
                            "job_url": candidate_url,
                            "title": candidate_label,
                            "company": company_name,
                            "status": "failed",
                        }
                    ],
                )
                continue

            site_jobs_found += 1
            searchable = " ".join(
                [
                    compact_whitespace(str(job.get("title") or "")),
                    compact_whitespace(str(job.get("company") or "")),
                    compact_whitespace(str(job.get("full_description") or ""))[:1200],
                    candidate_label,
                ]
            ).lower()
            if normalized_keywords and not any(keyword in searchable for keyword in normalized_keywords):
                keyword_filtered_jobs += 1
                record_job_url_history(
                    site_url,
                    [
                            {
                                "job_url": candidate_url,
                                "job_id": str(job.get("job_id") or ""),
                                "title": str(job.get("title") or candidate_label or ""),
                                "company": str(job.get("company") or company_name or ""),
                                "status": "keyword_filtered",
                                "payload": job,
                            }
                        ],
                    )
                continue
            if not _job_is_within_public_posting_window(job, posted_within_days):
                record_job_url_history(
                    site_url,
                    [
                            {
                                "job_url": candidate_url,
                                "job_id": str(job.get("job_id") or ""),
                                "title": str(job.get("title") or candidate_label or ""),
                                "company": str(job.get("company") or company_name or ""),
                                "status": "old_posting",
                                "payload": job,
                            }
                        ],
                    )
                continue

            if not compact_whitespace(str(job.get("title") or "")):
                job["title"] = candidate_label
            if company_name and not compact_whitespace(str(job.get("company") or "")):
                job["company"] = company_name
            job["source_type"] = "company_career_site"
            job["portal"] = "company_career_site"
            job["manual_approved"] = False
            job["career_site_url"] = site_url
            job["career_site_company_name"] = company_name
            job["company_site_locality_mode"] = site_locality_mode
            if site_policy_id:
                job["company_site_domain_policy_id"] = site_policy_id
            collected_jobs.append(job)
            record_job_url_history(
                site_url,
                [
                        {
                            "job_url": candidate_url,
                            "job_id": str(job.get("job_id") or ""),
                            "title": str(job.get("title") or candidate_label or ""),
                            "company": str(job.get("company") or company_name or ""),
                            "status": "accepted",
                            "payload": job,
                        }
                    ],
                )
        if callable(yield_callback):
            yield_callback(site_url, site_jobs_found)
        processed_sites += 1
        emit_progress(
            company_name=company_name,
            site_url=site_url,
            message=f"Completed {company_name or site_url}",
            active_locality_mode=site_locality_mode,
            domain_policy_id=site_policy_id,
        )

    deduped_jobs, dropped_duplicates = dedupe_job_records(collected_jobs, logger=active_logger)
    for dropped in dropped_duplicates:
        failures.append(
            {
                "company_name": str(dropped.get("company") or dropped.get("career_site_company_name") or ""),
                "url": str(dropped.get("apply_link") or dropped.get("source_url") or dropped.get("link") or ""),
                "error": str(dropped.get("dedupe_reason") or "duplicate_job"),
                "stage": "dedupe_company_jobs",
            }
        )
    if dropped_duplicates:
        emit_progress(message="Deduplicating discovered jobs.")
    if callable(progress_callback) and capped_sites:
        emit_progress(message="Completed company career site acquisition with capped coverage.")
    return deduped_jobs, failures


__all__ = [
    "ACADEMIC_CAREER_SITE_FILES",
    "CompanySiteScopePlan",
    "DEFAULT_MAX_JOB_LINKS_PER_SITE",
    "DEFAULT_JOB_DETAIL_REQUEST_MODES",
    "DEFAULT_SITE_REQUEST_MODES",
    "LOCALITY_MODE_LOCAL_PREFERRED",
    "LOCALITY_MODE_STRICT_LOCAL_ONLY",
    "estimate_company_site_runner_credit_range",
    "extract_company_job_links_from_html",
    "load_discovered_company_site_entries",
    "PageFetchResult",
    "parse_company_site_entries",
    "plan_company_site_scope",
    "REGULAR_COMPANY_SITE_FILES",
    "scrape_company_career_sites",
]
