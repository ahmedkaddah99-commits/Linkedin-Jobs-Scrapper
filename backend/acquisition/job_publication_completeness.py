"""Source-independent job publication completeness contract.

This module answers one question: *is this single canonical job record
complete and trustworthy enough to publish to Runr users?*

It is deliberately different from source-scan completeness.  A collector can
exhaust an employer or LinkedIn source (source-scan completeness) and still
produce individual records that must not be published (record completeness),
and vice versa: an individually complete job remains publishable even when the
collector did not exhaust the source.  This module only evaluates the former.

Rules:

* The validator is deterministic and source-independent.  The same record in,
  the same decision out, regardless of connector.
* It never fabricates or silently repairs a source value.  Every rejection
  carries machine-readable reason codes and the affected field names.
* It preserves provenance.  Merged records keep a provenance map, never a
  blended value with no audit trail.
* It does not consult the deleted admin dashboard or any live database.  It
  accepts a plain mapping (the normalized canonical-job record) plus optional
  company registry and source records.

The contract version is ``job_publication_completeness_v1``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from backend.domain.job_identity import canonicalize_url

CONTRACT_VERSION = "job_publication_completeness_v1"

# ---------------------------------------------------------------------------
# Statuses (deterministic outcomes)
# ---------------------------------------------------------------------------

STATUS_PUBLISHABLE_COMPLETE = "publishable_complete"
STATUS_MISSING_REQUIRED = "not_publishable_missing_required"
STATUS_INVALID = "not_publishable_invalid"
STATUS_UNRESOLVED_IDENTITY = "not_publishable_unresolved_identity"
STATUS_PLACEHOLDER = "not_publishable_placeholder"
STATUS_STALE_OR_CLOSED = "stale_or_closed"

STATUSES = (
    STATUS_PUBLISHABLE_COMPLETE,
    STATUS_MISSING_REQUIRED,
    STATUS_INVALID,
    STATUS_UNRESOLVED_IDENTITY,
    STATUS_PLACEHOLDER,
    STATUS_STALE_OR_CLOSED,
)

# ---------------------------------------------------------------------------
# Reason codes (machine-readable)
# ---------------------------------------------------------------------------

# Identity
REASON_MISSING_CANONICAL_JOB_ID = "missing_canonical_job_id"
REASON_MISSING_CANONICAL_COMPANY_ID = "missing_canonical_company_id"
REASON_UNKNOWN_CANONICAL_COMPANY_ID = "unknown_canonical_company_id"
REASON_MISSING_SOURCE_JOB_ID = "missing_source_job_id"
REASON_UNCERTAIN_DEDUPE_IDENTITY = "uncertain_dedupe_identity"
REASON_UNRESOLVED_OWNERSHIP_CONFLICT = "unresolved_ownership_conflict"

# Company / title
REASON_MISSING_COMPANY_NAME = "missing_company_name"
REASON_PLACEHOLDER_COMPANY_NAME = "placeholder_company_name"
REASON_MISSING_TITLE = "missing_title"
REASON_PLACEHOLDER_TITLE = "placeholder_title"

# Application / URL
REASON_MISSING_APPLICATION_URL = "missing_application_url"
REASON_INVALID_APPLICATION_URL = "invalid_application_url"
REASON_TRACKING_ONLY_APPLICATION_URL = "tracking_only_application_url"
REASON_LISTING_FALLBACK_APPLICATION_URL = "listing_fallback_application_url"

# Description
REASON_MISSING_DESCRIPTION = "missing_description"
REASON_PLACEHOLDER_DESCRIPTION = "placeholder_description"
REASON_INSUFFICIENT_DESCRIPTION = "insufficient_description"
REASON_BLOCKED_OR_ERROR_BODY = "blocked_or_error_body"

# Location
REASON_MISSING_LOCATION = "missing_location"

# Source / freshness / lifecycle
REASON_MISSING_SOURCE = "missing_source"
REASON_MISSING_OBSERVED_AT = "missing_observed_at"
REASON_STALE_OBSERVATION = "stale_observation"
REASON_CLOSED_LIFECYCLE_STATE = "closed_lifecycle_state"

# Date validity
REASON_FUTURE_POSTED_AT = "future_posted_at"
REASON_CLOSED_BEFORE_POSTED_AT = "closed_before_posted_at"

# Conflicts
REASON_CONFLICTING_SOURCE_VALUES = "conflicting_source_values"

REASON_CODES = (
    REASON_MISSING_CANONICAL_JOB_ID,
    REASON_MISSING_CANONICAL_COMPANY_ID,
    REASON_UNKNOWN_CANONICAL_COMPANY_ID,
    REASON_MISSING_SOURCE_JOB_ID,
    REASON_UNCERTAIN_DEDUPE_IDENTITY,
    REASON_UNRESOLVED_OWNERSHIP_CONFLICT,
    REASON_MISSING_COMPANY_NAME,
    REASON_PLACEHOLDER_COMPANY_NAME,
    REASON_MISSING_TITLE,
    REASON_PLACEHOLDER_TITLE,
    REASON_MISSING_APPLICATION_URL,
    REASON_INVALID_APPLICATION_URL,
    REASON_TRACKING_ONLY_APPLICATION_URL,
    REASON_LISTING_FALLBACK_APPLICATION_URL,
    REASON_MISSING_DESCRIPTION,
    REASON_PLACEHOLDER_DESCRIPTION,
    REASON_INSUFFICIENT_DESCRIPTION,
    REASON_BLOCKED_OR_ERROR_BODY,
    REASON_MISSING_LOCATION,
    REASON_MISSING_SOURCE,
    REASON_MISSING_OBSERVED_AT,
    REASON_STALE_OBSERVATION,
    REASON_CLOSED_LIFECYCLE_STATE,
    REASON_FUTURE_POSTED_AT,
    REASON_CLOSED_BEFORE_POSTED_AT,
    REASON_CONFLICTING_SOURCE_VALUES,
)

# Mapping from reason code to the outcome it forces.  Every reason is
# blocking: a single blocking reason moves the record out of
# ``publishable_complete``.  The status chosen is the most specific.
_REASON_STATUS = {
    REASON_MISSING_CANONICAL_JOB_ID: STATUS_UNRESOLVED_IDENTITY,
    REASON_MISSING_CANONICAL_COMPANY_ID: STATUS_UNRESOLVED_IDENTITY,
    REASON_UNKNOWN_CANONICAL_COMPANY_ID: STATUS_UNRESOLVED_IDENTITY,
    REASON_MISSING_SOURCE_JOB_ID: STATUS_UNRESOLVED_IDENTITY,
    REASON_UNCERTAIN_DEDUPE_IDENTITY: STATUS_UNRESOLVED_IDENTITY,
    REASON_UNRESOLVED_OWNERSHIP_CONFLICT: STATUS_UNRESOLVED_IDENTITY,
    REASON_MISSING_COMPANY_NAME: STATUS_MISSING_REQUIRED,
    REASON_PLACEHOLDER_COMPANY_NAME: STATUS_PLACEHOLDER,
    REASON_MISSING_TITLE: STATUS_MISSING_REQUIRED,
    REASON_PLACEHOLDER_TITLE: STATUS_PLACEHOLDER,
    REASON_MISSING_APPLICATION_URL: STATUS_MISSING_REQUIRED,
    REASON_INVALID_APPLICATION_URL: STATUS_INVALID,
    REASON_TRACKING_ONLY_APPLICATION_URL: STATUS_INVALID,
    REASON_LISTING_FALLBACK_APPLICATION_URL: STATUS_INVALID,
    REASON_MISSING_DESCRIPTION: STATUS_MISSING_REQUIRED,
    REASON_PLACEHOLDER_DESCRIPTION: STATUS_PLACEHOLDER,
    REASON_INSUFFICIENT_DESCRIPTION: STATUS_INVALID,
    REASON_BLOCKED_OR_ERROR_BODY: STATUS_PLACEHOLDER,
    REASON_MISSING_LOCATION: STATUS_MISSING_REQUIRED,
    REASON_MISSING_SOURCE: STATUS_MISSING_REQUIRED,
    REASON_MISSING_OBSERVED_AT: STATUS_MISSING_REQUIRED,
    REASON_STALE_OBSERVATION: STATUS_STALE_OR_CLOSED,
    REASON_CLOSED_LIFECYCLE_STATE: STATUS_STALE_OR_CLOSED,
    REASON_FUTURE_POSTED_AT: STATUS_INVALID,
    REASON_CLOSED_BEFORE_POSTED_AT: STATUS_INVALID,
    REASON_CONFLICTING_SOURCE_VALUES: STATUS_INVALID,
}

# ---------------------------------------------------------------------------
# Field classification
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = (
    "canonical_job_id",
    "canonical_company_id",
    "company_name",
    "title",
    "application_url",
    "description",
    "location_or_remote",
    "source",
    "source_job_id",
    "observed_at",
    "lifecycle_state",
)

CONDITIONALLY_REQUIRED_FIELDS = (
    "posted_at",
    "closed_at",
    "source_value_consistency",
)

RECOMMENDED_FIELDS = (
    "employment_type",
    "workplace_arrangement",
    "experience_level",
    "salary",
)

OPTIONAL_FIELDS = (
    "benefits",
    "seniority",
    "company_logo",
    "company_enrichment",
)

# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------

_UNKNOWN_TOKENS = frozenset({
    "", "unknown", "n/a", "na", "none", "null", "nil", "missing", "placeholder",
    "not available", "not disclosed", "undisclosed", "tbd", "to be determined",
    "-----", "---", "..", "...",
})

_PLACEHOLDER_SUBSTRINGS = (
    "{{", "}}", "<job", "<title", "<company", "<location", "<description",
    "lorem ipsum", "sample job", "test job", "example job", "template",
)

_BLOCKED_BODY_MARKERS = (
    "attention required", "unusual traffic", "captcha", "robot check",
    "please verify you are human", "access denied", "403 forbidden",
    "404 not found", "page not found", "something went wrong",
    "an error occurred", "this job is no longer available",
    "this position has been filled", "blocked", "challenge required",
)

_APPLICATION_DESTINATION_CLASSIFICATIONS = {
    "employer_application": "dedicated_apply",
    "ats_application": "dedicated_apply",
    "linkedin_easy_apply": "embedded_apply",
    "embedded_apply": "embedded_apply",
    "dedicated_apply": "dedicated_apply",
    "job_detail_with_apply": "job_detail_with_apply",
    "employer_job_detail": "job_detail_only",
    "ats_job_detail": "job_detail_only",
    "job_detail_only": "job_detail_only",
    "redirect_apply": "redirect_apply",
}

_TRACKING_ONLY_HOSTS = frozenset({
    "goo.gl", "bit.ly", "tinyurl.com", "t.co", "buff.ly", "ow.ly", "lnkd.in",
    "s.id", "cutt.ly", "rebrand.ly", "adf.ly",
})


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _text(value).casefold()).strip()


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (Mapping, Sequence)) and not isinstance(value, (str, bytes, bytearray)):
        return not bool(value)
    return not _text(value)


def is_unknown_token(value: Any) -> bool:
    return _norm(value) in _UNKNOWN_TOKENS


def is_placeholder(value: Any) -> bool:
    text = _text(value)
    lowered = text.casefold()
    if not lowered:
        return False
    if lowered in _UNKNOWN_TOKENS:
        return True
    if any(marker in lowered for marker in _PLACEHOLDER_SUBSTRINGS):
        return True
    # A title/company that is a bare bracketed token with no word content.
    if re.fullmatch(r"[<({\[].{0,32}[>)}\]]", text):
        return True
    return False


def is_blocked_body(value: Any) -> bool:
    text = _text(value)
    lowered = text.casefold()
    if not lowered:
        return False
    return any(marker in lowered for marker in _BLOCKED_BODY_MARKERS)


def _meaningful_char_count(value: Any) -> int:
    text = _text(value)
    # Count only letters and digits as meaningful content.
    return len(re.sub(r"[^a-z0-9]", "", text.casefold()))


def is_insufficient_description(value: Any, *, min_chars: int = 80) -> bool:
    return _meaningful_char_count(value) < min_chars


def _hostname(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().lstrip("www.")
    except ValueError:
        return ""


def is_valid_url(value: Any) -> bool:
    canonical = canonicalize_url(_text(value))
    return bool(canonical)


def is_tracking_only_url(value: Any) -> bool:
    canonical = canonicalize_url(_text(value))
    if not canonical:
        return False
    return _hostname(canonical) in _TRACKING_ONLY_HOSTS


def _parse_iso(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return None


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Reason:
    code: str
    fields: tuple[str, ...] = ()
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "fields": list(self.fields), "detail": self.detail}


@dataclass
class CompletenessResult:
    status: str
    contract_version: str = CONTRACT_VERSION
    reasons: list[Reason] = field(default_factory=list)
    field_states: dict[str, str] = field(default_factory=dict)
    merged: bool = False
    provenance: dict[str, Any] = field(default_factory=dict)
    evaluated_at: str = ""

    @property
    def publishable(self) -> bool:
        return self.status == STATUS_PUBLISHABLE_COMPLETE

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(reason.code for reason in self.reasons)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "publishable": self.publishable,
            "contract_version": self.contract_version,
            "reasons": [reason.to_dict() for reason in self.reasons],
            "reason_codes": list(self.reason_codes),
            "field_states": dict(self.field_states),
            "merged": self.merged,
            "provenance": dict(self.provenance),
            "evaluated_at": self.evaluated_at,
        }


# ---------------------------------------------------------------------------
# Field extraction (source-independent, alias-tolerant)
# ---------------------------------------------------------------------------


def _canonical_job_id(record: Mapping[str, Any]) -> str:
    return _text(_first(record, "canonical_job_id", "job_id"))


def _canonical_company_id(record: Mapping[str, Any]) -> str:
    return _text(_first(record, "canonical_company_id", "company_id", "canonical_CompanyID"))


def _company_name(record: Mapping[str, Any]) -> str:
    company = record.get("company")
    if isinstance(company, Mapping):
        name = _first(company, "name", "canonical_name", "company_name")
        if name:
            return _text(name)
    return _text(
        _first(record, "employer_name", "company_name", "display_name", "source_display_name", "company")
    )


def _title(record: Mapping[str, Any]) -> str:
    return _text(_first(record, "title", "job_title"))


def _location(record: Mapping[str, Any]) -> str:
    return _text(_first(record, "location_raw", "location"))


def _workplace_arrangement(record: Mapping[str, Any]) -> str:
    raw = _first(record, "workplace_arrangement", "workplace_type", "workplaceType", "remote_type")
    return _norm(raw)


def _description(record: Mapping[str, Any]) -> str:
    return _text(
        _first(record, "description_text", "description", "full_description", "description_html")
    )


def _source(record: Mapping[str, Any]) -> str:
    return _text(_first(record, "source", "source_ats", "connector"))


def _source_job_id(record: Mapping[str, Any]) -> str:
    return _text(_first(record, "source_job_id", "external_job_id", "job_id"))


def _observed_at(record: Mapping[str, Any]) -> str:
    return _text(_first(record, "observed_at", "observation_timestamp", "last_seen_at"))


def _lifecycle_state(record: Mapping[str, Any]) -> str:
    return _text(_first(record, "lifecycle_state", "state", "job_status")).casefold()


def _posted_at(record: Mapping[str, Any]) -> str:
    timestamps = record.get("source_timestamps")
    if isinstance(timestamps, Mapping):
        fields = timestamps.get("fields")
        if isinstance(fields, Mapping):
            posted = fields.get("source_posted_at") or fields.get("posted_at")
            if isinstance(posted, Mapping):
                value = posted.get("value")
                if value:
                    return _text(value)
    metadata = record.get("normalized_source_metadata")
    if isinstance(metadata, Mapping):
        ts = metadata.get("source_timestamps")
        if isinstance(ts, Mapping):
            fields = ts.get("fields")
            if isinstance(fields, Mapping):
                posted = fields.get("source_posted_at")
                if isinstance(posted, Mapping) and posted.get("value"):
                    return _text(posted["value"])
    return _text(_first(record, "source_posted_at", "posted_at", "date_posted", "published_at"))


def _closed_at(record: Mapping[str, Any]) -> str:
    timestamps = record.get("source_timestamps")
    if isinstance(timestamps, Mapping):
        fields = timestamps.get("fields")
        if isinstance(fields, Mapping):
            closed = fields.get("source_closed_at")
            if isinstance(closed, Mapping) and closed.get("value"):
                return _text(closed["value"])
    return _text(_first(record, "source_closed_at", "closed_at", "closedAt"))


def _application_url_and_kind(record: Mapping[str, Any]) -> tuple[str, str]:
    """Return (url, destination_kind) using the resolved application contract.

    The ``application_destination`` mapping is authoritative when it carries a
    resolved/user-facing/detail URL; otherwise we fall back to the flattened
    apply fields for legacy records.
    """
    kind = ""
    application = record.get("application_destination")
    if isinstance(application, Mapping):
        kind = _text(_first(application, "destination_type", "classification"))
        url = _text(
            _first(application, "resolved_url", "user_facing_url", "job_detail_url")
        )
        if url:
            return url, kind
    url = _text(
        _first(
            record,
            "apply_url",
            "application_url",
            "apply_link",
            "job_detail_url",
            "source_url",
            "canonical_url",
            "link",
        )
    )
    return url, kind


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def validate_job_for_publication(
    record: Mapping[str, Any],
    *,
    now: datetime | None = None,
    company_registry: set[str] | frozenset[str] | None = None,
    source_records: Sequence[Mapping[str, Any]] | None = None,
    min_description_chars: int = 80,
    stale_after_days: int = 90,
) -> CompletenessResult:
    """Classify one canonical job record for publication.

    ``record`` is the normalized canonical-job mapping (the shape written by
    ``normalize_job_for_ingestion`` / the acquisition read models).  It is
    never mutated.

    ``company_registry`` is an optional set of known canonical company IDs.
    When provided, a present-but-unknown company ID is treated as an
    unresolved identity.

    ``source_records`` is an optional sequence of the underlying source
    observations.  When more than one is supplied, cross-source conflicts are
    surfaced as ``conflicting_source_values`` instead of being silently
    blended.  A single record is evaluated as-is.
    """

    current = now or datetime.now(timezone.utc)
    reasons: list[Reason] = []
    field_states: dict[str, str] = {}

    def mark(code: str, *fields: str, detail: str = "") -> None:
        reasons.append(Reason(code, tuple(dict.fromkeys(fields)), detail))

    # --- identity ---
    canonical_job_id = _canonical_job_id(record)
    canonical_company_id = _canonical_company_id(record)
    source_job_id = _source_job_id(record)

    if not canonical_job_id:
        mark(REASON_MISSING_CANONICAL_JOB_ID, "canonical_job_id")
        field_states["canonical_job_id"] = "missing"
    else:
        field_states["canonical_job_id"] = "present"

    if not canonical_company_id:
        mark(REASON_MISSING_CANONICAL_COMPANY_ID, "canonical_company_id")
        field_states["canonical_company_id"] = "missing"
    elif company_registry is not None and canonical_company_id not in company_registry:
        mark(REASON_UNKNOWN_CANONICAL_COMPANY_ID, "canonical_company_id")
        field_states["canonical_company_id"] = "invalid"
    else:
        field_states["canonical_company_id"] = "present"

    if not source_job_id:
        mark(REASON_MISSING_SOURCE_JOB_ID, "source_job_id", "external_job_id")
        field_states["source_job_id"] = "missing"
    else:
        field_states["source_job_id"] = "present"

    # --- unresolved ownership / uncertain deduplication signals ---
    ownership = _text(_first(record, "ownership_status", "company_match_status")).casefold()
    if ownership in {"conflict", "unresolved", "disputed"}:
        mark(REASON_UNRESOLVED_OWNERSHIP_CONFLICT, "ownership_status", detail=ownership)
        field_states["ownership"] = "conflicting"

    dedupe_state = _text(_first(record, "dedupe_state", "duplicate_state", "dedupe_status")).casefold()
    if dedupe_state in {"uncertain", "ambiguous", "unresolved", "needs_review"}:
        mark(REASON_UNCERTAIN_DEDUPE_IDENTITY, "dedupe_state", detail=dedupe_state)
        field_states["dedupe"] = "uncertain"

    # --- company name ---
    company_name = _company_name(record)
    if not company_name:
        mark(REASON_MISSING_COMPANY_NAME, "company_name")
        field_states["company_name"] = "missing"
    elif is_placeholder(company_name):
        mark(REASON_PLACEHOLDER_COMPANY_NAME, "company_name", detail=company_name)
        field_states["company_name"] = "invalid"
    else:
        field_states["company_name"] = "present"

    # --- title ---
    title = _title(record)
    if not title:
        mark(REASON_MISSING_TITLE, "title")
        field_states["title"] = "missing"
    elif is_placeholder(title):
        mark(REASON_PLACEHOLDER_TITLE, "title", detail=title)
        field_states["title"] = "invalid"
    else:
        field_states["title"] = "present"

    # --- application URL ---
    application_url, application_kind = _application_url_and_kind(record)
    destination_class = _APPLICATION_DESTINATION_CLASSIFICATIONS.get(_norm(application_kind), application_kind)
    if not application_url:
        mark(REASON_MISSING_APPLICATION_URL, "apply_url", "application_url", "job_detail_url")
        field_states["application_url"] = "missing"
    elif not is_valid_url(application_url):
        mark(REASON_INVALID_APPLICATION_URL, "apply_url", "application_url", detail=application_url)
        field_states["application_url"] = "invalid"
    elif is_tracking_only_url(application_url):
        mark(REASON_TRACKING_ONLY_APPLICATION_URL, "apply_url", "application_url", detail=application_url)
        field_states["application_url"] = "invalid"
    elif destination_class in {"job_detail_only", "redirect_apply", "listing_fallback", "search_results", "portal_listing", "careers_index", "unresolved"}:
        mark(REASON_LISTING_FALLBACK_APPLICATION_URL, "application_destination", detail=application_kind)
        field_states["application_url"] = "invalid"
    else:
        field_states["application_url"] = "present"

    # --- description ---
    description = _description(record)
    if not description:
        mark(REASON_MISSING_DESCRIPTION, "description_text", "description")
        field_states["description"] = "missing"
    elif is_blocked_body(description):
        mark(REASON_BLOCKED_OR_ERROR_BODY, "description", detail=description[:80])
        field_states["description"] = "invalid"
    elif is_placeholder(description):
        mark(REASON_PLACEHOLDER_DESCRIPTION, "description")
        field_states["description"] = "invalid"
    elif is_insufficient_description(description, min_chars=min_description_chars):
        mark(REASON_INSUFFICIENT_DESCRIPTION, "description")
        field_states["description"] = "invalid"
    else:
        field_states["description"] = "present"

    # --- location or explicit remote ---
    location = _location(record)
    workplace = _workplace_arrangement(record)
    if not location and workplace not in {"remote", "fully_remote", "hybrid"}:
        mark(REASON_MISSING_LOCATION, "location_raw", "location", "workplace_arrangement")
        field_states["location_or_remote"] = "missing"
    else:
        field_states["location_or_remote"] = "present"

    # --- source ---
    source = _source(record)
    if not source:
        mark(REASON_MISSING_SOURCE, "source", "source_ats")
        field_states["source"] = "missing"
    else:
        field_states["source"] = "present"

    # --- freshness ---
    observed_at = _observed_at(record)
    if not observed_at:
        mark(REASON_MISSING_OBSERVED_AT, "observed_at")
        field_states["observed_at"] = "missing"
    else:
        observed_dt = _parse_iso(observed_at)
        if observed_dt is not None and (current - observed_dt).days > stale_after_days:
            mark(REASON_STALE_OBSERVATION, "observed_at", detail=observed_at)
            field_states["observed_at"] = "stale"
        else:
            field_states["observed_at"] = "present"

    # --- lifecycle ---
    lifecycle = _lifecycle_state(record)
    closed_lifecycle = lifecycle in {"closed", "expired", "filled", "archived", "inactive", "removed"}
    if closed_lifecycle:
        mark(REASON_CLOSED_LIFECYCLE_STATE, "lifecycle_state", detail=lifecycle)
        field_states["lifecycle_state"] = "closed"
    elif lifecycle:
        field_states["lifecycle_state"] = "present"
    else:
        field_states["lifecycle_state"] = "missing"

    # --- date validity (conditional) ---
    posted_at = _posted_at(record)
    closed_at = _closed_at(record)
    posted_dt = _parse_iso(posted_at) if posted_at else None
    closed_dt = _parse_iso(closed_at) if closed_at else None
    if posted_dt is not None and posted_dt > current + timedelta(days=1):
        mark(REASON_FUTURE_POSTED_AT, "posted_at", detail=posted_at)
        field_states["posted_at"] = "invalid"
    else:
        field_states["posted_at"] = "present" if posted_at else "unknown"
    if closed_dt is not None and posted_dt is not None and closed_dt < posted_dt:
        mark(REASON_CLOSED_BEFORE_POSTED_AT, "closed_at", "posted_at", detail=closed_at)
        field_states["closed_at"] = "invalid"
    else:
        field_states["closed_at"] = "present" if closed_at else "unknown"

    # --- cross-source conflict detection ---
    if source_records and len(source_records) > 1:
        title_values = {_norm(_title(item)) for item in source_records}
        company_values = {_norm(_company_name(item)) for item in source_records}
        if len(title_values) > 1 or len(company_values) > 1:
            mark(REASON_CONFLICTING_SOURCE_VALUES, "title", "company_name")
            field_states["source_value_consistency"] = "conflicting"
        else:
            field_states["source_value_consistency"] = "consistent"
    else:
        field_states["source_value_consistency"] = "n/a"

    # --- deterministic status resolution ---
    status = STATUS_PUBLISHABLE_COMPLETE
    if reasons:
        # Stale/closed and identity outcomes take precedence in a stable order.
        for reason in reasons:
            candidate = _REASON_STATUS[reason.code]
            if _status_rank(candidate) < _status_rank(status):
                status = candidate

    return CompletenessResult(
        status=status,
        reasons=reasons,
        field_states=field_states,
        merged=bool(source_records and len(source_records) > 1),
        evaluated_at=current.isoformat(),
    )


_STATUS_PRIORITY = {
    STATUS_STALE_OR_CLOSED: 0,
    STATUS_UNRESOLVED_IDENTITY: 1,
    STATUS_PLACEHOLDER: 2,
    STATUS_INVALID: 3,
    STATUS_MISSING_REQUIRED: 4,
    STATUS_PUBLISHABLE_COMPLETE: 5,
}


def _status_rank(status: str) -> int:
    return _STATUS_PRIORITY.get(status, 99)


def reason_status(code: str) -> str:
    return _REASON_STATUS.get(code, STATUS_INVALID)


__all__ = [
    "CONTRACT_VERSION",
    "CONDITIONALLY_REQUIRED_FIELDS",
    "OPTIONAL_FIELDS",
    "RECOMMENDED_FIELDS",
    "REQUIRED_FIELDS",
    "REASON_CODES",
    "STATUSES",
    "STATUS_INVALID",
    "STATUS_MISSING_REQUIRED",
    "STATUS_PLACEHOLDER",
    "STATUS_PUBLISHABLE_COMPLETE",
    "STATUS_STALE_OR_CLOSED",
    "STATUS_UNRESOLVED_IDENTITY",
    "CompletenessResult",
    "Reason",
    "canonicalize_url",
    "is_blocked_body",
    "is_blank",
    "is_insufficient_description",
    "is_placeholder",
    "is_tracking_only_url",
    "is_unknown_token",
    "is_valid_url",
    "reason_status",
    "validate_job_for_publication",
]
