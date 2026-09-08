from __future__ import annotations

import csv
import json
import threading
import time
from pathlib import Path

import pytest
from scripts import master_linkedin_jobs_catalog as catalog_module

from scripts.master_linkedin_jobs_catalog import (
    COMPANY_MATCH_CARD_DETAIL_MISMATCH,
    COMPANY_MATCH_AMBIGUOUS,
    COMPANY_MATCH_EXACT_PRIMARY,
    COMPANY_MATCH_VERIFIED_ALIAS,
    LOCATION_AMBIGUOUS,
    LOCATION_GERMANY_CONFIRMED,
    LOCATION_MULTI_LOCATION_INCLUDES_GERMANY,
    LOCATION_NOT_GERMANY,
    LOCATION_REMOTE_GERMANY_ELIGIBLE,
    CATALOG_FIELDS,
    StateStore,
    SourceCompanyGroup,
    alias_evidence_matches,
    canonical_company_slug,
    canonical_company_url,
    classify_germany_location,
    compute_content_hash,
    compute_card_evidence_hash,
    build_search_url,
    build_recovery_partitions,
    build_input_loader_reconciliation_report,
    AdaptiveConcurrency,
    CatalogRunner,
    ResponseEnvelope,
    RunnerConfig,
    SearchCard,
    WebshareProxy,
    WebshareTransport,
    build_arg_parser,
    backup_existing_artifacts,
    classify_http_response,
    redact_proxy_url,
    evaluate_ownership,
    evaluate_card_detail_ownership,
    load_pagination_evidence,
    load_source_company_groups,
    normalize_company_id,
    parse_job_detail,
    parse_search_page,
    read_current_catalog_generation,
    detail_refresh_required,
    detail_refresh_decision,
    union_job_ids,
)


FIXTURES = Path(__file__).parent / "fixtures"


def write_source_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fields = [
        "canonical_CompanyID",
        "company_name",
        "linkedin_company_url",
        "linkedin_slug",
        "linkedin_company_id",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_company_url_canonicalization_keeps_only_company_slug() -> None:
    raw = "https://de.linkedin.com/company/acme-gmbh/?trk=foo#about"

    assert canonical_company_slug(raw) == "acme-gmbh"
    assert canonical_company_url(raw) == "https://www.linkedin.com/company/acme-gmbh"
    assert canonical_company_url("https://www.linkedin.com/jobs/view/123") == ""


def test_source_loader_rejects_invalid_rows_and_groups_duplicate_ids(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_source_csv(
        source,
        [
            {
                "canonical_CompanyID": "C-002",
                "company_name": "Beta",
                "linkedin_company_url": "https://www.linkedin.com/company/beta/",
                "linkedin_slug": "beta",
                "linkedin_company_id": "22",
            },
            {
                "canonical_CompanyID": "C-001",
                "company_name": "Acme",
                "linkedin_company_url": "https://de.linkedin.com/company/acme?trk=x",
                "linkedin_slug": "acme",
                "linkedin_company_id": "22",
            },
            {
                "canonical_CompanyID": "C-003",
                "company_name": "Bad ID",
                "linkedin_company_url": "https://www.linkedin.com/company/bad-id",
                "linkedin_slug": "bad-id",
                "linkedin_company_id": "22.5",
            },
            {
                "canonical_CompanyID": "C-004",
                "company_name": "Bad URL",
                "linkedin_company_url": "https://www.linkedin.com/jobs/view/4",
                "linkedin_slug": "",
                "linkedin_company_id": "44",
            },
        ],
    )

    groups, stats = load_source_company_groups(source)

    assert set(groups) == {"22"}
    group = groups["22"]
    assert group.primary_canonical_company_id == "C-001"
    assert group.source_company_ids == ("C-001", "C-002")
    assert group.source_company_names == ("Acme", "Beta")
    assert group.source_company_urls == (
        "https://www.linkedin.com/company/acme",
        "https://www.linkedin.com/company/beta",
    )
    assert stats["rows_read"] == 4
    assert stats["rows_accepted"] == 2
    assert stats["rows_rejected"] == 2


def test_input_loader_reconciliation_keeps_scan_totals_out_of_task_denominator() -> None:
    report = build_input_loader_reconciliation_report(
        11907,
        {"rows_read": 12000, "rows_accepted": 11896, "rows_rejected": 104, "groups": 11896},
        excluded_count=7,
        unprocessed_count=2,
        scan_count=11921,
    )

    assert report["stored_source_groups"] == 11896
    assert report["difference"] == 11
    assert report["delta_classification"] == {
        "excluded": 7,
        "unprocessed": 2,
        "historical": 0,
        "unknown": 2,
    }
    assert report["scan_count"] == 11921
    assert report["scan_count_is_current_unique_denominator"] is False
    assert report["synthetic_tasks_created"] == 0
    assert report["status"] == "requires_explanation"


def test_ambiguous_source_slug_never_falls_back_to_first_canonical_id() -> None:
    rows = list(csv.DictReader((FIXTURES / "ambiguous_source_ownership.csv").open(encoding="utf-8")))
    group = SourceCompanyGroup(
        linkedin_company_id=rows[0]["linkedin_company_id"],
        primary_canonical_company_id=rows[0]["canonical_CompanyID"],
        source_company_names=tuple(row["company_name"] for row in rows),
        source_company_ids=tuple(row["canonical_CompanyID"] for row in rows),
        source_company_urls=tuple(row["linkedin_company_url"] for row in rows),
        primary_slug="acme",
    )

    assert evaluate_ownership("https://www.linkedin.com/company/unverified", group).status == COMPANY_MATCH_AMBIGUOUS
    mapped = evaluate_ownership("https://www.linkedin.com/company/acme-holdings", group)
    assert mapped.canonical_company_id == "C-002"


def test_source_pairs_keep_placeholder_rows_from_shifting_ownership_ids(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_source_csv(
        source,
        [
            {
                "canonical_CompanyID": "//",
                "company_name": "Unresolved",
                "linkedin_company_url": "https://www.linkedin.com/company/unresolved",
                "linkedin_slug": "unresolved",
                "linkedin_company_id": "22",
            },
            {
                "canonical_CompanyID": "C-002",
                "company_name": "Acme Holdings",
                "linkedin_company_url": "https://www.linkedin.com/company/acme-holdings",
                "linkedin_slug": "acme-holdings",
                "linkedin_company_id": "22",
            },
        ],
    )

    groups, _ = load_source_company_groups(source)
    assert evaluate_ownership("https://www.linkedin.com/company/acme-holdings", groups["22"]).canonical_company_id == "C-002"


def test_company_id_normalization_accepts_ascii_zero_padding_only() -> None:
    assert normalize_company_id("001043") == "1043"
    assert normalize_company_id("0") == ""
    assert normalize_company_id("١٠٤٣") == ""


def test_ownership_accepts_primary_and_verified_alias_but_quarantines_unknown_slug() -> None:
    group = SourceCompanyGroup(
        linkedin_company_id="22",
        primary_canonical_company_id="C-001",
        source_company_names=("Acme",),
        source_company_ids=("C-001",),
        source_company_urls=("https://www.linkedin.com/company/acme",),
        primary_slug="acme",
    )

    assert evaluate_ownership("https://nl.linkedin.com/company/acme/", group).status == (
        COMPANY_MATCH_EXACT_PRIMARY
    )
    assert evaluate_ownership(
        "https://www.linkedin.com/company/acme-holdings", group, verified_aliases={"acme-holdings"}
    ).status == COMPANY_MATCH_VERIFIED_ALIAS
    assert evaluate_ownership("https://www.linkedin.com/company/acme-holdings", group).status == (
        "ALIAS_PENDING_VERIFICATION"
    )
    assert evaluate_ownership("https://www.linkedin.com/company/other", group).status == (
        "ALIAS_PENDING_VERIFICATION"
    )
    assert alias_evidence_matches("urn:li:fsd_company:22", "22")
    assert not alias_evidence_matches("urn:li:fsd_company:23", "22")


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("Berlin, Germany", LOCATION_GERMANY_CONFIRMED),
        ("Remote - Germany", LOCATION_REMOTE_GERMANY_ELIGIBLE),
        ("Munich or Vienna", LOCATION_MULTI_LOCATION_INCLUDES_GERMANY),
        ("Europe (Remote)", LOCATION_AMBIGUOUS),
        ("New York, United States", LOCATION_NOT_GERMANY),
    ],
)
def test_germany_location_classification(location: str, expected: str) -> None:
    classification, reason = classify_germany_location(location)

    assert classification == expected
    assert reason


def test_content_hash_ignores_observation_metadata_but_changes_for_material_content() -> None:
    material = {
        "job_title": "Engineer",
        "description": "Build reliable systems.",
        "location": "Berlin, Germany",
        "employment_type": "Full-time",
        "workplace_type": "Hybrid",
        "canonical_apply_url": "https://jobs.example.test/engineer",
        "observed_company_url": "https://www.linkedin.com/company/acme",
    }

    first = compute_content_hash(material)
    same_content = compute_content_hash({**material, "applicant_count": "17", "run_id": "run-2"})
    changed = compute_content_hash({**material, "description": "Build resilient systems."})

    assert first == same_content
    assert first != changed


def test_search_url_always_keeps_company_and_germany_filters() -> None:
    url = build_search_url("22", start=20)

    assert "f_C=22" in url
    assert "geoId=101282230" in url
    assert "location=Germany" in url
    assert "start=20" in url


def test_search_parser_preserves_valid_cards_and_marks_partial_page() -> None:
    page = parse_search_page((FIXTURES / "linkedin_job_search_company_scoped.html").read_text())

    assert [card.linkedin_job_id for card in page.cards] == ["1234567890", "1234567891"]
    assert page.cards[0].company_url == "https://www.linkedin.com/company/acme"
    assert page.cards[1].location == "Remote - Germany"
    assert page.malformed_cards == ("missing_job_id",)
    assert page.is_usable
    assert page.is_partial


def test_search_parser_recognizes_explicit_no_results_and_rejects_http_200_challenge_body() -> None:
    no_results = parse_search_page((FIXTURES / "linkedin_job_search_no_results.html").read_text())
    challenge = parse_search_page((FIXTURES / "linkedin_job_search_challenge.html").read_text())

    assert no_results.is_usable
    assert no_results.is_no_results
    assert not no_results.cards
    assert not challenge.is_usable
    assert challenge.blocked_reason == "login_or_challenge"


def test_detail_parser_extracts_detail_fields_and_apply_metadata() -> None:
    detail = parse_job_detail("1234567890", (FIXTURES / "linkedin_job_detail.html").read_text())

    assert detail.linkedin_job_id == "1234567890"
    assert detail.title == "Senior Engineer"
    assert detail.company_url == "https://www.linkedin.com/company/acme"
    assert detail.location == "Berlin, Germany"
    assert "Build reliable systems" in detail.description
    assert detail.apply_url_raw.startswith("https://jobs.acme.example/apply/")
    assert detail.apply_url_canonical == "https://jobs.acme.example/apply/1234567890"
    assert detail.apply_url_source == "external"
    assert detail.applicant_count == "12"
    assert detail.employment_type == "Full-time"
    assert detail.workplace_type == "Hybrid"


def test_card_and_detail_urls_must_both_match_group() -> None:
    group = SourceCompanyGroup(
        linkedin_company_id="22",
        primary_canonical_company_id="C-001",
        source_company_names=("Acme",),
        source_company_ids=("C-001",),
        source_company_urls=("https://www.linkedin.com/company/acme",),
        primary_slug="acme",
    )

    accepted = evaluate_card_detail_ownership(
        "https://www.linkedin.com/company/acme",
        "https://de.linkedin.com/company/acme",
        group,
    )
    mismatch = evaluate_card_detail_ownership(
        "https://www.linkedin.com/company/acme",
        "https://www.linkedin.com/company/other",
        group,
    )

    assert accepted.status == COMPANY_MATCH_EXACT_PRIMARY
    assert mismatch.status == COMPANY_MATCH_CARD_DETAIL_MISMATCH


def test_pagination_evidence_is_loaded_and_validated(tmp_path: Path) -> None:
    report = tmp_path / "pagination.json"
    report.write_text(
        '{"endpoint":"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",'
        '"page_step":10,"full_card_count":10,"max_start":1000}',
        encoding="utf-8",
    )

    evidence = load_pagination_evidence(report)

    assert evidence.page_step == 10
    assert evidence.full_card_count == 10
    assert evidence.max_start == 1000


def make_catalog_row(
    *,
    company_id: str = "22",
    job_id: str = "1234567890",
    first_seen_at: str = "2026-08-31T08:00:00Z",
    last_seen_at: str = "2026-08-31T08:00:00Z",
) -> dict[str, str]:
    row = {field: "" for field in CATALOG_FIELDS}
    row.update(
        {
            "canonical_company_id": "C-001",
            "linkedin_company_id": company_id,
            "source_company_name": "Acme",
            "source_company_url": "https://www.linkedin.com/company/acme",
            "source_company_ids": "C-001",
            "source_company_names": "Acme",
            "source_company_urls": "https://www.linkedin.com/company/acme",
            "observed_company_name": "Acme GmbH",
            "observed_company_url": "https://www.linkedin.com/company/acme",
            "linkedin_job_id": job_id,
            "job_title": "Senior Engineer",
            "linkedin_job_url": f"https://www.linkedin.com/jobs/view/{job_id}",
            "location": "Berlin, Germany",
            "location_classification": LOCATION_GERMANY_CONFIRMED,
            "company_match_status": COMPANY_MATCH_EXACT_PRIMARY,
            "ownership_status": COMPANY_MATCH_EXACT_PRIMARY,
            "first_seen_at": first_seen_at,
            "last_seen_at": last_seen_at,
            "last_successful_company_scan_at": last_seen_at,
            "lifecycle_status": "active",
            "absence_count": "0",
            "run_id": "run-1",
        }
    )
    return row


def test_state_store_skips_successful_pages_only_within_same_run_and_deduplicates_detail_queue(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    group = SourceCompanyGroup(
        linkedin_company_id="22",
        primary_canonical_company_id="C-001",
        source_company_names=("Acme",),
        source_company_ids=("C-001",),
        source_company_urls=("https://www.linkedin.com/company/acme",),
        primary_slug="acme",
    )
    store.start_run("run-1", mode="initial", input_sha256="input")
    scan_id = store.start_company_scan("run-1", group)
    store.record_search_page("run-1", scan_id, "22", 0, status="COMPLETE", job_ids=("1234567890",))

    assert store.successful_page_exists("run-1", "22", 0)
    assert not store.successful_page_exists("run-2", "22", 0)
    assert store.enqueue_detail("run-1", scan_id, "22", "1234567890")
    assert not store.enqueue_detail("run-1", scan_id, "22", "1234567890")
    assert store.pending_detail_job_ids() == ("1234567890",)
    store.close()


def test_state_store_serializes_all_sqlite_reads(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    group = SourceCompanyGroup(
        linkedin_company_id="22",
        primary_canonical_company_id="C-001",
        source_company_names=("Acme",),
        source_company_ids=("C-001",),
        source_company_urls=("https://www.linkedin.com/company/acme",),
        primary_slug="acme",
    )
    store.start_run("run-1", mode="pilot", input_sha256="input")
    scan_id = store.start_company_scan("run-1", group)
    store.record_search_page("run-1", scan_id, "22", 0, status="COMPLETE", job_ids=("1234567890",))
    store.enqueue_detail("run-1", scan_id, "22", "1234567890")
    store.record_alias("22", "acme-alias", status=COMPANY_MATCH_VERIFIED_ALIAS)
    store.upsert_catalog_row(make_catalog_row())

    class GuardedConnection:
        def __init__(self, connection, lock) -> None:
            self._connection = connection
            self._lock = lock

        def execute(self, *args, **kwargs):
            assert self._lock._is_owned(), "SQLite execute occurred outside StateStore lock"
            return self._connection.execute(*args, **kwargs)

        def __enter__(self):
            self._connection.__enter__()
            return self

        def __exit__(self, *args):
            return self._connection.__exit__(*args)

        def close(self):
            return self._connection.close()

    store.connection = GuardedConnection(store.connection, store._lock)
    assert store.existing_company_scan("run-1", "22") == scan_id
    assert store.existing_company_scan_status("run-1", "22") == "RUNNING"
    assert store.successful_page_exists("run-1", "22", 0)
    assert store.page_job_ids("run-1", "22", 0) == ("1234567890",)
    assert store.search_cards_for_run("run-1", "22") == ()
    assert len(store.get_detail_queue_entries("run-1")) == 1
    assert store.verified_aliases("22") == ("acme-alias",)
    assert store.pending_detail_job_ids("run-1") == ("1234567890",)
    assert store.get_catalog_row("22", "1234567890")["job_title"] == "Senior Engineer"
    store.close()


def test_start_company_scan_is_idempotent_for_same_run_and_company(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    group = SourceCompanyGroup(
        linkedin_company_id="22",
        primary_canonical_company_id="C-001",
        source_company_names=("Acme",),
        source_company_ids=("C-001",),
        source_company_urls=("https://www.linkedin.com/company/acme",),
        primary_slug="acme",
    )
    store.start_run("run-1", mode="pilot", input_sha256="input")

    first = store.start_company_scan("run-1", group)
    second = store.start_company_scan("run-1", group)

    assert second == first
    assert store.connection.execute(
        "SELECT COUNT(*) FROM company_scans WHERE run_id=? AND linkedin_company_id=?",
        ("run-1", "22"),
    ).fetchone()[0] == 1
    store.close()


def test_state_store_backfills_observation_scan_ids_on_reopen(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    store = StateStore(path)
    group = SourceCompanyGroup(
        linkedin_company_id="22",
        primary_canonical_company_id="C-001",
        source_company_names=("Acme",),
        source_company_ids=("C-001",),
        source_company_urls=("https://www.linkedin.com/company/acme",),
        primary_slug="acme",
    )
    store.start_run("run-1", mode="pilot", input_sha256="input")
    scan_id = store.start_company_scan("run-1", group)
    store.upsert_catalog_row(make_catalog_row())
    assert "company_scan_id" not in store.get_catalog_row("22", "1234567890")
    store.close()

    reopened = StateStore(path)
    assert reopened.get_catalog_row("22", "1234567890")["company_scan_id"] == scan_id
    reopened.close()


def test_lifecycle_requires_two_distinct_complete_scans_and_reactivates(tmp_path: Path) -> None:
    lifecycle_fixture = json.loads((FIXTURES / "lifecycle_transitions.json").read_text(encoding="utf-8"))
    store = StateStore(tmp_path / "state.db")
    store.upsert_catalog_row(make_catalog_row())

    store.reconcile_lifecycle("22", "scan-partial", "PARTIAL_PAGE", set(), "2026-09-01T08:00:00Z")
    assert store.get_catalog_row("22", "1234567890")["absence_count"] == lifecycle_fixture["partial_scan"]["absence_count"]
    store.reconcile_lifecycle("22", "scan-complete-1", "COMPLETE", set(), "2026-09-02T08:00:00Z")
    first_absence = store.get_catalog_row("22", "1234567890")
    assert first_absence["absence_count"] == lifecycle_fixture["first_complete_absence"]["absence_count"]
    assert first_absence["lifecycle_status"] == lifecycle_fixture["first_complete_absence"]["lifecycle_status"]
    store.reconcile_lifecycle("22", "scan-complete-2", "COMPLETE", set(), "2026-09-03T08:00:00Z")
    inactive = store.get_catalog_row("22", "1234567890")
    assert inactive["lifecycle_status"] == lifecycle_fixture["second_complete_absence"]["lifecycle_status"]
    assert inactive["inactive_confirmed_at"] == "2026-09-03T08:00:00Z"
    events_before_replay = store.connection.execute("SELECT COUNT(*) FROM lifecycle_events").fetchone()[0]
    store.reconcile_lifecycle("22", "scan-complete-2", "COMPLETE", set(), "2026-09-03T08:00:00Z")
    assert store.connection.execute("SELECT COUNT(*) FROM lifecycle_events").fetchone()[0] == events_before_replay
    store.reconcile_lifecycle("22", "scan-complete-3", "COMPLETE", {"1234567890"}, "2026-09-04T08:00:00Z")
    row = store.get_catalog_row("22", "1234567890")
    assert row["lifecycle_status"] == "active"
    assert row["absence_count"] == "0"
    store.close()


def test_legacy_consistency_audit_is_read_only_and_withholds_suspicious_zero_evidence(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    group = SourceCompanyGroup(
        linkedin_company_id="22",
        primary_canonical_company_id="C-001",
        source_company_names=("Acme",),
        source_company_ids=("C-001",),
        source_company_urls=("https://www.linkedin.com/company/acme",),
        primary_slug="acme",
    )
    store.start_run("run-zero", mode="full", input_sha256="input", started_at="2026-09-01T08:00:00Z")
    zero_scan = store.start_company_scan("run-zero", group, scan_id="scan-zero", started_at="2026-09-01T08:00:00Z")
    store.record_search_page("run-zero", zero_scan, "22", 0, status="COMPLETE", job_ids=())
    store.finish_company_scan(zero_scan, "COMPLETE_ZERO_CONFIRMED", (), "2026-09-01T08:01:00Z")

    store.start_run("run-suspicious", mode="full", input_sha256="input", started_at="2026-09-02T08:00:00Z")
    suspicious_scan = store.start_company_scan(group=group, run_id="run-suspicious", scan_id="scan-suspicious", started_at="2026-09-02T08:00:00Z")
    store.record_search_page("run-suspicious", suspicious_scan, "22", 0, status="SUSPICIOUS_EMPTY", job_ids=())
    store.finish_company_scan(suspicious_scan, "PARTIAL_SUSPICIOUS_EMPTY", (), "2026-09-02T08:01:00Z")
    store.connection.execute(
        "INSERT INTO detail_queue(run_id, linkedin_job_id, linkedin_company_id, company_scan_id, status, next_attempt_at) VALUES (?, ?, ?, ?, 'RETRY', '')",
        ("run-suspicious", "123", "22", suspicious_scan),
    )
    store.record_alias("22", "acme-alias", status="ALIAS_PENDING_VERIFICATION", seen_at="2026-09-02T08:00:00Z")
    before = store.connection.execute("SELECT COUNT(*) FROM lifecycle_events").fetchone()[0]

    audit = store.audit_legacy_consistency()

    assert audit["read_only"] is True
    assert audit["zero_scan_count"] == 1
    assert audit["suspicious_empty_page_count"] == 1
    assert audit["qualifying_absence_count"] == 1
    assert audit["revalidation_required_zero_scan_count"] == 0
    assert audit["detail_retry_missing_due_count"] == 1
    assert audit["alias_pending_count"] == 1
    assert store.connection.execute("SELECT COUNT(*) FROM lifecycle_events").fetchone()[0] == before
    store.close()


def test_catalog_upsert_preserves_first_seen_and_updates_last_seen(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    store.upsert_catalog_row(make_catalog_row(first_seen_at="2026-08-01T08:00:00Z", last_seen_at="2026-08-01T08:00:00Z"))
    store.upsert_catalog_row(make_catalog_row(first_seen_at="2026-08-31T08:00:00Z", last_seen_at="2026-08-31T08:00:00Z"))

    row = store.get_catalog_row("22", "1234567890")

    assert row["first_seen_at"] == "2026-08-01T08:00:00Z"
    assert row["last_seen_at"] == "2026-08-31T08:00:00Z"
    store.close()


def test_detail_ttl_and_recovery_union_are_deterministic() -> None:
    assert not detail_refresh_required("2026-08-31T08:00:00Z", "2026-08-31T12:00:00Z", 24)
    assert detail_refresh_required("2026-08-29T08:00:00Z", "2026-08-31T12:00:00Z", 24)
    assert detail_refresh_required("2026-08-31T08:00:00Z", "2026-08-31T12:00:00Z", 24, card_changed=True)
    card = SearchCard("1234567890", "Senior Engineer", "Acme", "https://www.linkedin.com/company/acme", "Berlin, Germany", "1 day ago")
    previous = make_catalog_row()
    previous["detail_last_refreshed_at"] = "2026-08-31T08:00:00Z"
    previous["applicant_count_observed_at"] = "2026-08-31T08:00:00Z"
    previous["card_evidence_hash"] = compute_card_evidence_hash(card, card.company_url)
    fresh = detail_refresh_decision(previous, card, card.company_url, "2026-09-01T07:00:00Z")
    stale = detail_refresh_decision(previous, card, card.company_url, "2026-09-01T08:00:00Z")
    expired = detail_refresh_decision(previous, card, card.company_url, "2026-09-07T08:00:00Z")
    changed = detail_refresh_decision(previous, SearchCard("1234567890", "Principal Engineer", "Acme", card.company_url, card.location, card.posted_text), card.company_url, "2026-09-01T07:00:00Z")
    assert (fresh.required, fresh.reason, fresh.volatile_fields_stale) == (False, "cache_hit_fresh", False)
    assert (stale.required, stale.reason, stale.volatile_fields_stale) == (False, "volatile_fields_stale_reused", True)
    assert (expired.required, expired.reason) == (True, "durable_ttl_expired")
    assert (changed.required, changed.reason) == (True, "card_changed")
    assert union_job_ids([("1", "2"), ("2", "3"), ()]) == ("1", "2", "3")


def test_csv_export_is_bom_normalized_and_jsonl_is_explicitly_typed(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    store.upsert_catalog_row(make_catalog_row())
    csv_path = tmp_path / "master_linkedin_jobs.csv"
    jsonl_path = tmp_path / "master_linkedin_jobs.jsonl"

    store.export_catalog_csv(csv_path)
    store.append_jsonl_records(jsonl_path, [{"record_type": "job_observation", "schema_version": 1, "linkedin_job_id": "1234567890"}])

    raw = csv_path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert raw.decode("utf-8-sig").splitlines()[0].split(",") == list(CATALOG_FIELDS)
    assert "None" not in raw.decode("utf-8-sig")
    record = json.loads(jsonl_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["record_type"] == "job_observation"
    assert record["schema_version"] == 1
    store.close()


def test_jsonl_redacts_proxy_credentials(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    path = tmp_path / "diagnostics.jsonl"

    store.append_jsonl_records(path, [{"record_type": "diagnostic", "proxy_url": "http://user:super-secret@proxy.example:8080"}])

    assert "super-secret" not in path.read_text(encoding="utf-8")
    store.close()


def test_http_200_challenge_is_blocked_and_adaptive_workers_back_off_on_429() -> None:
    classification = classify_http_response(200, (FIXTURES / "linkedin_job_search_challenge.html").read_text())
    controller = AdaptiveConcurrency(initial=10, minimum=1, maximum=20)
    controller.observe(status_code=429, blocked=False)
    controller.observe(status_code=429, blocked=True)

    assert classification == "BLOCKED"
    assert controller.workers < 10


def test_shared_limiter_gates_actual_account_and_provider_in_flight_work() -> None:
    limiter = AdaptiveConcurrency(
        initial=3,
        minimum=1,
        maximum=3,
        provider_limits={"linkedin": 1, "company_resolution": 2},
    )
    state_lock = threading.Lock()
    active = {"count": 0, "peak": 0}

    def run(provider: str) -> None:
        limiter.acquire(provider)
        try:
            with state_lock:
                active["count"] += 1
                active["peak"] = max(active["peak"], active["count"])
            time.sleep(0.01)
        finally:
            with state_lock:
                active["count"] -= 1
            limiter.release(provider)

    threads = [threading.Thread(target=run, args=("linkedin",)) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert active["peak"] == 1
    assert limiter.peak_in_flight == 1

    threads = [threading.Thread(target=run, args=("company_resolution",)) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert active["peak"] == 2
    limiter.observe(status_code=429, blocked=False, provider="company_resolution")
    assert limiter.workers == 2


def test_webshare_reuses_worker_proxy_sessions_and_closes_them(monkeypatch: pytest.MonkeyPatch) -> None:
    sessions: list[object] = []

    class FakeSession:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}
            self.trust_env = True
            self.closed = False
            sessions.append(self)

        def get(self, _url: str, **_kwargs: object) -> object:
            return type("FakeResponse", (), {"status_code": 200, "text": "ok"})()

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(catalog_module.requests, "Session", FakeSession)
    transport = WebshareTransport(
        (WebshareProxy("proxy-1:8080", "http://user:secret@proxy-1:8080"),),
        retry_limit=0,
        request_limiter=AdaptiveConcurrency(initial=1, minimum=1, maximum=1),
    )

    assert transport.get("https://example.test/one", kind="search").status_code == 200
    assert transport.get("https://example.test/two", kind="detail").status_code == 200
    assert len(sessions) == 1
    assert transport.proxy_health_snapshot()[0]["success_count"] == 2

    transport.close()

    assert sessions[0].closed is True
    assert all("http" not in str(row) for row in transport.proxy_health_snapshot())


def test_proxy_health_records_cooldowns_and_persists_without_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [429, 200]

    class FakeSession:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}
            self.trust_env = True

        def get(self, _url: str, **_kwargs: object) -> object:
            status = responses.pop(0)
            return type("FakeResponse", (), {"status_code": status, "text": "ok"})()

        def close(self) -> None:
            return None

    monkeypatch.setattr(catalog_module.requests, "Session", FakeSession)
    transport = WebshareTransport(
        (
            WebshareProxy("proxy-1:8080", "http://user:secret@proxy-1:8080"),
            WebshareProxy("proxy-2:8080", "http://user:secret@proxy-2:8080"),
        ),
        retry_limit=0,
        request_limiter=AdaptiveConcurrency(initial=2, minimum=1, maximum=2),
    )

    assert transport.get("https://example.test/one", kind="search").status_code == 429
    assert transport.get("https://example.test/two", kind="search").status_code == 200
    snapshot = transport.proxy_health_snapshot()
    store = StateStore(tmp_path / "state.db")
    assert store.upsert_proxy_health(snapshot) == 2
    rows = store.connection.execute(
        "SELECT proxy_id, rate_limited_count, success_count, cooldown_until FROM proxy_health ORDER BY proxy_id"
    ).fetchall()

    assert rows[0][0] == "proxy-1:8080"
    assert rows[0][1:] == (1, 0, rows[0][3])
    assert rows[0][3]
    assert rows[1][0] == "proxy-2:8080"
    assert rows[1][2] == 1
    assert "http" not in store.connection.execute("SELECT * FROM proxy_health").fetchone()[0]
    store.close()
    transport.close()


def test_state_store_batch_rolls_back_unacknowledged_catalog_writes(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")

    with pytest.raises(RuntimeError):
        with store.batch():
            store.upsert_catalog_row(make_catalog_row())
            raise RuntimeError("crash before commit")

    with pytest.raises(KeyError):
        store.get_catalog_row("22", "1234567890")

    with store.batch():
        store.upsert_catalog_row(make_catalog_row())
    assert store.get_catalog_row("22", "1234567890")["linkedin_job_id"] == "1234567890"
    store.close()


def test_recovery_partitions_only_use_supported_validated_filters(tmp_path: Path) -> None:
    report = tmp_path / "filters.json"
    report.write_text(
        json.dumps(
            {
                "endpoint": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
                "status": "COMPLETE",
                "filters": {
                    "freshness": {"r3600": {"status": "SUPPORTED"}},
                    "job_type": {"temporary": {"status": "SUPPORTED"}, "full-time": {"status": "IGNORED"}},
                },
                "enable_only_statuses": ["SUPPORTED"],
            }
        ),
        encoding="utf-8",
    )

    partitions = build_recovery_partitions(report)

    assert [(item.parameter, item.value) for item in partitions] == [("f_TPR", "r3600"), ("f_JT", "T")]


def test_proxy_redaction_removes_credentials_from_diagnostics() -> None:
    assert redact_proxy_url("http://webshare-user:super-secret@proxy.example:8080") == "http://proxy.example:8080"
    assert "super-secret" not in redact_proxy_url("http://webshare-user:super-secret@proxy.example:8080")


class ScriptedTransport:
    def __init__(self, *, detail_body: str | None = None, search_body: str | None = None, company_body: str = "") -> None:
        self.urls: list[tuple[str, str]] = []
        self.detail_body = detail_body or (FIXTURES / "linkedin_job_detail.html").read_text()
        self.search_body = search_body or (FIXTURES / "linkedin_job_search_company_scoped.html").read_text()
        self.company_body = company_body

    def get(self, url: str, *, kind: str) -> ResponseEnvelope:
        self.urls.append((url, kind))
        if kind == "search":
            if "start=0" in url:
                body = self.search_body
            else:
                body = (FIXTURES / "linkedin_job_search_no_results.html").read_text()
            return ResponseEnvelope(200, body, "proxy-1", 0.01)
        if kind == "company":
            return ResponseEnvelope(200, self.company_body, "proxy-1", 0.01)
        return ResponseEnvelope(200, self.detail_body, "proxy-1", 0.01)


class FixtureRetryTransport:
    """Offline transport that consumes recorded retry responses before success."""

    def __init__(self) -> None:
        payload = json.loads((FIXTURES / "linkedin_retry_sequence.json").read_text(encoding="utf-8"))
        self.search_specs = list(payload["search"])
        self.detail_specs = list(payload["detail"])
        self.provider_credits_used = 2
        self.provider_cost = 0.02
        self.urls: list[tuple[str, str]] = []
        self.attempts: list[tuple[str, int]] = []

    def _body(self, spec: dict[str, object]) -> str:
        fixture = spec.get("fixture")
        return (FIXTURES / str(fixture)).read_text(encoding="utf-8") if fixture else str(spec.get("body") or "")

    def get(self, url: str, *, kind: str) -> ResponseEnvelope:
        self.urls.append((url, kind))
        if kind == "search" and "start=0" not in url:
            return ResponseEnvelope(200, (FIXTURES / "linkedin_job_search_no_results.html").read_text(encoding="utf-8"), "proxy-1", 0.01)
        specs = self.search_specs if kind == "search" else self.detail_specs
        if kind == "detail" and not specs:
            return ResponseEnvelope(200, (FIXTURES / "linkedin_job_detail.html").read_text(encoding="utf-8"), "proxy-1", 0.01)
        last = ResponseEnvelope(0, "", "proxy-1", 0.01, "network_error")
        while specs:
            spec = specs.pop(0)
            status = int(spec["status_code"])
            self.attempts.append((kind, status))
            last = ResponseEnvelope(status, self._body(spec), "proxy-1", 0.01)
            if status != 429 and status < 500:
                return last
        return last


class SearchBodyTransport(ScriptedTransport):
    def __init__(self, bodies_by_start: dict[str, str]) -> None:
        super().__init__()
        self.bodies_by_start = bodies_by_start

    def get(self, url: str, *, kind: str) -> ResponseEnvelope:
        self.urls.append((url, kind))
        if kind == "search":
            for start, body in self.bodies_by_start.items():
                if f"start={start}" in url:
                    return ResponseEnvelope(200, body, "proxy-1", 0.01)
            return ResponseEnvelope(200, (FIXTURES / "linkedin_job_search_no_results.html").read_text(encoding="utf-8"), "proxy-1", 0.01)
        if kind == "company":
            return ResponseEnvelope(200, self.company_body, "proxy-1", 0.01)
        return ResponseEnvelope(200, self.detail_body, "proxy-1", 0.01)


class DetailFailureTransport(ScriptedTransport):
    def get(self, url: str, *, kind: str) -> ResponseEnvelope:
        if kind == "detail":
            self.urls.append((url, kind))
            return ResponseEnvelope(503, "temporary detail failure", "proxy-1", 0.01)
        return super().get(url, kind=kind)


class RecoveryCompletingTransport(ScriptedTransport):
    def get(self, url: str, *, kind: str) -> ResponseEnvelope:
        if kind == "search" and "f_TPR=r3600" in url:
            self.urls.append((url, kind))
            return ResponseEnvelope(
                200,
                (FIXTURES / "linkedin_job_search_no_results.html").read_text(encoding="utf-8"),
                "proxy-1",
                0.01,
            )
        return super().get(url, kind=kind)


def write_pagination_report(path: Path) -> None:
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


def write_filter_report(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "endpoint": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
                "status": "COMPLETE",
                "filters": {"freshness": {"r3600": {"status": "SUPPORTED"}}},
                "enable_only_statuses": ["SUPPORTED"],
            }
        ),
        encoding="utf-8",
    )


def test_runner_publishes_only_detail_verified_company_jobs_and_keeps_query_scope(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_source_csv(
        source,
        [{
            "canonical_CompanyID": "C-001",
            "company_name": "Acme",
            "linkedin_company_url": "https://www.linkedin.com/company/acme",
            "linkedin_slug": "acme",
            "linkedin_company_id": "22",
        }],
    )
    pagination = tmp_path / "pagination.json"
    write_pagination_report(pagination)
    transport = ScriptedTransport()
    config = RunnerConfig(
        input_csv=source,
        output_dir=tmp_path / "output",
        pagination_report=pagination,
        mode="smoke",
        max_companies=1,
        detail_refresh_hours=24,
    )

    metrics = CatalogRunner(config, transport=transport).run()

    assert metrics["companies_partial"] == 1
    assert metrics["jobs_written"] == 2
    assert all("f_C=22" in url and "geoId=101282230" in url and "location=Germany" in url for url, kind in transport.urls if kind == "search")
    rows = list(csv.DictReader((tmp_path / "output" / "master_linkedin_jobs.csv").open(encoding="utf-8-sig")))
    assert {row["linkedin_job_id"] for row in rows} == {"1234567890", "1234567891"}
    assert all(row["company_match_status"] == COMPANY_MATCH_EXACT_PRIMARY for row in rows)
    assert all("location=Germany" in row["source_endpoint"] and "geoId=101282230" in row["source_endpoint"] and "f_C=22" in row["source_endpoint"] for row in rows)
    state = StateStore(tmp_path / "output" / "master_linkedin_jobs_state.db")
    assert state.get_catalog_row("22", "1234567890")["company_scan_id"]
    state.close()


def test_runner_rejects_detail_company_mismatch_and_does_not_publish_it(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_source_csv(
        source,
        [{
            "canonical_CompanyID": "C-001",
            "company_name": "Acme",
            "linkedin_company_url": "https://www.linkedin.com/company/acme",
            "linkedin_slug": "acme",
            "linkedin_company_id": "22",
        }],
    )
    pagination = tmp_path / "pagination.json"
    write_pagination_report(pagination)
    mismatched = (FIXTURES / "linkedin_job_detail.html").read_text().replace("company/acme", "company/other")
    config = RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="smoke", max_companies=1)

    metrics = CatalogRunner(config, transport=ScriptedTransport(detail_body=mismatched)).run()

    assert metrics["jobs_written"] == 0
    assert metrics["ownership_exclusions"] == 2
    assert not list(csv.DictReader((tmp_path / "output" / "master_linkedin_jobs.csv").open(encoding="utf-8-sig")))


def test_runner_dry_run_parser_has_safe_modes_and_no_target_transport() -> None:
    args = build_arg_parser().parse_args(["--dry-run", "--mode", "validate", "--company-id", "22"])

    assert args.dry_run
    assert args.mode == "validate"
    assert args.company_id == "22"
    assert args.workers == 10
    assert args.detail_workers == 5
    assert args.per_proxy_concurrency == 1


def test_runner_verifies_consistent_alias_before_publishing(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_source_csv(
        source,
        [{
            "canonical_CompanyID": "C-001",
            "company_name": "Acme",
            "linkedin_company_url": "https://www.linkedin.com/company/acme",
            "linkedin_slug": "acme",
            "linkedin_company_id": "22",
        }],
    )
    pagination = tmp_path / "pagination.json"
    write_pagination_report(pagination)
    search = (FIXTURES / "linkedin_job_search_valid.html").read_text().replace("company/acme", "company/acme-holdings")
    detail = (FIXTURES / "linkedin_job_detail.html").read_text().replace("company/acme", "company/acme-holdings")
    transport = ScriptedTransport(detail_body=detail, search_body=search, company_body=(FIXTURES / "linkedin_company_alias.html").read_text())
    config = RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="smoke", max_companies=1)

    metrics = CatalogRunner(config, transport=transport).run()

    assert metrics["jobs_written"] == 2
    rows = list(csv.DictReader((tmp_path / "output" / "master_linkedin_jobs.csv").open(encoding="utf-8-sig")))
    assert {row["ownership_status"] for row in rows} == {COMPANY_MATCH_VERIFIED_ALIAS}
    assert any(kind == "company" for _, kind in transport.urls)


def test_fresh_backup_copies_existing_artifacts_without_losing_them(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    artifact = output / "master_linkedin_jobs.csv"
    artifact.write_text("old", encoding="utf-8")

    backups = backup_existing_artifacts(output)

    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "old"
    assert artifact.read_text(encoding="utf-8") == "old"


def test_daily_run_rescans_search_but_reuses_fresh_unchanged_detail(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_source_csv(
        source,
        [{
            "canonical_CompanyID": "C-001",
            "company_name": "Acme",
            "linkedin_company_url": "https://www.linkedin.com/company/acme",
            "linkedin_slug": "acme",
            "linkedin_company_id": "22",
        }],
    )
    pagination = tmp_path / "pagination.json"
    write_pagination_report(pagination)
    first_config = RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="full", max_companies=1)
    first = CatalogRunner(first_config, transport=ScriptedTransport(search_body=(FIXTURES / "linkedin_job_search_valid.html").read_text()), now=lambda: "2026-08-31T08:00:00Z").run()
    second_transport = ScriptedTransport(search_body=(FIXTURES / "linkedin_job_search_valid.html").read_text())
    second_config = RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="daily", max_companies=1, detail_refresh_hours=24)
    second = CatalogRunner(second_config, transport=second_transport, now=lambda: "2026-08-31T12:00:00Z").run()

    assert first["detail_successes"] == 2
    assert second["detail_successes"] == 0
    assert second["detail_cache_hits"] == 2
    assert second["detail_avoided_requests"] == 2
    assert second["detail_provider_credits"] is None
    assert second["detail_provider_cost"] is None
    assert second["detail_provider_cost_status"] == "not_reported_by_transport"
    assert sum(kind == "search" for _, kind in second_transport.urls) == 2
    assert sum(kind == "detail" for _, kind in second_transport.urls) == 0
    state = StateStore(tmp_path / "output" / "master_linkedin_jobs_state.db")
    refreshed = state.get_catalog_row("22", "1234567890")
    assert refreshed["run_id"] == second["run_id"]
    assert refreshed["company_scan_id"]
    assert refreshed["last_seen_at"] == "2026-08-31T12:00:00Z"
    state.close()


def test_default_daily_refresh_reuses_durable_detail_and_marks_volatile_fields_stale(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_source_csv(
        source,
        [{
            "canonical_CompanyID": "C-001",
            "company_name": "Acme",
            "linkedin_company_url": "https://www.linkedin.com/company/acme",
            "linkedin_slug": "acme",
            "linkedin_company_id": "22",
        }],
    )
    pagination = tmp_path / "pagination.json"
    write_pagination_report(pagination)
    first = CatalogRunner(
        RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="full", max_companies=1),
        transport=ScriptedTransport(search_body=(FIXTURES / "linkedin_job_search_valid.html").read_text()),
        now=lambda: "2026-08-31T08:00:00Z",
    ).run()
    second_transport = ScriptedTransport(search_body=(FIXTURES / "linkedin_job_search_valid.html").read_text())
    second = CatalogRunner(
        RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="daily", max_companies=1),
        transport=second_transport,
        now=lambda: "2026-09-01T08:00:00Z",
    ).run()

    assert first["detail_successes"] == 2
    assert second["detail_successes"] == 0
    assert second["detail_cache_hits"] == 2
    assert second["detail_avoided_requests"] == 2
    assert second["detail_volatile_stale_rows"] == 2
    assert second["detail_refresh_reasons"] == {"volatile_fields_stale_reused": 2}
    assert not any(kind == "detail" for _, kind in second_transport.urls)
    state = StateStore(tmp_path / "output" / "master_linkedin_jobs_state.db")
    row = state.get_catalog_row("22", "1234567890")
    assert row["volatile_fields_status"] == "STALE"
    assert row["applicant_count_observed_at"] == "2026-08-31T08:00:00Z"
    assert row["detail_last_refreshed_at"] == "2026-08-31T08:00:00Z"
    state.close()


def test_durable_expiry_refreshes_unchanged_detail_after_bounded_window(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_source_csv(source, [{
        "canonical_CompanyID": "C-001",
        "company_name": "Acme",
        "linkedin_company_url": "https://www.linkedin.com/company/acme",
        "linkedin_slug": "acme",
        "linkedin_company_id": "22",
    }])
    pagination = tmp_path / "pagination.json"
    write_pagination_report(pagination)
    body = (FIXTURES / "linkedin_job_search_valid.html").read_text()
    CatalogRunner(
        RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="full", max_companies=1),
        transport=ScriptedTransport(search_body=body),
        now=lambda: "2026-08-31T08:00:00Z",
    ).run()
    transport = ScriptedTransport(search_body=body)
    metrics = CatalogRunner(
        RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="daily", max_companies=1),
        transport=transport,
        now=lambda: "2026-09-07T08:00:00Z",
    ).run()

    assert metrics["detail_successes"] == 2
    assert metrics["detail_refresh_reasons"] == {"durable_ttl_expired": 2}
    assert sum(kind == "detail" for _, kind in transport.urls) == 2


def test_changed_card_refreshes_detail_even_when_durable_cache_is_fresh(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_source_csv(source, [{
        "canonical_CompanyID": "C-001",
        "company_name": "Acme",
        "linkedin_company_url": "https://www.linkedin.com/company/acme",
        "linkedin_slug": "acme",
        "linkedin_company_id": "22",
    }])
    pagination = tmp_path / "pagination.json"
    write_pagination_report(pagination)
    body = (FIXTURES / "linkedin_job_search_valid.html").read_text()
    CatalogRunner(
        RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="full", max_companies=1),
        transport=ScriptedTransport(search_body=body),
        now=lambda: "2026-08-31T08:00:00Z",
    ).run()
    changed_body = body.replace("Senior Engineer", "Principal Engineer", 1)
    transport = ScriptedTransport(search_body=changed_body)
    metrics = CatalogRunner(
        RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="daily", max_companies=1),
        transport=transport,
        now=lambda: "2026-09-01T08:00:00Z",
    ).run()

    assert metrics["detail_successes"] == 1
    assert metrics["detail_refresh_reasons"] == {"card_changed": 1, "volatile_fields_stale_reused": 1}
    assert sum(kind == "detail" for _, kind in transport.urls) == 1


def test_failed_durable_refresh_does_not_reset_cached_freshness(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_source_csv(source, [{
        "canonical_CompanyID": "C-001",
        "company_name": "Acme",
        "linkedin_company_url": "https://www.linkedin.com/company/acme",
        "linkedin_slug": "acme",
        "linkedin_company_id": "22",
    }])
    pagination = tmp_path / "pagination.json"
    write_pagination_report(pagination)
    body = (FIXTURES / "linkedin_job_search_valid.html").read_text()
    CatalogRunner(
        RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="full", max_companies=1),
        transport=ScriptedTransport(search_body=body),
        now=lambda: "2026-08-31T08:00:00Z",
    ).run()
    metrics = CatalogRunner(
        RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="daily", max_companies=1),
        transport=DetailFailureTransport(search_body=body),
        now=lambda: "2026-09-07T08:00:00Z",
    ).run()

    assert metrics["detail_failures"] == 2
    assert metrics["run_outcome"] == "PARTIAL"
    state = StateStore(tmp_path / "output" / "master_linkedin_jobs_state.db")
    row = state.get_catalog_row("22", "1234567890")
    assert row["detail_last_refreshed_at"] == "2026-08-31T08:00:00Z"
    assert row["applicant_count_observed_at"] == "2026-08-31T08:00:00Z"
    state.close()


def test_source_disappearance_is_reconciled_when_detail_is_reused_or_not_requested(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_source_csv(source, [{
        "canonical_CompanyID": "C-001",
        "company_name": "Acme",
        "linkedin_company_url": "https://www.linkedin.com/company/acme",
        "linkedin_slug": "acme",
        "linkedin_company_id": "22",
    }])
    pagination = tmp_path / "pagination.json"
    write_pagination_report(pagination)
    valid = (FIXTURES / "linkedin_job_search_valid.html").read_text()
    CatalogRunner(
        RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="full", max_companies=1),
        transport=ScriptedTransport(search_body=valid),
        now=lambda: "2026-08-31T08:00:00Z",
    ).run()
    transport = ScriptedTransport(search_body=(FIXTURES / "linkedin_job_search_no_results.html").read_text())
    metrics = CatalogRunner(
        RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="daily", max_companies=1),
        transport=transport,
        now=lambda: "2026-09-01T08:00:00Z",
    ).run()

    assert metrics["detail_successes"] == 0
    assert metrics["companies_zero_confirmed"] == 1
    assert not any(kind == "detail" for _, kind in transport.urls)
    state = StateStore(tmp_path / "output" / "master_linkedin_jobs_state.db")
    assert state.get_catalog_row("22", "1234567890")["absence_count"] == "1"
    state.close()


def test_explicit_empty_snapshot_is_complete_zero_confirmed(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_source_csv(
        source,
        [{
            "canonical_CompanyID": "C-001",
            "company_name": "Acme",
            "linkedin_company_url": "https://www.linkedin.com/company/acme",
            "linkedin_slug": "acme",
            "linkedin_company_id": "22",
        }],
    )
    pagination = tmp_path / "pagination.json"
    write_pagination_report(pagination)
    empty_transport = ScriptedTransport(search_body=(FIXTURES / "linkedin_job_search_no_results.html").read_text())
    config = RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="smoke", max_companies=1)

    metrics = CatalogRunner(config, transport=empty_transport).run()

    assert metrics["companies_completed"] == 1
    assert metrics["jobs_written"] == 0
    assert sum(kind == "search" for _, kind in empty_transport.urls) == 2


def test_saturated_base_query_uses_validated_recovery_partition(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_source_csv(
        source,
        [{
            "canonical_CompanyID": "C-001",
            "company_name": "Acme",
            "linkedin_company_url": "https://www.linkedin.com/company/acme",
            "linkedin_slug": "acme",
            "linkedin_company_id": "22",
        }],
    )
    pagination = tmp_path / "pagination.json"
    pagination.write_text(
        json.dumps({"endpoint": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search", "page_step": 10, "full_card_count": 2, "max_start": 0}),
        encoding="utf-8",
    )
    filters = tmp_path / "filters.json"
    write_filter_report(filters)
    transport = RecoveryCompletingTransport(search_body=(FIXTURES / "linkedin_job_search_valid.html").read_text())
    config = RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, filters_report=filters, mode="smoke", max_companies=1)

    metrics = CatalogRunner(config, transport=transport).run()

    assert metrics["companies_completed"] == 1
    assert metrics["recovery_partitions_completed"] == 1
    assert metrics["recovery_partitions_pending"] == 0
    assert any("f_TPR=r3600" in url for url, kind in transport.urls if kind == "search")


def test_nonempty_recovery_page_at_cap_remains_partial(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_source_csv(
        source,
        [{
            "canonical_CompanyID": "C-001",
            "company_name": "Acme",
            "linkedin_company_url": "https://www.linkedin.com/company/acme",
            "linkedin_slug": "acme",
            "linkedin_company_id": "22",
        }],
    )
    pagination = tmp_path / "pagination.json"
    pagination.write_text(
        json.dumps({
            "endpoint": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
            "page_step": 10,
            "full_card_count": 2,
            "max_start": 0,
        }),
        encoding="utf-8",
    )
    filters = tmp_path / "filters.json"
    write_filter_report(filters)
    transport = ScriptedTransport(search_body=(FIXTURES / "linkedin_job_search_valid.html").read_text())

    metrics = CatalogRunner(
        RunnerConfig(
            input_csv=source,
            output_dir=tmp_path / "output",
            pagination_report=pagination,
            filters_report=filters,
            mode="smoke",
            max_companies=1,
        ),
        transport=transport,
    ).run()

    assert metrics["companies_partial"] == 1
    assert metrics["companies_completed"] == 0
    assert metrics["recovery_partitions_required"] == 1
    assert metrics["recovery_partitions_completed"] == 0
    assert metrics["recovery_partitions_partial"] == 1
    assert metrics["run_outcome"] == "PARTIAL"
    state = StateStore(tmp_path / "output" / "master_linkedin_jobs_state.db")
    assert state.connection.execute(
        "SELECT status FROM search_pages WHERE query_partition_type='f_TPR'"
    ).fetchone()[0] == "PARTIAL"
    state.close()


def test_retry_sequence_is_replayed_offline_before_classifying_the_scan(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_source_csv(
        source,
        [{
            "canonical_CompanyID": "C-001",
            "company_name": "Acme",
            "linkedin_company_url": "https://www.linkedin.com/company/acme",
            "linkedin_slug": "acme",
            "linkedin_company_id": "22",
        }],
    )
    pagination = tmp_path / "pagination.json"
    write_pagination_report(pagination)
    transport = FixtureRetryTransport()

    metrics = CatalogRunner(
        RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="smoke", max_companies=1),
        transport=transport,
        now=lambda: "2026-08-31T08:00:00Z",
    ).run()

    assert ("search", 503) in transport.attempts
    assert ("search", 200) in transport.attempts
    assert ("detail", 429) in transport.attempts
    assert metrics["jobs_written"] == 2
    assert metrics["run_outcome"] == "COMPLETE"
    assert metrics["detail_provider_credits"] == 2
    assert metrics["detail_provider_cost"] == 0.02
    assert metrics["detail_provider_cost_status"] == "reported_by_transport"
    generation = read_current_catalog_generation(tmp_path / "output")
    assert generation is not None
    jsonl_relative_path = generation["manifest"]["artifacts"]["master_linkedin_jobs.jsonl"]["path"]
    assert (tmp_path / "output" / str(jsonl_relative_path)).read_text(encoding="utf-8").strip()
    state = StateStore(tmp_path / "output" / "master_linkedin_jobs_state.db")
    run = state.connection.execute("SELECT status, finished_at FROM runs WHERE run_id=?", (metrics["run_id"],)).fetchone()
    assert tuple(run) == ("FINISHED", "2026-08-31T08:00:00Z")
    state.close()


def test_persistent_search_failure_is_reported_as_failure_not_zero(tmp_path: Path) -> None:
    source = tmp_path / "companies.csv"
    write_source_csv(
        source,
        [{
            "canonical_CompanyID": "C-001",
            "company_name": "Acme",
            "linkedin_company_url": "https://www.linkedin.com/company/acme",
            "linkedin_slug": "acme",
            "linkedin_company_id": "22",
        }],
    )
    pagination = tmp_path / "pagination.json"
    write_pagination_report(pagination)
    transport = FixtureRetryTransport()
    transport.search_specs = [{"status_code": 503, "body": "temporary upstream failure"}]

    metrics = CatalogRunner(
        RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="smoke", max_companies=1),
        transport=transport,
        now=lambda: "2026-09-06T08:00:00Z",
    ).run()

    assert metrics["companies_failed"] == 1
    assert metrics["companies_zero_confirmed"] == 0
    assert metrics["run_status"] == "FAILED"
    assert metrics["run_outcome"] == "FAILURE"
    state = StateStore(tmp_path / "output" / "master_linkedin_jobs_state.db")
    assert state.connection.execute("SELECT status FROM company_scans").fetchone()[0] == "FAILED"
    assert state.connection.execute("SELECT status FROM runs").fetchone()[0] == "FAILED"
    state.close()


def test_detail_retry_has_due_time_and_quarantines_at_the_attempt_budget(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    group = SourceCompanyGroup(
        linkedin_company_id="22",
        primary_canonical_company_id="C-001",
        source_company_names=("Acme",),
        source_company_ids=("C-001",),
        source_company_urls=("https://www.linkedin.com/company/acme",),
        primary_slug="acme",
    )
    store.start_run("run-1", mode="smoke", input_sha256="input")
    scan_id = store.start_company_scan("run-1", group)
    store.enqueue_detail("run-1", scan_id, "22", "1234567890")

    for attempt in range(1, 4):
        store.record_detail_attempt(
            "run-1",
            "1234567890",
            status="FAILED",
            error_class="RATE_LIMITED",
            attempted_at=f"2026-09-06T08:0{attempt}:00Z",
        )
        row = store.connection.execute(
            "SELECT status, attempt_count, next_attempt_at, terminal_status FROM detail_queue WHERE run_id=? AND linkedin_job_id=?",
            ("run-1", "1234567890"),
        ).fetchone()
        if attempt < 3:
            assert tuple(row)[:2] == ("RETRY", attempt)
            assert row[2]
        else:
            assert tuple(row) == ("QUARANTINED", 3, "", "ATTEMPT_BUDGET_EXHAUSTED")
    assert store.detail_queue_counts("run-1")["quarantined"] == 1
    assert not store.get_detail_queue_entries("run-1")
    store.close()


@pytest.mark.parametrize("bodies", [
    {
        "start=0": "linkedin_job_search_suspicious_empty.html",
        "start=10": "linkedin_job_search_suspicious_empty.html",
    },
    {
        "start=0": "linkedin_job_search_valid.html",
        "start=10": "linkedin_job_search_suspicious_empty.html",
    },
])
def test_suspicious_empty_pages_remain_partial_for_empty_first_and_after_nonempty(tmp_path: Path, bodies: dict[str, str]) -> None:
    source = tmp_path / "companies.csv"
    write_source_csv(
        source,
        [{
            "canonical_CompanyID": "C-001",
            "company_name": "Acme",
            "linkedin_company_url": "https://www.linkedin.com/company/acme",
            "linkedin_slug": "acme",
            "linkedin_company_id": "22",
        }],
    )
    pagination = tmp_path / "pagination.json"
    write_pagination_report(pagination)
    transport = SearchBodyTransport({key.split("=")[1]: (FIXTURES / value).read_text(encoding="utf-8") for key, value in bodies.items()})

    metrics = CatalogRunner(
        RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, mode="smoke", max_companies=1),
        transport=transport,
    ).run()

    assert metrics["companies_zero_confirmed"] == 0
    assert metrics["companies_partial"] == 1
    assert metrics["run_outcome"] == "PARTIAL"
    state = StateStore(tmp_path / "output" / "master_linkedin_jobs_state.db")
    assert state.connection.execute("SELECT status FROM company_scans").fetchone()[0] == "PARTIAL_SUSPICIOUS_EMPTY"
    assert state.connection.execute("SELECT COUNT(*) FROM search_pages WHERE status='SUSPICIOUS_EMPTY'").fetchone()[0] >= 1
    state.close()


def test_ambiguous_pipeline_excludes_unknown_company_without_primary_fallback(tmp_path: Path) -> None:
    pagination = tmp_path / "pagination.json"
    write_pagination_report(pagination)
    search = (FIXTURES / "linkedin_job_search_valid.html").read_text(encoding="utf-8").replace("company/acme", "company/unverified")
    detail = (FIXTURES / "linkedin_job_detail.html").read_text(encoding="utf-8").replace("company/acme", "company/unverified")
    transport = ScriptedTransport(search_body=search, detail_body=detail)

    metrics = CatalogRunner(
        RunnerConfig(
            input_csv=FIXTURES / "ambiguous_source_ownership.csv",
            output_dir=tmp_path / "output",
            pagination_report=pagination,
            mode="smoke",
            max_companies=1,
        ),
        transport=transport,
    ).run()

    assert metrics["jobs_written"] == 0
    assert metrics["ownership_exclusions"] == 2
    rows = list(csv.DictReader((tmp_path / "output" / "master_linkedin_jobs.csv").open(encoding="utf-8-sig")))
    assert rows == []
    state = StateStore(tmp_path / "output" / "master_linkedin_jobs_state.db")
    assert state.connection.execute("SELECT COUNT(*) FROM detail_queue").fetchone()[0] == 0
    assert state.connection.execute("SELECT COUNT(*) FROM ownership_exclusions WHERE reason LIKE '%ambiguous%'").fetchone()[0] == 2
    state.close()
