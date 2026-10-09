"""Audit logo and domain coverage for live companies never sent to CompanyEnrich."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.database.connection import connect_database
from scripts.import_restored_company_profiles import load_env
from scripts.run_companyenrich_v16_resume import AUDIT


def value(profile: dict, field: str) -> str:
    for group in ("fields", "additional_fields"):
        part = profile.get(group)
        if isinstance(part, dict):
            item = part.get(field)
            if isinstance(item, dict) and item.get("value"):
                return str(item["value"]).strip()
    return ""


def domain(text: str) -> str:
    try:
        host = urlsplit(text if "://" in text else "https://" + text).hostname or ""
    except ValueError:
        return ""
    host = host.casefold().removeprefix("www.").rstrip(".")
    return host if "." in host and "@" not in host else ""


def main() -> int:
    load_env(ROOT / "user_config/.env")
    attempted = set()
    for path in sorted(AUDIT.glob("provider_results_*.jsonl")) + [AUDIT / "provider_result_recovered_interruption.jsonl"]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                event = json.loads(line)
            except (TypeError, ValueError):
                continue
            if event.get("company_id") and event.get("event") in {"attempting", "result", "failed", "ambiguous_timeout", "rate_limited"}:
                attempted.add(str(event["company_id"]))
    connection = connect_database(AUDIT / "remote_probe.sqlite3")
    counts = Counter()
    hosts = Counter()
    candidates = []
    try:
        company_rows = connection.execute("SELECT c.company_id,c.canonical_name FROM canonical_companies c LEFT JOIN canonical_company_profiles p ON p.company_id=c.company_id WHERE trim(COALESCE(json_extract(p.profile_json,'$.fields.companyenrich_id.value'),json_extract(p.profile_json,'$.additional_fields.companyenrich_id.value'),''))='' ORDER BY c.company_id").fetchall()
        target_ids = [str(row[0]) for row in company_rows if str(row[0]) not in attempted]
        names = {str(row[0]): str(row[1] or "") for row in company_rows}
        counts["target_companies"] = len(target_ids)
        for start in range(0, len(target_ids), 250):
            batch = target_ids[start:start+250]
            placeholders = ",".join("?" for _ in batch)
            rows = connection.execute(f"SELECT company_id,profile_json,logo_source_url,logo_object_key,logo_verified_at FROM canonical_company_profiles WHERE company_id IN ({placeholders})", tuple(batch)).fetchall()
            profiles = {str(row[0]): row for row in rows}
            url_rows = connection.execute(f"SELECT company_id,url FROM canonical_company_urls WHERE url_type='homepage' AND selected_primary=1 AND company_id IN ({placeholders})", tuple(batch)).fetchall()
            homepages = {str(row[0]): str(row[1] or "") for row in url_rows}
            for cid in batch:
                row = profiles.get(cid)
                profile = json.loads(str(row[1] or "{}")) if row else {}
                source_url = str(row[2] or "").strip() if row else ""
                object_key = str(row[3] or "").strip() if row else ""
                verified_at = str(row[4] or "").strip() if row else ""
                field_logo = value(profile, "logo")
                any_logo = bool(source_url or object_key or field_logo)
                if any_logo:
                    counts["has_any_logo_reference"] += 1
                if source_url:
                    counts["has_logo_source_url"] += 1
                    host = domain(source_url)
                    if host.endswith("linkedin.com") or host.endswith("licdn.com"):
                        counts["linkedin_logo"] += 1
                    elif "companyenrich.com" in host:
                        counts["companyenrich_logo"] += 1
                    else:
                        counts["other_logo"] += 1
                    hosts[host] += 1
                if field_logo and not source_url:
                    counts["logo_field_only"] += 1
                if object_key:
                    counts["cached_logo_object"] += 1
                if verified_at:
                    counts["verified_logo"] += 1
                candidate_domain = domain(value(profile, "domain") or value(profile, "website") or homepages.get(cid, ""))
                if candidate_domain:
                    counts["has_lookup_domain"] += 1
                    if not any_logo:
                        counts["missing_logo_with_domain"] += 1
                elif not any_logo:
                    counts["missing_logo_no_domain"] += 1
                candidates.append({"company_id": cid, "name": names[cid], "domain": candidate_domain, "logo_source_url": source_url, "logo_field": field_logo, "logo_object_key": object_key, "logo_verified_at": verified_at})
        report = {"counts": dict(counts), "top_existing_logo_hosts": hosts.most_common(20), "samples_missing_with_domain": [r for r in candidates if not (r["logo_source_url"] or r["logo_field"] or r["logo_object_key"]) and r["domain"]][:20]}
        (AUDIT / "unattempted_company_logo_baseline.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (AUDIT / "unattempted_company_logo_candidates.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in candidates), encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
