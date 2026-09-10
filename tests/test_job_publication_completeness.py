"""Tests for the source-independent job publication completeness contract."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.acquisition.job_publication_completeness import (
    REASON_BLOCKED_OR_ERROR_BODY,
    REASON_CLOSED_BEFORE_POSTED_AT,
    REASON_CLOSED_LIFECYCLE_STATE,
    REASON_FUTURE_POSTED_AT,
    REASON_INSUFFICIENT_DESCRIPTION,
    REASON_INVALID_APPLICATION_URL,
    REASON_LISTING_FALLBACK_APPLICATION_URL,
    REASON_MISSING_APPLICATION_URL,
    REASON_MISSING_CANONICAL_COMPANY_ID,
    REASON_MISSING_CANONICAL_JOB_ID,
    REASON_MISSING_COMPANY_NAME,
    REASON_MISSING_DESCRIPTION,
    REASON_MISSING_LOCATION,
    REASON_MISSING_OBSERVED_AT,
    REASON_MISSING_SOURCE,
    REASON_MISSING_TITLE,
    REASON_PLACEHOLDER_COMPANY_NAME,
    REASON_PLACEHOLDER_DESCRIPTION,
    REASON_PLACEHOLDER_TITLE,
    REASON_STALE_OBSERVATION,
    REASON_TRACKING_ONLY_APPLICATION_URL,
    REASON_UNKNOWN_CANONICAL_COMPANY_ID,
    REASON_UNRESOLVED_OWNERSHIP_CONFLICT,
    REASON_UNCERTAIN_DEDUPE_IDENTITY,
    STATUS_INVALID,
    STATUS_MISSING_REQUIRED,
    STATUS_PLACEHOLDER,
    STATUS_PUBLISHABLE_COMPLETE,
    STATUS_STALE_OR_CLOSED,
    STATUS_UNRESOLVED_IDENTITY,
    validate_job_for_publication,
)

NOW = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
REGISTRY = {"canonical-acme", "canonical-beta"}


def _complete_record(**overrides) -> dict:
    record = {
        "canonical_job_id": "job-1",
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
        "source_job_id": "employer-123",
        "observed_at": "2026-09-09T12:00:00+00:00",
        "lifecycle_state": "active",
        "apply_url": "https://acme.example-careers.com/jobs/123/apply",
        "application_url": "https://acme.example-careers.com/jobs/123/apply",
        "application_destination": {
            "destination_type": "dedicated_apply",
            "classification": "employer_application",
            "resolved_url": "https://acme.example-careers.com/jobs/123/apply",
        },
        "source_timestamps": {"fields": {"source_posted_at": {"value": "2026-09-01T00:00:00+00:00"}}},
    }
    record.update(overrides)
    return record


def _codes(result) -> set:
    return set(result.reason_codes)


def test_complete_record_is_publishable():
    result = validate_job_for_publication(_complete_record(), now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_PUBLISHABLE_COMPLETE
    assert result.publishable
    assert result.reasons == []


def test_missing_canonical_job_id_is_unresolved_identity():
    result = validate_job_for_publication(_complete_record(canonical_job_id=""), now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_UNRESOLVED_IDENTITY
    assert REASON_MISSING_CANONICAL_JOB_ID in _codes(result)


def test_missing_canonical_company_id_is_unresolved_identity():
    result = validate_job_for_publication(_complete_record(canonical_company_id=""), now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_UNRESOLVED_IDENTITY
    assert REASON_MISSING_CANONICAL_COMPANY_ID in _codes(result)


def test_unknown_canonical_company_id_is_unresolved_identity():
    record = _complete_record(canonical_company_id="canonical-ghost")
    result = validate_job_for_publication(record, now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_UNRESOLVED_IDENTITY
    assert REASON_UNKNOWN_CANONICAL_COMPANY_ID in _codes(result)


def test_unknown_company_id_is_ok_when_registry_not_provided():
    record = _complete_record(canonical_company_id="canonical-ghost")
    result = validate_job_for_publication(record, now=NOW)
    # Without a registry we only require presence, not membership.
    assert result.status == STATUS_PUBLISHABLE_COMPLETE


def test_missing_title_is_missing_required():
    result = validate_job_for_publication(_complete_record(title=""), now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_MISSING_REQUIRED
    assert REASON_MISSING_TITLE in _codes(result)


def test_placeholder_title_is_placeholder():
    result = validate_job_for_publication(_complete_record(title="{{job_title}}"), now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_PLACEHOLDER
    assert REASON_PLACEHOLDER_TITLE in _codes(result)


def test_placeholder_company_name_is_placeholder():
    result = validate_job_for_publication(_complete_record(company_name="TBD"), now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_PLACEHOLDER
    assert REASON_PLACEHOLDER_COMPANY_NAME in _codes(result)


def test_missing_company_name_is_missing_required():
    record = _complete_record()
    record.pop("company_name")
    result = validate_job_for_publication(record, now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_MISSING_REQUIRED
    assert REASON_MISSING_COMPANY_NAME in _codes(result)


def test_missing_description_is_missing_required():
    result = validate_job_for_publication(_complete_record(description_text=""), now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_MISSING_REQUIRED
    assert REASON_MISSING_DESCRIPTION in _codes(result)


def test_short_description_is_invalid():
    result = validate_job_for_publication(_complete_record(description_text="See website."), now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_INVALID
    assert REASON_INSUFFICIENT_DESCRIPTION in _codes(result)


def test_placeholder_description_is_placeholder():
    result = validate_job_for_publication(_complete_record(description_text="{{job_description}}"), now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_PLACEHOLDER
    assert REASON_PLACEHOLDER_DESCRIPTION in _codes(result)


def test_blocked_body_description_is_placeholder():
    record = _complete_record(description_text="Attention required. Please verify you are human to continue.")
    result = validate_job_for_publication(record, now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_PLACEHOLDER
    assert REASON_BLOCKED_OR_ERROR_BODY in _codes(result)


def test_missing_location_is_missing_required():
    record = _complete_record(location_raw="")
    result = validate_job_for_publication(record, now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_MISSING_REQUIRED
    assert REASON_MISSING_LOCATION in _codes(result)


def test_remote_classification_satisfies_location_requirement():
    record = _complete_record(location_raw="", workplace_arrangement="Remote")
    result = validate_job_for_publication(record, now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_PUBLISHABLE_COMPLETE


def test_missing_application_url_is_missing_required():
    record = _complete_record()
    record.pop("apply_url")
    record.pop("application_url")
    record["application_destination"] = {}
    result = validate_job_for_publication(record, now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_MISSING_REQUIRED
    assert REASON_MISSING_APPLICATION_URL in _codes(result)


def test_invalid_application_url_is_invalid():
    record = _complete_record(
        apply_url="not-a-url",
        application_url="not-a-url",
        application_destination={"destination_type": "dedicated_apply", "resolved_url": "not-a-url"},
    )
    result = validate_job_for_publication(record, now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_INVALID
    assert REASON_INVALID_APPLICATION_URL in _codes(result)


def test_tracking_only_application_url_is_invalid():
    record = _complete_record(
        apply_url="https://bit.ly/xyz",
        application_url="https://bit.ly/xyz",
        application_destination={"destination_type": "dedicated_apply", "resolved_url": "https://bit.ly/xyz"},
    )
    result = validate_job_for_publication(record, now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_INVALID
    assert REASON_TRACKING_ONLY_APPLICATION_URL in _codes(result)


def test_listing_fallback_application_url_is_invalid():
    record = _complete_record(
        apply_url="https://acme.example-careers.com/careers",
        application_url="https://acme.example-careers.com/careers",
        application_destination={
            "destination_type": "listing_fallback",
            "classification": "careers_index",
            "user_facing_url": "https://acme.example-careers.com/careers",
        },
    )
    result = validate_job_for_publication(record, now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_INVALID
    assert REASON_LISTING_FALLBACK_APPLICATION_URL in _codes(result)


def test_missing_source_is_missing_required():
    record = _complete_record(source="", source_ats="")
    result = validate_job_for_publication(record, now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_MISSING_REQUIRED
    assert REASON_MISSING_SOURCE in _codes(result)


def test_missing_observed_at_is_missing_required():
    result = validate_job_for_publication(_complete_record(observed_at=""), now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_MISSING_REQUIRED
    assert REASON_MISSING_OBSERVED_AT in _codes(result)


def test_stale_observation_is_stale_or_closed():
    stale = (NOW - timedelta(days=120)).isoformat()
    result = validate_job_for_publication(_complete_record(observed_at=stale), now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_STALE_OR_CLOSED
    assert REASON_STALE_OBSERVATION in _codes(result)


def test_closed_lifecycle_is_stale_or_closed():
    result = validate_job_for_publication(_complete_record(lifecycle_state="closed"), now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_STALE_OR_CLOSED
    assert REASON_CLOSED_LIFECYCLE_STATE in _codes(result)


def test_future_posted_at_is_invalid():
    future = (NOW + timedelta(days=5)).isoformat()
    record = _complete_record(source_timestamps={"fields": {"source_posted_at": {"value": future}}})
    result = validate_job_for_publication(record, now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_INVALID
    assert REASON_FUTURE_POSTED_AT in _codes(result)


def test_closed_before_posted_is_invalid():
    posted = "2026-09-01T00:00:00+00:00"
    closed = "2026-08-01T00:00:00+00:00"
    record = _complete_record(
        source_timestamps={"fields": {"source_posted_at": {"value": posted}}},
        closed_at=closed,
        lifecycle_state="closed",
    )
    result = validate_job_for_publication(record, now=NOW, company_registry=REGISTRY)
    assert result.status in {STATUS_STALE_OR_CLOSED, STATUS_INVALID}
    assert REASON_CLOSED_BEFORE_POSTED_AT in _codes(result)


def test_conflicting_source_values_is_invalid():
    sources = [
        _complete_record(title="Backend Engineer", canonical_job_id="job-x"),
        _complete_record(title="Frontend Engineer", canonical_job_id="job-x"),
    ]
    result = validate_job_for_publication(
        _complete_record(), now=NOW, company_registry=REGISTRY, source_records=sources
    )
    assert result.status == STATUS_INVALID


def test_invalid_record_cannot_be_published_merely_because_collector_exited():
    # Source-scan success is not an input to record completeness.
    record = _complete_record(description_text="", title="")
    result = validate_job_for_publication(record, now=NOW, company_registry=REGISTRY)
    assert not result.publishable
    assert result.status == STATUS_MISSING_REQUIRED


def test_source_scan_incompleteness_does_not_invalidate_complete_job():
    # Record completeness is independent of source exhaustion.
    result = validate_job_for_publication(_complete_record(), now=NOW, company_registry=REGISTRY)
    assert result.publishable


def test_unresolved_ownership_conflict_is_unresolved_identity():
    record = _complete_record(ownership_status="conflict")
    result = validate_job_for_publication(record, now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_UNRESOLVED_IDENTITY
    assert REASON_UNRESOLVED_OWNERSHIP_CONFLICT in _codes(result)


def test_uncertain_dedupe_identity_is_unresolved_identity():
    record = _complete_record(dedupe_state="uncertain")
    result = validate_job_for_publication(record, now=NOW, company_registry=REGISTRY)
    assert result.status == STATUS_UNRESOLVED_IDENTITY
    assert REASON_UNCERTAIN_DEDUPE_IDENTITY in _codes(result)


def test_validation_never_mutates_input_record():
    record = _complete_record(title="", description_text="")
    before = dict(record)
    validate_job_for_publication(record, now=NOW, company_registry=REGISTRY)
    assert record == before


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
