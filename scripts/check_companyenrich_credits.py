"""Check all configured CompanyEnrich keys, then spend at most one credit each.

The two phases are intentionally separate so the free balance report can be
reviewed before any paid lookup. Every CompanyEnrich call uses a unique
Webshare proxy address. Tokens and proxy credentials never enter receipts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.database.connection import connect_database
from scripts.master_linkedin_jobs_catalog import load_webshare_proxies
from scripts.run_companyenrich_v16_resume import load_candidates, prior_state, request_body

AUDIT = ROOT / "data/audit/companyenrich_live_2026-09-26"
CHECK = AUDIT / "all_credential_balance_check_2026-09-27.json"
LEDGER = AUDIT / "provider_results_credential_one_credit_2026-09-27.jsonl"
SPEND = AUDIT / "all_credential_one_credit_2026-09-27.json"
ME_URL = "https://api.companyenrich.com/me"
ENRICH_URL = "https://api.companyenrich.com/companies/enrich"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def configured() -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    occurrences: dict[str, int] = {}
    for line in (ROOT / "user_config/.env").read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        name, raw = line.split("=", 1)
        name = name.strip()
        if name != "Company_Enrich_API_KEY" and not (name.startswith("Company_Enrich_API_URL_v") and name.removeprefix("Company_Enrich_API_URL_v").isdigit()):
            continue
        token = raw.strip().strip('"').strip("'").strip()
        if not token:
            continue
        occurrences[name] = occurrences.get(name, 0) + 1
        label = name if occurrences[name] == 1 else f"{name}#{occurrences[name]}"
        entries.append((label, token))
    return entries


def proxy_pool() -> list[Any]:
    # load_webshare_proxies reads the configured API key from environment.
    for line in (ROOT / "user_config/.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            if key.strip().startswith("WEBSHARE_"):
                os.environ[key.strip()] = value.strip().strip('"').strip("'")
    proxies = list(load_webshare_proxies())
    unique = []
    seen = set()
    for proxy in proxies:
        if proxy.identifier not in seen:
            seen.add(proxy.identifier)
            unique.append(proxy)
    return unique


def session_for(proxy: Any) -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.proxies.update({"http": proxy.url, "https": proxy.url})
    return session


def safe_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_event(payload: dict[str, Any]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()


def checked_tokens() -> tuple[list[tuple[str, str]], dict[str, str]]:
    unique = []
    duplicates: dict[str, str] = {}
    by_digest: dict[str, str] = {}
    for label, token in configured():
        digest = hashlib.sha256(token.encode()).hexdigest()
        if digest in by_digest:
            duplicates[label] = by_digest[digest]
        else:
            by_digest[digest] = label
            unique.append((label, token))
    return unique, duplicates


def check() -> int:
    entries, duplicates = checked_tokens()
    proxies = proxy_pool()
    if len(proxies) < len(entries):
        raise SystemExit(f"Need {len(entries)} distinct Webshare IPs for account checks; found {len(proxies)}")
    rows: list[dict[str, Any]] = []
    for index, (label, token) in enumerate(entries):
        with session_for(proxies[index]) as session:
            try:
                response = session.get(ME_URL, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=(10, 25))
                status = response.status_code
                account: dict[str, Any] = response.json() if status == 200 else {}
                if not isinstance(account, dict):
                    account = {}
                credits = account.get("credits") if isinstance(account.get("credits"), dict) else {}
                balance = safe_number(response.headers.get("x-credit-remaining"))
                if balance is None:
                    balance = safe_number(response.headers.get("x-credit-balance"))
                if balance is None:
                    total = safe_number(credits.get("total"))
                    used = safe_number(credits.get("used"))
                    balance = total - used if total is not None and used is not None else None
                row = {"credential": label, "http_status": status, "credits_remaining": balance, "credits_used": safe_number(credits.get("used")), "credits_total": safe_number(credits.get("total")), "usable": status == 200 and balance is not None and balance >= 1, "proxy_ip": proxies[index].identifier.split(":")[0]}
            except requests.RequestException as exc:
                row = {"credential": label, "http_status": None, "credits_remaining": None, "usable": False, "transport_error": type(exc).__name__, "proxy_ip": proxies[index].identifier.split(":")[0]}
        rows.append(row)
        print(json.dumps({key: value for key, value in row.items() if key != "proxy_ip"}, separators=(",", ":")), flush=True)
    report = {"checked_at": utc_now(), "distinct_proxy_ips": len(proxies), "credential_entries": len(configured()), "unique_tokens": len(entries), "duplicate_entries": duplicates, "accounts": rows}
    write_json(CHECK, report)
    print(json.dumps({"check_report": str(CHECK), "usable": sum(row["usable"] for row in rows), "duplicate_entries": duplicates}, separators=(",", ":")), flush=True)
    return 0


def recheck_errors() -> int:
    if not CHECK.exists():
        raise SystemExit("Run --check first")
    report = json.loads(CHECK.read_text(encoding="utf-8"))
    entries = dict(checked_tokens()[0])
    proxies = proxy_pool()
    used_ips = {row.get("proxy_ip") for row in report["accounts"]}
    fresh = [proxy for proxy in proxies if proxy.identifier.split(":")[0] not in used_ips]
    errors = [row for row in report["accounts"] if row.get("transport_error")]
    if len(fresh) < len(errors):
        raise SystemExit("Not enough fresh Webshare IPs to recheck transport errors")
    for row, proxy in zip(errors, fresh):
        with session_for(proxy) as session:
            try:
                response = session.get(ME_URL, headers={"Authorization": f"Bearer {entries[row['credential']]}", "Accept": "application/json"}, timeout=(10, 25))
                account = response.json() if response.status_code == 200 else {}
                if not isinstance(account, dict):
                    account = {}
                credits = account.get("credits") if isinstance(account.get("credits"), dict) else {}
                balance = safe_number(response.headers.get("x-credit-remaining"))
                if balance is None:
                    total = safe_number(credits.get("total"))
                    used = safe_number(credits.get("used"))
                    balance = total - used if total is not None and used is not None else None
                row.update({"http_status": response.status_code, "credits_remaining": balance, "credits_used": safe_number(credits.get("used")), "credits_total": safe_number(credits.get("total")), "usable": response.status_code == 200 and balance is not None and balance >= 1, "proxy_ip": proxy.identifier.split(":")[0]})
                row.pop("transport_error", None)
            except requests.RequestException as exc:
                row.update({"transport_error": type(exc).__name__, "proxy_ip": proxy.identifier.split(":")[0]})
        print(json.dumps({key: value for key, value in row.items() if key != "proxy_ip"}, separators=(",", ":")), flush=True)
    report["rechecked_at"] = utc_now()
    report["additional_check_ips"] = [proxy.identifier.split(":")[0] for proxy in fresh[:len(errors)]]
    write_json(CHECK, report)
    return 0


def spend() -> int:
    if not CHECK.exists():
        raise SystemExit("Run --check first")
    report = json.loads(CHECK.read_text(encoding="utf-8"))
    entries, _duplicates = checked_tokens()
    if [name for name, _token in entries] != [row["credential"] for row in report["accounts"]]:
        raise SystemExit("Credential inventory changed after balance check; run --check again")
    proxies = proxy_pool()
    used_ips = {row.get("proxy_ip") for row in report["accounts"]} | set(report.get("additional_check_ips") or [])
    fresh = [proxy for proxy in proxies if proxy.identifier.split(":")[0] not in used_ips]
    usable = [(name, token) for name, token in entries if next(row for row in report["accounts"] if row["credential"] == name)["usable"]]
    if len(fresh) < len(usable):
        raise SystemExit(f"Need {len(usable)} additional distinct Webshare IPs for paid calls; found {len(fresh)}")
    connection = connect_database(AUDIT / "remote_probe.sqlite3")
    try:
        completed, unresolved, _ordinal = prior_state()
        candidates = load_candidates(connection, completed | unresolved)
        active_ids = {str(row[0]) for row in connection.execute("SELECT DISTINCT company_id FROM canonical_jobs WHERE lifecycle_state='active'").fetchall()}
        candidates.sort(key=lambda item: (item["company_id"] not in active_ids, not bool(item["linkedin_url"] or item["linkedin_id"]), item["company_id"]))
    finally:
        connection.close()
    previous = {}
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                event = json.loads(line)
            except (TypeError, ValueError):
                continue
            if event.get("event") == "attempting":
                previous[event.get("credential")] = "ambiguous"
            elif event.get("event") in {"result", "failed", "ambiguous_timeout"}:
                previous[event.get("credential")] = "done"
    rows = []
    for index, (label, token) in enumerate(usable):
        if previous.get(label):
            rows.append({"credential": label, "outcome": "previously_attempted"})
            continue
        if not candidates:
            break
        item = candidates.pop(0)
        method, body = request_body(item)
        proxy = fresh[index]
        attempt_id = f"one-credit:{label}:{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        append_event({"event": "attempting", "attempt_id": attempt_id, "at": utc_now(), "credential": label, "company_id": item["company_id"], "method": method})
        with session_for(proxy) as session:
            try:
                response = session.post(ENRICH_URL, json=body, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=(10, 35))
            except requests.Timeout:
                row = {"credential": label, "company_id": item["company_id"], "outcome": "ambiguous_timeout", "credit_cost": None}
                append_event({"event": "ambiguous_timeout", "attempt_id": attempt_id, "at": utc_now(), **row})
            except requests.RequestException as exc:
                row = {"credential": label, "company_id": item["company_id"], "outcome": type(exc).__name__, "credit_cost": None}
                append_event({"event": "failed", "attempt_id": attempt_id, "at": utc_now(), **row})
            else:
                cost = safe_number(response.headers.get("x-credit-cost"))
                payload = None
                if response.status_code == 200:
                    try:
                        payload = response.json()
                    except ValueError:
                        pass
                matched = response.status_code == 200 and isinstance(payload, dict)
                row = {"credential": label, "company_id": item["company_id"], "http_status": response.status_code, "outcome": "matched" if matched else "no_match" if response.status_code == 404 else "http_error", "credit_cost": cost, "credit_remaining": safe_number(response.headers.get("x-credit-remaining")), "proxy_ip": proxy.identifier.split(":")[0]}
                append_event({"event": "result" if response.status_code in {200, 404} else "failed", "attempt_id": attempt_id, "at": utc_now(), "credential": label, "company_id": item["company_id"], "matched": matched, "status": response.status_code, "credit_cost": cost, "payload": payload if matched else None})
        rows.append(row)
        write_json(SPEND, {"generated_at": utc_now(), "accounts": rows})
        print(json.dumps({key: value for key, value in row.items() if key != "proxy_ip"}, separators=(",", ":")), flush=True)
    write_json(SPEND, {"generated_at": utc_now(), "accounts": rows})
    return 0


def retry_proxy_failures() -> int:
    if not CHECK.exists() or not SPEND.exists():
        raise SystemExit("Run --check and --spend first")
    check_report = json.loads(CHECK.read_text(encoding="utf-8"))
    spend_report = json.loads(SPEND.read_text(encoding="utf-8"))
    entries = dict(checked_tokens()[0])
    proxies = proxy_pool()
    # The original spend used the first fresh proxy for each usable key.
    account_check_ips = {row.get("proxy_ip") for row in check_report["accounts"]} | set(check_report.get("additional_check_ips") or [])
    originally_fresh = [proxy for proxy in proxies if proxy.identifier.split(":")[0] not in account_check_ips]
    usable_count = sum(bool(row.get("usable")) for row in check_report["accounts"])
    used_ips = account_check_ips | {proxy.identifier.split(":")[0] for proxy in originally_fresh[:usable_count]}
    used_ips |= {row.get("proxy_ip") for row in spend_report["accounts"]}
    fresh = [proxy for proxy in proxies if proxy.identifier.split(":")[0] not in used_ips]
    failures = [row for row in spend_report["accounts"] if row.get("outcome") == "ProxyError"]
    if len(fresh) < len(failures):
        raise SystemExit("Not enough fresh Webshare IPs to retry proxy errors")
    connection = connect_database(AUDIT / "remote_probe.sqlite3")
    try:
        completed, unresolved, _ordinal = prior_state()
        candidates = {item["company_id"]: item for item in load_candidates(connection, completed | unresolved)}
    finally:
        connection.close()
    for row, proxy in zip(failures, fresh):
        label = row["credential"]
        item = candidates.get(row["company_id"])
        if item is None:
            raise SystemExit(f"Candidate {row['company_id']} no longer eligible; cannot safely retry {label}")
        _method, body = request_body(item)
        attempt_id = f"one-credit-retry:{label}:{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        append_event({"event": "attempting", "attempt_id": attempt_id, "at": utc_now(), "credential": label, "company_id": item["company_id"], "method": "property"})
        with session_for(proxy) as session:
            try:
                response = session.post(ENRICH_URL, json=body, headers={"Authorization": f"Bearer {entries[label]}", "Accept": "application/json"}, timeout=(10, 35))
            except requests.Timeout:
                row.update({"outcome": "ambiguous_timeout", "credit_cost": None, "proxy_ip": proxy.identifier.split(":")[0]})
                append_event({"event": "ambiguous_timeout", "attempt_id": attempt_id, "at": utc_now(), "credential": label, "company_id": item["company_id"]})
            except requests.RequestException as exc:
                row.update({"outcome": type(exc).__name__, "credit_cost": None, "proxy_ip": proxy.identifier.split(":")[0]})
                append_event({"event": "failed", "attempt_id": attempt_id, "at": utc_now(), "credential": label, "company_id": item["company_id"], "error": type(exc).__name__})
            else:
                payload = None
                if response.status_code == 200:
                    try:
                        payload = response.json()
                    except ValueError:
                        pass
                matched = response.status_code == 200 and isinstance(payload, dict)
                cost = safe_number(response.headers.get("x-credit-cost"))
                row.update({"http_status": response.status_code, "outcome": "matched" if matched else "no_match" if response.status_code == 404 else "http_error", "credit_cost": cost, "credit_remaining": safe_number(response.headers.get("x-credit-remaining")), "proxy_ip": proxy.identifier.split(":")[0]})
                append_event({"event": "result" if response.status_code in {200, 404} else "failed", "attempt_id": attempt_id, "at": utc_now(), "credential": label, "company_id": item["company_id"], "matched": matched, "status": response.status_code, "credit_cost": cost, "payload": payload if matched else None})
        write_json(SPEND, {"generated_at": utc_now(), "accounts": spend_report["accounts"]})
        print(json.dumps({key: value for key, value in row.items() if key != "proxy_ip"}, separators=(",", ":")), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--recheck-errors", action="store_true")
    group.add_argument("--spend", action="store_true")
    group.add_argument("--retry-proxy-failures", action="store_true")
    args = parser.parse_args()
    return check() if args.check else recheck_errors() if args.recheck_errors else spend() if args.spend else retry_proxy_failures()


if __name__ == "__main__":
    raise SystemExit(main())
