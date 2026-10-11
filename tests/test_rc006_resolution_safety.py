from __future__ import annotations

import json
from pathlib import Path

from scripts.run_linkedin_company_id_resolution import CreditLedger, ResolutionState, make_groups, resolve_one
from backend.application.company_enrichment_resolution import (
    MISSING_CANONICAL_ID,
    MISSING_LINKEDIN_URL,
    MISSING_WEBSITE,
    OWNERSHIP_CONFLICT,
    PersistentResolverSafety,
    SafetyConfig,
    enrichment_queues,
    merge_evidence,
    EvidenceCandidate,
)
from scripts.linkedin_company_enrichment_pipeline import FetchResponse


FIXTURES = Path(__file__).parent / "fixtures"


class FakeFetcher:
    def __init__(self, responses: list[FetchResponse]):
        self.responses = list(responses)
        self.calls: list[str] = []

    def fetch(self, url: str, *, kind: str = "html") -> FetchResponse:
        self.calls.append(url)
        if not self.responses:
            raise AssertionError("unexpected network call")
        return self.responses.pop(0)


class FakePool:
    def __init__(self, fetcher: FakeFetcher):
        self.fetcher = fetcher

    def get(self) -> dict[str, object]:
        return {"webshare": self.fetcher, "scrapeops": None, "playwright": None, "errors": {}}


def response(url: str, body: str, status: int = 200) -> FetchResponse:
    return FetchResponse(url, url, status, "text/html", body.encode("utf-8"), 1)


def group() -> dict[str, object]:
    return {
        "normalized_url": "https://www.linkedin.com/company/example/",
        "linkedin_slug": "example",
        "source_row_numbers": [2],
        "row_indices": [0],
        "canonical_company_ids": [],
        "input_evidence_fingerprint": "fixture",
    }


def test_queues_are_independent_and_conflicts_are_explicit() -> None:
    queues = enrichment_queues(
        {
            "canonical_CompanyID": "//",
            "website_url": "",
            "linkedin_company_url": "https://www.linkedin.com/company/acme/",
            "linkedin_company_id": "not-numeric",
            "canonical_company_ids": ["C-1", "C-2"],
        }
    )

    assert queues == (MISSING_CANONICAL_ID, MISSING_WEBSITE, "unresolved_numeric_id", OWNERSHIP_CONFLICT)
    assert MISSING_LINKEDIN_URL not in queues


def test_weaker_evidence_does_not_replace_user_confirmed_value() -> None:
    result = merge_evidence(
        EvidenceCandidate("C-1", "admin", strength="user_confirmed", user_confirmed=True),
        EvidenceCandidate("C-2", "discovery", strength="discovered"),
    )

    assert result.value == "C-1"
    assert result.status == "protected"
    assert result.conflict is True


def test_resolve_one_retains_contradictory_ids_across_responses(tmp_path: Path) -> None:
    url = "https://www.linkedin.com/company/example/jobs/"
    fetcher = FakeFetcher(
        [
            response(url, "urn:li:fsd_company:111 urn:li:fsd_company:222"),
            response("https://www.linkedin.com/company/example/", "urn:li:fsd_company:111"),
        ]
    )
    state = ResolutionState(tmp_path / "state")
    safety = PersistentResolverSafety(
        tmp_path / "state" / "safety.sqlite3",
        config=SafetyConfig(cooldown_base_seconds=0, cooldown_max_seconds=0, circuit_failure_threshold=10),
    )
    try:
        payload = resolve_one(
            group(),
            state=state,
            pool=FakePool(fetcher),
            ledger=CreditLedger(0),
            webshare_only=True,
            safety=safety,
        )
        assert payload["output_fields"]["linkedin_company_id_status"] == "AMBIGUOUS"
        assert payload["output_fields"]["linkedin_company_id"] == ""
        assert payload["observed_contextual_ids"] == ["111", "222"]
        assert payload["last_error"] == "contradictory_contextual_company_ids_requires_reconciliation"
        assert len(fetcher.calls) == 2
    finally:
        safety.close()
        state.close()


def test_same_response_multiple_ids_stays_ambiguous(tmp_path: Path) -> None:
    url = "https://www.linkedin.com/company/example/jobs/"
    fetcher = FakeFetcher([response(url, "companyId=111 companyId=222")])
    state = ResolutionState(tmp_path / "state")
    try:
        payload = resolve_one(group(), state=state, pool=FakePool(fetcher), ledger=CreditLedger(0), webshare_only=True)
        assert payload["output_fields"]["linkedin_company_id_status"] == "AMBIGUOUS"
        assert payload["observed_contextual_ids"] == ["111", "222"]
    finally:
        state.close()


def test_job_producer_ownership_grouping_is_separate_from_id_parsing() -> None:
    rows = [
        {"linkedin_company_url": "https://www.linkedin.com/company/example", "canonical_CompanyID": "C-1"},
        {"linkedin_company_url": "https://www.linkedin.com/company/example/", "canonical_CompanyID": "C-2"},
    ]

    groups, invalid = make_groups(rows)

    assert invalid == []
    assert len(groups) == 1
    grouped = next(iter(groups.values()))
    assert grouped["row_indices"] == [0, 1]
    assert grouped["canonical_company_ids"] == ["C-1", "C-2"]


def test_reconciliation_decision_is_required_before_resolution(tmp_path: Path) -> None:
    url = "https://www.linkedin.com/company/example/jobs/"
    fetcher = FakeFetcher([response(url, "urn:li:fsd_company:111 urn:li:fsd_company:222")])
    state = ResolutionState(tmp_path / "state")
    try:
        first = resolve_one(group(), state=state, pool=FakePool(fetcher), ledger=CreditLedger(0), webshare_only=True)
        assert first["output_fields"]["linkedin_company_id_status"] == "AMBIGUOUS"
        state.record_reconciliation_decision(
            group()["normalized_url"], selected_id="111", reviewer="reviewer-1", reason="admin ownership review"
        )
        second = resolve_one(group(), state=state, pool=FakePool(FakeFetcher([])), ledger=CreditLedger(0), webshare_only=True)
        assert second["output_fields"]["linkedin_company_id_status"] == "RESOLVED"
        assert second["output_fields"]["linkedin_company_id"] == "111"
        assert second["output_fields"]["linkedin_company_id_source"] == "reconciliation_decision"
    finally:
        state.close()


def test_retry_cooldown_and_budget_persist_across_restart(tmp_path: Path) -> None:
    now = [1000.0]
    config = SafetyConfig(
        total_request_limit=3,
        provider_request_limit=3,
        rolling_window_seconds=100,
        cooldown_base_seconds=10,
        cooldown_max_seconds=40,
        circuit_failure_threshold=10,
        scrapeops_credit_limit=2,
    )
    path = tmp_path / "safety.sqlite3"
    first = PersistentResolverSafety(path, config=config, clock=lambda: now[0])
    try:
        admitted = first.allow("u1", "scrapeops", estimated_cost=1)
        assert admitted.allowed
        first.record(admitted, normalized_url="u1", provider="scrapeops", classification="rate_limited", success=False, estimated_cost=1)
        assert first.retry_due("u1", providers=("scrapeops",)) is False
        blocked = first.allow("u1", "scrapeops", estimated_cost=1)
        assert blocked.allowed is False and blocked.reason == "cooldown"
    finally:
        first.close()

    now[0] += 10
    second = PersistentResolverSafety(path, config=config, clock=lambda: now[0])
    try:
        admitted = second.allow("u1", "scrapeops", estimated_cost=1)
        assert admitted.allowed
        second.record(admitted, normalized_url="u1", provider="scrapeops", classification="valid_html", success=True, estimated_cost=1)
        assert second.snapshot()["providers"]["scrapeops"]["requests"] == 2
        denied = second.allow("u2", "scrapeops", estimated_cost=1)
        assert denied.allowed is False and denied.reason == "provider_credit_budget_exhausted"
    finally:
        second.close()


def test_mostly_blocked_fixture_opens_and_recovers_circuit(tmp_path: Path) -> None:
    fixture = json.loads((FIXTURES / "rc006_mostly_blocked.json").read_text(encoding="utf-8"))
    now = [0.0]
    safety = PersistentResolverSafety(
        tmp_path / "safety.sqlite3",
        config=SafetyConfig(
            total_request_limit=4,
            provider_request_limit=4,
            cooldown_base_seconds=0,
            cooldown_max_seconds=0,
            circuit_failure_threshold=2,
            circuit_open_seconds=10,
        ),
        clock=lambda: now[0],
    )
    try:
        for index, item in enumerate(fixture["sequence"][:2]):
            decision = safety.allow(f"u{index}", fixture["provider"])
            assert decision.allowed
            safety.record(
                decision,
                normalized_url=f"u{index}",
                provider=fixture["provider"],
                classification=item["classification"],
                success=False,
            )
        denied = safety.allow("u2", "webshare")
        assert denied.allowed is False and denied.reason == "circuit_open"
        now[0] = 10
        probe = safety.allow("u2", "webshare")
        assert probe.allowed and probe.recovery_probe
        safety.record(probe, normalized_url="u2", provider="webshare", classification="valid_html", success=True)
        recovered = safety.allow("u3", "webshare")
        assert recovered.allowed
        assert safety.snapshot()["total_requests"] == 3
        assert fixture["expected"]["upper_request_bound"] >= safety.snapshot()["total_requests"]
    finally:
        safety.close()
