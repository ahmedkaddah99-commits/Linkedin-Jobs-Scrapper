"""Apply missing-only LinkedIn company enrichment results to canonical companies."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.database.connection import connect_database
from scripts.collect_linkedin_company_gaps import clean
from scripts.import_restored_company_profiles import canonical_url, load_env

FIELD_SECTIONS = {
    "description": "additional_fields",
    "industry": "fields",
    "linkedin_company_url": "fields",
    "website": "fields",
    "company_size": "fields",
    "headquarters": "fields",
    "founded_year": "fields",
    "company_type": "additional_fields",
    "revenue": "additional_fields",
    "revenue_range": "additional_fields",
}


def current_value(profile: Mapping[str, Any], field: str) -> str:
    for section in ("fields", "additional_fields"):
        values = profile.get(section)
        item = values.get(field) if isinstance(values, Mapping) else None
        value = item.get("value") if isinstance(item, Mapping) else item
        if clean(value):
            return clean(value)
    return ""


def load_unambiguous_offers(path: Path) -> tuple[dict[str, dict[str, str]], Counter[str]]:
    values: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    stats: Counter[str] = Counter()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            row = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            stats["invalid_json_rows"] += 1
            continue
        stats["result_rows"] += 1
        company_id = clean(row.get("company_id"))
        if not company_id or clean(row.get("provider_status")).casefold() != "matched":
            stats["nonmatched_rows"] += 1
            continue
        stats["matched_rows"] += 1
        for field, raw in (row.get("collectible_offers") or {}).items():
            value = clean(raw)
            if field in {*FIELD_SECTIONS, "logo"} and value:
                values[company_id][field].add(value)
    offers: dict[str, dict[str, str]] = {}
    for company_id, fields in values.items():
        accepted: dict[str, str] = {}
        for field, candidates in fields.items():
            if len(candidates) == 1:
                accepted[field] = next(iter(candidates))
                stats[f"unambiguous_{field}"] += 1
            else:
                stats[f"conflicting_{field}"] += 1
        if accepted:
            offers[company_id] = accepted
    stats["companies_with_unambiguous_offers"] = len(offers)
    return offers, stats


def verified_field(value: str, linkedin_url: str, observed_at: str) -> dict[str, Any]:
    return {
        "value": value,
        "state": "verified",
        "status": "verified",
        "confidence": "provider_verified",
        "provenance": {"source": "linkedin_company_profile_webshare", "url": linkedin_url},
        "observed_at": observed_at,
        "verified_at": observed_at,
    }


def plan_changes(connection: Any, offers: Mapping[str, Mapping[str, str]], observed_at: str) -> dict[str, Any]:
    live_profiles: dict[str, tuple[str, dict[str, Any], str, str]] = {}
    primary_urls: dict[str, str] = {}
    offer_ids = sorted(offers)
    for start in range(0, len(offer_ids), 100):
        company_ids = offer_ids[start : start + 100]
        placeholders = ",".join("?" for _ in company_ids)
        for row in connection.execute(
            "SELECT c.company_id,p.profile_json,p.logo_source_url,p.updated_at "
            "FROM canonical_companies c JOIN canonical_company_profiles p ON p.company_id=c.company_id "
            f"WHERE c.company_id IN ({placeholders})",
            tuple(company_ids),
        ).fetchall():
            try:
                profile = json.loads(row[1] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                profile = {}
            live_profiles[str(row[0])] = (str(row[1] or "{}"), profile, str(row[2] or ""), str(row[3] or ""))
        for row in connection.execute(
            "SELECT company_id,canonical_url FROM canonical_company_urls "
            f"WHERE url_type='homepage' AND selected_primary=1 AND company_id IN ({placeholders})",
            tuple(company_ids),
        ).fetchall():
            primary_urls[str(row[0])] = canonical_url(row[1])
    updates: list[tuple[str, str, str, str]] = []
    logo_updates: list[tuple[str, str, str]] = []
    backups: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for company_id, incoming in offers.items():
        existing = live_profiles.get(company_id)
        if existing is None:
            counts["canonical_company_missing"] += 1
            continue
        before_json, profile, logo_source, previous_updated_at = existing
        profile = json.loads(json.dumps(profile))
        linkedin_url = clean(incoming.get("linkedin_company_url")) or current_value(profile, "linkedin_company_url")
        changed: list[str] = []
        for field, section in FIELD_SECTIONS.items():
            value = clean(incoming.get(field))
            if not value or current_value(profile, field):
                continue
            if field == "website":
                value = canonical_url(value)
                if not value:
                    counts["invalid_website"] += 1
                    continue
                primary = primary_urls.get(company_id, "")
                if primary and primary != value:
                    counts["website_conflicts_existing_primary"] += 1
                    continue
            profile.setdefault(section, {})[field] = verified_field(value, linkedin_url, observed_at)
            changed.append(field)
            counts[field] += 1
        if changed:
            profile["observed_at"] = observed_at
            profile["verified_at"] = observed_at
            updates.append((json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":")), observed_at, company_id, before_json))
            backups.append({"company_id": company_id, "profile_json": before_json, "updated_at": previous_updated_at})
        logo = clean(incoming.get("logo"))
        if logo and not logo_source:
            logo_updates.append((logo, observed_at, company_id))
            counts["logo_source_url"] += 1
    return {
        "profile_updates": updates,
        "logo_updates": logo_updates,
        "backups": backups,
        "counts": counts,
        "live_profile_count": len(live_profiles),
    }


def apply_plan(connection: Any, plan: Mapping[str, Any]) -> None:
    def batches(rows: list[Any], size: int = 25):
        for start in range(0, len(rows), size):
            yield rows[start : start + size]

    for batch in batches(plan["profile_updates"]):
        def apply_profiles(transaction: Any, rows: list[Any] = batch) -> None:
            transaction.executemany(
                "UPDATE canonical_company_profiles SET profile_json=?,updated_at=? "
                "WHERE company_id=? AND profile_json=?",
                rows,
            )
        connection.transaction(apply_profiles)
    for batch in batches(plan["logo_updates"]):
        def apply_logos(transaction: Any, rows: list[Any] = batch) -> None:
            transaction.executemany(
                "UPDATE canonical_company_profiles SET logo_source_url=?,updated_at=? "
                "WHERE company_id=? AND COALESCE(logo_source_url,'')=''",
                rows,
            )
        connection.transaction(apply_logos)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--env", type=Path, default=ROOT / "user_config" / ".env")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--remove-created-url-rows", action="store_true")
    args = parser.parse_args()
    load_env(args.env)
    observed_at = datetime.now(timezone.utc).isoformat()
    offers, input_stats = load_unambiguous_offers(args.results)
    connection = connect_database(args.receipt.parent / "remote_probe.sqlite3")
    try:
        if connection.backend != "libsql":
            raise RuntimeError("Expected live remote database")
        if args.remove_created_url_rows:
            before = int(connection.execute(
                "SELECT COUNT(1) FROM canonical_company_urls WHERE source=? AND rule_version=?",
                ("linkedin_company_profile_webshare", "linkedin_company_gap_import_v1"),
            ).fetchone()[0])
            if args.apply and before:
                connection.execute(
                    "DELETE FROM canonical_company_urls WHERE source=? AND rule_version=?",
                    ("linkedin_company_profile_webshare", "linkedin_company_gap_import_v1"),
                )
                connection.commit()
            after = int(connection.execute(
                "SELECT COUNT(1) FROM canonical_company_urls WHERE source=? AND rule_version=?",
                ("linkedin_company_profile_webshare", "linkedin_company_gap_import_v1"),
            ).fetchone()[0])
            receipt = {"applied": args.apply, "created_url_rows_before": before, "created_url_rows_after": after}
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(receipt, indent=2))
            return 0
        plan = plan_changes(connection, offers, observed_at)
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        backup_path = args.receipt.with_name(args.receipt.stem + "-before.json")
        backup_path.write_text(json.dumps(plan["backups"], ensure_ascii=False, indent=2), encoding="utf-8")
        if args.apply:
            apply_plan(connection, plan)
        receipt = {
            "generated_at": observed_at,
            "applied": args.apply,
            "input": dict(input_stats),
            "live_profile_count": plan["live_profile_count"],
            "companies_with_profile_updates": len(plan["profile_updates"]),
            "planned": dict(plan["counts"]),
            "backup": str(backup_path),
        }
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(receipt, indent=2))
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
