"""Deterministic, non-destructive canonical-ID backfill for RC-004.

The backfill operates on the master ID namespace only.  It never creates or
updates Runr application-company records.  A dry run produces a mapping
manifest; writing a new CSV requires an explicitly approved mapping manifest
and can never target the input file itself.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from backend.domain.company_identity import structural_url


SCHEMA_VERSION = "rc004_company_id_backfill_v1"
MASTER_CANONICAL_ID_FIELD = "canonical_CompanyID"
MISSING_MARKERS = {"", "//", "null", "none", "nan", "n/a", "na"}
NON_COMPANY_LINKEDIN_PAGE_TYPES = {"school", "showcase"}
ANCHOR_IDENTITY_TYPES = ("companyenrich_id", "linkedin_org_id")
ELIGIBLE_DECISIONS = {"retained", "matched_existing", "new", "duplicate"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _value(value: Any) -> str:
    candidate = _text(value)
    return "" if candidate.casefold() in MISSING_MARKERS else candidate


def _normalise_numeric_id(value: Any) -> str:
    candidate = _value(value)
    if not candidate or not candidate.isascii() or not candidate.isdecimal():
        return ""
    return str(int(candidate, 10))


def _url_details(value: Any) -> dict[str, str]:
    original, canonical, reason = structural_url(value)
    host = ""
    path = ""
    if canonical:
        parsed = urlsplit(canonical)
        host = (parsed.hostname or "").casefold().removeprefix("www.")
        path = parsed.path or "/"
    return {"original": original, "canonical": canonical, "host": host, "path": path, "reason": reason}


def _linkedin_page_type(row: Mapping[str, Any], linkedin_url: Mapping[str, str]) -> str:
    explicit = _value(row.get("linkedin_page_type")).casefold()
    if explicit:
        return explicit
    parts = [part for part in linkedin_url.get("path", "").casefold().split("/") if part]
    if parts and parts[0] in NON_COMPANY_LINKEDIN_PAGE_TYPES:
        return parts[0]
    if parts and parts[0] == "company":
        return "company"
    return "unknown"


def _row_fingerprint(row: Mapping[str, Any]) -> str:
    payload = json.dumps(
        {str(key): "" if value is None else str(value) for key, value in row.items()},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _identity_evidence(row: Mapping[str, Any]) -> tuple[list[dict[str, str]], bool, str, str]:
    linkedin_url = _url_details(row.get("linkedin_company_url"))
    page_type = _linkedin_page_type(row, linkedin_url)
    raw_linkedin_id = _value(row.get("linkedin_company_id"))
    linkedin_id = _normalise_numeric_id(raw_linkedin_id)
    invalid_linkedin_id = bool(raw_linkedin_id and not linkedin_id)
    keys: list[dict[str, str]] = []
    if linkedin_id:
        keys.append({"identity_key": f"linkedin-org:{linkedin_id}", "identity_type": "linkedin_org_id"})
    companyenrich_id = _value(row.get("companyenrich_id"))
    if companyenrich_id:
        keys.append({"identity_key": f"companyenrich:{companyenrich_id}", "identity_type": "companyenrich_id"})
    return keys, invalid_linkedin_id, page_type, linkedin_url["canonical"]


def _deterministic_id(identity_key: str) -> str:
    digest = hashlib.sha256(f"rc004:{identity_key}".encode("utf-8")).hexdigest()[:16]
    return f"canonical-{digest}"


def _approved_lookup(approved_mappings: Mapping[str, Any] | None) -> tuple[dict[str, str], dict[str, str]]:
    payload = approved_mappings or {}
    if "mapping_manifest" in payload and isinstance(payload["mapping_manifest"], Mapping):
        payload = payload["mapping_manifest"]
    approved = payload.get("approved") is True or _text(payload.get("approval_status")).casefold() == "approved"
    if not approved:
        return {}, {}
    key_map = {
        _text(key): _text(value)
        for key, value in (payload.get("identity_key_to_canonical_id") or {}).items()
        if _text(key) and _text(value)
    }
    row_map = {
        _text(key): _text(value)
        for key, value in (payload.get("row_fingerprint_to_canonical_id") or {}).items()
        if _text(key) and _text(value)
    }
    return key_map, row_map


def _prepared_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for source_row_number, row in enumerate(rows, start=2):
        raw = dict(row)
        keys, invalid_linkedin_id, page_type, linkedin_url = _identity_evidence(raw)
        master_id = _value(raw.get(MASTER_CANONICAL_ID_FIELD))
        prepared.append(
            {
                "source_row_number": source_row_number,
                "row_fingerprint": _row_fingerprint(raw),
                "raw": raw,
                "master_id": master_id,
                "identity_keys": keys,
                "identity_key_values": [item["identity_key"] for item in keys],
                "invalid_linkedin_id": invalid_linkedin_id,
                "page_type": page_type,
                "linkedin_url": linkedin_url,
                "company_name": _text(raw.get("company_name")),
            }
        )
    return prepared


def _candidate_ids_by_identity(prepared: Iterable[Mapping[str, Any]]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    existing_by_key: dict[str, set[str]] = defaultdict(set)
    key_rows: dict[str, set[str]] = defaultdict(set)
    for item in prepared:
        fingerprint = str(item["row_fingerprint"])
        for identity_key in item["identity_key_values"]:
            key_rows[identity_key].add(fingerprint)
            if item["master_id"]:
                existing_by_key[identity_key].add(str(item["master_id"]))
    return dict(existing_by_key), dict(key_rows)


def backfill_master_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    source_path: str = "",
    input_sha256: str = "",
    approved_mappings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a dry-run mapping without changing ``rows`` or any file."""

    prepared = _prepared_rows(rows)
    approved_key_map, approved_row_map = _approved_lookup(approved_mappings)
    existing_by_key, key_rows = _candidate_ids_by_identity(prepared)
    identity_key_occurrences = Counter(
        identity_key
        for item in prepared
        for identity_key in item["identity_key_values"]
    )
    for identity_key, canonical_id in approved_key_map.items():
        existing_by_key.setdefault(identity_key, set()).add(canonical_id)

    canonical_id_owners: dict[str, set[str]] = defaultdict(set)
    existing_canonical_ids = {str(item["master_id"]) for item in prepared if item["master_id"]}
    for identity_key, canonical_ids in existing_by_key.items():
        for canonical_id in canonical_ids:
            canonical_id_owners[canonical_id].add(identity_key)
    generated_id_owners: dict[str, str] = {}
    seen_fingerprints: dict[str, int] = {}
    mappings: list[dict[str, Any]] = []
    identity_key_to_canonical_id: dict[str, str] = {}
    duplicate_identity_evidence: list[dict[str, Any]] = []

    for identity_key, row_fingerprints in sorted(key_rows.items()):
        if identity_key_occurrences[identity_key] > 1:
            duplicate_identity_evidence.append(
                {
                    "identity_key": identity_key,
                    "row_fingerprints": sorted(row_fingerprints),
                    "existing_canonical_ids": sorted(existing_by_key.get(identity_key, set())),
                    "review_required": len(existing_by_key.get(identity_key, set())) > 1,
                }
            )

    for item in prepared:
        fingerprint = str(item["row_fingerprint"])
        duplicate_of = seen_fingerprints.get(fingerprint, 0)
        seen_fingerprints.setdefault(fingerprint, int(item["source_row_number"]))
        identity_keys = list(item["identity_key_values"])
        identity_evidence = list(item["identity_keys"])
        candidate_ids = set()
        for identity_key in identity_keys:
            candidate_ids.update(existing_by_key.get(identity_key, set()))
        approved_row_id = approved_row_map.get(fingerprint, "")
        if approved_row_id:
            candidate_ids.add(approved_row_id)
        approved_key_ids = {approved_key_map[key] for key in identity_keys if key in approved_key_map}
        candidate_ids.update(approved_key_ids)
        conflicting_identity_key = next(
            (
                key
                for key in identity_keys
                if len(existing_by_key.get(key, set())) > 1
            ),
            "",
        )
        reason = ""
        base_decision = ""
        proposed_id = item["master_id"]
        anchor_key = ""

        if item["master_id"]:
            base_decision = "retained"
            reason = "existing_master_id_preserved"
            if conflicting_identity_key or (candidate_ids and candidate_ids != {item["master_id"]}):
                base_decision = "quarantined"
                reason = "existing_id_conflicts_with_identity_evidence"
        elif item["page_type"] in NON_COMPANY_LINKEDIN_PAGE_TYPES:
            base_decision = "rejected"
            reason = "non_company_linkedin_page"
            proposed_id = ""
        elif conflicting_identity_key or len(candidate_ids) > 1:
            base_decision = "quarantined"
            reason = "identity_key_maps_to_multiple_canonical_ids"
            proposed_id = ""
        elif len(candidate_ids) == 1:
            base_decision = "matched_existing"
            proposed_id = next(iter(candidate_ids))
            reason = "unique_existing_identity_match"
        elif item["invalid_linkedin_id"]:
            base_decision = "rejected"
            reason = "malformed_linkedin_company_id"
            proposed_id = ""
        elif identity_keys:
            anchor_identity = next(
                (
                    key
                    for identity_type in ANCHOR_IDENTITY_TYPES
                    for key in identity_evidence
                    if key["identity_type"] == identity_type
                ),
                None,
            )
            anchor_key = str(anchor_identity["identity_key"]) if anchor_identity else ""
            if not anchor_key:
                anchor_key = sorted(identity_evidence, key=lambda key: key["identity_key"])[0]["identity_key"]
            proposed_id = _deterministic_id(anchor_key)
            owner_keys = canonical_id_owners.get(proposed_id, set())
            generated_owner = generated_id_owners.get(proposed_id, "")
            if (
                (proposed_id in existing_canonical_ids and anchor_key not in owner_keys)
                or (generated_owner and generated_owner != anchor_key)
            ):
                base_decision = "quarantined"
                reason = "deterministic_id_collision"
                proposed_id = ""
            else:
                base_decision = "new"
                reason = "deterministic_strong_identity_allocation_pending_approval"
                generated_id_owners[proposed_id] = anchor_key
                identity_key_to_canonical_id[anchor_key] = proposed_id
        elif not item["company_name"]:
            base_decision = "rejected"
            reason = "company_name_missing"
            proposed_id = ""
        else:
            base_decision = "provisional"
            reason = "no_strong_identity_evidence"
            proposed_id = ""

        decision = "duplicate" if duplicate_of and base_decision in ELIGIBLE_DECISIONS else base_decision
        eligible = bool(proposed_id and base_decision in {"retained", "matched_existing", "new"})
        mapping = {
            "source_row_number": item["source_row_number"],
            "row_fingerprint": fingerprint,
            "duplicate_of_source_row_number": duplicate_of,
            "original_canonical_id": item["master_id"],
            "proposed_canonical_id": proposed_id,
            "registry_record_key": f"master-registry:{proposed_id or fingerprint}",
            "quarantine_record_key": f"quarantine:{fingerprint}" if base_decision in {"quarantined", "rejected"} else "",
            "identity_keys": identity_keys,
            "anchor_identity_key": anchor_key,
            "decision": decision,
            "base_decision": base_decision,
            "reason": reason,
            "eligible_for_identity_backfill": eligible,
            "review_required": base_decision in {"new", "provisional", "quarantined", "rejected"},
        }
        mappings.append(mapping)

    for mapping in mappings:
        if mapping["proposed_canonical_id"]:
            for identity_key in mapping["identity_keys"]:
                if mapping["base_decision"] in {"retained", "matched_existing"}:
                    identity_key_to_canonical_id.setdefault(identity_key, mapping["proposed_canonical_id"])

    counts = Counter(mapping["base_decision"] for mapping in mappings)
    counts["duplicate_rows"] = sum(bool(mapping["duplicate_of_source_row_number"]) for mapping in mappings)
    counts["missing_master_id_rows"] = sum(not mapping["original_canonical_id"] for mapping in mappings)
    counts["existing_master_id_rows"] = sum(bool(mapping["original_canonical_id"]) for mapping in mappings)
    counts["existing_id_values_preserved"] = counts["existing_master_id_rows"]
    counts["eligible_rows"] = sum(bool(mapping["eligible_for_identity_backfill"]) for mapping in mappings)
    counts["quarantine_records"] = sum(bool(mapping["quarantine_record_key"]) for mapping in mappings)
    counts["identity_keys_with_duplicate_evidence"] = len(duplicate_identity_evidence)
    counts["identity_keys_with_conflicting_existing_ids"] = sum(
        len(canonical_ids) > 1 for canonical_ids in existing_by_key.values()
    )
    counts["new_identity_keys"] = len(identity_key_to_canonical_id) - sum(
        identity_key in existing_by_key for identity_key in identity_key_to_canonical_id
    )
    missing_id_counts = Counter(
        mapping["base_decision"] for mapping in mappings if not mapping["original_canonical_id"]
    )
    existing_id_counts = Counter(
        mapping["base_decision"] for mapping in mappings if mapping["original_canonical_id"]
    )
    for decision in ("retained", "matched_existing", "new", "provisional", "quarantined", "rejected"):
        counts[f"missing_id_{decision}"] = missing_id_counts[decision]
        counts[f"existing_id_{decision}"] = existing_id_counts[decision]
    counts["missing_id_eligible_rows"] = sum(
        bool(mapping["eligible_for_identity_backfill"])
        for mapping in mappings
        if not mapping["original_canonical_id"]
    )
    mapping_manifest = {
        "schema_version": f"{SCHEMA_VERSION}_mapping_manifest",
        "source_path": str(source_path or ""),
        "input_sha256": str(input_sha256 or ""),
        "approval_status": "dry_run",
        "identity_key_to_canonical_id": dict(sorted(identity_key_to_canonical_id.items())),
        "row_fingerprint_to_canonical_id": {
            mapping["row_fingerprint"]: mapping["proposed_canonical_id"]
            for mapping in mappings
            if mapping["proposed_canonical_id"] and mapping["base_decision"] == "new"
        },
        "mappings": mappings,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "read_only": True,
        "source_untouched": True,
        "application_tables_written": False,
        "original_master_ids_preserved": True,
        "automatic_merge": False,
        "automatic_publication": False,
        "approved_mapping_supplied": bool(approved_key_map or approved_row_map),
        "approved_identity_keys": sorted(approved_key_map),
        "approved_row_fingerprints": sorted(approved_row_map),
        "counts": dict(counts),
        "duplicate_identity_evidence": duplicate_identity_evidence,
        "identity_key_conflicts": {
            key: sorted(value) for key, value in existing_by_key.items() if len(value) > 1
        },
        "mapping_manifest": mapping_manifest,
        "mappings": mappings,
    }


def write_backfill_outputs(
    source_rows: Iterable[Mapping[str, Any]],
    fieldnames: Iterable[str],
    *,
    source_path: str | Path,
    output_path: str | Path,
    manifest_path: str | Path,
    report: Mapping[str, Any],
) -> dict[str, str]:
    """Write an approved output copy, persisting its mapping manifest first."""

    source = Path(source_path).resolve()
    output = Path(output_path).resolve()
    manifest = Path(manifest_path).resolve()
    if source in {output, manifest}:
        raise ValueError("Refusing to overwrite the original master input")
    if output == manifest:
        raise ValueError("Output CSV and mapping manifest must be different files")
    if not report.get("approved_mapping_supplied"):
        raise ValueError("An approved mapping manifest is required for --apply-output")
    mapping_manifest = report.get("mapping_manifest")
    expected_sha256 = str(mapping_manifest.get("input_sha256") or "") if isinstance(mapping_manifest, Mapping) else ""
    if expected_sha256 and hashlib.sha256(source.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("The input changed after the mapping manifest was created")
    mappings = list(report.get("mappings", ()))
    source_rows_list = [dict(row) for row in source_rows]
    mapping_by_row = {int(item["source_row_number"]): item for item in mappings}
    expected_rows = set(range(2, 2 + len(source_rows_list)))
    if set(mapping_by_row) != expected_rows:
        raise ValueError("Mapping manifest does not cover every source row")
    approved_new_keys = set(report.get("approved_identity_keys", ()))
    approved_new_fingerprints = set(report.get("approved_row_fingerprints", ()))
    for item in mappings:
        if (
            item.get("base_decision") == "new"
            and str(item.get("anchor_identity_key") or "") not in approved_new_keys
            and str(item.get("row_fingerprint") or "") not in approved_new_fingerprints
        ):
            raise ValueError("New mapping is missing explicit approval")
    columns = list(fieldnames)
    if MASTER_CANONICAL_ID_FIELD not in columns:
        raise ValueError(f"Input is missing {MASTER_CANONICAL_ID_FIELD}")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    backup = ""
    if output.exists():
        backup_path = output.with_name(f"{output.name}.before-rc004.bak")
        if backup_path.exists():
            raise FileExistsError(f"Refusing to overwrite existing backup: {backup_path}")
        output.replace(backup_path)
        backup = str(backup_path)
    manifest_payload = dict(report["mapping_manifest"])
    manifest_payload.update(
        {
            "approval_status": "approved_applied",
            "output_path": str(output),
            "backup_path": backup,
            "write_id": f"rc004-write-{uuid4().hex}",
        }
    )
    manifest.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for source_row_number, raw in enumerate(source_rows_list, start=2):
            row = dict(raw)
            mapping = mapping_by_row[source_row_number]
            if mapping.get("proposed_canonical_id"):
                row[MASTER_CANONICAL_ID_FIELD] = mapping["proposed_canonical_id"]
            writer.writerow({column: "" if row.get(column) is None else row.get(column, "") for column in columns})
    return {"output_path": str(output), "manifest_path": str(manifest), "backup_path": backup}


def read_csv_with_hash(path: str | Path) -> tuple[list[dict[str, str]], list[str], str]:
    source = Path(path)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Master input has no CSV header")
        rows = []
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"Master input row {line_number} has more values than its header")
            rows.append({str(key): "" if value is None else str(value) for key, value in row.items()})
    return rows, list(reader.fieldnames), digest


__all__ = [
    "ELIGIBLE_DECISIONS",
    "MASTER_CANONICAL_ID_FIELD",
    "SCHEMA_VERSION",
    "backfill_master_rows",
    "read_csv_with_hash",
    "write_backfill_outputs",
]
