"""Tests for deliberate source-merging rules in job completeness."""

from __future__ import annotations

from backend.acquisition.job_source_merging import (
    DECISION_AMBIGUOUS,
    DECISION_CONFLICT,
    DECISION_DISTINCT,
    DECISION_SAME,
    DECISION_SINGLE,
    merge_source_records,
)


def _record(**overrides) -> dict:
    record = {
        "canonical_job_id": "job-1",
        "canonical_company_id": "canonical-acme",
        "company_name": "ACME GmbH",
        "title": "Backend Software Engineer",
        "description_text": "Build scalable backend services and own features end to end.",
        "location_raw": "Berlin",
        "source": "employer_site",
        "source_job_id": "employer-1",
        "job_detail_url": "https://acme.example-careers.com/jobs/1",
        "source_url": "https://acme.example-careers.com/jobs/1",
        "apply_url": "https://acme.example-careers.com/jobs/1/apply",
        "application_destination": {
            "destination_type": "dedicated_apply",
            "resolved_url": "https://acme.example-careers.com/jobs/1/apply",
        },
    }
    record.update(overrides)
    return record


def test_single_record_is_single_decision():
    result = merge_source_records([_record()])
    assert result.decision == DECISION_SINGLE
    assert result.can_publish


def test_same_url_reobservations_merge():
    first = _record(observed_at="2026-09-01T00:00:00Z", description_text="short")
    second = _record(observed_at="2026-09-09T00:00:00Z", description_text="A much longer, richer description of responsibilities.")
    result = merge_source_records([first, second], identity_key="https://acme.example-careers.com/jobs/1")
    assert result.decision == DECISION_SAME
    assert result.can_publish
    assert result.merged["description_text"] == "A much longer, richer description of responsibilities."
    assert result.merged["_source_provenance"]["sources"][0]["observed_at"] == "2026-09-01T00:00:00Z"


def test_cross_source_with_explicit_relationship_merges():
    linkedin = _record(source="linkedin", source_job_id="linkedin-9", job_detail_url="https://www.linkedin.com/jobs/view/9")
    employer = _record(source="employer_site", source_job_id="employer-1", job_detail_url="https://acme.example-careers.com/jobs/1")
    result = merge_source_records(
        [linkedin, employer],
        relationship_evidence={"relationship_type": "same_posting", "related_job_id": "job-1"},
    )
    assert result.decision == DECISION_SAME
    assert result.can_publish


def test_resemblance_without_relationship_is_ambiguous_not_published():
    linkedin = _record(source="linkedin", job_detail_url="https://www.linkedin.com/jobs/view/9")
    employer = _record(source="employer_site", job_detail_url="https://acme.example-careers.com/jobs/1")
    result = merge_source_records([linkedin, employer])
    assert result.decision == DECISION_AMBIGUOUS
    assert not result.can_publish
    assert "uncertain_dedupe_identity" in result.reasons


def test_different_vacancies_are_distinct_not_merged():
    one = _record(title="Backend Software Engineer")
    two = _record(title="Frontend Software Engineer", job_detail_url="https://acme.example-careers.com/jobs/2")
    result = merge_source_records([one, two])
    assert result.decision == DECISION_DISTINCT
    assert not result.can_publish


def test_conflicting_titles_with_shared_url_are_conflict():
    one = _record(title="Backend Software Engineer")
    two = _record(title="Data Engineer")
    result = merge_source_records([one, two], identity_key="https://acme.example-careers.com/jobs/1")
    assert result.decision == DECISION_CONFLICT
    assert not result.can_publish


def test_merge_preserves_provenance_and_application_precedence():
    employer = _record(
        source="employer_site",
        apply_url="https://acme.example-careers.com/jobs/1/apply",
        application_destination={"destination_type": "dedicated_apply", "resolved_url": "https://acme.example-careers.com/jobs/1/apply"},
    )
    linkedin = _record(
        source="linkedin",
        apply_url="",
        job_detail_url="https://www.linkedin.com/jobs/view/9",
        application_destination={"destination_type": "job_detail_only", "resolved_url": ""},
    )
    result = merge_source_records(
        [linkedin, employer],
        relationship_evidence={"relationship_type": "same_posting"},
    )
    assert result.decision == DECISION_SAME
    assert result.merged["_merged_application_source"] == "employer_site"
    sources = [entry["source"] for entry in result.provenance["sources"]]
    assert "linkedin" in sources and "employer_site" in sources


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
