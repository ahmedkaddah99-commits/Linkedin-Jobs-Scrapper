"""Create, validate, preserve and restore bounded acquisition checkpoints.

The checkpoint database is made with SQLite's Online Backup API.  The source
database is opened read-only and is never copied together with its WAL/SHM
sidecars.  A checkpoint manifest is the remote commit record: the database is
uploaded first and the manifest last.  A remote checkpoint without its
manifest is therefore incomplete and must not be restored.

This module deliberately has no producer or provider imports.  It can be used
by the acquisition service and tested with fixture databases without starting
an acquisition run or contacting a provider.  S3/R2 uploads happen only when
the caller explicitly supplies a remote store (or the CLI ``--upload`` flag).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Protocol
from urllib.parse import quote


CHECKPOINT_SCHEMA_VERSION = "runr.acquisition.checkpoint.v1"
RECEIPT_SCHEMA_VERSION = "runr.acquisition.off-host-receipt.v1"
LEASE_SCHEMA_VERSION = "runr.acquisition.single-writer-lease.v1"
MANIFEST_FILENAME = "checkpoint.json"
MARKER_FILENAME = ".runr-checkpoint"
RECEIPT_FILENAME = "off-host-receipt.json"
DEFAULT_REMOTE_PREFIX = "runr/acquisition/checkpoints"
DEFAULT_LOCAL_RETENTION = 3
DEFAULT_REMOTE_RETENTION = 7
DEFAULT_FREE_SPACE_RESERVE = 64 * 1024 * 1024

ROLE_CONFIG: dict[str, dict[str, Any]] = {
    "linkedin": {
        "logical_name": "linkedin_authoritative_state",
        "db_filename": "master_linkedin_jobs_state.db",
        "required_tables": (
            "runs",
            "source_company_groups",
            "company_slug_aliases",
            "company_scans",
            "query_partitions",
            "search_pages",
            "search_cards",
            "jobs",
            "job_company_observations",
            "detail_queue",
            "detail_attempts",
            "ownership_exclusions",
            "lifecycle_events",
            "proxy_health",
        ),
    },
    "employer": {
        "logical_name": "employer_state",
        "db_filename": "master_employer_jobs_state.db",
        "required_tables": ("companies", "jobs"),
    },
}

SENSITIVE_KEY_PARTS = (
    "secret",
    "password",
    "token",
    "cookie",
    "credential",
    "api_key",
    "apikey",
    "browser_profile",
    "profile_path",
)


class CheckpointError(RuntimeError):
    """Raised when a checkpoint cannot be safely created or used."""


class RemoteStoreError(CheckpointError):
    """Raised for an off-host preservation or restore failure."""


class OwnershipConflict(CheckpointError):
    """Raised when another live owner holds the logical shard."""


class LeaseFenced(CheckpointError):
    """Raised when a worker tries to act with an expired or replaced lease."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_file(path: Path) -> None:
    # Windows does not permit FlushFileBuffers through a read-only handle.
    # Generated checkpoint/restore files are writable, and opening them here
    # does not change their contents.
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        _fsync_directory(path.parent)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _safe_component(value: str, *, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or normalized in {".", ".."} or "/" in normalized or "\\" in normalized or "\x00" in normalized:
        raise ValueError(f"{label} must be a non-empty single path component")
    return normalized


def _safe_remote_prefix(value: str) -> str:
    normalized = str(value or DEFAULT_REMOTE_PREFIX).strip().replace("\\", "/").strip("/")
    if not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError("remote prefix must be a relative object prefix")
    return normalized


def _validate_digest(value: str, *, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
        raise ValueError(f"{label} must be a SHA-256 hex digest")
    return normalized


def _validate_safe_mapping(payload: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw_key, value in payload.items():
        key = str(raw_key).strip()
        lowered = key.lower()
        if not key or any(part in lowered for part in SENSITIVE_KEY_PARTS):
            raise ValueError(f"{label} contains a secret or browser-profile key: {key!r}")
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[key] = value
        else:
            raise ValueError(f"{label} values must be scalar checkpoint markers")
    return result


def _normalise_evidence(evidence: Mapping[str, Any] | None) -> dict[str, list[str]]:
    allowed = {"terminal_receipt_ids", "identity_evidence_ids", "absence_evidence_ids"}
    result: dict[str, list[str]] = {}
    for raw_key, raw_values in (evidence or {}).items():
        key = str(raw_key)
        if key not in allowed:
            raise ValueError(f"unsupported evidence field: {key}")
        if isinstance(raw_values, str):
            values = [raw_values]
        elif isinstance(raw_values, (list, tuple)):
            values = [str(item).strip() for item in raw_values]
        else:
            raise ValueError(f"{key} must be a list of compact evidence IDs")
        if any(not value or len(value) > 256 or any(part in value.lower() for part in SENSITIVE_KEY_PARTS) for value in values):
            raise ValueError(f"{key} contains an invalid or sensitive evidence ID")
        result[key] = values
    return result


def _readonly_connection(path: Path) -> sqlite3.Connection:
    encoded_path = quote(str(path.resolve()).replace("\\", "/"), safe="/:")
    return sqlite3.connect(f"file:{encoded_path}?mode=ro", uri=True, timeout=30)


def _sqlite_schema(path: Path, role: str, *, integrity: bool = True) -> dict[str, Any]:
    config = ROLE_CONFIG[role]
    connection = _readonly_connection(path)
    try:
        tables = sorted(
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        )
        expected = sorted(config["required_tables"])
        if tables != expected:
            raise CheckpointError(
                f"{role} state schema mismatch: expected {expected}, got {tables}"
            )
        integrity_result = "not_run"
        if integrity:
            integrity_result = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            if integrity_result != "ok":
                raise CheckpointError(f"SQLite integrity check failed for {path}: {integrity_result}")
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        return {
            "user_version": user_version,
            "tables": tables,
            "integrity_check": integrity_result,
        }
    finally:
        connection.close()


def _sqlite_online_backup(
    source: Path,
    destination: Path,
    *,
    pages: int = 1024,
    sleep: float = 0.05,
    progress: Callable[[int, int, int], None] | None = None,
) -> None:
    if pages <= 0:
        raise ValueError("backup pages must be positive")
    source_connection = _readonly_connection(source)
    destination_connection = sqlite3.connect(str(destination), timeout=30)
    try:
        def report(status: int, remaining: int, total: int) -> None:
            if progress is not None:
                progress(status, remaining, total)

        source_connection.backup(
            destination_connection,
            pages=pages,
            progress=report,
            sleep=max(0.0, float(sleep)),
        )
        # A backup of a WAL-mode source can carry the source page-1 journal
        # mode.  Keep each checkpoint self-contained and rollback-journaled so
        # no destination WAL/SHM sidecars become part of the artifact.
        destination_connection.commit()
        destination_connection.execute("PRAGMA journal_mode=DELETE")
        destination_connection.commit()
    finally:
        destination_connection.close()
        source_connection.close()
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(f"{destination}{suffix}")
            if sidecar.exists():
                sidecar.unlink()


def _remote_keys(*, prefix: str, role: str, checkpoint_id: str, db_filename: str) -> tuple[str, str]:
    base = f"{_safe_remote_prefix(prefix)}/{_safe_component(role, label='role')}/{_safe_component(checkpoint_id, label='checkpoint_id')}"
    return f"{base}/{db_filename}", f"{base}/{MANIFEST_FILENAME}"


def _checkpoint_manifest_path(checkpoint_dir: Path) -> Path:
    return checkpoint_dir / MANIFEST_FILENAME


def create_checkpoint(
    *,
    role: str,
    source_db: str | Path,
    checkpoint_root: str | Path,
    source_version: str,
    manifest_id: str,
    manifest_sha256: str,
    cycle_id: str,
    shard_id: str,
    high_water_marks: Mapping[str, Any],
    release_commit: str = "",
    evidence: Mapping[str, Any] | None = None,
    source_sha256: str = "",
    source_bytes: int | None = None,
    remote_prefix: str = DEFAULT_REMOTE_PREFIX,
    local_retention_generations: int = DEFAULT_LOCAL_RETENTION,
    remote_retention_generations: int = DEFAULT_REMOTE_RETENTION,
    free_space_reserve_bytes: int = DEFAULT_FREE_SPACE_RESERVE,
    local_budget_bytes: int | None = None,
    backup_pages: int = 1024,
    backup_sleep: float = 0.05,
    progress: Callable[[int, int, int], None] | None = None,
    clock: Callable[[], str] = _utc_now,
) -> dict[str, Any]:
    if role not in ROLE_CONFIG:
        raise ValueError(f"unsupported acquisition state role: {role}")
    if not str(source_version or "").strip():
        raise ValueError("source_version is required")
    if not str(manifest_id or "").strip():
        raise ValueError("manifest_id is required")
    manifest_digest = _validate_digest(manifest_sha256, label="manifest_sha256")
    cycle = _safe_component(cycle_id, label="cycle_id")
    shard = _safe_component(shard_id, label="shard_id")
    high_water = _validate_safe_mapping(high_water_marks, label="high_water_marks")
    safe_evidence = _normalise_evidence(evidence)
    local_keep = max(1, int(local_retention_generations))
    remote_keep = max(1, int(remote_retention_generations))

    source_path = Path(source_db).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"source state database not found: {source_path}")
    source_stat = source_path.stat()
    observed_bytes = int(source_stat.st_size)
    if source_bytes is not None and observed_bytes != int(source_bytes):
        raise CheckpointError(f"source byte count mismatch: expected {source_bytes}, got {observed_bytes}")
    observed_digest = _sha256_file(source_path)
    if source_sha256:
        expected_source_digest = _validate_digest(source_sha256, label="source_sha256")
        if observed_digest != expected_source_digest:
            raise CheckpointError(
                f"source SHA-256 mismatch: expected {expected_source_digest}, got {observed_digest}"
            )
    schema = _sqlite_schema(source_path, role)

    root = Path(checkpoint_root).expanduser().resolve()
    role_root = root / role
    usage_path = root if root.exists() else root.parent
    free_bytes = shutil.disk_usage(usage_path).free
    required_free = observed_bytes + max(0, int(free_space_reserve_bytes))
    if free_bytes < required_free:
        raise CheckpointError(
            f"insufficient free space for atomic backup: need {required_free} bytes, have {free_bytes}"
        )
    if local_budget_bytes is not None:
        existing_bytes = sum(item.stat().st_size for item in role_root.rglob("*") if item.is_file()) if role_root.is_dir() else 0
        projected_bytes = existing_bytes + observed_bytes + max(0, int(free_space_reserve_bytes))
        if projected_bytes > int(local_budget_bytes):
            raise CheckpointError(
                "local checkpoint budget exhausted; pause acquisition before accepting more buffered state"
            )
    role_root.mkdir(parents=True, exist_ok=True)

    checkpoint_id = f"{role}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex[:12]}"
    checkpoint_dir = role_root / checkpoint_id
    db_filename = str(ROLE_CONFIG[role]["db_filename"])
    database_key, manifest_key = _remote_keys(
        prefix=remote_prefix,
        role=role,
        checkpoint_id=checkpoint_id,
        db_filename=db_filename,
    )
    checkpoint_dir.mkdir()
    (checkpoint_dir / MARKER_FILENAME).write_text("runr acquisition checkpoint\n", encoding="utf-8")
    temporary_path: Path | None = None
    try:
        temporary_path = checkpoint_dir / f".{db_filename}.{uuid.uuid4().hex}.tmp"
        _sqlite_online_backup(
            source_path,
            temporary_path,
            pages=backup_pages,
            sleep=backup_sleep,
            progress=progress,
        )
        _fsync_file(temporary_path)
        destination_path = checkpoint_dir / db_filename
        os.replace(temporary_path, destination_path)
        temporary_path = None
        backup_schema = _sqlite_schema(destination_path, role)
        backup_bytes = int(destination_path.stat().st_size)
        backup_digest = _sha256_file(destination_path)
        manifest: dict[str, Any] = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "checkpoint_id": checkpoint_id,
            "role": role,
            "created_at": clock(),
            "release": {
                "source_version": str(source_version).strip(),
                "commit": str(release_commit or source_version).strip(),
            },
            "input_manifest": {"id": str(manifest_id).strip(), "sha256": manifest_digest},
            "cycle": {
                "cycle_id": cycle,
                "shard_id": shard,
                "high_water_marks": high_water,
            },
            "state": {
                "logical_name": ROLE_CONFIG[role]["logical_name"],
                "source_basename": source_path.name,
                "source_bytes_before_backup": observed_bytes,
                "source_sha256_before_backup": observed_digest,
                "schema": schema,
            },
            "backup": {
                "filename": db_filename,
                "bytes": backup_bytes,
                "sha256": backup_digest,
                "method": "sqlite_online_backup",
                "wal_consistent": True,
                "sidecars_included": False,
                "schema": backup_schema,
            },
            "evidence": safe_evidence,
            "retention": {
                "local_generations_to_keep": local_keep,
                "remote_generations_to_keep": remote_keep,
                "temporary_peak_bytes_estimate": observed_bytes + int(free_space_reserve_bytes),
                "prune_requires_verified_off_host_receipt": True,
            },
            "off_host": {
                "provider": "s3_compatible_r2",
                "configured_via": ["S3_ENDPOINT_URL", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_BUCKET"],
                "status": "not_uploaded",
                "database_object_key": database_key,
                "manifest_object_key": manifest_key,
                "manifest_is_commit_record": True,
                "publication_order": ["database", "manifest"],
            },
        }
        _atomic_write_json(_checkpoint_manifest_path(checkpoint_dir), manifest)
        _fsync_directory(checkpoint_dir)
        return manifest
    except BaseException:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
        shutil.rmtree(checkpoint_dir, ignore_errors=True)
        raise


def validate_checkpoint(checkpoint_dir: str | Path, *, expected_role: str = "") -> dict[str, Any]:
    root = Path(checkpoint_dir).expanduser().resolve()
    marker = root / MARKER_FILENAME
    manifest_path = _checkpoint_manifest_path(root)
    if not marker.is_file() or not manifest_path.is_file():
        raise CheckpointError(f"not a Runr checkpoint directory: {root}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckpointError(f"invalid checkpoint manifest: {manifest_path}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise CheckpointError("unsupported checkpoint manifest schema")
    role = str(manifest.get("role") or "")
    if role not in ROLE_CONFIG or (expected_role and role != expected_role):
        raise CheckpointError(f"unexpected checkpoint role: {role}")
    checkpoint_id = _safe_component(str(manifest.get("checkpoint_id") or ""), label="checkpoint_id")
    backup = manifest.get("backup")
    if not isinstance(backup, dict):
        raise CheckpointError("checkpoint backup metadata is missing")
    database_path = root / str(backup.get("filename") or "")
    expected_path = root / ROLE_CONFIG[role]["db_filename"]
    if database_path != expected_path or not database_path.is_file():
        raise CheckpointError(f"checkpoint database is missing or has an unexpected path: {database_path}")
    expected_bytes = int(backup.get("bytes") or -1)
    expected_digest = _validate_digest(str(backup.get("sha256") or ""), label="backup.sha256")
    actual_bytes = int(database_path.stat().st_size)
    if actual_bytes != expected_bytes:
        raise CheckpointError(f"checkpoint byte count mismatch: expected {expected_bytes}, got {actual_bytes}")
    actual_digest = _sha256_file(database_path)
    if actual_digest != expected_digest:
        raise CheckpointError(f"checkpoint SHA-256 mismatch: expected {expected_digest}, got {actual_digest}")
    if backup.get("method") != "sqlite_online_backup" or backup.get("wal_consistent") is not True:
        raise CheckpointError("checkpoint was not made with the WAL-consistent Online Backup API")
    schema = _sqlite_schema(database_path, role)
    recorded_schema = backup.get("schema")
    if isinstance(recorded_schema, dict) and recorded_schema.get("tables") != schema.get("tables"):
        raise CheckpointError("checkpoint schema metadata does not match the database")
    if str(manifest.get("checkpoint_id")) != checkpoint_id:
        raise CheckpointError("checkpoint identity is invalid")
    return manifest


def restore_checkpoint(
    checkpoint_dir: str | Path,
    target_dir: str | Path,
    *,
    expected_role: str = "",
    clock: Callable[[], str] = _utc_now,
) -> dict[str, Any]:
    manifest = validate_checkpoint(checkpoint_dir, expected_role=expected_role)
    role = str(manifest["role"])
    source_root = Path(checkpoint_dir).expanduser().resolve()
    destination_root = Path(target_dir).expanduser().resolve()
    if destination_root.exists():
        raise CheckpointError(f"isolated restore target already exists; refusing overwrite: {destination_root}")
    destination_root.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(prefix=f".runr-restore-{role}-", dir=destination_root.parent))
    try:
        filename = str(ROLE_CONFIG[role]["db_filename"])
        source_db = source_root / filename
        target_db = temporary_root / filename
        shutil.copyfile(source_db, target_db)
        _fsync_file(target_db)
        restored_schema = _sqlite_schema(target_db, role)
        restored_digest = _sha256_file(target_db)
        if restored_digest != str(manifest["backup"]["sha256"]):
            raise CheckpointError("restored database digest differs from verified checkpoint")
        receipt = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "checkpoint_id": manifest["checkpoint_id"],
            "role": role,
            "restored_at": clock(),
            "source_backup_sha256": manifest["backup"]["sha256"],
            "restored_database_sha256": restored_digest,
            "schema": restored_schema,
            "resume": {
                "state_path": f"<target>/{filename}",
                "require_existing_state": True,
                "publication_replay": "resume producer from checkpoint; do not overwrite a newer target",
            },
        }
        _atomic_write_json(temporary_root / "restore-receipt.json", receipt)
        os.replace(temporary_root, destination_root)
        _fsync_directory(destination_root.parent)
        return receipt
    except BaseException:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise


class RemoteStore(Protocol):
    def put_file(self, path: Path, key: str, *, metadata: Mapping[str, str], content_type: str) -> Mapping[str, Any]: ...

    def head_file(self, key: str) -> Mapping[str, Any] | None: ...

    def get_file(self, key: str, destination: Path) -> None: ...


class S3CompatibleRemoteStore:
    """Streaming S3/R2 adapter using the repository's approved env contract."""

    def __init__(self, *, bucket: str, client: Any) -> None:
        if not str(bucket or "").strip():
            raise ValueError("S3_BUCKET is required for off-host preservation")
        self.bucket = str(bucket).strip()
        self.client = client

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "S3CompatibleRemoteStore":
        source = os.environ if environ is None else environ
        endpoint = str(source.get("S3_ENDPOINT_URL") or "").strip()
        access_key = str(source.get("S3_ACCESS_KEY_ID") or "").strip()
        secret_key = str(source.get("S3_SECRET_ACCESS_KEY") or "").strip()
        bucket = str(source.get("S3_BUCKET") or "").strip()
        missing = [name for name, value in {
            "S3_ENDPOINT_URL": endpoint,
            "S3_ACCESS_KEY_ID": access_key,
            "S3_SECRET_ACCESS_KEY": secret_key,
            "S3_BUCKET": bucket,
        }.items() if not value]
        if missing:
            raise ValueError("missing S3/R2 configuration: " + ", ".join(missing))
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError("boto3/botocore are required for S3/R2 preservation") from exc
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=str(source.get("S3_REGION") or "auto"),
            config=Config(
                signature_version="s3v4",
                connect_timeout=max(1, int(source.get("S3_CONNECT_TIMEOUT_SECONDS", "3"))),
                read_timeout=max(1, int(source.get("S3_READ_TIMEOUT_SECONDS", "15"))),
                retries={"max_attempts": max(1, int(source.get("S3_MAX_ATTEMPTS", "2"))), "mode": "standard"},
            ),
        )
        return cls(bucket=bucket, client=client)

    def put_file(self, path: Path, key: str, *, metadata: Mapping[str, str], content_type: str) -> Mapping[str, Any]:
        body = Path(path)
        digest = str(metadata.get("sha256") or "")
        try:
            existing = self.head_file(key)
        except Exception as exc:
            raise RemoteStoreError(f"unable to inspect existing remote checkpoint object: {key}") from exc
        if existing is not None:
            existing_metadata = {str(k).lower(): str(v) for k, v in (existing.get("Metadata") or {}).items()}
            if int(existing.get("ContentLength") or -1) == body.stat().st_size and existing_metadata.get("sha256") == digest:
                return {"status": "already_present", "key": key, "bytes": body.stat().st_size, "sha256": digest}
            raise RemoteStoreError(f"refusing to overwrite a different immutable remote object: {key}")
        try:
            self.client.upload_file(
                str(body),
                self.bucket,
                key,
                ExtraArgs={"ContentType": content_type, "Metadata": {str(k): str(v) for k, v in metadata.items()}},
            )
            observed = self.head_file(key)
        except Exception as exc:
            raise RemoteStoreError(f"off-host upload failed: {key}") from exc
        if observed is None:
            raise RemoteStoreError(f"off-host upload did not produce an object: {key}")
        observed_metadata = {str(k).lower(): str(v) for k, v in (observed.get("Metadata") or {}).items()}
        if int(observed.get("ContentLength") or -1) != body.stat().st_size or observed_metadata.get("sha256") != digest:
            raise RemoteStoreError(f"off-host upload verification failed: {key}")
        return {"status": "uploaded", "key": key, "bytes": body.stat().st_size, "sha256": digest}

    def head_file(self, key: str) -> Mapping[str, Any] | None:
        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            response = getattr(exc, "response", None)
            error = response.get("Error", {}) if isinstance(response, Mapping) else {}
            if str(error.get("Code") or "") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise

    def get_file(self, key: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            self.client.download_file(self.bucket, key, str(temporary))
            _fsync_file(temporary)
            os.replace(temporary, destination)
        except Exception as exc:
            raise RemoteStoreError(f"off-host download failed: {key}") from exc
        finally:
            if temporary.exists():
                temporary.unlink()


def preserve_checkpoint_off_host(checkpoint_dir: str | Path, remote: RemoteStore) -> dict[str, Any]:
    checkpoint_root = Path(checkpoint_dir).expanduser().resolve()
    manifest = validate_checkpoint(checkpoint_root)
    database = checkpoint_root / str(manifest["backup"]["filename"])
    off_host = manifest["off_host"]
    database_receipt = remote.put_file(
        database,
        str(off_host["database_object_key"]),
        metadata={
            "sha256": str(manifest["backup"]["sha256"]),
            "checkpoint-id": str(manifest["checkpoint_id"]),
            "role": str(manifest["role"]),
        },
        content_type="application/vnd.sqlite3",
    )
    manifest_receipt = remote.put_file(
        _checkpoint_manifest_path(checkpoint_root),
        str(off_host["manifest_object_key"]),
        metadata={
            "sha256": _sha256_file(_checkpoint_manifest_path(checkpoint_root)),
            "checkpoint-id": str(manifest["checkpoint_id"]),
            "role": str(manifest["role"]),
        },
        content_type="application/json",
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "checkpoint_id": manifest["checkpoint_id"],
        "role": manifest["role"],
        "published_at": _utc_now(),
        "publication_order": ["database", "manifest"],
        "database": dict(database_receipt),
        "manifest": dict(manifest_receipt),
        "manifest_is_commit_record": True,
    }
    _atomic_write_json(checkpoint_root / RECEIPT_FILENAME, receipt)
    return receipt


def restore_remote_checkpoint(
    remote: RemoteStore,
    *,
    manifest_key: str,
    target_dir: str | Path,
    expected_role: str = "",
) -> dict[str, Any]:
    destination_root = Path(target_dir).expanduser().resolve()
    if destination_root.exists():
        raise CheckpointError(f"isolated restore target already exists; refusing overwrite: {destination_root}")
    destination_root.parent.mkdir(parents=True, exist_ok=True)
    temporary_checkpoint = Path(tempfile.mkdtemp(prefix=".runr-remote-checkpoint-", dir=destination_root.parent))
    try:
        remote_manifest_head = remote.head_file(manifest_key)
        if remote_manifest_head is None:
            raise RemoteStoreError(f"remote checkpoint manifest is missing: {manifest_key}")
        remote.get_file(manifest_key, temporary_checkpoint / MANIFEST_FILENAME)
        remote_manifest_digest = _sha256_file(temporary_checkpoint / MANIFEST_FILENAME)
        recorded_remote_digest = str((remote_manifest_head.get("Metadata") or {}).get("sha256") or "")
        if recorded_remote_digest and remote_manifest_digest != recorded_remote_digest:
            raise RemoteStoreError("remote checkpoint manifest metadata hash mismatch")
        manifest = json.loads((temporary_checkpoint / MANIFEST_FILENAME).read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise CheckpointError("remote checkpoint manifest is not an object")
        role = str(manifest.get("role") or "")
        if expected_role and role != expected_role:
            raise CheckpointError(f"unexpected remote checkpoint role: {role}")
        if role not in ROLE_CONFIG:
            raise CheckpointError(f"unexpected remote checkpoint role: {role}")
        if str((manifest.get("off_host") or {}).get("manifest_object_key") or "") != manifest_key:
            raise CheckpointError("remote checkpoint manifest key does not match its committed object key")
        (temporary_checkpoint / MARKER_FILENAME).write_text("runr acquisition checkpoint\n", encoding="utf-8")
        database_key = str((manifest.get("off_host") or {}).get("database_object_key") or "")
        if not database_key:
            raise CheckpointError("remote checkpoint database object key is missing")
        remote.get_file(database_key, temporary_checkpoint / str(ROLE_CONFIG[role]["db_filename"]))
        validate_checkpoint(temporary_checkpoint, expected_role=role)
        return restore_checkpoint(temporary_checkpoint, destination_root, expected_role=role)
    finally:
        shutil.rmtree(temporary_checkpoint, ignore_errors=True)


@contextmanager
def _exclusive_file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True)
class StateLease:
    store: "SingleWriterLease"
    role: str
    shard_id: str
    owner_id: str
    token: str
    epoch: int
    expires_at: float

    def assert_current(self) -> None:
        self.store.assert_current(self)

    def renew(self, ttl_seconds: int = 300) -> "StateLease":
        return self.store.renew(self, ttl_seconds=ttl_seconds)

    def release(self) -> None:
        self.store.release(self)


class SingleWriterLease:
    """Epoch-fenced lease ledger for one logical state shard.

    ``root`` must be a shared durable path visible to every possible owner,
    such as the approved state/ownership mount.  A local per-host directory is
    suitable for fixture rehearsal only and cannot coordinate two machines.
    """

    def __init__(self, root: str | Path, *, clock: Callable[[], float] = time.time) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._ledger_path = self.root / "ownership.json"
        self._lock_path = self.root / "ownership.lock"

    @staticmethod
    def _key(role: str, shard_id: str) -> str:
        return json.dumps([_safe_component(role, label="role"), _safe_component(shard_id, label="shard_id")], separators=(",", ":"))

    def _read(self) -> dict[str, Any]:
        if not self._ledger_path.exists():
            return {"schema_version": LEASE_SCHEMA_VERSION, "leases": {}}
        payload = json.loads(self._ledger_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != LEASE_SCHEMA_VERSION:
            raise CheckpointError("unsupported single-writer lease ledger schema")
        leases = payload.get("leases")
        if not isinstance(leases, dict):
            raise CheckpointError("invalid single-writer lease ledger")
        return payload

    def _write(self, payload: Mapping[str, Any]) -> None:
        _atomic_write_json(self._ledger_path, payload)

    def claim(self, *, role: str, shard_id: str, owner_id: str, ttl_seconds: int = 300) -> StateLease:
        owner = _safe_component(owner_id, label="owner_id")
        ttl = max(1, int(ttl_seconds))
        key = self._key(role, shard_id)
        now = float(self._clock())
        with _exclusive_file_lock(self._lock_path):
            ledger = self._read()
            existing = ledger["leases"].get(key)
            if isinstance(existing, dict) and float(existing.get("expires_at") or 0) > now:
                raise OwnershipConflict(f"active owner already holds {role}/{shard_id}")
            epoch = int(existing.get("epoch") or 0) + 1 if isinstance(existing, dict) else 1
            token = uuid.uuid4().hex
            expires_at = now + ttl
            record = {
                "role": role,
                "shard_id": shard_id,
                "owner_id": owner,
                "token": token,
                "epoch": epoch,
                "claimed_at": now,
                "expires_at": expires_at,
            }
            ledger["leases"][key] = record
            self._write(ledger)
        return StateLease(self, role, shard_id, owner, token, epoch, expires_at)

    def _assert_record(self, lease: StateLease, *, now: float) -> dict[str, Any]:
        key = self._key(lease.role, lease.shard_id)
        with _exclusive_file_lock(self._lock_path):
            ledger = self._read()
            record = ledger["leases"].get(key)
            if not isinstance(record, dict) or any(
                record.get(field) != value
                for field, value in {
                    "owner_id": lease.owner_id,
                    "token": lease.token,
                    "epoch": lease.epoch,
                }.items()
            ) or float(record.get("expires_at") or 0) <= now:
                raise LeaseFenced(f"lease fenced for {lease.role}/{lease.shard_id}")
            return record

    def assert_current(self, lease: StateLease) -> None:
        self._assert_record(lease, now=float(self._clock()))

    def renew(self, lease: StateLease, *, ttl_seconds: int = 300) -> StateLease:
        now = float(self._clock())
        ttl = max(1, int(ttl_seconds))
        key = self._key(lease.role, lease.shard_id)
        with _exclusive_file_lock(self._lock_path):
            ledger = self._read()
            record = ledger["leases"].get(key)
            if not isinstance(record, dict) or any(
                record.get(field) != value
                for field, value in {"owner_id": lease.owner_id, "token": lease.token, "epoch": lease.epoch}.items()
            ) or float(record.get("expires_at") or 0) <= now:
                raise LeaseFenced(f"lease fenced for {lease.role}/{lease.shard_id}")
            record["expires_at"] = now + ttl
            ledger["leases"][key] = record
            self._write(ledger)
        return StateLease(self, lease.role, lease.shard_id, lease.owner_id, lease.token, lease.epoch, now + ttl)

    def release(self, lease: StateLease) -> None:
        key = self._key(lease.role, lease.shard_id)
        with _exclusive_file_lock(self._lock_path):
            ledger = self._read()
            record = ledger["leases"].get(key)
            if isinstance(record, dict) and record.get("token") == lease.token and record.get("epoch") == lease.epoch:
                del ledger["leases"][key]
                self._write(ledger)


def prune_local_checkpoints(
    checkpoint_root: str | Path,
    *,
    role: str,
    keep: int,
    apply: bool = False,
) -> list[str]:
    """Return, and optionally remove, only old generated checkpoints.

    A checkpoint is eligible only after a durable off-host receipt exists.  No
    source database or unpreserved local checkpoint is touched.
    """

    if role not in ROLE_CONFIG:
        raise ValueError(f"unsupported acquisition state role: {role}")
    role_root = Path(checkpoint_root).expanduser().resolve() / role
    if not role_root.is_dir():
        return []
    candidates: list[tuple[float, Path]] = []
    for item in role_root.iterdir():
        if not item.is_dir() or not (item / MARKER_FILENAME).is_file() or not (item / RECEIPT_FILENAME).is_file():
            continue
        try:
            manifest = validate_checkpoint(item, expected_role=role)
        except (CheckpointError, OSError, ValueError, json.JSONDecodeError):
            continue
        candidates.append((str(manifest.get("created_at") or ""), item))
    candidates.sort(key=lambda entry: entry[0])
    removable = [item for _, item in candidates[:-max(1, int(keep))]]
    if apply:
        for item in removable:
            shutil.rmtree(item)
    return [str(item) for item in removable]


def _parse_high_water(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"high-water marker must be key=value: {value}")
        key, marker = value.split("=", 1)
        result[key] = marker
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup = subparsers.add_parser("backup", help="create one consistent checkpoint")
    backup.add_argument("--role", choices=tuple(ROLE_CONFIG), required=True)
    backup.add_argument("--source-db", type=Path, required=True)
    backup.add_argument("--checkpoint-root", type=Path, required=True)
    backup.add_argument("--source-version", required=True)
    backup.add_argument("--release-commit", default="")
    backup.add_argument("--manifest-id", required=True)
    backup.add_argument("--manifest-sha256", required=True)
    backup.add_argument("--cycle-id", required=True)
    backup.add_argument("--shard-id", required=True)
    backup.add_argument("--high-water", action="append", default=[])
    backup.add_argument("--source-sha256", default="")
    backup.add_argument("--source-bytes", type=int)
    backup.add_argument("--remote-prefix", default=DEFAULT_REMOTE_PREFIX)
    backup.add_argument("--free-space-reserve-bytes", type=int, default=DEFAULT_FREE_SPACE_RESERVE)
    backup.add_argument(
        "--local-budget-bytes",
        type=int,
        help="measured local checkpoint/outage budget; refuse another checkpoint when it would be exceeded",
    )
    backup.add_argument("--upload", action="store_true", help="upload to configured S3/R2 after local creation")
    validate = subparsers.add_parser("validate", help="validate one local checkpoint")
    validate.add_argument("--checkpoint-dir", type=Path, required=True)
    validate.add_argument("--role", choices=tuple(ROLE_CONFIG), default="")
    restore = subparsers.add_parser("restore", help="restore into a new isolated state directory")
    restore.add_argument("--checkpoint-dir", type=Path, required=True)
    restore.add_argument("--target-dir", type=Path, required=True)
    restore.add_argument("--role", choices=tuple(ROLE_CONFIG), default="")
    remote_restore = subparsers.add_parser("restore-remote", help="download and restore a committed S3/R2 checkpoint")
    remote_restore.add_argument("--manifest-key", required=True)
    remote_restore.add_argument("--target-dir", type=Path, required=True)
    remote_restore.add_argument("--role", choices=tuple(ROLE_CONFIG), default="")
    prune = subparsers.add_parser("prune", help="list or remove preserved old local generations")
    prune.add_argument("--checkpoint-root", type=Path, required=True)
    prune.add_argument("--role", choices=tuple(ROLE_CONFIG), required=True)
    prune.add_argument("--keep", type=int, default=DEFAULT_LOCAL_RETENTION)
    prune.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "backup":
            manifest = create_checkpoint(
                role=args.role,
                source_db=args.source_db,
                checkpoint_root=args.checkpoint_root,
                source_version=args.source_version,
                release_commit=args.release_commit,
                manifest_id=args.manifest_id,
                manifest_sha256=args.manifest_sha256,
                cycle_id=args.cycle_id,
                shard_id=args.shard_id,
                high_water_marks=_parse_high_water(args.high_water),
                source_sha256=args.source_sha256,
                source_bytes=args.source_bytes,
                remote_prefix=args.remote_prefix,
                free_space_reserve_bytes=args.free_space_reserve_bytes,
                local_budget_bytes=args.local_budget_bytes,
            )
            checkpoint_dir = Path(args.checkpoint_root).expanduser().resolve() / args.role / manifest["checkpoint_id"]
            result: dict[str, Any] = {"checkpoint": manifest}
            if args.upload:
                result["off_host"] = preserve_checkpoint_off_host(
                    checkpoint_dir,
                    S3CompatibleRemoteStore.from_environment(),
                )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "validate":
            print(json.dumps(validate_checkpoint(args.checkpoint_dir, expected_role=args.role), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "restore":
            print(json.dumps(restore_checkpoint(args.checkpoint_dir, args.target_dir, expected_role=args.role), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "restore-remote":
            print(json.dumps(restore_remote_checkpoint(S3CompatibleRemoteStore.from_environment(), manifest_key=args.manifest_key, target_dir=args.target_dir, expected_role=args.role), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "prune":
            print(json.dumps({"apply": bool(args.apply), "removed": prune_local_checkpoints(args.checkpoint_root, role=args.role, keep=args.keep, apply=args.apply)}, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except (CheckpointError, OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"acquisition checkpoint failed: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "CheckpointError",
    "LeaseFenced",
    "OwnershipConflict",
    "ROLE_CONFIG",
    "RemoteStoreError",
    "SingleWriterLease",
    "StateLease",
    "S3CompatibleRemoteStore",
    "create_checkpoint",
    "main",
    "preserve_checkpoint_off_host",
    "prune_local_checkpoints",
    "restore_checkpoint",
    "restore_remote_checkpoint",
    "validate_checkpoint",
]
