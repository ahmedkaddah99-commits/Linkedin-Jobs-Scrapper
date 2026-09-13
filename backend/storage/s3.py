from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from typing import Any

from .base import ObjectNotFoundError, ObjectStorageError, StoredObject
from .keys import normalize_object_key


def _create_s3_client(
    *,
    endpoint_url: str,
    access_key_id: str,
    secret_access_key: str,
    region: str,
):
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise RuntimeError(
            "S3ObjectStorage requires boto3 and botocore. Install the runtime object-storage dependency."
        ) from exc

    try:
        connect_timeout = max(1, int(os.getenv("S3_CONNECT_TIMEOUT_SECONDS", "3") or "3"))
    except (TypeError, ValueError):
        connect_timeout = 3
    try:
        read_timeout = max(1, int(os.getenv("S3_READ_TIMEOUT_SECONDS", "15") or "15"))
    except (TypeError, ValueError):
        read_timeout = 15
    try:
        max_attempts = max(1, int(os.getenv("S3_MAX_ATTEMPTS", "2") or "2"))
    except (TypeError, ValueError):
        max_attempts = 2

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=region,
        config=Config(
            signature_version="s3v4",
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            retries={"max_attempts": max_attempts, "mode": "standard"},
        ),
    )


def _is_missing_object_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, Mapping):
        return False
    error = response.get("Error")
    if not isinstance(error, Mapping):
        return False
    code = str(error.get("Code") or "").lower()
    return code in {"404", "nosuchkey", "notfound"}


class S3ObjectStorage:
    supports_direct_download = True

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        region: str = "auto",
        default_signed_url_ttl_seconds: int = 900,
        client: Any | None = None,
    ):
        required = {
            "bucket": bucket,
            "endpoint_url": endpoint_url,
            "access_key_id": access_key_id,
            "secret_access_key": secret_access_key,
        }
        missing = [name for name, value in required.items() if not str(value or "").strip()]
        if missing:
            raise ValueError("Missing S3 configuration: " + ", ".join(missing))
        if default_signed_url_ttl_seconds <= 0:
            raise ValueError("default_signed_url_ttl_seconds must be positive")

        self.bucket = bucket
        self.default_signed_url_ttl_seconds = default_signed_url_ttl_seconds
        self.client = client or _create_s3_client(
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            region=region,
        )

    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "",
        metadata: Mapping[str, str] | None = None,
    ) -> StoredObject:
        normalized_key = normalize_object_key(key)
        body = bytes(data)
        request: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": normalized_key,
            "Body": body,
        }
        if content_type:
            request["ContentType"] = content_type
        if metadata:
            request["Metadata"] = {str(name): str(value) for name, value in metadata.items()}

        try:
            response = self.client.put_object(**request)
        except Exception as exc:
            raise ObjectStorageError(f"Unable to store object: {normalized_key}") from exc

        etag = str((response or {}).get("ETag") or "").strip('"')
        return StoredObject(
            key=normalized_key,
            size=len(body),
            content_type=content_type,
            etag=etag or hashlib.sha256(body).hexdigest(),
        )

    def get(self, key: str) -> bytes:
        normalized_key = normalize_object_key(key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=normalized_key)
            return bytes(response["Body"].read())
        except Exception as exc:
            if _is_missing_object_error(exc):
                raise ObjectNotFoundError(f"Object does not exist: {normalized_key}") from exc
            raise ObjectStorageError(f"Unable to read object: {normalized_key}") from exc

    def delete(self, key: str) -> None:
        normalized_key = normalize_object_key(key)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=normalized_key)
        except Exception as exc:
            raise ObjectStorageError(f"Unable to delete object: {normalized_key}") from exc

    def exists(self, key: str) -> bool:
        normalized_key = normalize_object_key(key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=normalized_key)
            return True
        except Exception as exc:
            if _is_missing_object_error(exc):
                return False
            raise ObjectStorageError(f"Unable to inspect object: {normalized_key}") from exc

    def signed_download_url(
        self,
        key: str,
        *,
        expires_in_seconds: int | None = None,
        download_filename: str = "",
    ) -> str:
        normalized_key = normalize_object_key(key)
        ttl = self.default_signed_url_ttl_seconds if expires_in_seconds is None else expires_in_seconds
        if ttl <= 0:
            raise ValueError("expires_in_seconds must be positive")

        params = {"Bucket": self.bucket, "Key": normalized_key}
        safe_filename = str(download_filename or "").replace("\\", "/").rsplit("/", 1)[-1].replace('"', "")
        if safe_filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{safe_filename}"'

        try:
            return str(
                self.client.generate_presigned_url(
                    "get_object",
                    Params=params,
                    ExpiresIn=ttl,
                )
            )
        except Exception as exc:
            raise ObjectStorageError(f"Unable to sign object download: {normalized_key}") from exc
