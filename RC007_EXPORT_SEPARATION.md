# RC-007 — Decouple employer, LinkedIn, and combined exports

Status: **complete offline** on 2026-09-06.

Target worktree: `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview`
Target branch: `deployment/render-turso-r2`
HEAD at validation: `e7662c63082d605d8ae6de090d3a04a55bba6556`
Required interpreter: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe`
Verified version: **Python 3.12.7**

The RC-007 implementation was already present in preserved dirty worktree
changes at the start of this turn. It was audited and validated; the exporter
files were not overwritten. No producer file was edited.

## Implementation and test files

- `scripts/master_employer_jobs_catalog.py` — employer-owned checkpoint and independent `--export-only` path.
- `scripts/build_master_jobs_catalog.py` — separately invocable streaming combined projection with required source generation IDs and manifest.
- `tests/test_master_employer_jobs_catalog.py` — employer-only, zero-job, missing/corrupt combined source, generation lineage, streaming, and promotion rollback tests.
- `tests/test_master_linkedin_jobs_catalog.py` — independent LinkedIn producer/export regression coverage.
- `tests/test_master_linkedin_jobs_url_catalog.py` — legacy LinkedIn export compatibility coverage.
- `RC007_EXPORT_SEPARATION.json` — machine-readable evidence.

## Acceptance evidence

Employer export-only reads authoritative employer SQLite state and does not load
the LinkedIn CSV, dotenv-dependent clients, or the collector. A valid empty
employer state produces a valid empty employer CSV and does not create a
combined CSV.

The LinkedIn path remains independently testable. The combined projection is a
separate command requiring both source CSVs and generation IDs. It validates
inputs before promotion, streams rows without materializing the full combined
catalog, preserves real producer fields, keeps legacy compatibility fields
explicit, and records both input hashes, row counts, paths, and generation IDs
in its manifest.

Missing or corrupt combined input returns a clear error and leaves the existing
employer output unchanged. Temporary validation failure and interrupted
promotion leave prior snapshots intact.

## Verification commands and results

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
# Python 3.12.7

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest tests/test_master_employer_jobs_catalog.py tests/test_master_linkedin_jobs_catalog.py tests/test_master_linkedin_jobs_url_catalog.py -q
# 114 passed in 27.78s

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m ruff check scripts/master_employer_jobs_catalog.py scripts/build_master_jobs_catalog.py tests/test_master_employer_jobs_catalog.py tests/test_master_linkedin_jobs_catalog.py
# All checks passed!

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m py_compile scripts/master_employer_jobs_catalog.py scripts/build_master_jobs_catalog.py scripts/master_linkedin_jobs_catalog.py tests/test_master_employer_jobs_catalog.py tests/test_master_linkedin_jobs_catalog.py
# exit code 0

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' scripts/master_employer_jobs_catalog.py --help
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' scripts/build_master_jobs_catalog.py --help
# both exit code 0
```

All tests used temporary state and mocked/synthetic inputs. Network calls: **0**.

## Limitations and rollback

- No live HTTP, proxy, browser, provider, credential, deployment, or production-state check was performed.
- No production artifact was generated or changed by this validation turn.
- The target worktree has no commit isolating RC-007 from other user-owned dirty changes.
- Stop here; RC-008 requires a separate producer handoff.

Rollback:

1. Stop collector/export processes and back up the employer state database and output directory.
2. Reverse only the reviewed RC-007 hunks in the two implementation files; do not reset, clean, or restore whole dirty files.
3. Preserve source-specific state and existing snapshots unless artifact rollback is explicitly requested.
4. Remove only a newly generated combined CSV/manifest if that projection must be withdrawn and the employer artifacts are verified intact.
5. Restore the backup if state or artifact rollback is required.

No rollback was performed.
