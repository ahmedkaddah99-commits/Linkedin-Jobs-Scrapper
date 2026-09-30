"""Import restored company source fields and definitive CompanyEnrich results.

The import is additive: existing known profile fields and verified logo metadata
win. Paid-provider timeout/failed ledger entries are never imported as results.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.application.company_enrichment import COMPANY_ENRICHMENT_FIELDS
from backend.application.company_identity_canonicalization import build_company_crosswalk
from backend.database.connection import connect_database


def load_env(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def text(value: Any) -> str:
    value = str(value or "").strip()
    return "" if value.casefold() in {"", "null", "none", "n/a", "na", "unknown", "-", "//"} else value


def domain(value: Any) -> str:
    raw = text(value)
    if not raw:
        return ""
    try:
        host = urlsplit(raw if "://" in raw else "https://" + raw).hostname or ""
    except ValueError:
        return ""
    return host.casefold().removeprefix("www.").rstrip(".")


def canonical_url(value: Any) -> str:
    host = domain(value)
    if not host:
        return ""
    raw = text(value)
    try:
        parsed = urlsplit(raw if "://" in raw else "https://" + raw)
    except ValueError:
        return ""
    path = "/" + "/".join(part for part in parsed.path.split("/") if part)
    return f"https://{host}{path.rstrip('/')}"


def known(value: Any, source: str, url: str, observed_at: str) -> dict[str, Any]:
    return {
        "value": value, "state": "known", "status": "known",
        "confidence": "restored_authoritative" if source.startswith("restored") else "provider_verified",
        "provenance": {"source": source, "url": url},
        "observed_at": observed_at, "verified_at": observed_at,
    }


def load_provider_results(paths: list[Path]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except (TypeError, ValueError):
                continue
            if item.get("event") not in (None, "result") or not item.get("matched"):
                continue
            payload = item.get("payload")
            company_id = text(item.get("company_id"))
            if company_id and isinstance(payload, dict):
                results[company_id] = payload
    return results


def multirow_upsert(connection: Any, sql_prefix: str, sql_suffix: str, rows: list[tuple[Any, ...]], width: int) -> None:
    for start in range(0, len(rows), 25):
        batch = rows[start:start + 25]
        connection.execute(
            sql_prefix + ",".join(["(" + ",".join(["?"] * width) + ")"] * len(batch)) + sql_suffix,
            tuple(value for row in batch for value in row),
        )
        connection.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / "user_config" / ".env")
    parser.add_argument("--source", type=Path, default=ROOT / "data" / "acquisition" / "inputs" / "company_sources_linkedin_ids.csv")
    parser.add_argument("--provider-results", type=Path, action="append", default=[])
    parser.add_argument(
        "--provider-only",
        action="store_true",
        help="Upsert only companies with definitive provider matches from this invocation.",
    )
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    load_env(args.env_file)
    source_rows = list(csv.DictReader(args.source.open(encoding="utf-8-sig", newline="")))
    crosswalk = build_company_crosswalk(source_rows)
    provider = load_provider_results(args.provider_results)
    now = datetime.now(timezone.utc).isoformat()
    connection = connect_database(args.receipt.parent / "remote_probe.sqlite3")
    try:
        live_ids = {str(row[0]) for row in connection.execute("SELECT company_id FROM canonical_companies").fetchall()}
        profile_sql = (
            "SELECT company_id,profile_json,logo_object_key,logo_source_url,logo_content_hash,logo_content_type,logo_verified_at,created_at "
            "FROM canonical_company_profiles"
        )
        profile_params: tuple[Any, ...] = ()
        if args.provider_only and provider:
            ids = sorted(provider)
            profile_sql += " WHERE company_id IN (" + ",".join("?" for _ in ids) + ")"
            profile_params = tuple(ids)
        existing_profiles = {
            str(row[0]): {
                "profile": json.loads(str(row[1] or "{}")), "logo_object_key": str(row[2] or ""),
                "logo_source_url": str(row[3] or ""), "logo_content_hash": str(row[4] or ""),
                "logo_content_type": str(row[5] or ""), "logo_verified_at": str(row[6] or ""),
                "created_at": str(row[7] or now),
            }
            for row in connection.execute(profile_sql, profile_params).fetchall()
        }
        primary_homepages = {
            str(row[0]) for row in connection.execute(
                "SELECT company_id FROM canonical_company_urls WHERE url_type='homepage' AND selected_primary=1"
            ).fetchall()
        }
        aggregated: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(source_rows):
            company_id = crosswalk.mapping_by_row[index]
            if company_id not in live_ids:
                continue
            target = aggregated.setdefault(company_id, {"fields": {}, "additional": {}, "logo": "", "website": ""})
            restored_url = text(row.get("website_url"))
            restored_domain = text(row.get("domain")) or domain(restored_url)
            headquarters = text(row.get("headquarters_display")) or ", ".join(filter(None, [text(row.get("headquarters_city")), text(row.get("headquarters_region")), text(row.get("headquarters_country"))]))
            values = {
                "companyenrich_id": text(row.get("companyenrich_id")), "company_name": text(row.get("company_name")),
                "domain": restored_domain, "linkedin_company_url": text(row.get("linkedin_company_url")),
                "linkedin_company_id": text(row.get("linkedin_company_id")), "website": restored_url,
                "industry": text(row.get("industry")), "company_size": text(row.get("employee_count_range")) or text(row.get("employee_count")),
                "headquarters": headquarters, "founded_year": text(row.get("founded_year")),
            }
            for name, value in values.items():
                if value and name not in target["fields"]:
                    target["fields"][name] = known(value, "restored_company_source", "", now)
            for name in ("company_type", "revenue_range", "description", "seo_description", "legal_name"):
                value = text(row.get(name))
                if value and name not in target["additional"]:
                    target["additional"][name] = known(value, "restored_company_source", "", now)
            target["logo"] = target["logo"] or text(row.get("logo_url")) or text(row.get("companyenrich_free_logo_url"))
            target["website"] = target["website"] or restored_url

        for company_id, payload in provider.items():
            if company_id not in live_ids:
                continue
            target = aggregated.setdefault(
                company_id,
                {"fields": {}, "additional": {}, "logo": "", "website": ""},
            )
            socials = payload.get("socials") if isinstance(payload.get("socials"), dict) else {}
            location = payload.get("location") if isinstance(payload.get("location"), dict) else {}
            parts = []
            for name in ("city", "state", "country"):
                value = location.get(name)
                value = value.get("name") if isinstance(value, dict) else value
                if text(value) and text(value) not in parts:
                    parts.append(text(value))
            values = {
                "companyenrich_id": payload.get("id"), "company_name": payload.get("name"), "domain": payload.get("domain"),
                "linkedin_company_url": socials.get("linkedin_url"), "linkedin_company_id": socials.get("linkedin_id"),
                "website": payload.get("website"), "industry": payload.get("industry"),
                "company_size": payload.get("employees") or payload.get("reported_employees"),
                "headquarters": ", ".join(parts), "founded_year": payload.get("founded_year"),
            }
            for name, value in values.items():
                if text(value):
                    target["fields"][name] = known(value, "companyenrich:batch_domain", "https://api.companyenrich.com/companies/enrich", now)
            for name in ("type", "revenue", "description", "seo_description", "legalName"):
                if text(payload.get(name)):
                    target["additional"][name] = known(payload[name], "companyenrich:batch_domain", "https://api.companyenrich.com/companies/enrich", now)
            target["logo"] = target["logo"] or text(payload.get("logo_url"))
            target["website"] = target["website"] or text(payload.get("website"))

        if args.provider_only:
            aggregated = {
                company_id: payload
                for company_id, payload in aggregated.items()
                if company_id in provider
            }

        profile_rows = []
        url_rows = []
        for company_id, incoming in aggregated.items():
            existing = existing_profiles.get(company_id, {})
            profile = existing.get("profile") if isinstance(existing.get("profile"), dict) else {}
            fields = profile.get("fields") if isinstance(profile.get("fields"), dict) else {}
            additional = profile.get("additional_fields") if isinstance(profile.get("additional_fields"), dict) else {}
            for name, value in incoming["fields"].items():
                if not isinstance(fields.get(name), dict) or not text(fields[name].get("value")):
                    fields[name] = value
            for name, value in incoming["additional"].items():
                if not isinstance(additional.get(name), dict) or not text(additional[name].get("value")):
                    additional[name] = value
            for name in COMPANY_ENRICHMENT_FIELDS:
                fields.setdefault(name, {"value": None, "state": "unknown", "status": "unknown", "provenance": None, "observed_at": None, "verified_at": None, "unknown_reason": "not_verified_from_authoritative_company_source"})
            profile.update({"schema_version": "phase_f_v3", "fields": fields, "additional_fields": additional, "source": "restored_company_source+companyenrich", "observed_at": now, "verified_at": now})
            known_count = sum(bool(isinstance(v, dict) and text(v.get("value"))) for v in fields.values())
            status = "present" if known_count == len(fields) else "incomplete" if known_count else "absent"
            logo_source = existing.get("logo_source_url") or incoming["logo"]
            profile_rows.append((company_id, json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":")), status,
                existing.get("logo_object_key", ""), logo_source, existing.get("logo_content_hash", ""),
                existing.get("logo_content_type", ""), existing.get("logo_verified_at", ""), existing.get("created_at", now), now))
            website = canonical_url(incoming["website"])
            if website and company_id not in primary_homepages:
                url_id = "company_url_" + hashlib.sha256(f"{company_id}:homepage:{website}".encode()).hexdigest()[:24]
                url_rows.append((url_id, company_id, "homepage", website, website, "restored_company_source", "", now, now,
                    "not_validated", "", 1, "company_identity_v1", now, now, "configured_official", "restored_canonical_company_source", "", 1, ""))

        multirow_upsert(connection,
            "INSERT INTO canonical_company_profiles(company_id,profile_json,profile_status,logo_object_key,logo_source_url,logo_content_hash,logo_content_type,logo_verified_at,created_at,updated_at) VALUES ",
            " ON CONFLICT(company_id) DO UPDATE SET profile_json=excluded.profile_json,profile_status=excluded.profile_status,logo_source_url=CASE WHEN canonical_company_profiles.logo_source_url='' THEN excluded.logo_source_url ELSE canonical_company_profiles.logo_source_url END,updated_at=excluded.updated_at", profile_rows, 10)
        multirow_upsert(connection,
            "INSERT INTO canonical_company_urls(company_url_id,company_id,url_type,url,canonical_url,source,source_observation_id,first_seen_at,last_seen_at,validation_status,redirect_target,selected_primary,rule_version,created_at,updated_at,url_lifecycle,validation_reason,ignored_reason,occurrence_count,source_target_id) VALUES ",
            " ON CONFLICT(company_id,url_type,canonical_url) DO UPDATE SET last_seen_at=excluded.last_seen_at,source=excluded.source,selected_primary=CASE WHEN canonical_company_urls.selected_primary=1 THEN 1 ELSE excluded.selected_primary END,updated_at=excluded.updated_at", url_rows, 20)
        receipt = {"generated_at": now, "source_rows": len(source_rows), "mapped_source_rows": sum(crosswalk.mapping_by_row[i] in live_ids for i in range(len(source_rows))),
            "distinct_companies_upserted": len(profile_rows), "provider_matches_imported": len(provider), "primary_homepages_inserted_or_updated": len(url_rows),
            "verified_logo_metadata_preserved": sum(bool(existing.get("logo_verified_at")) for existing in existing_profiles.values())}
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(receipt, indent=2))
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
