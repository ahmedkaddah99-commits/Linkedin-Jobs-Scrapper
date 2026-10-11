from __future__ import annotations

import hashlib
import mimetypes
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from backend.domain.models import ArtifactRecord

from .base import ObjectStorage
from .keys import build_private_object_key, normalize_object_key
from .policy import validate_object_download


_DEFAULT_CACHE_MAX_BYTES = 512 * 1024 * 1024
_DEFAULT_CACHE_MAX_AGE_SECONDS = 24 * 60 * 60


def _positive_env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default)) or str(default)))
    except (TypeError, ValueError):
        return default


def _cache_root() -> Path:
    return Path(os.getenv("OBJECT_STORAGE_CACHE_ROOT", ".backend_storage/cache")).expanduser().resolve()


def _cache_path(object_key: str, *, filename: str = "") -> Path:
    normalized_key = normalize_object_key(object_key)
    cache_root = _cache_root()
    digest = hashlib.sha256(normalized_key.encode("utf-8")).hexdigest()[:20]
    basename = Path(filename or normalized_key).name or "object.bin"
    return cache_root / digest / basename


def prune_materialization_cache(
    *,
    cache_root: str | Path | None = None,
    max_bytes: int | None = None,
    max_age_seconds: int | None = None,
    protected_paths: set[Path] | None = None,
    now: float | None = None,
) -> dict[str, int]:
    """Keep the disposable local object cache bounded and age-limited."""

    root = Path(cache_root or _cache_root()).expanduser().resolve()
    if not root.is_dir():
        return {"removed_files": 0, "removed_bytes": 0, "remaining_bytes": 0}
    byte_limit = max_bytes if max_bytes is not None else _positive_env_int(
        "OBJECT_STORAGE_CACHE_MAX_BYTES", _DEFAULT_CACHE_MAX_BYTES
    )
    age_limit = max_age_seconds if max_age_seconds is not None else _positive_env_int(
        "OBJECT_STORAGE_CACHE_MAX_AGE_SECONDS", _DEFAULT_CACHE_MAX_AGE_SECONDS
    )
    reference_time = time.time() if now is None else float(now)
    protected = {Path(path).resolve() for path in (protected_paths or set())}
    files: list[tuple[Path, int, float]] = []
    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        try:
            stat = candidate.stat()
        except OSError:
            continue
        files.append((candidate, int(stat.st_size), float(stat.st_mtime)))

    removed_files = 0
    removed_bytes = 0
    survivors: list[tuple[Path, int, float]] = []
    for candidate, size, modified_at in files:
        if candidate in protected or reference_time - modified_at <= age_limit:
            survivors.append((candidate, size, modified_at))
            continue
        try:
            candidate.unlink()
        except OSError:
            survivors.append((candidate, size, modified_at))
            continue
        removed_files += 1
        removed_bytes += size

    total_bytes = sum(size for _candidate, size, _modified_at in survivors)
    if total_bytes > byte_limit:
        for candidate, size, _modified_at in sorted(survivors, key=lambda item: item[2]):
            if total_bytes <= byte_limit or candidate in protected:
                continue
            try:
                candidate.unlink()
            except OSError:
                continue
            total_bytes -= size
            removed_files += 1
            removed_bytes += size

    return {
        "removed_files": removed_files,
        "removed_bytes": removed_bytes,
        "remaining_bytes": max(0, total_bytes),
    }


def materialize_object(storage: ObjectStorage, object_key: str, *, filename: str = "") -> Path:
    target = _cache_path(object_key, filename=filename)
    prune_materialization_cache(cache_root=target.parents[1], protected_paths={target})
    if target.is_file():
        return target.resolve()

    body = storage.get(object_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary_file:
            temporary_file.write(body)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(target)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    prune_materialization_cache(cache_root=target.parents[1], protected_paths={target})
    return target.resolve()


@dataclass
class ObjectMaterializationSession:
    """Request/run-scoped materialization cache for one storage backend."""

    storage: ObjectStorage
    _paths: dict[str, Path] = field(default_factory=dict)

    def materialize(self, object_key: str, *, filename: str = "") -> Path:
        normalized_key = normalize_object_key(object_key)
        cached = self._paths.get(normalized_key)
        if cached is not None and cached.is_file():
            return cached
        materialized = materialize_object(self.storage, normalized_key, filename=filename)
        self._paths[normalized_key] = materialized
        return materialized


def publish_file_artifacts(
    storage: ObjectStorage,
    *,
    run_id: str,
    artifacts: Iterable[ArtifactRecord],
) -> list[ArtifactRecord]:
    published: list[ArtifactRecord] = []
    for artifact in artifacts:
        source = Path(str(artifact.path or ""))
        if not source.is_file():
            published.append(artifact)
            continue

        body = source.read_bytes()
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        validate_object_download(content_type=content_type, size=len(body), filename=source.name)
        content_hash = hashlib.sha256(body).hexdigest()
        object_key = build_private_object_key(
            namespace="runs",
            owner_id=run_id,
            category=str(artifact.artifact_type or "artifacts"),
            object_id=f"{str(artifact.artifact_id or 'artifact')}-{content_hash[:16]}",
            filename=source.name,
        )
        stored = storage.put(
            object_key,
            body,
            content_type=content_type,
            metadata={
                "run_id": str(run_id),
                "artifact_id": str(artifact.artifact_id or ""),
                "artifact_type": str(artifact.artifact_type or ""),
                "content_sha256": content_hash,
                "file_name": source.name,
            },
        )
        artifact.metadata = {
            **dict(artifact.metadata or {}),
            "object_key": stored.key,
            "object_size": stored.size,
            "object_etag": stored.etag,
            "object_content_type": stored.content_type,
            "file_name": source.name,
        }
        published.append(artifact)
    return published
