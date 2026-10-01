from __future__ import annotations

from scripts.revalidate_published_employer_jobs import classify_head, job_identity


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
