"""Per-company employer-site coverage receipt and completeness classification.

The receipt records what was attempted, what was observed, and why the result is
or is not considered complete.  It is intentionally separate from the legacy
status field so that new consumers can reason about coverage without being bound
to historical string values.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


COVERAGE_CLASSIFICATIONS = (
    "confirmed_complete",
    "partial",
    "blocked",
    "failed",
    "unknown",
)

# Connector families supported by the employer collector.  The value is the
# canonical family name recorded on coverage receipts.
CONNECTOR_FAMILIES = {
    "greenhouse": "ats_native",
    "lever": "ats_native",
    "workday": "ats_expansion",
    "personio": "ats_expansion",
    "recruitee": "ats_expansion",
    "smartrecruiters": "ats_expansion",
    "generic_employer_site": "generic_direct",
    "json_ld": "generic_direct",
    "embedded_json": "generic_direct",
    "static_html": "generic_direct",
    "xhr": "generic_browser",
    "browser_rendered": "generic_browser",
    "browser": "generic_browser",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _connector_family(provider: str, extraction_methods: list[str]) -> str:
    # Prefer extraction-method family when it is more specific than the
    # provider (e.g. browser-rendered jobs discovered on a generic site).
    for method in extraction_methods:
        method_norm = _text(method).casefold()
        if method_norm in CONNECTOR_FAMILIES:
            return CONNECTOR_FAMILIES[method_norm]
    provider_norm = _text(provider).casefold()
    if provider_norm in CONNECTOR_FAMILIES:
        return CONNECTOR_FAMILIES[provider_norm]
    return "generic_direct"


def _sum_int(values: Mapping[str, Any], key: str) -> int:
    total = 0
    for item in values.values():
        if isinstance(item, Mapping):
            try:
                total += max(0, int(item.get(key) or 0))
            except (TypeError, ValueError):
                pass
    return total


@dataclass(frozen=True)
class EndpointAttempt:
    url: str
    connector_family: str
    transport: str
    pages_attempted: int = 0
    pages_completed: int = 0
    partitions_attempted: int = 0
    partitions_completed: int = 0
    expected_count: int | None = None
    observed_count: int = 0
    accepted_count: int = 0
    pending_detail_count: int = 0
    complete: bool = False
    stop_reason: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EmployerCoverageReceipt:
    """Machine-readable coverage evidence for one company acquisition."""

    company_id: str
    company_name: str = ""
    website_url: str = ""
    generation_id: str = ""
    source_version: str = ""
    created_at: str = field(default_factory=_utc_now)
    endpoint_used: str = ""
    connector_family: str = ""
    discovery_method: str = ""
    attempts: list[EndpointAttempt] = field(default_factory=list)
    persisted_job_count: int = 0
    terminal_classification: str = "unknown"
    reasons: list[str] = field(default_factory=list)
    completeness_evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_id": self.company_id,
            "company_name": self.company_name,
            "website_url": self.website_url,
            "generation_id": self.generation_id,
            "source_version": self.source_version,
            "created_at": self.created_at,
            "endpoint_used": self.endpoint_used,
            "connector_family": self.connector_family,
            "discovery_method": self.discovery_method,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "persisted_job_count": self.persisted_job_count,
            "terminal_classification": self.terminal_classification,
            "reasons": list(self.reasons),
            "completeness_evidence": dict(self.completeness_evidence),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


def _extract_attempts(result: Mapping[str, Any]) -> list[EndpointAttempt]:
    attempts: list[EndpointAttempt] = []
    targets = result.get("targets") or []
    if not isinstance(targets, list):
        return attempts
    for target in targets:
        if not isinstance(target, Mapping):
            continue
        url = _text(target.get("url"))
        if not url:
            continue
        provider = _text(target.get("provider"))
        extraction_methods = target.get("extraction_methods") or []
        if not isinstance(extraction_methods, list):
            extraction_methods = []
        family = _connector_family(provider, extraction_methods)
        counts = target.get("counts") or {}
        if not isinstance(counts, Mapping):
            counts = {}
        completeness = target.get("completeness_evidence") or {}
        if not isinstance(completeness, Mapping):
            completeness = {}
        stop_reason = _text(target.get("stop_reason"))
        status = _text(target.get("status"))
        complete = bool(target.get("complete_snapshot"))
        error = ""
        if status in {"blocked", "source_failed"}:
            error = stop_reason or status
        attempts.append(
            EndpointAttempt(
                url=url,
                connector_family=family,
                transport=_text(target.get("transport")) or "direct",
                pages_attempted=int(counts.get("pages") or 0),
                pages_completed=int(counts.get("pages") or 0) if complete else 0,
                partitions_attempted=1,
                partitions_completed=1 if complete else 0,
                expected_count=int(counts.get("jobs_observed") or 0) or None,
                observed_count=int(counts.get("jobs_observed") or 0),
                accepted_count=int(counts.get("jobs_accepted") or 0),
                pending_detail_count=int(counts.get("detail_failures") or 0),
                complete=complete,
                stop_reason=stop_reason,
                error=error,
            )
        )
    return attempts


def _failure_reasons(result: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    failures = result.get("failures") or []
    if isinstance(failures, list):
        for failure in failures:
            if isinstance(failure, Mapping):
                stage = _text(failure.get("stage"))
                error = _text(failure.get("error"))
                reason = _text(failure.get("reason"))
                if reason:
                    reasons.append(f"{stage}:{reason}")
                elif error:
                    reasons.append(f"{stage}:{error}")
                else:
                    reasons.append(stage)
    coverage = result.get("coverage") or {}
    if isinstance(coverage, Mapping):
        stop_reason = _text(coverage.get("stop_reason"))
        if (
            stop_reason
            and stop_reason not in {"collection_completed", "pagination_complete", "rendered_page_complete", "embedded_payload_complete"}
            and stop_reason not in reasons
        ):
            reasons.append(stop_reason)
        if coverage.get("request_budget_exhausted"):
            reasons.append("request_budget_exhausted")
    return reasons


def _classify(result: Mapping[str, Any], attempts: list[EndpointAttempt]) -> str:
    """Map a collector result to one of the five coverage classifications.

    ``confirmed_complete`` requires an authoritative endpoint that was fully
    exhausted with no unvisited partitions, no pending details, and no active
    block or cap.  Anything less certain is reported as ``partial``,
    ``blocked``, ``failed`` or ``unknown``.
    """

    outcome = _text(result.get("outcome") or result.get("status")).casefold()
    if outcome in {"blocked"}:
        return "blocked"
    if outcome in {"failed", "collector_error", "discovery_failed", "source_failed"}:
        return "failed"
    failures = result.get("failures") or []
    if not attempts:
        if isinstance(failures, list) and failures:
            failure_reasons = {_text(f.get("reason") or f.get("error")).casefold() for f in failures if isinstance(f, Mapping)}
            if "request_budget_exhausted" in failure_reasons or "request_budget_exhausted" in {
                _text(result.get("coverage", {}).get("stop_reason")).casefold()
                if isinstance(result.get("coverage"), Mapping)
                else ""
            }:
                return "failed"
        return "unknown"

    # Only a single authoritative endpoint that completed cleanly can confirm
    # completeness.  Multiple endpoints or a fallback path means we observed
    # something but cannot prove we exhausted the canonical source.
    complete_attempts = [attempt for attempt in attempts if attempt.complete]
    if len(complete_attempts) != 1:
        if outcome in {"confirmed_zero", "no_jobs"}:
            # A confirmed-zero result from an incomplete source is still partial
            # because we cannot prove exhaustiveness.
            return "partial"
        return "partial"

    attempt = complete_attempts[0]
    if attempt.pending_detail_count > 0:
        return "partial"
    if attempt.error:
        return "partial"
    if outcome in {"complete_with_jobs", "completed"}:
        return "confirmed_complete"
    if outcome in {"confirmed_zero", "no_jobs"}:
        return "confirmed_complete"
    return "partial"


def build_coverage_receipt(
    result: Mapping[str, Any],
    *,
    generation_id: str = "",
    source_version: str = "",
) -> EmployerCoverageReceipt:
    """Build a coverage receipt from an EmployerCollectionResult dict."""

    company = result.get("company") or {}
    if not isinstance(company, Mapping):
        company = {}
    company_id = _text(company.get("canonical_company_id")) or _text(company.get("website_url"))
    attempts = _extract_attempts(result)
    classification = _classify(result, attempts)
    reasons = _failure_reasons(result)
    endpoint_used = ""
    connector_family = ""
    discovery_method = ""
    if attempts:
        endpoint_used = attempts[0].url
        connector_family = attempts[0].connector_family
        discovery_method = _text((result.get("targets") or [{}])[0].get("discovery_method")) if result.get("targets") else ""
    coverage = result.get("coverage") or {}
    if not isinstance(coverage, Mapping):
        coverage = {}
    completeness_evidence = {
        "outcome": _text(coverage.get("outcome")),
        "targets": len(attempts),
        "complete_snapshot": bool(coverage.get("completeness_evidence", {}).get("complete_snapshot")) if isinstance(coverage.get("completeness_evidence"), Mapping) else False,
        "recheck_required": bool(coverage.get("recheck_policy", {}).get("recheck_required")) if isinstance(coverage.get("recheck_policy"), Mapping) else True,
        "request_budget_exhausted": bool(coverage.get("request_budget_exhausted")),
    }
    return EmployerCoverageReceipt(
        company_id=company_id,
        company_name=_text(company.get("company_name")),
        website_url=_text(company.get("website_url")),
        generation_id=generation_id,
        source_version=source_version,
        endpoint_used=endpoint_used,
        connector_family=connector_family,
        discovery_method=discovery_method,
        attempts=attempts,
        persisted_job_count=len(result.get("jobs") or []),
        terminal_classification=classification,
        reasons=reasons,
        completeness_evidence=completeness_evidence,
    )


def merge_receipts(previous: EmployerCoverageReceipt | None, current: EmployerCoverageReceipt) -> EmployerCoverageReceipt:
    """Keep the more complete receipt when a company is recollected.

    A confirmed_complete receipt is never downgraded.  A blocked or failed
    receipt is preserved only if the new receipt is unknown or equally bad.
    """

    if previous is None:
        return current
    precedence = {"confirmed_complete": 4, "partial": 3, "blocked": 2, "failed": 1, "unknown": 0}
    if precedence.get(previous.terminal_classification, 0) >= precedence.get(current.terminal_classification, 0):
        return previous
    return current


__all__ = [
    "CONNECTOR_FAMILIES",
    "COVERAGE_CLASSIFICATIONS",
    "EmployerCoverageReceipt",
    "EndpointAttempt",
    "build_coverage_receipt",
    "merge_receipts",
]
