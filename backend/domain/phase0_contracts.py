from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from backend.capabilities.tailored_documents.modes import (
    AGGRESSIVE_CUSTOMIZATION_EXTRA_PROMPT_FIELD,
    AGGRESSIVE_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD,
    APPLIED_CV_DOCUMENT_TYPE,
    DEFAULT_CV_GENERATION_MODE,
    LIGHT_CUSTOMIZATION_EXTRA_PROMPT_FIELD,
    LIGHT_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD,
    normalize_cv_generation_mode,
)


PHASE0_CONTRACT_VERSION = "2026-04-20"

WORKSPACE_CONFIGURATION_V2_SCHEMA = "workspace_configuration_v2"
CANDIDATE_ASSET_DESCRIPTOR_SCHEMA = "candidate_asset_descriptor_v1"
REJECTED_JOB_REVIEW_SCHEMA = "rejected_job_review_v1"
MAIL_CONNECTION_CONTRACT_SCHEMA = "mail_connection_contract_v1"
REFERRAL_RELATIONSHIP_SCHEMA = "referral_relationship_v1"
TRACKER_APPLICATION_SCHEMA = "tracker_application_v1"
GMAIL_APPLICATION_DETECTION_SCHEMA = "gmail_application_detection_v1"
APPLICATION_DOCUMENT_SCHEMA = "application_document_v1"
ATS_EXPORT_GATE_SCHEMA = "ats_export_gate_v1"

WORKSPACE_TARGETING_METHOD = "keyword_profile_aligned"
WORKSPACE_KEYWORD_LIMIT = 12
JOB_FILTERING_MODE_STRICT = "Strict Match"
JOB_FILTERING_MODE_BROADER = "Broader Match"
JOB_FILTERING_MODES = [
    JOB_FILTERING_MODE_STRICT,
    JOB_FILTERING_MODE_BROADER,
]

WORKSPACE_USER_FACING_FIELD_IDS = [
    "workspace_cv_asset_id",
    "cv_generation_mode",
    "keywords",
    "country_codes",
    "target_roles",
    "job_filtering_mode",
    "time_posted_seconds",
    "experience_levels",
    "manual_url_seed_list",
    "academic_career_sites",
    "company_career_sites",
    "portals",
    "forbidden_title_keywords",
    "max_german_level",
    "french_special_char_threshold",
    "spanish_special_char_threshold",
    "low_applicant_threshold",
    "languages",
    "cv_template",
    "cv_color_scheme",
    "cv_font",
    "include_photo",
    "stage1_model",
    "stage1_extra_prompt",
    "stage1_prompt_override",
    "stage4_model",
    "stage4_fallback_model",
    LIGHT_CUSTOMIZATION_EXTRA_PROMPT_FIELD,
    LIGHT_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD,
    AGGRESSIVE_CUSTOMIZATION_EXTRA_PROMPT_FIELD,
    AGGRESSIVE_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD,
    "stage4_max_jobs",
    "stage4_extra_prompt",
    "stage4_prompt_override",
]

WORKSPACE_HIDDEN_FIELD_IDS = [
    "job_filtering_target_phrases",
    "linkedin_max_pages",
    "max_enrich_jobs",
    "ai_batch_size",
    "reuse_scrape_snapshot",
    "page_fetch_sleep_seconds",
    "use_proxy_fallback",
    "manual_request_timeout_seconds",
    "company_site_max_jobs_per_site",
    "company_site_request_timeout_seconds",
    "dedupe_against_tracker",
    "stage4_sleep_seconds",
    "stage4_retries",
    "stage4_retry_sleep",
    "force_regenerate",
    "tracker_sheet_name",
    "tracker_expert_mode",
    "profile_default",
]

WORKSPACE_DEPRECATED_FIELD_IDS = [
    "geo_id",
    "linkedin_geo_id",
    "candidate_name",
    "candidate_email",
]

SOURCE_ID_ALIASES = {
    "linkedin_jobs": "linkedin_search",
    "curated_job_urls": "curated_urls",
    "job_board_collection": "multi_portal",
}

REJECTED_JOB_REASON_DEFINITIONS = [
    {"code": "keyword_mismatch", "label": "Keyword mismatch"},
    {"code": "seniority_mismatch", "label": "Seniority mismatch"},
    {"code": "language_mismatch", "label": "Language mismatch"},
    {"code": "location_mismatch", "label": "Location mismatch"},
    {"code": "duplicate", "label": "Duplicate or already tracked"},
    {"code": "source_validation_failed", "label": "Source validation failed"},
    {"code": "manual_rejection", "label": "Manually rejected"},
    {"code": "unknown", "label": "Unknown or uncategorized"},
]

MAIL_CONNECTION_AUTH_STRATEGIES = [
    "google_oauth",
    "legacy_imap_password",
]

MAIL_CONNECTION_STATUSES = [
    "disconnected",
    "pending_authorization",
    "connected",
    "attention_required",
]

MAIL_AUTHORIZATION_STATES = [
    "not_started",
    "authorization_url_created",
    "authorized",
    "failed",
]

MAIL_SUPPORTED_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
]

REFERRAL_SOURCE_KINDS = [
    "manual",
    "linkedin_csv",
    "linkedin_csv_import",
    "enriched",
]

APPLICATION_STATUSES = [
    "Not applied",
    "Applied",
    "Interviewing",
    "Rejected",
    "Offer",
    "Withdrawn",
    "Unknown",
]

APPLICATION_STATUS_DEFAULT = "Unknown"

LEGACY_TRACKER_STATUS_TO_APPLICATION_STATUS = {
    "": "Not applied",
    "not_applied": "Not applied",
    "not applied": "Not applied",
    "false": "Not applied",
    "no": "Not applied",
    "applied": "Applied",
    "true": "Applied",
    "yes": "Applied",
    "email_confirmed": "Applied",
    "email confirmed": "Applied",
    "interview_invited": "Interviewing",
    "interview invited": "Interviewing",
    "interviewing": "Interviewing",
    "rejected": "Rejected",
    "offer": "Offer",
    "withdrawn": "Withdrawn",
    "unknown": "Unknown",
}

REFERRAL_OUTREACH_STATUSES = [
    "Not contacted",
    "Contacted",
    "Replied",
    "Referral offered",
    "No referral",
]

REFERRAL_CONTACT_LIFECYCLE_STATUSES = [
    "active",
    "inactive",
]

GMAIL_SCAN_WINDOWS = [
    "now",
    "last_1_month",
    "last_2_months",
    "last_3_months",
]

GMAIL_DETECTION_CONFIDENCE_LEVELS = [
    "high",
    "medium",
    "low",
]

GMAIL_DETECTION_APPROVAL_STATES = [
    "pending_review",
    "approved",
    "dismissed",
]

APPLICATION_DOCUMENT_TYPES = [
    "Original CV",
    APPLIED_CV_DOCUMENT_TYPE,
    "Tailored CV",
    "Cover letter",
    "Transcript",
    "Certificate",
    "Other",
]

ATS_GATE_STATES = [
    "not_started",
    "drafting",
    "scoring",
    "passed",
    "blocked",
    "warning_acknowledged",
    "exported_anyway",
]

DEFAULT_MULTI_PORTAL_IDS = [
    "indeed",
    "stepstone",
]


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _casefold_key(value: Any) -> str:
    return _clean_text(value).casefold().replace("-", "_")


def _clean_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _clean_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple | set):
        return list(value)
    if value in (None, ""):
        return []
    return [value]


def _clean_tag_list(value: Any, *, limit: int = 50, lower: bool = False) -> list[str]:
    raw_values: list[str] = []
    for item in _clean_list(value):
        if isinstance(item, str):
            parts = item.replace("\r", "\n").replace(",", "\n").split("\n")
            raw_values.extend(parts)
        else:
            raw_values.append(str(item))
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        value_text = raw_value.strip()
        if not value_text:
            continue
        if lower:
            value_text = value_text.lower()
        dedupe_key = value_text.casefold()
        if dedupe_key in seen:
            continue
        cleaned.append(value_text)
        seen.add(dedupe_key)
        if len(cleaned) >= limit:
            break
    return cleaned


def _normalize_company_site_entries(value: Any) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    if isinstance(value, str):
        raw_items = [line.strip() for line in value.replace("\r", "\n").split("\n") if line.strip()]
        parsed_values: list[Any] = raw_items
    else:
        parsed_values = _clean_list(value)
    for item in parsed_values:
        company_name = ""
        url = ""
        if isinstance(item, Mapping):
            company_name = _clean_text(item.get("company_name") or item.get("company"))
            url = _clean_text(item.get("url"))
        else:
            text = _clean_text(item)
            if "|" in text:
                company_name, url = [part.strip() for part in text.split("|", 1)]
            else:
                url = text
        if not company_name and not url:
            continue
        entry = {
            "company_name": company_name,
            "url": url,
        }
        dedupe_key = (entry["company_name"].casefold(), entry["url"].casefold())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        entries.append(entry)
    return entries


def _normalize_prompt_overrides(settings: Mapping[str, Any]) -> list[dict[str, str]]:
    overrides: list[dict[str, str]] = []
    aggressive_extra_prompt = _clean_text(
        settings.get(AGGRESSIVE_CUSTOMIZATION_EXTRA_PROMPT_FIELD) or settings.get("stage4_extra_prompt")
    )
    aggressive_prompt_override = _clean_text(
        settings.get(AGGRESSIVE_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD) or settings.get("stage4_prompt_override")
    )
    prompt_pairs = [
        ("stage1", "append", _clean_text(settings.get("stage1_extra_prompt"))),
        ("stage1", "replace", _clean_text(settings.get("stage1_prompt_override"))),
        ("stage4_light", "append", _clean_text(settings.get(LIGHT_CUSTOMIZATION_EXTRA_PROMPT_FIELD))),
        ("stage4_light", "replace", _clean_text(settings.get(LIGHT_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD))),
        ("stage4_aggressive", "append", aggressive_extra_prompt),
        ("stage4_aggressive", "replace", aggressive_prompt_override),
    ]
    for stage_id, override_type, value in prompt_pairs:
        if not value:
            continue
        overrides.append(
            {
                "stage_id": stage_id,
                "override_type": override_type,
                "value": value,
            }
        )
    return overrides


def normalize_application_status(value: Any, *, default: str = APPLICATION_STATUS_DEFAULT) -> str:
    """Return the user-facing application status for legacy and new status values."""
    text = _clean_text(value)
    if not text:
        if default == "":
            return ""
        return default if default in APPLICATION_STATUSES else APPLICATION_STATUS_DEFAULT
    for status in APPLICATION_STATUSES:
        if text.casefold() == status.casefold():
            return status
    legacy_match = LEGACY_TRACKER_STATUS_TO_APPLICATION_STATUS.get(_casefold_key(text))
    if legacy_match:
        return legacy_match
    if default == "":
        return ""
    return default if default in APPLICATION_STATUSES else APPLICATION_STATUS_DEFAULT


def legacy_tracker_status_for_application_status(value: Any) -> str:
    status = normalize_application_status(value)
    if status == "Not applied":
        return "not_applied"
    if status == "Applied":
        return "applied"
    if status == "Interviewing":
        return "interview_invited"
    if status == "Rejected":
        return "rejected"
    if status == "Offer":
        return "offer"
    if status == "Withdrawn":
        return "withdrawn"
    return "unknown"


def normalize_referral_outreach_status(value: Any, *, default: str = "Not contacted") -> str:
    text = _clean_text(value)
    if not text:
        return default
    for status in REFERRAL_OUTREACH_STATUSES:
        if text.casefold().replace("_", " ") == status.casefold():
            return status
    return default


def normalize_gmail_scan_window(value: Any, *, default: str = "last_1_month") -> str:
    text = _casefold_key(value)
    if text in GMAIL_SCAN_WINDOWS:
        return text
    return default


def _normalize_source_ids(payload: Mapping[str, Any], settings: Mapping[str, Any]) -> set[str]:
    source_ids = {
        SOURCE_ID_ALIASES.get(_clean_text(item), _clean_text(item))
        for item in payload.get("source_ids")
        or payload.get("selected_source_ids")
        or settings.get("source_ids")
        or []
        if _clean_text(item)
    }
    if settings.get("manual_url_seed_list"):
        source_ids.add("curated_urls")
    if settings.get("academic_career_sites"):
        source_ids.add("academic_career_sites")
    if settings.get("company_career_sites"):
        source_ids.add("company_career_sites")
    if settings.get("geo_id") or settings.get("time_posted_seconds") or settings.get("experience_levels"):
        source_ids.add("linkedin_search")
    return source_ids


def _normalize_country_codes(value: Any) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in _clean_list(value):
        if isinstance(item, Mapping):
            code = _clean_text(item.get("code") or item.get("country_code"))
        else:
            code = _clean_text(item)
        code = code.upper()
        if not code or code in seen:
            continue
        cleaned.append(code)
        seen.add(code)
    return cleaned


def _derive_keywords_from_target_roles(settings: Mapping[str, Any]) -> list[str]:
    target_roles = _clean_tag_list(settings.get("target_roles"), limit=WORKSPACE_KEYWORD_LIMIT)
    return [role.casefold() for role in target_roles]


def normalize_job_filtering_mode(value: Any, *, default: str = JOB_FILTERING_MODE_BROADER) -> str:
    text = _clean_text(value)
    if not text:
        return default
    normalized = " ".join(text.casefold().replace("_", " ").replace("-", " ").split())
    if normalized == "strict match":
        return JOB_FILTERING_MODE_STRICT
    if normalized == "broader match":
        return JOB_FILTERING_MODE_BROADER
    return default


def derive_job_filtering_target_phrases(settings: Mapping[str, Any]) -> list[str]:
    phrases: list[str] = []
    seen: set[str] = set()
    for value in [
        *_clean_tag_list(settings.get("target_roles"), limit=25),
        *_clean_tag_list(settings.get("keywords"), limit=WORKSPACE_KEYWORD_LIMIT),
    ]:
        phrase = _clean_text(value)
        dedupe_key = phrase.casefold()
        if not phrase or dedupe_key in seen:
            continue
        phrases.append(phrase)
        seen.add(dedupe_key)
    return phrases


def default_workspace_configuration_v2() -> dict[str, Any]:
    return {
        "schema_version": WORKSPACE_CONFIGURATION_V2_SCHEMA,
        "cv_binding": {
            "required": True,
            "binding_mode": "selected_asset_or_upload",
            "asset_id": "",
            "profile_label": "",
        },
        "targeting": {
            "method": WORKSPACE_TARGETING_METHOD,
            "keyword_limit": WORKSPACE_KEYWORD_LIMIT,
            "keywords": [],
            "inferred_from_cv": True,
        },
        "location_preferences": {
            "country_codes": [],
            "legacy_source_locations": {
                "linkedin_geo_id": "",
            },
        },
        "source_configuration": {
            "linkedin_search": {
                "enabled": False,
                "posted_since_seconds": 604800,
                "experience_levels": [],
                "validate_before_run": False,
            },
            "multi_portal": {
                "enabled": False,
                "portals": list(DEFAULT_MULTI_PORTAL_IDS),
                "cities": [],
                "validate_before_run": True,
            },
            "curated_urls": {
                "enabled": False,
                "urls": [],
                "validate_before_run": True,
            },
            "academic_career_sites": {
                "enabled": False,
                "institutions": [],
                "validate_before_run": True,
            },
            "company_career_sites": {
                "enabled": False,
                "companies": [],
                "validate_before_run": True,
            },
        },
        "filter_preferences": {
            "job_filtering": {
                "mode": JOB_FILTERING_MODE_BROADER,
                "target_phrases": [],
            },
            "forbidden_title_keywords": [],
            "language_preferences": {
                "profile_languages": [],
                "max_german_level": "any",
                "allow_french": True,
                "allow_spanish": True,
            },
        },
        "document_preferences": {
            "cv_generation_mode": DEFAULT_CV_GENERATION_MODE,
            "cv_template": "",
            "cv_color_scheme": "",
            "cv_font": "",
            "include_photo": True,
        },
        "prompt_preferences": {
            "stage_overrides": [],
        },
        "technical_runtime": {},
        "legacy_passthrough": {},
    }


def normalize_workspace_configuration_v2(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    raw_payload = dict(payload or {})
    raw_settings = raw_payload.get("settings")
    settings = dict(raw_settings or raw_payload)
    contract = deepcopy(default_workspace_configuration_v2())
    source_ids = _normalize_source_ids(raw_payload, settings)

    derived_keywords = _derive_keywords_from_target_roles(settings)
    keywords = _clean_tag_list(settings.get("keywords"), limit=WORKSPACE_KEYWORD_LIMIT, lower=True)
    if not keywords and derived_keywords:
        keywords = derived_keywords[:WORKSPACE_KEYWORD_LIMIT]
    contract["cv_binding"]["asset_id"] = _clean_text(
        settings.get("workspace_cv_asset_id") or raw_payload.get("workspace_cv_asset_id")
    )
    contract["cv_binding"]["profile_label"] = _clean_text(
        raw_payload.get("profile_label") or settings.get("profile_label")
    )
    contract["targeting"]["keywords"] = keywords

    country_codes = _normalize_country_codes(
        settings.get("country_codes")
        or settings.get("countries")
        or settings.get("country")
    )
    contract["location_preferences"]["country_codes"] = country_codes
    contract["location_preferences"]["legacy_source_locations"]["linkedin_geo_id"] = _clean_text(
        settings.get("geo_id") or settings.get("linkedin_geo_id")
    )

    contract["source_configuration"]["linkedin_search"]["enabled"] = "linkedin_search" in source_ids
    contract["source_configuration"]["linkedin_search"]["posted_since_seconds"] = int(
        settings.get("time_posted_seconds") or 604800
    )
    contract["source_configuration"]["linkedin_search"]["experience_levels"] = [
        int(item)
        for item in _clean_list(settings.get("experience_levels"))
        if str(item).strip()
    ]

    contract["source_configuration"]["multi_portal"]["enabled"] = "multi_portal" in source_ids
    configured_portals = _clean_tag_list(
        settings.get("portals") or settings.get("portal_ids"),
        limit=10,
        lower=True,
    )
    if configured_portals:
        contract["source_configuration"]["multi_portal"]["portals"] = configured_portals
    configured_cities = _clean_tag_list(settings.get("cities"), limit=10)
    if configured_cities:
        contract["source_configuration"]["multi_portal"]["cities"] = configured_cities

    contract["source_configuration"]["curated_urls"]["enabled"] = "curated_urls" in source_ids
    contract["source_configuration"]["curated_urls"]["urls"] = _clean_tag_list(
        settings.get("manual_url_seed_list"),
        limit=250,
    )

    contract["source_configuration"]["academic_career_sites"]["enabled"] = "academic_career_sites" in source_ids
    contract["source_configuration"]["academic_career_sites"]["institutions"] = _normalize_company_site_entries(
        settings.get("academic_career_sites")
    )

    contract["source_configuration"]["company_career_sites"]["enabled"] = "company_career_sites" in source_ids
    contract["source_configuration"]["company_career_sites"]["companies"] = _normalize_company_site_entries(
        settings.get("company_career_sites")
    )

    contract["filter_preferences"]["forbidden_title_keywords"] = _clean_tag_list(
        settings.get("forbidden_title_keywords"),
        limit=50,
        lower=True,
    )
    contract["filter_preferences"]["job_filtering"]["mode"] = normalize_job_filtering_mode(
        settings.get("job_filtering_mode")
    )
    contract["filter_preferences"]["job_filtering"]["target_phrases"] = derive_job_filtering_target_phrases(settings)
    contract["filter_preferences"]["language_preferences"]["profile_languages"] = _clean_tag_list(
        settings.get("languages"),
        limit=20,
    )
    contract["filter_preferences"]["language_preferences"]["max_german_level"] = (
        _clean_text(settings.get("max_german_level") or "any") or "any"
    )
    contract["filter_preferences"]["language_preferences"]["allow_french"] = int(
        settings.get("french_special_char_threshold") or 0
    ) != 0
    contract["filter_preferences"]["language_preferences"]["allow_spanish"] = int(
        settings.get("spanish_special_char_threshold") or 0
    ) != 0

    contract["document_preferences"]["cv_generation_mode"] = normalize_cv_generation_mode(
        settings.get("cv_generation_mode")
    )
    contract["document_preferences"]["cv_template"] = _clean_text(settings.get("cv_template"))
    contract["document_preferences"]["cv_color_scheme"] = _clean_text(settings.get("cv_color_scheme"))
    contract["document_preferences"]["cv_font"] = _clean_text(settings.get("cv_font"))
    if "include_photo" in settings:
        contract["document_preferences"]["include_photo"] = _clean_bool(settings.get("include_photo"), default=True)

    contract["prompt_preferences"]["stage_overrides"] = _normalize_prompt_overrides(settings)

    technical_runtime: dict[str, Any] = {}
    legacy_passthrough: dict[str, Any] = {}
    for key, value in settings.items():
        if key in WORKSPACE_HIDDEN_FIELD_IDS and value not in (None, "", [], {}):
            technical_runtime[key] = value
        elif key in WORKSPACE_DEPRECATED_FIELD_IDS and value not in (None, "", [], {}):
            legacy_passthrough[key] = value
    contract["technical_runtime"] = technical_runtime
    contract["legacy_passthrough"] = legacy_passthrough
    return contract


def build_workspace_configuration_v2_contract() -> dict[str, Any]:
    return {
        "schema_id": WORKSPACE_CONFIGURATION_V2_SCHEMA,
        "version": PHASE0_CONTRACT_VERSION,
        "default": default_workspace_configuration_v2(),
        "targeting_method": WORKSPACE_TARGETING_METHOD,
        "user_facing_field_ids": list(WORKSPACE_USER_FACING_FIELD_IDS),
        "hidden_field_ids": list(WORKSPACE_HIDDEN_FIELD_IDS),
        "deprecated_field_ids": list(WORKSPACE_DEPRECATED_FIELD_IDS),
    }


def default_candidate_asset_descriptor() -> dict[str, Any]:
    return {
        "schema_version": CANDIDATE_ASSET_DESCRIPTOR_SCHEMA,
        "asset_id": "",
        "asset_kind": "uploaded_document",
        "display_name": "",
        "workspace_binding": {
            "workspace_id": "",
            "role": "supporting_document",
            "is_workspace_default": False,
        },
        "source": {
            "origin": "upload",
            "run_id": "",
            "artifact_id": "",
        },
        "file": {
            "path": "",
            "download_url": "",
            "mime_type": "",
            "extension": "",
        },
        "metadata": {
            "job_id": "",
            "created_at": "",
            "tags": [],
            "parsed_profile": {},
            "profile_extraction": {
                "provider": "",
                "model": "",
                "warnings": [],
                "extracted_at": "",
            },
        },
    }


def normalize_candidate_asset_descriptor(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    contract = deepcopy(default_candidate_asset_descriptor())
    contract["asset_id"] = _clean_text(raw.get("asset_id") or raw.get("artifact_id"))
    contract["asset_kind"] = _clean_text(raw.get("asset_kind") or raw.get("artifact_type") or "uploaded_document")
    contract["display_name"] = _clean_text(raw.get("display_name") or raw.get("file_name"))
    contract["workspace_binding"]["workspace_id"] = _clean_text(raw.get("workspace_id"))
    contract["workspace_binding"]["role"] = _clean_text(raw.get("role") or raw.get("asset_role") or "supporting_document")
    contract["workspace_binding"]["is_workspace_default"] = _clean_bool(
        raw.get("is_workspace_default"),
        default=False,
    )
    contract["source"]["origin"] = _clean_text(raw.get("origin") or raw.get("source_origin") or "upload")
    contract["source"]["run_id"] = _clean_text(raw.get("run_id"))
    contract["source"]["artifact_id"] = _clean_text(raw.get("artifact_id"))
    contract["file"]["path"] = _clean_text(raw.get("path"))
    contract["file"]["download_url"] = _clean_text(raw.get("download_url"))
    contract["file"]["mime_type"] = _clean_text(raw.get("mime_type") or raw.get("content_type"))
    contract["file"]["extension"] = _clean_text(raw.get("extension") or raw.get("file_extension"))
    metadata = dict(raw.get("metadata") or {})
    contract["metadata"]["job_id"] = _clean_text(raw.get("job_id") or metadata.get("job_id"))
    contract["metadata"]["created_at"] = _clean_text(raw.get("created_at") or metadata.get("created_at"))
    contract["metadata"]["tags"] = _clean_tag_list(raw.get("tags") or metadata.get("tags"), limit=20)
    parsed_profile = metadata.get("parsed_profile")
    contract["metadata"]["parsed_profile"] = dict(parsed_profile) if isinstance(parsed_profile, Mapping) else {}
    extraction = metadata.get("profile_extraction")
    extraction_dict = dict(extraction) if isinstance(extraction, Mapping) else {}
    contract["metadata"]["profile_extraction"] = {
        "provider": _clean_text(extraction_dict.get("provider")),
        "model": _clean_text(extraction_dict.get("model")),
        "warnings": _clean_tag_list(extraction_dict.get("warnings"), limit=20),
        "extracted_at": _clean_text(extraction_dict.get("extracted_at")),
    }
    return contract


def build_candidate_asset_contract() -> dict[str, Any]:
    return {
        "schema_id": CANDIDATE_ASSET_DESCRIPTOR_SCHEMA,
        "version": PHASE0_CONTRACT_VERSION,
        "default": default_candidate_asset_descriptor(),
        "asset_kinds": [
            "workspace_cv",
            "generated_cv",
            "cover_letter",
            "certification",
            "recommendation_letter",
            "uploaded_document",
            "bundle_export",
        ],
    }


def _infer_rejected_job_reason_code(payload: Mapping[str, Any]) -> str:
    explicit = _clean_text(payload.get("reason_code"))
    allowed_codes = {item["code"] for item in REJECTED_JOB_REASON_DEFINITIONS}
    if explicit in allowed_codes:
        return explicit
    searchable = " ".join(
        [
            _clean_text(payload.get("filter_status")),
            _clean_text(payload.get("notes")),
            _clean_text(payload.get("reason_summary")),
            _clean_text(payload.get("decision")),
            _clean_text(payload.get("status")),
        ]
    ).casefold()
    if "keyword" in searchable or "title" in searchable:
        return "keyword_mismatch"
    if "senior" in searchable or "director" in searchable or "seniority" in searchable:
        return "seniority_mismatch"
    if "language" in searchable or "french" in searchable or "spanish" in searchable or "german" in searchable:
        return "language_mismatch"
    if "country" in searchable or "location" in searchable or "geo" in searchable:
        return "location_mismatch"
    if "duplicate" in searchable or "tracker" in searchable:
        return "duplicate"
    if "scrape" in searchable or "validation" in searchable or "listing" in searchable:
        return "source_validation_failed"
    if "manual" in searchable or "reviewer" in searchable:
        return "manual_rejection"
    return "unknown"


def default_rejected_job_review_contract() -> dict[str, Any]:
    return {
        "schema_version": REJECTED_JOB_REVIEW_SCHEMA,
        "job_id": "",
        "run_id": "",
        "workspace_id": "",
        "review_status": "rejected",
        "rejection": {
            "reason_code": "unknown",
            "reason_summary": "",
            "details": [],
            "source_stage": "",
            "recorded_at": "",
        },
        "override": {
            "state": "not_requested",
            "requested_at": "",
            "requested_by": "",
            "notes": "",
            "requeue_supported": True,
        },
        "links": {
            "job_posting": "",
            "workspace_editor": "",
        },
        "metadata": {},
    }


def normalize_rejected_job_review(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    contract = deepcopy(default_rejected_job_review_contract())
    contract["job_id"] = _clean_text(raw.get("job_id"))
    contract["run_id"] = _clean_text(raw.get("run_id"))
    contract["workspace_id"] = _clean_text(raw.get("workspace_id"))
    contract["review_status"] = _clean_text(raw.get("review_status") or raw.get("status") or "rejected")
    contract["rejection"]["reason_code"] = _infer_rejected_job_reason_code(raw)
    contract["rejection"]["reason_summary"] = _clean_text(raw.get("reason_summary") or raw.get("notes"))
    contract["rejection"]["details"] = _clean_tag_list(raw.get("details"), limit=20)
    contract["rejection"]["source_stage"] = _clean_text(raw.get("source_stage") or raw.get("filter_status"))
    contract["rejection"]["recorded_at"] = _clean_text(raw.get("recorded_at") or raw.get("updated_at"))
    contract["override"]["state"] = _clean_text(raw.get("override_state") or "not_requested")
    contract["override"]["requested_at"] = _clean_text(raw.get("override_requested_at"))
    contract["override"]["requested_by"] = _clean_text(raw.get("override_requested_by"))
    contract["override"]["notes"] = _clean_text(raw.get("override_notes"))
    if "requeue_supported" in raw:
        contract["override"]["requeue_supported"] = _clean_bool(raw.get("requeue_supported"), default=True)
    contract["links"]["job_posting"] = _clean_text(raw.get("apply_link") or raw.get("job_posting"))
    contract["links"]["workspace_editor"] = _clean_text(raw.get("workspace_editor"))
    contract["metadata"] = dict(raw.get("metadata") or {})
    return contract


def build_rejected_job_review_contract() -> dict[str, Any]:
    return {
        "schema_id": REJECTED_JOB_REVIEW_SCHEMA,
        "version": PHASE0_CONTRACT_VERSION,
        "default": default_rejected_job_review_contract(),
        "reason_definitions": list(REJECTED_JOB_REASON_DEFINITIONS),
    }


def default_mail_connection_contract() -> dict[str, Any]:
    return {
        "schema_version": MAIL_CONNECTION_CONTRACT_SCHEMA,
        "provider": "gmail",
        "auth_strategy": "google_oauth",
        "connection_status": "disconnected",
        "authorization_state": "not_started",
        "account_email": "",
        "scope_set": list(MAIL_SUPPORTED_SCOPES),
        "token_refs": {
            "access_token_secret_id": "",
            "refresh_token_secret_id": "",
            "legacy_password_secret_id": "",
        },
        "provider_settings": {
            "folder": "INBOX",
            "imap_host": "",
            "imap_port": 993,
        },
        "sync_state": {
            "cursor": "",
            "processed_message_ids": [],
            "max_messages": 40,
            "last_sync_at": "",
            "last_error": "",
            "last_sync_summary": {},
        },
        "connection_timestamps": {
            "connected_at": "",
            "updated_at": "",
        },
    }


def normalize_mail_connection_contract(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    contract = deepcopy(default_mail_connection_contract())
    has_oauth_tokens = bool(
        _clean_text(raw.get("access_token_secret_id")) or _clean_text(raw.get("refresh_token_secret_id"))
    )
    has_legacy_password = bool(_clean_text(raw.get("password_secret_id")))
    auth_strategy = _clean_text(raw.get("auth_strategy"))
    if auth_strategy not in MAIL_CONNECTION_AUTH_STRATEGIES:
        auth_strategy = "google_oauth" if has_oauth_tokens or not has_legacy_password else "legacy_imap_password"
    contract["provider"] = _clean_text(raw.get("provider") or raw.get("provider_id") or "gmail") or "gmail"
    contract["auth_strategy"] = auth_strategy
    contract["authorization_state"] = _clean_text(raw.get("authorization_state") or "not_started") or "not_started"
    contract["account_email"] = _clean_text(raw.get("account_email") or raw.get("email_address"))
    contract["token_refs"]["access_token_secret_id"] = _clean_text(raw.get("access_token_secret_id"))
    contract["token_refs"]["refresh_token_secret_id"] = _clean_text(raw.get("refresh_token_secret_id"))
    contract["token_refs"]["legacy_password_secret_id"] = _clean_text(raw.get("password_secret_id"))
    contract["provider_settings"]["folder"] = _clean_text(raw.get("folder") or "INBOX") or "INBOX"
    contract["provider_settings"]["imap_host"] = _clean_text(raw.get("imap_host"))
    try:
        contract["provider_settings"]["imap_port"] = int(raw.get("imap_port") or 993)
    except (TypeError, ValueError):
        contract["provider_settings"]["imap_port"] = 993
    contract["sync_state"]["cursor"] = _clean_text(raw.get("cursor") or raw.get("history_id"))
    contract["sync_state"]["processed_message_ids"] = _clean_tag_list(
        raw.get("processed_message_ids"),
        limit=250,
    )
    try:
        contract["sync_state"]["max_messages"] = max(1, min(100, int(raw.get("max_messages") or 40)))
    except (TypeError, ValueError):
        contract["sync_state"]["max_messages"] = 40
    contract["sync_state"]["last_sync_at"] = _clean_text(raw.get("last_sync_at"))
    contract["sync_state"]["last_error"] = _clean_text(raw.get("last_error"))
    contract["sync_state"]["last_sync_summary"] = dict(raw.get("last_sync_summary") or {})
    contract["connection_timestamps"]["connected_at"] = _clean_text(raw.get("connected_at"))
    contract["connection_timestamps"]["updated_at"] = _clean_text(raw.get("updated_at"))

    if _clean_text(raw.get("connection_status")) in MAIL_CONNECTION_STATUSES:
        contract["connection_status"] = _clean_text(raw.get("connection_status"))
    elif contract["connection_timestamps"]["connected_at"] and (has_oauth_tokens or has_legacy_password):
        contract["connection_status"] = "connected"
    elif contract["authorization_state"] in {"authorization_url_created", "authorized"} and not has_oauth_tokens:
        contract["connection_status"] = "pending_authorization"
    elif contract["sync_state"]["last_error"]:
        contract["connection_status"] = "attention_required"
    else:
        contract["connection_status"] = "disconnected"
    return contract


def build_mail_connection_contract() -> dict[str, Any]:
    return {
        "schema_id": MAIL_CONNECTION_CONTRACT_SCHEMA,
        "version": PHASE0_CONTRACT_VERSION,
        "default": default_mail_connection_contract(),
        "auth_strategies": list(MAIL_CONNECTION_AUTH_STRATEGIES),
        "statuses": list(MAIL_CONNECTION_STATUSES),
        "authorization_states": list(MAIL_AUTHORIZATION_STATES),
        "default_scopes": list(MAIL_SUPPORTED_SCOPES),
    }


def default_tracker_application_contract() -> dict[str, Any]:
    return {
        "schema_version": TRACKER_APPLICATION_SCHEMA,
        "application_id": "",
        "review_id": "",
        "run_id": "",
        "workspace_id": "",
        "job": {
            "job_id": "",
            "title": "",
            "company": "",
            "location": "",
            "apply_link": "",
            "linkedin_link": "",
            "full_description": "",
        },
        "status": {
            "application_status": "Unknown",
            "legacy_tracker_status": "",
            "email_confirmed": False,
            "source": "manual",
            "confidence": "",
            "suggested_application_status": "",
        },
        "dates": {
            "application_date": "",
            "rejected_at": "",
            "updated_at": "",
        },
        "notes": "",
        "documents": [],
        "metadata": {},
    }


def normalize_tracker_application(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    metadata = dict(raw.get("metadata") or {})
    contract = deepcopy(default_tracker_application_contract())
    review_id = _clean_text(raw.get("review_id"))
    job_id = _clean_text(raw.get("job_id"))
    legacy_status = _clean_text(
        raw.get("tracker_status")
        or raw.get("legacy_tracker_status")
        or metadata.get("tracker_status")
        or raw.get("applied?")
    )
    application_status = normalize_application_status(
        raw.get("application_status")
        or raw.get("status")
        or legacy_status,
        default="Not applied" if legacy_status in {"", "not_applied"} else "Unknown",
    )
    contract["application_id"] = _clean_text(raw.get("application_id") or review_id or job_id)
    contract["review_id"] = review_id
    contract["run_id"] = _clean_text(raw.get("run_id"))
    contract["workspace_id"] = _clean_text(raw.get("workspace_id"))
    contract["job"]["job_id"] = job_id
    contract["job"]["title"] = _clean_text(raw.get("title"))
    contract["job"]["company"] = _clean_text(raw.get("company"))
    contract["job"]["location"] = _clean_text(raw.get("location") or raw.get("location_raw"))
    contract["job"]["apply_link"] = _clean_text(raw.get("apply_link") or raw.get("link"))
    contract["job"]["linkedin_link"] = _clean_text(raw.get("linkedin_link"))
    contract["job"]["full_description"] = _clean_text(raw.get("full_description") or raw.get("description"))
    contract["status"]["application_status"] = application_status
    contract["status"]["legacy_tracker_status"] = legacy_status or legacy_tracker_status_for_application_status(application_status)
    contract["status"]["email_confirmed"] = _clean_bool(
        raw.get("email_confirmed") or metadata.get("email_confirmed"),
        default=False,
    )
    contract["status"]["source"] = _clean_text(raw.get("status_source") or metadata.get("status_source") or "manual") or "manual"
    contract["status"]["confidence"] = _clean_text(raw.get("confidence") or metadata.get("confidence"))
    contract["status"]["suggested_application_status"] = normalize_application_status(
        raw.get("suggested_application_status") or metadata.get("suggested_application_status"),
        default="",
    )
    if contract["status"]["suggested_application_status"] not in APPLICATION_STATUSES:
        contract["status"]["suggested_application_status"] = ""
    contract["dates"]["application_date"] = _clean_text(raw.get("application_date") or raw.get("applied_at"))
    contract["dates"]["rejected_at"] = _clean_text(raw.get("rejected_at") or metadata.get("rejected_at"))
    contract["dates"]["updated_at"] = _clean_text(raw.get("updated_at"))
    contract["notes"] = _clean_text(raw.get("notes") or raw.get("rejection_note") or metadata.get("rejection_note"))
    contract["documents"] = [dict(item) for item in _clean_list(raw.get("documents")) if isinstance(item, Mapping)]
    contract["metadata"] = metadata
    return contract


def build_tracker_application_contract() -> dict[str, Any]:
    return {
        "schema_id": TRACKER_APPLICATION_SCHEMA,
        "version": PHASE0_CONTRACT_VERSION,
        "default": default_tracker_application_contract(),
        "application_statuses": list(APPLICATION_STATUSES),
        "legacy_status_mapping": dict(LEGACY_TRACKER_STATUS_TO_APPLICATION_STATUS),
    }


def default_gmail_application_detection_contract() -> dict[str, Any]:
    return {
        "schema_version": GMAIL_APPLICATION_DETECTION_SCHEMA,
        "detection_id": "",
        "scan_window": "last_1_month",
        "source_email": {
            "message_id": "",
            "subject": "",
            "from_address": "",
            "sent_at": "",
        },
        "detected_application": {
            "company": "",
            "title": "",
            "application_date": "",
            "source_url": "",
        },
        "status": {
            "suggested_application_status": "Unknown",
            "confidence": "low",
            "approval_state": "pending_review",
            "evidence": [],
        },
        "metadata": {},
    }


def normalize_gmail_application_detection(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    contract = deepcopy(default_gmail_application_detection_contract())
    source_email = dict(raw.get("source_email") or {})
    detected_application = dict(raw.get("detected_application") or {})
    raw_status = raw.get("status")
    status = dict(raw_status) if isinstance(raw_status, Mapping) else {}
    contract["detection_id"] = _clean_text(raw.get("detection_id"))
    contract["scan_window"] = normalize_gmail_scan_window(raw.get("scan_window"))
    contract["source_email"]["message_id"] = _clean_text(raw.get("message_id") or source_email.get("message_id"))
    contract["source_email"]["subject"] = _clean_text(raw.get("subject") or source_email.get("subject"))
    contract["source_email"]["from_address"] = _clean_text(raw.get("from_address") or source_email.get("from_address"))
    contract["source_email"]["sent_at"] = _clean_text(raw.get("sent_at") or source_email.get("sent_at"))
    contract["detected_application"]["company"] = _clean_text(raw.get("company") or detected_application.get("company"))
    contract["detected_application"]["title"] = _clean_text(raw.get("title") or detected_application.get("title"))
    contract["detected_application"]["application_date"] = _clean_text(
        raw.get("application_date") or detected_application.get("application_date")
    )
    contract["detected_application"]["source_url"] = _clean_text(
        raw.get("source_url") or raw.get("apply_link") or detected_application.get("source_url")
    )
    contract["status"]["suggested_application_status"] = normalize_application_status(
        raw.get("suggested_application_status")
        or raw.get("tracker_status")
        or status.get("suggested_application_status")
        or status.get("application_status")
        or raw.get("status"),
    )
    confidence = _casefold_key(raw.get("confidence") or status.get("confidence") or "low")
    contract["status"]["confidence"] = confidence if confidence in GMAIL_DETECTION_CONFIDENCE_LEVELS else "low"
    approval_state = _casefold_key(raw.get("approval_state") or status.get("approval_state") or "pending_review")
    contract["status"]["approval_state"] = (
        approval_state if approval_state in GMAIL_DETECTION_APPROVAL_STATES else "pending_review"
    )
    contract["status"]["evidence"] = _clean_tag_list(raw.get("evidence") or status.get("evidence"), limit=20)
    contract["metadata"] = dict(raw.get("metadata") or {})
    return contract


def build_gmail_application_detection_contract() -> dict[str, Any]:
    return {
        "schema_id": GMAIL_APPLICATION_DETECTION_SCHEMA,
        "version": PHASE0_CONTRACT_VERSION,
        "default": default_gmail_application_detection_contract(),
        "scan_windows": list(GMAIL_SCAN_WINDOWS),
        "confidence_levels": list(GMAIL_DETECTION_CONFIDENCE_LEVELS),
        "approval_states": list(GMAIL_DETECTION_APPROVAL_STATES),
        "application_statuses": list(APPLICATION_STATUSES),
    }


def default_application_document_contract() -> dict[str, Any]:
    return {
        "schema_version": APPLICATION_DOCUMENT_SCHEMA,
        "document_id": "",
        "document_name": "",
        "document_type": "Other",
        "related_application": {
            "application_id": "",
            "job_id": "",
            "company": "",
            "title": "",
        },
        "file": {
            "path": "",
            "download_url": "",
            "content_type": "",
        },
        "status": "ready",
        "created_at": "",
        "metadata": {},
    }


def normalize_application_document(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    metadata = dict(raw.get("metadata") or {})
    contract = deepcopy(default_application_document_contract())
    document_type = _clean_text(raw.get("document_type") or raw.get("type") or raw.get("asset_kind") or "Other")
    matching_type = next(
        (item for item in APPLICATION_DOCUMENT_TYPES if item.casefold() == document_type.casefold()),
        "Other",
    )
    contract["document_id"] = _clean_text(raw.get("document_id") or raw.get("artifact_id") or raw.get("asset_id"))
    contract["document_name"] = _clean_text(raw.get("document_name") or raw.get("file_name") or raw.get("display_name"))
    contract["document_type"] = matching_type
    contract["related_application"]["application_id"] = _clean_text(raw.get("application_id") or metadata.get("application_id"))
    contract["related_application"]["job_id"] = _clean_text(raw.get("job_id") or metadata.get("job_id"))
    contract["related_application"]["company"] = _clean_text(raw.get("company") or metadata.get("company"))
    contract["related_application"]["title"] = _clean_text(raw.get("title") or raw.get("job_title") or metadata.get("job_title"))
    contract["file"]["path"] = _clean_text(raw.get("path"))
    contract["file"]["download_url"] = _clean_text(raw.get("download_url"))
    contract["file"]["content_type"] = _clean_text(raw.get("content_type") or raw.get("mime_type"))
    contract["status"] = _clean_text(raw.get("status") or metadata.get("status") or "ready") or "ready"
    contract["created_at"] = _clean_text(raw.get("created_at") or metadata.get("created_at"))
    contract["metadata"] = metadata
    return contract


def build_application_document_contract() -> dict[str, Any]:
    return {
        "schema_id": APPLICATION_DOCUMENT_SCHEMA,
        "version": PHASE0_CONTRACT_VERSION,
        "default": default_application_document_contract(),
        "document_types": list(APPLICATION_DOCUMENT_TYPES),
    }


def default_ats_export_gate_contract() -> dict[str, Any]:
    return {
        "schema_version": ATS_EXPORT_GATE_SCHEMA,
        "target_score": 90,
        "best_score": 0,
        "attempt_count": 0,
        "max_attempts": 3,
        "gate_state": "not_started",
        "can_export_final": False,
        "export_anyway_allowed": False,
        "missing_requirements": [],
        "last_warning": "",
        "metadata": {},
    }


def normalize_ats_export_gate(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    contract = deepcopy(default_ats_export_gate_contract())
    try:
        contract["target_score"] = max(0, min(100, int(raw.get("target_score") or 90)))
    except (TypeError, ValueError):
        contract["target_score"] = 90
    try:
        contract["best_score"] = max(0, min(100, int(raw.get("best_score") or raw.get("score") or 0)))
    except (TypeError, ValueError):
        contract["best_score"] = 0
    try:
        contract["attempt_count"] = max(0, int(raw.get("attempt_count") or 0))
    except (TypeError, ValueError):
        contract["attempt_count"] = 0
    try:
        contract["max_attempts"] = max(1, int(raw.get("max_attempts") or 3))
    except (TypeError, ValueError):
        contract["max_attempts"] = 3
    gate_state = _casefold_key(raw.get("gate_state") or raw.get("state") or "not_started")
    contract["gate_state"] = gate_state if gate_state in ATS_GATE_STATES else "not_started"
    contract["can_export_final"] = _clean_bool(
        raw.get("can_export_final"),
        default=contract["best_score"] >= contract["target_score"],
    )
    contract["export_anyway_allowed"] = _clean_bool(
        raw.get("export_anyway_allowed"),
        default=contract["attempt_count"] >= contract["max_attempts"],
    )
    contract["missing_requirements"] = _clean_tag_list(raw.get("missing_requirements"), limit=50)
    contract["last_warning"] = _clean_text(raw.get("last_warning"))
    contract["metadata"] = dict(raw.get("metadata") or {})
    return contract


def build_ats_export_gate_contract() -> dict[str, Any]:
    return {
        "schema_id": ATS_EXPORT_GATE_SCHEMA,
        "version": PHASE0_CONTRACT_VERSION,
        "default": default_ats_export_gate_contract(),
        "gate_states": list(ATS_GATE_STATES),
        "default_target_score": 90,
        "default_max_attempts": 3,
    }


def default_referral_relationship_contract() -> dict[str, Any]:
    return {
        "schema_version": REFERRAL_RELATIONSHIP_SCHEMA,
        "person_id": "",
        "person": {
            "full_name": "",
            "linkedin_url": "",
            "notes": "",
        },
        "companies": [],
        "source": {
            "kind": "manual",
            "import_batch_id": "",
            "import_ref": "",
            "created_at": "",
            "updated_at": "",
        },
        "lifecycle": {
            "status": "active",
            "is_active": True,
            "inactive_at": "",
            "inactive_reason": "",
        },
        "matching": {
            "company_aliases": [],
        },
        "outreach": {
            "default_status": "Not contacted",
        },
        "metadata": {},
    }


def normalize_referral_relationship(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    contract = deepcopy(default_referral_relationship_contract())
    contract["person_id"] = _clean_text(raw.get("person_id") or raw.get("contact_id"))
    contract["person"]["full_name"] = _clean_text(raw.get("full_name") or raw.get("name"))
    contract["person"]["linkedin_url"] = _clean_text(raw.get("linkedin_url"))
    contract["person"]["notes"] = _clean_text(raw.get("notes") or raw.get("relationship_note"))

    companies_payload = raw.get("companies")
    companies: list[dict[str, Any]] = []
    if companies_payload:
        for item in _clean_list(companies_payload):
            if not isinstance(item, Mapping):
                continue
            company_name = _clean_text(item.get("company_name") or item.get("company"))
            if not company_name:
                continue
            companies.append(
                {
                    "company_name": company_name,
                    "company_domain": _clean_text(item.get("company_domain")),
                    "role_title": _clean_text(item.get("role_title")),
                    "employment_status": _clean_text(item.get("employment_status") or "unknown") or "unknown",
                    "can_refer": _clean_bool(item.get("can_refer"), default=False),
                }
            )
    else:
        company_name = _clean_text(raw.get("company"))
        if company_name:
            companies.append(
                {
                    "company_name": company_name,
                    "company_domain": "",
                    "role_title": "",
                    "employment_status": "unknown",
                    "can_refer": _clean_bool(raw.get("can_refer"), default=False),
                }
            )
    contract["companies"] = companies
    contract["source"]["kind"] = _clean_text(raw.get("source_kind") or raw.get("import_source") or "manual") or "manual"
    contract["source"]["import_batch_id"] = _clean_text(raw.get("import_batch_id"))
    contract["source"]["import_ref"] = _clean_text(raw.get("import_ref"))
    contract["source"]["created_at"] = _clean_text(raw.get("created_at"))
    contract["source"]["updated_at"] = _clean_text(raw.get("updated_at"))
    is_active = _clean_bool(raw.get("is_active", raw.get("active", True)), default=True)
    lifecycle_payload = raw.get("lifecycle") if isinstance(raw.get("lifecycle"), Mapping) else {}
    if lifecycle_payload:
        is_active = _clean_bool(lifecycle_payload.get("is_active"), default=is_active)
    lifecycle_status = _clean_text(
        (lifecycle_payload or {}).get("status")
        or raw.get("lifecycle_status")
        or ("active" if is_active else "inactive")
    ).casefold()
    if lifecycle_status not in REFERRAL_CONTACT_LIFECYCLE_STATUSES:
        lifecycle_status = "active" if is_active else "inactive"
    contract["lifecycle"]["status"] = lifecycle_status
    contract["lifecycle"]["is_active"] = lifecycle_status == "active" and is_active
    contract["lifecycle"]["inactive_at"] = _clean_text(
        (lifecycle_payload or {}).get("inactive_at") or raw.get("inactive_at")
    )
    contract["lifecycle"]["inactive_reason"] = _clean_text(
        (lifecycle_payload or {}).get("inactive_reason") or raw.get("inactive_reason")
    )

    aliases = _clean_tag_list(raw.get("company_aliases"), limit=50)
    if not aliases:
        aliases = [item["company_name"] for item in companies if _clean_text(item.get("company_name"))]
    contract["matching"]["company_aliases"] = aliases
    contract["outreach"]["default_status"] = normalize_referral_outreach_status(raw.get("outreach_status"))
    contract["metadata"] = dict(raw.get("metadata") or {})
    return contract


def build_referral_relationship_contract() -> dict[str, Any]:
    return {
        "schema_id": REFERRAL_RELATIONSHIP_SCHEMA,
        "version": PHASE0_CONTRACT_VERSION,
        "default": default_referral_relationship_contract(),
        "source_kinds": list(REFERRAL_SOURCE_KINDS),
        "lifecycle_statuses": list(REFERRAL_CONTACT_LIFECYCLE_STATUSES),
        "outreach_statuses": list(REFERRAL_OUTREACH_STATUSES),
    }


def phase0_contract_catalog() -> dict[str, Any]:
    return {
        "version": PHASE0_CONTRACT_VERSION,
        "workspace_configuration_v2": build_workspace_configuration_v2_contract(),
        "candidate_asset_descriptor": build_candidate_asset_contract(),
        "rejected_job_review": build_rejected_job_review_contract(),
        "mail_connection": build_mail_connection_contract(),
        "referral_relationship": build_referral_relationship_contract(),
        "tracker_application": build_tracker_application_contract(),
        "gmail_application_detection": build_gmail_application_detection_contract(),
        "application_document": build_application_document_contract(),
        "ats_export_gate": build_ats_export_gate_contract(),
    }


__all__ = [
    "CANDIDATE_ASSET_DESCRIPTOR_SCHEMA",
    "APPLICATION_DOCUMENT_SCHEMA",
    "APPLICATION_STATUSES",
    "ATS_EXPORT_GATE_SCHEMA",
    "GMAIL_APPLICATION_DETECTION_SCHEMA",
    "JOB_FILTERING_MODE_BROADER",
    "JOB_FILTERING_MODES",
    "JOB_FILTERING_MODE_STRICT",
    "MAIL_CONNECTION_CONTRACT_SCHEMA",
    "PHASE0_CONTRACT_VERSION",
    "REFERRAL_RELATIONSHIP_SCHEMA",
    "REJECTED_JOB_REVIEW_SCHEMA",
    "TRACKER_APPLICATION_SCHEMA",
    "WORKSPACE_CONFIGURATION_V2_SCHEMA",
    "build_application_document_contract",
    "build_ats_export_gate_contract",
    "build_candidate_asset_contract",
    "build_gmail_application_detection_contract",
    "build_mail_connection_contract",
    "build_referral_relationship_contract",
    "build_rejected_job_review_contract",
    "build_tracker_application_contract",
    "build_workspace_configuration_v2_contract",
    "default_application_document_contract",
    "default_ats_export_gate_contract",
    "default_candidate_asset_descriptor",
    "default_gmail_application_detection_contract",
    "default_mail_connection_contract",
    "default_referral_relationship_contract",
    "default_rejected_job_review_contract",
    "default_tracker_application_contract",
    "default_workspace_configuration_v2",
    "derive_job_filtering_target_phrases",
    "legacy_tracker_status_for_application_status",
    "normalize_application_document",
    "normalize_application_status",
    "normalize_ats_export_gate",
    "normalize_candidate_asset_descriptor",
    "normalize_gmail_application_detection",
    "normalize_job_filtering_mode",
    "normalize_mail_connection_contract",
    "normalize_referral_outreach_status",
    "normalize_referral_relationship",
    "normalize_rejected_job_review",
    "normalize_tracker_application",
    "normalize_workspace_configuration_v2",
    "phase0_contract_catalog",
]
