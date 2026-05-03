from __future__ import annotations

import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html import unescape
from typing import Callable, Iterable
from urllib.parse import urljoin, urlparse, urlunparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup


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

MAX_HTML_BYTES = 1_500_000


@dataclass(frozen=True, slots=True)
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str = ""
    text: str = ""
    error: str = ""


@dataclass(frozen=True, slots=True)
class CareerUrlCandidate:
    url: str
    source: str
    label: str = ""
    ats_type: str = ""
    status_code: int = 0
    confidence_score: float = 0.0
    evidence: list[str] = field(default_factory=list)

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

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["candidates"] = [candidate.to_dict() for candidate in self.candidates]
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
    lowered = (url or "").lower()
    for ats_type, hints in ATS_HOST_HINTS.items():
        if any(hint in lowered for hint in hints):
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


def scrapeops_rendered_fetcher(api_key: str, timeout_seconds: int = 45) -> Fetcher:
    session = requests.Session()

    def fetch(url: str) -> FetchResult:
        requested_url = normalize_url(url)
        if not requested_url:
            return FetchResult(url, "", 0, error="invalid_url")
        try:
            response = session.get(
                "https://proxy.scrapeops.io/v1/",
                params={
                    "api_key": api_key,
                    "url": requested_url,
                    "render_js": "true",
                    "residential": "true",
                },
                headers=DEFAULT_HEADERS,
                timeout=max(10, int(timeout_seconds)),
            )
            text = response.text[:MAX_HTML_BYTES] if response.text else ""
            return FetchResult(
                requested_url=requested_url,
                final_url=requested_url,
                status_code=int(response.status_code),
                content_type=response.headers.get("content-type", ""),
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
) -> CareerUrlCandidate | None:
    canonical_url = canonicalize_url(url)
    if not canonical_url or not is_probably_career_url(canonical_url, label):
        return None
    score, evidence = _score_candidate(
        url=canonical_url,
        label=label,
        source=source,
        status_code=status_code,
    )
    if score <= 0:
        return None
    return CareerUrlCandidate(
        url=canonical_url,
        source=source,
        label=label,
        ats_type=detect_ats_type(canonical_url),
        status_code=status_code,
        confidence_score=score,
        evidence=evidence,
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
            )
            if candidate:
                candidates.append(candidate)
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
        candidate = _make_candidate(url=absolute_url, source=source, label=label)
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

    for sitemap_url in sitemap_urls[:max(1, int(max_sitemaps))]:
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
            candidate = _make_candidate(url=url, source="sitemap", status_code=result.status_code)
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
    crawl_urls = [
        candidate.url
        for candidate in seed_links
        if same_domain_or_subdomain(candidate.url, homepage_url)
    ][: max(0, int(max_pages))]

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
        page_text = BeautifulSoup(result.text or "", "html.parser").get_text(" ", strip=True).lower()
        if any(token in page_text for token in tokens[:2]):
            return result.final_url or guessed_url
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
) -> CareerDiscoveryResult:
    direct_fetch = fetch or requests_fetcher(request_timeout_seconds)
    homepage = normalize_url(homepage_url or company_domain)
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
            validation_evidence=["No homepage URL or domain was available."],
        )

    homepage_result = direct_fetch(homepage)
    effective_homepage = homepage_result.final_url or homepage
    company_domain_value = company_domain or domain_from_url(effective_homepage)

    if homepage_result.status_code and not (200 <= homepage_result.status_code < 400):
        return CareerDiscoveryResult(
            company_domain=company_domain_value,
            homepage_url=effective_homepage,
            company_name=company_name,
            discovered_at=discovered_at,
            crawl_status="homepage_fetch_failed",
            validation_evidence=[f"Homepage fetch status: {homepage_result.status_code}"],
        )

    all_candidates: list[CareerUrlCandidate] = []
    all_candidates.extend(guess_common_career_urls(effective_homepage, direct_fetch))
    all_candidates.extend(
        extract_career_links_from_html(
            page_url=effective_homepage,
            html=homepage_result.text,
            homepage_url=effective_homepage,
            source="homepage_link",
        )
    )
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
            rendered_fetch = scrapeops_rendered_fetcher(api_key, request_timeout_seconds)
            rendered_homepage = rendered_fetch(effective_homepage)
            all_candidates.extend(
                extract_career_links_from_html(
                    page_url=effective_homepage,
                    html=rendered_homepage.text,
                    homepage_url=effective_homepage,
                    source="rendered_homepage_link",
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
            validation_evidence=["No career-like URL found after configured discovery steps."],
        )

    primary = candidates[0]
    secondaries = [candidate.url for candidate in candidates[1:6]]
    status = "found" if primary.confidence_score >= 0.55 else "low_confidence"
    evidence = list(primary.evidence)
    evidence.append(f"candidate_source:{primary.source}")

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
    )


def discover_many(
    targets: Iterable[dict],
    *,
    request_timeout_seconds: int = 20,
    shallow_crawl_pages: int = 8,
    use_rendered_fallback: bool = False,
    allow_domain_guessing: bool = False,
    sleep_seconds: float = 0.0,
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
    "guess_domains_from_company_name",
    "is_probably_career_url",
]
