"""Null and local-fixture providers.

There is intentionally no HTTP client, URL opener, database handle, or object
storage dependency in this module.  These providers are safe for offline
contract and replay tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.domain.models import utc_now_iso

from .cache import input_fingerprint
from .contracts import (
    EnrichmentCandidate,
    EnrichmentProvider,
    EnrichmentRequest,
    EvidenceEnvelope,
    LicenceMetadata,
    ProviderCapability,
    ProviderExecutionContext,
    ProviderMetadata,
    ProviderResult,
    ProviderResultState,
)


_FIXTURE_LICENCE = LicenceMetadata(
    licence_id="runr_internal_fixture",
    attribution="Runr offline fixture",
    raw_storage_permitted=False,
)


def _fixture_metadata(provider_id: str, target_type: str, fields: tuple[str, ...]) -> ProviderMetadata:
    return ProviderMetadata(
        provider_id=provider_id,
        adapter_version="fixture_adapter_v1",
        dataset_version="runr_fixture_v1",
        snapshot_version="offline_fixture_2026_08",
        display_name=f"Runr {target_type} fixture provider",
        supported_target_types=(target_type,),
        supported_fields=fields,
        licence=_FIXTURE_LICENCE,
        network_required=False,
        default_cacheable=True,
    )


class NullProvider:
    """Fail-closed provider used when no enrichment provider is approved."""

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_id="null",
            adapter_version="null_provider_v1",
            display_name="No enrichment provider",
            licence=_FIXTURE_LICENCE,
            network_required=False,
        )

    def capability(self, request: EnrichmentRequest) -> ProviderCapability:
        del request
        return ProviderCapability(False, reason="provider_disabled_by_default", network_required=False, offline=True)

    def resolve(self, request: EnrichmentRequest, context: ProviderExecutionContext) -> ProviderResult:
        del request, context
        return ProviderResult(
            state=ProviderResultState.BLOCKED_BY_POLICY,
            warnings=("enrichment_provider_disabled_by_default",),
        )


class _FixtureProvider:
    target_type = ""
    fields: tuple[str, ...] = ()

    def __init__(self, fixtures: Mapping[str, Any] | None = None):
        self.fixtures = dict(fixtures or {})

    def metadata(self) -> ProviderMetadata:
        return _fixture_metadata(self.provider_id, self.target_type, self.fields)

    def capability(self, request: EnrichmentRequest) -> ProviderCapability:
        if request.target_type != self.target_type:
            return ProviderCapability(False, reason="target_type_not_supported")
        if request.field_path not in self.fields:
            return ProviderCapability(False, reason="field_not_supported")
        return ProviderCapability(True, reason="offline_fixture")

    def _lookup_key(self, request: EnrichmentRequest) -> str:
        raise NotImplementedError

    def _candidates(self, request: EnrichmentRequest, value: Any) -> tuple[EnrichmentCandidate, ...]:
        raw_candidates = value if isinstance(value, list) else [value]
        candidates: list[EnrichmentCandidate] = []
        for index, raw in enumerate(raw_candidates):
            if not isinstance(raw, Mapping):
                raw = {"normalized_value": raw}
            normalized = raw.get("normalized_value", raw.get("value"))
            if normalized is None:
                continue
            candidates.append(
                EnrichmentCandidate(
                    candidate_id=str(raw.get("candidate_id") or f"fixture_candidate_{index + 1}"),
                    normalized_value=normalized,
                    display_value=str(raw.get("display_value") or normalized),
                    provider_score=float(raw["provider_score"]) if raw.get("provider_score") is not None else None,
                    source_uri=str(raw.get("source_uri") or "offline://runr-fixture"),
                    source_record_id=str(raw.get("source_record_id") or ""),
                    source_field=str(raw.get("source_field") or request.field_path),
                    reason=str(raw.get("reason") or "fixture_candidate"),
                )
            )
        return tuple(candidates)

    def resolve(self, request: EnrichmentRequest, context: ProviderExecutionContext) -> ProviderResult:
        del context  # Offline fixtures have no external request to budget.
        capability = self.capability(request)
        if not capability.supported:
            return ProviderResult(state=ProviderResultState.UNSUPPORTED, warnings=(capability.reason,))
        value = self.fixtures.get(self._lookup_key(request))
        if value is None:
            return ProviderResult(state=ProviderResultState.NO_MATCH)
        candidates = self._candidates(request, value)
        if not candidates:
            return ProviderResult(state=ProviderResultState.NO_MATCH)
        state = ProviderResultState.AMBIGUOUS if len(candidates) > 1 else ProviderResultState.MATCHED
        fingerprint = input_fingerprint(request)
        now = utc_now_iso()
        evidence = tuple(
            EvidenceEnvelope(
                target_type=request.target_type,
                target_id=request.target_id,
                field_path=request.field_path,
                input_fingerprint=fingerprint,
                normalized_candidate_value=candidate.normalized_value,
                candidate_id=candidate.candidate_id,
                provider_id=self.metadata().provider_id,
                adapter_version=self.metadata().adapter_version,
                dataset_version=self.metadata().dataset_version,
                snapshot_version=self.metadata().snapshot_version,
                source_uri=candidate.source_uri,
                source_record_id=candidate.source_record_id,
                source_field=candidate.source_field,
                extraction_method="offline_fixture",
                observed_at=now,
                retrieved_at=now,
                licence=self.metadata().licence,
                terms_url=self.metadata().licence.terms_url,
                privacy_class="offline_fixture",
                retention_class="fixture",
                rule_version=request.rule_version,
                result_state=state,
                raw_storage_permitted=False,
                provider_score=candidate.provider_score,
            )
            for candidate in candidates
        )
        return ProviderResult(state=state, candidates=candidates, evidence=evidence)


class FixturePlaceProvider(_FixtureProvider):
    provider_id = "fixture_place"
    target_type = "place"
    fields = ("place", "city", "country", "job_location")

    DEFAULT_FIXTURES = {
        "paris|fr|": {"candidate_id": "geonames:2988507", "normalized_value": {"city": "Paris", "country_code": "FR"}},
        "paris|us|tx": {
            "candidate_id": "fixture:paris-tx",
            "normalized_value": {"city": "Paris", "region": "Texas", "country_code": "US"},
        },
        "paris|ca|on": {
            "candidate_id": "fixture:paris-on",
            "normalized_value": {"city": "Paris", "region": "Ontario", "country_code": "CA"},
        },
        "paris||": [
            {"candidate_id": "geonames:2988507", "normalized_value": {"city": "Paris", "country_code": "FR"}},
            {
                "candidate_id": "fixture:paris-tx",
                "normalized_value": {"city": "Paris", "region": "Texas", "country_code": "US"},
            },
            {
                "candidate_id": "fixture:paris-on",
                "normalized_value": {"city": "Paris", "region": "Ontario", "country_code": "CA"},
            },
        ],
        "lowell|us|ma": {
            "candidate_id": "fixture:lowell-ma",
            "normalized_value": {"city": "Lowell", "region": "Massachusetts", "country_code": "US"},
        },
        "leeds|gb|": {"candidate_id": "fixture:leeds-gb", "normalized_value": {"city": "Leeds", "country_code": "GB"}},
    }

    def __init__(self, fixtures: Mapping[str, Any] | None = None):
        super().__init__(self.DEFAULT_FIXTURES if fixtures is None else fixtures)

    def _lookup_key(self, request: EnrichmentRequest) -> str:
        value = request.input
        raw_display = str(value.get("display") or value.get("raw_display") or "").strip().casefold()
        display = raw_display
        if "," in display:
            display = display.split(",", 1)[0].strip()
        country = str(value.get("country_code") or "").strip().casefold()
        if not country:
            country = {
                "france": "fr",
                "uk": "gb",
                "united kingdom": "gb",
                "great britain": "gb",
            }.get(raw_display.rsplit(",", 1)[-1].strip(), "")
        region = str(value.get("region") or value.get("admin1") or "").strip().casefold()
        region = {"texas": "tx", "ontario": "on", "massachusetts": "ma"}.get(region, region)
        return f"{display}|{country}|{region}"


class FixtureCompanyProvider(_FixtureProvider):
    provider_id = "fixture_company"
    target_type = "company"
    fields = ("company_identity", "website", "headquarters", "industry", "company_size", "founded_year")

    DEFAULT_FIXTURES = {
        "domain:lowell.com": {
            "candidate_id": "fixture:company:lowell",
            "normalized_value": {
                "company_id": "fixture-company-lowell",
                "name": "Lowell",
                "website": "https://www.lowell.com",
                "industry": "Financial Services",
                "company_size": "1001-5000",
                "headquarters": "Leeds, United Kingdom",
            },
        },
        "domain:example.com": {
            "candidate_id": "fixture:company:example",
            "normalized_value": {
                "company_id": "fixture-company-example",
                "name": "Example GmbH",
                "website": "https://example.com",
                "industry": "Enterprise Software",
                "company_size": "51-200",
                "headquarters": "Berlin, Germany",
            },
        },
    }

    def __init__(self, fixtures: Mapping[str, Any] | None = None):
        super().__init__(self.DEFAULT_FIXTURES if fixtures is None else fixtures)

    def _lookup_key(self, request: EnrichmentRequest) -> str:
        value = request.input
        domain = str(value.get("domain") or "").strip().casefold()
        if domain:
            return f"domain:{domain.removeprefix('www.')}"
        name = " ".join(str(value.get("name") or "").casefold().split())
        return f"name:{name}"


class FixtureOccupationProvider(_FixtureProvider):
    provider_id = "fixture_occupation"
    target_type = "occupation"
    fields = ("occupation", "runr_function", "runr_subfunction")

    DEFAULT_FIXTURES = {
        "senior backend engineer": {
            "candidate_id": "fixture:occupation:software-developer",
            "normalized_value": {
                "taxonomy": "fixture",
                "occupation_id": "software-developer",
                "label": "Software Developer",
            },
        },
        "werkstudent data analyst": {
            "candidate_id": "fixture:occupation:data-analyst",
            "normalized_value": {"taxonomy": "fixture", "occupation_id": "data-analyst", "label": "Data Analyst"},
        },
        "comptable": {
            "candidate_id": "fixture:occupation:accountant",
            "normalized_value": {"taxonomy": "fixture", "occupation_id": "accountant", "label": "Accountant"},
        },
    }

    def __init__(self, fixtures: Mapping[str, Any] | None = None):
        super().__init__(self.DEFAULT_FIXTURES if fixtures is None else fixtures)

    def _lookup_key(self, request: EnrichmentRequest) -> str:
        return " ".join(str(request.input.get("title") or "").casefold().split())


__all__ = [
    "FixtureCompanyProvider",
    "FixtureOccupationProvider",
    "FixturePlaceProvider",
    "NullProvider",
]
