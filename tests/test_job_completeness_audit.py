"""Tests for the offline publication-completeness audit."""

from __future__ import annotations

from datetime import datetime, timezone

from scripts.audit_job_publication_completeness import run_audit

NOW = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
REGISTRY = {"canonical-acme", "canonical-beta"}


def _complete(canonical_job_id: str, **overrides) -> dict:
    record = {
        "canonical_job_id": canonical_job_id,
        "canonical_company_id": "canonical-acme",
        "company_name": "ACME GmbH",
        "title": "Backend Software Engineer",
        "description_text": (
            "You will design, implement, and operate backend services in a "
            "cross-functional team, taking ownership of features end to end and "
            "collaborating closely with product and data teams."
        ),
        "location_raw": "Berlin",
        "source": "employer_site",
        "source_ats": "employer_site",
        "source_job_id": canonical_job_id,
        "observed_at": "2026-09-09T00:00:00Z",
        "lifecycle_state": "active",
        "seniority": "mid",
        "employment_type": "full_time",
        "workplace_arrangement": "hybrid",
        "company_logo": "https://acme.example/logo.png",
        "company_enrichment": "verified",
        "apply_url": "https://acme.example-careers.com/jobs/1/apply",
        "application_url": "https://acme.example-careers.com/jobs/1/apply",
        "application_destination": {
            "destination_type": "dedicated_apply",
            "resolved_url": "https://acme.example-careers.com/jobs/1/apply",
        },
    }
    record.update(overrides)
    return record


def test_audit_reconciles_exactly():
    records = [
        _complete("job-1"),
        _complete("job-2", description_text=""),
        _complete("job-3", title=""),
        _complete("job-4", canonical_company_id="canonical-ghost"),
        _complete("job-1"),  # duplicate identity
    ]
    report = run_audit(records, company_registry=REGISTRY, now=NOW)
    reconciliation = report["reconciliation"]
    assert reconciliation["input_records"] == 5
    assert reconciliation["unique_canonical_jobs"] == 4
    assert reconciliation["duplicate_identity_records_skipped"] == 1
    assert reconciliation["unique_plus_duplicates_equals_input"] is True
    assert reconciliation["outcome_total_equals_unique"] is True
    assert sum(report["outcome_counts"].values()) == 4


def test_audit_counts_published_that_would_fail():
    records = [
        _complete("job-ok", is_live=True, publication_state="published"),
        _complete("job-bad", description_text="", is_live=True, publication_state="published"),
    ]
    report = run_audit(records, company_registry=REGISTRY, now=NOW)
    assert report["published_that_would_fail"]["count"] == 1
    assert report["published_that_would_fail"]["canonical_job_ids"] == ["job-bad"]


def test_audit_company_coverage_counts_distinct_companies():
    records = [
        _complete("job-1"),
        _complete("job-2"),
        _complete("job-3", canonical_company_id="canonical-beta", company_name="Beta GmbH"),
    ]
    report = run_audit(records, company_registry=REGISTRY, now=NOW)
    coverage = report["company_coverage"]
    assert coverage["publishable_jobs"] == 3
    assert coverage["distinct_publishable_companies"] == 2


def test_audit_counts_missing_company_identity():
    records = [
        _complete("job-1"),
        _complete("job-2", canonical_company_id=""),
    ]
    report = run_audit(records, company_registry=REGISTRY, now=NOW)
    assert report["missing_canonical_company_identity"] == 1


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
