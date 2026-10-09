from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

import scripts.run_manifested_employer as employer_wrapper
import scripts.run_manifested_linkedin as linkedin_wrapper
import scripts.publish_producer_states as publisher
from scripts.master_employer_jobs_catalog import (
    EmployerCollectionResult,
    EmployerCompany,
    export_only,
    run_collection,
)
from scripts.master_linkedin_jobs_catalog import (
    CatalogRunner,
    ResponseEnvelope,
    RunnerConfig,
    StateStore,
    read_current_catalog_generation,
)
from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore
from scripts.publish_producer_states import (
    _ensure_publisher_checkpoint_table,
)


FIXTURES = Path(__file__).parent / "fixtures"


def _write_linkedin_source(path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "canonical_CompanyID",
                "company_name",
                "linkedin_company_url",
                "linkedin_slug",
                "linkedin_company_id",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "canonical_CompanyID": "C-001",
                "company_name": "Acme",
                "linkedin_company_url": "https://www.linkedin.com/company/acme",
                "linkedin_slug": "acme",
                "linkedin_company_id": "22",
            }
        )


def _write_pagination_report(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "endpoint": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
                "page_step": 10,
                "full_card_count": 10,
                "max_start": 10,
            }
        ),
        encoding="utf-8",
    )


class _FixtureLinkedInTransport:
    def __init__(self) -> None:
        self.search_body = (FIXTURES / "linkedin_job_search_valid.html").read_text(encoding="utf-8")
        self.detail_body = (FIXTURES / "linkedin_job_detail.html").read_text(encoding="utf-8")
        self.urls: list[tuple[str, str]] = []

    def get(self, url: str, *, kind: str) -> ResponseEnvelope:
        self.urls.append((url, kind))
        if kind == "search":
            body = self.search_body if "start=0" in url else (FIXTURES / "linkedin_job_search_no_results.html").read_text(encoding="utf-8")
        else:
            body = self.detail_body
        return ResponseEnvelope(200, body, "fixture", 0.01)


class _InterruptingLinkedInTransport:
    def get(self, _url: str, *, kind: str) -> ResponseEnvelope:
        raise KeyboardInterrupt(f"fixture interruption during {kind}")


def _write_employer_source(path: Path) -> None:
    path.write_text(
        "canonical_CompanyID,company_name,website_url\n"
        "canonical-acme,Acme,https://acme.example\n",
        encoding="utf-8",
    )


def _employer_company() -> EmployerCompany:
    return EmployerCompany(
        canonical_company_id="canonical-acme",
        company_name="Acme",
        website_url="https://acme.example",
        linkedin_company_url="https://www.linkedin.com/company/acme",
        source_row_number=2,
    )


def _employer_result(company: EmployerCompany) -> EmployerCollectionResult:
    return EmployerCollectionResult(
        company=company,
        jobs=[
            {
                "canonical_company_id": company.canonical_company_id,
                "source_type": "employer_site",
                "source_provider": "fixture",
                "source_job_id": "fixture-job",
                "source_job_url": "https://acme.example/jobs/fixture-job",
                "job_title": "Fixture job",
                "extraction_method": "fixture",
            }
        ],
        status="completed",
    )


def test_linkedin_explicit_state_keeps_generation_journal_and_db_outside_exports(tmp_path: Path) -> None:
    source = tmp_path / "linkedin.csv"
    pagination = tmp_path / "pagination.json"
    output = tmp_path / "exports" / "linkedin"
    state_dir = tmp_path / "state" / "linkedin"
    _write_linkedin_source(source)
    _write_pagination_report(pagination)

    metrics = CatalogRunner(
        RunnerConfig(
            input_csv=source,
            output_dir=output,
            state_dir=state_dir,
            pagination_report=pagination,
            mode="smoke",
            max_companies=1,
        ),
        transport=_FixtureLinkedInTransport(),
    ).run()

    state_path = state_dir / "master_linkedin_jobs_state.db"
    assert metrics["run_outcome"] == "COMPLETE"
    assert state_path.is_file()
    assert not list(output.rglob("*.db*"))
    generation = read_current_catalog_generation(output)
    assert generation is not None
    generation_dir = output / "generations" / str(generation["manifest"]["generation_id"])
    assert (generation_dir / "master_linkedin_jobs.jsonl").read_text(encoding="utf-8").strip()
    assert (generation_dir / "manifest.json").is_file()
    with sqlite3.connect(state_path) as connection:
        table_count = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()[0]
        assert table_count == 16


def test_linkedin_default_state_path_remains_output_dir(tmp_path: Path) -> None:
    source = tmp_path / "linkedin.csv"
    pagination = tmp_path / "pagination.json"
    output = tmp_path / "exports" / "linkedin"
    _write_linkedin_source(source)
    _write_pagination_report(pagination)

    CatalogRunner(
        RunnerConfig(input_csv=source, output_dir=output, pagination_report=pagination, mode="smoke", max_companies=1),
        transport=_FixtureLinkedInTransport(),
    ).run()

    assert (output / "master_linkedin_jobs_state.db").is_file()


def test_linkedin_interrupted_generation_resumes_from_separate_state_and_publishes(tmp_path: Path) -> None:
    source = tmp_path / "linkedin.csv"
    pagination = tmp_path / "pagination.json"
    output = tmp_path / "exports" / "linkedin"
    state_dir = tmp_path / "state" / "linkedin"
    _write_linkedin_source(source)
    _write_pagination_report(pagination)
    first_config = RunnerConfig(
        input_csv=source,
        output_dir=output,
        state_dir=state_dir,
        pagination_report=pagination,
        mode="smoke",
        max_companies=1,
    )

    with pytest.raises(KeyboardInterrupt):
        CatalogRunner(first_config, transport=_InterruptingLinkedInTransport()).run()

    state = StateStore(state_dir / "master_linkedin_jobs_state.db")
    try:
        run_id = state.connection.execute("SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()[0]
    finally:
        state.close()
    interrupted_manifest = output / "generations" / f"generation_{run_id}" / "manifest.json"
    assert json.loads(interrupted_manifest.read_text(encoding="utf-8"))["published"] is False

    resumed = CatalogRunner(
        RunnerConfig(
            input_csv=source,
            output_dir=output,
            state_dir=state_dir,
            pagination_report=pagination,
            mode="smoke",
            max_companies=1,
            resume_run_id=run_id,
            require_existing_state=True,
        ),
        transport=_FixtureLinkedInTransport(),
    ).run()

    assert resumed["run_id"] == run_id
    published = read_current_catalog_generation(output)
    assert published is not None
    assert published["manifest"]["published"] is True
    assert (output / "generations" / f"generation_{run_id}" / "master_linkedin_jobs.jsonl").read_text(
        encoding="utf-8"
    ).strip()


def test_linkedin_required_state_missing_does_not_initialize_empty_db(tmp_path: Path) -> None:
    source = tmp_path / "linkedin.csv"
    pagination = tmp_path / "pagination.json"
    output = tmp_path / "exports" / "linkedin"
    state_dir = tmp_path / "restored-state" / "linkedin"
    _write_linkedin_source(source)
    _write_pagination_report(pagination)

    with pytest.raises(FileNotFoundError, match="LinkedIn state database not found"):
        CatalogRunner(
            RunnerConfig(
                input_csv=source,
                output_dir=output,
                state_dir=state_dir,
                pagination_report=pagination,
                mode="smoke",
                max_companies=1,
                require_existing_state=True,
            ),
            transport=_FixtureLinkedInTransport(),
        ).run()

    assert not state_dir.exists()


def test_employer_explicit_state_supports_resume_and_export_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    source = tmp_path / "employer.csv"
    output = tmp_path / "exports" / "employer"
    state_dir = tmp_path / "state" / "employer"
    _write_employer_source(source)
    monkeypatch.setattr(catalog, "requests_fetcher", lambda *_: lambda _url: None)
    monkeypatch.setattr(catalog, "collect_company", lambda company, *_args, **_kwargs: _employer_result(company))

    first = run_collection(
        input_csv=source,
        output_dir=output,
        state_dir=state_dir,
        limit=1,
        resume=False,
        company_concurrency=1,
    )
    assert first["final_export_completed"] is True
    assert (state_dir / "master_employer_jobs_state.db").is_file()
    assert not list(output.rglob("*.db*"))
    assert (output / "master_employer_jobs.csv").is_file()

    resumed = run_collection(
        input_csv=source,
        output_dir=output,
        state_dir=state_dir,
        limit=1,
        resume=True,
        company_concurrency=1,
    )
    assert resumed["companies_skipped_resume"] == 1
    exported = export_only(output, state_dir=state_dir)
    assert exported["final_export_completed"] is True
    with (output / "master_employer_jobs.csv").open(encoding="utf-8-sig", newline="") as handle:
        assert [row["source_job_id"] for row in csv.DictReader(handle)] == ["fixture-job"]


def test_employer_default_state_path_remains_output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.master_employer_jobs_catalog as catalog

    source = tmp_path / "employer.csv"
    output = tmp_path / "exports" / "employer"
    _write_employer_source(source)
    monkeypatch.setattr(catalog, "requests_fetcher", lambda *_: lambda _url: None)
    monkeypatch.setattr(catalog, "collect_company", lambda company, *_args, **_kwargs: _employer_result(company))

    run_collection(input_csv=source, output_dir=output, limit=1, resume=False, company_concurrency=1)

    assert (output / "master_employer_jobs_state.db").is_file()


def test_employer_required_state_missing_does_not_initialize_empty_db(tmp_path: Path) -> None:
    source = tmp_path / "employer.csv"
    output = tmp_path / "exports" / "employer"
    state_dir = tmp_path / "restored-state" / "employer"
    _write_employer_source(source)

    with pytest.raises(FileNotFoundError, match="Employer state database not found"):
        run_collection(
            input_csv=source,
            output_dir=output,
            state_dir=state_dir,
            limit=1,
            require_existing_state=True,
        )

    assert not state_dir.exists()
    with pytest.raises(FileNotFoundError, match="Employer state database not found"):
        export_only(output, state_dir=state_dir)


def test_manifested_linkedin_wrapper_emits_bounded_telemetry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = {"manifest_id": "fixture-manifest", "manifest_hash": "fixture-hash"}
    monkeypatch.setattr(
        linkedin_wrapper,
        "require_eligibility_manifest",
        lambda *args, **kwargs: (manifest, [{"task_key": "fixture"}]),
    )
    monkeypatch.setattr(linkedin_wrapper, "materialize_source_input", lambda *args, **kwargs: {"rows": 1})

    class FakeRunner:
        def __init__(self, config: RunnerConfig, *, transport: object) -> None:
            pass

        def run(self) -> dict[str, object]:
            return {"run_outcome": "COMPLETE", "requests_made": 3}

    monkeypatch.setattr(linkedin_wrapper, "CatalogRunner", FakeRunner)
    assert linkedin_wrapper.main(
        [
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--output-dir",
            str(tmp_path / "exports" / "linkedin"),
            "--state-dir",
            str(tmp_path / "state" / "linkedin"),
            "--require-existing-state",
            "--mode",
            "validate",
            "--dry-run",
        ]
    ) == 0
    metrics = json.loads(capsys.readouterr().out)
    telemetry = metrics["telemetry"]
    assert set(telemetry) == set(linkedin_wrapper.TELEMETRY_KEYS)
    assert telemetry["schema_version"] == linkedin_wrapper.TELEMETRY_SCHEMA_VERSION
    assert telemetry["source"] == linkedin_wrapper.SOURCE_LINKEDIN
    assert telemetry["reason_code"] == "ok"
    assert telemetry["emitted_at"].endswith("Z")
    assert set(telemetry["resource_peaks"]) == set(linkedin_wrapper.RESOURCE_PEAK_KEYS)
    for word in ("secret", "password", "token", "api_key"):
        assert word not in json.dumps(telemetry).casefold()


def test_manifested_employer_wrapper_emits_bounded_telemetry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = {"manifest_id": "fixture-manifest", "manifest_hash": "fixture-hash"}
    monkeypatch.setattr(
        employer_wrapper,
        "require_eligibility_manifest",
        lambda *args, **kwargs: (manifest, [{"task_key": "fixture"}]),
    )
    monkeypatch.setattr(employer_wrapper, "materialize_source_input", lambda *args, **kwargs: {"rows": 1})

    def fake_collection(**kwargs: object) -> dict[str, object]:
        return {"run_outcome": "COMPLETE", "requests_made": 1}

    monkeypatch.setattr(employer_wrapper, "run_collection", fake_collection)
    assert employer_wrapper.main(
        [
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--output-dir",
            str(tmp_path / "exports" / "employer"),
            "--state-dir",
            str(tmp_path / "state" / "employer"),
            "--require-existing-state",
            "--dry-run",
        ]
    ) == 0
    metrics = json.loads(capsys.readouterr().out)
    telemetry = metrics["telemetry"]
    assert set(telemetry) == set(employer_wrapper.TELEMETRY_KEYS)
    assert telemetry["schema_version"] == employer_wrapper.TELEMETRY_SCHEMA_VERSION
    assert telemetry["source"] == employer_wrapper.SOURCE_EMPLOYER
    assert telemetry["reason_code"] == "ok"


def test_publisher_telemetry_reports_checkpoint_lag_and_staleness() -> None:
    now = "2026-09-19T12:00:00Z"
    checkpoints = {
        "linkedin": {
            "updated_at": "2026-09-19T11:00:00Z",
            "bootstrap_complete": True,
            "last_cycle_id": "cycle-1",
            "last_publication_id": "publication-1",
        },
        "employer": {
            "updated_at": "",
            "bootstrap_complete": False,
            "last_cycle_id": "",
            "last_publication_id": "",
        },
    }
    telemetry = publisher._publisher_telemetry(checkpoints, now)
    assert telemetry["schema_version"] == publisher.TELEMETRY_SCHEMA_VERSION
    assert telemetry["stale_checkpoint_seconds"] == publisher.DEFAULT_STALE_CHECKPOINT_SECONDS
    assert set(telemetry["sources"]["linkedin"]) == set(publisher.TELEMETRY_SOURCE_KEYS)
    assert telemetry["sources"]["linkedin"]["checkpoint_age_seconds"] == 3600.0
    assert telemetry["sources"]["linkedin"]["stale_checkpoint"] is False
    assert telemetry["sources"]["linkedin"]["publish_lag_seconds"] == 3600.0
    assert telemetry["sources"]["employer"]["stale_checkpoint"] is True
    assert telemetry["sources"]["employer"]["checkpoint_age_seconds"] is None
    assert telemetry["sources"]["employer"]["publish_lag_seconds"] is None
    assert set(telemetry["resource_peaks"]) == {"max_rss_bytes", "cpu_seconds"}
    for word in ("secret", "password", "token", "api_key"):
        assert word not in json.dumps(telemetry).casefold()


def test_publisher_telemetry_staleness_threshold_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = "2026-09-19T12:00:00Z"
    checkpoints = {
        "linkedin": {
            "updated_at": "2026-09-19T11:00:00Z",
            "bootstrap_complete": True,
            "last_cycle_id": "",
            "last_publication_id": "",
        }
    }
    monkeypatch.setenv("RUNR_TELEMETRY_STALE_CHECKPOINT_SECONDS", "60")
    assert publisher._publisher_telemetry(checkpoints, now)["sources"]["linkedin"]["stale_checkpoint"] is True
    monkeypatch.setenv("RUNR_TELEMETRY_STALE_CHECKPOINT_SECONDS", "7200")
    assert publisher._publisher_telemetry(checkpoints, now)["sources"]["linkedin"]["stale_checkpoint"] is False
    monkeypatch.setenv("RUNR_TELEMETRY_STALE_CHECKPOINT_SECONDS", "not-a-number")
    assert publisher._publisher_telemetry(checkpoints, now)["stale_checkpoint_seconds"] == publisher.DEFAULT_STALE_CHECKPOINT_SECONDS
    monkeypatch.setenv("RUNR_TELEMETRY_STALE_CHECKPOINT_SECONDS", "0")
    assert publisher._publisher_telemetry(checkpoints, now)["stale_checkpoint_seconds"] == publisher.DEFAULT_STALE_CHECKPOINT_SECONDS


def _bash_launcher() -> str | None:
    bash = shutil.which("bash")
    if bash is None:
        return None
    probe = subprocess.run([bash, "-c", "echo ok"], capture_output=True, text=True, timeout=60)
    if probe.returncode != 0:
        return None
    return bash


def _wsl_path(path: Path) -> str:
    posix = path.resolve().as_posix()
    if ":" not in posix:
        # Already a POSIX path (Linux/CI): use it verbatim.
        return posix
    drive, rest = posix.split(":", 1)
    return f"/mnt/{drive.casefold()}{rest}"


def _run_bash_script(bash: str, script: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    script_path = tmp_path / "harness.sh"
    script_path.write_text(script, encoding="utf-8", newline="\n")
    return subprocess.run(
        [bash, _wsl_path(script_path)],
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_source_wrapper_receipt_and_telemetry_survive_failure(
    tmp_path: Path,
) -> None:
    bash = _bash_launcher()
    if bash is None:
        pytest.skip("no usable POSIX shell harness")
    worktree = _wsl_path(Path(__file__).resolve().parents[1])
    script = "\n".join(
        [
            "set -u",
            f"wt={worktree}",
            "root=$(mktemp -d /tmp/t39-XXXXXX)",
            "export RUNR_PYTHON_BIN=/bin/false",
            "export RUNR_ACQUISITION_STATE_ROOT=$root/state",
            "export RUNR_ACQUISITION_EXPORT_ROOT=$root/exports",
            "export RUNR_ACQUISITION_LOCK_ROOT=$root/locks",
            'mkdir -p "$RUNR_ACQUISITION_STATE_ROOT" "$RUNR_ACQUISITION_EXPORT_ROOT"',
            'sh -n "$wt/deploy/run-acquisition-source.sh" || { echo SYNTAX_FAIL; exit 9; }',
            'sh -n "$wt/deploy/run-acquisition-publisher.sh" || { echo SYNTAX_FAIL; exit 9; }',
            'rc=0',
            'sh "$wt/deploy/run-acquisition-source.sh" linkedin > "$root/stdout.txt" 2>&1 || rc=$?',
            'telemetry=$(cat "$RUNR_ACQUISITION_EXPORT_ROOT/receipts/linkedin-latest-telemetry.json" 2>/dev/null || echo MISSING)',
            "metrics_file=$RUNR_ACQUISITION_EXPORT_ROOT/receipts/linkedin-latest-metrics.json",
            "metrics_survived=no",
            'if [ -f "$metrics_file" ]; then metrics_survived=yes; fi',
            'printf "RC=%s\\nTELEMETRY=%s\\nMETRICS_SURVIVED=%s\\n" "$rc" "$telemetry" "$metrics_survived"',
            'rm -rf "$root"',
        ]
    )
    result = _run_bash_script(bash, script, tmp_path)
    out = result.stdout
    assert "SYNTAX_FAIL" not in out
    assert "RC=1" in out
    assert '"reason_code":"validation_failed"' in out
    assert '"exit_code":1' in out
    assert "METRICS_SURVIVED=yes" in out


def test_source_wrapper_reports_lock_overlap_telemetry(
    tmp_path: Path,
) -> None:
    bash = _bash_launcher()
    if bash is None:
        pytest.skip("no usable POSIX shell harness")
    worktree = _wsl_path(Path(__file__).resolve().parents[1])
    script = "\n".join(
        [
            "set -u",
            f"wt={worktree}",
            "root=$(mktemp -d /tmp/t39-lock-XXXXXX)",
            "export RUNR_ACQUISITION_STATE_ROOT=$root/state",
            "export RUNR_ACQUISITION_EXPORT_ROOT=$root/exports",
            "export RUNR_ACQUISITION_LOCK_ROOT=$root/locks",
            'mkdir -p "$RUNR_ACQUISITION_STATE_ROOT" "$RUNR_ACQUISITION_EXPORT_ROOT" "$RUNR_ACQUISITION_LOCK_ROOT"',
            '( exec 9>"$RUNR_ACQUISITION_LOCK_ROOT/linkedin.lock"; flock -x 9; sleep 5 ) &',
            "holder=$!",
            "sleep 2",
            "exec 9>\"$RUNR_ACQUISITION_LOCK_ROOT/linkedin.lock\"",
            'flock -n 9 && { echo LOCK_HARNESS_UNRELIABLE; exit 8; }',
            "rc=0",
            'sh "$wt/deploy/run-acquisition-source.sh" linkedin > "$root/stdout.txt" 2>&1 || rc=$?',
            'kill "$holder" 2>/dev/null || true',
            'wait "$holder" 2>/dev/null || true',
            'telemetry=$(cat "$RUNR_ACQUISITION_EXPORT_ROOT/receipts/linkedin-latest-telemetry.json" 2>/dev/null || echo MISSING)',
            'printf "RC=%s\\nTELEMETRY=%s\\n" "$rc" "$telemetry"',
            'rm -rf "$root"',
        ]
    )
    result = _run_bash_script(bash, script, tmp_path)
    out = result.stdout
    assert "RC=75" in out
    assert '"reason_code":"lock_overlap"' in out
    assert '"exit_code":75' in out

def test_manifested_wrappers_forward_separate_state_and_restore_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = {"manifest_id": "fixture-manifest", "manifest_hash": "fixture-hash"}
    linkedin_capture: dict[str, object] = {}
    employer_capture: dict[str, object] = {}

    monkeypatch.setattr(
        linkedin_wrapper,
        "require_eligibility_manifest",
        lambda *args, **kwargs: (manifest, [{"task_key": "fixture"}]),
    )
    monkeypatch.setattr(linkedin_wrapper, "materialize_source_input", lambda *args, **kwargs: {"rows": 1})

    class FakeRunner:
        def __init__(self, config: RunnerConfig, *, transport: object) -> None:
            linkedin_capture["config"] = config
            linkedin_capture["transport"] = transport

        def run(self) -> dict[str, object]:
            return {"run_outcome": "DRY_RUN"}

    monkeypatch.setattr(linkedin_wrapper, "CatalogRunner", FakeRunner)
    assert linkedin_wrapper.main(
        [
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--output-dir",
            str(tmp_path / "exports" / "linkedin"),
            "--state-dir",
            str(tmp_path / "state" / "linkedin"),
            "--require-existing-state",
            "--mode",
            "validate",
            "--dry-run",
        ]
    ) == 0
    linkedin_config = linkedin_capture["config"]
    assert isinstance(linkedin_config, RunnerConfig)
    assert linkedin_config.state_dir == (tmp_path / "state" / "linkedin").resolve()
    assert linkedin_config.require_existing_state is True

    monkeypatch.setattr(
        employer_wrapper,
        "require_eligibility_manifest",
        lambda *args, **kwargs: (manifest, [{"task_key": "fixture"}]),
    )
    monkeypatch.setattr(employer_wrapper, "materialize_source_input", lambda *args, **kwargs: {"rows": 1})

    def fake_collection(**kwargs: object) -> dict[str, object]:
        employer_capture.update(kwargs)
        return {"run_outcome": "DRY_RUN"}

    monkeypatch.setattr(employer_wrapper, "run_collection", fake_collection)
    assert employer_wrapper.main(
        [
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--output-dir",
            str(tmp_path / "exports" / "employer"),
            "--state-dir",
            str(tmp_path / "state" / "employer"),
            "--require-existing-state",
            "--dry-run",
        ]
    ) == 0
    assert employer_capture["state_dir"] == (tmp_path / "state" / "employer").resolve()
    assert employer_capture["require_existing_state"] is True


def test_manifest_runtime_commands_use_posix_state_and_export_mounts() -> None:
    manifest = json.loads((Path(__file__).parents[1] / "deploy" / "acquisition-data-manifest.json").read_text())
    commands = {item["path"]: item["runtime_command"] for item in manifest["scripts"]}

    assert "--state-dir /srv/runr/state/linkedin --require-existing-state" in commands["scripts/master_linkedin_jobs_catalog.py"]
    assert "--state-dir /srv/runr/state/employer --require-existing-state" in commands["scripts/master_employer_jobs_catalog.py"]
    assert "--state-dir /srv/runr/state/linkedin --require-existing-state" in commands["scripts/run_manifested_linkedin.py"]
    assert "--state-dir /srv/runr/state/employer --require-existing-state" in commands["scripts/run_manifested_employer.py"]


def test_registry_owns_publisher_checkpoint_table_with_expected_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "catalog.db"
    store = SqliteAcquisitionStore(db_path)
    _ensure_publisher_checkpoint_table(store)

    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(acquisition_publisher_checkpoints)"
            ).fetchall()
        }
    assert columns == {
        "source",
        "source_rowid",
        "source_watermark",
        "bootstrap_complete",
        "last_cycle_id",
        "last_publication_id",
        "updated_at",
    }

    checkpoint = store.publisher_checkpoint("linkedin")
    assert checkpoint["source"] == "linkedin"
    assert checkpoint["source_rowid"] == 0
    assert checkpoint["bootstrap_complete"] is False


def test_restore_script_rollback_switches_active_to_previous_release(tmp_path: Path) -> None:
    bash = _bash_launcher()
    if bash is None:
        pytest.skip("no usable POSIX shell harness")
    worktree = _wsl_path(Path(__file__).resolve().parents[1])
    script = "\n".join(
        [
            "set -u",
            f"wt={worktree}",
            "root=$(mktemp -d /tmp/t45-rollback-XXXXXX)",
            'mkdir -p "$root/state/versions/gen-1" "$root/state/versions/gen-2" "$root/state/locks"',
            'ln -s "$root/state/versions/gen-2" "$root/state/active"',
            "export RUNR_ACQUISITION_STATE_ROOT_PHYSICAL=$root/state",
            "export RUNR_ACQUISITION_LOCK_ROOT=$root/state/locks",
            'sh -n "$wt/deploy/restore-acquisition-states.sh" || { echo SYNTAX_FAIL; exit 9; }',
            "rc=0",
            'sh "$wt/deploy/restore-acquisition-states.sh" rollback > "$root/stdout.txt" 2>&1 || rc=$?',
            "target=$(readlink \"$root/state/active\" 2>/dev/null || echo MISSING)",
            'printf "RC=%s\\nTARGET=%s\\n" "$rc" "$target"',
            "cat \"$root/stdout.txt\"",
            'rm -rf "$root"',
        ]
    )
    result = _run_bash_script(bash, script, tmp_path)
    out = result.stdout
    assert "SYNTAX_FAIL" not in out
    assert "RC=0" in out
    assert "rollback_from=" in out
    assert "TARGET=" in out and out.split("TARGET=")[1].splitlines()[0].endswith("gen-1")
    assert "rollback_to=" in out and "gen-1" in out.split("rollback_to=")[1].splitlines()[0]


def test_restore_script_rollback_fails_without_previous_release(tmp_path: Path) -> None:
    bash = _bash_launcher()
    if bash is None:
        pytest.skip("no usable POSIX shell harness")
    worktree = _wsl_path(Path(__file__).resolve().parents[1])
    script = "\n".join(
        [
            "set -u",
            f"wt={worktree}",
            "root=$(mktemp -d /tmp/t45-rollback-only-XXXXXX)",
            'mkdir -p "$root/state/versions/gen-1" "$root/state/locks"',
            'ln -s "$root/state/versions/gen-1" "$root/state/active"',
            "export RUNR_ACQUISITION_STATE_ROOT_PHYSICAL=$root/state",
            "export RUNR_ACQUISITION_LOCK_ROOT=$root/state/locks",
            "rc=0",
            'sh "$wt/deploy/restore-acquisition-states.sh" rollback > "$root/stdout.txt" 2>&1 || rc=$?',
            "target=$(readlink \"$root/state/active\" 2>/dev/null || echo MISSING)",
            'printf "RC=%s\\nTARGET=%s\\n" "$rc" "$target"',
            "cat \"$root/stdout.txt\"",
            'rm -rf "$root"',
        ]
    )
    result = _run_bash_script(bash, script, tmp_path)
    out = result.stdout
    assert "RC=1" in out
    assert out.split("TARGET=")[1].splitlines()[0].endswith("gen-1")
    assert "No previous state release is available for rollback" in out
