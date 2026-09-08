# Scraper Source Baseline Recovery Manifest

Recovery date: 2026-09-05. This manifest records source provenance and database comparison only. No scraper execution, network request, optimization, migration, deployment, push, merge, or rebase was performed.

## Producer conclusions

| Pipeline | Best-supported producer | Evidence | Confidence |
| --- | --- | --- | --- |
| Employer career sites | `scripts/master_employer_jobs_catalog.py` from the captured working tree | Its `EmployerState` creates exactly `companies` and `jobs`, matching the 83,841,024-byte database schema. The source was modified at `2026-08-31T17:01:19.7234277Z`, its Python 3.12 bytecode was compiled at `17:01:21Z`, and the full-run log begins at `19:01:53` local time. | High for schema/behavior; medium for exact historical bytes because no committed predecessor is present. |
| LinkedIn | `scripts/master_linkedin_jobs_catalog.py` at `codex/master-linkedin-jobs-url`, commit `6d0fca4d944328f4366daddbf1ca8dadba002733` | Its `StateStore` creates the exact 14-table model found in the 3,479,191,552-byte database, including company scans, partitions, pages, cards, detail queue/attempts, observations, lifecycle events, exclusions, and proxy health. | High |
| Combined projection | `scripts/build_master_jobs_catalog.py` | Reads the two source CSVs, normalizes them, concatenates LinkedIn then employer rows, and does not cross-deduplicate. This is intentionally not treated as a database producer. | High for projection behavior |

The current untracked `scripts/master_linkedin_jobs_url_catalog.py` is not the producer of the large LinkedIn database: it defines `source_companies`, `search_pages`, `detail_attempts`, `job_observations`, and a different `jobs` key, while the real database defines the 14-table `StateStore` model above. It is retained only as the current combined-projection dependency/candidate and is not silently substituted for the recovered producer.

## Candidate hashes

| Candidate | Size | SHA-256 | Modification/source evidence |
| --- | ---: | --- | --- |
| `scripts/master_employer_jobs_catalog.py` | 40,114 | `ff9eb18697e2e1ff785a2f758cede7342421f6630dfe7be7e519b31de072bfb6` | `2026-08-31T17:01:19.7234277Z` |
| `scripts/master_linkedin_jobs_url_catalog.py` | 71,619 | `c1a3e492bf91c830fb477e0dd124c681ad9074cd22c52ff4344ee73c81792940` | `2026-08-31T09:28:34.0308002Z`; schema mismatch |
| `scripts/build_master_jobs_catalog.py` | 5,153 | `91546319022efb14ab64c96938fa4d7368c99c671eda44812a2f6a8adb27e7d1` | `2026-08-31T09:29:10.6661536Z` |
| `codex/master-linkedin-jobs-url:scripts/master_linkedin_jobs_catalog.py` | 111,283 | `ab2bb8ef64164f27d578425c3e4346d0b6de35ffd10a4cdfd6ae43b8f8bd2c9b` | Worktree `C:\w\mlj`, `2026-08-31T02:05:09.2974055Z`; Git blob `a15786c8f7ade0e5f9459a91eb8103e805052586` |
| `Jobs-Urls/linkedin_germany_discovery.py` | 52,679 | `87edf1111d6697504d9c7afc98f3ba46fad6d9a364adb4373f15c1f9fc012c35` | Historical predecessor; different schema |
| `Jobs-Urls/linkedin_germany_adaptive.py` | 169,869 | `76ab01aadeeef0ffe415eb1cbc933640b5d8626f1ad7c81668356aa1aefef79a` | Historical predecessor; different schema |
| `Jobs-Urls/archive/2026-08-21/linkedin_germany_adaptive_v1.py` | 61,770 | `387f9ae54f7ae8be685fbaab2a5eda5e7864ac95ef7f8de315f9e702156496a6` | Archived predecessor; different schema |

## Database comparison

Employer state database: `Jobs-Urls/master linkedin jobs url/master_employer_jobs_state.db`, 83,841,024 bytes, SHA-256 `b1eee3b449afd075d9b860f12a5880da6769fcc666473bbfe8f08e7e4cb36737`. Tables are `companies` (428 rows) and `jobs` (2,612 rows), with the exact columns and primary keys created by the recovered employer source.

LinkedIn state database: `Jobs-Urls/master linkedin jobs url/master_linkedin_jobs_state.db`, 3,479,191,552 bytes, SHA-256 `26b81012177f40949b6b3ede3187860129db9fdaf3392d2195d78ac050244317`. Tables and row counts are: `company_scans` 11,921; `company_slug_aliases` 312; `detail_attempts` 198,493; `detail_queue` 198,491; `job_company_observations` 188,206; `jobs` 188,206; `lifecycle_events` 187,415; `ownership_exclusions` 8,689; `proxy_health` 0; `query_partitions` 42; `runs` 2; `search_cards` 198,491; `search_pages` 52,386; `source_company_groups` 11,896. The recovered source defines all 14 tables and the observed lifecycle/ownership transitions.

Archived predecessor database: `Jobs-Urls/archive/2026-08-21/linkedin_germany_discovery_state_pre_v2.db`, 2,038,747,136 bytes, SHA-256 `01559b47d6ca0e0e1c8186e8d3de0ebd6fa2214149043c1bfb42f58ceaf9304d`. Its tables are `discovery_provenance`, `jobs_seen`, `meta`, `proxy_stats`, `query_nodes`, and `query_stats`; it is not the producer of the current 14-table database.

Complete SQL schemas, indexes, constraints, pragmas, run/status aggregates, sanitized samples, and database hashes are retained in the previously created diagnostic ZIP and were rechecked read-only during this recovery.

## Required local import map

Employer transitive local modules: `backend.acquisition.network_policy`, `backend.acquisition.quality`, `backend.acquisition.rule_registry`, `backend.acquisition.unified_mapping`, `backend.config.job_seeker`, `backend.connectors.ats_expansions`, `backend.connectors.ats_router`, `backend.connectors.company_career_discovery`, `backend.connectors.employer_site_fallbacks`, `backend.connectors.generic_jsonld`, `backend.domain.job_identity`, `backend.domain.pipeline_jobs`, `backend.integrations.scrapeops`, `scripts.build_master_jobs_catalog`, `scripts.clean_master_company_url`, `scripts.master_employer_jobs_catalog`, and the current projection dependency `scripts.master_linkedin_jobs_url_catalog`. The URL-catalog dependency also imports `Jobs-Urls/webshare_linkedin_benchmark.py` as a top-level local module.

Recovered LinkedIn producer local imports: `backend.config.job_seeker`; all other imports are standard-library or third-party modules.

Relevant committed recovery tests and fixtures are the employer catalog/fallback/projection tests, the `clean_master_company_url` helper used by the projection tests, the nonproducer URL-catalog test, and the recovered LinkedIn catalog test with its seven captured HTML fixtures.

## Run evidence

The LinkedIn run row and metrics identify `run_20260831T080516037634Z`, started at `2026-08-31T08:05:16Z`, with 11,896 selected companies, 271,193 requests, 187,741 detail successes, and 187,741 jobs written. The exact shell command was not recorded; the full-population invocation and worker flags are therefore not asserted as exact.

The employer metrics identify 9,715 selected companies, 5,132 requests, and 2,612 jobs written. The full-run filename is `master_employer_full_run_20260831_190153`; `--full` is strongly inferred because the selected count exceeds the script default limit, but the exact shell command was not recorded.

No secret values are included. Environment-variable names are preserved only where needed to explain configuration, including Webshare and deployment/Turso names.

## Branch conclusion

The intended Turso/Render branch is `deployment/render-turso-r2`: it has matching upstream tracking, a clean existing worktree at `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview`, explicit branch references in `CURRENT_DATA_PIPELINE_MAP.*`, production acceptance reports, and the CI workflow branch rule. The active worktree `feature/admin-analytics-final-production` is dirty and remains untouched.
