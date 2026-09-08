from scripts.run_linkedin_company_id_resolution import (
    all_jobs_href,
    company_jobs_href,
    contextual_company_ids,
    existing_social_id_payload,
)


def test_contextual_company_ids_reads_id_from_clicked_jobs_url() -> None:
    ids, evidence = contextual_company_ids(
        "",
        "https://www.linkedin.com/jobs/search/?f_C=123456789",
    )

    assert ids == ["123456789"]
    assert evidence == ["linkedin_jobs_f_C"]


def test_all_jobs_href_finds_rendered_link_and_resolves_relative_url() -> None:
    html = """
    <html><body>
      <a aria-label="Show all jobs" href="/jobs/search/?f_C=123456789">Show all jobs</a>
    </body></html>
    """

    assert all_jobs_href(html, "https://www.linkedin.com/company/example/") == (
        "https://www.linkedin.com/jobs/search/?f_C=123456789"
    )


def test_company_jobs_href_finds_company_jobs_tab() -> None:
    html = """
    <html><body>
      <a href="/jobs/search?trk=organization_guest_guest_nav_menu_jobs">Jobs</a>
      <a href="/company/example/jobs/">Jobs</a>
    </body></html>
    """

    assert company_jobs_href(html, "https://www.linkedin.com/company/example/") == (
        "https://www.linkedin.com/company/example/jobs/"
    )


def test_all_jobs_href_ignores_generic_jobs_navigation() -> None:
    html = '<a href="/jobs/search?trk=organization_guest_guest_nav_menu_jobs">Jobs</a>'

    assert all_jobs_href(html, "https://www.linkedin.com/company/example/") == ""


def test_existing_social_id_payload_uses_one_consistent_source_id() -> None:
    group = {"normalized_url": "https://www.linkedin.com/company/example/", "linkedin_slug": "example", "source_row_numbers": [2], "row_indices": [0], "canonical_company_ids": []}
    rows = [{"linkedin_company_id": "", "socials_json": '[{"linkedin_id":"987654","linkedin_url":"https://www.linkedin.com/company/example"}]'}]

    payload = existing_social_id_payload(group, rows)

    assert payload is not None
    assert payload["output_fields"]["linkedin_company_id"] == "987654"
    assert payload["output_fields"]["linkedin_company_id_source"] == "existing_socials_json"
