from scripts.summarize_employer_coverage import summarize


def test_summarize_reports_aggregate_company_job_and_method_outcomes() -> None:
    payload = {
        "by_classification": {
            "confirmed_complete": [
                {
                    "terminal_classification": "confirmed_complete",
                    "persisted_job_count": 3,
                    "attempts": [
                        {
                            "connector_family": "ats_expansion",
                            "accepted_count": 3,
                            "pages_attempted": 2,
                            "pending_detail_count": 1,
                            "complete": True,
                        }
                    ],
                }
            ],
            "failed": [
                {
                    "terminal_classification": "failed",
                    "persisted_job_count": 0,
                    "attempts": [
                        {
                            "connector_family": "static_html",
                            "accepted_count": 0,
                            "complete": False,
                        }
                    ],
                }
            ],
        }
    }

    result = summarize(payload)

    assert result["companies"]["total"] == 2
    assert result["companies"]["outcomes"]["confirmed_complete"] == {
        "count": 1,
        "percentage": 50.0,
    }
    assert result["jobs"]["persisted"] == 3
    assert result["methods"]["ats_expansion"]["success_with_jobs_percentage"] == 100.0
    assert result["methods"]["ats_expansion"]["listing_pages_fetched"] == 2
    assert result["methods"]["ats_expansion"]["detail_failures"] == 1
    assert result["methods"]["static_html"]["unsuccessful_percentage"] == 100.0
