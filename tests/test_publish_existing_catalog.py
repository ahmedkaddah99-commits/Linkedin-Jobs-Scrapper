from pathlib import Path

from backend.bootstrap import create_backend
from backend.acquisition.publication import RestorePublicationConfirmation
from scripts.publish_existing_catalog import build_parser


def _target() -> dict[str, object]:
    return {
        "target_id": "existing-catalog-source",
        "target_kind": "employer_career_site",
        "display_name": "Existing Catalog Source",
        "canonical_target_url": "https://jobs.example",
        "provenance_url": "https://jobs.example",
        "request_url": "https://jobs.example/jobs",
        "official_employer_hosts": ["jobs.example"],
        "connector": "fixture",
        "source_token": "existing-catalog-source",
        "enabled": True,
        "publication_enabled": True,
        "config": {"absence_grace_attempts": 1},
    }


def test_publish_existing_catalog_defaults_to_display_first_policy() -> None:
    args = build_parser().parse_args([])

    assert args.policy_version == "publication_policy_v1"


def test_publish_existing_catalog_parser_exposes_bounded_dry_run_and_rollback_controls() -> None:
    args = build_parser().parse_args(
        ["--dry-run", "--batch-size", "1", "--rollback-publication", "acq_republish_previous"]
    )

    assert args.dry_run is True
    assert args.batch_size == 1
    assert args.rollback_publication == "acq_republish_previous"


def test_publish_existing_catalog_rechecks_blocking_completeness(tmp_path: Path) -> None:
    app = create_backend(tmp_path, storage_backend="sqlite")
    store = app.repositories.acquisition_store
    target = _target()
    store.ensure_targets([target])
    cycle = store.claim_due_cycle(
        window_key="existing-catalog-cycle",
        lease_owner="test",
        scheduled_at="2026-09-12T00:00:00Z",
    )
    assert cycle is not None
    store.ensure_cycle_tasks(str(cycle["cycle_id"]), [target])
    task = store.claim_next_task(cycle_id=str(cycle["cycle_id"]), lease_owner="test")
    assert task is not None
    store.ingest_snapshot(
        cycle_id=str(cycle["cycle_id"]),
        task_id=str(task["task_id"]),
        target_id=str(target["target_id"]),
        jobs=[
            {
                "job_id": "publishable",
                "title": "Publishable Engineer",
                "location": "Berlin",
                "url": "https://jobs.example/publishable",
                "application_url": "https://jobs.example/publishable/apply",
                "description": "This is a complete job description with enough detail for publication and a clear explanation of the role responsibilities.",
                "seniority": "mid",
                "employment_type": "full_time",
                "workplace_arrangement": "hybrid",
                "company_logo": "https://jobs.example/logo.png",
                "company_enrichment": "verified",
                "source_ats": "fixture",
            },
            {
                "job_id": "incomplete",
                "title": "Incomplete Engineer",
                "location": "Berlin",
                "url": "https://jobs.example/incomplete",
                "application_url": "https://jobs.example/incomplete/apply",
                "description": "",
                "seniority": "mid",
                "employment_type": "full_time",
                "workplace_arrangement": "hybrid",
                "company_logo": "https://jobs.example/logo.png",
                "company_enrichment": "verified",
                "source_ats": "fixture",
            },
        ],
        complete_snapshot=True,
        valid_snapshot=True,
    )

    publication_id = store.publish_existing_catalog_snapshot(
        created_by="test",
        policy_version="publication_policy_v2",
    )

    assert publication_id
    assert store.get_public_catalog()["total"] == 1


def test_publication_head_can_roll_back_to_the_previous_catalog(tmp_path: Path) -> None:
    app = create_backend(tmp_path, storage_backend="sqlite")
    store = app.repositories.acquisition_store
    target = _target()
    store.ensure_targets([target])
    cycle = store.claim_due_cycle(
        window_key="rollback-cycle",
        lease_owner="test",
        scheduled_at="2026-09-12T00:00:00Z",
    )
    assert cycle is not None
    store.ensure_cycle_tasks(str(cycle["cycle_id"]), [target])
    task = store.claim_next_task(cycle_id=str(cycle["cycle_id"]), lease_owner="test")
    assert task is not None
    store.ingest_snapshot(
        cycle_id=str(cycle["cycle_id"]),
        task_id=str(task["task_id"]),
        target_id=str(target["target_id"]),
        jobs=[
            {
                "job_id": "rollback-job",
                "title": "Rollback Engineer",
                "location": "Berlin",
                "url": "https://jobs.example/rollback",
                "application_url": "https://jobs.example/rollback/apply",
                "description": "This is a complete job description with enough detail for publication and a clear explanation of the role responsibilities.",
                "source_ats": "fixture",
            }
        ],
        complete_snapshot=True,
        valid_snapshot=True,
    )

    first = store.publish_existing_catalog_snapshot(created_by="test", policy_version="publication_policy_v1")
    second = store.publish_existing_catalog_snapshot(created_by="test", policy_version="publication_policy_v1")

    assert first != second
    restored = store.restore_publication(
        RestorePublicationConfirmation.from_values(
            target_publication_id=first,
            expected_head_publication_id=second,
            actor_user_id="test",
            confirmation="restore_publication",
        )
    )
    assert restored != first
    with store._connect() as connection:
        head = connection.execute(
            "SELECT publication_id FROM acquisition_publication_head WHERE head_id=1"
        ).fetchone()
        restored_publication = connection.execute(
            "SELECT previous_publication_id, origin FROM acquisition_publications WHERE publication_id=?",
            (restored,),
        ).fetchone()
    assert str(head["publication_id"]) == restored
    assert str(restored_publication["previous_publication_id"]) == second
    assert str(restored_publication["origin"]) == "restored"
