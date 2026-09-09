from __future__ import annotations

from copy import deepcopy

import pytest

from backend.application.expansion_wave_manifest import build_expansion_wave_manifest
from backend.application.source_eligibility_manifest import SCHEMA_VERSION


def _manifest() -> dict:
    rows = []
    tasks = []
    for index, (company_id, source, pilot, org_id) in enumerate(
        (
            ("company-b", "employer", True, ""),
            ("company-b", "linkedin", True, "org-2"),
            ("company-a", "employer", False, ""),
            ("company-a", "linkedin", False, "org-1"),
        ),
        start=2,
    ):
        fingerprint = f"fingerprint-{index}"
        rows.append(
            {
                "source_row_number": index,
                "row_fingerprint": fingerprint,
                "canonical_company_id": company_id,
                "source_eligibility": {"employer": True, "linkedin": True},
                "ownership": {"status": "resolved"},
                "review_required": False,
            }
        )
        tasks.append(
            {
                "task_key": f"{source}:{company_id}",
                "source": source,
                "canonical_company_id": company_id,
                "representative_source_row_number": index,
                "representative_row_fingerprint": fingerprint,
                "pilot_eligible": pilot,
                "row_fingerprints": [fingerprint],
                "organization_associations": ([{"linkedin_org_id": org_id}] if org_id else []),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": "source-eligibility-test",
        "manifest_version": "test:v1",
        "manifest_hash": "source-hash",
        "rows": rows,
        "tasks": tasks,
        "integrity": {"eligible_tasks_have_one_canonical_id": True},
    }


def test_wave_manifest_keeps_employers_together_and_is_deterministic():
    source = _manifest()
    first = build_expansion_wave_manifest(
        source,
        cohort="all",
        wave_size=1,
        request_cap=40,
        credit_cap=70,
        max_failure_rate=0.2,
        max_queue_age_seconds=900,
    )
    reversed_source = deepcopy(source)
    reversed_source["tasks"].reverse()
    second = build_expansion_wave_manifest(
        reversed_source,
        cohort="all",
        wave_size=1,
        request_cap=40,
        credit_cap=70,
        max_failure_rate=0.2,
        max_queue_age_seconds=900,
    )

    assert first == second
    assert [wave["canonical_company_ids"] for wave in first["waves"]] == [["company-a"], ["company-b"]]
    assert [wave["source_task_count"] for wave in first["waves"]] == [2, 2]
    assert first["waves"][0]["organization_groups"] == ["org-1"]
    assert first["policy"]["no_provider_requests"] is True


def test_wave_cohorts_expose_deferred_source_tasks_without_applying_them():
    projection = build_expansion_wave_manifest(
        _manifest(),
        cohort="pilot",
        wave_size=10,
        request_cap=10,
        credit_cap=10,
        max_failure_rate=0,
        max_queue_age_seconds=60,
    )

    assert projection["coverage"]["selected_source_tasks"] == 2
    assert projection["coverage"]["deferred_source_tasks"] == 2
    assert projection["coverage"]["deferred_task_keys"] == ["employer:company-a", "linkedin:company-a"]
    assert all("apply" not in wave for wave in projection["waves"])


def test_wave_manifest_rejects_missing_integrity_or_unsafe_caps():
    source = _manifest()
    source["integrity"] = {}
    with pytest.raises(ValueError, match="canonical-ID integrity"):
        build_expansion_wave_manifest(
            source,
            wave_size=1,
            request_cap=1,
            credit_cap=1,
            max_failure_rate=0,
            max_queue_age_seconds=1,
        )

    with pytest.raises(ValueError, match="credit_cap"):
        build_expansion_wave_manifest(
            _manifest(),
            wave_size=1,
            request_cap=1,
            credit_cap=0,
            max_failure_rate=0,
            max_queue_age_seconds=1,
        )
