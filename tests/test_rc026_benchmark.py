from __future__ import annotations

from pathlib import Path

import pytest

from scripts.acquisition_state_backup import create_checkpoint
from scripts.benchmark_acquisition_full_state import (
    benchmark_checkpoint,
    build_cost_model,
    run_customer_replay,
    run_employer_concurrency_matrix,
)
from scripts.master_employer_jobs_catalog import EmployerCollectionResult, EmployerCompany, EmployerState


def _company() -> EmployerCompany:
    return EmployerCompany(
        canonical_company_id="fixture-company",
        company_name="Fixture Company",
        website_url="https://fixture.invalid",
    )


def test_fixture_matrix_preserves_coverage_and_request_zero(tmp_path: Path) -> None:
    report = run_employer_concurrency_matrix(tmp_path / "matrix", company_concurrencies=(1, 2, 4))

    assert report["tuning"]["fixture_max_admitted_company_concurrency"] == 4
    assert report["tuning"]["production_company_concurrency"] is None
    for row in report["matrix"]:
        assert row["metrics"]["companies_processed"] == 5
        assert row["metrics"]["persisted_jobs"] == 5
        assert row["metrics"]["exported_jobs"] == 5
        assert row["metrics"]["final_export_completed"] is True
        assert row["metrics"]["request_accounting"]["total_attempts"] == 0
        assert row["peak_active_collectors"] <= row["company_concurrency"]


def test_customer_replay_is_bounded_and_offline(tmp_path: Path) -> None:
    report = run_customer_replay(tmp_path / "customer", jobs=20, iterations=2)

    assert report["result"]["jobs"] == 20
    assert report["result"]["iterations"] == 2
    assert report["result"]["network_requests"] == 0
    assert report["result"]["database_billing"].startswith("unknown")
    assert report["resources"]["wall_seconds"] >= 0


def test_verified_checkpoint_copy_and_real_export_are_integrity_checked(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_db = source_dir / "master_employer_jobs_state.db"
    state = EmployerState(source_db)
    try:
        state.save(
            EmployerCollectionResult(
                company=_company(),
                jobs=[
                    {
                        "canonical_company_id": "fixture-company",
                        "source_provider": "fixture",
                        "source_job_id": "fixture-job",
                        "source_job_url": "https://fixture.invalid/jobs/fixture-job",
                        "job_title": "Fixture job",
                    }
                ],
                status="completed",
            )
        )
    finally:
        state.close()
    checkpoint_root = tmp_path / "checkpoints"
    checkpoint = create_checkpoint(
        role="employer",
        source_db=source_db,
        checkpoint_root=checkpoint_root,
        source_version="fixture-release",
        manifest_id="fixture-input",
        manifest_sha256="a" * 64,
        cycle_id="fixture-cycle",
        shard_id="fixture-shard",
        high_water_marks={"companies": 1},
    )

    checkpoint_dir = checkpoint_root / "employer" / checkpoint["checkpoint_id"]
    result = benchmark_checkpoint("employer", checkpoint_dir, tmp_path / "benchmark")

    assert result["source"]["source_untouched"] is True
    assert result["copy"]["sha256_verified"] is True
    assert result["export"]["persisted_jobs"] == 1
    assert result["export"]["exported_jobs"] == 1
    assert result["export"]["final_export_completed"] is True
    assert result["export"]["exported_bytes"] > 0


def test_cost_model_keeps_unmeasured_prices_unknown() -> None:
    model = build_cost_model({"historical_state": [{"source": {"bytes": 10}}]})

    assert model["request_accounting"] == {"offline_observed": 0, "provider_benchmark": "not_run"}
    assert model["monthly_components"]["fixed_hosting"].startswith("unknown")
    assert model["scenarios"]["expected"]["cost_eur"] == "unknown"
    assert model["no_flat_capacity_or_savings_claim"] is True


def test_benchmark_rejects_uncapped_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        run_employer_concurrency_matrix(tmp_path / "matrix", company_concurrencies=(9,))
    with pytest.raises(ValueError):
        run_customer_replay(tmp_path / "customer", jobs=1, iterations=101)
