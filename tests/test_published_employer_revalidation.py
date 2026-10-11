from __future__ import annotations

import json
import sqlite3

from scripts.revalidate_published_employer_jobs import classify_head, job_identity, load_producer_evidence


def test_bonava_www_source_matches_catalog_url_and_is_removed() -> None:
    bonava = {"canonical_job_id": "bonava-service", "title": "Service",
              "canonical_url": "https://bonava.de/service"}
    linkedin = {"canonical_job_id": "linkedin-role", "title": "Data Engineer",
                "canonical_url": "https://linkedin.com/jobs/view/123"}
    evidence = {job_identity("https://www.bonava.de/service", "Service"): True}

    retained, removed, counts = classify_head([bonava, linkedin], evidence, {})

    assert retained == [linkedin]
    assert removed == [bonava]
    assert counts["producer_rejected"] == 1


def test_matching_valid_producer_evidence_preserves_job() -> None:
    job = {"canonical_job_id": "engineer", "title": "Data Engineer",
           "canonical_url": "https://example.com/jobs/42"}
    evidence = {job_identity("https://www.example.com/jobs/42", "Data Engineer"): False}

    retained, removed, _ = classify_head([job], evidence, {})

    assert retained == [job]
    assert removed == []


def test_conflicting_producer_rows_hold_unverified_page(tmp_path) -> None:
    db_path = tmp_path / "employer.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE jobs (payload_json TEXT NOT NULL)")
        for provider in ("generic_employer_site", "greenhouse"):
            connection.execute("INSERT INTO jobs (payload_json) VALUES (?)", (json.dumps({
                "source_provider": provider, "extraction_method": "embedded_json",
                "job_title": "Service", "source_job_url": "https://www.bonava.de/service",
            }),))
    evidence = load_producer_evidence(db_path)
    assert evidence[job_identity("https://bonava.de/service", "Service")] is True
