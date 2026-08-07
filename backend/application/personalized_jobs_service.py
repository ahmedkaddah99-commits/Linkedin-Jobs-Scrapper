from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from backend.application.personalized_jobs_intelligence import (
    MATCH_V1_VERSION,
    MATCH_V2_VERSION,
    SUMMARY_PROMPT_VERSION,
    TAILORED_DOCUMENT_VERSION,
    _profile_context,
    build_description_intelligence,
    build_intelligence_cache_key,
    build_match_intelligence,
    build_tailored_document,
    build_preserved_original_posting,
)
from backend.config.plans import DEFAULT_PLAN_ID, normalize_plan_id
from backend.domain.personalized_jobs_contracts import CandidateSearchPreferences
from backend.domain.models import utc_now_iso
from backend.repositories.contracts import BackendRepositories
from backend.application.production_rollout import catalog_user_access
from backend.application.company_logo import cache_logo, deterministic_monogram, validate_logo
from backend.acquisition.phase_g import build_applicant_competition, build_priority


EVALUATOR_VERSION = MATCH_V2_VERSION
EVALUATION_STATES = {"loading", "pending", "available", "stale", "partial", "unavailable"}
_MISSING = object()
_PUBLIC_INTERNAL_KEYS = {
    "source_ats", "source_observation_id", "observation_url", "original_url",
    "provenance_url", "provenance", "internal_provenance", "source_identifier",
    "workspace_id", "run_id", "target_id", "cycle_id", "task_id",
    "canonical_url", "description_version", "version_id", "content_hash", "observed_at",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return " ".join(_text(value).casefold().replace("-", " ").replace("_", " ").split())


def _list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _unique_strings(value: Any) -> list[str]:
    result: list[str] = []
    for item in _list(value):
        if isinstance(item, Mapping):
            nested = item.get("countries") or item.get("values")
            if nested:
                for nested_item in _unique_strings(nested):
                    if nested_item not in result:
                        result.append(nested_item)
                continue
            item = item.get("value") or item.get("name") or item.get("language") or item.get("country_code") or item.get("status") or item.get("authorization_status")
        for part in _text(item).split(","):
            text = _text(part)
            if text and text not in result:
                result.append(text)
    return result


def _parse_json(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}
    return {}


def _public_clean(value: Any) -> Any:
    """Remove catalog provenance and source identifiers from public payloads."""
    if isinstance(value, Mapping):
        return {
            str(key): _public_clean(item)
            for key, item in value.items()
            if str(key).casefold() not in _PUBLIC_INTERNAL_KEYS
        }
    if isinstance(value, list):
        return [_public_clean(item) for item in value]
    if isinstance(value, tuple):
        return [_public_clean(item) for item in value]
    return value


def _pending_description() -> dict[str, Any]:
    return _public_clean({
        "state": "pending",
        "summary": {},
        "structured_description": {},
        "original_posting": {},
        "provider": None,
        "model": None,
        "prompt_version": None,
    })


def _pending_match() -> dict[str, Any]:
    return {"state": "pending", "score": None, "v1": {"state": "pending"}, "v2": {"state": "pending"}}


def _approved_apply_url(row: Mapping[str, Any]) -> str | None:
    value = _text(row.get("apply_url"))
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if value == _text(row.get("observation_url")):
        return None
    return value


def _alias(payload: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in payload and payload[name] not in (None, "", []):
            return payload[name]
    return None


def _epoch(value: Any) -> float | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _cursor_encode(value: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(value), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _cursor_decode(value: str) -> dict[str, Any]:
    try:
        padded = str(value) + "=" * (-len(str(value)) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("invalid_cursor") from exc
    if not isinstance(decoded, dict) or not decoded.get("fingerprint"):
        raise ValueError("invalid_cursor")
    return decoded


def _filter_fingerprint(filters: Mapping[str, Any], *, user_id: str, hidden_only: bool) -> str:
    material = json.dumps(
        {"user_id": user_id, "filters": dict(filters), "hidden_only": hidden_only},
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _canonical_filter_key(key: str) -> str:
    aliases = {
        "q": "search_text",
        "search": "search_text",
        "searchText": "search_text",
        "roles": "role",
        "target_roles": "role",
        "targetRoles": "role",
        "categories": "category",
        "workArrangement": "work_arrangement",
        "employmentType": "employment_type",
        "experience": "experience_level",
        "experienceLevel": "experience_level",
        "seniority": "experience_level",
        "salaryMin": "salary_min",
        "minimum_salary": "salary_min",
        "minimumSalary": "salary_min",
        "salaryMax": "salary_max",
        "languages": "language",
        "workAuthorization": "work_authorization",
        "sponsorshipRequirement": "sponsorship",
        "postedWithinDays": "posted_within_days",
        "companyName": "company",
        "companyIndustry": "industry",
        "companySize": "company_size",
        "companyStage": "company_stage",
        "fundingStage": "funding_stage",
        "fundingMin": "funding_min",
        "fundingMax": "funding_max",
        "fundingRangeMin": "funding_min",
        "fundingRangeMax": "funding_max",
        "foundedYearMin": "founded_year_min",
        "foundedYearMax": "founded_year_max",
        "fundingYearMin": "funding_year_min",
        "fundingYearMax": "funding_year_max",
        "hiddenCompanies": "hidden_companies",
        "excludedCompanies": "hidden_companies",
        "preferredMajor": "preferred_major",
        "preferredMajors": "preferred_major",
        "securityClearance": "security_clearance",
        "liftingRequirement": "lifting_requirement",
        "physicalRequirement": "lifting_requirement",
    }
    return aliases.get(key, key)


def normalize_filters(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for raw_key, raw_value in dict(payload or {}).items():
        key = _canonical_filter_key(str(raw_key))
        if raw_value in (None, "", [], {}):
            continue
        if key in {"role", "category", "location", "work_arrangement", "employment_type", "experience_level", "language", "work_authorization", "sponsorship", "company", "industry", "company_size", "company_stage", "funding_stage", "hidden_companies", "education", "preferred_major", "security_clearance", "lifting_requirement"}:
            normalized[key] = _unique_strings(raw_value)
        elif key in {"salary_min", "salary_max", "funding_min", "funding_max", "founded_year_min", "founded_year_max", "funding_year_min", "funding_year_max", "posted_within_days"}:
            try:
                normalized[key] = float(raw_value) if key in {"salary_min", "salary_max", "funding_min", "funding_max"} else int(raw_value)
            except (TypeError, ValueError):
                continue
        elif key in {"use_saved_search", "include_hidden"}:
            normalized[key] = str(raw_value).casefold() in {"1", "true", "yes", "on"} if not isinstance(raw_value, bool) else raw_value
        elif key == "sort":
            normalized[key] = _text(raw_value).casefold() or "newest"
        else:
            normalized[key] = raw_value
    return normalized


def normalize_preferences(payload: Mapping[str, Any], *, user_id: str, profile_id: str = "") -> dict[str, Any]:
    raw = dict(payload)
    nested = raw.get("preferences")
    if isinstance(nested, Mapping):
        raw = {**raw, **dict(nested)}
    mapping = {
        "targetRoles": "target_roles",
        "roleCategories": "target_roles",
        "preferredLocations": "preferred_locations",
        "preferredLocation": "preferred_locations",
        "countryCodes": "country_codes",
        "workArrangements": "work_arrangements",
        "workArrangement": "work_arrangements",
        "seniorityLevels": "seniority_levels",
        "experienceLevel": "seniority_levels",
        "employmentTypes": "employment_types",
        "employmentType": "employment_types",
        "minimumSalary": "minimum_salary",
        "salaryCurrency": "salary_currency",
        "workAuthorization": "work_authorization",
        "sponsorshipRequirement": "sponsorship_requirement",
        "sponsorshipRequired": "sponsorship_requirement",
        "relocationPreference": "relocation_preference",
        "profileId": "profile_id",
    }
    for source, target in mapping.items():
        if source in raw and target not in raw:
            raw[target] = raw[source]
    raw["profile_id"] = _text(profile_id or raw.get("profile_id")) or f"user:{user_id}"
    raw["user_id"] = user_id
    raw["target_roles"] = _unique_strings(raw.get("target_roles"))
    raw["keywords"] = [item.casefold() for item in _unique_strings(raw.get("keywords"))]
    raw["preferred_locations"] = _unique_strings(raw.get("preferred_locations"))
    raw["country_codes"] = [item.upper() for item in _unique_strings(raw.get("country_codes"))]
    raw["work_arrangements"] = [_norm(item).replace(" ", "_") for item in _list(raw.get("work_arrangements")) if _text(item)]
    raw["seniority_levels"] = _unique_strings(raw.get("seniority_levels"))
    raw["employment_types"] = [_norm(item).replace(" ", "_") for item in _list(raw.get("employment_types")) if _text(item)]
    languages = []
    for item in _list(raw.get("languages")):
        if isinstance(item, Mapping):
            language = _text(item.get("language") or item.get("name"))
            if language:
                languages.append({"language": language, "proficiency": item.get("proficiency")})
        elif _text(item):
            languages.append({"language": _text(item), "proficiency": None})
    raw["languages"] = languages
    authorization = []
    for item in _list(raw.get("work_authorization")):
        if isinstance(item, Mapping):
            authorization.append(dict(item))
        elif _text(item):
            authorization.append({"country_code": _text(item).upper(), "status": "unknown"})
    raw["work_authorization"] = authorization
    if isinstance(raw.get("sponsorship_requirement"), Mapping):
        raw["sponsorship_requirement"] = raw["sponsorship_requirement"].get("value") or "unknown"
    if isinstance(raw.get("sponsorship_requirement"), bool):
        raw["sponsorship_requirement"] = "required" if raw["sponsorship_requirement"] else "not_required"
    raw["sponsorship_requirement"] = _norm(raw.get("sponsorship_requirement") or "unknown").replace(" ", "_")
    if raw.get("minimum_salary") not in (None, ""):
        try:
            raw["minimum_salary"] = float(raw["minimum_salary"])
        except (TypeError, ValueError):
            raw.pop("minimum_salary", None)
    # Validate the canonical preference subset, then retain only the user-owned
    # preference document. Unknown optional keys are preserved for future UI use.
    canonical = CandidateSearchPreferences.from_dict(raw).to_dict()
    for key in ("filters", "industry", "company", "company_size", "company_stage", "funding_stage"):
        if key in raw:
            canonical[key] = raw[key]
    return canonical


def _preference_filters(preferences: Mapping[str, Any] | None) -> dict[str, Any]:
    if not preferences:
        return {}
    raw = dict(preferences)
    filters: dict[str, Any] = {}
    mapping = {
        "target_roles": "role",
        "preferred_locations": "location",
        "work_arrangements": "work_arrangement",
        "seniority_levels": "experience_level",
        "employment_types": "employment_type",
        "languages": "language",
        "work_authorization": "work_authorization",
    }
    for source, target in mapping.items():
        if raw.get(source):
            filters[target] = raw[source]
    if raw.get("keywords"):
        filters["search_text"] = raw["keywords"]
    if raw.get("minimum_salary") is not None:
        filters["salary_min"] = raw["minimum_salary"]
    if raw.get("sponsorship_requirement") not in (None, "", "unknown"):
        filters["sponsorship"] = [raw["sponsorship_requirement"]]
    extra = raw.get("filters")
    if isinstance(extra, Mapping):
        filters.update(extra)
    return normalize_filters(filters)


def _payload_for_row(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = _parse_json(row.get("version_payload_json"))
    nested = payload.get("job")
    if isinstance(nested, Mapping):
        payload = {**payload, **dict(nested)}
    return payload


def _value(payload: Mapping[str, Any], row: Mapping[str, Any], *names: str) -> Any:
    value = _alias(payload, *names)
    if value not in (None, "", []):
        return value
    return _alias(row, *names)


def _normalize_arrangement(value: Any) -> str | None:
    normalized = _norm(value)
    if not normalized:
        return None
    if normalized in {"remote", "fully remote", "work from home"}:
        return "remote"
    if normalized in {"hybrid", "flexible hybrid"}:
        return "hybrid"
    if normalized in {"onsite", "on site", "in person", "office"}:
        return "onsite"
    return normalized.replace(" ", "_")


def _salary(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    raw = _alias(payload, "salary", "salary_range", "compensation", "pay")
    if not isinstance(raw, Mapping):
        return None
    result: dict[str, Any] = {}
    for key in ("min", "minimum", "min_salary", "lower"):
        if raw.get(key) not in (None, ""):
            try:
                result["min"] = float(raw[key])
                break
            except (TypeError, ValueError):
                pass
    for key in ("max", "maximum", "max_salary", "upper"):
        if raw.get(key) not in (None, ""):
            try:
                result["max"] = float(raw[key])
                break
            except (TypeError, ValueError):
                pass
    currency = _alias(raw, "currency", "currency_code")
    if currency:
        result["currency"] = _text(currency).upper()
    return result or None


_COMPANY_FIELD_ALIASES = {
    "description": ("description", "company_description", "about"),
    "website": ("website", "company_website", "site"),
    "industry": ("industry", "company_industry"),
    "company_size": ("company_size", "size", "employees"),
    "headquarters": ("headquarters", "company_headquarters", "hq"),
    "founded_year": ("founded_year", "company_founded_year", "founded"),
    "company_stage": ("company_stage", "stage", "company_lifecycle_stage"),
    "funding_stage": ("funding_stage", "company_funding_stage"),
    "total_funding": ("total_funding", "total_funding_amount", "funding"),
    "funding_year": ("funding_year", "last_funding_year"),
    "leadership_type": ("leadership_type", "leadership"),
    "benefits": ("benefits", "company_benefits"),
    "sponsorship": ("sponsorship", "sponsorship_information", "sponsors_h1b"),
    "logo": ("logo_url", "logo", "company_logo"),
}


def _is_unknown_value(value: Any) -> bool:
    return isinstance(value, str) and value.strip().casefold() in {
        "unknown",
        "not available",
        "not disclosed",
        "undisclosed",
        "n/a",
    }


def _company_profile_fields(row: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    stored = _parse_json(row.get("company_profile_json"))
    fields = stored.get("fields") if isinstance(stored, Mapping) else {}
    fields = dict(fields) if isinstance(fields, Mapping) else {}
    payload = _payload_for_row(row)
    company_payload = payload.get("company") if isinstance(payload.get("company"), Mapping) else {}
    source = _text(row.get("source_ats")) or "official_employer_source"
    provenance_url = _text(row.get("company_provenance_url")) or _text(row.get("observation_url"))
    verified_at = _text(row.get("observation_observed_at")) or _text(row.get("last_verified_at"))
    result: dict[str, dict[str, Any]] = {}
    for field, aliases in _COMPANY_FIELD_ALIASES.items():
        record = fields.get(field)
        if isinstance(record, Mapping):
            record = dict(record)
        else:
            record = {}
        value = record.get("value")
        if value in (None, "", []) and field == "logo" and _text(row.get("company_logo_object_key")):
            value = _text(row.get("company_logo_source_url")) or None
        if value in (None, "", []):
            value = _alias(company_payload, *aliases) or _alias(payload, *aliases)
        if _is_unknown_value(value):
            value = None
        known = value not in (None, "", []) and str(record.get("state") or "known") != "unknown"
        if not record or (record.get("state") == "unknown" and value not in (None, "", [])):
            record = {
                "value": value if value not in (None, "", []) else None,
                "state": "known" if known else "unknown",
                "status": "known" if known else "unknown",
                "provenance": {"source": source if known else "", "url": provenance_url if known else ""},
                "observed_at": verified_at if known else "",
                "verified_at": verified_at if known else "",
            }
        else:
            record.setdefault("value", value if value not in (None, "", []) else None)
            record.setdefault("state", "known" if value not in (None, "", []) else "unknown")
            record.setdefault("provenance", {})
            record.setdefault("verified_at", "")
            record.setdefault("observed_at", "")
            record.setdefault("status", record.get("state") or "unknown")
            if _is_unknown_value(record.get("value")):
                record["value"] = None
                record["state"] = "unknown"
        result[field] = record
    return result


def _company_profile_value(fields: Mapping[str, Mapping[str, Any]], field: str) -> Any:
    record = fields.get(field)
    if not isinstance(record, Mapping) or str(record.get("state") or "") != "known":
        return None
    return record.get("value")


def _requirement_value(payload: Mapping[str, Any], *names: str) -> Any:
    value = _alias(payload, *names)
    if value not in (None, "", []):
        return value
    for parent_name in ("requirements", "job_requirements", "candidate_requirements"):
        parent = payload.get(parent_name)
        if isinstance(parent, Mapping):
            value = _alias(parent, *names)
            if value not in (None, "", []):
                return value
    return None


def _user_applicant_projection(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep competition evidence useful without exposing internal source names."""

    result = dict(value or {"state": "unknown", "visibility": "pro"})
    provenance = result.get("provenance")
    if isinstance(provenance, Mapping):
        public_provenance = dict(provenance)
        if public_provenance.get("source"):
            public_provenance["source"] = "verified source"
        result["provenance"] = public_provenance
    return result


def _job_projection(
    row: Mapping[str, Any],
    disposition: Mapping[str, Any] | None,
    evaluation: Mapping[str, Any],
    description_intelligence: Mapping[str, Any] | None = None,
    match_intelligence: Mapping[str, Any] | None = None,
    company_profile: Mapping[str, Any] | None = None,
    applicant_intelligence: Mapping[str, Any] | None = None,
    priority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _payload_for_row(row)
    salary = _salary(payload)
    title = _text(row.get("title") or payload.get("title"))
    location = _text(row.get("location") or row.get("version_location") or payload.get("location"))
    apply_url = _approved_apply_url(row)
    canonical_url = _text(row.get("canonical_url")) or None
    arrangement = _normalize_arrangement(_value(payload, row, "work_arrangement", "workplace", "workplace_type", "remote_type"))
    employment = _value(payload, row, "employment_type", "job_type", "type")
    experience = _value(payload, row, "experience_level", "seniority", "level")
    category = _value(payload, row, "category", "job_category", "role_category", "function")
    languages = _unique_strings(_value(payload, row, "languages", "language_requirements", "required_languages")) or None
    authorization = _value(payload, row, "work_authorization", "authorization", "work_permit", "visa_requirement")
    sponsorship = _value(payload, row, "sponsorship", "visa_sponsorship", "sponsors_h1b")
    projection = _public_clean({
        "posting_id": str(row.get("canonical_job_id") or ""),
        "canonical_job_id": str(row.get("canonical_job_id") or ""),
        "company_id": str(row.get("company_id") or ""),
        "company": _text(row.get("company")) or None,
        "company_detail": {
            "company_id": str(row.get("company_id") or ""),
            "name": _text(row.get("company")) or None,
            "entity_kind": _text(row.get("company_entity_kind")) or "unknown",
            "provenance_url": _text(row.get("company_provenance_url")) or None,
            "profile": dict(company_profile or {"fields": _company_profile_fields(row)}),
        },
        "title": title or None,
        "location": location or None,
        "work_arrangement": arrangement,
        "employment_type": _text(employment) or None,
        "experience_level": _text(experience) or None,
        "category": _text(category) or None,
        "description": _text(row.get("description") or payload.get("description")) or None,
        "salary": salary,
        "languages": languages,
        "work_authorization": authorization if authorization not in (None, "") else None,
        "sponsorship": sponsorship if sponsorship not in (None, "") else None,
        "posted_at": _text(_value(payload, row, "posted_at", "published_at", "date_posted")) or None,
        "first_seen_at": _text(row.get("first_seen_at")) or None,
        "last_seen_at": _text(row.get("last_seen_at")) or None,
        "last_verified_at": _text(row.get("last_verified_at")) or None,
        "canonical_url": canonical_url,
        "apply_url": apply_url,
        "lifecycle_state": _text(row.get("lifecycle_state")) or "unknown",
        "version_id": _text(row.get("current_version_id")) or None,
        "version": int(row.get("version_number") or 0) or None,
        "description_version": {
            "id": _text(row.get("current_version_id")) or None,
            "number": int(row.get("version_number") or 0) or None,
            "content_hash": _text(row.get("content_hash")) or None,
            "created_at": _text(row.get("version_created_at")) or None,
        },
        "user_state": _text((disposition or {}).get("state")) or "none",
        "evaluation": dict(evaluation),
        "runr_summary": dict((description_intelligence or {}).get("summary") or {}),
        "structured_description": dict((description_intelligence or {}).get("structured_description") or {}),
        "original_posting": dict((description_intelligence or {}).get("original_posting") or {}),
        "description_intelligence": {
            "state": _text((description_intelligence or {}).get("state")) or "unknown",
            "provider": _text((description_intelligence or {}).get("provider")) or None,
            "model": _text((description_intelligence or {}).get("model")) or None,
            "prompt_version": _text((description_intelligence or {}).get("prompt_version")) or None,
        },
        "match_intelligence": dict(match_intelligence or {}),
        "applicant_intelligence": _user_applicant_projection(applicant_intelligence),
        "priority": dict(priority or {"state": "unknown", "score": None}),
    })
    return projection


def _job_filter_values(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = _payload_for_row(row)
    projection = _job_projection(row, None, {})
    company_fields = _company_profile_fields(row)
    company_characteristics = payload.get("company") if isinstance(payload.get("company"), Mapping) else {}
    profile_value = lambda name, *aliases: _company_profile_value(company_fields, name) or _value(payload, row, *aliases)
    return {
        "search_text": " ".join(
            _text(value) for value in (
                projection.get("title"), projection.get("company"), projection.get("location"),
                projection.get("description"), _value(payload, row, "skills", "required_skills"),
            ) if value not in (None, "")
        ).casefold(),
        "role": _unique_strings(_value(payload, row, "role", "roles", "role_category", "job_category", "function", "title")),
        "category": _unique_strings(_value(payload, row, "category", "categories", "job_category", "role_category", "function")),
        "location": [projection.get("location")] if projection.get("location") else [],
        "work_arrangement": [projection.get("work_arrangement")] if projection.get("work_arrangement") else [],
        "employment_type": _unique_strings(projection.get("employment_type")),
        "experience_level": _unique_strings(projection.get("experience_level")),
        "company": [projection.get("company")] if projection.get("company") else [],
        "industry": _unique_strings(profile_value("industry", "industry", "company_industry") or company_characteristics.get("industry")),
        "company_size": _unique_strings(profile_value("company_size", "company_size", "size") or company_characteristics.get("size")),
        "company_stage": _unique_strings(profile_value("company_stage", "company_stage", "stage") or _value(payload, row, "company_stage") or company_characteristics.get("stage")),
        "funding_stage": _unique_strings(profile_value("funding_stage", "funding_stage") or company_characteristics.get("funding_stage")),
        "education": _unique_strings(_requirement_value(payload, "education", "education_level", "degree", "required_education")),
        "preferred_major": _unique_strings(_requirement_value(payload, "preferred_major", "preferred_majors", "major", "majors")),
        "security_clearance": _unique_strings(_requirement_value(payload, "security_clearance", "clearance", "security_clearance_required")),
        "lifting_requirement": _unique_strings(_requirement_value(payload, "lifting_requirement", "physical_requirement", "physical_requirements", "lifting")),
        "language": _unique_strings(projection.get("languages")),
        "work_authorization": _unique_strings(projection.get("work_authorization")),
        "sponsorship": _unique_strings(profile_value("sponsorship", "sponsorship", "visa_sponsorship", "sponsors_h1b") or projection.get("sponsorship")),
        "salary": _salary(payload),
        "total_funding": profile_value("total_funding", "total_funding", "total_funding_amount", "funding"),
        "founded_year": profile_value("founded_year", "founded_year", "company_founded_year", "founded"),
        "funding_year": profile_value("funding_year", "funding_year", "last_funding_year"),
        "posted_at": projection.get("posted_at"),
    }


def _matches(row: Mapping[str, Any], filters: Mapping[str, Any]) -> tuple[bool, list[str]]:
    values = _job_filter_values(row)
    unknown: list[str] = []
    hidden_companies = _unique_strings(filters.get("hidden_companies"))
    company_name = _norm(row.get("company"))
    if hidden_companies and company_name and any(_norm(item) in company_name for item in hidden_companies):
        return False, unknown
    for field, requested in filters.items():
        requested_values = _unique_strings(requested)
        if field in {"include_hidden", "use_saved_search", "hidden_companies", "sort"} or not requested_values:
            continue
        if field == "search_text":
            terms = _unique_strings(requested)
            if not all(_norm(term) in values["search_text"] for term in terms):
                return False, unknown
        elif field in {"role", "category", "location", "work_arrangement", "employment_type", "experience_level", "company", "industry", "company_size", "company_stage", "funding_stage", "language", "work_authorization", "sponsorship", "education", "preferred_major", "security_clearance", "lifting_requirement"}:
            actual = [_norm(value) for value in values.get(field, []) if _text(value)]
            if field == "sponsorship" and any(_norm(value) == "unknown" for value in requested_values) and not actual:
                continue
            if not actual:
                unknown.append(field)
                return False, unknown
            wanted = [_norm(value) for value in requested_values]
            if field == "work_arrangement":
                wanted = [_normalize_arrangement(value) or _norm(value) for value in requested_values]
            if field == "company":
                if not any(wanted_value == actual_value for wanted_value in wanted for actual_value in actual):
                    return False, unknown
            elif not any(wanted_value in actual_value or actual_value in wanted_value for wanted_value in wanted for actual_value in actual):
                return False, unknown
        elif field in {"salary_min", "salary_max"}:
            salary = values.get("salary") or {}
            if not salary:
                unknown.append("salary")
                return False, unknown
            try:
                amount = float(salary.get("max") if field == "salary_min" else salary.get("min"))
                boundary = float(requested_values[0])
            except (TypeError, ValueError):
                unknown.append("salary")
                return False, unknown
            if field == "salary_min" and amount < boundary:
                return False, unknown
            if field == "salary_max" and amount > boundary:
                return False, unknown
        elif field in {"funding_min", "funding_max"}:
            raw_amount = values.get("total_funding")
            if raw_amount in (None, ""):
                unknown.append("total_funding")
                return False, unknown
            try:
                amount = float(raw_amount)
                boundary = float(requested_values[0])
            except (TypeError, ValueError):
                unknown.append("total_funding")
                return False, unknown
            if field == "funding_min" and amount < boundary:
                return False, unknown
            if field == "funding_max" and amount > boundary:
                return False, unknown
        elif field in {"founded_year_min", "founded_year_max", "funding_year_min", "funding_year_max"}:
            source = "founded_year" if field.startswith("founded") else "funding_year"
            raw_year = values.get(source)
            if raw_year in (None, ""):
                unknown.append(source)
                return False, unknown
            try:
                year = int(float(raw_year))
                boundary = int(float(requested_values[0]))
            except (TypeError, ValueError):
                unknown.append(source)
                return False, unknown
            if field.endswith("_min") and year < boundary:
                return False, unknown
            if field.endswith("_max") and year > boundary:
                return False, unknown
        elif field == "posted_within_days":
            posted = _epoch(values.get("posted_at"))
            if posted is None:
                unknown.append("posted_within_days")
                return False, unknown
            if posted < (datetime.now(timezone.utc) - timedelta(days=int(float(requested_values[0])))).timestamp():
                return False, unknown
    return True, unknown


def _filter_capabilities(rows: Iterable[Mapping[str, Any]]) -> dict[str, bool]:
    capabilities = {
        "salary": False,
        "language": False,
        "work_authorization": False,
        "sponsorship": False,
        "industry": False,
        "company_size": False,
        "company_stage": False,
        "funding_stage": False,
        "funding_range": False,
        "founded_year": False,
        "funding_year": False,
        "education": False,
        "preferred_major": False,
        "security_clearance": False,
        "lifting_requirement": False,
        "posting_recency": False,
        "hidden_companies": False,
    }
    for row in rows:
        values = _job_filter_values(row)
        capabilities["salary"] = capabilities["salary"] or bool(values.get("salary"))
        capabilities["language"] = capabilities["language"] or bool(values.get("language"))
        capabilities["work_authorization"] = capabilities["work_authorization"] or bool(values.get("work_authorization"))
        capabilities["sponsorship"] = capabilities["sponsorship"] or bool(values.get("sponsorship"))
        for name in ("industry", "company_size", "company_stage", "funding_stage", "education", "preferred_major", "security_clearance", "lifting_requirement"):
            capabilities[name] = capabilities[name] or bool(values.get(name))
        capabilities["funding_range"] = capabilities["funding_range"] or values.get("total_funding") not in (None, "")
        capabilities["founded_year"] = capabilities["founded_year"] or values.get("founded_year") not in (None, "")
        capabilities["funding_year"] = capabilities["funding_year"] or values.get("funding_year") not in (None, "")
        capabilities["posting_recency"] = capabilities["posting_recency"] or bool(values.get("posted_at"))
        capabilities["hidden_companies"] = capabilities["hidden_companies"] or bool(values.get("company"))
    return capabilities


class PersonalizedJobsService:
    def __init__(self, *, repositories: BackendRepositories, object_storage: Any = None):
        self.repositories = repositories
        self.object_storage = object_storage

    @property
    def store(self):
        return self.repositories.personalized_jobs_store

    def _assert_catalog_access(self, user_id: str) -> None:
        if not catalog_user_access(getattr(self.repositories, "config_store", None), user_id):
            raise PermissionError("jobs_catalog_rollout_not_available")

    def _company_profile(self, row: Mapping[str, Any]) -> dict[str, Any]:
        fields = _company_profile_fields(row)
        for field, record in list(fields.items()):
            if not isinstance(record, Mapping):
                continue
            provenance = record.get("provenance")
            if isinstance(provenance, Mapping) and provenance.get("source"):
                sanitized = dict(record)
                sanitized["provenance"] = {**dict(provenance), "source": "verified source"}
                fields[field] = sanitized
        logo_object_key = _text(row.get("company_logo_object_key"))
        logo_url = _text(row.get("company_logo_source_url")) if logo_object_key else ""
        logo_record = dict(fields.get("logo") or {})
        if logo_url:
            logo_record["value"] = logo_url
            logo_record["state"] = "known"
        fields["logo"] = logo_record
        return _public_clean({
            "schema_version": "phase_f_v2",
            "fields": fields,
            "logo_url": logo_url or None,
            "logo_cached": bool(logo_object_key),
            "monogram": deterministic_monogram(_text(row.get("company")) or _text(row.get("canonical_name"))),
            "profile_updated_at": _text(row.get("profile_updated_at")),
        })

    @staticmethod
    def _cache_entry_for_key(key: Mapping[str, Any], entries: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
        fields = (
            "user_id", "canonical_job_id", "job_version_id", "profile_version_id",
            "cv_version_id", "evidence_version_id", "evaluator_version", "input_hash",
            "intelligence_kind",
        )
        wanted = tuple(str(key.get(field) or "") for field in fields)
        for entry in entries:
            if tuple(str(entry.get(field) or "") for field in fields) == wanted:
                return entry
        return None

    def _description_intelligence(
        self,
        row: Mapping[str, Any],
        *,
        cache_entries: Iterable[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        original = build_preserved_original_posting(row)
        key = build_intelligence_cache_key(
            row,
            intelligence_kind="description",
            evaluator_version=SUMMARY_PROMPT_VERSION,
        )
        cached = self._cache_entry_for_key(key, cache_entries or ()) if cache_entries is not None else (self.store.get_intelligence_cache(key) if self.store is not None else None)
        if cached is not None and _text(cached.get("state")) == "available":
            result = dict(cached.get("payload") or {})
            result["state"] = "available"
            result["original_posting"] = _public_clean(result.get("original_posting") or original)
            return _public_clean(result)
        pending = _pending_description()
        pending["original_posting"] = _public_clean(original)
        pending["prompt_version"] = SUMMARY_PROMPT_VERSION
        return pending

    def enqueue_intelligence_for_job(self, user_id: str, posting_id: str) -> dict[str, Any]:
        """Queue description and match work from a worker/precompute boundary.

        Jobs and Company GET handlers must remain read-only with respect to
        intelligence generation. Publication workers or an explicit admin
        precompute job call this method instead.
        """
        if self.store is None:
            return {"state": "unavailable", "cache_ids": []}
        row = self.store.get_published_job_row(posting_id)
        if row is None:
            raise KeyError("job_not_found")
        keys: list[dict[str, str]] = [
            build_intelligence_cache_key(
                row,
                intelligence_kind="description",
                evaluator_version=SUMMARY_PROMPT_VERSION,
            )
        ]
        preferences = self.get_preferences(user_id)
        profile = _profile_context(
            user_id,
            preferences,
            getattr(self.repositories, "career_profile_store", None),
        )
        keys.extend(
            build_intelligence_cache_key(
                row,
                intelligence_kind="match",
                user_id=user_id,
                profile=profile,
                evaluator_version=evaluator_version,
                description={"prompt_version": SUMMARY_PROMPT_VERSION},
            )
            for evaluator_version in (MATCH_V1_VERSION, MATCH_V2_VERSION)
        )
        queued: list[str] = []
        available: list[str] = []
        for key in keys:
            cached = self.store.get_intelligence_cache(key)
            if cached is not None and _text(cached.get("state")) == "available":
                available.append(_text(key.get("cache_id")))
                continue
            self.store.enqueue_intelligence(key)
            queued.append(_text(key.get("cache_id")))
        return {
            "state": "available" if not queued else "queued",
            "canonical_job_id": _text(row.get("canonical_job_id")),
            "job_version_id": _text(row.get("current_version_id")),
            "cache_ids": queued + available,
            "queued_cache_ids": queued,
            "available_cache_ids": available,
        }

    def _match_intelligence(
        self,
        user_id: str,
        row: Mapping[str, Any],
        description_intelligence: Mapping[str, Any],
        preferences_record: Mapping[str, Any] | None,
        *,
        state: str,
        cache_entries: Iterable[Mapping[str, Any]] | None = None,
        evaluation_record: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        evaluation_payload = evaluation_record.get("payload") if isinstance(evaluation_record, Mapping) else None
        if isinstance(evaluation_payload, str):
            evaluation_payload = _parse_json(evaluation_payload)
        cached_match = evaluation_payload.get("match_intelligence") if isinstance(evaluation_payload, Mapping) else None
        if isinstance(cached_match, Mapping):
            result = dict(cached_match)
            result["state"] = _text(evaluation_record.get("state")) or state
            return _public_clean(result)
        profile = _profile_context(
            user_id,
            preferences_record,
            getattr(self.repositories, "career_profile_store", None),
        )
        cached_versions: dict[str, Mapping[str, Any]] = {}
        for evaluator_version in (MATCH_V1_VERSION, MATCH_V2_VERSION):
            key = build_intelligence_cache_key(
                row,
                intelligence_kind="match",
                user_id=user_id,
                profile=profile,
                evaluator_version=evaluator_version,
                description=description_intelligence,
            )
            cached = self._cache_entry_for_key(key, cache_entries or ()) if cache_entries is not None else (self.store.get_intelligence_cache(key) if self.store is not None else None)
            if cached is not None and _text(cached.get("state")) == "available":
                cached_intelligence = (cached.get("payload") or {}).get("match_intelligence")
                if isinstance(cached_intelligence, Mapping):
                    cached_versions[evaluator_version] = cached_intelligence

        if len(cached_versions) == 2:
            match = dict(cached_versions[MATCH_V2_VERSION])
            match["state"] = state
            return match
        job_version = {
            "canonical_job_id": _text(row.get("canonical_job_id")),
            "id": _text(row.get("current_version_id")),
            "number": int(row.get("version_number") or 0) or None,
            "content_hash": _text(row.get("content_hash")),
        }
        pending_score = lambda evaluator: {
            "score": None,
            "score_scale": "0-100",
            "status": "pending",
            "evaluator": {"name": "runr_match_intelligence", "version": evaluator},
            "job_version": job_version,
            "profile_version": {
                "id": _text(profile.get("version_id")),
                "profile_id": _text(profile.get("profile_id")),
                "cv_version_id": _text(profile.get("cv_version_id")),
                "evidence_version_id": _text(profile.get("evidence_version_id")),
            },
            "formula": "pending",
        }
        return {
            "state": "pending",
            "v1": dict(cached_versions.get(MATCH_V1_VERSION) or pending_score(MATCH_V1_VERSION)),
            "v2": dict(cached_versions.get(MATCH_V2_VERSION) or pending_score(MATCH_V2_VERSION)),
            "difference": {"score_delta": None, "summary": "Scores are being precomputed from this job version and your current evidence."},
            "evaluator": {"name": "runr_match_intelligence", "versions": [MATCH_V1_VERSION, MATCH_V2_VERSION]},
            "profile_version": {"id": _text(profile.get("version_id")), "cv_version_id": _text(profile.get("cv_version_id")), "evidence_version_id": _text(profile.get("evidence_version_id"))},
            "job_version": job_version,
            "evaluated_at": None,
            "improve_resume": {"free_explanations": [], "rewriting_available": False, "tailored_documents_available": False},
        }

    def process_next_intelligence(self) -> dict[str, Any] | None:
        """Worker-only entry point; GET paths never call this method."""
        if self.store is None:
            return None
        queued = self.store.claim_next_intelligence()
        if queued is None:
            return None
        cache_id = _text(queued.get("cache_id"))
        row = self.store.get_published_job_row(_text(queued.get("canonical_job_id")))
        if row is None:
            self.store.complete_intelligence(cache_id, state="failed", payload={}, error="job_version_not_found")
            return {"cache_id": cache_id, "state": "failed"}
        kind = _text(queued.get("intelligence_kind"))
        try:
            if kind == "description":
                generated = build_description_intelligence(row)
                self.store.complete_intelligence(cache_id, state="available", payload=generated)
                # Keep the original Phase E description projection populated
                # for existing readers; generation still happens only here,
                # in the worker boundary.
                self.store.save_description_intelligence(
                    version_id=_text(row.get("current_version_id")),
                    canonical_job_id=_text(row.get("canonical_job_id")),
                    content_hash=_text(row.get("content_hash")),
                    summary=generated.get("summary") or {},
                    structured_description=generated.get("structured_description") or {},
                    original_posting=generated.get("original_posting") or {},
                    provider=_text(generated.get("provider")),
                    model=_text(generated.get("model")),
                    prompt_version=_text(generated.get("prompt_version")),
                )
            elif kind == "match":
                preferences = self.get_preferences(_text(queued.get("user_id")))
                profile = _profile_context(_text(queued.get("user_id")), preferences, getattr(self.repositories, "career_profile_store", None))
                description_key = build_intelligence_cache_key(row, intelligence_kind="description", evaluator_version=SUMMARY_PROMPT_VERSION)
                description_cache = self.store.get_intelligence_cache(description_key)
                description = (description_cache or {}).get("payload") if description_cache else None
                if not isinstance(description, Mapping):
                    description = build_description_intelligence(row)
                match = build_match_intelligence(row, description, profile)
                self.store.complete_intelligence(cache_id, state="available", payload={"match_intelligence": match})
            elif kind == "tailored_document":
                preferences = self.get_preferences(_text(queued.get("user_id")))
                profile = _profile_context(_text(queued.get("user_id")), preferences, getattr(self.repositories, "career_profile_store", None))
                description_key = build_intelligence_cache_key(row, intelligence_kind="description", evaluator_version=SUMMARY_PROMPT_VERSION)
                description_cache = self.store.get_intelligence_cache(description_key)
                description = (description_cache or {}).get("payload") if description_cache else None
                if not isinstance(description, Mapping):
                    description = build_description_intelligence(row)
                match = build_match_intelligence(row, description, profile)
                generated = build_tailored_document(row, profile, match)
                self.store.complete_intelligence(cache_id, state="available", payload={"generation": generated})
            else:
                self.store.complete_intelligence(cache_id, state="failed", payload={}, error="unknown_intelligence_kind")
        except Exception as exc:
            self.store.complete_intelligence(cache_id, state="failed", payload={}, error=str(exc))
        return {"cache_id": cache_id, "state": "available" if kind in {"description", "match", "tailored_document"} else "failed"}

    @staticmethod
    def _apply_plan_entitlements(match: Mapping[str, Any], plan_id: str) -> dict[str, Any]:
        result = dict(match)
        review = dict(result.get("improve_resume") or {})
        result["improve_resume"] = {
            **review,
            "review_available": True,
            "rewriting_available": normalize_plan_id(plan_id) != DEFAULT_PLAN_ID,
            "tailored_documents_available": normalize_plan_id(plan_id) != DEFAULT_PLAN_ID,
            "required_plan": "Runr Pro",
        }
        result["entitlements"] = {
            "match_scores": {"free": True, "pro": True},
            "evidence_review": {"free": True, "pro": True},
            "rewriting": {"free": False, "pro": True},
            "tailored_documents": {"free": False, "pro": True},
        }
        return result

    def improve_resume(self, user_id: str, posting_id: str, *, mode: str = "review", plan_id: str = DEFAULT_PLAN_ID) -> dict[str, Any]:
        detail = self.detail(user_id, posting_id, plan_id=plan_id)
        if detail is None:
            raise KeyError("job_not_found")
        match = detail.get("match_intelligence") if isinstance(detail.get("match_intelligence"), Mapping) else {}
        evidence = {
            "matched_keywords": list((match.get("v2") or {}).get("matched_keywords") or []),
            "missing_keywords": list((match.get("v2") or {}).get("missing_keywords") or []),
            "matched_requirements": list((match.get("v2") or {}).get("matched_requirements") or []),
            "unproven_requirements": list((match.get("v2") or {}).get("unproven_requirements") or []),
            "apparent_non_matches": list((match.get("v2") or {}).get("apparent_non_matches") or []),
            "v1_v2_difference": dict(match.get("difference") or {}),
            "matched_evidence": list((match.get("v2") or {}).get("matched_evidence") or []),
            "missing_evidence": list((match.get("v2") or {}).get("missing_evidence") or []),
        }
        if _text(mode).casefold() in {"rewrite", "generate", "tailored"}:
            if normalize_plan_id(plan_id) == DEFAULT_PLAN_ID:
                raise PermissionError("runr_pro_required_for_rewriting")
            row = self.store.get_published_job_row(posting_id) if self.store is not None else None
            if row is None:
                raise KeyError("job_not_found")
            preferences = self.get_preferences(user_id)
            profile = _profile_context(user_id, preferences, getattr(self.repositories, "career_profile_store", None))
            key = build_intelligence_cache_key(
                row,
                intelligence_kind="tailored_document",
                user_id=user_id,
                profile=profile,
                evaluator_version=TAILORED_DOCUMENT_VERSION,
                description={"prompt_version": SUMMARY_PROMPT_VERSION},
            )
            cached = self.store.get_intelligence_cache(key)
            if cached is not None and _text(cached.get("state")) == "available":
                generation = (cached.get("payload") or {}).get("generation") or {}
                return {
                    "state": "available",
                    "entitlement": {"available": True, "plan": "Runr Pro"},
                    "evidence": evidence,
                    "generation": generation,
                }
            self.store.enqueue_intelligence(key)
            return {
                "state": "queued",
                "entitlement": {"available": True, "plan": "Runr Pro"},
                "evidence": evidence,
                "generation": {"state": "queued", "cache_id": key["cache_id"], "message": "Tailored document generation has been queued for the worker."},
            }
        return {
            "state": _text(match.get("state")) or "pending",
            "entitlement": {"available": True, "plan": "Free" if normalize_plan_id(plan_id) == DEFAULT_PLAN_ID else "Runr Pro"},
            "evidence": evidence,
            "guardrail": "Use only evidence you can truthfully support; never claim unsupported experience.",
        }

    def get_preferences(self, user_id: str) -> dict[str, Any] | None:
        return self.store.get_preferences(user_id) if self.store is not None else None

    def upsert_preferences(self, user_id: str, payload: Mapping[str, Any], *, expected_revision: int | None = None) -> dict[str, Any]:
        profile_id = _text(payload.get("profile_id") or payload.get("profileId"))
        normalized = normalize_preferences(payload, user_id=user_id, profile_id=profile_id)
        if self.store is None:
            return {"user_id": user_id, "profile_id": normalized["profile_id"], "revision": 1, "preferences": normalized}
        result = self.store.upsert_preferences(user_id, normalized, profile_id=normalized["profile_id"], expected_revision=expected_revision)
        self.store.record_event(user_id, event_name="preferences_updated", payload={"revision": result["revision"]})
        return result

    def get_saved_search(self, user_id: str) -> dict[str, Any] | None:
        return self.store.get_default_saved_search(user_id) if self.store is not None else None

    def upsert_saved_search(self, user_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        raw_filters = payload.get("filters") if isinstance(payload.get("filters"), Mapping) else payload
        filters = normalize_filters(raw_filters)
        name = _text(payload.get("name")) or "Default search"
        if self.store is None:
            return {"user_id": user_id, "name": name, "filters": filters, "is_default": True}
        result = self.store.upsert_default_saved_search(user_id, filters, name=name)
        self.store.record_event(user_id, event_name="saved_search_updated", payload={"saved_search_id": result["saved_search_id"]})
        return result

    def feed(
        self,
        user_id: str,
        *,
        filters: Mapping[str, Any] | None = None,
        cursor: str = "",
        limit: int = 25,
        include_hidden: bool = False,
        hidden_only: bool = False,
        plan_id: str = DEFAULT_PLAN_ID,
    ) -> dict[str, Any]:
        self._assert_catalog_access(user_id)
        limit = max(1, min(100, int(limit)))
        explicit_filters = normalize_filters(filters)
        preferences_record = self.get_preferences(user_id)
        preferences = preferences_record.get("preferences") if preferences_record else None
        saved = self.get_saved_search(user_id)
        effective_filters = _preference_filters(preferences)
        if not explicit_filters and saved and isinstance(saved.get("filters"), Mapping):
            effective_filters.update(normalize_filters(saved["filters"]))
        effective_filters.update(explicit_filters)
        sort_mode = _text(effective_filters.get("sort") or "newest").casefold()
        if sort_mode not in {"newest", "priority", "best"}:
            sort_mode = "newest"
        include_pro = normalize_plan_id(plan_id) != DEFAULT_PLAN_ID
        if not include_pro and sort_mode in {"priority", "best"}:
            sort_mode = "newest"
        effective_filters["sort"] = sort_mode
        fingerprint = _filter_fingerprint(effective_filters, user_id=user_id, hidden_only=hidden_only)
        cursor_payload = _cursor_decode(cursor) if cursor else None
        if cursor_payload is not None and cursor_payload.get("fingerprint") != fingerprint:
            raise ValueError("cursor_filter_mismatch")

        if self.store is None:
            return self._empty_feed(effective_filters, state="unavailable")
        result = self.store.query_published_jobs(
            user_id,
            filters=effective_filters,
            limit=limit,
            cursor=cursor_payload,
            include_hidden=include_hidden,
            hidden_only=hidden_only,
        )
        publication = result.get("publication")
        if publication is None:
            return self._empty_feed(effective_filters, state="unavailable")
        catalog_state = self._publication_state(publication)
        rows = list(result.get("rows") or [])
        has_more = len(rows) > limit
        page = rows[:limit]
        if has_more and page:
            last = page[-1]
            next_cursor = _cursor_encode({
                "fingerprint": fingerprint,
                "sort_mode": sort_mode,
                "sort": _text(last.get("last_verified_at") or last.get("first_seen_at")),
                "priority": last.get("priority_score"),
                "canonical_job_id": _text(last.get("canonical_job_id")),
            })
        else:
            next_cursor = ""
        job_ids = [str(row.get("canonical_job_id") or "") for row in page]
        dispositions = self.store.list_dispositions_for_jobs(user_id, job_ids)
        cache_entries = self.store.list_intelligence_cache_entries(job_ids, intelligence_kind="description")
        match_entries = self.store.list_intelligence_cache_entries(job_ids, user_id=user_id, intelligence_kind="match")
        evaluation_records = self.store.list_evaluations_for_jobs(
            user_id,
            job_ids,
            preferences_revision=int((preferences_record or {}).get("revision") or 0),
            evaluator_version=MATCH_V2_VERSION,
        )
        state = catalog_state if catalog_state in EVALUATION_STATES else "partial"
        jobs: list[dict[str, Any]] = []
        for row in page:
            description_intelligence = self._description_intelligence(row, cache_entries=cache_entries)
            match_intelligence = self._match_intelligence(
                user_id,
                row,
                description_intelligence,
                preferences_record,
                state=state,
                cache_entries=match_entries,
                evaluation_record=evaluation_records.get(str(row.get("canonical_job_id"))),
            )
            evaluation_status = "not_evaluated" if not preferences_record and not effective_filters else ("pending" if _text(match_intelligence.get("state")) == "pending" else "eligible")
            evaluation = {
                "state": state,
                "status": evaluation_status,
                "unknown_fields": [],
                "evaluator_version": EVALUATOR_VERSION,
                "match_intelligence": match_intelligence,
            }
            applicant_intelligence = build_applicant_competition(row, include_pro=include_pro)
            priority = build_priority(row, match_intelligence, applicant_intelligence)
            jobs.append(_job_projection(
                row,
                dispositions.get(str(row.get("canonical_job_id"))),
                evaluation,
                description_intelligence,
                match_intelligence,
                self._company_profile(row),
                applicant_intelligence,
                priority,
            ))
        return {
            "jobs": jobs,
            "total": int(result.get("total") or 0),
            "next_cursor": next_cursor or None,
            "filters": effective_filters,
            "filter_capabilities": self.store.get_published_filter_capabilities(),
            "evaluation": {
                "state": state,
                "supported_states": sorted(EVALUATION_STATES),
                "catalog_state": catalog_state,
                "preferences_revision": int((preferences_record or {}).get("revision") or 0),
                "evaluated_at": _text(publication.get("published_at")) or None,
            },
            "publication": {
                "publication_id": _text(publication.get("publication_id")),
                "cycle_id": _text(publication.get("cycle_id")),
                "published_at": _text(publication.get("published_at")),
                "valid_until": _text(publication.get("valid_until")),
            },
        }

    def detail(self, user_id: str, posting_id: str, *, plan_id: str = DEFAULT_PLAN_ID) -> dict[str, Any] | None:
        self._assert_catalog_access(user_id)
        if self.store is None:
            return None
        row = self.store.get_published_job_row(posting_id)
        if row is None:
            return None
        disposition = self.store.list_dispositions_for_jobs(user_id, [posting_id]).get(posting_id)
        preferences = self.get_preferences(user_id)
        publication = self.store.get_current_publication()
        catalog_state = self._publication_state(publication) if publication is not None else "unavailable"
        cache_entries = self.store.list_intelligence_cache_entries([posting_id], intelligence_kind="description")
        match_entries = self.store.list_intelligence_cache_entries([posting_id], user_id=user_id, intelligence_kind="match")
        description_intelligence = self._description_intelligence(row, cache_entries=cache_entries)
        match_intelligence = self._match_intelligence(
            user_id,
            row,
            description_intelligence,
            preferences,
            state=catalog_state if catalog_state in EVALUATION_STATES else "partial",
            cache_entries=match_entries,
            evaluation_record=self.store.get_evaluation(
                user_id,
                posting_id,
                job_version_id=_text(row.get("current_version_id")),
                preferences_revision=int((preferences or {}).get("revision") or 0),
                evaluator_version=MATCH_V2_VERSION,
            ),
        )
        match_intelligence = self._apply_plan_entitlements(match_intelligence, plan_id)
        evaluation_payload = {
            "state": catalog_state if catalog_state in EVALUATION_STATES else "partial",
            "status": "pending" if _text(match_intelligence.get("state")) == "pending" else "available",
            "evaluator_version": EVALUATOR_VERSION,
        }
        evaluation_payload["match_intelligence"] = match_intelligence
        include_pro = normalize_plan_id(plan_id) != DEFAULT_PLAN_ID
        applicant_intelligence = build_applicant_competition(row, include_pro=include_pro)
        return _job_projection(
            row,
            disposition,
            evaluation_payload,
            description_intelligence,
            match_intelligence,
            self._company_profile(row),
            applicant_intelligence,
            {"state": "pending", "score": None},
        )

    def _company_job_projection(
        self,
        user_id: str,
        row: Mapping[str, Any],
        dispositions: Mapping[str, Mapping[str, Any]],
        preferences: Mapping[str, Any] | None,
        *,
        include_pro: bool = False,
    ) -> dict[str, Any]:
        description_intelligence = self._description_intelligence(row)
        match_intelligence = _pending_match()
        evaluation = {
            "state": "available",
            "status": "pending",
            "evaluator_version": EVALUATOR_VERSION,
            "match_intelligence": match_intelligence,
        }
        return _job_projection(
            row,
            dispositions.get(str(row.get("canonical_job_id"))),
            evaluation,
            description_intelligence,
            match_intelligence,
            self._company_profile(row),
            {"state": "unknown", "visibility": "pro"},
            {"state": "pending", "score": None},
        )

    def upsert_company_profile(
        self,
        company_id: str,
        payload: Mapping[str, Any],
        *,
        logo_bytes: bytes | None = None,
        logo_source_url: str = "",
        logo_content_type: str = "image/png",
    ) -> dict[str, Any]:
        """Persist verified enrichment; intended for worker/admin enrichment paths."""
        if self.store is None:
            raise RuntimeError("personalized_jobs_store_unavailable")
        raw = payload.get("fields") if isinstance(payload.get("fields"), Mapping) else payload
        existing = self.store.get_company_profile(str(company_id)) or {}
        existing_profile = existing.get("profile") if isinstance(existing.get("profile"), Mapping) else {}
        existing_fields = existing_profile.get("fields") if isinstance(existing_profile, Mapping) else {}
        existing_fields = existing_fields if isinstance(existing_fields, Mapping) else {}
        payload_source = _text(payload.get("source")) if isinstance(payload, Mapping) else ""
        payload_url = _text(payload.get("provenance_url")) if isinstance(payload, Mapping) else ""
        payload_observed = _text(payload.get("observed_at")) if isinstance(payload, Mapping) else ""
        payload_verified = _text(payload.get("verified_at")) if isinstance(payload, Mapping) else ""
        fields: dict[str, Any] = {}
        for field in _COMPANY_FIELD_ALIASES:
            value = raw.get(field) if isinstance(raw, Mapping) else None
            if isinstance(value, Mapping):
                record = dict(value)
                record_value = record.get("value")
                record["value"] = record_value if record_value not in (None, "", []) else None
                record["state"] = "known" if record["value"] is not None and not _is_unknown_value(record["value"]) and str(record.get("state") or "") != "unknown" else "unknown"
                provenance = record.get("provenance") if isinstance(record.get("provenance"), Mapping) else {}
                record["provenance"] = {
                    "source": _text(provenance.get("source")) or payload_source,
                    "url": _text(provenance.get("url")) or payload_url,
                }
                record["observed_at"] = _text(record.get("observed_at")) or payload_observed
                record["verified_at"] = _text(record.get("verified_at")) or payload_verified
                record["status"] = "known" if record["state"] == "known" else "unknown"
            else:
                known = value not in (None, "", []) and not _is_unknown_value(value)
                record = {
                    "value": value if known else None,
                    "state": "known" if known else "unknown",
                    "status": "known" if known else "unknown",
                    "provenance": {
                        "source": payload_source,
                        "url": payload_url,
                    },
                    "observed_at": payload_observed,
                    "verified_at": payload_verified,
                    "unknown_reason": "not_verified" if not known else "",
                }
            old = existing_fields.get(field)
            old_known = isinstance(old, Mapping) and str(old.get("state") or "") == "known" and old.get("value") not in (None, "", [])
            if not (record.get("state") == "known" and record.get("value") not in (None, "", [])) and old_known:
                record = dict(old)
            fields[field] = record
        profile = {"schema_version": "phase_f_v2", "fields": fields}
        logo_object_key = ""
        logo_hash = ""
        logo_verified_at = ""
        if logo_bytes is not None:
            validated_logo = validate_logo(bytes(logo_bytes), logo_content_type)
            logo_hash = validated_logo.content_hash
            logo_verified_at = payload_verified
            logo_verified_at = logo_verified_at or utc_now_iso()
            logo_object_key, _ = cache_logo(self.object_storage, str(company_id), validated_logo)
            fields["logo"] = {
                "value": logo_source_url or logo_object_key,
                "state": "known",
                "status": "known",
                "provenance": {"source": _text(payload.get("source")) or "official_employer_source", "url": logo_source_url},
                "observed_at": payload_observed or logo_verified_at,
                "verified_at": logo_verified_at,
            }
            profile["fields"] = fields
        elif isinstance(existing.get("logo_content_hash"), str):
            logo_object_key = _text(existing.get("logo_object_key"))
            logo_hash = _text(existing.get("logo_content_hash"))
            logo_verified_at = _text(existing.get("logo_verified_at"))
        return self.store.upsert_company_profile(
            str(company_id),
            profile,
            logo_object_key=logo_object_key,
            logo_source_url=logo_source_url,
            logo_content_hash=logo_hash,
            logo_content_type=logo_content_type if logo_object_key else "",
            logo_verified_at=logo_verified_at,
        )

    def company_detail(self, user_id: str, company_id: str, *, plan_id: str = DEFAULT_PLAN_ID) -> dict[str, Any] | None:
        self._assert_catalog_access(user_id)
        if self.store is None:
            return None
        result = self.store.get_published_company_page(company_id, user_id, limit=25)
        company = result.get("company")
        rows = list(result.get("rows") or [])[:25]
        if company is None:
            return None
        jobs: list[dict[str, Any]] = []
        for row in rows:
            description_intelligence = _pending_description()
            match_intelligence = _pending_match()
            jobs.append(_job_projection(
                row,
                {"state": _text(row.get("user_state")) or "none"},
                {"state": "available", "status": "pending", "evaluator_version": EVALUATOR_VERSION, "match_intelligence": match_intelligence},
                description_intelligence,
                match_intelligence,
                self._company_profile(row),
                {"state": "unknown", "visibility": "pro"},
                {"state": "pending", "score": None},
            ))
        profile_row = dict(rows[0]) if rows else dict(company)
        if company.get("company_profile_json") not in (None, ""):
            profile_row["company_profile_json"] = company.get("company_profile_json")
        profile_row["company_logo_object_key"] = company.get("logo_object_key") or profile_row.get("company_logo_object_key")
        profile_row["company_logo_source_url"] = company.get("logo_source_url") or profile_row.get("company_logo_source_url")
        profile = self._company_profile(profile_row)
        fields = profile.get("fields") if isinstance(profile.get("fields"), Mapping) else {}
        characteristics = {
            "industry": _company_profile_value(fields, "industry"),
            "size": _company_profile_value(fields, "company_size"),
            "stage": _company_profile_value(fields, "company_stage"),
            "funding_stage": _company_profile_value(fields, "funding_stage"),
            "founded_year": _company_profile_value(fields, "founded_year"),
            "headquarters": _company_profile_value(fields, "headquarters"),
        }
        for row in rows:
            payload = _payload_for_row(row)
            if characteristics["stage"] is None:
                characteristics["stage"] = _alias(payload, "company_stage")
            if characteristics["industry"] is None:
                characteristics["industry"] = _alias(payload, "industry", "company_industry")
        return _public_clean({
            "company_id": str(company.get("company_id") or company_id),
            "name": _text(company.get("canonical_name")) or None,
            "entity_kind": _text(company.get("entity_kind")) or "unknown",
            "profile": profile,
            "characteristics": characteristics,
            "jobs": jobs,
            "job_count": int(result.get("total") or 0),
            "jobs_returned": len(jobs),
            "jobs_truncated": int(result.get("total") or 0) > len(jobs),
        })

    def set_state(self, user_id: str, posting_id: str, state: str, *, reason_code: str = "") -> dict[str, Any]:
        if self.store is None or self.store.get_published_job_row(posting_id) is None:
            raise KeyError("job_not_found")
        state = _norm(state).replace(" ", "_")
        if state not in {"saved", "hidden", "none", "applied"}:
            raise ValueError("invalid_job_state")
        current = self.store.list_dispositions_for_jobs(user_id, [posting_id]).get(posting_id)
        disposition = self.store.set_disposition(user_id, posting_id, state=state, reason_code=reason_code)
        event_name = {"saved": "job_saved", "hidden": "job_hidden", "none": "job_restored", "applied": "job_applied"}[state]
        self.store.record_event(user_id, event_name=event_name, canonical_job_id=posting_id, reason_code=reason_code, payload={"previous_state": _text((current or {}).get("state")) or "none"})
        return disposition

    def report(self, user_id: str, posting_id: str, *, reason_code: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if self.store is None or self.store.get_published_job_row(posting_id) is None:
            raise KeyError("job_not_found")
        return self.store.record_event(user_id, event_name="incorrect_filter_reported", canonical_job_id=posting_id, reason_code=_text(reason_code) or "unspecified", payload=payload)

    def report_filter(self, user_id: str, *, reason_code: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if self.store is None:
            return {"user_id": user_id, "event_name": "incorrect_filter_reported", "reason_code": _text(reason_code) or "unspecified", "payload": dict(payload or {})}
        return self.store.record_event(user_id, event_name="incorrect_filter_reported", reason_code=_text(reason_code) or "unspecified", payload=payload)

    def hidden(self, user_id: str, *, limit: int = 25, cursor: str = "") -> dict[str, Any]:
        self._assert_catalog_access(user_id)
        if self.store is None:
            return self._empty_feed({}, state="unavailable")
        limit = max(1, min(100, int(limit)))
        fingerprint = _filter_fingerprint({}, user_id=user_id, hidden_only=True)
        cursor_payload = _cursor_decode(cursor) if cursor else None
        if cursor_payload is not None and cursor_payload.get("fingerprint") != fingerprint:
            raise ValueError("cursor_filter_mismatch")
        result = self.store.list_hidden_published_jobs(user_id, limit=limit, cursor=cursor_payload)
        rows = list(result.get("rows") or [])
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = _cursor_encode({"fingerprint": fingerprint, "sort": _text(last.get("last_verified_at") or last.get("first_seen_at")), "canonical_job_id": _text(last.get("canonical_job_id"))})
        job_ids = [str(row.get("canonical_job_id") or "") for row in page]
        descriptions = self.store.list_intelligence_cache_entries(job_ids, intelligence_kind="description")
        matches = self.store.list_intelligence_cache_entries(job_ids, user_id=user_id, intelligence_kind="match")
        preferences = self.get_preferences(user_id)
        jobs = []
        for row in page:
            description = self._description_intelligence(row, cache_entries=descriptions)
            match = self._match_intelligence(user_id, row, description, preferences, state="available", cache_entries=matches)
            applicant_intelligence = build_applicant_competition(row, include_pro=False)
            jobs.append(_job_projection(row, {"state": "hidden"}, {"state": "available", "status": "pending", "evaluator_version": EVALUATOR_VERSION, "match_intelligence": match}, description, match, self._company_profile(row), applicant_intelligence, {"state": "pending", "score": None}))
        return {"jobs": jobs, "total": int(result.get("total") or 0), "next_cursor": next_cursor, "evaluation": {"state": "available", "supported_states": sorted(EVALUATION_STATES)}}

    @staticmethod
    def _publication_state(publication: Mapping[str, Any]) -> str:
        valid_until = _epoch(publication.get("valid_until"))
        if valid_until is not None and valid_until < datetime.now(timezone.utc).timestamp():
            return "stale"
        return "available"

    @staticmethod
    def _after_cursor(row: Mapping[str, Any], cursor: Mapping[str, Any]) -> bool:
        if _text(cursor.get("sort_mode")) in {"priority", "best"}:
            try:
                row_score = float(row.get("_phase_g_priority_score") or 0)
                cursor_score = float(cursor.get("priority") or 0)
            except (TypeError, ValueError):
                row_score = cursor_score = 0.0
            job_id = _text(row.get("canonical_job_id"))
            cursor_id = _text(cursor.get("canonical_job_id"))
            return row_score < cursor_score or (row_score == cursor_score and job_id < cursor_id)
        sort = _text(row.get("last_verified_at") or row.get("first_seen_at"))
        cursor_sort = _text(cursor.get("sort"))
        job_id = _text(row.get("canonical_job_id"))
        cursor_id = _text(cursor.get("canonical_job_id"))
        return sort < cursor_sort or (sort == cursor_sort and job_id < cursor_id)

    @staticmethod
    def _empty_feed(filters: Mapping[str, Any], *, state: str) -> dict[str, Any]:
        return {
            "jobs": [],
            "total": 0,
            "next_cursor": None,
            "filters": dict(filters),
            "evaluation": {"state": state, "supported_states": sorted(EVALUATION_STATES), "catalog_state": state},
            "publication": None,
            "filter_capabilities": {},
        }


__all__ = ["EVALUATION_STATES", "EVALUATOR_VERSION", "PersonalizedJobsService", "normalize_filters", "normalize_preferences"]
