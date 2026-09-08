# RC-001 baseline and input contract

Status: completed locally on 2026-09-06

Target worktree: `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview`

Target branch: `deployment/render-turso-r2`

Recorded starting commit: `e7662c63082d605d8ae6de090d3a04a55bba6556`

This is the offline evidence record for RC-001a and RC-001b. It does not claim a
production revision, a deployed input, live source coverage, or provider capacity.
No production request, paid enrichment, deployment, push, pull, reset, merge, or
branch reconciliation was performed.

## Worktree provenance

| Worktree | Branch | HEAD | Status at RC-001 start | Use |
| --- | --- | --- | --- | --- |
| `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview` | `deployment/render-turso-r2` | `e7662c63082d605d8ae6de090d3a04a55bba6556` | Three pre-existing modified exporter files; RC-001 files are now untracked | Integration target |
| `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper` | `feature/admin-analytics-final-production` | `0c4c4791a710c4575299d65923b03aca0e466721` | Dirty and untracked; reported `ahead 14, behind 37` | Read-only source reference |
| `C:\w\mlj` | `codex/master-linkedin-jobs-url` | `6d0fca4d944328f4366daddbf1ca8dadba002733` | Clean | Read-only producer reference |

The target's pre-existing modified files were preserved:

- `scripts/build_master_jobs_catalog.py`
- `scripts/master_employer_jobs_catalog.py`
- `tests/test_master_employer_jobs_catalog.py`

The source worktrees were not edited.

## Active master input

The active local input used for the baseline is:

`Company-Urls/Master-Company-Url/cleaned/Master-Company-Url-canonical_cleaned_linkedin_ids.csv`

Current local absolute path:

`C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\Company-Urls\Master-Company-Url\cleaned\Master-Company-Url-canonical_cleaned_linkedin_ids.csv`

| Property | Observed value |
| --- | ---: |
| Rows | 17,601 |
| Columns | 118 |
| Bytes | 18,807,047 |
| SHA-256 | `7f416ec6ebbcb936a42061ef0adaa07e4a6c04d2959d0eb579779126682440d9` |
| Encoding used for validation | UTF-8 with optional BOM, CSV newline handling |

The exact 118-field header is preserved in that file. Its contract-critical
spellings include `canonical_CompanyID`, `companyenrich_id`, `company_name`,
`website_url`, `linkedin_company_url`, `linkedin_slug`, `linkedin_company_id`,
`linkedin_company_id_status`, `linkedin_company_id_source`,
`linkedin_company_id_confidence`, `linkedin_company_id_resolved_at`,
`linkedin_company_id_transport`, `linkedin_company_id_url_used`, `Column1`-
`Column9`, `companyenrich_free_logo_url`, and `website_discovery_status`; all
other columns are preserved as unknown input fields.

The complete observed header, in order, is:

```text
canonical_CompanyID,companyenrich_id,merge_basis,company_name,website_url,linkedin_company_url,linkedin_slug,linkedin_page_type,headquarters_city,headquarters_region,headquarters_country,headquarters_country_code,headquarters_display,locations_1_address,locations_1_city_id,locations_1_city_latitude,locations_1_city_longitude,locations_1_city_name,locations_1_country_code,locations_1_country_latitude,locations_1_country_longitude,locations_1_country_name,locations_1_phone,locations_1_postal_code,locations_1_state_code,locations_1_state_id,locations_1_state_latitude,locations_1_state_longitude,locations_1_state_name,industry,industries_1,industries_2,industries_3,industries_4,industries_5,industries_6,categories_1,categories_2,categories_3,company_type,employee_count_range,employee_count_source,founded_year,revenue_range,description,seo_description,keywords_1,keywords_2,keywords_3,keywords_4,keywords_5,keywords_6,keywords_7,keywords_8,keywords_9,keywords_10,keywords_11,keywords_12,keywords_13,keywords_14,keywords_15,keywords_16,keywords_17,keywords_18,keywords_19,keywords_20,keywords_21,keywords_22,keywords_23,keywords_24,keywords_25,keywords_26,keywords_27,technologies_1,technologies_2,technologies_3,technologies_4,technologies_5,technologies_6,technologies_7,technologies_8,technologies_9,technologies_10,technologies_11,technologies_12,technologies_13,technologies_14,technologies_15,technologies_16,naics_codes_1,naics_codes_2,naics_codes_3,naics_codes_4,naics_codes_5,logo_url,logo_source,page_rank,record_sources,enrichment_status,last_enriched_at,linkedin_company_id,linkedin_company_id_status,linkedin_company_id_source,linkedin_company_id_confidence,linkedin_company_id_resolved_at,linkedin_company_id_transport,linkedin_company_id_url_used,Column1,Column2,Column3,Column4,Column5,Column6,Column7,Column8,Column9,companyenrich_free_logo_url,website_discovery_status
```

The target worktree intentionally does not receive the large local data files.
Collectors must receive their input/state paths explicitly or through their
existing configurable defaults when data is mounted in a runtime environment.

## Validity rules and readiness baseline

These are presence/shape checks, not evidence verification:

- **C (canonical ID):** non-empty after trimming and not the placeholder `//`.
  The only placeholder observed in this file is `//`.
- **W (website):** an HTTP(S) URL with a non-empty host. This records a URL
  value only; it does not prove ownership, reachability, or that it is a
  company website.
- **L (LinkedIn URL):** an HTTP(S) URL whose host ends in `linkedin.com` and
  whose path is non-empty. Both `/company/` and `/school/` URLs are retained as
  LinkedIn URLs; later eligibility rules decide which are organization sources.
- **I (numeric LinkedIn ID):** ASCII decimal digits only in
  `linkedin_company_id`.

The reproduced ten-bucket matrix is:

| C | W | L | I | Rows |
| --- | --- | --- | --- | ---: |
| Yes | Yes | Yes | Yes | 1,666 |
| Yes | Yes | Yes | No | 1,404 |
| Yes | Yes | No | No | 2,138 |
| Yes | No | Yes | Yes | 705 |
| Yes | No | Yes | No | 1,591 |
| Yes | No | No | No | 9 |
| No | Yes | Yes | Yes | 4,371 |
| No | Yes | Yes | No | 136 |
| No | No | Yes | Yes | 5,317 |
| No | No | Yes | No | 264 |
| **Total** |  |  |  | **17,601** |

Aggregate checks from the same file:

- 7,513 rows have an existing canonical ID; 10,088 have the `//` placeholder.
- 1,666 rows have all four C/W/L/I fields present under the rules above.
- 4,371 rows have W/L/I but no C and are the identity-first expansion cohort.
- 7,886 rows have no website URL; 2,147 have no LinkedIn URL.
- 5,542 rows have no valid numeric LinkedIn ID.
- There are 11,907 unique numeric LinkedIn organization IDs.
- 37 numeric LinkedIn organizations map to more than one existing canonical ID;
  these require ownership review and must not be assigned by `ids[0]`.

Presence is not verification. These counts do not establish source ownership,
freshness, Germany coverage, or a promised eligible-company count.

## Input lineage assessment

| Representation | Rows | Columns | Bytes | SHA-256 | Assessment |
| --- | ---: | ---: | ---: | --- | --- |
| `Company-Urls/Master-Company-Url/Master-Company-Url.csv` | 9,129 | 82 | 17,491,851 | `680b4c5cd1fb9309e81f04d8e8ee3b28aba0af154dc70811ca716654231967fc` | Original master population; not row-count equivalent to the active cleaned input |
| `Company-Urls/Master-Company-Url/cleaned/Master-Company-Url-canonical_cleaned.csv` | 17,601 | 42 | 11,986,132 | `31ed996ab2b2d0723b00a6634cdcba02901862f95ffb1b2f3c9d8432bb457446` | Canonical cleaned representation; contains source-row metadata |
| `Company-Urls/Master-Company-Url/cleaned/Master-Company-Url-canonical_cleaned_linkedin_ids.csv` | 17,601 | 118 | 18,807,047 | `7f416ec6ebbcb936a42061ef0adaa07e4a6c04d2959d0eb579779126682440d9` | Active flattened input for the LinkedIn producer |
| `Company-Urls/production-enriched-companies/enriched_companies.csv` | 1,388 | 38 | 9,461,117 | `504427fd7d9178f32a24f68072fac27746ee64962fbc081c7d09fd41ae9c386e` | Separate production-enriched population; not a substitute for the active master |

The row-count differences show that these files are different populations or
pipeline stages. `source_row_numbers` is useful lineage evidence but does not
prove complete row-level correspondence to the original file. The available
evidence does not establish how every missing canonical ID arose, so this
record does not attribute missing IDs to the cleaner.

## Producer and export contract

The actual LinkedIn producer is
`scripts/master_linkedin_jobs_catalog.py`. Its target-worktree SHA-256 is
`ab2bb8ef64164f27d578425c3e4346d0b6de35ffd10a4cdfd6ae43b8f8bd2c9b`, exactly
matching the reported original hash and the byte-identical file at
`C:\w\mlj\scripts\master_linkedin_jobs_catalog.py`. It was already present on
the target and was retained; the sanitized evidence source was not copied into
executable code.

Its `StateStore` defines the observed 14-table model:

`runs`, `source_company_groups`, `company_slug_aliases`, `company_scans`,
`query_partitions`, `search_pages`, `search_cards`, `jobs`,
`job_company_observations`, `detail_queue`, `detail_attempts`,
`ownership_exclusions`, `lifecycle_events`, and `proxy_health`.

The producer exposes 46 authoritative catalog fields. The target projection
retains those fields, then adds legacy URL-catalog fields for compatibility and
employer fields. `scripts/master_linkedin_jobs_url_catalog.py` remains a
separate legacy implementation and is not substituted as a producer or added
to live entrypoints.

The existing target employer/export changes are retained, not reimplemented:

- `master_employer_jobs_catalog.py` retains checkpoint-backed state,
  streaming/validated exports, and `--export-only` regeneration.
- `build_master_jobs_catalog.py` retains the producer-field projection,
  streaming rows, temporary validation, and atomic replacement.
- `tests/test_master_employer_jobs_catalog.py` retains the corresponding
  checkpoint/export regression coverage.

The primary-branch versions of those files remain read-only references; their
different hashes were not copied over the target's dirty versions.

## Missing evidence and explicit deferrals

- The deployed production revision and deployed input mapping remain unverified.
- No live HTTP, proxy, browser, ScrapeOps, or paid enrichment request was made.
- The local data files and scraper state databases are not committed to the
  target; they must be mounted/configured separately at runtime.
- Provider limits, actual live capacity, costs, and current source coverage are
  RC-002 and later release-gate concerns.
- The exact historical shell command that produced the large state snapshots is
  not recorded.

## Offline validation

The target worktree has no local `.venv` directory. The repository's existing
project interpreter was used and verified as Python 3.12.7:

`C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe`

All seven consolidated script entry points returned exit code 0 for `--help`.
The focused acquisition/identity/producer suite passed:

```text
116 passed in 9.58s
```

The validation imported only local code and fixtures. It made no external
requests and did not modify the input data or scraper state.
