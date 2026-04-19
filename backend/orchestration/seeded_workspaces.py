from __future__ import annotations

from backend.domain.models import StageDefinition, WorkflowTemplate, WorkspaceDefinition


DEFAULT_WORKFLOW_TEMPLATES = [
    WorkflowTemplate(
        id="search_apply_v1",
        name="Search and Apply",
        description="Search-driven acquisition, screening, prioritization, and tailored document generation.",
        stages=[
            StageDefinition(
                stage_id="source_search",
                stage_type="jobs.acquire.search_listings",
                name="Acquire Search Listings",
                output_key="source_search_jobs",
                config={"connector_id": "linkedin_jobs"},
            ),
            StageDefinition(
                stage_id="screen_jobs",
                stage_type="jobs.screen.filter",
                name="Screen Jobs",
                input_keys=["source_search_jobs"],
                output_key="screened_jobs",
                config={"screening_strategy": "tailored_documents"},
            ),
            StageDefinition(
                stage_id="prioritize_jobs",
                stage_type="jobs.prioritize.rank",
                name="Prioritize Jobs",
                input_keys=["screened_jobs"],
                output_key="production_jobs",
            ),
            StageDefinition(
                stage_id="generate_documents",
                stage_type="applications.generate.documents",
                name="Generate Application Documents",
                input_keys=["production_jobs"],
                output_key="generated_jobs",
                config={
                    "generation_id": "tailored_application_documents",
                    "renderer_id": "application_document_export",
                },
            ),
        ],
        default_run_settings={"automation_flow": "tailored_documents"},
    ),
    WorkflowTemplate(
        id="curated_apply_v1",
        name="Curated Intake and Apply",
        description="Curated URL intake, dedupe, and tailored document generation.",
        stages=[
            StageDefinition(
                stage_id="source_curated_urls",
                stage_type="jobs.ingest.curated_urls",
                name="Ingest Curated Job URLs",
                output_key="source_curated_jobs",
                config={"connector_id": "curated_job_urls"},
            ),
            StageDefinition(
                stage_id="merge_jobs",
                stage_type="jobs.merge.dedupe",
                name="Merge and Deduplicate",
                input_keys=["source_curated_jobs"],
                output_key="production_jobs",
                config={"dedupe_against_tracker": True},
            ),
            StageDefinition(
                stage_id="generate_documents",
                stage_type="applications.generate.documents",
                name="Generate Application Documents",
                input_keys=["production_jobs"],
                output_key="generated_jobs",
                config={
                    "generation_id": "tailored_application_documents",
                    "renderer_id": "application_document_export",
                },
            ),
        ],
        default_run_settings={"automation_flow": "tailored_documents"},
    ),
    WorkflowTemplate(
        id="blended_sources_apply_v1",
        name="Blended Sources and Apply",
        description="Combine search-driven and curated sources, then screen, prioritize, and generate tailored documents.",
        stages=[
            StageDefinition(
                stage_id="source_search",
                stage_type="jobs.acquire.search_listings",
                name="Acquire Search Listings",
                output_key="source_search_jobs",
                config={"connector_id": "linkedin_jobs"},
            ),
            StageDefinition(
                stage_id="source_curated_urls",
                stage_type="jobs.ingest.curated_urls",
                name="Ingest Curated Job URLs",
                output_key="source_curated_jobs",
                config={"connector_id": "curated_job_urls"},
            ),
            StageDefinition(
                stage_id="merge_jobs",
                stage_type="jobs.merge.dedupe",
                name="Merge and Deduplicate",
                input_keys=["source_search_jobs", "source_curated_jobs"],
                output_key="merged_jobs",
                config={"dedupe_against_tracker": True},
            ),
            StageDefinition(
                stage_id="screen_jobs",
                stage_type="jobs.screen.filter",
                name="Screen Jobs",
                input_keys=["merged_jobs"],
                output_key="screened_jobs",
                config={"screening_strategy": "tailored_documents"},
            ),
            StageDefinition(
                stage_id="prioritize_jobs",
                stage_type="jobs.prioritize.rank",
                name="Prioritize Jobs",
                input_keys=["screened_jobs"],
                output_key="production_jobs",
            ),
            StageDefinition(
                stage_id="generate_documents",
                stage_type="applications.generate.documents",
                name="Generate Application Documents",
                input_keys=["production_jobs"],
                output_key="generated_jobs",
                config={
                    "generation_id": "tailored_application_documents",
                    "renderer_id": "application_document_export",
                },
            ),
        ],
        default_run_settings={"automation_flow": "tailored_documents"},
    ),
    WorkflowTemplate(
        id="board_package_v1",
        name="Board Collection and Package",
        description="Collect jobs from boards, screen them, classify them into roles, build reusable profiles, and export packages.",
        stages=[
            StageDefinition(
                stage_id="source_job_boards",
                stage_type="jobs.acquire.job_boards",
                name="Collect Job Boards",
                output_key="source_board_jobs",
                config={"connector_id": "job_board_collection"},
            ),
            StageDefinition(
                stage_id="screen_jobs",
                stage_type="jobs.screen.filter",
                name="Screen Jobs",
                input_keys=["source_board_jobs"],
                output_key="screened_jobs",
                config={"screening_strategy": "reusable_packages"},
            ),
            StageDefinition(
                stage_id="classify_roles",
                stage_type="jobs.classify.roles",
                name="Classify Roles",
                input_keys=["screened_jobs"],
                output_key="classified_jobs",
            ),
            StageDefinition(
                stage_id="build_reusable_profiles",
                stage_type="profiles.generate.reusable",
                name="Build Reusable Profiles",
                input_keys=["classified_jobs"],
                output_key="role_profile_index",
                config={"generation_id": "reusable_role_profiles"},
            ),
            StageDefinition(
                stage_id="package_applications",
                stage_type="applications.package.export",
                name="Package Applications",
                input_keys=["classified_jobs", "role_profile_index"],
                output_key="packaged_jobs",
                config={"renderer_id": "application_package_export"},
            ),
        ],
        default_run_settings={"automation_flow": "reusable_packages"},
    ),
]


DEFAULT_WORKSPACES: list[WorkspaceDefinition] = []
