from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.database.connection import DatabaseConfigurationError, validate_release_provenance
from backend.repositories.sqlite_migrations import current_migration_head
from backend.deployment.release_contract import (
    RELEASE_CONTRACT_VERSION,
    ReleaseMetadata,
    affected_services,
    are_release_contracts_compatible,
)


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_only_changes_do_not_restart_api_or_workers() -> None:
    assert affected_services(["frontend/src/pages/TrackerPage.jsx"]) == {"frontend"}
    assert affected_services(["frontend/src/lib/api.js"]) == {"frontend"}
    assert affected_services(["frontend/src/lib/cvStudio.js"]) == {"frontend", "api", "worker"}


def test_shared_backend_and_worker_paths_have_explicit_impact() -> None:
    assert affected_services(["backend/api/server.py"]) == {"api", "worker"}
    assert affected_services(["scripts/master_linkedin_jobs_catalog.py"]) == {"worker"}
    assert affected_services(["docs/RC022_BUILD_RELEASE_STAGING.md"]) == set()
    assert affected_services(["Dockerfile"]) == set()
    assert affected_services(["render.yaml"]) == {"frontend", "api", "worker"}


def test_release_metadata_uses_render_commit_without_claiming_unknown_values(monkeypatch) -> None:
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")
    monkeypatch.setenv("RENDER_GIT_BRANCH", "deployment/render-turso-r2")
    monkeypatch.setenv("RUNR_RELEASE_COMMIT", "unknown")
    metadata = ReleaseMetadata.from_environment(service="worker", worker_role="acquisition")

    assert metadata.service == "worker"
    assert metadata.worker_role == "acquisition"
    assert metadata.commit == "abc123"
    assert metadata.branch == "deployment/render-turso-r2"
    assert metadata.contract_version == RELEASE_CONTRACT_VERSION
    assert json.loads(metadata.to_json())["schema_version"] == "runr.release.v1"


def test_previous_and_current_images_share_the_declared_contract() -> None:
    assert are_release_contracts_compatible("runr-contract-v1", "runr-contract-v1")
    assert not are_release_contracts_compatible("runr-contract-v0", "runr-contract-v1")


def test_runtime_dockerfiles_are_separate_and_do_not_build_static_frontend() -> None:
    legacy = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    api = (ROOT / "Dockerfile.api").read_text(encoding="utf-8")
    worker = (ROOT / "Dockerfile.worker").read_text(encoding="utf-8")

    assert "npm --prefix frontend run build" not in legacy
    for dockerfile in (api, worker):
        assert "USER runr" in dockerfile
        assert "npm run build" not in dockerfile
        assert "playwright install --with-deps chromium" in dockerfile
        assert "tesseract-ocr" in dockerfile
        assert "libreoffice-writer" in dockerfile

    assert 'RUNR_IMAGE_SERVICE=api' in api
    assert 'RUNR_IMAGE_SERVICE=worker' in worker


def test_render_and_ci_select_distinct_api_and_worker_images() -> None:
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "dockerfilePath: ./Dockerfile.api" in render
    assert "dockerfilePath: ./Dockerfile.worker" in render
    assert "buildFilter:" in render
    assert "Dockerfile.api" in ci
    assert "Dockerfile.worker" in ci


def test_render_declares_the_code_derived_migration_head_for_api_and_worker() -> None:
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    expected_head = current_migration_head()

    assert render.count(f"value: {expected_head}") == 2
    assert "value: 058_customer_task_queue" not in render


def test_startup_entrypoint_validates_release_provenance_before_emitting_metadata() -> None:
    start = (ROOT / "deploy" / "start.sh").read_text(encoding="utf-8")

    assert "validate_release_provenance" in start
    assert "backend.database.connection" in start
    assert "export RUNR_MIGRATION_HEAD=" in start


def test_release_provenance_validator_rejects_an_incompatible_migration_head() -> None:
    with pytest.raises(DatabaseConfigurationError, match="migration head"):
        validate_release_provenance(configured_migration_head="058_customer_task_queue")


def test_release_provenance_validator_rejects_conflicting_known_revisions() -> None:
    with pytest.raises(DatabaseConfigurationError, match="commit"):
        validate_release_provenance(release_commit="abc123", runtime_commit="def456")


def test_release_provenance_validator_ignores_placeholder_revisions() -> None:
    expected_head = current_migration_head()

    assert (
        validate_release_provenance(
            release_branch="unknown",
            runtime_branch="deployment/render-turso-r2",
            release_commit="unset",
            runtime_commit="abc123",
            configured_migration_head=expected_head,
        )
        == expected_head
    )
