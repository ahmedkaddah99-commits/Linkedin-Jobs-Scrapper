from __future__ import annotations

import hmac
from datetime import datetime, timezone
from hashlib import pbkdf2_hmac
from secrets import token_urlsafe

from backend.domain.models import (
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_REVIEWER,
    ROLE_VIEWER,
    TOKEN_SCOPE_ADMIN,
    TOKEN_SCOPE_ARTIFACTS_READ,
    TOKEN_SCOPE_ARTIFACTS_WRITE,
    TOKEN_SCOPE_REVIEWS_READ,
    TOKEN_SCOPE_REVIEWS_WRITE,
    TOKEN_SCOPE_RUNS_READ,
    TOKEN_SCOPE_RUNS_WRITE,
    TOKEN_SCOPE_SECRETS_READ,
    TOKEN_SCOPE_SECRETS_WRITE,
    TOKEN_SCOPE_TEMPLATES_READ,
    TOKEN_SCOPE_TEMPLATES_WRITE,
    TOKEN_SCOPE_USERS_READ,
    TOKEN_SCOPE_USERS_WRITE,
    TOKEN_SCOPE_WORKER_EXECUTE,
    TOKEN_SCOPE_WORKSPACES_READ,
    TOKEN_SCOPE_WORKSPACES_WRITE,
    ApiTokenRecord,
)


PBKDF2_ITERATIONS = 120_000

ROLE_DEFAULT_SCOPES = {
    ROLE_ADMIN: {
        TOKEN_SCOPE_ADMIN,
        TOKEN_SCOPE_WORKSPACES_READ,
        TOKEN_SCOPE_WORKSPACES_WRITE,
        TOKEN_SCOPE_TEMPLATES_READ,
        TOKEN_SCOPE_TEMPLATES_WRITE,
        TOKEN_SCOPE_RUNS_READ,
        TOKEN_SCOPE_RUNS_WRITE,
        TOKEN_SCOPE_WORKER_EXECUTE,
        TOKEN_SCOPE_REVIEWS_READ,
        TOKEN_SCOPE_REVIEWS_WRITE,
        TOKEN_SCOPE_ARTIFACTS_READ,
        TOKEN_SCOPE_ARTIFACTS_WRITE,
        TOKEN_SCOPE_SECRETS_READ,
        TOKEN_SCOPE_SECRETS_WRITE,
        TOKEN_SCOPE_USERS_READ,
        TOKEN_SCOPE_USERS_WRITE,
    },
    ROLE_EDITOR: {
        TOKEN_SCOPE_WORKSPACES_READ,
        TOKEN_SCOPE_WORKSPACES_WRITE,
        TOKEN_SCOPE_TEMPLATES_READ,
        TOKEN_SCOPE_RUNS_READ,
        TOKEN_SCOPE_RUNS_WRITE,
        TOKEN_SCOPE_REVIEWS_READ,
        TOKEN_SCOPE_REVIEWS_WRITE,
        TOKEN_SCOPE_ARTIFACTS_READ,
        TOKEN_SCOPE_ARTIFACTS_WRITE,
        TOKEN_SCOPE_SECRETS_READ,
    },
    ROLE_REVIEWER: {
        TOKEN_SCOPE_WORKSPACES_READ,
        TOKEN_SCOPE_TEMPLATES_READ,
        TOKEN_SCOPE_RUNS_READ,
        TOKEN_SCOPE_REVIEWS_READ,
        TOKEN_SCOPE_REVIEWS_WRITE,
        TOKEN_SCOPE_ARTIFACTS_READ,
    },
    ROLE_VIEWER: {
        TOKEN_SCOPE_WORKSPACES_READ,
        TOKEN_SCOPE_TEMPLATES_READ,
        TOKEN_SCOPE_RUNS_READ,
        TOKEN_SCOPE_REVIEWS_READ,
        TOKEN_SCOPE_ARTIFACTS_READ,
    },
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_token_value(raw_token: str, *, salt: bytes | None = None) -> str:
    effective_salt = salt or token_urlsafe(16).encode("utf-8")[:16]
    digest = pbkdf2_hmac("sha256", raw_token.encode("utf-8"), effective_salt, PBKDF2_ITERATIONS)
    return f"{PBKDF2_ITERATIONS}${effective_salt.hex()}${digest.hex()}"


def verify_token_value(raw_token: str, token_hash: str) -> bool:
    try:
        iterations_text, salt_hex, digest_hex = token_hash.split("$", 2)
        expected = pbkdf2_hmac(
            "sha256",
            raw_token.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations_text),
        )
    except Exception:
        return False
    return hmac.compare_digest(expected.hex(), digest_hex)


def build_token_scope_set(user_role: str, explicit_scopes: list[str] | None = None) -> list[str]:
    scopes = set(ROLE_DEFAULT_SCOPES.get(str(user_role or ROLE_VIEWER), set()))
    scopes.update(str(item).strip() for item in (explicit_scopes or []) if str(item).strip())
    return sorted(scopes)


def issue_api_token(
    *,
    user_id: str,
    token_name: str,
    user_role: str,
    scopes: list[str] | None = None,
    expires_at: str = "",
    metadata: dict | None = None,
) -> tuple[ApiTokenRecord, str]:
    raw_token = f"bkat_{token_urlsafe(32)}"
    token_prefix = raw_token[:14]
    record = ApiTokenRecord.create(
        user_id=user_id,
        name=token_name,
        token_prefix=token_prefix,
        token_hash=hash_token_value(raw_token),
        scopes=build_token_scope_set(user_role, scopes),
        expires_at=expires_at,
        metadata=metadata or {},
    )
    return record, raw_token


def token_is_expired(expires_at: str) -> bool:
    if not str(expires_at).strip():
        return False
    try:
        expires = datetime.fromisoformat(expires_at)
    except Exception:
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires <= utc_now()


def token_has_scope(scopes: list[str], required_scope: str) -> bool:
    scope_set = {str(item).strip() for item in scopes if str(item).strip()}
    return TOKEN_SCOPE_ADMIN in scope_set or required_scope in scope_set
