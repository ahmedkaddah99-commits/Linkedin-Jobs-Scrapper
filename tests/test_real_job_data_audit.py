"""Tests for the real-data audit field mapping and reconciliation.

These tests use small in-memory SQLite fixtures shaped like the producer
state, so they do not depend on the external snapshot paths.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from scripts.audit_real_job_data import (
    _employer_record,
    _linkedin_record,
    _source_metrics,
    run_real_audit,
)

NOW = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)


def _linkedin_json(**overrides) -> str:
    payload = {
        "canonical_company_id": "//",
        "source_company_name": "Deutsche Bank",
        "job_title": "Fintech Specialist (d/m/w)",
        "description": (
            "Implement reporting solutions across the private bank, working "
            "closely with stakeholders to deliver accurate, timely results."
        ),
        "location": "Munich, Bavaria, Germany",
        "workplace_type": "",
        "apply_url_canonical": "https://www.linkedin.com/jobs/view/4313287713",
        "last_seen_at": "2026-09-02T00:38:36Z",
        "lifecycle_status": "active",
        "posted_at_estimated": "2026-02-01",
        "ownership_status": "EXACT_PRIMARY_MATCH",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_linkedin_mapping_preserves_source_identity_and_sentinel():
    record = _linkedin_record("4313287713", _linkedin_json())
    assert record["source_job_id"] == "4313287713"
    assert record["canonical_job_id"] == "linkedin:4313287713"
    assert record["identity_mode"] == "source_derived"
    assert record["canonical_company_id"] == "//"  # preserved verbatim; validator treats as missing
    assert record["source"] == "linkedin"
    assert record["title"] == "Fintech Specialist (d/m/w)"


def test_employer_mapping_uses_source_job_url_as_apply_fallback():
    record = _employer_record(
        "n26-8144130",
        json.dumps({
            "canonical_company_id": "canonical-dc12c8131b127a83",
            "source_company_name": "n26 group",
            "job_title": "AFC Intern",
            "description_text": "<p>About the opportunity</p>",
            "location": "Madrid",
            "source_job_id": "https://n26.com/en-eu/careers/positions/8144130",
            "source_job_url": "https://n26.com/en-eu/careers/positions/8144130",
            "apply_url_canonical": "",
            "last_seen_at": "2026-08-31T16:24:10Z",
            "collection_status": "accepted",
            "date_posted": "2026-08-26T04:35:07-04:00",
        }),
    )
    assert record["source"] == "employer_site"
    assert record["apply_url"] == "https://n26.com/en-eu/careers/positions/8144130"


def test_source_metrics_use_sentinel_detection():
    records = [
        {"canonical_company_id": "//", "description_text": "x", "apply_url": "u", "location_raw": "l"},
        {"canonical_company_id": "canonical-x", "description_text": "", "apply_url": "", "location_raw": ""},
    ]
    metrics = _source_metrics(records)
    assert metrics["missing_canonical_company_id"] == 1  # '//' is missing, not the empty-string check
    assert metrics["missing_description"] == 1
    assert metrics["missing_application_url"] == 1
    assert metrics["missing_location"] == 1


def test_real_audit_reconciles_outcomes_to_records(tmp_path: Path):
    linkedin_db = tmp_path / "linkedin.db"
    conn = sqlite3.connect(linkedin_db)
    conn.execute("CREATE TABLE job_company_observations (linkedin_company_id TEXT, linkedin_job_id TEXT PRIMARY KEY, run_id TEXT, company_scan_id TEXT, ownership_status TEXT, first_seen_at TEXT, last_seen_at TEXT, row_json TEXT)")
    conn.execute(
        "INSERT INTO job_company_observations VALUES (?,?,?,?,?,?,?,?)",
        ("1262", "1", "run", "", "EXACT_PRIMARY_MATCH", "2026-08-31T00:00:00Z", "2026-09-02T00:00:00Z", _linkedin_json()),
    )
    conn.execute(
        "INSERT INTO job_company_observations VALUES (?,?,?,?,?,?,?,?)",
        ("1262", "2", "run", "", "EXACT_PRIMARY_MATCH", "2026-08-31T00:00:00Z", "2026-09-02T00:00:00Z", _linkedin_json(canonical_company_id="canonical-acme")),
    )
    conn.commit()
    conn.close()

    employer_db = tmp_path / "employer.db"
    conn = sqlite3.connect(employer_db)
    conn.execute("CREATE TABLE jobs (source_key TEXT PRIMARY KEY, payload_json TEXT NOT NULL, updated_at TEXT NOT NULL)")
    conn.execute("INSERT INTO jobs VALUES ('k1', '{\"source_job_id\":\"u1\",\"source_job_url\":\"u1\",\"job_title\":\"t\",\"description_text\":\"d\",\"location\":\"l\",\"canonical_company_id\":\"//\",\"collection_status\":\"accepted\",\"last_seen_at\":\"2026-08-31T00:00:00Z\"}', 'x')")
    conn.commit()
    conn.close()

    report = run_real_audit(
        linkedin_state=linkedin_db,
        employer_state=employer_db,
        company_registry={"canonical-acme"},
        now=NOW,
    )
    assert report["reconciliation"]["linkedin_outcome_total_equals_records"] is True
    assert report["reconciliation"]["employer_outcome_total_equals_records"] is True
    assert report["linkedin"]["total"] == 2
    assert report["linkedin"]["publishable"] == 1  # only the one with a known company id
    assert report["employer"]["total"] == 1
    assert report["employer"]["publishable"] == 0  # '//' company id → unresolved


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
