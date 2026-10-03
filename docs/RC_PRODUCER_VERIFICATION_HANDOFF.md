# RC-010–RC-015 producer verification handoff

Date: 2026-09-07
Target checkout: `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview`
Target branch: `deployment/render-turso-r2`
HEAD at start: `e7662c63082d605d8ae6de090d3a04a55bba6556`

This pass used fixture and temporary-state copies only. No historical
production database, network request, browser/provider request, deployment,
migration, commit, merge, push, reset, clean, or whole-file rollback was
performed. Existing dirty work was preserved.

## Interpreter

The shared repository interpreter documented by
`BASELINE_AND_INPUT_CONTRACT.md` was available and verified:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
Python 3.12.7
```

All Python commands below used that interpreter against this target checkout.

## Acceptance status

| Ticket | Status | Evidence and boundary |
| --- | --- | --- |
| RC-010 | Verified offline by fixture/API integration | Dual employer + LinkedIn observations deduplicate to one canonical job; canonical company matching, two authenticated route reads, replay idempotency, failed LinkedIn source handling, and prior-publication preservation pass. The two user reads are an in-process authenticated API-route fixture, not a browser demonstration. |
| RC-011 | Verified offline by focused tests | Uncertain, blocked, partial, and complete-empty employer outcomes remain distinct; bounded resume/recheck behavior and prior observations are covered. |
| RC-012 | Verified offline by focused tests | Stalled-company checkpointing, direct/proxy accounting, browser-process and account/origin bounds, SQLite writer ownership, resume, interruption, and export behavior pass. One compatibility defect in the offline Playwright double was fixed and the affected suite reran green. |
| RC-013 | Verified offline by current producer tests | Non-empty capped recovery remains partial; suspicious-empty, challenge, malformed, failed, lifecycle replay, ownership-conflict, retry-budget, and legacy-audit cases pass. |
| RC-014 | Verified offline by current producer tests | Cache-hit current run/scan attribution, volatile staleness, durable expiry, changed-card refresh, failed refresh freshness, and source disappearance pass. |
| RC-015 | Verified offline by current producer tests | Generation-local JSONL, immutable generation manifest/pointer hashes, session closure, limiter bounds, proxy health, bounded transactions, and typed/redacted exports pass. |

No ticket above is marked verified from static checks alone; each status above
has a passing offline test result. Live provider coverage, production state,
and a real browser walkthrough remain outside this offline handoff.

## Commands and results

RC-010 plus RC-017 matcher/publication, adapters, observation-store and phase-B
catalog proof:

```powershell
& $py -m pytest -q tests/test_rc010_first_acquisition_slice.py tests/test_phase_a_rc017.py tests/test_producer_adapters.py tests/test_observation_store_integration.py tests/test_phase_b_catalog.py
```

Result: **21 passed in 10.56s**.

This includes `test_rc010_dual_source_slice_reaches_jobs_and_preserves_public_head_on_failure` and RC-017’s newer-version/absence protection, stale staging promotion rejection, complete generation hash validation, and abandoned-generation pointer protection. The RC-010 user reads dispatch the authenticated `GET /v1/personalized-jobs` route for `user-a` and `user-b` in the fixture. No frontend server or browser session was started.

Employer outcome, fallback, checkpoint, concurrency, request-accounting,
resume and export verification:

```powershell
& $py -m pytest -q tests/test_employer_site_fallbacks.py tests/test_rc011_employer_outcomes.py tests/test_rc012_employer_concurrency.py tests/test_master_employer_jobs_catalog.py
```

Result after the local fix: **58 passed in 12.53s**.

The first run exposed one failure in
`test_fetch_browser_snapshot_keeps_same_origin_xhr_and_rendered_content`:
the offline Playwright double has response events but no `page.route`, and the
new bounded route hook converted the fixture result to `browser_failed`. The
fix in `backend/connectors/employer_site_fallbacks.py:416-422` uses route
interception when the real Playwright page provides it and retains the bounded
response-only path for older/offline doubles. The affected suite was rerun;
no production behavior or request limit was relaxed for real Playwright.

Current LinkedIn producer and later RC-013–RC-015 corrections:

```powershell
& $py -m pytest -q tests/test_master_linkedin_jobs_catalog.py
```

Result: **56 passed in 7.22s**.

The relevant current tests include:

- `test_nonempty_recovery_page_at_cap_remains_partial`;
- `test_daily_run_rescans_search_but_reuses_fresh_unchanged_detail`, including
  current `run_id`/`company_scan_id` attribution;
- `test_retry_sequence_is_replayed_offline_before_classifying_the_scan`,
  including the generation-local JSONL artifact; and
- lifecycle, suspicious-empty, ownership-conflict, retry quarantine,
  transaction, limiter, proxy-health, export and source-disappearance cases.

Static hygiene check:

```powershell
git diff --check
```

Result: exit code 0. Git emitted only existing LF/CRLF normalization warnings.

## Files changed in this pass

- `backend/connectors/employer_site_fallbacks.py` — compatibility guard for
  response-only offline Playwright doubles; existing RC-012 guards remain.
- `docs/RC_PRODUCER_VERIFICATION_HANDOFF.md` — this handoff.

The following existing dirty producer/test files were verified but not broadly
rewritten or rolled back: `scripts/master_employer_jobs_catalog.py`,
`tests/test_master_employer_jobs_catalog.py`,
`scripts/master_linkedin_jobs_catalog.py`,
`tests/test_master_linkedin_jobs_catalog.py`,
`tests/test_rc010_first_acquisition_slice.py`,
`tests/test_rc011_employer_outcomes.py`,
`tests/test_rc012_employer_concurrency.py`,
`tests/test_phase_a_rc017.py`, the producer adapters, and current RC-009/RC-017
publication/repository changes.

## Remaining limitations

- No live LinkedIn/employer/provider request was made.
- No actual frontend browser demonstration or screenshot was performed; the
  RC-010 user-visible proof is an authenticated in-process API route fixture.
- No historical production employer database was available or accessed for a
  migration audit; test databases were temporary copies.
- Render/deployed-state verification remains external.

## Handoff to Chat C

Chat C may take the next scheduler/queue-owned work (RC-016) from this exact
branch and dirty state. It should read this handoff and
`docs/RC_IDENTITY_RECONCILIATION_HANDOFF.md`, preserve all existing changes,
use the same shared Python interpreter, and keep verification offline unless a
separate live authorization is supplied. No RC-016 implementation or backend
scheduler files were changed in this pass.

## Rollback

To withdraw this pass, reverse only the route-compatibility hunk at
`backend/connectors/employer_site_fallbacks.py:416-422` and remove this
handoff document after confirming its absolute path. Do not reset, clean, or
restore either producer file wholesale; the worktree contains independent
RC-007–RC-017 changes that must remain intact.
