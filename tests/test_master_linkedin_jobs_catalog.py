from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.master_linkedin_jobs_catalog import (
    COMPANY_MATCH_CARD_DETAIL_MISMATCH,
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
    build_search_url,
    build_recovery_partitions,
    AdaptiveConcurrency,
    CatalogRunner,
    ResponseEnvelope,
    RunnerConfig,
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
    detail_refresh_required,
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
    store = StateStore(tmp_path / "state.db")
    store.upsert_catalog_row(make_catalog_row())

    store.reconcile_lifecycle("22", "scan-partial", "PARTIAL_PAGE", set(), "2026-09-01T08:00:00Z")
    assert store.get_catalog_row("22", "1234567890")["absence_count"] == "0"
    store.reconcile_lifecycle("22", "scan-complete-1", "COMPLETE", set(), "2026-09-02T08:00:00Z")
    assert store.get_catalog_row("22", "1234567890")["absence_count"] == "1"
    assert store.get_catalog_row("22", "1234567890")["lifecycle_status"] == "active"
    store.reconcile_lifecycle("22", "scan-complete-2", "COMPLETE", set(), "2026-09-03T08:00:00Z")
    assert store.get_catalog_row("22", "1234567890")["lifecycle_status"] == "inactive"
    store.reconcile_lifecycle("22", "scan-complete-3", "COMPLETE", {"1234567890"}, "2026-09-04T08:00:00Z")
    row = store.get_catalog_row("22", "1234567890")
    assert row["lifecycle_status"] == "active"
    assert row["absence_count"] == "0"
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
    assert second["detail_successes"] == 1
    assert sum(kind == "search" for _, kind in second_transport.urls) == 2
    assert sum(kind == "detail" for _, kind in second_transport.urls) == 1


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
    transport = ScriptedTransport(search_body=(FIXTURES / "linkedin_job_search_valid.html").read_text())
    config = RunnerConfig(input_csv=source, output_dir=tmp_path / "output", pagination_report=pagination, filters_report=filters, mode="smoke", max_companies=1)

    metrics = CatalogRunner(config, transport=transport).run()

    assert metrics["companies_completed"] == 1
    assert any("f_TPR=r3600" in url for url, kind in transport.urls if kind == "search")
