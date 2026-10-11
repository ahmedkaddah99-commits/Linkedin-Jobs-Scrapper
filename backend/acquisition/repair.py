"""Dry-run and safe annotation backfill for the shared acquisition catalog.

The repair pass never deletes rows, merges ambiguous companies, or rewrites the
immutable posting-version payload. It repairs unambiguous company ownership,
adds idempotent quality annotations, and leaves a report for manual review.
"""

from __future__ import annotations

import json
import hashlib
from collections.abc import Mapping
from typing import Any as AnyType

from backend.acquisition.quality import (
    canonical_employer_name,
    company_name_key,
    completeness_rules,
    normalize_job_for_ingestion,
    stable_content_payload,
)
from backend.application.personalized_jobs_intelligence import _deterministic_description
from backend.domain.models import utc_now_iso


def _json(value: AnyType) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode(value: AnyType, default: AnyType) -> AnyType:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _row(row: AnyType) -> dict[str, AnyType]:
    return {key: row[key] for key in row.keys()}


def _target_payload(row: Mapping[str, AnyType]) -> dict[str, AnyType]:
    target = dict(row)
    target["config"] = _decode(target.pop("config_json", "{}"), {})
    return target


def _quality_report(
    normalized: Mapping[str, AnyType],
    *,
    redundant: bool,
    reason: str,
    version: Mapping[str, AnyType] | None = None,
    observation: Mapping[str, AnyType] | None = None,
) -> dict[str, AnyType]:
    version = version or {}
    observation = observation or {}
    intelligence = _deterministic_description({
        "description": normalized.get("description_text") or normalized.get("description_raw") or "",
        "version_payload_json": dict(normalized),
        "current_version_id": version.get("version_id"),
        "version_number": version.get("version_number"),
        "content_hash": version.get("content_hash"),
        "source_observation_id": observation.get("observation_id"),
        "observation_original_url": observation.get("original_url"),
        "observation_observed_at": observation.get("observed_at"),
    })
    return {
        "schema_version": "acquisition_repair_v1",
        "application_destination": normalized.get("application_destination") or {},
        "description": {
            "has_raw_source": bool(normalized.get("description_raw")),
            "has_sanitized_html": bool(normalized.get("description_html")),
            "has_plain_text": bool(normalized.get("description_text")),
            "decoding": normalized.get("description_decoding") or "",
        },
        "normalized_source_metadata": normalized.get("normalized_source_metadata") or {},
        "source_timestamps": normalized.get("source_timestamps") or {},
        "intelligence": intelligence,
        "provenance_audit": {
            "source_observation_id": observation.get("observation_id") or None,
            "source_url": observation.get("original_url") or None,
            "observed_at": observation.get("observed_at") or None,
            "source_connector": observation.get("source_connector") or observation.get("source_ats") or None,
            "unknown_fields_have_null_provenance": True,
        },
        "quality_warnings": list(normalized.get("quality_warnings") or []),
        "completeness": normalized.get("quality_completeness") or {},
        "redundant": redundant,
        "redundant_reason": reason,
        "repair_mode": "annotation_only",
    }


def repair_acquisition_catalog(store: AnyType, *, apply: bool = False) -> dict[str, AnyType]:
    """Inspect the catalog and optionally apply only safe, idempotent repairs."""

    now = utc_now_iso()
    report: dict[str, AnyType] = {
        "schema_version": "acquisition_repair_v1",
        "mode": "apply" if apply else "dry_run",
        "idempotent": True,
        "blocking": False,
        "records_inspected": {"companies": 0, "jobs": 0, "observations": 0, "versions": 0},
        "company_mappings_proposed": [],
        "source_entities_marked": [],
        "application_urls_resolved": [],
        "source_metadata_normalized": [],
        "timestamps_normalized": [],
        "intelligence_processed": [],
        "provenance_checked": [],
        "descriptions_changed": [],
        "redundant_versions": [],
        "conflicts": [],
        "manual_review": [],
        "applied": {"company_mappings": 0, "quality_annotations": 0, "redundant_annotations": 0},
    }

    with store._connect() as connection:
        target_rows = connection.execute("SELECT * FROM acquisition_targets").fetchall()
        targets = {str(row["target_id"]): _target_payload(_row(row)) for row in target_rows}
        company_rows = connection.execute("SELECT * FROM canonical_companies").fetchall()
        companies = [_row(row) for row in company_rows]
        report["records_inspected"]["companies"] = len(companies)
        company_by_id = {str(item.get("company_id") or ""): item for item in companies}
        company_by_key: dict[str, list[dict[str, AnyType]]] = {}
        for company in companies:
            company_by_key.setdefault(company_name_key(company.get("canonical_name")), []).append(company)

        job_rows = connection.execute(
            "SELECT canonical_job_id, company_id, current_version_id FROM canonical_jobs ORDER BY canonical_job_id"
        ).fetchall()
        report["records_inspected"]["jobs"] = len(job_rows)
        job_by_id = {str(row["canonical_job_id"]): _row(row) for row in job_rows}
        alias_rows = connection.execute("SELECT company_id, alias_key FROM canonical_company_aliases").fetchall()
        alias_owner = {str(row["alias_key"]): str(row["company_id"]) for row in alias_rows}
        referenced_company_ids = {str(row["company_id"] or "") for row in job_rows}
        for company in companies:
            company_id = str(company.get("company_id") or "")
            if company_id in referenced_company_ids or str(company.get("entity_kind") or "") == "source":
                continue
            owner = alias_owner.get(company_name_key(company.get("canonical_name")))
            if owner and owner != company_id:
                report["source_entities_marked"].append(company_id)
                if apply:
                    connection.execute(
                        "UPDATE canonical_companies SET entity_kind='source', updated_at=? WHERE company_id=?",
                        (now, company_id),
                    )
        observation_rows = connection.execute("SELECT * FROM job_source_observations ORDER BY observed_at, observation_id").fetchall()
        observations = [_row(row) for row in observation_rows]
        report["records_inspected"]["observations"] = len(observations)
        observation_by_id = {str(item.get("observation_id") or ""): item for item in observations}
        observations_by_job: dict[str, list[dict[str, AnyType]]] = {}
        for item in observations:
            observations_by_job.setdefault(str(item.get("canonical_job_id") or ""), []).append(item)
        version_rows = connection.execute(
            "SELECT * FROM job_posting_versions ORDER BY canonical_job_id, version_number, version_id"
        ).fetchall()
        versions = [_row(row) for row in version_rows]
        report["records_inspected"]["versions"] = len(versions)
        quality_rows = connection.execute("SELECT * FROM acquisition_version_quality").fetchall()
        quality_by_version = {str(row["version_id"]): _row(row) for row in quality_rows}

        # First pass: map a source-labeled or otherwise misplaced job only
        # when exactly one canonical company matches the target's configured
        # employer name. Ambiguity is retained for review.
        for job_row in job_rows:
            job = _row(job_row)
            job_id = str(job.get("canonical_job_id") or "")
            current_company_id = str(job.get("company_id") or "")
            related = observations_by_job.get(job_id, [])
            target = targets.get(str(related[0].get("target_id") or "")) if related else None
            if not target:
                continue
            canonical_name = canonical_employer_name(target)
            candidates = company_by_key.get(company_name_key(canonical_name), [])
            current_company = company_by_id.get(current_company_id)
            if len(candidates) > 1:
                report["conflicts"].append({"canonical_job_id": job_id, "reason": "ambiguous_canonical_company", "candidate_company_ids": [str(item.get("company_id")) for item in candidates]})
                continue
            if len(candidates) == 1 and str(candidates[0].get("company_id") or "") != current_company_id:
                proposal = {
                    "canonical_job_id": job_id,
                    "from_company_id": current_company_id,
                    "from_company_name": str((current_company or {}).get("canonical_name") or ""),
                    "to_company_id": str(candidates[0].get("company_id") or ""),
                    "to_company_name": str(candidates[0].get("canonical_name") or canonical_name),
                    "reason": "unambiguous_target_canonical_name",
                }
                report["company_mappings_proposed"].append(proposal)
                if apply:
                    connection.execute(
                        "UPDATE canonical_jobs SET company_id=?, updated_at=? WHERE canonical_job_id=?",
                        (proposal["to_company_id"], now, job_id),
                    )
                    if current_company and current_company.get("canonical_name"):
                        store._ensure_company_alias(
                            connection,
                            proposal["to_company_id"],
                            str(current_company["canonical_name"]),
                            source="repair",
                            now=now,
                        )
                    job["company_id"] = proposal["to_company_id"]
                    job_by_id[job_id] = job
                    report["applied"]["company_mappings"] += 1
            elif not candidates:
                report["manual_review"].append({"canonical_job_id": job_id, "reason": "canonical_company_not_found", "target_id": str(related[0].get("target_id") or "")})

        if apply:
            for source_company_id in sorted({
                str(item.get("from_company_id") or "")
                for item in report["company_mappings_proposed"]
                if item.get("from_company_id")
            }):
                remaining = connection.execute(
                    "SELECT COUNT(*) AS count FROM canonical_jobs WHERE company_id=?",
                    (source_company_id,),
                ).fetchone()
                if int(remaining["count"] or 0) == 0:
                    connection.execute(
                        "UPDATE canonical_companies SET entity_kind='source', updated_at=? WHERE company_id=?",
                        (now, source_company_id),
                    )
                    report["source_entities_marked"].append(source_company_id)

        # Second pass: normalize every immutable version into an annotation.
        # The original payload remains available for audit and replay.
        seen_hashes: dict[str, set[str]] = {}
        for version in versions:
            version_id = str(version.get("version_id") or "")
            observation = observation_by_id.get(str(version.get("source_observation_id") or ""), {})
            target = targets.get(str(observation.get("target_id") or ""))
            if not target:
                report["manual_review"].append({"version_id": version_id, "reason": "target_not_found"})
                continue
            payload = _decode(version.get("payload_json"), {})
            if not isinstance(payload, Mapping):
                payload = {}
            normalized = normalize_job_for_ingestion(payload, target)
            stable_hash = hashlib.sha256(_json(stable_content_payload(normalized)).encode("utf-8")).hexdigest()
            seen_for_job = seen_hashes.setdefault(str(version.get("canonical_job_id") or ""), set())
            redundant = stable_hash in seen_for_job
            seen_for_job.add(stable_hash)
            if redundant:
                report["redundant_versions"].append({"version_id": version_id, "canonical_job_id": str(version.get("canonical_job_id") or ""), "stable_content_hash": stable_hash})
            application = normalized.get("application_destination") or {}
            if application.get("status") == "verified":
                report["application_urls_resolved"].append({"version_id": version_id, "url": application.get("resolved_url"), "classification": application.get("classification")})
            old_payload = payload
            if (old_payload.get("description_html") or "") != (normalized.get("description_html") or "") or not old_payload.get("description_text"):
                report["descriptions_changed"].append({"version_id": version_id, "reason": "normalized_description_representation"})
            report["source_metadata_normalized"].append({
                "version_id": version_id,
                "fields": sorted((normalized.get("normalized_source_metadata") or {}).get("fields", {}).keys()),
            })
            report["timestamps_normalized"].append({
                "version_id": version_id,
                "timestamp_state": (normalized.get("source_timestamps") or {}).get("timestamp_state") or "unknown",
                "timestamp_semantics": (normalized.get("source_timestamps") or {}).get("timestamp_semantics") or "unknown_source_timestamp",
            })
            report["intelligence_processed"].append({"version_id": version_id, "method": "deterministic_grounded"})
            report["provenance_checked"].append({
                "version_id": version_id,
                "observation_id": observation.get("observation_id") or None,
                "source_url": observation.get("original_url") or None,
            })
            current_job = job_by_id.get(str(version.get("canonical_job_id") or ""), {})
            normalized["canonical_job_id"] = str(version.get("canonical_job_id") or "")
            normalized["quality_completeness"] = completeness_rules(
                job=normalized,
                company={"company_id": current_job.get("company_id"), "name": canonical_employer_name(target)},
                source={"target_id": observation.get("target_id"), "source_observation_ids": [observation.get("observation_id")], "external_job_id": observation.get("external_job_id")},
                admin={"state": "staged"},
            )
            quality = _quality_report(
                normalized,
                redundant=redundant,
                reason="same_stable_content_hash" if redundant else "",
                version=version,
                observation=observation,
            )
            if apply:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO acquisition_version_quality (
                        version_id, canonical_job_id, stable_content_hash, redundant, report_json, calculated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (version_id, str(version.get("canonical_job_id") or ""), stable_hash, int(redundant), _json(quality), now),
                )
                report["applied"]["quality_annotations"] += 1
                report["applied"]["redundant_annotations"] += int(redundant)
                source_company_id = str((job_by_id.get(str(version.get("canonical_job_id") or "")) or {}).get("company_id") or "")
                for warning in normalized.get("quality_warnings") or []:
                    event_id = "repair_quality_" + version_id + "_" + "_".join(str(warning).split())
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO acquisition_quality_events (
                            event_id, cycle_id, task_id, target_id, canonical_job_id, company_id,
                            employer_name, connector, source_token, warning_code, severity, details_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'warning', ?, ?)
                        """,
                        (
                            event_id[:240],
                            str(observation.get("cycle_id") or ""),
                            str(observation.get("task_id") or ""),
                            str(observation.get("target_id") or ""),
                            str(version.get("canonical_job_id") or ""),
                            source_company_id,
                            canonical_employer_name(target),
                            str(target.get("connector") or ""),
                            str(target.get("source_token") or ""),
                            str(warning),
                            _json({"version_id": version_id, "repair": True}),
                            now,
                        ),
                    )

    # Arrays are useful for an admin dry-run, while counts make this safe to
    # consume as telemetry without re-counting the report.
    report["counts"] = {
        "company_mappings": len(report["company_mappings_proposed"]),
        "application_urls_resolved": len(report["application_urls_resolved"]),
        "source_metadata_normalized": len(report["source_metadata_normalized"]),
        "timestamps_normalized": len(report["timestamps_normalized"]),
        "intelligence_processed": len(report["intelligence_processed"]),
        "provenance_checked": len(report["provenance_checked"]),
        "descriptions_changed": len(report["descriptions_changed"]),
        "redundant_versions": len(report["redundant_versions"]),
        "conflicts": len(report["conflicts"]),
        "manual_review": len(report["manual_review"]),
        "source_entities_marked": len(report["source_entities_marked"]),
    }
    return report


__all__ = ["repair_acquisition_catalog"]
