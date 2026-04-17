from __future__ import annotations

from pathlib import Path

from backend.adapters import register_legacy_stage_adapters
from backend.application import BackendApplication
from backend.connectors.blue_collar import list_portal_strategy_ids
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
        "linkedin_search",
        ComponentDescriptor(
            id="linkedin_search",
            kind="connector",
            name="LinkedIn Search Connector",
            description="LinkedIn guest job discovery and enrichment pipeline.",
        ),
    )
    connector_registry.register(
        "manual_url",
        ComponentDescriptor(
            id="manual_url",
            kind="connector",
            name="Manual URL Connector",
            description="Manual job URL ingestion and normalization.",
        ),
    )
    connector_registry.register(
        "blue_collar_portals",
        ComponentDescriptor(
            id="blue_collar_portals",
            kind="connector",
            name="Blue-Collar Multi-Portal Connector",
            description="Blue-collar portal collection across Indeed, LinkedIn, Arbeitsagentur, and StepStone.",
            metadata={"portal_strategy_ids": list_portal_strategy_ids()},
        ),
    )
    connector_registry.register(
        "blue_collar_indeed",
        ComponentDescriptor(
            id="blue_collar_indeed",
            kind="connector",
            name="Indeed Connector",
            description="Blue-collar Indeed Germany source strategy.",
            metadata={"portal": "indeed", "group": "blue_collar"},
        ),
    )
    connector_registry.register(
        "blue_collar_arbeitsagentur",
        ComponentDescriptor(
            id="blue_collar_arbeitsagentur",
            kind="connector",
            name="Arbeitsagentur Connector",
            description="Blue-collar Bundesagentur fuer Arbeit source strategy.",
            metadata={"portal": "arbeitsagentur", "group": "blue_collar"},
        ),
    )
    connector_registry.register(
        "blue_collar_stepstone",
        ComponentDescriptor(
            id="blue_collar_stepstone",
            kind="connector",
            name="StepStone Connector",
            description="Blue-collar StepStone Germany source strategy.",
            metadata={"portal": "stepstone", "group": "blue_collar"},
        ),
    )
    connector_registry.register(
        "blue_collar_linkedin",
        ComponentDescriptor(
            id="blue_collar_linkedin",
            kind="connector",
            name="LinkedIn Connector",
            description="Blue-collar LinkedIn guest jobs source strategy.",
            metadata={"portal": "linkedin", "group": "blue_collar"},
        ),
    )

    generation_registry.register(
        "white_collar_cv_generation",
        ComponentDescriptor(
            id="white_collar_cv_generation",
            kind="generation",
            name="White-Collar CV Generation",
            description="AI-tailored CV generation for white-collar jobs.",
        ),
    )
    generation_registry.register(
        "blue_collar_role_cv_generation",
        ComponentDescriptor(
            id="blue_collar_role_cv_generation",
            kind="generation",
            name="Blue-Collar Role CV Builder",
            description="Reusable role-based CV generation for blue-collar categories.",
        ),
    )

    renderer_registry.register(
        "docx_pdf_renderer",
        ComponentDescriptor(
            id="docx_pdf_renderer",
            kind="renderer",
            name="DOCX/PDF Renderer",
            description="Exports tailored CVs to Word and PDF plus tracker files.",
        ),
    )
    renderer_registry.register(
        "blue_collar_package_renderer",
        ComponentDescriptor(
            id="blue_collar_package_renderer",
            kind="renderer",
            name="Blue-Collar Package Renderer",
            description="Copies assigned CVs, writes email drafts, and exports packaging artifacts.",
        ),
    )

    register_legacy_stage_adapters(stage_registry)
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
