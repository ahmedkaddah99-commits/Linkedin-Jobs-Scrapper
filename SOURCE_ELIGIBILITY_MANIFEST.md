# RC-005 — Versioned source-eligibility manifest

Status: complete locally on 2026-09-06. This ticket produced an offline,
versioned manifest and two manifest-gated collector entrypoints. No collector
network request, production write, deployment, pull, merge, push, reset, or
clean was performed.

Reconciliation note (2026-09-07): the original immutable RC-005 cycle remains
unchanged. Its row decisions correctly blocked 80 rows belonging to the 37
unresolved shared-organization groups, but its review subrecords listed only
the 75 rows that already had canonical IDs. The manifest builder now includes
all current source rows for each conflicting organization, including the five
blocked rows without IDs. The corrected immutable cycle is recorded in
`SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json` with sidecar
`SOURCE_ELIGIBILITY_RAW_RC005_RECONCILED.jsonl`; it has the same source hash,
counts, and pilot scope, with an 80-row review packet.

Target branch: `deployment/render-turso-r2`.

Starting target HEAD: `e7662c63082d605d8ae6de090d3a04a55bba6556`.

The existing dirty producer/exporter files were preserved and not edited:

- `scripts/build_master_jobs_catalog.py`
- `scripts/master_employer_jobs_catalog.py`
- `scripts/master_linkedin_jobs_catalog.py`
- their pre-existing producer tests

## Snapshot evidence

Source snapshot:

`C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\Company-Urls\Master-Company-Url\cleaned\Master-Company-Url-canonical_cleaned_linkedin_ids.csv`

- Rows: 17,601
- Columns: 118
- SHA-256: `7f416ec6ebbcb936a42061ef0adaa07e4a6c04d2959d0eb579779126682440d9`
- Header SHA-256: `28f68ab82a4710575f0a0c7fd43992e121fa45b0f1fd150e37c73a83f0ea2460`

Generated RC-005 artifacts:

- [SOURCE_ELIGIBILITY_MANIFEST_RC005.json](SOURCE_ELIGIBILITY_MANIFEST_RC005.json)
  - schema: `runr_source_eligibility_manifest_v1`
  - cycle: `rc005-full-20260906`
  - manifest SHA-256: `92186e75e30534f5bb4e1e206e3c5c2d0ce333d8c35f04ccce1ee7d6f3997a34`
- [SOURCE_ELIGIBILITY_RAW_RC005.jsonl](SOURCE_ELIGIBILITY_RAW_RC005.jsonl)
  - sidecar SHA-256: `cda46fee441e2e6e02d52ffe2fc86ae33121c82edc9f0636562367b63cbb5ef7`
  - 17,601 records and all 118 source columns, including `Column1`–`Column9`

The manifest is immutable for a cycle. Reusing an existing cycle path with a
different manifest or sidecar hash is rejected. The source snapshot hash and
header hash are recorded in the manifest. A later snapshot is a new cycle;
omitting a row does not authorize historical job absence closure.

## Full-list counts

| Measure | Count |
| --- | ---: |
| Input rows / columns | 17,601 / 118 |
| Rows mapped to an effective canonical ID | 7,513 |
| Mapped canonical entities | 7,513 |
| Missing-ID rows pending RC-004 approval | 9,682 |
| Missing-ID rows without a usable backfill proposal | 406 |
| Field-presence dual-ready rows | 6,037 |
| Evidence-verified dual-ready rows before canonical/ownership gates | 5,872 |
| Dual-ready entities for the pilot | 1,574 |
| Single-ready entities for later controlled expansion | 4,259 |
| Website-only entities | 3,561 |
| LinkedIn-only entities | 698 |
| Blocked entities | 11,768 |
| Employer tasks across all eligible source rows | 5,135 |
| LinkedIn tasks across all eligible source rows | 2,272 |
| Initial dual-source pilot tasks | 3,148 (1,574 per source) |
| Exact duplicate rows / duplicate associations | 0 / 0 |
| Unresolved conflicting organization groups / rows | 37 / 80 |

The field-presence baseline of 6,037 is not treated as an eligible count. The
manifest records 165 rows that had the three source fields present but did not
pass evidence checks, and 4,229 evidence-verified dual rows that still lacked
an approved canonical ID. The RC-004 dry-run mapping remains pending: no
missing-ID proposal was silently approved.

The largest recorded deductions are missing website URL (7,886 rows), missing
or invalid LinkedIn URL (2,147 rows), missing/non-numeric LinkedIn ID (5,542
rows), unresolved LinkedIn evidence status, URL/ID pair mismatches (414
rows), non-company school pages (79 rows), and unresolved ownership (80
rows). These are row-level reasons in the JSON manifest, not inferred zero-job
results.

## Eligibility contract

Each row contains the original and effective canonical ID state, raw-column
sidecar key, structural website result, website discovery evidence and
freshness, LinkedIn URL/page-type result, numeric ID evidence/status/source/
confidence/transport, URL/ID pair status, ownership review, independent
source eligibility, decision, and exclusion reasons.

The initial pilot requires all of the following:

1. An input canonical ID or explicitly approved RC-004 mapping.
2. Structurally valid website URL with accepted discovery evidence (`found`,
   `verified`, or `complete`) and no stale evidence.
3. Structurally valid LinkedIn company URL, numeric LinkedIn organization ID,
   accepted numeric-ID evidence (`resolved`, `validated`, `high_confidence`,
   or `verified`), positive supplied confidence when present, and no URL/ID
   mismatch.
4. No unresolved ownership conflict.

Website-only and LinkedIn-only tasks remain visible in the manifest but are not
used by the wrappers unless `--include-single-source` is explicitly supplied.
LinkedIn organization associations are grouped and carry the reviewed
ownership disposition; unresolved multi-owner groups produce no LinkedIn
task.

The raw sidecar is a separate JSONL contract rather than a lossy projection.
Materialized source inputs retain the exact 118-column order and replace only
the canonical-ID field with an approved effective ID where applicable.

## Files added

- `backend/application/source_eligibility_manifest.py` — snapshot hashing,
  evidence decisions, ownership gates, task deduplication, immutable bundle
  writer, sidecar reader, and source-input materialization.
- `scripts/build_source_eligibility_manifest.py` — offline manifest CLI.
- `scripts/run_manifested_employer.py` — employer collector entrypoint that
  requires and materializes the manifest first.
- `scripts/run_manifested_linkedin.py` — LinkedIn collector entrypoint that
  requires and materializes the manifest first.
- `tests/test_source_eligibility_manifest.py` — RC-005 behavior and gate tests.
- `tests/fixtures/rc005_source_eligibility.csv` — actual contract spellings,
  duplicate, missing, malformed, stale, school, conflict, and mismatch cases.
- `tests/fixtures/rc005_linkedin_pagination.json` — offline LinkedIn evidence
  fixture used by the wrapper test.
- `SOURCE_ELIGIBILITY_MANIFEST_RC005.json` — full row/task evidence.
- `SOURCE_ELIGIBILITY_RAW_RC005.jsonl` — full raw-column sidecar.

The low-level producer files remain source-owned. The supported scheduled paths
for this contract are the two `run_manifested_*` wrappers; a scheduled job
must not invoke the low-level producer CLIs with a raw master CSV directly.

## Commands and results

Interpreter verification:

```text
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
Python 3.12.7
```

Full offline build:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' scripts\build_source_eligibility_manifest.py `
  --input 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\Company-Urls\Master-Company-Url\cleaned\Master-Company-Url-canonical_cleaned_linkedin_ids.csv' `
  --output SOURCE_ELIGIBILITY_MANIFEST_RC005.json `
  --raw-sidecar SOURCE_ELIGIBILITY_RAW_RC005.jsonl `
  --cycle-id rc005-full-20260906 `
  --as-of 2026-09-06T00:00:00Z `
  --max-evidence-age-days 30 `
  --registry-report COMPANY_REGISTRY_RECONCILIATION.json `
  --backfill-report RC004_BACKFILL_REPORT.json
```

Focused RC-005 test:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest -q tests\test_source_eligibility_manifest.py
```

Result: `7 passed in 3.46s` after the reconciliation regression was added.

Static check:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m ruff check `
  backend\application\source_eligibility_manifest.py `
  scripts\build_source_eligibility_manifest.py `
  scripts\run_manifested_employer.py `
  scripts\run_manifested_linkedin.py `
  tests\test_source_eligibility_manifest.py
```

The invariant check confirms 17,601 row mappings, balanced mapped/blocked
counts, 37 ownership conflict groups, 118 raw columns, and the read-only
source/application flags. No application tables were written.

## Limitations

- The deployed production input and application registry were not accessed;
  this is local snapshot evidence only.
- The 9,682 RC-004 proposals remain pending approval. The full manifest has
  7,513 mapped rows because the approved mapping artifact was not supplied.
- No network, browser, proxy, provider, paid-enrichment, or collector run was
  performed. Wrapper tests use dry-run mode and local fixtures only.
- The existing producer CLIs were not edited because their files remain
  source-owned. Their scheduled use must be replaced by the manifest wrappers
  through an explicit integration handoff.

## Rollback

No data rollback is required: the master CSV and application tables were not
modified. To disable RC-005, stop scheduling the two manifest wrappers and
archive or remove only the generated RC-005 manifest, raw sidecar, and any
wrapper-generated `.manifest_inputs` copies. Preserve the source master,
RC-001–RC-004 evidence, and all dirty producer/exporter files.

If the code change itself must be reverted, remove or move aside only the RC-005
files listed above; do not use `git reset`, `git clean`, or a broad worktree
cleanup. RC-006 has not been started.
