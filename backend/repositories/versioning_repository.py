"""Versioning repository for profile, CV, and generation provenance (CP-025)."""

from __future__ import annotations

import json
from typing import Any, Mapping

from backend.database.connection import DatabaseConnection
from backend.domain.models import (
    CVAssetVersion,
    CV_VERSION_SOURCE_USED_IN_RUN,
    GenerationProvenance,
    ProfileVersion,
    PROFILE_VERSION_SOURCE_RUN,
    PROFILE_VERSION_SOURCE_SAVED,
    PROFILE_VERSION_SOURCE_RESTORE,
    utc_now_iso,
)


def _parse_json(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _profile_version_from_row(row: Mapping[str, Any]) -> ProfileVersion:
    return ProfileVersion(
        version_id=str(row["version_id"]),
        workspace_id=str(row["workspace_id"]),
        version_no=int(row["version_no"]),
        label=str(row.get("label") or ""),
        source=str(row.get("source") or PROFILE_VERSION_SOURCE_SAVED),
        workspace_snapshot=_parse_json(str(row.get("workspace_snapshot_json") or "{}")),
        resolved_settings=_parse_json(str(row.get("resolved_settings_json") or "{}")),
        created_at=str(row.get("created_at") or utc_now_iso()),
        run_id=str(row.get("run_id") or ""),
        metadata=_parse_json(str(row.get("metadata_json") or "{}")),
    )


def _cv_version_from_row(row: Mapping[str, Any]) -> CVAssetVersion:
    return CVAssetVersion(
        version_id=str(row["version_id"]),
        workspace_id=str(row["workspace_id"]),
        asset_id=str(row.get("asset_id") or ""),
        version_no=int(row.get("version_no") or 1),
        source=str(row.get("source") or CV_VERSION_SOURCE_USED_IN_RUN),
        display_name=str(row.get("display_name") or ""),
        object_key=str(row.get("object_key") or ""),
        mime_type=str(row.get("mime_type") or ""),
        extension=str(row.get("extension") or ""),
        char_count=int(row.get("char_count") or 0),
        cv_text_sha256=str(row.get("cv_text_sha256") or ""),
        source_text_preview=str(row.get("source_text_preview") or ""),
        extraction_timestamp=str(row.get("extraction_timestamp") or ""),
        created_at=str(row.get("created_at") or utc_now_iso()),
        run_id=str(row.get("run_id") or ""),
        metadata=_parse_json(str(row.get("metadata_json") or "{}")),
    )


def _provenance_from_row(row: Mapping[str, Any]) -> GenerationProvenance:
    return GenerationProvenance(
        provenance_id=str(row["provenance_id"]),
        run_id=str(row["run_id"]),
        workspace_id=str(row.get("workspace_id") or ""),
        job_id=str(row.get("job_id") or ""),
        profile_version_id=str(row.get("profile_version_id") or ""),
        profile_version_no=int(row.get("profile_version_no") or 0),
        cv_asset_version_id=str(row.get("cv_asset_version_id") or ""),
        cv_asset_version_no=int(row.get("cv_asset_version_no") or 0),
        evidence_set_key=str(row.get("evidence_set_key") or ""),
        evidence_job_count=int(row.get("evidence_job_count") or 0),
        generation_pipeline_version=str(row.get("generation_pipeline_version") or ""),
        generation_mode=str(row.get("generation_mode") or ""),
        generation_fingerprint=str(row.get("generation_fingerprint") or ""),
        renderer_version=str(row.get("renderer_version") or ""),
        created_at=str(row.get("created_at") or utc_now_iso()),
        metadata=_parse_json(str(row.get("metadata_json") or "{}")),
    )



def save_profile_version(connection: DatabaseConnection, version: ProfileVersion) -> None:
    connection.execute(
        """
        INSERT INTO profile_versions (
            version_id, workspace_id, version_no, label, source,
            workspace_snapshot_json, resolved_settings_json,
            created_at, run_id, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            version.version_id, version.workspace_id, version.version_no,
            version.label, version.source,
            json.dumps(version.workspace_snapshot, ensure_ascii=False),
            json.dumps(version.resolved_settings, ensure_ascii=False),
            version.created_at, version.run_id,
            json.dumps(version.metadata, ensure_ascii=False),
        ),
    )


def save_cv_asset_version(connection: DatabaseConnection, version: CVAssetVersion) -> None:
    connection.execute(
        """
        INSERT INTO cv_asset_versions (
            version_id, workspace_id, asset_id, version_no, source,
            display_name, object_key, mime_type, extension,
            char_count, cv_text_sha256, source_text_preview,
            extraction_timestamp, created_at, run_id, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            version.version_id, version.workspace_id, version.asset_id,
            version.version_no, version.source,
            version.display_name, version.object_key,
            version.mime_type, version.extension,
            version.char_count, version.cv_text_sha256,
            version.source_text_preview, version.extraction_timestamp,
            version.created_at, version.run_id,
            json.dumps(version.metadata, ensure_ascii=False),
        ),
    )


def save_generation_provenance(connection: DatabaseConnection, provenance: GenerationProvenance) -> None:
    connection.execute(
        """
        INSERT INTO generation_provenance (
            provenance_id, run_id, workspace_id, job_id,
            profile_version_id, profile_version_no,
            cv_asset_version_id, cv_asset_version_no,
            evidence_set_key, evidence_job_count,
            generation_pipeline_version, generation_mode,
            generation_fingerprint, renderer_version,
            created_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            provenance.provenance_id, provenance.run_id, provenance.workspace_id,
            provenance.job_id,
            provenance.profile_version_id, provenance.profile_version_no,
            provenance.cv_asset_version_id, provenance.cv_asset_version_no,
            provenance.evidence_set_key, provenance.evidence_job_count,
            provenance.generation_pipeline_version, provenance.generation_mode,
            provenance.generation_fingerprint, provenance.renderer_version,
            provenance.created_at,
            json.dumps(provenance.metadata, ensure_ascii=False),
        ),
    )


def get_latest_profile_version_no(connection: DatabaseConnection, workspace_id: str) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(version_no), 0) AS max_version FROM profile_versions WHERE workspace_id = ?",
        (workspace_id,),
    ).fetchone()
    return int(row["max_version"]) if row else 0


def get_latest_cv_asset_version_no(connection: DatabaseConnection, workspace_id: str, asset_id: str = "") -> int:
    if asset_id:
        row = connection.execute(
            "SELECT COALESCE(MAX(version_no), 0) AS max_version FROM cv_asset_versions WHERE workspace_id = ? AND asset_id = ?",
            (workspace_id, asset_id),
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT COALESCE(MAX(version_no), 0) AS max_version FROM cv_asset_versions WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()
    return int(row["max_version"]) if row else 0


def list_profile_versions(connection: DatabaseConnection, workspace_id: str, *, limit: int = 50) -> list[ProfileVersion]:
    rows = connection.execute(
        "SELECT * FROM profile_versions WHERE workspace_id = ? ORDER BY version_no DESC LIMIT ?",
        (workspace_id, limit),
    ).fetchall()
    return [_profile_version_from_row(row) for row in rows]


def list_cv_asset_versions(connection: DatabaseConnection, workspace_id: str, *, asset_id: str = "", limit: int = 50) -> list[CVAssetVersion]:
    if asset_id:
        rows = connection.execute(
            "SELECT * FROM cv_asset_versions WHERE workspace_id = ? AND asset_id = ? ORDER BY version_no DESC LIMIT ?",
            (workspace_id, asset_id, limit),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM cv_asset_versions WHERE workspace_id = ? ORDER BY version_no DESC LIMIT ?",
            (workspace_id, limit),
        ).fetchall()
    return [_cv_version_from_row(row) for row in rows]


def get_profile_version(connection: DatabaseConnection, version_id: str) -> ProfileVersion | None:
    row = connection.execute(
        "SELECT * FROM profile_versions WHERE version_id = ?", (version_id,),
    ).fetchone()
    return _profile_version_from_row(row) if row else None


def get_profile_version_by_no(connection: DatabaseConnection, workspace_id: str, version_no: int) -> ProfileVersion | None:
    row = connection.execute(
        "SELECT * FROM profile_versions WHERE workspace_id = ? AND version_no = ?",
        (workspace_id, version_no),
    ).fetchone()
    return _profile_version_from_row(row) if row else None


def list_provenance_by_run(connection: DatabaseConnection, run_id: str) -> list[GenerationProvenance]:
    rows = connection.execute(
        "SELECT * FROM generation_provenance WHERE run_id = ? ORDER BY created_at",
        (run_id,),
    ).fetchall()
    return [_provenance_from_row(row) for row in rows]


def list_provenance_by_workspace(connection: DatabaseConnection, workspace_id: str, *, limit: int = 100) -> list[GenerationProvenance]:
    rows = connection.execute(
        "SELECT * FROM generation_provenance WHERE workspace_id = ? ORDER BY created_at DESC LIMIT ?",
        (workspace_id, limit),


def restore_profile_from_version(
    connection: DatabaseConnection,
    *,
    workspace_id: str,
    version_id: str | None = None,
    version_no: int | None = None,
) -> ProfileVersion | None:
    """Create a new profile version that restores a prior version's settings."""
    if version_id:
        source_version = get_profile_version(connection, version_id)
    elif version_no is not None:
        source_version = get_profile_version_by_no(connection, workspace_id, version_no)
    else:
        return None

    if source_version is None:
        return None

    latest_no = get_latest_profile_version_no(connection, workspace_id)
    new_no = latest_no + 1

    restored = ProfileVersion.create(
        workspace_id=workspace_id,
        version_no=new_no,
        label=f"Restored from v{source_version.version_no} ({source_version.label or 'unnamed'})",
        source=PROFILE_VERSION_SOURCE_RESTORE,
        workspace_snapshot=dict(source_version.workspace_snapshot),
        resolved_settings=dict(source_version.resolved_settings),
        run_id="",
        metadata={
            "restored_from_version_id": source_version.version_id,
            "restored_from_version_no": source_version.version_no,
        },
    )
    save_profile_version(connection, restored)
    return restored


def capture_profile_version_from_run(
    connection: DatabaseConnection,
    *,
    workspace_id: str,
    workspace_snapshot: dict[str, Any],
    resolved_settings: dict[str, Any],
    run_id: str,
    label: str = "",
) -> ProfileVersion:
    """Create a profile version snapshot from a run's workspace snapshot."""
    latest_no = get_latest_profile_version_no(connection, workspace_id)
    version_no = latest_no + 1
    version = ProfileVersion.create(
        workspace_id=workspace_id,
        version_no=version_no,
        label=label or f"Run {run_id}",
        source=PROFILE_VERSION_SOURCE_RUN,
        workspace_snapshot=dict(workspace_snapshot),
        resolved_settings=dict(resolved_settings),
        run_id=run_id,
    )
    save_profile_version(connection, version)
    return version


def capture_cv_version_from_run(
    connection: DatabaseConnection,
    *,
    workspace_id: str,
    asset_id: str,
    display_name: str = "",
    object_key: str = "",
    mime_type: str = "",
    extension: str = "",
    char_count: int = 0,
    cv_text_sha256: str = "",
    source_text_preview: str = "",
    run_id: str = "",
) -> CVAssetVersion:
    """Create a CV asset version snapshot from a run."""
    latest_no = get_latest_cv_asset_version_no(connection, workspace_id, asset_id)
    version_no = latest_no + 1
    version = CVAssetVersion.create(
        workspace_id=workspace_id,
        asset_id=asset_id,
        version_no=version_no,
        source=CV_VERSION_SOURCE_USED_IN_RUN,
        display_name=display_name,
        object_key=object_key,
        mime_type=mime_type,
        extension=extension,
        char_count=char_count,
        cv_text_sha256=cv_text_sha256,
        source_text_preview=source_text_preview,
        run_id=run_id,
    )
    save_cv_asset_version(connection, version)
    return version

    ).fetchall()
    return [_provenance_from_row(row) for row in rows]

            provenance.job_id,
            provenance.profile_version_id, provenance.profile_version_no,
            provenance.cv_asset_version_id, provenance.cv_asset_version_no,
            provenance.evidence_set_key, provenance.evidence_job_count,
            provenance.generation_pipeline_version, provenance.generation_mode,
            provenance.generation_fingerprint, provenance.renderer_version,
            provenance.created_at,
            json.dumps(provenance.metadata, ensure_ascii=False),
        ),
    )
