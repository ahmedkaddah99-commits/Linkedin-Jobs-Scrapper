from __future__ import annotations

import os
from typing import Any, Callable

from backend.domain.models import SECRET_PROVIDER_ENV, SECRET_PROVIDER_STORED, SecretRecord


SECRET_REF_PREFIX = "${secret:"
ENV_REF_PREFIX = "${env:"


def is_secret_reference(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(SECRET_REF_PREFIX) and value.endswith("}")


def is_env_reference(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(ENV_REF_PREFIX) and value.endswith("}")


def parse_secret_reference(value: str) -> tuple[str, str]:
    if is_secret_reference(value):
        return "secret", value[len(SECRET_REF_PREFIX) : -1].strip()
    if is_env_reference(value):
        return "env", value[len(ENV_REF_PREFIX) : -1].strip()
    return "", ""


def resolve_secret_record(secret: SecretRecord) -> str:
    if secret.provider == SECRET_PROVIDER_ENV:
        if not secret.env_var_name:
            raise KeyError(f"Secret '{secret.secret_id}' is missing env_var_name.")
        value = os.getenv(secret.env_var_name, "")
        if not value:
            raise KeyError(f"Environment secret '{secret.env_var_name}' is not set.")
        return value
    if secret.provider == SECRET_PROVIDER_STORED:
        if not secret.secret_value:
            raise KeyError(f"Secret '{secret.secret_id}' has no stored value.")
        return secret.secret_value
    raise ValueError(f"Unsupported secret provider: {secret.provider}")


def resolve_secret_references(value: Any, *, secret_lookup: Callable[[str], SecretRecord]) -> Any:
    if isinstance(value, dict):
        return {key: resolve_secret_references(item, secret_lookup=secret_lookup) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_secret_references(item, secret_lookup=secret_lookup) for item in value]
    if is_secret_reference(value):
        _, secret_id = parse_secret_reference(value)
        return resolve_secret_record(secret_lookup(secret_id))
    if is_env_reference(value):
        _, env_name = parse_secret_reference(value)
        resolved = os.getenv(env_name, "")
        if not resolved:
            raise KeyError(f"Environment secret '{env_name}' is not set.")
        return resolved
    return value
