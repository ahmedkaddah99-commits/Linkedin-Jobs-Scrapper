from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from backend.application.source_eligibility_manifest import (
    SOURCE_EMPLOYER,
    SOURCE_LINKEDIN,
    build_source_eligibility_manifest,
    load_manifest,
    materialize_source_input,
    read_master_snapshot,
    validate_manifest_for_source,
    write_manifest_bundle,
)
from scripts.run_manifested_employer import main as employer_main
from scripts.run_manifested_linkedin import main as linkedin_main


FIXTURE = Path(__file__).parent / "fixtures" / "rc005_source_eligibility.csv"
AS_OF = "2026-09-06T00:00:00Z"


def _report(*, backfill_report=None, registry_report=None):
    rows, columns, digest = read_master_snapshot(FIXTURE)
    return build_source_eligibility_manifest(
        rows,
        columns,
        source_path=str(FIXTURE.resolve()),
        input_sha256=digest,
        cycle_id="fixture-cycle",
        as_of=AS_OF,
        max_evidence_age_days=30,
        registry_report=registry_report,
        backfill_report=backfill_report,
        raw_sidecar_path="fixture.raw.jsonl",
    )


def _registry_review():
    return {
        "shared_organization_dispositions": [
            {
                "linkedin_org_id": "700",
                "master_canonical_ids": ["master-conflict-a", "master-conflict-b"],
                "disposition": "unresolved_conflict",
                "review_required": True,
            }
        ]
    }


def test_rows_keep_presence_separate_from_evidence_and_tasks_are_deduplicated():
    report = _report(registry_report=_registry_review())
    counts = report["counts"]

    assert counts["input_rows"] == 13
    assert counts["mapped_rows"] == 12
    assert counts["mapped_entities"] == 10
    assert counts["duplicate_rows"] == 1
    assert counts["duplicate_associations"] == 3
    assert counts["tasks"] == 8
    assert counts["employer_tasks"] == 5
    assert counts["linkedin_tasks"] == 3
    assert counts["dual_ready_entities"] == 1
    assert counts["single_ready_entities"] == 6
    assert counts["website_only_entities"] == 4
    assert counts["linkedin_only_entities"] == 2
    assert counts["blocked_entities"] == 4
    assert counts["field_presence_dual_ready_rows"] == 10
    assert counts["evidence_verified_dual_ready_rows"] == 5
    assert counts["decision_dual_ready_rows"] == 2
    assert counts["decision_website_only_rows"] == 5
    assert counts["decision_linkedin_only_rows"] == 2
    assert counts["decision_blocked_rows"] == 4
    assert report["integrity"]["all_input_rows_mapped_or_blocked"]
    assert report["integrity"]["eligible_tasks_have_one_canonical_id"]

    by_name = {row["company_name"]: row for row in report["rows"]}
    alpha_dual = next(row for row in report["rows"] if row["company_name"] == "Alpha GmbH" and row["linkedin"]["numeric_id"] == "101")
    assert alpha_dual["source_eligibility"][SOURCE_EMPLOYER]
    assert alpha_dual["source_eligibility"][SOURCE_LINKEDIN]
    assert by_name["Gamma GmbH"]["decision"] == "website_only"
    assert "numeric_id_evidence_status_not_verified:unresolved" in by_name["Gamma GmbH"]["exclusion_reasons"]
    assert by_name["Delta GmbH"]["canonical_id_state"] == "missing"
    assert "canonical_id_missing_or_placeholder" in by_name["Delta GmbH"]["exclusion_reasons"]
    assert by_name["Mismatch GmbH"]["linkedin"]["evidence"]["url_id_pair_status"] == "mismatch"
    assert by_name["School Page"]["linkedin"]["page_type"] == "school"
    assert by_name["Stale GmbH"]["linkedin"]["freshness"] == "stale"
    assert report["ownership_review"]["conflicting_organization_groups"] == 1
    assert report["ownership_review"]["organization_groups"][0]["status"] == "unresolved_or_not_shared"


def test_pending_backfill_is_not_implicitly_approved_but_approved_mapping_unlocks_row():
    rows, _, _ = read_master_snapshot(FIXTURE)
    delta_fingerprint = next(
        item
        for item in _report()["rows"]
        if item["company_name"] == "Delta GmbH"
    )["row_fingerprint"]
    pending = _report(
        backfill_report={
            "approval_status": "dry_run",
            "mappings": [
                {
                    "row_fingerprint": delta_fingerprint,
                    "proposed_canonical_id": "canonical-delta",
                    "base_decision": "new",
                    "eligible_for_identity_backfill": True,
                }
            ],
        }
    )
    pending_delta = next(item for item in pending["rows"] if item["company_name"] == "Delta GmbH")
    assert pending_delta["canonical_company_id"] == ""
    assert pending_delta["pending_backfill_canonical_company_id"] == "canonical-delta"
    assert "canonical_id_backfill_pending_approval" in pending_delta["exclusion_reasons"]

    approved = _report(
        backfill_report={
            "approval_status": "approved",
            "mappings": [
                {
                    "row_fingerprint": delta_fingerprint,
                    "proposed_canonical_id": "canonical-delta",
                    "base_decision": "new",
                    "eligible_for_identity_backfill": True,
                }
            ],
        }
    )
    approved_delta = next(item for item in approved["rows"] if item["company_name"] == "Delta GmbH")
    assert approved_delta["canonical_company_id"] == "canonical-delta"
    assert approved_delta["decision"] == "dual_ready"
    assert approved["counts"]["mapped_rows"] == len(rows)


def test_ownership_review_includes_unmapped_rows_sharing_conflicting_org():
    rows, columns, digest = read_master_snapshot(FIXTURE)
    extra = dict(next(row for row in rows if row["company_name"] == "Conflict A GmbH"))
    extra["canonical_CompanyID"] = "//"
    extra["company_name"] = "Unmapped Conflict GmbH"
    extra["Column1"] = "unmapped-conflict"
    rows.append(extra)

    report = build_source_eligibility_manifest(
        rows,
        columns,
        source_path=str(FIXTURE.resolve()),
        input_sha256=digest,
        cycle_id="unmapped-conflict-review",
        as_of=AS_OF,
        registry_report=_registry_review(),
    )

    conflict = report["ownership_review"]["organization_groups"][0]
    assert conflict["review"]["row_count"] == 3
    assert conflict["review"]["source_row_numbers"] == [8, 9, 15]
    unmapped = next(item for item in report["rows"] if item["company_name"] == "Unmapped Conflict GmbH")
    assert unmapped["canonical_company_id"] == ""
    assert unmapped["decision"] == "blocked"
    assert "conflicting_ownership_unresolved" in unmapped["exclusion_reasons"]


def test_reordering_preserves_row_fingerprint_decisions_and_task_keys():
    rows, columns, digest = read_master_snapshot(FIXTURE)
    forward = build_source_eligibility_manifest(
        rows,
        columns,
        source_path=str(FIXTURE.resolve()),
        input_sha256=digest,
        cycle_id="order-forward",
        as_of=AS_OF,
        registry_report=_registry_review(),
    )
    reverse = build_source_eligibility_manifest(
        reversed(rows),
        columns,
        source_path=str(FIXTURE.resolve()),
        input_sha256=digest,
        cycle_id="order-reverse",
        as_of=AS_OF,
        registry_report=_registry_review(),
    )
    forward_decisions = {
        row["row_fingerprint"]: (row["decision"], row["canonical_company_id"])
        for row in forward["rows"]
    }
    reverse_decisions = {
        row["row_fingerprint"]: (row["decision"], row["canonical_company_id"])
        for row in reverse["rows"]
    }
    assert forward_decisions == reverse_decisions
    assert [item["task_key"] for item in forward["tasks"]] == [item["task_key"] for item in reverse["tasks"]]


def test_sidecar_manifest_and_materialized_inputs_are_immutable_and_lossless(tmp_path):
    report = _report(registry_report=_registry_review())
    manifest_path = tmp_path / "eligibility.json"
    sidecar_path = tmp_path / "eligibility.raw.jsonl"
    first = write_manifest_bundle(manifest_path, report, raw_sidecar_path=sidecar_path)
    second = write_manifest_bundle(manifest_path, report, raw_sidecar_path=sidecar_path)
    assert first == second

    loaded = load_manifest(manifest_path)
    assert loaded["manifest_hash"] == first["manifest_hash"]
    assert loaded["raw_schema"]["column_order"][0] == "canonical_CompanyID"
    assert loaded["raw_schema"]["unexplained_columns"] == [f"Column{i}" for i in range(1, 10)]
    sidecar_records = [json.loads(line) for line in sidecar_path.read_text(encoding="utf-8").splitlines()]
    assert len(sidecar_records) == 13
    assert len(sidecar_records[0]["raw_columns"]) == 24
    assert sidecar_records[0]["raw_columns"]["Column1"] == "a1"

    employer_output = tmp_path / "employer-input.csv"
    linkedin_output = tmp_path / "linkedin-input.csv"
    employer_materialized = materialize_source_input(loaded, SOURCE_EMPLOYER, employer_output, pilot_only=False)
    linkedin_materialized = materialize_source_input(loaded, SOURCE_LINKEDIN, linkedin_output, pilot_only=False)
    assert employer_materialized["rows"] == 5
    assert linkedin_materialized["rows"] == 3
    with employer_output.open("r", encoding="utf-8-sig", newline="") as handle:
        employer_rows = list(csv.DictReader(handle))
    with linkedin_output.open("r", encoding="utf-8-sig", newline="") as handle:
        linkedin_rows = list(csv.DictReader(handle))
    assert {row["canonical_CompanyID"] for row in employer_rows} == {
        "master-alpha",
        "master-gamma",
        "master-malformed",
        "master-mismatch",
        "master-school",
    }
    assert {row["canonical_CompanyID"] for row in linkedin_rows} == {"master-alpha", "master-beta", "master-epsilon"}
    assert len(employer_rows[0]) == 24

    changed = dict(report)
    changed["cycle_id"] = "changed-cycle"
    with pytest.raises(FileExistsError, match="immutable manifest cycle"):
        write_manifest_bundle(manifest_path, changed, raw_sidecar_path=sidecar_path)


def test_both_scheduled_entrypoints_require_and_consume_the_manifest(tmp_path):
    report = _report(registry_report=_registry_review())
    manifest_path = tmp_path / "eligibility.json"
    write_manifest_bundle(manifest_path, report, raw_sidecar_path=tmp_path / "eligibility.raw.jsonl")

    employer_output = tmp_path / "employer-run"
    assert employer_main(["--manifest", str(manifest_path), "--output-dir", str(employer_output), "--dry-run"]) == 0
    linkedin_output = tmp_path / "linkedin-run"
    assert (
        linkedin_main(
            [
                "--manifest",
                str(manifest_path),
                "--output-dir",
                str(linkedin_output),
                "--mode",
                "validate",
                "--pagination-report",
                str(Path(__file__).parent / "fixtures" / "rc005_linkedin_pagination.json"),
                "--dry-run",
            ]
        )
        == 0
    )


def test_manifest_source_gate_rejects_wrong_schema_and_duplicate_task():
    report = _report()
    assert len(validate_manifest_for_source(report, SOURCE_EMPLOYER)) == 1
    assert len(validate_manifest_for_source(report, SOURCE_EMPLOYER, pilot_only=False)) == 5
    with pytest.raises(ValueError, match="versioned source-eligibility"):
        validate_manifest_for_source({"schema_version": "old"}, SOURCE_LINKEDIN)
