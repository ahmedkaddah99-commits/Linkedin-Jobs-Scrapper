"""Tests for bounded-cycle advancement and recheck-budget filling.

These pin the employer collector defects from the stopped B handoff: a small
``limit`` must advance across the full input on repeated resumed cycles, and a
run must keep filling its slice with fresh rows after the recheck budget is
exhausted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.master_employer_jobs_catalog import (
    EmployerCollectionResult,
    EmployerCompany,
    EmployerState,
    run_collection,
)


def _company(identifier: str) -> EmployerCompany:
    return EmployerCompany(
        canonical_company_id=identifier,
        company_name=identifier,
        website_url=f"https://{identifier}.example",
    )


def _source(path: Path, *identifiers: str) -> None:
    path.write_text(
        "canonical_CompanyID,company_name,website_url\n"
        + "".join(f"{identifier},{identifier},https://{identifier}.example\n" for identifier in identifiers),
        encoding="utf-8",
    )


def test_bounded_cycles_advance_across_the_full_input(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "companies.csv"
    _source(source, "first", "second", "third")
    output_dir = tmp_path / "out"
    collected: list[str] = []

    def fake_collect(company, _fetcher, _limits):
        collected.append(company.canonical_company_id)
        return EmployerCollectionResult(company=company, status="completed", outcome="complete_with_jobs")

    monkeypatch.setattr("scripts.master_employer_jobs_catalog.requests_fetcher", lambda *_: lambda _url: None)
    monkeypatch.setattr("scripts.master_employer_jobs_catalog.collect_company", fake_collect)

    for _ in range(3):
        run_collection(input_csv=source, output_dir=output_dir, limit=1, resume=True, recheck_budget=0)

    assert collected == ["first", "second", "third"]


def test_recheck_budget_exhaustion_fills_slice_with_fresh_rows(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "companies.csv"
    _source(source, "done", "uncertain", "fresh")
    output_dir = tmp_path / "out"

    state = EmployerState(output_dir / "master_employer_jobs_state.db")
    try:
        state.save(EmployerCollectionResult(company=_company("done"), status="completed", outcome="complete_with_jobs"))
        state.save(EmployerCollectionResult(company=_company("uncertain"), status="partial", outcome="partial"))
    finally:
        state.close()

    collected: list[str] = []

    def fake_collect(company, _fetcher, _limits):
        collected.append(company.canonical_company_id)
        return EmployerCollectionResult(company=company, status="completed", outcome="complete_with_jobs")

    monkeypatch.setattr("scripts.master_employer_jobs_catalog.requests_fetcher", lambda *_: lambda _url: None)
    monkeypatch.setattr("scripts.master_employer_jobs_catalog.collect_company", fake_collect)

    metrics = run_collection(input_csv=source, output_dir=output_dir, limit=1, resume=True, recheck_budget=0)

    assert collected == ["fresh"]
    assert metrics["companies_skipped_resume"] == 1
    assert metrics["rechecks_skipped_budget"] == 1
    assert metrics["selected_companies"] == 1


def test_exact_cohort_is_not_expanded_by_cursor(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "companies.csv"
    _source(source, "alpha", "beta", "gamma")
    output_dir = tmp_path / "out"
    collected: list[str] = []

    def fake_collect(company, _fetcher, _limits):
        collected.append(company.canonical_company_id)
        return EmployerCollectionResult(company=company, status="completed", outcome="complete_with_jobs")

    monkeypatch.setattr("scripts.master_employer_jobs_catalog.requests_fetcher", lambda *_: lambda _url: None)
    monkeypatch.setattr("scripts.master_employer_jobs_catalog.collect_company", fake_collect)

    run_collection(input_csv=source, output_dir=output_dir, limit=1, resume=True, company_id="beta")

    assert collected == ["beta"]
