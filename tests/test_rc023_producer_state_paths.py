from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

import scripts.run_manifested_employer as employer_wrapper
import scripts.run_manifested_linkedin as linkedin_wrapper
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
    assert table_count == 15


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
