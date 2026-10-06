"""Version-bound Nemo enrichment; storage and scheduling stay in the VPS worker."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from backend.application.catalog_job_filters import classification_prompt, validate_classification
from backend.application.personalized_jobs_intelligence import build_preserved_original_posting
from backend.application.vps_job_descriptions import build_pilot_description
from backend.domain.job_filter_source_cache import SOURCE_PATHS, SOURCE_SCHEMA


def enrich_version(row: Mapping[str, Any], generate: Callable) -> dict[str, Any]:
    if row.get("filters_ready") and row.get("description_ready"):
        return {}
    original = build_preserved_original_posting(row)
    source = str(original.get("description_text") or original.get("description") or "").strip()
    if not source:
        raise ValueError("source_missing")
    result: dict[str, Any] = {}
    if not row.get("filters_ready"):
        inputs = [{"id": row["canonical_job_id"], "title": row["title"],
                   "location": row.get("version_location", ""), "description": source}]
        response = generate(classification_prompt(inputs))
        jobs = response.get("jobs") if isinstance(response, Mapping) else None
        if not isinstance(jobs, list) or len(jobs) != 1 or jobs[0].get("id") != row["canonical_job_id"]:
            raise ValueError("filter_response_identity_mismatch")
        filters = validate_classification(jobs[0], str(row["title"]) + " " + source, row["title"])
        if filters is None:
            raise ValueError("filter_validation_failed")
        result["filters"] = filters
    if not row.get("description_ready"):
        if len(source) < 80:
            raise ValueError("source_incomplete")
        description = build_pilot_description(row, generate, require_source_quotes=True)
        if not any(description["summary"].get(section) for section in
                   ("responsibilities", "required_qualifications", "preferred_qualifications", "benefits", "application_details")):
            raise ValueError("description_has_no_supported_facts")
        result["description"] = description
    return result


def attach_source_metadata(filters: dict, payload: dict) -> dict:
    projection = {}
    for path in SOURCE_PATHS:
        value: Any = payload
        for segment in path[2:].split("."):
            value = value.get(segment) if isinstance(value, Mapping) else None
        projection[path] = value
    return {**filters, "source_metadata": projection, "source_metadata_schema": SOURCE_SCHEMA}
