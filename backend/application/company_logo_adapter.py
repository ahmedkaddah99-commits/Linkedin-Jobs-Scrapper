"""Provider-independent company logo resolution for bounded operations.

The adapter consumes logo candidates produced elsewhere.  It never fetches a
provider and never requires credentials.  Validation reuses the existing safe
``company_logo`` primitives; optional cache persistence happens only when an
explicit, injected storage object is supplied with ``persist=True``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from backend.application.company_logo import (
    LogoValidationError,
    ValidatedLogo,
    cache_logo,
    deterministic_monogram,
    validate_logo,
    validate_official_url,
)


class LogoStorage(Protocol):
    def exists(self, key: str) -> bool: ...

    def put(self, key: str, data: bytes, *, content_type: str, metadata: Mapping[str, str] | None = None) -> Any: ...


def _text(value: Any) -> str:
    return str(value or "").strip()


def _now(value: datetime | str | None = None) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = _text(value)
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: Any) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _provider_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


@dataclass(frozen=True, slots=True)
class LogoCandidate:
    provider: str
    data: bytes
    content_type: str
    source_url: str = ""
    observed_at: str = ""
    provenance: Mapping[str, Any] = field(default_factory=dict)
    terms_metadata: Mapping[str, Any] = field(default_factory=dict)
    next_refresh_at: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], *, default_provider: str = "configured_provider") -> "LogoCandidate":
        return cls(
            provider=_text(value.get("provider") or value.get("source") or default_provider),
            data=bytes(value.get("data") or value.get("logo_bytes") or b""),
            content_type=_text(value.get("content_type") or value.get("logo_content_type") or "image/png"),
            source_url=_text(value.get("source_url") or value.get("logo_source_url")),
            observed_at=_text(value.get("observed_at") or ""),
            provenance=dict(value.get("provenance") or {}) if isinstance(value.get("provenance"), Mapping) else {},
            terms_metadata=dict(value.get("terms_metadata") or {}) if isinstance(value.get("terms_metadata"), Mapping) else {},
            next_refresh_at=_text(value.get("next_refresh_at") or ""),
        )


@dataclass(frozen=True, slots=True)
class LogoView:
    company_id: str
    company_name: str
    state: str
    refresh_state: str
    provider: str
    source_url: str
    object_key: str
    content_hash: str
    content_type: str
    validation_status: str
    cache_status: str
    last_attempt_at: str
    last_success_at: str
    next_refresh_at: str
    failure_code: str
    warnings: tuple[str, ...]
    monogram: str
    provenance: Mapping[str, Any] = field(default_factory=dict)
    terms_metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "company_id": self.company_id,
            "company_name": self.company_name,
            "state": self.state,
            "refresh_state": self.refresh_state,
            "provider": self.provider,
            "source_url": self.source_url,
            "object_key": self.object_key,
            "content_hash": self.content_hash,
            "content_type": self.content_type,
            "validation": {"status": self.validation_status},
            "validation_status": self.validation_status,
            "cache_status": self.cache_status,
            "last_attempt_at": self.last_attempt_at,
            "last_success_at": self.last_success_at,
            "next_refresh_at": self.next_refresh_at,
            "failure_code": self.failure_code,
            "warnings": list(self.warnings),
            "monogram": self.monogram,
            "provenance": dict(self.provenance),
            "terms_metadata": dict(self.terms_metadata),
        }


def candidate_from_provider_result(value: Any, *, default_provider: str = "configured_provider") -> LogoCandidate | None:
    """Adapt the existing enrichment result shape without importing its service."""

    data = _provider_value(value, "logo_bytes")
    if data is None and isinstance(value, Mapping):
        nested = value.get("logo")
        if isinstance(nested, Mapping):
            value = nested
            data = nested.get("data") or nested.get("logo_bytes")
    if data is None:
        return None
    return LogoCandidate(
        provider=_text(_provider_value(value, "provider") or _provider_value(value, "source") or default_provider),
        data=bytes(data),
        content_type=_text(_provider_value(value, "content_type") or _provider_value(value, "logo_content_type") or "image/png"),
        source_url=_text(_provider_value(value, "source_url") or _provider_value(value, "logo_source_url")),
        observed_at=_text(_provider_value(value, "observed_at")),
        provenance=dict(_provider_value(value, "provenance") or {}) if isinstance(_provider_value(value, "provenance"), Mapping) else {},
        terms_metadata=dict(_provider_value(value, "terms_metadata") or {}) if isinstance(_provider_value(value, "terms_metadata"), Mapping) else {},
        next_refresh_at=_text(_provider_value(value, "next_refresh_at")),
    )


def _refresh_state(cached: Mapping[str, Any] | None, *, now: datetime) -> str:
    if not cached:
        return "never_attempted"
    next_refresh = _parse_time(cached.get("next_refresh_at"))
    if next_refresh is not None and next_refresh > now:
        return "fresh"
    if _text(cached.get("last_attempt_at")) or _text(cached.get("last_success_at")):
        return "due"
    return "never_attempted"


def _cached_view(company_id: str, company_name: str, cached: Mapping[str, Any], *, now: datetime) -> LogoView:
    object_key = _text(cached.get("object_key"))
    content_hash = _text(cached.get("content_hash"))
    source_url = _text(cached.get("source_url"))
    status = _text(cached.get("status") or "cached")
    refresh = _refresh_state(cached, now=now)
    return LogoView(
        company_id=company_id,
        company_name=company_name,
        state="cached" if object_key or content_hash else "fallback",
        refresh_state=refresh,
        provider=_text(cached.get("provider") or "cached_logo"),
        source_url=source_url,
        object_key=object_key,
        content_hash=content_hash,
        content_type=_text(cached.get("content_type")),
        validation_status=_text(cached.get("validation_status") or "valid" if object_key or content_hash else "not_validated"),
        cache_status=status,
        last_attempt_at=_text(cached.get("last_attempt_at")),
        last_success_at=_text(cached.get("last_success_at") or cached.get("observed_at")),
        next_refresh_at=_text(cached.get("next_refresh_at")),
        failure_code=_text(cached.get("failure_code")),
        warnings=tuple(_text(item) for item in (cached.get("warnings") or []) if _text(item)),
        monogram=deterministic_monogram(company_name),
        provenance=dict(cached.get("provenance") or {}) if isinstance(cached.get("provenance"), Mapping) else {},
        terms_metadata=dict(cached.get("terms_metadata") or {}) if isinstance(cached.get("terms_metadata"), Mapping) else {},
    )


class CompanyLogoAdapter:
    """Resolve one or many supplied logo candidates without provider I/O."""

    def __init__(self, *, storage: LogoStorage | None = None, refresh_after_days: int = 30, rule_version: str = "company_logo_v1"):
        self.storage = storage
        self.refresh_after_days = max(1, int(refresh_after_days))
        self.rule_version = _text(rule_version) or "company_logo_v1"

    def resolve_one(
        self,
        company: Mapping[str, Any],
        *,
        candidates: Iterable[LogoCandidate | Mapping[str, Any] | Any] = (),
        cached: Mapping[str, Any] | None = None,
        now: datetime | str | None = None,
        persist: bool = False,
    ) -> dict[str, Any]:
        current = _now(now)
        company_id = _text(company.get("company_id") or company.get("id"))
        company_name = _text(company.get("canonical_name") or company.get("name") or company_id)
        if not company_id:
            raise ValueError("company_id_required")
        failures: list[dict[str, str]] = []
        valid: list[tuple[LogoCandidate, ValidatedLogo]] = []
        for raw_candidate in candidates:
            candidate: LogoCandidate | None = None
            try:
                candidate = raw_candidate if isinstance(raw_candidate, LogoCandidate) else (
                    LogoCandidate.from_mapping(raw_candidate) if isinstance(raw_candidate, Mapping) else candidate_from_provider_result(raw_candidate)
                )
                if candidate is None:
                    failures.append({"provider": "", "error_code": "logo_payload_missing"})
                    continue
                validated = validate_logo(candidate.data, candidate.content_type)
                if candidate.source_url:
                    candidate_source_url = validate_official_url(candidate.source_url)
                    candidate = LogoCandidate(
                        provider=candidate.provider,
                        data=candidate.data,
                        content_type=candidate.content_type,
                        source_url=candidate_source_url,
                        observed_at=candidate.observed_at,
                        provenance=candidate.provenance,
                        terms_metadata=candidate.terms_metadata,
                        next_refresh_at=candidate.next_refresh_at,
                    )
                valid.append((candidate, validated))
            except (LogoValidationError, TypeError, ValueError) as exc:
                failures.append({"provider": candidate.provider if candidate else "", "source_url": candidate.source_url if candidate else "", "error_code": str(exc) or type(exc).__name__})

        if valid:
            candidate, validated = valid[0]
            object_key = ""
            cache_status = "not_requested"
            warnings: list[str] = []
            if persist and self.storage is None:
                cache_status = "unavailable"
                warnings.append("logo_cache_unavailable")
            elif persist:
                try:
                    object_key, _written = cache_logo(self.storage, company_id, validated)
                    cache_status = "cached"
                except Exception as exc:  # cache failure must not discard a validated candidate
                    cache_status = "failed"
                    warnings.append("logo_cache_failed")
                    failures.append({"provider": candidate.provider, "source_url": candidate.source_url, "error_code": type(exc).__name__})
            if not candidate.source_url:
                warnings.append("logo_source_url_missing")
            if failures:
                warnings.append("logo_candidate_failures")
            next_refresh = candidate.next_refresh_at or _iso(current + timedelta(days=self.refresh_after_days))
            view = LogoView(
                company_id=company_id,
                company_name=company_name,
                state="cached" if object_key else "validated",
                refresh_state="fresh",
                provider=candidate.provider,
                source_url=candidate.source_url,
                object_key=object_key,
                content_hash=validated.content_hash,
                content_type=validated.content_type,
                validation_status="valid",
                cache_status=cache_status,
                last_attempt_at=_iso(current),
                last_success_at=_text(candidate.observed_at) or _iso(current),
                next_refresh_at=next_refresh,
                failure_code="",
                warnings=tuple(dict.fromkeys(warnings)),
                monogram=deterministic_monogram(company_name),
                provenance={
                    "provider": candidate.provider,
                    "source_url": candidate.source_url,
                    "observed_at": candidate.observed_at,
                    "rule_version": self.rule_version,
                    **dict(candidate.provenance),
                },
                terms_metadata=dict(candidate.terms_metadata),
            )
        elif cached:
            view = _cached_view(company_id, company_name, cached, now=current)
            warnings = list(view.warnings)
            if failures:
                warnings.append("logo_refresh_failed")
            view = replace(view, warnings=tuple(dict.fromkeys(warnings)))
        else:
            view = LogoView(
                company_id=company_id,
                company_name=company_name,
                state="fallback",
                refresh_state="never_attempted",
                provider="",
                source_url="",
                object_key="",
                content_hash="",
                content_type="",
                validation_status="not_validated",
                cache_status="not_requested",
                last_attempt_at=_iso(current) if failures else "",
                last_success_at="",
                next_refresh_at="",
                failure_code=failures[0]["error_code"] if failures else "",
                warnings=("logo_unavailable", "monogram_fallback", "logo_candidate_failures") if failures else ("logo_unavailable", "monogram_fallback"),
                monogram=deterministic_monogram(company_name),
                provenance={"rule_version": self.rule_version},
                terms_metadata={},
            )
        payload = view.as_dict()
        payload["candidate_failures"] = failures
        payload["rule_version"] = self.rule_version
        return payload

    def resolve_many(
        self,
        companies: Iterable[Mapping[str, Any]],
        *,
        candidates_by_company: Mapping[str, Iterable[LogoCandidate | Mapping[str, Any] | Any]] | None = None,
        cached_by_company: Mapping[str, Mapping[str, Any]] | None = None,
        limit: int = 25,
        now: datetime | str | None = None,
        persist: bool = False,
    ) -> dict[str, Any]:
        bounded = list(companies)[: max(0, min(100, int(limit)))]
        candidates = candidates_by_company or {}
        cached = cached_by_company or {}
        results: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        for company in bounded:
            company_id = _text(company.get("company_id") or company.get("id"))
            try:
                results.append(self.resolve_one(company, candidates=candidates.get(company_id, ()), cached=cached.get(company_id), now=now, persist=persist))
            except Exception as exc:  # bounded-many isolation contract
                failures.append({"company_id": company_id, "error_code": type(exc).__name__, "message": str(exc)})
        return {
            "status": "degraded" if failures else "completed",
            "requested": len(bounded),
            "processed": len(results) + len(failures),
            "succeeded": len(results),
            "failed": len(failures),
            "results": results,
            "failures": failures,
            "rule_version": self.rule_version,
        }


__all__ = [
    "CompanyLogoAdapter",
    "LogoCandidate",
    "LogoStorage",
    "LogoView",
    "candidate_from_provider_result",
]
