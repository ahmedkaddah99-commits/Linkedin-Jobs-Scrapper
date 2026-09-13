"""Read-only profiler for the company registry inputs used by job completeness auditing."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _is_placeholder_name(name: str) -> bool:
    lowered = name.lower()
    placeholders = {"unknown", "n/a", "na", "none", "null", "placeholder", "missing"}
    if lowered in placeholders:
        return True
    if len(name) <= 2:
        return True
    return False


def _read_rows(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig")
    return list(csv.DictReader(text.splitlines()))


def profile_company_csv(path: Path) -> dict[str, Any]:
    rows = _read_rows(path)
    total = len(rows)

    missing_canonical_id = sum(1 for r in rows if not _text(r.get("canonical_CompanyID")))
    missing_name = sum(1 for r in rows if not _text(r.get("company_name")))
    placeholder_names = sum(1 for r in rows if _is_placeholder_name(_text(r.get("company_name"))))
    missing_website = sum(1 for r in rows if not _text(r.get("website_url")))
    missing_linkedin = sum(1 for r in rows if not _text(r.get("linkedin_company_url")))
    missing_linkedin_id = sum(1 for r in rows if not _text(r.get("linkedin_company_id")))

    enrichment_statuses = Counter(_text(r.get("enrichment_status")) for r in rows)
    record_sources = Counter()
    for r in rows:
        sources = _text(r.get("record_sources"))
        if sources:
            try:
                parsed = json.loads(sources)
                if isinstance(parsed, list):
                    for s in parsed:
                        record_sources[s] += 1
                else:
                    record_sources[sources] += 1
            except json.JSONDecodeError:
                record_sources[sources] += 1
        else:
            record_sources["none"] += 1

    merge_basis = Counter(_text(r.get("merge_basis")) for r in rows)

    with_canonical = total - missing_canonical_id
    enrichment_succeeded = enrichment_statuses.get("succeeded", 0)
    return {
        "path": str(path),
        "total_rows": total,
        "missing_canonical_id": missing_canonical_id,
        "missing_name": missing_name,
        "placeholder_names": placeholder_names,
        "missing_website": missing_website,
        "missing_linkedin_url": missing_linkedin,
        "missing_linkedin_company_id": missing_linkedin_id,
        "with_canonical_id": with_canonical,
        "canonical_id_rate": round(with_canonical / total, 4) if total else 0.0,
        "enrichment_status_counts": dict(enrichment_statuses),
        "record_source_counts": dict(record_sources),
        "merge_basis_counts": dict(merge_basis),
    }


def profile_company_master_csv(path: Path) -> dict[str, Any]:
    rows = _read_rows(path)
    total = len(rows)

    missing_company_id = sum(1 for r in rows if not _text(r.get("company_id")))
    missing_company_name = sum(1 for r in rows if not _text(r.get("company")))
    missing_website = sum(1 for r in rows if not _text(r.get("website")) and not _text(r.get("website_url")))

    return {
        "path": str(path),
        "total_rows": total,
        "missing_company_id": missing_company_id,
        "missing_company_name": missing_company_name,
        "missing_website": missing_website,
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    registry_path = root / "data" / "acquisition" / "inputs" / "company_registry_canonical.csv"
    master_path = root / "data" / "acquisition" / "inputs" / "company_master.csv"

    registry_profile = profile_company_csv(registry_path)
    master_profile = profile_company_master_csv(master_path)

    print(json.dumps({"registry": registry_profile, "master": master_profile}, indent=2))
