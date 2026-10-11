"""Generate a deterministic, schema-faithful sample of canonical job records.

This sample is *synthetic*.  It exists because the checkout does not contain
production master-job data (job_source_observations / canonical_jobs).  It is
shaped exactly like the normalized canonical-job records produced by
``backend.acquisition.quality.normalize_job_for_ingestion`` so the offline
audit exercises the same code path a production export would.

Company identity values are drawn from the real canonical company registry
(``data/acquisition/inputs/company_registry_canonical.csv``) so company-coverage
counts are meaningful, but job titles/descriptions/URLs are fabricated.

Deterministic: a fixed seed produces identical output every run.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

REAL_TITLES = [
    "Software Engineer (Backend)",
    "Senior Data Analyst",
    "Product Manager",
    "Sales Development Representative",
    "HR Generalist",
    "Financial Controller",
    "Logistics Coordinator",
    "Mechanical Design Engineer",
    "Customer Success Manager",
    "Electrician (Industrial)",
]

PLACEHOLDER_TITLES = ["", "", "", "{{job_title}}", "TBD", "Position", "n/a"]

DESCRIPTIONS = [
    (
        "We are looking for a motivated engineer to join our team and build "
        "scalable systems. You will design, implement, and operate backend "
        "services, collaborate with product and data teams, and take ownership "
        "of features from ideation to production. Strong communication and a "
        "bias for action are essential."
    ),
    (
        "In this role you will support daily operations, coordinate logistics, "
        "and improve processes across the supply chain. You will work closely "
        "with internal stakeholders and external partners to ensure on-time "
        "delivery and high quality standards."
    ),
    (
        "You will own the roadmap for a core product area, translate customer "
        "needs into requirements, and partner with engineering and design to "
        "ship features. You will measure outcomes and iterate based on data."
    ),
]

SHORT_DESCRIPTION = "See website for details."
PLACEHOLDER_DESCRIPTION = "{{job_description}}"
BLOCKED_DESCRIPTION = "Attention required. Please verify you are human to continue."

TRACKING_URLS = [
    "https://lnkd.in/abc123",
    "https://bit.ly/xyz789",
]
LISTING_URLS = [
    "https://www.example-careers.com/jobs",
    "https://www.example-careers.com/careers",
]


def _load_companies(registry_path: Path, limit: int) -> list[dict[str, str]]:
    rows = list(csv.DictReader(registry_path.read_text(encoding="utf-8-sig").splitlines()))
    companies: list[dict[str, str]] = []
    for row in rows:
        canonical_id = str(row.get("canonical_CompanyID") or "").strip()
        name = str(row.get("company_name") or "").strip()
        if canonical_id and name:
            companies.append({"canonical_company_id": canonical_id, "company_name": name})
        if len(companies) >= limit:
            break
    return companies


def _record(
    index: int,
    rng: random.Random,
    companies: list[dict[str, str]],
    *,
    now_iso: str,
    stale_after_days: int,
) -> dict[str, Any]:
    company = rng.choice(companies) if companies else {"canonical_company_id": f"canonical-{index:08x}", "company_name": "Example GmbH"}
    source = rng.choices(["employer_site", "linkedin"], weights=[60, 40])[0]

    canonical_job_id = f"job-{index:08x}"
    missing_company_id = rng.random() < 0.15
    unknown_company_id = rng.random() < 0.05
    company_id = "" if missing_company_id else (f"canonical-unknown-{index:08x}" if unknown_company_id else company["canonical_company_id"])

    title = rng.choices(
        [rng.choice(REAL_TITLES), rng.choice(PLACEHOLDER_TITLES)], weights=[90, 10]
    )[0]

    description_roll = rng.random()
    if description_roll < 0.20:
        description = ""
    elif description_roll < 0.28:
        description = PLACEHOLDER_DESCRIPTION
    elif description_roll < 0.33:
        description = BLOCKED_DESCRIPTION
    elif description_roll < 0.50:
        description = SHORT_DESCRIPTION
    else:
        description = rng.choice(DESCRIPTIONS)

    location = "" if rng.random() < 0.15 else rng.choice(["Berlin", "Munich", "Hamburg", "Remote", "Frankfurt"])

    url_roll = rng.random()
    if url_roll < 0.15:
        apply_url = ""
        destination = ""
    elif url_roll < 0.25:
        apply_url = rng.choice(TRACKING_URLS)
        destination = "dedicated_apply"
    elif url_roll < 0.35:
        apply_url = rng.choice(LISTING_URLS)
        destination = "listing_fallback"
    else:
        apply_url = f"https://{company['company_name'].lower().replace(' ', '-')}.example-careers.com/jobs/{index}"
        destination = rng.choice(["dedicated_apply", "dedicated_apply", "job_detail_with_apply", "embedded_apply"])

    lifecycle = rng.choices(["active", "closed", "active"], weights=[85, 10, 5])[0]

    observed_at = now_iso
    if rng.random() < 0.10:
        # stale
        observed_at = (datetime.fromisoformat(now_iso.replace("Z", "+00:00")) - timedelta(days=stale_after_days + 30)).isoformat()

    posted_future = rng.random() < 0.02
    if posted_future:
        posted_at = (datetime.fromisoformat(now_iso.replace("Z", "+00:00")) + timedelta(days=5)).isoformat()
    else:
        posted_at = (datetime.fromisoformat(now_iso.replace("Z", "+00:00")) - timedelta(days=rng.randint(0, 20))).isoformat()

    record: dict[str, Any] = {
        "canonical_job_id": canonical_job_id,
        "canonical_company_id": company_id,
        "company_id": company_id,
        "company_name": company["company_name"],
        "title": title,
        "description_text": description,
        "location_raw": location,
        "source": source,
        "source_ats": source,
        "source_job_id": f"{source}-{index}",
        "external_job_id": f"{source}-{index}",
        "observed_at": observed_at,
        "lifecycle_state": lifecycle,
        "apply_url": apply_url,
        "application_url": apply_url,
        "application_destination": {"destination_type": destination, "resolved_url": apply_url, "classification": destination},
        "source_timestamps": {
            "fields": {
                "source_posted_at": {"value": posted_at},
            }
        },
        "posted_at": posted_at,
        "is_live": rng.random() < 0.70,
        "publication_state": "published" if rng.random() < 0.70 else "unpublished",
    }
    if lifecycle == "closed":
        record["closed_at"] = posted_at
    return record


def generate_sample(
    registry_path: Path,
    *,
    count: int = 300,
    seed: int = 20260812,
    now_iso: str = "",
    stale_after_days: int = 90,
    company_limit: int = 200,
) -> list[dict[str, Any]]:
    now = now_iso or datetime.now(timezone.utc).isoformat()
    rng = random.Random(seed)
    companies = _load_companies(registry_path, company_limit)
    return [
        _record(index, rng, companies, now_iso=now, stale_after_days=stale_after_days)
        for index in range(count)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a schema-faithful canonical job sample.")
    parser.add_argument("--registry", type=Path, default=PROJECT_ROOT / "data" / "acquisition" / "inputs" / "company_registry_canonical.csv")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "audit" / "master_jobs_sample.jsonl")
    parser.add_argument("--count", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--now", default="")
    parser.add_argument("--stale-after-days", type=int, default=90)
    args = parser.parse_args(argv)

    sample = generate_sample(
        args.registry,
        count=args.count,
        seed=args.seed,
        now_iso=args.now,
        stale_after_days=args.stale_after_days,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in sample:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Wrote {len(sample)} records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
