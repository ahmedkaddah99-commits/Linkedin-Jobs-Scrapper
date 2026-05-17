from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from backend.capabilities.networking import (
    PEOPLE_DISCOVERY_STATUS_COMPLETED,
    PEOPLE_DISCOVERY_STATUS_FAILED,
    PEOPLE_DISCOVERY_STATUS_RUNNING,
    build_empty_relevant_people_discovery,
    build_hiring_manager_outreach_draft,
    build_relevant_people_discovery,
    build_referral_outreach_draft,
    build_target_contact_discovery,
    find_referral_contacts_for_company,
    guess_hiring_manager_from_job,
    merge_referral_contacts,
    normalize_relevant_people_discovery_run,
    parse_referral_contacts_csv,
    update_relevant_people_status,
)
from backend.capabilities.tailored_documents.manual_urls import normalize_manual_urls
from backend.domain.models import (
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_REVIEWER,
    ROLE_VIEWER,
    RUN_STATUS_CANCEL_REQUESTED,
    RUN_STATUS_CANCELLED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_PLANNED,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    SECRET_PROVIDER_ENV,
    SECRET_PROVIDER_STORED,
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
    StageContext,
    UserRecord,
    WorkerRecord,
    WorkflowTemplate,
    WorkspaceDefinition,
    utc_plus_seconds,
    utc_now_iso,
)
from backend.orchestration import (
    build_quick_apply_workflow_template,
    build_workspace_from_scratch,
    validate_workspace_source_configuration,
    workspace_builder_catalog,
)
from backend.security import issue_api_token, resolve_secret_references, token_has_scope, token_is_expired, verify_token_value


ALLOWED_USER_ROLES = {ROLE_ADMIN, ROLE_EDITOR, ROLE_REVIEWER, ROLE_VIEWER}
BUILDER_WORKSPACE_FLOW_IDS = {"tailored_documents", "reusable_packages"}
BUILDER_CONNECTOR_SOURCE_IDS = {
    "linkedin_jobs": "linkedin_jobs",
    "curated_job_urls": "curated_job_urls",
    "company_career_sites": "company_career_sites",
    "academic_career_sites": "academic_career_sites",
    "job_board_collection": "job_board_collection",
}
AUTO_APPROVE_REVIEW_STAGE_TYPES = {
    "applications.generate.documents",
    "legacy.white_collar.docs",
}
APPLICATION_CONTEXTS_METADATA_KEY = "application_contexts"
RELEVANT_PEOPLE_DISCOVERY_CONTEXT_KEY = "relevant_people_discovery"
WORKSPACE_RUN_SCHEDULE_METADATA_KEY = "run_schedule"
SCHEDULED_RUN_REQUESTED_BY = "scheduler"
SCHEDULED_RUN_ACTIVE_STATUSES = {
    RUN_STATUS_PLANNED,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_CANCEL_REQUESTED,
}


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
    derived_source_ids: list[str] = []
    for source in workspace.sources:
        source_id = BUILDER_CONNECTOR_SOURCE_IDS.get(str(source.connector_id or "").strip())
        if source_id and source_id not in derived_source_ids:
            derived_source_ids.append(source_id)
    return derived_source_ids


def _workspace_cv_asset_id(workspace: WorkspaceDefinition) -> str:
    metadata = dict(workspace.metadata or {})
    workspace_configuration_v2 = metadata.get("workspace_configuration_v2") or {}
    cv_binding = dict(workspace_configuration_v2.get("cv_binding") or {})
    return str(workspace.settings.get("workspace_cv_asset_id") or cv_binding.get("asset_id") or "").strip()


def _builder_workspace_cv_asset_field_errors(workspace: WorkspaceDefinition) -> list[dict[str, str]]:
    asset_id = _workspace_cv_asset_id(workspace)
    if not asset_id:
        return []

    metadata = dict(workspace.metadata or {})
    asset = dict(metadata.get("workspace_cv_asset") or {})
    if not asset:
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

    file_path = str(asset.get("file", {}).get("path") or asset.get("path") or "").strip()
    if not file_path or not Path(file_path).is_file():
        return [
            _field_error(
                "workspace_cv_asset_id",
                "workspace_cv_asset_missing_file",
                "The selected workspace CV is no longer available on disk.",
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


def _artifact_matches_job(artifact: ArtifactRecord, job_id: str) -> bool:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return False
    if str((artifact.metadata or {}).get("job_id") or "").strip() == normalized_job_id:
        return True
    lowered_job_id = normalized_job_id.lower()
    candidate_text = " ".join(
        value
        for value in (
            str(artifact.artifact_id or "").strip(),
            str(artifact.path or "").strip(),
            Path(str(artifact.path or "")).name if str(artifact.path or "").strip() else "",
        )
        if value
    ).lower()
    return bool(lowered_job_id and lowered_job_id in candidate_text)


def _artifact_is_generated_document_container(artifact: ArtifactRecord) -> bool:
    return str(artifact.artifact_type or "").strip().lower() in {
        "stage5_docs_dir",
        "documents_json",
        "documents_xlsx",
    }


def _remove_job_from_blob_payload(value: Any, job_id: str) -> tuple[Any, bool]:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return value, False
    if isinstance(value, list):
        next_items = []
        changed = False
        for item in value:
            if isinstance(item, dict) and str(item.get("job_id") or "").strip() == normalized_job_id:
                changed = True
                continue
            cleaned_item, item_changed = _remove_job_from_blob_payload(item, normalized_job_id)
            next_items.append(cleaned_item)
            changed = changed or item_changed
        return next_items, changed
    if isinstance(value, dict):
        next_value = {}
        changed = False
        for key, item in value.items():
            cleaned_item, item_changed = _remove_job_from_blob_payload(item, normalized_job_id)
            next_value[key] = cleaned_item
            changed = changed or item_changed
        return next_value, changed
    return value, False


def _builder_workspace_run_preflight_field_errors(
    workspace: WorkspaceDefinition,
    *,
    run_plan_settings: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    asset_id = str(
        (run_plan_settings or {}).get("workspace_cv_asset_id")
        or _workspace_cv_asset_id(workspace)
        or ""
    ).strip()
    if not asset_id:
        return _builder_workspace_cv_asset_field_errors(workspace)

    workspace_cv_text = str((run_plan_settings or {}).get("workspace_cv_text") or "").strip()
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
    settings: Mapping[str, Any],
) -> dict[str, Any]:
    catalog_sources = {
        str(item["id"]): set(item.get("compatible_flows") or [])
        for item in workspace_builder_catalog().to_dict()["sources"]
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
            "field_errors": list(report.get("field_errors") or []),
            "source_results": list(report.get("source_results") or []),
        },
    )


def _validate_builder_workspace_payload(payload: Mapping[str, Any], *, workspace_id: str = "") -> None:
    flow_id = str(payload.get("flow_id") or "tailored_documents").strip()
    source_ids = [str(item).strip() for item in payload.get("source_ids") or [] if str(item).strip()]
    report = _builder_workspace_validation_report(
        flow_id=flow_id,
        source_ids=source_ids,
        settings=dict(payload.get("settings") or {}),
    )
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
) -> None:
    if not _is_builder_created_workspace(workspace):
        return

    report = _builder_workspace_validation_report(
        flow_id=_builder_workspace_flow_id(workspace),
        source_ids=_builder_workspace_source_ids(workspace),
        settings=dict(workspace.settings or {}),
    )
    if phase == "run_preflight" and run_plan_settings is not None:
        cv_field_errors = _builder_workspace_run_preflight_field_errors(
            workspace,
            run_plan_settings=run_plan_settings,
        )
    else:
        cv_field_errors = _builder_workspace_cv_asset_field_errors(workspace)
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


@dataclass(slots=True)
class BackendApplication:
    repositories: Any
    registries: Any
    stage_engine: Any

    def list_workspaces(self):
        return self.repositories.workspace_repository.list_workspaces()

    def get_workspace(self, workspace_id: str):
        return self.repositories.workspace_repository.get_workspace(workspace_id)

    def upsert_workspace(self, payload: Mapping[str, Any] | WorkspaceDefinition):
        workspace = payload if isinstance(payload, WorkspaceDefinition) else WorkspaceDefinition.from_dict(payload)
        if not workspace.id:
            raise ValueError("workspace id is required")
        if not workspace.name:
            raise ValueError("workspace name is required")
        if not workspace.workflow_template_id:
            raise ValueError("workspace workflow_template_id is required")
        self.repositories.workspace_repository.get_workflow_template(workspace.workflow_template_id)
        _validate_builder_workspace_definition(
            workspace,
            phase="save",
            error_code="workspace_validation_failed",
        )
        self.repositories.workspace_repository.upsert_workspace(workspace)
        return self.repositories.workspace_repository.get_workspace(workspace.id)

    def delete_workspace(self, workspace_id: str) -> None:
        self.repositories.workspace_repository.delete_workspace(workspace_id)

    def list_workflow_templates(self):
        return self.repositories.workspace_repository.list_workflow_templates()

    def get_workflow_template(self, template_id: str):
        return self.repositories.workspace_repository.get_workflow_template(template_id)

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

    def upsert_workflow_template(self, payload: Mapping[str, Any] | WorkflowTemplate):
        workflow_template = payload if isinstance(payload, WorkflowTemplate) else WorkflowTemplate.from_dict(payload)
        if not workflow_template.id:
            raise ValueError("workflow template id is required")
        if not workflow_template.name:
            raise ValueError("workflow template name is required")
        self.repositories.workspace_repository.upsert_workflow_template(workflow_template)
        return self.repositories.workspace_repository.get_workflow_template(workflow_template.id)

    def delete_workflow_template(self, template_id: str) -> None:
        self.repositories.workspace_repository.delete_workflow_template(template_id)

    def list_connectors(self):
        return [descriptor for _, descriptor in self.registries.connector_registry.list_items()]

    def list_generations(self):
        return [descriptor for _, descriptor in self.registries.generation_registry.list_items()]

    def list_renderers(self):
        return [descriptor for _, descriptor in self.registries.renderer_registry.list_items()]

    def get_workspace_builder_catalog(self) -> dict[str, Any]:
        catalog = workspace_builder_catalog().to_dict()
        catalog["connectors"] = [
            {
                "id": descriptor.id,
                "kind": descriptor.kind,
                "name": descriptor.name,
                "description": descriptor.description,
                "metadata": dict(descriptor.metadata),
            }
            for descriptor in self.list_connectors()
        ]
        catalog["generations"] = [
            {
                "id": descriptor.id,
                "kind": descriptor.kind,
                "name": descriptor.name,
                "description": descriptor.description,
                "metadata": dict(descriptor.metadata),
            }
            for descriptor in self.list_generations()
        ]
        catalog["renderers"] = [
            {
                "id": descriptor.id,
                "kind": descriptor.kind,
                "name": descriptor.name,
                "description": descriptor.description,
                "metadata": dict(descriptor.metadata),
            }
            for descriptor in self.list_renderers()
        ]
        return catalog

    def validate_workspace_builder_sources(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return validate_workspace_source_configuration(dict(payload))

    def start_quick_apply_run(
        self,
        workspace_id: str,
        *,
        manual_urls: list[str] | tuple[str, ...] | set[str] | str,
        execute: bool = True,
        enqueue: bool = False,
        requested_by: str = "api",
        max_attempts: int = 1,
    ) -> tuple[RunRecord, list[dict[str, Any]]]:
        if execute and enqueue:
            raise ValueError("run cannot be both queued and synchronously executed")

        workspace = self.repositories.workspace_repository.get_workspace(workspace_id)
        _validate_builder_workspace_definition(
            workspace,
            phase="run_preflight",
            error_code="run_preflight_failed",
        )
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
        run_input_overrides = {
            "manual_urls_inline": list(valid_urls),
            "manual_url_seed_list": list(valid_urls),
            "stage4_max_jobs": len(valid_urls),
        }
        run = RunRecord.create(
            workspace_id=workspace.id,
            workflow_template_id=workflow.id,
            run_input_overrides=run_input_overrides,
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
            run_input_overrides=run_input_overrides,
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
                run = self.enqueue_run(
                    workspace.id,
                    requested_by=SCHEDULED_RUN_REQUESTED_BY,
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
                        "metadata": {"auto_approved": True},
                    },
                )
                existing_reviews_by_job[job.job_id] = review

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
        return self.repositories.auth_repository.list_users()

    def get_user(self, user_id: str) -> UserRecord:
        return self.repositories.auth_repository.get_user(user_id)

    def upsert_user(self, payload: Mapping[str, Any] | UserRecord):
        user = payload if isinstance(payload, UserRecord) else UserRecord.from_dict(payload)
        if not user.user_id:
            if not user.email:
                raise ValueError("email is required")
            try:
                existing_user = self.repositories.auth_repository.get_user_by_email(user.email)
                role_was_provided = True
                if isinstance(payload, Mapping):
                    role_was_provided = bool(str(payload.get("role") or "").strip())
                user.user_id = existing_user.user_id
                if not user.display_name:
                    user.display_name = existing_user.display_name
                if not user.allowed_workspace_ids:
                    user.allowed_workspace_ids = list(existing_user.allowed_workspace_ids)
                if not user.metadata:
                    user.metadata = dict(existing_user.metadata)
                if not role_was_provided:
                    user.role = existing_user.role
                user.created_at = existing_user.created_at
                user.is_active = existing_user.is_active
            except KeyError:
                user = UserRecord.create(
                    email=user.email,
                    display_name=user.display_name,
                    role=user.role,
                    allowed_workspace_ids=user.allowed_workspace_ids,
                    metadata=user.metadata,
                )
        if not user.email:
            raise ValueError("email is required")
        if user.role not in ALLOWED_USER_ROLES:
            raise ValueError(f"unsupported role: {user.role}")
        user.updated_at = utc_now_iso()
        self.repositories.auth_repository.upsert_user(user)
        return self.repositories.auth_repository.get_user(user.user_id)

    def delete_user(self, user_id: str) -> None:
        self.repositories.auth_repository.delete_user(user_id)

    def list_referral_contacts(self, user_id: str) -> list[ReferralContactRecord]:
        user = self.repositories.auth_repository.get_user(user_id)
        contacts = [
            ReferralContactRecord.from_dict(item)
            for item in (user.metadata or {}).get("referrals") or []
            if isinstance(item, dict)
        ]
        return contacts

    def get_referral_contact(self, user_id: str, contact_id: str) -> ReferralContactRecord:
        for contact in self.list_referral_contacts(user_id):
            if contact.contact_id == contact_id:
                return contact
        raise KeyError(f"Referral contact '{contact_id}' not found.")

    def upsert_referral_contact(
        self,
        *,
        user_id: str,
        payload: Mapping[str, Any] | ReferralContactRecord,
        contact_id: str = "",
    ) -> ReferralContactRecord:
        user = self.repositories.auth_repository.get_user(user_id)
        contact = payload if isinstance(payload, ReferralContactRecord) else ReferralContactRecord.from_dict(payload)
        if contact_id:
            contact.contact_id = contact_id
        if not contact.contact_id:
            contact = ReferralContactRecord.create(
                name=contact.name,
                company=contact.company,
                companies=contact.companies,
                linkedin_url=contact.linkedin_url,
                relationship_note=contact.relationship_note,
                can_refer=contact.can_refer,
                source_kind=contact.source_kind,
                import_batch_id=contact.import_batch_id,
                import_ref=contact.import_ref,
                metadata=contact.metadata,
            )
        if not contact.name:
            raise ValueError("contact name is required")
        contact.company = contact.primary_company()
        contact.can_refer = bool(contact.can_refer or any(bool(item.get("can_refer")) for item in contact.companies))
        contact.updated_at = utc_now_iso()

        contacts = self.list_referral_contacts(user_id)
        replaced = False
        normalized_contacts: list[ReferralContactRecord] = []
        for existing in contacts:
            if existing.contact_id == contact.contact_id:
                normalized_contacts.append(contact)
                replaced = True
            else:
                normalized_contacts.append(existing)
        if not replaced:
            normalized_contacts.append(contact)
        self._persist_referral_contacts(user, normalized_contacts)
        return self.get_referral_contact(user_id, contact.contact_id)

    def import_referral_contacts(
        self,
        *,
        user_id: str,
        csv_text: str,
        source_kind: str = "linkedin_csv",
    ) -> dict[str, Any]:
        if not str(csv_text or "").strip():
            raise ValueError("csv_text is required")
        user = self.repositories.auth_repository.get_user(user_id)
        import_batch_id = f"import_{uuid4().hex[:12]}"
        parsed_contacts = parse_referral_contacts_csv(
            csv_text,
            source_kind=source_kind,
            import_batch_id=import_batch_id,
        )
        if not parsed_contacts:
            raise ValueError("No contacts could be parsed from the CSV.")
        existing_contacts = self.list_referral_contacts(user_id)
        merged_contacts, summary = merge_referral_contacts(existing_contacts, parsed_contacts)
        for contact in merged_contacts:
            contact.updated_at = utc_now_iso()
        self._persist_referral_contacts(user, merged_contacts)
        refreshed_contacts = self.list_referral_contacts(user_id)
        imported_contact_ids = {
            contact.contact_id
            for contact in refreshed_contacts
            if contact.import_batch_id == import_batch_id
        }
        return {
            "import_batch_id": import_batch_id,
            "source_kind": source_kind,
            "summary": {
                **summary,
                "parsed": len(parsed_contacts),
                "total_contacts": len(refreshed_contacts),
            },
            "contacts": [contact.to_dict() for contact in refreshed_contacts if contact.contact_id in imported_contact_ids],
        }

    def delete_referral_contact(self, user_id: str, contact_id: str) -> None:
        user = self.repositories.auth_repository.get_user(user_id)
        contacts = self.list_referral_contacts(user_id)
        kept_contacts = [contact for contact in contacts if contact.contact_id != contact_id]
        if len(kept_contacts) == len(contacts):
            raise KeyError(f"Referral contact '{contact_id}' not found.")
        self._persist_referral_contacts(user, kept_contacts)

    def generate_referral_outreach(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
        contact_id: str = "",
    ) -> dict[str, Any]:
        user = self.repositories.auth_repository.get_user(user_id)
        job = self._get_job_for_run(run_id=run_id, job_id=job_id)
        contacts = self.list_referral_contacts(user_id)
        matches = find_referral_contacts_for_company(contacts, job.company)
        if contact_id:
            contact = next((item for item in matches if item.contact_id == contact_id), None)
            if contact is None:
                contact = self.get_referral_contact(user_id, contact_id)
        else:
            contact = matches[0] if matches else None
        if contact is None:
            raise ValueError("No referral contact matches this job yet.")
        profile = dict((user.metadata or {}).get("profile") or {})
        payload = build_referral_outreach_draft(profile=profile, job=job, contact=contact)
        payload["matched_contacts"] = [item.to_dict() for item in matches]
        return payload

    def generate_hiring_manager_outreach(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        user = self.repositories.auth_repository.get_user(user_id)
        job = self._get_job_for_run(run_id=run_id, job_id=job_id)
        profile = dict((user.metadata or {}).get("profile") or {})
        hiring_manager = guess_hiring_manager_from_job(job)
        return build_hiring_manager_outreach_draft(
            profile=profile,
            job=job,
            hiring_manager=hiring_manager,
        )

    def generate_target_contact_discovery(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        user = self.repositories.auth_repository.get_user(user_id)
        job = self._get_job_for_run(run_id=run_id, job_id=job_id)
        profile = dict((user.metadata or {}).get("profile") or {})
        return build_target_contact_discovery(profile=profile, job=job)

    def get_job_workspace(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        user = self.repositories.auth_repository.get_user(user_id)
        run = self.get_run(run_id)
        workspace = self.get_workspace(run.workspace_id)
        job = self._get_job_for_run(run_id=run_id, job_id=job_id)
        return self._job_workspace_payload(
            user=user,
            run_id=run_id,
            job=job,
            workspace=workspace,
        )

    def get_relevant_people_discovery_status(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        workspace_payload = self.get_job_workspace(
            user_id=user_id,
            run_id=run_id,
            job_id=job_id,
        )
        discovery = normalize_relevant_people_discovery_run(
            workspace_payload.get("relevant_people_discovery") or {}
        )
        return {
            "runId": str(run_id or ""),
            "jobId": str(job_id or ""),
            "workspaceId": str(workspace_payload.get("workspace_id") or ""),
            "peopleDiscoveryStatus": str(discovery.get("peopleDiscoveryStatus") or ""),
            "selectedPeopleCount": len(discovery.get("selectedPeople") or []),
            "lastStartedAt": str(discovery.get("lastStartedAt") or ""),
            "lastCompletedAt": str(discovery.get("lastCompletedAt") or ""),
            "lastUpdatedAt": str(discovery.get("lastUpdatedAt") or ""),
            "error": str(discovery.get("error") or ""),
        }

    def get_relevant_people_discovery_results(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        workspace_payload = self.get_job_workspace(
            user_id=user_id,
            run_id=run_id,
            job_id=job_id,
        )
        return normalize_relevant_people_discovery_run(
            workspace_payload.get("relevant_people_discovery") or {}
        )

    def start_relevant_people_discovery(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        user = self.repositories.auth_repository.get_user(user_id)
        run = self.get_run(run_id)
        workspace = self.get_workspace(run.workspace_id)
        job = self._get_job_for_run(run_id=run_id, job_id=job_id)
        started_at = utc_now_iso()
        running_payload = build_empty_relevant_people_discovery(
            job=job,
            run_id=run_id,
            workspace_id=workspace.id,
            status=PEOPLE_DISCOVERY_STATUS_RUNNING,
            last_started_at=started_at,
        )
        self._persist_job_application_context(
            user,
            run_id=run_id,
            job_id=job_id,
            context_payload={RELEVANT_PEOPLE_DISCOVERY_CONTEXT_KEY: running_payload},
        )

        profile = dict((user.metadata or {}).get("profile") or {})
        try:
            completed_payload = build_relevant_people_discovery(
                profile=profile,
                job=job,
                run_id=run_id,
                workspace_id=workspace.id,
                last_started_at=started_at,
            )
        except Exception as exc:
            failed_payload = build_empty_relevant_people_discovery(
                job=job,
                run_id=run_id,
                workspace_id=workspace.id,
                status=PEOPLE_DISCOVERY_STATUS_FAILED,
                error=str(exc),
                last_started_at=started_at,
            )
            self._persist_job_application_context(
                user,
                run_id=run_id,
                job_id=job_id,
                context_payload={RELEVANT_PEOPLE_DISCOVERY_CONTEXT_KEY: failed_payload},
            )
            raise

        self._persist_job_application_context(
            user,
            run_id=run_id,
            job_id=job_id,
            context_payload={RELEVANT_PEOPLE_DISCOVERY_CONTEXT_KEY: completed_payload},
        )
        return completed_payload

    def set_relevant_people_status(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
        person_id: str,
        status: str,
    ) -> dict[str, Any]:
        user = self.repositories.auth_repository.get_user(user_id)
        current_payload = self.get_relevant_people_discovery_results(
            user_id=user_id,
            run_id=run_id,
            job_id=job_id,
        )
        updated_payload = update_relevant_people_status(
            current_payload,
            person_id=person_id,
            status=status,
        )
        self._persist_job_application_context(
            user,
            run_id=run_id,
            job_id=job_id,
            context_payload={RELEVANT_PEOPLE_DISCOVERY_CONTEXT_KEY: updated_payload},
        )
        return updated_payload

    def list_api_tokens(
        self,
        *,
        user_id: str = "",
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ApiTokenRecord]:
        repository = self.repositories.auth_repository
        try:
            return repository.list_api_tokens(
                user_id=user_id,
                active_only=not include_inactive,
                limit=limit,
                offset=offset,
            )
        except TypeError:
            tokens = repository.list_api_tokens(user_id=user_id, active_only=not include_inactive)
            normalized_offset = max(0, int(offset))
            normalized_limit = max(1, int(limit))
            return tokens[normalized_offset : normalized_offset + normalized_limit]

    def issue_api_token(
        self,
        *,
        user_id: str,
        name: str,
        scopes: list[str] | None = None,
        expires_at: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[ApiTokenRecord, str]:
        user = self.repositories.auth_repository.get_user(user_id)
        if not user.is_active:
            raise ValueError(f"User '{user_id}' is inactive.")
        token_record, raw_token = issue_api_token(
            user_id=user.user_id,
            token_name=name,
            user_role=user.role,
            scopes=scopes,
            expires_at=expires_at,
            metadata=dict(metadata or {}),
        )
        self.repositories.auth_repository.upsert_api_token(token_record)
        return self.repositories.auth_repository.get_api_token(token_record.token_id), raw_token

    def revoke_api_token(self, token_id: str) -> ApiTokenRecord:
        token = self.repositories.auth_repository.get_api_token(token_id)
        token.is_active = False
        token.updated_at = utc_now_iso()
        self.repositories.auth_repository.upsert_api_token(token)
        return self.repositories.auth_repository.get_api_token(token_id)

    def authenticate_access_token(self, raw_token: str) -> tuple[UserRecord, ApiTokenRecord]:
        token_text = str(raw_token or "").strip()
        if not token_text:
            raise PermissionError("Missing access token.")
        candidate_lookup = getattr(self.repositories.auth_repository, "list_api_tokens_for_value", None)
        candidate_tokens: list[ApiTokenRecord] = []
        if callable(candidate_lookup):
            candidate_tokens = list(candidate_lookup(token_text, active_only=True))
        tokens_to_check = candidate_tokens or self.repositories.auth_repository.list_api_tokens(active_only=True)
        for token in tokens_to_check:
            if not token.is_active or token_is_expired(token.expires_at):
                continue
            if not verify_token_value(token_text, token.token_hash):
                continue
            user = self.repositories.auth_repository.get_user(token.user_id)
            if not user.is_active:
                raise PermissionError("User is inactive.")
            token.last_used_at = utc_now_iso()
            token.updated_at = token.last_used_at
            self.repositories.auth_repository.upsert_api_token(token)
            return user, self.repositories.auth_repository.get_api_token(token.token_id)
        raise PermissionError("Invalid or expired access token.")

    def user_has_scope(self, token: ApiTokenRecord, required_scope: str) -> bool:
        return token_has_scope(token.scopes, required_scope)

    def user_can_access_workspace(self, user: UserRecord, workspace_id: str) -> bool:
        if user.role == ROLE_ADMIN:
            return True
        allowed = {item for item in user.allowed_workspace_ids if item}
        if not allowed:
            return True
        return workspace_id in allowed

    def list_secrets(self, *, workspace_id: str = "", limit: int = 100, offset: int = 0) -> list[SecretRecord]:
        repository = self.repositories.secret_store
        try:
            return repository.list_secrets(workspace_id=workspace_id, limit=limit, offset=offset)
        except TypeError:
            secrets = repository.list_secrets(workspace_id=workspace_id)
            normalized_offset = max(0, int(offset))
            normalized_limit = max(1, int(limit))
            return secrets[normalized_offset : normalized_offset + normalized_limit]

    def get_secret(self, secret_id: str) -> SecretRecord:
        return self.repositories.secret_store.get_secret(secret_id)

    def upsert_secret(self, payload: Mapping[str, Any] | SecretRecord):
        secret = payload if isinstance(payload, SecretRecord) else SecretRecord.from_dict(payload)
        existing_secret = None
        if secret.secret_id:
            try:
                existing_secret = self.repositories.secret_store.get_secret(secret.secret_id)
            except KeyError:
                existing_secret = None
        if not secret.secret_id:
            if not secret.name:
                raise ValueError("secret name is required")
            secret = SecretRecord.create(
                name=secret.name,
                provider=secret.provider,
                workspace_id=secret.workspace_id,
                description=secret.description,
                env_var_name=secret.env_var_name,
                secret_value=secret.secret_value,
                metadata=secret.metadata,
            )
        if not secret.name:
            raise ValueError("secret name is required")
        if secret.provider not in {SECRET_PROVIDER_STORED, SECRET_PROVIDER_ENV}:
            raise ValueError(f"unsupported secret provider: {secret.provider}")
        if existing_secret is not None:
            if not secret.secret_value and existing_secret.provider == SECRET_PROVIDER_STORED:
                secret.secret_value = existing_secret.secret_value
            if not secret.env_var_name and existing_secret.provider == SECRET_PROVIDER_ENV:
                secret.env_var_name = existing_secret.env_var_name
        if secret.provider == SECRET_PROVIDER_ENV and not secret.env_var_name:
            raise ValueError("env_var_name is required for env secrets")
        if secret.provider == SECRET_PROVIDER_STORED and not secret.secret_value:
            raise ValueError("secret_value is required for stored secrets")
        secret.updated_at = utc_now_iso()
        self.repositories.secret_store.upsert_secret(secret)
        return self.repositories.secret_store.get_secret(secret.secret_id)

    def delete_secret(self, secret_id: str) -> None:
        self.repositories.secret_store.delete_secret(secret_id)

    def resolve_secret_value(self, secret_id: str) -> str:
        secret = self.repositories.secret_store.get_secret(secret_id)
        return resolve_secret_references(f"${{secret:{secret.secret_id}}}", secret_lookup=self.repositories.secret_store.get_secret)

    def resolve_runtime_value(self, payload: Any) -> Any:
        return resolve_secret_references(payload, secret_lookup=self.repositories.secret_store.get_secret)

    def _persist_referral_contacts(self, user: UserRecord, contacts: list[ReferralContactRecord]) -> None:
        metadata = dict(user.metadata or {})
        metadata["referrals"] = [contact.to_dict() for contact in contacts]
        user.metadata = metadata
        user.updated_at = utc_now_iso()
        self.repositories.auth_repository.upsert_user(user)

    def _job_application_context_key(self, *, run_id: str, job_id: str) -> str:
        return f"{str(run_id or '').strip()}::{str(job_id or '').strip()}"

    def _load_job_application_context(self, user: UserRecord, *, run_id: str, job_id: str) -> dict[str, Any]:
        metadata = dict(user.metadata or {})
        all_contexts = dict(metadata.get(APPLICATION_CONTEXTS_METADATA_KEY) or {})
        context_key = self._job_application_context_key(run_id=run_id, job_id=job_id)
        return dict(all_contexts.get(context_key) or {})

    def _persist_job_application_context(
        self,
        user: UserRecord,
        *,
        run_id: str,
        job_id: str,
        context_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        metadata = dict(user.metadata or {})
        all_contexts = dict(metadata.get(APPLICATION_CONTEXTS_METADATA_KEY) or {})
        context_key = self._job_application_context_key(run_id=run_id, job_id=job_id)
        existing_context = dict(all_contexts.get(context_key) or {})
        merged_context = {
            **existing_context,
            **dict(context_payload or {}),
            "run_id": str(run_id or "").strip(),
            "job_id": str(job_id or "").strip(),
            "updated_at": utc_now_iso(),
        }
        all_contexts[context_key] = merged_context
        metadata[APPLICATION_CONTEXTS_METADATA_KEY] = all_contexts
        user.metadata = metadata
        user.updated_at = utc_now_iso()
        self.repositories.auth_repository.upsert_user(user)
        refreshed_user = self.repositories.auth_repository.get_user(user.user_id)
        return self._load_job_application_context(refreshed_user, run_id=run_id, job_id=job_id)

    def _job_workspace_payload(
        self,
        *,
        user: UserRecord,
        run_id: str,
        job: JobRecord,
        workspace: WorkspaceDefinition,
    ) -> dict[str, Any]:
        stored_context = self._load_job_application_context(user, run_id=run_id, job_id=job.job_id)
        relevant_people_discovery = stored_context.get(RELEVANT_PEOPLE_DISCOVERY_CONTEXT_KEY)
        if relevant_people_discovery:
            normalized_discovery = normalize_relevant_people_discovery_run(
                dict(relevant_people_discovery or {})
            )
        else:
            normalized_discovery = build_empty_relevant_people_discovery(
                job=job,
                run_id=run_id,
                workspace_id=workspace.id,
            )
        job_payload = job.to_dict()
        description_text = str(job.description_text or job_payload.get("description") or "").strip()
        return {
            "run_id": run_id,
            "workspace_id": workspace.id,
            "workspace_name": workspace.name,
            "job": {
                **job_payload,
                "job_id": str(job.job_id or ""),
                "title": str(job.title or ""),
                "company": str(job.company or ""),
                "location": str(job.location_raw or ""),
                "apply_link": str(job.apply_link or job.link or job.source_url or ""),
                "description_text": description_text,
            },
            "selected_relevant_people": [
                person
                for person in normalized_discovery.get("selectedPeople") or []
                if isinstance(person, dict)
            ],
            "relevant_people_discovery": normalized_discovery,
            "application_context": stored_context,
        }

    def _get_job_for_run(self, *, run_id: str, job_id: str) -> JobRecord:
        self.repositories.run_repository.get(run_id)
        for jobs in self.repositories.job_store.load_all_job_sets(run_id).values():
            for job in jobs:
                if job.job_id == job_id:
                    return job
        raise KeyError(f"Job '{job_id}' not found for run '{run_id}'.")

    def get_run(self, run_id: str) -> RunRecord:
        return self.repositories.run_repository.get(run_id)

    def delete_run(self, run_id: str) -> None:
        run = self.repositories.run_repository.get(run_id)
        deletable_statuses = {
            RUN_STATUS_PLANNED,
            RUN_STATUS_QUEUED,
            RUN_STATUS_CANCELLED,
            RUN_STATUS_FAILED,
            RUN_STATUS_COMPLETED,
        }
        if run.status not in deletable_statuses:
            raise ValueError(
                "only planned, queued, completed, failed, or cancelled runs can be deleted",
            )

        self.repositories.job_store.clear_run(run_id)
        self.repositories.artifact_store.clear_run(run_id)

        for review in self.list_reviews(run_id=run_id, limit=100000, offset=0):
            self.repositories.review_store.delete_review(review.review_id)

        for worker in self.list_workers(limit=1000, offset=0, status=""):
            if worker.current_run_id != run_id:
                continue
            worker.current_run_id = ""
            worker.status = WORKER_STATUS_IDLE
            worker.last_heartbeat_at = utc_now_iso()
            worker.lease_expires_at = worker.last_heartbeat_at
            self.repositories.worker_store.upsert_worker(worker)

        self.repositories.run_repository.delete(run_id)

    def list_runs(self, *, limit: int = 50, offset: int = 0, status: str = "", workspace_id: str = ""):
        repository = self.repositories.run_repository
        try:
            return repository.list_runs(limit=limit, offset=offset, status=status, workspace_id=workspace_id)
        except TypeError:
            runs = repository.list_runs(limit=max(1, int(limit)) + max(0, int(offset)), status=status, workspace_id=workspace_id)
            normalized_offset = max(0, int(offset))
            normalized_limit = max(1, int(limit))
            return runs[normalized_offset : normalized_offset + normalized_limit]

    def list_job_sets(self, run_id: str) -> dict[str, list[JobRecord]]:
        self.repositories.run_repository.get(run_id)
        return self.repositories.job_store.load_all_job_sets(run_id)

    def get_job_set(self, run_id: str, set_key: str) -> list[JobRecord]:
        self.repositories.run_repository.get(run_id)
        return self.repositories.job_store.load_job_set(run_id, set_key)

    def upsert_job_set(self, run_id: str, set_key: str, jobs: list[Mapping[str, Any] | JobRecord]) -> list[JobRecord]:
        self.repositories.run_repository.get(run_id)
        job_records = [job if isinstance(job, JobRecord) else JobRecord.from_mapping(job) for job in jobs]
        self.repositories.job_store.save_job_set(run_id, set_key, job_records)
        self._refresh_run_job_keys(run_id)
        return self.repositories.job_store.load_job_set(run_id, set_key)

    def delete_job_set(self, run_id: str, set_key: str) -> None:
        self.repositories.run_repository.get(run_id)
        self.repositories.job_store.delete_job_set(run_id, set_key)
        self._refresh_run_job_keys(run_id)

    def delete_job(self, run_id: str, job_id: str) -> None:
        run = self.repositories.run_repository.get(run_id)
        if run.status in {RUN_STATUS_RUNNING, RUN_STATUS_CANCEL_REQUESTED}:
            raise ValueError("stop the run before deleting jobs")

        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            raise ValueError("job_id is required")

        removed_from_job_sets = False
        removed_reviews = False
        removed_artifacts = False
        removed_blob_references = False
        remaining_job_ids: set[str] = set()

        for set_key, jobs in self.list_job_sets(run_id).items():
            remaining_jobs = [job for job in jobs if job.job_id != normalized_job_id]
            remaining_job_ids.update(
                str(job.job_id or "").strip()
                for job in remaining_jobs
                if str(job.job_id or "").strip()
            )
            if len(remaining_jobs) == len(jobs):
                continue
            removed_from_job_sets = True
            if remaining_jobs:
                self.repositories.job_store.save_job_set(run_id, set_key, remaining_jobs)
            else:
                self.repositories.job_store.delete_job_set(run_id, set_key)

        for review in self.list_reviews(run_id=run_id, limit=100000, offset=0):
            if review.job_id != normalized_job_id:
                continue
            self.repositories.review_store.delete_review(review.review_id)
            removed_reviews = True

        for artifact in self.list_artifacts(run_id):
            should_delete_artifact = _artifact_matches_job(artifact, normalized_job_id)
            if not should_delete_artifact and not remaining_job_ids:
                should_delete_artifact = _artifact_is_generated_document_container(artifact)
            if not should_delete_artifact:
                continue
            self.repositories.artifact_store.delete_artifact(run_id, artifact.artifact_id)
            removed_artifacts = True

        for blob_key in self.repositories.job_store.list_blob_keys(run_id):
            blob_value = self.repositories.job_store.load_blob(run_id, blob_key, None)
            cleaned_blob_value, blob_changed = _remove_job_from_blob_payload(blob_value, normalized_job_id)
            if not blob_changed:
                continue
            self.repositories.job_store.save_blob(run_id, blob_key, cleaned_blob_value)
            removed_blob_references = True

        if not any(
            (
                removed_from_job_sets,
                removed_reviews,
                removed_artifacts,
                removed_blob_references,
            )
        ):
            raise KeyError(f"Job '{normalized_job_id}' not found for run '{run_id}'.")

        self._refresh_run_job_keys(run_id)

    def list_artifacts(self, run_id: str) -> list[ArtifactRecord]:
        self.repositories.run_repository.get(run_id)
        return self.repositories.artifact_store.load_artifacts(run_id)

    def get_artifact(self, run_id: str, artifact_id: str) -> ArtifactRecord:
        self.repositories.run_repository.get(run_id)
        return self.repositories.artifact_store.get_artifact(run_id, artifact_id)

    def upsert_artifact(self, run_id: str, payload: Mapping[str, Any] | ArtifactRecord) -> ArtifactRecord:
        self.repositories.run_repository.get(run_id)
        artifact = payload if isinstance(payload, ArtifactRecord) else ArtifactRecord.from_dict(payload)
        if not artifact.artifact_id:
            raise ValueError("artifact_id is required")
        self.repositories.artifact_store.upsert_artifact(run_id, artifact)
        return self.repositories.artifact_store.get_artifact(run_id, artifact.artifact_id)

    def delete_artifact(self, run_id: str, artifact_id: str) -> None:
        self.repositories.run_repository.get(run_id)
        self.repositories.artifact_store.delete_artifact(run_id, artifact_id)

    def list_reviews(
        self,
        *,
        run_id: str = "",
        job_id: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[ReviewRecord]:
        repository = self.repositories.review_store
        try:
            return repository.list_reviews(run_id=run_id, job_id=job_id, limit=limit, offset=offset)
        except TypeError:
            reviews = repository.list_reviews(run_id=run_id, job_id=job_id, limit=max(1, int(limit)) + max(0, int(offset)))
            normalized_offset = max(0, int(offset))
            normalized_limit = max(1, int(limit))
            return reviews[normalized_offset : normalized_offset + normalized_limit]

    def get_review(self, review_id: str) -> ReviewRecord:
        return self.repositories.review_store.get_review(review_id)

    def upsert_review(
        self,
        *,
        run_id: str,
        payload: Mapping[str, Any] | ReviewRecord,
        review_id: str = "",
    ) -> ReviewRecord:
        self.repositories.run_repository.get(run_id)
        review = payload if isinstance(payload, ReviewRecord) else ReviewRecord.from_dict(payload)
        if not review.job_id:
            raise ValueError("job_id is required")
        normalized_review_id = str(review_id or review.review_id or "").strip()
        existing_review = None
        if normalized_review_id:
            try:
                existing_review = self.repositories.review_store.get_review(normalized_review_id)
            except KeyError:
                existing_review = None
        if existing_review is None:
            matching_reviews = self.list_reviews(run_id=run_id, job_id=review.job_id, limit=1, offset=0)
            if matching_reviews:
                existing_review = matching_reviews[0]
                if not normalized_review_id:
                    normalized_review_id = existing_review.review_id
        if not normalized_review_id:
            review = ReviewRecord.create(
                run_id=run_id,
                job_id=review.job_id,
                status=review.status,
                decision=review.decision,
                reviewer=review.reviewer,
                notes=review.notes,
                job_set_key=review.job_set_key,
                metadata=review.metadata,
            )
        else:
            review.review_id = normalized_review_id
            if existing_review is not None:
                review.created_at = existing_review.created_at
                if not review.job_set_key:
                    review.job_set_key = existing_review.job_set_key
                review.metadata = {
                    **dict(existing_review.metadata or {}),
                    **dict(review.metadata or {}),
                }
        review.run_id = run_id
        review.updated_at = utc_now_iso()
        self.repositories.review_store.upsert_review(review)
        return self.repositories.review_store.get_review(review.review_id)

    def delete_review(self, review_id: str) -> None:
        self.repositories.review_store.delete_review(review_id)

    def list_workers(self, *, limit: int = 50, offset: int = 0, status: str = "") -> list[WorkerRecord]:
        repository = self.repositories.worker_store
        try:
            return repository.list_workers(limit=limit, offset=offset, status=status)
        except TypeError:
            workers = repository.list_workers(limit=max(1, int(limit)) + max(0, int(offset)), status=status)
            normalized_offset = max(0, int(offset))
            normalized_limit = max(1, int(limit))
            return workers[normalized_offset : normalized_offset + normalized_limit]

    def get_worker(self, worker_id: str) -> WorkerRecord:
        return self.repositories.worker_store.get_worker(worker_id)

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
        now = utc_now_iso()
        try:
            worker = self.repositories.worker_store.get_worker(worker_id)
        except KeyError:
            worker = WorkerRecord.create(
                worker_id=worker_id,
                status=status,
                host_name=host_name,
                process_id=process_id,
                current_run_id=current_run_id,
                lease_expires_at=utc_plus_seconds(lease_seconds),
                metadata=metadata,
            )
        worker.status = status
        worker.current_run_id = str(current_run_id or "")
        worker.host_name = str(host_name or worker.host_name)
        worker.process_id = int(process_id or worker.process_id or 0)
        worker.last_heartbeat_at = now
        worker.lease_expires_at = utc_plus_seconds(lease_seconds)
        if metadata is not None:
            worker.metadata = dict(metadata)
        self.repositories.worker_store.upsert_worker(worker)
        return self.repositories.worker_store.get_worker(worker.worker_id)

    def stop_worker(self, worker_id: str) -> WorkerRecord:
        worker = self.repositories.worker_store.get_worker(worker_id)
        worker.status = WORKER_STATUS_STOPPED
        worker.current_run_id = ""
        worker.last_heartbeat_at = utc_now_iso()
        worker.lease_expires_at = worker.last_heartbeat_at
        self.repositories.worker_store.upsert_worker(worker)
        return self.repositories.worker_store.get_worker(worker_id)

    def recover_stale_workers(self) -> list[WorkerRecord]:
        now = utc_now_iso()
        stale_workers = self.repositories.worker_store.list_expired_workers(expires_before=now)
        recovered: list[WorkerRecord] = []
        for worker in stale_workers:
            if worker.current_run_id:
                try:
                    run = self.repositories.run_repository.get(worker.current_run_id)
                except KeyError:
                    run = None
                if run is not None and run.status in {RUN_STATUS_RUNNING, RUN_STATUS_CANCEL_REQUESTED}:
                    run.status = RUN_STATUS_QUEUED
                    run.current_stage_id = ""
                    run.updated_at = now
                    run.last_error = "Recovered from expired worker lease."
                    self.repositories.run_repository.save(run)
            worker.status = WORKER_STATUS_STALE
            worker.current_run_id = ""
            worker.last_heartbeat_at = now
            worker.lease_expires_at = now
            self.repositories.worker_store.upsert_worker(worker)
            recovered.append(worker)
        return recovered

    def _fail_run_preflight(self, run: RunRecord, exc: BackendValidationError) -> RunRecord:
        now = utc_now_iso()
        metadata = dict(run.metadata or {})
        metadata["preflight_error"] = {
            "code": exc.error_code,
            "message": str(exc),
            "details": dict(exc.details),
        }
        run.metadata = metadata
        run.status = RUN_STATUS_FAILED
        run.current_stage_id = ""
        run.last_error = str(exc)
        run.finished_at = now
        run.updated_at = now
        self.repositories.run_repository.save(run)
        return self.repositories.run_repository.get(run.id)

    def start_run(
        self,
        workspace_id: str,
        *,
        run_input_overrides: Mapping[str, Any] | None = None,
        execute: bool = True,
        enqueue: bool = False,
        requested_by: str = "cli",
        max_attempts: int = 1,
    ) -> RunRecord:
        if execute and enqueue:
            raise ValueError("run cannot be both queued and synchronously executed")
        workspace = self.repositories.workspace_repository.get_workspace(workspace_id)
        _validate_builder_workspace_definition(
            workspace,
            phase="run_preflight",
            error_code="run_preflight_failed",
        )
        workflow = self.repositories.workspace_repository.get_workflow_template(workspace.workflow_template_id)

        run = RunRecord.create(
            workspace_id=workspace.id,
            workflow_template_id=workflow.id,
            run_input_overrides=run_input_overrides or {},
            requested_by=requested_by,
            max_attempts=max_attempts,
            metadata={"workspace_type": workspace.workspace_type},
        )
        run.run_plan = self.stage_engine.build_run_plan(
            workspace=workspace,
            workflow=workflow,
            run_input_overrides=run_input_overrides or {},
        )
        self.repositories.run_repository.save(run)

        if enqueue:
            return self._queue_run(run)
        if not execute:
            return self.repositories.run_repository.get(run.id)
        return self._execute_run(run, workspace=workspace, workflow=workflow, auto_retry_failed=False)

    def enqueue_run(
        self,
        workspace_id: str,
        *,
        run_input_overrides: Mapping[str, Any] | None = None,
        requested_by: str = "api",
        max_attempts: int = 1,
    ) -> RunRecord:
        return self.start_run(
            workspace_id,
            run_input_overrides=run_input_overrides,
            execute=False,
            enqueue=True,
            requested_by=requested_by,
            max_attempts=max_attempts,
        )

    def claim_next_queued_run(
        self,
        *,
        worker_id: str = "",
        host_name: str = "",
        process_id: int = 0,
        lease_seconds: int = 60,
    ) -> RunRecord | None:
        if worker_id:
            self.recover_stale_workers()
        self.enqueue_due_scheduled_runs()
        run = self.repositories.run_repository.claim_next_queued()
        if run is None:
            if worker_id:
                self.heartbeat_worker(
                    worker_id=worker_id,
                    status=WORKER_STATUS_IDLE,
                    current_run_id="",
                    host_name=host_name,
                    process_id=process_id,
                    lease_seconds=lease_seconds,
                )
            return None
        if worker_id:
            self.heartbeat_worker(
                worker_id=worker_id,
                status=WORKER_STATUS_RUNNING,
                current_run_id=run.id,
                host_name=host_name,
                process_id=process_id,
                lease_seconds=lease_seconds,
            )
        return run

    def execute_claimed_run(self, run_id: str, *, auto_retry_failed: bool = True) -> RunRecord:
        run = self.repositories.run_repository.get(run_id)
        workspace = self._workspace_from_run_snapshot(run)
        workflow = self._workflow_from_run_snapshot(run)
        try:
            _validate_builder_workspace_definition(
                workspace,
                phase="run_preflight",
                error_code="run_preflight_failed",
                run_plan_settings=run.run_plan.resolved_run_settings if run.run_plan else {},
            )
        except BackendValidationError as exc:
            return self._fail_run_preflight(run, exc)
        return self._execute_run(run, workspace=workspace, workflow=workflow, auto_retry_failed=auto_retry_failed)

    def release_worker(self, worker_id: str, *, status: str = WORKER_STATUS_IDLE) -> WorkerRecord | None:
        if not worker_id:
            return None
        try:
            worker = self.repositories.worker_store.get_worker(worker_id)
        except KeyError:
            return None
        worker.status = status
        worker.current_run_id = ""
        worker.last_heartbeat_at = utc_now_iso()
        worker.lease_expires_at = worker.last_heartbeat_at
        self.repositories.worker_store.upsert_worker(worker)
        return self.repositories.worker_store.get_worker(worker_id)

    def process_next_queued_run(
        self,
        *,
        auto_retry_failed: bool = True,
        worker_id: str = "",
        host_name: str = "",
        process_id: int = 0,
        lease_seconds: int = 60,
    ) -> RunRecord | None:
        run = self.claim_next_queued_run(
            worker_id=worker_id,
            host_name=host_name,
            process_id=process_id,
            lease_seconds=lease_seconds,
        )
        if run is None:
            return None
        try:
            return self.execute_claimed_run(run.id, auto_retry_failed=auto_retry_failed)
        finally:
            if worker_id:
                self.release_worker(worker_id)

    def cancel_run(self, run_id: str) -> RunRecord:
        run = self.repositories.run_repository.get(run_id)
        now = utc_now_iso()
        if run.status in {RUN_STATUS_COMPLETED, RUN_STATUS_FAILED, RUN_STATUS_CANCELLED}:
            return run
        if run.status == RUN_STATUS_RUNNING:
            run.status = RUN_STATUS_CANCEL_REQUESTED
        else:
            run.status = RUN_STATUS_CANCELLED
            run.finished_at = now
            run.current_stage_id = ""
        run.updated_at = now
        self.repositories.run_repository.save(run)
        return self.repositories.run_repository.get(run.id)

    def retry_run(self, run_id: str) -> RunRecord:
        run = self.repositories.run_repository.get(run_id)
        if run.status not in {RUN_STATUS_FAILED, RUN_STATUS_CANCELLED}:
            raise ValueError("only failed or cancelled runs can be retried")
        _validate_builder_workspace_definition(
            self._workspace_from_run_snapshot(run),
            phase="run_preflight",
            error_code="run_preflight_failed",
            run_plan_settings=run.run_plan.resolved_run_settings if run.run_plan else {},
        )
        self.repositories.job_store.clear_run(run.id)
        self.repositories.artifact_store.clear_run(run.id)
        run.stage_results = []
        run.final_job_set_keys = []
        run.current_stage_id = ""
        run.last_error = ""
        run.started_at = ""
        run.finished_at = ""
        return self._queue_run(run)

    def resume_run(self, run_id: str) -> RunRecord:
        run = self.repositories.run_repository.get(run_id)
        if run.status not in {RUN_STATUS_PLANNED, RUN_STATUS_FAILED, RUN_STATUS_CANCELLED}:
            raise ValueError("only planned, failed, or cancelled runs can be resumed")
        _validate_builder_workspace_definition(
            self._workspace_from_run_snapshot(run),
            phase="run_preflight",
            error_code="run_preflight_failed",
            run_plan_settings=run.run_plan.resolved_run_settings if run.run_plan else {},
        )
        self._trim_to_resumable_prefix(run)
        run.final_job_set_keys = sorted(self.repositories.job_store.list_job_set_keys(run.id))
        run.current_stage_id = ""
        run.last_error = ""
        run.started_at = ""
        run.finished_at = ""
        return self._queue_run(run)

    def _execute_run(
        self,
        run: RunRecord,
        *,
        workspace: WorkspaceDefinition,
        workflow: WorkflowTemplate,
        auto_retry_failed: bool,
    ) -> RunRecord:
        logger = logging.getLogger(f"backend.run.{run.id}")
        raw_run_settings = dict(run.run_plan.resolved_run_settings if run.run_plan else {})
        resolved_run_settings = self.resolve_runtime_value(raw_run_settings)
        context = StageContext(
            workspace=workspace,
            workflow=workflow,
            run=run,
            repositories=self.repositories,
            registries=self.registries,
            logger=logger,
            data={
                "run_settings": raw_run_settings,
                "resolved_run_settings": resolved_run_settings,
                "secret_resolver": self.resolve_runtime_value,
            },
        )
        try:
            self.stage_engine.execute(context)
        except Exception:
            run = self.repositories.run_repository.get(run.id)
            if auto_retry_failed and run.status == RUN_STATUS_FAILED and run.attempt_count < run.max_attempts:
                self._trim_to_resumable_prefix(run)
                self._queue_run(run)
            return self.repositories.run_repository.get(run.id)
        try:
            self._auto_approve_generated_job_reviews(run_id=run.id, workflow=workflow)
        except Exception:
            logger.exception("Unable to auto-approve generated jobs for run %s", run.id)
        return self.repositories.run_repository.get(run.id)

    def _queue_run(self, run: RunRecord) -> RunRecord:
        now = utc_now_iso()
        run.status = RUN_STATUS_QUEUED
        run.queued_at = now
        run.current_stage_id = ""
        run.started_at = ""
        run.finished_at = ""
        run.updated_at = now
        self.repositories.run_repository.save(run)
        return self.repositories.run_repository.get(run.id)

    def _trim_to_resumable_prefix(self, run: RunRecord) -> None:
        kept_results = []
        for result in run.stage_results:
            if result.status in {"completed", "skipped"}:
                kept_results.append(result)
                continue
            break
        run.stage_results = kept_results

    def _refresh_run_job_keys(self, run_id: str) -> None:
        run = self.repositories.run_repository.get(run_id)
        run.final_job_set_keys = sorted(self.repositories.job_store.list_job_set_keys(run.id))
        run.updated_at = utc_now_iso()
        self.repositories.run_repository.save(run)
