# Local Runr data inventory — 2026-09-19

This inventory was produced by read-only filesystem and SQLite inspection.
Python checks used the project interpreter `.venv\\Scripts\\python.exe`.

## Missing full producer state

The authoritative historical files documented by the repository are not
currently present locally:

- LinkedIn producer state: `C:\\Users\\ahmed\\Projects_Local\\runr-acquisition-snapshots\\rc023-20260908\\feature-worktree-recovery\\jobs-urls-preserved\\Jobs-Urls\\master linkedin jobs url\\master_linkedin_jobs_state.db`
- Employer producer state: `C:\\Users\\ahmed\\Projects_Local\\runr-acquisition-snapshots\\rc023-20260908\\feature-worktree-recovery\\jobs-urls-preserved\\Jobs-Urls\\master linkedin jobs url\\master_employer_jobs_state.db`

The `runr-acquisition-snapshots` directory was absent. No full
`master_linkedin_jobs_state.db`, `master_linkedin_jobs.csv`, or
`master_linkedin_jobs.jsonl` was found under `C:\\Users\\ahmed\\Projects_Local`.
The only matching employer state found is a smoke fixture with 10 jobs.

Historical evidence says the missing LinkedIn state contained 188,206 jobs and
had SQLite integrity `ok`; that is not a current local-file verification.

## Data that is present locally

### Canonical acquisition inputs

| Path | Size | Meaning |
|---|---:|---|
| `data\\acquisition\\inputs\\company_sources_linkedin_ids.csv` | 18,807,044 bytes | 17,601 source-company rows with LinkedIn IDs; input, not scraped jobs |
| `data\\acquisition\\inputs\\company_master.csv` | 17,482,721 bytes | Company master input; 9,129 rows × 82 columns |
| `data\\acquisition\\inputs\\company_registry_canonical.csv` | 11,968,530 bytes | Canonical company registry; 17,601 rows × 42 columns |

### Local SQLite databases

| Path | Size | Integrity | Contents |
|---|---:|---|---|
| `.backend_data\\backend.sqlite3` | 19,652,608 bytes | `ok` | Application DB; acquisition/canonical tables exist but contain 0 rows locally |
| `.backend_data\\reprocessing_backups\\production_before_reprocessing_resume_20260810.sqlite3` | 102,735,872 bytes | `ok` | Legacy application/acquisition backup: 141 canonical jobs, 11 canonical companies, 587 observations, 1 publication head |
| `Company-Urls\\Master-Company-Url\\cleaned\\linkedin_company_enrichment_state\\linkedin_id_resolution\\linkedin_id_resolution.sqlite3` | 413,691,904 bytes | `ok` | Company-ID/url enrichment state: 15,454 URL resolutions, 1,475,495 request-log rows, 10 run metadata rows; not the LinkedIn jobs database |
| `.tmp_employer_smoke_20260831_190009\\master_employer_jobs_state.db` | 462,848 bytes | `ok` | Smoke fixture: 1 company and 10 jobs; not the 2,612-row employer corpus |

The `Company-Urls` tree contains about 2.69 GB across roughly 5,900 files,
mostly enrichment transport caches and SQLite sidecars. It does not contain
the full LinkedIn job-state DB.

### Audit outputs, not source data

- `data\\audit\\runr_source_state\\2026-09-11\\rc023-authoritative\\completeness_audit_real.json`
- `data\\audit\\runr_source_state\\2026-09-11\\full_source_state_audit_report.md`
- `data\\audit\\runr_readiness\\2026-09-11\\audit_summary.json`
- `data\\audit\\runr_readiness\\2026-09-11\\jobs_readiness.csv`
- `data\\audit\\runr_readiness\\2026-09-11\\companies_readiness.csv`

These files contain summaries and remediation queues; they do not contain all
188,206 LinkedIn job records.

## Configuration conclusion

`user_config\\.env` currently has:

- `DATABASE_BACKEND=turso`
- `RUNR_DATA_DIR=.backend_data`

The local `.backend_data\\backend.sqlite3` is therefore not evidence that the
full producer corpus is present locally. The documented full source state was
intended as an external restore artifact and, for runtime, as
`/srv/runr/state/linkedin/master_linkedin_jobs_state.db` and
`/srv/runr/state/employer/master_employer_jobs_state.db` on the acquisition
host. No VPS filesystem was inspected in this local search.
