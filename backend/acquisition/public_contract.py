"""Typed, backward-compatible projections for acquisition read models.

The acquisition pipeline stores a richer evidence-first mapping than the
personalized Jobs API currently exposes.  This module is the adapter boundary
for a later route integration: it reads canonical mapping values, keeps legacy
fields untouched, and adds a namespaced ``typed`` projection.

The module deliberately does not persist, query, or mutate data.  Public
serialization contains typed values only.  ``build_field_lineage`` can expose
bounded evidence to an explicitly selected admin consumer, but never includes
raw payloads in the public contract.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypedDict

from backend.acquisition.rule_registry import canonical_field_state
from backend.acquisition.unified_mapping import UNIFIED_RULE_VERSION, map_job_fields


PUBLIC_TYPED_CONTRACT_VERSION = "public_typed_contract_v1"
PUBLIC_CONTRACT_RULE_VERSION = "public_contract_v1"
TYPED_CONTRACT_KEY = "typed"
_PUBLIC_ADMIN_ONLY_KEYS = frozenset({
    "source_raw_payload", "raw_payload", "raw_payload_json", "payload_json", "unified_mapping",
    "normalized_mapping", "normalized_source_metadata", "field_provenance", "observation_payloads",
    "version_payload_json", "raw_value", "evidence",
})

TYPED_FIELD_NAMES = (
    "runr_function",
    "runr_subfunction",
    "source_department",
    "source_team",
    "source_category",
    "employment_type",
    "workplace_arrangement",
    "remote_geographic_restrictions",
    "locations",
    "languages",
    "experience",
    "salary",
    "work_authorization",
    "sponsorship",
    "application_destination",
    "application_method",
    "application_status",
    "timestamp_semantics",
    "completeness",
    "warnings",
    "freshness",
    "duplicate",
    "logo",
    "enrichment",
    "publication_state",
)

_UNKNOWN = {"", "n/a", "na", "none", "not available", "not disclosed", "unknown", "undisclosed"}
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "runr_function": ("function", "category_function"),
    "runr_subfunction": ("subfunction", "sub_function"),
    "source_department": ("department", "department_name"),
    "source_team": ("team", "team_name"),
    "source_category": ("category", "job_category", "role_category"),
    "employment_type": ("employmentType", "job_type", "type", "commitment"),
    "workplace_arrangement": ("work_arrangement", "workplace", "workplace_type", "workplaceType", "remote_type"),
    "remote_geographic_restrictions": ("remote_scope", "remote_restrictions", "remote_geography"),
    "locations": ("location_collection", "location", "location_raw", "locations_raw"),
    "languages": ("language_requirements", "language", "required_languages", "preferred_languages"),
    "experience": ("experience_requirements", "experience_level", "seniority", "experience"),
    "salary": ("salary_range", "compensation", "pay"),
    "work_authorization": ("authorization", "work_permit", "visa_requirement"),
    "sponsorship": ("visa_sponsorship", "sponsors_h1b", "sponsorship_requirement"),
    "application_destination": ("application",),
    "timestamp_semantics": ("source_timestamps", "timestamps"),
    "completeness": ("quality_completeness", "quality", "completeness_report"),
    "warnings": ("quality_warnings", "warning_codes", "warning_type"),
    "freshness": ("freshness_state", "last_verified_at", "last_seen_at"),
    "duplicate": ("duplicate_state", "duplicate_status", "duplicate_review"),
    "logo": ("logo_url", "company_logo"),
    "enrichment": ("company_enrichment",),
    "publication_state": ("publication", "published_state", "is_live"),
}

_FILTER_ALIASES = {
    "function": "runr_function",
    "role": "runr_function",
    "subfunction": "runr_subfunction",
    "department": "source_department",
    "team": "source_team",
    "category": "source_category",
    "work_arrangement": "workplace_arrangement",
    "workplace": "workplace_arrangement",
    "locations": "location",
    "languages": "language",
    "warning": "warnings",
    "warning_type": "warnings",
    "duplicate_state": "duplicate",
    "publication": "publication_state",
    "application": "application_method",
    "application_status": "application_status",
    "completeness_state": "completeness",
    "freshness_state": "freshness",
    "seniority": "experience_seniority",
    "source": "source",
    "experience_min": "experience_minimum_years",
    "minimum_experience": "experience_minimum_years",
    "experience_max": "experience_maximum_years",
    "maximum_experience": "experience_maximum_years",
    "salary_min": "salary_minimum",
    "salary_max": "salary_maximum",
    "workAuthorization": "work_authorization",
    "workplaceArrangement": "workplace_arrangement",
    "workArrangement": "workplace_arrangement",
    "runrFunction": "runr_function",
    "runrSubfunction": "runr_subfunction",
    "sourceDepartment": "source_department",
    "sourceTeam": "source_team",
    "sourceCategory": "source_category",
    "employmentType": "employment_type",
    "remoteGeographicRestrictions": "remote_geographic_restrictions",
    "applicationMethod": "application_method",
    "publicationState": "publication_state",
}


class TypedContract(TypedDict, total=False):
    schema_version: str
    rule_version: str
    mapping_rule_version: str
    runr_function: str | None
    runr_subfunction: str | None
    source_department: str | None
    source_team: str | None
    source_category: str | None
    employment_type: str | None
    workplace_arrangement: str | None
    remote_geographic_restrictions: list[str]
    locations: list[dict[str, Any]]
    languages: list[dict[str, Any]]
    experience: dict[str, Any]
    salary: dict[str, Any]
    work_authorization: list[dict[str, Any]]
    sponsorship: str | None
    application_destination: dict[str, Any]
    application_method: str
    application_status: str
    timestamp_semantics: dict[str, Any]
    completeness: dict[str, Any]
    warnings: list[str]
    freshness: dict[str, Any]
    duplicate: dict[str, Any]
    logo: dict[str, Any]
    enrichment: dict[str, Any]
    publication_state: str
    field_states: dict[str, str]
    company: dict[str, Any]


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and value.strip().casefold() not in _UNKNOWN
    if isinstance(value, (Mapping, Sequence)) and not isinstance(value, (str, bytes, bytearray)):
        return bool(value)
    return True


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _text(value).casefold()).strip("_")


def _number(value: Any) -> int | float | None:
    if value is None or value == "" or value is False:
        return None
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value]


def _views(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    views = [payload]
    nested = payload.get("job")
    if isinstance(nested, Mapping):
        views.append(nested)
    return views


def _direct_value(payload: Mapping[str, Any], *names: str) -> Any:
    for view in _views(payload):
        for name in names:
            value = view.get(name)
            if _present(value):
                return value
    return None


def _record_value(record: Mapping[str, Any]) -> Any:
    for key in ("normalized_value", "value", "raw_value"):
        if key in record and _present(record.get(key)):
            return record.get(key)
    return None


def _mapping_and_fields(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    mapping = payload.get("unified_mapping")
    if not isinstance(mapping, Mapping):
        mapping = payload.get("normalized_mapping")
    if not isinstance(mapping, Mapping):
        try:
            mapping = map_job_fields(
                payload,
                observed_at=_text(payload.get("observed_at") or payload.get("observation_timestamp")),
                source_observation_id=_text(payload.get("source_observation_id") or payload.get("observation_id")),
                source=_text(payload.get("source_ats") or payload.get("source")),
            )
        except (TypeError, ValueError):
            mapping = {}
    fields = mapping.get("fields") if isinstance(mapping, Mapping) else None
    if not isinstance(fields, Mapping):
        fields = payload.get("field_provenance") or payload.get("fields") or {}
    return mapping, fields if isinstance(fields, Mapping) else {}


def _field_record(
    payload: Mapping[str, Any],
    fields: Mapping[str, Any],
    name: str,
) -> tuple[Any, Mapping[str, Any] | None]:
    candidates = (name, *_FIELD_ALIASES.get(name, ()))
    metadata = payload.get("normalized_source_metadata")
    metadata_fields = metadata.get("fields") if isinstance(metadata, Mapping) else {}
    if not isinstance(metadata_fields, Mapping):
        metadata_fields = {}
    for candidate in candidates:
        record = fields.get(candidate)
        if isinstance(record, Mapping):
            value = _record_value(record)
            if value is not None:
                return value, record
        record = metadata_fields.get(candidate)
        if isinstance(record, Mapping):
            value = _record_value(record)
            if value is not None:
                return value, record
    direct = _direct_value(payload, *candidates)
    return direct, None


def _state(record: Mapping[str, Any] | None, value: Any) -> str:
    if record is not None:
        return canonical_field_state(record.get("state"), default="present" if _present(value) else "unknown")
    return "present" if _present(value) else "unknown"


def _taxonomy(value: Any, aliases: Mapping[str, str]) -> str | None:
    if not _present(value):
        return None
    normalized = _key(value)
    return aliases.get(normalized, _text(value))


_FUNCTION_ALIASES = {
    "engineering": "Engineering", "data": "Data", "product": "Product", "design": "Design",
    "marketing": "Marketing", "sales": "Sales", "customer_support": "Customer Support",
    "operations": "Operations", "finance": "Finance", "legal": "Legal",
    "risk_and_compliance": "Risk and Compliance", "people": "People", "security": "Security",
    "executive": "Executive", "other": "Other", "unclassified": "Unclassified",
}
_EMPLOYMENT_ALIASES = {
    "full_time": "Full-time", "fulltime": "Full-time", "part_time": "Part-time", "parttime": "Part-time",
    "contract": "Contract", "temporary": "Temporary", "internship": "Internship", "intern": "Internship",
    "apprenticeship": "Apprenticeship", "freelance": "Freelance", "working_student": "Working student",
}
_WORKPLACE_ALIASES = {
    "remote": "Remote", "fully_remote": "Remote", "home_office": "Remote", "hybrid": "Hybrid",
    "onsite": "On-site", "on_site": "On-site", "office": "On-site", "flexible": "Flexible",
}


def _canonical_strings(value: Any) -> list[str]:
    result: list[str] = []
    for item in _as_list(value):
        if isinstance(item, Mapping):
            nested = item.get("countries") or item.get("regions") or item.get("values")
            if nested:
                for nested_item in _canonical_strings(nested):
                    if _key(nested_item) not in {_key(existing) for existing in result}:
                        result.append(nested_item)
                continue
            item = item.get("value") or item.get("name") or item.get("label") or item.get("code")
        text = _text(item)
        if text and text.casefold() not in {item.casefold() for item in result}:
            result.append(text)
    return result


def _location_record(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        label = _text(value.get("label") or value.get("name") or value.get("location") or value.get("value"))
        record = {
            "label": label or None,
            "city": _text(value.get("city")) or None,
            "region": _text(value.get("region") or value.get("state")) or None,
            "country": _text(value.get("country")) or None,
            "country_code": _text(value.get("country_code") or value.get("countryCode")).upper() or None,
        }
        if not any(record.values()):
            return None
        return record
    label = _text(value)
    return {"label": label, "city": None, "region": None, "country": None, "country_code": None} if label else None


def _locations(value: Any) -> list[dict[str, Any]]:
    values = _as_list(value)
    if len(values) == 1 and isinstance(values[0], str):
        values = [item for item in re.split(r"[;\n]", values[0]) if _text(item)]
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in values:
        record = _location_record(item)
        if record is None:
            continue
        identity = json.dumps(record, sort_keys=True, separators=(",", ":")).casefold()
        if identity in seen:
            continue
        seen.add(identity)
        result.append(record)
    return result


def _languages(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    rank = {"required": 4, "preferred": 3, "optional": 2, "mentioned": 1, "unknown": 0}
    for item in _as_list(value):
        if isinstance(item, Mapping):
            language = _text(item.get("language") or item.get("name") or item.get("value"))
            requirement = _text(item.get("requirement") or item.get("status") or item.get("requiredness"))
            proficiency = _text(item.get("proficiency") or item.get("level")) or None
        else:
            language, requirement, proficiency = _text(item), "unknown", None
        if not language:
            continue
        requirement_key = _key(requirement)
        requirement = {
            "must_have": "required", "required": "required", "mandatory": "required",
            "nice_to_have": "preferred", "preferred": "preferred", "optional": "optional",
            "mentioned": "mentioned",
        }.get(requirement_key, "unknown")
        record = {"language": language, "requirement": requirement, "proficiency": proficiency}
        existing = next((entry for entry in result if _key(entry["language"]) == _key(language)), None)
        if existing is None:
            result.append(record)
        elif rank[requirement] > rank[existing["requirement"]]:
            existing.update(record)
    return result


def _experience(value: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        value = {}
    minimum = _number(value.get("minimum_years", value.get("minimum", value.get("min", value.get("min_years")))))
    maximum = _number(value.get("maximum_years", value.get("maximum", value.get("max", value.get("max_years")))))
    seniority = _text(value.get("seniority") or value.get("experience_level") or _direct_value(payload, "experience_level", "seniority")) or None
    status = _key(value.get("requirement_status") or value.get("status")) or "unknown"
    if status not in {"required", "preferred", "optional", "unknown"}:
        status = "unknown"
    return {
        "minimum_years": minimum,
        "maximum_years": maximum,
        "seniority": seniority,
        "requirement_status": status,
    }


def _salary(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        value = {}
    return {
        "minimum": _number(value.get("minimum", value.get("min", value.get("min_salary", value.get("lower"))))),
        "maximum": _number(value.get("maximum", value.get("max", value.get("max_salary", value.get("upper"))))),
        "currency": _text(value.get("currency") or value.get("currency_code")).upper() or None,
        "period": _text(value.get("period") or value.get("pay_period") or value.get("interval")).casefold() or None,
    }


def _authorization(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in _as_list(value):
        if isinstance(item, Mapping):
            record = {
                "country_code": _text(item.get("country_code") or item.get("countryCode")).upper() or None,
                "region": _text(item.get("region")) or None,
                "status": _key(item.get("status") or item.get("authorization_status")) or "unknown",
            }
        else:
            record = {"country_code": _text(item).upper() or None, "region": None, "status": "unknown"}
        if record["country_code"] or record["region"] or record["status"] != "unknown":
            result.append(record)
    return result


def _sponsorship(value: Any) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("requirement") or value.get("status") or value.get("value")
    if isinstance(value, bool):
        return "required" if value else "not_required"
    if not _present(value):
        return None
    normalized = _key(value)
    return {
        "required": "required", "sponsorship_required": "required", "yes": "required", "true": "required",
        "not_required": "not_required", "no": "not_required", "false": "not_required",
        "unknown": "unknown", "not_disclosed": "unknown",
    }.get(normalized, _text(value))


def _application(value: Any, payload: Mapping[str, Any]) -> tuple[dict[str, Any], str, str]:
    raw = dict(value) if isinstance(value, Mapping) else {}
    method = _text(raw.get("application_method") or _direct_value(payload, "application_method")) or "unknown"
    classification = _key(raw.get("classification"))
    destination_type = _key(raw.get("destination_type"))
    status = _key(raw.get("status")) or "unknown"
    resolved = _text(raw.get("resolved_url")) or _text(_direct_value(payload, "application_url", "apply_url"))
    detail = _text(raw.get("job_detail_url")) or _text(_direct_value(payload, "job_detail_url"))
    user_url = _text(raw.get("user_facing_url")) or detail or resolved
    listing_classes = {"careers_index", "search_results", "portal_listing"}
    listing_methods = {"listing_fallback", "unknown"}
    if classification in listing_classes or destination_type in {"listing_fallback", "job_detail_only"} or (method in listing_methods and not status == "verified"):
        if status != "verified":
            status = "unresolved"
        resolved = ""
    if status == "verified" and not resolved:
        status = "unresolved"
    typed = {
        "destination_type": destination_type or classification or "unresolved",
        "classification": classification or None,
        "resolved_url": resolved or None,
        "user_facing_url": user_url or None,
        "job_detail_url": detail or None,
        "status": status,
        "application_method": method,
        "is_actionable": status == "verified" and bool(resolved),
        "warnings": [str(item) for item in raw.get("warnings") or [] if _text(item)],
    }
    return typed, method, status


def _timestamps(value: Any) -> dict[str, Any]:
    raw = dict(value) if isinstance(value, Mapping) else {}
    source_fields = raw.get("fields") if isinstance(raw.get("fields"), Mapping) else {}
    result_fields: dict[str, Any] = {}
    semantics: dict[str, str] = {}
    for name in ("published_at", "updated_at", "first_seen_at", "last_seen_at", "closed_at"):
        candidate = source_fields.get(name) or source_fields.get("source_" + name) or source_fields.get("source_posted_at" if name == "published_at" else "")
        if not candidate and isinstance(raw.get(name), Mapping):
            candidate = raw.get(name)
        if isinstance(candidate, Mapping):
            result_fields[name] = candidate.get("value")
            semantic = _text(candidate.get("semantic") or candidate.get("meaning") or candidate.get("evidence"))
            if semantic:
                semantics[name] = semantic
        else:
            result_fields[name] = candidate if _present(candidate) else None
    return {
        "state": _text(raw.get("timestamp_state") or raw.get("state")) or "unknown",
        "fields": result_fields,
        "semantics": semantics,
    }


def _completeness(value: Any) -> dict[str, Any]:
    raw = dict(value) if isinstance(value, Mapping) else {}
    overall = raw.get("overall") if isinstance(raw.get("overall"), Mapping) else raw
    present = _number(overall.get("present"))
    total = _number(overall.get("total"))
    score = round(present / total, 4) if isinstance(present, (int, float)) and isinstance(total, (int, float)) and total else None
    return {
        "state": _key(overall.get("state") or overall.get("status")) or "unknown",
        "status": _key(overall.get("status") or overall.get("state")) or "unknown",
        "present": present,
        "total": total,
        "score": score,
        "report_only": bool(raw.get("report_only", True)),
    }


def _warnings(value: Any) -> list[str]:
    result: list[str] = []
    for item in _as_list(value):
        if isinstance(item, Mapping):
            item = item.get("code") or item.get("warning_code") or item.get("name") or item.get("message")
        warning = _text(item)
        if warning and warning not in result:
            result.append(warning)
    return result


def _status_object(value: Any, *, default_state: str = "unknown") -> dict[str, Any]:
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return {"state": "known", "url": value}
    if isinstance(value, Mapping):
        state = _key(value.get("state") or value.get("status")) or default_state
        return {
            "state": state,
            **{
                key: value.get(key)
                for key in ("provider", "url", "updated_at", "verified_at", "cluster_id", "decision", "age_days", "age_hours", "last_seen_at", "last_verified_at")
                if _present(value.get(key))
            },
        }
    if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value.strip()):
        return {"state": "known", "last_seen_at": value}
    state = _key(value) or default_state
    return {"state": state}


def _company_contract(payload: Mapping[str, Any], logo: Mapping[str, Any], enrichment: Mapping[str, Any]) -> dict[str, Any]:
    company_value = payload.get("company")
    company = company_value if isinstance(company_value, Mapping) else {}
    urls = payload.get("company_urls") or payload.get("company_url_records") or company.get("urls") or []
    typed_urls: list[dict[str, Any]] = []
    for item in _as_list(urls):
        if isinstance(item, Mapping):
            url = _text(item.get("canonical_url") or item.get("url"))
            if url:
                typed_urls.append({
                    "url": url,
                    "url_type": _text(item.get("url_type") or item.get("type")) or "unknown",
                    "source": _text(item.get("source")) or None,
                    "validation_status": _text(item.get("validation_status") or item.get("status")) or "unknown",
                    "selected_primary": bool(item.get("selected_primary") or item.get("primary")),
                })
    company_name = company.get("name") or _direct_value(payload, "company_name", "employer_name")
    if not _present(company_name) and isinstance(company_value, str):
        company_name = company_value
    return {"name": _text(company_name) or None, "urls": typed_urls, "logo": dict(logo), "enrichment": dict(enrichment)}


def normalize_typed_contract(payload: Mapping[str, Any], *, include_admin_evidence: bool = False) -> TypedContract:
    """Normalize a canonical/read-model payload into additive typed values."""

    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    mapping, fields = _mapping_and_fields(payload)
    values: dict[str, Any] = {}
    states: dict[str, str] = {}

    def field(name: str, *aliases: str) -> Any:
        value, record = _field_record(payload, fields, name)
        if value is None and aliases:
            value = _direct_value(payload, *aliases)
        states[name] = _state(record, value)
        return value

    department = field("source_department")
    function = field("runr_function")
    subfunction = field("runr_subfunction")
    source_team = field("source_team")
    source_category = field("source_category")
    employment = field("employment_type")
    workplace = field("workplace_arrangement")
    remote = field("remote_geographic_restrictions")
    locations = field("locations")
    languages = field("languages")
    experience = field("experience")
    salary = field("salary")
    authorization = field("work_authorization")
    sponsorship = field("sponsorship")
    application = field("application_destination")
    timestamps = field("timestamp_semantics")
    completeness = field("completeness")
    warnings = field("warnings")
    freshness = field("freshness")
    duplicate = field("duplicate")
    logo = field("logo")
    enrichment = field("enrichment")
    publication = field("publication_state")

    mapping_fields = mapping.get("fields") if isinstance(mapping, Mapping) else {}
    function = _taxonomy(function, _FUNCTION_ALIASES)
    subfunction = _text(subfunction) or None
    department = _text(department) or None
    source_team = _text(source_team) or None
    source_category = _text(source_category) or None
    employment = _taxonomy(employment, _EMPLOYMENT_ALIASES)
    workplace = _taxonomy(workplace, _WORKPLACE_ALIASES)
    remote_values = _canonical_strings(remote)
    location_values = _locations(locations)
    language_values = _languages(languages)
    experience_value = _experience(experience, payload)
    salary_value = _salary(salary)
    authorization_values = _authorization(authorization)
    sponsorship_value = _sponsorship(sponsorship)
    application_value, application_method, application_status = _application(application, payload)
    timestamp_value = _timestamps(timestamps)
    completeness_value = _completeness(completeness)
    warning_values = _warnings(warnings)
    freshness_value = _status_object(freshness)
    duplicate_value = _status_object(duplicate)
    logo_value = _status_object(logo)
    enrichment_value = _status_object(enrichment)
    if isinstance(publication, bool):
        publication_state = "published" if publication else "unpublished"
    else:
        publication_state = _key(publication) or ("published" if payload.get("is_live") is True else "unknown")

    result: TypedContract = {
        "schema_version": PUBLIC_TYPED_CONTRACT_VERSION,
        "rule_version": PUBLIC_CONTRACT_RULE_VERSION,
        "mapping_rule_version": _text(mapping.get("rule_version") or payload.get("unified_rule_version") or UNIFIED_RULE_VERSION),
        "runr_function": function,
        "runr_subfunction": subfunction,
        "source_department": department,
        "source_team": source_team,
        "source_category": source_category,
        "employment_type": employment,
        "workplace_arrangement": workplace,
        "remote_geographic_restrictions": remote_values,
        "locations": location_values,
        "languages": language_values,
        "experience": experience_value,
        "salary": salary_value,
        "work_authorization": authorization_values,
        "sponsorship": sponsorship_value,
        "application_destination": application_value,
        "application_method": application_method,
        "application_status": application_status,
        "timestamp_semantics": timestamp_value,
        "completeness": completeness_value,
        "warnings": warning_values,
        "freshness": freshness_value,
        "duplicate": duplicate_value,
        "logo": logo_value,
        "enrichment": enrichment_value,
        "publication_state": publication_state,
        "field_states": states,
        "company": _company_contract(payload, logo_value, enrichment_value),
    }
    if include_admin_evidence:
        result["admin"] = {"field_count": len(mapping_fields) if isinstance(mapping_fields, Mapping) else 0}
    return result


def serialize_public_contract(payload: Mapping[str, Any], *, audience: str = "public") -> dict[str, Any]:
    """Add ``typed`` while preserving every legacy field in ``payload``.

    ``audience='admin'`` adds a bounded ``typed_lineage`` view.  Public
    serialization intentionally has no raw evidence or raw-payload escape
    hatch.
    """

    normalized = normalize_typed_contract(payload, include_admin_evidence=audience.casefold() == "admin")
    if audience.casefold() not in {"public", "admin"}:
        raise ValueError("audience must be 'public' or 'admin'")
    result = {
        key: value
        for key, value in payload.items()
        if audience.casefold() == "admin" or str(key).casefold() not in _PUBLIC_ADMIN_ONLY_KEYS
    }
    result[TYPED_CONTRACT_KEY] = normalized
    result["typed_contract_version"] = PUBLIC_TYPED_CONTRACT_VERSION
    if audience.casefold() == "admin":
        result["typed_lineage"] = build_field_lineage(payload, audience="admin")
    return result


def _record_for_lineage(payload: Mapping[str, Any], field_name: str) -> Mapping[str, Any] | None:
    _, fields = _mapping_and_fields(payload)
    _, record = _field_record(payload, fields, field_name)
    return record


def _bounded(value: Any, *, max_chars: int = 180, max_items: int = 12) -> Any:
    if isinstance(value, str):
        return value if len(value) <= max_chars else value[: max_chars - 1] + "…"
    if isinstance(value, Mapping):
        return {str(key): _bounded(item, max_chars=max_chars, max_items=max_items) for key, item in list(value.items())[:max_items]}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_bounded(item, max_chars=max_chars, max_items=max_items) for item in list(value)[:max_items]]
    return value


def build_field_lineage(
    payload: Mapping[str, Any],
    *,
    fields: Sequence[str] | None = None,
    audience: str = "admin",
    max_evidence_chars: int = 180,
) -> list[dict[str, Any]]:
    """Present compact lineage; only admin receives evidence summaries."""

    normalized = normalize_typed_contract(payload)
    selected = list(fields or TYPED_FIELD_NAMES)
    result: list[dict[str, Any]] = []
    for field_name in selected:
        if field_name not in TYPED_FIELD_NAMES:
            continue
        record = _record_for_lineage(payload, field_name)
        item: dict[str, Any] = {
            "field": field_name,
            "value": _bounded(normalized.get(field_name)),
            "state": normalized.get("field_states", {}).get(field_name, "unknown"),
            "rule_version": _text((record or {}).get("rule_version")) or normalized.get("mapping_rule_version"),
        }
        if audience.casefold() == "admin":
            item["provenance"] = {
                key: (record or {}).get(key)
                for key in ("source", "source_field", "extraction_method", "confidence", "observed_at")
                if _present((record or {}).get(key))
            }
            if record is not None and any(key in record for key in ("raw_value", "evidence")):
                item["evidence_summary"] = _bounded(record.get("evidence", record.get("raw_value")), max_chars=max_evidence_chars)
        elif audience.casefold() != "public":
            raise ValueError("audience must be 'public' or 'admin'")
        result.append(item)
    return result


def build_version_diff(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    fields: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Return a bounded typed diff between two posting versions."""

    before_typed = normalize_typed_contract(before)
    after_typed = normalize_typed_contract(after)
    selected = list(fields or TYPED_FIELD_NAMES)
    changes: list[dict[str, Any]] = []
    for field_name in selected:
        if field_name not in TYPED_FIELD_NAMES:
            continue
        old = _bounded(before_typed.get(field_name))
        new = _bounded(after_typed.get(field_name))
        if old != new:
            changes.append({"field": field_name, "before": old, "after": new})
    return {
        "schema_version": PUBLIC_TYPED_CONTRACT_VERSION,
        "changed": bool(changes),
        "changed_fields": [item["field"] for item in changes],
        "changes": changes,
        "rule_versions": {
            "before": before_typed.get("mapping_rule_version"),
            "after": after_typed.get("mapping_rule_version"),
        },
    }


def _filter_key(value: Any) -> str:
    raw = str(value)
    return _FILTER_ALIASES.get(raw, _FILTER_ALIASES.get(raw.casefold(), raw.casefold()))


def normalize_typed_filters(filters: Mapping[str, Any] | None) -> dict[str, Any]:
    """Canonicalize filter aliases and scalar types before predicate use."""

    result: dict[str, Any] = {}
    for raw_name, value in dict(filters or {}).items():
        name = _filter_key(raw_name)
        if value in (None, "", [], {}):
            continue
        if name in {"salary_minimum", "salary_maximum", "experience_minimum_years", "experience_maximum_years"}:
            number = _number(value)
            if number is not None:
                result[name] = number
        elif name == "posted_within_days":
            number = _number(value)
            if number is not None:
                result[name] = number
        elif name in {"search_text", "q", "search"}:
            result["search_text"] = _canonical_strings(value)
        else:
            result[name] = _as_list(value)
    return result


def _compare(value: Any) -> str:
    return _key(value)


def _tokens(value: Any) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", _text(value).casefold()) if token}


def _contains_exact(actual: Sequence[Any], requested: Sequence[Any]) -> bool:
    actual_keys = {_compare(item) for item in actual if _present(item)}
    wanted_keys = {_compare(item) for item in requested if _present(item)}
    if not wanted_keys:
        return True
    if not actual_keys:
        return "unknown" in wanted_keys
    return bool(actual_keys & wanted_keys)


def _filter_values(contract: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    locations = contract.get("locations") or []
    location_values: list[str] = []
    for item in locations:
        if isinstance(item, Mapping):
            location_values.extend(str(item.get(key)) for key in ("label", "city", "region", "country", "country_code") if _present(item.get(key)))
        else:
            location_values.append(str(item))
    languages = [item.get("language") for item in contract.get("languages") or [] if isinstance(item, Mapping)]
    authorization: list[str] = []
    for item in contract.get("work_authorization") or []:
        if isinstance(item, Mapping):
            authorization.extend(str(item.get(key)) for key in ("country_code", "region", "status") if _present(item.get(key)))
    company = payload.get("company")
    company_name = company.get("name") if isinstance(company, Mapping) else company
    search_parts = [
        _direct_value(payload, "title"),
        company_name,
        _direct_value(payload, "description_text", "description"),
        *location_values,
        contract.get("runr_function"),
        contract.get("runr_subfunction"),
        contract.get("source_department"),
        contract.get("source_team"),
        contract.get("source_category"),
    ]
    return {
        "runr_function": [contract.get("runr_function")],
        "runr_subfunction": [contract.get("runr_subfunction")],
        "source_department": [contract.get("source_department")],
        "source_team": [contract.get("source_team")],
        "source_category": [contract.get("source_category")],
        "employment_type": [contract.get("employment_type")],
        "workplace_arrangement": [contract.get("workplace_arrangement")],
        "remote_geographic_restrictions": contract.get("remote_geographic_restrictions") or [],
        "location": location_values,
        "language": languages,
        "work_authorization": authorization,
        "experience_seniority": [contract.get("experience", {}).get("seniority")],
        "source": [_direct_value(payload, "source_ats", "source", "connector")],
        "sponsorship": [contract.get("sponsorship")],
        "application_method": [contract.get("application_method")],
        "application_status": [contract.get("application_status")],
        "timestamp_semantics": list((contract.get("timestamp_semantics") or {}).get("semantics", {}).values()),
        "completeness": [contract.get("completeness", {}).get("state"), contract.get("completeness", {}).get("status")],
        "warnings": contract.get("warnings") or [],
        "freshness": [contract.get("freshness", {}).get("state")],
        "duplicate": [contract.get("duplicate", {}).get("state")],
        "logo": [contract.get("logo", {}).get("state")],
        "enrichment": [contract.get("enrichment", {}).get("state")],
        "publication_state": [contract.get("publication_state")],
        "search_text": [" ".join(_text(item) for item in search_parts if _present(item))],
    }


def matches_typed_filters(payload: Mapping[str, Any], filters: Mapping[str, Any] | None) -> bool:
    """Match only normalized typed values; never search serialized raw JSON."""

    normalized_filters = normalize_typed_filters(filters)
    contract = normalize_typed_contract(payload)
    values = _filter_values(contract, payload)
    numeric_filters = {"salary_minimum", "salary_maximum", "experience_minimum_years", "experience_maximum_years", "posted_within_days"}
    for name, requested in normalized_filters.items():
        if name == "search_text":
            haystack = _tokens(values["search_text"])
            if not all(_tokens(item) <= haystack for item in requested):
                return False
        elif name in {"salary_minimum", "salary_maximum"}:
            salary = contract.get("salary") or {}
            boundary = float(requested if isinstance(requested, (int, float)) else requested[0])
            actual = salary.get("maximum") if name == "salary_minimum" else salary.get("minimum")
            if actual is None:
                actual = salary.get("minimum") if name == "salary_minimum" else salary.get("maximum")
            if actual is None or (actual < boundary if name == "salary_minimum" else actual > boundary):
                return False
        elif name in {"experience_minimum_years", "experience_maximum_years"}:
            experience = contract.get("experience") or {}
            boundary = float(requested if isinstance(requested, (int, float)) else requested[0])
            actual = experience.get("minimum_years") if name == "experience_minimum_years" else experience.get("maximum_years")
            if actual is None or (actual < boundary if name == "experience_minimum_years" else actual > boundary):
                return False
        elif name == "posted_within_days":
            freshness = contract.get("freshness") or {}
            age = freshness.get("age_days")
            boundary = float(requested if isinstance(requested, (int, float)) else requested[0])
            if age is None or float(age) > boundary:
                return False
        elif name in values:
            if not _contains_exact(values[name], requested):
                return False
        elif name not in numeric_filters:
            return False
    return True


def build_typed_filter_predicate(filters: Mapping[str, Any] | None) -> Callable[[Mapping[str, Any]], bool]:
    """Build a reusable predicate for canonical/read-model collections."""

    normalized = normalize_typed_filters(filters)
    return lambda payload: matches_typed_filters(payload, normalized)


typed_filter_predicate = build_typed_filter_predicate
normalize_public_contract = normalize_typed_contract
serialize_typed_contract = serialize_public_contract
field_lineage = build_field_lineage
version_diff = build_version_diff


__all__ = [
    "PUBLIC_CONTRACT_RULE_VERSION",
    "PUBLIC_TYPED_CONTRACT_VERSION",
    "TYPED_CONTRACT_KEY",
    "TYPED_FIELD_NAMES",
    "TypedContract",
    "build_field_lineage",
    "build_typed_filter_predicate",
    "build_version_diff",
    "field_lineage",
    "matches_typed_filters",
    "normalize_public_contract",
    "normalize_typed_contract",
    "normalize_typed_filters",
    "serialize_public_contract",
    "serialize_typed_contract",
    "typed_filter_predicate",
    "version_diff",
]
