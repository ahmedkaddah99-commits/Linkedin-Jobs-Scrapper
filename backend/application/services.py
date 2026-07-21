from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from backend.application.assisted_apply_package_service import (
    ApplicationPackageService,
)
from backend.application.assisted_apply_service import AssistedApplyConnectionService
from backend.application.contracts import BackendRegistriesProtocol, StageEngineProtocol
from backend.application.domain_services import IdentityAccessService, WorkspaceCatalogService
from backend.application.quota import get_usage_snapshot
from backend.application.run_services import RunLifecycleService
from backend.application.tracker_services import TrackerApplicationService
from backend.capabilities.networking import build_relevant_people_discovery
from backend.capabilities.tailored_documents.manual_urls import normalize_manual_urls
from backend.config.plans import get_limit, normalize_plan_id
from backend.config.scrapeops_admin_policy import (
    SCRAPEOPS_ADMIN_POLICY_CONFIG_KEY,
    default_scrapeops_admin_policy,
    normalize_scrapeops_admin_policy,
    plan_policy_limits,
)
from backend.connectors.company_career_sites import (
    ACADEMIC_CAREER_SITE_FILES,
    REGULAR_COMPANY_SITE_FILES,
    estimate_company_site_runner_credit_range,
    load_discovered_company_site_entries,
    parse_company_site_entries,
    plan_company_site_scope,
)
from backend.domain.assisted_apply import AssistedApplyConnectionRecord, AssistedApplyPreferences
from backend.domain.models import (
    CareerProfile,

    RUN_STATUS_CANCEL_REQUESTED,
    RUN_STATUS_CANCELLED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_PLANNED,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    WORKER_STATUS_IDLE,
    WORKER_STATUS_RUNNING,
    WORKER_STATUS_STALE,
    WORKER_STATUS_STOPPED,
    ArtifactRecord,
    ApiTokenRecord,
    JobRecord,
    ReferralContactRecord,
    ReviewRecord,
    RunRecord,
    SecretRecord,
    StageDefinition,
    UserRecord,
    WorkerRecord,
    WorkflowTemplate,
    WorkspaceDefinition,
    utc_now_iso,
)
from backend.integrations.scrapeops import (
    SCRAPEOPS_POLICY_VERSION,
    SCRAPEOPS_USAGE_EVENT_NAME,
    fetch_account_usage,
    fetch_domain_stats,
)
from backend.orchestration import (
    build_quick_apply_workflow_template,
    build_workspace_from_scratch,
    validate_workspace_source_configuration,
    workspace_builder_catalog,
)
from backend.orchestration.workspace_builder import (
    SOURCE_ACADEMIC_CAREER_SITES,
    SOURCE_COMPANY_CAREER_SITES,
)
from backend.repositories.contracts import BackendRepositories


BUILDER_WORKSPACE_FLOW_IDS = {"tailored_documents", "reusable_packages"}
BUILDER_CONNECTOR_SOURCE_IDS = {
    "linkedin_jobs": "linkedin_jobs",
    "curated_job_urls": "curated_job_urls",
    "company_career_sites": "company_career_sites",
    "academic_career_sites": "academic_career_sites",
    "job_board_collection": "job_board_collection",
}
BUILDER_MODULE_FEATURE_FLAGS = {
    "screening_filter": "screening_filter",
    "priority_ranking": "priority_ranking",
    "role_classification": "role_classification",
    "reusable_profile_builder": "reusable_profile_builder",
    "tailored_document_generation": "tailored_document_generation",
    "application_packaging": "application_packaging",
}
AUTO_APPROVE_REVIEW_STAGE_TYPES = {
    "applications.generate.documents",
    "legacy.white_collar.docs",
}
WORKSPACE_RUN_SCHEDULE_METADATA_KEY = "run_schedule"
SCHEDULED_RUN_ACTIVE_STATUSES = {
    RUN_STATUS_PLANNED,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_CANCEL_REQUESTED,
}
SCHEDULED_RUN_REQUESTED_BY = "scheduler"
SCRAPEOPS_RECONCILIATION_EVENT_NAME = "scrapeops_reconciliation_snapshot"
SCRAPEOPS_ALERT_EVENT_NAME = "scrapeops_alert"


class BackendValidationError(ValueError):
    def __init__(self, error_code: str, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.error_code = str(error_code or "validation_failed")
        self.details = dict(details or {})


def _field_error(
    field: str,
    code: str,
    message: str,
    *,
    source_id: str = "",
) -> dict[str, str]:
    error = {
        "field": str(field or "").strip(),
        "code": str(code or "").strip(),
        "message": str(message or "").strip(),
    }
    if source_id:
        error["source_id"] = str(source_id).strip()
    return error


def _dedupe_field_errors(errors: list[dict[str, Any]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_error in errors:
        if not isinstance(raw_error, dict):
            continue
        field = str(raw_error.get("field") or "").strip()
        code = str(raw_error.get("code") or "").strip()
        message = str(raw_error.get("message") or "").strip()
        source_id = str(raw_error.get("source_id") or "").strip()
        if not field or not code or not message:
            continue
        dedupe_key = (field, code, source_id)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(_field_error(field, code, message, source_id=source_id))
    return deduped


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc_datetime(value: Any) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _schedule_interval_days(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _next_schedule_timestamp(*, from_dt: datetime, interval_days: int) -> str:
    return (from_dt + timedelta(days=max(1, int(interval_days)))).isoformat()


def _workspace_run_schedule_payload(workspace: WorkspaceDefinition) -> dict[str, Any]:
    raw_schedule = dict((workspace.metadata or {}).get(WORKSPACE_RUN_SCHEDULE_METADATA_KEY) or {})
    interval_days = _schedule_interval_days(raw_schedule.get("interval_days"))
    enabled = bool(raw_schedule.get("enabled")) and interval_days >= 1
    return {
        "enabled": enabled,
        "interval_days": interval_days if enabled else 0,
        "next_run_at": str(raw_schedule.get("next_run_at") or ""),
        "last_enqueued_at": str(raw_schedule.get("last_enqueued_at") or ""),
        "last_run_id": str(raw_schedule.get("last_run_id") or ""),
        "last_error": str(raw_schedule.get("last_error") or ""),
        "last_error_at": str(raw_schedule.get("last_error_at") or ""),
    }


def _is_builder_created_workspace(workspace: WorkspaceDefinition) -> bool:
    metadata = dict(workspace.metadata or {})
    return str(metadata.get("builder_mode") or "").strip() == "scratch" or bool(metadata.get("workspace_configuration_v2"))


def _builder_workspace_flow_id(workspace: WorkspaceDefinition) -> str:
    metadata = dict(workspace.metadata or {})
    return str(metadata.get("automation_flow") or workspace.settings.get("automation_flow") or "").strip()


def _builder_workspace_source_ids(workspace: WorkspaceDefinition) -> list[str]:
    metadata = dict(workspace.metadata or {})
    source_ids = [str(item).strip() for item in metadata.get("source_ids") or [] if str(item).strip()]
    if source_ids:
        return source_ids
    return _builder_workspace_connector_source_ids(workspace)


def _builder_workspace_connector_source_ids(workspace: WorkspaceDefinition) -> list[str]:
    derived_source_ids: list[str] = []
    for source in workspace.sources:
        source_id = BUILDER_CONNECTOR_SOURCE_IDS.get(str(source.connector_id or "").strip())
        if source_id and source_id not in derived_source_ids:
            derived_source_ids.append(source_id)
    return derived_source_ids


def _builder_workspace_module_ids(workspace: WorkspaceDefinition) -> list[str]:
    metadata = dict(workspace.metadata or {})
    return [str(item).strip() for item in metadata.get("modules") or [] if str(item).strip()]


def _builder_workspace_enabled_module_ids(workspace: WorkspaceDefinition) -> list[str]:
    return [
        module_id
        for module_id, feature_flag in BUILDER_MODULE_FEATURE_FLAGS.items()
        if bool((workspace.feature_flags or {}).get(feature_flag))
    ]


def _workspace_cv_asset_id(workspace: WorkspaceDefinition) -> str:
    metadata = dict(workspace.metadata or {})
    workspace_configuration_v2 = metadata.get("workspace_configuration_v2") or {}
    cv_binding = dict(workspace_configuration_v2.get("cv_binding") or {})
    return str(workspace.settings.get("workspace_cv_asset_id") or cv_binding.get("asset_id") or "").strip()


def _workspace_cv_asset_is_available(
    *,
    file_path: str,
    object_key: str,
    object_storage: Any = None,
) -> bool:
    if object_key:
        exists = getattr(object_storage, "exists", None)
        if not callable(exists):
            return True
        try:
            return bool(exists(object_key))
        except Exception:
            return False
    return bool(file_path and Path(file_path).is_file())


def _builder_workspace_cv_asset_field_errors(
    workspace: WorkspaceDefinition,
    *,
    object_storage: Any = None,
) -> list[dict[str, str]]:
    asset_id = _workspace_cv_asset_id(workspace)
    if not asset_id:
        if _builder_workspace_flow_id(workspace) != "tailored_documents":
            return []
        return [
            _field_error(
                "workspace_cv_asset_id",
                "required",
                "Select a workspace CV before saving or running this workspace.",
            )
        ]

    metadata = dict(workspace.metadata or {})
    asset = dict(metadata.get("workspace_cv_asset") or {})
    if not asset:
        settings = dict(workspace.settings or {})
        if settings.get("workspace_cv_asset_object_key") or settings.get("workspace_cv_asset_path"):
            asset = {
                "asset_id": asset_id,
                "asset_kind": "workspace_cv",
                "display_name": str(settings.get("workspace_cv_asset_display_name") or ""),
                "workspace_binding": {"workspace_id": ""},
                "file": {
                    "path": str(settings.get("workspace_cv_asset_path") or ""),
                    "object_key": str(settings.get("workspace_cv_asset_object_key") or ""),
                    "mime_type": str(settings.get("workspace_cv_asset_mime_type") or ""),
                    "extension": str(settings.get("workspace_cv_asset_extension") or ""),
                },
            }
        else:
            return [
                _field_error(
                    "workspace_cv_asset_id",
                    "workspace_cv_asset_unresolved",
                    "Select an accessible workspace CV before saving or running this workspace.",
                )
            ]

    snapshot_asset_id = str(asset.get("asset_id") or "").strip()
    if snapshot_asset_id != asset_id:
        return [
            _field_error(
                "workspace_cv_asset_id",
                "workspace_cv_asset_mismatch",
                "The saved workspace CV no longer matches the selected workspace_cv_asset_id.",
            )
        ]

    asset_kind = str(asset.get("asset_kind") or "").strip()
    if asset_kind != "workspace_cv":
        return [
            _field_error(
                "workspace_cv_asset_id",
                "workspace_cv_asset_invalid_kind",
                "workspace_cv_asset_id must reference an uploaded workspace CV.",
            )
        ]

    bound_workspace_id = str(
        asset.get("workspace_binding", {}).get("workspace_id")
        or asset.get("workspace_id")
        or ""
    ).strip()
    if bound_workspace_id and bound_workspace_id != workspace.id:
        return [
            _field_error(
                "workspace_cv_asset_id",
                "workspace_cv_asset_inaccessible",
                "The selected workspace CV is bound to a different workspace.",
            )
        ]

    file_payload = dict(asset.get("file") or {})
    file_path = str(file_payload.get("path") or asset.get("path") or "").strip()
    object_key = str(file_payload.get("object_key") or "").strip()
    if not _workspace_cv_asset_is_available(
        file_path=file_path,
        object_key=object_key,
        object_storage=object_storage,
    ):
        return [
            _field_error(
                "workspace_cv_asset_id",
                "workspace_cv_asset_missing_file",
                "The selected workspace CV is no longer available in durable storage.",
            )
        ]
    return []


def _auto_approve_review_job_set_keys(workflow: WorkflowTemplate) -> list[str]:
    job_set_keys: list[str] = []
    for stage in workflow.stages:
        if stage.stage_type not in AUTO_APPROVE_REVIEW_STAGE_TYPES:
            continue
        output_key = str(stage.output_key or "").strip()
        if output_key and output_key not in job_set_keys:
            job_set_keys.append(output_key)
    return job_set_keys


def _builder_workspace_run_preflight_field_errors(
    workspace: WorkspaceDefinition,
    *,
    run_plan_settings: Mapping[str, Any] | None = None,
    object_storage: Any = None,
) -> list[dict[str, str]]:
    saved_asset_id = _workspace_cv_asset_id(workspace)
    asset_id = str(
        (run_plan_settings or {}).get("workspace_cv_asset_id")
        or saved_asset_id
        or ""
    ).strip()
    if asset_id and saved_asset_id and asset_id != saved_asset_id:
        return [
            _field_error(
                "workspace_cv_asset_id",
                "workspace_cv_asset_mismatch",
                "Run workspace_cv_asset_id does not match the saved workspace CV.",
            )
        ]
    if not asset_id:
        return _builder_workspace_cv_asset_field_errors(workspace, object_storage=object_storage)

    settings = dict(run_plan_settings or {})
    file_path = str(settings.get("workspace_cv_asset_path") or "").strip()
    object_key = str(settings.get("workspace_cv_asset_object_key") or "").strip()
    if file_path or object_key:
        if not _workspace_cv_asset_is_available(
            file_path=file_path,
            object_key=object_key,
            object_storage=object_storage,
        ):
            return [
                _field_error(
                    "workspace_cv_asset_id",
                    "workspace_cv_asset_missing_file",
                    "The selected workspace CV is no longer available in durable storage.",
                )
            ]

    workspace_cv_text = str(settings.get("workspace_cv_text") or "").strip()
    if workspace_cv_text:
        return []

    return [
        _field_error(
            "workspace_cv_asset_id",
            "workspace_cv_snapshot_missing",
            "Builder-created tailored-document runs require a resolved workspace CV snapshot. Re-save the workspace and start a new run.",
        )
    ]


def _builder_workspace_validation_report(
    *,
    flow_id: str,
    source_ids: list[str],
    module_ids: list[str],
    settings: Mapping[str, Any],
) -> dict[str, Any]:
    catalog = workspace_builder_catalog().to_dict()
    catalog_sources = {
        str(item["id"]): set(item.get("compatible_flows") or [])
        for item in catalog["sources"]
    }
    catalog_modules = {
        str(item["id"]): set(item.get("compatible_flows") or [])
        for item in catalog["modules"]
    }
    field_errors: list[dict[str, str]] = []
    valid_source_ids: list[str] = []

    if flow_id not in BUILDER_WORKSPACE_FLOW_IDS:
        field_errors.append(
            _field_error(
                "flow_id",
                "unsupported",
                "flow_id must be one of: tailored_documents, reusable_packages.",
            )
        )

    if not source_ids:
        field_errors.append(
            _field_error(
                "source_ids",
                "required",
                "Choose at least one source for this workspace.",
            )
        )
    else:
        for source_id in source_ids:
            compatible_flows = catalog_sources.get(source_id)
            if compatible_flows is None:
                field_errors.append(
                    _field_error(
                        "source_ids",
                        "unknown_source",
                        f"Unknown source_id '{source_id}'.",
                        source_id=source_id,
                    )
                )
                continue
            if flow_id in compatible_flows:
                valid_source_ids.append(source_id)
                continue
            field_errors.append(
                _field_error(
                    "source_ids",
                    "incompatible_source",
                    f"Source '{source_id}' is not compatible with flow '{flow_id}'.",
                    source_id=source_id,
                )
            )

    if not module_ids:
        field_errors.append(
            _field_error(
                "module_ids",
                "required",
                "Enable at least one automation module for this workspace.",
            )
        )
    else:
        for module_id in module_ids:
            compatible_flows = catalog_modules.get(module_id)
            if compatible_flows is None:
                field_errors.append(
                    _field_error(
                        "module_ids",
                        "unknown_module",
                        f"Unknown module_id '{module_id}'.",
                    )
                )
            elif flow_id not in compatible_flows:
                field_errors.append(
                    _field_error(
                        "module_ids",
                        "incompatible_module",
                        f"Module '{module_id}' is not compatible with flow '{flow_id}'.",
                    )
                )

    if flow_id == "tailored_documents":
        required_modules = {
            "screening_filter": "Enable the screening_filter module for tailored-document workspaces.",
            "tailored_document_generation": (
                "Enable the tailored_document_generation module for tailored-document workspaces."
            ),
        }
        for module_id, message in required_modules.items():
            if module_id not in module_ids:
                field_errors.append(
                    _field_error(
                        "module_ids",
                        "required_module",
                        message,
                    )
                )
    elif flow_id == "reusable_packages":
        if "application_packaging" in module_ids and "reusable_profile_builder" not in module_ids:
            field_errors.append(
                _field_error(
                    "module_ids",
                    "module_dependency",
                    "application_packaging requires the reusable_profile_builder module.",
                )
            )
        if "reusable_profile_builder" in module_ids and "role_classification" not in module_ids:
            field_errors.append(
                _field_error(
                    "module_ids",
                    "module_dependency",
                    "reusable_profile_builder requires the role_classification module.",
                )
            )

    validation_payload = {
        "flow_id": flow_id,
        "source_ids": valid_source_ids,
        "settings": dict(settings or {}),
    }
    source_report = validate_workspace_source_configuration(validation_payload)
    merged_field_errors = _dedupe_field_errors([*field_errors, *(source_report.get("field_errors") or [])])
    return {
        "flow_id": flow_id,
        "source_ids": list(source_ids),
        "module_ids": list(module_ids),
        "field_errors": merged_field_errors,
        "source_results": list(source_report.get("source_results") or []),
        "derived_runtime_defaults": dict(source_report.get("derived_runtime_defaults") or {}),
        "valid": not merged_field_errors,
    }


def _raise_builder_validation_error(
    *,
    error_code: str,
    message: str,
    phase: str,
    workspace_id: str,
    report: Mapping[str, Any],
) -> None:
    raise BackendValidationError(
        error_code,
        message,
        details={
            "phase": phase,
            "workspace_id": workspace_id,
            "flow_id": str(report.get("flow_id") or ""),
            "source_ids": [str(item) for item in report.get("source_ids") or [] if str(item).strip()],
            "module_ids": [str(item) for item in report.get("module_ids") or [] if str(item).strip()],
            "field_errors": list(report.get("field_errors") or []),
            "source_results": list(report.get("source_results") or []),
        },
    )


def _validate_builder_workspace_payload(payload: Mapping[str, Any], *, workspace_id: str = "") -> None:
    flow_id = str(payload.get("flow_id") or "tailored_documents").strip()
    source_ids = [str(item).strip() for item in payload.get("source_ids") or [] if str(item).strip()]
    module_ids = [str(item).strip() for item in payload.get("module_ids") or [] if str(item).strip()]
    report = _builder_workspace_validation_report(
        flow_id=flow_id,
        source_ids=source_ids,
        module_ids=module_ids,
        settings=dict(payload.get("settings") or {}),
    )
    settings = dict(payload.get("settings") or {})
    if flow_id == "tailored_documents" and not str(
        settings.get("workspace_cv_asset_id") or payload.get("workspace_cv_asset_id") or ""
    ).strip():
        report["field_errors"] = _dedupe_field_errors(
            [
                *(report.get("field_errors") or []),
                _field_error(
                    "workspace_cv_asset_id",
                    "required",
                    "Select a workspace CV before saving or running this workspace.",
                ),
            ]
        )
        report["valid"] = False
    if report["valid"]:
        return
    _raise_builder_validation_error(
        error_code="workspace_validation_failed",
        message="Workspace validation failed.",
        phase="save",
        workspace_id=workspace_id,
        report=report,
    )


def _validate_builder_workspace_definition(
    workspace: WorkspaceDefinition,
    *,
    phase: str,
    error_code: str,
    run_plan_settings: Mapping[str, Any] | None = None,
    object_storage: Any = None,
) -> None:
    if not _is_builder_created_workspace(workspace):
        return

    report = _builder_workspace_validation_report(
        flow_id=_builder_workspace_flow_id(workspace),
        source_ids=_builder_workspace_source_ids(workspace),
        module_ids=_builder_workspace_module_ids(workspace),
        settings=dict(workspace.settings or {}),
    )
    configured_source_ids = _builder_workspace_connector_source_ids(workspace)
    if sorted(configured_source_ids) != sorted(_builder_workspace_source_ids(workspace)):
        report["field_errors"] = _dedupe_field_errors(
            [
                *(report.get("field_errors") or []),
                _field_error(
                    "source_ids",
                    "source_configuration_mismatch",
                    "Saved source_ids do not match the workspace connector configuration.",
                ),
            ]
        )
    if sorted(_builder_workspace_enabled_module_ids(workspace)) != sorted(
        _builder_workspace_module_ids(workspace)
    ):
        report["field_errors"] = _dedupe_field_errors(
            [
                *(report.get("field_errors") or []),
                _field_error(
                    "module_ids",
                    "module_configuration_mismatch",
                    "Saved module_ids do not match the enabled workspace automation modules.",
                ),
            ]
        )
    if phase == "run_preflight" and run_plan_settings is not None:
        cv_field_errors = _builder_workspace_run_preflight_field_errors(
            workspace,
            run_plan_settings=run_plan_settings,
            object_storage=object_storage,
        )
    else:
        cv_field_errors = _builder_workspace_cv_asset_field_errors(workspace, object_storage=object_storage)
    merged_field_errors = _dedupe_field_errors([*(report.get("field_errors") or []), *cv_field_errors])
    report["field_errors"] = merged_field_errors
    report["valid"] = not merged_field_errors
    if report["valid"]:
        return
    _raise_builder_validation_error(
        error_code=error_code,
        message="Workspace validation failed." if phase == "save" else "Run preflight failed.",
        phase=phase,
        workspace_id=workspace.id,
        report=report,
    )


def _load_scrapeops_admin_policy(repositories: BackendRepositories) -> dict[str, Any]:
    config_store = getattr(repositories, "config_store", None)
    if config_store is None or not hasattr(config_store, "get_value"):
        return default_scrapeops_admin_policy()
    payload = config_store.get_value(SCRAPEOPS_ADMIN_POLICY_CONFIG_KEY, default_scrapeops_admin_policy())
    return normalize_scrapeops_admin_policy(payload if isinstance(payload, Mapping) else {})


def _save_scrapeops_admin_policy(repositories: BackendRepositories, payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_scrapeops_admin_policy(payload)
    normalized["updated_at"] = utc_now_iso()
    config_store = getattr(repositories, "config_store", None)
    if config_store is None or not hasattr(config_store, "set_value"):
        raise ValueError("The configured repository does not support app configuration persistence.")
    config_store.set_value(SCRAPEOPS_ADMIN_POLICY_CONFIG_KEY, normalized)
    return normalized


def _effective_scrapeops_policy_limits(
    repositories: BackendRepositories,
    *,
    user_id: str,
    plan_id: str,
    quota_overrides: Mapping[str, Any] | None = None,
) -> dict[str, int | str]:
    admin_policy = _load_scrapeops_admin_policy(repositories)
    limits = plan_policy_limits(
        admin_policy,
        plan_id=plan_id,
        user_id=user_id,
    )
    if isinstance(quota_overrides, Mapping):
        for field_name in ("runner_credits_per_month", "company_sites_per_run", "runner_credits_per_run"):
            override_value = quota_overrides.get(field_name)
            if override_value in {None, ""}:
                continue
            try:
                limits[field_name] = int(override_value)
            except (TypeError, ValueError):
                continue
    return limits


def _plan_limit_for_user(
    repositories: BackendRepositories,
    *,
    user_id: str,
    plan_id: str,
    limit_type: str,
    quota_overrides: Mapping[str, Any] | None = None,
) -> int:
    limits = _effective_scrapeops_policy_limits(
        repositories,
        user_id=user_id,
        plan_id=plan_id,
        quota_overrides=quota_overrides,
    )
    if limit_type in limits:
        return int(limits.get(limit_type) or 0)
    return int(get_limit(plan_id, limit_type))


def _company_site_discovery_paths_for_source_id(source_id: str) -> tuple[Path, ...]:
    if str(source_id or "").strip() == BUILDER_CONNECTOR_SOURCE_IDS.get("academic_career_sites"):
        return tuple(ACADEMIC_CAREER_SITE_FILES)
    return tuple(REGULAR_COMPANY_SITE_FILES)


def _merge_company_site_entries(*raw_sources: Any) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen_urls = set()
    for raw_source in raw_sources:
        for entry in parse_company_site_entries(raw_source, limit=None):
            url = str(entry.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            merged.append(
                {
                    "company_name": str(entry.get("company_name") or "").strip(),
                    "url": url,
                }
            )
            seen_urls.add(url)
    return merged


def _current_company_site_policy_snapshot(
    repositories: Any,
    *,
    user_id: str,
    plan_id: str,
    quota_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    effective_limits = _effective_scrapeops_policy_limits(
        repositories,
        user_id=user_id,
        plan_id=plan_id,
        quota_overrides=quota_overrides,
    )
    normalized_plan_id = normalize_plan_id(effective_limits.get("plan_id") or plan_id)
    effective_quota_overrides = {
        **dict(quota_overrides or {}),
        "runner_credits_per_month": int(effective_limits.get("runner_credits_per_month") or 0),
    }
    runner_credit_usage = get_usage_snapshot(
        repositories,
        user_id,
        "runner_credits_per_month",
        normalized_plan_id,
        quota_overrides=effective_quota_overrides,
    )
    monthly_remaining = int(runner_credit_usage.get("remaining") or 0)
    per_run_budget = _plan_limit_for_user(
        repositories,
        user_id=user_id,
        plan_id=normalized_plan_id,
        limit_type="runner_credits_per_run",
        quota_overrides=effective_quota_overrides,
    )
    if per_run_budget == -1:
        effective_run_budget = monthly_remaining if monthly_remaining != -1 else -1
    elif monthly_remaining == -1:
        effective_run_budget = per_run_budget
    else:
        effective_run_budget = max(0, min(per_run_budget, monthly_remaining))
    return {
        "policy_version": SCRAPEOPS_POLICY_VERSION,
        "plan_id": normalized_plan_id,
        "runner_credits_per_month": runner_credit_usage,
        "company_sites_per_run": _plan_limit_for_user(
            repositories,
            user_id=user_id,
            plan_id=normalized_plan_id,
            limit_type="company_sites_per_run",
            quota_overrides=effective_quota_overrides,
        ),
        "runner_credits_per_run": per_run_budget,
        "effective_runner_credits_per_run": effective_run_budget,
    }


def _scrapeops_account_state() -> dict[str, Any]:
    api_key = str(os.getenv("SCRAPEOPS_API_KEY") or "").strip()
    if not api_key:
        return {
            "available": False,
            "status": "missing_api_key",
            "summary": "SCRAPEOPS_API_KEY is not configured.",
            "usage": {},
        }
    try:
        usage_payload = fetch_account_usage(api_key, timeout_seconds=6)
    except Exception as exc:
        return {
            "available": False,
            "status": "unavailable",
            "summary": str(exc),
            "usage": {},
        }
    usage_values = usage_payload.get("results") if isinstance(usage_payload.get("results"), Mapping) else usage_payload
    used = int(
        usage_values.get("API Credits Used")
        or usage_values.get("credits_used")
        or usage_values.get("used_api_credits")
        or 0
    )
    limit = int(
        usage_values.get("API Credit Limit")
        or usage_values.get("credit_limit")
        or usage_values.get("plan_api_credits")
        or 0
    )
    remaining = max(0, limit - used) if limit > 0 else 0
    status = "healthy" if remaining > 0 else "out_of_credits"
    summary = "ScrapeOps account is healthy." if remaining > 0 else "ScrapeOps account is out of credits."
    return {
        "available": True,
        "status": status,
        "summary": summary,
        "usage": {
            "used": used,
            "limit": limit,
            "remaining": remaining,
        },
    }


@dataclass(slots=True)
class BackendApplication:
    repositories: BackendRepositories
    registries: BackendRegistriesProtocol
    stage_engine: StageEngineProtocol
    object_storage: Any
    _workspace_catalog_service: WorkspaceCatalogService = field(init=False, repr=False)
    _identity_access_service: IdentityAccessService = field(init=False, repr=False)
    _assisted_apply_connection_service: AssistedApplyConnectionService = field(init=False, repr=False)
    _assisted_apply_package_service: ApplicationPackageService = field(init=False, repr=False)
    _tracker_application_service: TrackerApplicationService = field(init=False, repr=False)
    _run_lifecycle_service: RunLifecycleService = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._workspace_catalog_service = WorkspaceCatalogService(
            repositories=self.repositories,
            registries=self.registries,
            validate_workspace=self._validate_workspace_definition,
        )
        self._identity_access_service = IdentityAccessService(repositories=self.repositories)
        self._assisted_apply_connection_service = AssistedApplyConnectionService(
            repositories=self.repositories
        )
        self._assisted_apply_package_service = ApplicationPackageService(
            repositories=self.repositories,
            object_storage=self.object_storage,
        )
        self._tracker_application_service = TrackerApplicationService(
            repositories=self.repositories,
            build_relevant_people_discovery=lambda **kwargs: build_relevant_people_discovery(**kwargs),
        )
        self._run_lifecycle_service = RunLifecycleService(
            repositories=self.repositories,
            registries=self.registries,
            stage_engine=self.stage_engine,
            validate_workspace=self._validate_workspace_definition,
            validation_error_type=BackendValidationError,
            resolve_runtime_value=self.resolve_runtime_value,
            review_is_actionable_tracker_item=self._tracker_application_service.review_is_actionable_tracker_item,
            find_duplicate_user_tracker_posting=self._tracker_application_service.find_duplicate_user_tracker_posting,
            auto_approve_generated_job_reviews=self._auto_approve_generated_job_reviews,
            enqueue_due_scheduled_runs=self.enqueue_due_scheduled_runs,
            object_storage=self.object_storage,
        )

    def _validate_workspace_definition(
        self,
        workspace: WorkspaceDefinition,
        *,
        phase: str,
        error_code: str,
        run_plan_settings: Mapping[str, Any] | None = None,
    ) -> None:
        _validate_builder_workspace_definition(
            workspace,
            phase=phase,
            error_code=error_code,
            run_plan_settings=run_plan_settings,
            object_storage=self.object_storage,
        )

    def list_workspaces(self):
        return self._workspace_catalog_service.list_workspaces()

    def get_workspace(self, workspace_id: str):
        return self._workspace_catalog_service.get_workspace(workspace_id)

    def upsert_workspace(self, payload: Mapping[str, Any] | WorkspaceDefinition):
        return self._workspace_catalog_service.upsert_workspace(payload)

    def delete_workspace(self, workspace_id: str) -> None:
        self._workspace_catalog_service.delete_workspace(workspace_id)

    def list_workflow_templates(self):
        return self._workspace_catalog_service.list_workflow_templates()

    def get_workflow_template(self, template_id: str):
        return self._workspace_catalog_service.get_workflow_template(template_id)

    def emit_event(
        self,
        event_name: str,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
        run_id: str | None = None,
        job_id: str | None = None,
        review_id: str | None = None,
        session_id: str | None = None,
        route: str = "",
        source: str = "",
        payload: Mapping[str, Any] | None = None,
        **extra_payload,
    ) -> None:
        analytics_store = getattr(self.repositories, "analytics_store", None)
        if analytics_store is None or not hasattr(analytics_store, "emit_event"):
            return
        try:
            merged_payload = dict(payload or {})
            merged_payload.update(extra_payload)
            analytics_store.emit_event(
                event_id=f"evt_{uuid4().hex[:16]}",
                event_name=str(event_name or "").strip(),
                occurred_at=utc_now_iso(),
                user_id=str(user_id or "").strip(),
                workspace_id=str(workspace_id or "").strip(),
                run_id=str(run_id or "").strip(),
                job_id=str(job_id or "").strip(),
                review_id=str(review_id or "").strip(),
                session_id=str(session_id or "").strip(),
                route=str(route or "").strip(),
                source=str(source or "").strip(),
                payload={key: value for key, value in merged_payload.items() if value is not None},
            )
        except Exception:
            logging.getLogger("backend.analytics").exception(
                "Failed to emit analytics event '%s'.",
                event_name,
            )

    def get_analytics_overview(self) -> dict[str, Any]:
        analytics_store = getattr(self.repositories, "analytics_store", None)
        query_rows = getattr(analytics_store, "query_rows", None)
        if not callable(query_rows):
            raise ValueError("Analytics overview requires the sqlite storage backend.")

        queries: dict[str, str] = {
            "automation_success_rate": """
                SELECT
                  date(created_at) AS day,
                  COUNT(*) AS total_runs,
                  SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_runs,
                  ROUND(
                    100.0 * SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) / COUNT(*),
                    1
                  ) AS success_rate_pct
                FROM runs
                GROUP BY date(created_at)
                ORDER BY day DESC
            """,
            "automation_failure_rate_by_stage_type": """
                SELECT
                  stage_type,
                  COUNT(*) AS failed_steps
                FROM run_stage_results
                WHERE status = 'failed'
                GROUP BY stage_type
                ORDER BY failed_steps DESC
            """,
            "jobs_discovered_by_source": """
                SELECT
                  COALESCE(NULLIF(portal, ''), NULLIF(source_type, ''), 'unknown') AS source,
                  COUNT(*) AS jobs
                FROM run_jobs
                GROUP BY 1
                ORDER BY jobs DESC
            """,
            "screening_generation_funnel": """
                SELECT
                  stage_type,
                  SUM(COALESCE(CAST(json_extract(metrics_json, '$.jobs_found') AS INTEGER), 0)) AS jobs_found,
                  SUM(COALESCE(CAST(json_extract(metrics_json, '$.approved') AS INTEGER), 0)) AS approved,
                  SUM(COALESCE(CAST(json_extract(metrics_json, '$.rejected') AS INTEGER), 0)) AS rejected,
                  SUM(COALESCE(CAST(json_extract(metrics_json, '$.generated_jobs') AS INTEGER), 0)) AS generated_jobs,
                  SUM(COALESCE(CAST(json_extract(metrics_json, '$.packaged_jobs') AS INTEGER), 0)) AS packaged_jobs
                FROM run_stage_results
                GROUP BY stage_type
                ORDER BY stage_type
            """,
            "applications_per_user": """
                WITH run_owners AS (
                  SELECT id AS run_id, user_id
                  FROM runs
                  WHERE user_id != ''
                )
                SELECT
                  ro.user_id,
                  COUNT(*) AS approved_reviews,
                  SUM(
                    CASE
                      WHEN COALESCE(json_extract(r.payload_json, '$.metadata.tracker_status'), '') != ''
                      THEN 1 ELSE 0
                    END
                  ) AS explicit_tracker_updates,
                  SUM(
                    CASE
                      WHEN COALESCE(json_extract(r.payload_json, '$.metadata.email_confirmed'), 0) = 1
                      THEN 1 ELSE 0
                    END
                  ) AS email_confirmed
                FROM reviews r
                JOIN run_owners ro ON ro.run_id = r.run_id
                WHERE json_extract(r.payload_json, '$.decision') = 'approved'
                GROUP BY ro.user_id
                ORDER BY email_confirmed DESC, approved_reviews DESC
            """,
            "quick_apply_adoption": """
                SELECT
                  date(created_at) AS day,
                  COUNT(*) AS quick_apply_runs,
                  SUM(COALESCE(CAST(json_extract(metadata_json, '$.accepted_url_count') AS INTEGER), 0)) AS accepted_urls
                FROM runs
                WHERE json_extract(metadata_json, '$.run_kind') = 'quick_apply'
                GROUP BY date(created_at)
                ORDER BY day DESC
            """,
            "referral_outreach_funnel": """
                SELECT
                  u.user_id,
                  COUNT(ro.key) AS outreach_records,
                  SUM(CASE WHEN json_extract(ro.value, '$.outreach_status') = 'Not contacted' THEN 1 ELSE 0 END) AS not_contacted,
                  SUM(CASE WHEN json_extract(ro.value, '$.outreach_status') = 'Contacted' THEN 1 ELSE 0 END) AS contacted,
                  SUM(CASE WHEN json_extract(ro.value, '$.outreach_status') = 'Replied' THEN 1 ELSE 0 END) AS replied,
                  SUM(CASE WHEN json_extract(ro.value, '$.outreach_status') = 'Referral offered' THEN 1 ELSE 0 END) AS referral_offered,
                  SUM(CASE WHEN json_extract(ro.value, '$.outreach_status') = 'No referral' THEN 1 ELSE 0 END) AS no_referral
                FROM users u
                LEFT JOIN json_each(COALESCE(json_extract(u.payload_json, '$.metadata.referral_outreach'), '{}')) ro
                GROUP BY u.user_id
                ORDER BY referral_offered DESC, replied DESC
            """,
            "users_with_repeated_failures": """
                WITH run_owners AS (
                  SELECT id AS run_id, user_id
                  FROM runs
                  WHERE user_id != ''
                )
                SELECT
                  ro.user_id,
                  rs.stage_type,
                  rs.error,
                  COUNT(*) AS occurrences
                FROM run_stage_results rs
                JOIN run_owners ro ON ro.run_id = rs.run_id
                WHERE rs.status = 'failed'
                GROUP BY ro.user_id, rs.stage_type, rs.error
                HAVING COUNT(*) >= 2
                ORDER BY occurrences DESC
            """,
            "users_not_returned_after_signup": """
                SELECT
                  u.user_id,
                  json_extract(u.payload_json, '$.created_at') AS user_created_at,
                  MAX(json_extract(t.payload_json, '$.last_used_at')) AS last_token_use
                FROM users u
                LEFT JOIN api_tokens t ON t.user_id = u.user_id AND t.is_active = 1
                GROUP BY u.user_id
                HAVING COALESCE(MAX(json_extract(t.payload_json, '$.last_used_at')), '') = ''
            """,
            "most_successful_job_sources": """
                SELECT
                  COALESCE(NULLIF(j.portal, ''), NULLIF(j.source_type, ''), 'unknown') AS source,
                  COUNT(*) AS reviewed_jobs,
                  SUM(
                    CASE
                      WHEN json_extract(r.payload_json, '$.metadata.application_status') IN ('Interviewing', 'Offer')
                      THEN 1 ELSE 0
                    END
                  ) AS positive_outcomes
                FROM run_jobs j
                JOIN reviews r
                  ON r.run_id = j.run_id
                 AND r.job_id = j.job_id
                GROUP BY 1
                ORDER BY positive_outcomes DESC, reviewed_jobs DESC
            """,
        }
        overview = {"generated_at": utc_now_iso()}
        for metric_name, sql in queries.items():
            overview[metric_name] = query_rows(sql)
        return overview

    def list_analytics_events(
        self,
        *,
        limit: int,
        offset: int,
        event_name: str = "",
        user_id: str = "",
        occurred_from: str = "",
        occurred_to: str = "",
    ) -> dict[str, Any]:
        analytics_store = getattr(self.repositories, "analytics_store", None)
        list_events = getattr(analytics_store, "list_events", None)
        count_events = getattr(analytics_store, "count_events", None)
        if not callable(list_events) or not callable(count_events):
            raise ValueError("Analytics event listing requires analytics storage support.")

        normalized_filters = {
            "event_name": str(event_name or "").strip(),
            "user_id": str(user_id or "").strip(),
            "occurred_from": str(occurred_from or "").strip(),
            "occurred_to": str(occurred_to or "").strip(),
        }
        return {
            "events": list_events(limit=int(limit), offset=int(offset), **normalized_filters),
            "total": int(count_events(**normalized_filters)),
        }

    def _scrapeops_event_rows(
        self,
        *,
        user_id: str = "",
        workspace_id: str = "",
        run_id: str = "",
        occurred_from: str = "",
        occurred_to: str = "",
    ) -> list[dict[str, Any]]:
        analytics_store = getattr(self.repositories, "analytics_store", None)
        query_rows = getattr(analytics_store, "query_rows", None)
        if not callable(query_rows):
            raise ValueError("ScrapeOps usage reporting requires analytics storage support.")
        filters = ["event_name = ?"]
        params: list[Any] = [SCRAPEOPS_USAGE_EVENT_NAME]
        if str(user_id or "").strip():
            filters.append("user_id = ?")
            params.append(str(user_id).strip())
        if str(workspace_id or "").strip():
            filters.append("workspace_id = ?")
            params.append(str(workspace_id).strip())
        if str(run_id or "").strip():
            filters.append("run_id = ?")
            params.append(str(run_id).strip())
        if str(occurred_from or "").strip():
            filters.append("occurred_at >= ?")
            params.append(str(occurred_from).strip())
        if str(occurred_to or "").strip():
            filters.append("occurred_at < ?")
            params.append(str(occurred_to).strip())
        where_clause = " AND ".join(filters)
        rows = query_rows(
            (
                "SELECT occurred_at, user_id, workspace_id, run_id, payload_json "
                f"FROM analytics_events WHERE {where_clause} "
                "ORDER BY occurred_at DESC"
            ),
            tuple(params),
        )
        events: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row.get("payload_json") or "{}")
            if not isinstance(payload, dict):
                payload = {}
            events.append(
                {
                    "occurred_at": str(row.get("occurred_at") or ""),
                    "user_id": str(row.get("user_id") or ""),
                    "workspace_id": str(row.get("workspace_id") or ""),
                    "run_id": str(row.get("run_id") or ""),
                    **payload,
                }
            )
        return events

    def get_scrapeops_usage_summary(
        self,
        *,
        user_id: str = "",
        workspace_id: str = "",
        run_id: str = "",
        occurred_from: str = "",
        occurred_to: str = "",
    ) -> dict[str, Any]:
        events = self._scrapeops_event_rows(
            user_id=user_id,
            workspace_id=workspace_id,
            run_id=run_id,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
        )
        totals = {
            "requests": len(events),
            "billed_requests": 0,
            "failed_requests": 0,
            "runner_credits": 0,
            "native_credits": 0,
        }
        by_mode: dict[str, dict[str, Any]] = {}
        by_domain: dict[str, dict[str, Any]] = {}
        by_run: dict[str, dict[str, Any]] = {}
        for event in events:
            billed = bool(event.get("billed"))
            runner_credits = int(event.get("runner_credits") or 0)
            native_credits = int(event.get("native_credits") or 0)
            request_mode = str(event.get("request_mode") or "basic").strip() or "basic"
            domain = str(event.get("domain") or "unknown").strip() or "unknown"
            event_run_id = str(event.get("run_id") or "").strip()
            totals["runner_credits"] += runner_credits
            totals["native_credits"] += native_credits
            if billed:
                totals["billed_requests"] += 1
            else:
                totals["failed_requests"] += 1

            mode_bucket = by_mode.setdefault(
                request_mode,
                {"request_mode": request_mode, "requests": 0, "billed_requests": 0, "runner_credits": 0, "native_credits": 0},
            )
            mode_bucket["requests"] += 1
            mode_bucket["runner_credits"] += runner_credits
            mode_bucket["native_credits"] += native_credits
            if billed:
                mode_bucket["billed_requests"] += 1

            domain_bucket = by_domain.setdefault(
                domain,
                {"domain": domain, "requests": 0, "billed_requests": 0, "runner_credits": 0, "native_credits": 0},
            )
            domain_bucket["requests"] += 1
            domain_bucket["runner_credits"] += runner_credits
            domain_bucket["native_credits"] += native_credits
            if billed:
                domain_bucket["billed_requests"] += 1

            if event_run_id:
                run_bucket = by_run.setdefault(
                    event_run_id,
                    {
                        "run_id": event_run_id,
                        "requests": 0,
                        "billed_requests": 0,
                        "runner_credits": 0,
                        "native_credits": 0,
                        "jobs_found": 0,
                        "runner_credits_per_job": 0,
                    },
                )
                run_bucket["requests"] += 1
                run_bucket["runner_credits"] += runner_credits
                run_bucket["native_credits"] += native_credits
                if billed:
                    run_bucket["billed_requests"] += 1

        job_store = getattr(self.repositories, "job_store", None)
        load_all_job_sets = getattr(job_store, "load_all_job_sets", None)
        if callable(load_all_job_sets):
            for run_bucket in by_run.values():
                run_id_value = str(run_bucket.get("run_id") or "")
                try:
                    job_sets = load_all_job_sets(run_id_value)
                except Exception:
                    continue
                seen_job_ids: set[str] = set()
                jobs_found = 0
                for jobs in job_sets.values():
                    for job_record in jobs:
                        job_payload = job_record.to_dict() if hasattr(job_record, "to_dict") else dict(job_record or {})
                        source_type = str(job_payload.get("source_type") or "").strip()
                        portal = str(job_payload.get("portal") or "").strip()
                        if source_type != "company_career_site" and portal != "company_career_site":
                            continue
                        job_id = str(
                            job_payload.get("job_id")
                            or job_payload.get("apply_link")
                            or job_payload.get("source_url")
                            or job_payload.get("link")
                            or ""
                        ).strip()
                        if job_id and job_id in seen_job_ids:
                            continue
                        if job_id:
                            seen_job_ids.add(job_id)
                        jobs_found += 1
                run_bucket["jobs_found"] = jobs_found
                run_bucket["runner_credits_per_job"] = (
                    round(float(run_bucket["runner_credits"]) / jobs_found, 2) if jobs_found > 0 else 0
                )

        return {
            "filters": {
                "user_id": str(user_id or "").strip(),
                "workspace_id": str(workspace_id or "").strip(),
                "run_id": str(run_id or "").strip(),
                "occurred_from": str(occurred_from or "").strip(),
                "occurred_to": str(occurred_to or "").strip(),
            },
            "totals": totals,
            "by_request_mode": sorted(by_mode.values(), key=lambda item: (-int(item["runner_credits"]), str(item["request_mode"]))),
            "by_domain": sorted(by_domain.values(), key=lambda item: (-int(item["runner_credits"]), str(item["domain"]))),
            "by_run": sorted(by_run.values(), key=lambda item: (-int(item["runner_credits"]), str(item["run_id"]))),
        }

    def get_scrapeops_user_usage_summary(
        self,
        *,
        user_id: str,
        plan_id: str,
        quota_overrides: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        current_period = datetime.now(timezone.utc).strftime("%Y-%m")
        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        usage = self.get_scrapeops_usage_summary(
            user_id=user_id,
            occurred_from=month_start.isoformat(),
        )
        policy_snapshot = _current_company_site_policy_snapshot(
            self.repositories,
            user_id=user_id,
            plan_id=plan_id,
            quota_overrides=quota_overrides,
        )
        return {
            "period": current_period,
            "policy": policy_snapshot,
            "usage": usage,
        }

    def get_scrapeops_reconciliation(self, *, date: str = "") -> dict[str, Any]:
        account_state = _scrapeops_account_state()
        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        internal_usage = self.get_scrapeops_usage_summary(occurred_from=month_start.isoformat())
        internal_native_credits = int(internal_usage.get("totals", {}).get("native_credits") or 0)
        remote_usage = dict(account_state.get("usage") or {})
        remote_used_credits = int(remote_usage.get("used") or 0)
        discrepancy = remote_used_credits - internal_native_credits
        domain_stats: dict[str, Any] = {}
        if account_state.get("available"):
            try:
                domain_stats = fetch_domain_stats(
                    str(os.getenv("SCRAPEOPS_API_KEY") or "").strip(),
                    date=str(date or "").strip(),
                    timeout_seconds=6,
                )
            except Exception as exc:
                domain_stats = {"error": str(exc)}
        return {
            "generated_at": utc_now_iso(),
            "account_state": account_state,
            "internal_native_credits": internal_native_credits,
            "remote_used_credits": remote_used_credits,
            "discrepancy": discrepancy,
            "domain_stats": domain_stats,
        }

    def get_scrapeops_admin_policy(self) -> dict[str, Any]:
        return _load_scrapeops_admin_policy(self.repositories)

    def save_scrapeops_admin_policy(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        normalized = _save_scrapeops_admin_policy(self.repositories, payload)
        self.emit_event(
            "scrapeops_admin_policy_updated",
            source="admin",
            payload={
                "policy_version": str(normalized.get("policy_version") or ""),
                "updated_at": str(normalized.get("updated_at") or ""),
                "domain_policy_count": len(normalized.get("domain_policies") or []),
                "user_override_count": len(normalized.get("user_overrides") or []),
            },
        )
        return normalized

    def build_scrapeops_quota_overrides(
        self,
        *,
        user_id: str,
        plan_id: str,
        quota_overrides: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        limits = _effective_scrapeops_policy_limits(
            self.repositories,
            user_id=user_id,
            plan_id=plan_id,
            quota_overrides=quota_overrides,
        )
        return {
            **dict(quota_overrides or {}),
            "runner_credits_per_month": int(limits.get("runner_credits_per_month") or 0),
            "company_sites_per_run": int(limits.get("company_sites_per_run") or 0),
            "runner_credits_per_run": int(limits.get("runner_credits_per_run") or 0),
        }

    def _list_named_analytics_events(
        self,
        *,
        event_name: str,
        occurred_from: str = "",
        occurred_to: str = "",
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        analytics_store = getattr(self.repositories, "analytics_store", None)
        list_events = getattr(analytics_store, "list_events", None)
        if not callable(list_events):
            return []
        return list_events(
            limit=max(1, int(limit)),
            offset=0,
            event_name=str(event_name or "").strip(),
            occurred_from=str(occurred_from or "").strip(),
            occurred_to=str(occurred_to or "").strip(),
        )

    def get_scrapeops_usage_series(
        self,
        *,
        user_id: str = "",
        workspace_id: str = "",
        run_id: str = "",
        occurred_from: str = "",
        occurred_to: str = "",
        days: int = 30,
    ) -> list[dict[str, Any]]:
        if not str(occurred_from or "").strip():
            occurred_from = (
                datetime.now(timezone.utc)
                .replace(hour=0, minute=0, second=0, microsecond=0)
                - timedelta(days=max(1, int(days)) - 1)
            ).isoformat()
        events = self._scrapeops_event_rows(
            user_id=user_id,
            workspace_id=workspace_id,
            run_id=run_id,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
        )
        by_day: dict[str, dict[str, Any]] = {}
        for event in events:
            day = str(event.get("occurred_at") or "")[:10]
            if not day:
                continue
            bucket = by_day.setdefault(
                day,
                {
                    "day": day,
                    "requests": 0,
                    "billed_requests": 0,
                    "failed_requests": 0,
                    "runner_credits": 0,
                    "native_credits": 0,
                },
            )
            bucket["requests"] += 1
            if bool(event.get("billed")):
                bucket["billed_requests"] += 1
            else:
                bucket["failed_requests"] += 1
            bucket["runner_credits"] += int(event.get("runner_credits") or 0)
            bucket["native_credits"] += int(event.get("native_credits") or 0)
        return [by_day[key] for key in sorted(by_day)]

    def get_scrapeops_reconciliation_history(self, *, days: int = 30) -> list[dict[str, Any]]:
        occurred_from = (
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(days=max(1, int(days)) - 1)
        ).isoformat()
        events = self._list_named_analytics_events(
            event_name=SCRAPEOPS_RECONCILIATION_EVENT_NAME,
            occurred_from=occurred_from,
            limit=max(100, int(days) * 8),
        )
        history: list[dict[str, Any]] = []
        for event in reversed(events):
            payload = dict(event.get("payload") or {})
            account_state = dict(payload.get("account_state") or {})
            account_usage = dict(account_state.get("usage") or {})
            history.append(
                {
                    "day": str(event.get("occurred_at") or "")[:10],
                    "occurred_at": str(event.get("occurred_at") or ""),
                    "remote_used_credits": int(payload.get("remote_used_credits") or 0),
                    "internal_native_credits": int(payload.get("internal_native_credits") or 0),
                    "discrepancy": int(payload.get("discrepancy") or 0),
                    "remaining_credits": int(account_usage.get("remaining") or 0),
                    "account_status": str(account_state.get("status") or ""),
                }
            )
        return history

    def get_scrapeops_alert_history(self, *, days: int = 30, limit: int = 50) -> dict[str, Any]:
        occurred_from = (
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(days=max(1, int(days)) - 1)
        ).isoformat()
        events = self._list_named_analytics_events(
            event_name=SCRAPEOPS_ALERT_EVENT_NAME,
            occurred_from=occurred_from,
            limit=max(int(limit), int(days) * 8),
        )
        latest: list[dict[str, Any]] = []
        by_day: dict[str, dict[str, Any]] = {}
        for event in events:
            payload = dict(event.get("payload") or {})
            occurred_at = str(event.get("occurred_at") or "")
            day = occurred_at[:10]
            severity = str(payload.get("severity") or "warning")
            bucket = by_day.setdefault(day, {"day": day, "alerts": 0, "critical_alerts": 0})
            bucket["alerts"] += 1
            if severity in {"critical", "error"}:
                bucket["critical_alerts"] += 1
            latest.append(
                {
                    "occurred_at": occurred_at,
                    "alert_type": str(payload.get("alert_type") or ""),
                    "severity": severity,
                    "message": str(payload.get("message") or ""),
                }
            )
        latest.sort(key=lambda item: str(item.get("occurred_at") or ""), reverse=True)
        return {
            "latest": latest[: max(1, int(limit))],
            "series": [by_day[key] for key in sorted(by_day)],
        }

    def run_scrapeops_reconciliation_cycle(self, *, force: bool = False, source: str = "system") -> dict[str, Any]:
        policy = self.get_scrapeops_admin_policy()
        alert_policy = dict(policy.get("alert_policy") or {})
        cadence_hours = max(1, int(alert_policy.get("cadence_hours") or 6))
        now = datetime.now(timezone.utc)
        bucket_hour = now.hour - (now.hour % cadence_hours)
        bucket_start = now.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)
        bucket_end = bucket_start + timedelta(hours=cadence_hours)
        bucket_key = bucket_start.strftime("%Y%m%d%H")
        if not force:
            existing = self._list_named_analytics_events(
                event_name=SCRAPEOPS_RECONCILIATION_EVENT_NAME,
                occurred_from=bucket_start.isoformat(),
                occurred_to=bucket_end.isoformat(),
                limit=1,
            )
            if existing:
                return {
                    "status": "skipped",
                    "reason": "not_due",
                    "snapshot": dict(existing[0].get("payload") or {}),
                    "alerts": [],
                }

        snapshot = self.get_scrapeops_reconciliation(date=now.strftime("%Y-%m-%d"))
        snapshot_payload = {
            **snapshot,
            "bucket_start": bucket_start.isoformat(),
            "bucket_end": bucket_end.isoformat(),
            "policy_version": str(policy.get("policy_version") or SCRAPEOPS_POLICY_VERSION),
            "source": str(source or "system"),
        }
        self.emit_event(
            SCRAPEOPS_RECONCILIATION_EVENT_NAME,
            source=source,
            payload=snapshot_payload,
        )

        alerts: list[dict[str, Any]] = []
        account_state = dict(snapshot.get("account_state") or {})
        account_usage = dict(account_state.get("usage") or {})
        discrepancy = int(snapshot.get("discrepancy") or 0)
        low_remaining_threshold = max(0, int(alert_policy.get("low_remaining_credits_threshold") or 0))
        discrepancy_threshold = max(0, int(alert_policy.get("discrepancy_threshold") or 0))

        if str(account_state.get("status") or "") == "out_of_credits":
            alerts.append(
                {
                    "alert_type": "out_of_credits",
                    "severity": "critical",
                    "message": "ScrapeOps account is out of credits.",
                }
            )
        elif account_state.get("available") and low_remaining_threshold > 0 and int(account_usage.get("remaining") or 0) <= low_remaining_threshold:
            alerts.append(
                {
                    "alert_type": "low_remaining_credits",
                    "severity": "warning",
                    "message": (
                        f"ScrapeOps account is below the remaining-credit threshold "
                        f"({int(account_usage.get('remaining') or 0)} <= {low_remaining_threshold})."
                    ),
                }
            )
        if discrepancy_threshold > 0 and abs(discrepancy) >= discrepancy_threshold:
            alerts.append(
                {
                    "alert_type": "reconciliation_discrepancy",
                    "severity": "warning",
                    "message": (
                        f"ScrapeOps reconciliation discrepancy reached {discrepancy}, "
                        f"which exceeds the threshold of {discrepancy_threshold}."
                    ),
                }
            )

        for alert in alerts:
            self.emit_event(
                SCRAPEOPS_ALERT_EVENT_NAME,
                source=source,
                payload={
                    **alert,
                    "bucket_key": bucket_key,
                    "snapshot_generated_at": str(snapshot.get("generated_at") or ""),
                    "account_status": str(account_state.get("status") or ""),
                    "remaining_credits": int(account_usage.get("remaining") or 0),
                    "discrepancy": discrepancy,
                },
            )

        return {
            "status": "completed",
            "snapshot": snapshot_payload,
            "alerts": alerts,
        }

    def maybe_run_scheduled_scrapeops_maintenance(self, *, source: str = "system") -> dict[str, Any]:
        policy = self.get_scrapeops_admin_policy()
        alert_policy = dict(policy.get("alert_policy") or {})
        if not bool(alert_policy.get("enabled", True)):
            return {"status": "disabled", "reason": "alert_policy_disabled"}
        try:
            return self.run_scrapeops_reconciliation_cycle(force=False, source=source)
        except Exception as exc:
            self.emit_event(
                SCRAPEOPS_ALERT_EVENT_NAME,
                source=source,
                payload={
                    "alert_type": "reconciliation_cycle_failed",
                    "severity": "warning",
                    "message": str(exc),
                },
            )
            return {"status": "failed", "reason": str(exc)}

    def get_scrapeops_admin_dashboard(
        self,
        *,
        user_id: str = "",
        workspace_id: str = "",
        run_id: str = "",
        occurred_from: str = "",
        occurred_to: str = "",
        date: str = "",
    ) -> dict[str, Any]:
        policy = self.get_scrapeops_admin_policy()
        history_days = max(7, int(dict(policy.get("alert_policy") or {}).get("history_days") or 30))
        usage = self.get_scrapeops_usage_summary(
            user_id=user_id,
            workspace_id=workspace_id,
            run_id=run_id,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
        )
        return {
            "policy": policy,
            "usage": usage,
            "usage_series": self.get_scrapeops_usage_series(
                user_id=user_id,
                workspace_id=workspace_id,
                run_id=run_id,
                occurred_from=occurred_from,
                occurred_to=occurred_to,
                days=history_days,
            ),
            "reconciliation": self.get_scrapeops_reconciliation(date=date),
            "reconciliation_series": self.get_scrapeops_reconciliation_history(days=history_days),
            "alerts": self.get_scrapeops_alert_history(days=history_days),
        }

    def upsert_workflow_template(self, payload: Mapping[str, Any] | WorkflowTemplate):
        return self._workspace_catalog_service.upsert_workflow_template(payload)

    def delete_workflow_template(self, template_id: str) -> None:
        self._workspace_catalog_service.delete_workflow_template(template_id)

    def list_connectors(self):
        return self._workspace_catalog_service.list_connectors()

    def list_generations(self):
        return self._workspace_catalog_service.list_generations()

    def list_renderers(self):
        return self._workspace_catalog_service.list_renderers()

    def get_workspace_builder_catalog(self) -> dict[str, Any]:
        return self._workspace_catalog_service.get_workspace_builder_catalog()

    def validate_workspace_builder_sources(
        self,
        payload: Mapping[str, Any],
        *,
        user_id: str = "",
        plan_id: str = "",
        quota_overrides: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        report = validate_workspace_source_configuration(dict(payload))
        source_ids = [str(item).strip() for item in report.get("source_ids") or [] if str(item).strip()]
        if not source_ids:
            return report

        selected_company_sources = [
            source_id
            for source_id in source_ids
            if source_id in {SOURCE_COMPANY_CAREER_SITES, SOURCE_ACADEMIC_CAREER_SITES}
        ]
        if not selected_company_sources:
            return report

        effective_settings = dict(payload.get("settings") or {})
        for key, value in dict(report.get("derived_runtime_defaults") or {}).items():
            current_value = effective_settings.get(key)
            if key not in effective_settings or current_value is None or current_value == "" or current_value == [] or current_value == {}:
                effective_settings[key] = value

        locality_mode = str(effective_settings.get("company_site_locality_mode") or "local_preferred").strip() or "local_preferred"
        account_state = _scrapeops_account_state()
        admin_policy = self.get_scrapeops_admin_policy()
        active_domain_policies = [
            dict(item)
            for item in admin_policy.get("domain_policies") or []
            if isinstance(item, Mapping) and bool(item.get("is_active", True))
        ]
        policy_snapshot = (
            _current_company_site_policy_snapshot(
                self.repositories,
                user_id=user_id,
                plan_id=plan_id,
                quota_overrides=quota_overrides,
            )
            if user_id and plan_id
            else {}
        )
        runtime_quota_overrides = (
            self.build_scrapeops_quota_overrides(
                user_id=user_id,
                plan_id=plan_id,
                quota_overrides=quota_overrides,
            )
            if user_id and plan_id
            else dict(quota_overrides or {})
        )
        source_results = list(report.get("source_results") or [])
        updated_results: list[dict[str, Any]] = []
        for result in source_results:
            source_id = str(result.get("source_id") or "").strip()
            if source_id not in {SOURCE_COMPANY_CAREER_SITES, SOURCE_ACADEMIC_CAREER_SITES}:
                updated_results.append(result)
                continue
            configured_sites = effective_settings.get(source_id) or []
            discovered_sites = load_discovered_company_site_entries(
                _company_site_discovery_paths_for_source_id(source_id)
            )
            merged_sites = _merge_company_site_entries(configured_sites, discovered_sites)
            scope_plan = plan_company_site_scope(
                company_sites=merged_sites,
                target_country_codes=effective_settings.get("country_codes") or [],
                target_cities=effective_settings.get("cities") or [],
                locality_mode=locality_mode,
                max_sites_per_run=int(policy_snapshot.get("company_sites_per_run") or 0),
                domain_policies=active_domain_policies,
            )
            run_budget = int(policy_snapshot.get("effective_runner_credits_per_run") or 0)
            estimate = estimate_company_site_runner_credit_range(
                site_count=int(scope_plan.stats.get("selected_site_count") or 0),
                locality_mode=locality_mode,
                has_target_country=bool(effective_settings.get("country_codes") or []),
                run_credit_budget=run_budget,
            )
            details = list(result.get("details") or [])
            details.append(
                (
                    f"{int(scope_plan.stats.get('selected_site_count') or 0)} of "
                    f"{int(scope_plan.stats.get('input_site_count') or 0)} site(s) remain after locality filtering."
                )
            )
            if int(scope_plan.stats.get("plan_site_limit_applied_count") or 0) > 0:
                details.append(
                    f"Plan policy trims {int(scope_plan.stats['plan_site_limit_applied_count'])} site(s) from this run."
                )
            details.append(
                (
                    "Estimated runner credits: "
                    f"{int(estimate.get('min_runner_credits') or 0)}-"
                    f"{int(estimate.get('max_runner_credits') or 0)} "
                    f"(likely {int(estimate.get('likely_runner_credits') or 0)})."
                )
            )
            if policy_snapshot:
                remaining_runner_credits = dict(policy_snapshot.get("runner_credits_per_month") or {}).get("remaining")
                details.append(
                    "Remaining monthly runner credits: "
                    + ("Unlimited" if int(remaining_runner_credits or 0) == -1 else str(int(remaining_runner_credits or 0)))
                )
            source_field_errors = list(result.get("field_errors") or [])
            status = str(result.get("status") or "valid")
            summary = str(result.get("summary") or "")
            if account_state.get("status") in {"missing_api_key", "out_of_credits"}:
                status = "invalid"
                summary = str(account_state.get("summary") or summary)
                if summary and summary not in details:
                    details.insert(0, summary)
                source_field_errors.append(
                    _field_error(
                        "company_career_sites",
                        str(account_state.get("status") or "scrapeops_unavailable"),
                        str(account_state.get("summary") or "ScrapeOps is not available."),
                        source_id=source_id,
                    )
                )
            updated_results.append(
                {
                    **dict(result),
                    "status": status,
                    "summary": summary,
                    "details": details,
                    "field_errors": _dedupe_field_errors(source_field_errors),
                    "scope_plan": {
                        "selected_site_count": int(scope_plan.stats.get("selected_site_count") or 0),
                        "input_site_count": int(scope_plan.stats.get("input_site_count") or 0),
                        "skipped_site_count": int(scope_plan.stats.get("skipped_site_count") or 0),
                        "local_site_count": int(scope_plan.stats.get("local_site_count") or 0),
                        "global_site_count": int(scope_plan.stats.get("global_site_count") or 0),
                        "unknown_site_count": int(scope_plan.stats.get("unknown_site_count") or 0),
                    },
                    "runner_credit_estimate": estimate,
                }
            )

        report["source_results"] = updated_results
        report["field_errors"] = _dedupe_field_errors(
            [
                *(report.get("field_errors") or []),
                *[
                    item
                    for result in updated_results
                    if str(result.get("status") or "") == "invalid"
                    for item in result.get("field_errors") or []
                ],
            ]
        )
        report["valid"] = not report["field_errors"] and all(
            str(item.get("status") or "") == "valid" for item in updated_results
        )
        report["company_site_policy"] = {
            **dict(policy_snapshot or {}),
            "account_state": account_state,
            "locality_mode": locality_mode,
            "policy_version": SCRAPEOPS_POLICY_VERSION,
            "domain_policy_count": len(active_domain_policies),
        }
        report["policy_run_overrides"] = {
            "company_site_locality_mode": locality_mode,
            "company_site_max_sites_per_run": int(policy_snapshot.get("company_sites_per_run") or 0),
            "company_site_runner_credit_budget": int(policy_snapshot.get("effective_runner_credits_per_run") or 0),
            "company_site_max_job_links_per_site": 25,
            "company_site_policy_version": SCRAPEOPS_POLICY_VERSION,
            "scrapeops_domain_policies": active_domain_policies,
            "run_user_plan_id": normalize_plan_id(plan_id) if plan_id else "",
            "run_user_quota_overrides": runtime_quota_overrides,
        }
        return report

    def start_quick_apply_run(
        self,
        workspace_id: str,
        *,
        manual_urls: list[str] | tuple[str, ...] | set[str] | str,
        run_input_overrides: Mapping[str, Any] | None = None,
        execute: bool = True,
        enqueue: bool = False,
        requested_by: str = "api",
        max_attempts: int = 1,
    ) -> tuple[RunRecord, list[dict[str, Any]]]:
        if execute and enqueue:
            raise ValueError("run cannot be both queued and synchronously executed")

        workspace = self.repositories.workspace_repository.get_workspace(workspace_id)
        automation_flow = str(
            workspace.metadata.get("automation_flow")
            or workspace.settings.get("automation_flow")
            or ""
        ).strip()
        if automation_flow and automation_flow != "tailored_documents":
            raise ValueError("Quick apply requires a tailored-documents workspace.")

        valid_urls, invalid_entries = normalize_manual_urls(manual_urls)
        if not valid_urls:
            raise ValueError("Add at least one valid exact job URL.")

        workflow = build_quick_apply_workflow_template()
        effective_run_input_overrides = dict(run_input_overrides or {})
        effective_run_input_overrides.update(
            {
                "manual_urls_inline": list(valid_urls),
                "manual_url_seed_list": list(valid_urls),
                "stage4_max_jobs": len(valid_urls),
            }
        )
        planned_run_settings = dict(workspace.settings or {})
        planned_run_settings.update(effective_run_input_overrides)
        _validate_builder_workspace_definition(
            workspace,
            phase="run_preflight",
            error_code="run_preflight_failed",
            run_plan_settings=planned_run_settings,
            object_storage=self.object_storage,
        )
        run = RunRecord.create(
            workspace_id=workspace.id,
            workflow_template_id=workflow.id,
            run_input_overrides=effective_run_input_overrides,
            requested_by=requested_by,
            max_attempts=max_attempts,
            metadata={
                "workspace_type": workspace.workspace_type,
                "run_kind": "quick_apply",
                "accepted_url_count": len(valid_urls),
                "invalid_url_count": len(invalid_entries),
            },
        )
        run.run_plan = self.stage_engine.build_run_plan(
            workspace=workspace,
            workflow=workflow,
            run_input_overrides=effective_run_input_overrides,
        )
        self.repositories.run_repository.save(run)

        if enqueue:
            return self._queue_run(run), invalid_entries
        if not execute:
            return self.repositories.run_repository.get(run.id), invalid_entries
        return self._execute_run(run, workspace=workspace, workflow=workflow, auto_retry_failed=False), invalid_entries

    def create_workspace_from_scratch(self, payload: Mapping[str, Any]) -> WorkspaceDefinition:
        builder_payload = dict(payload)
        _validate_builder_workspace_payload(
            builder_payload,
            workspace_id=str(builder_payload.get("workspace_id") or "").strip(),
        )
        workflow_template, workspace = build_workspace_from_scratch(builder_payload)
        self.upsert_workflow_template(workflow_template)
        return self.upsert_workspace(workspace)

    def update_workspace_from_scratch(self, workspace_id: str, payload: Mapping[str, Any]) -> WorkspaceDefinition:
        existing_workspace = self.get_workspace(workspace_id)
        builder_payload = dict(payload)
        builder_payload["workspace_id"] = existing_workspace.id
        builder_payload.setdefault("workflow_template_id", existing_workspace.workflow_template_id)
        _validate_builder_workspace_payload(builder_payload, workspace_id=existing_workspace.id)
        workflow_template, workspace = build_workspace_from_scratch(builder_payload)
        workspace.owner_user_id = existing_workspace.owner_user_id
        existing_schedule = (existing_workspace.metadata or {}).get(WORKSPACE_RUN_SCHEDULE_METADATA_KEY)
        if isinstance(existing_schedule, dict):
            workspace.metadata = dict(workspace.metadata or {})
            workspace.metadata[WORKSPACE_RUN_SCHEDULE_METADATA_KEY] = _workspace_run_schedule_payload(existing_workspace)
        self.upsert_workflow_template(workflow_template)
        return self.upsert_workspace(workspace)

    def update_workspace_schedule(self, workspace_id: str, payload: Mapping[str, Any]) -> WorkspaceDefinition:
        workspace = self.get_workspace(workspace_id)
        schedule = _workspace_run_schedule_payload(workspace)
        interval_days = _schedule_interval_days(payload.get("interval_days"))
        enabled = bool(payload.get("enabled"))
        if "enabled" not in payload and interval_days >= 1:
            enabled = True

        if enabled and interval_days < 1:
            raise ValueError("interval_days must be at least 1 when recurring scheduling is enabled.")

        if not enabled:
            schedule.update(
                {
                    "enabled": False,
                    "interval_days": 0,
                    "next_run_at": "",
                    "last_error": "",
                    "last_error_at": "",
                }
            )
            return self._persist_workspace_run_schedule(workspace, schedule)

        preserve_existing_next_run = (
            schedule["enabled"]
            and schedule["interval_days"] == interval_days
            and _parse_utc_datetime(schedule["next_run_at"]) is not None
        )
        schedule.update(
            {
                "enabled": True,
                "interval_days": interval_days,
                "next_run_at": (
                    schedule["next_run_at"]
                    if preserve_existing_next_run
                    else _next_schedule_timestamp(from_dt=_utc_now(), interval_days=interval_days)
                ),
                "last_error": "",
                "last_error_at": "",
            }
        )
        return self._persist_workspace_run_schedule(workspace, schedule)

    def enqueue_due_scheduled_runs(self) -> list[RunRecord]:
        scheduler_logger = logging.getLogger("backend.scheduler")
        now = _utc_now()
        now_iso = now.isoformat()
        active_workspace_ids = {
            run.workspace_id
            for run in self.list_runs(limit=100000, offset=0, status="", workspace_id="")
            if run.status in SCHEDULED_RUN_ACTIVE_STATUSES
        }
        queued_runs: list[RunRecord] = []

        for workspace in self.list_workspaces():
            schedule = _workspace_run_schedule_payload(workspace)
            if not schedule["enabled"] or schedule["interval_days"] < 1:
                continue

            next_run_at = _parse_utc_datetime(schedule["next_run_at"])
            if next_run_at is None:
                schedule["next_run_at"] = _next_schedule_timestamp(
                    from_dt=now,
                    interval_days=schedule["interval_days"],
                )
                self._persist_workspace_run_schedule(workspace, schedule)
                continue

            if next_run_at > now or workspace.id in active_workspace_ids:
                continue

            try:
                owner_user_id = str(workspace.owner_user_id or "").strip()
                if not owner_user_id:
                    raise ValueError(
                        f"Workspace '{workspace.id}' has no owner and cannot enqueue scheduled runs."
                    )
                run = self.enqueue_run(
                    workspace.id,
                    requested_by=SCHEDULED_RUN_REQUESTED_BY,
                    user_id=owner_user_id,
                    max_attempts=1,
                )
            except Exception as exc:
                scheduler_logger.exception(
                    "Unable to enqueue scheduled run for workspace %s",
                    workspace.id,
                )
                schedule.update(
                    {
                        "next_run_at": _next_schedule_timestamp(
                            from_dt=now,
                            interval_days=schedule["interval_days"],
                        ),
                        "last_error": str(exc),
                        "last_error_at": now_iso,
                    }
                )
                self._persist_workspace_run_schedule(workspace, schedule)
                continue

            schedule.update(
                {
                    "next_run_at": _next_schedule_timestamp(
                        from_dt=now,
                        interval_days=schedule["interval_days"],
                    ),
                    "last_enqueued_at": now_iso,
                    "last_run_id": run.id,
                    "last_error": "",
                    "last_error_at": "",
                }
            )
            self._persist_workspace_run_schedule(workspace, schedule)
            active_workspace_ids.add(workspace.id)
            queued_runs.append(run)

        return queued_runs

    def _find_job_payload(self, run_id: str, job_id: str) -> dict[str, Any]:
        for jobs in self.repositories.job_store.load_all_job_sets(run_id).values():
            for job in jobs:
                if job.job_id == job_id:
                    return job.to_dict()
        for key, value in self.repositories.job_store.load_all_blobs(run_id).items():
            if not (
                str(key).endswith("_rejected")
                or str(key).endswith("_dropped_duplicates")
            ) or not isinstance(value, list):
                continue
            for item in value:
                if isinstance(item, dict) and str(item.get("job_id") or "") == job_id:
                    return dict(item)
        raise KeyError(f"Job '{job_id}' not found in run '{run_id}'.")

    def _persist_workspace_run_schedule(
        self,
        workspace: WorkspaceDefinition,
        schedule: Mapping[str, Any],
    ) -> WorkspaceDefinition:
        updated_workspace = WorkspaceDefinition.from_dict(workspace.to_dict())
        updated_workspace.metadata = dict(updated_workspace.metadata or {})
        updated_workspace.metadata[WORKSPACE_RUN_SCHEDULE_METADATA_KEY] = dict(schedule)
        self.repositories.workspace_repository.upsert_workspace(updated_workspace)
        return self.repositories.workspace_repository.get_workspace(updated_workspace.id)

    def _workflow_from_run_snapshot(self, run: RunRecord) -> WorkflowTemplate:
        if run.run_plan and run.run_plan.workflow_snapshot:
            return WorkflowTemplate.from_dict(run.run_plan.workflow_snapshot)
        return self.repositories.workspace_repository.get_workflow_template(run.workflow_template_id)

    def _workspace_from_run_snapshot(self, run: RunRecord) -> WorkspaceDefinition:
        if run.run_plan and run.run_plan.workspace_snapshot:
            return WorkspaceDefinition.from_dict(run.run_plan.workspace_snapshot)
        return self.repositories.workspace_repository.get_workspace(run.workspace_id)

    def _build_requeue_workflow(self, workflow: WorkflowTemplate) -> WorkflowTemplate:
        requeue_stages = [
            StageDefinition.from_dict(stage.to_dict())
            for stage in workflow.stages
            if stage.stage_type in AUTO_APPROVE_REVIEW_STAGE_TYPES
            or bool((stage.metadata or {}).get("supports_requeue"))
        ]
        if not requeue_stages:
            raise ValueError("This workspace does not expose a document-generation stage that can be requeued.")
        requeue_stages[0].input_keys = ["requeued_jobs"]
        return WorkflowTemplate(
            id=f"{workflow.id}_requeue",
            name=f"{workflow.name} Requeue",
            description=f"Requeue workflow for {workflow.name}.",
            stages=requeue_stages,
            default_run_settings=dict(workflow.default_run_settings),
        )

    def _auto_approve_generated_job_reviews(
        self,
        *,
        run_id: str,
        workflow: WorkflowTemplate,
        reviewer: str = "system",
    ) -> None:
        review_job_set_keys = _auto_approve_review_job_set_keys(workflow)
        if not review_job_set_keys:
            return

        run = self.repositories.run_repository.get(run_id)
        existing_user_postings = self._user_tracker_posting_urls(
            user_id=run.normalized_user_id,
            exclude_run_id=run_id,
        )
        job_sets = self.list_job_sets(run_id)
        existing_reviews_by_job = {
            review.job_id: review
            for review in self.list_reviews(run_id=run_id, limit=100000, offset=0)
        }

        for set_key in review_job_set_keys:
            for job in job_sets.get(set_key, []):
                existing_review = existing_reviews_by_job.get(job.job_id)
                if (
                    existing_review
                    and existing_review.status == "approved"
                    and existing_review.decision == "approved"
                ):
                    continue
                if existing_review and existing_review.decision == "rejected":
                    continue

                posting_url = self._job_record_posting_url(job)
                duplicate_posting = dict(existing_user_postings.get(posting_url) or {}) if posting_url else {}
                if duplicate_posting:
                    duplicate_review = self.upsert_review(
                        run_id=run_id,
                        review_id=existing_review.review_id if existing_review else "",
                        payload={
                            "job_id": job.job_id,
                            "status": "duplicate",
                            "decision": "duplicate",
                            "reviewer": reviewer,
                            "notes": "Duplicate posting URL already exists in this user's tracker.",
                            "job_set_key": set_key,
                            "metadata": {
                                "auto_duplicate": True,
                                "duplicate_scope": "user_posting_url",
                                "canonical_posting_url": posting_url,
                                "duplicate_of": duplicate_posting,
                            },
                        },
                    )
                    existing_reviews_by_job[job.job_id] = duplicate_review
                    continue

                review = self.upsert_review(
                    run_id=run_id,
                    review_id=existing_review.review_id if existing_review else "",
                    payload={
                        "job_id": job.job_id,
                        "status": "approved",
                        "decision": "approved",
                        "reviewer": (
                            existing_review.reviewer
                            if existing_review and existing_review.reviewer
                            else reviewer
                        ),
                        "notes": existing_review.notes if existing_review else "",
                        "job_set_key": set_key,
                        "metadata": {"auto_approved": True, "canonical_posting_url": posting_url},
                    },
                )
                existing_reviews_by_job[job.job_id] = review
                if posting_url:
                    existing_user_postings[posting_url] = {
                        "posting_url": posting_url,
                        "run_id": run_id,
                        "workspace_id": run.workspace_id,
                        "review_id": review.review_id,
                        "job_id": job.job_id,
                    }

    def backfill_completed_test_run_tracker_reviews(self, *, run_ids: list[str]) -> int:
        backfilled_reviews = 0
        logger = logging.getLogger("backend.tracker.test_run_backfill")
        for run_id in run_ids:
            try:
                run = self.get_run(run_id)
            except KeyError:
                continue
            if run.status != RUN_STATUS_COMPLETED or not run.is_test_run:
                continue
            if self.list_reviews(run_id=run.id, limit=1, offset=0):
                continue
            try:
                workflow = self._workflow_from_run_snapshot(run)
                self._auto_approve_generated_job_reviews(run_id=run.id, workflow=workflow)
            except Exception:
                logger.exception("Unable to backfill tracker review for completed test run %s", run.id)
                continue
            backfilled_reviews += len(self.list_reviews(run_id=run.id, limit=1000, offset=0))
        return backfilled_reviews

    def requeue_job_for_generation(
        self,
        *,
        run_id: str,
        job_id: str,
        requested_by: str = "api",
        max_attempts: int = 1,
        execute: bool = False,
        notes: str = "",
    ) -> RunRecord:
        original_run = self.get_run(run_id)
        workspace = self.get_workspace(original_run.workspace_id)
        original_workflow = self.repositories.workspace_repository.get_workflow_template(workspace.workflow_template_id)
        job_payload = self._find_job_payload(run_id, job_id)
        requeue_workflow = self._build_requeue_workflow(original_workflow)
        run_overrides = dict(original_run.run_input_overrides or {})
        run_overrides["force_regenerate"] = True

        requeue_run = RunRecord.create(
            workspace_id=workspace.id,
            workflow_template_id=requeue_workflow.id,
            run_input_overrides=run_overrides,
            requested_by=requested_by,
            max_attempts=max_attempts,
            metadata={
                "workspace_type": workspace.workspace_type,
                "requeue_origin": {
                    "run_id": run_id,
                    "job_id": job_id,
                    "notes": str(notes or ""),
                },
            },
        )
        requeue_run.run_plan = self.stage_engine.build_run_plan(
            workspace=workspace,
            workflow=requeue_workflow,
            run_input_overrides=run_overrides,
        )
        self.repositories.run_repository.save(requeue_run)
        self.repositories.job_store.save_job_set(
            requeue_run.id,
            "requeued_jobs",
            [JobRecord.from_mapping(job_payload)],
        )
        self._refresh_run_job_keys(requeue_run.id)

        if execute:
            return self._execute_run(
                requeue_run,
                workspace=workspace,
                workflow=requeue_workflow,
                auto_retry_failed=False,
            )
        return self._queue_run(requeue_run)

    def list_users(self) -> list[UserRecord]:
        return self._identity_access_service.list_users()

    def get_user(self, user_id: str) -> UserRecord:
        return self._identity_access_service.get_user(user_id)

    def upsert_user(self, payload: Mapping[str, Any] | UserRecord):
        return self._identity_access_service.upsert_user(payload)

    def delete_user(self, user_id: str) -> None:
        self._identity_access_service.delete_user(user_id)

    def delete_user(self, user_id: str) -> None:
        self._identity_access_service.delete_user(user_id)

    def list_career_profiles(self, *, user_id: str = "") -> list:
        store = getattr(self.repositories, "career_profile_store", None)
        if store is None:
            return []
        return store.list_profiles(user_id=user_id)

    def get_career_profile(self, profile_id: str):
        store = getattr(self.repositories, "career_profile_store", None)
        if store is None:
            raise ValueError("Career profile storage is not configured.")
        return store.get_profile(profile_id)

    def create_career_profile(self, payload: Mapping[str, Any]):
        store = getattr(self.repositories, "career_profile_store", None)
        if store is None:
            raise ValueError("Career profile storage is not configured.")
        profile = CareerProfile.create(
            user_id=str(payload.get("user_id") or "").strip(),
            name=str(payload.get("name") or "").strip(),
            description=str(payload.get("description") or "").strip(),
            preferred_language=str(payload.get("preferred_language") or "en").strip(),
            target_direction=str(payload.get("target_direction") or "").strip(),
        )
        store.upsert_profile(profile)
        return profile

    def update_career_profile(self, profile_id: str, payload: Mapping[str, Any]):
        store = getattr(self.repositories, "career_profile_store", None)
        if store is None:
            raise ValueError("Career profile storage is not configured.")
        profile = store.get_profile(profile_id)
        if "name" in payload:
            name = str(payload["name"] or "").strip()
            if name:
                profile.name = name
        if "description" in payload:
            profile.description = str(payload["description"] or "").strip()
        if "preferred_language" in payload:
            lang = str(payload["preferred_language"] or "").strip()
            if lang:
                profile.preferred_language = lang
        if "target_direction" in payload:
            profile.target_direction = str(payload["target_direction"] or "").strip()
        if "target_direction" in payload:
            profile.target_direction = str(payload["target_direction"] or "").strip()
        if "baseline_cv_asset_id" in payload:
            profile.baseline_cv_asset_id = str(payload["baseline_cv_asset_id"] or "").strip()
        if "baseline_cv_display_name" in payload:
            profile.baseline_cv_display_name = str(payload["baseline_cv_display_name"] or "").strip()
        if "baseline_cv_extraction_date" in payload:
            profile.baseline_cv_extraction_date = str(payload["baseline_cv_extraction_date"] or "").strip()
        if "baseline_cv_source_version" in payload:
            profile.baseline_cv_source_version = str(payload["baseline_cv_source_version"] or "").strip()
        if "status" in payload:
        if "status" in payload:
            from backend.domain.models import CAREER_PROFILE_STATUSES
            status = str(payload["status"] or "").strip()
            if status in CAREER_PROFILE_STATUSES:
                profile.status = status
        profile.updated_at = utc_now_iso()
        store.upsert_profile(profile)
        return profile

    def delete_career_profile(self, profile_id: str) -> None:
        store = getattr(self.repositories, "career_profile_store", None)
        if store is None:
            raise ValueError("Career profile storage is not configured.")
        store.delete_profile(profile_id)

    def list_referral_contacts(self, user_id: str) -> list[ReferralContactRecord]:
        return self._tracker_application_service.list_referral_contacts(user_id)

    def get_referral_contact(self, user_id: str, contact_id: str) -> ReferralContactRecord:
        return self._tracker_application_service.get_referral_contact(user_id, contact_id)

    def upsert_referral_contact(
        self,
        *,
        user_id: str,
        payload: Mapping[str, Any] | ReferralContactRecord,
        contact_id: str = "",
    ) -> ReferralContactRecord:
        return self._tracker_application_service.upsert_referral_contact(
            user_id=user_id,
            payload=payload,
            contact_id=contact_id,
        )

    def import_referral_contacts(
        self,
        *,
        user_id: str,
        csv_text: str,
        source_kind: str = "linkedin_csv",
    ) -> dict[str, Any]:
        return self._tracker_application_service.import_referral_contacts(
            user_id=user_id,
            csv_text=csv_text,
            source_kind=source_kind,
        )

    def delete_imported_referral_contacts(self, *, user_id: str) -> dict[str, Any]:
        return self._tracker_application_service.delete_imported_referral_contacts(user_id=user_id)

    def delete_referral_contact(self, user_id: str, contact_id: str) -> None:
        self._tracker_application_service.delete_referral_contact(user_id, contact_id)

    def generate_referral_outreach(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
        contact_id: str = "",
    ) -> dict[str, Any]:
        return self._tracker_application_service.generate_referral_outreach(
            user_id=user_id,
            run_id=run_id,
            job_id=job_id,
            contact_id=contact_id,
        )

    def generate_hiring_manager_outreach(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        return self._tracker_application_service.generate_hiring_manager_outreach(
            user_id=user_id,
            run_id=run_id,
            job_id=job_id,
        )

    def generate_target_contact_discovery(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        return self._tracker_application_service.generate_target_contact_discovery(
            user_id=user_id,
            run_id=run_id,
            job_id=job_id,
        )

    def get_job_workspace(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        return self._tracker_application_service.get_job_workspace(
            user_id=user_id,
            run_id=run_id,
            job_id=job_id,
        )

    def get_relevant_people_discovery_status(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        return self._tracker_application_service.get_relevant_people_discovery_status(
            user_id=user_id,
            run_id=run_id,
            job_id=job_id,
        )

    def get_relevant_people_discovery_results(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        return self._tracker_application_service.get_relevant_people_discovery_results(
            user_id=user_id,
            run_id=run_id,
            job_id=job_id,
        )

    def start_relevant_people_discovery(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        return self._tracker_application_service.start_relevant_people_discovery(
            user_id=user_id,
            run_id=run_id,
            job_id=job_id,
        )

    def set_relevant_people_status(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
        person_id: str,
        status: str,
    ) -> dict[str, Any]:
        return self._tracker_application_service.set_relevant_people_status(
            user_id=user_id,
            run_id=run_id,
            job_id=job_id,
            person_id=person_id,
            status=status,
        )
    def list_api_tokens(
        self,
        *,
        user_id: str = "",
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ApiTokenRecord]:
        return self._identity_access_service.list_api_tokens(
            user_id=user_id,
            include_inactive=include_inactive,
            limit=limit,
            offset=offset,
        )

    def create_assisted_apply_connection_request(
        self,
        *,
        extension_origin: str,
        state: str,
        challenge: str,
        installation_id: str,
        version: str,
    ) -> AssistedApplyConnectionRecord:
        return self._assisted_apply_connection_service.create_request(
            extension_origin=extension_origin,
            state=state,
            challenge=challenge,
            installation_id=installation_id,
            version=version,
        )

    def get_assisted_apply_connection_dashboard(
        self,
        *,
        user_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        return self._assisted_apply_connection_service.dashboard(
            user_id=user_id,
            request_id=request_id,
        )

    def authorize_assisted_apply_connection(
        self,
        *,
        user_id: str,
        request_id: str,
        preferences: Mapping[str, Any] | None = None,
    ) -> str:
        return self._assisted_apply_connection_service.authorize(
            user_id=user_id,
            request_id=request_id,
            preferences=preferences,
        )

    def reject_assisted_apply_connection(
        self,
        *,
        user_id: str,
        request_id: str,
    ) -> AssistedApplyConnectionRecord:
        return self._assisted_apply_connection_service.reject(
            user_id=user_id,
            request_id=request_id,
        )

    def exchange_assisted_apply_authorization(
        self,
        *,
        extension_origin: str,
        request_id: str,
        code: str,
        verifier: str,
    ) -> tuple[AssistedApplyConnectionRecord, str]:
        return self._assisted_apply_connection_service.exchange(
            extension_origin=extension_origin,
            request_id=request_id,
            code=code,
            verifier=verifier,
        )

    def authenticate_assisted_apply_session(
        self,
        *,
        raw_session: str,
        extension_origin: str,
    ) -> tuple[UserRecord, AssistedApplyConnectionRecord]:
        return self._assisted_apply_connection_service.authenticate_session(
            raw_session=raw_session,
            extension_origin=extension_origin,
        )

    def get_assisted_apply_preferences(self, user_id: str) -> AssistedApplyPreferences:
        return self._assisted_apply_connection_service.get_preferences(user_id)

    def update_assisted_apply_preferences(
        self,
        *,
        user_id: str,
        preferences: Mapping[str, Any] | None,
    ) -> AssistedApplyPreferences:
        return self._assisted_apply_connection_service.update_preferences(
            user_id,
            preferences,
        )

    def revoke_current_assisted_apply_session(
        self,
        *,
        raw_session: str,
        extension_origin: str,
    ) -> AssistedApplyConnectionRecord:
        return self._assisted_apply_connection_service.revoke_current(
            raw_session=raw_session,
            extension_origin=extension_origin,
        )

    def revoke_owned_assisted_apply_connection(
        self,
        *,
        user_id: str,
        request_id: str,
    ) -> AssistedApplyConnectionRecord:
        return self._assisted_apply_connection_service.revoke_owned(
            user_id=user_id,
            request_id=request_id,
        )

    def issue_api_token(
        self,
        *,
        user_id: str,
        name: str,
        scopes: list[str] | None = None,
        expires_at: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[ApiTokenRecord, str]:
        return self._identity_access_service.issue_api_token(
            user_id=user_id,
            name=name,
            scopes=scopes,
            expires_at=expires_at,
            metadata=metadata,
        )

    def revoke_api_token(self, token_id: str) -> ApiTokenRecord:
        return self._identity_access_service.revoke_api_token(token_id)

    def authenticate_access_token(self, raw_token: str) -> tuple[UserRecord, ApiTokenRecord]:
        return self._identity_access_service.authenticate_access_token(raw_token)

    def user_has_scope(self, token: ApiTokenRecord, required_scope: str) -> bool:
        return self._identity_access_service.user_has_scope(token, required_scope)

    def user_can_access_workspace(self, user: UserRecord, workspace_id: str) -> bool:
        return self._identity_access_service.user_can_access_workspace(user, workspace_id)

    def user_can_access_run(self, user: UserRecord, run: RunRecord) -> bool:
        return self._identity_access_service.user_can_access_run(user, run)

    def list_secrets(self, *, workspace_id: str = "", limit: int = 100, offset: int = 0) -> list[SecretRecord]:
        return self._identity_access_service.list_secrets(
            workspace_id=workspace_id,
            limit=limit,
            offset=offset,
        )

    def get_secret(self, secret_id: str) -> SecretRecord:
        return self._identity_access_service.get_secret(secret_id)

    def upsert_secret(self, payload: Mapping[str, Any] | SecretRecord):
        return self._identity_access_service.upsert_secret(payload)

    def delete_secret(self, secret_id: str) -> None:
        self._identity_access_service.delete_secret(secret_id)

    def resolve_secret_value(self, secret_id: str) -> str:
        return self._identity_access_service.resolve_secret_value(secret_id)

    def resolve_runtime_value(self, payload: Any) -> Any:
        return self._identity_access_service.resolve_runtime_value(payload)

    @staticmethod
    def _review_is_actionable_tracker_item(review: ReviewRecord) -> bool:
        return TrackerApplicationService.review_is_actionable_tracker_item(review)

    def _job_record_posting_url(self, job: JobRecord | None) -> str:
        return self._tracker_application_service.job_record_posting_url(job)

    def _user_tracker_posting_urls(
        self,
        *,
        user_id: str,
        exclude_review_id: str = "",
        exclude_run_id: str = "",
        exclude_job_id: str = "",
    ) -> dict[str, dict[str, str]]:
        return self._tracker_application_service.user_tracker_posting_urls(
            user_id=user_id,
            exclude_review_id=exclude_review_id,
            exclude_run_id=exclude_run_id,
            exclude_job_id=exclude_job_id,
        )

    def _find_duplicate_user_tracker_posting(
        self,
        *,
        run_id: str,
        job_id: str,
        review_id: str = "",
    ) -> dict[str, str]:
        return self._tracker_application_service.find_duplicate_user_tracker_posting(
            run_id=run_id,
            job_id=job_id,
            review_id=review_id,
        )

    def _get_job_for_run(self, *, run_id: str, job_id: str) -> JobRecord:
        return self._tracker_application_service.get_job_for_run(run_id=run_id, job_id=job_id)
    def get_run(self, run_id: str) -> RunRecord:
        return self._run_lifecycle_service.get_run(run_id)

    def delete_run(self, run_id: str) -> None:
        self._run_lifecycle_service.delete_run(run_id)

    def list_runs(self, *, limit: int = 50, offset: int = 0, status: str = "", workspace_id: str = ""):
        return self._run_lifecycle_service.list_runs(
            limit=limit,
            offset=offset,
            status=status,
            workspace_id=workspace_id,
        )

    def list_job_sets(self, run_id: str) -> dict[str, list[JobRecord]]:
        return self._run_lifecycle_service.list_job_sets(run_id)

    def get_job_set(self, run_id: str, set_key: str) -> list[JobRecord]:
        return self._run_lifecycle_service.get_job_set(run_id, set_key)

    def upsert_job_set(self, run_id: str, set_key: str, jobs: list[Mapping[str, Any] | JobRecord]) -> list[JobRecord]:
        return self._run_lifecycle_service.upsert_job_set(run_id, set_key, jobs)

    def delete_job_set(self, run_id: str, set_key: str) -> None:
        self._run_lifecycle_service.delete_job_set(run_id, set_key)

    def delete_job(self, run_id: str, job_id: str) -> None:
        self._run_lifecycle_service.delete_job(run_id, job_id)

    def list_artifacts(self, run_id: str) -> list[ArtifactRecord]:
        return self._run_lifecycle_service.list_artifacts(run_id)

    def get_artifact(self, run_id: str, artifact_id: str) -> ArtifactRecord:
        return self._run_lifecycle_service.get_artifact(run_id, artifact_id)

    def upsert_artifact(self, run_id: str, payload: Mapping[str, Any] | ArtifactRecord) -> ArtifactRecord:
        return self._run_lifecycle_service.upsert_artifact(run_id, payload)

    def delete_artifact(self, run_id: str, artifact_id: str) -> None:
        self._run_lifecycle_service.delete_artifact(run_id, artifact_id)

    def list_reviews(
        self,
        *,
        run_id: str = "",
        job_id: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[ReviewRecord]:
        return self._run_lifecycle_service.list_reviews(
            run_id=run_id,
            job_id=job_id,
            limit=limit,
            offset=offset,
        )

    def get_review(self, review_id: str) -> ReviewRecord:
        return self._run_lifecycle_service.get_review(review_id)

    def upsert_review(
        self,
        *,
        run_id: str,
        payload: Mapping[str, Any] | ReviewRecord,
        review_id: str = "",
    ) -> ReviewRecord:
        return self._run_lifecycle_service.upsert_review(
            run_id=run_id,
            payload=payload,
            review_id=review_id,
        )

    def delete_review(self, review_id: str) -> None:
        self._run_lifecycle_service.delete_review(review_id)

    def list_workers(self, *, limit: int = 50, offset: int = 0, status: str = "") -> list[WorkerRecord]:
        return self._run_lifecycle_service.list_workers(limit=limit, offset=offset, status=status)

    def get_worker(self, worker_id: str) -> WorkerRecord:
        return self._run_lifecycle_service.get_worker(worker_id)

    def heartbeat_worker(
        self,
        *,
        worker_id: str,
        status: str = WORKER_STATUS_IDLE,
        current_run_id: str = "",
        host_name: str = "",
        process_id: int = 0,
        lease_seconds: int = 60,
        metadata: Mapping[str, Any] | None = None,
    ) -> WorkerRecord:
        return self._run_lifecycle_service.heartbeat_worker(
            worker_id=worker_id,
            status=status,
            current_run_id=current_run_id,
            host_name=host_name,
            process_id=process_id,
            lease_seconds=lease_seconds,
            metadata=metadata,
        )

    def renew_worker_lease(
        self,
        *,
        worker_id: str,
        current_run_id: str,
        run_attempt_count: int,
        host_name: str = "",
        process_id: int = 0,
        lease_seconds: int = 60,
    ) -> WorkerRecord:
        return self._run_lifecycle_service.renew_worker_lease(
            worker_id=worker_id,
            current_run_id=current_run_id,
            run_attempt_count=run_attempt_count,
            host_name=host_name,
            process_id=process_id,
            lease_seconds=lease_seconds,
        )

    def stop_worker(self, worker_id: str) -> WorkerRecord:
        return self._run_lifecycle_service.stop_worker(worker_id)

    def recover_stale_workers(self) -> list[WorkerRecord]:
        return self._run_lifecycle_service.recover_stale_workers()

    def _fail_run_preflight(self, run: RunRecord, exc: BackendValidationError) -> RunRecord:
        return self._run_lifecycle_service.fail_run_preflight(run, exc)

    def start_run(
        self,
        workspace_id: str,
        *,
        run_input_overrides: Mapping[str, Any] | None = None,
        execute: bool = True,
        enqueue: bool = False,
        requested_by: str = "cli",
        user_id: str = "",
        max_attempts: int = 1,
    ) -> RunRecord:
        return self._run_lifecycle_service.start_run(
            workspace_id,
            run_input_overrides=run_input_overrides,
            execute=execute,
            enqueue=enqueue,
            requested_by=requested_by,
            user_id=user_id,
            max_attempts=max_attempts,
        )

    def enqueue_run(
        self,
        workspace_id: str,
        *,
        run_input_overrides: Mapping[str, Any] | None = None,
        requested_by: str = "api",
        user_id: str = "",
        max_attempts: int = 1,
    ) -> RunRecord:
        return self._run_lifecycle_service.enqueue_run(
            workspace_id,
            run_input_overrides=run_input_overrides,
            requested_by=requested_by,
            user_id=user_id,
            max_attempts=max_attempts,
        )

    def claim_next_queued_run(
        self,
        *,
        worker_id: str = "",
        host_name: str = "",
        process_id: int = 0,
        lease_seconds: int = 60,
        recover_stale_workers: bool = True,
        enqueue_scheduled_runs: bool = True,
    ) -> RunRecord | None:
        return self._run_lifecycle_service.claim_next_queued_run(
            worker_id=worker_id,
            host_name=host_name,
            process_id=process_id,
            lease_seconds=lease_seconds,
            recover_stale_workers=recover_stale_workers,
            enqueue_scheduled_runs=enqueue_scheduled_runs,
        )

    def execute_claimed_run(self, run_id: str, *, auto_retry_failed: bool = True) -> RunRecord:
        return self._run_lifecycle_service.execute_claimed_run(run_id, auto_retry_failed=auto_retry_failed)

    def release_worker(self, worker_id: str, *, status: str = WORKER_STATUS_IDLE) -> WorkerRecord | None:
        return self._run_lifecycle_service.release_worker(worker_id, status=status)

    def process_next_queued_run(
        self,
        *,
        auto_retry_failed: bool = True,
        worker_id: str = "",
        host_name: str = "",
        process_id: int = 0,
        lease_seconds: int = 60,
    ) -> RunRecord | None:
        return self._run_lifecycle_service.process_next_queued_run(
            auto_retry_failed=auto_retry_failed,
            worker_id=worker_id,
            host_name=host_name,
            process_id=process_id,
            lease_seconds=lease_seconds,
        )

    def cancel_run(self, run_id: str) -> RunRecord:
        return self._run_lifecycle_service.cancel_run(run_id)

    def retry_run(self, run_id: str) -> RunRecord:
        return self._run_lifecycle_service.retry_run(run_id)

    def resume_run(self, run_id: str) -> RunRecord:
        return self._run_lifecycle_service.resume_run(run_id)

    def _execute_run(
        self,
        run: RunRecord,
        *,
        workspace: WorkspaceDefinition,
        workflow: WorkflowTemplate,
        auto_retry_failed: bool,
    ) -> RunRecord:
        return self._run_lifecycle_service.execute_run(
            run,
            workspace=workspace,
            workflow=workflow,
            auto_retry_failed=auto_retry_failed,
        )

    def _queue_run(self, run: RunRecord) -> RunRecord:
        return self._run_lifecycle_service.queue_run(run)

    def _trim_to_resumable_prefix(self, run: RunRecord) -> None:
        self._run_lifecycle_service.trim_to_resumable_prefix(run)

    def _refresh_run_job_keys(self, run_id: str) -> None:
        self._run_lifecycle_service.refresh_run_job_keys(run_id)
    # --- AA-03: Application Package delegation ---

    def create_application_package(
        self,
        *,
        user_id: str,
        job: Any,
        answers: Any = None,
        documents: Any = None,
        warnings_items: Any = None,
    ):
        return self._assisted_apply_package_service.create_package(
            user_id=user_id,
            job=job,
            answers=answers,
            documents=documents,
            warnings_items=warnings_items,
        )

    def launch_application_package(self, *, user_id: str, package_id: str):
        return self._assisted_apply_package_service.launch_package(
            user_id=user_id,
            package_id=package_id,
        )

    def bind_application_package(self, *, binding_id: str, extension_origin: str):
        return self._assisted_apply_package_service.bind_package(
            binding_id=binding_id,
            extension_origin=extension_origin,
        )

    def get_application_package_for_extension(
        self,
        *,
        package_id: str,
        raw_session: str,
        extension_origin: str,
    ):
        return self._assisted_apply_package_service.get_package_for_extension(
            package_id=package_id,
            raw_session=raw_session,
            extension_origin=extension_origin,
        )

    def save_assisted_apply_correction(
        self,
        *,
        package_id: str,
        field_intent: str,
        corrected_value: str,
        scope: str,
        raw_session: str,
        extension_origin: str,
    ):
        return self._assisted_apply_package_service.save_correction_for_extension(
            package_id=package_id,
            field_intent=field_intent,
            corrected_value=corrected_value,
            scope=scope,
            raw_session=raw_session,
            extension_origin=extension_origin,
        )

    def create_assisted_apply_document_grant(
        self, *, package_id: str, document_id: str, raw_session: str, extension_origin: str
    ):
        return self._assisted_apply_package_service.create_document_grant(
            package_id=package_id,
            document_id=document_id,
            raw_session=raw_session,
            extension_origin=extension_origin,
        )

    def consume_assisted_apply_document_grant(
        self, *, raw_grant: str, raw_session: str, extension_origin: str
    ):
        return self._assisted_apply_package_service.consume_document_grant(
            raw_grant=raw_grant,
            raw_session=raw_session,
            extension_origin=extension_origin,
        )

    def respond_to_assisted_apply_outcome(
        self,
        *,
        package_id: str,
        package_version: int,
        adapter: str,
        adapter_version: str,
        evidence_category: str,
        decision: str,
        uploaded_documents: list[Mapping[str, Any]],
        raw_session: str,
        extension_origin: str,
    ):
        return self._assisted_apply_package_service.respond_to_application_outcome(
            package_id=package_id,
            package_version=package_version,
            adapter=adapter,
            adapter_version=adapter_version,
            evidence_category=evidence_category,
            decision=decision,
            uploaded_documents=uploaded_documents,
            raw_session=raw_session,
            extension_origin=extension_origin,
        )
