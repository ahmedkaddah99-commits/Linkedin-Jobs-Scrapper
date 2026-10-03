"""Create a disposable, published Jobs API fixture for RC-030 browser checks."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend import create_backend
from backend.domain.models import utc_now_iso


def seed(data_dir: Path) -> dict[str, str]:
    os.environ.update(
        {
            "RUNR_ENV": "development",
            "RUNR_TEST_MODE": "1",
            "DATABASE_BACKEND": "sqlite",
            "TURSO_DATABASE_URL": "",
            "TURSO_AUTH_TOKEN": "",
            "OBJECT_STORAGE_BACKEND": "local",
            "OBJECT_STORAGE_LOCAL_ROOT": "",
            "RUNR_ACQUISITION_LIVE_NETWORK_ENABLED": "false",
        }
    )
    app = create_backend(data_dir, storage_backend="sqlite", test_mode=True)
    store = app.repositories.acquisition_store
    now = utc_now_iso()

    def write(connection):
        companies = (
            ("company-acme", "Acme Labs", "https://acme.example"),
            ("company-beta", "Beta Systems", "https://beta.example"),
        )
        for company_id, name, website in companies:
            connection.execute(
                "INSERT INTO canonical_companies VALUES (?, ?, ?, ?, ?, ?)",
                (company_id, name, "employer", website, now, now),
            )
        jobs = (
            (
                "job-a",
                "company-acme",
                "Operations Analyst",
                "Berlin",
                "https://boards.greenhouse.io/acme/jobs/a",
                "operations",
                "remote",
            ),
            (
                "job-b",
                "company-beta",
                "Finance Analyst",
                "Munich",
                "https://jobs.lever.co/beta/b",
                "finance",
                "onsite",
            ),
        )
        for job_id, company_id, title, location, apply_url, category, arrangement in jobs:
            version_id = f"version-{job_id}"
            description = f"{category} role with reporting and cross-functional coordination."
            payload = {
                "title": title,
                "location": location,
                "description": description,
                "category": category,
                "work_arrangement": arrangement,
                "employment_type": "full_time",
                "experience_level": "entry",
                "salary": {"min": 50000, "max": 70000, "currency": "EUR"},
                "languages": ["German"],
                "application_destination": {
                    "destination_type": "dedicated_apply",
                    "classification": "employer_application",
                    "resolved_url": apply_url,
                    "user_facing_url": apply_url,
                    "job_detail_url": apply_url,
                    "status": "verified",
                    "application_method": "external_ats",
                    "is_actionable": True,
                    "warnings": [],
                },
            }
            connection.execute(
                """
                INSERT INTO canonical_jobs (
                    canonical_job_id, company_id, identity_key, title, location, canonical_url,
                    lifecycle_state, first_seen_at, last_seen_at, last_verified_at,
                    absence_count, current_version_id, created_at, updated_at, identity_signature
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    company_id,
                    f"url:{job_id}",
                    title,
                    location,
                    apply_url,
                    "active",
                    now,
                    now,
                    now,
                    0,
                    version_id,
                    now,
                    now,
                    f"signature:{job_id}",
                ),
            )
            connection.execute(
                "INSERT INTO job_posting_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    version_id,
                    job_id,
                    1,
                    f"hash-{job_id}",
                    title,
                    description,
                    location,
                    apply_url,
                    f"observation-{job_id}",
                    json.dumps(payload),
                    now,
                ),
            )
        connection.execute(
            """
            INSERT INTO acquisition_publications (
                publication_id, cycle_id, status, snapshot_json, published_at,
                valid_until, previous_publication_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("publication-rc030", "cycle-rc030", "valid", "[]", now, "", ""),
        )
        connection.executemany(
            "INSERT INTO acquisition_publication_jobs VALUES (?, ?)",
            [("publication-rc030", "job-a"), ("publication-rc030", "job-b")],
        )
        connection.execute(
            "INSERT INTO acquisition_publication_head VALUES (?, ?, ?)",
            (1, "publication-rc030", now),
        )

    store._run_transaction(write)
    user = app.upsert_user(
        {
            "email": "rc030-user@local.invalid",
            "display_name": "RC030 local browser user",
            "role": "viewer",
        }
    )
    _, token = app.issue_api_token(user_id=user.user_id, name="rc030-local-browser")
    admin = app.upsert_user(
        {
            "email": "rc030-admin@local.invalid",
            "display_name": "RC030 local admin",
            "role": "admin",
        }
    )
    _, admin_token = app.issue_api_token(user_id=admin.user_id, name="rc030-local-admin")
    return {
        "api_token": token,
        "user_id": user.user_id,
        "admin_api_token": admin_token,
        "admin_user_id": admin.user_id,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: rc030_local_jobs_seed.py DATA_DIR")
    print(json.dumps(seed(Path(sys.argv[1]).resolve())))
