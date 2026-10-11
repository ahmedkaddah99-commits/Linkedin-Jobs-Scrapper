"""Deliberate source-merging rules for canonical job completeness.

The pipeline's canonical job identity is URL-based (see
``backend.domain.job_identity``).  Multiple observations of the *same* URL are
re-observations over time and merge trivially.  Two observations of *different*
URLs are, by default, two different vacancies.

The only circumstances under which complementary observations (for example a
LinkedIn posting and an employer ATS posting) may form one complete canonical
job are explicit, recorded relationships.  Title/company resemblance is never
enough.  Uncertain deduplication must not produce a publishable job.

This module is source-independent and side-effect free.  It only computes a
merged projection and a provenance map; it never writes to any store.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from backend.domain.job_identity import canonicalize_url

MERGE_SCHEMA_VERSION = "job_source_merging_v1"

DECISION_SAME = "same_job"
DECISION_CONFLICT = "conflict"
DECISION_AMBIGUOUS = "ambiguous"
DECISION_DISTINCT = "distinct"
DECISION_SINGLE = "single"

DECISIONS = (DECISION_SAME, DECISION_CONFLICT, DECISION_AMBIGUOUS, DECISION_DISTINCT, DECISION_SINGLE)

# Relationship types that legally merge two observations of different URLs
# into one canonical job.
MERGE_RELATIONSHIP_TYPES = frozenset({
    "same_posting",
    "duplicate",
    "cross_source_match",
    "repost",
    "canonical_match",
})

# Field precedence, most authoritative first.
_APPLICATION_DESTINATION_RANK = {
    "dedicated_apply": 60,
    "embedded_apply": 50,
    "job_detail_with_apply": 40,
    "job_detail_only": 30,
    "redirect_apply": 20,
    "listing_fallback": 10,
    "unresolved": 0,
    "unknown": 0,
}

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


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _text(value).casefold()).strip()


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return None


def _title(record: Mapping[str, Any]) -> str:
    return _text(_first(record, "title", "job_title"))


def _company_name(record: Mapping[str, Any]) -> str:
    company = record.get("company")
    if isinstance(company, Mapping):
        name = _first(company, "name", "canonical_name", "company_name")
        if name:
            return _text(name)
    return _text(_first(record, "employer_name", "company_name", "display_name", "company"))


def _description(record: Mapping[str, Any]) -> str:
    return _text(_first(record, "description_text", "description", "full_description"))


def _location(record: Mapping[str, Any]) -> str:
    return _text(_first(record, "location_raw", "location"))


def _application(record: Mapping[str, Any]) -> tuple[str, str]:
    application = record.get("application_destination")
    if isinstance(application, Mapping):
        kind = _norm(_first(application, "destination_type", "classification"))
        url = _text(_first(application, "resolved_url", "user_facing_url", "job_detail_url"))
        return url, kind
    url = _text(_first(record, "apply_url", "application_url", "apply_link", "job_detail_url", "source_url"))
    return url, ""


def _application_rank(kind: str) -> int:
    canonical = _APPLICATION_DESTINATION_CLASSIFICATIONS.get(_norm(kind), _norm(kind))
    return _APPLICATION_DESTINATION_RANK.get(canonical, 0)


def _source(record: Mapping[str, Any]) -> str:
    return _text(_first(record, "source", "source_ats"))


def _source_job_id(record: Mapping[str, Any]) -> str:
    return _text(_first(record, "source_job_id", "external_job_id"))


def _identity_key(record: Mapping[str, Any]) -> str:
    url = _text(
        _first(
            record,
            "canonical_url",
            "job_detail_url",
            "source_url",
            "url",
            "link",
            "linkedin_job_url",
            "job_url",
        )
    )
    canonical = canonicalize_url(url)
    return canonical or ""


@dataclass
class MergeResult:
    decision: str
    merged: Mapping[str, Any] | None
    provenance: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    @property
    def can_publish(self) -> bool:
        return self.decision in {DECISION_SAME, DECISION_SINGLE} and self.merged is not None


def _provenance(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for record in records:
        entries.append({
            "source": _source(record) or None,
            "source_job_id": _source_job_id(record) or None,
            "identity_key": _identity_key(record) or None,
            "observation_id": _text(_first(record, "source_observation_id", "observation_id")) or None,
            "observed_at": _text(_first(record, "observed_at", "observation_timestamp")) or None,
            "title": _title(record) or None,
            "company_name": _company_name(record) or None,
        })
    return {"schema_version": MERGE_SCHEMA_VERSION, "sources": entries}


def _pick_description(records: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    best: tuple[str, str] = ("", "")
    for record in records:
        description = _description(record)
        if len(description) > len(best[0]):
            best = (description, _source(record))
    return best


def _pick_application(records: Sequence[Mapping[str, Any]]) -> tuple[str, str, str]:
    best: tuple[int, str, str, str] = (-1, "", "", "")
    for record in records:
        url, kind = _application(record)
        if not url:
            continue
        rank = _application_rank(kind)
        if rank > best[0]:
            best = (rank, url, kind, _source(record))
    return best[1], best[2], best[3]


def merge_source_records(
    records: Sequence[Mapping[str, Any]],
    *,
    identity_key: str = "",
    relationship_evidence: Mapping[str, Any] | None = None,
) -> MergeResult:
    """Decide whether observations form one canonical job and, if so, merge.

    ``identity_key`` is the canonical identity (URL) shared by true
    re-observations.  ``relationship_evidence`` is an optional explicit
    relationship record, e.g. ``{"relationship_type": "same_posting",
    "related_job_id": "..."}``, that licenses a cross-source merge.
    """

    cleaned = [dict(record) for record in records]
    if not cleaned:
        return MergeResult(DECISION_AMBIGUOUS, None, reasons=["no_source_records"])

    if len(cleaned) == 1:
        return MergeResult(DECISION_SINGLE, cleaned[0], provenance=_provenance(cleaned))

    keys = {_identity_key(record) for record in cleaned}
    keys.discard("")
    shared_url_identity = bool(identity_key) or len(keys) <= 1

    relationship_type = ""
    if isinstance(relationship_evidence, Mapping):
        relationship_type = str(relationship_evidence.get("relationship_type") or "").strip().casefold()

    if shared_url_identity or relationship_type in MERGE_RELATIONSHIP_TYPES:
        pass
    else:
        # Different URLs and no explicit relationship.  Resemblance is not
        # enough; treat as distinct unless title+company are also different
        # (then clearly distinct) or identical (then ambiguous).
        titles = {_norm(_title(record)) for record in cleaned}
        companies = {_norm(_company_name(record)) for record in cleaned}
        if len(titles) <= 1 and len(companies) <= 1:
            return MergeResult(
                DECISION_AMBIGUOUS,
                None,
                provenance=_provenance(cleaned),
                reasons=["uncertain_dedupe_identity"],
            )
        return MergeResult(
            DECISION_DISTINCT,
            None,
            provenance=_provenance(cleaned),
            reasons=["distinct_vacancies"],
        )

    # Now merge.  Conflicts on identity-significant fields are fatal: we do
    # not blend differing titles or companies without an explicit authority.
    titles = {_norm(_title(record)) for record in cleaned if _title(record)}
    companies = {_norm(_company_name(record)) for record in cleaned if _company_name(record)}
    if len(titles) > 1 or len(companies) > 1:
        return MergeResult(
            DECISION_CONFLICT,
            None,
            provenance=_provenance(cleaned),
            reasons=["conflicting_identity_fields"],
        )

    base = cleaned[0]
    merged = dict(base)
    merged["canonical_job_id"] = _text(_first(base, "canonical_job_id", "job_id")) or identity_key

    description, description_source = _pick_description(cleaned)
    if description:
        merged["description_text"] = description
        merged["description"] = description

    apply_url, apply_kind, apply_source = _pick_application(cleaned)
    if apply_url:
        merged["apply_url"] = apply_url
        merged["application_url"] = apply_url
        merged["_merged_application_kind"] = apply_kind

    # Preserve provenance and a source list rather than a blended value.
    merged["_source_provenance"] = _provenance(cleaned)
    merged["_merged_description_source"] = description_source or None
    merged["_merged_application_source"] = apply_source or None
    merged["_merge_relationship_type"] = relationship_type or ("same_url" if shared_url_identity else "none")

    return MergeResult(
        DECISION_SAME,
        merged,
        provenance=_provenance(cleaned),
    )


__all__ = [
    "DECISIONS",
    "DECISION_AMBIGUOUS",
    "DECISION_CONFLICT",
    "DECISION_DISTINCT",
    "DECISION_SAME",
    "DECISION_SINGLE",
    "MERGE_RELATIONSHIP_TYPES",
    "MERGE_SCHEMA_VERSION",
    "MergeResult",
    "merge_source_records",
]
