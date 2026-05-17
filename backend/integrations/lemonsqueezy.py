from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping

from backend.config.env_schema import require_env
from backend.integrations.clerk import update_user_metadata

_LEMONSQUEEZY_API_BASE_URL = "https://api.lemonsqueezy.com/v1"


def verify_webhook_signature(raw_body: bytes, signature: str, *, secret: str | None = None) -> None:
    webhook_secret = str(secret or require_env("LEMONSQUEEZY_WEBHOOK_SECRET")).strip()
    provided_signature = str(signature or "").strip()
    if not webhook_secret:
        raise RuntimeError("Missing LEMONSQUEEZY_WEBHOOK_SECRET.")
    if not provided_signature:
        raise ValueError("Missing LemonSqueezy webhook signature.")
    digest = hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, provided_signature):
        raise ValueError("Invalid LemonSqueezy webhook signature.")


def _lemonsqueezy_request(method: str, path: str, *, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    url = f"{_LEMONSQUEEZY_API_BASE_URL}{path if str(path).startswith('/') else f'/{path}'}"
    request_headers = {
        "Accept": "application/vnd.api+json",
        "Authorization": f"Bearer {require_env('LEMONSQUEEZY_API_KEY')}",
    }
    encoded_body = None
    if payload is not None:
        encoded_body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/vnd.api+json"
    request = urllib.request.Request(
        url,
        data=encoded_body,
        headers=request_headers,
        method=str(method or "GET").upper(),
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LemonSqueezy API request failed ({exc.code}): {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Unable to reach LemonSqueezy API: {exc}") from exc
    return json.loads(response_body or "{}")


def update_user_plan_in_clerk(
    clerk_user_id: str,
    plan_id: str,
    *,
    quota_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return update_user_metadata(
        clerk_user_id,
        public_metadata={
            "plan_id": str(plan_id or "").strip(),
            "quota_overrides": dict(quota_overrides or {}),
        },
    )


def get_checkout_url(
    user_id: str,
    variant_id: str | int,
    email: str,
    *,
    name: str = "",
    custom_data: Mapping[str, Any] | None = None,
    redirect_url: str = "",
) -> str:
    normalized_variant_id = str(variant_id or "").strip()
    if not normalized_variant_id:
        raise ValueError("LemonSqueezy variant_id is required to create a checkout.")

    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "product_options": {
                    "enabled_variants": [int(normalized_variant_id)],
                    "redirect_url": str(redirect_url or "").strip(),
                },
                "checkout_data": {
                    "email": str(email or "").strip(),
                    "name": str(name or "").strip(),
                    "custom": {
                        "user_id": str(user_id or "").strip(),
                        **dict(custom_data or {}),
                    },
                },
            },
            "relationships": {
                "store": {
                    "data": {
                        "type": "stores",
                        "id": str(require_env("LEMONSQUEEZY_STORE_ID")),
                    }
                },
                "variant": {
                    "data": {
                        "type": "variants",
                        "id": normalized_variant_id,
                    }
                },
            },
        }
    }
    response = _lemonsqueezy_request("POST", "/checkouts", payload=payload)
    checkout_url = str(
        (((response.get("data") or {}).get("attributes") or {}).get("url") or "")
    ).strip()
    if not checkout_url:
        raise RuntimeError("LemonSqueezy checkout creation succeeded without returning a checkout URL.")
    return checkout_url


def retrieve_subscription(lemonsqueezy_subscription_id: str) -> dict[str, Any]:
    normalized_subscription_id = urllib.parse.quote(str(lemonsqueezy_subscription_id or "").strip())
    return _lemonsqueezy_request("GET", f"/subscriptions/{normalized_subscription_id}")


def retrieve_customer(lemonsqueezy_customer_id: str) -> dict[str, Any]:
    normalized_customer_id = urllib.parse.quote(str(lemonsqueezy_customer_id or "").strip())
    return _lemonsqueezy_request("GET", f"/customers/{normalized_customer_id}")


def get_customer_portal_url(
    *,
    subscription_id: str = "",
    customer_id: str = "",
) -> str:
    if subscription_id:
        response = retrieve_subscription(subscription_id)
        portal_url = str(
            ((((response.get("data") or {}).get("attributes") or {}).get("urls") or {}).get("customer_portal") or "")
        ).strip()
        if portal_url:
            return portal_url
    if customer_id:
        response = retrieve_customer(customer_id)
        portal_url = str(
            ((((response.get("data") or {}).get("attributes") or {}).get("urls") or {}).get("customer_portal") or "")
        ).strip()
        if portal_url:
            return portal_url
    raise ValueError("No signed LemonSqueezy customer portal URL is available for this user.")
