"""Stable domain contracts for Runr's personalized Jobs experience.

This module defines shapes only.  It deliberately does not persist preferences,
project jobs across runs, evaluate eligibility, calculate semantic matches, or
enforce feature access.  The adapters at the bottom of the module allow the
existing run-local models to be consumed by later work without making their
``job_id`` values global posting identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import re
from typing import Any, Mapping, Sequence
from uuid import uuid4

from backend.domain.job_identity import canonicalize_url, compact_whitespace


class ContractValidationError(ValueError):
    """Raised when a personalized Jobs contract contains an invalid value."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _optional_text(value: Any) -> str | None:
    value = _text(value)
    return value or None


def _string_list(value: Any, *, lower: bool = False) -> list[str]:
    if value is None or value == "":
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        if isinstance(item, str) and ("\n" in item or "," in item):
            items = re.split(r"[\n,]", item)
        else:
            items = [item]
        for raw_item in items:
            item_text = _text(raw_item)
            if lower:
                item_text = item_text.casefold()
            if not item_text or item_text.casefold() in seen:
                continue
            result.append(item_text)
            seen.add(item_text.casefold())
    return result


def _enum_value(value: Any, enum_type: type[StrEnum], *, field_name: str, default: StrEnum | None = None) -> str:
    if value is None or value == "":
        if default is not None:
            return default.value
        raise ContractValidationError(f"{field_name} is required")
    normalized = _text(value).casefold().replace("-", "_").replace(" ", "_")
    for item in enum_type:
        if normalized == item.value.casefold():
            return item.value
    allowed = ", ".join(item.value for item in enum_type)
    raise ContractValidationError(f"{field_name} must be one of: {allowed}")


def _enum_list(value: Any, enum_type: type[StrEnum], *, field_name: str) -> list[str]:
    raw_values = value if isinstance(value, (list, tuple, set)) else ([] if value in (None, "") else [value])
    result: list[str] = []
    for item in raw_values:
        normalized = _enum_value(item, enum_type, field_name=field_name)
        if normalized not in result:
            result.append(normalized)
    return result


def _require_id(value: Any, field_name: str) -> str:
    normalized = _text(value)
    if not normalized:
        raise ContractValidationError(f"{field_name} is required")
    return normalized


def _confidence(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractValidationError("confidence must be a number between 0 and 1") from exc
    if not 0 <= normalized <= 1:
        raise ContractValidationError("confidence must be between 0 and 1")
    return normalized


def _bool_value(value: Any, *, field_name: str, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = _text(value).casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ContractValidationError(f"{field_name} must be a boolean")


def _version(value: Any) -> int | str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ContractValidationError("version cannot be boolean")
    try:
        return int(value)
    except (TypeError, ValueError):
        return _text(value)


class WorkArrangement(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    ANY = "any"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    INTERNSHIP = "internship"
    SELF_EMPLOYED = "self_employed"


class SponsorshipRequirement(StrEnum):
    REQUIRED = "required"
    NOT_REQUIRED = "not_required"
    UNKNOWN = "unknown"


class RelocationPreference(StrEnum):
    WILLING = "willing"
    NOT_WILLING = "not_willing"
    CONDITIONAL = "conditional"
    UNKNOWN = "unknown"


class AuthorizationStatus(StrEnum):
    AUTHORIZED = "authorized"
    NOT_AUTHORIZED = "not_authorized"
    UNKNOWN = "unknown"


class JobPostingState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    LIKELY_ELIGIBLE = "likely_eligible"
    INELIGIBLE = "ineligible"
    UNCERTAIN = "uncertain"
    NOT_EVALUATED = "not_evaluated"


class EligibilityCategory(StrEnum):
    LANGUAGE = "language"
    AUTHORIZATION = "authorization"
    SPONSORSHIP = "sponsorship"
    LOCATION = "location"
    WORK_ARRANGEMENT = "work_arrangement"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    EMPLOYMENT_TYPE = "employment_type"
    SALARY = "salary"
    RELEVANCE = "relevance"
    INSUFFICIENT_INFORMATION = "insufficient_information"


class RequirementMatchStatus(StrEnum):
    MATCHING = "matching"
    MISSING = "missing"
    UNCERTAIN = "uncertain"


class RequirementRequiredness(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    UNSPECIFIED = "unspecified"


class JobDispositionState(StrEnum):
    NONE = "none"
    SAVED = "saved"
    HIDDEN = "hidden"
    INTERESTED = "interested"
    PREPARING = "preparing"
    APPLIED = "applied"
    DISMISSED = "dismissed"
    ARCHIVED = "archived"


class PersonalizedFeatureKey(StrEnum):
    """Canonical backend feature identifiers; these are not plan allocations."""

    AI_ELIGIBILITY_FILTERING = "ai_eligibility_filtering"
    SEMANTIC_JOB_MATCHING = "semantic_job_matching"
    FULL_MATCH_EXPLANATIONS = "full_match_explanations"
    TAILORED_CV = "tailored_cv"
    TAILORED_MOTIVATION_LETTER = "tailored_motivation_letter"
    SCHEDULED_JOB_SEARCHES = "scheduled_job_searches"
    MULTIPLE_JOB_SEARCHES = "multiple_job_searches"
    ASSISTED_APPLY = "assisted_apply"
    PRIORITY_RANKING = "priority_ranking"
    ADVANCED_APPLICATION_INSIGHTS = "advanced_application_insights"


CANONICAL_PLAN_IDS = ("none", "launch", "momentum", "scale")

FRONTEND_PERSONALIZED_FEATURE_KEY_MAP = {
    "ai_eligibility_filter": PersonalizedFeatureKey.AI_ELIGIBILITY_FILTERING.value,
    "semantic_matching": PersonalizedFeatureKey.SEMANTIC_JOB_MATCHING.value,
    "full_match_explanation": PersonalizedFeatureKey.FULL_MATCH_EXPLANATIONS.value,
    "multiple_active_searches": PersonalizedFeatureKey.MULTIPLE_JOB_SEARCHES.value,
}

for _feature_key in PersonalizedFeatureKey:
    FRONTEND_PERSONALIZED_FEATURE_KEY_MAP.setdefault(_feature_key.value, _feature_key.value)


SCHEMA_VERSIONS = {
    "candidate_search_preferences": "candidate_search_preferences_v1",
    "job_posting": "job_posting_v1",
    "job_source_observation": "job_source_observation_v1",
    "eligibility_reason": "eligibility_reason_v1",
    "eligibility_evaluation": "eligibility_evaluation_v1",
    "match_evidence_reference": "match_evidence_reference_v1",
    "match_requirement": "match_requirement_v1",
    "match_evaluation": "match_evaluation_v1",
    "job_disposition": "job_disposition_v1",
}


@dataclass(slots=True)
class CandidateLanguagePreference:
    language: str
    proficiency: str | None = None

    def __post_init__(self) -> None:
        self.language = _require_id(self.language, "language")
        self.proficiency = _optional_text(self.proficiency)

    def to_dict(self) -> dict[str, Any]:
        return {"language": self.language, "proficiency": self.proficiency}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | str) -> "CandidateLanguagePreference":
        if isinstance(payload, str):
            language, separator, proficiency = payload.partition("-")
            return cls(language=language, proficiency=proficiency if separator else None)
        return cls(language=payload.get("language") or payload.get("name") or "", proficiency=payload.get("proficiency"))


@dataclass(slots=True)
class WorkAuthorizationPreference:
    country_code: str | None = None
    region: str | None = None
    status: str = AuthorizationStatus.UNKNOWN.value
    reference_id: str | None = None

    def __post_init__(self) -> None:
        self.country_code = _optional_text(self.country_code)
        self.region = _optional_text(self.region)
        if not self.country_code and not self.region:
            raise ContractValidationError("work authorization needs a country_code or region")
        if self.country_code:
            self.country_code = self.country_code.upper()
        self.status = _enum_value(self.status, AuthorizationStatus, field_name="status", default=AuthorizationStatus.UNKNOWN)
        self.reference_id = _optional_text(self.reference_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "country_code": self.country_code,
            "region": self.region,
            "status": self.status,
            "reference_id": self.reference_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkAuthorizationPreference":
        return cls(
            country_code=payload.get("country_code"),
            region=payload.get("region"),
            status=payload.get("status") or payload.get("authorization_status") or AuthorizationStatus.UNKNOWN.value,
            reference_id=payload.get("reference_id"),
        )


@dataclass(slots=True)
class CandidateSearchPreferences:
    """User/profile-owned job-search choices, not a copy of candidate facts."""

    profile_id: str
    user_id: str | None = None
    target_roles: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    preferred_locations: list[str] = field(default_factory=list)
    country_codes: list[str] = field(default_factory=list)
    work_arrangements: list[str] = field(default_factory=list)
    seniority_levels: list[str] = field(default_factory=list)
    employment_types: list[str] = field(default_factory=list)
    languages: list[CandidateLanguagePreference] = field(default_factory=list)
    work_authorization: list[WorkAuthorizationPreference] = field(default_factory=list)
    sponsorship_requirement: str = SponsorshipRequirement.UNKNOWN.value
    relocation_preference: str = RelocationPreference.UNKNOWN.value
    minimum_salary: float | None = None
    salary_currency: str | None = None
    earliest_start_date: str | None = None
    notice_period_days: int | None = None
    maximum_commute_minutes: int | None = None
    willingness_to_travel: bool | None = None
    associated_asset_id: str | None = None
    active: bool = True
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    schema_version: str = SCHEMA_VERSIONS["candidate_search_preferences"]

    def __post_init__(self) -> None:
        self.profile_id = _require_id(self.profile_id, "profile_id")
        self.user_id = _optional_text(self.user_id)
        self.target_roles = _string_list(self.target_roles)
        self.keywords = _string_list(self.keywords, lower=True)
        self.preferred_locations = _string_list(self.preferred_locations)
        self.country_codes = [item.upper() for item in _string_list(self.country_codes)]
        self.work_arrangements = _enum_list(self.work_arrangements, WorkArrangement, field_name="work_arrangements")
        self.seniority_levels = _string_list(self.seniority_levels)
        self.employment_types = _enum_list(self.employment_types, EmploymentType, field_name="employment_types")
        self.languages = [
            item if isinstance(item, CandidateLanguagePreference) else CandidateLanguagePreference.from_dict(item)
            for item in (self.languages or [])
        ]
        self.work_authorization = [
            item if isinstance(item, WorkAuthorizationPreference) else WorkAuthorizationPreference.from_dict(item)
            for item in (self.work_authorization or [])
        ]
        self.sponsorship_requirement = _enum_value(
            self.sponsorship_requirement,
            SponsorshipRequirement,
            field_name="sponsorship_requirement",
            default=SponsorshipRequirement.UNKNOWN,
        )
        self.relocation_preference = _enum_value(
            self.relocation_preference,
            RelocationPreference,
            field_name="relocation_preference",
            default=RelocationPreference.UNKNOWN,
        )
        if self.minimum_salary is not None:
            try:
                self.minimum_salary = float(self.minimum_salary)
            except (TypeError, ValueError) as exc:
                raise ContractValidationError("minimum_salary must be a non-negative number") from exc
            if self.minimum_salary < 0:
                raise ContractValidationError("minimum_salary must be non-negative")
        self.salary_currency = _optional_text(self.salary_currency)
        if self.salary_currency:
            self.salary_currency = self.salary_currency.upper()
        self.earliest_start_date = _optional_text(self.earliest_start_date)
        for field_name in ("notice_period_days", "maximum_commute_minutes"):
            value = getattr(self, field_name)
            if value is not None:
                try:
                    value = int(value)
                except (TypeError, ValueError) as exc:
                    raise ContractValidationError(f"{field_name} must be a non-negative integer") from exc
                if value < 0:
                    raise ContractValidationError(f"{field_name} must be non-negative")
                setattr(self, field_name, value)
        if self.willingness_to_travel is not None:
            self.willingness_to_travel = _bool_value(
                self.willingness_to_travel,
                field_name="willingness_to_travel",
                default=False,
            )
        self.active = _bool_value(self.active, field_name="active", default=True)
        self.associated_asset_id = _optional_text(self.associated_asset_id)
        self.schema_version = _text(self.schema_version) or SCHEMA_VERSIONS["candidate_search_preferences"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "user_id": self.user_id,
            "target_roles": list(self.target_roles),
            "keywords": list(self.keywords),
            "preferred_locations": list(self.preferred_locations),
            "country_codes": list(self.country_codes),
            "work_arrangements": list(self.work_arrangements),
            "seniority_levels": list(self.seniority_levels),
            "employment_types": list(self.employment_types),
            "languages": [item.to_dict() for item in self.languages],
            "work_authorization": [item.to_dict() for item in self.work_authorization],
            "sponsorship_requirement": self.sponsorship_requirement,
            "relocation_preference": self.relocation_preference,
            "minimum_salary": self.minimum_salary,
            "salary_currency": self.salary_currency,
            "earliest_start_date": self.earliest_start_date,
            "notice_period_days": self.notice_period_days,
            "maximum_commute_minutes": self.maximum_commute_minutes,
            "willingness_to_travel": self.willingness_to_travel,
            "associated_asset_id": self.associated_asset_id,
            "active": self.active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "schema_version": self.schema_version,
        }

    def to_authenticated_dict(self) -> dict[str, Any]:
        """Explicit name for the candidate-private serialization."""

        return self.to_dict()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CandidateSearchPreferences":
        return cls(
            profile_id=payload.get("profile_id") or "",
            user_id=payload.get("user_id"),
            target_roles=payload.get("target_roles") or [],
            keywords=payload.get("keywords") or [],
            preferred_locations=payload.get("preferred_locations") or [],
            country_codes=payload.get("country_codes") or [],
            work_arrangements=payload.get("work_arrangements") or [],
            seniority_levels=payload.get("seniority_levels") or [],
            employment_types=payload.get("employment_types") or [],
            languages=payload.get("languages") or [],
            work_authorization=payload.get("work_authorization") or [],
            sponsorship_requirement=payload.get("sponsorship_requirement") or SponsorshipRequirement.UNKNOWN.value,
            relocation_preference=payload.get("relocation_preference") or RelocationPreference.UNKNOWN.value,
            minimum_salary=payload.get("minimum_salary"),
            salary_currency=payload.get("salary_currency"),
            earliest_start_date=payload.get("earliest_start_date"),
            notice_period_days=payload.get("notice_period_days"),
            maximum_commute_minutes=payload.get("maximum_commute_minutes"),
            willingness_to_travel=payload.get("willingness_to_travel"),
            associated_asset_id=payload.get("associated_asset_id") or payload.get("cv_asset_id"),
            active=payload.get("active", True),
            created_at=_text(payload.get("created_at")) or _utc_now_iso(),
            updated_at=_text(payload.get("updated_at")) or _utc_now_iso(),
            schema_version=_text(payload.get("schema_version")) or SCHEMA_VERSIONS["candidate_search_preferences"],
        )

    @classmethod
    def from_workspace_settings(
        cls,
        *,
        profile_id: str,
        user_id: str | None = None,
        settings: Mapping[str, Any],
    ) -> "CandidateSearchPreferences":
        """Adapt existing targeting settings without copying workspace runtime configuration."""

        raw = dict(settings)
        if isinstance(raw.get("settings"), Mapping):
            raw = {**raw, **dict(raw["settings"])}
        targeting = dict(raw.get("targeting") or {})
        locations = dict(raw.get("location_preferences") or {})
        filters = dict(raw.get("filter_preferences") or {})
        language_preferences = dict(filters.get("language_preferences") or {})
        document_preferences = dict(raw.get("document_preferences") or {})
        work_arrangement = raw.get("work_arrangements") or raw.get("work_arrangement") or targeting.get("work_arrangement")
        seniority = raw.get("seniority_levels") or raw.get("experience_levels") or {}
        if isinstance(seniority, Mapping):
            seniority = list(seniority.values())
        return cls(
            profile_id=profile_id,
            user_id=user_id,
            target_roles=raw.get("target_roles") or [],
            keywords=raw.get("keywords") or targeting.get("keywords") or [],
            preferred_locations=raw.get("preferred_locations") or raw.get("cities") or [],
            country_codes=raw.get("country_codes") or locations.get("country_codes") or [],
            work_arrangements=work_arrangement if isinstance(work_arrangement, (list, tuple, set)) else ([work_arrangement] if work_arrangement else []),
            seniority_levels=seniority,
            employment_types=raw.get("employment_types") or [],
            languages=raw.get("languages") or language_preferences.get("profile_languages") or [],
            associated_asset_id=(
                raw.get("associated_asset_id")
                or raw.get("workspace_cv_asset_id")
                or document_preferences.get("workspace_cv_asset_id")
                or (dict(raw.get("cv_binding") or {}).get("asset_id"))
            ),
        )

    def to_analytics_dict(self) -> dict[str, Any]:
        """Return metadata safe for analytics; sensitive preference values are omitted."""

        return {
            "contract": "candidate_search_preferences",
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "active": self.active,
            "target_role_count": len(self.target_roles),
            "keyword_count": len(self.keywords),
            "location_count": len(self.preferred_locations),
            "country_count": len(self.country_codes),
            "work_arrangement_count": len(self.work_arrangements),
            "seniority_count": len(self.seniority_levels),
            "employment_type_count": len(self.employment_types),
            "language_count": len(self.languages),
            "has_associated_asset": self.associated_asset_id is not None,
        }


@dataclass(slots=True)
class ContractReference:
    reference_type: str
    reference_id: str
    profile_id: str | None = None
    version: int | str | None = None

    def __post_init__(self) -> None:
        self.reference_type = _require_id(self.reference_type, "reference_type")
        self.reference_id = _require_id(self.reference_id, "reference_id")
        self.profile_id = _optional_text(self.profile_id)
        self.version = _version(self.version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_type": self.reference_type,
            "reference_id": self.reference_id,
            "profile_id": self.profile_id,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContractReference":
        return cls(
            reference_type=payload.get("reference_type") or payload.get("type") or "",
            reference_id=payload.get("reference_id") or payload.get("id") or "",
            profile_id=payload.get("profile_id"),
            version=payload.get("version"),
        )


@dataclass(slots=True)
class JobSourceObservation:
    source_type: str
    source_identifier: str | None = None
    original_url: str | None = None
    observed_title: str | None = None
    observed_company: str | None = None
    observed_location: str | None = None
    observation_time: str = field(default_factory=_utc_now_iso)
    run_id: str | None = None
    workspace_id: str | None = None
    raw_job_id: str | None = None
    source_metadata: dict[str, Any] = field(default_factory=dict)
    observation_id: str = field(default_factory=lambda: f"obs_{uuid4().hex[:16]}")
    schema_version: str = SCHEMA_VERSIONS["job_source_observation"]

    def __post_init__(self) -> None:
        self.source_type = _require_id(self.source_type, "source_type")
        self.source_identifier = _optional_text(self.source_identifier)
        self.original_url = _optional_text(self.original_url)
        self.observed_title = _optional_text(self.observed_title)
        self.observed_company = _optional_text(self.observed_company)
        self.observed_location = _optional_text(self.observed_location)
        self.observation_time = _text(self.observation_time) or _utc_now_iso()
        self.run_id = _optional_text(self.run_id)
        self.workspace_id = _optional_text(self.workspace_id)
        self.raw_job_id = _optional_text(self.raw_job_id)
        self.source_metadata = dict(self.source_metadata or {})
        self.observation_id = _require_id(self.observation_id, "observation_id")
        self.schema_version = _text(self.schema_version) or SCHEMA_VERSIONS["job_source_observation"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_identifier": self.source_identifier,
            "original_url": self.original_url,
            "observed_title": self.observed_title,
            "observed_company": self.observed_company,
            "observed_location": self.observed_location,
            "observation_time": self.observation_time,
            "run_id": self.run_id,
            "workspace_id": self.workspace_id,
            "raw_job_id": self.raw_job_id,
            "source_metadata": dict(self.source_metadata),
            "observation_id": self.observation_id,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "JobSourceObservation":
        return cls(
            source_type=payload.get("source_type") or "",
            source_identifier=payload.get("source_identifier") or payload.get("source_id"),
            original_url=payload.get("original_url") or payload.get("url"),
            observed_title=payload.get("observed_title") or payload.get("title"),
            observed_company=payload.get("observed_company") or payload.get("company"),
            observed_location=payload.get("observed_location") or payload.get("location"),
            observation_time=payload.get("observation_time") or payload.get("observed_at") or _utc_now_iso(),
            run_id=payload.get("run_id"),
            workspace_id=payload.get("workspace_id"),
            raw_job_id=payload.get("raw_job_id") or payload.get("job_id"),
            source_metadata=payload.get("source_metadata") or payload.get("metadata") or {},
            observation_id=payload.get("observation_id") or f"obs_{uuid4().hex[:16]}",
            schema_version=payload.get("schema_version") or SCHEMA_VERSIONS["job_source_observation"],
        )

    def to_analytics_dict(self) -> dict[str, Any]:
        return {
            "contract": "job_source_observation",
            "schema_version": self.schema_version,
            "source_type": self.source_type,
            "has_source_identifier": self.source_identifier is not None,
            "has_original_url": self.original_url is not None,
            "has_run_id": self.run_id is not None,
            "has_workspace_id": self.workspace_id is not None,
            "observation_time": self.observation_time,
        }


@dataclass(slots=True)
class SalaryRange:
    minimum: float | None = None
    maximum: float | None = None
    currency: str | None = None
    period: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("minimum", "maximum"):
            value = getattr(self, field_name)
            if value is not None:
                try:
                    value = float(value)
                except (TypeError, ValueError) as exc:
                    raise ContractValidationError("salary amounts must be numbers") from exc
                if value < 0:
                    raise ContractValidationError("salary amounts must be non-negative")
                setattr(self, field_name, value)
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ContractValidationError("salary minimum cannot exceed maximum")
        self.currency = _optional_text(self.currency)
        if self.currency:
            self.currency = self.currency.upper()
        self.period = _optional_text(self.period)

    def to_dict(self) -> dict[str, Any]:
        return {"minimum": self.minimum, "maximum": self.maximum, "currency": self.currency, "period": self.period}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SalaryRange":
        return cls(
            minimum=payload.get("minimum") if "minimum" in payload else payload.get("min"),
            maximum=payload.get("maximum") if "maximum" in payload else payload.get("max"),
            currency=payload.get("currency"),
            period=payload.get("period"),
        )


@dataclass(slots=True)
class JobPostingProvenance:
    source_observation_id: str
    source_type: str
    source_identifier: str | None = None
    run_id: str | None = None
    workspace_id: str | None = None

    def __post_init__(self) -> None:
        self.source_observation_id = _require_id(self.source_observation_id, "source_observation_id")
        self.source_type = _require_id(self.source_type, "source_type")
        self.source_identifier = _optional_text(self.source_identifier)
        self.run_id = _optional_text(self.run_id)
        self.workspace_id = _optional_text(self.workspace_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_observation_id": self.source_observation_id,
            "source_type": self.source_type,
            "source_identifier": self.source_identifier,
            "run_id": self.run_id,
            "workspace_id": self.workspace_id,
        }

    @classmethod
    def from_observation(cls, observation: JobSourceObservation) -> "JobPostingProvenance":
        return cls(
            source_observation_id=observation.observation_id,
            source_type=observation.source_type,
            source_identifier=observation.source_identifier,
            run_id=observation.run_id,
            workspace_id=observation.workspace_id,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "JobPostingProvenance":
        return cls(
            source_observation_id=payload.get("source_observation_id") or payload.get("observation_id") or "",
            source_type=payload.get("source_type") or "",
            source_identifier=payload.get("source_identifier"),
            run_id=payload.get("run_id"),
            workspace_id=payload.get("workspace_id"),
        )


@dataclass(slots=True)
class JobPosting:
    """Canonical public/shared posting projection with source traceability."""

    posting_id: str
    normalized_title: str = ""
    normalized_company: str = ""
    normalized_location: str = ""
    work_arrangement: str | None = None
    description: str = ""
    canonical_apply_url: str | None = None
    canonical_source_url: str | None = None
    posted_at: str | None = None
    first_seen: str = field(default_factory=_utc_now_iso)
    last_seen: str = field(default_factory=_utc_now_iso)
    state: str = JobPostingState.UNKNOWN.value
    salary: SalaryRange | None = None
    source_observations: list[JobSourceObservation] = field(default_factory=list)
    provenance: list[JobPostingProvenance] = field(default_factory=list)
    version: int = 1
    schema_version: str = SCHEMA_VERSIONS["job_posting"]

    def __post_init__(self) -> None:
        self.posting_id = _require_id(self.posting_id, "posting_id")
        self.normalized_title = compact_whitespace(_text(self.normalized_title))
        self.normalized_company = compact_whitespace(_text(self.normalized_company))
        self.normalized_location = compact_whitespace(_text(self.normalized_location))
        self.work_arrangement = None if self.work_arrangement in (None, "") else _enum_value(
            self.work_arrangement, WorkArrangement, field_name="work_arrangement"
        )
        self.description = _text(self.description)
        self.canonical_apply_url = self._normalize_url(self.canonical_apply_url, "canonical_apply_url")
        self.canonical_source_url = self._normalize_url(self.canonical_source_url, "canonical_source_url")
        self.posted_at = _optional_text(self.posted_at)
        self.first_seen = _text(self.first_seen) or _utc_now_iso()
        self.last_seen = _text(self.last_seen) or self.first_seen
        self.state = _enum_value(self.state, JobPostingState, field_name="state", default=JobPostingState.UNKNOWN)
        if self.salary is not None and not isinstance(self.salary, SalaryRange):
            self.salary = SalaryRange.from_dict(self.salary)
        self.source_observations = [
            item if isinstance(item, JobSourceObservation) else JobSourceObservation.from_dict(item)
            for item in (self.source_observations or [])
        ]
        self.provenance = [
            item if isinstance(item, JobPostingProvenance) else JobPostingProvenance.from_dict(item)
            for item in (self.provenance or [])
        ]
        if not self.provenance:
            self.provenance = [JobPostingProvenance.from_observation(item) for item in self.source_observations]
        try:
            self.version = int(self.version)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("version must be a positive integer") from exc
        if self.version < 1:
            raise ContractValidationError("version must be at least 1")
        self.schema_version = _text(self.schema_version) or SCHEMA_VERSIONS["job_posting"]

    @staticmethod
    def _normalize_url(value: Any, field_name: str) -> str | None:
        raw = _optional_text(value)
        if raw is None:
            return None
        normalized = canonicalize_url(raw)
        if not normalized:
            raise ContractValidationError(f"{field_name} must be an absolute HTTP(S) URL")
        return normalized

    def to_dict(self) -> dict[str, Any]:
        return {
            "posting_id": self.posting_id,
            "normalized_title": self.normalized_title,
            "normalized_company": self.normalized_company,
            "normalized_location": self.normalized_location,
            "work_arrangement": self.work_arrangement,
            "description": self.description,
            "canonical_apply_url": self.canonical_apply_url,
            "canonical_source_url": self.canonical_source_url,
            "posted_at": self.posted_at,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "state": self.state,
            "salary": self.salary.to_dict() if self.salary else None,
            "source_observations": [item.to_dict() for item in self.source_observations],
            "provenance": [item.to_dict() for item in self.provenance],
            "version": self.version,
            "schema_version": self.schema_version,
        }

    def to_public_dict(self) -> dict[str, Any]:
        """Project only shared posting data; run/workspace provenance stays private."""

        return {
            "posting_id": self.posting_id,
            "normalized_title": self.normalized_title,
            "normalized_company": self.normalized_company,
            "normalized_location": self.normalized_location,
            "work_arrangement": self.work_arrangement,
            "description": self.description,
            "canonical_apply_url": self.canonical_apply_url,
            "canonical_source_url": self.canonical_source_url,
            "posted_at": self.posted_at,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "state": self.state,
            "salary": self.salary.to_dict() if self.salary else None,
            "version": self.version,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "JobPosting":
        return cls(
            posting_id=payload.get("posting_id") or "",
            normalized_title=payload.get("normalized_title") or payload.get("title") or "",
            normalized_company=payload.get("normalized_company") or payload.get("company") or "",
            normalized_location=payload.get("normalized_location") or payload.get("location") or "",
            work_arrangement=payload.get("work_arrangement"),
            description=payload.get("description") or "",
            canonical_apply_url=payload.get("canonical_apply_url"),
            canonical_source_url=payload.get("canonical_source_url"),
            posted_at=payload.get("posted_at"),
            first_seen=payload.get("first_seen") or _utc_now_iso(),
            last_seen=payload.get("last_seen") or _utc_now_iso(),
            state=payload.get("state") or JobPostingState.UNKNOWN.value,
            salary=SalaryRange.from_dict(payload["salary"]) if isinstance(payload.get("salary"), Mapping) else None,
            source_observations=payload.get("source_observations") or [],
            provenance=payload.get("provenance") or [],
            version=int(payload.get("version") or 1),
            schema_version=payload.get("schema_version") or SCHEMA_VERSIONS["job_posting"],
        )

    @classmethod
    def from_job_record(
        cls,
        record: Mapping[str, Any] | Any,
        *,
        run_id: str | None = None,
        workspace_id: str | None = None,
        posting_id: str | None = None,
        observed_at: str | None = None,
    ) -> "JobPosting":
        payload = record.to_dict() if hasattr(record, "to_dict") else dict(record)
        return cls._from_legacy_record(
            payload,
            run_id=run_id,
            workspace_id=workspace_id,
            posting_id=posting_id,
            observed_at=observed_at,
        )

    @classmethod
    def from_pipeline_job(
        cls,
        record: Mapping[str, Any] | Any,
        *,
        run_id: str | None = None,
        workspace_id: str | None = None,
        posting_id: str | None = None,
        observed_at: str | None = None,
    ) -> "JobPosting":
        payload = record.to_record() if hasattr(record, "to_record") else dict(record)
        return cls._from_legacy_record(
            payload,
            run_id=run_id,
            workspace_id=workspace_id,
            posting_id=posting_id,
            observed_at=observed_at,
        )

    @classmethod
    def _from_legacy_record(
        cls,
        payload: Mapping[str, Any],
        *,
        run_id: str | None,
        workspace_id: str | None,
        posting_id: str | None,
        observed_at: str | None,
    ) -> "JobPosting":
        apply_url = canonicalize_url(_text(payload.get("apply_link"))) or None
        source_url = canonicalize_url(_text(payload.get("source_url") or payload.get("link"))) or None
        identity_url = apply_url or source_url
        legacy_job_id = _optional_text(payload.get("job_id"))
        resolved_posting_id = posting_id or derive_posting_id(
            canonical_url=identity_url,
            run_id=run_id,
            legacy_job_id=legacy_job_id,
            title=payload.get("title"),
            company=payload.get("company"),
        )
        observation = JobSourceObservation(
            source_type=_text(payload.get("source_type")) or "unknown",
            source_identifier=legacy_job_id,
            original_url=_optional_text(payload.get("link") or payload.get("source_url") or payload.get("apply_link")),
            observed_title=_optional_text(payload.get("title")),
            observed_company=_optional_text(payload.get("company")),
            observed_location=_optional_text(payload.get("location_raw")),
            observation_time=observed_at or _utc_now_iso(),
            run_id=run_id,
            workspace_id=workspace_id,
            raw_job_id=legacy_job_id,
            source_metadata={
                "legacy_filter_status": _text(payload.get("filter_status")) or None,
                "legacy_portal": _text(payload.get("portal")) or None,
            },
        )
        posted_at = _optional_text(payload.get("posted_datetime_estimated_utc") or payload.get("posted_at"))
        salary = payload.get("salary")
        if not isinstance(salary, Mapping):
            salary = None
        return cls(
            posting_id=resolved_posting_id,
            normalized_title=payload.get("title") or "",
            normalized_company=payload.get("company") or "",
            normalized_location=payload.get("location_raw") or "",
            work_arrangement=payload.get("work_arrangement"),
            description=payload.get("description_text") or payload.get("full_description") or payload.get("description") or "",
            canonical_apply_url=apply_url,
            canonical_source_url=source_url,
            posted_at=posted_at,
            first_seen=_text(payload.get("first_seen")) or observation.observation_time,
            last_seen=_text(payload.get("last_seen")) or observation.observation_time,
            state=payload.get("state") or JobPostingState.UNKNOWN.value,
            salary=SalaryRange.from_dict(salary) if salary else None,
            source_observations=[observation],
        )

    def to_analytics_dict(self) -> dict[str, Any]:
        return {
            "contract": "job_posting",
            "schema_version": self.schema_version,
            "posting_id": self.posting_id,
            "state": self.state,
            "version": self.version,
            "source_observation_count": len(self.source_observations),
            "source_type_count": len({item.source_type for item in self.source_observations}),
            "has_salary": self.salary is not None,
            "has_description": bool(self.description),
            "has_apply_url": self.canonical_apply_url is not None,
        }


def derive_posting_id(
    *,
    canonical_url: str | None,
    run_id: str | None,
    legacy_job_id: str | None,
    title: Any = "",
    company: Any = "",
) -> str:
    """Derive an ID from a canonical URL, or a visibly provisional legacy key.

    A run-local ``job_id`` is never used by itself as a global posting ID.  A
    URL-less legacy record remains provisional until a later cross-run identity
    adapter supplies a real canonical posting ID.
    """

    if canonical_url:
        return f"posting_{sha256(canonical_url.encode('utf-8')).hexdigest()[:24]}"
    provisional_key = "|".join(
        (
            _text(run_id) or "no_run",
            _text(legacy_job_id) or "no_job_id",
            compact_whitespace(_text(title)).casefold(),
            compact_whitespace(_text(company)).casefold(),
        )
    )
    return f"provisional_posting_{sha256(provisional_key.encode('utf-8')).hexdigest()[:24]}"


@dataclass(slots=True)
class EligibilityReason:
    reason_code: str
    category: str
    user_facing_summary: str
    evaluation_outcome: str
    source_type: str
    job_description_excerpt: str | None = None
    candidate_reference: ContractReference | None = None
    confidence: float | None = None
    is_explicit: bool | None = None
    evaluator_name: str = ""
    evaluator_version: str = ""
    schema_version: str = SCHEMA_VERSIONS["eligibility_reason"]

    def __post_init__(self) -> None:
        self.reason_code = _require_id(self.reason_code, "reason_code")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", self.reason_code):
            raise ContractValidationError("reason_code must be a stable lowercase identifier")
        self.category = _enum_value(self.category, EligibilityCategory, field_name="category")
        self.user_facing_summary = _require_id(self.user_facing_summary, "user_facing_summary")
        self.evaluation_outcome = _enum_value(self.evaluation_outcome, EligibilityStatus, field_name="evaluation_outcome")
        self.source_type = _require_id(self.source_type, "source_type")
        self.job_description_excerpt = _optional_text(self.job_description_excerpt)
        if self.candidate_reference is not None and not isinstance(self.candidate_reference, ContractReference):
            self.candidate_reference = ContractReference.from_dict(self.candidate_reference)
        self.confidence = _confidence(self.confidence)
        if self.is_explicit is not None and not isinstance(self.is_explicit, bool):
            raise ContractValidationError("is_explicit must be true, false, or null")
        self.evaluator_name = _text(self.evaluator_name)
        self.evaluator_version = _text(self.evaluator_version)
        self.schema_version = _text(self.schema_version) or SCHEMA_VERSIONS["eligibility_reason"]
        if not self.evaluator_name or not self.evaluator_version:
            raise ContractValidationError("eligibility reason requires evaluator_name and evaluator_version")
        if self.category in {EligibilityCategory.AUTHORIZATION.value, EligibilityCategory.SPONSORSHIP.value}:
            if self.evaluation_outcome == EligibilityStatus.INELIGIBLE.value and self.is_explicit is not True:
                raise ContractValidationError(
                    "authorization or sponsorship cannot be ineligible unless the job requirement is explicit"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "category": self.category,
            "user_facing_summary": self.user_facing_summary,
            "evaluation_outcome": self.evaluation_outcome,
            "source_type": self.source_type,
            "job_description_excerpt": self.job_description_excerpt,
            "candidate_reference": self.candidate_reference.to_dict() if self.candidate_reference else None,
            "confidence": self.confidence,
            "is_explicit": self.is_explicit,
            "evaluator_name": self.evaluator_name,
            "evaluator_version": self.evaluator_version,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EligibilityReason":
        return cls(
            reason_code=payload.get("reason_code") or "",
            category=payload.get("category") or "insufficient_information",
            user_facing_summary=payload.get("user_facing_summary") or payload.get("summary") or "",
            evaluation_outcome=payload.get("evaluation_outcome") or payload.get("outcome") or "uncertain",
            source_type=payload.get("source_type") or "unknown",
            job_description_excerpt=payload.get("job_description_excerpt") or payload.get("excerpt"),
            candidate_reference=(
                ContractReference.from_dict(payload["candidate_reference"])
                if isinstance(payload.get("candidate_reference"), Mapping)
                else None
            ),
            confidence=payload.get("confidence"),
            is_explicit=payload.get("is_explicit"),
            evaluator_name=payload.get("evaluator_name") or "",
            evaluator_version=payload.get("evaluator_version") or "",
            schema_version=payload.get("schema_version") or SCHEMA_VERSIONS["eligibility_reason"],
        )


@dataclass(slots=True)
class EligibilityEvaluation:
    profile_id: str
    posting_id: str
    status: str = EligibilityStatus.NOT_EVALUATED.value
    reasons: list[EligibilityReason] = field(default_factory=list)
    user_id: str | None = None
    evaluator_name: str = ""
    evaluator_version: str = ""
    evaluated_profile_version: int | str | None = None
    evaluated_evidence_version: int | str | None = None
    evaluated_job_version: int | str | None = None
    evaluated_at: str | None = None
    provenance_references: list[ContractReference] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSIONS["eligibility_evaluation"]

    def __post_init__(self) -> None:
        self.profile_id = _require_id(self.profile_id, "profile_id")
        self.posting_id = _require_id(self.posting_id, "posting_id")
        self.user_id = _optional_text(self.user_id)
        self.status = _enum_value(self.status, EligibilityStatus, field_name="status", default=EligibilityStatus.NOT_EVALUATED)
        self.reasons = [item if isinstance(item, EligibilityReason) else EligibilityReason.from_dict(item) for item in (self.reasons or [])]
        self.evaluator_name = _text(self.evaluator_name)
        self.evaluator_version = _text(self.evaluator_version)
        self.evaluated_profile_version = _version(self.evaluated_profile_version)
        self.evaluated_evidence_version = _version(self.evaluated_evidence_version)
        self.evaluated_job_version = _version(self.evaluated_job_version)
        self.evaluated_at = _optional_text(self.evaluated_at)
        self.provenance_references = [
            item if isinstance(item, ContractReference) else ContractReference.from_dict(item)
            for item in (self.provenance_references or [])
        ]
        self.schema_version = _text(self.schema_version) or SCHEMA_VERSIONS["eligibility_evaluation"]
        if self.status == EligibilityStatus.NOT_EVALUATED.value:
            if self.reasons or self.evaluator_name or self.evaluator_version or self.evaluated_at:
                raise ContractValidationError("not_evaluated eligibility cannot contain evaluator output")
        elif not self.evaluator_name or not self.evaluator_version:
            raise ContractValidationError("evaluated eligibility requires evaluator_name and evaluator_version")
        elif self.evaluated_at is None:
            self.evaluated_at = _utc_now_iso()
        if self.status == EligibilityStatus.INELIGIBLE.value:
            uncertain_auth = any(
                reason.category in {EligibilityCategory.AUTHORIZATION.value, EligibilityCategory.SPONSORSHIP.value}
                and reason.evaluation_outcome in {
                    EligibilityStatus.UNCERTAIN.value,
                    EligibilityStatus.NOT_EVALUATED.value,
                }
                for reason in self.reasons
            )
            if uncertain_auth:
                raise ContractValidationError(
                    "uncertain authorization or sponsorship must produce uncertain eligibility"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "posting_id": self.posting_id,
            "status": self.status,
            "reasons": [item.to_dict() for item in self.reasons],
            "user_id": self.user_id,
            "evaluator_name": self.evaluator_name,
            "evaluator_version": self.evaluator_version,
            "evaluated_profile_version": self.evaluated_profile_version,
            "evaluated_evidence_version": self.evaluated_evidence_version,
            "evaluated_job_version": self.evaluated_job_version,
            "evaluated_at": self.evaluated_at,
            "provenance_references": [item.to_dict() for item in self.provenance_references],
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EligibilityEvaluation":
        return cls(
            profile_id=payload.get("profile_id") or "",
            posting_id=payload.get("posting_id") or "",
            status=payload.get("status") or EligibilityStatus.NOT_EVALUATED.value,
            reasons=payload.get("reasons") or [],
            user_id=payload.get("user_id"),
            evaluator_name=payload.get("evaluator_name") or "",
            evaluator_version=payload.get("evaluator_version") or "",
            evaluated_profile_version=payload.get("evaluated_profile_version"),
            evaluated_evidence_version=payload.get("evaluated_evidence_version"),
            evaluated_job_version=payload.get("evaluated_job_version"),
            evaluated_at=payload.get("evaluated_at"),
            provenance_references=payload.get("provenance_references") or [],
            schema_version=payload.get("schema_version") or SCHEMA_VERSIONS["eligibility_evaluation"],
        )

    def to_analytics_dict(self) -> dict[str, Any]:
        """Exclude reason outcomes, excerpts, references, and candidate identity."""

        return {
            "contract": "eligibility_evaluation",
            "schema_version": self.schema_version,
            "evaluated": self.status != EligibilityStatus.NOT_EVALUATED.value,
            "reason_count": len(self.reasons),
            "has_evaluator": bool(self.evaluator_name and self.evaluator_version),
        }


@dataclass(slots=True)
class MatchEvidenceReference:
    """A pointer to a verified profile record; it intentionally carries no copied prose."""

    reference_type: str
    reference_id: str
    profile_id: str
    record_version: int | str | None = None
    location: str | None = None
    schema_version: str = SCHEMA_VERSIONS["match_evidence_reference"]

    ALLOWED_REFERENCE_TYPES = frozenset(
        {"candidate_evidence", "work_experience", "evidence_record", "career_profile", "verified_profile_record"}
    )

    def __post_init__(self) -> None:
        self.reference_type = _require_id(self.reference_type, "reference_type")
        if self.reference_type not in self.ALLOWED_REFERENCE_TYPES:
            raise ContractValidationError("reference_type must identify an existing verified profile record")
        self.reference_id = _require_id(self.reference_id, "reference_id")
        self.profile_id = _require_id(self.profile_id, "profile_id")
        self.record_version = _version(self.record_version)
        self.location = _optional_text(self.location)
        self.schema_version = _text(self.schema_version) or SCHEMA_VERSIONS["match_evidence_reference"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_type": self.reference_type,
            "reference_id": self.reference_id,
            "profile_id": self.profile_id,
            "record_version": self.record_version,
            "location": self.location,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MatchEvidenceReference":
        return cls(
            reference_type=payload.get("reference_type") or payload.get("type") or "",
            reference_id=payload.get("reference_id") or payload.get("evidence_id") or payload.get("experience_id") or "",
            profile_id=payload.get("profile_id") or "",
            record_version=payload.get("record_version") or payload.get("version"),
            location=payload.get("location"),
            schema_version=payload.get("schema_version") or SCHEMA_VERSIONS["match_evidence_reference"],
        )


@dataclass(slots=True)
class MatchRequirement:
    requirement_id: str
    requirement_text: str
    category: str
    status: str
    requiredness: str = RequirementRequiredness.UNSPECIFIED.value
    evidence_references: list[MatchEvidenceReference] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSIONS["match_requirement"]

    def __post_init__(self) -> None:
        self.requirement_id = _require_id(self.requirement_id, "requirement_id")
        self.requirement_text = _require_id(self.requirement_text, "requirement_text")
        self.category = _require_id(self.category, "category")
        self.status = _enum_value(self.status, RequirementMatchStatus, field_name="status")
        self.requiredness = _enum_value(
            self.requiredness,
            RequirementRequiredness,
            field_name="requiredness",
            default=RequirementRequiredness.UNSPECIFIED,
        )
        self.evidence_references = [
            item if isinstance(item, MatchEvidenceReference) else MatchEvidenceReference.from_dict(item)
            for item in (self.evidence_references or [])
        ]
        self.schema_version = _text(self.schema_version) or SCHEMA_VERSIONS["match_requirement"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "requirement_text": self.requirement_text,
            "category": self.category,
            "status": self.status,
            "requiredness": self.requiredness,
            "evidence_references": [item.to_dict() for item in self.evidence_references],
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MatchRequirement":
        return cls(
            requirement_id=payload.get("requirement_id") or "",
            requirement_text=payload.get("requirement_text") or payload.get("text") or "",
            category=payload.get("category") or payload.get("requirement_category") or "other",
            status=payload.get("status") or RequirementMatchStatus.UNCERTAIN.value,
            requiredness=payload.get("requiredness") or RequirementRequiredness.UNSPECIFIED.value,
            evidence_references=payload.get("evidence_references") or [],
            schema_version=payload.get("schema_version") or SCHEMA_VERSIONS["match_requirement"],
        )


@dataclass(slots=True)
class MatchEvaluation:
    profile_id: str
    posting_id: str
    overall_score: float | None = None
    score_scale: str | None = None
    score_version: str | None = None
    label: str | None = None
    matching_requirements: list[MatchRequirement] = field(default_factory=list)
    missing_requirements: list[MatchRequirement] = field(default_factory=list)
    uncertain_requirements: list[MatchRequirement] = field(default_factory=list)
    evidence_references: list[MatchEvidenceReference] = field(default_factory=list)
    explanation_summary: str | None = None
    user_id: str | None = None
    evaluator_name: str = ""
    evaluator_version: str = ""
    evaluated_profile_version: int | str | None = None
    evaluated_evidence_version: int | str | None = None
    evaluated_job_version: int | str | None = None
    evaluated_at: str | None = None
    provenance_references: list[ContractReference] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSIONS["match_evaluation"]

    def __post_init__(self) -> None:
        self.profile_id = _require_id(self.profile_id, "profile_id")
        self.posting_id = _require_id(self.posting_id, "posting_id")
        if self.overall_score is not None:
            try:
                self.overall_score = float(self.overall_score)
            except (TypeError, ValueError) as exc:
                raise ContractValidationError("overall_score must be a number or null") from exc
            if not 0 <= self.overall_score <= 1:
                raise ContractValidationError("overall_score must be between 0 and 1 for the default scale")
        self.score_scale = _optional_text(self.score_scale)
        self.score_version = _optional_text(self.score_version)
        self.label = _optional_text(self.label)
        self.matching_requirements = self._requirements(self.matching_requirements, RequirementMatchStatus.MATCHING.value)
        self.missing_requirements = self._requirements(self.missing_requirements, RequirementMatchStatus.MISSING.value)
        self.uncertain_requirements = self._requirements(self.uncertain_requirements, RequirementMatchStatus.UNCERTAIN.value)
        self.evidence_references = [
            item if isinstance(item, MatchEvidenceReference) else MatchEvidenceReference.from_dict(item)
            for item in (self.evidence_references or [])
        ]
        self.explanation_summary = _optional_text(self.explanation_summary)
        self.user_id = _optional_text(self.user_id)
        self.evaluator_name = _text(self.evaluator_name)
        self.evaluator_version = _text(self.evaluator_version)
        self.evaluated_profile_version = _version(self.evaluated_profile_version)
        self.evaluated_evidence_version = _version(self.evaluated_evidence_version)
        self.evaluated_job_version = _version(self.evaluated_job_version)
        self.evaluated_at = _optional_text(self.evaluated_at)
        self.provenance_references = [
            item if isinstance(item, ContractReference) else ContractReference.from_dict(item)
            for item in (self.provenance_references or [])
        ]
        self.schema_version = _text(self.schema_version) or SCHEMA_VERSIONS["match_evaluation"]
        if self.overall_score is not None and not self.evaluator_name:
            raise ContractValidationError("overall_score cannot be present when no evaluator ran")
        if self.overall_score is not None and (not self.score_scale or not self.score_version):
            raise ContractValidationError("a score requires score_scale and score_version")
        if self.evaluator_name and not self.evaluator_version:
            raise ContractValidationError("evaluator_name requires evaluator_version")
        if self.evaluator_name and self.evaluated_at is None:
            self.evaluated_at = _utc_now_iso()

    @staticmethod
    def _requirements(value: Any, expected_status: str) -> list[MatchRequirement]:
        requirements = [
            item if isinstance(item, MatchRequirement) else MatchRequirement.from_dict(item)
            for item in (value or [])
        ]
        if any(item.status != expected_status for item in requirements):
            raise ContractValidationError(f"requirements in this collection must have status={expected_status}")
        return requirements

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "posting_id": self.posting_id,
            "overall_score": self.overall_score,
            "score_scale": self.score_scale,
            "score_version": self.score_version,
            "label": self.label,
            "matching_requirements": [item.to_dict() for item in self.matching_requirements],
            "missing_requirements": [item.to_dict() for item in self.missing_requirements],
            "uncertain_requirements": [item.to_dict() for item in self.uncertain_requirements],
            "evidence_references": [item.to_dict() for item in self.evidence_references],
            "explanation_summary": self.explanation_summary,
            "user_id": self.user_id,
            "evaluator_name": self.evaluator_name,
            "evaluator_version": self.evaluator_version,
            "evaluated_profile_version": self.evaluated_profile_version,
            "evaluated_evidence_version": self.evaluated_evidence_version,
            "evaluated_job_version": self.evaluated_job_version,
            "evaluated_at": self.evaluated_at,
            "provenance_references": [item.to_dict() for item in self.provenance_references],
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MatchEvaluation":
        return cls(
            profile_id=payload.get("profile_id") or "",
            posting_id=payload.get("posting_id") or "",
            overall_score=payload.get("overall_score"),
            score_scale=payload.get("score_scale"),
            score_version=payload.get("score_version"),
            label=payload.get("label"),
            matching_requirements=payload.get("matching_requirements") or [],
            missing_requirements=payload.get("missing_requirements") or [],
            uncertain_requirements=payload.get("uncertain_requirements") or [],
            evidence_references=payload.get("evidence_references") or [],
            explanation_summary=payload.get("explanation_summary"),
            user_id=payload.get("user_id"),
            evaluator_name=payload.get("evaluator_name") or "",
            evaluator_version=payload.get("evaluator_version") or "",
            evaluated_profile_version=payload.get("evaluated_profile_version"),
            evaluated_evidence_version=payload.get("evaluated_evidence_version"),
            evaluated_job_version=payload.get("evaluated_job_version"),
            evaluated_at=payload.get("evaluated_at"),
            provenance_references=payload.get("provenance_references") or [],
            schema_version=payload.get("schema_version") or SCHEMA_VERSIONS["match_evaluation"],
        )

    @classmethod
    def from_profile_requirement_matches(
        cls,
        *,
        profile_id: str,
        posting_id: str,
        matches: Sequence[Any],
        user_id: str | None = None,
        evidence_reference_type: str = "work_experience",
        **kwargs: Any,
    ) -> "MatchEvaluation":
        """Adapt existing ``ProfileRequirementMatch`` values without copying snippets."""

        converted: list[MatchRequirement] = []
        for match in matches:
            payload = match.to_dict() if hasattr(match, "to_dict") else dict(match)
            status_map = {
                "strong": RequirementMatchStatus.MATCHING.value,
                "partial": RequirementMatchStatus.MATCHING.value,
                "missing": RequirementMatchStatus.MISSING.value,
            }
            status = status_map.get(_text(payload.get("match_status")), RequirementMatchStatus.UNCERTAIN.value)
            evidence_ids = payload.get("matched_evidence_ids") or []
            references = [
                MatchEvidenceReference(
                    reference_type=evidence_reference_type,
                    reference_id=str(evidence_id),
                    profile_id=profile_id,
                )
                for evidence_id in evidence_ids
                if str(evidence_id).strip()
            ]
            converted.append(
                MatchRequirement(
                    requirement_id=payload.get("requirement_id") or "",
                    requirement_text=payload.get("requirement_text") or "",
                    category=payload.get("requirement_category") or "other",
                    status=status,
                    evidence_references=references,
                )
            )
        kwargs.setdefault("overall_score", None)
        kwargs.setdefault("evaluator_name", "legacy_profile_matching")
        kwargs.setdefault("evaluator_version", "adapter_v1")
        return cls(
            profile_id=profile_id,
            posting_id=posting_id,
            user_id=user_id,
            matching_requirements=[item for item in converted if item.status == RequirementMatchStatus.MATCHING.value],
            missing_requirements=[item for item in converted if item.status == RequirementMatchStatus.MISSING.value],
            uncertain_requirements=[item for item in converted if item.status == RequirementMatchStatus.UNCERTAIN.value],
            evidence_references=[ref for item in converted for ref in item.evidence_references],
            **kwargs,
        )

    @classmethod
    def from_job_application_binding(
        cls,
        binding: Any,
        *,
        posting_id: str | None = None,
        user_id: str | None = None,
        **kwargs: Any,
    ) -> "MatchEvaluation":
        """Adapt a binding; callers should pass the canonical posting ID explicitly."""

        profile_id = _require_id(getattr(binding, "profile_id", ""), "profile_id")
        legacy_job_id = _text(getattr(binding, "job_id", ""))
        run_id = _text(getattr(binding, "run_id", ""))
        resolved_posting_id = posting_id or derive_posting_id(
            canonical_url=None,
            run_id=run_id,
            legacy_job_id=legacy_job_id,
            title=getattr(binding, "job_title", ""),
            company=getattr(binding, "company", ""),
        )
        matches = getattr(binding, "requirement_matches", []) or []
        kwargs.setdefault("explanation_summary", _optional_text(getattr(binding, "match_summary", "")))
        kwargs.setdefault("overall_score", None)
        kwargs.setdefault("evaluator_name", "legacy_profile_matching")
        kwargs.setdefault("evaluator_version", "adapter_v1")
        return cls.from_profile_requirement_matches(
            profile_id=profile_id,
            posting_id=resolved_posting_id,
            matches=matches,
            user_id=user_id,
            **kwargs,
        )

    def to_analytics_dict(self) -> dict[str, Any]:
        return {
            "contract": "match_evaluation",
            "schema_version": self.schema_version,
            "posting_id": self.posting_id,
            "has_score": self.overall_score is not None,
            "label": self.label,
            "matching_requirement_count": len(self.matching_requirements),
            "missing_requirement_count": len(self.missing_requirements),
            "uncertain_requirement_count": len(self.uncertain_requirements),
            "evidence_reference_count": len(self.evidence_references),
            "has_explanation": bool(self.explanation_summary),
        }


@dataclass(slots=True)
class JobDisposition:
    user_id: str
    posting_id: str
    state: str = JobDispositionState.NONE.value
    reason_code: str | None = None
    source_of_change: str = "user"
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    version: int = 1
    schema_version: str = SCHEMA_VERSIONS["job_disposition"]

    def __post_init__(self) -> None:
        self.user_id = _require_id(self.user_id, "user_id")
        self.posting_id = _require_id(self.posting_id, "posting_id")
        self.state = _enum_value(self.state, JobDispositionState, field_name="state", default=JobDispositionState.NONE)
        self.reason_code = _optional_text(self.reason_code)
        self.source_of_change = _require_id(self.source_of_change, "source_of_change")
        self.created_at = _text(self.created_at) or _utc_now_iso()
        self.updated_at = _text(self.updated_at) or self.created_at
        try:
            self.version = int(self.version)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("version must be a positive integer") from exc
        if self.version < 1:
            raise ContractValidationError("version must be a positive integer")
        self.schema_version = _text(self.schema_version) or SCHEMA_VERSIONS["job_disposition"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "posting_id": self.posting_id,
            "state": self.state,
            "reason_code": self.reason_code,
            "source_of_change": self.source_of_change,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "JobDisposition":
        return cls(
            user_id=payload.get("user_id") or "",
            posting_id=payload.get("posting_id") or "",
            state=payload.get("state") or JobDispositionState.NONE.value,
            reason_code=payload.get("reason_code"),
            source_of_change=payload.get("source_of_change") or payload.get("source") or "user",
            created_at=payload.get("created_at") or _utc_now_iso(),
            updated_at=payload.get("updated_at") or _utc_now_iso(),
            version=payload.get("version") or 1,
            schema_version=payload.get("schema_version") or SCHEMA_VERSIONS["job_disposition"],
        )

    def transition_to(self, state: str, *, source_of_change: str, reason_code: str | None = None) -> "JobDisposition":
        target = _enum_value(state, JobDispositionState, field_name="state")
        if not can_transition_disposition(self.state, target):
            raise ContractValidationError(f"cannot transition disposition from {self.state} to {target}")
        return replace(
            self,
            state=target,
            reason_code=reason_code,
            source_of_change=source_of_change,
            updated_at=_utc_now_iso(),
            version=self.version + 1,
        )

    def to_analytics_dict(self) -> dict[str, Any]:
        return {
            "contract": "job_disposition",
            "schema_version": self.schema_version,
            "state": self.state,
            "source_of_change": self.source_of_change,
            "version": self.version,
        }


def can_transition_disposition(current_state: str, target_state: str) -> bool:
    """Return whether a current-state update is allowed.

    Hidden and dismissed jobs are restored by moving to ``none``.  Requeue is
    intentionally absent: ``/rejected-jobs/requeue`` remains document
    generation behavior, not a feed disposition transition.
    """

    current = _enum_value(current_state, JobDispositionState, field_name="current_state")
    target = _enum_value(target_state, JobDispositionState, field_name="target_state")
    if current == target:
        return True
    if current in {JobDispositionState.HIDDEN.value, JobDispositionState.DISMISSED.value}:
        return target == JobDispositionState.NONE.value
    if current == JobDispositionState.SAVED.value and target == JobDispositionState.PREPARING.value:
        return True
    if current == JobDispositionState.PREPARING.value and target == JobDispositionState.APPLIED.value:
        return True
    if target == JobDispositionState.ARCHIVED.value:
        return True
    if current == JobDispositionState.NONE.value:
        return target != JobDispositionState.NONE.value
    return target in {
        JobDispositionState.NONE.value,
        JobDispositionState.SAVED.value,
        JobDispositionState.INTERESTED.value,
        JobDispositionState.PREPARING.value,
        JobDispositionState.APPLIED.value,
        JobDispositionState.ARCHIVED.value,
    }


def normalize_personalized_feature_key(value: str | PersonalizedFeatureKey) -> str:
    normalized = _text(value).casefold()
    canonical = FRONTEND_PERSONALIZED_FEATURE_KEY_MAP.get(normalized)
    if canonical is None:
        raise ContractValidationError(f"unknown personalized feature key: {value}")
    return canonical


def canonical_plan_id(value: str) -> str:
    normalized = _text(value).casefold()
    if normalized not in CANONICAL_PLAN_IDS:
        raise ContractValidationError(f"plan_id must be one of: {', '.join(CANONICAL_PLAN_IDS)}")
    return normalized


def adapt_language_rule_reasons(
    reasons: Sequence[str],
    *,
    evaluator_name: str = "language_rules",
    evaluator_version: str = "adapter_v1",
) -> list[EligibilityReason]:
    """Adapt ``language_rules.detect_reasons`` strings without changing that module."""

    return [
        EligibilityReason(
            reason_code="language_requirement_detected",
            category=EligibilityCategory.LANGUAGE.value,
            user_facing_summary=str(reason),
            evaluation_outcome=EligibilityStatus.UNCERTAIN.value,
            source_type="language_rules",
            job_description_excerpt=None,
            confidence=None,
            is_explicit=None,
            evaluator_name=evaluator_name,
            evaluator_version=evaluator_version,
        )
        for reason in reasons
        if _text(reason)
    ]


__all__ = [
    "AuthorizationStatus",
    "CANONICAL_PLAN_IDS",
    "CandidateLanguagePreference",
    "CandidateSearchPreferences",
    "ContractReference",
    "ContractValidationError",
    "EligibilityCategory",
    "EligibilityEvaluation",
    "EligibilityReason",
    "EligibilityStatus",
    "EmploymentType",
    "FRONTEND_PERSONALIZED_FEATURE_KEY_MAP",
    "JobDisposition",
    "JobDispositionState",
    "JobPosting",
    "JobPostingProvenance",
    "JobPostingState",
    "JobSourceObservation",
    "MatchEvidenceReference",
    "MatchEvaluation",
    "MatchRequirement",
    "PersonalizedFeatureKey",
    "RelocationPreference",
    "RequirementMatchStatus",
    "RequirementRequiredness",
    "SCHEMA_VERSIONS",
    "SalaryRange",
    "SponsorshipRequirement",
    "WorkArrangement",
    "WorkAuthorizationPreference",
    "adapt_language_rule_reasons",
    "can_transition_disposition",
    "canonical_plan_id",
    "derive_posting_id",
    "normalize_personalized_feature_key",
]
