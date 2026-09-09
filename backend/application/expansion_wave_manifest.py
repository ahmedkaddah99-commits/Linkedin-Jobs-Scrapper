"""Build deterministic, execution-free RC-029 expansion wave manifests."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from typing import Any, Mapping

from backend.application.source_eligibility_manifest import (
    SCHEMA_VERSION as SOURCE_MANIFEST_SCHEMA_VERSION,
    SOURCE_EMPLOYER,
    SOURCE_LINKEDIN,
    validate_manifest_for_source,
)


WAVE_MANIFEST_SCHEMA_VERSION = "runr_expansion_wave_manifest_v1"
WAVE_COHORTS = frozenset({"all", "pilot", "expansion"})
SOURCES = (SOURCE_EMPLOYER, SOURCE_LINKEDIN)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _validate_positive_int(value: int, name: str) -> int:
    normalized = int(value)
    if normalized <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return normalized


def _validate_nonnegative_number(value: float, name: str) -> float:
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(f"{name} must not be negative")
    return normalized


def _validate_manifest(manifest: Mapping[str, Any]) -> None:
    if _text(manifest.get("schema_version")) != SOURCE_MANIFEST_SCHEMA_VERSION:
        raise ValueError("RC-029 requires an RC-005 source-eligibility manifest")
    if not _text(manifest.get("manifest_hash")):
        raise ValueError("RC-005 manifest_hash is required")
    integrity = manifest.get("integrity")
    if not isinstance(integrity, Mapping) or not integrity.get("eligible_tasks_have_one_canonical_id"):
        raise ValueError("RC-005 manifest failed canonical-ID integrity checks")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("RC-005 manifest is missing tasks")
    task_keys: set[str] = set()
    for task in tasks:
        if not isinstance(task, Mapping):
            raise ValueError("RC-005 manifest contains a malformed task")
        task_key = _text(task.get("task_key"))
        if _text(task.get("source")) not in SOURCES or not task_key or task_key in task_keys:
            raise ValueError("RC-005 manifest contains an unsupported or duplicate task")
        task_keys.add(task_key)
    # Reuse the collector gate for both source task sets. This rejects duplicate
    # or unmapped tasks instead of allowing a wave planner to broaden eligibility.
    for source in SOURCES:
        validate_manifest_for_source(manifest, source, pilot_only=False)


def _task_copy(task: Mapping[str, Any]) -> dict[str, Any]:
    source = _text(task.get("source"))
    canonical_id = _text(task.get("canonical_company_id"))
    organization_ids = sorted(
        {
            _text(item.get("linkedin_org_id"))
            for item in task.get("organization_associations") or []
            if isinstance(item, Mapping) and _text(item.get("linkedin_org_id"))
        }
    )
    return {
        "task_key": _text(task.get("task_key")),
        "source": source,
        "canonical_company_id": canonical_id,
        "representative_source_row_number": task.get("representative_source_row_number"),
        "representative_row_fingerprint": _text(task.get("representative_row_fingerprint")),
        "pilot_eligible": bool(task.get("pilot_eligible")),
        "organization_ids": organization_ids,
    }


def _cohort_selected(task: Mapping[str, Any], cohort: str) -> bool:
    if cohort == "all":
        return True
    return bool(task.get("pilot_eligible")) if cohort == "pilot" else not bool(task.get("pilot_eligible"))


def _non_task_summary(manifest: Mapping[str, Any]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for row in manifest.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        canonical_id = _text(row.get("canonical_company_id"))
        eligibility = row.get("source_eligibility")
        if not canonical_id:
            counts["missing_canonical_id"] += 1
        elif not isinstance(eligibility, Mapping) or not any(bool(eligibility.get(source)) for source in SOURCES):
            counts["no_eligible_source"] += 1
        ownership = row.get("ownership") if isinstance(row.get("ownership"), Mapping) else {}
        if _text(ownership.get("status")) == "conflicting_unresolved":
            counts["unresolved_ownership"] += 1
        if bool(row.get("review_required")):
            counts["review_required"] += 1
    return dict(sorted(counts.items()))


def build_expansion_wave_manifest(
    source_manifest: Mapping[str, Any],
    *,
    cohort: str = "all",
    wave_size: int,
    request_cap: int,
    credit_cap: float,
    max_failure_rate: float,
    max_queue_age_seconds: int,
) -> dict[str, Any]:
    """Return a stable wave plan without writing data or making network calls.

    One employer group is never split across waves. A group contains every
    selected source task for its canonical company, which preserves the
    source-specific expansion boundary and avoids duplicate scheduling.
    """

    _validate_manifest(source_manifest)
    if cohort not in WAVE_COHORTS:
        raise ValueError(f"unsupported RC-029 cohort: {cohort}")
    normalized_wave_size = _validate_positive_int(wave_size, "wave_size")
    normalized_request_cap = _validate_positive_int(request_cap, "request_cap")
    normalized_credit_cap = _validate_nonnegative_number(credit_cap, "credit_cap")
    if normalized_credit_cap <= 0:
        raise ValueError("credit_cap must be greater than zero")
    normalized_failure_rate = _validate_nonnegative_number(max_failure_rate, "max_failure_rate")
    if normalized_failure_rate > 1:
        raise ValueError("max_failure_rate must be at most 1")
    normalized_queue_age = _validate_positive_int(max_queue_age_seconds, "max_queue_age_seconds")

    all_tasks = [_task_copy(task) for task in source_manifest.get("tasks") or [] if isinstance(task, Mapping)]
    all_tasks.sort(key=lambda task: (task["canonical_company_id"], task["source"], task["task_key"]))
    selected_tasks = [task for task in all_tasks if _cohort_selected(task, cohort)]
    selected_task_keys = {task["task_key"] for task in selected_tasks}
    deferred_task_keys = [task["task_key"] for task in all_tasks if task["task_key"] not in selected_task_keys]

    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in selected_tasks:
        groups[task["canonical_company_id"]].append(task)
    employer_groups = [
        {
            "canonical_company_id": canonical_id,
            "tasks": sorted(tasks, key=lambda task: (task["source"], task["task_key"])),
            "organization_ids": sorted({org_id for task in tasks for org_id in task["organization_ids"]}),
        }
        for canonical_id, tasks in sorted(groups.items())
    ]
    waves: list[dict[str, Any]] = []
    for start in range(0, len(employer_groups), normalized_wave_size):
        wave_groups = employer_groups[start : start + normalized_wave_size]
        wave_number = len(waves) + 1
        wave_tasks = [task for group in wave_groups for task in group["tasks"]]
        waves.append(
            {
                "wave_number": wave_number,
                "canonical_company_ids": [group["canonical_company_id"] for group in wave_groups],
                "unique_employers": len(wave_groups),
                "organization_groups": sorted(
                    {org_id for group in wave_groups for org_id in group["organization_ids"]}
                ),
                "source_tasks": [
                    {
                        "task_key": task["task_key"],
                        "source": task["source"],
                        "canonical_company_id": task["canonical_company_id"],
                        "organization_ids": task["organization_ids"],
                    }
                    for task in wave_tasks
                ],
                "source_task_count": len(wave_tasks),
                "request_cap": normalized_request_cap,
                "credit_cap": normalized_credit_cap,
                "stop_conditions": {
                    "max_failure_rate": normalized_failure_rate,
                    "max_queue_age_seconds": normalized_queue_age,
                    "pause_at_request_cap": True,
                    "pause_at_credit_cap": True,
                    "pause_on_budget_breach": True,
                    "pause_on_unclassified_result": True,
                    "preserve_accepted_results_on_pause": True,
                },
            }
        )

    body = {
        "schema_version": WAVE_MANIFEST_SCHEMA_VERSION,
        "source_manifest": {
            "schema_version": _text(source_manifest.get("schema_version")),
            "manifest_id": _text(source_manifest.get("manifest_id")),
            "manifest_version": _text(source_manifest.get("manifest_version")),
            "manifest_hash": _text(source_manifest.get("manifest_hash")),
        },
        "cohort": cohort,
        "policy": {
            "wave_size_unique_employers": normalized_wave_size,
            "request_cap_per_wave": normalized_request_cap,
            "credit_cap_per_wave": normalized_credit_cap,
            "max_failure_rate": normalized_failure_rate,
            "max_queue_age_seconds": normalized_queue_age,
            "no_mapping_application": True,
            "no_provider_requests": True,
        },
        "coverage": {
            "source_tasks_in_manifest": len(all_tasks),
            "selected_source_tasks": len(selected_tasks),
            "deferred_source_tasks": len(deferred_task_keys),
            "deferred_task_keys": deferred_task_keys,
            "selected_unique_employers": len(employer_groups),
            "selected_organization_groups": len(
                {org_id for group in employer_groups for org_id in group["organization_ids"]}
            ),
            "non_task_row_reasons": _non_task_summary(source_manifest),
            "runtime_outcomes_required": ["partial", "failed", "unsupported", "deferred", "accepted", "published"],
        },
        "waves": waves,
    }
    return {**body, "wave_manifest_hash": _hash_json(body)}


__all__ = ["WAVE_MANIFEST_SCHEMA_VERSION", "WAVE_COHORTS", "build_expansion_wave_manifest"]
