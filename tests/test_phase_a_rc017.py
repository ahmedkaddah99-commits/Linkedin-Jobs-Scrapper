from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.acquisition.publication import StalePublicationHeadError
from backend.bootstrap import create_backend
from scripts.master_linkedin_jobs_catalog import (
    GENERATION_DIRECTORY_NAME,
    GENERATION_POINTER_NAME,
    GENERATION_ARTIFACT_NAMES,
    publish_catalog_generation,
    read_current_catalog_generation,
    write_catalog_generation_manifest,
)


def _target(target_id: str, display_name: str = "Acme GmbH") -> dict[str, object]:
    return {
        "target_id": target_id,
        "target_kind": "employer_career_site",
        "display_name": display_name,
        "canonical_target_url": f"https://{target_id}.example/jobs",
        "provenance_url": f"https://{target_id}.example",
        "request_url": f"https://{target_id}.example/jobs",
        "official_employer_hosts": [f"{target_id}.example"],
        "connector": "fixture",
        "source_token": target_id,
        "enabled": True,
        "publication_enabled": True,
        "config": {"absence_grace_attempts": 1},
    }


def _job(job_id: str, url: str, description: str, *, requisition_id: str = "") -> dict[str, str]:
    job = {
        "job_id": job_id,
        "title": "Platform Engineer",
        "location": "Berlin",
        "url": url,
        "apply_link": f"{url}/apply",
        "description": description,
    }
    if requisition_id:
        job["requisition_id"] = requisition_id
    return job


def _ingest(store, target: dict[str, object], key: str, observed_at: str, jobs: list[dict[str, str]]):
    cycle = store.claim_due_cycle(
        window_key=key,
        lease_owner="rc017-fixture",
        scheduled_at=observed_at,
    )
    assert cycle is not None
    cycle_id = str(cycle["cycle_id"])
    store.ensure_cycle_tasks(cycle_id, [target])
    task = store.claim_next_task(cycle_id=cycle_id, lease_owner="rc017-fixture")
    assert task is not None
    return store.ingest_snapshot(
        cycle_id=cycle_id,
        task_id=str(task["task_id"]),
        target_id=str(target["target_id"]),
        jobs=jobs,
        complete_snapshot=True,
        valid_snapshot=True,
        observed_at=observed_at,
    ), cycle_id


def test_late_scan_cannot_regress_newer_version_or_apply_absence(tmp_path: Path) -> None:
    app = create_backend(tmp_path, storage_backend="sqlite")
    store = app.repositories.acquisition_store
    linkedin = _target("linkedin-source")
    employer = _target("employer-source")
    store.ensure_targets([linkedin, employer])

    _ingest(
        store,
        linkedin,
        "rc017-linkedin-newer-source",
        "2026-09-02T10:00:00Z",
        [_job("linkedin-1", "https://linkedin-source.example/jobs/1", "LinkedIn accepted content", requisition_id="REQ-1")],
    )
    _ingest(
        store,
        employer,
        "rc017-employer-newest-source",
        "2026-09-03T10:00:00Z",
        [_job("employer-1", "https://employer-source.example/jobs/1", "Employer accepted content", requisition_id="REQ-1")],
    )
    stale_result, _ = _ingest(
        store,
        linkedin,
        "rc017-linkedin-old-content",
        "2026-09-01T10:00:00Z",
        [_job("linkedin-1", "https://linkedin-source.example/jobs/1", "Old late content", requisition_id="REQ-1")],
    )
    empty_result, _ = _ingest(
        store,
        linkedin,
        "rc017-linkedin-old-empty",
        "2026-09-01T11:00:00Z",
        [],
    )

    assert stale_result["stale_ignored"] == 1
    assert empty_result["closed"] == 0
    assert store.get_source_state_summary("linkedin-source") == {"active": 1}
    with store._connect() as connection:
        job = connection.execute(
            """
            SELECT j.lifecycle_state, v.description
            FROM canonical_jobs j
            JOIN job_posting_versions v ON v.version_id=j.current_version_id
            """
        ).fetchone()
        assert job["lifecycle_state"] == "active"
        assert job["description"] == "Employer accepted content"


def test_staging_candidate_with_old_job_version_cannot_be_promoted(tmp_path: Path) -> None:
    app = create_backend(tmp_path, storage_backend="sqlite")
    store = app.repositories.acquisition_store
    target = _target("publication-source")
    store.ensure_targets([target])

    _, first_cycle = _ingest(
        store,
        target,
        "rc017-publication-one",
        "2026-09-01T10:00:00Z",
        [_job("job-1", "https://publication-source.example/jobs/1", "Version one")],
    )
    first = store.publish_valid_snapshot(
        cycle_id=first_cycle,
        valid_target_ids=[str(target["target_id"])],
    )

    _, staging_cycle = _ingest(
        store,
        target,
        "rc017-publication-staging",
        "2026-09-02T10:00:00Z",
        [_job("job-1", "https://publication-source.example/jobs/1", "Version two")],
    )
    staging = store.publish_staging_snapshot(
        cycle_id=staging_cycle,
        valid_target_ids=[str(target["target_id"])],
    )

    _, newest_cycle = _ingest(
        store,
        target,
        "rc017-publication-newest",
        "2026-09-03T10:00:00Z",
        [_job("job-1", "https://publication-source.example/jobs/1", "Version three")],
    )
    newest = store.publish_valid_snapshot(
        cycle_id=newest_cycle,
        valid_target_ids=[str(target["target_id"])],
    )
    assert newest != first

    with pytest.raises(StalePublicationHeadError):
        store.promote_staging_publication(
            staging,
            expected_previous_publication_id=newest,
            created_by="rc017-fixture",
        )
    assert store.get_public_catalog()["publication"]["publication_id"] == newest


def test_generation_pointer_publishes_complete_hash_checked_snapshot(tmp_path: Path) -> None:
    output = tmp_path / "output"
    generation_id = "generation_rc017_complete"
    generation_dir = output / GENERATION_DIRECTORY_NAME / generation_id
    generation_dir.mkdir(parents=True)
    (generation_dir / GENERATION_ARTIFACT_NAMES[0]).write_text("id,title\n1,Engineer\n", encoding="utf-8")
    (generation_dir / GENERATION_ARTIFACT_NAMES[1]).write_text('{"record_type":"job_observation"}\n', encoding="utf-8")
    (generation_dir / GENERATION_ARTIFACT_NAMES[2]).write_text('{"run_outcome":"COMPLETE"}\n', encoding="utf-8")

    result = publish_catalog_generation(
        output,
        generation_id=generation_id,
        run_id="run_rc017",
        input_sha256="input-hash",
        run_status="FINISHED",
        run_outcome="COMPLETE",
    )
    current = read_current_catalog_generation(output)
    assert result["manifest_sha256"]
    assert current is not None
    assert current["manifest"]["generation_id"] == generation_id
    assert current["manifest"]["published"] is True
    assert (output / GENERATION_POINTER_NAME).exists()
    assert (output / "master_linkedin_jobs.csv").read_text(encoding="utf-8") == "id,title\n1,Engineer\n"


def test_abandoned_generation_is_manifested_without_moving_current_pointer(tmp_path: Path) -> None:
    output = tmp_path / "output"
    complete_dir = output / GENERATION_DIRECTORY_NAME / "generation_old"
    complete_dir.mkdir(parents=True)
    for name in GENERATION_ARTIFACT_NAMES:
        (complete_dir / name).write_text("complete\n", encoding="utf-8")
    publish_catalog_generation(
        output,
        generation_id="generation_old",
        run_id="run_old",
        input_sha256="old-input",
        run_status="FINISHED",
        run_outcome="COMPLETE",
    )
    before = json.loads((output / GENERATION_POINTER_NAME).read_text(encoding="utf-8"))

    abandoned_dir = output / GENERATION_DIRECTORY_NAME / "generation_abandoned"
    abandoned_dir.mkdir(parents=True)
    (abandoned_dir / "master_linkedin_jobs_metrics.json").write_text("{\"run_outcome\":\"FAILURE\"}\n", encoding="utf-8")
    manifest = write_catalog_generation_manifest(
        output,
        generation_id="generation_abandoned",
        run_id="run_abandoned",
        input_sha256="new-input",
        status="FAILED",
        run_outcome="FAILURE",
        published=False,
    )

    after = json.loads((output / GENERATION_POINTER_NAME).read_text(encoding="utf-8"))
    assert manifest["published"] is False
    assert after == before
    assert read_current_catalog_generation(output)["manifest"]["generation_id"] == "generation_old"
