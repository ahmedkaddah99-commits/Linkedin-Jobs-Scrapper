from __future__ import annotations

import os
from pathlib import Path

from backend.adapters import register_stage_adapters
from backend.application import BackendApplication
from backend.connectors.job_boards import list_portal_strategy_ids
from backend.database import database_target_info, initialize_database
from backend.orchestration import BackendRegistries, ComponentDescriptor, Registry, StageEngine
from backend.repositories import (
    BackendRepositories,
    SqliteAcquisitionStore,
    SqlitePersonalizedJobsStore,
    FileAnalyticsStore,
    FileAuthRepository,
    FileCareerProfileStore,

    FileArtifactStore,
    FileConfigStore,
    FileJobStore,
    FileReviewStore,
    FileRunRepository,
    FileSecretStore,
    FileWorkerStore,
    FileWorkspaceRepository,
    SqliteAnalyticsStore,
    SqliteCareerProfileStore,

    SqliteEvidenceStore,

    SqliteAuthRepository,
    SqliteArtifactStore,
    SqliteConfigStore,
    SqliteJobStore,
    SqliteReviewStore,
    SqliteRunRepository,
    SqliteSecretStore,
    SqliteSourcePolicyStore,
    SqliteWorkerStore,
    SqliteWorkspaceRepository,
)
from backend.storage import create_object_storage, publish_file_artifacts


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
            analytics_store=FileAnalyticsStore(base_path),
            config_store=FileConfigStore(base_path),
            career_profile_store=FileCareerProfileStore(base_path),
            evidence_store=None,
            acquisition_store=None,
            personalized_jobs_store=None,


        )
    if storage_backend == "sqlite":
        db_path = _resolve_sqlite_path(base_path)
        initialize_database(db_path)
        return BackendRepositories(
            workspace_repository=SqliteWorkspaceRepository(db_path),
            run_repository=SqliteRunRepository(db_path),
            job_store=SqliteJobStore(db_path),
            artifact_store=SqliteArtifactStore(db_path),
            review_store=SqliteReviewStore(db_path),
            auth_repository=SqliteAuthRepository(db_path),
            secret_store=SqliteSecretStore(db_path),
            worker_store=SqliteWorkerStore(db_path),
            analytics_store=SqliteAnalyticsStore(db_path),
            config_store=SqliteConfigStore(db_path),
            source_policy_store=SqliteSourcePolicyStore(db_path),
            career_profile_store=SqliteCareerProfileStore(db_path),
            evidence_store=SqliteEvidenceStore(db_path),
            acquisition_store=SqliteAcquisitionStore(db_path),
            personalized_jobs_store=SqlitePersonalizedJobsStore(db_path),


        )

    raise ValueError(f"Unsupported storage backend: {storage_backend}")


def create_backend(
    base_dir: str | Path = ".backend_data",
    *,
    storage_backend: str = "sqlite",
    test_mode: bool = False,
) -> BackendApplication:
    base_path = Path(base_dir)
    if test_mode or _is_test_context():
        _assert_test_database_boundary(base_path, storage_backend=storage_backend)
    repositories = _build_repositories(base_path, storage_backend=storage_backend)
    storage_environment = dict(os.environ)
    object_storage_backend = str(storage_environment.get("OBJECT_STORAGE_BACKEND") or "local").strip().lower()
    if object_storage_backend == "local":
        local_root_was_managed = str(os.environ.get("RUNR_INTERNAL_OBJECT_STORAGE_LOCAL_ROOT") or "") == "1"
        if local_root_was_managed or not str(storage_environment.get("OBJECT_STORAGE_LOCAL_ROOT") or "").strip():
            storage_environment["OBJECT_STORAGE_LOCAL_ROOT"] = str(base_path / "objects")
            os.environ["RUNR_INTERNAL_OBJECT_STORAGE_LOCAL_ROOT"] = "1"
        os.environ["OBJECT_STORAGE_BACKEND"] = "local"
        os.environ["OBJECT_STORAGE_LOCAL_ROOT"] = str(storage_environment["OBJECT_STORAGE_LOCAL_ROOT"])
    object_storage = create_object_storage(storage_environment)
    registries = _build_registries()
    stage_engine = StageEngine(
        stage_registry=registries.stage_registry,
        run_repository=repositories.run_repository,
        job_store=repositories.job_store,
        artifact_store=repositories.artifact_store,
        event_emitter=None,
        artifact_publisher=lambda run_id, artifacts: publish_file_artifacts(
            object_storage,
            run_id=run_id,
            artifacts=artifacts,
        ),
    )
    application = BackendApplication(
        repositories=repositories,
        registries=registries,
        stage_engine=stage_engine,
        object_storage=object_storage,
    )
    stage_engine.event_emitter = application.emit_event
    return application


def _assert_test_database_boundary(base_path: Path, *, storage_backend: str) -> None:
    """Fail before repository construction if a test could reach production storage."""

    test_signals = {
        str(os.environ.get("RUNR_TEST_MODE") or "").strip().casefold() in {"1", "true", "yes", "on"},
        str(os.environ.get("RUNR_ENV") or "").strip().casefold() in {"test", "testing"},
        bool(str(os.environ.get("PYTEST_CURRENT_TEST") or "").strip()),
    }
    if not any(test_signals):
        raise RuntimeError("Test bootstrap requires RUNR_TEST_MODE=1 or RUNR_ENV=test.")
    info = database_target_info(_resolve_sqlite_path(base_path))
    if bool(info.get("remote_required")) or bool(info.get("remote_configured")):
        raise RuntimeError("Test bootstrap rejected remote/production database configuration.")
    if str(os.environ.get("DATABASE_BACKEND") or "sqlite").strip().casefold() == "turso":
        raise RuntimeError("Test bootstrap rejected DATABASE_BACKEND=turso.")
    if str(os.environ.get("RUNR_ENV") or "").strip().casefold() in {"prod", "production"}:
        raise RuntimeError("Test bootstrap rejected production runtime configuration.")
    if str(os.environ.get("RUNR_ACQUISITION_LIVE_NETWORK_ENABLED") or "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise RuntimeError("Test bootstrap rejected live acquisition network authorization.")
    if storage_backend == "sqlite" and base_path.resolve() == Path(".backend_data").resolve():
        raise RuntimeError("Test bootstrap requires an explicit isolated SQLite path.")


def _is_test_context() -> bool:
    return (
        str(os.environ.get("RUNR_TEST_MODE") or "").strip().casefold() in {"1", "true", "yes", "on"}
        or str(os.environ.get("RUNR_ENV") or "").strip().casefold() in {"test", "testing"}
        or bool(str(os.environ.get("PYTEST_CURRENT_TEST") or "").strip())
    )
