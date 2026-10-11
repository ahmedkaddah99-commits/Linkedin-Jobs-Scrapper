"""Bounded Webshare trial for LinkedIn-ID companies with profile gaps.

The default mode is evidence-only: it reads the live catalog and writes JSONL
and summary artifacts locally. It never mutates the catalog.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.application.company_enrichment import WebshareLinkedInCompanyProvider
from backend.database.connection import connect_database
from scripts.master_linkedin_jobs_catalog import load_webshare_proxies

SENTINELS = {"", "//", "-", "n/a", "none", "null", "unknown", "undisclosed", "not disclosed"}
COLLECTIBLE_FIELDS = (
    "description",
    "industry",
    "linkedin_company_url",
    "logo",
    "website",
    "company_size",
    "headquarters",
    "founded_year",
    "company_type",
    "revenue",
    "revenue_range",
)


def clean(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip()
    return "" if text.casefold() in SENTINELS else text


def load_env(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def completed_company_ids(path: Path) -> set[str]:
    """Return durably completed company IDs from a checkpoint JSONL file."""

    completed: set[str] = set()
    if not path.exists():
        return completed
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            record = json.loads(line)
        except (TypeError, ValueError):
            continue
        if record.get("event") != "result" and "provider_status" not in record:
            continue
        company_id = clean(record.get("company_id"))
        if company_id:
            completed.add(company_id)
    return completed


def profile_value(profile: Mapping[str, Any], field: str) -> Any:
    for section in ("fields", "additional_fields"):
        values = profile.get(section)
        entry = values.get(field) if isinstance(values, Mapping) else None
        value = entry.get("value") if isinstance(entry, Mapping) else entry
        if clean(value):
            return value
    return ""


def linkedin_homepage(profile: Mapping[str, Any], linkedin_id: Any) -> str:
    existing = clean(profile_value(profile, "linkedin_company_url"))
    if existing:
        return existing
    identifier = clean(linkedin_id)
    if not identifier:
        return ""
    return f"https://www.linkedin.com/company/{quote(identifier, safe='-._~')}/"


def missing_collectible_fields(profile: Mapping[str, Any], *, logo_source_url: Any, logo_object_key: Any) -> list[str]:
    present = {
        "description": bool(clean(profile_value(profile, "description")) or clean(profile_value(profile, "linkedin_description"))),
        "industry": bool(clean(profile_value(profile, "industry")) or clean(profile_value(profile, "linkedin_industry"))),
        "linkedin_company_url": bool(clean(profile_value(profile, "linkedin_company_url"))),
        "logo": any(clean(item) for item in (logo_source_url, logo_object_key, profile_value(profile, "logo"), profile_value(profile, "logo_url"))),
        "website": bool(clean(profile_value(profile, "website")) or clean(profile_value(profile, "linkedin_website"))),
        "company_size": bool(clean(profile_value(profile, "company_size")) or clean(profile_value(profile, "linkedin_company_size"))),
        "headquarters": bool(clean(profile_value(profile, "headquarters")) or clean(profile_value(profile, "linkedin_headquarters"))),
        "founded_year": bool(clean(profile_value(profile, "founded_year")) or clean(profile_value(profile, "linkedin_founded_year"))),
        "company_type": bool(clean(profile_value(profile, "company_type")) or clean(profile_value(profile, "linkedin_company_type"))),
        "revenue": bool(clean(profile_value(profile, "revenue")) or clean(profile_value(profile, "linkedin_revenue"))),
        "revenue_range": bool(clean(profile_value(profile, "revenue_range"))),
    }
    return [field for field in COLLECTIBLE_FIELDS if not present[field]]


def offered_fields(result: Mapping[str, Any]) -> dict[str, Any]:
    fields = result.get("fields") if isinstance(result.get("fields"), Mapping) else {}
    extra = result.get("extra_fields") if isinstance(result.get("extra_fields"), Mapping) else {}
    matched = clean(extra.get("linkedin_lookup_status")).casefold() == "matched"
    offers = {
        "description": extra.get("linkedin_description"),
        "industry": fields.get("industry") or extra.get("linkedin_industry"),
        "linkedin_company_url": (extra.get("linkedin_company_url") or result.get("provenance_url")) if matched else "",
        "logo": result.get("logo_source_url") if result.get("logo_bytes") else "",
        "website": fields.get("website") or extra.get("linkedin_website"),
        "company_size": fields.get("company_size") or extra.get("linkedin_company_size"),
        "headquarters": fields.get("headquarters") or extra.get("linkedin_headquarters"),
        "founded_year": fields.get("founded_year") or extra.get("linkedin_founded_year"),
        "company_type": extra.get("linkedin_company_type"),
        "revenue": extra.get("linkedin_revenue"),
        "revenue_range": "",
    }
    return {key: value for key, value in offers.items() if clean(value)}


def load_candidates(connection: Any) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT c.company_id,c.canonical_name,c.provenance_url,p.profile_json,
               p.logo_source_url,p.logo_object_key
        FROM canonical_companies c
        JOIN canonical_company_profiles p ON p.company_id=c.company_id
        ORDER BY c.company_id
        """
    ).fetchall()
    candidates = []
    for row in rows:
        try:
            profile = json.loads(row[3] or "{}")
        except (TypeError, ValueError):
            continue
        linkedin_id = profile_value(profile, "linkedin_company_id")
        if not clean(linkedin_id):
            continue
        missing = missing_collectible_fields(profile, logo_source_url=row[4], logo_object_key=row[5])
        if not missing:
            continue
        candidates.append(
            {
                "company_id": clean(row[0]),
                "canonical_name": clean(row[1]),
                "linkedin_company_id": clean(linkedin_id),
                "linkedin_url": linkedin_homepage(profile, linkedin_id),
                "missing_fields": missing,
                "profile_json": row[3],
            }
        )
    # Highest potential field yield first, then stable order for resumability.
    return sorted(candidates, key=lambda item: (-len(item["missing_fields"]), item["company_id"]))


async def collect_one(item: Mapping[str, Any], *, proxy_url: str, request_timeout: int) -> dict[str, Any]:
    """Collect one company through one fixed proxy; never mutate shared provider state."""

    provider = WebshareLinkedInCompanyProvider(timeout_seconds=request_timeout)
    provider.webshare_proxy_url = proxy_url
    provider.official_provider.proxy_url = proxy_url
    company = {
        "company_id": item["company_id"],
        "canonical_name": item["canonical_name"],
        "provenance_url": item["linkedin_url"],
        "profile_json": item["profile_json"],
    }
    began = time.monotonic()
    try:
        result = await provider.enrich(company, conditional={})
        offers = offered_fields(result)
        usable = {key: value for key, value in offers.items() if key in item["missing_fields"]}
        status = clean((result.get("extra_fields") or {}).get("linkedin_lookup_status")) or "unknown"
        return {
            "event": "result",
            "company_id": item["company_id"],
            "canonical_name": item["canonical_name"],
            "linkedin_company_id": item["linkedin_company_id"],
            "linkedin_url": item["linkedin_url"],
            "missing_before": item["missing_fields"],
            "collectible_offers": usable,
            "provider_status": status,
            "transport": (result.get("extra_fields") or {}).get("linkedin_fetch_transport", ""),
            "requests": int(result.get("request_count") or 0),
            "elapsed_seconds": round(time.monotonic() - began, 3),
        }
    except Exception as exc:
        return {
            "event": "result",
            "company_id": item["company_id"],
            "canonical_name": item["canonical_name"],
            "linkedin_company_id": item["linkedin_company_id"],
            "linkedin_url": item["linkedin_url"],
            "missing_before": item["missing_fields"],
            "collectible_offers": {},
            "provider_status": "error",
            "error_type": type(exc).__name__,
            "elapsed_seconds": round(time.monotonic() - began, 3),
        }


async def collect(args: argparse.Namespace) -> dict[str, Any]:
    load_env(Path(args.env))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    connection = connect_database(output / "remote_probe.sqlite3")
    try:
        candidates = load_candidates(connection)
    finally:
        connection.close()
    if args.target_field:
        candidates = [item for item in candidates if args.target_field in item["missing_fields"]]
    result_path = output / "results.jsonl"
    already_completed = completed_company_ids(result_path) if args.resume else set()
    total_eligible = len(candidates)
    candidates = [item for item in candidates if item["company_id"] not in already_completed]
    # Prefer the current direct proxy pool returned by Webshare's published API.
    # Static gateway credentials can expire and currently return HTTP 407.
    proxies = load_webshare_proxies()
    if not proxies:
        raise RuntimeError("Webshare returned no usable direct proxies")
    started_at = datetime.now(timezone.utc).isoformat()
    started_monotonic = time.monotonic()
    deadline = time.monotonic() + args.duration_seconds if args.duration_seconds else float("inf")
    attempts = successes = failures = request_count = 0
    field_yield: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    status_path = output / "progress.json"
    file_mode = "a" if args.resume else "w"
    with result_path.open(file_mode, encoding="utf-8") as handle:
        bounded_candidates = candidates[: args.max_companies]
        concurrency = min(args.concurrency, len(proxies), len(bounded_candidates))
        for offset in range(0, len(bounded_candidates), max(1, concurrency)):
            if time.monotonic() >= deadline:
                break
            batch = bounded_candidates[offset : offset + max(1, concurrency)]
            records = await asyncio.gather(
                *(
                    collect_one(
                        item,
                        proxy_url=proxies[(offset + index) % len(proxies)].url,
                        request_timeout=args.request_timeout,
                    )
                    for index, item in enumerate(batch)
                )
            )
            last_company_id = ""
            for record in records:
                attempts += 1
                last_company_id = str(record["company_id"])
                status = str(record.get("provider_status") or "unknown")
                status_counts[status if status != "error" else str(record.get("error_type") or "error")] += 1
                request_count += int(record.get("requests") or 0)
                usable = record.get("collectible_offers") or {}
                if status == "error":
                    failures += 1
                elif usable:
                    successes += 1
                    field_yield.update(usable.keys())
                handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            progress = {
                "status": "running",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "total_eligible": total_eligible,
                "completed_before_resume": len(already_completed),
                "completed_this_run": attempts,
                "completed_total": len(already_completed) + attempts,
                "remaining": max(0, total_eligible - len(already_completed) - attempts),
                "matched_with_new_fields_this_run": successes,
                "failures_this_run": failures,
                "last_company_id": last_company_id,
                "concurrency": concurrency,
            }
            status_path.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")

    elapsed = time.monotonic() - started_monotonic
    summary = {
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "mode": "evidence_only_no_database_writes",
        "target_field": args.target_field,
        "configured_duration_seconds": args.duration_seconds,
        "elapsed_seconds": round(elapsed, 2),
        "eligible_companies": total_eligible,
        "completed_before_resume": len(already_completed),
        "attempted_companies": attempts,
        "companies_with_new_collectible_fields": successes,
        "companies_without_new_collectible_fields": attempts - successes - failures,
        "failed_companies": failures,
        "success_percentage": round(100 * successes / attempts, 2) if attempts else 0,
        "provider_requests": request_count,
        "webshare_proxy_pool_size": len(proxies),
        "concurrency": min(args.concurrency, len(proxies)),
        "field_yield": dict(field_yield),
        "provider_statuses": dict(status_counts),
        "results_file": str(result_path),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    status_path.write_text(
        json.dumps(
            {
                "status": "completed" if len(already_completed) + attempts >= total_eligible else "stopped_at_bound",
                "updated_at": summary["finished_at"],
                "total_eligible": total_eligible,
                "completed_total": len(already_completed) + attempts,
                "remaining": max(0, total_eligible - len(already_completed) - attempts),
                "summary_file": str(output / "summary.json"),
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=str(ROOT / "user_config" / ".env"))
    parser.add_argument("--output", default=str(ROOT / "data" / "audit" / "linkedin_webshare_trial_2026-09-28"))
    parser.add_argument("--duration-seconds", type=int, default=300)
    parser.add_argument("--max-companies", type=int, default=1000)
    parser.add_argument("--request-timeout", type=int, default=15)
    parser.add_argument("--target-field", choices=COLLECTIBLE_FIELDS, default="")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args()
    if args.duration_seconds < 0 or args.max_companies < 1 or args.request_timeout < 2 or args.concurrency < 1:
        parser.error("duration cannot be negative; max companies and request timeout must be positive")
    return args


if __name__ == "__main__":
    raise SystemExit(asyncio.run(collect(parse_args())) is None)
