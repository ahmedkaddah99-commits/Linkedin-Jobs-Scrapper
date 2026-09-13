from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from hashlib import sha1
from typing import Any, Mapping


SOURCE_TYPE_LINKEDIN_SEARCH = "linkedin_search"
SOURCE_TYPE_MANUAL_URL = "manual_url"

FILTER_STATUS_PENDING = "pending_filter"
FILTER_STATUS_PASSED_LINKEDIN_PIPELINE = "passed_linkedin_pipeline"
FILTER_STATUS_BYPASSED_MANUAL_APPROVAL = "bypassed_manual_approval"


def stable_manual_job_id(url: str, prefix: str = "manual") -> str:
    digest = sha1((url or "").strip().encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


@dataclass(slots=True)
class PipelineJob:
    job_id: str
    title: str
    company: str
    source_type: str
    filter_status: str
    location_raw: str = ""
    keyword: str = ""
    link: str = ""
    linkedin_link: str = ""
    source_url: str = ""
    apply_link: str = ""
    apply_link_source: str = ""
    full_description: str = ""
    easy_apply_status: Any = "unknown"
    posted_time_text: str = ""
    posted_age_hours: float | None = None
    posted_datetime_estimated_utc: str | None = None
    applicant_count: int | None = None
    priority_rank: int | None = None
    priority_tier: int | None = None
    priority_bucket: str = ""
    priority_rule: str = ""
    enrich_error: str | None = None
    enrich_status_code: int | None = None
    manual_approved: bool = False
    ingest_error: str | None = None
    extra_fields: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, Any],
        *,
        source_type: str | None = None,
        filter_status: str | None = None,
    ) -> "PipelineJob":
        payload = dict(record)
        known_field_names = {field_info.name for field_info in fields(cls) if field_info.name != "extra_fields"}
        extra_fields = {key: value for key, value in payload.items() if key not in known_field_names}

        payload["source_type"] = source_type or str(payload.get("source_type") or SOURCE_TYPE_LINKEDIN_SEARCH)
        payload["filter_status"] = filter_status or str(payload.get("filter_status") or FILTER_STATUS_PENDING)
        payload["job_id"] = str(payload.get("job_id") or "")
        payload["title"] = str(payload.get("title") or "")
        payload["company"] = str(payload.get("company") or "")
        payload["extra_fields"] = extra_fields

        supported_payload = {key: payload.get(key) for key in known_field_names}
        supported_payload["extra_fields"] = extra_fields
        return cls(**supported_payload)

    def to_record(self) -> dict[str, Any]:
        payload = asdict(self)
        extra_fields = payload.pop("extra_fields", {}) or {}
        payload.update(extra_fields)
        return payload


def normalize_job_record(
    record: Mapping[str, Any],
    *,
    source_type: str,
    filter_status: str,
    manual_approved: bool = False,
) -> dict[str, Any]:
    job = PipelineJob.from_record(record, source_type=source_type, filter_status=filter_status)
    job.manual_approved = manual_approved
    return job.to_record()


__all__ = [
    "FILTER_STATUS_BYPASSED_MANUAL_APPROVAL",
    "FILTER_STATUS_PASSED_LINKEDIN_PIPELINE",
    "FILTER_STATUS_PENDING",
    "SOURCE_TYPE_LINKEDIN_SEARCH",
    "SOURCE_TYPE_MANUAL_URL",
    "PipelineJob",
    "normalize_job_record",
    "stable_manual_job_id",
]
