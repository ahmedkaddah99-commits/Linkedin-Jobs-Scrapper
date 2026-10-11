# Runr full source-state data readiness audit

Generated: `2026-09-11`

## Decision

The historical producer state is **not ready for an unqualified publish-all command**.

The previous audit was limited to the current Turso canonical tables (`299` jobs). This audit additionally scanned the authoritative RC023 producer-state databases containing the large scrape history:

- LinkedIn producer state: `188,206` jobs.
- Direct employer-site producer state: `2,612` jobs.
- Combined producer-state jobs: `190,818`.

The source-state audit used Runr contract `job_publication_completeness_v1` and the existing read-only script `audit_real_job_data.py`. No producer database was modified.

## Source-state result

| Source | Records | Publishable by current validator | Not publishable | Distinct source IDs | Duplicate source IDs |
|---|---:|---:|---:|---:|---:|
| LinkedIn | 188,206 | 42,564 | 145,642 | 188,206 | 0 |
| Direct employer sites | 2,612 | 63 | 2,549 | 2,440 | 172 |
| Combined | 190,818 | 42,627 | 148,191 | 190,646 | source-specific |

The current-validator publishable ratio is `22.3%` overall. This is not yet the final safe-to-publish ratio because of the LinkedIn application-destination issue described below.

### LinkedIn blockers

| Current validator outcome/reason | Jobs |
|---|---:|
| Publishable complete | 42,564 |
| Unresolved identity | 145,637 |
| Invalid | 5 |
| Missing canonical company ID | 145,637 |
| Insufficient description | 466 occurrences |
| Blocked/error description body | 51 occurrences |

Source metrics:

- `145,637 / 188,206` LinkedIn rows have a missing/sentinel `canonical_company_id` (`77.4%`). The producer writes `//` for unresolved identity; this is treated as missing.
- `0` rows are missing description, location, or an apply URL under the producer field mapping.
- `631` rows have `easy_apply_status=true`.
- `188,206 / 188,206` rows have a URL containing `linkedin.com/jobs/view`.

### LinkedIn application-destination blocker

The completeness contract says a user-facing job-detail URL is not an application destination. However, the source-state mapper passes the LinkedIn view URL into the flattened `apply_url` field, and the current validator only recognizes the exact `linkedin.com` hostname. Localized hosts such as `de.linkedin.com` therefore pass the URL check even though they are still job-detail pages.

This means the `42,564` LinkedIn passes are **provisional**, not safe to publish as-is. Before publishing them, the implementation must either:

1. resolve a direct employer/ATS application URL and classify it as a dedicated application destination;
2. explicitly map verified Easy Apply records to an embedded application destination; or
3. reject/quarantine the LinkedIn detail URL when no direct application destination is available.

The full source metric shows the maximum affected population is all `188,206` LinkedIn records; the exact directly-applicable subset requires the source application fields to be mapped into the validator instead of relying on the detail URL.

### Direct employer-site blockers

| Current validator outcome/reason | Jobs |
|---|---:|
| Publishable complete | 63 |
| Unresolved identity | 2,018 |
| Missing required field | 487 |
| Invalid | 41 |
| Placeholder | 3 |
| Missing canonical company ID | 2,018 |
| Missing location | 1,911 |
| Missing description | 1,404 |
| Insufficient description | 72 occurrences |
| Blocked/error description body | 3 occurrences |
| Placeholder title | 1 occurrence |

Source/application metrics:

- `1,663` rows have no explicit application URL after excluding the source job-detail fallback.
- `2,612 / 2,612` rows retain a source job-detail URL fallback.
- `172` duplicate source-job-ID occurrences exist across `2,440` distinct employer source IDs. These require dedupe/reconciliation before a publish-all operation.

## Canonical Runr/Turso state

The live canonical tables remain much smaller than the producer state:

| Dataset | Ready/publishable | Total | Main blockers |
|---|---:|---:|---|
| Current publication head | 47 | 47 | No record-level validator blocker; acquisition cycle is degraded |
| All canonical jobs | 93 | 299 | Listing fallback URL `186`; missing description `46`; closed lifecycle `35`; missing location `22`; insufficient description `6` |
| Canonical company identity | 1,428 | 1,428 | None at identity gate |
| Company presentation | 1,379 | 1,428 | Missing selected primary URL `49` |
| Company enrichment | 893 | 1,428 | Missing verified logo `525`; missing company profile `2` |

Current publication metadata:

- Publication head: `acq_publication_5ff941b21ea84b78af39a4a5cb508b3c`.
- Head status: `valid`; `47` jobs; all `47` pass the current canonical validator.
- Latest cycle: `acq_cycle_818f17433ea047c6b2c86f949cdbdd58`.
- Latest cycle status: `degraded`, error `partial_source_coverage`.
- Latest cycle observed/new/published: `0 / 0 / 47`.
- The cycle published existing state, not the full historical producer corpus.

Raw canonical-table gaps remain separate from validator outcomes:

- `canonical_jobs`: location `22`, lifecycle blank `66`, identity signature `9`, source-updated timestamp `186`.
- `job_posting_versions`: description `136`, location `54`, apply URL `411`.
- `job_source_observations`: source ATS `5`, source display name `585`, connector `585`, application URL `3,011`, application classification `613`.
- `canonical_company_profiles`: missing verified logo fields `525`.

## Company readiness and identity blockers

The canonical company table contains `1,428` stored companies and all have a canonical company ID and name. This does not mean all producer jobs resolve to those identities: the source-state sweep found `147,655` jobs with a missing canonical company ID across LinkedIn and employer-site state.

The company registry used for the source audit is:

`C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\data\acquisition\inputs\company_registry_canonical.csv`

The registry contains `17,601` canonical company rows. The largest remaining blocker is therefore the job-to-company identity bridge, not the existence of company records in the canonical table.

## Source databases audited

Authoritative historical source-state files, as documented by the Runr runtime inventory:

| Source | Absolute path | Size | Integrity/status |
|---|---|---:|---|
| LinkedIn | `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\state\linkedin\master_linkedin_jobs_state.db` | 3,479,191,552 bytes | Runtime inventory: integrity OK; 188,206 job rows |
| Employer sites | `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\state\employer\master_employer_jobs_state.db` | 83,841,024 bytes | Runtime inventory: integrity OK; 428 companies and 2,612 job rows |

Known handoff hashes recorded in the Runr RC-C handoff:

- LinkedIn SHA-256: `26b81012177f40949b6b3ede3187860129db9fdaf3392d2195d78ac050244317`.
- Employer SHA-256: `b1eee3b449afd075d9b860f12a5880da6769fcc666473bbfe8f08e7e4cb36737`.

The RC027 files were checked for scope and are only `770,048` bytes each, so they are pilot/restored subsets and were not used as the authoritative full-corpus count:

- `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc027-20260909\restored-linkedin\master_linkedin_jobs_state.db`
- `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc027-20260909\restored-from-r2-linkedin\master_linkedin_jobs_state.db`
- `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc027-20260909\offhost-linkedin\offhost-linkedin-20260909\master_linkedin_jobs_state.db`

## Remaining implementation blockers

1. Resolve or quarantine the `147,655` source jobs missing canonical company IDs.
2. Map real application destinations. Do not treat LinkedIn or employer job-detail pages as application URLs.
3. Repair employer-site missing locations (`1,911`) and descriptions (`1,404`), then revalidate.
4. Reconcile the `172` employer duplicate source-job-ID occurrences.
5. Decide whether the `466` insufficient-description, `51` blocked/error-body, `72` insufficient-description, and placeholder/error rows are fillable or should be deleted/quarantined.
6. Build a canonical ingestion/publication bridge from the producer DBs; the current Turso head contains only `299` canonical jobs and publishes `47`.
7. Require source coverage/closure evidence before declaring the acquisition catalog complete; the latest cycle is `degraded` with `partial_source_coverage`.
8. Repair or recheck the separate deployed frontend API-proxy issue: the live bundle exposed API host `${n}`, so customer Jobs UI visibility is not yet proven.

Company logos and profiles are enrichment concerns. They are useful for presentation but are not job-publication blockers under the current Runr contract.

## Exact audit outputs

- Full source-state validator JSON: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\data\audit\runr_source_state\2026-09-11\rc023-authoritative\completeness_audit_real.json`
- Full source-state validator Markdown: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\data\audit\runr_source_state\2026-09-11\rc023-authoritative\completeness_audit_real.md`
- This combined report: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\data\audit\runr_source_state\2026-09-11\full_source_state_audit_report.md`
- Canonical/Turso report: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\data\audit\runr_readiness\2026-09-11\audit_report.md`
- Canonical/Turso JSON: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\data\audit\runr_readiness\2026-09-11\audit_summary.json`
- Canonical job remediation queue: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\data\audit\runr_readiness\2026-09-11\jobs_readiness.csv`
- Canonical company remediation queue: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\data\audit\runr_readiness\2026-09-11\companies_readiness.csv`
- Production visibility evidence: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\data\audit\runr_readiness\2026-09-11\production_visibility_evidence.md`

## Scripts and source references included in the expanded ZIP

The expanded ZIP includes copies of the exact scripts and contract files used to interpret the data, including:

- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\audit_real_job_data.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\audit_job_publication_completeness.py`
- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\scripts\audit_runr_data_readiness.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\acquisition\job_publication_completeness.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\master_linkedin_jobs_catalog.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\master_employer_jobs_catalog.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\run_manifested_linkedin.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\run_manifested_employer.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\publish_producer_states.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\build_master_jobs_catalog.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\acquisition_state_backup.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\clean_master_company_url.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\apply_known_company_websites.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\linkedin_company_enrichment_pipeline.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\run_linkedin_company_id_resolution.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\acquisition\producer_adapters.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\acquisition\employer_coverage.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\audit_employer_coverage.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\backfill_company_ids.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\reconcile_company_registry.py`
- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\scripts\master_employer_jobs_catalog.py` (active scraper-worktree reference)
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\docs\ACQUISITION_RUNTIME_DATA_INVENTORY.md`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\docs\JOB_PUBLICATION_COMPLETENESS_CONTRACT.md`
- `C:\Users\ahmed\.codex\attachments\0383ee05-fb65-451e-9a36-ed608b63fda5\pasted-text.txt`

The ZIP intentionally excludes `.env` files, credentials, production databases, the 3.48 GB/83.8 MB source SQLite files, logs, caches, `node_modules`, and `.venv`.
