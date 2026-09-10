# OpenCode E: Employer-site completeness handoff

Date: 2026-09-10  
Worktree: `C:\Users\ahmed\Projects_Local\runr-opencode-e-employer-completeness`  
Branch: `temp/opencode-e-employer-completeness`  
Base SHA: `848408f3024c3c675abb3f8d6696563eb4184c50`  
Final SHA: `7d91de2c31e4ea8f608ae52862737f3ed450116e`  
Owner: E (employer-site collector, career-page/ATS discovery, pagination/partition traversal, direct/proxy/browser connectors, per-company coverage receipts)

## Scope

Make Runr's employer-career-site acquisition demonstrably capable of reporting truthful per-company coverage.  No uncertain result becomes confirmed empty or confirmed complete.  This pass is offline and uses fixtures/captured evidence only; it does not restart live acquisition or consume provider credits.

## Base and final SHAs

- Base: `848408f3024c3f8d6696563eb4184c50` (`deployment/render-turso-r2` tip at worktree creation)
- Final: `7d91de2c31e4ea8f608ae52862737f3ed450116e`

## Changed files

### New files

| File | Purpose |
|---|---|
| `backend/acquisition/employer_coverage.py` | Coverage receipt contract, classification, and merge logic |
| `scripts/report_employer_coverage_offline.py` | Offline coverage-report generator from fixtures or existing state |
| `tests/test_employer_coverage_receipts.py` | Receipt persistence, classification, and connector-family tests |
| `tests/fixtures/employer_coverage/connector_families.json` | Representative per-family coverage scenarios |
| `docs/OPENCODE_E_EMPLOYER_COVERAGE_REPORT.json` | Offline fixture-synthesized coverage report |
| `docs/OPENCODE_E_EMPLOYER_COMPLETENESS_HANDOFF.md` | This handoff |

### Modified files

| File | Change |
|---|---|
| `scripts/master_employer_jobs_catalog.py` | Persist per-company coverage receipts in `EmployerState`; pass generation/source version through `save()` and `record_checkpoint()` |
| `scripts/audit_employer_coverage.py` | Emit classification-based report with `confirmed_complete/partial/blocked/failed/unknown` buckets |
| `tests/test_rc012_employer_concurrency.py` | Update monkeypatched `EmployerState.save` signature to accept new `**kwargs` |

## Supported connector families

The receipt records the canonical connector family for each attempted endpoint:

- `ats_native` — Greenhouse, Lever (direct public ATS API pagination)
- `ats_expansion` — Workday, Personio, Recruitee, SmartRecruiters (opt-in expansion connectors)
- `generic_direct` — JSON-LD, embedded JSON, static HTML listing/detail extraction
- `generic_browser` — Browser-rendered pages and same-origin XHR capture

## Definition and evidence for `confirmed_complete`

A company receives `confirmed_complete` only when all of the following hold:

1. Exactly one authoritative endpoint was used (no fallback fan-out).
2. That endpoint's snapshot is marked `complete_snapshot=True`.
3. Pagination or cursor exhaustion was observed (`stop_reason` is `pagination_complete`, `embedded_payload_complete`, or equivalent).
4. No unvisited partitions, pages, or pending detail attempts remain (`pending_detail_count == 0`).
5. No active block, timeout, challenge, or cap is recorded (`error` empty).
6. The observed jobs were persisted.

Anything that fails these conditions is reported as `partial`, `blocked`, `failed`, or `unknown`.  In particular:

- A marketing career page that links to an ATS but is scraped directly is **not** complete; the ATS endpoint must be exhausted.
- An empty app shell, empty listing page, selector failure, or suspicious empty response is **partial/unknown**, not `confirmed_zero`.
- A budget cap, timeout, or block is classified as `failed`/`blocked`/`partial`, never `confirmed_zero`.

## Company coverage counts by status (offline fixture synthesis)

Generated from `tests/fixtures/employer_coverage/connector_families.json` via `scripts/report_employer_coverage_offline.py`:

| Classification | Count | Description |
|---|---|---|
| `confirmed_complete` | 5 | Native/expansion ATS endpoints fully exhausted (Greenhouse, Lever, Workday, Personio) plus one authoritative empty ATS source |
| `partial` | 3 | Generic direct/browser sources with unverified pagination or suspicious empty response |
| `blocked` | 1 | Challenge/CAPTCHA page |
| `failed` | 1 | Browser timeout |
| `unknown` | 0 | No companies lacked evidence in the fixture set |

The full per-company receipt list is in `docs/OPENCODE_E_EMPLOYER_COVERAGE_REPORT.json`.

Historical production state (`master_employer_jobs_state.db`) was not copied into the worktree per the no-live-acquisition instruction.  Running `scripts/audit_employer_coverage.py --state-db <path>` on a restored copy will produce the same five-bucket report over real checkpoints.

## Remaining live uncertainties

- No live source requests were made in this pass.
- Real-world employer homepage/ATS drift, new ATS tenants, and locale variants are not proven by fixtures.
- Multi-domain or multi-tenant companies require manual identity mapping; the receipt preserves `company_id`/`website_url` but does not invent endpoint ownership.
- Production state still contains 428 historical rows whose receipts must be populated by a bounded recheck run before any are marked `confirmed_complete`.
- The report does **not** claim universal live completeness from offline evidence.

## Exact test commands and results

All commands used the repository-mandated interpreter:

```powershell
C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe --version
# Python 3.12.7
```

Focused new-receipt suite:

```powershell
.venv\..\..\..\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe -m pytest -q tests/test_employer_coverage_receipts.py
# 13 passed
```

Employer collector regression (modified + directly adjacent tests):

```powershell
.venv\..\..\..\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe -m pytest -q `
  tests/test_master_employer_jobs_catalog.py `
  tests/test_rc011_employer_outcomes.py `
  tests/test_rc012_employer_concurrency.py `
  tests/test_employer_site_fallbacks.py `
  tests/test_company_career_discovery.py `
  tests/test_employer_coverage_receipts.py
# 109 passed
```

Static hygiene:

```powershell
.venv\..\..\..\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe -m ruff check `
  backend/acquisition/employer_coverage.py `
  scripts/master_employer_jobs_catalog.py `
  scripts/audit_employer_coverage.py `
  scripts/report_employer_coverage_offline.py `
  tests/test_employer_coverage_receipts.py `
  tests/test_rc012_employer_concurrency.py
# All checks passed!

.venv\..\..\..\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe -m py_compile `
  backend/acquisition/employer_coverage.py `
  scripts/master_employer_jobs_catalog.py `
  scripts/audit_employer_coverage.py `
  scripts/report_employer_coverage_offline.py `
  tests/test_employer_coverage_receipts.py `
  tests/test_rc012_employer_concurrency.py
# (no output)
```

Offline report generation:

```powershell
.venv\..\..\..\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe scripts/report_employer_coverage_offline.py --from-fixtures --output docs/OPENCODE_E_EMPLOYER_COVERAGE_REPORT.json
```

## Interface/shared changes required from C

1. **Receipt publication decision** — C owns publication.  The new `coverage_receipts` SQLite table in `master_employer_jobs_state.db` and the JSON report are inputs for C's `runr-contract-v1` publication gate.  C should treat only `confirmed_complete` companies as eligible for closure-safe publication; all others remain open/recheck.
2. **Source version stamping** — `run_collection` reads `RUNR_RELEASE_COMMIT` or `RUNR_SOURCE_VERSION` for receipt provenance.  C should set one of these in the acquisition worker environment.
3. **State/output separation** — receipts live in the durable state DB, not the export catalog.  C's existing state/export split is preserved.
4. **No migration required** — the `coverage_receipts` table is created lazily on existing state DBs and is backward-compatible.

## Stopped-B work retained or superseded

- `docs/RC_B_HANDOFF.md` employer-collector repair (`c98603a51c2775512e49ccb2d54a4adbe731ddb7`) is retained.  This E pass does not modify those discovery/ATS-stop/budget-classification fixes; it adds the coverage-receipt layer on top.
- B's `--state-dir`/`--require-existing-state` producer contract is preserved and unaffected.
- B's RC-024/026 runtime/backup/benchmark work remains separate.

## Commit and rollback

No reset, clean, push, deploy, live request, or production mutation was performed.  To roll back, revert the commits listed in the final SHA record or review the changed files above.  Do not reset or amend the persistent checkout.

## Clean branch tip

Final commit SHA after this handoff: `7d91de2c31e4ea8f608ae52862737f3ed450116e`.
