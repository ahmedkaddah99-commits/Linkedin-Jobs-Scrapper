"""Worker-only, company-target enrichment with verified-field semantics."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from backend.application.company_logo import LogoValidationError, ValidatedLogo, cache_logo, validate_logo
from backend.domain.models import utc_now_iso


COMPANY_ENRICHMENT_FIELDS = (
    "website",
    "industry",
    "company_size",
    "headquarters",
    "founded_year",
    "company_stage",
    "funding_stage",
    "total_funding",
    "funding_year",
    "benefits",
    "sponsorship",
    "leadership_type",
)
UNKNOWN_REASON = "not_verified_from_authoritative_company_source"


class CompanyEnrichmentProvider(Protocol):
    async def enrich(self, company: Mapping[str, Any], *, conditional: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class CompanyEnrichmentResult:
    fields: Mapping[str, Any]
    source: str = "verified_provider"
    provenance_url: str = ""
    observed_at: str = ""
    verified_at: str = ""
    logo_bytes: bytes | None = None
    logo_source_url: str = ""
    logo_content_type: str = ""
    request_count: int = 1
    cost_units: float = 0.0


class OfficialWebsiteProvider:
    """Small, conservative parser for explicit Organization structured data.

    It deliberately does not turn free-form prose into company facts. A deployment
    can replace this provider with a licensed source adapter while retaining the
    same bounded/idempotent worker contract.
    """

    def __init__(self, *, timeout_seconds: int = 10, max_html_bytes: int = 512_000):
        self.timeout_seconds = max(2, int(timeout_seconds))
        self.max_html_bytes = max(32_000, int(max_html_bytes))

    @staticmethod
    def _fetch(url: str, *, timeout_seconds: int, max_bytes: int) -> tuple[bytes, str, str, Mapping[str, str]]:
        request = Request(url, headers={"User-Agent": "Runr-company-verifier/1.0", "Accept": "text/html,application/xhtml+xml"})
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - worker-only, bounded official URL fetch
            return bytes(response.read(max_bytes + 1)), str(response.headers.get("content-type") or ""), str(response.url or url), dict(response.headers.items())

    @staticmethod
    def _json_ld(html: str) -> Mapping[str, Any]:
        for raw in re.findall(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", html, flags=re.IGNORECASE | re.DOTALL):
            try:
                payload = json.loads(raw.strip())
            except (TypeError, ValueError):
                continue
            candidates = payload if isinstance(payload, list) else [payload]
            if isinstance(payload, Mapping) and isinstance(payload.get("@graph"), list):
                candidates.extend(payload["@graph"])
            for candidate in candidates:
                if not isinstance(candidate, Mapping):
                    continue
                types = candidate.get("@type")
                names = {str(item).casefold() for item in (types if isinstance(types, list) else [types])}
                if names & {"organization", "corporation", "localbusiness", "person"}:
                    return candidate
        return {}

    @staticmethod
    def _address(value: Any) -> str | None:
        if not isinstance(value, Mapping):
            return str(value).strip() if value not in (None, "") else None
        parts = [value.get(name) for name in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry")]
        result = ", ".join(str(item).strip() for item in parts if str(item or "").strip())
        return result or None

    @staticmethod
    def _explicit_fields(data: Mapping[str, Any]) -> dict[str, Any]:
        mapping = {
            "url": "website",
            "industry": "industry",
            "companySize": "company_size",
            "headquarters": "headquarters",
            "foundingDate": "founded_year",
            "companyStage": "company_stage",
            "fundingStage": "funding_stage",
            "totalFunding": "total_funding",
            "fundingYear": "funding_year",
            "benefits": "benefits",
            "sponsorship": "sponsorship",
            "leadershipType": "leadership_type",
        }
        result: dict[str, Any] = {}
        for source_name, field_name in mapping.items():
            if data.get(source_name) not in (None, "", []):
                result[field_name] = data[source_name]
        employees = data.get("numberOfEmployees")
        if isinstance(employees, Mapping) and employees.get("value") not in (None, ""):
            result.setdefault("company_size", employees.get("value"))
        if "address" in data and "headquarters" not in result:
            address = OfficialWebsiteProvider._address(data.get("address"))
            if address:
                result["headquarters"] = address
        if isinstance(result.get("founding_year"), str):
            match = re.fullmatch(r"\s*(\d{4})(?:-\d{2}(?:-\d{2})?)?\s*", result["founding_year"])
            result["founding_year"] = int(match.group(1)) if match else None
        return {key: value for key, value in result.items() if value not in (None, "", [])}

    async def enrich(self, company: Mapping[str, Any], *, conditional: Mapping[str, Any]) -> Mapping[str, Any]:
        del conditional
        source_url = str(company.get("provenance_url") or "").strip()
        parsed = urlparse(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return {"fields": {}, "source": "official_company_website", "provenance_url": source_url, "request_count": 0}
        body, content_type, final_url, headers = await asyncio.to_thread(
            self._fetch, source_url, timeout_seconds=self.timeout_seconds, max_bytes=self.max_html_bytes
        )
        if len(body) > self.max_html_bytes or "html" not in content_type.casefold():
            return {"fields": {}, "source": "official_company_website", "provenance_url": final_url, "request_count": 1}
        data = self._json_ld(body.decode("utf-8", errors="replace"))
        fields = self._explicit_fields(data)
        result: dict[str, Any] = {
            "fields": fields,
            "source": "official_company_website",
            "provenance_url": final_url,
            "observed_at": utc_now_iso(),
            "verified_at": utc_now_iso() if fields else "",
            "request_count": 1,
            "cost_units": 0.0,
        }
        logo_url = data.get("logo") if isinstance(data.get("logo"), str) else ""
        logo_parsed = urlparse(str(logo_url))
        source_host = parsed.hostname or ""
        logo_host = logo_parsed.hostname or ""
        same_official_host = bool(source_host and logo_host and (logo_host.casefold() == source_host.casefold() or logo_host.casefold().endswith("." + source_host.casefold())))
        if logo_url and logo_parsed.scheme in {"http", "https"} and same_official_host:
            logo_body, logo_type, logo_final_url, _ = await asyncio.to_thread(
                self._fetch, str(logo_url), timeout_seconds=self.timeout_seconds, max_bytes=2 * 1024 * 1024
            )
            result.update({"logo_bytes": logo_body, "logo_content_type": logo_type, "logo_source_url": logo_final_url, "request_count": 2})
        del headers
        return result


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_result(value: Mapping[str, Any]) -> CompanyEnrichmentResult:
    fields = value.get("fields") if isinstance(value.get("fields"), Mapping) else {}
    return CompanyEnrichmentResult(
        fields=dict(fields), source=str(value.get("source") or "verified_provider"),
        provenance_url=str(value.get("provenance_url") or value.get("url") or ""),
        observed_at=str(value.get("observed_at") or ""), verified_at=str(value.get("verified_at") or ""),
        logo_bytes=bytes(value["logo_bytes"]) if value.get("logo_bytes") is not None else None,
        logo_source_url=str(value.get("logo_source_url") or ""), logo_content_type=str(value.get("logo_content_type") or ""),
        request_count=max(0, int(value.get("request_count") or 0)), cost_units=max(0.0, float(value.get("cost_units") or 0)),
    )


def _known(value: Any) -> bool:
    return value not in (None, "", []) and not (isinstance(value, str) and value.strip().casefold() in {"unknown", "n/a", "not disclosed", "undisclosed"})


def _valid_value(field: str, value: Any, *, now_year: int) -> Any:
    if not _known(value):
        return None
    if field == "website":
        parsed = urlparse(str(value).strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        return parsed._replace(fragment="").geturl()
    if field in {"founded_year", "funding_year"}:
        try:
            year = int(value)
        except (TypeError, ValueError):
            return None
        return year if 1800 <= year <= now_year + 1 else None
    if field == "total_funding":
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return None
        if amount < 0:
            return None
        return int(amount) if amount.is_integer() else amount
    if field == "benefits":
        values = value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else [value]
        cleaned = [str(item).strip() for item in values if _known(item)]
        return list(dict.fromkeys(cleaned)) or None
    if isinstance(value, (str, int, float, bool)):
        return value
    return None


class CompanyEnrichmentService:
    def __init__(self, *, repositories: Any, object_storage: Any, profile_writer: Any, provider: CompanyEnrichmentProvider | None = None, lease_owner: str = "company-enrichment-worker"):
        self.repositories = repositories
        self.object_storage = object_storage
        self.profile_writer = profile_writer
        self.provider = provider or OfficialWebsiteProvider()
        self.lease_owner = lease_owner

    @property
    def store(self):
        return getattr(self.repositories, "personalized_jobs_store", None)

    async def run(
        self,
        *,
        max_companies: int = 25,
        concurrency: int = 5,
        request_budget: int = 25,
        cycle_key: str = "",
        force: bool = False,
    ) -> dict[str, Any]:
        store = self.store
        if store is None:
            return {"status": "unavailable", "companies_processed": 0}
        now = _now()
        cycle_key = cycle_key or now.strftime("%Y-%m-%d")
        candidates = store.list_company_enrichment_targets(now=now.isoformat(), limit=max(1, int(max_companies)))
        if force and not candidates:
            candidates = store.list_company_enrichment_targets(now="9999-12-31T00:00:00+00:00", limit=max(1, int(max_companies)))
        semaphore = asyncio.Semaphore(max(1, int(concurrency)))
        budget = max(0, int(request_budget))
        budget_lock = asyncio.Lock()
        totals = {"status": "completed", "cycle_key": cycle_key, "companies_considered": len(candidates), "companies_processed": 0, "companies_succeeded": 0, "requests": 0, "cost_units": 0.0, "fields_available": 0, "fields_written": 0, "logos_cached": 0, "failures": 0}

        async def process(candidate: Mapping[str, Any]) -> None:
            nonlocal budget
            async with semaphore:
                current = _now()
                claimed = store.claim_company_enrichment_target(
                    str(candidate.get("company_id") or ""), cycle_key=cycle_key, lease_owner=self.lease_owner,
                    lease_expires_at=(current + timedelta(minutes=10)).isoformat(), now=current.isoformat(),
                )
                if claimed is None:
                    return
                attempt_id = str(claimed["attempt_id"])
                try:
                    async with budget_lock:
                        if budget <= 0:
                            raise RuntimeError("company_enrichment_request_budget_exhausted")
                        budget -= 1
                    conditional = {
                        "logo_content_hash": str(claimed.get("logo_content_hash") or ""),
                        "logo_verified_at": str(claimed.get("logo_verified_at") or ""),
                        "profile_updated_at": str(claimed.get("profile_updated_at") or ""),
                    }
                    raw = await self.provider.enrich(claimed, conditional=conditional)
                    result = raw if isinstance(raw, CompanyEnrichmentResult) else _as_result(raw)
                    observed_at = result.observed_at or current.isoformat()
                    verified_at = result.verified_at or (current.isoformat() if result.fields else "")
                    fields: dict[str, Any] = {}
                    fields_available = 0
                    for field in COMPANY_ENRICHMENT_FIELDS:
                        raw_field = result.fields.get(field)
                        raw_value = raw_field.get("value") if isinstance(raw_field, Mapping) else raw_field
                        value = _valid_value(field, raw_value, now_year=current.year)
                        if value is not None:
                            fields_available += 1
                            field_source = raw_field.get("source") if isinstance(raw_field, Mapping) else result.source
                            field_url = raw_field.get("url") if isinstance(raw_field, Mapping) else result.provenance_url
                            fields[field] = {"value": value, "state": "known", "status": "known", "provenance": {"source": str(field_source or result.source), "url": str(field_url or result.provenance_url)}, "observed_at": str(raw_field.get("observed_at") if isinstance(raw_field, Mapping) else observed_at), "verified_at": str(raw_field.get("verified_at") if isinstance(raw_field, Mapping) else verified_at)}
                        else:
                            fields[field] = {"value": None, "state": "unknown", "status": "unknown", "provenance": {}, "observed_at": observed_at, "verified_at": "", "unknown_reason": UNKNOWN_REASON}
                    logo_key = ""
                    logo_cached = False
                    if result.logo_bytes is not None:
                        validated = validate_logo(result.logo_bytes, result.logo_content_type)
                        logo_key, logo_cached = cache_logo(self.object_storage, str(claimed["company_id"]), validated)
                    payload = {"schema_version": "phase_f_v2", "fields": fields, "source": result.source, "provenance_url": result.provenance_url, "observed_at": observed_at, "verified_at": verified_at}
                    written = self.profile_writer(str(claimed["company_id"]), payload, logo_bytes=result.logo_bytes, logo_source_url=result.logo_source_url, logo_content_type=result.logo_content_type) if result.logo_bytes is not None else self.profile_writer(str(claimed["company_id"]), payload)
                    del written
                    finish = store.finish_company_enrichment_attempt(
                        attempt_id, status="succeeded", request_count=result.request_count, cost_units=result.cost_units,
                        fields_available=fields_available, fields_written=fields_available, logo_cached=logo_cached,
                        yield_payload={"fields": [field for field in COMPANY_ENRICHMENT_FIELDS if fields[field]["state"] == "known"], "logo": bool(logo_key)},
                        next_attempt_at=(current + timedelta(days=30)).isoformat(), now=_now().isoformat(),
                    )
                    totals["companies_processed"] += 1; totals["companies_succeeded"] += 1; totals["requests"] += int(finish.get("request_count") or 0); totals["cost_units"] += float(finish.get("cost_units") or 0); totals["fields_available"] += fields_available; totals["fields_written"] += fields_available; totals["logos_cached"] += int(logo_cached)
                except Exception as exc:
                    store.finish_company_enrichment_attempt(
                        attempt_id, status="failed", request_count=0, cost_units=0, fields_available=0, fields_written=0, logo_cached=False,
                        error_code=type(exc).__name__, error_message=str(exc), next_attempt_at=(_now() + timedelta(hours=6)).isoformat(), now=_now().isoformat(),
                    )
                    totals["companies_processed"] += 1; totals["failures"] += 1

        await asyncio.gather(*(process(candidate) for candidate in candidates))
        if totals["failures"]:
            totals["status"] = "degraded"
        return totals

    def run_sync(self, **kwargs: Any) -> dict[str, Any]:
        return asyncio.run(self.run(**kwargs))


__all__ = ["COMPANY_ENRICHMENT_FIELDS", "CompanyEnrichmentResult", "CompanyEnrichmentService", "OfficialWebsiteProvider"]
