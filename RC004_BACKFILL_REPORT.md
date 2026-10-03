# RC-004 — Company ID backfill evidence

Status: complete for the bounded offline pilot and full-list dry run. No production application, database write, deployment, pull, merge, push, live test, or network test was performed.

## Scope and safety

- Target branch: `deployment/render-turso-r2`
- Starting target HEAD: `e7662c63082d605d8ae6de090d3a04a55bba6556`
- Input: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\Company-Urls\Master-Company-Url\cleaned\Master-Company-Url-canonical_cleaned_linkedin_ids.csv`
- Input SHA-256: `7f416ec6ebbcb936a42061ef0adaa07e4a6c04d2959d0eb579779126682440d9`
- Input shape: 17,601 rows and 118 columns
- Required interpreter: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe` — Python 3.12.7
- Source master remains untouched. The report is read-only evidence; application tables were not written.
- Existing dirty exporter/producer changes were preserved and the employer and LinkedIn producer files were not edited.

## Full-list dry-run result

The exact command was:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' scripts\backfill_company_ids.py --input 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\Company-Urls\Master-Company-Url\cleaned\Master-Company-Url-canonical_cleaned_linkedin_ids.csv' --output RC004_BACKFILL_REPORT.json
```

The output is [RC004_BACKFILL_REPORT.json](RC004_BACKFILL_REPORT.json). Every source row has a mapping entry. Rows without an eligible ID have an explicit provisional, quarantine, or rejection disposition and registry-record key where applicable.

| Measure | Rows |
| --- | ---: |
| Existing master IDs preserved in proposed mappings | 7,513 |
| Existing-ID rows retained and eligible | 7,438 |
| Existing-ID rows quarantined for conflict review | 75 |
| Missing-ID rows | 10,088 |
| Missing-ID rows matched to an existing registry ID | 128 |
| Missing-ID rows with deterministic new-ID proposals | 9,554 |
| Missing-ID rows provisional pending review/enrichment | 400 |
| Missing-ID rows quarantined | 6 |
| Missing-ID rows rejected | 0 |
| Total eligible rows with exactly one nonempty proposed ID | 17,120 |
| Total quarantine records | 81 |
| Exact duplicate raw rows | 0 |
| Identity keys with duplicate evidence | 208 |
| Identity keys mapping to conflicting existing IDs | 37 |

The missing-ID reconciliation balances exactly: `128 + 9,554 + 400 + 6 + 0 = 10,088`. The existing-ID accounting also balances: `7,438 + 75 = 7,513`; quarantined existing rows retain their original IDs in the proposed mapping and are not silently rewritten.

New IDs are deterministic `canonical-<sha256-prefix>` values anchored by validated CompanyEnrich ID first, then validated numeric LinkedIn organization ID. Website, description, and other enrichment changes do not alter an anchored ID. A row number or mutable company name is not used as long-term identity. Strong evidence that maps to multiple existing IDs is quarantined instead of selecting the first match.

## Bounded pilot and tests

The pilot fixture covers blank IDs, existing-ID reuse, duplicate rows, same-organization conflicts, malformed LinkedIn IDs, non-company LinkedIn page types, reordering, enrichment changes, deterministic hash collision, approval gating, input-hash verification, source protection, manifest ordering, and repeat application.

The focused command was:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest -q tests\test_company_id_backfill.py
```

Result: `7 passed in 2.21s`; the fixture helper also reported `All checks passed!`.

## Files added for RC-004

- `backend/application/company_id_backfill.py` — deterministic analysis, conflict/quarantine decisions, manifest generation, and guarded non-destructive writer.
- `scripts/backfill_company_ids.py` — offline dry-run and explicitly approved-copy CLI.
- `tests/test_company_id_backfill.py` — pilot, idempotence, conflict, collision, hash, and rollback-safety tests.
- `tests/fixtures/rc004_company_id_backfill.csv` — bounded offline pilot input.
- `RC004_BACKFILL_REPORT.json` — full-list dry-run evidence and row-level mapping manifest.
- `RC004_BACKFILL_REPORT.md` — this review record.

## Approved application procedure (not run)

Full-list application remains a later, separately authorized wave. The writer requires an approval manifest, rechecks the source hash, requires coverage for every source row, requires explicit approval for every new anchor, writes the mapping manifest before the output copy, and refuses to overwrite the source. The intended shape is:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' scripts\backfill_company_ids.py `
  --input <master.csv> `
  --output RC004_APPLY_REPORT.json `
  --approved-mappings <reviewed-approved-mappings.json> `
  --apply-output <new-master-copy.csv> `
  --manifest-output <mapping-manifest.json>
```

The command must target a new output copy, never the original master. If an existing output copy is intentionally replaced, the writer first moves it to `<output>.before-rc004.bak`; it refuses to overwrite an existing backup. No application database migration or application-table write is included in RC-004.

## Limitations and rollback

- No application database snapshot or live registry import was available or authorized, so referential-integrity verification is limited to the offline row/mapping invariants and RC-003 registry fixtures.
- The 9,554 deterministic new-ID proposals and 400 provisional records are not approved. They must be reviewed before any full-list write.
- No paid enrichment, producer execution, live provider call, or RC-005 work was performed.
- The full-list report is a dry run; it does not modify the source CSV.

Rollback for an authorized copy application is non-destructive: stop consuming the generated copy, retain the mapping manifest and report for audit, and restore the prior output from `<output>.before-rc004.bak` only after verifying its hash and receiving authorization. If the new copy has not replaced an existing output, delete or archive only that generated copy and its manifest according to the operator’s retention policy. The original master remains the rollback source throughout. No `git reset`, `git clean`, or destructive repository rollback is required.

RC-004 is complete locally. Stop here; RC-005 has not been started.
