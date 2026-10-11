# RC-001 acquisition source-transfer manifest

Status: completed locally on 2026-09-06

Integration target: `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview`

Branch/HEAD: `deployment/render-turso-r2` at
`e7662c63082d605d8ae6de090d3a04a55bba6556`

This manifest records the scoped RC-001b transfer. Source worktrees remain
untouched. No branch merge, reset, pull, overwrite of pre-existing dirty files,
production access, push, or deployment was performed.

## Source revisions

| Label | Worktree | Branch | HEAD | Status |
| --- | --- | --- | --- | --- |
| Target | `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview` | `deployment/render-turso-r2` | `e7662c63082d605d8ae6de090d3a04a55bba6556` | Existing exporter files modified; RC-001 files are untracked |
| Primary reference | `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper` | `feature/admin-analytics-final-production` | `0c4c4791a710c4575299d65923b03aca0e466721` | Dirty, ahead 14 / behind 37, many unrelated browser/frontend files |
| Producer reference | `C:\w\mlj` | `codex/master-linkedin-jobs-url` | `6d0fca4d944328f4366daddbf1ca8dadba002733` | Clean |

## Selected components

`SHA-256` values below are full content hashes. For retained target files,
"existing target version" is the version used without overwrite. For ported
files, the target was absent and the copied bytes were checked against the
primary-reference hash.

| Target path | Origin path/worktree | Origin commit | SHA-256 | Existing target version | Decision and selected responsibilities |
| --- | --- | --- | --- | --- | --- |
| `scripts/master_linkedin_jobs_catalog.py` | `scripts/master_linkedin_jobs_catalog.py` / target and producer | target `e7662c63`; producer `6d0fca4d` | `ab2bb8ef64164f27d578425c3e4346d0b6de35ffd10a4cdfd6ae43b8f8bd2c9b` | Same | **Retain.** `StateStore`, `load_source_company_groups`, `_scan_company`, `finish_run`, and catalog export are the actual 14-table producer. |
| `scripts/master_employer_jobs_catalog.py` | target | target `e7662c63` | `7e3be1302703eb6a76536e86d872780d81737f09cbf8ba36133a43eb96fc42b3` | Same dirty target file | **Retain.** Keep checkpointing, streaming/validated output, and `export_only`; do not replace with the primary's different dirty copy. |
| `scripts/build_master_jobs_catalog.py` | target | target `e7662c63` | `9a93173ed685f1a3a9913ffd1d57da28226f7a56e6c6010da10acddc04b648fb` | Same dirty target file | **Retain.** Keep the real producer fields, legacy compatibility fields, streaming projection, and atomic validation. |
| `scripts/clean_master_company_url.py` | target | target `e7662c63` | `936de952809ec962db1a794c995b23ac0e7d04eb4d20216d5b49ff08eac7b508` | Same | **Retain.** Existing canonical preparation and provenance helpers remain the input-side base. |
| `tests/test_master_linkedin_jobs_catalog.py` | target | target `e7662c63` | `95aaf361e7eae7cdd2a851a17fff79f9b797a59bb58f4d1b9fe653eae5caa3a0` | Same | **Retain.** Producer schema, lifecycle, and parsing coverage. |
| `tests/test_master_employer_jobs_catalog.py` | target | target `e7662c63` | `42c3e6d7b77db2537de344da857ea3d8c78d62608922970f0f1398d93aa37d62` | Same dirty target test | **Retain.** Checkpoint/export regression coverage. |
| `tests/test_company_csv_consolidation.py` | target | target `e7662c63` | `0f8ed9b46aba822d314d14174867c502957d50d53f998c183c8d6e1575736315` | Same | **Retain.** Input/projection compatibility coverage. |
| `scripts/apply_known_company_websites.py` | primary | primary `0c4c4791` | `16530ded31e648d27f66bd5d5c8f6c80acaf58ca089382eec748379f13014bca` | Absent | **Port.** `match_known_rows` and `apply_known_websites`; uses the logo helper below. |
| `scripts/populate_free_companyenrich_logos.py` | primary | primary `0c4c4791` | `2e24331a87700a590b1c8dbe15f75c7709ed82eb34f437365d8f8fce0bbcd081` | Absent | **Port helper.** Shared local logo/data utility required by website preparation modules. |
| `scripts/discover_websites_from_web_search.py` | primary | primary `0c4c4791` | `93d8128c0afe0006c32a6479cb3746db03dfd4a55304fa1bff6849c07bbdc67e` | Absent | **Port.** Local discovery keys/maps and bounded discovery application; no live run performed. |
| `scripts/discover_websites_consensus.py` | primary | primary `0c4c4791` | `699a47d7f60a4a60de1d2116d95dec8470810025a5cde13f79b5c25bd617dd2b` | Absent | **Port.** Independent-query consensus and review output. |
| `scripts/add_website_discovery_status_column.py` | primary | primary `0c4c4791` | `a64c54379d6d8c2df0fbef902bfa0425baab55a7fcd5dffd76b2dd619d123719` | Absent | **Port.** Explicit status projection helper. |
| `scripts/linkedin_company_enrichment_pipeline.py` | primary | primary `0c4c4791` | `9a9162eea80b20caf01b1a1195ae3a39eecdc8b9ac3bcac5672a6f8234e0b397` | Absent | **Port.** `EnrichmentPipeline`, `StateStore`, `enrich_row`, and configurable `run_pipeline`. |
| `scripts/run_linkedin_company_id_resolution.py` | primary | primary `0c4c4791` | `9bbfcbf42385c251d066e9408c410d21e989a1ea8414f97564e4b28f2b1081ef` | Absent | **Port.** `resolve_one`, `apply_payload`, and bounded/configurable resolver runner. |
| `tests/test_known_company_websites.py` | primary | primary `0c4c4791` | `8be4ac9339215f4047c66bc84243c182348003a95da2bc121297a5642eded3f` | Absent | **Port.** Known-site matching regression tests. |
| `tests/test_company_website_consensus.py` | primary | primary `0c4c4791` | `cad93a353b9e0546dafc4da21f512990279fb1a2658ba458aac1b1530b40d406` | Absent | **Port.** Local maps, consensus, and conflict tests. |
| `tests/test_linkedin_company_enrichment_pipeline.py` | primary | primary `0c4c4791` | `c832cd4d10ce40ac8603dad3803b7f219589333846d247a23750b70121ebb38c` | Absent | **Port.** Offline parser/normalization/state tests. |
| `tests/test_linkedin_company_id_browser_resolution.py` | primary | primary `0c4c4791` | `4bef562e85c2f27b50f90fd95f058ac79282497b9359046b00ebead011f46323` | Absent | **Port.** Contextual ID and rendered-link parsing tests; no browser launch. |

The exact hashes can be regenerated with `Get-FileHash -Algorithm SHA256`.

## Legacy and excluded code

`scripts/master_linkedin_jobs_url_catalog.py` remains in the target because the
projection retains its legacy field names. It is explicitly not the 14-table
producer and was not installed as a schedule, worker entrypoint, or VPS
producer. No URL-catalog source was copied or rewritten.

The primary branch's browser-extension, frontend, unrelated connector, and
other dirty files were not transferred. The target's deployment-specific
backend was used as-is; the ported scripts resolve their existing target
backend imports without absolute-path imports or cross-worktree loading.

## Offline verification

The copied files were byte-compared against their primary-worktree sources.
All seven copied script entry points returned exit code 0 for `--help`.

Focused command, run from the target worktree with the repository's verified
Python 3.12.7 environment:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest -q `
  tests/test_known_company_websites.py `
  tests/test_company_website_consensus.py `
  tests/test_linkedin_company_enrichment_pipeline.py `
  tests/test_linkedin_company_id_browser_resolution.py `
  tests/test_master_linkedin_jobs_catalog.py `
  tests/test_master_employer_jobs_catalog.py `
  tests/test_company_csv_consolidation.py
```

Observed result:

```text
116 passed in 9.58s
```

No test imported another worktree, made an external request, or mutated the
large local input/state artifacts.

## Rollback boundary

RC-001 changes are limited to this manifest, the baseline contract, and the
listed untracked scripts/tests. The three pre-existing dirty exporter files
remain untouched. A future rollback can remove or move aside only the listed
RC-001 untracked files and restore the two evidence documents; no reset or
global cleanup is required.
