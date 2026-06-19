from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping, Sequence
from uuid import uuid4

from backend.config.env_schema import require_env
from backend.integrations.clerk import update_user_metadata

_CREEM_API_BASE_URL = "https://api.creem.io/v1"
_CREEM_TEST_API_BASE_URL = "https://test-api.creem.io/v1"


def _creem_api_base_url(api_key: str) -> str:
    configured_base_url = str(os.getenv("CREEM_API_BASE_URL") or "").strip().rstrip("/")
    if configured_base_url:
        return configured_base_url
    if str(api_key or "").startswith("creem_test_"):
        return _CREEM_TEST_API_BASE_URL
    return _CREEM_API_BASE_URL


def verify_webhook_signature(raw_body: bytes, signature: str, *, secret: str | None = None) -> None:
    webhook_secret = str(secret or require_env("CREEM_WEBHOOK_SECRET")).strip()
    provided_signature = str(signature or "").strip()
    if not webhook_secret:
        raise RuntimeError("Missing CREEM_WEBHOOK_SECRET.")
    if not provided_signature:
        raise ValueError("Missing Creem webhook signature.")
    digest = hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, provided_signature):
        raise ValueError("Invalid Creem webhook signature.")


def _creem_request(method: str, path: str, *, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    api_key = require_env("CREEM_API_KEY")
    url = f"{_creem_api_base_url(api_key)}{path if str(path).startswith('/') else f'/{path}'}"
    request_headers = {
        "Accept": "application/json",
        "x-api-key": api_key,
    }
    encoded_body = None
    if payload is not None:
        encoded_body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
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
        raise RuntimeError(f"Creem API request failed ({exc.code}): {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Unable to reach Creem API: {exc}") from exc
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


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first_text(payload: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if value is not None:
            return str(value or "").strip()
    return ""


def _first_int(payload: Mapping[str, Any], *names: str) -> int:
    for name in names:
        value = payload.get(name)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _response_items(response: Mapping[str, Any]) -> list[Any]:
    for key in ("data", "items", "discounts", "results"):
        value = response.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, Mapping):
            nested_items = _response_items(value)
            if nested_items:
                return nested_items
    return []


def _normalize_discount_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    source = _as_dict(payload.get("data")) or dict(payload)
    item = _as_dict(source.get("attributes")) or source
    discount_type = _first_text(item, "type", "amount_type").lower()
    amount_type = "percent" if discount_type in {"percentage", "percent"} else "fixed"
    amount = _first_int(item, "percentage", "percent_off") if amount_type == "percent" else _first_int(item, "amount")
    status = _first_text(item, "status") or ("active" if not _first_text(item, "deleted_at") else "deleted")
    return {
        "discount_id": _first_text(item, "id", "discount_id") or _first_text(source, "id", "discount_id"),
        "name": _first_text(item, "name"),
        "code": _first_text(item, "code", "discount_code"),
        "amount": amount,
        "amount_type": amount_type,
        "is_limited_to_products": bool(item.get("applies_to_products") or item.get("appliesToProducts")),
        "is_limited_redemptions": _first_int(item, "max_redemptions", "maxRedemptions") > 0,
        "max_redemptions": _first_int(item, "max_redemptions", "maxRedemptions"),
        "starts_at": _first_text(item, "starts_at", "startsAt"),
        "expires_at": _first_text(item, "expiry_date", "expires_at", "expiresAt"),
        "duration": _first_text(item, "duration") or "once",
        "duration_in_months": _first_int(item, "duration_in_months", "durationInMonths"),
        "status": status,
        "status_formatted": status.replace("_", " ").title(),
        "test_mode": str(item.get("mode") or "").strip().lower() in {"test", "sandbox", "local"},
        "created_at": _first_text(item, "created_at", "createdAt"),
        "updated_at": _first_text(item, "updated_at", "updatedAt"),
    }


def list_discounts(
    *,
    store_id: str | int | None = None,
    page_number: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    del store_id
    query_params = {
        "page": max(1, int(page_number)),
        "limit": max(1, int(page_size)),
    }
    response = _creem_request(
        "GET",
        f"/discounts/search?{urllib.parse.urlencode(query_params)}",
    )
    items = _response_items(response)
    meta = _as_dict(response.get("meta")) or _as_dict(response.get("pagination"))
    return {
        "discounts": [
            _normalize_discount_payload(item)
            for item in items
            if isinstance(item, Mapping)
        ],
        "meta": {
            "current_page": _first_int(meta, "current_page", "currentPage", "page") or page_number,
            "per_page": _first_int(meta, "per_page", "perPage", "limit", "page_size") or page_size,
            "total": _first_int(meta, "total", "total_count", "totalCount") or len(items),
            "last_page": _first_int(meta, "last_page", "lastPage") or 1,
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
    product_ids: Sequence[str | int] | None = None,
    test_mode: bool | None = None,
) -> dict[str, Any]:
    del starts_at, duration_in_months, test_mode
    normalized_product_ids = [
        str(item).strip()
        for item in (product_ids or [])
        if str(item).strip()
    ]
    normalized_amount_type = str(amount_type or "").strip().lower()
    payload: dict[str, Any] = {
        "name": str(name or "").strip(),
        "code": str(code or "").strip(),
        "duration": str(duration or "once").strip() or "once",
    }
    if normalized_amount_type in {"percent", "percentage"}:
        payload["type"] = "percentage"
        payload["percentage"] = int(amount or 0)
    else:
        payload["type"] = "fixed"
        payload["amount"] = int(amount or 0)
        payload["currency"] = "EUR"
    if normalized_product_ids:
        payload["applies_to_products"] = normalized_product_ids
    normalized_expires_at = str(expires_at or "").strip()
    if normalized_expires_at:
        payload["expiry_date"] = normalized_expires_at
    if int(max_redemptions or 0) > 0:
        payload["max_redemptions"] = int(max_redemptions)
    response = _creem_request("POST", "/discounts", payload=payload)
    return _normalize_discount_payload(response)


def delete_discount(discount_id: str | int) -> None:
    normalized_discount_id = urllib.parse.quote(str(discount_id or "").strip())
    if not normalized_discount_id:
        raise ValueError("discount_id is required")
    _creem_request("DELETE", f"/discounts/{normalized_discount_id}/delete")


def get_checkout_url(
    user_id: str,
    product_id: str | int,
    email: str,
    *,
    name: str = "",
    discount_code: str = "",
    custom_data: Mapping[str, Any] | None = None,
    redirect_url: str = "",
) -> str:
    normalized_product_id = str(product_id or "").strip()
    if not normalized_product_id:
        raise ValueError("Creem product_id is required to create a checkout.")

    metadata = {
        "user_id": str(user_id or "").strip(),
        **dict(custom_data or {}),
    }
    payload: dict[str, Any] = {
        "product_id": normalized_product_id,
        "request_id": f"runr_{str(user_id or '').strip()}_{uuid4().hex[:12]}",
        "metadata": metadata,
    }
    normalized_redirect_url = str(redirect_url or "").strip()
    if normalized_redirect_url:
        payload["success_url"] = normalized_redirect_url
    customer: dict[str, str] = {}
    normalized_email = str(email or "").strip()
    if normalized_email:
        customer["email"] = normalized_email
    normalized_name = str(name or "").strip()
    if normalized_name:
        customer["name"] = normalized_name
    if customer:
        payload["customer"] = customer
    normalized_discount_code = str(discount_code or "").strip()
    if normalized_discount_code:
        payload["discount_code"] = normalized_discount_code

    response = _creem_request("POST", "/checkouts", payload=payload)
    checkout = _as_dict(response.get("data")) or response
    checkout_url = _first_text(checkout, "checkout_url", "checkoutUrl", "url")
    if not checkout_url:
        raise RuntimeError("Creem checkout creation succeeded without returning a checkout URL.")
    return checkout_url


def retrieve_subscription(creem_subscription_id: str) -> dict[str, Any]:
    normalized_subscription_id = str(creem_subscription_id or "").strip()
    if not normalized_subscription_id:
        raise ValueError("creem_subscription_id is required")
    return _creem_request(
        "GET",
        f"/subscriptions?{urllib.parse.urlencode({'subscription_id': normalized_subscription_id})}",
    )


def retrieve_customer(creem_customer_id: str) -> dict[str, Any]:
    normalized_customer_id = str(creem_customer_id or "").strip()
    if not normalized_customer_id:
        raise ValueError("creem_customer_id is required")
    return _creem_request(
        "GET",
        f"/customers?{urllib.parse.urlencode({'customer_id': normalized_customer_id})}",
    )


def get_customer_portal_url(
    *,
    subscription_id: str = "",
    customer_id: str = "",
) -> str:
    normalized_customer_id = str(customer_id or "").strip()
    if not normalized_customer_id and subscription_id:
        response = retrieve_subscription(subscription_id)
        subscription = _as_dict(response.get("data")) or response
        customer = subscription.get("customer")
        if isinstance(customer, Mapping):
            normalized_customer_id = _first_text(customer, "id", "customer_id")
        else:
            normalized_customer_id = str(customer or "").strip()
    if not normalized_customer_id:
        raise ValueError("No Creem customer id is available for this user.")

    response = _creem_request("POST", "/customers/billing", payload={"customer_id": normalized_customer_id})
    portal = _as_dict(response.get("data")) or response
    portal_url = _first_text(portal, "customer_portal_link", "customerPortalLink", "url")
    if portal_url:
        return portal_url
    raise RuntimeError("Creem customer portal creation succeeded without returning a portal URL.")
