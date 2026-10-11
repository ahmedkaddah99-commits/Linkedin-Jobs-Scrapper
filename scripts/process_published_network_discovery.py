"""Find likely hiring contacts for published jobs with one public-web search pass."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from backend.capabilities.networking.discovery import _parse_duckduckgo_html_results
from backend.config import load_project_dotenv
from backend.database.connection import database_session, validate_release_provenance
from scripts.process_catalog_enrichment import NemoClient


def execute(sql: str, args=()) -> list[dict]:
    """Use the same authoritative SQLite path as the serving customer API."""
    path = os.environ["SQLITE_DATABASE_PATH"]
    with database_session(path) as connection:
        rows = connection.execute(sql, args).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def _proxy_url() -> str:
    explicit = (os.getenv("WEBSHARE_PROXY_URL") or os.getenv("WEBSHARE_PROXY") or "").strip()
    if explicit:
        return explicit
    api_key = (os.getenv("WEBSHARE_API_KEY") or "").strip()
    if api_key:
        session = requests.Session()
        session.trust_env = False
        try:
            response = session.get(
                "https://proxy.webshare.io/api/v2/proxy/list/",
                params={"mode": "direct", "page": 1, "page_size": 100},
                headers={"Authorization": f"Token {api_key}"},
                timeout=20,
            )
            response.raise_for_status()
            for proxy in response.json().get("results", []):
                if not proxy.get("valid", True):
                    continue
                host, port = proxy.get("proxy_address"), proxy.get("port")
                username, password = proxy.get("username"), proxy.get("password")
                if host and port and username and password:
                    return f"http://{quote(str(username), safe='')}:{quote(str(password), safe='')}@{host}:{port}"
        except (requests.RequestException, ValueError, TypeError):
            pass
        finally:
            session.close()
    username = (os.getenv("WEBSHARE_PROXY_USERNAME") or "").strip()
    password = (os.getenv("WEBSHARE_PROXY_PASSWORD") or "").strip()
    if not username or not password:
        return ""
    host = (os.getenv("WEBSHARE_PROXY_HOST") or "p.webshare.io").strip()
    port = (os.getenv("WEBSHARE_PROXY_PORT") or "80").strip()
    return f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"


def _linkedin_profile(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    return (parsed.scheme == "https" and parsed.hostname in {"linkedin.com", "www.linkedin.com"}
            and parsed.path.startswith("/in/"))


def discover(row: dict, generate, *, proxy_url: str) -> dict:
    if not proxy_url:
        raise RuntimeError("webshare_unconfigured")
    company = str(row.get("company") or "").strip()
    title = str(row.get("title") or "").strip()
    query = f'site:linkedin.com/in "{company}" "{title}" manager OR recruiter'
    session = requests.Session()
    session.trust_env = False
    response = session.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        proxies={"https": proxy_url, "http": proxy_url},
        headers={"User-Agent": "Mozilla/5.0 (compatible; Runr/1.0)"},
        timeout=35,
    )
    response.raise_for_status()
    hits = [hit for hit in _parse_duckduckgo_html_results(response.text, max_results=8)
            if _linkedin_profile(hit.get("url"))]
    if not hits:
        return {"state": "no_candidates", "candidates": [], "evidence": []}
    prompt = (
        "Identify up to three plausible hiring managers or recruiters for this job from ONLY the search results. "
        "A person may be uncertain. Never invent a name, role, employer, or URL. "
        "Prefer people currently at the employer and in the relevant team. "
        "Return JSON: {\"people\":[{\"name\":\"\",\"role\":\"\",\"linkedin_url\":\"\",\"reason\":\"\"}]}.\n"
        f"Employer: {company}\nJob: {title}\nLocation: {row.get('location') or 'unknown'}\n"
        f"Search results: {json.dumps(hits, ensure_ascii=False)}"
    )
    result = generate(prompt)
    allowed = {str(hit["url"]).split("?")[0].rstrip("/"): hit for hit in hits}
    candidates = []
    seen = set()
    for raw in result.get("people") or []:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("linkedin_url") or "").split("?")[0].rstrip("/")
        name = str(raw.get("name") or "").strip()
        if url not in allowed or url in seen or len(name.split()) < 2:
            continue
        evidence_text = f"{allowed[url]['title']} {allowed[url].get('snippet') or ''}"
        if company.casefold() not in evidence_text.casefold():
            continue
        seen.add(url)
        candidates.append({"name": name, "role": str(raw.get("role") or "").strip(),
                           "linkedin_url": url, "reason": str(raw.get("reason") or "").strip(),
                           "confidence": "likely", "source": "public_web",
                           "evidence_snippet": str(allowed[url].get("snippet") or "")})
        if len(candidates) == 3:
            break
    return {"state": "available" if candidates else "no_candidates", "candidates": candidates,
            "evidence": [{"title": hit["title"], "url": hit["url"], "snippet": hit.get("snippet") or ""} for hit in hits]}


def _pending_rows(job_id: str, limit: int) -> list[dict]:
    filter_sql = " AND j.canonical_job_id=?" if job_id else ""
    retry_before = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    params = (retry_before, job_id, limit) if job_id else (retry_before, limit)
    return execute("""SELECT j.canonical_job_id,j.current_version_id AS version_id,
        v.content_hash,j.title,j.location,c.canonical_name AS company
        FROM acquisition_publication_head h
        JOIN acquisition_publication_jobs pj ON pj.publication_id=h.publication_id
        JOIN canonical_jobs j ON j.canonical_job_id=pj.canonical_job_id
        JOIN canonical_companies c ON c.company_id=j.company_id
        JOIN job_posting_versions v ON v.version_id=j.current_version_id
        LEFT JOIN published_job_network_discovery n ON n.version_id=v.version_id
        WHERE h.head_id=1 AND (n.version_id IS NULL OR (n.state='unavailable' AND n.updated_at<?))""" + filter_sql + " ORDER BY j.canonical_job_id LIMIT ?", params)


def process_one(row: dict, generate, *, proxy_url: str) -> dict:
    try:
        result = discover(row, generate, proxy_url=proxy_url)
        error_code = ""
    except Exception as exc:
        result = {"state": "unavailable", "candidates": [], "evidence": []}
        error_code = type(exc).__name__ if str(exc) != "webshare_unconfigured" else "webshare_unconfigured"
        if isinstance(exc, RuntimeError):
            print(json.dumps({"event": "network_discovery_error", "code": error_code,
                              "reason": str(exc)[:120]}), flush=True)
    updated_at = datetime.now(timezone.utc).isoformat()
    execute("""INSERT OR REPLACE INTO published_job_network_discovery
        (version_id,canonical_job_id,content_hash,state,candidates_json,evidence_json,error_code,updated_at)
        SELECT ?,?,?,?,?,?,?,? WHERE EXISTS (
            SELECT 1 FROM canonical_jobs WHERE canonical_job_id=? AND current_version_id=?)""",
        (row["version_id"], row["canonical_job_id"], row["content_hash"], result["state"],
         json.dumps(result["candidates"], ensure_ascii=False), json.dumps(result["evidence"], ensure_ascii=False),
         error_code, updated_at, row["canonical_job_id"], row["version_id"]))
    return {"job_id": row["canonical_job_id"], "state": result["state"],
            "candidate_count": len(result["candidates"]), "error_code": error_code}


def main() -> int:
    load_project_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", default="", help="Process one published role by canonical job ID")
    parser.add_argument("--max-jobs", type=int, default=10)
    parser.add_argument("--daily-budget", type=float, default=1.0)
    parser.add_argument("--ledger", type=Path, default=Path("/srv/runr/state/network-discovery-usage.sqlite3"))
    args = parser.parse_args()
    if not 1 <= args.max_jobs <= 100 or args.daily_budget <= 0:
        parser.error("invalid job or budget limit")
    for key in ("OPENROUTER_API_KEY", "SQLITE_DATABASE_PATH"):
        if not os.environ.get(key):
            parser.error("missing " + key)
    validate_release_provenance()
    client = NemoClient(args.ledger, args.daily_budget)
    proxy_url = _proxy_url()
    if not proxy_url:
        parser.error("Webshare proxy is not configured")
    rows = _pending_rows(args.job_id, min(args.max_jobs, 1) if args.job_id else args.max_jobs)
    if args.job_id and not rows:
        print(json.dumps({"job_id": args.job_id, "state": "already_processed_or_not_published"}))
    for row in rows:
        print(json.dumps(process_one(row, client, proxy_url=proxy_url)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
