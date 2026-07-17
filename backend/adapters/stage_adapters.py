from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4


from backend.capabilities.reusable_packages.acquisition import build_stage1_args as build_reusable_stage1_args
from backend.capabilities.reusable_packages.acquisition import run_stage1_pipeline as run_reusable_stage1_pipeline
from backend.capabilities.reusable_packages.classification import build_stage3_args as build_reusable_stage3_args
from backend.capabilities.reusable_packages.classification import run_stage3_pipeline as run_reusable_stage3_pipeline
from backend.capabilities.reusable_packages.filtering import build_stage2_args as build_reusable_stage2_args
from backend.capabilities.reusable_packages.filtering import run_stage2_pipeline as run_reusable_stage2_pipeline
from backend.capabilities.reusable_packages.packaging import build_stage5_args as build_reusable_stage5_args
from backend.capabilities.reusable_packages.packaging import run_stage5_pipeline as run_reusable_stage5_pipeline
from backend.capabilities.reusable_packages.reusable_profiles import build_stage4_args as build_reusable_stage4_args
from backend.capabilities.reusable_packages.reusable_profiles import run_stage4_pipeline as run_reusable_stage4_pipeline
from backend.capabilities.reusable_packages.support import load_reusable_packages_config
from backend.capabilities.tailored_documents.acquisition import run_stage1_pipeline as run_tailored_stage1_pipeline
from backend.capabilities.tailored_documents.documents import (
    run_standard_cv_pipeline,
    run_stage4_pipeline as run_tailored_stage4_pipeline,
)
from backend.capabilities.tailored_documents.modes import (
    APPLIED_CV_ASSET_KIND,
    CV_GENERATION_MODE_STANDARD,
    normalize_cv_generation_mode,
)
from backend.capabilities.tailored_documents.prioritization import run_stage3_pipeline as run_tailored_stage3_pipeline
from backend.capabilities.tailored_documents.runtime import (
    build_main_defaults,
    build_stage1_args as build_tailored_stage1_args,
    build_stage4_args as build_tailored_stage4_args,
)
from backend.capabilities.tailored_documents.screening import run_stage2_pipeline as run_tailored_stage2_pipeline
from backend.capabilities.tailored_documents.workflow import run_manual_pipeline
from backend.config.plans import DEFAULT_PLAN_ID, get_limit, normalize_plan_id
from backend.connectors.company_career_sites import (
    ACADEMIC_MIN_JOB_LINKS_PER_SITE,
    ACADEMIC_CAREER_SITE_FILES,
    REGULAR_COMPANY_SITE_FILES,
    load_discovered_company_site_entries,
    parse_company_site_entries,
    plan_company_site_scope,
    scrape_company_career_sites,
)
from backend.domain.job_identity import canonicalize_url
from backend.domain.phase0_contracts import derive_job_filtering_target_phrases, normalize_job_filtering_mode
from backend.domain.models import ArtifactRecord, JobRecord, StageContext, StageDefinition, utc_now_iso
from backend.orchestration.engine import BaseStage, StageOutcome
from backend.orchestration.workspace_builder import derive_runtime_defaults_from_settings
from backend.profiles.cv_text import runtime_cv_override
from backend.storage import ObjectMaterializationSession, create_object_storage

TARGET_ROLE_KEYWORD_MAP = {
    "Product Manager": ["product manager", "product owner", "go-to-market"],
    "Business Analyst": ["business analyst", "requirements engineering", "process improvement"],
    "Project Manager": ["project manager", "program manager", "delivery manager"],
    "Consultant": ["consultant", "strategy", "stakeholder management"],
    "Product Designer": ["product designer", "ux designer", "design system"],
    "Frontend Engineer": ["frontend engineer", "react", "javascript", "typescript"],
    "Data Analyst": ["data analyst", "sql", "dashboarding", "insights"],
}
SAFE_COMPANY_SITE_FALLBACK_MAX_SITES_PER_RUN = 10
SAFE_COMPANY_SITE_FALLBACK_RUN_CREDITS = 150
DEFAULT_COMPANY_SITE_MAX_JOB_LINKS_PER_SITE = 25
LOGGER = logging.getLogger(__name__)


def _runtime_limit_int(value: Any, *, default: int = 0, allow_unlimited: bool = False) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return int(default)
    if allow_unlimited and normalized == -1:
        return -1
    return normalized if normalized > 0 else int(default)


def _safe_plan_limit(plan_id: str, limit_type: str, fallback: int) -> int:
    try:
        plan_limit = int(get_limit(normalize_plan_id(plan_id or DEFAULT_PLAN_ID), limit_type))
    except Exception:
        return int(fallback)
    if plan_limit <= 0:
        return int(fallback)
    return min(plan_limit, int(fallback))


def _resolve_company_site_stage_limits(cli_args: Any, *, logger=None) -> dict[str, int]:
    plan_id = str(getattr(cli_args, "run_user_plan_id", "") or DEFAULT_PLAN_ID)
    explicit_site_limit = _runtime_limit_int(
        getattr(cli_args, "company_site_max_sites_per_run", 0),
        default=0,
        allow_unlimited=True,
    )
    explicit_credit_budget = _runtime_limit_int(
        getattr(cli_args, "company_site_runner_credit_budget", 0),
        default=0,
        allow_unlimited=True,
    )
    explicit_link_limit = _runtime_limit_int(getattr(cli_args, "company_site_max_job_links_per_site", 0), default=0)
    deprecated_link_limit = _runtime_limit_int(
        getattr(cli_args, "company_site_emergency_max_job_links_per_site", 0), default=0
    )
    if not explicit_link_limit and deprecated_link_limit:
        (logger or LOGGER).warning(
            "Setting company_site_emergency_max_job_links_per_site is deprecated; "
            "use company_site_max_job_links_per_site instead."
        )
        explicit_link_limit = deprecated_link_limit
    return {
        "max_sites_per_run": explicit_site_limit
        or _safe_plan_limit(plan_id, "company_sites_per_run", SAFE_COMPANY_SITE_FALLBACK_MAX_SITES_PER_RUN),
        "runner_credit_budget": explicit_credit_budget
        or _safe_plan_limit(plan_id, "runner_credits_per_run", SAFE_COMPANY_SITE_FALLBACK_RUN_CREDITS),
        "max_job_links_per_site": explicit_link_limit or DEFAULT_COMPANY_SITE_MAX_JOB_LINKS_PER_SITE,
    }


def _to_job_records(records: list[dict[str, Any]]) -> list[JobRecord]:
    return [JobRecord.from_mapping(record) for record in records]


def _json_artifact(run_id: str, stage_id: str, artifact_type: str, path: str) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=f"{run_id}_{stage_id}_{artifact_type}",
        artifact_type=artifact_type,
        path=path,
    )


def _build_scrapeops_usage_callback(context: StageContext, definition: StageDefinition):
    def _record_usage_event(event: dict[str, Any]) -> None:
        analytics_store = getattr(context.repositories, "analytics_store", None)
        if analytics_store is None or not hasattr(analytics_store, "emit_event"):
            return
        event_id = f"evt_{uuid4().hex[:16]}"
        user_id = str(getattr(context.run, "normalized_user_id", "") or getattr(context.run, "user_id", "") or "")
        workspace_id = str(getattr(context.workspace, "id", "") or "")
        run_id = str(getattr(context.run, "id", "") or "")
        route = f"/runs/{run_id}"
        if hasattr(analytics_store, "record_scrapeops_usage") and event.get("method") == "scrapeops_proxy":
            analytics_store.record_scrapeops_usage(
                ledger_id=event_id,
                payload=event,
                user_id=user_id,
                workspace_id=workspace_id,
                run_id=run_id,
                route=route,
                source="worker",
            )
        analytics_store.emit_event(
            event_id=event_id,
            event_name="scrapeops_request",
            occurred_at=utc_now_iso(),
            user_id=user_id,
            workspace_id=workspace_id,
            run_id=run_id,
            route=route,
            source="worker",
            payload={
                "stage_id": definition.stage_id,
                "stage_type": definition.stage_type,
                **dict(event or {}),
            },
        )

    return _record_usage_event


def _read_json_list_if_exists(path: str) -> list[dict[str, Any]]:
    file_path = Path(path or "").expanduser()
    if not file_path.exists():
        return []
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)]


def _tailored_document_artifact_metadata(record: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "job_id": str(record.get("job_id") or ""),
        "job_title": str(record.get("title") or ""),
        "company": str(record.get("company") or ""),
        "status": "ready" if not record.get("doc_generation_error") else "error",
    }
    for field_name in (
        "cv_generation_mode",
        "document_asset_kind",
        "document_display_name",
        "applied_cv_asset_id",
        "applied_cv_display_name",
    ):
        value = record.get(field_name)
        if value not in (None, "", [], {}):
            metadata[field_name] = value
    propagated_fields = (
        "ats_score",
        "ats_best_score",
        "ats_target_score",
        "ats_attempt_count",
        "ats_max_attempts",
        "ats_missing_requirements",
        "missing_requirements",
        "ats_gate_state",
        "ats_can_export_final",
        "ats_export_anyway_allowed",
        "ats_last_warning",
        "ats_stop_reason",
        "ats_attempt_history",
    )
    for field_name in propagated_fields:
        value = record.get(field_name)
        if value not in (None, "", [], {}):
            metadata[field_name] = value
    if isinstance(record.get("ats_export_gate"), dict):
        metadata["ats_export_gate"] = dict(record["ats_export_gate"])
    return metadata


def _tailored_document_artifacts(
    run_id: str,
    stage_id: str,
    *,
    output_json: str,
    output_xlsx: str,
    records: list[dict[str, Any]],
) -> list[ArtifactRecord]:
    artifacts = [
        _json_artifact(run_id, stage_id, "documents_json", output_json),
        _json_artifact(run_id, stage_id, "documents_xlsx", output_xlsx),
    ]
    for record in records:
        job_id = str(record.get("job_id") or "")
        metadata = _tailored_document_artifact_metadata(record)
        applied_cv_path = str(record.get("applied_cv") or "")
        if applied_cv_path:
            artifacts.append(
                ArtifactRecord(
                    artifact_id=f"{run_id}_{stage_id}_{job_id}_applied_cv",
                    artifact_type=APPLIED_CV_ASSET_KIND,
                    path=applied_cv_path,
                    metadata=metadata,
                )
            )
        cv_pdf_path = str(record.get("cv_pdf") or "")
        if cv_pdf_path:
            artifacts.append(
                ArtifactRecord(
                    artifact_id=f"{run_id}_{stage_id}_{job_id}_cv_pdf",
                    artifact_type="cv_pdf",
                    path=cv_pdf_path,
                    metadata=metadata,
                )
            )
        cv_docx_path = str(record.get("cv_docx") or "")
        if cv_docx_path:
            artifacts.append(
                ArtifactRecord(
                    artifact_id=f"{run_id}_{stage_id}_{job_id}_cv_docx",
                    artifact_type="cv_docx",
                    path=cv_docx_path,
                    metadata=metadata,
                )
            )
    return artifacts


def _namespace_from_defaults(defaults: dict[str, Any], overrides: dict[str, Any]) -> SimpleNamespace:
    merged = dict(defaults)
    merged.update({key: value for key, value in overrides.items() if value is not None})
    return SimpleNamespace(**merged)


def _build_tailored_stage2_args(cli_args: Any) -> SimpleNamespace:
    return SimpleNamespace(
        input=str(getattr(cli_args, "stage1_output", "") or "highly_curated_jobs.json"),
        output=str(getattr(cli_args, "stage2_output", "") or "stage2_filtered_local.json"),
        rejected=str(getattr(cli_args, "stage2_rejected_output", "") or "stage2_rejected_local.json"),
        german_special_char_threshold=int(getattr(cli_args, "german_special_char_threshold", 9999) or 0),
        french_special_char_threshold=int(getattr(cli_args, "french_special_char_threshold", 0) or 0),
        spanish_special_char_threshold=int(getattr(cli_args, "spanish_special_char_threshold", 0) or 0),
        max_german_level=str(getattr(cli_args, "max_german_level", "") or "B2"),
        languages=list(getattr(cli_args, "languages", []) or []),
    )


def _build_tailored_stage3_args(cli_args: Any) -> SimpleNamespace:
    return SimpleNamespace(
        input=str(getattr(cli_args, "stage2_output", "") or "stage2_filtered_local.json"),
        output=str(getattr(cli_args, "stage3_output", "") or "stage3_filtered_ai.json"),
        rejected=str(getattr(cli_args, "stage3_rejected_output", "") or "stage3_rejected_local.json"),
        checkpoint=str(getattr(cli_args, "stage3_checkpoint", "") or "stage3_checkpoint.json"),
        force_reprocess=bool(getattr(cli_args, "force_reprocess", False)),
        low_applicant_threshold=int(getattr(cli_args, "low_applicant_threshold", 80) or 0),
        stage3_german_special_char_threshold=int(
            getattr(cli_args, "stage3_german_special_char_threshold", 9999) or 0
        ),
        stage3_french_special_char_threshold=int(
            getattr(cli_args, "stage3_french_special_char_threshold", 0) or 0
        ),
        stage3_spanish_special_char_threshold=int(
            getattr(cli_args, "stage3_spanish_special_char_threshold", 0) or 0
        ),
        stage3_max_german_level=str(getattr(cli_args, "stage3_max_german_level", "") or "B2"),
        stage3_extra_prompt=str(getattr(cli_args, "stage3_extra_prompt", "") or ""),
        stage3_prompt_override=str(getattr(cli_args, "stage3_prompt_override", "") or ""),
        languages=list(getattr(cli_args, "languages", []) or []),
    )


def _resolved_settings(context: StageContext, definition: StageDefinition) -> dict[str, Any]:
    settings = dict(context.data.get("resolved_run_settings") or {})
    settings.update(definition.config or {})
    resolver = context.data.get("secret_resolver")
    if callable(resolver):
        return dict(resolver(settings))
    return settings


def _workspace_cv_snapshot_from_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": str(settings.get("workspace_cv_asset_id") or "").strip(),
        "display_name": str(settings.get("workspace_cv_asset_display_name") or "").strip(),
        "path": str(settings.get("workspace_cv_asset_path") or "").strip(),
        "docx_path": str(settings.get("workspace_cv_asset_docx_path") or "").strip(),
        "text": str(settings.get("workspace_cv_text") or "").strip(),
        "required": bool(
            str(settings.get("builder_mode") or "").strip() == "scratch"
            and str(settings.get("automation_flow") or "").strip() == "tailored_documents"
        ),
    }


def _materialize_workspace_cv_settings(settings: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(settings)
    session = ObjectMaterializationSession(create_object_storage())
    source_path_text = str(resolved.get("workspace_cv_asset_path") or "").strip()
    source_path = Path(source_path_text) if source_path_text else None
    object_key = str(resolved.get("workspace_cv_asset_object_key") or "").strip()
    if object_key:
        source_path = session.materialize(
            object_key,
            filename=str(resolved.get("workspace_cv_asset_display_name") or ""),
        )
        resolved["workspace_cv_asset_path"] = str(source_path)

    companion_path_text = str(resolved.get("workspace_cv_asset_docx_path") or "").strip()
    companion_path = Path(companion_path_text) if companion_path_text else None
    companion_key = str(resolved.get("workspace_cv_asset_docx_object_key") or "").strip()
    if companion_key:
        companion_path = session.materialize(
            companion_key,
            filename=f"{Path(str(resolved.get('workspace_cv_asset_display_name') or 'workspace-cv')).stem}.docx",
        )
        resolved["workspace_cv_asset_docx_path"] = str(companion_path)
    return resolved


def _assert_workspace_cv_binding(settings: dict[str, Any]) -> None:
    snapshot = _workspace_cv_snapshot_from_settings(settings)
    if not snapshot["required"]:
        return
    if not snapshot["asset_id"]:
        raise RuntimeError("Builder-created tailored-document runs require a selected workspace CV asset.")
    if not snapshot["text"]:
        raise RuntimeError(
            "Builder-created tailored-document runs require a resolved workspace CV snapshot. "
            "Re-save the workspace after selecting a workspace CV."
        )


def _normalize_target_roles(raw_value: Any) -> list[str]:
    if isinstance(raw_value, str):
        values = [item.strip() for item in raw_value.split(",") if item.strip()]
    elif isinstance(raw_value, (list, tuple, set)):
        values = [str(item).strip() for item in raw_value if str(item).strip()]
    else:
        return []
    deduped: list[str] = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        deduped.append(value)
        seen.add(value)
    return deduped[:3]


def _augment_with_target_role_context(settings: dict[str, Any]) -> dict[str, Any]:
    target_roles = _normalize_target_roles(settings.get("target_roles"))
    if not target_roles:
        return settings

    existing_keywords = [str(item).strip() for item in settings.get("keywords") or [] if str(item).strip()]
    derived_keywords: list[str] = []
    for role in target_roles:
        for keyword in TARGET_ROLE_KEYWORD_MAP.get(role, [role.lower()]):
            if keyword not in derived_keywords:
                derived_keywords.append(keyword)
    merged_keywords: list[str] = []
    for keyword in [*existing_keywords, *derived_keywords]:
        if keyword and keyword not in merged_keywords:
            merged_keywords.append(keyword)
    if merged_keywords:
        settings["keywords"] = merged_keywords

    role_context = (
        "Target role focus for this workspace: "
        f"{', '.join(target_roles)}. Prefer listings and document tailoring aligned to these role families."
    )
    for prompt_key in ("stage1_extra_prompt", "stage3_extra_prompt", "stage4_extra_prompt"):
        existing_prompt = str(settings.get(prompt_key) or "").strip()
        if role_context.lower() in existing_prompt.lower():
            continue
        settings[prompt_key] = f"{existing_prompt}\n\n{role_context}".strip() if existing_prompt else role_context
    settings["target_roles"] = target_roles
    return settings


def _harmonize_tailored_runtime_settings(settings: dict[str, Any]) -> dict[str, Any]:
    settings.update(derive_runtime_defaults_from_settings(settings, source_ids=["linkedin_jobs", "job_board_collection"]))
    if "linkedin_max_pages" in settings and "max_pages" not in settings:
        settings["max_pages"] = settings["linkedin_max_pages"]
    mirrored_pairs = (
        ("max_german_level", "stage3_max_german_level"),
        ("french_special_char_threshold", "stage3_french_special_char_threshold"),
        ("spanish_special_char_threshold", "stage3_spanish_special_char_threshold"),
        ("german_special_char_threshold", "stage3_german_special_char_threshold"),
    )
    for source_key, target_key in mirrored_pairs:
        if source_key in settings and target_key not in settings:
            settings[target_key] = settings[source_key]
    return settings


def _merge_company_site_entries(*raw_sources: Any) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen_urls = set()
    for raw_source in raw_sources:
        for entry in parse_company_site_entries(raw_source, limit=None):
            normalized_url = canonicalize_url(str(entry.get("url") or "")) or str(entry.get("url") or "")
            if not normalized_url or normalized_url in seen_urls:
                continue
            merged.append(
                {
                    "company_name": str(entry.get("company_name") or "").strip(),
                    "url": normalized_url,
                }
            )
            seen_urls.add(normalized_url)
    return merged


def _filter_discovered_academic_sites_for_target_countries(
    settings: dict[str, Any],
    discovered_sites: list[dict[str, str]],
) -> list[dict[str, str]]:
    country_codes = settings.get("country_codes") or []
    if not country_codes:
        return list(discovered_sites)
    scope_plan = plan_company_site_scope(
        company_sites=discovered_sites,
        target_country_codes=country_codes,
        target_cities=settings.get("cities") or [],
        locality_mode=str(settings.get("company_site_locality_mode") or "local_preferred"),
        max_sites_per_run=-1,
        domain_policies=settings.get("scrapeops_domain_policies") or [],
    )
    return [
        {
            "company_name": str(site.get("company_name") or "").strip(),
            "url": str(site.get("url") or "").strip(),
        }
        for site in scope_plan.selected_sites
        if str(site.get("locality_signal") or "") == "local" and not list(site.get("matched_foreign_countries") or [])
    ]


def _prepare_company_site_source_settings(settings: dict[str, Any], definition: StageDefinition) -> dict[str, Any]:
    normalized = dict(settings)
    config = dict(definition.config or {})
    site_settings_key = str(config.get("site_settings_key") or "company_career_sites").strip() or "company_career_sites"
    timeout_setting_key = (
        str(config.get("request_timeout_setting_key") or "company_site_request_timeout_seconds").strip()
        or "company_site_request_timeout_seconds"
    )
    max_jobs_setting_key = (
        str(config.get("max_jobs_setting_key") or "company_site_max_jobs_per_site").strip()
        or "company_site_max_jobs_per_site"
    )
    discovered_site_paths = config.get("discovered_site_paths")
    if not discovered_site_paths:
        if site_settings_key == "academic_career_sites":
            discovered_site_paths = [str(path) for path in ACADEMIC_CAREER_SITE_FILES]
        else:
            discovered_site_paths = [str(path) for path in REGULAR_COMPANY_SITE_FILES]

    configured_sites = normalized.get(site_settings_key)
    configured_site_entries = _merge_company_site_entries(configured_sites)
    discovered_company_sites = load_discovered_company_site_entries(discovered_site_paths)
    if site_settings_key == "academic_career_sites":
        discovered_company_sites = _filter_discovered_academic_sites_for_target_countries(
            normalized,
            discovered_company_sites,
        )
    merged_company_sites = _merge_company_site_entries(configured_sites, discovered_company_sites)
    if merged_company_sites:
        normalized["company_career_sites"] = merged_company_sites
    selected_scope_entries = (
        merged_company_sites if site_settings_key == "academic_career_sites" else configured_site_entries
    )
    normalized["company_site_selected_scope_urls"] = [
        str(item.get("url") or "") for item in selected_scope_entries if str(item.get("url") or "")
    ]
    normalized["company_site_source_type"] = "academic" if site_settings_key == "academic_career_sites" else "company"
    if (
        "company_site_emergency_max_job_links_per_site" in normalized
        and "company_site_max_job_links_per_site" not in normalized
    ):
        LOGGER.warning(
            "Setting company_site_emergency_max_job_links_per_site is deprecated; "
            "use company_site_max_job_links_per_site instead."
        )
        normalized["company_site_max_job_links_per_site"] = normalized["company_site_emergency_max_job_links_per_site"]
    if site_settings_key == "academic_career_sites":
        configured_link_limit = _runtime_limit_int(
            normalized.get("company_site_max_job_links_per_site"),
            default=0,
        )
        if 0 < configured_link_limit < ACADEMIC_MIN_JOB_LINKS_PER_SITE:
            normalized["company_site_max_job_links_per_site"] = ACADEMIC_MIN_JOB_LINKS_PER_SITE
    if timeout_setting_key in normalized and "company_site_request_timeout_seconds" not in normalized:
        normalized["company_site_request_timeout_seconds"] = normalized[timeout_setting_key]
    if max_jobs_setting_key in normalized and "company_site_max_jobs_per_site" not in normalized:
        normalized["company_site_max_jobs_per_site"] = normalized[max_jobs_setting_key]
    return normalized


def _build_root_cli_args(
    context: StageContext,
    definition: StageDefinition,
    *,
    settings_transform: Any = None,
    materialize_workspace_cv: bool = False,
):
    from backend.config.job_seeker import load_job_seeker_config, load_project_dotenv

    load_project_dotenv()
    config = load_job_seeker_config()
    defaults = build_main_defaults(config)
    resolved_settings = _resolved_settings(context, definition)
    if materialize_workspace_cv:
        resolved_settings = _materialize_workspace_cv_settings(resolved_settings)
    _assert_workspace_cv_binding(resolved_settings)
    resolved_settings = _harmonize_tailored_runtime_settings(resolved_settings)
    resolved_settings["job_filtering_mode"] = normalize_job_filtering_mode(
        resolved_settings.get("job_filtering_mode")
    )
    resolved_settings["job_filtering_target_phrases"] = derive_job_filtering_target_phrases(resolved_settings)
    if callable(settings_transform):
        resolved_settings = settings_transform(resolved_settings, definition)
    resolved_settings = _augment_with_target_role_context(resolved_settings)
    cli_args = _namespace_from_defaults(defaults, resolved_settings)
    return config, cli_args


class LinkedInAcquireStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        return True

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        connector_id = str(definition.config.get("connector_id") or "")
        if connector_id:
            context.registries.connector_registry.get(connector_id)

        config, cli_args = _build_root_cli_args(context, definition)
        stage_args = build_tailored_stage1_args(config, cli_args)
        with runtime_cv_override(_workspace_cv_snapshot_from_settings(vars(cli_args))):
            jobs = run_tailored_stage1_pipeline(
                stage_args,
                usage_callback=_build_scrapeops_usage_callback(context, definition),
            )
        excluded_jobs = _read_json_list_if_exists(str(stage_args.excluded_output))
        artifacts = [_json_artifact(context.run.id, definition.stage_id, "stage1_output", str(stage_args.output))]
        if str(stage_args.excluded_output).strip():
            artifacts.append(
                _json_artifact(context.run.id, definition.stage_id, "stage1_excluded", str(stage_args.excluded_output))
            )
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(jobs)},
            data={f"{definition.stage_id}_rejected": excluded_jobs},
            metrics={"jobs_found": len(jobs)},
            artifacts=artifacts,
        )


class ManualUrlIngestionStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        return True

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        connector_id = str(definition.config.get("connector_id") or "")
        if connector_id:
            context.registries.connector_registry.get(connector_id)

        _, cli_args = _build_root_cli_args(context, definition)
        jobs, failures = run_manual_pipeline(
            cli_args,
            usage_callback=_build_scrapeops_usage_callback(context, definition),
        )
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(jobs)},
            data={"manual_url_failures": failures},
            metrics={"jobs_ingested": len(jobs), "failures": len(failures)},
            artifacts=[
                _json_artifact(context.run.id, definition.stage_id, "manual_jobs", str(cli_args.manual_output_json)),
                _json_artifact(
                    context.run.id,
                    definition.stage_id,
                    "manual_failures",
                    str(cli_args.manual_failures_json),
                ),
            ],
        )


class CompanyCareerSiteAcquisitionStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        connector_id = str(definition.config.get("connector_id") or "")
        if connector_id:
            context.registries.connector_registry.get(connector_id)
        _, cli_args = _build_root_cli_args(
            context,
            definition,
            settings_transform=_prepare_company_site_source_settings,
        )
        return bool(getattr(cli_args, "company_career_sites", None))

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        from backend.application.quota import check_and_increment_quota_amount

        _, cli_args = _build_root_cli_args(
            context,
            definition,
            settings_transform=_prepare_company_site_source_settings,
        )
        stage_name = str(definition.name or definition.stage_id)
        user_id = str(
            getattr(context.run, "normalized_user_id", "")
            or getattr(context.run, "user_id", "")
            or ""
        ).strip()
        plan_id = str(getattr(cli_args, "run_user_plan_id", "") or "").strip()
        quota_overrides = dict(getattr(cli_args, "run_user_quota_overrides", {}) or {})
        company_site_limits = _resolve_company_site_stage_limits(cli_args, logger=context.logger)
        run_credit_budget = int(company_site_limits["runner_credit_budget"])
        run_credit_consumed = 0
        capped_sites: list[dict[str, Any]] = []
        last_company_site_counters: dict[str, Any] = {}
        all_company_sites = list(getattr(cli_args, "company_career_sites", []) or [])
        selected_scope_urls = getattr(cli_args, "company_site_selected_scope_urls", None)
        if selected_scope_urls is None:
            selected_scope_urls = [str(item.get("url") or "") for item in all_company_sites]
        site_type = str(getattr(cli_args, "company_site_source_type", "company") or "company")
        source_policy_store = getattr(getattr(context, "repositories", None), "source_policy_store", None)
        crawlable_company_sites = all_company_sites
        skipped_by_site_state: list[dict[str, Any]] = []
        if source_policy_store is not None:
            source_policy_store.ensure_sites(all_company_sites, site_type=site_type)
            transitions = source_policy_store.mark_workspace_selected(selected_scope_urls, site_type=site_type)
            crawlable_company_sites, skipped_by_site_state = source_policy_store.filter_crawlable_sites(
                all_company_sites,
                explicitly_triggered_urls=selected_scope_urls,
            )
            if getattr(context, "logger", None) is not None:
                for site_url, transition in transitions.items():
                    context.logger.info("Site state transition for %s: %s", site_url, transition)
                for site in skipped_by_site_state:
                    context.logger.info(
                        "Skipping site %s because site_state=%s.",
                        site.get("url", ""),
                        site.get("site_state", "pending"),
                    )

        def _record_site_yield(site_url: str, jobs_found: int) -> None:
            if source_policy_store is None:
                return
            transition = source_policy_store.record_site_yield(site_url, jobs_found=jobs_found)
            if getattr(context, "logger", None) is not None:
                context.logger.info(
                    "Site yield state for %s: jobs_found=%s state=%s zero_yield_runs=%s.",
                    site_url,
                    transition["jobs_found"],
                    transition["site_state"],
                    transition["consecutive_zero_yield_runs"],
                )

        def _record_usage_event(event: dict[str, Any]) -> None:
            nonlocal run_credit_consumed
            runner_credits = int(event.get("runner_credits") or 0)
            if bool(event.get("billed")) and run_credit_budget > 0 and run_credit_consumed + runner_credits > run_credit_budget:
                raise RuntimeError("This run reached its runner-credit budget before the next company-site request.")
            if bool(event.get("billed")):
                run_credit_consumed += runner_credits
                if user_id and plan_id and runner_credits > 0:
                    check_and_increment_quota_amount(
                        context.repositories,
                        user_id,
                        "runner_credits_per_month",
                        plan_id,
                        amount=runner_credits,
                        route=f"/runs/{context.run.id}",
                        quota_overrides=quota_overrides,
                    )
            analytics_store = getattr(context.repositories, "analytics_store", None)
            if analytics_store is not None and hasattr(analytics_store, "emit_event"):
                event_id = f"evt_{uuid4().hex[:16]}"
                if hasattr(analytics_store, "record_scrapeops_usage") and event.get("method") == "scrapeops_proxy":
                    analytics_store.record_scrapeops_usage(
                        ledger_id=event_id,
                        payload=event,
                        user_id=user_id,
                        workspace_id=context.workspace.id,
                        run_id=context.run.id,
                        route=f"/runs/{context.run.id}",
                        source="worker",
                    )
                analytics_store.emit_event(
                    event_id=event_id,
                    event_name="scrapeops_request",
                    occurred_at=utc_now_iso(),
                    user_id=user_id,
                    workspace_id=context.workspace.id,
                    run_id=context.run.id,
                    route=f"/runs/{context.run.id}",
                    source="worker",
                    payload={
                        "policy_version": str(getattr(cli_args, "company_site_policy_version", "") or ""),
                        "stage_id": definition.stage_id,
                        "stage_type": definition.stage_type,
                        **dict(event or {}),
                    },
                )

        def _progress_callback(payload: dict[str, Any]) -> None:
            nonlocal capped_sites, last_company_site_counters
            last_company_site_counters = dict(payload.get("counters") or {})
            capped_sites = list(last_company_site_counters.get("capped_sites") or capped_sites)
            context.update_run_progress(
                stage_id=definition.stage_id,
                stage_type=definition.stage_type,
                stage_name=stage_name,
                message=str(payload.get("message") or f"Running {stage_name}"),
                counters=dict(payload.get("counters") or {}),
                current_item=dict(payload.get("current_item") or {}),
                recent_failures=list(payload.get("recent_failures") or []),
                status="running",
                extra={"stage_description": str(definition.description or "")},
            )

        def _should_cancel() -> bool:
            try:
                latest = context.repositories.run_repository.get(context.run.id)
            except Exception:
                return False
            return str(latest.status or "") in {"cancel_requested", "cancelled"}

        def _seen_job_url_lookup(site_url: str, job_urls: list[str]) -> set[str]:
            if source_policy_store is None or not hasattr(source_policy_store, "get_seen_job_urls"):
                return set()
            try:
                return set(source_policy_store.get_seen_job_urls(job_urls))
            except TypeError:
                return set(source_policy_store.get_seen_job_urls(job_urls))

        def _cached_job_lookup(site_url: str, job_urls: list[str]) -> dict[str, dict[str, Any]]:
            if source_policy_store is None or not hasattr(source_policy_store, "get_cached_job_postings"):
                return {}
            return dict(source_policy_store.get_cached_job_postings(job_urls))

        def _record_job_url_history(site_url: str, attempts: list[dict[str, Any]]) -> None:
            if source_policy_store is None or not hasattr(source_policy_store, "record_job_url_attempts"):
                return
            source_policy_store.record_job_url_attempts(
                [
                    {
                        **dict(attempt or {}),
                        "site_url": str(dict(attempt or {}).get("site_url") or site_url),
                    }
                    for attempt in attempts
                    if isinstance(attempt, dict)
                ],
                run_id=context.run.id,
                workspace_id=str(getattr(getattr(context, "workspace", None), "id", "") or ""),
            )

        jobs, failures = scrape_company_career_sites(
            company_sites=crawlable_company_sites,
            source_type=site_type,
            keywords=getattr(cli_args, "keywords", []),
            request_timeout_seconds=int(getattr(cli_args, "company_site_request_timeout_seconds", 30)),
            max_jobs_per_site=int(getattr(cli_args, "company_site_max_jobs_per_site", 0)),
            use_proxy_fallback=bool(getattr(cli_args, "use_proxy_fallback", False)),
            target_country_codes=getattr(cli_args, "country_codes", []),
            target_cities=getattr(cli_args, "cities", []),
            posted_within_days=int(getattr(cli_args, "posted_within_days", 0) or 0),
            locality_mode=str(getattr(cli_args, "company_site_locality_mode", "local_preferred") or "local_preferred"),
            max_sites_per_run=int(company_site_limits["max_sites_per_run"]),
            run_credit_budget=run_credit_budget,
            max_job_links_per_site=int(company_site_limits["max_job_links_per_site"]),
            domain_policies=getattr(cli_args, "scrapeops_domain_policies", []),
            usage_callback=_record_usage_event,
            logger=context.logger,
            progress_callback=_progress_callback,
            should_cancel=_should_cancel,
            yield_callback=_record_site_yield,
            seen_job_url_lookup=_seen_job_url_lookup,
            cached_job_lookup=_cached_job_lookup,
            job_url_history_callback=_record_job_url_history,
        )
        coverage_limit_reasons = {
            "company_site_max_job_links_per_site",
            "explicit_jobs_per_site_cap",
        }
        coverage_skips = [
            item
            for item in failures
            if str(item.get("error") or "").strip() in coverage_limit_reasons
        ]
        operational_failures = [
            item
            for item in failures
            if str(item.get("error") or "").strip() not in coverage_limit_reasons
        ]
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(jobs)},
            data={
                "company_site_failures": operational_failures,
                "company_site_coverage_skips": coverage_skips,
                "company_site_state_skips": skipped_by_site_state,
                "capped_sites": [*list(getattr(context, "data", {}).get("capped_sites") or []), *capped_sites],
                "company_site_policy": {
                    "policy_version": str(getattr(cli_args, "company_site_policy_version", "") or ""),
                    "locality_mode": str(getattr(cli_args, "company_site_locality_mode", "local_preferred") or "local_preferred"),
                    "max_sites_per_run": int(company_site_limits["max_sites_per_run"]),
                    "runner_credit_budget": run_credit_budget,
                    "company_site_max_job_links_per_site": int(company_site_limits["max_job_links_per_site"]),
                },
            },
            metrics={
                "jobs_found": len(jobs),
                "failures": len(operational_failures),
                "coverage_skips": len(coverage_skips),
                "incremental_skipped_job_urls": int(last_company_site_counters.get("incremental_skipped_job_urls") or 0),
                "public_index_reused_job_urls": int(last_company_site_counters.get("public_index_reused_job_urls") or 0),
                "candidate_jobs_discovered": int(last_company_site_counters.get("candidate_jobs_discovered") or 0),
                "candidate_jobs_followed": int(last_company_site_counters.get("candidate_jobs_followed") or 0),
                "candidate_jobs_skipped": int(last_company_site_counters.get("candidate_jobs_skipped") or 0),
                "link_cap_hits": int(last_company_site_counters.get("link_cap_hits") or 0),
                "runner_credits_consumed": int(last_company_site_counters.get("runner_credits_consumed") or 0),
                "scrapeops_credits_consumed": int(last_company_site_counters.get("native_credits_consumed") or 0),
                "billed_request_count": int(last_company_site_counters.get("billed_request_count") or 0),
                "request_count": int(last_company_site_counters.get("request_count") or 0),
            },
        )


class TailoredScreeningStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        return bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        _, cli_args = _build_root_cli_args(context, definition)
        stage_args = _build_tailored_stage2_args(cli_args)
        input_jobs = context.get_job_dicts(definition.input_keys[0])
        approved, rejected = run_tailored_stage2_pipeline(input_jobs, stage_args)
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(approved)},
            data={f"{definition.stage_id}_rejected": rejected},
            metrics={"approved": len(approved), "rejected": len(rejected)},
            artifacts=[
                _json_artifact(context.run.id, definition.stage_id, "approved", str(stage_args.output)),
                _json_artifact(context.run.id, definition.stage_id, "rejected", str(stage_args.rejected)),
            ],
        )


class TailoredPrioritizationStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        return bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        _, cli_args = _build_root_cli_args(context, definition)
        stage_args = _build_tailored_stage3_args(cli_args)
        input_jobs = context.get_job_dicts(definition.input_keys[0])
        approved, rejected = run_tailored_stage3_pipeline(input_jobs, stage_args)
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(approved)},
            data={f"{definition.stage_id}_rejected": rejected},
            metrics={"approved": len(approved), "rejected": len(rejected)},
            artifacts=[
                _json_artifact(context.run.id, definition.stage_id, "approved", str(stage_args.output)),
                _json_artifact(context.run.id, definition.stage_id, "rejected", str(stage_args.rejected)),
            ],
        )


class GenericScreeningStage(BaseStage):
    def __init__(self) -> None:
        self._tailored_stage = TailoredScreeningStage()
        self._reusable_stage = ReusablePackageFilteringStage()

    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        strategy = str(definition.config.get("screening_strategy") or "").strip()
        if strategy == "reusable_packages":
            return self._reusable_stage.can_run(context, definition)
        return self._tailored_stage.can_run(context, definition)

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        strategy = str(definition.config.get("screening_strategy") or "").strip()
        if strategy == "reusable_packages":
            return self._reusable_stage.execute(context, definition)
        return self._tailored_stage.execute(context, definition)


class MergeJobSetsStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        return any(context.get_job_set(key) for key in definition.input_keys)

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        from backend.domain.job_identity import dedupe_job_records, load_existing_tracker_identity_keys

        _, cli_args = _build_root_cli_args(context, definition)
        merged_input: list[dict[str, Any]] = []
        for key in definition.input_keys:
            merged_input.extend(context.get_job_dicts(key))

        merged_jobs, dropped_duplicates = dedupe_job_records(merged_input, logger=context.logger)
        dedupe_against_tracker = definition.config.get("dedupe_against_tracker")
        if dedupe_against_tracker is None:
            dedupe_against_tracker = bool(getattr(cli_args, "dedupe_against_tracker", True))
        if bool(dedupe_against_tracker):
            existing_keys = load_existing_tracker_identity_keys(str(cli_args.output_xlsx))
            merged_jobs, dropped_against_tracker = dedupe_job_records(
                merged_jobs,
                existing_keys=existing_keys,
                logger=context.logger,
            )
            dropped_duplicates.extend(dropped_against_tracker)

        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(merged_jobs)},
            data={f"{definition.stage_id}_dropped_duplicates": dropped_duplicates},
            metrics={"merged_jobs": len(merged_jobs), "dropped_duplicates": len(dropped_duplicates)},
        )


class TailoredDocumentExportStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        return bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        generation_id = str(definition.config.get("generation_id") or "")
        renderer_id = str(definition.config.get("renderer_id") or "")
        if generation_id:
            context.registries.generation_registry.get(generation_id)
        if renderer_id:
            context.registries.renderer_registry.get(renderer_id)

        config, cli_args = _build_root_cli_args(
            context,
            definition,
            materialize_workspace_cv=True,
        )
        stage4_args = build_tailored_stage4_args(cli_args)
        jobs = context.get_job_dicts(definition.input_keys[0])
        if not jobs:
            Path(stage4_args.output_json).write_text("[]", encoding="utf-8")
            return StageOutcome(job_sets={definition.output_key: []}, metrics={"generated_jobs": 0})

        Path(stage4_args.input).write_text(json.dumps(jobs, indent=2, ensure_ascii=False), encoding="utf-8")
        with runtime_cv_override(_workspace_cv_snapshot_from_settings(vars(cli_args))):
            if normalize_cv_generation_mode(getattr(stage4_args, "cv_generation_mode", "")) == CV_GENERATION_MODE_STANDARD:
                records = run_standard_cv_pipeline(stage4_args, config=config, jobs=jobs)
            else:
                records = run_tailored_stage4_pipeline(stage4_args, config=config, jobs=jobs)
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(records)},
            metrics={"generated_jobs": len(records)},
            artifacts=_tailored_document_artifacts(
                context.run.id,
                definition.stage_id,
                output_json=str(stage4_args.output_json),
                output_xlsx=str(stage4_args.output_xlsx),
                records=records,
            ),
        )


class JobBoardAcquisitionStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        connector_id = str(definition.config.get("connector_id") or "")
        if connector_id:
            context.registries.connector_registry.get(connector_id)
        return True

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        config = load_reusable_packages_config()
        args = build_reusable_stage1_args(config, overrides=_resolved_settings(context, definition))
        result = run_reusable_stage1_pipeline(
            args,
            config=config,
            usage_callback=_build_scrapeops_usage_callback(context, definition),
        )
        jobs = result["jobs"]
        output_path = result["output_path"]
        source_log_path = result["source_log_path"]
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(jobs)},
            metrics={"jobs_found": len(jobs)},
            artifacts=[
                _json_artifact(context.run.id, definition.stage_id, "stage1_output", str(output_path)),
                _json_artifact(context.run.id, definition.stage_id, "stage1_source_log", str(source_log_path)),
            ],
        )


class ReusablePackageFilteringStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        return bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        config = load_reusable_packages_config()
        args = build_reusable_stage2_args(config, overrides=_resolved_settings(context, definition))
        result = run_reusable_stage2_pipeline(
            args,
            config=config,
            jobs=context.get_job_dicts(definition.input_keys[0]),
        )
        jobs = result["approved_jobs"]
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(jobs)},
            metrics={"approved": len(jobs)},
            artifacts=[
                _json_artifact(context.run.id, definition.stage_id, "stage2_output", result["output_path"]),
                _json_artifact(context.run.id, definition.stage_id, "stage2_rejected", result["rejected_path"]),
            ],
        )


class RoleClassificationStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        return bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        config = load_reusable_packages_config()
        args = build_reusable_stage3_args(config, overrides=_resolved_settings(context, definition))
        result = run_reusable_stage3_pipeline(
            args,
            config=config,
            jobs=context.get_job_dicts(definition.input_keys[0]),
        )
        jobs = result["classified_jobs"]
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(jobs)},
            metrics={"classified_jobs": len(jobs)},
            artifacts=[
                _json_artifact(context.run.id, definition.stage_id, "stage3_output", result["output_path"]),
                _json_artifact(
                    context.run.id,
                    definition.stage_id,
                    "stage3_clusters",
                    result["clusters_output_path"],
                ),
            ],
        )


class ReusableProfileGenerationStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        generation_id = str(definition.config.get("generation_id") or "")
        if generation_id:
            context.registries.generation_registry.get(generation_id)
        return bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        config = load_reusable_packages_config()
        args = build_reusable_stage4_args(config, overrides=_resolved_settings(context, definition))
        result = run_reusable_stage4_pipeline(
            args,
            config=config,
            jobs=context.get_job_dicts(definition.input_keys[0]),
        )
        payload = result["role_cv_index"]
        role_cvs = result["role_cv_records"]
        return StageOutcome(
            data={definition.output_key: payload},
            metrics={"role_cvs": len(role_cvs or [])},
            artifacts=[
                _json_artifact(
                    context.run.id,
                    definition.stage_id,
                    "stage4_role_cvs",
                    result["role_cv_index_path"],
                ),
                _json_artifact(
                    context.run.id,
                    definition.stage_id,
                    "stage4_role_cv_dir",
                    result["role_cv_output_dir"],
                ),
            ],
        )


class ApplicationPackageExportStage(BaseStage):
    def can_run(self, context: StageContext, definition: StageDefinition) -> bool:
        renderer_id = str(definition.config.get("renderer_id") or "")
        if renderer_id:
            context.registries.renderer_registry.get(renderer_id)
        has_jobs = bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))
        has_role_cvs = bool(context.data.get(definition.input_keys[1])) if len(definition.input_keys) > 1 else True
        return has_jobs and has_role_cvs

    def execute(self, context: StageContext, definition: StageDefinition) -> StageOutcome:
        config = load_reusable_packages_config()
        args = build_reusable_stage5_args(config, overrides=_resolved_settings(context, definition))
        role_index_payload = context.data.get(definition.input_keys[1]) if len(definition.input_keys) > 1 else None
        result = run_reusable_stage5_pipeline(
            args,
            config=config,
            jobs=context.get_job_dicts(definition.input_keys[0]),
            role_index_payload=role_index_payload,
        )
        records = result["records"]
        return StageOutcome(
            job_sets={definition.output_key: _to_job_records(records)},
            metrics={"packaged_jobs": len(records)},
            artifacts=[
                _json_artifact(context.run.id, definition.stage_id, "stage5_output", result["output_json"]),
                _json_artifact(context.run.id, definition.stage_id, "stage5_xlsx", result["output_xlsx"]),
                _json_artifact(context.run.id, definition.stage_id, "stage5_docs_dir", result["docs_root"]),
            ],
        )


def register_stage_adapters(stage_registry) -> None:
    stage_registry.register("jobs.acquire.search_listings", LinkedInAcquireStage())
    stage_registry.register("jobs.ingest.curated_urls", ManualUrlIngestionStage())
    stage_registry.register("jobs.acquire.company_sites", CompanyCareerSiteAcquisitionStage())
    stage_registry.register("jobs.screen.filter", GenericScreeningStage())
    stage_registry.register("jobs.prioritize.rank", TailoredPrioritizationStage())
    stage_registry.register("jobs.merge.dedupe", MergeJobSetsStage())
    stage_registry.register("applications.generate.documents", TailoredDocumentExportStage())
    stage_registry.register("jobs.acquire.job_boards", JobBoardAcquisitionStage())
    stage_registry.register("jobs.classify.roles", RoleClassificationStage())
    stage_registry.register("profiles.generate.reusable", ReusableProfileGenerationStage())
    stage_registry.register("applications.package.export", ApplicationPackageExportStage())

    # Compatibility aliases for persisted legacy workflow templates.
    stage_registry.register("legacy.linkedin.acquire", LinkedInAcquireStage())
    stage_registry.register("legacy.manual_url.ingest", ManualUrlIngestionStage())
    stage_registry.register("legacy.jobs.merge", MergeJobSetsStage())
    stage_registry.register("legacy.white_collar.local_filter", TailoredScreeningStage())
    stage_registry.register("legacy.white_collar.rank", TailoredPrioritizationStage())
    stage_registry.register("legacy.white_collar.docs", TailoredDocumentExportStage())
    stage_registry.register("legacy.blue_collar.stage1", JobBoardAcquisitionStage())
    stage_registry.register("legacy.blue_collar.stage2", ReusablePackageFilteringStage())
    stage_registry.register("legacy.blue_collar.stage3", RoleClassificationStage())
    stage_registry.register("legacy.blue_collar.stage4", ReusableProfileGenerationStage())
    stage_registry.register("legacy.blue_collar.stage5", ApplicationPackageExportStage())
