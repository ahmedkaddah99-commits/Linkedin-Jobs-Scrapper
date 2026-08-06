from __future__ import annotations

from copy import deepcopy
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def canonicalize_target_url(url: str) -> str:
    """Return the durable target URL while retaining functional query values."""

    parts = urlsplit(str(url or "").strip())
    if not parts.scheme or not parts.netloc:
        raise ValueError("Acquisition target URL must be an absolute URL.")
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_") and key.casefold() not in {"gclid", "fbclid", "mc_cid", "mc_eid"}
        ]
    )
    path = parts.path or "/"
    if not path.endswith("/") and not parts.query:
        path = f"{path}/"
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, query, ""))


PHASE_A_TARGETS: tuple[dict[str, object], ...] = (
    {
        "target_id": "siemens",
        "target_kind": "employer_career_site",
        "display_name": "Siemens Industry Software",
        "canonical_target_url": "https://www.siemens.com/en-us/company/jobs",
        "provenance_url": "https://www.siemens.com/en-us/company/jobs",
        "request_url": "https://www.siemens.com/en-us/company/jobs",
        "connector": "bounded_probe",
        "maturity_state": "unproven",
        "enabled": False,
        "disabled_reason": "phase_a_target_disabled_by_default",
        "publication_enabled": False,
        "max_direct_requests": 3,
        "request_mode": "direct",
        "policy_version": "phase_a_v1",
    },
    {
        "target_id": "basf",
        "target_kind": "employer_career_site",
        "display_name": "BASF",
        "canonical_target_url": "https://basf.jobs/",
        "provenance_url": "https://basf.jobs/",
        "request_url": "https://basf.jobs/",
        "connector": "bounded_probe",
        "maturity_state": "unproven",
        "enabled": False,
        "disabled_reason": "phase_a_target_disabled_by_default",
        "publication_enabled": False,
        "max_direct_requests": 3,
        "request_mode": "direct",
        "policy_version": "phase_a_v1",
    },
    {
        "target_id": "bosch",
        "target_kind": "employer_career_site",
        "display_name": "Bosch",
        "canonical_target_url": "https://jobs.bosch.de/",
        "provenance_url": "https://www.bosch.de/karriere/",
        "request_url": "https://jobs.bosch.de/",
        "connector": "bounded_probe",
        "maturity_state": "unproven",
        "enabled": False,
        "disabled_reason": "phase_a_target_disabled_by_default",
        "publication_enabled": False,
        "max_direct_requests": 3,
        "request_mode": "direct",
        "policy_version": "phase_a_v1",
    },
    {
        "target_id": "dhl",
        "target_kind": "employer_career_site",
        "display_name": "Deutsche Post/DHL",
        "canonical_target_url": "https://careers.dhl.com/eu/de",
        "provenance_url": "https://careers.dhl.com/eu/de",
        "request_url": "https://careers.dhl.com/eu/de",
        "connector": "bounded_probe",
        "maturity_state": "unproven",
        "enabled": False,
        "disabled_reason": "phase_a_target_disabled_by_default",
        "publication_enabled": False,
        "max_direct_requests": 3,
        "request_mode": "direct",
        "policy_version": "phase_a_v1",
    },
    {
        "target_id": "adidas",
        "target_kind": "employer_career_site",
        "display_name": "adidas",
        "canonical_target_url": "https://careers.adidas-group.com/",
        "provenance_url": "https://careers.adidas-group.com/",
        "request_url": "https://careers.adidas-group.com/",
        "connector": "bounded_probe",
        "maturity_state": "unproven",
        "enabled": False,
        "disabled_reason": "phase_a_target_disabled_by_default",
        "publication_enabled": False,
        "max_direct_requests": 3,
        "request_mode": "direct",
        "policy_version": "phase_a_v1",
    },
    {
        "target_id": "n26_greenhouse",
        "target_kind": "ats_connector_validation",
        "display_name": "N26 Greenhouse",
        "canonical_target_url": "https://job-boards.greenhouse.io/n26",
        "provenance_url": "https://developers.greenhouse.io/job-board.html",
        "request_url": "https://boards-api.greenhouse.io/v1/boards/n26/jobs?content=true",
        "connector": "greenhouse",
        "provider": "greenhouse",
        "source_token": "n26",
        "canonical_company_name": "N26",
        "official_employer_hosts": ["n26.com"],
        "maturity_state": "candidate",
        "enabled": False,
        "disabled_reason": "connector_validation_disabled_by_default",
        "publication_enabled": False,
        "max_direct_requests": 2,
        "request_mode": "direct",
        "policy_version": "phase_a_v1",
    },
    {
        "target_id": "qonto_lever",
        "target_kind": "ats_connector_validation",
        "display_name": "Qonto Lever",
        "canonical_target_url": "https://jobs.lever.co/qonto",
        "provenance_url": "https://github.com/lever/postings-api",
        "request_url": "https://api.lever.co/v0/postings/qonto?mode=json",
        "connector": "lever",
        "provider": "lever",
        "source_token": "qonto",
        "canonical_company_name": "Qonto",
        "official_employer_hosts": ["qonto.com"],
        "maturity_state": "candidate",
        "enabled": False,
        "disabled_reason": "connector_validation_disabled_by_default",
        "publication_enabled": False,
        "max_direct_requests": 2,
        "request_mode": "direct",
        "policy_version": "phase_a_v1",
    },
)


def load_phase_a_manifest() -> list[dict[str, object]]:
    """Return a copy so callers cannot mutate the server-owned manifest."""

    manifest = deepcopy(list(PHASE_A_TARGETS))
    for target in manifest:
        target["canonical_target_url"] = canonicalize_target_url(str(target["canonical_target_url"]))
    return manifest


__all__ = ["PHASE_A_TARGETS", "canonicalize_target_url", "load_phase_a_manifest"]
