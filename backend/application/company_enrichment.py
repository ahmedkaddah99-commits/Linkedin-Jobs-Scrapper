"""Worker-only, company-target enrichment with verified-field semantics."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from bs4 import BeautifulSoup

from backend.integrations.scrapeops import (
    SCRAPEOPS_PROXY_ENDPOINT,
    build_proxy_params,
    estimate_mode_native_credits,
    parse_proxy_response_envelope,
    raise_for_failure,
    scrapeops_request_with_retry,
)

from backend.application.company_logo import (
    LogoValidationError,
    assert_public_official_host,
    cache_logo,
    validate_logo,
    validate_official_url,
)
from backend.domain.models import utc_now_iso


COMPANY_ENRICHMENT_FIELDS = (
    "website",
    "careers_page",
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


class _SafeOfficialRedirectHandler(HTTPRedirectHandler):
    def __init__(self, *, approved_host: str):
        super().__init__()
        self.approved_host = approved_host

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        target = validate_official_url(urljoin(request.full_url, newurl), approved_host=self.approved_host)
        assert_public_official_host(urlparse(target).hostname or "")
        return super().redirect_request(request, fp, code, msg, headers, target)


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
    extra_fields: Mapping[str, Any] | None = None
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
    def _fetch(
        url: str,
        *,
        timeout_seconds: int,
        max_bytes: int,
        approved_host: str = "",
    ) -> tuple[bytes, str, str, Mapping[str, str]]:
        safe_url = validate_official_url(url, approved_host=approved_host)
        assert_public_official_host(urlparse(safe_url).hostname or "")
        request = Request(safe_url, headers={"User-Agent": "Runr-company-verifier/1.0", "Accept": "text/html,application/xhtml+xml"})
        opener = build_opener(_SafeOfficialRedirectHandler(approved_host=approved_host))
        with opener.open(request, timeout=timeout_seconds) as response:  # noqa: S310 - worker-only, bounded official URL fetch
            final_url = validate_official_url(str(response.url or safe_url), approved_host=approved_host)
            assert_public_official_host(urlparse(final_url).hostname or "")
            headers = dict(response.headers.items())
            try:
                declared_size = int(str(headers.get("Content-Length") or "").strip())
            except ValueError:
                declared_size = 0
            if declared_size > max_bytes:
                raise LogoValidationError("official_response_too_large")
            body = bytes(response.read(max_bytes + 1))
            if len(body) > max_bytes:
                raise LogoValidationError("official_response_too_large")
            return body, str(headers.get("content-type") or ""), final_url, headers

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
            "careersPage": "careers_page",
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
        try:
            source_url = validate_official_url(source_url)
        except LogoValidationError:
            return {"fields": {}, "source": "official_company_website", "provenance_url": source_url, "request_count": 0}
        parsed = urlparse(source_url)
        source_host = parsed.hostname or ""
        body, content_type, final_url, headers = await asyncio.to_thread(
            self._fetch,
            source_url,
            timeout_seconds=self.timeout_seconds,
            max_bytes=self.max_html_bytes,
            approved_host=source_host,
        )
        if len(body) > self.max_html_bytes or "html" not in content_type.casefold():
            return {"fields": {}, "source": "official_company_website", "provenance_url": final_url, "request_count": 1}
        html_text = body.decode("utf-8", errors="replace")
        data = self._json_ld(html_text)
        fields = self._explicit_fields(data)
        # Career links are often navigation data rather than JSON-LD. Keep
        # discovery on the approved official host and accept only clearly
        # career/job-related links.
        soup = BeautifulSoup(html_text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = urljoin(final_url, str(link.get("href") or "").strip())
            label = " ".join(link.get_text(" ", strip=True).casefold().split())
            path = (urlparse(href).path or "").casefold()
            if not (
                "career" in label
                or "job" in label
                or "karriere" in label
                or any(token in path for token in ("/career", "/jobs", "/karriere", "/stellen"))
            ):
                continue
            try:
                safe_careers_url = validate_official_url(href, approved_host=source_host)
                assert_public_official_host(urlparse(safe_careers_url).hostname or "")
            except LogoValidationError:
                continue
            fields.setdefault("careers_page", safe_careers_url)
            break
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
        try:
            safe_logo_url = validate_official_url(logo_url, approved_host=source_host) if logo_url else ""
        except LogoValidationError:
            safe_logo_url = ""
        if safe_logo_url:
            logo_body, logo_type, logo_final_url, _ = await asyncio.to_thread(
                self._fetch,
                safe_logo_url,
                timeout_seconds=self.timeout_seconds,
                max_bytes=2 * 1024 * 1024,
                approved_host=source_host,
            )
            result.update({"logo_bytes": logo_body, "logo_content_type": logo_type, "logo_source_url": logo_final_url, "request_count": 2})
        del headers
        return result


class ScrapeOpsCompanyProvider(OfficialWebsiteProvider):
    """Enrich company pages through the configured ScrapeOps proxy."""

    def __init__(
        self,
        *,
        api_key: str = "",
        mode: str = "",
        timeout_seconds: int = 30,
        max_html_bytes: int = 1_000_000,
        max_retries: int = 2,
    ):
        super().__init__(timeout_seconds=timeout_seconds, max_html_bytes=max_html_bytes)
        self.api_key = str(api_key or os.getenv("SCRAPEOPS_API_KEY") or "").strip()
        self.max_retries = max(0, int(max_retries))
        configured_mode = str(mode or os.getenv("RUNR_COMPANY_ENRICHMENT_SCRAPEOPS_MODE") or "basic").strip()
        allowed_modes = {"basic", "render_js_cheap", "render_js", "residential", "render_js_residential"}
        self.mode = configured_mode if configured_mode in allowed_modes else "basic"

    def _proxy_fetch(self, url: str, *, raw: bool = False) -> tuple[bytes, str, str, int, float]:
        if not self.api_key:
            raise ValueError("SCRAPEOPS_API_KEY is required for ScrapeOps company enrichment.")
        safe_url = validate_official_url(url)
        assert_public_official_host(urlparse(safe_url).hostname or "")
        params = build_proxy_params(api_key=self.api_key, url=safe_url, mode=self.mode)
        if raw:
            params.pop("json_response", None)
        retry = scrapeops_request_with_retry(
            "GET",
            SCRAPEOPS_PROXY_ENDPOINT,
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries,
            params=params,
            headers={"User-Agent": "Runr-company-verifier/1.0", "Accept": "*/*" if raw else "text/html,application/xhtml+xml"},
        )
        response = retry.response
        if response is None:
            raise_for_failure(None, fallback_message="ScrapeOps company request failed.")
        if int(response.status_code or 0) >= 400:
            raise_for_failure(response, fallback_message="ScrapeOps company request failed.")
        if raw:
            content_type = str(response.headers.get("content-type") or "")
            return bytes(response.content), content_type, safe_url, retry.attempts, float(estimate_mode_native_credits(self.mode))
        envelope = parse_proxy_response_envelope(response)
        if envelope.target_status_code >= 500:
            raise_for_failure(response, fallback_message="ScrapeOps could not retrieve the company page.")
        return (
            envelope.body.encode("utf-8", errors="replace"),
            str(envelope.payload.get("content_type") or response.headers.get("content-type") or "text/html"),
            safe_url,
            retry.attempts,
            float(envelope.billed_credits_actual or estimate_mode_native_credits(self.mode)),
        )

    @staticmethod
    def _extra_fields(data: Mapping[str, Any], *, final_url: str, html_text: str) -> dict[str, Any]:
        address = data.get("address") if isinstance(data.get("address"), Mapping) else {}
        contact_value = data.get("contactPoint")
        contacts = contact_value if isinstance(contact_value, list) else [contact_value]
        contact = next((item for item in contacts if isinstance(item, Mapping)), {})
        employee = data.get("numberOfEmployees")
        if isinstance(employee, Mapping):
            employee_count = employee.get("value")
            employee_min = employee.get("minValue")
            employee_max = employee.get("maxValue")
        else:
            employee_count, employee_min, employee_max = employee, None, None
        logo = data.get("logo")
        if isinstance(logo, Mapping):
            logo = logo.get("url") or logo.get("contentUrl")
        same_as = data.get("sameAs")
        if isinstance(same_as, str):
            same_as = [same_as]
        knows_about = data.get("knowsAbout")
        if isinstance(knows_about, str):
            knows_about = [knows_about]
        result: dict[str, Any] = {
            "legal_name": data.get("legalName"),
            "alternate_names": data.get("alternateName"),
            "description": data.get("description"),
            "employee_count": employee_count,
            "employee_min": employee_min,
            "employee_max": employee_max,
            "contact_email": data.get("email") or contact.get("email"),
            "phone": data.get("telephone") or contact.get("telephone"),
            "social_profiles": same_as,
            "logo_url": logo,
            "address_street": address.get("streetAddress"),
            "address_locality": address.get("addressLocality"),
            "address_region": address.get("addressRegion"),
            "postal_code": address.get("postalCode"),
            "country": address.get("addressCountry"),
            "founded_date": data.get("foundingDate"),
            "specialties": knows_about,
            "area_served": data.get("areaServed"),
            "parent_organization": data.get("parentOrganization"),
            "stock_ticker": data.get("tickerSymbol"),
            "schema_type": data.get("@type"),
        }
        soup = BeautifulSoup(html_text, "html.parser")
        meta = {
            str(item.get("property") or item.get("name") or "").casefold(): str(item.get("content") or "").strip()
            for item in soup.find_all("meta")
            if str(item.get("content") or "").strip()
        }
        result.update({
            "open_graph_site_name": meta.get("og:site_name"),
            "open_graph_description": meta.get("og:description"),
            "open_graph_image": meta.get("og:image"),
            "canonical_url": final_url,
        })
        return {key: value for key, value in result.items() if value not in (None, "", [])}

    async def enrich(self, company: Mapping[str, Any], *, conditional: Mapping[str, Any]) -> Mapping[str, Any]:
        del conditional
        source_url = str(company.get("provenance_url") or "").strip()
        try:
            source_url = validate_official_url(source_url)
        except LogoValidationError:
            return {"fields": {}, "extra_fields": {}, "source": "scrapeops_company_website", "provenance_url": source_url, "request_count": 0}
        body, content_type, final_url, attempts, cost_units = await asyncio.to_thread(self._proxy_fetch, source_url)
        if len(body) > self.max_html_bytes or "html" not in content_type.casefold():
            return {"fields": {}, "extra_fields": {}, "source": "scrapeops_company_website", "provenance_url": final_url, "request_count": attempts, "cost_units": cost_units}
        html_text = body.decode("utf-8", errors="replace")
        data = self._json_ld(html_text)
        fields = self._explicit_fields(data)
        fields.setdefault("website", final_url)
        soup = BeautifulSoup(html_text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = urljoin(final_url, str(link.get("href") or "").strip())
            label = " ".join(link.get_text(" ", strip=True).casefold().split())
            path = (urlparse(href).path or "").casefold()
            if not ("career" in label or "job" in label or "karriere" in label or any(token in path for token in ("/career", "/jobs", "/karriere", "/stellen"))):
                continue
            try:
                safe_careers_url = validate_official_url(href, approved_host=urlparse(final_url).hostname or "")
                assert_public_official_host(urlparse(safe_careers_url).hostname or "")
            except LogoValidationError:
                continue
            fields.setdefault("careers_page", safe_careers_url)
            break
        extra_fields = self._extra_fields(data, final_url=final_url, html_text=html_text)
        result: dict[str, Any] = {
            "fields": fields,
            "extra_fields": extra_fields,
            "source": "scrapeops_company_website",
            "provenance_url": final_url,
            "observed_at": utc_now_iso(),
            "verified_at": utc_now_iso() if fields or extra_fields else "",
            "request_count": attempts,
            "cost_units": cost_units,
        }
        logo_url = str(extra_fields.get("logo_url") or extra_fields.get("open_graph_image") or "").strip()
        try:
            logo_url = validate_official_url(urljoin(final_url, logo_url), approved_host=urlparse(final_url).hostname or "") if logo_url else ""
        except LogoValidationError:
            logo_url = ""
        if logo_url:
            logo_body, logo_type, logo_final_url, logo_attempts, logo_cost = await asyncio.to_thread(self._proxy_fetch, logo_url, raw=True)
            result.update({"logo_bytes": logo_body, "logo_content_type": logo_type, "logo_source_url": logo_final_url, "request_count": attempts + logo_attempts, "cost_units": cost_units + logo_cost})
        return result


def _linkedin_company_url(value: Any) -> str:
    """Return a canonical public LinkedIn company URL, or an empty string."""

    try:
        parsed = urlparse(str(value or "").strip())
    except (TypeError, ValueError):
        return ""
    host = str(parsed.hostname or "").casefold()
    path_parts = [part for part in str(parsed.path or "").split("/") if part]
    if not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        return ""
    if len(path_parts) < 2 or path_parts[0].casefold() != "company":
        return ""
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "", unquote(path_parts[1])).strip(".-_")
    if not slug:
        return ""
    return f"https://www.linkedin.com/company/{slug}"


def _company_name_tokens(value: Any) -> set[str]:
    legal_suffixes = {
        "ag", "bv", "co", "company", "corp", "corporation", "gmbh", "inc", "international",
        "kg", "limited", "llc", "ltd", "plc", "sa", "se", "spa", "the",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(value or "").casefold())
        if token not in legal_suffixes and len(token) > 1
    }


def _linkedin_identity_matches(company_name: Any, page_name: Any) -> bool:
    expected = _company_name_tokens(company_name)
    observed = _company_name_tokens(page_name)
    if not expected or not observed:
        return bool(page_name)
    if expected <= observed or observed <= expected:
        return True
    overlap = len(expected & observed)
    return overlap >= 1 and overlap / max(1, min(len(expected), len(observed))) >= 0.5


class ScrapeOpsLinkedInCompanyProvider(ScrapeOpsCompanyProvider):
    """Discover and enrich public LinkedIn company pages through ScrapeOps.

    Discovery starts with LinkedIn URLs already present in authoritative
    Organization metadata. If none is available, a bounded DuckDuckGo HTML
    search discovers a candidate and the candidate page is identity-checked
    against the canonical company name before any facts are accepted.
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        mode: str = "",
        timeout_seconds: int = 12,
        max_html_bytes: int = 1_000_000,
        max_retries: int = 0,
    ):
        super().__init__(
            api_key=api_key,
            mode=mode or os.getenv("RUNR_COMPANY_ENRICHMENT_LINKEDIN_SCRAPEOPS_MODE") or "render_js_cheap",
            timeout_seconds=timeout_seconds,
            max_html_bytes=max_html_bytes,
            max_retries=max_retries,
        )

    @staticmethod
    def _existing_linkedin_urls(company: Mapping[str, Any]) -> list[str]:
        profile_json = company.get("profile_json")
        try:
            profile = json.loads(profile_json) if isinstance(profile_json, str) else profile_json
        except (TypeError, ValueError):
            profile = {}
        if not isinstance(profile, Mapping):
            return []
        extra = profile.get("additional_fields") if isinstance(profile.get("additional_fields"), Mapping) else {}
        candidates: list[Any] = []
        linkedin_field = extra.get("linkedin_company_url")
        candidates.append(linkedin_field.get("value") if isinstance(linkedin_field, Mapping) else linkedin_field)
        social = extra.get("social_profiles")
        social_value = social.get("value") if isinstance(social, Mapping) else social
        candidates.extend(social_value if isinstance(social_value, Sequence) and not isinstance(social_value, (str, bytes)) else [social_value])
        result: list[str] = []
        for candidate in candidates:
            normalized = _linkedin_company_url(candidate)
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    def _direct_fetch(self, url: str, *, raw: bool = False) -> tuple[bytes, str, str, int, float]:
        """Fetch a public LinkedIn/search response when the proxy is unavailable.

        ScrapeOps remains the primary transport. The direct fallback is bounded,
        HTTPS-only, public-host validated, and recorded separately in provenance
        so a transient proxy outage does not discard otherwise usable LinkedIn
        facts.
        """

        safe_url = validate_official_url(url)
        approved_host = urlparse(safe_url).hostname or ""
        body, content_type, final_url, _ = self._fetch(
            safe_url,
            timeout_seconds=self.timeout_seconds,
            max_bytes=2 * 1024 * 1024 if raw else self.max_html_bytes,
            approved_host=approved_host,
        )
        return body, content_type, final_url, 1, 0.0

    def _fetch_with_fallback(
        self,
        url: str,
        *,
        raw: bool = False,
        prefer_direct: bool = False,
    ) -> tuple[bytes, str, str, int, float, str]:
        transports = (
            (("direct_fallback", self._direct_fetch), ("scrapeops", self._proxy_fetch))
            if prefer_direct
            else (("scrapeops", self._proxy_fetch), ("direct_fallback", self._direct_fetch))
        )
        last_error: Exception | None = None
        for transport, fetcher in transports:
            try:
                body, content_type, final_url, attempts, cost_units = fetcher(url, raw=raw)
                return body, content_type, final_url, attempts, cost_units, transport
            except Exception as exc:
                last_error = exc
        raise last_error or RuntimeError("linkedin_fetch_failed")

    def _discover_linkedin_urls(self, company: Mapping[str, Any]) -> tuple[list[str], int, float, str]:
        existing = self._existing_linkedin_urls(company)
        if existing:
            return existing[:3], 0, 0.0, "existing_profile"
        name = str(company.get("canonical_name") or "").strip()
        if not name:
            return [], 0, 0.0, "none"
        search_url = (
            "https://html.duckduckgo.com/html/?q="
            + quote_plus(f'site:linkedin.com/company "{name}"')
        )
        body, content_type, _, attempts, cost_units, transport = self._fetch_with_fallback(search_url)
        if "html" not in content_type.casefold():
            return [], attempts, cost_units, transport
        soup = BeautifulSoup(body.decode("utf-8", errors="replace"), "html.parser")
        urls: list[str] = []
        for anchor in soup.find_all("a", href=True):
            raw_href = str(anchor.get("href") or "").strip()
            parsed_href = urlparse(raw_href)
            redirect = parse_qs(parsed_href.query).get("uddg", [""])[0]
            candidate = _linkedin_company_url(unquote(redirect or raw_href))
            if candidate and candidate not in urls:
                urls.append(candidate)
            if len(urls) >= 3:
                break
        return urls, attempts, cost_units, transport

    @staticmethod
    def _meta(html_text: str) -> dict[str, str]:
        return {
            str(item.get("property") or item.get("name") or "").casefold(): " ".join(str(item.get("content") or "").split())
            for item in BeautifulSoup(html_text, "html.parser").find_all("meta")
            if str(item.get("content") or "").strip()
        }

    def _parse_linkedin_page(
        self,
        *,
        company: Mapping[str, Any],
        linkedin_url: str,
        html_text: str,
        final_url: str,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        meta = self._meta(html_text)
        data = self._json_ld(html_text)
        title = meta.get("og:title") or meta.get("twitter:title") or meta.get("title")
        if not title:
            title = BeautifulSoup(html_text, "html.parser").title.get_text(" ", strip=True) if BeautifulSoup(html_text, "html.parser").title else ""
        page_name = re.sub(r"\s*[|·-]\s*linkedin(?:\s*[:|].*)?$", "", title, flags=re.IGNORECASE).strip()
        lowered = html_text.casefold()
        if any(marker in lowered for marker in ("page not found", "profile not found", "this page doesn’t exist")):
            return None
        if not _linkedin_identity_matches(company.get("canonical_name"), page_name):
            return None
        address = data.get("address") if isinstance(data.get("address"), Mapping) else {}
        employee = data.get("numberOfEmployees")
        if isinstance(employee, Mapping):
            employee_value = employee.get("value")
            employee_min = employee.get("minValue")
            employee_max = employee.get("maxValue")
        else:
            employee_value = employee
            employee_min = employee_max = None
        website = data.get("url") if isinstance(data.get("url"), str) else ""
        if str(website).casefold().find("linkedin.com") >= 0:
            website = ""
        founding_date = data.get("foundingDate")
        founding_year = None
        year_match = re.search(r"\b(18\d{2}|19\d{2}|20\d{2})\b", str(founding_date or ""))
        if year_match:
            founding_year = int(year_match.group(1))
        fields = {
            "website": website,
            "industry": data.get("industry") or meta.get("industry") or meta.get("linkedin:industry"),
            "company_size": employee_value or meta.get("linkedin:company_size"),
            "headquarters": OfficialWebsiteProvider._address(address) or meta.get("linkedin:headquarters"),
            "founded_year": founding_year,
        }
        logo = data.get("logo") if isinstance(data.get("logo"), str) else meta.get("og:image")
        extra = {
            "linkedin_company_url": linkedin_url,
            "linkedin_name": page_name,
            "linkedin_description": data.get("description") or meta.get("og:description") or meta.get("description"),
            "linkedin_industry": data.get("industry") or meta.get("industry") or meta.get("linkedin:industry"),
            "linkedin_company_size": employee_value or meta.get("linkedin:company_size"),
            "linkedin_employee_min": employee_min,
            "linkedin_employee_max": employee_max,
            "linkedin_headquarters": OfficialWebsiteProvider._address(address) or meta.get("linkedin:headquarters"),
            "linkedin_founded_year": founding_year,
            "linkedin_logo_url": logo,
            "linkedin_website": website,
            "linkedin_meta": {key: value for key, value in meta.items() if key.startswith(("og:", "linkedin:", "twitter:"))},
            "linkedin_lookup_status": "matched",
        }
        return fields, extra

    async def enrich(self, company: Mapping[str, Any], *, conditional: Mapping[str, Any]) -> Mapping[str, Any]:
        del conditional
        candidates, discovery_attempts, discovery_cost, discovery_transport = self._discover_linkedin_urls(company)
        request_count = discovery_attempts
        cost_units = discovery_cost
        for candidate in candidates:
            try:
                body, content_type, final_url, attempts, cost, transport = await asyncio.to_thread(
                    self._fetch_with_fallback,
                    candidate,
                    prefer_direct=discovery_transport == "direct_fallback",
                )
            except Exception:
                continue
            request_count += attempts
            cost_units += cost
            if "html" not in content_type.casefold():
                continue
            parsed = self._parse_linkedin_page(
                company=company,
                linkedin_url=_linkedin_company_url(final_url) or candidate,
                html_text=body.decode("utf-8", errors="replace"),
                final_url=final_url,
            )
            if parsed is None:
                continue
            fields, extra = parsed
            logo_url = str(extra.get("linkedin_logo_url") or "").strip()
            result: dict[str, Any] = {
                "fields": fields,
                "extra_fields": extra,
                "source": "scrapeops_linkedin_company_page" if transport == "scrapeops" else "linkedin_company_page_direct_fallback",
                "provenance_url": _linkedin_company_url(final_url) or candidate,
                "observed_at": utc_now_iso(),
                "verified_at": utc_now_iso(),
                "request_count": request_count,
                "cost_units": cost_units,
            }
            extra["linkedin_fetch_transport"] = transport
            if logo_url:
                try:
                    logo_body, logo_type, logo_final_url, logo_attempts, logo_cost, _ = await asyncio.to_thread(
                        self._fetch_with_fallback,
                        logo_url,
                        raw=True,
                        prefer_direct=transport == "direct_fallback",
                    )
                    # LinkedIn CDN responses can be consent/error HTML even
                    # when the page exposes an og:image URL. Never let an
                    # unusable optional logo discard otherwise valid company
                    # facts; validate before attaching the optional asset.
                    validate_logo(logo_body, logo_type)
                    result.update({
                        "logo_bytes": logo_body,
                        "logo_content_type": logo_type,
                        "logo_source_url": logo_final_url,
                        "request_count": request_count + logo_attempts,
                        "cost_units": cost_units + logo_cost,
                    })
                except Exception:
                    pass
            return result
        return {
            "fields": {},
            "extra_fields": {
                "linkedin_lookup_status": "not_found",
                "linkedin_candidates_checked": candidates,
            },
            "source": "scrapeops_linkedin_company_discovery",
            "provenance_url": str(company.get("provenance_url") or ""),
            "observed_at": utc_now_iso(),
            "verified_at": "",
            "request_count": request_count,
            "cost_units": cost_units,
        }


def configured_company_enrichment_provider() -> CompanyEnrichmentProvider:
    """Build the explicitly configured provider without starting enrichment."""

    provider = str(os.getenv("RUNR_COMPANY_ENRICHMENT_PROVIDER") or "official_website").strip().casefold()
    if provider in {"scrapeops_linkedin", "linkedin_scrapeops", "scrapeops_linkedin_company"}:
        return ScrapeOpsLinkedInCompanyProvider()
    if provider in {"scrapeops", "scrapeops_company", "scrapeops_company_website"}:
        return ScrapeOpsCompanyProvider()
    if provider in {"official_website", "company_website"}:
        return OfficialWebsiteProvider()
    raise ValueError(f"Unsupported RUNR_COMPANY_ENRICHMENT_PROVIDER: {provider}")


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
        extra_fields=dict(value.get("extra_fields") or {}) if isinstance(value.get("extra_fields"), Mapping) else {},
        request_count=max(0, int(value.get("request_count") or 0)), cost_units=max(0.0, float(value.get("cost_units") or 0)),
    )


def _known(value: Any) -> bool:
    return value not in (None, "", []) and not (isinstance(value, str) and value.strip().casefold() in {"unknown", "n/a", "not disclosed", "undisclosed"})


def _valid_value(field: str, value: Any, *, now_year: int) -> Any:
    if not _known(value):
        return None
    if field in {"website", "careers_page"}:
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


def _valid_extra_value(value: Any) -> Any:
    """Bound arbitrary public company metadata before storing it in JSON."""
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        cleaned = " ".join(value.split())
        return cleaned[:4096] or None
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, Mapping):
        result = {}
        for key, item in list(value.items())[:50]:
            cleaned = _valid_extra_value(item)
            if cleaned is not None:
                result[str(key)[:100]] = cleaned
        return result or None
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        result = []
        for item in list(value)[:100]:
            cleaned = _valid_extra_value(item)
            if cleaned is not None:
                result.append(cleaned)
        return result or None
    return None


class CompanyEnrichmentService:
    def __init__(self, *, repositories: Any, object_storage: Any, profile_writer: Any, provider: CompanyEnrichmentProvider | None = None, lease_owner: str = "company-enrichment-worker"):
        self.repositories = repositories
        self.object_storage = object_storage
        self.profile_writer = profile_writer
        self.provider = provider or configured_company_enrichment_provider()
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
        force_all: bool = False,
    ) -> dict[str, Any]:
        store = self.store
        if store is None:
            return {"status": "unavailable", "companies_processed": 0}
        now = _now()
        cycle_key = cycle_key or now.strftime("%Y-%m-%d")
        if force_all:
            candidates = store.list_company_enrichment_targets(now="9999-12-31T00:00:00+00:00", limit=max(1, int(max_companies)))
        else:
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
                    try:
                        existing_payload = json.loads(str(claimed.get("profile_json") or "{}"))
                    except (TypeError, ValueError):
                        existing_payload = {}
                    existing_fields = existing_payload.get("fields") if isinstance(existing_payload, Mapping) and isinstance(existing_payload.get("fields"), Mapping) else {}
                    existing_extra_fields = existing_payload.get("additional_fields") if isinstance(existing_payload, Mapping) and isinstance(existing_payload.get("additional_fields"), Mapping) else {}
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
                            existing_field = existing_fields.get(field)
                            existing_value = existing_field.get("value") if isinstance(existing_field, Mapping) else None
                            if isinstance(existing_field, Mapping) and _known(existing_value):
                                fields[field] = dict(existing_field)
                            else:
                                fields[field] = {"value": None, "state": "unknown", "status": "unknown", "provenance": None, "observed_at": None, "verified_at": None, "unknown_reason": UNKNOWN_REASON}
                    extra_fields: dict[str, Any] = {
                        str(extra_name): dict(existing_extra)
                        for extra_name, existing_extra in existing_extra_fields.items()
                        if isinstance(existing_extra, Mapping) and _known(existing_extra.get("value"))
                    }
                    for extra_name, raw_extra in (result.extra_fields or {}).items():
                        value = _valid_extra_value(raw_extra.get("value") if isinstance(raw_extra, Mapping) else raw_extra)
                        if value is None:
                            continue
                        extra_source = raw_extra.get("source") if isinstance(raw_extra, Mapping) else result.source
                        extra_url = raw_extra.get("url") if isinstance(raw_extra, Mapping) else result.provenance_url
                        extra_fields[str(extra_name)] = {
                            "value": value,
                            "state": "known",
                            "status": "known",
                            "provenance": {"source": str(extra_source or result.source), "url": str(extra_url or result.provenance_url)},
                            "observed_at": str(raw_extra.get("observed_at") if isinstance(raw_extra, Mapping) else observed_at),
                            "verified_at": str(raw_extra.get("verified_at") if isinstance(raw_extra, Mapping) else verified_at),
                        }
                    logo_key = ""
                    logo_cached = False
                    if result.logo_bytes is not None:
                        validated = validate_logo(result.logo_bytes, result.logo_content_type)
                        logo_key, logo_cached = cache_logo(self.object_storage, str(claimed["company_id"]), validated)
                    payload = {"schema_version": "phase_f_v3", "fields": fields, "additional_fields": extra_fields, "source": result.source, "provenance_url": result.provenance_url, "observed_at": observed_at, "verified_at": verified_at}
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


__all__ = ["COMPANY_ENRICHMENT_FIELDS", "CompanyEnrichmentResult", "CompanyEnrichmentService", "OfficialWebsiteProvider", "ScrapeOpsCompanyProvider", "ScrapeOpsLinkedInCompanyProvider", "configured_company_enrichment_provider"]
