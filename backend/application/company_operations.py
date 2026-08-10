"""Provider-independent company URL and enrichment view operations.

This module is deliberately a read-model boundary.  It accepts source evidence
already collected by an acquisition or enrichment worker and returns typed,
JSON-safe views; it does not fetch URLs, call providers, or write production
data.  A lead agent can later connect the view to repository rows and the
existing :mod:`backend.application.company_logo` primitives.

Integration notes:

* ``build_company_url_view`` can consume rows from ``canonical_company_urls``
  without changing that table.  Its ``provenance.entries`` value preserves the
  contributing source rows for an admin drawer.
* ``CompanyOperations.one`` and ``CompanyOperations.many`` are bounded
  operation contracts.  They are intentionally synchronous and provider-free;
  callers own authentication, scheduling, persistence, and authorization.
* URL validation here is structural only.  DNS/redirect validation belongs to
  the existing safe fetch path and must update evidence explicitly rather than
  being implied by this view.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import ipaddress
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit


COMPANY_URL_TYPES = (
    "homepage",
    "careers",
    "ats_board",
    "employer_jobs",
    "application_host",
    "source",
    "social_profile",
    "enrichment",
)

_URL_TYPE_ALIASES = {
    "website": "homepage",
    "homepage_url": "homepage",
    "company_website": "homepage",
    "site": "homepage",
    "careers_page": "careers",
    "careers_url": "careers",
    "career_page": "careers",
    "jobs_url": "employer_jobs",
    "employer_jobs_url": "employer_jobs",
    "ats_url": "ats_board",
    "ats_board_url": "ats_board",
    "application_url": "application_host",
    "application_host_url": "application_host",
    "source_url": "source",
    "provenance_url": "source",
    "social_url": "social_profile",
    "profile_url": "social_profile",
    "enrichment_url": "enrichment",
}

_SOURCE_PRECEDENCE = {
    "official_company_website": 100,
    "official_employer_source": 95,
    "source_observation": 90,
    "ats_connector": 85,
    "enrichment_provider": 70,
    "company_record": 60,
    "manual": 50,
}

_VALIDATION_ALIASES = {
    "validated": "valid",
    "verified": "valid",
    "structurally_valid": "not_validated",
    "not_checked": "not_validated",
    "unverified": "not_validated",
    "rejected": "invalid",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _truthy(value: Any) -> bool:
    return value is True or value == 1 or _text(value).casefold() in {"1", "true", "yes", "primary"}


def _normalise_url_type(value: Any, default: str = "source") -> str:
    candidate = _text(value).casefold().replace("-", "_").replace(" ", "_")
    candidate = _URL_TYPE_ALIASES.get(candidate, candidate)
    return candidate if candidate in COMPANY_URL_TYPES else default


def _timestamp(value: Any) -> str:
    """Return a trimmed timestamp only when it is parseable or clearly empty."""

    raw = _text(value)
    if not raw:
        return ""
    try:
        datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return raw


def _timestamp_key(value: str) -> tuple[int, datetime]:
    if not value:
        return (0, datetime.min.replace(tzinfo=timezone.utc))
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return (1, parsed.replace(tzinfo=timezone.utc))
    return (1, parsed.astimezone(timezone.utc))


def _range_timestamp(values: Iterable[str], *, first: bool) -> str:
    present = [value for value in values if value]
    if not present:
        return ""
    return (min if first else max)(present, key=_timestamp_key)


def _normalise_host(host: str) -> str:
    return _text(host).rstrip(".").casefold()


@dataclass(frozen=True, slots=True)
class NormalizedCompanyUrl:
    url: str
    canonical_url: str
    validation_status: str
    validation_reason: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "url": self.url,
            "canonical_url": self.canonical_url,
            "validation_status": self.validation_status,
            "validation_reason": self.validation_reason,
        }


def normalize_company_url(url: Any) -> NormalizedCompanyUrl:
    """Canonicalise a URL without performing network or DNS I/O.

    The result preserves the original URL even when it is rejected.  This is
    important for audit views: malformed or unsupported source evidence should
    be visible as a warning, not silently discarded.
    """

    original = _text(url)
    if not original:
        return NormalizedCompanyUrl("", "", "invalid", "url_missing")
    try:
        parsed = urlsplit(original)
        host = _normalise_host(parsed.hostname or "")
        port = parsed.port
    except ValueError:
        return NormalizedCompanyUrl(original, "", "invalid", "url_parse_failed")
    if parsed.scheme.casefold() not in {"http", "https"}:
        return NormalizedCompanyUrl(original, "", "invalid", "unsupported_scheme")
    if not host:
        return NormalizedCompanyUrl(original, "", "invalid", "host_missing")
    if parsed.username or parsed.password:
        return NormalizedCompanyUrl(original, "", "invalid", "embedded_credentials")
    if port not in (None, 80, 443):
        return NormalizedCompanyUrl(original, "", "invalid", "non_default_port")
    try:
        parsed_ip = ipaddress.ip_address(host)
    except ValueError:
        parsed_ip = None
    if parsed_ip is not None and not parsed_ip.is_global:
        return NormalizedCompanyUrl(original, "", "blocked", "non_public_address")
    if host in {"localhost", "metadata", "metadata.google.internal"} or host.endswith((".localhost", ".local")):
        return NormalizedCompanyUrl(original, "", "blocked", "blocked_host")
    scheme = parsed.scheme.casefold()
    netloc = host
    if port not in (None, 80 if scheme == "http" else 443):
        netloc = f"{host}:{port}"
    path = parsed.path or "/"
    canonical = urlunsplit((scheme, netloc, path, parsed.query, ""))
    return NormalizedCompanyUrl(original, canonical, "not_validated", "network_validation_not_run")


@dataclass(frozen=True, slots=True)
class CompanyUrlRecord:
    """One deduplicated URL plus enough evidence for an admin detail view."""

    company_id: str
    url_type: str
    url: str
    canonical_url: str
    source: str
    source_observation_id: str
    first_seen_at: str
    last_seen_at: str
    validation_status: str
    validation_reason: str
    redirect_target: str
    primary_state: str
    rule_version: str
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "company_id": self.company_id,
            "url_type": self.url_type,
            "url": self.url,
            "canonical_url": self.canonical_url,
            "source": self.source,
            "source_observation_id": self.source_observation_id,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "validation": {
                "status": self.validation_status,
                "reason": self.validation_reason,
            },
            "validation_status": self.validation_status,
            "redirect_target": self.redirect_target,
            "primary_state": self.primary_state,
            "selected_primary": self.primary_state == "primary",
            "rule_version": self.rule_version,
            "provenance": dict(self.provenance),
        }


@dataclass(frozen=True, slots=True)
class CompanyUrlViewModel:
    company_id: str
    urls: tuple[CompanyUrlRecord, ...]
    rule_version: str
    warnings: tuple[str, ...] = ()

    @property
    def primary_urls(self) -> Mapping[str, CompanyUrlRecord]:
        return {record.url_type: record for record in self.urls if record.primary_state == "primary"}

    def as_dict(self) -> dict[str, Any]:
        return {
            "company_id": self.company_id,
            "urls": [record.as_dict() for record in self.urls],
            "primary_urls": {key: value.as_dict() for key, value in self.primary_urls.items()},
            "rule_version": self.rule_version,
            "warnings": list(self.warnings),
        }


def _items(value: Any) -> list[Any]:
    if value in (None, "", []):
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return [value]


def _candidate_from_value(value: Any, *, url_type: str, source: str, company_id: str) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        item = dict(value)
        url = item.get("url") or item.get("canonical_url") or item.get("value")
        item_type = _normalise_url_type(item.get("url_type") or item.get("type"), url_type)
    else:
        item = {}
        url = value
        item_type = url_type
    if not _text(url):
        return None
    provenance = item.get("provenance") if isinstance(item.get("provenance"), Mapping) else {}
    validation = item.get("validation") if isinstance(item.get("validation"), Mapping) else {}
    return {
        "company_id": _text(item.get("company_id") or company_id),
        "url_type": item_type,
        "url": _text(url),
        "source": _text(item.get("source") or source),
        "source_observation_id": _text(item.get("source_observation_id") or item.get("observation_id")),
        "first_seen_at": _timestamp(item.get("first_seen_at") or item.get("observed_at")),
        "last_seen_at": _timestamp(item.get("last_seen_at") or item.get("observed_at")),
        "validation_status": _text(item.get("validation_status") or validation.get("status")),
        "validation_reason": _text(item.get("validation_reason") or validation.get("reason")),
        "redirect_target": _text(item.get("redirect_target")),
        "selected_primary": _truthy(item.get("selected_primary") or item.get("primary")),
        "provenance": dict(provenance),
    }


def _company_candidates(company: Mapping[str, Any], company_id: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    aliases = {
        "homepage": ("homepage", "homepage_url", "website", "company_website", "site"),
        "careers": ("careers", "careers_page", "careers_url", "career_page"),
        "ats_board": ("ats_board", "ats_url", "ats_board_url"),
        "employer_jobs": ("employer_jobs", "employer_jobs_url", "jobs_url"),
        "application_host": ("application_host", "application_host_url", "application_url"),
        "source": ("source_url", "provenance_url"),
        "enrichment": ("enrichment_url",),
    }
    for url_type, names in aliases.items():
        for name in names:
            for value in _items(company.get(name)):
                candidate = _candidate_from_value(value, url_type=url_type, source="company_record", company_id=company_id)
                if candidate:
                    candidates.append(candidate)
    for field_name, default_type in (("social_urls", "social_profile"), ("profile_urls", "social_profile"), ("enrichment_urls", "enrichment")):
        values = company.get(field_name)
        if isinstance(values, Mapping):
            values = [dict(value, source=str(key)) if isinstance(value, Mapping) else {"url": value, "source": key} for key, value in values.items()]
        for value in _items(values):
            candidate = _candidate_from_value(value, url_type=default_type, source="company_record", company_id=company_id)
            if candidate:
                candidates.append(candidate)
    for value in _items(company.get("company_urls") or company.get("urls")):
        candidate = _candidate_from_value(value, url_type="source", source="company_record", company_id=company_id)
        if candidate:
            candidates.append(candidate)
    return candidates


def _evidence_candidates(evidence: Iterable[Mapping[str, Any] | CompanyUrlRecord], company_id: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in evidence:
        if isinstance(item, CompanyUrlRecord):
            value: Mapping[str, Any] = item.as_dict()
        elif isinstance(item, Mapping):
            value = item
        else:
            continue
        candidate = _candidate_from_value(
            value,
            url_type=_normalise_url_type(value.get("url_type") or value.get("type")),
            source=_text(value.get("source") or "source_observation"),
            company_id=company_id,
        )
        if candidate:
            candidates.append(candidate)
    return candidates


def _source_rank(source: str) -> int:
    source_key = _text(source).casefold()
    return max((rank for name, rank in _SOURCE_PRECEDENCE.items() if name in source_key), default=0)


def build_company_url_view(
    company: Mapping[str, Any],
    url_evidence: Iterable[Mapping[str, Any] | CompanyUrlRecord] = (),
    *,
    rule_version: str = "company_urls_v1",
    max_urls: int = 100,
) -> dict[str, Any]:
    """Build a bounded, provenance-aware company URL view from existing evidence."""

    company_id = _text(company.get("company_id") or company.get("id"))
    if not company_id:
        raise ValueError("company_id_required")
    limit = max(1, min(500, int(max_urls)))
    candidates = _company_candidates(company, company_id) + _evidence_candidates(url_evidence, company_id)
    warnings: list[str] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for candidate in candidates:
        normalized = normalize_company_url(candidate["url"])
        supplied_status = _VALIDATION_ALIASES.get(candidate["validation_status"].casefold(), candidate["validation_status"].casefold())
        if supplied_status in {"valid", "invalid", "blocked", "not_validated", "unknown"}:
            status = supplied_status
        else:
            status = normalized.validation_status
        reason = candidate["validation_reason"] or normalized.validation_reason
        if normalized.validation_status in {"invalid", "blocked"}:
            status = normalized.validation_status
            reason = normalized.validation_reason
        canonical = normalized.canonical_url
        if not canonical:
            canonical = f"invalid:{candidate['url']}"
            warnings.append(f"url_not_canonical:{candidate['url']}")
        candidate = {
            **candidate,
            "canonical_url": canonical,
            "url": normalized.url,
            "validation_status": status,
            "validation_reason": reason,
        }
        grouped.setdefault((candidate["url_type"], canonical), []).append(candidate)

    merged: list[CompanyUrlRecord] = []
    for (url_type, canonical_url), rows in grouped.items():
        representative = max(
            rows,
            key=lambda row: (
                int(row["selected_primary"]),
                int(row["validation_status"] == "valid"),
                _source_rank(row["source"]),
                _timestamp_key(row["last_seen_at"]),
                row["url"],
            ),
        )
        statuses = {row["validation_status"] for row in rows}
        status = "valid" if "valid" in statuses else representative["validation_status"]
        reasons = sorted({_text(row["validation_reason"]) for row in rows if _text(row["validation_reason"])})
        redirect_targets = []
        for row in rows:
            redirect = normalize_company_url(row["redirect_target"])
            redirect_targets.append(redirect.canonical_url or _text(row["redirect_target"]))
        redirect_targets = list(dict.fromkeys(value for value in redirect_targets if value))
        if len(redirect_targets) > 1:
            warnings.append(f"redirect_conflict:{url_type}:{canonical_url}")
        source_values = list(dict.fromkeys(_text(row["source"]) for row in rows if _text(row["source"])))
        observations = list(dict.fromkeys(_text(row["source_observation_id"]) for row in rows if _text(row["source_observation_id"])))
        entries = [
            {
                "source": row["source"],
                "source_observation_id": row["source_observation_id"],
                "validation_status": row["validation_status"],
                "validation_reason": row["validation_reason"],
                "provenance": dict(row["provenance"]),
            }
            for row in rows
        ]
        merged.append(
            CompanyUrlRecord(
                company_id=company_id,
                url_type=url_type,
                url=representative["url"],
                canonical_url=canonical_url,
                source=representative["source"],
                source_observation_id=representative["source_observation_id"],
                first_seen_at=_range_timestamp((row["first_seen_at"] for row in rows), first=True),
                last_seen_at=_range_timestamp((row["last_seen_at"] for row in rows), first=False),
                validation_status=status,
                validation_reason=";".join(reasons),
                redirect_target=redirect_targets[0] if redirect_targets else "",
                primary_state="candidate",
                rule_version=rule_version,
                provenance={"sources": source_values, "observations": observations, "entries": entries},
            )
        )

    selected: list[CompanyUrlRecord] = []
    for url_type in COMPANY_URL_TYPES:
        candidates_for_type = [record for record in merged if record.url_type == url_type]
        if not candidates_for_type:
            continue
        winner = max(
            candidates_for_type,
            key=lambda record: (
                int(any(entry.get("validation_status") == "valid" for entry in record.provenance.get("entries", []))),
                _source_rank(record.source),
                _timestamp_key(record.last_seen_at),
                record.canonical_url,
            ),
        )
        for record in candidates_for_type:
            selected.append(
                replace(record, primary_state="primary" if record is winner else "alternative")
            )
    selected.sort(key=lambda record: (COMPANY_URL_TYPES.index(record.url_type), record.primary_state != "primary", record.canonical_url))
    if len(selected) > limit:
        warnings.append(f"url_view_bounded:{len(selected)}:{limit}")
        selected = selected[:limit]
    view = CompanyUrlViewModel(company_id, tuple(selected), rule_version, tuple(dict.fromkeys(warnings)))
    return view.as_dict()


class CompanyOperations:
    """Bounded, non-persisting company operation contracts for future adapters."""

    def __init__(self, *, logo_adapter: Any = None, max_urls: int = 100):
        self.logo_adapter = logo_adapter
        self.max_urls = max(1, min(500, int(max_urls)))

    def one(
        self,
        company: Mapping[str, Any],
        *,
        url_evidence: Iterable[Mapping[str, Any] | CompanyUrlRecord] = (),
        logo_candidates: Iterable[Any] = (),
        cached_logo: Mapping[str, Any] | None = None,
        persist_logo: bool = False,
    ) -> dict[str, Any]:
        company_id = _text(company.get("company_id") or company.get("id"))
        result: dict[str, Any] = {
            "status": "completed",
            "company_id": company_id,
            "url_view": build_company_url_view(company, url_evidence, max_urls=self.max_urls),
        }
        if self.logo_adapter is not None:
            result["logo"] = self.logo_adapter.resolve_one(
                company,
                candidates=logo_candidates,
                cached=cached_logo,
                persist=persist_logo,
            )
        return result

    def many(
        self,
        companies: Iterable[Mapping[str, Any]],
        *,
        url_evidence_by_company: Mapping[str, Iterable[Mapping[str, Any] | CompanyUrlRecord]] | None = None,
        logo_candidates_by_company: Mapping[str, Iterable[Any]] | None = None,
        cached_logos_by_company: Mapping[str, Mapping[str, Any]] | None = None,
        limit: int = 25,
        persist_logo: bool = False,
    ) -> dict[str, Any]:
        bounded = list(companies)[: max(0, min(100, int(limit)))]
        evidence = url_evidence_by_company or {}
        logos = logo_candidates_by_company or {}
        cached = cached_logos_by_company or {}
        results: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        for company in bounded:
            company_id = _text(company.get("company_id") or company.get("id"))
            try:
                results.append(
                    self.one(
                        company,
                        url_evidence=evidence.get(company_id, ()),
                        logo_candidates=logos.get(company_id, ()),
                        cached_logo=cached.get(company_id),
                        persist_logo=persist_logo,
                    )
                )
            except Exception as exc:  # one bad source row must not abort a bounded set
                failures.append({"company_id": company_id, "error_code": type(exc).__name__, "message": str(exc)})
        return {
            "status": "degraded" if failures else "completed",
            "requested": len(bounded),
            "processed": len(results) + len(failures),
            "succeeded": len(results),
            "failed": len(failures),
            "results": results,
            "failures": failures,
        }


__all__ = [
    "COMPANY_URL_TYPES",
    "CompanyOperations",
    "CompanyUrlRecord",
    "CompanyUrlViewModel",
    "NormalizedCompanyUrl",
    "build_company_url_view",
    "normalize_company_url",
]
