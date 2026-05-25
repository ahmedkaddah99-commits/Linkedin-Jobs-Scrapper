from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests


SCRAPEOPS_PROXY_ENDPOINT = "https://proxy.scrapeops.io/v1/"
SCRAPEOPS_USAGE_ENDPOINT = "https://backend.scrapeops.io/v1/proxy/account/usage"
SCRAPEOPS_DOMAIN_STATS_ENDPOINT = "https://backend.scrapeops.io/v1/proxy/account/domain-success-rates"
SCRAPEOPS_POLICY_VERSION = "2026-05-25.local-market-v1"
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
    params = {
        "api_key": str(api_key or "").strip(),
        "url": str(url or "").strip(),
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
    "SCRAPEOPS_POLICY_VERSION",
    "SCRAPEOPS_PROXY_ENDPOINT",
    "SCRAPEOPS_REQUEST_MODES",
    "SCRAPEOPS_STANDARD_COUNTRIES",
    "SCRAPEOPS_USAGE_ENDPOINT",
    "SCRAPEOPS_USAGE_EVENT_NAME",
    "ScrapeOpsFailure",
    "ScrapeOpsOutOfCreditsError",
    "ScrapeOpsRequestError",
    "billed_status_code",
    "build_proxy_params",
    "classify_failure",
    "estimate_mode_native_credits",
    "estimate_mode_runner_credits",
    "fetch_account_usage",
    "fetch_domain_stats",
    "normalize_scrapeops_country_code",
    "parse_json_safely",
    "raise_for_failure",
    "request_mode_label",
    "request_mode_params",
    "sanitize_scrapeops_text",
    "sanitize_url_for_logs",
]
