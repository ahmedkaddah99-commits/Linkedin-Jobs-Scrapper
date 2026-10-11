"""Apply missing-only audited values; bounded validation of producer board evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_publication_and_company_reuse import clean, host
from scripts.import_restored_company_profiles import load_env, canonical_url
from backend.database.connection import connect_database
from backend.application.company_logo import assert_public_official_host, validate_official_url
from backend.connectors.company_career_discovery import detect_ats_type, is_probably_career_url

AUDIT = ROOT / "data/audit/publication_reuse_2026-09-28"


def field(profile, key):
    for section in ("fields", "additional_fields"):
        item = profile.get(section, {}).get(key)
        if isinstance(item, dict) and clean(item.get("value")):
            return clean(item["value"])
    return ""


def missing_updates(profile, offers, now):
    updated = json.loads(json.dumps(profile))
    changed = []
    for key in ("domain", "description", "linkedin_company_id"):
        values = offers.get(key, [])
        if len(values) != 1 or field(updated, key):
            continue
        if key == "domain" and not host(values[0]):
            continue
        if key == "linkedin_company_id" and not str(values[0]).isdigit():
            continue
        section = "additional_fields" if key == "description" else "fields"
        updated.setdefault(section, {})[key] = {
            "value": values[0], "state": "known", "status": "known",
            "confidence": "derived_existing_website" if key == "domain" else "restored_authoritative",
            "provenance": {"source": "existing_data_reconciliation", "artifact": "reconciliation_queue.json"},
            "observed_at": now, "verified_at": None,
        }
        changed.append(key)
    return updated, changed


def public_get(url):
    with requests.Session() as session:
        session.trust_env = False
        session.headers["User-Agent"] = "Mozilla/5.0 (compatible; RunrCareerValidation/1.0)"
        for _ in range(5):
            url = validate_official_url(url)
            assert_public_official_host(urlsplit(url).hostname or "")
            with session.get(url, timeout=(5, 10), allow_redirects=False, stream=True) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    url = urljoin(url, response.headers.get("Location", ""))
                    continue
                if response.status_code != 200:
                    return url, response.status_code, ""
                if "html" not in response.headers.get("Content-Type", "").lower():
                    return url, 200, ""
                body = bytearray()
                for chunk in response.iter_content(65536):
                    body.extend(chunk)
                    if len(body) >= 1048576:
                        break
                return url, 200, body.decode(response.encoding or "utf-8", errors="replace")
        return url, 0, ""


def normalized_text(value):
    return re.sub(r"[^\w]+", " ", value.casefold()).strip()


def check_board(company, url):
    result = {"company_id": company["company_id"], "source_url": url, "status": "needs_review"}
    try:
        final, status, html = public_get(url)
        result.update(final_url=final, http_status=status, ats=detect_ats_type(final))
        if status != 200 or not html:
            result["status"] = f"http_{status}" if status != 200 else "non_html_or_empty"
            return result
        if re.search(r"access denied|verify you are human|just a moment|captcha|page not found", html[:50000], re.I):
            result["status"] = "blocked_or_error_page"
            return result
        if not is_probably_career_url(final) or re.search(r"/j/|/jobs?/\d|[?&](gh_jid|jobid)=|/[0-9a-f]{8}-[0-9a-f-]{27,}", final, re.I):
            result["status"] = "not_a_board_url"
            return result
        official_hosts = {host(u) for u in company["selected"] + company["homepages"] + [company["website"]] if u}
        on_official_host = any(host(final) == h or host(final).endswith("." + h) for h in official_hosts)
        plain = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", html, flags=re.S | re.I)
        text = normalized_text(re.sub(r"<[^>]*>", " ", plain))
        name = normalized_text(company["name"])
        name_match = len(name) >= 5 and name in text
        linked_from_official = False
        if not on_official_host and not name_match and company["website"]:
            _, home_status, home_html = public_get(company["website"])
            if home_status == 200:
                links = re.findall(r'href=["\']([^"\']+)', home_html, re.I)
                linked_from_official = any(canonical_url(urljoin(company["website"], link)) in {canonical_url(url), canonical_url(final)} for link in links)
        if not (on_official_host or name_match or linked_from_official):
            result["status"] = "company_identity_not_confirmed"
            return result
        career_content = bool(re.search(r"jobposting|stellenangebote|stellenangebot|karriere|careers|open positions|vacancies|stellen suchen|job openings|jobs suchen|offene stellen", text))
        if not career_content:
            result["status"] = "career_content_not_confirmed"
            return result
        result.update(status="validated_career_page", identity_evidence="official_host" if on_official_host else "exact_company_name" if name_match else "official_homepage_link")
    except Exception as exc:
        result["status"] = type(exc).__name__
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--validate-boards", action="store_true")
    args = parser.parse_args()
    load_env(ROOT / "user_config/.env")
    queue = json.loads((AUDIT / "reconciliation_queue.json").read_text(encoding="utf-8"))
    companies = {c["company_id"]: c for c in json.loads((AUDIT / "report.json").read_text(encoding="utf-8"))["companies"]}
    now = datetime.now(timezone.utc).isoformat()
    conn = connect_database(AUDIT / "remote_probe.sqlite3")
    if conn.backend != "libsql":
        raise RuntimeError("Expected live remote database")
    events = []
    backups = []
    changes = Counter()
    ids = [r["company_id"] for r in queue if r["offers"] and not r["conflicts"]]
    profiles = {}
    primaries = set()
    for start in range(0, len(ids), 100):
        chunk = ids[start:start+100]
        params = ",".join("?" for _ in chunk)
        profiles.update({r[0]: r[1] for r in conn.execute(f"SELECT company_id,profile_json FROM canonical_company_profiles WHERE company_id IN ({params})", tuple(chunk)).fetchall()})
        primaries.update(r[0] for r in conn.execute(f"SELECT company_id FROM canonical_company_urls WHERE url_type='homepage' AND selected_primary=1 AND company_id IN ({params})", tuple(chunk)).fetchall())
    updates, url_inserts = [], []
    for row in queue:
        cid = row["company_id"]
        if row["conflicts"]:
            continue
        before = profiles.get(cid)
        if before:
            profile, keys = missing_updates(json.loads(before), row["offers"], now)
            if keys:
                backups.append({"company_id": cid, "profile_json": before})
                updates.append((json.dumps(profile, ensure_ascii=False, separators=(",", ":")), now, cid, before))
                changes.update(keys)
                events.append({"company_id": cid, "fields": keys})
        values = row["offers"].get("selected_homepage", [])
        if cid not in primaries and len(values) == 1:
            url = canonical_url(values[0])
            if url:
                url_inserts.append(("company_url_" + hashlib.sha256(f"{cid}:homepage:{url}".encode()).hexdigest()[:24], cid, "homepage", url, url, "existing_data_reconciliation", now, now, "not_validated", 1, "company_reuse_v1", now, now))
                changes["selected_homepage"] += 1
    (AUDIT / "profiles_before_reuse.json").write_text(json.dumps(backups, indent=2), encoding="utf-8")
    def apply(db):
        if updates:
            db.executemany("UPDATE canonical_company_profiles SET profile_json=?,updated_at=? WHERE company_id=? AND profile_json=?", updates)
        for row in url_inserts:
            db.execute("""INSERT INTO canonical_company_urls(company_url_id,company_id,url_type,url,canonical_url,source,first_seen_at,last_seen_at,validation_status,selected_primary,rule_version,created_at,updated_at)
                SELECT ?,?,?,?,?,?,?,?,?,?,?,?,? WHERE NOT EXISTS(SELECT 1 FROM canonical_company_urls WHERE company_id=? AND url_type='homepage' AND selected_primary=1)
                ON CONFLICT(company_id,url_type,canonical_url) DO UPDATE SET selected_primary=1,updated_at=excluded.updated_at""", (*row, row[1]))
    if args.apply:
        conn.transaction(apply)
    verified = Counter()
    if args.apply:
        for start in range(0, len(ids), 100):
            chunk = ids[start:start+100]
            params = ",".join("?" for _ in chunk)
            actual = {r[0]: json.loads(r[1]) for r in conn.execute(f"SELECT company_id,profile_json FROM canonical_company_profiles WHERE company_id IN ({params})", tuple(chunk)).fetchall()}
            for event in events:
                if event["company_id"] in actual:
                    for key in event["fields"]:
                        item = actual[event["company_id"]].get("additional_fields" if key == "description" else "fields", {}).get(key, {})
                        if item.get("observed_at") == now:
                            verified[key] += 1
        for row in url_inserts:
            if conn.execute("SELECT 1 FROM canonical_company_urls WHERE company_id=? AND url_type='homepage' AND selected_primary=1 AND canonical_url=?", (row[1], row[4])).fetchone():
                verified["selected_homepage"] += 1
    receipt = {"at": now, "applied": args.apply, "planned": dict(changes), "verified": dict(verified), "board_results": {}}
    (AUDIT / "reuse_apply_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt), flush=True)
    if args.validate_boards:
        targets = [(companies[r["company_id"]], u) for r in queue for u in r["offers"].get("career_board_evidence", [])]
        results = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(check_board, company, url) for company, url in targets]
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                with (AUDIT / "board_validation_results.jsonl").open("a", encoding="utf-8") as out:
                    out.write(json.dumps(result) + "\n")
        valid = [r for r in results if r["status"] == "validated_career_page"]
        def save_boards(db):
            for r in valid:
                url = canonical_url(r["final_url"])
                db.execute("""INSERT INTO canonical_company_urls(company_url_id,company_id,url_type,url,canonical_url,source,first_seen_at,last_seen_at,validation_status,selected_primary,rule_version,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(company_id,url_type,canonical_url) DO NOTHING""",
                    ("company_url_" + hashlib.sha256(f"{r['company_id']}:careers:{url}".encode()).hexdigest()[:24], r["company_id"], "careers", url, url, "producer_board_revalidated:" + r["identity_evidence"], now, now, "http_observed", 0, "company_reuse_board_v1", now, now))
        if args.apply and valid:
            conn.transaction(save_boards)
        stored = sum(bool(conn.execute("SELECT 1 FROM canonical_company_urls WHERE company_id=? AND url_type='careers' AND canonical_url=?", (r["company_id"], canonical_url(r["final_url"]))).fetchone()) for r in valid) if args.apply else 0
        receipt["board_results"] = {"urls_checked": len(results), "companies_checked": len({r['company_id'] for r in results}), "statuses": dict(Counter(r['status'] for r in results)), "validated_companies": len({r['company_id'] for r in valid}), "stored_urls_verified": stored}
        (AUDIT / "reuse_apply_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(json.dumps(receipt, indent=2), flush=True)
    conn.close()


if __name__ == "__main__":
    main()
