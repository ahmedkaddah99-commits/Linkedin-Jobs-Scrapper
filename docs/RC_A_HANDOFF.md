# Chat A handoff — RC-025

Status: **verified offline; implementation complete for the bounded read model and local UI/API exercise; live/integrated acceptance pending**.

This handoff is for `temp/rc-a-observability-growth` at the reserved worktree
`C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview-rc-a-observability-growth`.
The worktree started clean at the manifest launch commit
`b0f47788c1a5d385ae4c3c770d5cd990f586a626`. The persistent target checkout and
the B/C worktrees were not edited.

## RC-025 result

The existing read-only `GET /admin/acquisition/analytics` contract now includes
two additive projections:

- `coverage` (`acquisition_coverage_v1`) keeps the frozen source-master facts
  separate from runtime task facts. It reports master rows, existing and
  missing IDs, unique baseline LinkedIn organizations, explicit runtime scan
  groups/tasks, evidence-verified eligibility, identity/alias/negative-result/
  retry backlogs, and one latest-task row per acquisition target.
- `health` reports customer queue age and duration, failures/retries, local DB
  read latency, worker role/version and heartbeat freshness, metadata-reported
  disk/RAM, durable provider throttling/budget state, stale coverage, stale
  workers, stuck tasks, missing-worker, spend-limit and retention-unknown
  conditions.

The UI is read-only. It shows the denominator, backlogs, per-source eligibility
and scan state, observed/accepted/published/rejected counts, stop reason,
freshness and next action, followed by queue/worker/provider health. A failed or
deferred source without an authoritative result renders unknown job counts; it
does not render zero jobs. “Online” is derived from heartbeat age, not the
stored worker status label.

## Exact changed files

- `backend/acquisition/analytics.py` — additive RC-025 coverage and health
  builders and response fields; no migrations or producer changes.
- `frontend/src/pages/AdminAcquisitionAnalyticsPage.jsx` — denominator,
  backlog, per-source coverage and health panels.
- `frontend/src/lib/acquisitionOperations.js` — explicit coverage/heartbeat
  display-label helpers.
- `frontend/src/lib/acquisitionOperations.test.js` — fixture-state UI label
  regression checks.
- `tests/fixtures/rc025_operational_dashboard.json` — sanitized fresh, stale,
  partial, failed/unknown-cost, stuck-task and stale-heartbeat fixture.
- `tests/test_acquisition_analytics.py` — fixture-backed offline API/read-model
  test, including no inferred job count for failed unknown-cost work.
- `docs/RC_A_HANDOFF.md` — this handoff.

No employer producer, LinkedIn producer, migration registry, route registry,
worker entrypoint, `render.yaml`, persistent target checkout, or B/C worktree
was changed.

The verification pass additionally changed:

- `frontend/src/pages/AdminAcquisitionAnalyticsPage.jsx` - preserve a
  composite failure/retry metric as text instead of rendering `NaN`.

## Evidence and commands

The mandated external repository environment was used because the target-local
`.venv` is absent:

```text
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
Python 3.12.7
```

Offline backend regression:

```text
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest -q tests/test_acquisition_analytics.py tests/test_acquisition_audit_permissions.py tests/test_acquisition_quality.py tests/test_phase_a_routes.py
27 passed in 11.83s
```

Python static validation:

```text
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m ruff check 'C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview-rc-a-observability-growth\backend\acquisition\analytics.py' 'C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview-rc-a-observability-growth\tests\test_acquisition_analytics.py'
All checks passed!

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m py_compile 'C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview-rc-a-observability-growth\backend\acquisition\analytics.py' 'C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview-rc-a-observability-growth\tests\test_acquisition_analytics.py'
exit code 0
```

Focused frontend regression:

```text
node --test src/lib/acquisitionOperations.test.js
10 passed, 0 failed
```

`git diff --check` returned exit code 0. The full frontend command was also
attempted offline:

```text
npm test
157 passed, 1 failed
```

The one failure is the pre-existing `src/lib/personalizedJobs.test.js` module
load error (`Cannot find package 'react'`); this worktree has no
`frontend/node_modules`. `npm exec eslint` was not allowed to resolve/install a
package without network authorization and was stopped. No live/provider,
network, paid, deployment or production migration test was run.

## RC-025 verification closure

This section supersedes the earlier dependency-unavailable result above. The
starting state for this pass was clean at
`c5b57777785e98ebfa4b2b0a0a4f466907cb7ee7` on
`temp/rc-a-observability-growth`; the only source change was the formatter fix
listed above.

Environment and dependency checks:

```text
Test-Path .venv\Scripts\python.exe
False
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
Python 3.12.7

frontend\package.json: npm test / npm run check / npm run build
frontend\package-lock.json: lockfileVersion 3
```

The authorized lockfile install commands were attempted in `frontend` without
changing `package-lock.json`:

```text
npm ci
npm ci --no-audit --no-fund
npm ci --ignore-scripts --no-audit --no-fund
```

Each resolved cached packages but did not terminate in this Windows
environment; the stalled npm process was stopped. The locked `react` 18.3.1,
`eslint`, and `vite` package files were present afterward. This is an install
environment limitation, not a dependency upgrade or lockfile replacement.

Frontend acceptance against that locked dependency tree:

```text
npm test
168 passed, 0 failed

node .\node_modules\eslint\bin\eslint.js src --max-warnings=0
exit code 0

$env:VITE_E2E_AUTH='1'; $env:VITE_E2E_ADMIN='1';
$env:VITE_PERSONALIZED_JOBS_DATA_MODE='real';
$env:VITE_REPLACE_LEGACY_JOBS_NAV='1';
node .\scripts\write-release-metadata.mjs;
node .\node_modules\vite\bin\vite.js build --logLevel error
1148 modules transformed; exit code 0

node --test .\scripts\production-build.test.mjs
1 passed, 0 failed
```

`npm run check` also reran all 168 unit tests, then stopped at
`eslint is not recognized` because the stalled npm install did not create
`frontend/node_modules/.bin/eslint.cmd`. Direct execution of the installed
locked ESLint and Vite entrypoints passed. The production assertion was run
with the repository's explicit real-mode/legacy-navigation flags; no runtime
or provider request was made.

The backend regression was rerun with the mandated interpreter:

```text
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest -q tests/test_acquisition_analytics.py tests/test_acquisition_audit_permissions.py tests/test_acquisition_quality.py tests/test_phase_a_routes.py
27 passed in 6.67s
```

Local API and rendered-page exercise used only the sanitized
`tests/fixtures/rc025_operational_dashboard.json` in an isolated ignored
SQLite directory. The local API response and permission boundary were:

```text
GET http://127.0.0.1:8000/v1/admin/acquisition/analytics?... (Bearer e2e-token)
200; schema acquisition_analytics_v1; master_rows 17601; targets 5;
partial partial-company; failed-unknown-cost jobs_observed null;
failed-unknown-cost cost unknown; worker-offline stale
GET without credentials: 401
GET with invalid credentials: 401
```

The local frontend was run with Vite's `/v1` proxy at
`http://127.0.0.1:4173`, and the page was opened at:

```text
/admin/analytics?range=7d&start=2026-08-05T00%3A00%3A00Z&end=2026-08-12T00%3A00%3A00Z&timezone=UTC
```

The browser executed the actual page/API request, clicked the read-only
`Refresh` control, and the visible DOM showed:

- `0 / 0` for queue failures/retries; no `NaN`.
- Partial Company: observed 2, accepted 1, published 1, rejected 1.
- Failed Unknown Cost: observed/accepted/published/rejected all `Unknown`,
  with unknown cost and a bounded retry review action.
- `worker-offline`: stale heartbeat, despite stored status `running`, with
  unknown resources.
- Baseline cards for 17,601 rows, 7,513 existing IDs, 10,088 missing IDs,
  and 11,907 unique organizations.
- Main-page buttons contained only `Refresh`; no acquisition mutation control
  was rendered. The admin role was visible from the test-only session.

No provider, acquisition, paid, deployment, production migration, or live
network action was performed. Temporary local servers were stopped after the
exercise. The isolated fixture database remains under the ignored
`.backend_test_tmp\rc025_browser` path for recoverable local inspection and
was not copied into application data.

## Baseline and dependency interpretation

The response preserves the baseline contract facts: 17,601 master rows, 7,513
existing IDs, 10,088 missing-ID rows, 11,907 unique numeric LinkedIn
organizations and 37 conflicting organizations. These are source-contract
facts, not counts inferred from the smaller application database.

`evidence_verified_eligible` is counted only from an explicit persisted
manifest/runtime configuration flag. If the RC-005 reconciled manifest is not
mounted, the value is `null`; enabled state is not treated as evidence. Scan
group and explicit employer counts are likewise `null` when the current target
configuration does not persist them. No RC-005 manifest or sidecar was copied
or applied here.

The plan still gates live acceptance on RC-005/016/018/019 producer, worker and
recovery evidence. RC-026 must receive this integrated read model before its
benchmark/cost work; RC-028 Gate A must precede RC-029. RC-029 was not started.
Optional RC-030 remains independent of hosting but still waits for RC-025
integration and was not started.

## Limitations

- This is an offline read model over existing SQLite/Turso-compatible tables;
  it does not prove live collector coverage, provider availability, or host
  capacity.
- Worker disk/RAM values are read only from explicitly reported worker
  metadata. Missing values are `null`; no host inspection is performed.
- DB latency is a local read-only `SELECT 1` measurement, not a Turso/network
  latency claim. Retention telemetry is explicitly unknown because no durable
  retention table is present in this contract.
- Provider throttling and limits use durable request/budget rows only. No
  provider was activated and no request was made.
- The coverage endpoint bounds returned target rows at 5,000 and reports when
  truncation occurs. The master denominator is still the complete frozen
  source-contract count.
- Frontend unit, lint, production-build, and local UI/API evidence now pass
  against the installed locked package tree. A clean `npm ci` exit remains
  blocked by the Windows npm stall described above; the lockfile itself is
  unchanged.
- This remains offline evidence. It does not establish live provider
  availability, host capacity, production permissions, or actual collector
  coverage.

## Handoff to Chat C

The implementation commit is recorded below. Chat C should integrate this tip
only after checking the target and B/C worktree state, then run the focused
backend and frontend tests from the accepted integrated tip. C owns conflict
resolution, route/release integration and any later shared changes.

Implementation commit: **`297e6827`**

The verification fix and evidence are in the subsequent commit recorded below.
Chat C may integrate the immutable tip after checking the target/B/C state;
Chat A is frozen for INT-1 after this handoff. RC-029 and optional RC-030 were
not started, and RC-025 live operational acceptance remains pending runtime
and data verification.

Verification source commit: **`d5f7b561d2a7c6cf07287a4b9bf61fb02c4572ae`**

Next dependency: **RC-025 integration review**, then RC-026 comparable offline
benchmark inputs and RC-028 Gate A before RC-029. Do not treat this offline
fixture as live RC-027/028/029 evidence.

## Targeted rollback

This slice creates no application data, provider state, migration, deployment
artifact or production side effect; no data rollback is required. Before
integration, C can omit the implementation commit from the integration branch.
After integration, revert only the verification commit and then the prior
documentation/implementation commits as needed, using `git revert` on the
exact immutable SHAs after checking that no later change depends on the
additive `coverage`/`health` fields. Do not reset or whole-file-restore the
target checkout. The source master and all existing runtime state remain
unchanged; the browser fixture database is temporary, ignored, and can be
removed after independently verifying that no local process still uses it.
