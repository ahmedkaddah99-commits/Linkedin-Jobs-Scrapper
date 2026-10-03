# Runr data completion and publication-readiness audit

Generated: `2026-09-22T10:25:57.123739+00:00`
Decision: **NOT_PUBLISHABLE_AS_COMPLETE**

## Scope

- Live database backend: `libsql`
- Current publication head: `acq_republish_872faf4172f4456db85b0e93984d367d`
- Current publication status: `valid`
- Current publication jobs: `6335`
- Latest acquisition cycle: `acq_cycle_d4154222ec84435792421b5d4924e577` (`running`)
- Latest cycle observed/new/published: `0/0/0`
- All canonical jobs stored: `6370`
- All canonical companies stored: `18994`
- Validator contract: `job_publication_completeness_v1`

The audit evaluates the live canonical tables and the current publication head. It does not infer completeness from collector success, source-scan completion, or a previous migration report.

## Executive result

- Current head: `0/6335` jobs pass the production completeness validator.
- All stored canonical jobs: `0/6370` pass the same validator.
- Canonical company identity-ready: `18994/18994`.
- Company presentation-ready with selected primary URL: `1379/18994`.
- Company enrichment-complete under the audit’s non-blocking enrichment definition: `893/18994`.
- Companies referenced by the current head: `218`; head-referenced companies with a selected primary URL: `14`.

## Current-head blockers

### Reason counts

| Reason | Jobs |
|---|---:|
| `missing_company_enrichment` | 6335 |
| `missing_company_logo` | 6335 |
| `missing_employment_type` | 6335 |
| `missing_seniority` | 6335 |
| `missing_workplace_arrangement` | 6335 |
| `listing_fallback_application_url` | 165 |
| `missing_description` | 46 |
| `missing_location` | 22 |
| `insufficient_description` | 6 |

### Status counts

| Status | Jobs |
|---|---:|
| `not_publishable_missing_required` | 6165 |
| `not_publishable_invalid` | 170 |

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
| `source_updated_at` | 6257 |

### `canonical_companies`

| Field | Missing/sentinel rows |
|---|---:|
| `company_id` | 0 |
| `canonical_name` | 0 |
| `entity_kind` | 0 |
| `provenance_url` | 16 |

### `canonical_company_profiles`

| Field | Missing/sentinel rows |
|---|---:|
| `company_id` | 0 |
| `profile_json` | 0 |
| `logo_object_key` | 832 |
| `logo_source_url` | 832 |
| `logo_verified_at` | 832 |
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
| `apply_url` | 6482 |
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
| `application_url` | 9101 |
| `application_classification` | 6703 |

## All stored-job gaps

| Status | Jobs |
|---|---:|
| `not_publishable_missing_required` | 6165 |
| `not_publishable_invalid` | 170 |
| `stale_or_closed` | 35 |

| Reason | Jobs |
|---|---:|
| `missing_company_enrichment` | 6370 |
| `missing_company_logo` | 6370 |
| `missing_employment_type` | 6370 |
| `missing_seniority` | 6370 |
| `missing_workplace_arrangement` | 6370 |
| `listing_fallback_application_url` | 186 |
| `missing_description` | 46 |
| `closed_lifecycle_state` | 35 |
| `missing_location` | 22 |
| `insufficient_description` | 6 |

## Company readiness

| Gate | Ready | Total |
|---|---:|---:|
| Canonical identity (ID + name) | 18994 | 18994 |
| Presentation (identity + selected primary URL) | 1379 | 18994 |
| Enrichment (presentation + profile + verified logo) | 893 | 18994 |

| Company blocker | Companies |
|---|---:|
| `missing_selected_primary_url` | 17615 |
| `missing_company_profile` | 17261 |
| `missing_verified_logo` | 832 |

## Interpretation and implementation queue

1. Fix or quarantine every current-head job listed in `jobs_readiness.csv` with a non-publishable status. The CSV is the fill/delete decision queue, keyed by canonical job ID.
2. Do not treat missing company profiles, logos, or selected company URLs as interchangeable with missing canonical identity. The report separates those gates so deletion is not used for optional enrichment gaps.
3. Re-run this audit after remediation and require the current head to be 100% `publishable_complete` before calling the catalog complete.
4. Keep the separate operational frontend/API-proxy failure in the deployment checklist; it is not a data-field count but can prevent customers from seeing an otherwise valid publication.

## Evidence and absolute paths

- collector_root: `C:\Users\ahmed\Projects_Local\job-automation\runr-t33-producer-state-reconciliation`
- runr_root: `C:\Users\ahmed\Projects_Local\job-automation\runr-t33-producer-state-reconciliation`
- env_file_used_redacted: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\user_config\.env`
- migration_transcript: `C:\Users\ahmed\.codex\attachments\0383ee05-fb65-451e-9a36-ed608b63fda5\pasted-text.txt`
- runr_completeness_contract: `C:\Users\ahmed\Projects_Local\job-automation\runr-t33-producer-state-reconciliation\docs\JOB_PUBLICATION_COMPLETENESS_CONTRACT.md`
- runr_completeness_validator: `C:\Users\ahmed\Projects_Local\job-automation\runr-t33-producer-state-reconciliation\backend\acquisition\job_publication_completeness.py`
- audit_script: `C:\Users\ahmed\Projects_Local\job-automation\runr-t33-producer-state-reconciliation\scripts\audit_runr_data_readiness.py`
- json_report: `C:\Users\ahmed\Projects_Local\job-automation\runr-t33-producer-state-reconciliation\data\audit\runr_readiness\2026-09-22\audit_summary.json`
- markdown_report: `C:\Users\ahmed\Projects_Local\job-automation\runr-t33-producer-state-reconciliation\data\audit\runr_readiness\2026-09-22\audit_report.md`
- jobs_queue: `C:\Users\ahmed\Projects_Local\job-automation\runr-t33-producer-state-reconciliation\data\audit\runr_readiness\2026-09-22\jobs_readiness.csv`
- companies_queue: `C:\Users\ahmed\Projects_Local\job-automation\runr-t33-producer-state-reconciliation\data\audit\runr_readiness\2026-09-22\companies_readiness.csv`

## Audit caveat

The company readiness gates are an audit classification for remediation. The Runr job publication contract is authoritative for job publication; company logo/profile enrichment is explicitly optional/non-blocking there.
