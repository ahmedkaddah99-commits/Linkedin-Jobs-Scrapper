"""Discover missing company websites with public web search and fill free logo results.

This workflow intentionally does not request any LinkedIn URL.  It reads the
company name, LinkedIn slug, and existing CSV values locally, then uses Bing's
public HTML search results to find a likely official domain.  It calls only
CompanyEnrich's free, domain-based logo endpoint afterwards.

The target CSV schema is preserved: blank ``website_url`` cells are filled in
place, and logo URLs are written to the existing final
``companyenrich_free_logo_url`` column.  No CSV columns are added.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import csv
from collections import defaultdict
import html
import json
import os
import re
import sqlite3
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

import requests

from populate_free_companyenrich_logos import (
    fetch_all_free_logos,
    normalize_domain,
    normalize_linkedin_url,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "Company-Urls" / "Master-Company-Url" / "cleaned" / "Master-Company-Url-canonical_cleaned_linkedin_ids.csv"
DEFAULT_DB = ROOT / "Company-Urls" / "Master-Company-Url" / "cleaned" / "linkedin_company_enrichment_state" / "linkedin_id_resolution" / "linkedin_id_resolution.sqlite3"
DEFAULT_LOG = ROOT / "Company-Urls" / "Master-Company-Url" / "cleaned" / "linkedin_company_enrichment_state" / "website_discovery" / "bing_web_search_results_v4.jsonl"
OUTPUT_COLUMN = "companyenrich_free_logo_url"
CSV_ENCODING = "utf-8-sig"
BING_SEARCH_URL = "https://www.bing.com/search?q="
SEARCH_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
SEARCH_TIMEOUT_SECONDS = 15.0
SEARCH_BLACKLIST = {
    "bing.com",
    "www.bing.com",
    "microsoft.com",
    "www.microsoft.com",
    "linkedin.com",
    "www.linkedin.com",
    "facebook.com",
    "www.facebook.com",
    "instagram.com",
    "www.instagram.com",
    "twitter.com",
    "www.twitter.com",
    "x.com",
    "www.x.com",
    "youtube.com",
    "www.youtube.com",
    "wikipedia.org",
    "www.wikipedia.org",
    "crunchbase.com",
    "www.crunchbase.com",
    "zoominfo.com",
    "www.zoominfo.com",
    "rocketreach.co",
    "www.rocketreach.co",
    "signalhire.com",
    "www.signalhire.com",
    "theorg.com",
    "www.theorg.com",
    "glassdoor.com",
    "www.glassdoor.com",
    "indeed.com",
    "www.indeed.com",
    "yelp.com",
    "www.yelp.com",
    "bloomberg.com",
    "www.bloomberg.com",
    "dnb.com",
    "www.dnb.com",
    "mapquest.com",
    "www.mapquest.com",
}
MULTI_PART_PUBLIC_SUFFIXES = {
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
    "co.in",
    "co.jp",
    "co.nz",
    "co.za",
}
STOPWORDS = {
    "a",
    "an",
    "and",
    "company",
    "co",
    "com",
    "corporation",
    "corp",
    "gmbh",
    "group",
    "inc",
    "incorporated",
    "international",
    "limited",
    "llc",
    "ltd",
    "of",
    "plc",
    "sa",
    "se",
    "the",
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slug_from_linkedin_url(value: Any) -> str:
    raw = clean(value)
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0].casefold() != "company":
        return ""
    return unquote(parts[1]).strip().casefold()


def normalize_text(value: Any) -> str:
    value = clean(value).casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def discovery_key_for_row(row: dict[str, str]) -> str:
    """Return the stable key used to apply a discovery back to a CSV row."""
    linkedin_slug = clean(row.get("linkedin_slug")).casefold() or slug_from_linkedin_url(row.get("linkedin_company_url"))
    if linkedin_slug:
        return linkedin_slug
    canonical_id = clean(row.get("canonical_CompanyID")).casefold()
    if canonical_id:
        return f"missing-canonical:{canonical_id}"
    company_name = normalize_text(row.get("company_name"))
    return f"missing-name:{company_name}" if company_name else ""


def meaningful_tokens(value: Any) -> set[str]:
    return {
        token
        for token in normalize_text(value).split()
        if len(token) >= 2 and token not in STOPWORDS
    }


def build_local_domain_maps(rows: list[dict[str, str]]) -> dict[str, dict[str, set[str]]]:
    """Build exact, reusable domain mappings from rows that already have websites."""
    maps: dict[str, dict[str, set[str]]] = {
        "slug": defaultdict(set),
        "linkedin_company_id": defaultdict(set),
        "company_name": defaultdict(set),
    }
    for row in rows:
        domain = normalize_domain(row.get("website_url"))
        if not domain:
            continue
        slug = clean(row.get("linkedin_slug")).casefold() or slug_from_linkedin_url(row.get("linkedin_company_url"))
        company_id = clean(row.get("linkedin_company_id"))
        company_name = normalize_text(row.get("company_name"))
        if slug:
            maps["slug"][slug].add(domain)
        if company_id and company_id.isdigit():
            maps["linkedin_company_id"][company_id].add(domain)
        if company_name:
            maps["company_name"][company_name].add(domain)
    return maps


def local_domain_for_row(row: dict[str, str], maps: dict[str, dict[str, set[str]]]) -> str | None:
    """Return a domain only when one exact local key maps to exactly one domain."""
    keys = (
        ("slug", clean(row.get("linkedin_slug")).casefold() or slug_from_linkedin_url(row.get("linkedin_company_url"))),
        ("linkedin_company_id", clean(row.get("linkedin_company_id"))),
        ("company_name", normalize_text(row.get("company_name"))),
    )
    for map_name, key in keys:
        if not key:
            continue
        candidates = maps.get(map_name, {}).get(key, set())
        if len(candidates) == 1:
            return next(iter(candidates))
        if len(candidates) > 1:
            return None
    return None


def select_consensus_candidate(
    query_results: list[dict[str, Any]], company_name: str, slug: str
) -> dict[str, Any]:
    """Select a domain supported by independent search queries."""
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for query_index, query_result in enumerate(query_results):
        seen_in_query: set[str] = set()
        for candidate in query_result.get("candidates", []):
            domain = normalize_domain(candidate.get("domain"))
            if not domain or domain in seen_in_query:
                continue
            seen_in_query.add(domain)
            by_domain[domain].append({
                "query_index": query_index,
                "query": query_result.get("query", ""),
                **candidate,
            })
    if not by_domain:
        return {"status": "not_found", "website_url": "", "domain": "", "candidates": []}

    ranked = sorted(
        by_domain.items(),
        key=lambda item: (
            -len(item[1]),
            -max(int(c.get("evidence", 0)) for c in item[1]),
            -max(int(c.get("score", 0)) for c in item[1]),
            min(int(c.get("position", 99)) for c in item[1]),
        ),
    )
    winner_domain, winner_observations = ranked[0]
    agreement_count = len(winner_observations)
    second_count = len(ranked[1][1]) if len(ranked) > 1 else 0
    strongest = max(winner_observations, key=lambda c: (int(c.get("evidence", 0)), int(c.get("score", 0))))
    # Two independent queries agreeing is the normal acceptance path.  A
    # single top result is allowed only when it carries exact-domain/title
    # evidence; otherwise it remains ambiguous for review.
    single_strong = (
        agreement_count == 1
        and second_count == 0
        and int(strongest.get("evidence", 0)) >= 5
        and int(strongest.get("score", 0)) >= 12
        and int(strongest.get("position", 99)) == 0
    )
    if agreement_count < 2 and not single_strong:
        return {
            "status": "ambiguous",
            "website_url": "",
            "domain": "",
            "agreement_count": agreement_count,
            "candidates": [
                {"domain": domain, "agreement_count": len(observations), "observations": observations}
                for domain, observations in ranked[:5]
            ],
        }
    return {
        "status": "found",
        "website_url": f"https://{winner_domain}/",
        "domain": winner_domain,
        "agreement_count": agreement_count,
        "selected": strongest,
        "candidates": [
            {"domain": domain, "agreement_count": len(observations), "observations": observations}
            for domain, observations in ranked[:5]
        ],
    }


def decode_bing_target(value: str) -> str:
    """Decode Bing's /ck/a redirect when possible."""
    value = html.unescape(clean(value))
    try:
        query = parse_qs(urlsplit(value).query)
        encoded = query.get("u", [""])[0]
        if encoded.startswith("a1"):
            payload = encoded[2:]
            payload += "=" * (-len(payload) % 4)
            return base64.urlsafe_b64decode(payload).decode("utf-8", "replace")
    except (ValueError, UnicodeError, base64.binascii.Error):
        pass
    return value


def extract_result_blocks(page: str) -> list[str]:
    return re.findall(r'<li[^>]+class="[^"]*b_algo[^"]*".*?</li>', page, re.S | re.I)


def extract_result_url(block: str) -> str:
    match = re.search(r"<h2.*?<a[^>]+href=[\"']([^\"']+)", block, re.S | re.I)
    if not match:
        return ""
    return decode_bing_target(match.group(1))


def extract_result_title(block: str) -> str:
    match = re.search(r"<h2[^>]*>(.*?)</h2>", block, re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(match.group(1)))).strip() if match else ""


def registrable_domain(host: str) -> str:
    """Collapse search-result subdomains to the public registrable domain."""
    parts = [part for part in clean(host).casefold().rstrip(".").split(".") if part]
    if len(parts) <= 2:
        return ".".join(parts)
    suffix = ".".join(parts[-2:])
    if suffix in MULTI_PART_PUBLIC_SUFFIXES and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def domain_from_result_url(value: str) -> str:
    parsed = urlsplit(value if "://" in value else f"https://{value}")
    host = clean(parsed.hostname).casefold().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    host = registrable_domain(host)
    if not host or "." not in host or host in SEARCH_BLACKLIST:
        return ""
    if any(host == blocked or host.endswith(f".{blocked}") for blocked in SEARCH_BLACKLIST):
        return ""
    return host


def website_domain_from_result_url(value: str, company_name: str, slug: str) -> str:
    """Keep a brand-specific subdomain only when it identifies the company."""
    parsed = urlsplit(value if "://" in value else f"https://{value}")
    host = clean(parsed.hostname).casefold().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    root = registrable_domain(host)
    if not host or not root or host == root:
        return root
    prefix = host[:-(len(root) + 1)] if host.endswith(f".{root}") else ""
    prefix_tokens = set(re.split(r"[^a-z0-9]+", prefix))
    prefix_tokens.discard("")
    company_tokens = meaningful_tokens(company_name)
    slug_tokens = meaningful_tokens(slug.replace("-", " "))
    # Keep e.g. sheraton.marriott.com; collapse login/careers/etc. to the root.
    if prefix_tokens & (company_tokens | slug_tokens):
        return host
    return root


def score_candidate(
    *,
    domain: str,
    title: str,
    company_name: str,
    slug: str,
    position: int,
) -> int:
    host_tokens = set(re.split(r"[^a-z0-9]+", domain.casefold()))
    host_tokens.discard("")
    company_tokens = meaningful_tokens(company_name)
    slug_tokens = meaningful_tokens(slug.replace("-", " "))
    title_tokens = meaningful_tokens(title)
    score = max(0, 5 - position)
    host_slug_overlap = len(host_tokens & slug_tokens)
    host_company_overlap = len(host_tokens & company_tokens)
    title_company_overlap = len(title_tokens & company_tokens)
    score += 4 * host_slug_overlap
    score += 3 * host_company_overlap
    score += min(6, title_company_overlap * 2)
    compact_domain = re.sub(r"[^a-z0-9]", "", domain.casefold())
    compact_slug = re.sub(r"[^a-z0-9]", "", slug.casefold())
    compact_company = re.sub(r"[^a-z0-9]", "", normalize_text(company_name))
    if compact_slug and len(compact_slug) >= 4 and compact_slug in compact_domain:
        score += 5
    if compact_company and len(compact_company) >= 5 and compact_company in compact_domain:
        score += 5
    # Preserve these diagnostics for the acceptance rule and audit log.
    return score


def candidate_evidence(domain: str, title: str, company_name: str, slug: str) -> int:
    host_tokens = set(re.split(r"[^a-z0-9]+", domain.casefold()))
    host_tokens.discard("")
    company_tokens = meaningful_tokens(company_name)
    slug_tokens = meaningful_tokens(slug.replace("-", " "))
    title_tokens = meaningful_tokens(title)
    compact_domain = re.sub(r"[^a-z0-9]", "", domain.casefold())
    compact_company = re.sub(r"[^a-z0-9]", "", normalize_text(company_name))
    compact_slug = re.sub(r"[^a-z0-9]", "", slug.casefold())
    title_phrase_tokens = [
        token for token in normalize_text(company_name).split()
        if token not in {"and", "of", "the"}
    ]
    if compact_company and len(compact_company) >= 5 and compact_company in compact_domain:
        return 5
    if compact_slug and len(compact_slug) >= 4 and compact_slug in compact_domain:
        return 5
    normalized_title_tokens = set(normalize_text(title).split())
    if len(title_phrase_tokens) >= 2 and set(title_phrase_tokens).issubset(normalized_title_tokens):
        return 5
    if len((host_tokens & slug_tokens) | (host_tokens & company_tokens)) >= 2:
        return 4
    if len(title_tokens & company_tokens) >= 2:
        return 3
    return 0


def find_candidate(page: str, company_name: str, slug: str) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for position, block in enumerate(extract_result_blocks(page)[:8]):
        result_url = extract_result_url(block)
        root_domain = domain_from_result_url(result_url)
        domain = website_domain_from_result_url(result_url, company_name, slug)
        if not root_domain or not domain:
            continue
        title = extract_result_title(block)
        candidates.append({
            "position": position,
            "domain": domain,
            "registrable_domain": root_domain,
            "title": title,
            "result_url": result_url,
            "score": score_candidate(
                domain=root_domain,
                title=title,
                company_name=company_name,
                slug=slug,
                position=position,
            ),
            "evidence": candidate_evidence(root_domain, title, company_name, slug),
        })
    if not candidates:
        return {"status": "not_found", "website_url": "", "domain": "", "candidates": []}
    candidates.sort(key=lambda item: (-int(item["evidence"]), -int(item["score"]), int(item["position"])))
    winner = candidates[0]
    # A domain is accepted only with strong evidence.  In particular, one
    # shared generic word such as "bank" or "booz" is not enough.
    if int(winner["score"]) < 10 or int(winner["evidence"]) < 3:
        return {"status": "ambiguous", "website_url": "", "domain": "", "candidates": candidates[:5]}
    return {
        "status": "found",
        "website_url": f"https://{winner['domain']}/",
        "domain": winner["domain"],
        "selected": winner,
        "candidates": candidates[:5],
    }


_thread_local = threading.local()


def search_queries(task: dict[str, str]) -> list[str]:
    company_name = clean(task["company_name"])
    slug = clean(task["slug"])
    queries = [f'"{company_name}" official website']
    # Parenthetical abbreviations are often the real search term (e.g. BCG).
    aliases = re.findall(r"\(([^()]{2,30})\)", company_name)
    queries.extend(f'"{alias}" official website' for alias in aliases)
    # Use the slug only as a fallback query.  Combining it in quotes with the
    # full name caused Bing to return unrelated localized results.
    slug_words = slug.replace("-", " ").strip()
    if slug_words and normalize_text(slug_words) != normalize_text(company_name):
        queries.append(f'"{slug_words}" official website')
    return list(dict.fromkeys(queries))


def search_one(task: dict[str, str], timeout_seconds: float, delay_seconds: float) -> dict[str, Any]:
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": SEARCH_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        _thread_local.session = session
    started = time.perf_counter()
    base = {
        "slug": task["slug"],
        "company_name": task["company_name"],
        "queries": search_queries(task),
        "search_engine": "bing_public_html",
        "requested_at": now_utc(),
    }
    try:
        attempts: list[dict[str, Any]] = []
        for query in base["queries"]:
            response = session.get(
                f"{BING_SEARCH_URL}{quote(query)}&setlang=en-us&cc=us",
                timeout=timeout_seconds,
                allow_redirects=True,
            )
            attempt = {
                "query": query,
                "http_status": response.status_code,
                "result": {},
            }
            if response.status_code == 200:
                attempt["result"] = find_candidate(response.text, task["company_name"], task["slug"])
                attempts.append(attempt)
                if attempt["result"].get("status") == "found":
                    base.update(attempt["result"])
                    base["query"] = query
                    base["http_status"] = response.status_code
                    base["attempts"] = attempts
                    base["latency_seconds"] = round(time.perf_counter() - started, 3)
                    return base
            else:
                attempts.append(attempt)
                if response.status_code in {403, 429, 503}:
                    base.update({
                        "status": "blocked",
                        "error": f"http_{response.status_code}",
                        "query": query,
                        "http_status": response.status_code,
                        "attempts": attempts,
                        "latency_seconds": round(time.perf_counter() - started, 3),
                    })
                    return base
        best = max(
            (attempt["result"] for attempt in attempts if attempt.get("result")),
            key=lambda result: max((int(candidate.get("score", 0)) for candidate in result.get("candidates", [])), default=0),
            default={"status": "not_found", "website_url": "", "domain": "", "candidates": []},
        )
        base.update(best)
        base["query"] = next((attempt["query"] for attempt in attempts if attempt.get("result") == best), base["queries"][0])
        base["http_status"] = next((attempt["http_status"] for attempt in reversed(attempts)), 0)
        base["attempts"] = attempts
        base["latency_seconds"] = round(time.perf_counter() - started, 3)
        return base
    except requests.RequestException as exc:
        base.update({
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "latency_seconds": round(time.perf_counter() - started, 3),
        })
        return base


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding=CSV_ENCODING, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if not fieldnames:
            raise ValueError("CSV has no header")
        return fieldnames, list(reader)


def load_log(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    results: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                print({"ignored_invalid_log_line": line_number}, flush=True)
                continue
            slug = clean(record.get("slug")).casefold()
            if slug and slug not in results:
                results[slug] = record
    return results


def append_log(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def build_tasks(rows: list[dict[str, str]], existing: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if clean(row.get("website_url")):
            continue
        slug = clean(row.get("linkedin_slug")).casefold() or slug_from_linkedin_url(row.get("linkedin_company_url"))
        if not slug or slug in seen or slug in existing:
            continue
        company_name = clean(row.get("company_name"))
        if not company_name:
            continue
        seen.add(slug)
        tasks.append({"slug": slug, "company_name": company_name})
    return tasks


def atomic_write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    temporary_fd, temporary_name = tempfile.mkstemp(prefix=f"{path.stem}.", suffix=".tmp", dir=path.parent)
    os.close(temporary_fd)
    temporary_path = Path(temporary_name)
    try:
        with temporary_path.open("w", encoding=CSV_ENCODING, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\r\n")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def merge_result_json(raw: str, discovery: dict[str, Any], logo_url: str) -> str:
    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {"previous_result_json": payload}
    except json.JSONDecodeError:
        payload = {"previous_result_json": raw}
    payload["web_search_website_discovery"] = {
        "status": clean(discovery.get("status")),
        "website_url": clean(discovery.get("website_url")),
        "domain": clean(discovery.get("domain")),
        "query": clean(discovery.get("query")),
        "search_engine": clean(discovery.get("search_engine")),
        "selected": discovery.get("selected", {}),
        "updated_at": now_utc(),
    }
    if logo_url:
        payload["web_search_website_discovery"]["companyenrich_free_logo_url"] = logo_url
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def update_database(path: Path, rows: list[dict[str, str]], discoveries: dict[str, dict[str, Any]]) -> int:
    updated = 0
    with sqlite3.connect(path, timeout=60) as connection:
        connection.execute("PRAGMA busy_timeout=60000")
        by_key: dict[str, tuple[str, str]] = {}
        for normalized_url, result_json, logo_url in connection.execute(
            "SELECT normalized_url, result_json, companyenrich_free_logo_url FROM url_resolution"
        ):
            key = normalize_linkedin_url(normalized_url)
            if key:
                by_key[key] = (clean(result_json), clean(logo_url))

        updates: list[tuple[str, str, str]] = []
        for row in rows:
            linkedin_key = normalize_linkedin_url(row.get("linkedin_company_url"))
            slug = clean(row.get("linkedin_slug")).casefold() or slug_from_linkedin_url(row.get("linkedin_company_url"))
            if not linkedin_key or linkedin_key not in by_key or slug not in discoveries:
                continue
            previous_json, previous_logo = by_key[linkedin_key]
            current_logo = clean(row.get(OUTPUT_COLUMN)) or previous_logo
            updates.append((
                merge_result_json(previous_json, discoveries[slug], current_logo),
                current_logo,
                linkedin_key,
            ))
        connection.executemany(
            "UPDATE url_resolution SET result_json=?, companyenrich_free_logo_url=? WHERE normalized_url=?",
            updates,
        )
        updated = len(updates)
    return updated


def apply_discoveries(
    csv_path: Path,
    db_path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
    discoveries: dict[str, dict[str, Any]],
    logo_by_domain: dict[str, str],
) -> dict[str, int]:
    if OUTPUT_COLUMN not in fieldnames:
        raise RuntimeError(f"Expected existing final column {OUTPUT_COLUMN!r}")
    if fieldnames[-1] != OUTPUT_COLUMN:
        raise RuntimeError(f"Expected {OUTPUT_COLUMN!r} to remain the last CSV column")
    changed_websites = 0
    changed_logos = 0
    for row in rows:
        slug = discovery_key_for_row(row)
        discovery = discoveries.get(slug)
        if not discovery or discovery.get("status") != "found":
            continue
        website = clean(discovery.get("website_url"))
        if website and not clean(row.get("website_url")):
            row["website_url"] = website
            changed_websites += 1
        domain = normalize_domain(website)
        if domain and not clean(row.get(OUTPUT_COLUMN)) and logo_by_domain.get(domain):
            row[OUTPUT_COLUMN] = logo_by_domain[domain]
            changed_logos += 1

    db_rows = update_database(db_path, rows, discoveries)
    atomic_write_csv(csv_path, fieldnames, rows)
    return {"website_urls_added": changed_websites, "logo_urls_added": changed_logos, "database_rows_updated": db_rows}


def existing_logo_cache(rows: list[dict[str, str]]) -> dict[str, str]:
    """Reuse logo URLs already present for a domain without another request."""
    cache: dict[str, str] = {}
    for row in rows:
        domain = normalize_domain(row.get("website_url"))
        logo_url = clean(row.get(OUTPUT_COLUMN))
        if domain and logo_url:
            cache.setdefault(domain, logo_url)
    return cache


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--limit", type=int, default=0, help="Limit new search tasks; 0 means all remaining tasks.")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=SEARCH_TIMEOUT_SECONDS)
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--write", action="store_true", help="Write discovered websites/logos into CSV and DB.")
    parser.add_argument("--apply-log-only", action="store_true", help="Skip new searches and apply only records already in the checkpoint log.")
    parser.add_argument("--logo-workers", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csv_path = args.csv.resolve()
    db_path = args.db.resolve()
    log_path = args.log.resolve()
    fieldnames, rows = load_csv(csv_path)
    if OUTPUT_COLUMN not in fieldnames or fieldnames[-1] != OUTPUT_COLUMN:
        raise RuntimeError(f"CSV must retain {OUTPUT_COLUMN!r} as its final column")
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    discoveries = load_log(log_path)
    tasks = [] if args.apply_log_only else build_tasks(rows, discoveries)
    if args.limit > 0:
        tasks = tasks[:args.limit]
    print({
        "csv_rows": len(rows),
        "existing_discovery_records": len(discoveries),
        "new_search_tasks": len(tasks),
        "search_engine": "bing_public_html",
        "linkedin_requests": 0,
        "scrapeops_requests": 0,
        "paid_companyenrich_requests": 0,
        "write_enabled": args.write,
    }, flush=True)

    new_records: list[dict[str, Any]] = []
    batch_size = max(1, args.batch_size)
    for start in range(0, len(tasks), batch_size):
        batch = tasks[start:start + batch_size]
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = {
                pool.submit(search_one, task, max(1.0, args.timeout), max(0.0, args.delay)): task
                for task in batch
            }
            batch_records: list[dict[str, Any]] = []
            for future in as_completed(futures):
                record = future.result()
                batch_records.append(record)
                discoveries[clean(record.get("slug")).casefold()] = record
            batch_records.sort(key=lambda item: clean(item.get("slug")))
        append_log(log_path, batch_records)
        new_records.extend(batch_records)
        print({
            "search_batch_completed": min(start + len(batch), len(tasks)),
            "search_total": len(tasks),
            "found": sum(record.get("status") == "found" for record in batch_records),
            "ambiguous": sum(record.get("status") == "ambiguous" for record in batch_records),
            "not_found": sum(record.get("status") == "not_found" for record in batch_records),
            "blocked_or_error": sum(record.get("status") in {"blocked", "error"} for record in batch_records),
        }, flush=True)

    if not args.write:
        print({"dry_run_records": len(new_records), "log": str(log_path)}, flush=True)
        return 0

    existing_logos = existing_logo_cache(rows)
    found_domains = {
        normalize_domain(record.get("website_url"))
        for record in discoveries.values()
        if record.get("status") == "found"
        and normalize_domain(record.get("website_url"))
        and normalize_domain(record.get("website_url")) not in existing_logos
    }
    print({"free_logo_domains_to_check": len(found_domains)}, flush=True)
    logo_by_domain = dict(existing_logos)
    if found_domains:
        logo_by_domain.update(asyncio.run(
            fetch_all_free_logos(
                sorted(found_domains),
                workers=max(1, args.logo_workers),
                timeout_seconds=5.0,
            )
        ))
    summary = apply_discoveries(csv_path, db_path, fieldnames, rows, discoveries, logo_by_domain)
    print({
        **summary,
        "free_logo_urls_found": len(logo_by_domain),
        "endpoint": "https://api.companyenrich.com/logo/",
        "linkedin_requests": 0,
        "scrapeops_requests": 0,
        "paid_companyenrich_requests": 0,
        "csv_columns_added": 0,
        "csv_last_column": fieldnames[-1],
        "log": str(log_path),
    }, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
