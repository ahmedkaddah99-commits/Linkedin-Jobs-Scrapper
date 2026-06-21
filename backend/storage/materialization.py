from __future__ import annotations

import hashlib
import mimetypes
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from backend.domain.models import ArtifactRecord

from .base import ObjectStorage
from .keys import build_private_object_key, normalize_object_key


def _cache_path(object_key: str, *, filename: str = "") -> Path:
    normalized_key = normalize_object_key(object_key)
    cache_root = Path(os.getenv("OBJECT_STORAGE_CACHE_ROOT", ".backend_storage/cache"))
    digest = hashlib.sha256(normalized_key.encode("utf-8")).hexdigest()[:20]
    basename = Path(filename or normalized_key).name or "object.bin"
    return cache_root / digest / basename


def materialize_object(storage: ObjectStorage, object_key: str, *, filename: str = "") -> Path:
    target = _cache_path(object_key, filename=filename)
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

        object_key = build_private_object_key(
            namespace="runs",
            owner_id=run_id,
            category=str(artifact.artifact_type or "artifacts"),
            object_id=str(artifact.artifact_id or "artifact"),
            filename=source.name,
        )
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        stored = storage.put(
            object_key,
            source.read_bytes(),
            content_type=content_type,
            metadata={
                "run_id": str(run_id),
                "artifact_id": str(artifact.artifact_id or ""),
                "artifact_type": str(artifact.artifact_type or ""),
            },
        )
        artifact.metadata = {
            **dict(artifact.metadata or {}),
            "object_key": stored.key,
            "object_size": stored.size,
            "object_etag": stored.etag,
            "object_content_type": stored.content_type,
        }
        published.append(artifact)
    return published
