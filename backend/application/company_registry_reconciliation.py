"""Read-only reconciliation of the master company list with Runr identity state.

This module deliberately stops before RC-004.  It does not allocate canonical
company IDs, write aliases, or update application tables.  Its output is a
reviewable crosswalk proposal that keeps the master ID namespace separate from
the application's ``canonical_company_<uuid>`` namespace.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from backend.domain.company_identity import name_key, structural_url


SCHEMA_VERSION = "company_registry_reconciliation_v1"
MASTER_CANONICAL_ID_FIELD = "canonical_CompanyID"
MISSING_MARKERS = {"", "//", "null", "none", "nan", "n/a", "na"}
SHARED_ORG_DISPOSITIONS = (
    "same_entity_alias",
    "distinct_related_employers",
    "unresolved_conflict",
)
ORGANIZATION_PAGE_TYPES = {"company", "organization", "employer"}
NON_COMPANY_LINKEDIN_PAGE_TYPES = {"school", "showcase"}
COMPLETE_ENRICHMENT_STATUSES = {
    "complete",
    "completed",
    "enriched",
    "found",
    "success",
    "verified",
}
ENRICHMENT_FIELDS = (
    "companyenrich_id",
    "website_url",
    "description",
    "industry",
    "headquarters_country",
    "employee_count_range",
    "logo_url",
)


MASTER_FIELD_MAPPING: tuple[dict[str, Any], ...] = (
    {
        "master_fields": ["canonical_CompanyID"],
        "application_target": "crosswalk.master_canonical_id",
        "export_target": "canonical_company_id (only after reviewed mapping)",
        "source_precedence": "preserve_existing_master_reference",
        "provenance": "master_input",
        "notes": "Durable external reference; equality with company_id is not assumed.",
    },
    {
        "master_fields": ["company_name"],
        "application_target": "canonical_companies.canonical_name",
        "export_target": "employer/company display name",
        "source_precedence": "reviewed_canonical_name_then_master_observation",
        "provenance": "master_input",
        "notes": "Name is display/evidence only and never an automatic identity key.",
    },
    {
        "master_fields": ["company_name", "linkedin_slug"],
        "application_target": "canonical_company_aliases.alias_display/alias_key",
        "export_target": "historical/display alias where reviewed",
        "source_precedence": "append_reviewed_alias",
        "provenance": "master_input",
        "notes": "Rename candidates retain the established canonical company ID.",
    },
    {
        "master_fields": [
            "merge_basis",
            "linkedin_page_type",
            "linkedin_company_id_status",
            "linkedin_company_id_source",
            "linkedin_company_id_confidence",
            "linkedin_company_id_resolved_at",
            "linkedin_company_id_transport",
            "linkedin_company_id_url_used",
        ],
        "application_target": "company_identity_evidence.evidence_json/link_state/review_required",
        "export_target": "identity evidence and review state",
        "source_precedence": "retain_provenance_and_review_state",
        "provenance": "master_input and resolver evidence",
        "notes": "A resolved source ID remains reviewable when ownership conflicts.",
    },
    {
        "master_fields": ["linkedin_company_id"],
        "application_target": "company_identity_keys.identity_key and company_identity_evidence",
        "export_target": "source organization identity, not canonical_company_id",
        "source_precedence": "reviewed_source_identity_then_review",
        "provenance": "master_input plus source evidence",
        "notes": "Shared organization IDs require observation-level ownership review.",
    },
    {
        "master_fields": ["companyenrich_id"],
        "application_target": "company_identity_keys.identity_key/company_identity_evidence",
        "export_target": "enrichment provenance, not employer ownership by itself",
        "source_precedence": "reviewed_external_identity_then_review",
        "provenance": "companyenrich evidence",
        "notes": "Missing enrichment never implies missing identity.",
    },
    {
        "master_fields": ["website_url"],
        "application_target": "canonical_company_urls and canonical_company_url_occurrences (homepage)",
        "export_target": "company website/source URL after validation",
        "source_precedence": "reviewed_official_url_then_observed_url",
        "provenance": "master_input plus URL validation",
        "notes": "A shared ATS/hosting domain is evidence, not ownership.",
    },
    {
        "master_fields": ["linkedin_company_url"],
        "application_target": "canonical_company_urls and canonical_company_url_occurrences (source)",
        "export_target": "source profile provenance",
        "source_precedence": "reviewed_organization_profile_then_review",
        "provenance": "master_input plus source validation",
        "notes": "School/showcase URLs are quarantined from employer acquisition.",
    },
    {
        "master_fields": ["enrichment_status", "website_discovery_status", *ENRICHMENT_FIELDS],
        "application_target": "canonical_company_profiles.profile_json/profile_status",
        "export_target": "profile/enrichment fields with field-level provenance",
        "source_precedence": "stronger_verified_field_then_richer_observation",
        "provenance": "master_input/companyenrich/discovery evidence",
        "notes": "Enrichment state is independent from identity and eligibility.",
    },
    {
        "master_fields": ["Column1", "Column2", "Column3", "Column4", "Column5", "Column6", "Column7", "Column8", "Column9"],
        "application_target": "raw-column sidecar/provenance (not silently dropped)",
        "export_target": "preserved input fields",
        "source_precedence": "retain_raw_value",
        "provenance": "master_input",
        "notes": "Unexplained columns remain available for later review.",
    },
)


def _field_mapping_for_columns(columns: Iterable[str]) -> list[dict[str, Any]]:
    """Expand grouped policy into one explicit disposition per input column."""

    selected_columns = set(columns)
    grouped: dict[str, dict[str, Any]] = {
        field: {
            "master_field": field,
            "application_target": mapping["application_target"],
            "export_target": mapping["export_target"],
            "source_precedence": mapping["source_precedence"],
            "provenance": mapping["provenance"],
        }
        for mapping in MASTER_FIELD_MAPPING
        for field in mapping["master_fields"]
    }
    profile_prefixes = (
        "categories_",
        "employee_count",
        "headquarters_",
        "industries_",
        "keywords_",
        "locations_",
        "naics_codes_",
        "technologies_",
    )
    profile_fields = {
        "company_type",
        "description",
        "founded_year",
        "industry",
        "logo_source",
        "page_rank",
        "record_sources",
        "revenue_range",
        "seo_description",
    }
    for field in selected_columns:
        if field in grouped:
            continue
        if field == "companyenrich_free_logo_url":
            grouped[field] = {
                "master_field": field,
                "application_target": "company_logo_enrichments.source_url/provenance_json",
                "export_target": "logo provenance after terms/URL review",
                "source_precedence": "retain_reviewed_logo_evidence",
                "provenance": "free_logo_observation",
            }
        elif field.startswith(profile_prefixes) or field in profile_fields:
            grouped[field] = {
                "master_field": field,
                "application_target": "canonical_company_profiles.profile_json",
                "export_target": "company profile field with provenance",
                "source_precedence": "stronger_verified_field_then_richer_observation",
                "provenance": "master_input/companyenrich evidence",
            }
        elif field == "website_discovery_status":
            grouped[field] = {
                "master_field": field,
                "application_target": "company_identity_evidence.evidence_json and canonical_company_urls",
                "export_target": "website discovery/review status",
                "source_precedence": "retain_discovery_evidence_until_url_review",
                "provenance": "website_discovery",
            }
        elif field in {"enrichment_status", "last_enriched_at"}:
            grouped[field] = {
                "master_field": field,
                "application_target": "canonical_company_profiles.profile_json/profile_status",
                "export_target": "enrichment lifecycle metadata",
                "source_precedence": "retain_status_and_observed_at",
                "provenance": "companyenrich evidence",
            }
        else:
            grouped[field] = {
                "master_field": field,
                "application_target": "raw-column sidecar/provenance",
                "export_target": "preserved input field",
                "source_precedence": "retain_raw_value",
                "provenance": "master_input",
            }
    return [grouped[field] for field in sorted(grouped) if field in selected_columns]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _value(value: Any) -> str:
    candidate = _text(value)
    return "" if candidate.casefold() in MISSING_MARKERS else candidate


def _truthy(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y", "reviewed", "approved"}


def _normalise_numeric_id(value: Any) -> str:
    candidate = _value(value)
    if not candidate or not candidate.isascii() or not candidate.isdecimal():
        return ""
    return str(int(candidate, 10))


def _url_details(value: Any) -> dict[str, str]:
    original, canonical, reason = structural_url(value)
    host = ""
    path = ""
    if canonical:
        parsed = urlsplit(canonical)
        host = (parsed.hostname or "").casefold().removeprefix("www.")
        path = parsed.path or "/"
    return {"original": original, "canonical": canonical, "host": host, "path": path, "reason": reason}


def _linkedin_page_type(row: Mapping[str, Any], url: Mapping[str, str]) -> str:
    explicit = _value(row.get("linkedin_page_type")).casefold()
    if explicit:
        return explicit
    parts = [part for part in url.get("path", "").casefold().split("/") if part]
    if parts and parts[0] in NON_COMPANY_LINKEDIN_PAGE_TYPES:
        return parts[0]
    if parts and parts[0] == "company":
        return "company"
    return "unknown"


def _row_fingerprint(row: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalise_registry(application_registry: Mapping[str, Any] | None) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    registry = application_registry or {}
    identity_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    companies: dict[str, dict[str, Any]] = {}
    for item in registry.get("companies", ()):
        if not isinstance(item, Mapping):
            continue
        company_id = _text(item.get("company_id"))
        if company_id:
            companies[company_id] = dict(item)
    for item in registry.get("identity_keys", ()):
        if not isinstance(item, Mapping):
            continue
        identity_key = _text(item.get("identity_key"))
        company_id = _text(item.get("company_id"))
        if not identity_key or not company_id:
            continue
        record = dict(item)
        record["company_id"] = company_id
        evidence = record.get("evidence")
        if not isinstance(evidence, Mapping):
            evidence = record.get("evidence_json") if isinstance(record.get("evidence_json"), Mapping) else {}
        record["reviewed"] = bool(record.get("reviewed")) or _truthy(evidence.get("reviewed"))
        identity_by_key[identity_key].append(record)
    for item in registry.get("aliases", ()):
        if not isinstance(item, Mapping):
            continue
        alias_key = _text(item.get("alias_key"))
        company_id = _text(item.get("company_id"))
        if alias_key and company_id:
            record = companies.setdefault(company_id, {"company_id": company_id})
            record.setdefault("aliases", []).append(alias_key)
    return dict(identity_by_key), companies


def _review_disposition(
    org_id: str,
    master_ids: list[str],
    dispositions: Mapping[str, Any] | None,
) -> dict[str, Any]:
    supplied = dispositions.get(org_id) if isinstance(dispositions, Mapping) else None
    if not isinstance(supplied, Mapping):
        return {
            "disposition": "unresolved_conflict",
            "review_required": True,
            "reason": "aggregate_or_source_rows_do_not_contain_a_reviewed_ownership_decision",
            "reviewer": "",
            "evidence": [],
        }
    disposition = _text(supplied.get("disposition"))
    reviewed_ids = sorted({_text(item) for item in supplied.get("master_ids", ()) if _text(item)})
    if disposition not in SHARED_ORG_DISPOSITIONS or reviewed_ids != sorted(master_ids):
        return {
            "disposition": "unresolved_conflict",
            "review_required": True,
            "reason": "invalid_or_incomplete_review_annotation",
            "reviewer": _text(supplied.get("reviewer")),
            "evidence": list(supplied.get("evidence", ())) if isinstance(supplied.get("evidence"), list) else [],
        }
    return {
        "disposition": disposition,
        "review_required": disposition == "unresolved_conflict",
        "reason": "reviewed_explicitly" if disposition != "unresolved_conflict" else "reviewed_as_unresolved_conflict",
        "reviewer": _text(supplied.get("reviewer")),
        "evidence": list(supplied.get("evidence", ())) if isinstance(supplied.get("evidence"), list) else [],
    }


def _enrichment_state(row: Mapping[str, Any]) -> tuple[str, list[str], list[str]]:
    present = [field for field in ENRICHMENT_FIELDS if _value(row.get(field))]
    missing = [field for field in ENRICHMENT_FIELDS if field not in present]
    status = _value(row.get("enrichment_status")).casefold()
    discovery = _value(row.get("website_discovery_status")).casefold()
    if status in COMPLETE_ENRICHMENT_STATUSES and present:
        return "complete", present, missing
    if present or discovery in {"found", "verified", "complete"}:
        return "partial", present, missing
    return "missing", present, missing


def _identity_keys_for_row(row: Mapping[str, Any], website: Mapping[str, str], page_type: str) -> list[dict[str, str]]:
    keys: list[dict[str, str]] = []
    linkedin_id = _normalise_numeric_id(row.get("linkedin_company_id"))
    if linkedin_id and page_type not in NON_COMPANY_LINKEDIN_PAGE_TYPES:
        keys.append({"identity_key": f"linkedin-org:{linkedin_id}", "identity_type": "linkedin_org_id"})
    companyenrich_id = _value(row.get("companyenrich_id"))
    if companyenrich_id:
        keys.append({"identity_key": f"companyenrich:{companyenrich_id}", "identity_type": "companyenrich_id"})
    if website.get("host"):
        keys.append({"identity_key": f"domain:{website['host']}", "identity_type": "verified_official_domain"})
    return keys


def reconcile_master_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    application_registry: Mapping[str, Any] | None = None,
    shared_organization_dispositions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic, non-mutating master-to-application review report."""

    source_rows = [dict(row) for row in rows if isinstance(row, Mapping)]
    identity_by_key, application_companies = _normalise_registry(application_registry)
    shared_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    prepared: list[dict[str, Any]] = []
    all_columns: set[str] = set()

    for index, row in enumerate(source_rows, start=2):
        all_columns.update(row)
        website = _url_details(row.get("website_url"))
        linkedin_url = _url_details(row.get("linkedin_company_url"))
        page_type = _linkedin_page_type(row, linkedin_url)
        master_id = _value(row.get(MASTER_CANONICAL_ID_FIELD))
        linkedin_id = _normalise_numeric_id(row.get("linkedin_company_id"))
        if linkedin_id and master_id:
            shared_groups[linkedin_id].append({"row_number": index, "master_id": master_id})
        enrichment_state, enrichment_present, enrichment_missing = _enrichment_state(row)
        identity_keys = _identity_keys_for_row(row, website, page_type)
        prepared.append(
            {
                "source_row_number": index,
                "row_fingerprint": _row_fingerprint(row),
                "raw": row,
                "master_canonical_id": master_id,
                "master_external_key": f"master-company:{master_id}" if master_id else "",
                "canonical_name": _text(row.get("company_name")),
                "name_key": name_key(row.get("company_name")),
                "website": website,
                "linkedin_url": linkedin_url,
                "linkedin_page_type": page_type,
                "linkedin_org_id": linkedin_id,
                "identity_keys": identity_keys,
                "enrichment_state": enrichment_state,
                "enrichment_fields_present": enrichment_present,
                "missing_enrichment_fields": enrichment_missing,
            }
        )

    shared_dispositions: list[dict[str, Any]] = []
    shared_by_id: dict[str, dict[str, Any]] = {}
    for org_id, group_rows in sorted(shared_groups.items()):
        master_ids = sorted({item["master_id"] for item in group_rows if item["master_id"]})
        if len(master_ids) < 2:
            continue
        disposition = _review_disposition(org_id, master_ids, shared_organization_dispositions)
        group = {
            "linkedin_org_id": org_id,
            "master_canonical_ids": master_ids,
            "source_row_numbers": sorted(item["row_number"] for item in group_rows),
            "row_count": len(group_rows),
            **disposition,
            "ownership_rule": "do_not_assign_by_sort_order_or_fan_observations_to_all_employers",
        }
        shared_dispositions.append(group)
        shared_by_id[org_id] = group

    rows_out: list[dict[str, Any]] = []
    alias_candidates: dict[str, set[str]] = defaultdict(set)
    website_candidates: dict[str, set[str]] = defaultdict(set)
    for item in prepared:
        master_id = item["master_canonical_id"]
        if master_id and item["canonical_name"]:
            alias_candidates[master_id].add(item["canonical_name"])
        if master_id and item["website"]["canonical"]:
            website_candidates[master_id].add(item["website"]["canonical"])

        candidate_application_ids: set[str] = set()
        matched_identity_keys: list[str] = []
        unreviewed_identity_keys: list[str] = []
        for identity in item["identity_keys"]:
            records = identity_by_key.get(identity["identity_key"], [])
            if records:
                if any(record.get("reviewed") for record in records):
                    candidate_application_ids.update(str(record["company_id"]) for record in records)
                    matched_identity_keys.append(identity["identity_key"])
                else:
                    unreviewed_identity_keys.append(identity["identity_key"])
        names = {item["name_key"]} if item["name_key"] else set()
        for company_id, company in application_companies.items():
            company_names = {name_key(company.get("canonical_name")), *[name_key(alias) for alias in company.get("aliases", [])]}
            if names & {candidate for candidate in company_names if candidate}:
                candidate_application_ids.add(company_id)

        shared = shared_by_id.get(item["linkedin_org_id"])
        non_company_page = item["linkedin_page_type"] in NON_COMPANY_LINKEDIN_PAGE_TYPES
        if non_company_page:
            decision, reason, review_required = "quarantined", "non_company_linkedin_page", True
        elif shared and shared["disposition"] == "unresolved_conflict":
            decision, reason, review_required = "quarantined", "shared_linkedin_org_ownership_unresolved", True
        elif shared:
            decision, reason, review_required = "review", "shared_linkedin_org_requires_observation_level_ownership", True
        elif len(candidate_application_ids) > 1:
            decision, reason, review_required = "review", "multiple_application_companies_match_strong_keys", True
        elif len(candidate_application_ids) == 1 and matched_identity_keys and not unreviewed_identity_keys:
            decision, reason, review_required = "matched", "reviewed_strong_identity_key", False
        elif unreviewed_identity_keys:
            decision, reason, review_required = "review", "strong_identity_key_not_reviewed", True
        elif candidate_application_ids:
            decision, reason, review_required = "review", "name_or_alias_match_requires_review", True
        elif master_id or item["identity_keys"]:
            decision, reason, review_required = "provisional", "external_reference_without_proven_application_mapping", True
        else:
            decision, reason, review_required = "provisional", "missing_identity_evidence", True

        application_id = next(iter(candidate_application_ids)) if decision == "matched" else ""
        durable_identity_evidence = bool(
            master_id
            or (item["linkedin_org_id"] and not non_company_page)
            or (decision == "matched" and application_id)
        )
        identity_state = "conflicted" if shared else "present" if durable_identity_evidence else "missing"
        urls = []
        if item["website"]["original"]:
            urls.append(
                {
                    "master_field": "website_url",
                    "application_table": "canonical_company_urls/canonical_company_url_occurrences",
                    "url_type": "homepage",
                    "canonical_url": item["website"]["canonical"],
                    "lifecycle": "discovered" if item["website"]["canonical"] else "invalid",
                    "provenance": "master_input",
                }
            )
        if item["linkedin_url"]["original"]:
            urls.append(
                {
                    "master_field": "linkedin_company_url",
                    "application_table": "canonical_company_urls/canonical_company_url_occurrences",
                    "url_type": "source",
                    "canonical_url": item["linkedin_url"]["canonical"],
                    "lifecycle": "rejected" if non_company_page else "discovered",
                    "provenance": "master_input",
                    "validation_reason": "non_company_linkedin_page" if non_company_page else "",
                }
            )
        rows_out.append(
            {
                "source_row_number": item["source_row_number"],
                "row_fingerprint": item["row_fingerprint"],
                "master_canonical_id": master_id,
                "master_external_key": item["master_external_key"],
                "application_company_id": application_id,
                "candidate_application_company_ids": sorted(candidate_application_ids),
                "canonical_name": item["canonical_name"],
                "linkedin_org_id": item["linkedin_org_id"],
                "linkedin_page_type": item["linkedin_page_type"],
                "identity_keys": item["identity_keys"],
                "matched_identity_keys": sorted(matched_identity_keys),
                "identity_state": identity_state,
                "enrichment_state": item["enrichment_state"],
                "enrichment_fields_present": item["enrichment_fields_present"],
                "missing_enrichment_fields": item["missing_enrichment_fields"],
                "registry_decision": decision,
                "decision_reason": reason,
                "review_required": review_required,
                "eligible_for_acquisition_or_publication": False,
                "eligibility_reason": "deferred_to_versioned_source_eligibility_manifest",
                "urls": urls,
                "raw_fields_preserved": sorted(item["raw"]),
            }
        )

    alias_report = [
        {
            "master_canonical_id": master_id,
            "observed_names": sorted(names),
            "decision": "preserve_id_review_alias" if len(names) > 1 else "no_rename_observed",
            "review_required": len(names) > 1,
            "rule": "never_replace_established_id_for_a_rename",
        }
        for master_id, names in sorted(alias_candidates.items())
    ]
    website_report = [
        {
            "master_canonical_id": master_id,
            "observed_websites": sorted(urls),
            "decision": "append_url_occurrence_review_primary" if len(urls) > 1 else "retain_observed_url",
            "review_required": len(urls) > 1,
            "rule": "changed_websites_are_evidence_history_not_id_replacement",
        }
        for master_id, urls in sorted(website_candidates.items())
    ]
    field_mapping = _field_mapping_for_columns(all_columns)
    semantic_fields = {
        item["master_field"]
        for item in field_mapping
        if not item["application_target"].startswith("raw-column sidecar")
    }
    counts = {
        "rows": len(rows_out),
        "master_canonical_ids_present": sum(bool(row["master_canonical_id"]) for row in rows_out),
        "master_canonical_ids_missing": sum(not row["master_canonical_id"] for row in rows_out),
        "application_companies_matched": sum(bool(row["application_company_id"]) for row in rows_out),
        "identity_state_present": sum(row["identity_state"] == "present" for row in rows_out),
        "identity_state_missing": sum(row["identity_state"] == "missing" for row in rows_out),
        "identity_state_conflicted": sum(row["identity_state"] == "conflicted" for row in rows_out),
        "enrichment_state_complete": sum(row["enrichment_state"] == "complete" for row in rows_out),
        "enrichment_state_partial": sum(row["enrichment_state"] == "partial" for row in rows_out),
        "enrichment_state_missing": sum(row["enrichment_state"] == "missing" for row in rows_out),
        "registry_decision_matched": sum(row["registry_decision"] == "matched" for row in rows_out),
        "registry_decision_review": sum(row["registry_decision"] == "review" for row in rows_out),
        "registry_decision_provisional": sum(row["registry_decision"] == "provisional" for row in rows_out),
        "registry_decision_quarantined": sum(row["registry_decision"] == "quarantined" for row in rows_out),
        "review_required": sum(bool(row["review_required"]) for row in rows_out),
        "shared_organization_groups": len(shared_dispositions),
        "shared_organization_rows": sum(group["row_count"] for group in shared_dispositions),
        "rename_groups": sum(item["review_required"] for item in alias_report),
        "changed_website_groups": sum(item["review_required"] for item in website_report),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "read_only": True,
        "writes_application_tables": False,
        "allocates_application_ids": False,
        "automatic_merge": False,
        "automatic_publication": False,
        "master_id_namespace": "master canonical_CompanyID",
        "application_id_namespace": "canonical_company_<uuid>",
        "application_id_equality_proven": False,
        "source_precedence": list(MASTER_FIELD_MAPPING),
        "field_mapping": field_mapping,
        "input_columns": sorted(all_columns),
        "unknown_input_columns": sorted(all_columns - semantic_fields),
        "counts": counts,
        "shared_organization_dispositions": shared_dispositions,
        "rename_and_alias_review": alias_report,
        "website_history_review": website_report,
        "rows": rows_out,
    }


def summarise_registry_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Remove row-level data while preserving evidence needed for an audit."""

    return {
        key: value
        for key, value in report.items()
        if key not in {"rows"}
    }


def read_master_csv(path: str | Path) -> tuple[list[dict[str, str]], list[str], str]:
    """Read an explicit UTF-8 CSV path and return rows, header and SHA-256."""

    import csv

    source = Path(path)
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]
        return rows, list(reader.fieldnames or []), digest.hexdigest()


__all__ = [
    "MASTER_FIELD_MAPPING",
    "SCHEMA_VERSION",
    "SHARED_ORG_DISPOSITIONS",
    "read_master_csv",
    "reconcile_master_rows",
    "summarise_registry_report",
]
