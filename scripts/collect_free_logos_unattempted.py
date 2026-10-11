"""Fill missing logos for never-enriched companies using free CompanyEnrich APIs.

Requests are serial and rotate through Webshare's distinct proxy addresses.
Only validated non-placeholder images are cached to R2 and linked in Turso.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.application.company_logo import LogoValidationError, MAX_LOGO_BYTES, cache_logo, validate_logo
from backend.database.connection import connect_database
from backend.storage import create_object_storage
from scripts.check_companyenrich_credits import checked_tokens, proxy_pool, session_for
from scripts.import_restored_company_profiles import load_env
from scripts.populate_free_companyenrich_logos import image_dimensions
from scripts.run_companyenrich_v16_resume import AUDIT

BASE = "https://api.companyenrich.com"
CANDIDATES = AUDIT / "unattempted_company_logo_candidates.jsonl"
LEDGER = AUDIT / "free_logo_unattempted_results.jsonl"
SUMMARY = AUDIT / "free_logo_unattempted_summary.json"
STOPWORDS = {"gmbh", "ag", "co", "kg", "mbh", "inc", "ltd", "llc", "group", "holding", "gesellschaft", "mit", "beschraenkter", "haftung", "und", "the", "company", "university", "stadt", "deutschland"}
LAST_REQUEST_AT = 0.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def identity_tokens(value: str) -> set[str]:
    folded = value.casefold().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return {part for part in re.findall(r"[a-z0-9]+", folded) if len(part) >= 3 and part not in STOPWORDS}


def domain_affinity(name: str, domain: str) -> bool:
    host_label = domain.split(".", 1)[0].casefold().replace("-", "")
    tokens = identity_tokens(name)
    return bool(tokens and any(token in host_label or (len(host_label) >= 5 and host_label in token) for token in tokens))


def exact_name_match(expected: str, actual: str) -> bool:
    expected_tokens = identity_tokens(expected)
    actual_tokens = identity_tokens(actual)
    if not expected_tokens or not actual_tokens:
        return False
    return expected_tokens == actual_tokens or (len(expected_tokens) >= 2 and expected_tokens <= actual_tokens and len(actual_tokens - expected_tokens) <= 1)


def append_event(row: dict) -> None:
    with LEDGER.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()


def read_completed() -> set[str]:
    completed = set()
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                row = json.loads(line)
            except (TypeError, ValueError):
                continue
            if row.get("event") == "result" and row.get("company_id"):
                completed.add(row["company_id"])
    return completed


def fetch(session: requests.Session, url: str, token: str, *, accept: str) -> requests.Response:
    global LAST_REQUEST_AT
    wait = LAST_REQUEST_AT + 0.21 - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    LAST_REQUEST_AT = time.monotonic()
    response = session.get(url, headers={"Authorization": f"Bearer {token}", "Accept": accept}, timeout=(8, 20), stream=True)
    if float(response.headers.get("x-credit-cost") or 0) > 0:
        response.close()
        raise RuntimeError("Unexpected paid credit cost from a free endpoint")
    return response


def fetch_logo(session: requests.Session, domain: str, token: str):
    url = f"{BASE}/logo/{quote(domain, safe='.-')}"
    response = fetch(session, url, token, accept="image/png")
    try:
        if response.status_code != 200:
            return None, f"http_{response.status_code}"
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
        data = bytearray()
        for chunk in response.iter_content(64 * 1024):
            data.extend(chunk)
            if len(data) > MAX_LOGO_BYTES:
                return None, "too_large"
        dimensions = image_dimensions(bytes(data), content_type)
        if dimensions == (128, 128):
            return None, "placeholder_128"
        try:
            return validate_logo(bytes(data), content_type), "ok"
        except LogoValidationError as exc:
            return None, str(exc)
    finally:
        response.close()


def autocomplete(session: requests.Session, name: str, token: str) -> tuple[str, str]:
    response = fetch(session, f"{BASE}/companies/autocomplete?query={quote(name, safe='')}", token, accept="application/json")
    try:
        if response.status_code != 200:
            return "", f"autocomplete_http_{response.status_code}"
        data = response.json()
        if not isinstance(data, list):
            return "", "autocomplete_invalid"
        matches = []
        for item in data:
            if not isinstance(item, dict):
                continue
            domain = str(item.get("domain") or "").strip().casefold()
            if domain and exact_name_match(name, str(item.get("name") or "")):
                matches.append(domain)
        matches = sorted(set(matches))
        return (matches[0], "autocomplete_exact") if len(matches) == 1 else ("", "autocomplete_ambiguous" if matches else "autocomplete_no_exact_match")
    finally:
        response.close()


def persist(connection, storage, company_id: str, domain: str, logo) -> str:
    source_url = f"{BASE}/logo/{quote(domain, safe='.-')}"
    object_key, _ = cache_logo(storage, company_id, logo)
    now = utc_now()
    existing = connection.execute("SELECT profile_json,logo_source_url,logo_object_key,created_at,profile_status FROM canonical_company_profiles WHERE company_id=?", (company_id,)).fetchone()
    if existing is not None and (str(existing[1] or "").strip() or str(existing[2] or "").strip()):
        return "already_filled"
    try:
        profile = json.loads(str(existing[0] or "{}")) if existing else {}
    except (TypeError, ValueError):
        profile = {}
    if not isinstance(profile, dict):
        profile = {}
    fields = profile.get("fields")
    fields = dict(fields) if isinstance(fields, dict) else {}
    fields["logo"] = {"value": source_url, "state": "known", "status": "known", "confidence": "provider_verified", "provenance": {"source": "companyenrich:free_logo", "url": source_url}, "observed_at": now, "verified_at": now}
    profile["fields"] = fields
    profile["schema_version"] = profile.get("schema_version") or "phase_f_v3"
    created_at = str(existing[3] or now) if existing else now
    profile_status = str(existing[4] or "incomplete") if existing else "incomplete"
    connection.execute(
        "INSERT INTO canonical_company_profiles(company_id,profile_json,profile_status,logo_object_key,logo_source_url,logo_content_hash,logo_content_type,logo_verified_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(company_id) DO UPDATE SET profile_json=excluded.profile_json,logo_object_key=excluded.logo_object_key,logo_source_url=excluded.logo_source_url,logo_content_hash=excluded.logo_content_hash,logo_content_type=excluded.logo_content_type,logo_verified_at=excluded.logo_verified_at,updated_at=excluded.updated_at",
        (company_id, json.dumps(profile, ensure_ascii=False, separators=(",", ":")), profile_status, object_key, source_url, logo.content_hash, logo.content_type, now, created_at, now),
    )
    enrichment_id = "companyenrich_free_logo_" + hashlib.sha256(f"{company_id}:{source_url}".encode()).hexdigest()[:32]
    connection.execute(
        "INSERT INTO company_logo_enrichments(logo_enrichment_id,company_id,provider,source_url,object_key,content_hash,content_type,status,terms_metadata_json,provenance_json,observed_at,rule_version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(logo_enrichment_id) DO UPDATE SET object_key=excluded.object_key,content_hash=excluded.content_hash,content_type=excluded.content_type,status=excluded.status,updated_at=excluded.updated_at",
        (enrichment_id, company_id, "companyenrich_free_logo", source_url, object_key, logo.content_hash, logo.content_type, "cached", json.dumps({"credit_cost": 0}), json.dumps({"domain": domain, "source": "companyenrich_free_logo"}), now, "company_logo_v1", now, now),
    )
    connection.commit()
    return "stored"


def main() -> int:
    load_env(ROOT / "user_config/.env")
    token = dict(checked_tokens()[0])["Company_Enrich_API_URL_v17"]
    proxies = proxy_pool()
    candidates = [json.loads(line) for line in CANDIDATES.read_text(encoding="utf-8").splitlines()]
    targets = [row for row in candidates if not (row.get("logo_source_url") or row.get("logo_field") or row.get("logo_object_key"))]
    targets.sort(key=lambda row: (not bool(row["domain"]), row["company_id"]))
    completed = read_completed()
    connection = connect_database(AUDIT / "remote_probe.sqlite3")
    storage = create_object_storage(dict(__import__("os").environ))
    counters = Counter()
    proxy_cursor = 40
    try:
        for index, row in enumerate(targets, start=1):
            cid = row["company_id"]
            if cid in completed:
                continue
            domain = row["domain"]
            status = ""
            logo = None
            used_autocomplete = False
            for attempt in range(3):
                try:
                    if not domain:
                        proxy = proxies[proxy_cursor % len(proxies)]
                        proxy_cursor += 1
                        with session_for(proxy) as session:
                            domain, status = autocomplete(session, row["name"], token)
                        used_autocomplete = True
                    if domain:
                        proxy = proxies[proxy_cursor % len(proxies)]
                        proxy_cursor += 1
                        with session_for(proxy) as session:
                            logo, status = fetch_logo(session, domain, token)
                        if logo is not None and not (domain_affinity(row["name"], domain) or used_autocomplete):
                            logo = None
                            status = "identity_mismatch"
                    break
                except requests.RequestException as exc:
                    status = type(exc).__name__
                    if attempt < 2:
                        continue
                except RuntimeError:
                    raise
            if logo is not None:
                try:
                    status = persist(connection, storage, cid, domain, logo)
                except Exception as exc:
                    status = "persist_" + type(exc).__name__
            counters[status] += 1
            append_event({"event": "result", "company_id": cid, "at": utc_now(), "domain": domain, "status": status, "logo_url": f"{BASE}/logo/{quote(domain, safe='.-')}" if status == "stored" else "", "autocomplete": used_autocomplete})
            if index % 25 == 0 or index == len(targets):
                report = {"at": utc_now(), "target_count": len(targets), "processed_including_previous": len(read_completed()), "results_this_run": dict(counters), "last_company_id": cid, "proxy_pool_size": len(proxies)}
                SUMMARY.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
                print(json.dumps(report, separators=(",", ":")), flush=True)
            time.sleep(0.01)
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
