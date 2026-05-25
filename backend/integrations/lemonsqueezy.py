from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping, Sequence

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


def _normalize_discount_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    attributes = dict(payload.get("attributes") or {})
    return {
        "discount_id": str(payload.get("id") or "").strip(),
        "name": str(attributes.get("name") or "").strip(),
        "code": str(attributes.get("code") or "").strip(),
        "amount": int(attributes.get("amount") or 0),
        "amount_type": str(attributes.get("amount_type") or "").strip(),
        "is_limited_to_products": bool(attributes.get("is_limited_to_products")),
        "is_limited_redemptions": bool(attributes.get("is_limited_redemptions")),
        "max_redemptions": int(attributes.get("max_redemptions") or 0),
        "starts_at": str(attributes.get("starts_at") or "").strip(),
        "expires_at": str(attributes.get("expires_at") or "").strip(),
        "duration": str(attributes.get("duration") or "").strip(),
        "duration_in_months": int(attributes.get("duration_in_months") or 0),
        "status": str(attributes.get("status") or "").strip(),
        "status_formatted": str(attributes.get("status_formatted") or "").strip(),
        "test_mode": bool(attributes.get("test_mode")),
        "created_at": str(attributes.get("created_at") or "").strip(),
        "updated_at": str(attributes.get("updated_at") or "").strip(),
    }


def list_discounts(
    *,
    store_id: str | int | None = None,
    page_number: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    query_params = {
        "page[number]": max(1, int(page_number)),
        "page[size]": max(1, int(page_size)),
    }
    normalized_store_id = str(store_id or require_env("LEMONSQUEEZY_STORE_ID")).strip()
    if normalized_store_id:
        query_params["filter[store_id]"] = normalized_store_id
    response = _lemonsqueezy_request(
        "GET",
        f"/discounts?{urllib.parse.urlencode(query_params)}",
    )
    items = response.get("data") or []
    page = ((response.get("meta") or {}).get("page") or {})
    return {
        "discounts": [
            _normalize_discount_payload(item)
            for item in items
            if isinstance(item, dict)
        ],
        "meta": {
            "current_page": int(page.get("currentPage") or page_number or 1),
            "per_page": int(page.get("perPage") or page_size or 0),
            "total": int(page.get("total") or 0),
            "last_page": int(page.get("lastPage") or 1),
        },
    }


def create_discount(
    *,
    name: str,
    code: str,
    amount: int,
    amount_type: str,
    starts_at: str = "",
    expires_at: str = "",
    max_redemptions: int = 0,
    duration: str = "once",
    duration_in_months: int = 1,
    variant_ids: Sequence[str | int] | None = None,
    test_mode: bool | None = None,
) -> dict[str, Any]:
    normalized_variant_ids = [str(item).strip() for item in (variant_ids or []) if str(item).strip()]
    payload = {
        "data": {
            "type": "discounts",
            "attributes": {
                "name": str(name or "").strip(),
                "code": str(code or "").strip(),
                "amount": int(amount or 0),
                "amount_type": str(amount_type or "").strip(),
                "is_limited_to_products": bool(normalized_variant_ids),
                "is_limited_redemptions": int(max_redemptions or 0) > 0,
                "max_redemptions": max(0, int(max_redemptions or 0)),
                "duration": str(duration or "once").strip() or "once",
                "duration_in_months": max(1, int(duration_in_months or 1)),
            },
            "relationships": {
                "store": {
                    "data": {
                        "type": "stores",
                        "id": str(require_env("LEMONSQUEEZY_STORE_ID")),
                    }
                },
            },
        }
    }
    if normalized_variant_ids:
        payload["data"]["relationships"]["variants"] = {
            "data": [
                {
                    "type": "variants",
                    "id": item,
                }
                for item in normalized_variant_ids
            ]
        }
    normalized_starts_at = str(starts_at or "").strip()
    if normalized_starts_at:
        payload["data"]["attributes"]["starts_at"] = normalized_starts_at
    normalized_expires_at = str(expires_at or "").strip()
    if normalized_expires_at:
        payload["data"]["attributes"]["expires_at"] = normalized_expires_at
    if test_mode is not None:
        payload["data"]["attributes"]["test_mode"] = bool(test_mode)
    response = _lemonsqueezy_request("POST", "/discounts", payload=payload)
    return _normalize_discount_payload(dict(response.get("data") or {}))


def delete_discount(discount_id: str | int) -> None:
    normalized_discount_id = urllib.parse.quote(str(discount_id or "").strip())
    if not normalized_discount_id:
        raise ValueError("discount_id is required")
    _lemonsqueezy_request("DELETE", f"/discounts/{normalized_discount_id}")


def get_checkout_url(
    user_id: str,
    variant_id: str | int,
    email: str,
    *,
    name: str = "",
    discount_code: str = "",
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
                "checkout_options": {
                    "discount": True,
                },
                "checkout_data": {
                    "email": str(email or "").strip(),
                    "name": str(name or "").strip(),
                    "discount_code": str(discount_code or "").strip(),
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
