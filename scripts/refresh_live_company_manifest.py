"""Build a complete company eligibility snapshot from the live catalog.

The existing producer CSV remains the authority for reviewed source evidence.
Live canonical companies missing from that CSV are appended and are promoted to
source-eligible only when the catalog carries a verified field value.  Merely
existing in ``canonical_companies`` never grants scraper eligibility.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(os.environ.get("RUNR_PROJECT_DIR", "")).resolve() if os.environ.get("RUNR_PROJECT_DIR") else Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.application.source_eligibility_manifest import (
    build_source_eligibility_manifest,
    read_master_snapshot,
    write_manifest_bundle,
)
from backend.database.connection import connect_database


def _text(value: object) -> str:
    return str(value or "").strip()


def _field(profile: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    for group in ("fields", "additional_fields"):
        value = profile.get(group, {}).get(name) if isinstance(profile.get(group), Mapping) else None
        if isinstance(value, Mapping) and _text(value.get("value")):
            return value
    return {}


def _verified(field: Mapping[str, Any]) -> bool:
    confidence = _text(field.get("confidence")).casefold()
    state = _text(field.get("state") or field.get("status")).casefold()
    return bool(field.get("verified_at")) or confidence in {"provider_verified", "verified", "high_confidence"} or state == "verified"


def catalog_row(company: Mapping[str, Any], profile: Mapping[str, Any], primary_url: Mapping[str, Any] | None) -> dict[str, str]:
    website_field = _field(profile, "website") or _field(profile, "canonical_url")
    linkedin_url_field = _field(profile, "linkedin_company_url")
    linkedin_id_field = _field(profile, "linkedin_company_id")
    website = _text((primary_url or {}).get("canonical_url") or (primary_url or {}).get("url") or website_field.get("value"))
    website_verified = (
        _text((primary_url or {}).get("validation_status")).casefold() in {"valid", "verified", "complete", "found"}
        or _verified(website_field)
    )
    linkedin_url = _text(linkedin_url_field.get("value"))
    linkedin_id = _text(linkedin_id_field.get("value"))
    linkedin_verified = _verified(linkedin_url_field) and _verified(linkedin_id_field) and linkedin_id.isdecimal()
    verified_at = _text(
        linkedin_id_field.get("verified_at")
        or linkedin_url_field.get("verified_at")
        or website_field.get("verified_at")
        or company.get("updated_at")
    )
    return {
        "canonical_CompanyID": _text(company.get("company_id")),
        "company_name": _text(company.get("canonical_name")),
        "website_url": website,
        "linkedin_company_url": linkedin_url,
        "linkedin_company_id": linkedin_id,
        "linkedin_page_type": "company" if linkedin_url else "",
        "website_discovery_status": "verified" if website and website_verified else "missing",
        "linkedin_company_id_status": "verified" if linkedin_verified else "missing",
        "linkedin_company_id_source": _text((linkedin_id_field.get("provenance") or {}).get("source")),
        "linkedin_company_id_confidence": "1" if linkedin_verified else "",
        "linkedin_company_id_resolved_at": verified_at if linkedin_verified else "",
        "linkedin_company_id_url_used": linkedin_url if linkedin_verified else "",
        "last_enriched_at": verified_at if website_verified else "",
    }


def merge_rows(source_rows: list[dict[str, str]], columns: list[str], catalog_rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    represented = {_text(row.get("canonical_CompanyID")) for row in source_rows if _text(row.get("canonical_CompanyID"))}
    added = 0
    for row in catalog_rows:
        company_id = _text(row.get("canonical_CompanyID"))
        if not company_id or company_id in represented:
            continue
        source_rows.append({column: _text(row.get(column)) for column in columns})
        represented.add(company_id)
        added += 1
    return source_rows, added


def _load_catalog(connection: Any) -> list[dict[str, str]]:
    companies = {
        str(row[0]): {"company_id": row[0], "canonical_name": row[1], "updated_at": row[2]}
        for row in connection.execute("SELECT company_id,canonical_name,updated_at FROM canonical_companies").fetchall()
    }
    profiles: dict[str, Mapping[str, Any]] = {}
    for row in connection.execute("SELECT company_id,profile_json FROM canonical_company_profiles").fetchall():
        try:
            profiles[str(row[0])] = json.loads(row[1] or "{}")
        except (TypeError, ValueError):
            profiles[str(row[0])] = {}
    urls: dict[str, dict[str, Any]] = {}
    for row in connection.execute(
        "SELECT company_id,url,canonical_url,validation_status FROM canonical_company_urls "
        "WHERE url_type='homepage' AND selected_primary=1"
    ).fetchall():
        urls[str(row[0])] = {"url": row[1], "canonical_url": row[2], "validation_status": row[3]}
    return [catalog_row(company, profiles.get(company_id, {}), urls.get(company_id)) for company_id, company in companies.items()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-sidecar", type=Path, required=True)
    parser.add_argument("--snapshot-output", type=Path, required=True)
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument("--as-of", default=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    parser.add_argument("--max-evidence-age-days", type=int, default=365)
    parser.add_argument("--env", type=Path, default=ROOT / "user_config" / ".env")
    args = parser.parse_args()
    if args.env.is_file():
        for line in args.env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip().strip('"').strip("'")
    source_rows, columns, _ = read_master_snapshot(args.input)
    connection = connect_database(args.snapshot_output.with_suffix(".sqlite3"))
    try:
        live_rows = _load_catalog(connection)
    finally:
        connection.close()
    merged, added = merge_rows(source_rows, columns, live_rows)
    args.snapshot_output.parent.mkdir(parents=True, exist_ok=True)
    with args.snapshot_output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(merged)
    rows, fields, digest = read_master_snapshot(args.snapshot_output)
    report = build_source_eligibility_manifest(
        rows, fields, source_path=str(args.snapshot_output.resolve()), input_sha256=digest,
        cycle_id=args.cycle_id, as_of=args.as_of, max_evidence_age_days=args.max_evidence_age_days,
        raw_sidecar_path=str(args.raw_sidecar.resolve()),
    )
    persisted = write_manifest_bundle(args.output, report, raw_sidecar_path=args.raw_sidecar)
    print(json.dumps({"live_companies": len(live_rows), "snapshot_rows": len(rows), "catalog_companies_added": added,
                      "counts": report["counts"], "deductions": report["deductions"], **persisted}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
