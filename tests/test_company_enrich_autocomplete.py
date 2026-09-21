from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
import requests

from backend.connectors.company_enrich_autocomplete import (
    CompanyEnrichAutocompleteAdapter,
    normalize_autocomplete_query,
    normalize_domain,
)


@dataclass
class FakeResponse:
    status_code: int
    payload: Any = None
    headers: dict[str, str] | None = None

    def json(self) -> Any:
        return self.payload


AUTOCOMPLETE_FIXTURE = [
    {"name": "Adidas", "domain": "adidas.com", "logoUrl": "https://cdn.example/adidas.png"},
    {"name": "Adidas AG Careers", "domain": "careers-adidas.example"},
    {"name": "Adidas Labs", "domain": "adidas-labs.example"},
    {"name": "Adidas Retail", "domain": "adidas-retail.example"},
    {"name": "Adidas Sports", "domain": "adidas-sports.example"},
    {"name": "Adidas Supply", "domain": "adidas-supply.example"},
    {"name": "Adidas Europe", "domain": "adidas-europe.example"},
    {"name": "Adidas Digital", "domain": "adidas-digital.example"},
    {"name": "Adidas Finance", "domain": "adidas-finance.example"},
    {"name": "Adidas Research", "domain": "adidas-research.example"},
    {"name": "Adidas Archive", "domain": "adidas-archive.example"},
]


def test_normalizes_query_and_accepts_only_the_bounded_suggestion_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        return FakeResponse(200, AUTOCOMPLETE_FIXTURE)

    monkeypatch.setattr("backend.connectors.company_enrich_autocomplete.requests.get", fake_get)
    adapter = CompanyEnrichAutocompleteAdapter(
        credentials=[{"name": "test", "token": "secret-token"}],
        request_budget=3,
        max_retries=0,
    )

    decision = adapter.resolve(company_name="  Adidas, AG  ")

    assert normalize_autocomplete_query("  Adidas, AG  ") == "adidas"
    assert calls[0]["url"].endswith("/companies/autocomplete")
    assert calls[0]["params"] == {"query": "adidas"}
    assert calls[0]["headers"]["Authorization"] == "Bearer secret-token"
    assert decision.status == "accepted"
    assert decision.domain == "adidas.com"
    assert len(decision.candidates) == 10
    assert decision.provenance["credit_intent"] == "free"
    assert decision.provenance["credit_cost"] == 0
    assert "secret-token" not in repr(decision.to_dict())
    assert adapter.metrics["requests"] == 1
    assert adapter.metrics["zero_credit_intent"] is True


@pytest.mark.parametrize("status", [401, 402, 422])
def test_provider_auth_payment_and_validation_errors_fail_closed(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    monkeypatch.setattr(
        "backend.connectors.company_enrich_autocomplete.requests.get",
        lambda *_args, **_kwargs: FakeResponse(status, {"detail": "provider secret must not escape"}),
    )
    adapter = CompanyEnrichAutocompleteAdapter(
        credentials=[{"name": "test", "token": "secret-token"}],
        request_budget=3,
        max_retries=2,
    )

    decision = adapter.resolve(company_name="Acme GmbH")

    assert decision.status == "provider_error"
    assert decision.domain == ""
    assert decision.reason == f"http_{status}"
    assert "provider secret" not in repr(decision.to_dict())
    assert adapter.metrics["requests"] == 1


def test_rate_limit_retries_are_bounded_and_budget_exhaustion_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter([FakeResponse(429), FakeResponse(429), FakeResponse(200, AUTOCOMPLETE_FIXTURE)])
    monkeypatch.setattr(
        "backend.connectors.company_enrich_autocomplete.requests.get",
        lambda *_args, **_kwargs: next(responses),
    )
    adapter = CompanyEnrichAutocompleteAdapter(
        credentials=[{"name": "test", "token": "secret-token"}],
        request_budget=2,
        max_retries=5,
    )

    decision = adapter.resolve(company_name="Adidas")

    assert decision.status == "budget_exhausted"
    assert decision.reason == "request_budget_exhausted"
    assert adapter.metrics["requests"] == 2
    assert adapter.metrics["retry_count"] == 1


def test_transport_error_is_sanitized_and_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_transport_error(*_args: Any, **_kwargs: Any) -> FakeResponse:
        raise requests.ConnectionError("secret host response must not escape")

    monkeypatch.setattr(
        "backend.connectors.company_enrich_autocomplete.requests.get",
        raise_transport_error,
    )
    adapter = CompanyEnrichAutocompleteAdapter(
        credentials=[{"name": "test", "token": "secret-token"}],
        request_budget=2,
        max_retries=1,
    )

    decision = adapter.resolve(company_name="Acme")

    assert decision.status == "provider_error"
    assert decision.reason == "transport_error"
    assert "secret host response" not in repr(decision.to_dict())
    assert adapter.metrics["requests"] == 2


def test_ambiguous_and_unsafe_suggestions_are_deferred(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(
        [
            FakeResponse(
                200,
                [
                    {"name": "Acme", "domain": "acme.com"},
                    {"name": "Acme", "domain": "acme.de"},
                ],
            ),
            FakeResponse(
                200,
                [{"name": "Acme", "domain": "https://127.0.0.1/internal"}],
            ),
        ]
    )
    monkeypatch.setattr(
        "backend.connectors.company_enrich_autocomplete.requests.get",
        lambda *_args, **_kwargs: next(responses),
    )
    adapter = CompanyEnrichAutocompleteAdapter(
        credentials=[{"name": "test", "token": "secret-token"}],
        request_budget=4,
        max_retries=0,
    )

    ambiguous = adapter.resolve(company_name="Acme")
    unsafe = adapter.resolve(company_name="Acme Labs")

    assert ambiguous.status == "ambiguous"
    assert ambiguous.domain == ""
    assert ambiguous.reason == "top_candidates_too_close"
    assert unsafe.status == "rejected"
    assert unsafe.reason == "no_safe_candidates"


def test_cache_is_idempotent_and_missing_credentials_never_call_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(
        "backend.connectors.company_enrich_autocomplete.requests.get",
        lambda *_args, **_kwargs: calls.append(object()) or FakeResponse(200, AUTOCOMPLETE_FIXTURE),
    )
    adapter = CompanyEnrichAutocompleteAdapter(
        credentials=[{"name": "test", "token": "secret-token"}],
        request_budget=2,
        max_retries=0,
    )

    first = adapter.resolve(company_name="Adidas")
    second = adapter.resolve(company_name=" adidas ")
    missing = CompanyEnrichAutocompleteAdapter(request_budget=2).resolve(company_name="Acme")

    assert first.status == "accepted"
    assert second.status == "accepted"
    assert second.provenance["cache_status"] == "hit"
    assert len(calls) == 1
    assert missing.status == "missing_credentials"
    assert missing.reason == "credentials_missing"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://WWW.Example.com/", "example.com"),
        ("example.com", "example.com"),
        ("https://user:pass@example.com", ""),
        ("http://127.0.0.1", ""),
        ("localhost", ""),
        ("not-a-domain", ""),
    ],
)
def test_domain_normalization_is_public_host_only(raw: str, expected: str) -> None:
    assert normalize_domain(raw) == expected
