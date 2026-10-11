"""Create a read-only live report for companies that have a LinkedIn company ID."""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.database.connection import connect_database


SENTINELS = {"", "//", "-", "n/a", "none", "null", "unknown"}
PROFILE_FIELDS = (
    "description",
    "industry",
    "linkedin_company_id",
    "linkedin_company_url",
    "revenue",
    "revenue_range",
    "type",
    "company_type",
    "website",
)
REPORT_FIELDS = (
    "description",
    "industry",
    "linkedin_company_id",
    "linkedin_company_url",
    "logo",
    "logo_verified_timestamp",
    "name",
    "provenance_url",
    "revenue",
    "revenue_range",
    "selected_primary_homepage",
    "type",
    "company_type",
    "website",
)


def load_env() -> None:
    for line in (ROOT / "user_config" / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def populated(value: object) -> bool:
    return str(value or "").strip().lower() not in SENTINELS


def profile_value(profile: dict, field: str) -> object:
    # Check each value independently: an unknown/sentinel in one section must not
    # mask a useful value in the other section.
    for section in ("fields", "additional_fields"):
        entry = profile.get(section, {}).get(field, {})
        value = entry.get("value") if isinstance(entry, dict) else entry
        if populated(value):
            return value
    return ""


def main() -> int:
    load_env()
    output_dir = ROOT / "data" / "audit" / "linkedin_company_field_gaps_2026-09-28"
    output_dir.mkdir(parents=True, exist_ok=True)
    connection = connect_database(output_dir / "remote_probe.sqlite3")
    try:
        rows = connection.execute(
            """
            SELECT c.company_id, c.canonical_name, c.provenance_url,
                   p.profile_json, p.logo_source_url, p.logo_object_key,
                   p.logo_verified_at,
                   CASE WHEN EXISTS (
                       SELECT 1 FROM canonical_company_urls u
                       WHERE u.company_id=c.company_id
                         AND u.url_type='homepage' AND u.selected_primary=1
                         AND trim(COALESCE(u.url,''))<>''
                   ) THEN 1 ELSE 0 END AS selected_primary_homepage
            FROM canonical_companies c
            LEFT JOIN canonical_company_profiles p ON p.company_id=c.company_id
            ORDER BY lower(c.canonical_name), c.company_id
            """
        ).fetchall()
    finally:
        connection.close()

    all_company_count = len(rows)
    companies: list[dict[str, object]] = []
    for row in rows:
        try:
            profile = json.loads(row[3] or "{}")
        except (TypeError, ValueError):
            profile = {}
        values = {field: profile_value(profile, field) for field in PROFILE_FIELDS}
        if not populated(values["linkedin_company_id"]):
            continue
        present = {
            **{field: populated(values[field]) for field in PROFILE_FIELDS},
            "logo": any(
                populated(value)
                for value in (
                    row[4],
                    row[5],
                    profile_value(profile, "logo"),
                    profile_value(profile, "logo_url"),
                )
            ),
            "logo_verified_timestamp": populated(row[6]),
            "name": populated(row[1]),
            "provenance_url": populated(row[2]),
            "selected_primary_homepage": bool(row[7]),
        }
        missing = [field for field in REPORT_FIELDS if not present[field]]
        companies.append(
            {
                "company_id": row[0],
                "name": row[1],
                "linkedin_company_id": values["linkedin_company_id"],
                "linkedin_company_url": values["linkedin_company_url"],
                "missing_fields": missing,
                "missing_field_count": len(missing),
            }
        )

    cohort_count = len(companies)
    field_summary = []
    for field in REPORT_FIELDS:
        missing_count = sum(field in company["missing_fields"] for company in companies)
        populated_count = cohort_count - missing_count
        field_summary.append(
            {
                "field": field,
                "populated": populated_count,
                "missing": missing_count,
                "total_linkedin_id_companies": cohort_count,
                "completeness_percentage": round(100 * populated_count / cohort_count, 2) if cohort_count else 0,
                "missing_percentage": round(100 * missing_count / cohort_count, 2) if cohort_count else 0,
            }
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "generated_at": generated_at,
        "source": "live Turso canonical catalog (read-only)",
        "all_canonical_companies": all_company_count,
        "linkedin_id_company_cohort": cohort_count,
        "cohort_percentage_of_all_companies": round(100 * cohort_count / all_company_count, 2) if all_company_count else 0,
        "field_summary": field_summary,
        "companies_with_any_missing_reported_field": sum(bool(company["missing_fields"]) for company in companies),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    with (output_dir / "companies_missing_fields.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "company_id",
                "name",
                "linkedin_company_id",
                "linkedin_company_url",
                "missing_field_count",
                "missing_fields",
            ),
        )
        writer.writeheader()
        for company in companies:
            if company["missing_fields"]:
                writer.writerow({**company, "missing_fields": ";".join(company["missing_fields"])})

    lines = [
        "# LinkedIn-ID company field completeness",
        "",
        f"Generated {generated_at} from the live Turso canonical catalog using read-only queries.",
        f"Cohort: {cohort_count:,} companies with a non-sentinel LinkedIn company ID "
        f"out of {all_company_count:,} canonical companies ({summary['cohort_percentage_of_all_companies']:.2f}%).",
        "Logo combines the profile logo/logo_url values with logo_source_url and logo_object_key. "
        "The verification timestamp is measured separately. Type/company_type and revenue/revenue_range are separate aliases and are not added together.",
        "",
        "| Field | Populated | Missing | Completeness | Missing |",
        "|---|---:|---:|---:|---:|",
    ]
    lines.extend(
        f"| `{item['field']}` | {item['populated']:,} | {item['missing']:,} | "
        f"{item['completeness_percentage']:.2f}% | {item['missing_percentage']:.2f}% |"
        for item in field_summary
    )
    lines.extend(
        [
            "",
            f"Companies missing at least one reported field: {summary['companies_with_any_missing_reported_field']:,}.",
            "The companion CSV lists each affected company and its missing fields.",
            "",
        ]
    )
    (output_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
