from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from backend.config.env_schema import require_env
from backend.config.plans import DEFAULT_PLAN_ID, normalize_plan_id
from backend.domain.models import (
    TOKEN_SCOPE_ADMIN,
    TOKEN_SCOPE_ACQUISITION_AUDIT,
    TOKEN_SCOPE_ACQUISITION_COLLECT,
    TOKEN_SCOPE_ACQUISITION_DUPLICATES,
    TOKEN_SCOPE_ACQUISITION_ENRICH,
    TOKEN_SCOPE_ACQUISITION_OVERRIDE,
    TOKEN_SCOPE_ACQUISITION_PREVIEW,
    TOKEN_SCOPE_ACQUISITION_PROVIDERS,
    TOKEN_SCOPE_ACQUISITION_PUBLISH,
    TOKEN_SCOPE_ACQUISITION_REVIEW,
    TOKEN_SCOPE_ACQUISITION_ROLLBACK,
    TOKEN_SCOPE_ACQUISITION_VIEW,
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
)

_CLERK_API_BASE_URL = "https://api.clerk.com/v1"
_JWKS_CACHE_TTL_SECONDS = 300
_WEBHOOK_TOLERANCE_SECONDS = 300
_DEFAULT_HTTP_USER_AGENT = "runr-backend/0.1 (+https://127.0.0.1 local-dev)"
CLERK_JWT_TEMPLATE_NAME = "runr_backend"
# This must match the Clerk JWT Template name in the Clerk dashboard exactly.

_JWKS_CACHE: dict[str, Any] = {
    "fetched_at_by_url": {},
    "keys_by_url": {},
}

_USER_SCOPES = [
    TOKEN_SCOPE_WORKSPACES_READ,
    TOKEN_SCOPE_WORKSPACES_WRITE,
    TOKEN_SCOPE_TEMPLATES_READ,
    TOKEN_SCOPE_RUNS_READ,
    TOKEN_SCOPE_RUNS_WRITE,
    TOKEN_SCOPE_REVIEWS_READ,
    TOKEN_SCOPE_REVIEWS_WRITE,
    TOKEN_SCOPE_ARTIFACTS_READ,
    TOKEN_SCOPE_ARTIFACTS_WRITE,
]
_ADMIN_SCOPES = [
    TOKEN_SCOPE_ADMIN,
    TOKEN_SCOPE_ACQUISITION_AUDIT,
    TOKEN_SCOPE_ACQUISITION_COLLECT,
    TOKEN_SCOPE_ACQUISITION_DUPLICATES,
    TOKEN_SCOPE_ACQUISITION_ENRICH,
    TOKEN_SCOPE_ACQUISITION_OVERRIDE,
    TOKEN_SCOPE_ACQUISITION_PREVIEW,
    TOKEN_SCOPE_ACQUISITION_PROVIDERS,
    TOKEN_SCOPE_ACQUISITION_PUBLISH,
    TOKEN_SCOPE_ACQUISITION_REVIEW,
    TOKEN_SCOPE_ACQUISITION_ROLLBACK,
    TOKEN_SCOPE_ACQUISITION_VIEW,
    TOKEN_SCOPE_WORKSPACES_READ,
    TOKEN_SCOPE_WORKSPACES_WRITE,
    TOKEN_SCOPE_TEMPLATES_READ,
    TOKEN_SCOPE_TEMPLATES_WRITE,
    TOKEN_SCOPE_RUNS_READ,
    TOKEN_SCOPE_RUNS_WRITE,
    TOKEN_SCOPE_REVIEWS_READ,
    TOKEN_SCOPE_REVIEWS_WRITE,
    TOKEN_SCOPE_ARTIFACTS_READ,
    TOKEN_SCOPE_ARTIFACTS_WRITE,
    TOKEN_SCOPE_SECRETS_READ,
    TOKEN_SCOPE_SECRETS_WRITE,
    TOKEN_SCOPE_USERS_READ,
    TOKEN_SCOPE_USERS_WRITE,
    TOKEN_SCOPE_WORKER_EXECUTE,
]


@dataclass(slots=True)
class ClerkSessionClaims:
    clerk_user_id: str
    session_id: str = ""
    role: str = "user"
    plan_id: str = DEFAULT_PLAN_ID
    quota_overrides: dict[str, Any] = field(default_factory=dict)
    issued_at: str = ""
    expires_at: str = ""
    authorized_party: str = ""
    raw_claims: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SyntheticSessionToken:
    user_id: str
    scopes: list[str]
    auth_method: str
    token_id: str = ""
    name: str = "clerk-session"
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""
    last_used_at: str = ""
    expires_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "user_id": self.user_id,
            "name": self.name,
            "scopes": list(self.scopes),
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_used_at": self.last_used_at,
            "expires_at": self.expires_at,
            "metadata": dict(self.metadata),
            "auth_method": self.auth_method,
        }


def normalize_clerk_role(value: Any) -> str:
    return "admin" if str(value or "").strip().lower() == "admin" else "user"


def default_scopes_for_role(role: str) -> list[str]:
    return list(_ADMIN_SCOPES if normalize_clerk_role(role) == "admin" else _USER_SCOPES)


def build_synthetic_token(
    *,
    user_id: str,
    auth_method: str,
    role: str,
    session_id: str = "",
    expires_at: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> SyntheticSessionToken:
    now_iso = datetime.now(timezone.utc).isoformat()
    token_id = str(session_id or f"{auth_method}:{user_id}").strip() or f"{auth_method}:{user_id}"
    return SyntheticSessionToken(
        user_id=str(user_id or "").strip(),
        scopes=default_scopes_for_role(role),
        auth_method=str(auth_method or "clerk").strip() or "clerk",
        token_id=token_id,
        created_at=now_iso,
        updated_at=now_iso,
        last_used_at=now_iso,
        expires_at=str(expires_at or "").strip(),
        metadata=dict(metadata or {}),
    )


def _urlsafe_b64decode(value: str) -> bytes:
    normalized = str(value or "").strip()
    padding_length = (-len(normalized)) % 4
    return base64.urlsafe_b64decode(f"{normalized}{'=' * padding_length}")


def _decode_clerk_publishable_key_host(value: str) -> str:
    publishable_key = str(value or "").strip()
    if not publishable_key:
        return ""
    parts = publishable_key.split("_", 2)
    if len(parts) != 3:
        return ""
    try:
        decoded = _urlsafe_b64decode(parts[2]).decode("utf-8")
    except Exception:
        return ""
    return decoded.rstrip("$").strip().strip("/")


def _configured_clerk_issuer() -> str:
    configured = str(os.getenv("CLERK_ISSUER") or "").strip().rstrip("/")
    if configured:
        return configured
    publishable_host = _decode_clerk_publishable_key_host(os.getenv("CLERK_PUBLISHABLE_KEY") or "")
    if publishable_host:
        return f"https://{publishable_host}"
    return ""


def _jwks_url_for_issuer(issuer: str) -> str:
    normalized = str(issuer or "").strip().rstrip("/")
    if not normalized:
        raise RuntimeError("Missing Clerk issuer; cannot determine JWKS endpoint.")
    return f"{normalized}/.well-known/jwks.json"


def _json_request(
    method: str,
    url: str,
    *,
    payload: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    try:
        timeout_seconds = float(os.getenv("CLERK_HTTP_TIMEOUT_SECONDS", "5") or "5")
    except (TypeError, ValueError):
        timeout_seconds = 5.0
    timeout_seconds = min(10.0, max(1.0, timeout_seconds))
    encoded_body = None
    request_headers = {
        "Accept": "application/json",
        "User-Agent": _DEFAULT_HTTP_USER_AGENT,
    }
    if payload is not None:
        encoded_body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request_headers.update({str(key): str(value) for key, value in (headers or {}).items()})
    request = urllib.request.Request(
        url,
        data=encoded_body,
        headers=request_headers,
        method=str(method or "GET").upper(),
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Clerk API request failed ({exc.code}): {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Unable to reach Clerk API: {exc}") from exc
    return json.loads(response_body or "{}")


def _fetch_jwks(issuer: str, *, force: bool = False) -> dict[str, Any]:
    jwks_url = _jwks_url_for_issuer(issuer)
    now = time.time()
    keys_by_url = _JWKS_CACHE.get("keys_by_url") or {}
    fetched_at_by_url = _JWKS_CACHE.get("fetched_at_by_url") or {}
    cached_keys = keys_by_url.get(jwks_url) or {}
    fetched_at = float(fetched_at_by_url.get(jwks_url) or 0.0)
    if not force and cached_keys and now - fetched_at < _JWKS_CACHE_TTL_SECONDS:
        return dict(cached_keys)
    payload = _json_request("GET", jwks_url)
    keys_by_id = {
        str(item.get("kid") or "").strip(): dict(item)
        for item in payload.get("keys") or []
        if str(item.get("kid") or "").strip()
    }
    if not keys_by_id:
        raise RuntimeError("Clerk JWKS endpoint returned no signing keys.")
    keys_by_url[jwks_url] = keys_by_id
    fetched_at_by_url[jwks_url] = now
    _JWKS_CACHE["keys_by_url"] = keys_by_url
    _JWKS_CACHE["fetched_at_by_url"] = fetched_at_by_url
    return dict(keys_by_id)


def _public_key_from_jwk(jwk: Mapping[str, Any]):
    modulus = int.from_bytes(_urlsafe_b64decode(str(jwk.get("n") or "")), "big")
    exponent = int.from_bytes(_urlsafe_b64decode(str(jwk.get("e") or "")), "big")
    public_numbers = rsa.RSAPublicNumbers(exponent, modulus)
    return public_numbers.public_key()


def _extract_public_metadata(claims: Mapping[str, Any]) -> dict[str, Any]:
    candidate = claims.get("publicMetadata")
    if isinstance(candidate, Mapping):
        return dict(candidate)
    return {}


def _unix_timestamp_to_iso(value: Any) -> str:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _normalize_quota_overrides(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        if isinstance(parsed, Mapping):
            return {str(key): item for key, item in parsed.items()}
    return {}


def verify_session_token(
    token: str,
    *,
    allowed_authorized_parties: set[str] | None = None,
) -> ClerkSessionClaims:
    token_text = str(token or "").strip()
    segments = token_text.split(".")
    if len(segments) != 3:
        raise ValueError("The supplied token is not a JWT.")

    header = json.loads(_urlsafe_b64decode(segments[0]).decode("utf-8"))
    claims = json.loads(_urlsafe_b64decode(segments[1]).decode("utf-8"))
    signature = _urlsafe_b64decode(segments[2])

    algorithm = str(header.get("alg") or "").strip()
    if algorithm != "RS256":
        raise ValueError(f"Unsupported Clerk JWT algorithm: {algorithm or 'missing'}")

    key_id = str(header.get("kid") or "").strip()
    if not key_id:
        raise ValueError("Missing Clerk JWT key identifier.")

    configured_issuer = _configured_clerk_issuer()
    token_issuer = str(claims.get("iss") or "").strip().rstrip("/")
    if configured_issuer and token_issuer and token_issuer != configured_issuer:
        raise ValueError("Clerk session token issuer does not match the configured Clerk instance.")
    issuer = token_issuer or configured_issuer
    if not issuer:
        raise ValueError("Missing Clerk session token issuer.")

    jwks = _fetch_jwks(issuer)
    jwk = jwks.get(key_id)
    if jwk is None:
        jwks = _fetch_jwks(issuer, force=True)
        jwk = jwks.get(key_id)
    if jwk is None:
        raise ValueError(f"Unable to find Clerk JWKS key '{key_id}'.")

    public_key = _public_key_from_jwk(jwk)
    signed_payload = ".".join(segments[:2]).encode("utf-8")
    try:
        public_key.verify(signature, signed_payload, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature as exc:
        raise ValueError("Clerk session token signature verification failed.") from exc

    now = time.time()
    expires_at = float(claims.get("exp") or 0.0)
    if expires_at and now >= expires_at:
        raise ValueError("Clerk session token is expired.")
    not_before = float(claims.get("nbf") or 0.0)
    if not_before and now + 5 < not_before:
        raise ValueError("Clerk session token is not active yet.")

    authorized_party = str(claims.get("azp") or "").strip()
    if allowed_authorized_parties and authorized_party and authorized_party not in allowed_authorized_parties:
        raise ValueError("The Clerk session token authorized party is not allowed for this backend.")

    public_metadata = _extract_public_metadata(claims)
    return ClerkSessionClaims(
        clerk_user_id=str(claims.get("sub") or "").strip(),
        session_id=str(claims.get("sid") or "").strip(),
        role=normalize_clerk_role(public_metadata.get("role")),
        plan_id=normalize_plan_id(public_metadata.get("plan_id")),
        quota_overrides=_normalize_quota_overrides(public_metadata.get("quota_overrides")),
        issued_at=_unix_timestamp_to_iso(claims.get("iat")),
        expires_at=_unix_timestamp_to_iso(claims.get("exp")),
        authorized_party=authorized_party,
        raw_claims=dict(claims),
    )


def _clerk_api_request(
    method: str,
    path: str,
    *,
    payload: Mapping[str, Any] | None = None,
    query: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{_CLERK_API_BASE_URL}{path if str(path).startswith('/') else f'/{path}'}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query, doseq=True)}"
    return _json_request(
        method,
        url,
        payload=payload,
        headers={"Authorization": f"Bearer {require_env('CLERK_SECRET_KEY')}"},
    )


def get_user(clerk_user_id: str) -> dict[str, Any]:
    return _clerk_api_request("GET", f"/users/{urllib.parse.quote(str(clerk_user_id or '').strip())}")


def list_users(*, email_addresses: list[str] | None = None, external_ids: list[str] | None = None) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"limit": 100}
    if email_addresses:
        query["email_address"] = [item for item in email_addresses if str(item).strip()]
    if external_ids:
        query["external_id"] = [item for item in external_ids if str(item).strip()]
    payload = _clerk_api_request("GET", "/users", query=query)
    if isinstance(payload, Mapping):
        items = payload.get("data") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    return [dict(item) for item in items if isinstance(item, Mapping)]


def find_user_by_email(email_address: str) -> dict[str, Any] | None:
    normalized_email = str(email_address or "").strip()
    if not normalized_email:
        return None
    users = list_users(email_addresses=[normalized_email])
    return users[0] if users else None


def find_user_by_external_id(external_id: str) -> dict[str, Any] | None:
    normalized_external_id = str(external_id or "").strip()
    if not normalized_external_id:
        return None
    users = list_users(external_ids=[normalized_external_id])
    return users[0] if users else None


def update_user_metadata(
    clerk_user_id: str,
    *,
    public_metadata: Mapping[str, Any] | None = None,
    private_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if public_metadata is not None:
        payload["public_metadata"] = dict(public_metadata)
    if private_metadata is not None:
        payload["private_metadata"] = dict(private_metadata)
    return _clerk_api_request(
        "PATCH",
        f"/users/{urllib.parse.quote(str(clerk_user_id or '').strip())}/metadata",
        payload=payload,
    )


def create_user(
    *,
    email: str,
    display_name: str = "",
    external_id: str = "",
    public_metadata: Mapping[str, Any] | None = None,
    private_metadata: Mapping[str, Any] | None = None,
    created_at: str = "",
) -> dict[str, Any]:
    first_name, last_name = split_display_name(display_name)
    payload: dict[str, Any] = {
        "email_address": [str(email or "").strip()],
        "skip_password_requirement": True,
        "skip_legal_checks": True,
    }
    if first_name:
        payload["first_name"] = first_name
    if last_name:
        payload["last_name"] = last_name
    if external_id:
        payload["external_id"] = str(external_id).strip()
    if public_metadata is not None:
        payload["public_metadata"] = dict(public_metadata)
    if private_metadata is not None:
        payload["private_metadata"] = dict(private_metadata)
    if created_at:
        payload["created_at"] = str(created_at).strip()
    return _clerk_api_request("POST", "/users", payload=payload)


def split_display_name(display_name: str) -> tuple[str, str]:
    normalized = str(display_name or "").strip()
    if not normalized:
        return "", ""
    parts = normalized.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def get_primary_email_address(user_payload: Mapping[str, Any]) -> str:
    primary_email_id = str(user_payload.get("primary_email_address_id") or "").strip()
    for item in user_payload.get("email_addresses") or []:
        if not isinstance(item, Mapping):
            continue
        email_id = str(item.get("id") or "").strip()
        email_address = str(item.get("email_address") or item.get("emailAddress") or "").strip()
        if primary_email_id and email_id == primary_email_id and email_address:
            return email_address
        if email_address and not primary_email_id:
            return email_address
    return ""


def get_display_name(user_payload: Mapping[str, Any]) -> str:
    first_name = str(user_payload.get("first_name") or user_payload.get("firstName") or "").strip()
    last_name = str(user_payload.get("last_name") or user_payload.get("lastName") or "").strip()
    full_name = " ".join(part for part in (first_name, last_name) if part).strip()
    if full_name:
        return full_name
    return str(user_payload.get("username") or "").strip()


def get_signup_source(user_payload: Mapping[str, Any]) -> str:
    unsafe_metadata = user_payload.get("unsafe_metadata") or user_payload.get("unsafeMetadata") or {}
    if isinstance(unsafe_metadata, Mapping):
        source = str(unsafe_metadata.get("source") or "").strip()
        if source:
            return source
    for item in user_payload.get("external_accounts") or []:
        if not isinstance(item, Mapping):
            continue
        provider = str(item.get("provider") or item.get("provider_name") or "").strip()
        if provider:
            return provider
    return "clerk"


def verify_webhook(raw_body: bytes, headers: Mapping[str, Any], *, secret: str | None = None) -> dict[str, Any]:
    webhook_secret = str(secret or os.getenv("CLERK_WEBHOOK_SECRET") or "").strip()
    if not webhook_secret:
        raise RuntimeError("Missing CLERK_WEBHOOK_SECRET.")

    try:
        from svix.webhooks import Webhook
    except Exception:
        Webhook = None

    normalized_headers = {
        str(key).lower(): str(value)
        for key, value in dict(headers or {}).items()
        if value is not None
    }
    message_id = normalized_headers.get("svix-id", "")
    message_timestamp = normalized_headers.get("svix-timestamp", "")
    message_signature = normalized_headers.get("svix-signature", "")

    if Webhook is not None:
        verified = Webhook(webhook_secret).verify(
            raw_body.decode("utf-8"),
            {
                "svix-id": message_id,
                "svix-timestamp": message_timestamp,
                "svix-signature": message_signature,
            },
        )
        return dict(verified)

    if not message_id or not message_timestamp or not message_signature:
        raise ValueError("Missing Svix webhook verification headers.")

    try:
        timestamp_value = int(message_timestamp)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid Svix timestamp header.") from exc
    if abs(int(time.time()) - timestamp_value) > _WEBHOOK_TOLERANCE_SECONDS:
        raise ValueError("Svix webhook timestamp is outside the allowed verification window.")

    secret_payload = webhook_secret[6:] if webhook_secret.startswith("whsec_") else webhook_secret
    secret_bytes = base64.b64decode(secret_payload)
    signed_content = f"{message_id}.{message_timestamp}.{raw_body.decode('utf-8')}".encode("utf-8")
    expected_signature = base64.b64encode(hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()).decode(
        "utf-8"
    )
    provided_signatures = []
    for item in str(message_signature).split(" "):
        version, delimiter, signature_value = item.partition(",")
        if delimiter and version == "v1" and signature_value:
            provided_signatures.append(signature_value)
    if not any(hmac.compare_digest(expected_signature, signature_value) for signature_value in provided_signatures):
        raise ValueError("Invalid Svix webhook signature.")
    return json.loads(raw_body.decode("utf-8"))
