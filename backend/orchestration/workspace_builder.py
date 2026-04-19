from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from backend.domain.models import JobSource, ProfileRef, PromptSetRef, StageDefinition, WorkflowTemplate, WorkspaceDefinition


FLOW_TAILORED_DOCUMENTS = "tailored_documents"
FLOW_REUSABLE_PACKAGES = "reusable_packages"

SOURCE_LINKEDIN_SEARCH = "linkedin_jobs"
SOURCE_CURATED_URLS = "curated_job_urls"
SOURCE_MULTI_PORTAL = "job_board_collection"

MODULE_SCREENING = "screening_filter"
MODULE_PRIORITY = "priority_ranking"
MODULE_ROLE_CLASSIFICATION = "role_classification"
MODULE_REUSABLE_PROFILES = "reusable_profile_builder"
MODULE_TAILORED_DOCUMENTS = "tailored_document_generation"
MODULE_APPLICATION_PACKAGING = "application_packaging"


@dataclass(frozen=True, slots=True)
class BuilderCatalog:
    flows: list[dict]
    sources: list[dict]
    modules: list[dict]
    configuration_fields: list[dict]
    starter_profiles: list[dict]
    starter_prompt_families: list[dict]

    def to_dict(self) -> dict:
        return {
            "flows": list(self.flows),
            "sources": list(self.sources),
            "modules": list(self.modules),
            "configuration_fields": list(self.configuration_fields),
            "starter_profiles": list(self.starter_profiles),
            "starter_prompt_families": list(self.starter_prompt_families),
        }


def _configuration_fields() -> list[dict]:
    return [
        {
            "id": "keywords",
            "label": "Target Keywords",
            "description": "Keywords the system should search for when discovering jobs.",
            "type": "tag_list",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS, FLOW_REUSABLE_PACKAGES],
            "source_ids": [SOURCE_LINKEDIN_SEARCH, SOURCE_MULTI_PORTAL],
            "placeholder": "analyst, consultant, product manager",
        },
        {
            "id": "geo_id",
            "label": "LinkedIn Geo ID",
            "description": "LinkedIn geographic target used for listing discovery.",
            "type": "text",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_LINKEDIN_SEARCH],
            "placeholder": "101282230",
        },
        {
            "id": "time_posted_seconds",
            "label": "Posting Age Window",
            "description": "How recent a listing must be before it is included.",
            "type": "select",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_LINKEDIN_SEARCH],
            "options": [
                {"value": 86400, "label": "Last 24 hours"},
                {"value": 172800, "label": "Last 2 days"},
                {"value": 604800, "label": "Last 7 days"},
                {"value": 1209600, "label": "Last 14 days"},
                {"value": 2592000, "label": "Last 30 days"},
            ],
        },
        {
            "id": "experience_levels",
            "label": "Experience Levels",
            "description": "LinkedIn experience buckets to include in the search.",
            "type": "multi_select",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_LINKEDIN_SEARCH],
            "options": [
                {"value": 1, "label": "Internship"},
                {"value": 2, "label": "Entry Level"},
                {"value": 3, "label": "Associate"},
                {"value": 4, "label": "Mid-Senior"},
            ],
        },
        {
            "id": "low_applicant_threshold",
            "label": "Priority Applicant Threshold",
            "description": "Listings below this applicant count get boosted during prioritization.",
            "type": "number",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_LINKEDIN_SEARCH, SOURCE_CURATED_URLS],
            "placeholder": "80",
        },
        {
            "id": "stage4_max_jobs",
            "label": "Max Jobs To Generate",
            "description": "Optional cap on how many jobs should reach document generation in one run.",
            "type": "number",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_LINKEDIN_SEARCH, SOURCE_CURATED_URLS],
            "placeholder": "25",
        },
        {
            "id": "cities",
            "label": "Target Cities",
            "description": "Cities used to collect jobs from job boards and portal searches.",
            "type": "tag_list",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "source_ids": [SOURCE_MULTI_PORTAL],
            "placeholder": "Berlin, Hamburg, Munich",
        },
        {
            "id": "portals",
            "label": "Job Boards",
            "description": "Job boards or portals that should be queried for this workspace.",
            "type": "multi_select",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "source_ids": [SOURCE_MULTI_PORTAL],
            "options": [
                {"value": "indeed", "label": "Indeed"},
                {"value": "stepstone", "label": "StepStone"},
                {"value": "arbeitsagentur", "label": "Arbeitsagentur"},
                {"value": "linkedin", "label": "LinkedIn"},
            ],
        },
        {
            "id": "max_pages",
            "label": "Pages Per Source",
            "description": "Maximum pages each job-board connector should scan.",
            "type": "number",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "source_ids": [SOURCE_MULTI_PORTAL],
            "placeholder": "2",
        },
        {
            "id": "radius_km",
            "label": "Search Radius (km)",
            "description": "Distance around each target city when collecting reusable package jobs.",
            "type": "number",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "source_ids": [SOURCE_MULTI_PORTAL],
            "placeholder": "35",
        },
        {
            "id": "posted_within_days",
            "label": "Posted Within Days",
            "description": "Age limit for job-board results.",
            "type": "number",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "source_ids": [SOURCE_MULTI_PORTAL],
            "placeholder": "14",
        },
        {
            "id": "max_jobs_total",
            "label": "Max Jobs Collected",
            "description": "Hard cap on how many collected jobs the workflow should retain.",
            "type": "number",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "source_ids": [SOURCE_MULTI_PORTAL],
            "placeholder": "1200",
        },
    ]


def workspace_builder_catalog() -> BuilderCatalog:
    return BuilderCatalog(
        flows=[
            {
                "id": FLOW_TAILORED_DOCUMENTS,
                "name": "Tailored Application Documents",
                "description": "Build a workflow that searches or ingests jobs, screens them, and generates tailored application documents.",
            },
            {
                "id": FLOW_REUSABLE_PACKAGES,
                "name": "Reusable Application Packages",
                "description": "Build a workflow that collects jobs, groups them into reusable role buckets, and exports packaged application assets.",
            },
        ],
        sources=[
            {
                "id": SOURCE_LINKEDIN_SEARCH,
                "connector_id": "linkedin_jobs",
                "name": "LinkedIn Job Search",
                "description": "Discover jobs from LinkedIn listings and enrich them for downstream processing.",
                "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            },
            {
                "id": SOURCE_CURATED_URLS,
                "connector_id": "curated_job_urls",
                "name": "Curated Job URLs",
                "description": "Ingest job URLs supplied manually by the user and normalize them into the shared job schema.",
                "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            },
            {
                "id": SOURCE_MULTI_PORTAL,
                "connector_id": "job_board_collection",
                "name": "Job Board Collection",
                "description": "Collect jobs from multiple job boards and portals through the shared board connector layer.",
                "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            },
        ],
        modules=[
            {
                "id": MODULE_SCREENING,
                "name": "Screening Filter",
                "description": "Apply a first-pass fit filter before deeper processing.",
                "compatible_flows": [FLOW_TAILORED_DOCUMENTS, FLOW_REUSABLE_PACKAGES],
                "default_enabled": True,
            },
            {
                "id": MODULE_PRIORITY,
                "name": "Priority Ranking",
                "description": "Rank jobs and keep the strongest matches before document generation.",
                "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
                "default_enabled": True,
            },
            {
                "id": MODULE_ROLE_CLASSIFICATION,
                "name": "Role Classification",
                "description": "Assign jobs into reusable role groups for profile packaging.",
                "compatible_flows": [FLOW_REUSABLE_PACKAGES],
                "default_enabled": True,
            },
            {
                "id": MODULE_REUSABLE_PROFILES,
                "name": "Reusable Profile Builder",
                "description": "Generate reusable role-based profile documents from the classified jobs.",
                "compatible_flows": [FLOW_REUSABLE_PACKAGES],
                "default_enabled": True,
            },
            {
                "id": MODULE_TAILORED_DOCUMENTS,
                "name": "Tailored Document Generation",
                "description": "Generate tailored application documents and tracker exports for each accepted job.",
                "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
                "default_enabled": True,
            },
            {
                "id": MODULE_APPLICATION_PACKAGING,
                "name": "Application Packaging",
                "description": "Export application bundles, email drafts, and reusable package artifacts.",
                "compatible_flows": [FLOW_REUSABLE_PACKAGES],
                "default_enabled": True,
            },
        ],
        configuration_fields=_configuration_fields(),
        starter_profiles=[
            {"id": "job_seeker_primary", "label": "Primary Job Seeker Profile"},
            {"id": "operations_profile", "label": "Operations-Focused Profile"},
        ],
        starter_prompt_families=[
            {"id": FLOW_TAILORED_DOCUMENTS, "label": "Tailored Documents"},
            {"id": FLOW_REUSABLE_PACKAGES, "label": "Reusable Packages"},
        ],
    )


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or f"workspace_{uuid4().hex[:8]}"


def _validate_flow_sources(flow_id: str, source_ids: list[str]) -> None:
    catalog = workspace_builder_catalog().to_dict()
    compatible_sources = {
        item["id"]
        for item in catalog["sources"]
        if flow_id in item["compatible_flows"]
    }
    invalid_sources = [source_id for source_id in source_ids if source_id not in compatible_sources]
    if invalid_sources:
        raise ValueError(
            f"Sources {invalid_sources} are not compatible with flow '{flow_id}'.",
        )


def _validate_modules(flow_id: str, module_ids: list[str]) -> None:
    catalog = workspace_builder_catalog().to_dict()
    compatible_modules = {
        item["id"]
        for item in catalog["modules"]
        if flow_id in item["compatible_flows"]
    }
    invalid_modules = [module_id for module_id in module_ids if module_id not in compatible_modules]
    if invalid_modules:
        raise ValueError(
            f"Modules {invalid_modules} are not compatible with flow '{flow_id}'.",
        )


def _default_modules_for_flow(flow_id: str) -> list[str]:
    catalog = workspace_builder_catalog().to_dict()
    return [
        item["id"]
        for item in catalog["modules"]
        if flow_id in item["compatible_flows"] and bool(item.get("default_enabled"))
    ]


def _normalize_tag_list(raw_value: Any) -> list[str]:
    if isinstance(raw_value, str):
        values = raw_value.split(",")
    elif isinstance(raw_value, (list, tuple, set)):
        values = list(raw_value)
    else:
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def _normalize_multi_select(raw_value: Any) -> list[Any]:
    if isinstance(raw_value, str):
        values = [item.strip() for item in raw_value.split(",") if item.strip()]
    elif isinstance(raw_value, (list, tuple, set)):
        values = [item for item in raw_value if str(item).strip()]
    else:
        return []
    normalized: list[Any] = []
    for item in values:
        text = str(item).strip()
        if not text:
            continue
        if text.isdigit():
            normalized.append(int(text))
        else:
            normalized.append(text)
    return normalized


def _normalize_setting_value(field_definition: dict, raw_value: Any) -> Any:
    field_type = str(field_definition.get("type") or "").strip()
    if field_type == "tag_list":
        return _normalize_tag_list(raw_value)
    if field_type == "multi_select":
        return _normalize_multi_select(raw_value)
    if field_type == "number":
        text = str(raw_value or "").strip()
        if not text:
            return None
        return int(float(text))
    if field_type == "select":
        text = str(raw_value or "").strip()
        if not text:
            return None
        return int(text) if text.isdigit() else text
    text = str(raw_value or "").strip()
    return text or None


def _build_workspace_settings(flow_id: str, source_ids: list[str], payload_settings: dict[str, Any]) -> dict[str, Any]:
    field_map = {field["id"]: field for field in _configuration_fields()}
    selected_source_ids = set(source_ids)
    settings: dict[str, Any] = {}
    for key, raw_value in dict(payload_settings or {}).items():
        field = field_map.get(str(key))
        if field is None:
            continue
        compatible_flows = set(field.get("compatible_flows") or [])
        if compatible_flows and flow_id not in compatible_flows:
            continue
        field_source_ids = set(field.get("source_ids") or [])
        if field_source_ids and not field_source_ids.intersection(selected_source_ids):
            continue
        normalized = _normalize_setting_value(field, raw_value)
        if normalized in (None, "", [], {}):
            continue
        settings[str(key)] = normalized
    return settings


def _default_prompt_family(flow_id: str) -> str:
    return flow_id


def _default_profile_label(flow_id: str) -> str:
    if flow_id == FLOW_REUSABLE_PACKAGES:
        return "Operations Profile"
    return "Primary Job Seeker Profile"


def _build_source_stages(source_ids: list[str]) -> tuple[list[StageDefinition], list[str], list[JobSource]]:
    stages: list[StageDefinition] = []
    output_keys: list[str] = []
    sources: list[JobSource] = []

    if SOURCE_LINKEDIN_SEARCH in source_ids:
        stages.append(
            StageDefinition(
                stage_id="source_linkedin_search",
                stage_type="jobs.acquire.search_listings",
                name="Acquire Search Listings",
                description="Acquire and enrich jobs from the LinkedIn search connector.",
                output_key="source_linkedin_jobs",
                config={"connector_id": "linkedin_jobs"},
            )
        )
        output_keys.append("source_linkedin_jobs")
        sources.append(JobSource(id="source_linkedin_search", connector_id="linkedin_jobs"))

    if SOURCE_CURATED_URLS in source_ids:
        stages.append(
            StageDefinition(
                stage_id="source_curated_urls",
                stage_type="jobs.ingest.curated_urls",
                name="Ingest Curated Job URLs",
                description="Load manually selected job URLs into the shared job schema.",
                output_key="source_curated_jobs",
                config={"connector_id": "curated_job_urls"},
            )
        )
        output_keys.append("source_curated_jobs")
        sources.append(JobSource(id="source_curated_urls", connector_id="curated_job_urls"))

    if SOURCE_MULTI_PORTAL in source_ids:
        stages.append(
            StageDefinition(
                stage_id="source_job_boards",
                stage_type="jobs.acquire.job_boards",
                name="Collect Job Boards",
                description="Collect jobs from the shared job-board connector layer.",
                output_key="source_board_jobs",
                config={"connector_id": "job_board_collection"},
            )
        )
        output_keys.append("source_board_jobs")
        sources.append(JobSource(id="source_job_boards", connector_id="job_board_collection"))

    return stages, output_keys, sources


def _build_tailored_stages(source_output_key: str, module_ids: list[str]) -> list[StageDefinition]:
    stages: list[StageDefinition] = []
    current_key = source_output_key

    if MODULE_SCREENING in module_ids:
        stages.append(
            StageDefinition(
                stage_id="screen_jobs",
                stage_type="jobs.screen.filter",
                name="Screen Jobs",
                description="Apply the shared screening filter to the sourced jobs.",
                input_keys=[current_key],
                output_key="screened_jobs",
                config={"screening_strategy": FLOW_TAILORED_DOCUMENTS},
            )
        )
        current_key = "screened_jobs"

    if MODULE_PRIORITY in module_ids:
        stages.append(
            StageDefinition(
                stage_id="prioritize_jobs",
                stage_type="jobs.prioritize.rank",
                name="Prioritize Jobs",
                description="Rank jobs and keep the best matches for production output.",
                input_keys=[current_key],
                output_key="production_jobs",
            )
        )
        current_key = "production_jobs"

    if MODULE_TAILORED_DOCUMENTS in module_ids:
        stages.append(
            StageDefinition(
                stage_id="generate_application_documents",
                stage_type="applications.generate.documents",
                name="Generate Application Documents",
                description="Create tailored application files and export tracking records.",
                input_keys=[current_key],
                output_key="generated_jobs",
                config={
                    "generation_id": "tailored_application_documents",
                    "renderer_id": "application_document_export",
                },
            )
        )

    return stages


def _build_reusable_package_stages(source_output_key: str, module_ids: list[str]) -> list[StageDefinition]:
    stages: list[StageDefinition] = []
    current_key = source_output_key

    if MODULE_SCREENING in module_ids:
        stages.append(
            StageDefinition(
                stage_id="screen_jobs",
                stage_type="jobs.screen.filter",
                name="Screen Jobs",
                description="Apply the shared screening filter to the sourced jobs.",
                input_keys=[current_key],
                output_key="screened_jobs",
                config={"screening_strategy": FLOW_REUSABLE_PACKAGES},
            )
        )
        current_key = "screened_jobs"

    if MODULE_ROLE_CLASSIFICATION in module_ids:
        stages.append(
            StageDefinition(
                stage_id="classify_roles",
                stage_type="jobs.classify.roles",
                name="Classify Roles",
                description="Assign jobs to reusable role groups.",
                input_keys=[current_key],
                output_key="classified_jobs",
            )
        )
        current_key = "classified_jobs"

    if MODULE_REUSABLE_PROFILES in module_ids:
        stages.append(
            StageDefinition(
                stage_id="build_reusable_profiles",
                stage_type="profiles.generate.reusable",
                name="Build Reusable Profiles",
                description="Build reusable role-based profile documents.",
                input_keys=[current_key],
                output_key="role_profile_index",
                config={"generation_id": "reusable_role_profiles"},
            )
        )

    if MODULE_APPLICATION_PACKAGING in module_ids:
        stages.append(
            StageDefinition(
                stage_id="package_applications",
                stage_type="applications.package.export",
                name="Package Applications",
                description="Create packaged application assets for the generated role profiles.",
                input_keys=[current_key, "role_profile_index"],
                output_key="packaged_jobs",
                config={"renderer_id": "application_package_export"},
            )
        )

    return stages


def build_workspace_from_scratch(payload: dict) -> tuple[WorkflowTemplate, WorkspaceDefinition]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("workspace name is required")

    flow_id = str(payload.get("flow_id") or FLOW_TAILORED_DOCUMENTS).strip()
    if flow_id not in {FLOW_TAILORED_DOCUMENTS, FLOW_REUSABLE_PACKAGES}:
        raise ValueError(f"Unsupported flow_id: {flow_id}")

    source_ids = [str(item).strip() for item in payload.get("source_ids") or [] if str(item).strip()]
    if not source_ids:
        raise ValueError("At least one source is required.")
    _validate_flow_sources(flow_id, source_ids)

    module_ids = [str(item).strip() for item in payload.get("module_ids") or [] if str(item).strip()]
    if not module_ids:
        module_ids = _default_modules_for_flow(flow_id)
    _validate_modules(flow_id, module_ids)

    if flow_id == FLOW_REUSABLE_PACKAGES and MODULE_APPLICATION_PACKAGING in module_ids and MODULE_REUSABLE_PROFILES not in module_ids:
        raise ValueError("Application packaging requires the reusable profile builder module.")
    if flow_id == FLOW_REUSABLE_PACKAGES and MODULE_REUSABLE_PROFILES in module_ids and MODULE_ROLE_CLASSIFICATION not in module_ids:
        raise ValueError("Reusable profile builder requires the role classification module.")

    workspace_slug = str(payload.get("workspace_id") or "").strip() or _slugify(name)
    template_id = str(payload.get("workflow_template_id") or "").strip() or f"{workspace_slug}_workflow"
    description = str(payload.get("description") or "").strip()
    prompt_family = str(payload.get("prompt_family") or _default_prompt_family(flow_id)).strip()
    profile_label = str(payload.get("profile_label") or _default_profile_label(flow_id)).strip()
    prompt_set_id = f"{workspace_slug}_prompt"
    profile_id = f"{workspace_slug}_profile"
    workspace_settings = _build_workspace_settings(
        flow_id,
        source_ids,
        dict(payload.get("settings") or {}),
    )

    source_stages, source_output_keys, sources = _build_source_stages(source_ids)
    if len(source_output_keys) > 1:
        source_stages.append(
            StageDefinition(
                stage_id="merge_source_jobs",
                stage_type="jobs.merge.dedupe",
                name="Merge Source Jobs",
                description="Combine jobs from all enabled sources and remove duplicates.",
                input_keys=source_output_keys,
                output_key="merged_source_jobs",
                config={"dedupe_against_tracker": True},
            )
        )
        source_output_key = "merged_source_jobs"
    else:
        source_output_key = source_output_keys[0]

    if flow_id == FLOW_REUSABLE_PACKAGES:
        flow_stages = _build_reusable_package_stages(source_output_key, module_ids)
        settings = {
            "config_loader": "reusable_packages",
            "automation_flow": FLOW_REUSABLE_PACKAGES,
        }
    else:
        flow_stages = _build_tailored_stages(source_output_key, module_ids)
        settings = {
            "config_loader": "tailored_documents",
            "automation_flow": FLOW_TAILORED_DOCUMENTS,
            "manual_sources_are_preapproved": bool(payload.get("manual_sources_are_preapproved", True)),
        }

    workflow_template = WorkflowTemplate(
        id=template_id,
        name=f"{name} Workflow",
        description=description or f"Custom workflow for {name}.",
        stages=[*source_stages, *flow_stages],
        default_run_settings={
            "builder_mode": "scratch",
            "automation_flow": flow_id,
        },
    )

    feature_flags = {
        "screening_filter": MODULE_SCREENING in module_ids,
        "priority_ranking": MODULE_PRIORITY in module_ids,
        "role_classification": MODULE_ROLE_CLASSIFICATION in module_ids,
        "reusable_profile_builder": MODULE_REUSABLE_PROFILES in module_ids,
        "tailored_document_generation": MODULE_TAILORED_DOCUMENTS in module_ids,
        "application_packaging": MODULE_APPLICATION_PACKAGING in module_ids,
    }

    workspace = WorkspaceDefinition(
        id=workspace_slug,
        name=name,
        workflow_template_id=workflow_template.id,
        description=description,
        workspace_type="custom",
        settings={**settings, **workspace_settings},
        feature_flags=feature_flags,
        profiles=[
            ProfileRef(
                id=profile_id,
                label=profile_label,
                settings={"automation_flow": flow_id},
            )
        ],
        prompt_sets=[
            PromptSetRef(
                id=prompt_set_id,
                family=prompt_family,
                settings={"automation_flow": flow_id},
            )
        ],
        sources=sources,
        metadata={
            "builder_mode": "scratch",
            "automation_flow": flow_id,
            "modules": list(module_ids),
            "source_ids": list(source_ids),
        },
    )
    return workflow_template, workspace
