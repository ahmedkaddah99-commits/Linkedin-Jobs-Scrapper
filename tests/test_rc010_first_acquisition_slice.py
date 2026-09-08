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
from backend.api.routes import build_route_registry
from backend.api.routes.registry import ApiRouteContext
from backend.bootstrap import create_backend


class _UserHandler:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.payload = None

    def _require_identity(self):
        return {"user_id": self.user_id}, object()

    def _send_json(self, payload, status=200, *, headers=None):
        self.payload = (status, payload)


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


def _cycle_with_tasks(store, targets: list[dict[str, object]], key: str):
    cycle = store.claim_due_cycle(window_key=key, lease_owner="rc010-fixture", scheduled_at=key)
    assert cycle is not None
    store.ensure_cycle_tasks(cycle["cycle_id"], targets)
    tasks = {
        target["target_id"]: store.claim_next_task(
            cycle_id=cycle["cycle_id"], lease_owner="rc010-fixture"
        )
        for target in targets
    }
    assert all(task is not None for task in tasks.values())
    return cycle, tasks


def _employer_observation(cycle_id: str, *, canonical_company_id: str = "company-acme"):
    return adapt_employer_job(
        {
            "canonical_company_id": canonical_company_id,
            "source_company_name": "Acme GmbH",
            "source_company_url": "https://acme.example",
            "source_provider": "greenhouse",
            "source_job_id": "acme-employer-42",
            "source_job_url": "https://jobs.acme.example/jobs/42",
            "apply_url_canonical": "https://boards.greenhouse.io/acme/jobs/42/apply",
            "job_title": "Operations Analyst",
            "description": "Operate reporting systems.",
            "location": "Berlin, Germany",
            "workplace_type": "Hybrid",
            "raw_content_hash": "employer-42-hash",
            "last_seen_at": "2026-09-06T10:00:00Z",
        },
        cycle_id=cycle_id,
        scan_id="employer-scan-42",
        observed_at="2026-09-06T10:00:00Z",
    )


def _linkedin_observation(cycle_id: str, *, canonical_company_id: str = "company-acme"):
    return adapt_linkedin_job(
        {
            "canonical_company_id": canonical_company_id,
            "linkedin_company_id": "123456",
            "source_company_name": "Acme GmbH",
            "source_company_url": "https://www.linkedin.com/company/acme",
            "linkedin_job_id": "linkedin-42",
            "linkedin_job_url": "https://www.linkedin.com/jobs/view/42",
            "apply_url_canonical": "https://boards.greenhouse.io/acme/jobs/42/apply",
            "apply_url_source": "external",
            "job_title": "Operations Analyst",
            "description": "Operate reporting systems.",
            "location": "Berlin, Germany",
            "easy_apply_status": "false",
            "applicant_count": "42",
            "company_match_status": "EXACT_PRIMARY_MATCH",
            "ownership_status": "EXACT_PRIMARY_MATCH",
            "location_classification": "GERMANY_CONFIRMED",
            "content_hash": "linkedin-42-hash",
            "run_id": "linkedin-run-42",
            "company_scan_id": "linkedin-scan-42",
        },
        cycle_id=cycle_id,
        scan_id="linkedin-scan-42",
        observed_at="2026-09-06T10:00:00Z",
    )


def _send_final(
    store,
    *,
    cycle_id: str,
    task_id: str,
    target_id: str,
    observation,
    mark_complete: bool = True,
):
    batch = next(iter_observation_batches((observation,), max_batch_size=25))
    transport = SqliteAcquisitionTransport(
        store,
        cycle_id=cycle_id,
        task_id=task_id,
        target_id=target_id,
        observed_at="2026-09-06T10:00:00Z",
    )
    receipt = transport.send_final(
        batch,
        snapshot_external_ids=[observation.source_job_id],
    )
    if mark_complete:
        store.complete_task(task_id, status="completed", result=receipt.store_result)
    return receipt


def _dispatch_jobs_route(app, user_id: str):
    handler = _UserHandler(user_id)
    context = ApiRouteContext(
        application=app,
        handler=handler,
        method="GET",
        segments=("personalized-jobs",),
        query={},
    )
    assert build_route_registry().dispatch(context, auth_required=True)
    assert handler.payload is not None
    assert handler.payload[0] == 200
    return handler.payload[1]


def _request_count(store) -> int:
    with store._connect() as connection:
        return int(connection.execute("SELECT COUNT(*) AS count FROM acquisition_requests").fetchone()["count"])


def test_rc010_dual_source_slice_reaches_jobs_and_preserves_public_head_on_failure(tmp_path: Path) -> None:
    app = create_backend(tmp_path, storage_backend="sqlite")
    store = app.repositories.acquisition_store
    employer = _target(
        "acme-employer",
        connector="career_site",
        provider="greenhouse",
        request_url="https://jobs.acme.example/jobs",
    )
    linkedin = _target(
        "acme-linkedin",
        connector="linkedin_guest",
        provider="linkedin",
        request_url="https://www.linkedin.com/company/acme/jobs",
    )
    targets = [employer, linkedin]
    master_row = {
        "canonical_company_id": "company-acme",
        "canonical_name": "Acme GmbH",
        "verified_website": "https://acme.example",
    }
    store.ensure_targets(targets)

    cycle, tasks = _cycle_with_tasks(store, targets, "rc010-success")
    employer_observation = _employer_observation(
        cycle["cycle_id"], canonical_company_id=master_row["canonical_company_id"]
    )
    linkedin_observation = _linkedin_observation(
        cycle["cycle_id"], canonical_company_id=master_row["canonical_company_id"]
    )
    _send_final(
        store,
        cycle_id=cycle["cycle_id"],
        task_id=tasks[employer["target_id"]]["task_id"],
        target_id=employer["target_id"],
        observation=employer_observation,
    )
    _send_final(
        store,
        cycle_id=cycle["cycle_id"],
        task_id=tasks[linkedin["target_id"]]["task_id"],
        target_id=linkedin["target_id"],
        observation=linkedin_observation,
    )
    publication_id = store.publish_staging_snapshot(
        cycle_id=cycle["cycle_id"],
        valid_target_ids=[target["target_id"] for target in targets],
        created_by="rc010-fixture",
    )
    store.promote_staging_publication(publication_id, created_by="rc010-fixture")
    store.complete_cycle(cycle["cycle_id"], status="completed", publication_id=publication_id)

    public = app.get_public_acquisition_catalog()
    assert public["freshness"] == "valid"
    assert public["total"] == 1
    assert public["jobs"][0]["company"] == "Acme GmbH"

    with store._connect() as connection:
        canonical = connection.execute(
            "SELECT canonical_job_id, company_id FROM canonical_jobs"
        ).fetchall()
        observations = connection.execute(
            "SELECT target_id, source_ats, raw_payload_json FROM job_source_observations ORDER BY target_id"
        ).fetchall()
        company_count_before_replay = connection.execute(
            "SELECT COUNT(*) AS count FROM canonical_companies"
        ).fetchone()["count"]
    assert len(canonical) == 1
    assert len(observations) == 2
    assert public["jobs"][0]["canonical_job_id"] == canonical[0]["canonical_job_id"]
    assert {row["target_id"] for row in observations} == {employer["target_id"], linkedin["target_id"]}
    assert {row["source_ats"] for row in observations} == {"greenhouse", "linkedin"}
    contracts = [
        json.loads(row["raw_payload_json"])["source_raw_payload"]["observation_contract"]
        for row in observations
    ]
    assert {contract["canonical_company_id"] for contract in contracts} == {master_row["canonical_company_id"]}
    assert {contract["scan_id"] for contract in contracts} == {"employer-scan-42", "linkedin-scan-42"}

    # The actual user Jobs route is a read of the published head. Two users
    # can browse the same result without reserving an acquisition request.
    request_count_before_reads = _request_count(store)
    first_user = _dispatch_jobs_route(app, "user-a")
    second_user = _dispatch_jobs_route(app, "user-b")
    assert first_user["total"] == second_user["total"] == 1
    assert first_user["jobs"][0]["title"] == "Operations Analyst"
    assert second_user["jobs"][0]["posting_id"] == first_user["jobs"][0]["posting_id"]
    assert _request_count(store) == request_count_before_reads

    # Replaying completed producer input is a no-op at the durable boundary.
    _send_final(
        store,
        cycle_id=cycle["cycle_id"],
        task_id=tasks[employer["target_id"]]["task_id"],
        target_id=employer["target_id"],
        observation=employer_observation,
        mark_complete=False,
    )
    _send_final(
        store,
        cycle_id=cycle["cycle_id"],
        task_id=tasks[linkedin["target_id"]]["task_id"],
        target_id=linkedin["target_id"],
        observation=linkedin_observation,
        mark_complete=False,
    )
    with store._connect() as connection:
        assert connection.execute("SELECT COUNT(*) AS count FROM canonical_jobs").fetchone()["count"] == 1
        assert connection.execute("SELECT COUNT(*) AS count FROM job_source_observations").fetchone()["count"] == 2
        assert connection.execute("SELECT COUNT(*) AS count FROM canonical_companies").fetchone()["count"] == company_count_before_replay

    # A failed LinkedIn collection makes only that source unknown; it cannot
    # replace the last valid employer-backed public publication.
    failed_cycle, failed_tasks = _cycle_with_tasks(store, targets, "rc010-linkedin-failed")
    _send_final(
        store,
        cycle_id=failed_cycle["cycle_id"],
        task_id=failed_tasks[employer["target_id"]]["task_id"],
        target_id=employer["target_id"],
        observation=_employer_observation(
            failed_cycle["cycle_id"], canonical_company_id=master_row["canonical_company_id"]
        ),
    )
    failed_transport = SqliteAcquisitionTransport(
        store,
        cycle_id=failed_cycle["cycle_id"],
        task_id=failed_tasks[linkedin["target_id"]]["task_id"],
        target_id=linkedin["target_id"],
        observed_at="2026-09-06T11:00:00Z",
    )
    failed_receipt = failed_transport.send_final(
        empty_observation_batch(),
        snapshot_external_ids=[],
        valid_snapshot=False,
        closure_safe=False,
    )
    store.complete_task(
        failed_tasks[linkedin["target_id"]]["task_id"],
        status="failed",
        result=failed_receipt.store_result,
        error_code="source_unavailable",
        error_message="Recorded fixture transport failure",
    )
    store.complete_cycle(
        failed_cycle["cycle_id"],
        status="degraded",
        error_code="source_unavailable",
        error_message="LinkedIn fixture unavailable",
    )

    unchanged_public = app.get_public_acquisition_catalog()
    assert unchanged_public["publication"]["publication_id"] == publication_id
    assert unchanged_public["total"] == 1
    assert store.get_cycle(failed_cycle["cycle_id"])["status"] == "degraded"
    assert store.get_source_state_summary(linkedin["target_id"]) == {"unknown": 1}
    successful_source = next(
        item for item in store.list_cycle_targets(failed_cycle["cycle_id"])
        if item["target_id"] == employer["target_id"]
    )
    assert successful_source["task"]["task_status"] == "completed"
    assert successful_source["task"]["valid_snapshot"] == 1
    assert successful_source["task"]["jobs_observed"] == 1
    failed_source = next(
        item for item in store.list_cycle_targets(failed_cycle["cycle_id"])
        if item["target_id"] == linkedin["target_id"]
    )
    assert failed_source["task"]["task_status"] == "failed"
    assert failed_source["task"]["valid_snapshot"] == 0
    assert failed_source["task"]["task_error_code"] == "source_unavailable"
