from __future__ import annotations

import json
from pathlib import Path

from backend.acquisition.phase_b import normalize_phase_b_jobs
from backend.acquisition.producer_adapters import (
    SqliteAcquisitionTransport,
    adapt_employer_job,
    adapt_linkedin_job,
    iter_observation_batches,
)
from backend.bootstrap import create_backend


FIXTURE = Path(__file__).parent / "fixtures" / "rc009_cross_source_identity.json"


def _target(target_id: str, *, connector: str, provider: str, request_url: str) -> dict[str, object]:
    return {
        "target_id": target_id,
        "target_kind": "employer_career_site",
        "display_name": "Acme GmbH",
        "canonical_company_name": "Acme GmbH",
        "canonical_target_url": request_url,
        "provenance_url": "https://acme.example",
        "request_url": request_url,
        "official_employer_hosts": ["jobs.acme.example"],
        "connector": connector,
        "provider": provider,
        "source_token": "acme",
        "enabled": True,
        "publication_enabled": True,
        "config": {"absence_grace_attempts": 2},
    }


def _deliver(store, *, cycle_id: str, task_id: str, target_id: str, observations, source_ids):
    batch = next(iter_observation_batches(observations, max_batch_size=25))
    transport = SqliteAcquisitionTransport(
        store,
        cycle_id=cycle_id,
        task_id=task_id,
        target_id=target_id,
        observed_at="2026-09-06T10:00:00Z",
    )
    return transport.send_final(batch, snapshot_external_ids=source_ids)


def test_cross_source_matching_requires_strong_evidence(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    app = create_backend(tmp_path, storage_backend="sqlite")
    store = app.repositories.acquisition_store
    employer_target = _target(
        "acme-employer",
        connector="career_site",
        provider="greenhouse",
        request_url="https://jobs.acme.example/jobs",
    )
    linkedin_target = _target(
        "acme-linkedin",
        connector="linkedin_guest",
        provider="linkedin",
        request_url="https://www.linkedin.com/company/acme/jobs",
    )
    store.ensure_targets([employer_target, linkedin_target])
    cycle = store.claim_due_cycle(window_key="rc009-identity", lease_owner="rc009-test", scheduled_at="rc009-identity")
    assert cycle is not None
    cycle_id = str(cycle["cycle_id"])
    store.ensure_cycle_tasks(cycle_id, [employer_target, linkedin_target])
    tasks = {
        target["target_id"]: store.claim_next_task(cycle_id=cycle_id, lease_owner="rc009-test")
        for target in (employer_target, linkedin_target)
    }
    assert all(task is not None for task in tasks.values())

    employer_observations = tuple(
        adapt_employer_job(item, cycle_id=cycle_id, scan_id="employer-scan-009")
        for item in fixture["employer"]
    )
    linkedin_observations = tuple(
        adapt_linkedin_job(item, cycle_id=cycle_id, scan_id="linkedin-scan-009")
        for item in fixture["linkedin"]
    )
    _deliver(
        store,
        cycle_id=cycle_id,
        task_id=str(tasks[employer_target["target_id"]]["task_id"]),
        target_id=str(employer_target["target_id"]),
        observations=employer_observations,
        source_ids=[item.source_job_id for item in employer_observations],
    )
    _deliver(
        store,
        cycle_id=cycle_id,
        task_id=str(tasks[linkedin_target["target_id"]]["task_id"]),
        target_id=str(linkedin_target["target_id"]),
        observations=linkedin_observations,
        source_ids=[item.source_job_id for item in linkedin_observations],
    )

    with store._connect() as connection:
        canonical = connection.execute(
            "SELECT canonical_job_id, title, canonical_url FROM canonical_jobs ORDER BY canonical_url"
        ).fetchall()
        observations = connection.execute(
            "SELECT external_job_id, canonical_job_id FROM job_source_observations ORDER BY external_job_id"
        ).fetchall()

    # Two same-source openings and one cross-source opening remain distinct;
    # the application URL and requisition ID each identify their source twin.
    assert len(canonical) == 3
    assert len(observations) == 5
    by_external = {str(row["external_job_id"]): str(row["canonical_job_id"]) for row in observations}
    assert by_external["linkedin-strong-application"] == by_external["employer-42"]
    assert by_external["linkedin-strong-requisition"] == by_external["employer-43"]
    assert by_external["linkedin-ambiguous"] not in {
        by_external["employer-42"],
        by_external["employer-43"],
    }


def test_foreign_label_and_invalid_apply_stay_traceable_and_easy_apply_is_rejected(tmp_path: Path) -> None:
    app = create_backend(tmp_path, storage_backend="sqlite")
    store = app.repositories.acquisition_store
    target = _target(
        "acme-employer",
        connector="career_site",
        provider="greenhouse",
        request_url="https://jobs.acme.example/jobs",
    )
    store.ensure_targets([target])
    cycle = store.claim_due_cycle(window_key="rc009-quality", lease_owner="rc009-test", scheduled_at="rc009-quality")
    assert cycle is not None
    cycle_id = str(cycle["cycle_id"])
    store.ensure_cycle_tasks(cycle_id, [target])
    task = store.claim_next_task(cycle_id=cycle_id, lease_owner="rc009-test")
    assert task is not None
    observation = adapt_employer_job(
        {
            "canonical_company_id": "company-acme",
            "source_company_name": "Foreign Holdings Ltd",
            "source_company_url": "https://foreign.example",
            "source_provider": "greenhouse",
            "source_job_id": "foreign-label-1",
            "source_job_url": "https://jobs.acme.example/jobs/foreign-label-1",
            "apply_url_canonical": "javascript:void(0)",
            "job_title": "Operations Analyst",
            "description": "Retained for review.",
            "location": "Berlin, Germany",
        },
        cycle_id=cycle_id,
        scan_id="quality-scan-009",
    )
    _deliver(
        store,
        cycle_id=cycle_id,
        task_id=str(task["task_id"]),
        target_id=str(target["target_id"]),
        observations=(observation,),
        source_ids=[observation.source_job_id],
    )
    publication_id = store.publish_staging_snapshot(
        cycle_id=cycle_id,
        valid_target_ids=[str(target["target_id"])],
        created_by="rc009-test",
    )
    staging = store.get_staging_catalog(publication_id=publication_id)
    assert staging["total"] == 1
    assert staging["jobs"][0]["company"] == "Acme GmbH"
    assert staging["jobs"][0]["apply_url"] == ""
    assert staging["publication"]["preflight"]["broken_apply_destinations"]

    with store._connect() as connection:
        row = connection.execute(
            "SELECT raw_payload_json, quality_warnings_json FROM job_source_observations WHERE external_job_id=?",
            ("foreign-label-1",),
        ).fetchone()
    raw = json.loads(row["raw_payload_json"])
    assert raw["source_raw_payload"]["producer_record"]["source_company_name"] == "Foreign Holdings Ltd"
    assert "source_labeled_employer_name_normalized" in json.loads(row["quality_warnings_json"])

    policy_result = normalize_phase_b_jobs(
        [
            {
                "id": "easy-1",
                "title": "Operations Analyst",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/easy-1",
                "application_method": "easy_apply",
            }
        ],
        target,
    )
    assert policy_result["accepted"] == []
    assert policy_result["rejected"][0]["reason"] == "unsupported_application_method"
