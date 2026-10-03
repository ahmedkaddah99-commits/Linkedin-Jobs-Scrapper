"""Read-only deployed-validator audit and existing-data reconciliation.

Runs read-only queries on the VPS with its deployed Python and validator.
Only local audit artifacts are written; no provider calls or catalog updates.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def clean(value):
    return "" if str(value or "").strip().casefold() in {"", "//", "unknown", "null", "none", "n/a", "-"} else str(value).strip()


def host(value):
    try:
        return (urlsplit(value if "://" in value else "https://" + value).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def remote_audit():
    import os
    import sqlite3
    import hashlib
    sys.path.insert(0, "/opt/runr")
    for path in ("/opt/runr/.env.acquisition", "/etc/runr/acquisition-catalog.env"):
        for line in Path(path).read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip().strip('"').strip("'")
    from backend.database.connection import connect_database
    from backend.acquisition.job_publication_completeness import validate_job_for_publication, REQUIRED_FIELDS
    from backend.application.company_identity_canonicalization import resolve_company_id
    crosswalk_path = os.environ.get("RUNR_COMPANY_IDENTITY_CROSSWALK", "/srv/runr/state/active/company_identity_crosswalk.json")
    crosswalk_doc = json.loads(Path(crosswalk_path).read_text()) if Path(crosswalk_path).exists() else {}
    crosswalk_map = crosswalk_doc.get("mapping_by_identity", {})
    if not os.environ.get("TURSO_DATABASE_URL"):
        raise RuntimeError("Live remote catalog is required")
    conn = connect_database(Path("/nonexistent/read_only_audit.sqlite3"))
    def rows(sql, params=()):
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    def decode(value):
        try:
            data = json.loads(value or "{}")
            return data if isinstance(data, dict) else {}
        except (ValueError, TypeError):
            return {}
    companies = rows("SELECT company_id,canonical_name,provenance_url FROM canonical_companies")
    ids = {c["company_id"] for c in companies}
    profiles = {r["company_id"]: r for r in rows("SELECT * FROM canonical_company_profiles")}
    urls = rows("SELECT * FROM canonical_company_urls")
    by_url = defaultdict(list)
    for row in urls:
        by_url[row["company_id"]].append(row)
    head = rows("SELECT * FROM acquisition_publication_head WHERE head_id=1")[0]
    publication = rows("SELECT policy_version,status FROM acquisition_publications WHERE publication_id=?", (head["publication_id"],))[0]
    from backend.acquisition.publication import get_publication_policy
    policy = get_publication_policy(publication["policy_version"])
    head.update(publication)
    head["require_application_destination"] = policy.missing_apply_is_blocker
    head_ids = {r["canonical_job_id"] for r in rows("SELECT canonical_job_id FROM acquisition_publication_jobs WHERE publication_id=?", (head["publication_id"],))}
    jobs = rows("""SELECT j.*,c.canonical_name AS company,v.description AS version_description,
        v.location AS version_location,v.apply_url,v.payload_json AS version_payload_json,
        o.external_job_id AS source_job_id,o.source_ats,o.observed_at AS observation_observed_at
        FROM canonical_jobs j LEFT JOIN canonical_companies c ON c.company_id=j.company_id
        LEFT JOIN job_posting_versions v ON v.version_id=j.current_version_id
        LEFT JOIN job_source_observations o ON o.observation_id=v.source_observation_id""")
    evaluated = []
    for row in jobs:
        record = {**decode(row.get("version_payload_json")),
            "canonical_job_id": row["canonical_job_id"], "canonical_company_id": row["company_id"],
            "company": row.get("company"), "title": row.get("title"),
            "location": row.get("version_location") or row.get("location"),
            "location_raw": row.get("version_location") or row.get("location"),
            "description": row.get("version_description"), "description_text": row.get("version_description"),
            "full_description": row.get("version_description"), "apply_url": row.get("apply_url"),
            "application_url": row.get("apply_url"), "source_job_id": row.get("source_job_id"),
            "source": row.get("source_ats"), "source_ats": row.get("source_ats"),
            "observed_at": row.get("observation_observed_at"), "last_seen_at": row.get("last_seen_at"),
            "last_verified_at": row.get("last_verified_at"), "lifecycle_state": row.get("lifecycle_state")}
        result = validate_job_for_publication(record, company_registry={str(row["company_id"] or "")}, require_application_destination=policy.missing_apply_is_blocker)
        strict_result = validate_job_for_publication(record, company_registry={str(row["company_id"] or "")}, require_application_destination=True)
        evaluated.append({"job_id": row["canonical_job_id"], "company_id": row["company_id"],
            "in_head": row["canonical_job_id"] in head_ids, "lifecycle": row.get("lifecycle_state"),
            "publishable": result.publishable, "reasons": list(result.reason_codes),
            "direct_apply_publishable": strict_result.publishable, "direct_apply_reasons": list(strict_result.reason_codes)})
    def metrics(items):
        blocked = [r for r in items if not r["publishable"]]
        return {"jobs": len(items), "publishable": sum(r["publishable"] for r in items),
            "blocked": len(blocked), "blocked_companies": len({r["company_id"] for r in blocked}),
            "reasons": dict(Counter(reason for r in blocked for reason in r["reasons"]))}
    catalog = {"head": head, "all": metrics(evaluated),
        "head_jobs": metrics([r for r in evaluated if r["in_head"]]),
        "active_not_head": metrics([r for r in evaluated if not r["in_head"] and r["lifecycle"] == "active"]),
        "strict_direct_apply": metrics([{**r, "publishable": r["direct_apply_publishable"], "reasons": r["direct_apply_reasons"]} for r in evaluated]),
        "blocked_jobs": [r for r in evaluated if not r["publishable"]]}
    rejections = rows("SELECT reason_code,COUNT(*) AS rows,COUNT(DISTINCT external_job_id) AS jobs FROM acquisition_job_rejections GROUP BY reason_code")
    boards = defaultdict(set)
    source_summary = {}
    for source, default_path, query in (
        ("linkedin", "/srv/runr/state/linkedin/master_linkedin_jobs_state.db", "SELECT linkedin_job_id AS source_id,row_json AS payload FROM job_company_observations"),
        ("employer", "/srv/runr/state/employer/master_employer_jobs_state.db", "SELECT source_key AS source_id,payload_json AS payload FROM jobs")):
        state_path = os.environ.get("RUNR_LINKEDIN_STATE_DB" if source == "linkedin" else "RUNR_EMPLOYER_STATE_DB", default_path)
        db = sqlite3.connect(f"file:{state_path}?mode=ro", uri=True)
        entries = []
        source_query = query + " LIMIT 2000" if source == "linkedin" else query
        for source_id, raw in db.execute(source_query):
            p = decode(raw)
            cid = clean(resolve_company_id(p, crosswalk_map)) or clean(p.get("canonical_company_id"))
            if source == "employer":
                for key in ("career_target_url", "source_site_url"):
                    if clean(p.get(key)) and cid:
                        boards[cid].add(clean(p[key]))
            rec = {**p, "canonical_job_id": f"{source}:{source_id}", "canonical_company_id": cid,
                "company_name": p.get("source_company_name") or p.get("observed_company_name"),
                "title": p.get("job_title") or p.get("title_raw"),
                "description_text": p.get("description_text") or p.get("description"),
                "location_raw": p.get("location") or p.get("location_raw"),
                "apply_url": p.get("apply_url_canonical") or p.get("apply_url_raw") or (p.get("source_job_url") if source == "employer" else ""),
                "source": "linkedin" if source == "linkedin" else "employer_site",
                "source_ats": p.get("source_provider") or source, "source_job_id": str(source_id),
                "observed_at": p.get("last_seen_at") or p.get("detail_last_refreshed_at") or p.get("first_seen_at"),
                "lifecycle_state": p.get("lifecycle_status") if source == "linkedin" else ("active" if p.get("collection_status", "accepted") in {"accepted", "active"} else p.get("collection_status")),
                "posted_at": p.get("posted_at_estimated") or p.get("date_posted")}
            if len(entries) < 2000:
                result = validate_job_for_publication(rec, company_registry=ids)
                entries.append({"job_id": str(source_id), "company_id": cid, "publishable": result.publishable, "reasons": list(result.reason_codes)})
        source_summary[source] = {"state_path": state_path, "stored_rows": db.execute("SELECT COUNT(*) FROM " + ("job_company_observations" if source == "linkedin" else "jobs")).fetchone()[0],
            "first_2000_sample_only": metrics(entries)}
        if source == "employer":
            source_summary[source]["company_statuses"] = dict(db.execute("SELECT status,COUNT(*) FROM companies GROUP BY status"))
        db.close()
    reusable = []
    for c in companies:
        cid = c["company_id"]
        p = profiles.get(cid, {})
        data = decode(p.get("profile_json"))
        def field(name):
            for section in ("fields", "additional_fields"):
                item = data.get(section, {}).get(name)
                if isinstance(item, dict) and clean(item.get("value")):
                    return clean(item["value"])
            return ""
        selected = [u["url"] for u in by_url[cid] if u.get("url_type") == "homepage" and u.get("selected_primary")]
        homes = [u["url"] for u in by_url[cid] if u.get("url_type") == "homepage"]
        careers = [u["url"] for u in by_url[cid] if u.get("url_type") in {"career", "careers", "jobs", "job_board", "ats", "ats_jobs"}]
        reusable.append({"company_id": cid, "name": c["canonical_name"], "website": field("website"),
            "domain": field("domain"), "selected": selected, "homepages": homes,
            "catalog_careers": careers, "producer_boards": sorted(boards[cid]),
            "fields": {k: field(k) for k in ("linkedin_company_id", "industry", "company_size", "headquarters", "founded_year", "description", "company_type", "revenue_range")},
            "logo": clean(p.get("logo_source_url"))})
    conn.close()
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "required_fields": list(REQUIRED_FIELDS),
        "validator_sha256": hashlib.sha256(Path('/opt/runr/backend/acquisition/job_publication_completeness.py').read_bytes()).hexdigest(),
        "catalog": catalog, "historical_rejections": rejections, "producer_states": source_summary,
        "url_types": dict(Counter(u.get("url_type") for u in urls)), "companies": reusable}


def main():
    if "--remote" in sys.argv:
        print(json.dumps(remote_audit(), separators=(",", ":")))
        return
    result = subprocess.run(["ssh", "runr-vps", "sudo /opt/runr/.venv/bin/python - --remote"],
        input=Path(__file__).read_bytes(), capture_output=True, timeout=300)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace")[-2000:])
    report = json.loads(result.stdout)
    from backend.application.company_identity_canonicalization import build_company_crosswalk
    source_path = ROOT / "data/acquisition/inputs/company_sources_linkedin_ids.csv"
    source = list(csv.DictReader(source_path.open(encoding="utf-8-sig")))
    crosswalk = build_company_crosswalk(source)
    restored = defaultdict(list)
    for i, row in enumerate(source):
        restored[crosswalk.mapping_by_row[i]].append(row)
    restored_ids = set(restored)
    counts = Counter()
    queue = []
    for c in report["companies"]:
        cid = c["company_id"]
        offers = {}
        conflicts = []
        homes = set(filter(None, c["homepages"]))
        source_homes = {clean(r.get("website_url")) for r in restored[cid]} - {""}
        if not c["website"] and (homes or source_homes):
            offers["website"] = sorted(homes | source_homes)
            counts["missing_profile_website_with_existing_candidate"] += 1
        if not c["selected"] and (c["website"] or homes or source_homes):
            offers["selected_homepage"] = sorted(homes | source_homes | ({c["website"]} if c["website"] else set()))
            counts["missing_selected_homepage_with_existing_candidate"] += 1
        if not c["domain"] and (c["website"] or homes or source_homes):
            offers["domain"] = sorted({host(u) for u in homes | source_homes | ({c["website"]} if c["website"] else set())} - {""})
            counts["missing_domain_with_existing_candidate"] += 1
        if c["website"] and c["selected"] and host(c["website"]) not in {host(u) for u in c["selected"]}:
            conflicts.append("profile_vs_selected_hostname")
            counts["profile_selected_hostname_conflicts"] += 1
        if len({host(u) for u in homes | source_homes | ({c["website"]} if c["website"] else set())} - {""}) > 1:
            counts["multiple_existing_homepage_hostnames"] += 1
        for field_name, source_names in {"linkedin_company_id": ("linkedin_company_id",), "industry": ("industry",),
            "company_size": ("employee_count_range", "employee_count"), "headquarters": ("headquarters_display",),
            "founded_year": ("founded_year",), "description": ("description",), "company_type": ("company_type",),
            "revenue_range": ("revenue_range",)}.items():
            values = sorted({clean(r.get(k)) for r in restored[cid] for k in source_names} - {""})
            if not c["fields"][field_name] and values:
                offers[field_name] = values
                counts["restored_missing_" + field_name] += 1
        if not c["logo"]:
            values = sorted({clean(r.get(k)) for r in restored[cid] for k in ("logo_url", "companyenrich_free_logo_url")} - {""})
            if values:
                offers["logo"] = values
                counts["restored_missing_logo"] += 1
        if c["producer_boards"]:
            counts["companies_with_producer_board_evidence"] += 1
            if not c["catalog_careers"]:
                offers["career_board_evidence"] = c["producer_boards"]
                counts["producer_board_evidence_missing_catalog_career"] += 1
        if c["catalog_careers"]:
            counts["companies_with_catalog_career_urls"] += 1
        if offers or conflicts:
            queue.append({"company_id": cid, "name": c["name"], "offers": offers, "conflicts": conflicts})
    report["reuse"] = {"counts": dict(counts), "restored_source_rows": len(source),
        "restored_mapped_live_companies": len({c['company_id'] for c in report['companies']} & restored_ids),
        "queue_companies": len(queue), "database_writes": 0, "provider_calls": 0}
    out = ROOT / "data/audit/publication_reuse_2026-09-28"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "reconciliation_queue.json").write_text(json.dumps(queue, indent=2), encoding="utf-8")
    summary = {k: v for k, v in report.items() if k != "companies"}
    summary["catalog"] = {k: v for k, v in summary["catalog"].items() if k != "blocked_jobs"}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
