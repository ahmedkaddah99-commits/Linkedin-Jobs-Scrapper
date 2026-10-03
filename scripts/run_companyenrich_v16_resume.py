"""Run one CompanyEnrich credential serially with durable, proxy-backed checkpoints."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database.connection import connect_database
from scripts.master_linkedin_jobs_catalog import load_webshare_proxies


AUDIT = ROOT / "data" / "audit" / "companyenrich_live_2026-09-26"
ENV_FILE = ROOT / "user_config" / ".env"
API_VERSION = os.environ.get("COMPANY_ENRICH_API_VERSION", "16").strip()
RUN_LABEL = f"v{API_VERSION}"
LEDGER = AUDIT / f"provider_results_{RUN_LABEL}_sequential_proxy.jsonl"
SUMMARY = AUDIT / f"provider_run_summary_{RUN_LABEL}_sequential_proxy.json"
TOKEN_NAME = f"Company_Enrich_API_URL_{RUN_LABEL}"
ENDPOINT = "https://api.companyenrich.com/companies/enrich"
PROXY_INDEX = int(os.environ.get("COMPANY_ENRICH_PROXY_INDEX", "11" if API_VERSION == "16" else "12"))
TARGET_CREDITS = 499.0


def load_env() -> None:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def clean(value: Any) -> str:
    value = str(value or "").strip()
    return "" if value.casefold() in {"", "null", "none", "n/a", "na", "unknown", "-"} else value


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_event(event: dict[str, Any]) -> None:
    AUDIT.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()


def prior_state() -> tuple[set[str], set[str], int]:
    """Return completed IDs, interrupted IDs, and the next ordinal."""
    completed: set[str] = set()
    unresolved: set[str] = set()
    max_ordinal = 0
    paths = sorted(AUDIT.glob("provider_results_*.jsonl")) + [AUDIT / "provider_result_recovered_interruption.jsonl"]
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                item = json.loads(line)
            except (TypeError, ValueError):
                continue
            company_id = clean(item.get("company_id"))
            if not company_id:
                continue
            attempt_id = clean(item.get("attempt_id"))
            match = re.search(rf"{re.escape(RUN_LABEL)}:(?:resume:)?(\d+):", attempt_id)
            if match:
                max_ordinal = max(max_ordinal, int(match.group(1)))
            event = item.get("event")
            if event == "attempting" and attempt_id:
                unresolved.add(company_id)
            elif event in {"result", "ambiguous_timeout"}:
                completed.add(company_id)
                unresolved.discard(company_id)
            elif event == "failed":
                # Transport/server failures are safe to retry on another proxy.
                unresolved.discard(company_id)
    return completed, unresolved, max_ordinal


def load_candidates(connection: Any, excluded: set[str]) -> list[dict[str, str]]:
    sql = """
        SELECT
          c.company_id,
          c.canonical_name,
          COALESCE(
            json_extract(p.profile_json, '$.fields.linkedin_company_url.value'),
            json_extract(p.profile_json, '$.additional_fields.linkedin_company_url.value')
          ) AS linkedin_url,
          COALESCE(
            json_extract(p.profile_json, '$.fields.linkedin_company_id.value'),
            json_extract(p.profile_json, '$.additional_fields.linkedin_company_id.value')
          ) AS linkedin_id,
          COALESCE(
            json_extract(p.profile_json, '$.fields.domain.value'),
            json_extract(p.profile_json, '$.additional_fields.domain.value')
          ) AS domain,
          COALESCE(
            json_extract(p.profile_json, '$.fields.website.value'),
            json_extract(p.profile_json, '$.additional_fields.website.value')
          ) AS website
        FROM canonical_companies c
        LEFT JOIN canonical_company_profiles p ON p.company_id = c.company_id
        WHERE COALESCE(
          json_extract(p.profile_json, '$.fields.companyenrich_id.value'),
          json_extract(p.profile_json, '$.additional_fields.companyenrich_id.value')
        ) IS NULL
        ORDER BY c.company_id
    """
    rows = connection.execute(sql).fetchall()
    candidates: list[dict[str, str]] = []
    for row in rows:
        company_id = clean(row[0])
        if not company_id or company_id in excluded:
            continue
        item = {
            "company_id": company_id,
            "canonical_name": clean(row[1]),
            "linkedin_url": clean(row[2]),
            "linkedin_id": clean(row[3]),
            "domain": clean(row[4]),
            "website": clean(row[5]),
        }
        if item["linkedin_url"] or item["linkedin_id"] or item["canonical_name"]:
            candidates.append(item)
    return candidates


def request_body(item: dict[str, str]) -> tuple[str, dict[str, str]]:
    if item["linkedin_url"]:
        return "property", {"linkedinUrl": item["linkedin_url"]}
    if item["linkedin_id"]:
        return "property", {"linkedinId": item["linkedin_id"]}
    return "property", {"name": item["canonical_name"]}


def header(response: requests.Response, name: str) -> str:
    return str(response.headers.get(name, "") or "").strip()


def as_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def main() -> int:
    load_env()
    token = clean(os.environ.get(TOKEN_NAME))
    if not token:
        raise SystemExit(f"Missing {TOKEN_NAME} in {ENV_FILE}")
    completed, unresolved, max_ordinal = prior_state()
    excluded = completed | unresolved
    connection = connect_database(AUDIT / "remote_probe.sqlite3")
    candidates = load_candidates(connection, excluded)
    proxies = load_webshare_proxies()
    if len(proxies) <= PROXY_INDEX:
        raise SystemExit(f"Webshare proxy pool has {len(proxies)} entries; index {PROXY_INDEX} is unavailable")
    proxy = proxies[PROXY_INDEX]
    print(json.dumps({"candidate_count": len(candidates), "completed_excluded": len(completed), "interrupted_excluded": len(unresolved), "proxy_pool_index": PROXY_INDEX, "proxy": proxy.identifier}, separators=(",", ":")), flush=True)

    started = now()
    summary: dict[str, Any] = {
        "started_at": started,
        "parallelism": 1,
        "proxy_pool_index": PROXY_INDEX,
        "eligible_unattempted": len(candidates),
        "matched": 0,
        "no_match": 0,
        "rate_limited": 0,
        "ambiguous": 0,
        "failed": 0,
        "credit_cost": 0.0,
        "last_credit_remaining": "",
    }

    session = requests.Session()
    session.trust_env = False
    session.proxies.update({"http": proxy.url, "https": proxy.url})
    ordinal = max_ordinal
    index = 0
    try:
        while index < len(candidates):
            item = candidates[index]
            ordinal += 1
            attempt_id = f"{RUN_LABEL}:{ordinal}:{int(time.time() * 1000)}"
            method, body = request_body(item)
            write_event({"event": "attempting", "attempt_id": attempt_id, "at": now(), "credential": TOKEN_NAME, "company_id": item["company_id"], "method": method, "body_kind": next(iter(body))})
            try:
                response = session.post(
                    ENDPOINT,
                    json=body,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    timeout=(10, 35),
                )
            except requests.Timeout:
                summary["ambiguous"] += 1
                write_event({"event": "ambiguous_timeout", "attempt_id": attempt_id, "at": now(), "credential": TOKEN_NAME, "company_id": item["company_id"], "error": "timeout"})
                print("ambiguous timeout; stopping to avoid a duplicate credit", flush=True)
                break
            except requests.RequestException as exc:
                summary["failed"] += 1
                write_event({"event": "failed", "attempt_id": attempt_id, "at": now(), "credential": TOKEN_NAME, "company_id": item["company_id"], "status": 0, "error": type(exc).__name__})
                index += 1
                continue

            status = int(response.status_code)
            credit_cost = as_float(header(response, "x-credit-cost"), 1.0 if status in {200, 404} else 0.0)
            credit_remaining = header(response, "x-credit-remaining")
            summary["credit_cost"] += credit_cost
            summary["last_credit_remaining"] = credit_remaining
            if status == 429:
                summary["rate_limited"] += 1
                retry_after = max(1.0, as_float(header(response, "retry-after"), 1.0))
                write_event({"event": "rate_limited", "attempt_id": attempt_id, "at": now(), "credential": TOKEN_NAME, "company_id": item["company_id"], "status": status, "retry_after": retry_after, "credit_cost": credit_cost})
                time.sleep(min(retry_after, 65.0))
                # 429 is not a completed company attempt; retry the same item.
                continue

            if status in {401, 402}:
                summary["failed"] += 1
                write_event({"event": "failed", "attempt_id": attempt_id, "at": now(), "credential": TOKEN_NAME, "company_id": item["company_id"], "status": status, "error": "credential_or_credit_rejected", "credit_cost": credit_cost})
                print(f"credential stopped with HTTP {status}", flush=True)
                break
            if status >= 500:
                summary["failed"] += 1
                write_event({"event": "failed", "attempt_id": attempt_id, "at": now(), "credential": TOKEN_NAME, "company_id": item["company_id"], "status": status, "error": "provider_server_error", "credit_cost": credit_cost})
                index += 1
                continue

            payload: Any = None
            if status == 200:
                try:
                    payload = response.json()
                except ValueError:
                    payload = None
            matched = status == 200 and isinstance(payload, dict)
            if matched:
                summary["matched"] += 1
            else:
                summary["no_match"] += 1
            write_event({"event": "result", "attempt_id": attempt_id, "at": now(), "credential": TOKEN_NAME, "company_id": item["company_id"], "matched": matched, "status": status, "credit_cost": credit_cost, "credit_remaining": credit_remaining, "payload": payload if matched else None})
            index += 1
            if index % 25 == 0:
                print(json.dumps({"processed": index, "remaining": len(candidates) - index, "matched": summary["matched"], "no_match": summary["no_match"], "rate_limited": summary["rate_limited"], "credit_cost": summary["credit_cost"], "credit_remaining": credit_remaining}, separators=(",", ":")), flush=True)
            SUMMARY.write_text(json.dumps({**summary, "finished_at": now(), "next_candidate_index": index, "remaining_eligible_unattempted": len(candidates) - index}, indent=2), encoding="utf-8")
            if summary["credit_cost"] >= TARGET_CREDITS or (credit_remaining and as_float(credit_remaining, 999999) <= 1):
                print("credit budget reached; stopping with one credit reserved", flush=True)
                break
            # No artificial one-second throttle: requests remain strictly serial.
            time.sleep(0.01)
    finally:
        session.close()
        SUMMARY.write_text(json.dumps({**summary, "finished_at": now(), "next_candidate_index": index, "remaining_eligible_unattempted": len(candidates) - index}, indent=2), encoding="utf-8")
    print(json.dumps({**summary, "next_candidate_index": index, "remaining_eligible_unattempted": len(candidates) - index}, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
