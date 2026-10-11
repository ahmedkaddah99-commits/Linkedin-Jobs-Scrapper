from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable


class ObjectStorageError(RuntimeError):
    pass


class ObjectNotFoundError(ObjectStorageError):
    pass


class InvalidObjectKeyError(ObjectStorageError, ValueError):
    pass


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    content_type: str = ""
    etag: str = ""


@runtime_checkable
class ObjectStorage(Protocol):
    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "",
        metadata: Mapping[str, str] | None = None,
    ) -> StoredObject: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...

    def signed_download_url(
        self,
        key: str,
        *,
        expires_in_seconds: int | None = None,
        download_filename: str = "",
    ) -> str: ...
