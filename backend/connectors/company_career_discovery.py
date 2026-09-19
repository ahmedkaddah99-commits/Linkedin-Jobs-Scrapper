from __future__ import annotations

import os
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html import unescape
from ipaddress import ip_address
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlparse, urlunparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

from backend.integrations.scrapeops import (
    SCRAPEOPS_PROXY_ENDPOINT,
    billed_status_code,
    build_proxy_params,
    build_proxy_usage_record,
    estimate_mode_native_credits,
    parse_proxy_response_envelope,
    require_scrapeops_proxy_health,
)


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
}

COMMON_CAREER_PATHS = (
    "/careers",
    "/career",
    "/jobs",
    "/job",
    "/join-us",
    "/join",
    "/work-with-us",
    "/vacancies",
    "/open-positions",
    "/positions",
    "/recruiting",
    "/karriere",
    "/stellenangebote",
    "/stellen",
    "/jobs-karriere",
    "/de/karriere",
    "/de/jobs",
    "/en/careers",
    "/en/jobs",
)

CAREER_TERMS = (
    "career",
    "careers",
    "job",
    "jobs",
    "join-us",
    "join us",
    "work-with-us",
    "work with us",
    "vacanc",
    "opening",
    "position",
    "recruit",
    "karriere",
    "stellenangebot",
    "stellenangebote",
    "stellen",
    "bewerb",
)

NEGATIVE_TERMS = (
    "privacy",
    "datenschutz",
    "cookie",
    "cookies",
    "terms",
    "impressum",
    "kontakt",
    "contact",
    "press",
    "news",
    "blog",
    "login",
    "signin",
    "sign-in",
    "facebook",
    "instagram",
    "linkedin.com/company",
    "youtube",
)

ATS_HOST_HINTS = {
    "greenhouse": ("greenhouse.io", "boards.greenhouse.io"),
    "lever": ("jobs.lever.co",),
    "workday": ("myworkdayjobs.com", "myworkdaysite.com", "workdayjobs.com"),
    "smartrecruiters": ("smartrecruiters.com",),
    "personio": ("personio.de", "personio.com", "jobs.personio.com"),
    "softgarden": ("softgarden.io", "softgarden.de"),
    "recruitee": ("recruitee.com",),
    "workable": ("workable.com", "jobs.workable.com"),
    "ashby": ("ashbyhq.com",),
    "join": ("join.com",),
    "bamboohr": ("bamboohr.com",),
    "icims": ("icims.com",),
    "taleo": ("taleo.net",),
    "jobvite": ("jobvite.com",),
    "successfactors": ("successfactors.com", "sapsf.com"),
    "talentlink": ("talent-soft.com", "talentlink.com"),
    "interfolio": ("interfolio.com",),
    "academicpositions": ("academicpositions.com",),
}

CAREER_DISCOVERY_POLICY_VERSION = "career-host-policy-v2"
CAREER_DISCOVERY_FOUND_REASON = "career_url_found"
CAREER_DISCOVERY_NO_TARGET_REASON = "no_career_target_found"

MAX_HTML_BYTES = 1_500_000


@dataclass(frozen=True, slots=True)
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str = ""
    text: str = ""
    error: str = ""
    transport: str = "direct"


@dataclass(frozen=True, slots=True)
class CareerUrlCandidate:
    url: str
    source: str
    label: str = ""
    ats_type: str = ""
    status_code: int = 0
    confidence_score: float = 0.0
    evidence: list[str] = field(default_factory=list)
    validated: bool = True
    validation_status: str = "policy_validated"
    host_policy: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)
    freshness: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CareerDiscoveryResult:
    company_domain: str
    homepage_url: str
    company_name: str = ""
    primary_career_url: str = ""
    secondary_candidate_urls: list[str] = field(default_factory=list)
    ats_type: str = ""
    confidence_score: float = 0.0
    discovered_at: str = ""
    crawl_status: str = "not_found"
    candidates: list[CareerUrlCandidate] = field(default_factory=list)
    validation_evidence: list[str] = field(default_factory=list)
    validated_career_url: str = ""
    reason_code: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)
    freshness: dict[str, Any] = field(default_factory=dict)
    host_policy: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        payload["validated_career_url"] = self.validated_career_url or self.primary_career_url
        return payload

    def to_company_site_entry(self) -> str:
        if not self.primary_career_url:
            return ""
        label = self.company_name or self.company_domain
        return f"{label} | {self.primary_career_url}"


Fetcher = Callable[[str], FetchResult]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_url(raw_url: str) -> str:
    value = str(raw_url or "").strip()
    if not value:
        return ""
    if value.startswith("//"):
        value = f"https:{value}"
    if not re.match(r"^[a-z][a-z0-9+.-]*://", value, re.IGNORECASE):
        value = f"https://{value}"

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""

    path = parsed.path or "/"
    cleaned = parsed._replace(fragment="", path=path)
    return urlunparse(cleaned)


def _host_policy_for_url(raw_url: str) -> tuple[bool, str, str]:
    """Return (allowed, policy, reason) without resolving or contacting a host."""

    normalized = normalize_url(raw_url)
    if not normalized:
        return False, "invalid_url", "invalid_url"
    parsed = urlparse(normalized)
    if parsed.username or parsed.password:
        return False, "credentialed_url", "credentialed_url"
    host = (parsed.hostname or "").casefold().rstrip(".")
    if not host:
        return False, "missing_host", "missing_host"
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal")):
        return False, "private_host", "private_host"
    try:
        address = ip_address(host)
    except ValueError:
        address = None
    if address is not None and (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved):
        return False, "private_host", "private_host"
    return True, "public_host", ""


def _candidate_host_policy(candidate_url: str, homepage_url: str) -> tuple[bool, str, str]:
    allowed, _, reason = _host_policy_for_url(candidate_url)
    if not allowed:
        return False, "blocked", reason
    if same_domain_or_subdomain(candidate_url, homepage_url):
        return True, "same_company_host", ""
    ats_type = detect_ats_type(candidate_url)
    if ats_type:
        return True, f"recognized_ats:{ats_type}", ""
    return False, "unsupported_external_host", "unsupported_external_host"


def canonicalize_url(raw_url: str) -> str:
    normalized = normalize_url(raw_url)
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    netloc = parsed.netloc.lower()
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((parsed.scheme.lower(), netloc, path, "", parsed.query, ""))


def domain_from_url(raw_url: str) -> str:
    parsed = urlparse(normalize_url(raw_url))
    host = (parsed.netloc or "").lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def same_domain_or_subdomain(candidate_url: str, homepage_url: str) -> bool:
    candidate_host = domain_from_url(candidate_url)
    homepage_host = domain_from_url(homepage_url)
    if not candidate_host or not homepage_host:
        return False
    return candidate_host == homepage_host or candidate_host.endswith(f".{homepage_host}")


def detect_ats_type(url: str) -> str:
    host = (urlparse(normalize_url(url)).hostname or "").casefold().rstrip(".")
    if not host:
        return ""
    for ats_type, hints in ATS_HOST_HINTS.items():
        if any(host == hint or host.endswith(f".{hint}") for hint in hints):
            return ats_type
    return ""


def is_probably_career_url(url: str, label: str = "") -> bool:
    haystack = f"{url} {label}".lower()
    if any(term in haystack for term in NEGATIVE_TERMS):
        return False
    if detect_ats_type(url):
        return True
    return any(term in haystack for term in CAREER_TERMS)


def requests_fetcher(timeout_seconds: int = 20) -> Fetcher:
    session = requests.Session()

    def fetch(url: str) -> FetchResult:
        requested_url = normalize_url(url)
        if not requested_url:
            return FetchResult(url, "", 0, error="invalid_url")
        allowed, _, reason = _host_policy_for_url(requested_url)
        if not allowed:
            return FetchResult(requested_url, requested_url, 0, error=reason)
        try:
            response = session.get(
                requested_url,
                headers=DEFAULT_HEADERS,
                timeout=max(3, int(timeout_seconds)),
                allow_redirects=True,
            )
            text = response.text[:MAX_HTML_BYTES] if response.text else ""
            return FetchResult(
                requested_url=requested_url,
                final_url=response.url or requested_url,
                status_code=int(response.status_code),
                content_type=response.headers.get("content-type", ""),
                text=text,
            )
        except Exception as exc:
            return FetchResult(requested_url, requested_url, 0, error=str(exc))

    return fetch


def scrapeops_rendered_fetcher(api_key: str, timeout_seconds: int = 45, usage_callback=None) -> Fetcher:
    require_scrapeops_proxy_health(api_key, usage_callback=usage_callback)
    session = requests.Session()

    def fetch(url: str) -> FetchResult:
        requested_url = normalize_url(url)
        if not requested_url:
            return FetchResult(url, "", 0, error="invalid_url")
        try:
            request_started = time.perf_counter()
            response = session.get(
                SCRAPEOPS_PROXY_ENDPOINT,
                params=build_proxy_params(api_key=api_key, url=requested_url, mode="render_js_residential"),
                headers=DEFAULT_HEADERS,
                timeout=max(10, int(timeout_seconds)),
            )
            envelope = parse_proxy_response_envelope(response)
            billed = billed_status_code(envelope.target_status_code)
            if callable(usage_callback):
                usage_callback(
                    build_proxy_usage_record(
                        source_id=domain_from_url(requested_url),
                        target_url=requested_url,
                        request_mode="render_js_residential",
                        target_status_code=envelope.target_status_code,
                        provider_status_code=envelope.provider_status_code,
                        latency_ms=round((time.perf_counter() - request_started) * 1000),
                        billed_credits_actual=envelope.billed_credits_actual,
                        billed_credits_estimated=estimate_mode_native_credits("render_js_residential") if billed else 0,
                        error_category="" if envelope.target_status_code < 400 else "target_http_error",
                    )
                )
            text = envelope.body[:MAX_HTML_BYTES] if envelope.body else ""
            return FetchResult(
                requested_url=requested_url,
                final_url=requested_url,
                status_code=envelope.target_status_code,
                content_type=str(envelope.payload.get("content_type") or response.headers.get("content-type", "")),
                text=text,
            )
        except Exception as exc:
            return FetchResult(requested_url, requested_url, 0, error=str(exc))

    return fetch


def _score_candidate(
    *,
    url: str,
    label: str,
    source: str,
    status_code: int = 0,
) -> tuple[float, list[str]]:
    lowered_url = url.lower()
    lowered_label = label.lower()
    evidence: list[str] = []
    score = 0.2

    if source == "common_path_guess":
        score += 0.2
        evidence.append("matched_common_career_path")
    if source in {"homepage_link", "shallow_crawl_link"}:
        score += 0.15
        evidence.append(f"found_in_{source}")
    if source in {"sitemap", "robots_sitemap"}:
        score += 0.1
        evidence.append(f"found_in_{source}")

    ats_type = detect_ats_type(url)
    if ats_type:
        score += 0.3
        evidence.append(f"detected_ats:{ats_type}")

    if any(term in lowered_url for term in CAREER_TERMS):
        score += 0.25
        evidence.append("career_term_in_url")
    if any(term in lowered_label for term in CAREER_TERMS):
        score += 0.15
        evidence.append("career_term_in_link_text")
    if status_code and 200 <= status_code < 400:
        score += 0.1
        evidence.append(f"http_status:{status_code}")
    if any(term in f"{lowered_url} {lowered_label}" for term in NEGATIVE_TERMS):
        score -= 0.5
        evidence.append("negative_term_present")

    return round(max(0.0, min(1.0, score)), 4), evidence


def _make_candidate(
    *,
    url: str,
    source: str,
    label: str = "",
    status_code: int = 0,
    homepage_url: str = "",
    provenance: dict[str, Any] | None = None,
) -> CareerUrlCandidate | None:
    canonical_url = canonicalize_url(url)
    if not canonical_url or not is_probably_career_url(canonical_url, label):
        return None
    if homepage_url:
        allowed, host_policy, reason = _candidate_host_policy(canonical_url, homepage_url)
        if not allowed:
            return None
        if canonicalize_url(canonical_url) == canonicalize_url(homepage_url):
            return None
    else:
        allowed, host_policy, reason = _host_policy_for_url(canonical_url)
        if not allowed:
            return None
        reason = ""
    score, evidence = _score_candidate(
        url=canonical_url,
        label=label,
        source=source,
        status_code=status_code,
    )
    if score <= 0:
        return None
    evidence.append(f"host_policy:{host_policy}")
    validation_status = "http_observed" if 200 <= status_code < 400 else "policy_validated"
    if reason:
        evidence.append(f"validation_reason:{reason}")
    return CareerUrlCandidate(
        url=canonical_url,
        source=source,
        label=label,
        ats_type=detect_ats_type(canonical_url),
        status_code=status_code,
        confidence_score=score,
        evidence=evidence,
        validated=True,
        validation_status=validation_status,
        host_policy=host_policy,
        provenance=dict(provenance or {"source": source}),
        freshness={"state": "observed", "observed_at": utc_now_iso()},
    )


def _dedupe_candidates(candidates: Iterable[CareerUrlCandidate]) -> list[CareerUrlCandidate]:
    best_by_url: dict[str, CareerUrlCandidate] = {}
    for candidate in candidates:
        existing = best_by_url.get(candidate.url)
        if existing is None or candidate.confidence_score > existing.confidence_score:
            best_by_url[candidate.url] = candidate
    return sorted(
        best_by_url.values(),
        key=lambda item: (-item.confidence_score, item.url),
    )


def guess_common_career_urls(homepage_url: str, fetch: Fetcher) -> list[CareerUrlCandidate]:
    parsed = urlparse(normalize_url(homepage_url))
    base = urlunparse((parsed.scheme, parsed.netloc, "/", "", "", ""))
    candidates: list[CareerUrlCandidate] = []
    for path in COMMON_CAREER_PATHS:
        candidate_url = urljoin(base, path.lstrip("/"))
        result = fetch(candidate_url)
        if 200 <= result.status_code < 400:
            candidate = _make_candidate(
                url=result.final_url or candidate_url,
                source="common_path_guess",
                label=path,
                status_code=result.status_code,
                homepage_url=homepage_url,
                provenance={"requested_url": candidate_url, "resolved_url": result.final_url or candidate_url},
            )
            if candidate:
                candidates.append(candidate)
                # A known ATS host is a source-specific endpoint. Do not spend
                # the remaining common-path budget probing unrelated paths.
                if candidate.ats_type:
                    break
    return candidates


def extract_career_links_from_html(
    *,
    page_url: str,
    html: str,
    homepage_url: str,
    source: str,
) -> list[CareerUrlCandidate]:
    soup = BeautifulSoup(html or "", "html.parser")
    candidates: list[CareerUrlCandidate] = []

    for anchor in soup.select("a[href]"):
        raw_href = unescape(str(anchor.get("href") or "")).strip()
        if not raw_href or raw_href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute_url = urljoin(page_url, raw_href)
        label = " ".join(anchor.get_text(" ", strip=True).split())
        ats_type = detect_ats_type(absolute_url)
        if not ats_type and not same_domain_or_subdomain(absolute_url, homepage_url):
            continue
        candidate = _make_candidate(
            url=absolute_url,
            source=source,
            label=label,
            homepage_url=homepage_url,
            provenance={"page_url": page_url, "link_label": label},
        )
        if candidate:
            candidates.append(candidate)

    return candidates


def extract_career_urls_from_json_ld(
    *,
    page_url: str,
    html: str,
    homepage_url: str,
) -> list[CareerUrlCandidate]:
    """Extract safe career targets from JobPosting JSON-LD without extra requests."""

    soup = BeautifulSoup(str(html or "")[:MAX_HTML_BYTES], "html.parser")
    candidates: list[CareerUrlCandidate] = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        try:
            payload = json.loads(script.get_text("", strip=True))
        except (TypeError, ValueError):
            continue
        items: list[Any] = []
        if isinstance(payload, list):
            items.extend(payload)
        elif isinstance(payload, dict):
            items.append(payload)
            graph = payload.get("@graph")
            if isinstance(graph, list):
                items.extend(graph)
        for item in items:
            if not isinstance(item, dict):
                continue
            types = item.get("@type")
            types = types if isinstance(types, list) else [types]
            if not any(str(value or "").casefold() == "jobposting" for value in types):
                continue
            target_url = str(item.get("url") or item.get("@id") or "").strip()
            if not target_url:
                target_url = page_url
            title = " ".join(str(item.get("title") or "JobPosting").split())
            candidate = _make_candidate(
                url=target_url,
                source="json_ld",
                label=f"JobPosting {title}",
                homepage_url=homepage_url,
                provenance={
                    "page_url": page_url,
                    "structured_data_type": "JobPosting",
                    "title": title,
                },
            )
            if candidate:
                candidates.append(candidate)
    return candidates


def _find_sitemap_urls_from_robots(homepage_url: str, fetch: Fetcher) -> list[str]:
    parsed = urlparse(normalize_url(homepage_url))
    robots_url = urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
    result = fetch(robots_url)
    if not (200 <= result.status_code < 400):
        return []
    sitemap_urls = []
    for line in result.text.splitlines():
        if line.lower().startswith("sitemap:"):
            sitemap_url = line.split(":", 1)[1].strip()
            if sitemap_url:
                sitemap_urls.append(sitemap_url)
    return sitemap_urls


def _extract_urls_from_sitemap_xml(xml_text: str) -> list[str]:
    urls: list[str] = []
    try:
        root = ElementTree.fromstring(xml_text.encode("utf-8"))
    except Exception:
        return urls

    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag == "loc" and element.text:
            urls.append(element.text.strip())
    return urls


def discover_from_sitemaps(homepage_url: str, fetch: Fetcher, max_sitemaps: int = 5) -> list[CareerUrlCandidate]:
    parsed = urlparse(normalize_url(homepage_url))
    sitemap_urls = [
        urlunparse((parsed.scheme, parsed.netloc, "/sitemap.xml", "", "", "")),
        *_find_sitemap_urls_from_robots(homepage_url, fetch),
    ]
    candidates: list[CareerUrlCandidate] = []
    seen_sitemaps: set[str] = set()

    for sitemap_url in sitemap_urls[: max(1, int(max_sitemaps))]:
        normalized_sitemap = canonicalize_url(sitemap_url)
        if not normalized_sitemap or normalized_sitemap in seen_sitemaps:
            continue
        seen_sitemaps.add(normalized_sitemap)
        result = fetch(normalized_sitemap)
        if not (200 <= result.status_code < 400):
            continue
        for url in _extract_urls_from_sitemap_xml(result.text):
            if not is_probably_career_url(url):
                continue
            candidate = _make_candidate(
                url=url,
                source="sitemap",
                status_code=result.status_code,
                homepage_url=homepage_url,
                provenance={"sitemap_url": normalized_sitemap},
            )
            if candidate:
                candidates.append(candidate)
    return candidates


def shallow_same_domain_crawl(
    *,
    homepage_url: str,
    homepage_html: str,
    fetch: Fetcher,
    max_pages: int = 8,
) -> list[CareerUrlCandidate]:
    seed_links = extract_career_links_from_html(
        page_url=homepage_url,
        html=homepage_html,
        homepage_url=homepage_url,
        source="shallow_crawl_link",
    )
    crawl_urls = [candidate.url for candidate in seed_links if same_domain_or_subdomain(candidate.url, homepage_url)][
        : max(0, int(max_pages))
    ]

    candidates = list(seed_links)
    for crawl_url in crawl_urls:
        result = fetch(crawl_url)
        if not (200 <= result.status_code < 400):
            continue
        candidates.extend(
            extract_career_links_from_html(
                page_url=result.final_url or crawl_url,
                html=result.text,
                homepage_url=homepage_url,
                source="shallow_crawl_link",
            )
        )
        candidates.extend(
            extract_career_urls_from_json_ld(
                page_url=result.final_url or crawl_url,
                html=result.text,
                homepage_url=homepage_url,
            )
        )
    return candidates


def _company_name_tokens(company_name: str) -> list[str]:
    cleaned = re.sub(r"\b(gmbh|ag|se|kg|ug|mbh|co)\b", " ", company_name, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^a-zA-Z0-9 ]+", " ", cleaned)
    tokens = [token.lower() for token in cleaned.split() if len(token) >= 4]
    return tokens[:4]


def guess_domains_from_company_name(company_name: str) -> list[str]:
    tokens = _company_name_tokens(company_name)
    if not tokens:
        return []
    full_slug = "".join(tokens)
    hyphen_slug = "-".join(tokens)
    guesses = [
        f"https://www.{full_slug}.de",
        f"https://{full_slug}.de",
        f"https://www.{hyphen_slug}.de",
        f"https://{hyphen_slug}.de",
    ]
    if len(tokens) > 1:
        guesses.extend([f"https://www.{tokens[0]}.de", f"https://{tokens[0]}.de"])
    deduped: list[str] = []
    seen = set()
    for guess in guesses:
        if guess not in seen:
            deduped.append(guess)
            seen.add(guess)
    return deduped


def resolve_homepage_from_company_name(company_name: str, fetch: Fetcher) -> str:
    tokens = _company_name_tokens(company_name)
    if not tokens:
        return ""
    for guessed_url in guess_domains_from_company_name(company_name):
        result = fetch(guessed_url)
        if not (200 <= result.status_code < 400):
            continue
        resolved = result.final_url or guessed_url
        if not _host_policy_for_url(resolved)[0]:
            continue
        page_text = BeautifulSoup(result.text or "", "html.parser").get_text(" ", strip=True).lower()
        if any(token in page_text for token in tokens[:2]):
            return resolved
    return ""


def discover_career_url(
    *,
    homepage_url: str = "",
    company_domain: str = "",
    company_name: str = "",
    fetch: Fetcher | None = None,
    request_timeout_seconds: int = 20,
    shallow_crawl_pages: int = 8,
    use_rendered_fallback: bool = False,
    allow_domain_guessing: bool = False,
    prefer_homepage_candidates: bool = False,
    usage_callback=None,
) -> CareerDiscoveryResult:
    direct_fetch = fetch or requests_fetcher(request_timeout_seconds)
    raw_homepage = homepage_url or company_domain
    homepage = normalize_url(raw_homepage)
    if not homepage and allow_domain_guessing and company_name:
        homepage = resolve_homepage_from_company_name(company_name, direct_fetch)

    discovered_at = utc_now_iso()
    if not homepage:
        return CareerDiscoveryResult(
            company_domain=company_domain,
            homepage_url="",
            company_name=company_name,
            discovered_at=discovered_at,
            crawl_status="missing_homepage_or_domain",
            reason_code="invalid_homepage_or_domain" if raw_homepage else "missing_homepage_or_domain",
            freshness={"state": "not_observed", "observed_at": discovered_at},
            validation_evidence=["No homepage URL or domain was available."],
        )

    homepage_allowed, homepage_policy, homepage_reason = _host_policy_for_url(homepage)
    if not homepage_allowed:
        return CareerDiscoveryResult(
            company_domain=company_domain or domain_from_url(homepage),
            homepage_url=canonicalize_url(homepage),
            company_name=company_name,
            discovered_at=discovered_at,
            crawl_status="unsafe_homepage",
            reason_code=homepage_reason,
            freshness={"state": "not_observed", "observed_at": discovered_at},
            host_policy={
                "policy_version": CAREER_DISCOVERY_POLICY_VERSION,
                "homepage": homepage_policy,
                "allowed": False,
            },
            validation_evidence=[f"Homepage rejected by host policy: {homepage_reason}"],
        )

    homepage_result = direct_fetch(homepage)
    effective_homepage = canonicalize_url(homepage_result.final_url or homepage) or homepage
    company_domain_value = company_domain or domain_from_url(effective_homepage)

    if homepage_result.error or (homepage_result.status_code and not (200 <= homepage_result.status_code < 400)):
        return CareerDiscoveryResult(
            company_domain=company_domain_value,
            homepage_url=effective_homepage,
            company_name=company_name,
            discovered_at=discovered_at,
            crawl_status="homepage_fetch_failed",
            reason_code="homepage_fetch_failed",
            provenance={
                "requested_url": homepage,
                "resolved_url": effective_homepage,
                "transport": homepage_result.transport,
                "error": homepage_result.error,
            },
            freshness={"state": "observed", "observed_at": discovered_at},
            host_policy={
                "policy_version": CAREER_DISCOVERY_POLICY_VERSION,
                "homepage": homepage_policy,
                "allowed": True,
            },
            validation_evidence=[f"Homepage fetch status: {homepage_result.status_code}"],
        )

    all_candidates: list[CareerUrlCandidate] = []
    homepage_candidates = extract_career_links_from_html(
        page_url=effective_homepage,
        html=homepage_result.text,
        homepage_url=effective_homepage,
        source="homepage_link",
    )
    all_candidates.extend(homepage_candidates)
    all_candidates.extend(
        extract_career_urls_from_json_ld(
            page_url=effective_homepage,
            html=homepage_result.text,
            homepage_url=effective_homepage,
        )
    )

    # Prefer an ATS link already present in the homepage. It is an
    # authoritative source-specific endpoint, so common-path and sitemap
    # probing would only add request cost before the producer verifies it.
    has_authoritative_ats = any(candidate.ats_type for candidate in all_candidates)
    has_homepage_target = prefer_homepage_candidates and any(
        candidate.confidence_score >= 0.55 for candidate in homepage_candidates
    )
    if not has_authoritative_ats and not has_homepage_target:
        all_candidates.extend(guess_common_career_urls(effective_homepage, direct_fetch))
        has_authoritative_ats = any(candidate.ats_type for candidate in all_candidates)
    if not has_authoritative_ats and not has_homepage_target:
        all_candidates.extend(discover_from_sitemaps(effective_homepage, direct_fetch))

    if not all_candidates and shallow_crawl_pages > 0:
        all_candidates.extend(
            shallow_same_domain_crawl(
                homepage_url=effective_homepage,
                homepage_html=homepage_result.text,
                fetch=direct_fetch,
                max_pages=shallow_crawl_pages,
            )
        )

    if not all_candidates and use_rendered_fallback:
        api_key = os.getenv("SCRAPEOPS_API_KEY", "")
        if api_key:
            rendered_fetch = scrapeops_rendered_fetcher(
                api_key,
                request_timeout_seconds,
                usage_callback=usage_callback,
            )
            rendered_homepage = rendered_fetch(effective_homepage)
            all_candidates.extend(
                extract_career_links_from_html(
                    page_url=effective_homepage,
                    html=rendered_homepage.text,
                    homepage_url=effective_homepage,
                    source="rendered_homepage_link",
                )
            )
            all_candidates.extend(
                extract_career_urls_from_json_ld(
                    page_url=effective_homepage,
                    html=rendered_homepage.text,
                    homepage_url=effective_homepage,
                )
            )

    candidates = _dedupe_candidates(all_candidates)
    if not candidates:
        return CareerDiscoveryResult(
            company_domain=company_domain_value,
            homepage_url=effective_homepage,
            company_name=company_name,
            discovered_at=discovered_at,
            crawl_status="not_found",
            reason_code=CAREER_DISCOVERY_NO_TARGET_REASON,
            provenance={
                "requested_url": homepage,
                "resolved_url": effective_homepage,
                "transport": homepage_result.transport,
                "discovery_steps": [
                    "homepage_links",
                    "json_ld",
                    "common_path_guesses",
                    "sitemaps",
                    "shallow_crawl",
                ],
            },
            freshness={"state": "observed", "observed_at": discovered_at},
            host_policy={
                "policy_version": CAREER_DISCOVERY_POLICY_VERSION,
                "homepage": homepage_policy,
                "allowed": True,
            },
            validation_evidence=["No career-like URL found after configured discovery steps."],
        )

    primary = candidates[0]
    secondaries = [candidate.url for candidate in candidates[1:6]]
    status = "found" if primary.confidence_score >= 0.55 else "low_confidence"
    evidence = list(primary.evidence)
    evidence.append(f"candidate_source:{primary.source}")
    evidence.append(f"validation_status:{primary.validation_status}")

    return CareerDiscoveryResult(
        company_domain=company_domain_value,
        homepage_url=effective_homepage,
        company_name=company_name,
        primary_career_url=primary.url,
        secondary_candidate_urls=secondaries,
        ats_type=primary.ats_type,
        confidence_score=primary.confidence_score,
        discovered_at=discovered_at,
        crawl_status=status,
        candidates=candidates,
        validation_evidence=evidence,
        validated_career_url=primary.url if primary.validated else "",
        reason_code=CAREER_DISCOVERY_FOUND_REASON,
        provenance={
            "requested_url": homepage,
            "resolved_url": effective_homepage,
            "selected_candidate_source": primary.source,
            "selected_candidate": primary.provenance,
            "transport": homepage_result.transport,
        },
        freshness={
            "state": "fresh",
            "observed_at": discovered_at,
            "age_seconds": 0,
        },
        host_policy={
            "policy_version": CAREER_DISCOVERY_POLICY_VERSION,
            "homepage": homepage_policy,
            "selected": primary.host_policy,
            "allowed": primary.validated,
        },
    )


def discover_many(
    targets: Iterable[dict],
    *,
    request_timeout_seconds: int = 20,
    shallow_crawl_pages: int = 8,
    use_rendered_fallback: bool = False,
    allow_domain_guessing: bool = False,
    sleep_seconds: float = 0.0,
    usage_callback=None,
) -> list[CareerDiscoveryResult]:
    results: list[CareerDiscoveryResult] = []
    for target in targets:
        result = discover_career_url(
            homepage_url=str(target.get("homepage_url") or target.get("url") or ""),
            company_domain=str(target.get("company_domain") or target.get("domain") or ""),
            company_name=str(target.get("company_name") or target.get("name") or ""),
            request_timeout_seconds=request_timeout_seconds,
            shallow_crawl_pages=shallow_crawl_pages,
            use_rendered_fallback=use_rendered_fallback,
            allow_domain_guessing=allow_domain_guessing,
            usage_callback=usage_callback,
        )
        results.append(result)
        if sleep_seconds > 0:
            time.sleep(float(sleep_seconds))
    return results


__all__ = [
    "CareerDiscoveryResult",
    "CareerUrlCandidate",
    "FetchResult",
    "discover_career_url",
    "discover_many",
    "domain_from_url",
    "extract_career_links_from_html",
    "extract_career_urls_from_json_ld",
    "guess_domains_from_company_name",
    "is_probably_career_url",
]
