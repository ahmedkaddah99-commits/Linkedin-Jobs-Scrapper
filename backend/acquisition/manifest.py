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
        "canonical_target_url": "https://jobs.siemens.com/en_US/externaljobs/SearchJobs/?42392=%5B67940248%5D&42392_format=17551&listFilterMode=1&folderRecordsPerPage=6",
        "provenance_url": "https://www.siemens.com/en-us/company/jobs",
        "request_url": "https://jobs.siemens.com/en_US/externaljobs/SearchJobs/?42392=%5B67940248%5D&42392_format=17551&listFilterMode=1&folderRecordsPerPage=6",
        "connector": "generic_jsonld",
        "canonical_company_name": "Siemens",
        "official_employer_hosts": ["siemens.com", "jobs.siemens.com"],
        "maturity_state": "candidate",
        "enabled": False,
        "disabled_reason": "phase_a_target_disabled_by_default",
        "admin_import_enabled": True,
        "publication_enabled": False,
        "max_direct_requests": 7,
        "request_mode": "direct",
        "config": {
            "max_retries": 1,
            "admin_scope": {"max_pages": 6, "max_requests": 7, "full_source_import": False},
            "company_profile": {
                "website": "https://www.siemens.com/",
                "careers_page": "https://www.siemens.com/en-us/company/jobs",
                "ats_url": "https://jobs.siemens.com/en_US/externaljobs/SearchJobs/",
            },
        },
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
        "config": {
            "company_profile": {
                "website": "https://n26.com/",
                "careers_page": "https://n26.com/en-eu/careers/",
                "ats_url": "https://job-boards.greenhouse.io/n26",
            }
        },
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
        "config": {
            "company_profile": {
                "website": "https://qonto.com/",
                "careers_page": "https://qonto.com/en/careers/",
                "ats_url": "https://jobs.lever.co/qonto",
            }
        },
        "maturity_state": "candidate",
        "enabled": False,
        "disabled_reason": "connector_validation_disabled_by_default",
        "publication_enabled": False,
        "max_direct_requests": 2,
        "request_mode": "direct",
        "policy_version": "phase_a_v1",
    },
    {
        "target_id": "lowell_workday",
        "target_kind": "ats_connector_validation",
        "display_name": "Lowell Workday",
        "canonical_target_url": "https://lowell.wd3.myworkdayjobs.com/de-DE/LowellGroup_Careers2",
        "provenance_url": "https://www.lowell.com/",
        "request_url": "https://lowell.wd3.myworkdayjobs.com/de-DE/LowellGroup_Careers2",
        "connector": "workday",
        "provider": "workday",
        "source_token": "lowell",
        "canonical_company_name": "Lowell",
        "official_employer_hosts": ["lowell.com", "lowell.wd3.myworkdayjobs.com"],
        "maturity_state": "candidate",
        "enabled": False,
        "disabled_reason": "phase_a_target_disabled_by_default",
        "admin_import_enabled": True,
        "publication_enabled": False,
        "max_direct_requests": 1,
        "request_mode": "direct",
        "config": {
            "page_size": 10,
            "max_retries": 1,
            "admin_scope": {"max_pages": 1, "max_requests": 1, "full_source_import": False},
            "company_profile": {
                "website": "https://www.lowell.com/",
                "careers_page": "https://lowell.wd3.myworkdayjobs.com/de-DE/LowellGroup_Careers2",
                "ats_url": "https://lowell.wd3.myworkdayjobs.com/de-DE/LowellGroup_Careers2",
            },
        },
        "policy_version": "phase_a_v1",
    },
    {
        "target_id": "liqui_moly_personio",
        "target_kind": "ats_connector_validation",
        "display_name": "Liqui Moly Personio",
        "canonical_target_url": "https://liqui-moly-gmbh.jobs.personio.com/",
        "provenance_url": "https://www.liqui-moly.com/",
        "request_url": "https://liqui-moly-gmbh.jobs.personio.com/",
        "connector": "personio",
        "provider": "personio",
        "source_token": "liqui-moly-gmbh",
        "canonical_company_name": "LIQUI MOLY",
        "official_employer_hosts": ["liqui-moly.com", "liqui-moly-gmbh.jobs.personio.com"],
        "maturity_state": "candidate",
        "enabled": False,
        "disabled_reason": "phase_a_target_disabled_by_default",
        "admin_import_enabled": True,
        "publication_enabled": False,
        "max_direct_requests": 1,
        "request_mode": "direct",
        "config": {
            "page_size": 100,
            "max_retries": 1,
            "admin_scope": {"max_pages": 1, "max_requests": 1, "full_source_import": False},
            "company_profile": {
                "website": "https://www.liqui-moly.com/",
                "careers_page": "https://liqui-moly-gmbh.jobs.personio.com/",
                "ats_url": "https://liqui-moly-gmbh.jobs.personio.com/",
            },
        },
        "policy_version": "phase_a_v1",
    },
    {
        "target_id": "die_bayerische_recruitee",
        "target_kind": "ats_connector_validation",
        "display_name": "die Bayerische Recruitee",
        "canonical_target_url": "https://diebayerische.recruitee.com/",
        "provenance_url": "https://www.diebayerische.de/",
        "request_url": "https://diebayerische.recruitee.com/",
        "connector": "recruitee",
        "provider": "recruitee",
        "source_token": "diebayerische",
        "canonical_company_name": "die Bayerische",
        "official_employer_hosts": ["diebayerische.de", "diebayerische.recruitee.com"],
        "maturity_state": "candidate",
        "enabled": False,
        "disabled_reason": "phase_a_target_disabled_by_default",
        "admin_import_enabled": True,
        "publication_enabled": False,
        "max_direct_requests": 1,
        "request_mode": "direct",
        "config": {
            "page_size": 100,
            "max_retries": 1,
            "admin_scope": {"max_pages": 1, "max_requests": 1, "full_source_import": False},
            "company_profile": {
                "website": "https://www.diebayerische.de/",
                "careers_page": "https://diebayerische.recruitee.com/",
                "ats_url": "https://diebayerische.recruitee.com/",
            },
        },
        "policy_version": "phase_a_v1",
    },
    {
        "target_id": "rheingroup_smartrecruiters",
        "target_kind": "ats_connector_validation",
        "display_name": "RheinGroup SmartRecruiters",
        "canonical_target_url": "https://careers.smartrecruiters.com/RheinGroup",
        "provenance_url": "https://careers.smartrecruiters.com/RheinGroup",
        "request_url": "https://careers.smartrecruiters.com/RheinGroup",
        "connector": "smartrecruiters",
        "provider": "smartrecruiters",
        "source_token": "RheinGroup",
        "canonical_company_name": "RheinGroup",
        "official_employer_hosts": [
            "careers.smartrecruiters.com",
            "jobs.smartrecruiters.com",
            "api.smartrecruiters.com",
            "rhein-bmw.de",
        ],
        "maturity_state": "candidate",
        "enabled": False,
        "disabled_reason": "phase_a_target_disabled_by_default",
        "admin_import_enabled": True,
        "publication_enabled": False,
        "max_direct_requests": 1,
        "request_mode": "direct",
        "config": {
            "page_size": 10,
            "max_retries": 1,
            "admin_scope": {"max_pages": 1, "max_requests": 1, "full_source_import": False},
            "company_profile": {
                "website": "https://www.rhein-bmw.de/",
                "careers_page": "https://careers.smartrecruiters.com/RheinGroup",
                "ats_url": "https://careers.smartrecruiters.com/RheinGroup",
            },
        },
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
