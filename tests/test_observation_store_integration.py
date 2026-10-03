from __future__ import annotations

import json
from pathlib import Path

from backend.acquisition.producer_adapters import (
    adapt_employer_job,
    adapt_linkedin_job,
    empty_observation_batch,
    iter_observation_batches,
    SqliteAcquisitionTransport,
)
from backend.bootstrap import create_backend


def _target(target_id: str) -> dict[str, object]:
    return {
        "target_id": target_id,
        "target_kind": "employer_career_site",
        "display_name": "Acme Germany source",
        "canonical_company_name": "Acme GmbH",
        "canonical_target_url": "https://jobs.acme.example",
        "provenance_url": "https://acme.example",
        "request_url": "https://jobs.acme.example/jobs",
        "official_employer_hosts": ["jobs.acme.example"],
        "connector": "career_site",
        "provider": "greenhouse",
        "source_token": "acme",
        "enabled": True,
        "publication_enabled": True,
        "config": {"absence_grace_attempts": 2},
    }


def _observation(index: int, cycle_id: str):
    return adapt_employer_job(
        {
            "canonical_company_id": "company-acme",
            "source_company_name": "Acme GmbH",
            "source_company_url": "https://acme.example",
            "source_provider": "greenhouse",
            "source_job_id": f"acme-{index}",
            "source_job_url": f"https://jobs.acme.example/jobs/{index}",
            "apply_url_canonical": f"https://boards.greenhouse.io/acme/jobs/{index}/apply",
            "job_title": "Backend Engineer",
            "description": f"Build platform service {index}.",
            "location": "Berlin, Germany",
            "workplace_type": "Hybrid",
            "raw_content_hash": f"hash-{index}",
            "last_seen_at": "2026-09-06T10:00:00Z",
        },
        cycle_id=cycle_id,
        scan_id="scan-acme",
    )


def _cycle_task(store, target: dict[str, object], key: str) -> tuple[dict[str, object], dict[str, object]]:
    cycle = store.claim_due_cycle(window_key=key, lease_owner="rc009-test", scheduled_at=key)
    store.ensure_cycle_tasks(cycle["cycle_id"], [target])
    task = store.claim_next_task(cycle_id=cycle["cycle_id"], lease_owner="rc009-test")
    return cycle, task


def test_adapter_transport_publishes_bounded_final_inventory_and_replays_safely(tmp_path: Path) -> None:
    app = create_backend(tmp_path, storage_backend="sqlite")
    store = app.repositories.acquisition_store
    target = _target("acme-employer")
    store.ensure_targets([target])
    cycle, task = _cycle_task(store, target, "rc009-large-company")
    observations = [_observation(index, cycle["cycle_id"]) for index in range(26)]
    batches = tuple(iter_observation_batches(observations, max_batch_size=26))
    assert len(batches) == 1
    transport = SqliteAcquisitionTransport(
        store,
        cycle_id=cycle["cycle_id"],
        task_id=task["task_id"],
        target_id=target["target_id"],
        observed_at="2026-09-06T10:00:00Z",
    )

    intermediate = transport.send(batches[0])
    assert intermediate.store_result["complete_snapshot"] is False
    assert intermediate.store_result["closure_safe"] is False

    external_ids = [observation.source_job_id for observation in observations]
    final = transport.send_final(batches[0], snapshot_external_ids=external_ids)
    replay = transport.send_final(batches[0], snapshot_external_ids=external_ids)
    assert final.store_result["complete_snapshot"] is True
    assert final.store_result["closure_safe"] is True
    assert replay.receipt_id == final.receipt_id

    with store._connect() as connection:
        observation_count = connection.execute(
            "SELECT COUNT(*) AS count FROM job_source_observations WHERE cycle_id=?",
            (cycle["cycle_id"],),
        ).fetchone()["count"]
        active_count = connection.execute(
            "SELECT COUNT(*) AS count FROM job_source_states WHERE target_id=? AND lifecycle_state='active'",
            (target["target_id"],),
        ).fetchone()["count"]
        raw_payload = connection.execute(
            "SELECT raw_payload_json FROM job_source_observations WHERE cycle_id=? LIMIT 1",
            (cycle["cycle_id"],),
        ).fetchone()["raw_payload_json"]
    assert observation_count == 26
    assert active_count == 26
    assert (
        json.loads(raw_payload)["source_raw_payload"]["observation_contract"]["schema_version"]
        == "runr_source_observation_v1"
    )

    publication_id = store.publish_staging_snapshot(
        cycle_id=cycle["cycle_id"],
        valid_target_ids=[target["target_id"]],
        created_by="rc009-test",
    )
    staging = store.get_staging_catalog(publication_id=publication_id)
    assert staging["total"] == 26
    assert staging["jobs"][0]["company"] == "Acme GmbH"


def test_partial_and_confirmed_zero_delivery_never_authorize_false_closure(tmp_path: Path) -> None:
    app = create_backend(tmp_path, storage_backend="sqlite")
    store = app.repositories.acquisition_store
    target = _target("acme-employer")
    store.ensure_targets([target])

    first_cycle, first_task = _cycle_task(store, target, "rc009-seed")
    first = _observation(1, first_cycle["cycle_id"])
    first_transport = SqliteAcquisitionTransport(
        store,
        cycle_id=first_cycle["cycle_id"],
        task_id=first_task["task_id"],
        target_id=target["target_id"],
    )
    first_transport.send_final(
        next(iter_observation_batches((first,), max_batch_size=25)),
        snapshot_external_ids=[first.source_job_id],
    )
    first_staging = store.publish_staging_snapshot(
        cycle_id=first_cycle["cycle_id"],
        valid_target_ids=[target["target_id"]],
        created_by="rc009-test",
    )
    store.promote_staging_publication(first_staging, created_by="rc009-test")

    second_cycle, second_task = _cycle_task(store, target, "rc009-invalid-empty")
    second_transport = SqliteAcquisitionTransport(
        store,
        cycle_id=second_cycle["cycle_id"],
        task_id=second_task["task_id"],
        target_id=target["target_id"],
    )
    invalid = second_transport.send_final(
        empty_observation_batch(),
        snapshot_external_ids=[],
        valid_snapshot=False,
        closure_safe=False,
    )
    assert invalid.store_result["closure_safe"] is False
    assert invalid.store_result["valid_snapshot"] is False

    with store._connect() as connection:
        state = connection.execute(
            "SELECT lifecycle_state, absence_count FROM job_source_states WHERE target_id=?",
            (target["target_id"],),
        ).fetchone()
    assert state["lifecycle_state"] == "unknown"
    assert state["absence_count"] == 0

    zero_target = _target("acme-zero")
    store.ensure_targets([zero_target])
    zero_cycle, zero_task = _cycle_task(store, zero_target, "rc009-confirmed-zero")
    zero_transport = SqliteAcquisitionTransport(
        store,
        cycle_id=zero_cycle["cycle_id"],
        task_id=zero_task["task_id"],
        target_id=zero_target["target_id"],
    )
    zero = zero_transport.send_final(empty_observation_batch(), snapshot_external_ids=[])
    assert zero.store_result["valid_snapshot"] is True
    assert zero.store_result["closure_safe"] is True
    assert store.get_public_catalog()["total"] == 1


def test_linkedin_observation_uses_the_same_store_contract(tmp_path: Path) -> None:
    app = create_backend(tmp_path, storage_backend="sqlite")
    store = app.repositories.acquisition_store
    target = {**_target("acme-linkedin"), "provider": "linkedin", "connector": "linkedin_guest"}
    store.ensure_targets([target])
    cycle, task = _cycle_task(store, target, "rc009-linkedin")
    observation = adapt_linkedin_job(
        {
            "canonical_company_id": "company-acme",
            "linkedin_company_id": "123",
            "source_company_name": "Acme GmbH",
            "source_company_url": "https://www.linkedin.com/company/acme",
            "linkedin_job_id": "linkedin-42",
            "linkedin_job_url": "https://www.linkedin.com/jobs/view/42",
            "apply_url_canonical": "https://jobs.acme.example/jobs/42/apply",
            "apply_url_source": "external",
            "job_title": "Data Engineer",
            "description": "Build data systems.",
            "location": "Berlin, Germany",
            "easy_apply_status": "false",
            "applicant_count": "42",
            "company_match_status": "EXACT_PRIMARY_MATCH",
            "ownership_status": "EXACT_PRIMARY_MATCH",
            "location_classification": "GERMANY_CONFIRMED",
            "content_hash": "linkedin-42-hash",
            "last_seen_at": "2026-09-06T10:00:00Z",
            "run_id": "run-linkedin",
            "company_scan_id": "scan-linkedin",
        },
        cycle_id=cycle["cycle_id"],
        scan_id="scan-linkedin",
    )
    transport = SqliteAcquisitionTransport(
        store,
        cycle_id=cycle["cycle_id"],
        task_id=task["task_id"],
        target_id=target["target_id"],
    )
    result = transport.send_final(
        next(iter_observation_batches((observation,), max_batch_size=25)),
        snapshot_external_ids=[observation.source_job_id],
    )
    assert result.accepted_count == 1
    with store._connect() as connection:
        stored = connection.execute(
            "SELECT source_ats, raw_payload_json FROM job_source_observations WHERE cycle_id=?",
            (cycle["cycle_id"],),
        ).fetchone()
    assert stored["source_ats"] == "linkedin"
    assert json.loads(stored["raw_payload_json"])["source_raw_payload"]["observation_contract"]["source"] == "linkedin"
