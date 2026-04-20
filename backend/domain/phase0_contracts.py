from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


PHASE0_CONTRACT_VERSION = "2026-04-20"

WORKSPACE_CONFIGURATION_V2_SCHEMA = "workspace_configuration_v2"
CANDIDATE_ASSET_DESCRIPTOR_SCHEMA = "candidate_asset_descriptor_v1"
REJECTED_JOB_REVIEW_SCHEMA = "rejected_job_review_v1"
MAIL_CONNECTION_CONTRACT_SCHEMA = "mail_connection_contract_v1"
REFERRAL_RELATIONSHIP_SCHEMA = "referral_relationship_v1"

WORKSPACE_TARGETING_METHOD = "keyword_profile_aligned"
WORKSPACE_KEYWORD_LIMIT = 12

WORKSPACE_USER_FACING_FIELD_IDS = [
    "keywords",
    "country_codes",
    "time_posted_seconds",
    "experience_levels",
    "manual_url_seed_list",
    "company_career_sites",
    "forbidden_title_keywords",
    "max_german_level",
    "languages",
    "cv_template",
    "cv_color_scheme",
    "cv_font",
    "include_photo",
]

WORKSPACE_HIDDEN_FIELD_IDS = [
    "linkedin_max_pages",
    "max_enrich_jobs",
    "ai_batch_size",
    "reuse_scrape_snapshot",
    "page_fetch_sleep_seconds",
    "use_proxy_fallback",
    "manual_request_timeout_seconds",
    "company_site_max_jobs_per_site",
    "company_site_request_timeout_seconds",
    "stage4_max_jobs",
    "dedupe_against_tracker",
    "stage1_model",
    "stage1_prompt_override",
    "stage4_model",
    "stage4_fallback_model",
    "stage4_prompt_override",
    "stage4_sleep_seconds",
    "stage4_retries",
    "stage4_retry_sleep",
    "force_regenerate",
    "tracker_sheet_name",
    "tracker_expert_mode",
    "profile_default",
]

WORKSPACE_DEPRECATED_FIELD_IDS = [
    "target_roles",
    "geo_id",
    "linkedin_geo_id",
    "candidate_name",
    "candidate_email",
]

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
    "linkedin_csv_import",
    "enriched",
]

DEFAULT_MULTI_PORTAL_IDS = [
    "indeed",
    "glassdoor",
]


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


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
    prompt_pairs = [
        ("stage1", "append", _clean_text(settings.get("stage1_extra_prompt"))),
        ("stage1", "replace", _clean_text(settings.get("stage1_prompt_override"))),
        ("stage4", "append", _clean_text(settings.get("stage4_extra_prompt"))),
        ("stage4", "replace", _clean_text(settings.get("stage4_prompt_override"))),
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


def _normalize_source_ids(payload: Mapping[str, Any], settings: Mapping[str, Any]) -> set[str]:
    source_ids = {
        _clean_text(item)
        for item in payload.get("source_ids")
        or payload.get("selected_source_ids")
        or settings.get("source_ids")
        or []
        if _clean_text(item)
    }
    if settings.get("manual_url_seed_list"):
        source_ids.add("curated_urls")
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
                "validate_before_run": True,
            },
            "curated_urls": {
                "enabled": False,
                "urls": [],
                "validate_before_run": True,
            },
            "company_career_sites": {
                "enabled": False,
                "companies": [],
                "validate_before_run": True,
            },
        },
        "filter_preferences": {
            "forbidden_title_keywords": [],
            "language_preferences": {
                "profile_languages": [],
                "max_german_level": "any",
                "allow_french": True,
                "allow_spanish": True,
            },
        },
        "document_preferences": {
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
    configured_portals = _clean_tag_list(settings.get("portal_ids"), limit=10, lower=True)
    if configured_portals:
        contract["source_configuration"]["multi_portal"]["portals"] = configured_portals

    contract["source_configuration"]["curated_urls"]["enabled"] = "curated_urls" in source_ids
    contract["source_configuration"]["curated_urls"]["urls"] = _clean_tag_list(
        settings.get("manual_url_seed_list"),
        limit=250,
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
        "matching": {
            "company_aliases": [],
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

    aliases = _clean_tag_list(raw.get("company_aliases"), limit=50)
    if not aliases:
        aliases = [item["company_name"] for item in companies if _clean_text(item.get("company_name"))]
    contract["matching"]["company_aliases"] = aliases
    contract["metadata"] = dict(raw.get("metadata") or {})
    return contract


def build_referral_relationship_contract() -> dict[str, Any]:
    return {
        "schema_id": REFERRAL_RELATIONSHIP_SCHEMA,
        "version": PHASE0_CONTRACT_VERSION,
        "default": default_referral_relationship_contract(),
        "source_kinds": list(REFERRAL_SOURCE_KINDS),
    }


def phase0_contract_catalog() -> dict[str, Any]:
    return {
        "version": PHASE0_CONTRACT_VERSION,
        "workspace_configuration_v2": build_workspace_configuration_v2_contract(),
        "candidate_asset_descriptor": build_candidate_asset_contract(),
        "rejected_job_review": build_rejected_job_review_contract(),
        "mail_connection": build_mail_connection_contract(),
        "referral_relationship": build_referral_relationship_contract(),
    }


__all__ = [
    "CANDIDATE_ASSET_DESCRIPTOR_SCHEMA",
    "MAIL_CONNECTION_CONTRACT_SCHEMA",
    "PHASE0_CONTRACT_VERSION",
    "REFERRAL_RELATIONSHIP_SCHEMA",
    "REJECTED_JOB_REVIEW_SCHEMA",
    "WORKSPACE_CONFIGURATION_V2_SCHEMA",
    "build_candidate_asset_contract",
    "build_mail_connection_contract",
    "build_referral_relationship_contract",
    "build_rejected_job_review_contract",
    "build_workspace_configuration_v2_contract",
    "default_candidate_asset_descriptor",
    "default_mail_connection_contract",
    "default_referral_relationship_contract",
    "default_rejected_job_review_contract",
    "default_workspace_configuration_v2",
    "normalize_candidate_asset_descriptor",
    "normalize_mail_connection_contract",
    "normalize_referral_relationship",
    "normalize_rejected_job_review",
    "normalize_workspace_configuration_v2",
    "phase0_contract_catalog",
]
