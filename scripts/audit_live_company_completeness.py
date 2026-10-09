"""Audit populated company fields in the live Turso catalog."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.database.connection import connect_database


def load_env() -> None:
    for line in (ROOT / "user_config" / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def n(value: object) -> int:
    return int(value or 0)


def main() -> int:
    load_env()
    audit_dir = ROOT / "data" / "audit" / "companyenrich_live_2026-09-26"
    connection = connect_database(audit_dir / "remote_probe.sqlite3")
    try:
        total = n(connection.execute("SELECT count(*) FROM canonical_companies").fetchall()[0][0])
        selected = n(connection.execute("SELECT count(DISTINCT company_id) FROM canonical_company_urls WHERE url_type='homepage' AND selected_primary=1").fetchall()[0][0])
        provenance = n(connection.execute("SELECT count(*) FROM canonical_companies WHERE trim(COALESCE(provenance_url,''))<>''").fetchall()[0][0])
        profiles = n(connection.execute("SELECT count(*) FROM canonical_company_profiles").fetchall()[0][0])
        logo_source = n(connection.execute("SELECT count(*) FROM canonical_company_profiles WHERE trim(COALESCE(logo_source_url,''))<>''").fetchall()[0][0])
        verified_logo = n(connection.execute("SELECT count(*) FROM canonical_company_profiles WHERE trim(COALESCE(logo_verified_at,''))<>''").fetchall()[0][0])
        query = """
          SELECT
            count(*) AS total,
            sum(CASE WHEN trim(COALESCE(c.canonical_name,''))<>'' THEN 1 ELSE 0 END),
            sum(CASE WHEN trim(COALESCE(json_extract(p.profile_json,'$.fields.website.value'),json_extract(p.profile_json,'$.additional_fields.website.value'),''))<>'' THEN 1 ELSE 0 END),
            sum(CASE WHEN trim(COALESCE(json_extract(p.profile_json,'$.fields.domain.value'),json_extract(p.profile_json,'$.additional_fields.domain.value'),''))<>'' THEN 1 ELSE 0 END),
            sum(CASE WHEN trim(COALESCE(json_extract(p.profile_json,'$.fields.linkedin_company_url.value'),json_extract(p.profile_json,'$.additional_fields.linkedin_company_url.value'),''))<>'' THEN 1 ELSE 0 END),
            sum(CASE WHEN trim(COALESCE(json_extract(p.profile_json,'$.fields.linkedin_company_id.value'),json_extract(p.profile_json,'$.additional_fields.linkedin_company_id.value'),''))<>'' THEN 1 ELSE 0 END),
            sum(CASE WHEN trim(COALESCE(json_extract(p.profile_json,'$.fields.companyenrich_id.value'),json_extract(p.profile_json,'$.additional_fields.companyenrich_id.value'),''))<>'' THEN 1 ELSE 0 END),
            sum(CASE WHEN trim(COALESCE(json_extract(p.profile_json,'$.fields.industry.value'),json_extract(p.profile_json,'$.additional_fields.industry.value'),''))<>'' THEN 1 ELSE 0 END),
            sum(CASE WHEN trim(COALESCE(json_extract(p.profile_json,'$.fields.company_size.value'),json_extract(p.profile_json,'$.additional_fields.company_size.value'),''))<>'' THEN 1 ELSE 0 END),
            sum(CASE WHEN trim(COALESCE(json_extract(p.profile_json,'$.fields.headquarters.value'),json_extract(p.profile_json,'$.additional_fields.headquarters.value'),''))<>'' THEN 1 ELSE 0 END),
            sum(CASE WHEN trim(COALESCE(json_extract(p.profile_json,'$.fields.founded_year.value'),json_extract(p.profile_json,'$.additional_fields.founded_year.value'),''))<>'' THEN 1 ELSE 0 END),
            sum(CASE WHEN trim(COALESCE(json_extract(p.profile_json,'$.additional_fields.type.value'),json_extract(p.profile_json,'$.additional_fields.company_type.value'),''))<>'' THEN 1 ELSE 0 END),
            sum(CASE WHEN trim(COALESCE(json_extract(p.profile_json,'$.additional_fields.revenue.value'),json_extract(p.profile_json,'$.additional_fields.revenue_range.value'),''))<>'' THEN 1 ELSE 0 END),
            sum(CASE WHEN trim(COALESCE(json_extract(p.profile_json,'$.additional_fields.description.value'),''))<>'' THEN 1 ELSE 0 END)
          FROM canonical_companies c
          LEFT JOIN canonical_company_profiles p ON p.company_id=c.company_id
        """
        values = connection.execute(query).fetchall()[0]
        total = n(values[0])
        counts = {
            "Canonical company ID": total,
            "Company name": n(values[1]),
            "Selected primary URL": selected,
            "Provenance URL": provenance,
            "Company profile": profiles,
            "Company website URL": n(values[2]),
            "Domain": n(values[3]),
            "LinkedIn company URL": n(values[4]),
            "LinkedIn company ID": n(values[5]),
            "CompanyEnrich ID": n(values[6]),
            "Industry": n(values[7]),
            "Company size": n(values[8]),
            "Headquarters": n(values[9]),
            "Founded year": n(values[10]),
            "Company type": n(values[11]),
            "Revenue range": n(values[12]),
            "Description": n(values[13]),
            "Logo source URL": logo_source,
            "Verified logo": verified_logo,
        }
        active_ids = "(SELECT DISTINCT company_id FROM canonical_jobs WHERE lifecycle_state='active')"
        active_total = n(connection.execute(f"SELECT count(*) FROM canonical_companies WHERE company_id IN {active_ids}").fetchall()[0][0])
        active_selected = n(connection.execute(f"SELECT count(DISTINCT u.company_id) FROM canonical_company_urls u WHERE u.url_type='homepage' AND u.selected_primary=1 AND u.company_id IN {active_ids}").fetchall()[0][0])
        active_provenance = n(connection.execute(f"SELECT count(*) FROM canonical_companies WHERE trim(COALESCE(provenance_url,''))<>'' AND company_id IN {active_ids}").fetchall()[0][0])
        active_profiles = n(connection.execute(f"SELECT count(*) FROM canonical_company_profiles WHERE company_id IN {active_ids}").fetchall()[0][0])
        active_logo_source = n(connection.execute(f"SELECT count(*) FROM canonical_company_profiles WHERE trim(COALESCE(logo_source_url,''))<>'' AND company_id IN {active_ids}").fetchall()[0][0])
        active_verified_logo = n(connection.execute(f"SELECT count(*) FROM canonical_company_profiles WHERE trim(COALESCE(logo_verified_at,''))<>'' AND company_id IN {active_ids}").fetchall()[0][0])
        # Add the active-job company set before the profile LEFT JOIN.
        active_query = query.replace("FROM canonical_companies c\n          LEFT JOIN", "FROM canonical_companies c\n          JOIN (SELECT DISTINCT company_id FROM canonical_jobs WHERE lifecycle_state='active') aj ON aj.company_id=c.company_id\n          LEFT JOIN")
        active_values = connection.execute(active_query).fetchall()[0]
        active_counts = {
            "Canonical company ID": active_total,
            "Company name": n(active_values[1]),
            "Selected primary URL": active_selected,
            "Provenance URL": active_provenance,
            "Company profile": active_profiles,
            "Company website URL": n(active_values[2]),
            "Domain": n(active_values[3]),
            "LinkedIn company URL": n(active_values[4]),
            "LinkedIn company ID": n(active_values[5]),
            "CompanyEnrich ID": n(active_values[6]),
            "Industry": n(active_values[7]),
            "Company size": n(active_values[8]),
            "Headquarters": n(active_values[9]),
            "Founded year": n(active_values[10]),
            "Company type": n(active_values[11]),
            "Revenue range": n(active_values[12]),
            "Description": n(active_values[13]),
            "Logo source URL": active_logo_source,
            "Verified logo": active_verified_logo,
        }
        report = {"generated_at": datetime.now(timezone.utc).isoformat(), "all_companies": [{"field": k, "populated": v, "total": total, "percentage": round(v * 100 / total, 2) if total else 0.0} for k, v in counts.items()], "active_job_companies": [{"field": k, "populated": v, "total": active_total, "percentage": round(v * 100 / active_total, 2) if active_total else 0.0} for k, v in active_counts.items()], "counts": counts, "active_job_counts": active_counts}
        report_version = os.environ.get("COMPANY_ENRICH_API_VERSION", "latest").strip() or "latest"
        if report_version != "latest" and not report_version.startswith("v"):
            report_version = "v" + report_version
        path = audit_dir / f"live_completeness_{report_version}.json"
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        print("lifecycle_states", [[row[0], row[1]] for row in connection.execute("SELECT lifecycle_state,count(*) FROM canonical_jobs GROUP BY lifecycle_state").fetchall()])
        print("job_company_counts", [[row[0], row[1]] for row in connection.execute("SELECT lifecycle_state,count(DISTINCT company_id) FROM canonical_jobs GROUP BY lifecycle_state").fetchall()])
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
