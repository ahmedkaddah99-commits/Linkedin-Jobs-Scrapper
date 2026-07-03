from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

CLERK_SESSION_TOKEN_TEMPLATE_HINT = {
    "publicMetadata": {
        "role": "{{user.public_metadata.role}}",
        "plan_id": "{{user.public_metadata.plan_id}}",
        "quota_overrides": "{{user.public_metadata.quota_overrides}}",
    }
}

ENV_SCHEMA: dict[str, dict[str, Any]] = {
    "RUNR_ENV": {
        "required": False,
        "scope": "backend",
        "default": "development",
        "description": "Runtime environment: development, test, staging, or production.",
    },
    "DATABASE_BACKEND": {
        "required": False,
        "scope": "backend",
        "default": "sqlite",
        "description": "Database backend. Local development defaults to sqlite; production must use turso.",
    },
    "TURSO_DATABASE_URL": {
        "required": False,
        "scope": "backend",
        "description": "Turso/libSQL database URL. Required in production.",
    },
    "TURSO_AUTH_TOKEN": {
        "required": False,
        "scope": "backend",
        "description": "Turso authentication token. Required in production.",
    },
    "OBJECT_STORAGE_BACKEND": {
        "required": False,
        "scope": "backend",
        "default": "local",
        "description": "Object storage backend: local, s3, or r2. Production must use s3 or r2.",
    },
    "OBJECT_STORAGE_LOCAL_ROOT": {
        "required": False,
        "scope": "backend",
        "default": ".backend_storage/objects",
        "description": "Filesystem root for local-development object storage.",
    },
    "OBJECT_STORAGE_CACHE_ROOT": {
        "required": False,
        "scope": "backend",
        "default": ".backend_storage/cache",
        "description": "Ephemeral cache used when cloud objects must be materialized as local files.",
    },
    "LOCAL_OBJECT_STORAGE_BASE_URL": {
        "required": False,
        "scope": "backend",
        "default": "http://127.0.0.1:8000/v1/storage/objects",
        "description": "Base URL used to create signed local-development download URLs.",
    },
    "LOCAL_OBJECT_STORAGE_SIGNING_SECRET": {
        "required": False,
        "scope": "backend",
        "description": "Development-only HMAC secret used for local signed download URLs.",
    },
    "S3_ENDPOINT_URL": {
        "required": False,
        "scope": "backend",
        "description": "S3-compatible endpoint URL, including the Cloudflare R2 account endpoint.",
    },
    "S3_ACCESS_KEY_ID": {
        "required": False,
        "scope": "backend",
        "description": "S3-compatible access key ID.",
    },
    "S3_SECRET_ACCESS_KEY": {
        "required": False,
        "scope": "backend",
        "description": "S3-compatible secret access key.",
    },
    "S3_BUCKET": {
        "required": False,
        "scope": "backend",
        "description": "Private S3-compatible bucket name.",
    },
    "S3_REGION": {
        "required": False,
        "scope": "backend",
        "default": "auto",
        "description": "S3-compatible region. Cloudflare R2 uses auto.",
    },
    "S3_SIGNED_URL_TTL_SECONDS": {
        "required": False,
        "scope": "backend",
        "default": "900",
        "description": "Default lifetime for signed object-download URLs.",
    },
    "CLERK_SECRET_KEY": {
        "required": True,
        "scope": "backend",
        "description": "Clerk Backend API secret key.",
    },
    "CLERK_PUBLISHABLE_KEY": {
        "required": True,
        "scope": "shared",
        "description": "Clerk publishable key used by the frontend and deployment config.",
    },
    "CLERK_WEBHOOK_SECRET": {
        "required": True,
        "scope": "backend",
        "description": "Clerk Svix webhook signing secret.",
    },
    "CREEM_API_KEY": {
        "required": True,
        "scope": "backend",
        "description": "Creem API key used for checkout, portal, and discount calls.",
    },
    "CREEM_WEBHOOK_SECRET": {
        "required": True,
        "scope": "backend",
        "description": "Creem webhook signing secret.",
    },
    "CREEM_API_BASE_URL": {
        "required": False,
        "scope": "backend",
        "description": "Optional Creem API base URL override. Test keys otherwise use https://test-api.creem.io/v1 automatically.",
    },
    "CREEM_LAUNCH_PRODUCT_ID": {
        "required": False,
        "scope": "backend",
        "description": "Creem product id for the Launch plan.",
    },
    "CREEM_MOMENTUM_PRODUCT_ID": {
        "required": False,
        "scope": "backend",
        "description": "Creem product id for the Momentum plan.",
    },
    "CREEM_SCALE_PRODUCT_ID": {
        "required": False,
        "scope": "backend",
        "description": "Creem product id for the Scale plan.",
    },
    "APP_FRONTEND_ORIGIN": {
        "required": False,
        "scope": "backend",
        "description": "Public frontend origin used for external checkout success redirects, for example https://app.userunr.com.",
    },
    "RENDER_FRONTEND_EXTERNAL_HOSTNAME": {
        "required": False,
        "scope": "backend",
        "description": "Render-provided frontend hostname allowed by the API for Blueprint preview environments.",
    },
    "VITE_CLERK_PUBLISHABLE_KEY": {
        "required": True,
        "scope": "frontend",
        "description": "Frontend Clerk publishable key exposed to Vite.",
    },
    "VITE_API_EXTERNAL_HOSTNAME": {
        "required": False,
        "scope": "frontend",
        "description": "Render-provided API hostname used by the frontend to derive preview API URLs.",
    },
    "RUNR_ENABLE_LIVE_NETWORKING_DISCOVERY": {
        "required": False,
        "scope": "backend",
        "description": "Optional opt-in for live DuckDuckGo and DeepSeek target-contact discovery. Disabled by default for deterministic local/test behavior.",
    },
    "RUNR_DISABLE_QUOTAS": {
        "required": False,
        "scope": "backend",
        "description": "Optional local-development switch that bypasses quota enforcement when set to 1/true/yes/on.",
    },
}


class EnvironmentValidationError(RuntimeError):
    def __init__(self, errors: list[str] | tuple[str, ...]):
        self.errors = tuple(errors)
        super().__init__("Invalid environment configuration: " + "; ".join(self.errors))


@dataclass(frozen=True)
class EnvironmentSettings:
    runr_env: str
    database_backend: str
    turso_database_url: str
    turso_auth_token: str
    object_storage_backend: str
    object_storage_local_root: str
    local_object_storage_base_url: str
    local_object_storage_signing_secret: str
    s3_endpoint_url: str
    s3_access_key_id: str
    s3_secret_access_key: str
    s3_bucket: str
    s3_region: str
    s3_signed_url_ttl_seconds: int

    @property
    def is_production(self) -> bool:
        return self.runr_env in {"prod", "production"}


def _mapping_value(environ: Mapping[str, str], name: str, default: str = "") -> str:
    return str(environ.get(name, default) or default).strip()


def get_env(name: str, default: str = "") -> str:
    return _mapping_value(os.environ, name, default)


def require_env(name: str) -> str:
    value = get_env(name)
    if value:
        return value
    raise RuntimeError(f"Missing required environment variable: {name}")


def get_missing_required_env() -> list[str]:
    return [name for name, descriptor in ENV_SCHEMA.items() if descriptor.get("required") and not get_env(name)]


def describe_env_schema() -> dict[str, dict[str, Any]]:
    return {
        name: {
            **descriptor,
            "value_present": bool(get_env(name)),
        }
        for name, descriptor in ENV_SCHEMA.items()
    }


def read_environment_settings(environ: Mapping[str, str] | None = None) -> EnvironmentSettings:
    source = os.environ if environ is None else environ

    ttl_raw = _mapping_value(source, "S3_SIGNED_URL_TTL_SECONDS", "900")
    try:
        ttl_seconds = int(ttl_raw)
    except (TypeError, ValueError):
        ttl_seconds = 0

    return EnvironmentSettings(
        runr_env=_mapping_value(source, "RUNR_ENV", "development").lower(),
        database_backend=_mapping_value(source, "DATABASE_BACKEND", "sqlite").lower(),
        turso_database_url=_mapping_value(source, "TURSO_DATABASE_URL"),
        turso_auth_token=_mapping_value(source, "TURSO_AUTH_TOKEN"),
        object_storage_backend=_mapping_value(source, "OBJECT_STORAGE_BACKEND", "local").lower(),
        object_storage_local_root=_mapping_value(
            source,
            "OBJECT_STORAGE_LOCAL_ROOT",
            ".backend_storage/objects",
        ),
        local_object_storage_base_url=_mapping_value(
            source,
            "LOCAL_OBJECT_STORAGE_BASE_URL",
            "http://127.0.0.1:8000/v1/storage/objects",
        ),
        local_object_storage_signing_secret=_mapping_value(
            source,
            "LOCAL_OBJECT_STORAGE_SIGNING_SECRET",
        ),
        s3_endpoint_url=_mapping_value(source, "S3_ENDPOINT_URL"),
        s3_access_key_id=_mapping_value(source, "S3_ACCESS_KEY_ID"),
        s3_secret_access_key=_mapping_value(source, "S3_SECRET_ACCESS_KEY"),
        s3_bucket=_mapping_value(source, "S3_BUCKET"),
        s3_region=_mapping_value(source, "S3_REGION", "auto"),
        s3_signed_url_ttl_seconds=ttl_seconds,
    )


def get_environment_validation_errors(
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    settings = read_environment_settings(environ)
    errors: list[str] = []

    if settings.runr_env not in {"dev", "development", "test", "staging", "prod", "production"}:
        errors.append("RUNR_ENV must be development, test, staging, or production")
    if settings.database_backend not in {"sqlite", "turso"}:
        errors.append("DATABASE_BACKEND must be 'sqlite' or 'turso'")
    if settings.object_storage_backend not in {"local", "s3", "r2"}:
        errors.append("OBJECT_STORAGE_BACKEND must be 'local', 's3', or 'r2'")
    if settings.s3_signed_url_ttl_seconds <= 0:
        errors.append("S3_SIGNED_URL_TTL_SECONDS must be a positive integer")

    if settings.database_backend == "turso" or settings.is_production:
        if not settings.turso_database_url:
            errors.append("TURSO_DATABASE_URL is required for Turso and production")
        if not settings.turso_auth_token:
            errors.append("TURSO_AUTH_TOKEN is required for Turso and production")

    if settings.object_storage_backend in {"s3", "r2"} or settings.is_production:
        required_storage_values = {
            "S3_ENDPOINT_URL": settings.s3_endpoint_url,
            "S3_ACCESS_KEY_ID": settings.s3_access_key_id,
            "S3_SECRET_ACCESS_KEY": settings.s3_secret_access_key,
            "S3_BUCKET": settings.s3_bucket,
        }
        errors.extend(
            f"{name} is required for S3-compatible and production object storage"
            for name, value in required_storage_values.items()
            if not value
        )

    if settings.is_production:
        if settings.database_backend != "turso":
            errors.append("Production requires DATABASE_BACKEND=turso")
        if settings.object_storage_backend not in {"s3", "r2"}:
            errors.append("Production requires OBJECT_STORAGE_BACKEND=s3 or r2")

    return errors


def validate_environment(environ: Mapping[str, str] | None = None) -> EnvironmentSettings:
    errors = get_environment_validation_errors(environ)
    if errors:
        raise EnvironmentValidationError(errors)
    return read_environment_settings(environ)
