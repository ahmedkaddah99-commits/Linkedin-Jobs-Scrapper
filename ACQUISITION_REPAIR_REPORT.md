# Acquisition pipeline repair report

## Result

The acquisition contract is now source-backed and report-only. Scraping,
import, enrichment, intelligence, and publication do not become blocked when
a field is missing. The repair pass does not delete rows, merge ambiguous
companies, rewrite immutable posting versions, or call Crunchbase/Apollo/any
other external enrichment provider.

The configured workspace database was inspected and repaired with the safe
annotation pass:

```json
{
  "mode": "apply",
  "blocking": false,
  "records_inspected": {
    "companies": 9,
    "jobs": 139,
    "observations": 585,
    "versions": 585
  },
  "company_mappings": 0,
  "conflicts": 0,
  "manual_review": 0,
  "quality_annotations": 585,
  "redundant_version_annotations": 445,
  "application_urls_resolved": 0,
  "descriptions_processed": 585,
  "metadata_records_processed": 585,
  "timestamp_records_processed": 585,
  "intelligence_records_processed": 585,
  "provenance_records_checked": 585
}
```

The post-apply dry run remained `blocking: false`, with zero company mapping
conflicts and zero manual-review records. `application_urls_resolved` is zero
for the existing catalog because those immutable observations did not retain a
fetched job-page HTML document or a provider `applyUrl`; the repair pass cannot
invent one. New ingestion now retains the raw provider payload and extracts
HTML Apply links when HTML is available.

## Main root causes found

1. The older catalog stored a flattened record. Existing N26/Greenhouse and
   Qonto/Lever rows had the source URL, title, location, and description, but
   not the raw Greenhouse/Lever response fields such as `departments`,
   `offices`, `categories`, `salaryRange`, or Lever `applyUrl`.
2. The old `apply_link` was sometimes just the employer or ATS job-detail URL.
   It was not evidence of a direct application destination.
3. Greenhouse `updated_at` and Lever `createdAt` had previously been allowed
   to look like posting times. ATS creation/update time is now retained under
   its own timestamp semantic and is not used as `posted_age_hours`.
4. Structured description extraction existed, but field-level source
   observation ID, source URL, and observation time were not carried with each
   extracted value.
5. Unknown company facts were represented with empty provenance objects. They
   now use `value: null`, `provenance: null`, and `verified_at: null`.

## Before/after source examples

These are compact projections of real existing records. “Before” means the
immutable source observation that was available to repair; “after” means the
new report-only normalized annotation. The original immutable payload remains
available in the database.

### N26 / Greenhouse

```json
{
  "before": {
    "external_job_id": "7758692",
    "source_ats": "greenhouse",
    "original_url": "https://n26.com/en-eu/careers/positions/7758692?gh_jid=7758692",
    "raw_fields": [
      "application_method", "apply_link", "apply_link_source", "apply_url",
      "company", "description", "employer_verified", "external_job_id",
      "full_description", "job_id", "link", "location", "location_raw",
      "posted_age_hours", "posted_at", "posted_time_text", "source_ats",
      "source_url", "title", "url"
    ]
  },
  "after": {
    "job_detail_url": "https://n26.com/en-eu/careers/positions/7758692?gh_jid=7758692",
    "application_url": null,
    "application_status": "unresolved",
    "user_facing_url": "https://n26.com/en-eu/careers/positions/7758692?gh_jid=7758692",
    "source_posted_at": null,
    "posted_age_hours": null,
    "timestamp_state": "unknown",
    "timestamp_semantics": "unknown_source_timestamp",
    "department": {"value": null, "state": "unknown", "provenance": null},
    "description": {"raw": true, "sanitized_html": true, "plain_text": true},
    "warning_codes": [
      "missing_direct_application_url",
      "job_detail_url_used_as_application_url",
      "description_contains_html_entities",
      "department_not_available"
    ]
  }
}
```

### Qonto / Lever

```json
{
  "before": {
    "external_job_id": "c087ac46-54ac-4227-b9ef-5a377c35b9ab",
    "source_ats": "lever",
    "original_url": "https://jobs.lever.co/qonto/c087ac46-54ac-4227-b9ef-5a377c35ab9",
    "raw_fields": [
      "application_method", "apply_link", "apply_link_source", "apply_url",
      "company", "description", "employer_verified", "external_job_id",
      "full_description", "job_id", "link", "location", "location_raw",
      "posted_age_hours", "posted_at", "posted_time_text", "source_ats",
      "source_url", "title", "url"
    ]
  },
  "after": {
    "job_detail_url": "https://jobs.lever.co/qonto/c087ac46-54ac-4227-b9ef-5a377c35ab9",
    "application_url": null,
    "application_status": "unresolved",
    "user_facing_url": "https://jobs.lever.co/qonto/c087ac46-54ac-4227-b9ef-5a377c35ab9",
    "source_posted_at": null,
    "source_created_at": null,
    "timestamp_state": "unknown",
    "timestamp_semantics": "unknown_source_timestamp",
    "description": {"raw": true, "sanitized_html": true, "plain_text": true},
    "warning_codes": [
      "missing_direct_application_url",
      "job_detail_url_used_as_application_url",
      "department_not_available"
    ]
  }
}
```

The Qonto `2021-10-13` value that was previously presented as a posting time
was removed from the trusted posting-time projection because the old row did
not say whether it came from Lever `createdAt` or a true publication field.

## Files and schema changes

- `backend/acquisition/quality.py` — shared URL taxonomy, HTML Apply-link
  extraction, description representations, source metadata states, timestamp
  semantics, stable hashes, completeness denominator, and warnings.
- `backend/acquisition/repair.py` — dry-run/apply annotation repair, deterministic
  description intelligence, provenance checks, and idempotent warnings.
- `backend/connectors/ats_router.py` — raw Greenhouse/Lever fields, direct
  Lever `applyUrl`, typed categories/custom fields, and timestamp separation.
- `backend/capabilities/tailored_documents/manual_urls.py` — retained source
  HTML/provider payload and reusable employer/ATS Apply-link extraction.
- `backend/application/personalized_jobs_intelligence.py` — field-level
  `value`, `state`, observation ID, URL, method, and observed time.
- `backend/application/company_enrichment.py` and
  `backend/repositories/sqlite_acquisition.py` — null provenance for unknown
  company facts and read-time source posting age.
- `backend/repositories/sqlite_migrations.py` — existing additive quality
  tables `acquisition_quality_events`, `acquisition_version_quality`, source
  observation provenance columns, and company aliases remain the storage
  contract; immutable version rows are not altered.
- `scripts/repair_acquisition_catalog.py` — safe dry-run/apply entry point.
- `ACQUISITION_SOURCE_INVENTORY.md` — source-to-canonical mapping inventory.

## Warning and completeness behavior

Warnings are visible through task quality fields, quality events, version
quality reports, and admin inspection. Examples include missing direct apply
destination, job-detail URL used as apply input, suspicious/unknown source
timestamp, unavailable department, and incomplete metadata. Completeness now
includes job identity/title/location/description/detail/application,
employment/workplace, source identity/external ID/provenance/timestamp/status,
freshness, company identity/profile fields, and admin publication state. Every
rule is `blocking: false` and marked report-only.

## Verification

```text
34 passed, 11 subtests passed
ruff: All checks passed
compileall: passed
```

The targeted regression coverage includes Greenhouse, Lever, generic HTML
Apply forms, ATS URL taxonomy, description decoding, timestamp semantics,
structured extraction provenance, company enrichment, Phase B normalization,
repair idempotence, duplicate identities, and report-only completeness.

## Future source-backed enrichment

The next safe enrichment step is to fetch and retain the employer job-detail
HTML through the configured ScrapeOps request policy for providers that do not
return an `applyUrl` (especially Greenhouse). The existing HTML resolver can
then promote only an actual employer/ATS form or Apply link. If the page does
not expose one, the system will keep the detail URL and warning. No AI
per-record URL guessing and no external company database are required.
