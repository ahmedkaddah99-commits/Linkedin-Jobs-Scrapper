"""Per-company employer-site coverage receipt and completeness classification.

The receipt records what was attempted, what was observed, and why the result is
or is not considered complete.  It is intentionally separate from the legacy
status field so that new consumers can reason about coverage without being bound
to historical string values.

Correctness contract (see ``docs/OPENCODE_E_EMPLOYER_COMPLETENESS_HANDOFF.md``):

* ``expected_count`` is only ever populated from independent source evidence
  (an explicit ``source_reported_total`` produced by the connector).  It is
  never derived from the number of jobs we happened to observe.
* Traversal counts (pages/partitions) are only reported when they were measured;
  otherwise they remain ``None`` (unknown).
* ``confirmed_complete`` requires every authoritative endpoint to be fully
  exhausted, reconciled against any independent total, free of pending details,
  free of caps/blocks/errors, and free of unresolved partition coverage.
* An old complete scan is never allowed to make a newer failed/partial scan
  closure-safe: the current generation's outcome is authoritative, and any
  prior confirmed-complete scan is preserved only as historical reference.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
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

# Families whose public listing is a single flat catalog for one tenant: the
# listing covers all locations/categories/business units, so there are no
# additional partitions to enumerate beyond pagination.
FLAT_LISTING_FAMILIES = {"ats_native", "ats_expansion"}

# Stop reasons that prove the collector hit a cap rather than exhausting the
# source.  A capped scan can never be confirmed complete.
CAP_STOP_REASONS = {"max_requests", "max_pages", "request_budget_exhausted", "budget_exhausted"}

CHALLENGE_MARKERS = ("captcha", "cf-chl-", "challenge", "access denied", "bot", "security")


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _connector_family(provider: str, extraction_methods: list[str]) -> str:
    for method in extraction_methods:
        method_norm = _text(method).casefold()
        if method_norm in CONNECTOR_FAMILIES:
            return CONNECTOR_FAMILIES[method_norm]
    provider_norm = _text(provider).casefold()
    if provider_norm in CONNECTOR_FAMILIES:
        return CONNECTOR_FAMILIES[provider_norm]
    return "generic_direct"


def _partition_state(family: str) -> str:
    """Return whether a family requires partition enumeration for completeness.

    ``flat`` means the listing is a single catalog for one tenant; ``unknown``
    means the source may shard by location/category/entity and the collector has
    not proven that every partition was traversed.
    """

    return "flat" if family in FLAT_LISTING_FAMILIES else "unknown"


def _is_block(error: str, stop_reason: str) -> bool:
    haystack = f"{error} {stop_reason}".casefold()
    return any(marker in haystack for marker in CHALLENGE_MARKERS)


@dataclass(frozen=True)
class EndpointAttempt:
    url: str
    connector_family: str
    transport: str = ""
    role: str = "authoritative"
    pages_attempted: int | None = None
    pages_completed: int | None = None
    partitions_attempted: int | None = None
    partitions_completed: int | None = None
    partition_state: str = "unknown"
    expected_count: int | None = None
    observed_count: int = 0
    accepted_count: int = 0
    pending_detail_count: int = 0
    complete: bool = False
    pagination_complete: bool = False
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
    source_inventory: list[dict[str, Any]] = field(default_factory=list)
    persisted_job_count: int = 0
    terminal_classification: str = "unknown"
    reasons: list[str] = field(default_factory=list)
    completeness_evidence: dict[str, Any] = field(default_factory=dict)
    last_confirmed_complete_at: str = ""
    last_confirmed_complete_generation: str = ""

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
            "source_inventory": [dict(entry) for entry in self.source_inventory],
            "persisted_job_count": self.persisted_job_count,
            "terminal_classification": self.terminal_classification,
            "reasons": list(self.reasons),
            "completeness_evidence": dict(self.completeness_evidence),
            "last_confirmed_complete_at": self.last_confirmed_complete_at,
            "last_confirmed_complete_generation": self.last_confirmed_complete_generation,
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
        pagination_complete = bool(completeness.get("pagination_complete"))
        error = ""
        if status in {"blocked", "source_failed"}:
            error = stop_reason or status
        elif status == "browser_failed":
            error = stop_reason or "browser_failed"

        # Role: the endpoint that established complete coverage is authoritative;
        # every other endpoint is an alternative that did not establish coverage.
        role = "authoritative" if status in {"complete_with_jobs", "confirmed_zero"} else "alternate"

        # Expected total must be independent source evidence, never the observed
        # count.  The connector sets ``source_reported_total`` only when the
        # source exposes a total; otherwise it stays unknown.
        expected_count = target.get("expected_count")
        if expected_count is None:
            expected_count = counts.get("source_reported_total")
        if expected_count is not None:
            try:
                expected_count = int(expected_count)
            except (TypeError, ValueError):
                expected_count = None

        pages_attempted = _measured_int(counts.get("pages"))
        pages_completed = pages_attempted if (complete and pagination_complete) else _measured_int(counts.get("pages_completed"))
        partitions_attempted = _measured_int(counts.get("partitions_attempted"))
        partitions_completed = _measured_int(counts.get("partitions_completed"))

        attempts.append(
            EndpointAttempt(
                url=url,
                connector_family=family,
                transport=_text(target.get("transport")) or "direct",
                role=role,
                pages_attempted=pages_attempted,
                pages_completed=pages_completed,
                partitions_attempted=partitions_attempted,
                partitions_completed=partitions_completed,
                partition_state=_partition_state(family),
                expected_count=expected_count,
                observed_count=int(counts.get("jobs_observed") or 0),
                accepted_count=int(counts.get("jobs_accepted") or 0),
                pending_detail_count=int(counts.get("detail_failures") or 0),
                complete=complete,
                pagination_complete=pagination_complete,
                stop_reason=stop_reason,
                error=error,
            )
        )
    return attempts


def _measured_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


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


def _source_inventory(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the durable all-candidate source inventory recorded by the collector."""

    coverage = result.get("coverage") or {}
    if not isinstance(coverage, Mapping):
        return []
    raw_inventory = coverage.get("source_inventory")
    if not isinstance(raw_inventory, list):
        return []
    return [dict(entry) for entry in raw_inventory if isinstance(entry, Mapping)]


def _reconciles(attempt: EndpointAttempt) -> bool:
    """Return True when any independent source total matches observations."""

    if attempt.expected_count is None:
        return True
    return attempt.observed_count == attempt.expected_count


def _classify(result: Mapping[str, Any], attempts: list[EndpointAttempt]) -> str:
    """Map a collector result to one of the five coverage classifications."""

    outcome = _text(result.get("outcome") or result.get("status")).casefold()
    coverage = result.get("coverage") or {}
    if not isinstance(coverage, Mapping):
        coverage = {}
    budget_exhausted = bool(coverage.get("request_budget_exhausted")) or _text(
        coverage.get("stop_reason")
    ).casefold() == "request_budget_exhausted"

    if outcome in {"blocked"}:
        return "blocked"
    if outcome in {"failed", "collector_error", "discovery_failed", "source_failed", "unsupported"}:
        return "failed"

    if any(_is_block(a.error, a.stop_reason) for a in attempts):
        return "blocked"

    if not attempts:
        # No endpoint was reached.  Budget exhaustion is retryable partial
        # progress; otherwise the company is genuinely unexamined.
        return "partial" if budget_exhausted else "unknown"

    if budget_exhausted:
        return "partial"

    # An unvisited complementary partition (a distinct ATS tenant surfaced by
    # discovery but not traversed) means the company's catalog was not fully
    # accounted for.
    discovery = coverage.get("discovery") or {}
    if isinstance(discovery, Mapping) and discovery.get("complementary_partitions_skipped"):
        return "partial"

    authoritative = [a for a in attempts if a.role == "authoritative"]
    if not authoritative:
        # No endpoint established authoritative coverage.
        return "partial"

    for attempt in authoritative:
        if not attempt.complete:
            return "partial"
        if not attempt.pagination_complete and attempt.connector_family not in FLAT_LISTING_FAMILIES:
            return "partial"
        if attempt.pending_detail_count > 0:
            return "partial"
        if attempt.error:
            return "partial"
        if attempt.stop_reason in CAP_STOP_REASONS:
            return "partial"
        if attempt.partition_state == "unknown":
            # Cannot prove every location/category/entity partition was traversed.
            return "partial"
        if not _reconciles(attempt):
            return "partial"

    if outcome in {"complete_with_jobs", "completed", "confirmed_zero", "no_jobs"}:
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
    inventory = _source_inventory(result)
    source_union = {
        "union_jobs": len(result.get("jobs") or []),
        "duplicates_skipped": sum(int(entry.get("duplicate_count") or 0) for entry in inventory),
        "sources_traversed": sum(1 for entry in inventory if entry.get("traversal_status") == "traversed"),
        "sources_deferred": sum(1 for entry in inventory if entry.get("traversal_status") == "deferred"),
    }
    endpoint_used = ""
    connector_family = ""
    discovery_method = ""
    if attempts:
        authoritative = next((a for a in attempts if a.role == "authoritative"), None)
        primary = authoritative or attempts[0]
        endpoint_used = primary.url
        connector_family = primary.connector_family
        first_target = (result.get("targets") or [{}])[0]
        discovery_method = _text(first_target.get("discovery_method")) if isinstance(first_target, Mapping) else ""
    coverage = result.get("coverage") or {}
    if not isinstance(coverage, Mapping):
        coverage = {}
    completeness_evidence = {
        "outcome": _text(coverage.get("outcome")),
        "targets": len(attempts),
        "complete_snapshot": bool(
            coverage.get("completeness_evidence", {}).get("complete_snapshot")
        ) if isinstance(coverage.get("completeness_evidence"), Mapping) else False,
        "recheck_required": bool(
            coverage.get("recheck_policy", {}).get("recheck_required")
        ) if isinstance(coverage.get("recheck_policy"), Mapping) else True,
        "request_budget_exhausted": bool(coverage.get("request_budget_exhausted")),
        "source_union": source_union,
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
        source_inventory=inventory,
        persisted_job_count=len(result.get("jobs") or []),
        terminal_classification=classification,
        reasons=reasons,
        completeness_evidence=completeness_evidence,
    )


def classify_legacy_result(result: Mapping[str, Any]) -> str:
    """Classify a pre-receipt employer result (status/targets/failures/jobs).

    Legacy runs never recorded pagination or partition evidence, so they can
    never be ``confirmed_complete``.  A positive collection is ``partial``
    (unproven); a genuine empty page is ``partial`` (suspicious empty, not a
    confirmed zero); a timeout/incomplete scan is ``failed``.
    """

    status = _text(result.get("status")).casefold()
    jobs = result.get("jobs") or []
    targets = result.get("targets") or []
    failures = result.get("failures") or []

    if status in {"source_failed", "discovery_failed", "collector_error"}:
        return "failed"
    if any(
        isinstance(f, Mapping) and _is_block(_text(f.get("error")), "")
        for f in failures
    ):
        return "blocked"
    if any(
        isinstance(t, Mapping) and _text(t.get("status")) == "blocked"
        for t in targets
    ):
        return "blocked"
    if jobs:
        return "partial"
    if status == "completed":
        return "partial"
    if status == "partial":
        return "partial"
    if status == "no_jobs":
        target_statuses = {_text(t.get("status")) for t in targets if isinstance(t, Mapping)}
        if "completed" in target_statuses:
            return "partial"
        if "browser_failed" in target_statuses or "incomplete" in target_statuses:
            return "failed"
        return "unknown"
    return "unknown"


def merge_receipts(previous: EmployerCoverageReceipt | None, current: EmployerCoverageReceipt) -> EmployerCoverageReceipt:
    """Merge a prior receipt into the current generation.

    The current generation's classification is always authoritative for coverage:
    a newer failed/partial scan must never be made closure-safe by an older
    confirmed-complete scan.  The prior confirmed-complete result is retained as
    historical reference only.
    """

    if previous is None:
        return current
    if previous.terminal_classification == "confirmed_complete" and current.terminal_classification != "confirmed_complete":
        return replace(
            current,
            last_confirmed_complete_at=previous.created_at or current.last_confirmed_complete_at,
            last_confirmed_complete_generation=previous.generation_id or current.last_confirmed_complete_generation,
        )
    return current


__all__ = [
    "CONNECTOR_FAMILIES",
    "COVERAGE_CLASSIFICATIONS",
    "EmployerCoverageReceipt",
    "EndpointAttempt",
    "build_coverage_receipt",
    "classify_legacy_result",
    "merge_receipts",
]
