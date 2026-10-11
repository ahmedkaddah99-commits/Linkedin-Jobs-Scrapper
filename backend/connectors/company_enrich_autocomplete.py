"""Guarded, free CompanyEnrich domain autocomplete.

This adapter is deliberately separate from paid CompanyEnrich enrichment.  It
only reads the provider's autocomplete endpoint, records sanitized decisions,
and fails closed when a domain cannot be corroborated by employer identity
evidence.
"""

from __future__ import annotations

import ipaddress
import re
import threading
import time
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Callable
from urllib.parse import urlsplit

import requests

from backend.integrations.companyenrich import (
    CompanyEnrichCredential,
    discover_company_enrich_credentials,
)


COMPANY_ENRICH_BASE_URL = "https://api.companyenrich.com"
COMPANY_ENRICH_AUTOCOMPLETE_PATH = "/companies/autocomplete"
COMPANY_ENRICH_AUTOCOMPLETE_ENDPOINT = (
    f"{COMPANY_ENRICH_BASE_URL}{COMPANY_ENRICH_AUTOCOMPLETE_PATH}"
)
COMPANY_ENRICH_AUTOCOMPLETE_PROVIDER = "companyenrich_autocomplete"
COMPANY_ENRICH_AUTOCOMPLETE_MAX_RESULTS = 10

_LEGAL_SUFFIXES = {
    "ag",
    "co",
    "corp",
    "corporation",
    "gmbh",
    "inc",
    "incorporated",
    "kg",
    "limited",
    "llc",
    "ltd",
    "plc",
    "sa",
    "se",
}
_AMBIGUOUS_STATUS_MARKERS = {
    "ambiguous",
    "conflict",
    "missing",
    "not_found",
    "not-found",
    "unknown",
    "unresolved",
    "uncertain",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _public_host(host: str) -> str:
    normalized = host.casefold().rstrip(".")
    if normalized.startswith("www."):
        normalized = normalized[4:]
    if not normalized or "." not in normalized or "@" in normalized:
        return ""
    if normalized in {"localhost", "localhost.localdomain"} or normalized.endswith(
        (".localhost", ".local", ".internal")
    ):
        return ""
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        address = None
    if address is not None and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
    ):
        return ""
    return normalized


def normalize_domain(value: Any) -> str:
    """Return a public registrable-looking host, never a URL or private host."""

    raw = _text(value)
    if not raw:
        return ""
    candidate = raw if "://" in raw else f"https://{raw}"
    try:
        parsed = urlsplit(candidate)
        if parsed.scheme.casefold() not in {"http", "https"}:
            return ""
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            return ""
        if parsed.path not in {"", "/"}:
            return ""
        return _public_host(parsed.hostname or "")
    except ValueError:
        return ""


def _identity_tokens(value: Any) -> set[str]:
    normalized = unicodedata.normalize("NFKC", _text(value)).casefold()
    tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", normalized)
        if token and token not in _LEGAL_SUFFIXES
    }
    return tokens


def normalize_autocomplete_query(value: Any) -> str:
    """Normalize a company name/domain into the provider's required query."""

    raw = unicodedata.normalize("NFKC", _text(value))
    if not raw:
        return ""
    domain = normalize_domain(raw)
    if domain:
        return domain
    tokens = [
        token
        for token in re.split(r"[^a-zA-Z0-9]+", raw.casefold())
        if token and token not in _LEGAL_SUFFIXES
    ]
    return " ".join(tokens)


def _safe_logo_url(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme.casefold() not in {"http", "https"} or parsed.username or parsed.password:
        return ""
    if not _public_host(parsed.hostname or ""):
        return ""
    return raw


@dataclass(frozen=True, slots=True)
class AutocompleteSuggestion:
    name: str
    domain: str
    logo_url: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AutocompleteDecision:
    query: str
    status: str
    domain: str = ""
    name: str = ""
    confidence: float = 0.0
    reason: str = ""
    candidates: list[dict[str, str]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidates"] = [dict(candidate) for candidate in self.candidates]
        payload["provenance"] = dict(self.provenance)
        return payload


def should_attempt_autocomplete(row: Mapping[str, Any]) -> bool:
    """Return whether the row lacks a trusted official website/domain seed."""

    website = normalize_domain(
        row.get("website_url") or row.get("website") or row.get("domain")
    )
    status = _text(
        row.get("website_discovery_status")
        or row.get("website_status")
        or row.get("domain_status")
        or row.get("companyenrich_match_status")
    ).casefold()
    status = re.sub(r"[\s-]+", "_", status)
    return not website or any(marker in status for marker in _AMBIGUOUS_STATUS_MARKERS)


class CompanyEnrichAutocompleteAdapter:
    """Bounded adapter for the free CompanyEnrich autocomplete endpoint."""

    def __init__(
        self,
        *,
        credentials: Sequence[CompanyEnrichCredential | Mapping[str, Any]] | None = None,
        timeout_seconds: float = 12.0,
        request_budget: int = 10,
        max_retries: int = 1,
        max_concurrency: int = 1,
        cache_ttl_seconds: float = 86_400.0,
        request_get: Callable[..., Any] | None = None,
    ) -> None:
        raw_credentials = discover_company_enrich_credentials() if credentials is None else credentials
        normalized: list[CompanyEnrichCredential] = []
        for raw in raw_credentials:
            if isinstance(raw, CompanyEnrichCredential):
                credential = raw
            elif isinstance(raw, Mapping):
                credential = CompanyEnrichCredential(
                    _text(raw.get("name") or "slot"), _text(raw.get("token"))
                )
            else:
                continue
            if credential.token:
                normalized.append(credential)
        self.credentials = tuple(normalized)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.request_budget = max(0, int(request_budget))
        self.max_retries = max(0, int(max_retries))
        self.max_concurrency = max(1, int(max_concurrency))
        self.cache_ttl_seconds = max(0.0, float(cache_ttl_seconds))
        self._request_get = request_get or requests.get
        self._semaphore = threading.BoundedSemaphore(self.max_concurrency)
        self._lock = threading.RLock()
        self._requests = 0
        self._retry_count = 0
        self._cache_hits = 0
        self._provider_errors = 0
        self._budget_exhausted = 0
        self._cache: dict[str, tuple[float, tuple[AutocompleteSuggestion, ...], int]] = {}

    @classmethod
    def from_environment(cls, **kwargs: Any) -> "CompanyEnrichAutocompleteAdapter":
        return cls(credentials=discover_company_enrich_credentials(), **kwargs)

    @property
    def metrics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "requests": self._requests,
                "retry_count": self._retry_count,
                "cache_hits": self._cache_hits,
                "provider_errors": self._provider_errors,
                "budget_exhausted": self._budget_exhausted,
                "request_budget": self.request_budget,
                "max_retries": self.max_retries,
                "max_concurrency": self.max_concurrency,
                "zero_credit_intent": True,
            }

    def resolve_row(self, row: Mapping[str, Any]) -> AutocompleteDecision:
        return self.resolve(
            company_name=_text(row.get("company_name") or row.get("name")),
            existing_domain=normalize_domain(
                row.get("website_url") or row.get("website") or row.get("domain")
            ),
            identity_evidence=(
                _text(row.get("company_name") or row.get("name")),
                _text(row.get("linkedin_company_url") or row.get("linkedin_url")),
            ),
        )

    def resolve(
        self,
        *,
        company_name: str = "",
        existing_domain: str = "",
        identity_evidence: Sequence[str] = (),
    ) -> AutocompleteDecision:
        query = normalize_autocomplete_query(existing_domain or company_name)
        base_provenance = {
            "provider": COMPANY_ENRICH_AUTOCOMPLETE_PROVIDER,
            "endpoint": COMPANY_ENRICH_AUTOCOMPLETE_ENDPOINT,
            "query": query,
            "credit_intent": "free",
            "credit_cost": 0,
            "max_results": COMPANY_ENRICH_AUTOCOMPLETE_MAX_RESULTS,
        }
        if not query:
            return AutocompleteDecision(
                query="",
                status="rejected",
                reason="missing_query",
                provenance={**base_provenance, "result_count": 0},
            )
        if not self.credentials:
            return AutocompleteDecision(
                query=query,
                status="missing_credentials",
                reason="credentials_missing",
                provenance={**base_provenance, "result_count": 0},
            )

        fetched = self._fetch_suggestions(query)
        suggestions, fetch_status, fetch_reason, fetch_provenance = fetched
        provenance = {**base_provenance, **fetch_provenance}
        candidate_dicts = [suggestion.to_dict() for suggestion in suggestions]
        if fetch_status != "ok":
            return AutocompleteDecision(
                query=query,
                status=fetch_status,
                reason=fetch_reason,
                candidates=candidate_dicts,
                provenance=provenance,
            )
        if not suggestions:
            return AutocompleteDecision(
                query=query,
                status="rejected",
                reason="no_safe_candidates",
                candidates=[],
                provenance=provenance,
            )

        identity_values = tuple(value for value in (company_name, *identity_evidence) if _text(value))
        identity_tokens = set().union(*(_identity_tokens(value) for value in identity_values))
        scored: list[tuple[float, AutocompleteSuggestion]] = []
        for suggestion in suggestions:
            name_tokens = _identity_tokens(suggestion.name)
            domain_tokens = _identity_tokens(suggestion.domain.replace(".", " "))
            name_overlap = len(identity_tokens & name_tokens)
            domain_overlap = len(identity_tokens & domain_tokens)
            if not identity_tokens or not (name_overlap or domain_overlap):
                score = 0.0
            else:
                score = min(
                    1.0,
                    (name_overlap / len(identity_tokens)) * 0.45
                    + (name_overlap / len(name_tokens)) * 0.35
                    + (domain_overlap / len(domain_tokens)) * 0.20,
                )
            if existing_domain and suggestion.domain == normalize_domain(existing_domain):
                score = min(1.0, score + 0.2)
            scored.append((round(score, 4), suggestion))
        scored.sort(key=lambda item: (-item[0], item[1].domain))
        best_score, best = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        if best_score < 0.65:
            return AutocompleteDecision(
                query=query,
                status="rejected",
                reason="identity_evidence_did_not_match",
                confidence=best_score,
                candidates=candidate_dicts,
                provenance=provenance,
            )
        if len(scored) > 1 and best_score - second_score < 0.15:
            return AutocompleteDecision(
                query=query,
                status="ambiguous",
                reason="top_candidates_too_close",
                confidence=best_score,
                candidates=candidate_dicts,
                provenance=provenance,
            )
        return AutocompleteDecision(
            query=query,
            status="accepted",
            domain=best.domain,
            name=best.name,
            confidence=best_score,
            reason="identity_evidence_match",
            candidates=candidate_dicts,
            provenance={
                **provenance,
                "selected_domain": best.domain,
                "selected_name": best.name,
                "selected_confidence": best_score,
            },
        )

    def _fetch_suggestions(
        self, query: str
    ) -> tuple[tuple[AutocompleteSuggestion, ...], str, str, dict[str, Any]]:
        with self._lock:
            cached = self._cache.get(query)
            if cached is not None:
                cached_at, suggestions, result_count = cached
                if self.cache_ttl_seconds <= 0 or time.monotonic() - cached_at <= self.cache_ttl_seconds:
                    self._cache_hits += 1
                    return (
                        suggestions,
                        "ok",
                        "",
                        {"result_count": result_count, "cache_status": "hit", "request_count": 0},
                    )

        if not self.credentials:
            return (), "missing_credentials", "credentials_missing", {"result_count": 0}
        attempt = 0
        while True:
            with self._semaphore:
                with self._lock:
                    if self._requests >= self.request_budget:
                        self._budget_exhausted += 1
                        return (), "budget_exhausted", "request_budget_exhausted", {
                            "result_count": 0,
                            "request_count": 0,
                        }
                    self._requests += 1
                credential = self.credentials[0]
                try:
                    response = self._request_get(
                        COMPANY_ENRICH_AUTOCOMPLETE_ENDPOINT,
                        params={"query": query},
                        headers={
                            "Authorization": f"Bearer {credential.token}",
                            "Accept": "application/json",
                        },
                        timeout=self.timeout_seconds,
                    )
                except requests.RequestException:
                    status = 0
                else:
                    status = int(getattr(response, "status_code", 0) or 0)

                if status == 200:
                    try:
                        payload = response.json()
                    except (AttributeError, TypeError, ValueError):
                        payload = None
                    suggestions = self._parse_suggestions(payload)
                    valid_shape = isinstance(payload, list) or (
                        isinstance(payload, Mapping)
                        and isinstance(
                            payload.get("companies")
                            or payload.get("suggestions")
                            or payload.get("data"),
                            list,
                        )
                    )
                    if not valid_shape:
                        with self._lock:
                            self._provider_errors += 1
                        return (), "provider_error", "invalid_response_shape", {
                            "result_count": 0,
                            "request_count": 1,
                        }
                    with self._lock:
                        self._cache[query] = (time.monotonic(), suggestions, len(suggestions))
                    return suggestions, "ok", "", {
                        "result_count": len(suggestions),
                        "cache_status": "miss",
                        "request_count": 1,
                    }

                retryable = status == 429 or status >= 500 or status == 0
                if retryable and attempt < self.max_retries:
                    with self._lock:
                        budget_exhausted = self._requests >= self.request_budget
                    if budget_exhausted:
                        with self._lock:
                            self._budget_exhausted += 1
                        return (), "budget_exhausted", "request_budget_exhausted", {
                            "result_count": 0,
                            "request_count": attempt + 1,
                        }
                    attempt += 1
                    with self._lock:
                        self._retry_count += 1
                    continue
                with self._lock:
                    self._provider_errors += 1
                reason = f"http_{status}" if status else "transport_error"
                return (), "provider_error", reason, {"result_count": 0, "request_count": attempt + 1}

    @staticmethod
    def _parse_suggestions(payload: Any) -> tuple[AutocompleteSuggestion, ...]:
        if isinstance(payload, Mapping):
            payload = payload.get("companies") or payload.get("suggestions") or payload.get("data")
        if not isinstance(payload, list):
            return ()
        suggestions: list[AutocompleteSuggestion] = []
        for item in payload[:COMPANY_ENRICH_AUTOCOMPLETE_MAX_RESULTS]:
            if not isinstance(item, Mapping):
                continue
            domain = normalize_domain(item.get("domain"))
            name = _text(item.get("name"))
            if not domain or not name:
                continue
            suggestions.append(
                AutocompleteSuggestion(
                    name=name,
                    domain=domain,
                    logo_url=_safe_logo_url(item.get("logoUrl") or item.get("logo_url")),
                )
            )
        return tuple(suggestions)


__all__ = [
    "AutocompleteDecision",
    "AutocompleteSuggestion",
    "COMPANY_ENRICH_AUTOCOMPLETE_ENDPOINT",
    "COMPANY_ENRICH_AUTOCOMPLETE_MAX_RESULTS",
    "CompanyEnrichAutocompleteAdapter",
    "normalize_autocomplete_query",
    "normalize_domain",
    "should_attempt_autocomplete",
]
