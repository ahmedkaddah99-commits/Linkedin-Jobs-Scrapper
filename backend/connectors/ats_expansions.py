"""Opt-in, bounded contracts for ATS connectors not yet in the production router.

This module intentionally has no manifest or router registration.  It gives lead
integration code a stable shape for fixture validation and future canaries while
keeping failures report-only and raw source evidence available to admin/storage
layers.  The ``source_raw_payload`` member is evidence, not a public API field.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

import requests


EXPANSION_CONNECTORS = ("workday", "personio", "recruitee", "smartrecruiters")
DEFAULT_MAX_REQUESTS = 1
DEFAULT_MAX_PAGES = 1
DEFAULT_MAX_RETRIES = 0
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_PAGE_SIZE = 100

TYPED_CONTRACT_FIELDS = (
    "runr_function",
    "runr_subfunction",
    "source_department",
    "source_team",
    "source_category",
    "employment_type",
    "workplace_arrangement",
    "remote_geographic_restrictions",
    "locations",
    "languages",
    "experience",
    "salary",
    "work_authorization",
    "sponsorship",
    "application_destination",
    "application_method",
    "application_status",
    "timestamp_semantics",
    "completeness",
    "warnings",
    "freshness",
    "duplicate",
    "logo",
    "enrichment",
    "publication_state",
)

_CAPABILITY_STATES = ("supported", "partial", "unsupported", "derived")


def _capability(state: str, *fields: str, note: str = "") -> dict[str, Any]:
    return {
        "state": state,
        "source_fields": list(fields),
        "note": note,
    }


def _capability_matrix(**overrides: dict[str, Any]) -> dict[str, dict[str, Any]]:
    matrix = {
        field: _capability("unsupported", note="Not extracted by this adapter contract.")
        for field in TYPED_CONTRACT_FIELDS
    }
    matrix.update(overrides)
    return matrix


_CAPABILITIES: dict[str, dict[str, dict[str, Any]]] = {
    "workday": _capability_matrix(
        source_department=_capability("supported", "jobPostingInfo.jobFamily", "jobPostingInfo.jobCategory"),
        source_team=_capability("partial", "jobPostingInfo.team", note="Only present on some Workday tenants."),
        source_category=_capability("supported", "jobPostingInfo.jobCategory"),
        employment_type=_capability("supported", "jobPostingInfo.timeType"),
        workplace_arrangement=_capability("partial", "jobPostingInfo.remoteType"),
        remote_geographic_restrictions=_capability("partial", "jobPostingInfo.remoteLocation"),
        locations=_capability("supported", "jobPostingInfo.locations", "jobPostingInfo.location"),
        languages=_capability("partial", "jobPostingInfo.languages", note="May require description extraction."),
        experience=_capability("partial", "jobPostingInfo.experience", note="Tenant-dependent structured field."),
        salary=_capability("partial", "jobPostingInfo.salary"),
        work_authorization=_capability("partial", "jobPostingInfo.workAuthorization"),
        sponsorship=_capability("partial", "jobPostingInfo.sponsorship"),
        application_destination=_capability("supported", "externalUrl", "jobPostingInfo.externalUrl", "url"),
        application_method=_capability("derived", "application_destination"),
        application_status=_capability("derived", "application_destination"),
        timestamp_semantics=_capability("supported", "postedOn", "updatedOn", "startDate"),
        completeness=_capability("derived", "snapshot_semantics", "required_identity_fields"),
        warnings=_capability("derived", "adapter_validation"),
        freshness=_capability("derived", "observed_at", "timestamp_semantics"),
        duplicate=_capability("derived", "stable_external_id"),
        publication_state=_capability("derived", "snapshot_semantics"),
    ),
    "personio": _capability_matrix(
        source_department=_capability("supported", "department"),
        source_team=_capability("partial", "team", note="Field is not present for every Personio tenant."),
        source_category=_capability("partial", "category"),
        employment_type=_capability("supported", "employmentType"),
        workplace_arrangement=_capability("partial", "office", "remote"),
        remote_geographic_restrictions=_capability("partial", "remote"),
        locations=_capability("supported", "office", "location"),
        languages=_capability("partial", "languages", note="Usually description-derived."),
        experience=_capability("partial", "experience", note="Usually description-derived."),
        salary=_capability("partial", "salary"),
        application_destination=_capability("supported", "jobAdLink", "applyUrl", "url"),
        application_method=_capability("derived", "application_destination"),
        application_status=_capability("derived", "application_destination"),
        timestamp_semantics=_capability("partial", "createdAt", "updatedAt"),
        completeness=_capability("derived", "snapshot_semantics", "required_identity_fields"),
        warnings=_capability("derived", "adapter_validation"),
        freshness=_capability("derived", "observed_at", "timestamp_semantics"),
        duplicate=_capability("derived", "stable_external_id"),
        publication_state=_capability("derived", "snapshot_semantics"),
    ),
    "recruitee": _capability_matrix(
        source_department=_capability("supported", "department"),
        source_team=_capability("partial", "team"),
        source_category=_capability("partial", "category"),
        employment_type=_capability("supported", "employment_type", "employmentType"),
        workplace_arrangement=_capability("partial", "remote", "workplaceType"),
        remote_geographic_restrictions=_capability("partial", "remote"),
        locations=_capability("supported", "location", "locations"),
        languages=_capability("partial", "languages", note="May be description-derived."),
        experience=_capability("partial", "experience", note="May be description-derived."),
        salary=_capability("partial", "salary"),
        application_destination=_capability("supported", "careers_url", "apply_url", "url"),
        application_method=_capability("derived", "application_destination"),
        application_status=_capability("derived", "application_destination"),
        timestamp_semantics=_capability("partial", "created_at", "updated_at"),
        completeness=_capability("derived", "snapshot_semantics", "required_identity_fields"),
        warnings=_capability("derived", "adapter_validation"),
        freshness=_capability("derived", "observed_at", "timestamp_semantics"),
        duplicate=_capability("derived", "stable_external_id"),
        publication_state=_capability("derived", "snapshot_semantics"),
    ),
    "smartrecruiters": _capability_matrix(
        source_department=_capability("supported", "department"),
        source_team=_capability("partial", "team"),
        source_category=_capability("supported", "function"),
        employment_type=_capability("supported", "typeOfEmployment"),
        workplace_arrangement=_capability("partial", "remoteType"),
        remote_geographic_restrictions=_capability("partial", "remoteLocation"),
        locations=_capability("supported", "location", "locations"),
        languages=_capability("partial", "languages", note="May be description-derived."),
        experience=_capability("partial", "experience", note="May be description-derived."),
        salary=_capability("partial", "salary"),
        application_destination=_capability("supported", "ref", "applyUrl", "jobAd"),
        application_method=_capability("derived", "application_destination"),
        application_status=_capability("derived", "application_destination"),
        timestamp_semantics=_capability("supported", "releasedDate", "updatedDate"),
        completeness=_capability("derived", "snapshot_semantics", "required_identity_fields"),
        warnings=_capability("derived", "adapter_validation"),
        freshness=_capability("derived", "observed_at", "timestamp_semantics"),
        duplicate=_capability("derived", "stable_external_id"),
        publication_state=_capability("derived", "snapshot_semantics"),
    ),
}

_IDENTITY_KEYS = {
    "workday": ("externalId", "jobPostingId", "jobId", "id", "bulletFields.id"),
    "personio": ("id", "uuid", "positionId", "jobId"),
    "recruitee": ("id", "offerId", "jobId", "uuid"),
    "smartrecruiters": ("id", "uuid", "jobAdId", "postingId"),
}

_DETAIL_KEYS = (
    "job_detail_url",
    "jobDetailUrl",
    "hostedUrl",
    "jobAd",
    "jobAdLink",
    "careers_url",
    "url",
    "ref",
    "absolute_url",
    "externalUrl",
    "jobPostingInfo.externalUrl",
    "externalPath",
)

_APPLICATION_KEYS = (
    "application_url",
    "applicationUrl",
    "apply_url",
    "applyUrl",
    "applicationLink",
    "applicationLinkUrl",
    "externalUrl",
    "jobAdLink",
    "jobAd",
    "ref",
    "url",
)


def _first_value(payload: Mapping[str, Any], paths: Iterable[str]) -> Any:
    for path in paths:
        value: Any = payload
        for part in path.split("."):
            if not isinstance(value, Mapping) or part not in value:
                value = None
                break
            value = value[part]
        if value not in (None, "", [], {}):
            return value
    return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Mapping):
        for key in ("name", "label", "value", "text", "title", "url", "href", "ref", "link"):
            if value.get(key) not in (None, ""):
                return _text(value[key])
        return ""
    return str(value).strip()


def _canonical_url(value: Any, *, base_url: str = "") -> str:
    raw = _text(value)
    if not raw:
        return ""
    absolute = urljoin(base_url, raw)
    parts = urlsplit(absolute)
    if not parts.scheme or not parts.netloc:
        return ""
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
            if key.casefold() not in {"gclid", "fbclid", "mc_cid", "mc_eid"}
            and not key.casefold().startswith("utm_")
        ]
    )
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, query, ""))


def _string_list(value: Any) -> list[str]:
    if value in (None, "", []):
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    result: list[str] = []
    for item in values:
        text = _text(item)
        if text and text not in result:
            result.append(text)
    return result


def _normalize_timestamp(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 10_000_000_000:
            numeric /= 1000
        try:
            return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(numeric))
        except (OverflowError, OSError, ValueError):
            return None
    text = _text(value)
    if not text:
        return None
    return text


def _stable_external_identity(connector: str, item: Mapping[str, Any], detail_url: str) -> dict[str, str]:
    external_id = _text(_first_value(item, _IDENTITY_KEYS[connector]))
    identity_source = "source_external_id" if external_id else "canonical_detail_url"
    identity_seed = external_id or detail_url
    if not identity_seed:
        identity_source = "payload_fingerprint"
        identity_seed = json.dumps(item, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(f"{connector}|{identity_seed}".encode("utf-8")).hexdigest()[:32]
    return {
        "external_id": external_id or f"{connector}:{digest}",
        "stable_external_id": f"{connector}:{digest}",
        "identity_key": f"{connector}:{digest}",
        "identity_source": identity_source,
    }


def _looks_like_listing(url: str, target_url: str) -> bool:
    canonical = _canonical_url(url)
    target = _canonical_url(target_url)
    if not canonical:
        return True
    if target and canonical == target:
        return True
    path = urlsplit(canonical).path.casefold().strip("/")
    if not path:
        return True
    return path.endswith(("/jobs", "/careers", "/positions", "/vacancies", "/postings"))


def _application_destination(item: Mapping[str, Any], *, detail_url: str, target_url: str) -> dict[str, Any]:
    raw_application = _first_value(item, _APPLICATION_KEYS)
    application_url = _canonical_url(raw_application, base_url=detail_url or target_url)
    same_page_form = bool(
        _first_value(
            item,
            ("has_application_form", "hasApplicationForm", "applyOnPage", "applicationForm", "formAction"),
        )
    )
    warnings: list[str] = []
    if application_url and detail_url and application_url == detail_url:
        if same_page_form:
            return {
                "url": application_url,
                "method": "same_page",
                "status": "verified",
                "source_field": "application_url",
                "warnings": warnings,
            }
        warnings.append("job_detail_not_apply_destination")
        return {
            "url": application_url,
            "method": "job_detail",
            "status": "inferred",
            "source_field": "application_url",
            "warnings": warnings,
        }
    if application_url and not _looks_like_listing(application_url, target_url):
        return {
            "url": application_url,
            "method": "direct_apply",
            "status": "verified",
            "source_field": "application_url",
            "warnings": warnings,
        }
    if application_url:
        warnings.append("careers_index_not_apply_destination")
        return {
            "url": "",
            "method": "unknown",
            "status": "unsupported",
            "source_field": "application_url",
            "warnings": warnings,
        }
    if detail_url and same_page_form:
        return {
            "url": detail_url,
            "method": "same_page",
            "status": "verified",
            "source_field": "detail_page_form",
            "warnings": warnings,
        }
    if detail_url:
        warnings.append("missing_direct_application_url")
        return {
            "url": detail_url,
            "method": "job_detail",
            "status": "inferred",
            "source_field": "job_detail_url",
            "warnings": warnings,
        }
    warnings.append("missing_application_destination")
    return {
        "url": "",
        "method": "unknown",
        "status": "missing",
        "source_field": "",
        "warnings": warnings,
    }


def _timestamp_semantics(item: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "published_at": _normalize_timestamp(
            _first_value(item, ("publishedAt", "published_at", "datePosted", "releasedDate", "postedOn"))
        ),
        "created_at": _normalize_timestamp(_first_value(item, ("createdAt", "created_at", "startDate"))),
        "updated_at": _normalize_timestamp(_first_value(item, ("updatedAt", "updated_at", "updatedDate"))),
    }
    known = [name for name, value in fields.items() if value]
    return {
        "state": "known" if known else "unknown",
        "fields": fields,
        "available_fields": known,
        "source_timestamp_policy": "preserve_source_semantics; do_not_infer_posted_at",
    }


def _locations(item: Mapping[str, Any]) -> list[str]:
    value = _first_value(item, ("locations", "locationsText", "jobPostingInfo.locations", "jobLocation", "location", "office"))
    return _string_list(value)


def _languages(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = _first_value(item, ("languages", "language", "requiredLanguages"))
    if value in (None, "", []):
        return []
    rows = value if isinstance(value, list) else [value]
    result: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, Mapping):
            language = _text(row.get("language") or row.get("name") or row.get("value"))
            requirement = _text(row.get("requirement") or row.get("status")) or "unknown"
            proficiency = _text(row.get("proficiency") or row.get("level")) or None
        else:
            language, requirement, proficiency = _text(row), "unknown", None
        if language:
            result.append({"language": language, "requirement": requirement, "proficiency": proficiency})
    return result


def _experience(item: Mapping[str, Any]) -> dict[str, Any]:
    value = _first_value(
        item,
        ("experience", "experienceRequirements", "experience_requirements", "jobPostingInfo.experience"),
    )
    if isinstance(value, Mapping):
        return {
            "minimum_years": value.get("minimum_years", value.get("minimumYears")),
            "maximum_years": value.get("maximum_years", value.get("maximumYears")),
            "seniority": _text(value.get("seniority")) or None,
            "requirement_status": _text(value.get("requirement_status") or value.get("status")) or "unknown",
        }
    return {
        "minimum_years": None,
        "maximum_years": None,
        "seniority": _text(value) or None,
        "requirement_status": "unknown" if not value else "present_unparsed",
    }


def _salary(item: Mapping[str, Any]) -> dict[str, Any]:
    value = _first_value(item, ("salary", "salaryRange", "compensation", "jobPostingInfo.salary"))
    if not isinstance(value, Mapping):
        return {"minimum": None, "maximum": None, "currency": None, "period": None}
    return {
        "minimum": value.get("minimum", value.get("min", value.get("from"))),
        "maximum": value.get("maximum", value.get("max", value.get("to"))),
        "currency": _text(value.get("currency")) or None,
        "period": _text(value.get("period") or value.get("interval")) or None,
    }


def _normalize_job(connector: str, item: Mapping[str, Any], *, target_url: str, snapshot_complete: bool) -> dict[str, Any]:
    raw_detail = _first_value(item, _DETAIL_KEYS)
    if connector == "smartrecruiters" and _text(raw_detail).startswith("https://api.smartrecruiters.com/"):
        target_parts = urlsplit(target_url)
        company_slug = next((part for part in target_parts.path.split("/") if part), "")
        posting_id = _text(_first_value(item, ("id", "uuid", "jobAdId")))
        if company_slug and posting_id:
            raw_detail = f"https://jobs.smartrecruiters.com/{quote(company_slug, safe='')}/{quote(posting_id, safe='')}"
    if connector == "workday" and not _text(raw_detail):
        raw_detail = _first_value(item, ("jobPostingInfo.externalPath",))
    if connector == "personio" and not _text(raw_detail):
        position_id = _text(_first_value(item, ("id", "uuid", "positionId", "jobId")))
        if position_id:
            raw_detail = urljoin(target_url.rstrip("/") + "/", f"job/{quote(position_id, safe='')}")
    detail_url = _canonical_url(raw_detail, base_url=target_url)
    identity = _stable_external_identity(connector, item, detail_url)
    application = _application_destination(item, detail_url=detail_url, target_url=target_url)
    timestamp_semantics = _timestamp_semantics(item)
    title = _text(_first_value(item, ("title", "text", "name", "jobPostingInfo.title")))
    description = _text(_first_value(item, ("description", "descriptionPlain", "description_text", "jobDescriptions.description", "jobPostingInfo.description")))
    location_values = _locations(item)
    apply_url = application["url"] or detail_url
    warnings = list(application["warnings"])
    if not title:
        warnings.append("missing_title")
    if not detail_url:
        warnings.append("missing_job_detail_url")
    required = bool(title and identity["external_id"] and detail_url)
    return {
        **identity,
        "title": title,
        "job_id": identity["external_id"],
        "external_job_id": identity["external_id"],
        "job_detail_url": detail_url,
        "url": detail_url,
        "link": detail_url,
        "source_url": detail_url,
        "apply_link": apply_url,
        "apply_url": application["url"],
        "location": ", ".join(location_values),
        "location_raw": ", ".join(location_values),
        "full_description": description,
        "description": description,
        "source_ats": connector,
        "source_raw_payload": deepcopy(dict(item)),
        "application_destination": application,
        "application_method": application["method"],
        "application_status": application["status"],
        "department": _text(_first_value(item, ("source_department", "department", "jobPostingInfo.jobFamily", "jobPostingInfo.jobCategory", "fieldOfWork"))) or None,
        "team": _text(_first_value(item, ("source_team", "team", "jobPostingInfo.team"))) or None,
        "category": _text(_first_value(item, ("source_category", "category", "function", "jobPostingInfo.jobCategory"))) or None,
        "source_department": _text(_first_value(item, ("source_department", "department", "jobPostingInfo.jobFamily", "jobPostingInfo.jobCategory", "fieldOfWork"))) or None,
        "source_team": _text(_first_value(item, ("source_team", "team", "jobPostingInfo.team"))) or None,
        "source_category": _text(_first_value(item, ("source_category", "category", "function", "jobPostingInfo.jobCategory")))
        or None,
        "runr_function": _text(_first_value(item, ("runr_function", "runrFunction"))) or None,
        "runr_subfunction": _text(_first_value(item, ("runr_subfunction", "runrSubfunction"))) or None,
        "employment_type": _text(_first_value(item, ("employment_type", "employmentType", "typeOfEmployment", "commitment", "jobPostingInfo.timeType", "timeType")))
        or None,
        "workplace_arrangement": _text(
            _first_value(item, ("workplace_arrangement", "workplaceType", "remoteType", "remote", "jobPostingInfo.remoteType"))
        )
        or None,
        "remote_geographic_restrictions": _string_list(
            _first_value(item, ("remote_geographic_restrictions", "remoteRestrictions", "remoteLocation"))
        ),
        "locations": _locations(item),
        "languages": _languages(item),
        "experience": _experience(item),
        "salary": _salary(item),
        "work_authorization": _text(_first_value(item, ("work_authorization", "workAuthorization"))) or None,
        "sponsorship": _text(_first_value(item, ("sponsorship", "visaSponsorship"))) or None,
        "timestamp_semantics": timestamp_semantics,
        "completeness": {
            "state": "complete" if required else "partial",
            "required_fields_present": required,
            "missing_fields": [field for field, value in (("title", title), ("job_detail_url", detail_url)) if not value],
            "snapshot_semantics": "complete" if snapshot_complete else "incomplete",
        },
        "warnings": sorted(set(warnings)),
        "freshness": {"state": "observed", "source_timestamp_state": timestamp_semantics["state"]},
        "duplicate": {"state": "not_evaluated", "stable_external_id": identity["stable_external_id"]},
        "logo": {"state": "not_requested"},
        "enrichment": {"state": "not_requested"},
        "publication_state": {"state": "not_published"},
        # Admin/storage evidence only.  Public serializers must omit this member.
        "source_raw_payload": deepcopy(dict(item)),
    }


def _request_url(connector: str, target_url: str, *, offset: int, page_size: int) -> str:
    parts = urlsplit(target_url)
    path_segments = [segment for segment in parts.path.split("/") if segment]
    slug = path_segments[0] if path_segments else parts.hostname or ""
    if connector == "smartrecruiters":
        base = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
        return f"{base}?limit={page_size}&offset={offset}"
    if connector == "recruitee":
        base = f"{parts.scheme}://{parts.netloc}/api/offers"
        return f"{base}?limit={page_size}&offset={offset}"
    if connector == "personio" and "/xml" not in parts.path.casefold():
        return urljoin(target_url.rstrip("/") + "/", "xml")
    if connector == "workday":
        tenant = (parts.hostname or "").split(".", 1)[0]
        site = path_segments[-1] if path_segments else ""
        if len(path_segments) >= 2 and re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", path_segments[0]):
            site = path_segments[-1]
        return f"{parts.scheme}://{parts.netloc}/wday/cxs/{quote(tenant, safe='')}/{quote(site, safe='')}/jobs"
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({"limit": str(page_size), "offset": str(offset)})
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", urlencode(query), ""))


def _items_from_payload(connector: str, payload: Any) -> list[Any]:
    if connector == "personio" and isinstance(payload, str) and payload.lstrip().startswith("<"):
        try:
            root = ET.fromstring(payload)
        except ET.ParseError:
            return []
        rows: list[dict[str, Any]] = []
        for position in root.iter():
            if position.tag.rsplit("}", 1)[-1].casefold() != "position":
                continue
            row: dict[str, Any] = dict(position.attrib)
            for child in position.iter():
                if child is position:
                    continue
                key = child.tag.rsplit("}", 1)[-1]
                text = " ".join(" ".join(child.itertext()).split())
                if text and key not in row:
                    row[key] = text
            rows.append(row)
        return rows
    if isinstance(payload, list):
        return list(payload)
    if not isinstance(payload, Mapping):
        return []
    keys = {
        "workday": ("jobPostings", "jobs", "results", "data"),
        "personio": ("position", "positions", "jobs", "results", "data"),
        "recruitee": ("offers", "jobs", "results", "data"),
        "smartrecruiters": ("content", "postings", "jobs", "results", "data"),
    }[connector]
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return list(value)
    return []


def _pagination(payload: Any, *, item_count: int, offset: int, page_size: int) -> tuple[bool, int | None]:
    if not isinstance(payload, Mapping):
        return item_count >= page_size, offset + item_count
    next_value = _first_value(
        payload,
        ("next", "nextPage", "next_page", "links.next", "pagination.next", "meta.next"),
    )
    if next_value:
        return True, offset + item_count
    has_more = _first_value(payload, ("hasMore", "has_more", "pagination.hasMore", "meta.hasMore"))
    if isinstance(has_more, bool):
        return has_more, offset + item_count
    total = _first_value(
        payload,
        ("totalFound", "total", "totalResults", "count", "pagination.total", "meta.total", "paginator.total"),
    )
    if isinstance(total, (int, float)):
        return offset + item_count < int(total), offset + item_count
    return item_count >= page_size, offset + item_count


def _safe_request(
    request: Callable[..., Any],
    url: str,
    timeout_seconds: int,
    *,
    method: str = "GET",
    json_payload: Mapping[str, Any] | None = None,
) -> Any:
    try:
        return request(url, timeout=timeout_seconds, allow_redirects=False, json=dict(json_payload or {})) if method == "POST" else request(url, timeout=timeout_seconds, allow_redirects=False)
    except TypeError:
        return request(url, timeout=timeout_seconds, json=dict(json_payload or {})) if method == "POST" else request(url, timeout=timeout_seconds)


def _error_message(exc: BaseException) -> str:
    return re.sub(r"([?&](?:token|key|secret|password)=)[^&\s]+", r"\1[REDACTED]", str(exc), flags=re.IGNORECASE)[:500]


def build_capability_snapshot(
    connector: str,
    target_url: str = "",
    *,
    enabled: bool = False,
    fixture_mode: bool = False,
    max_requests: int = DEFAULT_MAX_REQUESTS,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_retries: int = DEFAULT_MAX_RETRIES,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Describe an expansion connector and its bounded production contract."""

    normalized = str(connector or "").strip().casefold()
    capabilities = deepcopy(_CAPABILITIES.get(normalized, {}))
    known = normalized in EXPANSION_CONNECTORS
    bounded_requests = max(1, min(20, int(max_requests)))
    bounded_pages = max(1, min(10, int(max_pages)))
    bounded_retries = max(0, min(3, int(max_retries)))
    return {
        "connector": normalized,
        "target_url": _canonical_url(target_url) if target_url else "",
        "enabled": bool(enabled and known),
        "state": "enabled" if enabled and known else "fixture_only" if fixture_mode and known else "disabled" if known else "unsupported",
        "production_registered": bool(enabled and known),
        "capabilities": capabilities,
        "request_limits": {
            "max_requests": bounded_requests,
            "max_pages": bounded_pages,
            "timeout_seconds": max(1, min(120, int(timeout_seconds))),
        },
        "retry_policy": {
            "max_retries": bounded_retries,
            "retryable_statuses": [408, 425, 429, 500, 502, 503, 504],
            "recovery": "resume_from_last_successful_page; no projection on failed snapshot",
        },
        "raw_retention": {
            "required": True,
            "field": "source_raw_payload",
            "admin_only": True,
            "metric_helper": "measure_raw_retention",
        },
        "failure_policy": "report_only",
    }


def build_capability_snapshots() -> list[dict[str, Any]]:
    """Return the production-registered capability inventory."""

    return [build_capability_snapshot(connector, enabled=True) for connector in EXPANSION_CONNECTORS]


def measure_raw_retention(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Measure retained raw evidence without returning its contents."""

    total = retained = invalid = total_bytes = 0
    hashes: set[str] = set()
    for record in records:
        total += 1
        payload = record.get("source_raw_payload", record.get("raw_payload", record.get("raw_payload_json")))
        if isinstance(payload, str):
            if not payload.strip():
                payload = None
            else:
                try:
                    json.loads(payload)
                except (TypeError, ValueError):
                    invalid += 1
        if payload not in (None, "", [], {}):
            retained += 1
            encoded = payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True, default=str)
            total_bytes += len(encoded.encode("utf-8"))
            hashes.add(hashlib.sha256(encoded.encode("utf-8")).hexdigest())
    return {
        "observations": total,
        "retained": retained,
        "missing": total - retained,
        "invalid_json": invalid,
        "retention_rate": round(retained / total, 4) if total else 1.0,
        "distinct_payload_hashes": len(hashes),
        "retained_bytes": total_bytes,
        "raw_field": "source_raw_payload",
    }


def fetch_expansion_snapshot(
    target_url: str,
    connector: str,
    *,
    requester: Callable[..., Any] | None = None,
    fixture_payload: Any = None,
    enabled: bool = False,
    max_requests: int = DEFAULT_MAX_REQUESTS,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_retries: int = DEFAULT_MAX_RETRIES,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    page_size: int = DEFAULT_PAGE_SIZE,
    sleep_fn: Callable[[float], Any] | None = None,
) -> dict[str, Any]:
    """Fetch a bounded fixture or explicitly enabled public listing snapshot.

    A fixture payload never performs I/O.  Live calls are opt-in, capped by both
    ``max_requests`` and ``max_pages``, and return failures as report data.
    """

    normalized = str(connector or "").strip().casefold()
    snapshot = build_capability_snapshot(
        normalized,
        target_url,
        enabled=enabled,
        fixture_mode=fixture_payload is not None,
        max_requests=max_requests,
        max_pages=max_pages,
        max_retries=max_retries,
        timeout_seconds=timeout_seconds,
    )
    base_result = {
        **snapshot,
        "status": "disabled" if not enabled and fixture_payload is None else "unsupported",
        "complete_snapshot": False,
        "snapshot_semantics": "not_attempted",
        "credible_evidence": False,
        "jobs": [],
        "request_log": [],
        "requests_made": 0,
        "pages_fetched": 0,
        "raw_retention": {**snapshot["raw_retention"], **measure_raw_retention([])},
        "recovery": {
            "attempts": 0,
            "max_retries": snapshot["retry_policy"]["max_retries"],
            "retryable_failures": 0,
            "recovered": False,
            "resume_cursor": None,
            "report_only": True,
        },
        "warnings": [],
    }
    if normalized not in EXPANSION_CONNECTORS:
        base_result["warnings"] = ["unsupported_connector"]
        return base_result
    if not enabled and fixture_payload is None:
        base_result["warnings"] = ["connector_disabled_by_default"]
        return base_result

    request = requester or (requests.post if normalized == "workday" else requests.get)
    bounded_requests = snapshot["request_limits"]["max_requests"]
    bounded_pages = snapshot["request_limits"]["max_pages"]
    bounded_page_size = max(1, min(500, int(page_size)))
    retry_limit = snapshot["retry_policy"]["max_retries"]
    observed_at = None
    all_jobs: list[dict[str, Any]] = []
    observation_failures: list[dict[str, Any]] = []
    request_log: list[dict[str, Any]] = []
    failures: list[str] = []
    retryable_failures = 0
    pages_fetched = 0
    offset = 0
    has_more = False
    complete = False
    fixture = fixture_payload is not None
    fixture_pages = fixture_payload if isinstance(fixture_payload, tuple) else None

    while pages_fetched < bounded_pages and (fixture or len(request_log) < bounded_requests):
        page_payload: Any
        request_url = _request_url(normalized, target_url, offset=offset, page_size=bounded_page_size)
        request_method = "POST" if normalized == "workday" else "GET"
        request_payload = {"appliedFacets": {}, "limit": min(bounded_page_size, 10), "offset": offset, "searchText": ""} if normalized == "workday" else None
        if fixture:
            if fixture_pages is not None:
                if pages_fetched >= len(fixture_pages):
                    break
                page_payload = fixture_pages[pages_fetched]
            else:
                page_payload = fixture_payload
            request_log.append({"page": pages_fetched + 1, "attempt": 1, "mode": "fixture", "outcome": "success"})
        else:
            page_payload = None
            page_failed = False
            for attempt in range(1, min(retry_limit + 1, bounded_requests - len(request_log)) + 1):
                if len(request_log) >= bounded_requests:
                    break
                try:
                    response = _safe_request(
                        request,
                        request_url,
                        snapshot["request_limits"]["timeout_seconds"],
                        method=request_method,
                        json_payload=request_payload,
                    )
                    status_code = int(getattr(response, "status_code", 0) or 0)
                    retryable = status_code in snapshot["retry_policy"]["retryable_statuses"]
                    if status_code >= 400:
                        if retryable:
                            retryable_failures += 1
                        request_log.append(
                            {
                                "page": pages_fetched + 1,
                                "attempt": attempt,
                                "url": request_url,
                                "status_code": status_code,
                                "outcome": "retryable_failure" if retryable else "failure",
                                "retriable": retryable,
                            }
                        )
                        if retryable and attempt <= retry_limit:
                            if sleep_fn:
                                sleep_fn(0)
                            continue
                        failures.append(f"http_{status_code}")
                        page_failed = True
                        break
                    try:
                        page_payload = response.json()
                    except (ValueError, AttributeError):
                        page_payload = getattr(response, "text", "")
                    request_log.append(
                        {
                            "page": pages_fetched + 1,
                            "attempt": attempt,
                            "url": request_url,
                            "status_code": status_code,
                            "outcome": "success",
                            "retriable": False,
                        }
                    )
                    if attempt > 1:
                        base_result["recovery"]["recovered"] = True
                    break
                except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
                    retryable_failures += 1
                    request_log.append(
                        {
                            "page": pages_fetched + 1,
                            "attempt": attempt,
                            "url": request_url,
                            "outcome": "retryable_failure" if attempt <= retry_limit else "failure",
                            "retriable": attempt <= retry_limit,
                            "error_type": type(exc).__name__,
                            "error": _error_message(exc),
                        }
                    )
                    if attempt <= retry_limit:
                        if sleep_fn:
                            sleep_fn(0)
                        continue
                    failures.append(type(exc).__name__)
                    page_failed = True
                    break
            if page_failed or page_payload is None:
                break
        items = _items_from_payload(normalized, page_payload)
        page_has_more, next_offset = _pagination(
            page_payload,
            item_count=len(items),
            offset=offset,
            page_size=bounded_page_size,
        )
        pages_fetched += 1
        for item_index, item in enumerate(items):
            if not isinstance(item, Mapping):
                observation_failures.append(
                    {
                        "page": pages_fetched + 1,
                        "index": item_index,
                        "error_type": "invalid_item",
                        "error": "listing entry is not an object",
                        "report_only": True,
                    }
                )
                continue
            try:
                all_jobs.append(
                    _normalize_job(
                        normalized,
                        item,
                        target_url=target_url,
                        snapshot_complete=not page_has_more,
                    )
                )
            except (TypeError, ValueError, KeyError, AttributeError) as exc:
                observation_failures.append(
                    {
                        "page": pages_fetched + 1,
                        "index": item_index,
                        "error_type": type(exc).__name__,
                        "error": _error_message(exc),
                        "report_only": True,
                    }
                )
        has_more = page_has_more
        offset = next_offset or offset + len(items)
        if observed_at is None and isinstance(page_payload, Mapping):
            observed_at = page_payload.get("observed_at")
        if not has_more:
            complete = True
            break
        if fixture and fixture_pages is None:
            break

    if has_more and pages_fetched >= bounded_pages:
        failures.append("bounded_page_limit_reached")
    if observation_failures:
        failures.append("observation_failure")
    if not pages_fetched and not failures:
        failures.append("no_snapshot_page")
    status = "failed" if failures and not all_jobs else "incomplete" if failures or has_more else "completed"
    complete = bool(complete and not failures and not has_more)
    base_result.update(
        {
            "status": status,
            "complete_snapshot": complete,
            "snapshot_semantics": "complete" if complete else "incomplete",
            "credible_evidence": bool(pages_fetched and not failures),
            "jobs": all_jobs,
            "request_url": _request_url(normalized, target_url, offset=0, page_size=bounded_page_size),
            "requests_made": len(request_log),
            "pages_fetched": pages_fetched,
            "request_log": request_log,
            "raw_retention": {**snapshot["raw_retention"], **measure_raw_retention(all_jobs)},
            "recovery": {
                **base_result["recovery"],
                "attempts": len(request_log),
                "retryable_failures": retryable_failures,
                "resume_cursor": offset if has_more else None,
            },
            "warnings": sorted(set(failures)),
            "observed_at": observed_at,
            "source_reported_count": len(all_jobs),
            "observation_failures": observation_failures,
        }
    )
    return base_result


def run_fixture_snapshot(connector: str, target_url: str, payload: Any) -> dict[str, Any]:
    """Convenience wrapper proving fixtures cannot perform network I/O."""

    return fetch_expansion_snapshot(target_url, connector, fixture_payload=payload, enabled=False)


__all__ = [
    "EXPANSION_CONNECTORS",
    "TYPED_CONTRACT_FIELDS",
    "build_capability_snapshot",
    "build_capability_snapshots",
    "fetch_expansion_snapshot",
    "measure_raw_retention",
    "run_fixture_snapshot",
]
