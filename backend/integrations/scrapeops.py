from __future__ import annotations

import html
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, TypedDict
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests


LOGGER = logging.getLogger(__name__)
SCRAPEOPS_PROXY_ENDPOINT = "https://proxy.scrapeops.io/v1/"
SCRAPEOPS_USAGE_ENDPOINT = "https://backend.scrapeops.io/v1/proxy/account/usage"
SCRAPEOPS_DOMAIN_STATS_ENDPOINT = "https://backend.scrapeops.io/v1/proxy/account/domain-success-rates"
SCRAPEOPS_HEALTH_TARGET_URL = "https://httpbin.org/get"
SCRAPEOPS_POLICY_VERSION = "2026-05-26.credit-guard-v2"
SCRAPEOPS_USAGE_EVENT_NAME = "scrapeops_request"

SCRAPEOPS_REQUEST_MODES: dict[str, dict[str, Any]] = {
    "basic": {
        "label": "Basic Proxy",
        "native_credits": 1,
        "runner_credits": 1,
        "params": {},
    },
    "render_js_cheap": {
        "label": "Cheap JS Render",
        "native_credits": 5,
        "runner_credits": 5,
        "params": {"render_js_cheap": "true"},
    },
    "render_js": {
        "label": "JavaScript Render",
        "native_credits": 10,
        "runner_credits": 10,
        "params": {"render_js": "true"},
    },
    "residential": {
        "label": "Residential Proxy",
        "native_credits": 10,
        "runner_credits": 10,
        "params": {"residential": "true"},
    },
    "render_js_residential": {
        "label": "Residential JS Render",
        "native_credits": 25,
        "runner_credits": 25,
        "params": {"render_js": "true", "residential": "true"},
    },
}

SCRAPEOPS_STANDARD_COUNTRIES = {
    "br",
    "ca",
    "cn",
    "de",
    "es",
    "fr",
    "in",
    "it",
    "jp",
    "ru",
    "uk",
    "us",
}


def billed_status_code(status_code: int) -> bool:
    return int(status_code) in {200, 404}


def estimate_mode_native_credits(mode: str) -> int:
    descriptor = SCRAPEOPS_REQUEST_MODES.get(str(mode or "").strip(), SCRAPEOPS_REQUEST_MODES["basic"])
    return max(1, int(descriptor.get("native_credits") or 1))


def estimate_mode_runner_credits(mode: str) -> int:
    descriptor = SCRAPEOPS_REQUEST_MODES.get(str(mode or "").strip(), SCRAPEOPS_REQUEST_MODES["basic"])
    return max(1, int(descriptor.get("runner_credits") or 1))


def request_mode_label(mode: str) -> str:
    descriptor = SCRAPEOPS_REQUEST_MODES.get(str(mode or "").strip(), SCRAPEOPS_REQUEST_MODES["basic"])
    return str(descriptor.get("label") or "Basic Proxy")


def normalize_scrapeops_country_code(country_code: str) -> str:
    normalized = str(country_code or "").strip().lower()
    if not normalized:
        return ""
    aliases = {
        "gb": "uk",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in SCRAPEOPS_STANDARD_COUNTRIES else ""


def request_mode_params(mode: str) -> dict[str, str]:
    descriptor = SCRAPEOPS_REQUEST_MODES.get(str(mode or "").strip(), SCRAPEOPS_REQUEST_MODES["basic"])
    return {
        str(key): str(value)
        for key, value in dict(descriptor.get("params") or {}).items()
        if str(key).strip() and value not in {None, ""}
    }


def build_proxy_params(
    *,
    api_key: str,
    url: str,
    mode: str,
    country_code: str = "",
) -> dict[str, str]:
    target_host = (urlparse(str(url or "").strip()).hostname or "").casefold()
    if target_host == "linkedin.com" or target_host.endswith(".linkedin.com"):
        LOGGER.warning(
            "LinkedIn proxy request initiated - documented cost is 70 credits/request. "
            "Ensure this is intentional and budgeted."
        )
    params = {
        "api_key": str(api_key or "").strip(),
        "url": str(url or "").strip(),
        "json_response": "true",
        **request_mode_params(mode),
    }
    normalized_country_code = normalize_scrapeops_country_code(country_code)
    if normalized_country_code:
        params["country"] = normalized_country_code
    return params


def sanitize_scrapeops_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"([?&]api_key=)[^&\s]+", r"\1[redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"([?&]url=)[^&\s]+", r"\1[target]", text, flags=re.IGNORECASE)
    return text


def sanitize_url_for_logs(raw_url: str) -> str:
    value = str(raw_url or "").strip()
    if not value:
        return ""
    try:
        parsed = urlparse(value)
    except Exception:
        return sanitize_scrapeops_text(value)
    sanitized_pairs: list[tuple[str, str]] = []
    for key, item_value in parse_qsl(parsed.query, keep_blank_values=True):
        if str(key).lower() == "api_key":
            sanitized_pairs.append((key, "[redacted]"))
        elif str(key).lower() == "url":
            sanitized_pairs.append((key, "[target]"))
        else:
            sanitized_pairs.append((key, item_value))
    return urlunparse(parsed._replace(query=urlencode(sanitized_pairs, doseq=True)))


def parse_json_safely(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return None


@dataclass(frozen=True, slots=True)
class ScrapeOpsFailure:
    category: str
    status_code: int
    billed: bool
    safe_message: str
    response_payload: dict[str, Any]


class ScrapeOpsRequestError(RuntimeError):
    def __init__(self, failure: ScrapeOpsFailure) -> None:
        self.failure = failure
        super().__init__(failure.safe_message)


class ScrapeOpsOutOfCreditsError(ScrapeOpsRequestError):
    pass


class ScrapeOpsProxyHealthResult(TypedDict):
    healthy: bool
    reason: str
    credits_remaining: int | None


class ScrapeOpsProxyUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ScrapeOpsProxyEnvelope:
    provider_status_code: int
    target_status_code: int
    body: str
    billed_credits_actual: int | None
    payload: dict[str, Any]


_REMAINING_CREDIT_KEYS = {
    "api_credits_remaining",
    "credits_remaining",
    "remaining_api_credits",
    "remaining_credits",
    "sops_api_credits_remaining",
}


def _integer_or_none(value: Any) -> int | None:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def _credits_remaining_from_payload(payload: Mapping[str, Any]) -> int | None:
    for key, value in payload.items():
        normalized_key = re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")
        if normalized_key in _REMAINING_CREDIT_KEYS:
            return _integer_or_none(value)
        if normalized_key in {"body", "cookies", "headers", "xhr"}:
            continue
        if isinstance(value, Mapping):
            nested_value = _credits_remaining_from_payload(value)
            if nested_value is not None:
                return nested_value
    return None


def parse_proxy_response_envelope(response: requests.Response) -> ScrapeOpsProxyEnvelope:
    """Read a json_response proxy envelope while retaining target response semantics."""
    payload_value = parse_json_safely(response.text)
    payload = payload_value if isinstance(payload_value, dict) else {}
    has_envelope = "body" in payload or "sops_api_credits" in payload or "status_code" in payload
    provider_status_code = int(response.status_code or 0)
    target_status_code = (
        _integer_or_none(payload.get("status_code"))
        if has_envelope
        else provider_status_code
    )
    if target_status_code is None:
        target_status_code = provider_status_code
    body = str(payload.get("body") or "") if has_envelope else response.text
    content_type = str(payload.get("content_type") or "").casefold()
    if has_envelope and ("html" in content_type or body.lstrip().startswith("&lt;")):
        body = html.unescape(body)
    billed_credits_actual = _integer_or_none(payload.get("sops_api_credits")) if has_envelope else None
    return ScrapeOpsProxyEnvelope(
        provider_status_code=provider_status_code,
        target_status_code=target_status_code,
        body=body,
        billed_credits_actual=billed_credits_actual,
        payload=payload,
    )


def build_proxy_usage_record(
    *,
    source_id: str,
    target_url: str,
    request_mode: str,
    target_status_code: int,
    provider_status_code: int,
    latency_ms: int,
    billed_credits_actual: int | None,
    billed_credits_estimated: int,
    usable_job_count: int = 0,
    error_category: str = "",
) -> dict[str, Any]:
    return {
        "source_id": str(source_id or "").strip(),
        "target_url": sanitize_url_for_logs(target_url),
        "method": "scrapeops_proxy",
        "request_mode": str(request_mode or "basic").strip() or "basic",
        "target_status_code": int(target_status_code or 0),
        "provider_status_code": int(provider_status_code or 0),
        "latency_ms": max(0, int(latency_ms or 0)),
        "billed_credits_actual": billed_credits_actual,
        "billed_credits_estimated": max(0, int(billed_credits_estimated or 0)),
        "usable_job_count": max(0, int(usable_job_count or 0)),
        "error_category": str(error_category or "").strip(),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def check_scrapeops_proxy_health(
    api_key: str = "",
    *,
    timeout_seconds: int = 5,
    usage_callback=None,
) -> ScrapeOpsProxyHealthResult:
    """Probe the paid Proxy API once before proxy-backed acquisition begins."""
    normalized_api_key = str(api_key or os.getenv("SCRAPEOPS_API_KEY", "")).strip()
    if not normalized_api_key:
        reason = "missing_api_key"
        LOGGER.error("ScrapeOps proxy health check failed: reason=%s", reason)
        return {"healthy": False, "reason": reason, "credits_remaining": None}

    request_started = time.perf_counter()
    try:
        response = requests.get(
            SCRAPEOPS_PROXY_ENDPOINT,
            params={
                "api_key": normalized_api_key,
                "url": SCRAPEOPS_HEALTH_TARGET_URL,
                "json_response": "true",
            },
            timeout=max(1, int(timeout_seconds)),
        )
    except requests.RequestException as exc:
        reason = "network_or_timeout_error"
        if callable(usage_callback):
            usage_callback(
                {
                    **build_proxy_usage_record(
                        source_id="scrapeops_health_check",
                        target_url=SCRAPEOPS_HEALTH_TARGET_URL,
                        request_mode="basic",
                        target_status_code=0,
                        provider_status_code=0,
                        latency_ms=round((time.perf_counter() - request_started) * 1000),
                        billed_credits_actual=0,
                        billed_credits_estimated=0,
                        error_category=reason,
                    ),
                    "domain": "httpbin.org",
                    "status_code": 0,
                    "billed": False,
                    "native_credits": 0,
                    "runner_credits": 0,
                }
            )
        LOGGER.error("ScrapeOps proxy health check failed: reason=%s detail=%s", reason, sanitize_scrapeops_text(exc))
        return {"healthy": False, "reason": reason, "credits_remaining": None}

    payload_value = parse_json_safely(response.text)
    payload = payload_value if isinstance(payload_value, dict) else {}
    credits_remaining = _credits_remaining_from_payload(payload)
    response_detail = sanitize_scrapeops_text(response.text)[:500]
    lowered_detail = response.text.casefold()
    provider_status_code = _integer_or_none(payload.get("status_code"))
    billed_status = provider_status_code if provider_status_code is not None else int(response.status_code or 0)
    billed = billed_status_code(billed_status)
    actual_credits = _integer_or_none(payload.get("sops_api_credits")) if billed else 0
    estimated_credits = estimate_mode_native_credits("basic") if billed else 0
    accounted_credits = actual_credits if actual_credits is not None else estimated_credits

    if int(response.status_code or 0) == 403 and "banned account" in lowered_detail:
        reason = "banned_account"
    elif credits_remaining is not None and credits_remaining <= 0:
        reason = "insufficient_credits"
    elif (
        int(response.status_code or 0) == 401
        or "consumed all your api credits" in lowered_detail
        or "insufficient credit" in lowered_detail
        or "insufficient api credit" in lowered_detail
        or "out of credits" in lowered_detail
    ):
        reason = "insufficient_credits"
    elif int(response.status_code or 0) in {200, 404} and billed_status in {200, 404}:
        reason = "healthy"
    else:
        reason = "proxy_unavailable"

    if callable(usage_callback):
        usage_callback(
            {
                **build_proxy_usage_record(
                    source_id="scrapeops_health_check",
                    target_url=SCRAPEOPS_HEALTH_TARGET_URL,
                    request_mode="basic",
                    target_status_code=billed_status,
                    provider_status_code=int(response.status_code or 0),
                    latency_ms=round((time.perf_counter() - request_started) * 1000),
                    billed_credits_actual=actual_credits,
                    billed_credits_estimated=estimated_credits,
                    error_category="" if reason == "healthy" else reason,
                ),
                "domain": "httpbin.org",
                "status_code": billed_status,
                "billed": billed,
                "native_credits": accounted_credits,
                "runner_credits": accounted_credits,
            }
        )
    if reason == "healthy":
        return {
            "healthy": True,
            "reason": "healthy",
            "credits_remaining": credits_remaining,
        }

    LOGGER.error(
        "ScrapeOps proxy health check failed: reason=%s provider_http_status=%s target_status=%s "
        "credits_remaining=%s response=%s",
        reason,
        int(response.status_code or 0),
        billed_status,
        credits_remaining,
        response_detail,
    )
    return {"healthy": False, "reason": reason, "credits_remaining": credits_remaining}


def require_scrapeops_proxy_health(api_key: str = "", *, usage_callback=None) -> ScrapeOpsProxyHealthResult:
    result = check_scrapeops_proxy_health(api_key, usage_callback=usage_callback)
    if result["healthy"]:
        return result

    messages = {
        "banned_account": "ScrapeOps proxy is unavailable (banned account). Please contact support.",
        "insufficient_credits": "ScrapeOps proxy is unavailable (insufficient credits). Please add credits or contact support.",
        "network_or_timeout_error": "ScrapeOps proxy is unavailable due to a network or timeout error. Please try again.",
        "missing_api_key": "ScrapeOps proxy is unavailable because its API key is not configured.",
    }
    raise ScrapeOpsProxyUnavailableError(
        messages.get(result["reason"], "ScrapeOps proxy is unavailable. Please contact support.")
    )


def classify_failure(
    *,
    status_code: int,
    response_text: str = "",
    fallback_message: str = "",
) -> ScrapeOpsFailure:
    parsed_payload = parse_json_safely(response_text)
    payload = parsed_payload if isinstance(parsed_payload, dict) else {}
    detail = " ".join(
        item
        for item in (
            str(payload.get("error") or "").strip(),
            str(payload.get("message") or "").strip(),
            str(payload.get("API Credits") or "").strip(),
            str(fallback_message or "").strip(),
        )
        if item
    ).strip()
    lowered = detail.lower()
    category = "request_failed"
    safe_message = "ScrapeOps request failed."
    if int(status_code) == 401 or "consumed all your api credits" in lowered:
        category = "out_of_credits"
        safe_message = "ScrapeOps is out of credits."
    elif int(status_code) == 403:
        category = "invalid_api_key"
        safe_message = "ScrapeOps API key is missing or invalid."
    elif int(status_code) == 429:
        category = "concurrency_limit"
        safe_message = "ScrapeOps concurrency limit reached."
    elif int(status_code) == 400:
        category = "bad_request"
        safe_message = "ScrapeOps rejected the request parameters."
    elif int(status_code) >= 500:
        category = "upstream_fetch_failed"
        safe_message = "ScrapeOps could not retrieve the target page."
    elif detail:
        safe_message = sanitize_scrapeops_text(detail)
    return ScrapeOpsFailure(
        category=category,
        status_code=int(status_code),
        billed=billed_status_code(status_code),
        safe_message=safe_message,
        response_payload={
            key: sanitize_scrapeops_text(item)
            for key, item in payload.items()
            if key not in {"api_key"}
        },
    )


def raise_for_failure(
    response: requests.Response | None = None,
    *,
    fallback_message: str = "",
) -> None:
    if response is None:
        failure = ScrapeOpsFailure(
            category="request_failed",
            status_code=0,
            billed=False,
            safe_message=sanitize_scrapeops_text(fallback_message) or "ScrapeOps request failed.",
            response_payload={},
        )
    else:
        failure = classify_failure(
            status_code=int(response.status_code or 0),
            response_text=response.text,
            fallback_message=fallback_message,
        )
    if failure.category == "out_of_credits":
        raise ScrapeOpsOutOfCreditsError(failure)
    raise ScrapeOpsRequestError(failure)


def fetch_account_usage(api_key: str, *, timeout_seconds: int = 8) -> dict[str, Any]:
    normalized_api_key = str(api_key or "").strip()
    if not normalized_api_key:
        raise ValueError("SCRAPEOPS_API_KEY is required.")
    response = requests.get(
        SCRAPEOPS_USAGE_ENDPOINT,
        params={"api_key": normalized_api_key},
        timeout=max(3, int(timeout_seconds)),
    )
    if response.status_code >= 400:
        raise_for_failure(response, fallback_message="Unable to fetch ScrapeOps account usage.")
    payload = parse_json_safely(response.text)
    if not isinstance(payload, dict):
        raise ValueError("Unexpected ScrapeOps usage response.")
    return payload


def fetch_domain_stats(
    api_key: str,
    *,
    domain: str = "",
    date: str = "",
    timeout_seconds: int = 8,
) -> dict[str, Any]:
    normalized_api_key = str(api_key or "").strip()
    if not normalized_api_key:
        raise ValueError("SCRAPEOPS_API_KEY is required.")
    params = {"api_key": normalized_api_key}
    if str(domain or "").strip():
        params["domain"] = str(domain).strip()
    if str(date or "").strip():
        params["date"] = str(date).strip()
    response = requests.get(
        SCRAPEOPS_DOMAIN_STATS_ENDPOINT,
        params=params,
        timeout=max(3, int(timeout_seconds)),
    )
    if response.status_code >= 400:
        raise_for_failure(response, fallback_message="Unable to fetch ScrapeOps domain stats.")
    payload = parse_json_safely(response.text)
    if not isinstance(payload, dict):
        raise ValueError("Unexpected ScrapeOps domain stats response.")
    return payload


__all__ = [
    "SCRAPEOPS_DOMAIN_STATS_ENDPOINT",
    "SCRAPEOPS_HEALTH_TARGET_URL",
    "SCRAPEOPS_POLICY_VERSION",
    "SCRAPEOPS_PROXY_ENDPOINT",
    "SCRAPEOPS_REQUEST_MODES",
    "SCRAPEOPS_STANDARD_COUNTRIES",
    "SCRAPEOPS_USAGE_ENDPOINT",
    "SCRAPEOPS_USAGE_EVENT_NAME",
    "ScrapeOpsFailure",
    "ScrapeOpsOutOfCreditsError",
    "ScrapeOpsProxyEnvelope",
    "ScrapeOpsProxyHealthResult",
    "ScrapeOpsProxyUnavailableError",
    "ScrapeOpsRequestError",
    "billed_status_code",
    "build_proxy_usage_record",
    "build_proxy_params",
    "check_scrapeops_proxy_health",
    "classify_failure",
    "estimate_mode_native_credits",
    "estimate_mode_runner_credits",
    "fetch_account_usage",
    "fetch_domain_stats",
    "normalize_scrapeops_country_code",
    "parse_json_safely",
    "parse_proxy_response_envelope",
    "raise_for_failure",
    "require_scrapeops_proxy_health",
    "request_mode_label",
    "request_mode_params",
    "sanitize_scrapeops_text",
    "sanitize_url_for_logs",
]
