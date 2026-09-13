from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def test_render_images_create_the_interpreter_used_by_the_launcher():
    for name in ("Dockerfile.api", "Dockerfile.worker"):
        text = (SOURCE_ROOT / name).read_text(encoding="utf-8")
        assert "python -m venv /app/.venv" in text
        assert "/app/.venv/bin/python -m pip install" in text


def test_source_wrapper_has_a_finite_process_watchdog():
    text = (SOURCE_ROOT / "deploy/run-acquisition-source.sh").read_text(encoding="utf-8")
    assert 'run_timeout="${RUNR_SOURCE_RUN_TIMEOUT_SECONDS:-900}"' in text
    assert 'timeout --foreground "$run_timeout" "$python_bin"' in text


def test_linkedin_selection_is_a_due_bounded_window():
    from scripts.master_linkedin_jobs_catalog import select_due_company_window

    selected, next_cursor, examined = select_due_company_window(
        ["1", "2", "3", "4"],
        cursor=2,
        limit=2,
        due_ids={"2", "4"},
    )
    assert selected == ["4", "2"]
    assert next_cursor == 2
    assert examined == 4


def test_employer_selection_is_bounded_and_skips_future_checkpoints():
    from scripts.master_employer_jobs_catalog import select_due_company_window

    selected, next_cursor, examined = select_due_company_window(
        ["a", "b", "c", "d"],
        cursor=1,
        limit=2,
        due_ids={"b", "d"},
    )
    assert selected == ["b", "d"]
    assert next_cursor == 0
    assert examined == 3


def test_publisher_reads_incremental_source_rows_in_bounded_chunks(tmp_path):
    import sqlite3

    from scripts.publish_producer_states import read_incremental_rows

    path = tmp_path / "source.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE jobs (source_key TEXT PRIMARY KEY, payload_json TEXT NOT NULL)")
    connection.executemany(
        "INSERT INTO jobs(source_key, payload_json) VALUES (?, ?)",
        [(f"job-{index}", "{}") for index in range(3)],
    )
    connection.commit()
    rows, marker, complete = read_incremental_rows(
        connection,
        source="employer",
        rowid=0,
        limit=2,
    )
    connection.close()
    assert len(rows) == 2
    assert marker == 2
    assert complete is False


def test_publisher_target_uses_display_first_policy():
    from scripts.publish_producer_states import _target

    target = _target(
        {"canonical_company_id": "co-1", "canonical_company_name": "Example"},
        "linkedin",
    )
    assert target["policy_version"] == "publication_policy_v1"


def test_publisher_resolves_linkedin_rows_through_identity_crosswalk():
    import json

    from scripts.publish_producer_states import _source_group_from_rows

    grouped, _ = _source_group_from_rows(
        [
            {
                "linkedin_company_id": "1262",
                "linkedin_job_id": "job-1",
                "row_json": json.dumps(
                    {
                        "canonical_company_id": "canonical_company_legacy",
                        "linkedin_company_id": "1262",
                        "source_company_url": "https://www.linkedin.com/company/deutsche-bank",
                    }
                ),
            }
        ],
        source="linkedin",
        canonical_by_source_company={},
        selected_ids={"canonical_company_resolved"},
        crosswalk={
            "linkedin-org-url:https://www.linkedin.com/company/deutsche-bank": "canonical_company_resolved"
        },
    )
    assert list(grouped) == ["canonical_company_resolved"]


def test_publisher_bootstrap_keeps_latest_linkedin_run_live(tmp_path):
    import json
    import sqlite3

    from scripts.publish_producer_states import _load_incremental_source

    path = tmp_path / "linkedin.db"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE company_scans (run_id TEXT, finished_at TEXT, status TEXT, linkedin_company_id TEXT)"
    )
    connection.execute(
        "CREATE TABLE job_company_observations (linkedin_company_id TEXT, linkedin_job_id TEXT, run_id TEXT, company_scan_id TEXT, row_json TEXT)"
    )
    connection.execute(
        "INSERT INTO company_scans VALUES (?, ?, ?, ?)",
        ("latest-run", "2026-09-12T20:00:00Z", "COMPLETE", "1262"),
    )
    connection.execute(
        "INSERT INTO job_company_observations VALUES (?, ?, ?, ?, ?)",
        (
            "1262",
            "job-1",
            "latest-run",
            "scan-1",
            json.dumps(
                {
                    "canonical_company_id": "canonical_company_legacy",
                    "linkedin_company_id": "1262",
                    "source_company_url": "https://www.linkedin.com/company/deutsche-bank",
                    "job_title": "Backend Engineer",
                }
            ),
        ),
    )
    connection.commit()
    grouped, changed, checkpoint, source_changed = _load_incremental_source(
        connection,
        source="linkedin",
        checkpoint={"source_rowid": 0, "bootstrap_complete": False, "source_watermark": ""},
        canonical_by_source_company={},
        selected_ids={"canonical_company_resolved"},
        crosswalk={
            "linkedin-org-url:https://www.linkedin.com/company/deutsche-bank": "canonical_company_resolved"
        },
        batch_size=1,
        now="2026-09-12T20:01:00Z",
    )
    connection.close()
    assert list(grouped) == ["canonical_company_resolved"]
    assert changed == {"canonical_company_resolved"}
    assert checkpoint["bootstrap_complete"] is False
    assert source_changed is True


def test_display_first_policy_allows_missing_apply_destination():
    from backend.acquisition.job_publication_completeness import validate_job_for_publication

    result = validate_job_for_publication(
        {
            "canonical_job_id": "job-1",
            "canonical_company_id": "co-1",
            "source_job_id": "source-1",
            "company_name": "Example GmbH",
            "title": "Backend Engineer",
            "description": "Build resilient backend services with a collaborative engineering team and clear ownership across the product.",
            "location": "Berlin, Germany",
            "source": "linkedin",
            "observed_at": "2026-09-12T00:00:00Z",
            "lifecycle_state": "active",
        },
        company_registry={"co-1"},
        require_application_destination=False,
    )
    assert result.publishable


def test_display_first_policy_still_rejects_linkedin_easy_apply():
    from backend.acquisition.job_publication_completeness import validate_job_for_publication

    result = validate_job_for_publication(
        {
            "canonical_job_id": "job-1",
            "canonical_company_id": "co-1",
            "source_job_id": "source-1",
            "company_name": "Example GmbH",
            "title": "Backend Engineer",
            "description": "Build resilient backend services with a collaborative engineering team and clear ownership across the product.",
            "location": "Berlin, Germany",
            "source": "linkedin",
            "easy_apply_status": "true",
            "observed_at": "2026-09-12T00:00:00Z",
            "lifecycle_state": "active",
        },
        company_registry={"co-1"},
        require_application_destination=False,
    )
    assert not result.publishable
    assert "easy_apply_not_supported" in result.reason_codes


def test_jobs_workspace_keeps_pagination_explicit_and_capability_aware():
    text = (SOURCE_ROOT / "frontend/src/components/personalized/JobsWorkspace.jsx").read_text(encoding="utf-8")
    assert "IntersectionObserver" not in text
    assert "function FilterDrawer({ capabilities = {}, filters" in text
