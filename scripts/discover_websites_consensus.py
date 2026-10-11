"""Second-pass website discovery using local exact matches and search consensus.

The runner never requests a LinkedIn page. It first reuses exact mappings
already present in the CSV, then searches Bing with independent query variants
for every remaining blank website. A normal web result is accepted only when
the same domain appears in at least two query results. Results are checkpointed
as JSONL so an interrupted full run can resume without repeating completed
slugs.

Only the existing CSV ``website_url`` and final
``companyenrich_free_logo_url`` columns are changed. No CSV columns are added,
and only CompanyEnrich's free logo endpoint is called.
"""

from __future__ import annotations

import argparse
import csv
import html as html_lib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

from discover_websites_from_web_search import (
    BING_SEARCH_URL,
    candidate_evidence,
    domain_from_result_url,
    OUTPUT_COLUMN,
    SEARCH_TIMEOUT_SECONDS,
    SEARCH_USER_AGENT,
    apply_discoveries,
    build_local_domain_maps,
    clean,
    discovery_key_for_row,
    existing_logo_cache,
    find_candidate,
    local_domain_for_row,
    normalize_domain,
    normalize_text,
    score_candidate,
    slug_from_linkedin_url,
    select_consensus_candidate,
    website_domain_from_result_url,
)

import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "Company-Urls" / "Master-Company-Url" / "cleaned" / "Master-Company-Url-canonical_cleaned_linkedin_ids.csv"
DEFAULT_DB = ROOT / "Company-Urls" / "Master-Company-Url" / "cleaned" / "linkedin_company_enrichment_state" / "linkedin_id_resolution" / "linkedin_id_resolution.sqlite3"
DEFAULT_LOG = ROOT / "Company-Urls" / "Master-Company-Url" / "cleaned" / "linkedin_company_enrichment_state" / "website_discovery" / "bing_web_search_consensus_results.jsonl"
DEFAULT_DEEP_LOG = ROOT / "Company-Urls" / "Master-Company-Url" / "cleaned" / "linkedin_company_enrichment_state" / "website_discovery" / "ambiguous_bing_recovery_results.jsonl"
DUCKDUCKGO_SEARCH_URL = "https://html.duckduckgo.com/html/?q="

_session_local = __import__("threading").local()


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if not fieldnames:
            raise ValueError("CSV has no header")
        return fieldnames, list(reader)


def load_log(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
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
            if slug:
                # Last record wins so a later explicit retry can replace a
                # transient error while preserving the append-only audit log.
                records[slug] = record
    return records


def append_log(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def row_slug(row: dict[str, str]) -> str:
    return discovery_key_for_row(row)


def local_discovery_records(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    maps = build_local_domain_maps(rows)
    records: dict[str, dict[str, Any]] = {}
    for row in rows:
        if clean(row.get("website_url")):
            continue
        slug = row_slug(row)
        if not slug or slug in records:
            continue
        domain = local_domain_for_row(row, maps)
        if not domain:
            continue
        records[slug] = {
            "slug": slug,
            "company_name": clean(row.get("company_name")),
            "status": "found",
            "website_url": f"https://{domain}/",
            "domain": domain,
            "method": "local_exact_mapping",
            "query": "local_exact_mapping",
            "search_engine": "local_csv_mapping",
            "agreement_count": 1,
            "requested_at": now_utc(),
        }
    return records


def consensus_queries(company_name: str, slug: str) -> list[str]:
    name = clean(company_name)
    queries = [
        f'"{name}" official website',
        f'"{name}" company website',
    ]
    aliases = re.findall(r"\(([^()]{2,30})\)", name)
    queries.extend(f'"{alias}" official website' for alias in aliases)
    slug_words = clean(slug).replace("-", " ")
    if slug_words and not slug.startswith(("missing-canonical:", "missing-name:")):
        queries.append(f'"{slug_words}" official website')
    return list(dict.fromkeys(query for query in queries if query.strip()))


def deep_query_plan(task: dict[str, Any]) -> list[dict[str, str]]:
    """Build independent Bing query families using the row's context."""
    name = clean(task.get("company_name"))
    slug = clean(task.get("slug"))
    city = clean(task.get("headquarters_city"))
    region = clean(task.get("headquarters_region"))
    country = clean(task.get("headquarters_country"))
    industry = clean(task.get("industry"))
    context_parts = [part for part in (city, region, country) if part]
    context = " ".join(dict.fromkeys(context_parts))
    plan: list[dict[str, str]] = []

    def add(engine: str, family: str, query: str) -> None:
        if not query.strip() or any(item["engine"] == engine and item["query"] == query for item in plan):
            return
        plan.append({"engine": engine, "query_family": family, "query": query})

    add("bing", "name_official", f'"{name}" official website')
    add("bing", "name_company", f'"{name}" company website')
    if context:
        add("bing", "context", f'"{name}" "{context}" official website')
        if industry:
            add("bing", "industry", f'"{name}" "{industry}" "{country}" website')
    elif industry:
        add("bing", "industry", f'"{name}" "{industry}" official website')
    elif slug and not slug.startswith(("missing-canonical:", "missing-name:")):
        slug_words = slug.replace("-", " ")
        add("bing", "slug", f'"{slug_words}" official website')
    if slug and not slug.startswith(("missing-canonical:", "missing-name:")):
        slug_words = slug.replace("-", " ")
        add("bing", "slug", f'"{slug_words}" official website')

    prior_candidates = task.get("prior_candidates") or []
    for candidate in prior_candidates[:1]:
        domain = normalize_domain(candidate.get("domain")) if isinstance(candidate, dict) else ""
        if not domain:
            continue
        add("bing", "targeted_candidate", f'site:{domain} "{name}"')
    return plan


def decode_duckduckgo_target(value: str) -> str:
    raw = html_lib.unescape(clean(value))
    parsed = urlsplit(raw if "//" in raw else f"https://{raw}")
    encoded = parse_qs(parsed.query).get("uddg", [""])[0]
    return unquote(encoded) if encoded else raw


def clean_html_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_lib.unescape(value))).strip()


class _DuckDuckGoResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.result: dict[str, str] | None = None
        self.results: list[dict[str, str]] = []
        self._depth = 0
        self._capture: str | None = None
        self._buffer: list[str] = []

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        value = next((value for key, value in attrs if key == "class"), "") or ""
        return set(value.split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = self._classes(attrs)
        if tag == "div" and "result" in classes and self.result is None:
            self.result = {"href": "", "title": "", "snippet": ""}
            self._depth = 1
            return
        if self.result is None:
            return
        if tag == "div":
            self._depth += 1
        if tag in {"a", "div"} and "result__a" in classes:
            self._capture = "title"
            self._buffer = []
            href = next((value for key, value in attrs if key == "href"), "") or ""
            self.result["href"] = href
        elif tag in {"a", "div"} and "result__snippet" in classes:
            self._capture = "snippet"
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self.result is not None and self._capture:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.result is None:
            return
        if self._capture and tag in {"a", "div"}:
            self.result[self._capture] = clean_html_text(" ".join(self._buffer))
            self._capture = None
            self._buffer = []
        if tag == "div":
            self._depth -= 1
            if self._depth <= 0:
                if self.result.get("href"):
                    self.results.append(self.result)
                self.result = None
                self._depth = 0

    def close(self) -> None:
        super().close()
        if self.result is not None and self.result.get("href"):
            self.results.append(self.result)
            self.result = None


def parse_duckduckgo_candidates(page: str, company_name: str, slug: str) -> list[dict[str, Any]]:
    """Parse DuckDuckGo HTML results into the shared candidate shape."""
    parser = _DuckDuckGoResultParser()
    parser.feed(page)
    parser.close()
    candidates: list[dict[str, Any]] = []
    for position, result in enumerate(parser.results[:8]):
        result_url = decode_duckduckgo_target(result.get("href", ""))
        title = clean_html_text(result.get("title", ""))
        root_domain = domain_from_result_url(result_url)
        domain = website_domain_from_result_url(result_url, company_name, slug)
        if not root_domain or not domain:
            continue
        snippet = clean_html_text(result.get("snippet", ""))
        evidence_text = f"{title} {snippet}".strip()
        candidates.append({
            "position": position,
            "domain": domain,
            "registrable_domain": root_domain,
            "title": title,
            "snippet": snippet,
            "result_url": result_url,
            "score": score_candidate(
                domain=root_domain,
                title=evidence_text,
                company_name=company_name,
                slug=slug,
                position=position,
            ),
            "evidence": candidate_evidence(root_domain, evidence_text, company_name, slug),
        })
    candidates.sort(key=lambda item: (-int(item["evidence"]), -int(item["score"]), int(item["position"])))
    return candidates


def select_deep_candidate(
    query_results: list[dict[str, Any]], company_name: str, slug: str
) -> dict[str, Any]:
    """Accept only a domain corroborated by independent search engines."""
    by_domain: dict[str, list[dict[str, Any]]] = {}
    for query_result in query_results:
        seen_in_query: set[str] = set()
        for candidate in query_result.get("candidates", []):
            domain = normalize_domain(candidate.get("domain"))
            if not domain or domain in seen_in_query:
                continue
            seen_in_query.add(domain)
            by_domain.setdefault(domain, []).append({
                "engine": query_result.get("engine", ""),
                "query_family": query_result.get("query_family", ""),
                "query": query_result.get("query", ""),
                **candidate,
            })
    if not by_domain:
        return {"status": "not_found", "website_url": "", "domain": "", "candidates": []}

    ranked = sorted(
        by_domain.items(),
        key=lambda item: (
            -len({str(observation.get("engine")) for observation in item[1]}),
            -len(item[1]),
            -max(int(observation.get("evidence", 0)) for observation in item[1]),
            -max(int(observation.get("score", 0)) for observation in item[1]),
            min(int(observation.get("position", 99)) for observation in item[1]),
        ),
    )
    winner_domain, observations = ranked[0]
    engine_count = len({str(observation.get("engine")) for observation in observations})
    query_count = len({(str(observation.get("engine")), str(observation.get("query"))) for observation in observations})
    strongest = max(observations, key=lambda item: (int(item.get("evidence", 0)), int(item.get("score", 0))))
    competing = ranked[1][1] if len(ranked) > 1 else []
    competing_engine_count = len({str(observation.get("engine")) for observation in competing})
    competing_query_count = len({(str(observation.get("engine")), str(observation.get("query"))) for observation in competing})
    accepted = (
        engine_count >= 2
        and query_count >= 2
        and int(strongest.get("evidence", 0)) >= 3
        and not (competing_engine_count == engine_count and competing_query_count == query_count)
    )
    candidate_summary = [
        {"domain": domain, "engine_count": len({str(item.get("engine")) for item in items}), "observations": items}
        for domain, items in ranked[:5]
    ]
    if not accepted:
        return {
            "status": "ambiguous",
            "website_url": "",
            "domain": "",
            "agreement_count": query_count,
            "engine_count": engine_count,
            "candidates": candidate_summary,
        }
    return {
        "status": "found",
        "website_url": f"https://{winner_domain}/",
        "domain": winner_domain,
        "agreement_count": query_count,
        "engine_count": engine_count,
        "selected": strongest,
        "candidates": candidate_summary,
    }


def select_bing_recovery_candidate(
    query_results: list[dict[str, Any]], company_name: str, slug: str
) -> dict[str, Any]:
    """Select a domain repeated across distinct Bing query families."""
    by_domain: dict[str, list[dict[str, Any]]] = {}
    for query_result in query_results:
        seen_in_query: set[str] = set()
        for candidate in query_result.get("candidates", []):
            domain = normalize_domain(candidate.get("domain"))
            if not domain or domain in seen_in_query:
                continue
            seen_in_query.add(domain)
            by_domain.setdefault(domain, []).append({
                "query_family": query_result.get("query_family", ""),
                "query": query_result.get("query", ""),
                **candidate,
            })
    if not by_domain:
        return {"status": "not_found", "website_url": "", "domain": "", "candidates": []}

    ranked = sorted(
        by_domain.items(),
        key=lambda item: (
            -len({str(observation.get("query_family")) for observation in item[1]}),
            -len(item[1]),
            -max(int(observation.get("evidence", 0)) for observation in item[1]),
            -max(int(observation.get("score", 0)) for observation in item[1]),
            min(int(observation.get("position", 99)) for observation in item[1]),
        ),
    )
    winner_domain, observations = ranked[0]
    family_count = len({str(observation.get("query_family")) for observation in observations})
    query_count = len({str(observation.get("query")) for observation in observations})
    strongest = max(observations, key=lambda item: (int(item.get("evidence", 0)), int(item.get("score", 0))))
    competing = ranked[1][1] if len(ranked) > 1 else []
    competing_family_count = len({str(observation.get("query_family")) for observation in competing})
    competing_query_count = len({str(observation.get("query")) for observation in competing})
    accepted = (
        family_count >= 2
        and query_count >= 2
        and int(strongest.get("evidence", 0)) >= 3
        and not (competing_family_count == family_count and competing_query_count == query_count)
    )
    candidate_summary = [
        {"domain": domain, "family_count": len({str(item.get("query_family")) for item in items}), "observations": items}
        for domain, items in ranked[:5]
    ]
    if not accepted:
        return {
            "status": "ambiguous",
            "website_url": "",
            "domain": "",
            "agreement_count": query_count,
            "query_family_count": family_count,
            "candidates": candidate_summary,
        }
    return {
        "status": "found",
        "website_url": f"https://{winner_domain}/",
        "domain": winner_domain,
        "agreement_count": query_count,
        "query_family_count": family_count,
        "selected": strongest,
        "candidates": candidate_summary,
    }


def build_ambiguous_tasks(
    rows: list[dict[str, str]], discoveries: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    seen: set[str] = set()
    context_fields = (
        "headquarters_city",
        "headquarters_region",
        "headquarters_country",
        "industry",
    )
    for row in rows:
        if clean(row.get("website_url")):
            continue
        slug = row_slug(row)
        if not slug or slug in seen:
            continue
        prior = discoveries.get(slug) or {}
        if prior.get("status") != "ambiguous":
            continue
        seen.add(slug)
        task = {
            "slug": slug,
            "company_name": clean(row.get("company_name")),
            "prior_candidates": prior.get("candidates", []),
        }
        for field in context_fields:
            value = clean(row.get(field))
            if value:
                task[field] = value
        tasks.append(task)
    return tasks


def is_blocked_search_body(page: str) -> bool:
    text = clean_html_text(page).casefold()
    signals = (
        "unusual traffic",
        "verify you are human",
        "robot check",
        "access denied",
        "captcha",
    )
    return len(text) < 20000 and any(signal in text for signal in signals)


def search_deep_one(task: dict[str, Any], timeout_seconds: float, delay_seconds: float) -> dict[str, Any]:
    """Run the cross-engine recovery plan for one previously ambiguous row."""
    plan = deep_query_plan(task)
    attempts: list[dict[str, Any]] = []
    started = time.perf_counter()
    for item in plan:
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        engine = item["engine"]
        query = item["query"]
        url = f"{BING_SEARCH_URL}{quote(query)}&setlang=en-us&cc=us"
        try:
            response = session().get(url, timeout=timeout_seconds, allow_redirects=True)
        except requests.RequestException as exc:
            attempts.append({
                **item,
                "http_status": 0,
                "blocked": False,
                "error": f"{type(exc).__name__}: {exc}",
                "candidates": [],
            })
            continue
        if response.status_code != 200:
            attempts.append({
                **item,
                "http_status": response.status_code,
                "blocked": response.status_code in {403, 429, 503},
                "candidates": [],
            })
            continue
        body_blocked = is_blocked_search_body(response.text)
        if body_blocked:
            candidates: list[dict[str, Any]] = []
        else:
            candidates = find_candidate(response.text, task["company_name"], task["slug"]).get("candidates", [])
        attempts.append({
            **item,
            "http_status": response.status_code,
            "blocked": body_blocked,
            "candidates": candidates,
        })
        selection = select_bing_recovery_candidate(attempts, task["company_name"], task["slug"])
        if selection.get("status") == "found":
            return {
                "slug": task["slug"],
                "company_name": task["company_name"],
                "queries": plan,
                "query": query,
                "search_engine": "bing_multi_query_recovery",
                "requested_at": now_utc(),
                "http_status": response.status_code,
                "latency_seconds": round(time.perf_counter() - started, 3),
                "attempts": attempts,
                **selection,
            }
    selection = select_bing_recovery_candidate(attempts, task["company_name"], task["slug"])
    blocked = any(attempt.get("blocked") for attempt in attempts) or any(
        attempt.get("http_status") in {403, 429, 503} for attempt in attempts
    )
    status = selection.get("status", "not_found")
    if blocked and status == "not_found":
        status = "blocked"
        selection["status"] = status
    return {
        "slug": task["slug"],
        "company_name": task["company_name"],
        "queries": plan,
        "query": attempts[-1].get("query", plan[0]["query"]) if attempts else plan[0]["query"],
        "search_engine": "bing_multi_query_recovery",
        "requested_at": now_utc(),
        "http_status": attempts[-1].get("http_status", 0) if attempts else 0,
        "latency_seconds": round(time.perf_counter() - started, 3),
        "attempts": attempts,
        **selection,
    }


def session() -> requests.Session:
    value = getattr(_session_local, "session", None)
    if value is None:
        value = requests.Session()
        value.headers.update({
            "User-Agent": SEARCH_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        _session_local.session = value
    return value


def search_consensus_one(task: dict[str, str], timeout_seconds: float, delay_seconds: float) -> dict[str, Any]:
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    queries = consensus_queries(task["company_name"], task["slug"])
    attempts: list[dict[str, Any]] = []
    started = time.perf_counter()
    for query in queries:
        try:
            response = session().get(
                f"{BING_SEARCH_URL}{quote(query)}&setlang=en-us&cc=us",
                timeout=timeout_seconds,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            attempts.append({"query": query, "http_status": 0, "error": f"{type(exc).__name__}: {exc}", "candidates": []})
            continue
        if response.status_code != 200:
            attempts.append({"query": query, "http_status": response.status_code, "error": f"http_{response.status_code}", "candidates": []})
            continue
        result = find_candidate(response.text, task["company_name"], task["slug"])
        attempts.append({
            "query": query,
            "http_status": response.status_code,
            "candidates": result.get("candidates", []),
        })
        # Require two independent query results before early acceptance. The
        # final selection below can still accept one exact top result when all
        # query variants have been exhausted and no competing domain exists.
        selection = select_consensus_candidate(attempts, task["company_name"], task["slug"])
        if selection.get("status") == "found" and int(selection.get("agreement_count", 0)) >= 2:
            return {
                "slug": task["slug"],
                "company_name": task["company_name"],
                "queries": queries,
                "query": query,
                "search_engine": "bing_public_html_consensus",
                "requested_at": now_utc(),
                "http_status": response.status_code,
                "latency_seconds": round(time.perf_counter() - started, 3),
                "attempts": attempts,
                **selection,
            }
    selection = select_consensus_candidate(attempts, task["company_name"], task["slug"])
    status = selection.get("status", "not_found")
    if any(attempt.get("http_status") in {403, 429, 503} for attempt in attempts) and status == "not_found":
        status = "blocked"
        selection["status"] = status
    return {
        "slug": task["slug"],
        "company_name": task["company_name"],
        "queries": queries,
        "query": attempts[-1].get("query", queries[0]) if attempts else queries[0],
        "search_engine": "bing_public_html_consensus",
        "requested_at": now_utc(),
        "http_status": attempts[-1].get("http_status", 0) if attempts else 0,
        "latency_seconds": round(time.perf_counter() - started, 3),
        "attempts": attempts,
        **selection,
    }


def build_tasks(rows: list[dict[str, str]], discoveries: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if clean(row.get("website_url")):
            continue
        slug = row_slug(row)
        if not slug or slug in seen or slug in discoveries:
            continue
        company_name = clean(row.get("company_name"))
        if not company_name:
            continue
        seen.add(slug)
        tasks.append({"slug": slug, "company_name": company_name})
    return tasks


def unresolved_identifier_records(rows: list[dict[str, str]], discoveries: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Record blank rows with no usable slug so every blank is classified."""
    records = dict(discoveries)
    for row in rows:
        if clean(row.get("website_url")) or row_slug(row):
            continue
        synthetic = f"row-{len(records) + 1}"
        records[synthetic] = {
            "slug": synthetic,
            "company_name": clean(row.get("company_name")),
            "status": "unavailable_missing_linkedin_slug",
            "website_url": "",
            "domain": "",
            "query": "",
            "search_engine": "not_searchable",
            "requested_at": now_utc(),
        }
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--deep-ambiguous", action="store_true", help="Recover only rows currently classified as ambiguous.")
    parser.add_argument("--base-log", type=Path, default=DEFAULT_LOG, help="Existing consensus log used to select ambiguous rows.")
    parser.add_argument("--deep-log", type=Path, default=DEFAULT_DEEP_LOG, help="Checkpoint log for the cross-engine recovery pass.")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--timeout", type=float, default=SEARCH_TIMEOUT_SECONDS)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--apply-log-only", action="store_true")
    parser.add_argument("--logo-workers", type=int, default=20)
    return parser.parse_args()


def deep_main(args: argparse.Namespace) -> int:
    csv_path = args.csv.resolve()
    db_path = args.db.resolve()
    base_log_path = args.base_log.resolve()
    deep_log_path = args.deep_log.resolve()
    fieldnames, rows = load_csv(csv_path)
    if OUTPUT_COLUMN not in fieldnames or fieldnames[-1] != OUTPUT_COLUMN:
        raise RuntimeError(f"CSV must retain {OUTPUT_COLUMN!r} as its final column")
    base_discoveries = load_log(base_log_path)
    deep_discoveries = load_log(deep_log_path)
    tasks = build_ambiguous_tasks(rows, base_discoveries)
    tasks = [task for task in tasks if task["slug"] not in deep_discoveries]
    print({
        "csv_rows": len(rows),
        "blank_website_rows": sum(not clean(row.get("website_url")) for row in rows),
        "ambiguous_rows_selected": len(build_ambiguous_tasks(rows, base_discoveries)),
        "existing_deep_recovery_records": len(deep_discoveries),
        "new_bing_recovery_tasks": len(tasks),
        "search_engines": ["bing"],
        "linkedin_requests": 0,
        "scrapeops_requests": 0,
        "paid_companyenrich_requests": 0,
        "write_enabled": args.write,
    }, flush=True)

    for start in range(0, len(tasks), max(1, args.batch_size)):
        batch = tasks[start:start + max(1, args.batch_size)]
        batch_records: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = {
                pool.submit(search_deep_one, task, max(1.0, args.timeout), max(0.0, args.delay)): task
                for task in batch
            }
            for future in as_completed(futures):
                record = future.result()
                batch_records.append(record)
                deep_discoveries[clean(record.get("slug")).casefold()] = record
        batch_records.sort(key=lambda record: clean(record.get("slug")))
        append_log(deep_log_path, batch_records)
        print({
            "deep_batch_completed": min(start + len(batch), len(tasks)),
            "deep_total": len(tasks),
            "found": sum(record.get("status") == "found" for record in batch_records),
            "ambiguous": sum(record.get("status") == "ambiguous" for record in batch_records),
            "not_found": sum(record.get("status") == "not_found" for record in batch_records),
            "blocked": sum(record.get("status") == "blocked" for record in batch_records),
            "errors": sum(record.get("status") == "error" for record in batch_records),
        }, flush=True)

    if not args.write:
        print({"dry_run_records": len(deep_discoveries), "log": str(deep_log_path)}, flush=True)
        return 0

    combined_discoveries = dict(base_discoveries)
    combined_discoveries.update(deep_discoveries)
    existing_logos = existing_logo_cache(rows)
    found_domains = {
        normalize_domain(record.get("website_url"))
        for record in deep_discoveries.values()
        if record.get("status") == "found"
        and normalize_domain(record.get("website_url"))
        and normalize_domain(record.get("website_url")) not in existing_logos
    }
    print({"free_logo_domains_to_check": len(found_domains)}, flush=True)
    logos: dict[str, str] = dict(existing_logos)
    if found_domains:
        from populate_free_companyenrich_logos import fetch_all_free_logos
        logos.update(asyncio_run_logos(fetch_all_free_logos, found_domains, args.logo_workers))
    summary = apply_discoveries(csv_path, db_path, fieldnames, rows, combined_discoveries, logos)
    print({
        **summary,
        "free_logo_urls_found": len(logos),
        "endpoint": "https://api.companyenrich.com/logo/",
        "linkedin_requests": 0,
        "scrapeops_requests": 0,
        "paid_companyenrich_requests": 0,
        "csv_columns_added": 0,
        "csv_last_column": fieldnames[-1],
        "bing_recovery_records": len(deep_discoveries),
        "deep_log": str(deep_log_path),
    }, flush=True)
    return 0


def main() -> int:
    args = parse_args()
    if args.deep_ambiguous:
        return deep_main(args)
    csv_path = args.csv.resolve()
    db_path = args.db.resolve()
    log_path = args.log.resolve()
    fieldnames, rows = load_csv(csv_path)
    if OUTPUT_COLUMN not in fieldnames or fieldnames[-1] != OUTPUT_COLUMN:
        raise RuntimeError(f"CSV must retain {OUTPUT_COLUMN!r} as its final column")
    discoveries = load_log(log_path)
    local_records = local_discovery_records(rows)
    for slug, record in local_records.items():
        # An exact mapping already present in the CSV is stronger evidence
        # than an older ambiguous web-search checkpoint for the same key.
        discoveries[slug] = record
    tasks = [] if args.apply_log_only else build_tasks(rows, discoveries)
    print({
        "csv_rows": len(rows),
        "blank_website_rows": sum(not clean(row.get("website_url")) for row in rows),
        "existing_discovery_records": len(discoveries),
        "local_exact_matches_available": len(local_records),
        "new_consensus_search_tasks": len(tasks),
        "search_engine": "bing_public_html_consensus",
        "linkedin_requests": 0,
        "scrapeops_requests": 0,
        "paid_companyenrich_requests": 0,
        "write_enabled": args.write,
    }, flush=True)

    for start in range(0, len(tasks), max(1, args.batch_size)):
        batch = tasks[start:start + max(1, args.batch_size)]
        batch_records: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = {
                pool.submit(search_consensus_one, task, max(1.0, args.timeout), max(0.0, args.delay)): task
                for task in batch
            }
            for future in as_completed(futures):
                record = future.result()
                batch_records.append(record)
                discoveries[clean(record.get("slug")).casefold()] = record
        batch_records.sort(key=lambda record: clean(record.get("slug")))
        append_log(log_path, batch_records)
        print({
            "search_batch_completed": min(start + len(batch), len(tasks)),
            "search_total": len(tasks),
            "found": sum(record.get("status") == "found" for record in batch_records),
            "ambiguous": sum(record.get("status") == "ambiguous" for record in batch_records),
            "not_found": sum(record.get("status") == "not_found" for record in batch_records),
            "blocked": sum(record.get("status") == "blocked" for record in batch_records),
            "errors": sum(record.get("status") == "error" for record in batch_records),
        }, flush=True)

    if not args.write:
        print({"dry_run_records": len(discoveries), "log": str(log_path)}, flush=True)
        return 0

    discoveries = unresolved_identifier_records(rows, discoveries)
    existing_logos = existing_logo_cache(rows)
    found_domains = {
        normalize_domain(record.get("website_url"))
        for record in discoveries.values()
        if record.get("status") == "found"
        and normalize_domain(record.get("website_url"))
        and normalize_domain(record.get("website_url")) not in existing_logos
    }
    print({"free_logo_domains_to_check": len(found_domains)}, flush=True)
    logos: dict[str, str] = dict(existing_logos)
    if found_domains:
        from populate_free_companyenrich_logos import fetch_all_free_logos
        logos.update(asyncio_run_logos(fetch_all_free_logos, found_domains, args.logo_workers))
    summary = apply_discoveries(csv_path, db_path, fieldnames, rows, discoveries, logos)
    print({
        **summary,
        "free_logo_urls_found": len(logos),
        "endpoint": "https://api.companyenrich.com/logo/",
        "linkedin_requests": 0,
        "scrapeops_requests": 0,
        "paid_companyenrich_requests": 0,
        "csv_columns_added": 0,
        "csv_last_column": fieldnames[-1],
        "classified_discoveries": len(discoveries),
        "log": str(log_path),
    }, flush=True)
    return 0


def asyncio_run_logos(fetcher: Any, domains: set[str], workers: int) -> dict[str, str]:
    import asyncio
    return asyncio.run(fetcher(sorted(domains), workers=max(1, workers), timeout_seconds=5.0))


if __name__ == "__main__":
    raise SystemExit(main())
