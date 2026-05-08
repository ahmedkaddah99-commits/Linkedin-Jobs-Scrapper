from __future__ import annotations

from pathlib import Path

from backend.adapters import register_stage_adapters
from backend.application import BackendApplication
from backend.connectors.job_boards import list_portal_strategy_ids
from backend.orchestration import BackendRegistries, ComponentDescriptor, Registry, StageEngine
from backend.repositories import (
    BackendRepositories,
    FileAuthRepository,
    FileArtifactStore,
    FileJobStore,
    FileReviewStore,
    FileRunRepository,
    FileSecretStore,
    FileWorkerStore,
    FileWorkspaceRepository,
    SqliteAuthRepository,
    SqliteArtifactStore,
    SqliteJobStore,
    SqliteReviewStore,
    SqliteRunRepository,
    SqliteSecretStore,
    SqliteWorkerStore,
    SqliteWorkspaceRepository,
)


def _build_registries() -> BackendRegistries:
    stage_registry = Registry(kind="stage")
    connector_registry = Registry(kind="connector")
    generation_registry = Registry(kind="generation")
    renderer_registry = Registry(kind="renderer")

    connector_registry.register(
        "linkedin_jobs",
        ComponentDescriptor(
            id="linkedin_jobs",
            kind="connector",
            name="LinkedIn Job Search",
            description="Search-driven job discovery and enrichment using LinkedIn listings.",
        ),
    )
    connector_registry.register(
        "linkedin_search",
        ComponentDescriptor(
            id="linkedin_search",
            kind="connector",
            name="LinkedIn Job Search",
            description="Legacy alias for LinkedIn search-driven job discovery.",
            metadata={"alias_for": "linkedin_jobs"},
        ),
    )
    connector_registry.register(
        "curated_job_urls",
        ComponentDescriptor(
            id="curated_job_urls",
            kind="connector",
            name="Curated Job URLs",
            description="Manual job URL ingestion and normalization for curated opportunities.",
        ),
    )
    connector_registry.register(
        "manual_url",
        ComponentDescriptor(
            id="manual_url",
            kind="connector",
            name="Curated Job URLs",
            description="Legacy alias for curated manual job URL ingestion.",
            metadata={"alias_for": "curated_job_urls"},
        ),
    )
    connector_registry.register(
        "company_career_sites",
        ComponentDescriptor(
            id="company_career_sites",
            kind="connector",
            name="Company Career Sites",
            description="Discover jobs directly from backend-prepared company career pages, with manual overrides when needed.",
        ),
    )
    connector_registry.register(
        "academic_career_sites",
        ComponentDescriptor(
            id="academic_career_sites",
            kind="connector",
            name="Academic Career Sites",
            description="Discover academic jobs directly from backend-prepared university, department, chair, and institute pages.",
        ),
    )
    connector_registry.register(
        "job_board_collection",
        ComponentDescriptor(
            id="job_board_collection",
            kind="connector",
            name="Job Board Collection",
            description="Collect jobs across multiple job boards and portals.",
            metadata={"portal_strategy_ids": list_portal_strategy_ids()},
        ),
    )
    connector_registry.register(
        "blue_collar_portals",
        ComponentDescriptor(
            id="blue_collar_portals",
            kind="connector",
            name="Blue-Collar Portal Collection",
            description="Legacy alias for multi-board blue-collar portal collection.",
            metadata={"alias_for": "job_board_collection", "portal_strategy_ids": list_portal_strategy_ids()},
        ),
    )
    connector_registry.register(
        "job_board_indeed",
        ComponentDescriptor(
            id="job_board_indeed",
            kind="connector",
            name="Indeed Board Source",
            description="Indeed source strategy within the generic job-board collection layer.",
            metadata={"portal": "indeed", "group": "job_boards"},
        ),
    )
    connector_registry.register(
        "job_board_arbeitsagentur",
        ComponentDescriptor(
            id="job_board_arbeitsagentur",
            kind="connector",
            name="Arbeitsagentur Board Source",
            description="Bundesagentur fuer Arbeit source strategy within the generic job-board collection layer.",
            metadata={"portal": "arbeitsagentur", "group": "job_boards"},
        ),
    )
    connector_registry.register(
        "job_board_stepstone",
        ComponentDescriptor(
            id="job_board_stepstone",
            kind="connector",
            name="StepStone Board Source",
            description="StepStone source strategy within the generic job-board collection layer.",
            metadata={"portal": "stepstone", "group": "job_boards"},
        ),
    )
    connector_registry.register(
        "job_board_linkedin",
        ComponentDescriptor(
            id="job_board_linkedin",
            kind="connector",
            name="LinkedIn Board Source",
            description="LinkedIn source strategy within the generic job-board collection layer.",
            metadata={"portal": "linkedin", "group": "job_boards"},
        ),
    )

    generation_registry.register(
        "tailored_application_documents",
        ComponentDescriptor(
            id="tailored_application_documents",
            kind="generation",
            name="Tailored Application Documents",
            description="Generate tailored application documents for accepted jobs.",
        ),
    )
    generation_registry.register(
        "white_collar_cv_generation",
        ComponentDescriptor(
            id="white_collar_cv_generation",
            kind="generation",
            name="Tailored Application Documents",
            description="Legacy alias for tailored white-collar document generation.",
            metadata={"alias_for": "tailored_application_documents"},
        ),
    )
    generation_registry.register(
        "reusable_role_profiles",
        ComponentDescriptor(
            id="reusable_role_profiles",
            kind="generation",
            name="Reusable Role Profiles",
            description="Generate reusable role-based profile documents for grouped jobs.",
        ),
    )
    generation_registry.register(
        "blue_collar_role_cv_generation",
        ComponentDescriptor(
            id="blue_collar_role_cv_generation",
            kind="generation",
            name="Reusable Role Profiles",
            description="Legacy alias for blue-collar reusable role profile generation.",
            metadata={"alias_for": "reusable_role_profiles"},
        ),
    )

    renderer_registry.register(
        "application_document_export",
        ComponentDescriptor(
            id="application_document_export",
            kind="renderer",
            name="Application Document Export",
            description="Export tailored application documents to Word, PDF, and tracker outputs.",
        ),
    )
    renderer_registry.register(
        "docx_pdf_renderer",
        ComponentDescriptor(
            id="docx_pdf_renderer",
            kind="renderer",
            name="Application Document Export",
            description="Legacy alias for Word/PDF application document export.",
            metadata={"alias_for": "application_document_export"},
        ),
    )
    renderer_registry.register(
        "application_package_export",
        ComponentDescriptor(
            id="application_package_export",
            kind="renderer",
            name="Application Package Export",
            description="Export packaged application assets, reusable bundles, and email drafts.",
        ),
    )
    renderer_registry.register(
        "blue_collar_package_renderer",
        ComponentDescriptor(
            id="blue_collar_package_renderer",
            kind="renderer",
            name="Application Package Export",
            description="Legacy alias for blue-collar application package export.",
            metadata={"alias_for": "application_package_export"},
        ),
    )

    register_stage_adapters(stage_registry)
    return BackendRegistries(
        stage_registry=stage_registry,
        connector_registry=connector_registry,
        generation_registry=generation_registry,
        renderer_registry=renderer_registry,
    )


def _resolve_sqlite_path(base_path: Path) -> Path:
    if base_path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        return base_path
    return base_path / "backend.sqlite3"


def _build_repositories(base_path: Path, *, storage_backend: str) -> BackendRepositories:
    if storage_backend == "file":
        return BackendRepositories(
            workspace_repository=FileWorkspaceRepository(base_path),
            run_repository=FileRunRepository(base_path),
            job_store=FileJobStore(base_path),
            artifact_store=FileArtifactStore(base_path),
            review_store=FileReviewStore(base_path),
            auth_repository=FileAuthRepository(base_path),
            secret_store=FileSecretStore(base_path),
            worker_store=FileWorkerStore(base_path),
        )
    if storage_backend == "sqlite":
        db_path = _resolve_sqlite_path(base_path)
        return BackendRepositories(
            workspace_repository=SqliteWorkspaceRepository(db_path),
            run_repository=SqliteRunRepository(db_path),
            job_store=SqliteJobStore(db_path),
            artifact_store=SqliteArtifactStore(db_path),
            review_store=SqliteReviewStore(db_path),
            auth_repository=SqliteAuthRepository(db_path),
            secret_store=SqliteSecretStore(db_path),
            worker_store=SqliteWorkerStore(db_path),
        )
    raise ValueError(f"Unsupported storage backend: {storage_backend}")


def create_backend(
    base_dir: str | Path = ".backend_data",
    *,
    storage_backend: str = "sqlite",
) -> BackendApplication:
    base_path = Path(base_dir)
    repositories = _build_repositories(base_path, storage_backend=storage_backend)
    registries = _build_registries()
    stage_engine = StageEngine(
        stage_registry=registries.stage_registry,
        run_repository=repositories.run_repository,
        job_store=repositories.job_store,
        artifact_store=repositories.artifact_store,
    )
    return BackendApplication(
        repositories=repositories,
        registries=registries,
        stage_engine=stage_engine,
    )
