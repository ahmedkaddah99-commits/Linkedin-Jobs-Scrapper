from __future__ import annotations

import hashlib
import hmac
import os
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from urllib.parse import quote, urlencode

from .base import InvalidObjectKeyError, ObjectNotFoundError, StoredObject
from .keys import normalize_object_key


_OBJECT_DIGEST_HEX_LENGTH = 32


class LocalObjectStorage:
    def __init__(
        self,
        root: str | Path,
        *,
        download_base_url: str = "http://127.0.0.1:8000/v1/storage/objects",
        signing_secret: str = "runr-local-development-only",
        default_signed_url_ttl_seconds: int = 900,
        clock: Callable[[], float] = time.time,
    ):
        if default_signed_url_ttl_seconds <= 0:
            raise ValueError("default_signed_url_ttl_seconds must be positive")
        if not signing_secret:
            raise ValueError("signing_secret must not be empty")
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.download_base_url = download_base_url.rstrip("/")
        self.signing_secret = signing_secret.encode("utf-8")
        self.default_signed_url_ttl_seconds = default_signed_url_ttl_seconds
        self._clock = clock

    def _path_for(self, key: str) -> tuple[str, Path]:
        normalized_key = normalize_object_key(key)
        digest = hashlib.sha256(normalized_key.encode("utf-8")).hexdigest()
        path = (self.root / digest[:2] / digest[2:4] / digest[4:_OBJECT_DIGEST_HEX_LENGTH]).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise InvalidObjectKeyError("Object key resolves outside the storage root") from exc
        return normalized_key, path

    def _legacy_digest_path_for(self, normalized_key: str) -> Path:
        digest = hashlib.sha256(normalized_key.encode("utf-8")).hexdigest()
        return (self.root / digest[:2] / digest[2:4] / digest).resolve()

    def _legacy_path_for(self, normalized_key: str) -> Path:
        return (self.root / Path(*normalized_key.split("/"))).resolve()

    def _existing_path_for(self, normalized_key: str, path: Path) -> Path:
        if path.is_file():
            return path
        for legacy_path in (self._legacy_digest_path_for(normalized_key), self._legacy_path_for(normalized_key)):
            try:
                legacy_path.relative_to(self.root)
            except ValueError as exc:
                raise InvalidObjectKeyError("Object key resolves outside the storage root") from exc
            if legacy_path.is_file():
                return legacy_path
        return path

    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "",
        metadata: Mapping[str, str] | None = None,
    ) -> StoredObject:
        del metadata
        normalized_key, path = self._path_for(key)
        body = bytes(data)
        path.parent.mkdir(parents=True, exist_ok=True)

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary_file:
                temporary_file.write(body)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
                temporary_path = Path(temporary_file.name)
            temporary_path.replace(path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

        return StoredObject(
            key=normalized_key,
            size=len(body),
            content_type=content_type,
            etag=hashlib.sha256(body).hexdigest(),
        )

    def get(self, key: str) -> bytes:
        normalized_key, path = self._path_for(key)
        path = self._existing_path_for(normalized_key, path)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(f"Object does not exist: {normalized_key}") from exc

    def delete(self, key: str) -> None:
        normalized_key, path = self._path_for(key)
        paths = [path, self._legacy_digest_path_for(normalized_key), self._legacy_path_for(normalized_key)]
        for candidate in paths:
            try:
                candidate.unlink()
            except FileNotFoundError:
                continue

    def exists(self, key: str) -> bool:
        normalized_key, path = self._path_for(key)
        path = self._existing_path_for(normalized_key, path)
        return path.is_file()

    def signed_download_url(
        self,
        key: str,
        *,
        expires_in_seconds: int | None = None,
        download_filename: str = "",
    ) -> str:
        normalized_key, path = self._path_for(key)
        path = self._existing_path_for(normalized_key, path)
        if not path.is_file():
            raise ObjectNotFoundError(f"Object does not exist: {normalized_key}")

        ttl = self.default_signed_url_ttl_seconds if expires_in_seconds is None else expires_in_seconds
        if ttl <= 0:
            raise ValueError("expires_in_seconds must be positive")
        expires_at = int(self._clock()) + ttl
        safe_filename = str(download_filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        payload = f"{normalized_key}\n{expires_at}\n{safe_filename}".encode("utf-8")
        signature = hmac.new(self.signing_secret, payload, hashlib.sha256).hexdigest()
        query = {"expires": str(expires_at), "signature": signature}
        if safe_filename:
            query["download"] = safe_filename
        encoded_key = quote(normalized_key, safe="/")
        return f"{self.download_base_url}/{encoded_key}?{urlencode(query)}"
