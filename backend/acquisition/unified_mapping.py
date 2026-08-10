"""Connector-independent field mapping for the acquisition catalog.

The mapper is deliberately deterministic and evidence-first.  It produces a
typed projection for the canonical catalog while retaining the source value,
where it came from, how it was extracted, and why the value is known or
unknown.  It never mutates a source observation.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

from backend.acquisition.network_policy import hostname_for_url
from backend.acquisition.rule_registry import (
    FIELD_STATE_SET,
    FIELD_STATES,
    RULE_VERSION_REGISTRY,
    VALUE_FIELD_STATES,
    canonical_field_state,
    field_state_for,
    value_is_present,
)
from backend.domain.job_identity import canonicalize_url, compact_whitespace


UNIFIED_RULE_VERSION = "unified_mapping_v1"

FUNCTION_TAXONOMY = (
    "Engineering", "Data", "Product", "Design", "Marketing", "Sales",
    "Customer Support", "Operations", "Finance", "Legal", "Risk and Compliance",
    "People", "Security", "Executive", "Other", "Unclassified",
)
EMPLOYMENT_TYPES = (
    "Full-time", "Part-time", "Contract", "Temporary", "Internship",
    "Apprenticeship", "Freelance", "Working student", "Unknown",
)
WORKPLACE_ARRANGEMENTS = ("On-site", "Hybrid", "Remote", "Flexible", "Unknown")
APPLICATION_DESTINATIONS = (
    "dedicated_apply", "embedded_apply", "job_detail_with_apply", "redirect_apply",
    "job_detail_only", "unresolved",
)

_UNKNOWN = {"", "unknown", "n/a", "not available", "not disclosed", "undisclosed", "none"}
_FUNCTION_RULES = (
    ("Engineering", ("engineering", "software", "developer", "development", "platform", "devops", "technology", "technical")),
    ("Data", ("data", "analytics", "machine learning", "artificial intelligence", "business intelligence")),
    ("Product", ("product", "product management")),
    ("Design", ("design", "ux", "ui", "creative")),
    ("Marketing", ("marketing", "brand", "communications", "content", "growth")),
    ("Sales", ("sales", "business development", "account", "revenue")),
    ("Customer Support", ("customer support", "customer service", "success", "care")),
    ("Operations", ("operations", "procurement", "supply chain", "logistics", "administration")),
    ("Finance", ("finance", "accounting", "treasury", "tax")),
    ("Legal", ("legal", "law", "counsel")),
    ("Risk and Compliance", ("risk", "compliance", "audit", "regulatory")),
    ("People", ("people", "human resources", "hr", "talent", "recruiting")),
    ("Security", ("security", "cyber", "information security")),
    ("Executive", ("executive", "leadership", "chief", "c-suite")),
)
_SUBFUNCTION_RULES = {
    "Engineering": (
        ("Backend Engineering", ("backend", "back-end", "server")),
        ("Frontend Engineering", ("frontend", "front-end", "web")),
        ("Platform Engineering", ("platform", "infrastructure", "devops", "sre")),
        ("Quality Engineering", ("quality", "qa", "test")),
        ("Security Engineering", ("security", "cyber")),
    ),
    "Data": (
        ("Data Analytics", ("analytics", "bi", "business intelligence")),
        ("Data Science", ("data science", "machine learning", "artificial intelligence")),
        ("Data Engineering", ("data engineering", "data platform")),
    ),
    "Product": (("Product Management", ("product manager", "product management")), ("Product Operations", ("product operations",))),
    "Design": (("UX Design", ("ux", "user experience")), ("UI Design", ("ui", "visual design"))),
    "Sales": (("Business Development", ("business development", "sales development")), ("Account Management", ("account management", "account executive"))),
    "Marketing": (("Growth Marketing", ("growth", "performance")), ("Content and Brand", ("content", "brand", "communications"))),
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _known(value: Any) -> bool:
    if not value_is_present(value):
        return False
    return not (isinstance(value, str) and value.strip().casefold() in _UNKNOWN)


def _first(mapping: Mapping[str, Any], *keys: str) -> tuple[Any, str]:
    for key in keys:
        value = mapping.get(key)
        if _known(value):
            return value, key
    return None, ""


def _nested_sources(job: Mapping[str, Any]) -> list[tuple[Mapping[str, Any], str, str]]:
    sources: list[tuple[Mapping[str, Any], str, str]] = [(job, "job", "source_payload")]
    for key in ("source_metadata", "source_raw_payload"):
        value = job.get(key)
        if isinstance(value, Mapping):
            sources.append((value, key, "structured_ats_field" if key == "source_metadata" else "raw_source_field"))
    return sources


def _source_value(job: Mapping[str, Any], keys: Sequence[str]) -> tuple[Any, str, str]:
    for source, source_name, method in _nested_sources(job):
        value, field = _first(source, *keys)
        if _known(value):
            return value, f"{source_name}.{field}", method
    return None, "", "not_available"


def _company_value(job: Mapping[str, Any], keys: Sequence[str]) -> tuple[Any, str, str]:
    """Read company attributes from structured company objects or the job row."""

    sources: list[tuple[Mapping[str, Any], str, str]] = [(job, "job", "source_payload")]
    for key in ("company", "company_profile", "company_details", "employer"):
        value = job.get(key)
        if isinstance(value, Mapping):
            sources.append((value, key, "structured_company_field"))
    for key in ("source_raw_payload", "source_metadata"):
        value = job.get(key)
        if isinstance(value, Mapping):
            nested = value.get("company") or value.get("employer")
            if isinstance(nested, Mapping):
                sources.append((nested, f"{key}.company", "structured_source_company_field"))
    for source, source_name, method in sources:
        value, field = _first(source, *keys)
        if _known(value):
            return value, f"{source_name}.{field}", method
    return None, "", "not_available"


def _source_conflicting(job: Mapping[str, Any], keys: Sequence[str]) -> bool:
    """Detect disagreement across connector, structured, and raw values."""

    values: list[str] = []
    for source, _, _ in _nested_sources(job):
        for key in keys:
            value = source.get(key)
            if _known(value):
                token = compact_whitespace(_text(value)).casefold()
                if token and token not in values:
                    values.append(token)
    return len(values) > 1


def _company_conflicting(job: Mapping[str, Any], keys: Sequence[str]) -> bool:
    values: list[str] = []
    sources: list[Mapping[str, Any]] = [job]
    for key in ("company", "company_profile", "company_details", "employer"):
        value = job.get(key)
        if isinstance(value, Mapping):
            sources.append(value)
    for key in ("source_raw_payload", "source_metadata"):
        value = job.get(key)
        if isinstance(value, Mapping):
            nested = value.get("company") or value.get("employer")
            if isinstance(nested, Mapping):
                sources.append(nested)
    for source in sources:
        for key in keys:
            value = source.get(key)
            if _known(value):
                token = compact_whitespace(_text(value)).casefold()
                if token and token not in values:
                    values.append(token)
    return len(values) > 1


def _normalize_count(value: Any) -> Any:
    if isinstance(value, Mapping):
        return dict(value)
    text = _text(value).replace(",", "")
    match = re.fullmatch(r"(\d+)(\s*\+)?", text)
    if not match:
        return value
    number = int(match.group(1))
    return {"minimum": number, "open_ended": bool(match.group(2)), "display": _text(value)}


def field_record(
    *, raw_value: Any = None, normalized_value: Any = None, source: str = "", source_field: str = "",
    extraction_method: str = "not_available", evidence: Any = None, confidence: float = 0.0,
    observed_at: str = "", state: str = "unknown", unsupported: bool = False,
    state_reason: str = "",
) -> dict[str, Any]:
    if unsupported:
        state = "unsupported"
    state = canonical_field_state(state)
    return {
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "state": state,
        "source": source or None,
        "source_field": source_field or None,
        "extraction_method": extraction_method,
        "evidence": evidence,
        "confidence": round(max(0.0, min(1.0, float(confidence or 0.0))), 3),
        "observed_at": observed_at or None,
        "state_reason": state_reason or None,
        "rule_version": UNIFIED_RULE_VERSION,
    }


def _normalized_token(value: Any) -> str:
    return compact_whitespace(_text(value)).casefold().replace("–", "-")


def _normalize_employment(value: Any) -> str:
    token = _normalized_token(value)
    if not token:
        return ""
    if "working student" in token or "werkstudent" in token:
        return "Working student"
    if "intern" in token or "praktikum" in token:
        return "Internship"
    if "apprent" in token or "ausbildung" in token:
        return "Apprenticeship"
    if "freelance" in token or "freiberuf" in token:
        return "Freelance"
    if "temporary" in token or "befrist" in token or "fixed term" in token:
        return "Temporary"
    if "part" in token or "teilzeit" in token:
        return "Part-time"
    if "contract" in token or "contractor" in token or "vertrag" in token:
        return "Contract"
    if "full" in token or "vollzeit" in token:
        return "Full-time"
    return ""


def _normalize_workplace(value: Any) -> str:
    token = _normalized_token(value)
    if not token:
        return ""
    if "hybrid" in token or "hybride" in token:
        return "Hybrid"
    if "remote" in token or "remot" in token or "home office" in token or "homeoffice" in token:
        return "Remote"
    if "flexible" in token or "flexibel" in token:
        return "Flexible"
    if "on-site" in token or "onsite" in token or "on site" in token or "office" in token or "vor ort" in token:
        return "On-site"
    return ""


def _map_function(raw_department: Any) -> tuple[str, str]:
    token = _normalized_token(raw_department)
    if not token:
        return "Unclassified", ""
    for function, terms in _FUNCTION_RULES:
        if any(term in token for term in terms):
            subfunction = ""
            for candidate, subterms in _SUBFUNCTION_RULES.get(function, ()):
                if any(term in token for term in subterms):
                    subfunction = candidate
                    break
            return function, subfunction
    return "Other", ""


def _description_text(job: Mapping[str, Any]) -> str:
    for key in ("description_text", "description", "full_description", "description_raw"):
        if _known(job.get(key)):
            return _text(job.get(key))
    return ""


def _parse_languages(raw: Any, *, source_field: str, method: str, description: str, observed_at: str) -> list[dict[str, Any]]:
    values: list[Any]
    if isinstance(raw, Mapping):
        values = [{"language": key, **(value if isinstance(value, Mapping) else {"status": value})} for key, value in raw.items()]
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        values = list(raw)
    elif _known(raw):
        values = re.split(r"[,;/|]", _text(raw))
    else:
        values = []
    result: list[dict[str, Any]] = []
    for item in values:
        if isinstance(item, Mapping):
            language = _text(item.get("language") or item.get("name") or item.get("value"))
            status = _text(item.get("status") or item.get("requirement") or "mentioned").casefold()
            proficiency = _text(item.get("proficiency") or item.get("level")) or None
            evidence = item.get("evidence") or source_field
        else:
            language = _text(item)
            status, proficiency, evidence = "mentioned", None, source_field
        if not language or language.casefold() in {"languages", "language", "communication"}:
            continue
        if status not in {"required", "preferred", "optional", "mentioned"}:
            status = "mentioned"
        result.append({
            "language": language, "status": status, "proficiency": proficiency,
            "evidence": evidence, "source": source_field, "extraction_method": method,
            "confidence": 0.9 if method.startswith("structured") else 0.75,
            "state": "inferred" if method == "labeled_page_text" else "present",
            "observed_at": observed_at or None, "rule_version": UNIFIED_RULE_VERSION,
        })
    if result:
        return result
    # Only parse an explicitly labelled language line.  This avoids treating
    # generic company boilerplate or arbitrary prose as a job requirement.
    match = re.search(r"(?im)^\s*(?:required\s+|preferred\s+)?languages?\s*[:\-]\s*([^\n]+)", description)
    if not match:
        return []
    return _parse_languages(match.group(1), source_field="description.languages", method="labeled_page_text", description="", observed_at=observed_at)


def _experience(job: Mapping[str, Any], description: str, observed_at: str) -> dict[str, Any]:
    raw, source_field, method = _source_value(job, ("experience_requirements", "years_experience", "experience_years", "min_experience_years", "experience_min_years"))
    minimum: int | None = None
    maximum: int | None = None
    evidence: Any = raw
    if isinstance(raw, Mapping):
        minimum = _int_or_none(raw.get("min") or raw.get("minimum") or raw.get("min_years"))
        maximum = _int_or_none(raw.get("max") or raw.get("maximum") or raw.get("max_years"))
        evidence = raw.get("evidence") or raw
    elif _known(raw):
        match = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)\s*years?", _text(raw), re.IGNORECASE)
        if match:
            minimum, maximum = int(match.group(1)), int(match.group(2))
        else:
            match = re.search(r"(\d+)\s*\+?\s*years?", _text(raw), re.IGNORECASE)
            if match:
                minimum = int(match.group(1))
    if minimum is None and maximum is None:
        match = re.search(r"(?i)(?:at least|minimum of|minimum)\s+(\d+)\s+years?[^.\n]{0,80}(?:experience|professional)", description)
        if match:
            minimum, source_field, method, evidence = int(match.group(1)), "description.experience", "description_evidence", match.group(0).strip()
    if minimum is not None and minimum < 0:
        minimum = None
    if maximum is not None and maximum < 0:
        maximum = None
    seniority, seniority_field, seniority_method = _source_value(job, ("seniority", "experience_level"))
    requirement_status = "required" if minimum is not None or maximum is not None or _known(raw) else "unknown"
    return {
        "minimum_years": minimum, "maximum_years": maximum,
        "seniority": _text(seniority) or None, "requirement_status": requirement_status,
        "raw_value": raw, "source": source_field or seniority_field or None,
        "extraction_method": method if minimum is not None or maximum is not None else seniority_method if seniority else "not_available",
        "evidence": evidence or (seniority if seniority else None),
        "confidence": 0.9 if minimum is not None or maximum is not None else 0.75 if seniority else 0.0,
        "state": "present" if minimum is not None or maximum is not None or seniority else "unknown",
        "observed_at": observed_at or None, "rule_version": UNIFIED_RULE_VERSION,
    }


def _int_or_none(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def company_url_records(job: Mapping[str, Any], *, company_id: str = "", observed_at: str = "") -> list[dict[str, Any]]:
    """Return discovered company/employer URLs without selecting a stronger value."""

    candidates: list[tuple[str, str, str]] = []
    for field, url_type in (
        ("website", "homepage"), ("company_website", "homepage"), ("careers_page", "careers"),
        ("careers_url", "careers"), ("jobs_url", "employer_jobs"), ("ats_url", "ats_jobs"),
        ("job_detail_url", "job_detail"), ("source_url", "source"),
    ):
        value = job.get(field)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            candidates.extend((_text(item), url_type, f"job.{field}") for item in value)
        elif _known(value):
            candidates.append((_text(value), url_type, f"job.{field}"))
    for object_name in ("company", "company_profile", "company_details", "employer"):
        nested = job.get(object_name) if isinstance(job.get(object_name), Mapping) else {}
        for field, url_type in (("website", "homepage"), ("company_website", "homepage"), ("careers_page", "careers"), ("careers_url", "careers"), ("jobs_url", "employer_jobs"), ("ats_url", "ats_jobs")):
            if _known(nested.get(field)):
                candidates.append((_text(nested[field]), url_type, f"{object_name}.{field}"))
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw_url, url_type, source_field in candidates:
        url = canonicalize_url(raw_url)
        if not url or (url, url_type) in seen:
            continue
        seen.add((url, url_type))
        configured = source_field.startswith(("company_profile.", "company_details."))
        result.append({
            "company_id": company_id or None, "url_type": url_type, "url": url,
            "canonical_url": url, "source": "configured_official" if configured else "source_observation", "source_field": source_field,
            "first_seen_at": observed_at or None, "last_seen_at": observed_at or None,
            "validation_status": "configured_official" if configured else "not_validated", "redirect_target": None,
            "selected_primary": bool(configured and url_type in {"homepage", "careers", "employer_jobs", "ats_jobs"}), "rule_version": UNIFIED_RULE_VERSION,
        })
    return result


def map_job_fields(job: Mapping[str, Any], *, observed_at: str = "", source_observation_id: str = "", source: str = "") -> dict[str, Any]:
    """Build the complete connector-independent job/company field projection."""

    department, department_field, department_method = _source_value(job, ("source_department", "department", "department_name"))
    function, subfunction = _map_function(department)
    employment, employment_field, employment_method = _source_value(job, ("employment_type", "employmentType", "job_type", "type", "commitment"))
    workplace, workplace_field, workplace_method = _source_value(job, ("workplace_arrangement", "workplace_type", "workplaceType", "remote_type", "workplace"))
    description = _description_text(job)
    languages_raw, languages_field, languages_method = _source_value(job, ("languages", "language_requirements", "language", "required_languages", "preferred_languages"))
    languages = _parse_languages(languages_raw, source_field=languages_field, method=languages_method, description=description, observed_at=observed_at)
    experience = _experience(job, description, observed_at)
    metadata_fields = (
        job.get("normalized_source_metadata", {}).get("fields", {})
        if isinstance(job.get("normalized_source_metadata"), Mapping)
        else {}
    )

    def metadata_state(
        field_name: str,
        raw_value: Any,
        *,
        inferred: bool = False,
        invalid: bool = False,
        conflicting: bool = False,
    ) -> str:
        record = metadata_fields.get(field_name) if isinstance(metadata_fields, Mapping) else None
        if isinstance(record, Mapping) and str(record.get("state") or ""):
            state = canonical_field_state(record.get("state"))
            if state != "unknown" or not value_is_present(raw_value):
                if inferred and state == "present":
                    return "inferred"
                return state
        supported = None
        capability = (
            job.get("normalized_source_metadata", {}).get("source_capability")
            if isinstance(job.get("normalized_source_metadata"), Mapping)
            else None
        )
        supported_fields = (
            job.get("normalized_source_metadata", {}).get("supported_fields")
            if isinstance(job.get("normalized_source_metadata"), Mapping)
            else None
        )
        if capability == "known" and isinstance(supported_fields, Sequence) and not isinstance(supported_fields, (str, bytes)):
            supported = field_name in supported_fields
        return field_state_for(
            raw_value,
            supported=supported,
            observed=bool(source_observation_id or source or observed_at or job.get("source_raw_payload")),
            inferred=inferred,
            invalid=invalid,
            conflicting=conflicting,
        )

    department_state = metadata_state(
        "department",
        department,
        conflicting=_source_conflicting(job, ("source_department", "department", "department_name")),
    )
    employment_normalized = _normalize_employment(employment)
    workplace_normalized = _normalize_workplace(workplace)
    employment_state = metadata_state(
        "employment_type",
        employment,
        invalid=bool(_known(employment) and not employment_normalized),
        conflicting=_source_conflicting(job, ("employment_type", "employmentType", "job_type", "type", "commitment")),
    )
    workplace_state = metadata_state(
        "workplace_arrangement",
        workplace,
        invalid=bool(_known(workplace) and not workplace_normalized),
        conflicting=_source_conflicting(job, ("workplace_arrangement", "workplace_type", "workplaceType", "remote_type", "workplace")),
    )
    if experience.get("extraction_method") == "description_evidence" and experience.get("state") == "present":
        experience["state"] = "inferred"
    language_state = "unknown"
    if languages:
        language_state = "inferred" if all(item.get("state") == "inferred" for item in languages) else "present"
    company_fields: dict[str, dict[str, Any]] = {}
    company_field_map = {
        "name": ("name", "canonical_name", "company_name", "employer_name"),
        "description": ("description", "company_description", "about"),
        "website": ("website", "company_website", "site", "homepage"),
        "careers_page": ("careers_page", "careers_url", "career_page", "jobs_url"),
        "industry": ("industry", "company_industry"),
        "company_size": ("company_size", "size", "employees"),
        "headquarters": ("headquarters", "company_headquarters", "hq"),
        "founded_year": ("founded_year", "company_founded_year", "founded"),
        "company_stage": ("company_stage", "stage", "company_growth_stage"),
        "funding_stage": ("funding_stage", "company_funding_stage"),
        "total_funding": ("total_funding", "total_funding_amount", "funding"),
        "funding_year": ("funding_year", "last_funding_year"),
        "leadership_type": ("leadership_type", "leadership"),
        "benefits": ("benefits", "company_benefits"),
        "sponsorship": ("sponsorship", "sponsorship_information", "sponsors_h1b"),
        "logo_url": ("logo_url", "logo", "company_logo", "logoUrl"),
        "headcount": ("headcount", "employee_count", "employees_count", "company_headcount"),
        "associated_members": ("associated_members", "associated_member_count", "people_associated", "employees_on_linkedin"),
    }
    for field_name, keys in company_field_map.items():
        raw_value, source_field, method = _company_value(job, keys)
        normalized_value = _normalize_count(raw_value) if field_name in {"headcount", "associated_members"} else raw_value
        company_fields[field_name] = field_record(
            raw_value=raw_value, normalized_value=normalized_value,
            source=source or "source_observation" if _known(raw_value) else "",
            source_field=source_field, extraction_method=method,
            evidence=raw_value, confidence=0.95 if _known(raw_value) else 0.0,
            observed_at=observed_at,
            state=field_state_for(
                raw_value,
                observed=bool(source_observation_id or source or observed_at or job.get("source_raw_payload")),
                conflicting=_company_conflicting(job, keys),
            ),
        )
    application = job.get("application_destination") if isinstance(job.get("application_destination"), Mapping) else {}
    classification = _text(application.get("classification"))
    if application.get("embedded_apply") or application.get("embedded_form") or any(str(item.get("source_field") or "").startswith("html_form") for item in application.get("candidate_urls") or [] if isinstance(item, Mapping)):
        destination_type = "embedded_apply"
    elif application.get("redirected") or classification == "redirect_apply":
        destination_type = "redirect_apply"
    elif classification in {"employer_application", "ats_application"}:
        destination_type = "dedicated_apply"
    elif classification in {"employer_job_detail", "ats_job_detail"} and application.get("resolved_url"):
        destination_type = "job_detail_with_apply"
    elif classification in {"employer_job_detail", "ats_job_detail"}:
        destination_type = "job_detail_only"
    else:
        destination_type = "unresolved"
    application = {**dict(application), "destination_type": destination_type, "rule_version": UNIFIED_RULE_VERSION,
                   "validation": dict(application.get("validation") or {"validated_at": None, "final_url": None, "http_status": None, "evidence_type": None, "failure_reason": "not_validated"})}
    timestamp_fields = job.get("source_timestamps") if isinstance(job.get("source_timestamps"), Mapping) else {}
    timestamps: dict[str, Any] = {}
    for name in ("published_at", "updated_at", "first_seen_at", "last_seen_at", "closed_at"):
        source_name = "source_" + name if name in {"published_at", "updated_at", "closed_at"} else name
        item = timestamp_fields.get("fields", {}).get(source_name) if isinstance(timestamp_fields.get("fields"), Mapping) else None
        if not item and name == "published_at" and isinstance(timestamp_fields.get("fields"), Mapping):
            # Acquisition quality names the canonical source publication field
            # ``source_posted_at``; expose it as the mapper's published_at.
            source_name = "source_posted_at"
            item = timestamp_fields["fields"].get(source_name)
        value = item.get("value") if isinstance(item, Mapping) else job.get(source_name)
        timestamps[name] = field_record(raw_value=value, normalized_value=value, source=source or "source_observation" if value else "", source_field=(item or {}).get("source_field", "") if isinstance(item, Mapping) else source_name if value else "", extraction_method=(item or {}).get("method", "source_field") if isinstance(item, Mapping) and value else "not_available", evidence=(item or {}).get("semantic") if isinstance(item, Mapping) else None, confidence=0.95 if value else 0.0, observed_at=observed_at, state="present" if value else "unknown")
    fields = {
        "source_department": field_record(raw_value=department, normalized_value=_text(department) or None, source=source or "source_observation" if department else "", source_field=department_field, extraction_method=department_method, evidence=department, confidence=0.95 if department else 0.0, observed_at=observed_at, state=department_state),
        "runr_function": field_record(raw_value=department, normalized_value=function if _known(department) else None, source=source or "source_observation" if department else "", source_field=department_field, extraction_method="versioned_department_mapping" if department else "not_available", evidence=department or None, confidence=0.9 if department else 0.0, observed_at=observed_at, state=department_state),
        "runr_subfunction": field_record(raw_value=department, normalized_value=subfunction or None, source=source or "source_observation" if subfunction else "", source_field=department_field, extraction_method="versioned_department_mapping" if subfunction else "not_available", evidence=department or None, confidence=0.85 if subfunction else 0.0, observed_at=observed_at, state="present" if subfunction else department_state),
        "employment_type": field_record(raw_value=employment, normalized_value=employment_normalized or None, source=source or "source_observation" if employment_normalized else "", source_field=employment_field, extraction_method=employment_method, evidence=employment, confidence=0.95 if employment_method.startswith("structured") else 0.8 if employment_normalized else 0.0, observed_at=observed_at, state=employment_state),
        "workplace_arrangement": field_record(raw_value=workplace, normalized_value=workplace_normalized or None, source=source or "source_observation" if workplace_normalized else "", source_field=workplace_field, extraction_method=workplace_method, evidence=workplace, confidence=0.95 if workplace_method.startswith("structured") else 0.8 if workplace_normalized else 0.0, observed_at=observed_at, state=workplace_state),
        "remote_geographic_restrictions": field_record(raw_value=job.get("remote_scope") or job.get("remote_restrictions"), normalized_value=job.get("remote_scope") or job.get("remote_restrictions"), source=source if _known(job.get("remote_scope") or job.get("remote_restrictions")) else "", source_field="remote_scope" if _known(job.get("remote_scope")) else "remote_restrictions" if _known(job.get("remote_restrictions")) else "", extraction_method="structured_source_field" if _known(job.get("remote_scope") or job.get("remote_restrictions")) else "not_available", confidence=0.9 if _known(job.get("remote_scope") or job.get("remote_restrictions")) else 0.0, observed_at=observed_at, state=field_state_for(job.get("remote_scope") or job.get("remote_restrictions"), observed=bool(source_observation_id or source or observed_at or job.get("source_raw_payload")))),
        "application_destination": field_record(raw_value=job.get("application_destination"), normalized_value=application, source=source if application else "", source_field="application_destination" if application else "", extraction_method="deterministic_destination_rules" if application else "not_available", evidence=application.get("evidence") if application else None, confidence=0.95 if application else 0.0, observed_at=observed_at, state="present" if destination_type != "unresolved" else "missing" if application else "unknown"),
        "description": field_record(raw_value=job.get("description_raw") or job.get("full_description") or job.get("description"), normalized_value={"raw_html": job.get("description_raw"), "sanitized_html": job.get("description_html"), "clean_text": job.get("description_text") or job.get("description")}, source=source if description else "", source_field="description", extraction_method="html_sanitization" if description else "not_available", evidence="description representations" if description else None, confidence=0.95 if description else 0.0, observed_at=observed_at, state="present" if description else "missing" if source_observation_id or source or observed_at else "unknown"),
        "experience": field_record(raw_value=experience.get("raw_value"), normalized_value={key: experience.get(key) for key in ("minimum_years", "maximum_years", "seniority", "requirement_status")}, source=source if experience.get("state") in VALUE_FIELD_STATES else "", source_field=experience.get("source") or "", extraction_method=experience.get("extraction_method") or "not_available", evidence=experience.get("evidence"), confidence=experience.get("confidence", 0.0), observed_at=observed_at, state=experience.get("state", "unknown")),
        "languages": field_record(raw_value=languages_raw, normalized_value=languages, source=source if languages else "", source_field=languages_field or "description.languages", extraction_method=languages_method if languages else "not_available", evidence=[item.get("evidence") for item in languages], confidence=max((float(item.get("confidence", 0.0)) for item in languages), default=0.0), observed_at=observed_at, state=language_state),
    }
    return {
        "schema_version": "unified_mapping_v1", "rule_version": UNIFIED_RULE_VERSION,
        "source_observation_id": source_observation_id or None, "observed_at": observed_at or None,
        "fields": fields, "company_fields": company_fields, "languages": languages, "experience": experience,
        "application_destination": application, "timestamps": timestamps,
        "company_urls": company_url_records(job, observed_at=observed_at),
        "function_taxonomy": list(FUNCTION_TAXONOMY), "employment_taxonomy": list(EMPLOYMENT_TYPES),
        "workplace_taxonomy": list(WORKPLACE_ARRANGEMENTS), "application_taxonomy": list(APPLICATION_DESTINATIONS),
    }


__all__ = [
    "APPLICATION_DESTINATIONS", "EMPLOYMENT_TYPES", "FUNCTION_TAXONOMY", "UNIFIED_RULE_VERSION",
    "FIELD_STATE_SET", "FIELD_STATES", "RULE_VERSION_REGISTRY", "VALUE_FIELD_STATES",
    "WORKPLACE_ARRANGEMENTS", "company_url_records", "field_record", "map_job_fields",
]
