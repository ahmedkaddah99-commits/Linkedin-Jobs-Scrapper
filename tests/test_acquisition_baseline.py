from __future__ import annotations

import json
from pathlib import Path

from scripts.benchmark_acquisition_baseline import DEFAULT_FIXTURE_DIR, run_baseline


def test_rc002_workload_profiles_preserve_plan_cohorts() -> None:
    profiles = json.loads((DEFAULT_FIXTURE_DIR / "workload_profiles.json").read_text(encoding="utf-8"))

    assert profiles["dual_field_ready"]["input_rows"] == 1666
    assert profiles["identity_first_expansion"]["input_rows"] == 4371
    assert profiles["existing_linkedin_state"]["stored_jobs"] == 188206
    assert profiles["reviewed_eligible"]["execution_mode"] == "deferred_until_identity_review"


def test_rc002_offline_baseline_measures_adapters_publication_and_recovery() -> None:
    summary = run_baseline()

    assert summary["status"] == "completed"
    assert summary["execution"]["network_requests_allowed"] is False
    assert summary["measured_runtime"]["companies"] == 5
    assert summary["measured_runtime"]["raw_jobs"] == 38
    assert summary["measured_runtime"]["unique_jobs"] == 37
    assert summary["measured_runtime"]["accepted_jobs"] == 36
    assert summary["measured_runtime"]["retries"] == 1
    assert summary["measured_runtime"]["rate_limited_responses"] == 1
    assert summary["source_results"]["generic_large"]["complete_snapshot"] is False
    assert summary["source_results"]["generic_large"]["accepted_jobs"] == 1
    assert summary["publication"]["replay_same_publication"] is True
    assert summary["publication"]["duplicate_publications"] == 0
    assert summary["recovery"]["interrupted"] is True
    assert summary["recovery"]["resumed"] is True
    assert summary["recovery"]["replayed_completed_sources"] == 0


def test_rc002_fixture_hash_is_stable_for_comparison() -> None:
    first = run_baseline()
    second = run_baseline()

    assert first["execution"]["fixture_directory_sha256"] == second["execution"]["fixture_directory_sha256"]
    assert first["workload_profiles"] == second["workload_profiles"]
