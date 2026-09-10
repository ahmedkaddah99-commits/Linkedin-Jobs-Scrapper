# OpenCode E: Employer-site completeness handoff

| Field | Value |
|---|---|
| Date | 2026-09-10 |
| Worktree | `C:\Users\ahmed\Projects_Local\runr-opencode-e-employer-completeness` |
| Branch | `temp/opencode-e-employer-completeness` |
| Base SHA | `7f1d7be57836499930ebc99491d1d6354175c0c6` |
| Final SHA | `TBD` |
| Owner | E (employer-site collector, career-page/ATS discovery, pagination/partition traversal, direct/proxy/browser connectors, per-company coverage receipts) |

## Scope

Correct the coverage-evidence layer and the collector's traversal so that per-company coverage is truthful, then audit the real historical employer state.  No uncertain result becomes confirmed empty or confirmed complete.  This pass is offline: it uses captured/representative responses and a read-only copy of the preserved state, and makes no live requests or provider-credit consumption.

## Corrections applied

### 1. Coverage evidence (`backend/acquisition/employer_coverage.py`)

The prior receipt implementation had four defects; all are fixed with focused regressions in `tests/test_employer_coverage_evidence.py`:

- **Expected totals now come from independent source evidence.** `EndpointAttempt.expected_count` is populated only from `target.expected_count` / `source_reported_total` (a connector-reported total), never from `jobs_observed`.  The Greenhouse connector now emits `source_reported_total` (its `meta.total`) separately from the observed count.
- **Traversal counts are measured or unknown.** `pages_*` and `partitions_*` are `int | None`; unknown traversal is `None`, not a fabricated `1`.  A `partition_state` (`flat` vs `unknown`) records whether a connector family needs partition enumeration to prove completeness.
- **Classification accounts for all required endpoints/partitions.** `confirmed_complete` requires every authoritative endpoint to be complete, reconciled against any independent total, free of pending details, free of caps/blocks/errors, and free of unresolved partition coverage (`partition_state != "unknown"`).  A native/expansion ATS listing is `flat` (a single catalog), so it can be proven complete; a generic/browser page is `unknown` and stays `partial`.
- **Old complete scans never make a new scan closure-safe.** `merge_receipts` now returns the current generation and records the prior `confirmed_complete` only as `last_confirmed_complete_at`/`last_confirmed_complete_generation` reference.
- **A cap, missing partition, unresolved detail, or contradictory evidence is never `confirmed_complete`.** `request_budget_exhausted` is retryable `partial`, not `failed`.

### 2. Collector traversal fixes (`scripts/master_employer_jobs_catalog.py`)

- **Complementary partitions are detected.** After collection, any discovered native-ATS candidate that was not traversed is recorded in `coverage.discovery.complementary_partitions_skipped`; a skipped complementary ATS tenant forces `partial` instead of `confirmed_complete`.
- **Independent source totals flow into targets.** `_coverage_target` now carries `expected_count` from connector `source_reported_total`.

### 3. Stopped-B employer defects (bounded cycles)

Addressed from the stopped-B handoff (`temp/opencode-b-collectors`, `66b61445`):

- **Bounded-cycle advancement** — `EmployerState` gains a durable `collection_cursor`; with `resume=True` and a positive `limit`, the work list is filled from a rotated order and the cursor advances after each window, so repeated small cycles cover the full input instead of re-selecting the same first rows.
- **Recheck-budget filling** — when the recheck budget is exhausted, the slice continues filling with fresh rows instead of leaving the run empty.
- **Exact-cohort invariant** — `--company-id` (and the manifest wrapper's `--company-ids`) never expands via the cursor; the cursor is disabled for exact-cohort runs.

## Supported connector families

- `ats_native` — Greenhouse, Lever (flat public ATS listing; pagination exhaustible)
- `ats_expansion` — Workday, Personio, Recruitee, SmartRecruiters (flat per-tenant listing)
- `generic_direct` — JSON-LD, embedded JSON, static HTML listing/detail
- `generic_browser` — browser-rendered pages and same-origin XHR

Real traversal is proven by `tests/test_employer_traversal.py`, which drives the actual `fetch_ats_snapshot` and `collect_company` paths against a fake transport returning representative multi-page responses (pagination exhaustion, source-count reconciliation, result caps, browser fallback, complementary-partition detection).

## Definition and evidence for `confirmed_complete`

A company is `confirmed_complete` only when all of the following hold:

1. At least one endpoint is authoritative (`role == "authoritative"`).
2. Every authoritative endpoint is `complete` and (for non-flat families) `pagination_complete`.
3. Any independent source total reconciles with the observed count (`observed_count == expected_count`).
4. No pending detail attempts, no error, no block, and no cap (`stop_reason` not in `max_requests`/`max_pages`/`request_budget_exhausted`).
5. `partition_state` is `flat` (or partitions are otherwise measured and complete), i.e. no unvisited location/category/entity partition remains.
6. No complementary ATS partition was skipped by discovery.

Anything else is `partial`, `blocked`, `failed`, or `unknown`.  A browser timeout, empty app shell, or empty listing is never `confirmed_zero`.

## Real-company coverage (read-only historical audit)

`scripts/audit_employer_coverage_real.py` opens the preserved employer state read-only (`mode=ro`, no state helper, no migration) at:

`C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\feature-worktree-recovery\jobs-urls-preserved\Jobs-Urls\master linkedin jobs url\master_employer_jobs_state.db`

and classifies all 428 companies with `classify_legacy_result` (historical rows predate coverage receipts, so none can be `confirmed_complete`):

| Classification | Count |
|---|---|
| `confirmed_complete` | 0 |
| `partial` | 91 |
| `blocked` | 0 |
| `failed` | 337 |
| `unknown` | 0 |

Legacy `status_counts`: `no_jobs` 194, `discovery_failed` 146, `partial` 82, `completed` 1, `source_failed` 5.  The 194 `no_jobs` rows split into 186 `failed` (browser timeout) and 8 `partial` (genuine empty page, suspicious empty).

**Largest concrete failure categories** (from `docs/OPENCODE_E_EMPLOYER_COVERAGE_REAL_REPORT.json`):

| Failure | Count |
|---|---|
| `source:timeout` (browser) | 2452 |
| `rendered_discovery:timeout` | 145 |
| `discovery:homepage_fetch_failed` | 96 |
| `job_detail:http_404` | 86 |
| `discovery:not_found` | 50 |
| `job_detail:http_403` | 44 |
| `job_detail:http_429` | 29 |
| `job_detail:http_503` | 25 |

The dominant failure is the browser fallback timing out on generic career sites; the collector already records this as `failed`/`partial` (never `no_jobs`/confirmed zero) and the receipt layer preserves that truthfully.  These are external/operational failures, not offline-repairable code defects, and are reported rather than guessed.

## Changed files

### New files

| File | Purpose |
|---|---|
| `scripts/audit_employer_coverage_real.py` | Read-only real-state audit + report |
| `tests/test_employer_coverage_evidence.py` | Regression tests for the four evidence defects |
| `tests/test_employer_traversal.py` | Real connector traversal tests (pagination/caps/browser/partitions) |
| `tests/test_employer_bounded_cycles.py` | Bounded-cycle advancement + recheck-budget tests |
| `docs/OPENCODE_E_EMPLOYER_COVERAGE_REAL_REPORT.json` | Real historical coverage report |

### Modified files

| File | Change |
|---|---|
| `backend/acquisition/employer_coverage.py` | Corrected evidence model, classification, merge, and `classify_legacy_result` |
| `backend/connectors/ats_router.py` | Greenhouse emits `source_reported_total` (independent `meta.total`) |
| `scripts/master_employer_jobs_catalog.py` | Durable collection cursor, complementary-partition recording, `expected_count` on targets |
| `tests/test_employer_coverage_receipts.py` | Updated merge/budget expectations to corrected semantics |

## Exact test commands and results

All commands used the repository-mandated interpreter (`Python 3.12.7`).

```powershell
.venv\Scripts\python.exe -m pytest -q `
  tests/test_master_employer_jobs_catalog.py `
  tests/test_rc011_employer_outcomes.py `
  tests/test_rc012_employer_concurrency.py `
  tests/test_employer_site_fallbacks.py `
  tests/test_company_career_discovery.py `
  tests/test_employer_coverage_receipts.py `
  tests/test_employer_coverage_evidence.py `
  tests/test_employer_traversal.py `
  tests/test_employer_bounded_cycles.py `
  tests/test_ats_router.py `
  tests/test_ats_expansions.py `
  tests/test_producer_adapters.py `
  tests/test_source_eligibility_manifest.py
# 159 passed, 14 subtests passed
```

```powershell
.venv\Scripts\python.exe -m ruff check `
  backend/acquisition/employer_coverage.py `
  backend/connectors/ats_router.py `
  scripts/master_employer_jobs_catalog.py `
  scripts/audit_employer_coverage.py `
  scripts/audit_employer_coverage_real.py `
  scripts/report_employer_coverage_offline.py `
  tests/test_employer_coverage_evidence.py `
  tests/test_employer_traversal.py `
  tests/test_employer_bounded_cycles.py `
  tests/test_employer_coverage_receipts.py
# All checks passed!
```

Real-state audit:

```powershell
.venv\Scripts\python.exe scripts/audit_employer_coverage_real.py `
  --state-db "C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\feature-worktree-recovery\jobs-urls-preserved\Jobs-Urls\master linkedin jobs url\master_employer_jobs_state.db" `
  --output docs/OPENCODE_E_EMPLOYER_COVERAGE_REAL_REPORT.json
```

## Interface/shared changes required from C

1. **Publication gate** — only `confirmed_complete` receipts are eligible for closure-safe publication; `partial`/`blocked`/`failed`/`unknown` stay open.  C owns the publication decision and must read `coverage_receipts.terminal_classification`.
2. **Source version stamping** — `run_collection` reads `RUNR_RELEASE_COMMIT`/`RUNR_SOURCE_VERSION` for receipt provenance; C should set one in the acquisition worker environment.
3. **Bounded-cycle cursor** — the new `collection_cursor` table and `--limit` rotation semantics are employer-owned; C's scheduler must not assume `--limit` always starts at the first row.  The manifest wrapper's `--company-ids` exact-cohort path disables the cursor.
4. **Greenhouse `source_reported_total`** — the connector now exposes an independent total; C's normalization/publication should not treat `source_reported_count` (which still falls back to observed for backward compat) as authoritative for reconciliation.
5. **No migration required** — `coverage_receipts` and `collection_cursor` tables are created lazily and are backward-compatible.

## Remaining live uncertainties

- No live source requests were made; real-world ATS/homepage drift and locale variants remain unproven.
- Multi-domain/multi-tenant companies require manual identity mapping; the receipt records `company_id`/`website_url` but does not invent endpoint ownership.  Complementary-partition detection relies on discovery surfacing the additional tenant.
- The historical report is derived from preserved offline state; it does not claim universal live completeness, and 337/428 companies remain `failed` (browser timeout) pending a bounded live recheck.
- The `source:timeout` browser failure is operational (external sites timing out); no offline code change can make it a confirmed result.

## Stopped-B work retained or superseded

- Stopped-B handoff `temp/opencode-b-collectors` (`66b61445`) identified bounded-cycle advancement, exact-cohort, and recheck-budget defects; these are implemented and tested in this pass (`tests/test_employer_bounded_cycles.py`).
- B's `--state-dir`/`--require-existing-state` producer contract and the RC_B employer repair (`c98603a51c2775512e49ccb2d54a4adbe731ddb7`) are preserved.
- B's RC-024/026 runtime/backup/benchmark work remains separate and unchanged.

## Commit and rollback

No reset, clean, push, deploy, live request, or production mutation was performed.  To roll back, revert the commits listed in the final SHA record or review the changed files above.  Do not reset or amend the persistent checkout.

## Clean branch tip

Implementation commit: `TBD`
Branch tip (`temp/opencode-e-employer-completeness`): `git rev-parse HEAD` — a documentation-only commit records the implementation SHA after this handoff.
