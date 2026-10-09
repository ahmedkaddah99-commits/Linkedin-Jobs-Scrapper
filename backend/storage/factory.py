from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from backend.config.env_schema import read_environment_settings, validate_environment

from .base import ObjectStorage
from .local import LocalObjectStorage
from .s3 import S3ObjectStorage


def create_object_storage(
    environ: Mapping[str, str] | None = None,
    *,
    s3_client: Any | None = None,
    clock: Callable[[], float] | None = None,
) -> ObjectStorage:
    settings = validate_environment(environ)

    if settings.object_storage_backend == "local":
        kwargs: dict[str, Any] = {}
        if clock is not None:
            kwargs["clock"] = clock
        return LocalObjectStorage(
            settings.object_storage_local_root,
            download_base_url=settings.local_object_storage_base_url,
            signing_secret=settings.local_object_storage_signing_secret or "runr-local-development-only",
            default_signed_url_ttl_seconds=settings.s3_signed_url_ttl_seconds,
            **kwargs,
        )

    return S3ObjectStorage(
        bucket=settings.s3_bucket,
        endpoint_url=settings.s3_endpoint_url,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key,
        region=settings.s3_region,
        default_signed_url_ttl_seconds=settings.s3_signed_url_ttl_seconds,
        client=s3_client,
    )
