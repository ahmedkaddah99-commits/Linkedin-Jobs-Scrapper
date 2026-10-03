"""Bounded, fixture-friendly CompanyEnrich transport and field mapping."""

from __future__ import annotations

import os
import re
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import requests


COMPANY_ENRICH_BASE_URL = "https://api.companyenrich.com"
COMPANY_ENRICH_DOMAIN_PATH = "/companies/enrich"
COMPANY_ENRICH_BATCH_PATH = "/companies/enrich/batch"
COMPANY_ENRICH_PROVIDER = "companyenrich"
COMPANY_ENRICH_BATCH_SIZE = 50
_CREDENTIAL_SLOT = re.compile(r"^Company_Enrich_API_URL_v(\d+)$", flags=re.IGNORECASE)


class CompanyEnrichError(RuntimeError):
    """Base error whose message never contains credentials or response bodies."""


class CompanyEnrichAmbiguousTimeout(CompanyEnrichError):
    """The request may have reached the provider and must not be duplicated."""


class CompanyEnrichBudgetExceeded(CompanyEnrichError):
    """The local request or credit budget rejected a provider call."""


class CompanyEnrichProviderError(CompanyEnrichError):
    """The provider returned an unusable response after bounded failover."""


@dataclass(frozen=True, slots=True, repr=False)
class CompanyEnrichCredential:
    name: str
    token: str = field(repr=False)

    def __repr__(self) -> str:
        return f"CompanyEnrichCredential(name={self.name!r}, token=<redacted>)"


def discover_company_enrich_credentials(env: Mapping[str, str] | None = None) -> tuple[CompanyEnrichCredential, ...]:
    """Discover the primary key and every numeric credential slot without a cap."""

    values = os.environ if env is None else env
    discovered: list[CompanyEnrichCredential] = []
    primary = str(values.get("Company_Enrich_API_KEY") or "").strip()
    if primary:
        discovered.append(CompanyEnrichCredential("Company_Enrich_API_KEY", primary))
    slots: list[tuple[int, str, str]] = []
    for name, raw_value in values.items():
        match = _CREDENTIAL_SLOT.fullmatch(str(name))
        value = str(raw_value or "").strip()
        if match and value:
            version = int(match.group(1))
            slots.append((version, f"Company_Enrich_API_URL_v{version}", value))
    for _version, name, token in sorted(slots, key=lambda item: (item[0], item[1])):
        discovered.append(CompanyEnrichCredential(name, token))
    return tuple(discovered)


def _header(headers: Mapping[str, Any], name: str) -> str:
    wanted = name.casefold()
    for key, value in headers.items():
        if str(key).casefold() == wanted:
            return str(value or "").strip()
    return ""


def _float_header(headers: Mapping[str, Any], name: str, default: float = 0.0) -> float:
    try:
        return max(0.0, float(_header(headers, name)))
    except (TypeError, ValueError):
        return default


def _duration_seconds(value: Any) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        parts = raw.split(":")
        if len(parts) != 3:
            return 0.0
        try:
            hours, minutes, seconds = (float(part) for part in parts)
        except ValueError:
            return 0.0
        return max(0.0, hours * 3600 + minutes * 60 + seconds)


def _normalize_domain(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlsplit(candidate)
    host = (parsed.hostname or "").casefold().removeprefix("www.").rstrip(".")
    return host if host and "." in host and "@" not in host else ""


def _location_text(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    parts: list[str] = []
    for group_name in ("city", "state", "country"):
        group = value.get(group_name)
        if isinstance(group, Mapping):
            text = str(group.get("name") or group.get("code") or "").strip()
        else:
            text = str(group or "").strip()
        if text and text not in parts:
            parts.append(text)
    return ", ".join(parts)


def _property_request(company: Mapping[str, Any]) -> dict[str, Any]:
    linkedin_url = str(
        company.get("linkedin_company_url")
        or company.get("linkedin_url")
        or ""
    ).strip()
    if linkedin_url:
        return {"linkedinUrl": linkedin_url}
    linkedin_id = str(company.get("linkedin_company_id") or company.get("linkedin_org_id") or "").strip()
    if linkedin_id:
        return {"linkedinId": linkedin_id}
    name = str(company.get("canonical_name") or company.get("company_name") or company.get("name") or "").strip()
    if name:
        return {"name": name}
    return {}


class CompanyEnrichProvider:
    """CompanyEnrich adapter with deterministic credential failover.

    HTTP calls are synchronous inside the existing worker-provider contract, as
    the other providers in this module are. Tests inject response fixtures by
    patching ``requests.request``; no live provider call is required.
    """

    def __init__(
        self,
        *,
        credentials: Sequence[CompanyEnrichCredential | Mapping[str, Any]] | None = None,
        timeout_seconds: float = 12.0,
        request_budget: int = 25,
        credit_budget: float = 0.0,
        max_concurrency: int = 1,
        min_interval_seconds: float = 0.0,
        circuit_failure_threshold: int = 3,
        circuit_open_seconds: float = 300.0,
        cache_ttl_seconds: float = 86_400.0,
    ) -> None:
        raw_credentials = discover_company_enrich_credentials() if credentials is None else credentials
        normalized: list[CompanyEnrichCredential] = []
        for raw in raw_credentials:
            if isinstance(raw, CompanyEnrichCredential):
                credential = raw
            else:
                credential = CompanyEnrichCredential(str(raw.get("name") or "slot"), str(raw.get("token") or "").strip())
            if credential.token:
                normalized.append(credential)
        if not normalized:
            raise CompanyEnrichError("companyenrich_credentials_missing")
        self.credentials = tuple(normalized)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.request_budget = max(0, int(request_budget))
        self.credit_budget = max(0.0, float(credit_budget))
        self.max_concurrency = max(1, int(max_concurrency))
        self.min_interval_seconds = max(0.0, float(min_interval_seconds))
        self.circuit_failure_threshold = max(1, int(circuit_failure_threshold))
        self.circuit_open_seconds = max(1.0, float(circuit_open_seconds))
        self.cache_ttl_seconds = max(0.0, float(cache_ttl_seconds))
        self._lock = threading.RLock()
        self._credential_cursor = 0
        self._requests = 0
        self._credit_cost = 0.0
        self._cache: dict[str, tuple[float, Mapping[str, Any]]] = {}
        self._last_request_at = {credential.name: 0.0 for credential in self.credentials}
        self._rate_intervals = {credential.name: 0.0 for credential in self.credentials}
        self._rate_reset_at = {credential.name: 0.0 for credential in self.credentials}
        self._concurrency = threading.BoundedSemaphore(self.max_concurrency)
        self._semaphores = {credential.name: threading.BoundedSemaphore(self.max_concurrency) for credential in self.credentials}
        self._state = {
            credential.name: {
                "requests": 0,
                "successes": 0,
                "failures": 0,
                "credit_cost": 0.0,
                "credit_balance": 0.0,
                "credit_remaining": 0.0,
                "rate_limit": 0,
                "rate_remaining": 0,
                "rate_window": "",
                "circuit_failures": 0,
                "circuit_open_until": 0.0,
                "last_status": 0,
            }
            for credential in self.credentials
        }

    @property
    def accounting(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {name: dict(values) for name, values in self._state.items()}

    def _ordered_credentials(self) -> tuple[CompanyEnrichCredential, ...]:
        with self._lock:
            start = self._credential_cursor % len(self.credentials)
            self._credential_cursor += 1
        return tuple(self.credentials[(start + offset) % len(self.credentials)] for offset in range(len(self.credentials)))

    def _circuit_open(self, name: str) -> bool:
        with self._lock:
            return float(self._state[name]["circuit_open_until"]) > time.monotonic()

    def _reserve_request(self, credential: CompanyEnrichCredential, estimated_credit_cost: float) -> None:
        with self._lock:
            if self._requests >= self.request_budget:
                raise CompanyEnrichBudgetExceeded("companyenrich_request_budget_exhausted")
            if self.credit_budget and self._credit_cost + estimated_credit_cost > self.credit_budget:
                raise CompanyEnrichBudgetExceeded("companyenrich_credit_budget_exhausted")
            now = time.monotonic()
            state = self._state[credential.name]
            interval = max(self.min_interval_seconds, self._rate_intervals[credential.name])
            next_request_at = max(now, self._last_request_at[credential.name] + interval)
            if state["rate_remaining"] <= 0 and self._rate_reset_at[credential.name] > now:
                next_request_at = max(next_request_at, self._rate_reset_at[credential.name])
            wait_seconds = max(0.0, next_request_at - now)
            self._last_request_at[credential.name] = next_request_at
            self._requests += 1
            self._state[credential.name]["requests"] += 1
        if wait_seconds:
            time.sleep(wait_seconds)

    def _record_headers(self, credential: CompanyEnrichCredential, headers: Mapping[str, Any], status: int) -> float:
        cost = _float_header(headers, "x-credit-cost")
        rate_limit = int(_float_header(headers, "x-ratelimit-limit"))
        rate_remaining = int(_float_header(headers, "x-ratelimit-remaining"))
        rate_window = _header(headers, "x-ratelimit-window")
        window_seconds = _duration_seconds(rate_window)
        with self._lock:
            state = self._state[credential.name]
            state["credit_balance"] = _float_header(headers, "x-credit-balance")
            state["credit_remaining"] = _float_header(headers, "x-credit-remaining")
            state["rate_limit"] = rate_limit
            state["rate_remaining"] = rate_remaining
            state["rate_window"] = rate_window
            if rate_limit and window_seconds:
                self._rate_intervals[credential.name] = window_seconds / rate_limit
            if rate_remaining <= 0 and window_seconds:
                self._rate_reset_at[credential.name] = time.monotonic() + window_seconds
            state["last_status"] = status
            state["credit_cost"] += cost
            self._credit_cost += cost
        return cost

    def _record_success(self, credential: CompanyEnrichCredential) -> None:
        with self._lock:
            state = self._state[credential.name]
            state["successes"] += 1
            state["circuit_failures"] = 0
            state["circuit_open_until"] = 0.0

    def _record_failure(self, credential: CompanyEnrichCredential, status: int = 0, cooldown_seconds: float = 0.0) -> None:
        with self._lock:
            state = self._state[credential.name]
            state["failures"] += 1
            state["last_status"] = status
            state["circuit_failures"] += 1
            if state["circuit_failures"] >= self.circuit_failure_threshold:
                state["circuit_open_until"] = time.monotonic() + self.circuit_open_seconds
            if cooldown_seconds > 0:
                state["circuit_open_until"] = max(state["circuit_open_until"], time.monotonic() + cooldown_seconds)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        estimated_credit_cost: float = 1.0,
    ) -> tuple[int, Mapping[str, Any], Any, CompanyEnrichCredential, float]:
        last_status = 0
        for credential in self._ordered_credentials():
            if self._circuit_open(credential.name):
                continue
            semaphore = self._semaphores[credential.name]
            with self._concurrency, semaphore:
                self._reserve_request(credential, estimated_credit_cost)
                try:
                    response = requests.request(
                        method,
                        f"{COMPANY_ENRICH_BASE_URL}{path}",
                        params=dict(params or {}),
                        json=dict(body or {}) if body is not None else None,
                        headers={"Authorization": f"Bearer {credential.token}", "Accept": "application/json"},
                        timeout=self.timeout_seconds,
                    )
                except requests.Timeout as exc:
                    self._record_failure(credential)
                    raise CompanyEnrichAmbiguousTimeout("companyenrich_request_timeout") from exc
                except requests.RequestException as exc:
                    self._record_failure(credential)
                    last_status = 0
                    continue

                status = int(getattr(response, "status_code", 0) or 0)
                headers = getattr(response, "headers", {}) or {}
                cost = self._record_headers(credential, headers, status)
                last_status = status
                if status == 200:
                    self._record_success(credential)
                    try:
                        return status, headers, response.json(), credential, cost
                    except (TypeError, ValueError) as exc:
                        self._record_failure(credential, status)
                        raise CompanyEnrichProviderError("companyenrich_invalid_json") from exc
                if status == 404:
                    self._record_success(credential)
                    return status, headers, None, credential, cost
                if status in {401, 402, 429} or status >= 500:
                    retry_after = _duration_seconds(_header(headers, "retry-after"))
                    self._record_failure(credential, status, retry_after if status == 429 else 0.0)
                    continue
                self._record_failure(credential, status)
                raise CompanyEnrichProviderError(f"companyenrich_http_{status}")
        raise CompanyEnrichProviderError(f"companyenrich_failover_exhausted_{last_status or 'transport'}")

    @staticmethod
    def _result(payload: Mapping[str, Any], *, method: str, cost: float) -> dict[str, Any]:
        socials = payload.get("socials") if isinstance(payload.get("socials"), Mapping) else {}
        fields: dict[str, Any] = {
            "website": payload.get("website"),
            "industry": payload.get("industry"),
            "company_size": payload.get("employees") or payload.get("reported_employees"),
            "headquarters": _location_text(payload.get("location")),
        }
        identity_fields: dict[str, Any] = {
            "companyenrich_id": payload.get("id"),
            "company_name": payload.get("name"),
            "domain": payload.get("domain"),
            "linkedin_company_url": socials.get("linkedin_url"),
            "linkedin_company_id": socials.get("linkedin_id"),
        }
        return {
            "fields": {key: value for key, value in fields.items() if value not in (None, "", [])},
            "source": f"{COMPANY_ENRICH_PROVIDER}:{method}",
            "provenance_url": f"{COMPANY_ENRICH_BASE_URL}{COMPANY_ENRICH_DOMAIN_PATH}",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "extra_fields": {
                **{key: value for key, value in identity_fields.items() if value not in (None, "", [])},
                "companyenrich_lookup_method": method,
            },
            "request_count": 1,
            "cost_units": cost,
        }

    @staticmethod
    def _no_match(*, method: str) -> dict[str, Any]:
        return {
            "fields": {},
            "source": f"{COMPANY_ENRICH_PROVIDER}:{method}:no_match",
            "provenance_url": f"{COMPANY_ENRICH_BASE_URL}{COMPANY_ENRICH_DOMAIN_PATH}",
            "extra_fields": {"companyenrich_lookup_method": method, "companyenrich_match": "no_match"},
            "request_count": 1,
            "cost_units": 0.0,
        }

    def _cache_result(self, key: str, result: Mapping[str, Any]) -> None:
        with self._lock:
            self._cache[key] = (time.monotonic(), dict(result))

    def _cached_fallback(self, key: str) -> Mapping[str, Any] | None:
        with self._lock:
            cached = self._cache.get(key)
        if cached is None:
            return None
        cached_at, result = cached
        age = max(0.0, time.monotonic() - cached_at)
        status = "stale_cache" if self.cache_ttl_seconds <= 0 or age > self.cache_ttl_seconds else "cache_fallback"
        fallback = dict(result)
        fallback["source"] = f"{result.get('source') or COMPANY_ENRICH_PROVIDER}:{status}"
        fallback["request_count"] = 0
        fallback["cost_units"] = 0.0
        extra = dict(result.get("extra_fields") or {}) if isinstance(result.get("extra_fields"), Mapping) else {}
        extra["companyenrich_cache_status"] = status
        fallback["extra_fields"] = extra
        return fallback

    async def _property_enrich(self, company: Mapping[str, Any]) -> Mapping[str, Any]:
        body = _property_request(company)
        if not body:
            return self._no_match(method="property:no_input")
        status, _headers, payload, _credential, cost = self._request(
            "POST", COMPANY_ENRICH_DOMAIN_PATH, body=body, estimated_credit_cost=1.0
        )
        if status == 404 or not isinstance(payload, Mapping):
            return self._no_match(method="property")
        result = self._result(payload, method="property", cost=cost)
        self._cache_result("property:" + repr(sorted(body.items())), result)
        return result

    async def enrich(self, company: Mapping[str, Any], *, conditional: Mapping[str, Any]) -> Mapping[str, Any]:
        del conditional
        domain = _normalize_domain(company.get("domain") or company.get("website") or company.get("website_url"))
        if domain:
            cache_key = "domain:" + domain
            try:
                status, _headers, payload, _credential, cost = self._request(
                    "GET",
                    COMPANY_ENRICH_DOMAIN_PATH,
                    params={"domain": domain, "waitForEnrichment": "false"},
                    estimated_credit_cost=1.0,
                )
            except CompanyEnrichAmbiguousTimeout:
                fallback = self._cached_fallback(cache_key)
                if fallback is not None:
                    return fallback
                raise
            except CompanyEnrichProviderError:
                fallback = self._cached_fallback(cache_key)
                if fallback is not None:
                    return fallback
                raise
            if status == 200 and isinstance(payload, Mapping):
                result = self._result(payload, method="domain", cost=cost)
                self._cache_result(cache_key, result)
                return result
            if status != 404:
                raise CompanyEnrichProviderError("companyenrich_domain_response_invalid")
        return await self._property_enrich(company)

    async def enrich_many(self, companies: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
        """Batch reliable domains, then property-fallback unresolved companies."""

        by_domain: dict[str, Mapping[str, Any]] = {}
        by_key: dict[str, Mapping[str, Any]] = {}
        for company in companies:
            key = str(company.get("company_id") or "").strip()
            domain = _normalize_domain(company.get("domain") or company.get("website") or company.get("website_url"))
            if domain and domain not in by_domain:
                by_domain[domain] = company
            if key:
                by_key[key] = company
        results: dict[str, Mapping[str, Any]] = {}
        domains = list(by_domain)
        if len(domains) <= 1:
            if domains:
                domain = domains[0]
                result = await self.enrich(by_domain[domain], conditional={})
                results[domain] = result
                for key, company in by_key.items():
                    if _normalize_domain(company.get("domain") or company.get("website") or company.get("website_url")) == domain:
                        results[key] = result
            else:
                for key, company in by_key.items():
                    results[key] = await self._property_enrich(company)
            return results
        for start in range(0, len(domains), COMPANY_ENRICH_BATCH_SIZE):
            chunk = domains[start : start + COMPANY_ENRICH_BATCH_SIZE]
            status, _headers, payload, _credential, _cost = self._request(
                "POST",
                COMPANY_ENRICH_BATCH_PATH,
                body={"domains": chunk},
                estimated_credit_cost=float(len(chunk)),
            )
            if status != 200 or not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
                continue
            for item in payload:
                if not isinstance(item, Mapping):
                    continue
                domain = _normalize_domain(item.get("domain"))
                if domain and domain in by_domain:
                    result = self._result(item, method="batch_domain", cost=1.0)
                    results[domain] = result
                    company_key = str(by_domain[domain].get("company_id") or "").strip()
                    if company_key:
                        results[company_key] = result
        for domain, company in by_domain.items():
            if domain not in results:
                fallback = await self._property_enrich(company)
                results[domain] = fallback
                company_key = str(company.get("company_id") or "").strip()
                if company_key:
                    results[company_key] = fallback
        for key, company in by_key.items():
            if key not in results:
                results[key] = await self._property_enrich(company)
        return results

    async def enrich_batch(self, companies: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
        return await self.enrich_many(companies)


__all__ = [
    "CompanyEnrichAmbiguousTimeout",
    "CompanyEnrichBudgetExceeded",
    "CompanyEnrichCredential",
    "CompanyEnrichError",
    "CompanyEnrichProvider",
    "COMPANY_ENRICH_BATCH_SIZE",
    "discover_company_enrich_credentials",
]
