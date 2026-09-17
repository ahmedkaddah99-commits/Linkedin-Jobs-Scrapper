from pathlib import Path

import pytest

from runr_automation.scope_router import (
    ScopeError,
    build_scope_manifest,
    load_registry,
    resolve_primary_subsystem,
)


@pytest.fixture
def registry_file(tmp_path: Path) -> Path:
    path = tmp_path / "subsystems.yaml"
    path.write_text(
        """
subsystems:
  - id: http-api-cli
    workstream: WS-1
    linear_project: WS-01 HTTP API and CLI
    owned_paths:
      - backend/api/**
    documentation:
      - docs/api.md
  - id: workers-orchestration
    workstream: WS-2
    linear_project: WS-02 Workers and Orchestration
    owned_paths:
      - backend/worker/**
    documentation:
      - docs/workers.md
""",
        encoding="utf-8",
    )
    return path


def test_primary_subsystem_requires_exactly_one_grouped_label(registry_file: Path) -> None:
    registry = load_registry(registry_file)

    assert resolve_primary_subsystem(
        [{"group": "Subsystem", "name": "WS-01 HTTP API and CLI"}], registry
    ) == "http-api-cli"
    with pytest.raises(ScopeError, match="exactly one"):
        resolve_primary_subsystem([], registry)
    with pytest.raises(ScopeError, match="exactly one"):
        resolve_primary_subsystem(
            [
                {"group": "Subsystem", "name": "WS-01 HTTP API and CLI"},
                {"group": "Subsystem", "name": "WS-02 Workers and Orchestration"},
            ],
            registry,
        )


def test_scope_manifest_contains_content_hashes_for_required_reading(registry_file: Path, tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("policy", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "INDEX.md").write_text("index", encoding="utf-8")
    (tmp_path / "docs" / "subsystems.yaml").write_text("registry", encoding="utf-8")

    manifest = build_scope_manifest(
        load_registry(registry_file),
        issue_id="linear-1",
        primary_subsystem="WS-1",
        allowed_paths=["backend/api/**"],
        required_reading=["docs/INDEX.md"],
        repo_root=tmp_path,
    )

    hashes = dict(manifest.content_hashes)
    assert set(hashes) == {"AGENTS.md", "docs/INDEX.md", "docs/subsystems.yaml"}
    assert len(hashes["AGENTS.md"]) == 64


def test_scope_manifest_rejects_reads_and_writes_outside_ticket_scope(registry_file: Path) -> None:
    manifest = build_scope_manifest(
        load_registry(registry_file),
        issue_id="linear-1",
        primary_subsystem="http-api-cli",
        allowed_paths=["backend/api/allowed.py"],
    )

    manifest.validate_read_paths(["backend/api/allowed.py"])
    manifest.validate_write_paths(["backend/api/allowed.py"])
    with pytest.raises(ScopeError, match="reads outside allowed paths"):
        manifest.validate_read_paths(["backend/worker/service.py"])
    with pytest.raises(ScopeError, match="writes outside allowed paths"):
        manifest.validate_write_paths(["backend/api/other.py"])


def test_cross_subsystem_allowed_path_requires_declared_co_owner(registry_file: Path) -> None:
    registry = load_registry(registry_file)
    with pytest.raises(ScopeError, match="co-owner"):
        build_scope_manifest(
            registry,
            issue_id="linear-1",
            primary_subsystem="http-api-cli",
            allowed_paths=["backend/worker/service.py"],
        )

    manifest = build_scope_manifest(
        registry,
        issue_id="linear-1",
        primary_subsystem="http-api-cli",
        allowed_paths=["backend/api/allowed.py", "backend/worker/service.py"],
        co_owners=["WS-02"],
    )
    assert manifest.co_owners == ("workers-orchestration",)
