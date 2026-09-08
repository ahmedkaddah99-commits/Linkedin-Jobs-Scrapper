"""Build and enforce a versioned source-eligibility manifest.

The manifest is the only supported collector input for the acquisition lane.
It is derived from one immutable master snapshot and keeps field presence,
evidence quality, identity mapping, ownership review, and source eligibility as
separate facts.  The raw master columns are retained in a sidecar so the
manifest can be reviewed without silently losing provenance.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.parse import urlsplit

from backend.domain.company_identity import structural_url


SCHEMA_VERSION = "runr_source_eligibility_manifest_v1"
RAW_SIDECAR_SCHEMA_VERSION = "runr_source_eligibility_raw_sidecar_v1"
MASTER_CANONICAL_ID_FIELD = "canonical_CompanyID"
SOURCE_EMPLOYER = "employer_site"
SOURCE_LINKEDIN = "linkedin"
SOURCES = (SOURCE_EMPLOYER, SOURCE_LINKEDIN)
MISSING_MARKERS = {"", "//", "null", "none", "nan", "n/a", "na"}
NON_COMPANY_LINKEDIN_PAGE_TYPES = {"school", "showcase"}
WEBSITE_EVIDENCE_STATUSES = {"found", "verified", "complete"}
LINKEDIN_EVIDENCE_STATUSES = {"resolved", "validated", "high_confidence", "verified"}
REVIEWED_OWNERSHIP_DISPOSITIONS = {"same_entity_alias", "distinct_related_employers"}
REQUIRED_COLUMNS = (
    MASTER_CANONICAL_ID_FIELD,
    "company_name",
    "website_url",
    "linkedin_company_url",
    "linkedin_company_id",
    "linkedin_page_type",
    "website_discovery_status",
    "linkedin_company_id_status",
)
KNOWN_CONTRACT_COLUMNS = {
    MASTER_CANONICAL_ID_FIELD,
    "companyenrich_id",
    "merge_basis",
    "company_name",
    "website_url",
    "linkedin_company_url",
    "linkedin_slug",
    "linkedin_page_type",
    "headquarters_city",
    "headquarters_region",
    "headquarters_country",
    "headquarters_country_code",
    "headquarters_display",
    "linkedin_company_id",
    "linkedin_company_id_status",
    "linkedin_company_id_source",
    "linkedin_company_id_confidence",
    "linkedin_company_id_resolved_at",
    "linkedin_company_id_transport",
    "linkedin_company_id_url_used",
    "website_discovery_status",
    "enrichment_status",
    "last_enriched_at",
    "description",
    "industry",
    "employee_count_range",
    "logo_url",
    "companyenrich_free_logo_url",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _value(value: Any) -> str:
    candidate = _text(value)
    return "" if candidate.casefold() in MISSING_MARKERS else candidate


def _normalise_numeric_id(value: Any) -> str:
    candidate = _value(value)
    if not candidate or not candidate.isascii() or not candidate.isdecimal() or int(candidate, 10) <= 0:
        return ""
    return str(int(candidate, 10))


def _row_fingerprint(row: Mapping[str, Any]) -> str:
    payload = json.dumps(
        {str(key): "" if value is None else str(value) for key, value in row.items()},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _parse_timestamp(value: Any) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _freshness(
    timestamp: Any,
    *,
    as_of: datetime | None,
    max_age_days: int | None,
) -> tuple[str, str]:
    raw = _text(timestamp)
    if not raw:
        return "unknown", "evidence_timestamp_missing"
    parsed = _parse_timestamp(raw)
    if parsed is None:
        return "unsupported", "evidence_timestamp_invalid"
    if as_of is None or max_age_days is None:
        return "unknown", "freshness_policy_not_supplied"
    age_days = (as_of - parsed).total_seconds() / 86400
    if age_days > int(max_age_days):
        return "stale", f"evidence_older_than_{int(max_age_days)}_days"
    return "fresh", "within_evidence_age_policy"


def _url_details(value: Any) -> dict[str, str | bool]:
    original, canonical, reason = structural_url(value)
    host = ""
    path = ""
    if canonical:
        parsed = urlsplit(canonical)
        host = (parsed.hostname or "").casefold().removeprefix("www.")
        path = parsed.path or "/"
    return {
        "original": original,
        "canonical": canonical,
        "host": host,
        "path": path,
        "structurally_valid": bool(canonical),
        "reason": reason,
    }


def _linkedin_page_type(row: Mapping[str, Any], details: Mapping[str, Any]) -> tuple[str, bool]:
    parts = [part for part in _text(details.get("path")).casefold().split("/") if part]
    path_type = parts[0] if parts else "unknown"
    declared = _value(row.get("linkedin_page_type")).casefold()
    effective = declared or path_type
    conflict = bool(declared and path_type in {"company", "school", "showcase"} and declared != path_type)
    return effective, conflict


def _linkedin_slug(value: Any) -> str:
    details = _url_details(value)
    parts = [part for part in _text(details.get("path")).split("/") if part]
    if not details.get("structurally_valid") or len(parts) < 2 or parts[0].casefold() != "company":
        return ""
    return parts[1].casefold()


def _normalise_as_of(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = _parse_timestamp(value)
    if parsed is None:
        raise ValueError(f"Invalid --as-of timestamp: {value}")
    return parsed


def read_master_snapshot(path: str | Path) -> tuple[list[dict[str, str]], list[str], str]:
    """Read a strict CSV snapshot and return rows, exact header, and byte hash."""

    source = Path(path)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        missing = sorted(set(REQUIRED_COLUMNS).difference(fieldnames))
        if missing:
            raise ValueError(f"master input missing required columns: {', '.join(missing)}")
        rows: list[dict[str, str]] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"master input row {line_number} has more values than its header")
            rows.append({str(key): "" if value is None else str(value) for key, value in row.items()})
    return rows, fieldnames, digest


def _unwrap_json(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = payload.get("mapping_manifest")
    return nested if isinstance(nested, Mapping) else payload


def _approved_payload(payload: Mapping[str, Any]) -> bool:
    nested = _unwrap_json(payload)
    return nested.get("approved") is True or _text(nested.get("approval_status")).casefold() in {
        "approved",
        "approved_applied",
    }


def load_backfill_context(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Extract approved and pending RC-004 mappings without approving dry-run data."""

    if not isinstance(payload, Mapping):
        return {"approved": False, "approved_rows": {}, "pending_rows": {}, "source_sha256": ""}
    nested = _unwrap_json(payload)
    entries = nested.get("mappings")
    if not isinstance(entries, list):
        entries = payload.get("mappings") if isinstance(payload.get("mappings"), list) else []
    approved = _approved_payload(payload)
    approved_rows: dict[str, str] = {}
    pending_rows: dict[str, str] = {}
    for item in entries:
        if not isinstance(item, Mapping):
            continue
        fingerprint = _text(item.get("row_fingerprint"))
        proposed = _value(item.get("proposed_canonical_id"))
        decision = _text(item.get("base_decision")).casefold()
        if not fingerprint or not proposed or decision not in {"retained", "matched_existing", "new"}:
            continue
        pending_rows[fingerprint] = proposed
        if approved and bool(item.get("eligible_for_identity_backfill")):
            approved_rows[fingerprint] = proposed
    direct_rows = nested.get("row_fingerprint_to_canonical_id")
    if isinstance(direct_rows, Mapping) and approved:
        for fingerprint, proposed in direct_rows.items():
            if _text(fingerprint) and _value(proposed):
                approved_rows[_text(fingerprint)] = _value(proposed)
                pending_rows[_text(fingerprint)] = _value(proposed)
    return {
        "approved": approved,
        "approved_rows": approved_rows,
        "pending_rows": pending_rows,
        "source_sha256": _text(nested.get("input_sha256")),
        "approval_status": _text(nested.get("approval_status")) or "dry_run",
    }


def _ownership_reviews(payload: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return {}
    raw = payload.get("shared_organization_dispositions")
    if isinstance(raw, Mapping):
        records = []
        for org_id, item in raw.items():
            if isinstance(item, Mapping):
                records.append({"linkedin_org_id": org_id, **dict(item)})
    elif isinstance(raw, list):
        records = [item for item in raw if isinstance(item, Mapping)]
    else:
        records = []
    result: dict[str, dict[str, Any]] = {}
    for item in records:
        org_id = _normalise_numeric_id(item.get("linkedin_org_id") or item.get("org_id"))
        if org_id:
            result[org_id] = dict(item)
    return result


def _ownership_state(
    org_id: str,
    canonical_id: str,
    groups: Mapping[str, set[str]],
    reviews: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    owners = sorted(groups.get(org_id, set())) if org_id else []
    if len(owners) <= 1:
        return {
            "status": "clear",
            "reviewed": False,
            "organization_id": org_id,
            "canonical_company_ids": owners,
            "disposition": "not_shared",
            "reason": "no_conflicting_canonical_owners",
        }
    review = reviews.get(org_id)
    disposition = _text(review.get("disposition")) if isinstance(review, Mapping) else ""
    reviewed_ids = set()
    if isinstance(review, Mapping):
        reviewed_ids = {
            _value(item)
            for item in (review.get("master_canonical_ids") or review.get("master_ids") or ())
            if _value(item)
        }
    if reviewed_ids == set(owners) and disposition in REVIEWED_OWNERSHIP_DISPOSITIONS and not bool(
        review.get("review_required")
    ):
        return {
            "status": "reviewed_shared_mapping",
            "reviewed": True,
            "organization_id": org_id,
            "canonical_company_ids": owners,
            "disposition": disposition,
            "reason": "reviewed_organization_mapping_exactly_covers_observed_owners",
        }
    return {
        "status": "conflicting_unresolved",
        "reviewed": False,
        "organization_id": org_id,
        "canonical_company_ids": owners,
        "disposition": disposition or "unresolved_conflict",
        "reason": "organization_maps_to_multiple_canonical_owners_without_valid_review",
    }


def _website_evidence(
    row: Mapping[str, Any],
    *,
    as_of: datetime | None,
    max_evidence_age_days: int | None,
) -> dict[str, Any]:
    details = _url_details(row.get("website_url"))
    status = _value(row.get("website_discovery_status")).casefold()
    freshness, freshness_reason = _freshness(
        row.get("last_enriched_at"), as_of=as_of, max_age_days=max_evidence_age_days
    )
    verified = bool(details["structurally_valid"]) and status in WEBSITE_EVIDENCE_STATUSES and freshness != "stale"
    reasons: list[str] = []
    if not details["structurally_valid"]:
        reasons.append(str(details["reason"]))
    elif status not in WEBSITE_EVIDENCE_STATUSES:
        reasons.append(f"website_evidence_status_not_verified:{status or 'missing'}")
    if freshness == "stale":
        reasons.append(freshness_reason)
    return {
        "url": details,
        "discovery_status": status or "missing",
        "freshness": freshness,
        "freshness_reason": freshness_reason,
        "evidence_verified": verified,
        "reasons": reasons,
    }


def _linkedin_evidence(
    row: Mapping[str, Any],
    *,
    as_of: datetime | None,
    max_evidence_age_days: int | None,
) -> dict[str, Any]:
    details = _url_details(row.get("linkedin_company_url"))
    host = _text(details.get("host")).casefold()
    path_parts = [part for part in _text(details.get("path")).split("/") if part]
    linkedin_host_valid = host == "linkedin.com" or host.endswith(".linkedin.com")
    declared_page_type, page_type_conflict = _linkedin_page_type(row, details)
    raw_id = _value(row.get("linkedin_company_id"))
    numeric_id = _normalise_numeric_id(raw_id)
    status = _value(row.get("linkedin_company_id_status")).casefold()
    source = _value(row.get("linkedin_company_id_source"))
    confidence_raw = _value(row.get("linkedin_company_id_confidence"))
    confidence: float | None = None
    if confidence_raw:
        try:
            confidence = float(confidence_raw)
        except ValueError:
            confidence = None
    used_url = _url_details(row.get("linkedin_company_id_url_used"))
    url_slug = _linkedin_slug(row.get("linkedin_company_url"))
    used_slug = _linkedin_slug(row.get("linkedin_company_id_url_used"))
    pair_status = "not_recorded"
    if used_slug and url_slug and used_slug != url_slug:
        pair_status = "mismatch"
    elif used_slug and url_slug:
        pair_status = "matched"
    elif used_url["structurally_valid"]:
        pair_status = "unsupported_url_shape"
    freshness, freshness_reason = _freshness(
        row.get("linkedin_company_id_resolved_at"), as_of=as_of, max_age_days=max_evidence_age_days
    )
    reasons: list[str] = []
    if not details["structurally_valid"] or not linkedin_host_valid:
        reasons.append("linkedin_url_missing_or_invalid")
    elif not path_parts:
        reasons.append("linkedin_url_path_missing")
    if declared_page_type in NON_COMPANY_LINKEDIN_PAGE_TYPES:
        reasons.append(f"non_company_linkedin_page:{declared_page_type}")
    if page_type_conflict:
        reasons.append("linkedin_page_type_field_conflicts_with_url")
    if raw_id and not numeric_id:
        reasons.append("malformed_numeric_linkedin_id")
    elif not numeric_id:
        reasons.append("numeric_linkedin_id_missing")
    if status not in LINKEDIN_EVIDENCE_STATUSES:
        reasons.append(f"numeric_id_evidence_status_not_verified:{status or 'missing'}")
    if confidence is not None and confidence <= 0:
        reasons.append("numeric_id_confidence_not_positive")
    if pair_status == "mismatch":
        reasons.append("linkedin_url_id_evidence_pair_mismatch")
    if freshness == "stale":
        reasons.append(freshness_reason)
    verified = (
        bool(details["structurally_valid"])
        and linkedin_host_valid
        and bool(path_parts)
        and declared_page_type == "company"
        and not page_type_conflict
        and bool(numeric_id)
        and status in LINKEDIN_EVIDENCE_STATUSES
        and (confidence is None or confidence > 0)
        and pair_status != "mismatch"
        and freshness != "stale"
    )
    return {
        "url": details,
        "page_type": declared_page_type,
        "page_type_conflict": page_type_conflict,
        "numeric_id_raw": raw_id,
        "numeric_id": numeric_id,
        "numeric_id_valid": bool(numeric_id),
        "verification_status": status or "missing",
        "evidence": {
            "source": source,
            "confidence": confidence,
            "confidence_raw": confidence_raw,
            "resolved_at": _value(row.get("linkedin_company_id_resolved_at")),
            "transport": _value(row.get("linkedin_company_id_transport")),
            "url_used": used_url,
            "url_id_pair_status": pair_status,
        },
        "freshness": freshness,
        "freshness_reason": freshness_reason,
        "evidence_verified": verified,
        "reasons": reasons,
    }


def _effective_identity(
    row: Mapping[str, Any],
    fingerprint: str,
    backfill: Mapping[str, Any],
) -> tuple[str, str, str]:
    original = _value(row.get(MASTER_CANONICAL_ID_FIELD))
    if original:
        return original, "input", ""
    approved = _value((backfill.get("approved_rows") or {}).get(fingerprint))
    if approved:
        return approved, "approved_backfill", ""
    pending = _value((backfill.get("pending_rows") or {}).get(fingerprint))
    return "", "missing", pending


def _row_decision(
    row: Mapping[str, Any],
    *,
    source_row_number: int,
    fingerprint: str,
    backfill: Mapping[str, Any],
    ownership_groups: Mapping[str, set[str]],
    ownership_reviews: Mapping[str, Mapping[str, Any]],
    as_of: datetime | None,
    max_evidence_age_days: int | None,
) -> dict[str, Any]:
    canonical_id, canonical_state, pending_backfill_id = _effective_identity(row, fingerprint, backfill)
    website = _website_evidence(row, as_of=as_of, max_evidence_age_days=max_evidence_age_days)
    linkedin = _linkedin_evidence(row, as_of=as_of, max_evidence_age_days=max_evidence_age_days)
    ownership = _ownership_state(
        linkedin["numeric_id"],
        canonical_id,
        ownership_groups,
        ownership_reviews,
    )
    exclusions: list[str] = []
    if not canonical_id:
        exclusions.append(
            "canonical_id_backfill_pending_approval" if pending_backfill_id else "canonical_id_missing_or_placeholder"
        )
    exclusions.extend(website["reasons"])
    exclusions.extend(linkedin["reasons"])
    if ownership["status"] == "conflicting_unresolved":
        exclusions.append("conflicting_ownership_unresolved")
    website_eligible = bool(canonical_id and website["evidence_verified"] and ownership["status"] != "conflicting_unresolved")
    linkedin_eligible = bool(canonical_id and linkedin["evidence_verified"] and ownership["status"] != "conflicting_unresolved")
    if website_eligible and linkedin_eligible:
        decision = "dual_ready"
    elif website_eligible:
        decision = "website_only"
    elif linkedin_eligible:
        decision = "linkedin_only"
    else:
        decision = "blocked"
    return {
        "source_row_number": source_row_number,
        "row_fingerprint": fingerprint,
        "raw_sidecar_key": fingerprint,
        "company_name": _text(row.get("company_name")),
        "original_canonical_company_id": _value(row.get(MASTER_CANONICAL_ID_FIELD)),
        "canonical_company_id": canonical_id,
        "canonical_id_state": canonical_state,
        "pending_backfill_canonical_company_id": pending_backfill_id,
        "field_presence": {
            "canonical_id": bool(_value(row.get(MASTER_CANONICAL_ID_FIELD))),
            "website_url": bool(website["url"]["structurally_valid"]),
            "linkedin_url": bool(linkedin["url"]["structurally_valid"] and linkedin["url"]["host"] == "linkedin.com"),
            "numeric_linkedin_id": bool(linkedin["numeric_id_valid"]),
        },
        "website": website,
        "linkedin": linkedin,
        "ownership": ownership,
        "source_eligibility": {
            SOURCE_EMPLOYER: website_eligible,
            SOURCE_LINKEDIN: linkedin_eligible,
            "dual_source": bool(website_eligible and linkedin_eligible),
        },
        "decision": decision,
        "exclusion_reasons": list(dict.fromkeys(exclusions)),
        "review_required": bool(exclusions) or decision == "blocked",
        "entity_key": f"canonical:{canonical_id}" if canonical_id else f"unmapped:{fingerprint}",
    }


def _task_record(source: str, item: Mapping[str, Any], *, pilot_eligible: bool) -> dict[str, Any]:
    return {
        "task_key": f"{source}:{item['canonical_company_id']}",
        "source": source,
        "canonical_company_id": item["canonical_company_id"],
        "representative_source_row_number": item["source_row_number"],
        "representative_row_fingerprint": item["row_fingerprint"],
        "source_row_numbers": [item["source_row_number"]],
        "row_fingerprints": [item["row_fingerprint"]],
        "duplicate_association_count": 0,
        "pilot_eligible": pilot_eligible,
        "organization_associations": [],
    }


def _build_tasks(rows: Iterable[Mapping[str, Any]], pilot_entities: set[str]) -> list[dict[str, Any]]:
    tasks: dict[tuple[str, str], dict[str, Any]] = {}
    for item in rows:
        canonical_id = _text(item.get("canonical_company_id"))
        if not canonical_id:
            continue
        eligibility = item.get("source_eligibility")
        if not isinstance(eligibility, Mapping):
            continue
        for source in SOURCES:
            if not bool(eligibility.get(source)):
                continue
            key = (source, canonical_id)
            task = tasks.setdefault(
                key,
                _task_record(
                    source,
                    item,
                    pilot_eligible=item["entity_key"] in pilot_entities,
                ),
            )
            task["pilot_eligible"] = bool(task["pilot_eligible"] or item["entity_key"] in pilot_entities)
            if item["source_row_number"] != task["representative_source_row_number"]:
                task["duplicate_association_count"] += 1
            task["source_row_numbers"].append(item["source_row_number"])
            task["row_fingerprints"].append(item["row_fingerprint"])
            if source == SOURCE_LINKEDIN:
                org_id = _text(item["linkedin"].get("numeric_id"))
                existing_org = next(
                    (entry for entry in task["organization_associations"] if entry["linkedin_org_id"] == org_id),
                    None,
                )
                if existing_org is None:
                    task["organization_associations"].append(
                        {
                            "linkedin_org_id": org_id,
                            "representative_source_row_number": item["source_row_number"],
                            "representative_row_fingerprint": item["row_fingerprint"],
                            "ownership": item["ownership"],
                        }
                    )
    for task in tasks.values():
        task["source_row_numbers"] = sorted(set(task["source_row_numbers"]))
        task["row_fingerprints"] = sorted(set(task["row_fingerprints"]))
        task["organization_associations"] = sorted(
            task["organization_associations"], key=lambda item: item["linkedin_org_id"]
        )
    return [tasks[key] for key in sorted(tasks)]


def _manifest_hash(payload: Mapping[str, Any]) -> str:
    body = json.loads(json.dumps(payload, ensure_ascii=False))
    body.pop("manifest_hash", None)
    return _hash_json(body)


def build_source_eligibility_manifest(
    rows: Iterable[Mapping[str, Any]],
    fieldnames: Iterable[str],
    *,
    source_path: str = "",
    input_sha256: str = "",
    cycle_id: str = "",
    as_of: str | datetime | None = None,
    max_evidence_age_days: int | None = 30,
    registry_report: Mapping[str, Any] | None = None,
    backfill_report: Mapping[str, Any] | None = None,
    raw_sidecar_path: str = "",
) -> dict[str, Any]:
    """Build a deterministic eligibility snapshot without making network calls."""

    source_rows = [dict(row) for row in rows if isinstance(row, Mapping)]
    columns = list(fieldnames)
    as_of_datetime = _normalise_as_of(as_of)
    source_hash = _text(input_sha256)
    if not source_hash:
        source_hash = _hash_json(source_rows)
    cycle = _text(cycle_id) or f"cycle-{source_hash[:16]}"
    backfill = load_backfill_context(backfill_report)
    reviews = _ownership_reviews(registry_report)
    fingerprints = [_row_fingerprint(row) for row in source_rows]
    existing_by_org: dict[str, set[str]] = defaultdict(set)
    for row, fingerprint in zip(source_rows, fingerprints):
        canonical_id, _, _ = _effective_identity(row, fingerprint, backfill)
        linkedin_id = _normalise_numeric_id(row.get("linkedin_company_id"))
        if canonical_id and linkedin_id:
            existing_by_org[linkedin_id].add(canonical_id)
    decisions = [
        _row_decision(
            row,
            source_row_number=index,
            fingerprint=fingerprint,
            backfill=backfill,
            ownership_groups=existing_by_org,
            ownership_reviews=reviews,
            as_of=as_of_datetime,
            max_evidence_age_days=max_evidence_age_days,
        )
        for index, (row, fingerprint) in enumerate(zip(source_rows, fingerprints), start=2)
    ]
    organization_row_numbers: dict[str, list[int]] = defaultdict(list)
    for item in decisions:
        organization_id = _text((item.get("ownership") or {}).get("organization_id"))
        if organization_id:
            organization_row_numbers[organization_id].append(int(item["source_row_number"]))
    duplicate_fingerprints = Counter(fingerprints)
    entity_sources: dict[str, set[str]] = defaultdict(set)
    for item in decisions:
        for source in SOURCES:
            if item["source_eligibility"][source]:
                entity_sources[item["entity_key"]].add(source)
        entity_sources.setdefault(item["entity_key"], set())
    entity_categories = Counter()
    for sources in entity_sources.values():
        if sources == set(SOURCES):
            entity_categories["dual_ready_entities"] += 1
        elif sources:
            entity_categories["single_ready_entities"] += 1
            entity_categories["website_only_entities" if SOURCE_EMPLOYER in sources else "linkedin_only_entities"] += 1
        else:
            entity_categories["blocked_entities"] += 1
    pilot_entities = {
        entity_key
        for entity_key, sources in entity_sources.items()
        if sources == set(SOURCES)
    }
    tasks = _build_tasks(decisions, pilot_entities)
    decision_counts = Counter(item["decision"] for item in decisions)
    exclusion_counts = Counter(
        reason for item in decisions for reason in item["exclusion_reasons"]
    )
    field_presence_dual_rows = sum(
        bool(item["field_presence"]["website_url"] and item["field_presence"]["linkedin_url"] and item["field_presence"]["numeric_linkedin_id"])
        for item in decisions
    )
    evidence_verified_dual_rows = sum(
        bool(item["website"]["evidence_verified"] and item["linkedin"]["evidence_verified"])
        for item in decisions
    )
    mapped_ids = {item["canonical_company_id"] for item in decisions if item["canonical_company_id"]}
    mapped_rows = sum(bool(item["canonical_company_id"]) for item in decisions)
    source_associations = sum(
        bool(item["source_eligibility"].get(source)) for item in decisions for source in SOURCES
    )
    sidecar_records = [
        {
            "schema_version": RAW_SIDECAR_SCHEMA_VERSION,
            "source_row_number": item["source_row_number"],
            "row_fingerprint": item["row_fingerprint"],
            "raw_columns": source_rows[item["source_row_number"] - 2],
        }
        for item in decisions
    ]
    unknown_columns = [column for column in columns if column not in KNOWN_CONTRACT_COLUMNS]
    unexplained_columns = [column for column in columns if column.casefold().startswith("column")]
    header_sha256 = _hash_json(columns)
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "manifest_version": f"{SCHEMA_VERSION}:{source_hash[:16]}:{cycle}",
        "cycle_id": cycle,
        "manifest_id": f"source-eligibility-{source_hash[:16]}-{_hash_json(cycle)[:12]}",
        "manifest_hash": "",
        "source_snapshot": {
            "path": str(source_path),
            "input_sha256": source_hash,
            "rows": len(source_rows),
            "columns": len(columns),
            "header_sha256": header_sha256,
            "cycle_semantics": "immutable_snapshot; omission does not authorize historical absence closure",
        },
        "policy": {
            "as_of": as_of_datetime.isoformat().replace("+00:00", "Z") if as_of_datetime else "",
            "max_evidence_age_days": max_evidence_age_days,
            "website_evidence_statuses": sorted(WEBSITE_EVIDENCE_STATUSES),
            "linkedin_evidence_statuses": sorted(LINKEDIN_EVIDENCE_STATUSES),
            "pilot_requires": ["canonical_id", "website_source_eligible", "linkedin_source_eligible"],
            "identity_backfill": {
                "approval_status": backfill.get("approval_status", "dry_run"),
                "approved": bool(backfill.get("approved")),
                "approved_mapping_rows": len(backfill.get("approved_rows") or {}),
                "pending_mapping_rows": len(backfill.get("pending_rows") or {}),
            },
        },
        "raw_schema": {
            "schema_version": RAW_SIDECAR_SCHEMA_VERSION,
            "column_order": columns,
            "column_count": len(columns),
            "unknown_columns": unknown_columns,
            "unexplained_columns": unexplained_columns,
            "required_columns": list(REQUIRED_COLUMNS),
        },
        "raw_sidecar": {
            "path": str(raw_sidecar_path),
            "schema_version": RAW_SIDECAR_SCHEMA_VERSION,
            "rows": len(sidecar_records),
            "columns": len(columns),
            "sha256": "",
        },
        "counts": {
            "input_rows": len(source_rows),
            "input_columns": len(columns),
            "mapped_rows": mapped_rows,
            "mapped_entities": len(mapped_ids),
            "duplicate_rows": sum(max(0, count - 1) for count in duplicate_fingerprints.values()),
            "duplicate_associations": source_associations - len(tasks),
            "source_associations": source_associations,
            "tasks": len(tasks),
            "employer_tasks": sum(item["source"] == SOURCE_EMPLOYER for item in tasks),
            "linkedin_tasks": sum(item["source"] == SOURCE_LINKEDIN for item in tasks),
            "pilot_tasks": sum(bool(item["pilot_eligible"]) for item in tasks),
            "pilot_employer_tasks": sum(
                item["source"] == SOURCE_EMPLOYER and bool(item["pilot_eligible"]) for item in tasks
            ),
            "pilot_linkedin_tasks": sum(
                item["source"] == SOURCE_LINKEDIN and bool(item["pilot_eligible"]) for item in tasks
            ),
            "field_presence_dual_ready_rows": field_presence_dual_rows,
            "evidence_verified_dual_ready_rows": evidence_verified_dual_rows,
            "field_presence_potential_after_identity_rows": field_presence_dual_rows,
            **dict(entity_categories),
            "blocked_rows": decision_counts["blocked"],
            **{f"decision_{key}_rows": value for key, value in sorted(decision_counts.items())},
        },
        "deductions": {
            "exclusion_reason_counts": dict(sorted(exclusion_counts.items())),
            "field_presence_dual_ready_rows_not_evidence_verified": field_presence_dual_rows - evidence_verified_dual_rows,
            "evidence_verified_dual_rows_without_canonical_id": sum(
                bool(
                    item["website"]["evidence_verified"]
                    and item["linkedin"]["evidence_verified"]
                    and not item["canonical_company_id"]
                )
                for item in decisions
            ),
            "unresolved_ownership_rows": sum(
                item["ownership"]["status"] == "conflicting_unresolved" for item in decisions
            ),
            "stale_evidence_rows": sum(
                item["website"]["freshness"] == "stale" or item["linkedin"]["freshness"] == "stale"
                for item in decisions
            ),
        },
        "ownership_review": {
            "organization_groups": [
                {
                    "linkedin_org_id": org_id,
                    "canonical_company_ids": sorted(ids),
                    "review": {
                        **dict(reviews.get(org_id) or {}),
                        "source_row_numbers": sorted(set(organization_row_numbers.get(org_id, []))),
                        "row_count": len(set(organization_row_numbers.get(org_id, []))),
                    },
                    "status": "reviewed" if org_id in reviews and _text(reviews[org_id].get("disposition")) in REVIEWED_OWNERSHIP_DISPOSITIONS and not bool(reviews[org_id].get("review_required")) else "unresolved_or_not_shared",
                }
                for org_id, ids in sorted(existing_by_org.items())
                if len(ids) > 1
            ],
            "conflicting_organization_groups": sum(len(ids) > 1 for ids in existing_by_org.values()),
        },
        "rows": decisions,
        "tasks": tasks,
        "integrity": {
            "source_untouched": True,
            "application_tables_written": False,
            "historical_absence_closure_authorized": False,
            "all_input_rows_mapped_or_blocked": len(decisions) == len(source_rows),
            "eligible_tasks_have_one_canonical_id": all(
                bool(item["canonical_company_id"]) and item["canonical_company_id"].strip() for item in tasks
            ),
        },
    }
    manifest["manifest_hash"] = _manifest_hash(manifest)
    manifest["_raw_sidecar_records"] = sidecar_records
    return manifest


def _sidecar_bytes(records: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join((_canonical_json(record) + "\n").encode("utf-8") for record in records)


def write_manifest_bundle(
    manifest_path: str | Path,
    report: Mapping[str, Any],
    *,
    raw_sidecar_path: str | Path | None = None,
) -> dict[str, str]:
    """Persist the manifest and raw sidecar, refusing to mutate an existing cycle."""

    output = Path(manifest_path).resolve()
    sidecar = Path(raw_sidecar_path or report.get("raw_sidecar", {}).get("path") or output.with_suffix(".raw.jsonl")).resolve()
    private_records = report.get("_raw_sidecar_records")
    if not isinstance(private_records, list):
        raise ValueError("manifest report has no raw sidecar records")
    sidecar_payload = _sidecar_bytes(private_records)
    sidecar_hash = hashlib.sha256(sidecar_payload).hexdigest()
    manifest_payload = {key: value for key, value in report.items() if not str(key).startswith("_")}
    manifest_payload["raw_sidecar"] = {
        **dict(manifest_payload.get("raw_sidecar") or {}),
        "path": str(sidecar),
        "sha256": sidecar_hash,
        "bytes": len(sidecar_payload),
    }
    manifest_payload["manifest_hash"] = _manifest_hash(manifest_payload)
    encoded_manifest = (_canonical_json(manifest_payload) + "\n").encode("utf-8")
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing.get("manifest_hash") != manifest_payload["manifest_hash"]:
            raise FileExistsError(f"refusing to replace immutable manifest cycle: {output}")
        if sidecar.exists() and sidecar.read_bytes() != sidecar_payload:
            raise FileExistsError(f"refusing to replace immutable raw sidecar: {sidecar}")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(encoded_manifest)
    if sidecar.exists():
        if hashlib.sha256(sidecar.read_bytes()).hexdigest() != sidecar_hash:
            raise FileExistsError(f"raw sidecar hash mismatch: {sidecar}")
    else:
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_bytes(sidecar_payload)
    return {
        "manifest_path": str(output),
        "raw_sidecar_path": str(sidecar),
        "manifest_hash": manifest_payload["manifest_hash"],
        "raw_sidecar_sha256": sidecar_hash,
    }


def load_manifest(path: str | Path, *, verify_sidecar: bool = True) -> dict[str, Any]:
    """Load and integrity-check one immutable eligibility manifest."""

    manifest_path = Path(path).resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported eligibility manifest schema: {payload.get('schema_version')}")
    if payload.get("manifest_hash") != _manifest_hash(payload):
        raise ValueError("eligibility manifest hash mismatch")
    if verify_sidecar:
        raw_sidecar = payload.get("raw_sidecar") or {}
        recorded_sidecar_path = str(raw_sidecar.get("path") or "")
        sidecar_path = Path(recorded_sidecar_path)
        # A manifest can be restored on Linux even when its recorded path was
        # produced on Windows.  pathlib.Path follows the host OS, so a
        # Windows drive-qualified path is otherwise misclassified as a
        # relative path and joined to the manifest directory verbatim.
        recorded_path_is_absolute = sidecar_path.is_absolute() or PureWindowsPath(
            recorded_sidecar_path
        ).is_absolute()
        if not recorded_path_is_absolute:
            sidecar_path = manifest_path.parent / sidecar_path
        elif not sidecar_path.exists():
            # Historical manifests were generated on Windows and may retain
            # the creator's absolute path.  A restored immutable bundle keeps
            # the sidecar beside the manifest, so make that bundle portable
            # without changing the manifest's recorded provenance or hash.
            colocated = manifest_path.parent / sidecar_path.name
            if colocated.exists():
                sidecar_path = colocated
        if not sidecar_path.exists():
            raise FileNotFoundError(f"raw manifest sidecar is missing: {sidecar_path}")
        actual_hash = hashlib.sha256(sidecar_path.read_bytes()).hexdigest()
        if actual_hash != _text(raw_sidecar.get("sha256")):
            raise ValueError("raw manifest sidecar hash mismatch")
        payload["raw_sidecar"]["resolved_path"] = str(sidecar_path)
    return payload


def validate_manifest_for_source(
    payload: Mapping[str, Any], source: str, *, pilot_only: bool = True
) -> list[dict[str, Any]]:
    """Return eligible tasks for a source, rejecting a bypassed/invalid contract."""

    if source not in SOURCES:
        raise ValueError(f"unsupported source: {source}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("collector requires a versioned source-eligibility manifest")
    integrity = payload.get("integrity")
    if not isinstance(integrity, Mapping) or not integrity.get("eligible_tasks_have_one_canonical_id"):
        raise ValueError("eligibility manifest failed canonical-ID integrity checks")
    rows = payload.get("rows")
    tasks = payload.get("tasks")
    if not isinstance(rows, list) or not isinstance(tasks, list):
        raise ValueError("eligibility manifest is missing row/task records")
    eligible_rows = {
        _text(item.get("row_fingerprint")): item
        for item in rows
        if isinstance(item, Mapping) and _text(item.get("row_fingerprint"))
    }
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in tasks:
        if not isinstance(item, Mapping) or item.get("source") != source:
            continue
        if pilot_only and not bool(item.get("pilot_eligible")):
            continue
        task = dict(item)
        task_key = _text(task.get("task_key"))
        canonical_id = _value(task.get("canonical_company_id"))
        if not task_key or not canonical_id or task_key in seen:
            raise ValueError("eligibility manifest contains an invalid or duplicate collector task")
        fingerprints = task.get("row_fingerprints")
        if not isinstance(fingerprints, list) or not fingerprints:
            raise ValueError(f"task {task_key} has no source-row evidence")
        if not all(fingerprint in eligible_rows for fingerprint in fingerprints):
            raise ValueError(f"task {task_key} references a missing row record")
        if source == SOURCE_LINKEDIN and not task.get("organization_associations"):
            raise ValueError(f"LinkedIn task {task_key} has no reviewed organization association")
        seen.add(task_key)
        selected.append(task)
    return selected


def _read_sidecar(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    sidecar_path = Path(str((payload.get("raw_sidecar") or {}).get("resolved_path") or ""))
    if not sidecar_path.exists():
        raise FileNotFoundError(sidecar_path)
    result: dict[str, dict[str, Any]] = {}
    with sidecar_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("schema_version") != RAW_SIDECAR_SCHEMA_VERSION:
                raise ValueError(f"unsupported raw sidecar schema on line {line_number}")
            fingerprint = _text(record.get("row_fingerprint"))
            raw = record.get("raw_columns")
            if not fingerprint or not isinstance(raw, Mapping):
                raise ValueError(f"invalid raw sidecar record on line {line_number}")
            result[fingerprint] = {str(key): "" if value is None else str(value) for key, value in raw.items()}
    return result


def materialize_source_input(
    manifest: Mapping[str, Any],
    source: str,
    output_path: str | Path,
    *,
    pilot_only: bool = True,
) -> dict[str, Any]:
    """Create a source-specific CSV from eligible task representatives only."""

    tasks = validate_manifest_for_source(manifest, source, pilot_only=pilot_only)
    output = Path(output_path).resolve()
    source_path = Path(str((manifest.get("source_snapshot") or {}).get("path") or "")).resolve()
    if output == source_path:
        raise ValueError("manifest materialization cannot overwrite the master snapshot")
    sidecar = _read_sidecar(manifest)
    columns = list((manifest.get("raw_schema") or {}).get("column_order") or [])
    if MASTER_CANONICAL_ID_FIELD not in columns:
        raise ValueError(f"manifest raw schema is missing {MASTER_CANONICAL_ID_FIELD}")
    selected_rows: list[dict[str, str]] = []
    seen_associations: set[tuple[str, str]] = set()
    for task in tasks:
        associations = task.get("organization_associations") if source == SOURCE_LINKEDIN else None
        representatives = associations if isinstance(associations, list) and associations else [task]
        for association in representatives:
            fingerprint = _text(association.get("representative_row_fingerprint"))
            if not fingerprint:
                fingerprint = _text(task.get("representative_row_fingerprint"))
            raw = sidecar.get(fingerprint)
            if raw is None:
                raise ValueError(f"manifest task references missing raw row {fingerprint}")
            association_key = (task["task_key"], _text(association.get("linkedin_org_id")))
            if association_key in seen_associations:
                continue
            seen_associations.add(association_key)
            row = dict(raw)
            row[MASTER_CANONICAL_ID_FIELD] = task["canonical_company_id"]
            selected_rows.append(row)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in selected_rows:
            writer.writerow({column: row.get(column, "") for column in columns})
    return {
        "path": str(output),
        "source": source,
        "manifest_id": manifest.get("manifest_id", ""),
        "rows": len(selected_rows),
        "tasks": len(tasks),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }


def require_eligibility_manifest(
    path: str | Path, source: str, *, pilot_only: bool = True
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Entry-point guard used by both scheduled collector wrappers."""

    payload = load_manifest(path)
    return payload, validate_manifest_for_source(payload, source, pilot_only=pilot_only)


__all__ = [
    "MASTER_CANONICAL_ID_FIELD",
    "RAW_SIDECAR_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "SOURCE_EMPLOYER",
    "SOURCE_LINKEDIN",
    "build_source_eligibility_manifest",
    "load_backfill_context",
    "load_manifest",
    "materialize_source_input",
    "read_master_snapshot",
    "require_eligibility_manifest",
    "validate_manifest_for_source",
    "write_manifest_bundle",
]
