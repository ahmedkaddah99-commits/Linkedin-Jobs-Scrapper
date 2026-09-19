# Runr data completion and publication-readiness audit

Generated: `2026-09-11T10:35:39.152096+00:00`
Decision: **CURRENT_HEAD_PUBLISHABLE_BUT_CATALOG_INCOMPLETE**

## Scope

- Live database backend: `libsql`
- Current publication head: `acq_publication_5ff941b21ea84b78af39a4a5cb508b3c`
- Current publication status: `valid`
- Current publication jobs: `47`
- Latest acquisition cycle: `acq_cycle_818f17433ea047c6b2c86f949cdbdd58` (`degraded`)
- Latest cycle observed/new/published: `0/0/47`
- All canonical jobs stored: `299`
- All canonical companies stored: `1428`
- Validator contract: `job_publication_completeness_v1`

The audit evaluates the live canonical tables and the current publication head. It does not infer completeness from collector success, source-scan completion, or a previous migration report.

## Executive result

- Current head: `47/47` jobs pass the production completeness validator.
- All stored canonical jobs: `93/299` pass the same validator.
- Canonical company identity-ready: `1428/1428`.
- Company presentation-ready with selected primary URL: `1379/1428`.
- Company enrichment-complete under the audit’s non-blocking enrichment definition: `893/1428`.
- Companies referenced by the current head: `2`; head-referenced companies with a selected primary URL: `2`.

## Current-head blockers

### Reason counts

| Reason | Jobs |
|---|---:|

### Status counts

| Status | Jobs |
|---|---:|
| `publishable_complete` | 47 |

A job is publishable only when its canonical identity, company identity, title, direct application destination, description, location/remote classification, source identity, freshness, and lifecycle checks pass. Recommended fields such as salary, benefits, seniority, and logos are not publication blockers in the contract.

## Raw field gaps across stored tables

These counts are row-level storage gaps, including non-head and historical rows. They are separate from the validator outcome counts above.

### `canonical_jobs`

| Field | Missing/sentinel rows |
|---|---:|
| `canonical_job_id` | 0 |
| `company_id` | 0 |
| `identity_key` | 0 |
| `title` | 0 |
| `location` | 22 |
| `canonical_url` | 0 |
| `lifecycle_state` | 66 |
| `last_verified_at` | 0 |
| `current_version_id` | 0 |
| `identity_signature` | 9 |
| `source_updated_at` | 186 |

### `canonical_companies`

| Field | Missing/sentinel rows |
|---|---:|
| `company_id` | 0 |
| `canonical_name` | 0 |
| `entity_kind` | 0 |
| `provenance_url` | 2 |

### `canonical_company_profiles`

| Field | Missing/sentinel rows |
|---|---:|
| `company_id` | 0 |
| `profile_json` | 0 |
| `logo_object_key` | 525 |
| `logo_source_url` | 525 |
| `logo_verified_at` | 525 |
| `profile_status` | 0 |

### `canonical_company_urls`

| Field | Missing/sentinel rows |
|---|---:|
| `company_id` | 0 |
| `url_type` | 0 |
| `url` | 0 |
| `canonical_url` | 0 |
| `validation_status` | 0 |
| `selected_primary` | 0 |

### `job_posting_versions`

| Field | Missing/sentinel rows |
|---|---:|
| `version_id` | 0 |
| `canonical_job_id` | 0 |
| `version_number` | 0 |
| `content_hash` | 0 |
| `title` | 0 |
| `description` | 136 |
| `location` | 54 |
| `apply_url` | 411 |
| `source_observation_id` | 0 |
| `payload_json` | 0 |

### `job_source_observations`

| Field | Missing/sentinel rows |
|---|---:|
| `observation_id` | 0 |
| `canonical_job_id` | 0 |
| `target_id` | 0 |
| `cycle_id` | 0 |
| `task_id` | 0 |
| `external_job_id` | 0 |
| `original_url` | 0 |
| `apply_url` | 0 |
| `source_ats` | 5 |
| `content_hash` | 0 |
| `payload_json` | 0 |
| `observed_at` | 0 |
| `source_display_name` | 585 |
| `source_connector` | 585 |
| `application_url` | 3011 |
| `application_classification` | 613 |

## All stored-job gaps

| Status | Jobs |
|---|---:|
| `not_publishable_invalid` | 170 |
| `publishable_complete` | 93 |
| `stale_or_closed` | 35 |
| `not_publishable_missing_required` | 1 |

| Reason | Jobs |
|---|---:|
| `listing_fallback_application_url` | 186 |
| `missing_description` | 46 |
| `closed_lifecycle_state` | 35 |
| `missing_location` | 22 |
| `insufficient_description` | 6 |

## Company readiness

| Gate | Ready | Total |
|---|---:|---:|
| Canonical identity (ID + name) | 1428 | 1428 |
| Presentation (identity + selected primary URL) | 1379 | 1428 |
| Enrichment (presentation + profile + verified logo) | 893 | 1428 |

| Company blocker | Companies |
|---|---:|
| `missing_verified_logo` | 525 |
| `missing_selected_primary_url` | 49 |
| `missing_company_profile` | 2 |

## Interpretation and implementation queue

1. Fix or quarantine every current-head job listed in `jobs_readiness.csv` with a non-publishable status. The CSV is the fill/delete decision queue, keyed by canonical job ID.
2. Do not treat missing company profiles, logos, or selected company URLs as interchangeable with missing canonical identity. The report separates those gates so deletion is not used for optional enrichment gaps.
3. Re-run this audit after remediation and require the current head to be 100% `publishable_complete` before calling the catalog complete.
4. Keep the separate operational frontend/API-proxy failure in the deployment checklist; it is not a data-field count but can prevent customers from seeing an otherwise valid publication.

## Evidence and absolute paths

- collector_root: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper`
- runr_root: `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview`
- env_file_used_redacted: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\user_config\.env`
- migration_transcript: `C:\Users\ahmed\.codex\attachments\0383ee05-fb65-451e-9a36-ed608b63fda5\pasted-text.txt`
- runr_completeness_contract: `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\docs\JOB_PUBLICATION_COMPLETENESS_CONTRACT.md`
- runr_completeness_validator: `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\acquisition\job_publication_completeness.py`
- audit_script: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\scripts\audit_runr_data_readiness.py`
- json_report: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\data\audit\runr_readiness\2026-09-11\audit_summary.json`
- markdown_report: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\data\audit\runr_readiness\2026-09-11\audit_report.md`
- jobs_queue: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\data\audit\runr_readiness\2026-09-11\jobs_readiness.csv`
- companies_queue: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\data\audit\runr_readiness\2026-09-11\companies_readiness.csv`
- zip_bundle: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\RUNR_DATA_READINESS_AUDIT_2026-09-11.zip`

## Audit caveat

The company readiness gates are an audit classification for remediation. The Runr job publication contract is authoritative for job publication; company logo/profile enrichment is explicitly optional/non-blocking there.
