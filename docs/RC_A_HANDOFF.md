# Historical Chat A handoff — RC-025 (superseded)

Status: **Historical RC-025 baseline. The current reconciliation amendment is below and supersedes this status.**

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

## RC-025 FIX-A acceptance mapping

FIX-A closes the local frontend verification slice. The statuses below keep
offline fixture evidence separate from the checks that require C's integrated
runtime and the later live-source pilot.

| Plan acceptance criterion | Result | Evidence and remaining action |
| --- | --- | --- |
| 1. Per-company/source eligibility, attempt/success, completeness, job outcomes, stop reason, freshness and next action | Satisfied offline for the read model/UI contract; integrated verification pending | The fixture page rendered eligibility evidence, scan state, observed/accepted/published/rejected values, stop reason, freshness and next action. The API includes `last_attempt_at` and `last_success_at`. After runtime integration, verify those fields and actual worker/cycle metadata on the dashboard. Live-source completeness/failure evidence belongs to RC-027. |
| 2. Reconciled totals without double-counting master rows, employers, scan groups and source tasks | Satisfied offline for the bounded read model; integrated counts pending | The page kept the frozen denominator separate from runtime targets and showed the 17,601-row baseline with five fixture targets. Reconcile the corresponding integrated database counts after C's merge. |
| 3. Frozen baseline, evidence-verified eligibility and review/retry backlogs | Satisfied offline for baseline/read-only behavior; manifest data action pending | The page rendered 17,601 rows, 7,513 existing IDs, 10,088 missing-ID rows and 11,907 unique organizations, with identity/alias/negative-result/due-retry backlogs. Eligibility is verified only from explicit persisted evidence; no manifest or sidecar was applied here. |
| 4. Queue age/duration, failures/retries, heartbeat age, DB latency, resources and provider throttling by role/version | Satisfied offline for display semantics; actual metadata verification pending | The fixture rendered `0 / 0` failures/retries, queue and duration fields, local DB latency, worker role/version, stale heartbeat and unknown resources. Re-run against the integrated runtime's actual worker/cycle metadata. |
| 5. Missing-worker, stale-coverage, stuck-task and spend/retention alerts; heartbeat-based Online state | Satisfied offline for covered fixture states; integrated/live verification pending | The fixture exercised stale worker/coverage, stuck-task and spend-limit/unknown-limit states, and stored `running` did not override a stale heartbeat. Confirm missing-worker and retention behavior with the durable metadata available after integration. |
| 6. Scoped/audited admin recovery actions, normal-user prohibition and redacted logs | Satisfied offline for the RC-025 read-only slice; runtime audit verification remains | The focused backend suite passed 27 tests; authenticated local GET returned 200, unauthenticated/invalid requests returned 401, and the actual page exposed only `Refresh`, with no acquisition mutation control. No live recovery action was invoked. |
| Plan verification: offline worker, stale task, partial company and unknown-cost fixture states | Satisfied offline | The actual browser page rendered stale `worker-offline`, partial-company counts, and failed-unknown-cost counts as `Unknown` rather than zero, including the bounded review action. |

Post-integration action: after C integrates this immutable tip, verify the
dashboard against the real local/integrated API data available at that stage,
including worker heartbeat, cycle/task status, attempt/success timestamps and
role/version metadata. Record the endpoint, runtime identifiers and observed
values as integrated evidence; do not substitute the committed fixture.

RC-027 action: collect live-source failure and coverage evidence during the
authorized RC-027 pilot. That evidence is intentionally deferred and is not a
prerequisite for closing this local FIX-A verification slice. No production run,
provider request or live coverage claim is made by this handoff.

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
# Current reconciliation amendment — RC-025, RC-029 preparation, and RC-030

Date: 2026-09-09

Status at this handoff:

- RC-025: implementation and local UI/API verification complete; integrated
  operational acceptance remains pending actual acquisition-worker data from
  RC-027/C. The local Jobs fixture is not acquisition-worker evidence.
- RC-030: offline implementation complete and verified through the local
  authenticated API, rendered Jobs page, persisted first-party events, and
  admin product-analytics view. Production/staging acceptance remains pending
  deployment of this tip and real event/data verification.
- RC-029: deterministic wave-manifest preparation complete. Live expansion was
  not executed because RC-026 capacity evidence and RC-028 Gate A acceptance
  are not present in the current C handoff. No mapping was applied and no
  provider was contacted.

The A worktree is
`C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview-rc-a-observability-growth`
on `temp/rc-a-observability-growth`. It was fast-forwarded from C's accepted
target tip `f9417f2286c4d423bbf16ab15e2c90fe36d3f625`; the persistent target,
B worktree, and C worktree were not edited. The implementation commit is
`bdd58615`; the versioned browser walkthrough is `e728e364`.

## Exact changed files

Implementation and test files:

- `backend/application/product_analytics.py` — bounded, privacy-safe RC-030
  funnel, retention, feature-usage, latency, failure, environment, and
  exclusion projection.
- `backend/application/expansion_wave_manifest.py` — deterministic RC-029
  employer-grouped wave planner; validates the RC-005 task gate and never
  applies mappings or performs requests.
- `backend/application/services.py` — narrow shared integration: authoritative
  runtime environment tagging for analytics events and additive
  `product_analytics` output on the existing admin overview.
- `backend/profiles/cv_upload_jobs.py` — backend-confirmed, idempotent
  `profile_ready` event after usable CV processing; no CV contents are sent.
- `scripts/build_rc029_wave_manifests.py` — explicit-cap offline CLI for the
  wave planner.
- `frontend/src/lib/analytics.js` — asynchronous first-party event sink and
  primitive allowlist; Firebase remains the existing optional secondary sink.
- `frontend/src/lib/personalizedAnalyticsPayload.js` — bounded job/filter/
  feedback fields.
- `frontend/src/context/SessionContext.jsx` — first-party sink wiring and
  explicit local API base support in the browser-test provider.
- `frontend/src/components/personalized/JobsWorkspace.jsx` — user-visible
  Jobs events and real/synthetic data-mode propagation; no internal fields are
  exposed.
- `frontend/src/components/UpgradeModal.jsx` — removed its duplicate direct
  analytics POST while preserving the existing event.
- `frontend/src/pages/AdminEventsPage.jsx` — read-only RC-030 funnel,
  retention, feature, latency/failure, environment, and exclusion view.
- `tests/fixtures/rc030_local_jobs_seed.py` — disposable published employer/
  LinkedIn-shaped Jobs API fixture with viewer and admin tokens.
- `frontend/scripts/rc030_local_browser_check.mjs` — reproducible local
  authenticated user/dashboard walkthrough.
- `tests/test_product_analytics.py`,
  `frontend/src/lib/analytics.test.js`, and the relevant
  `tests/test_backend_api.py` assertions.
- `tests/test_rc029_wave_manifest.py` — deterministic grouping, cohort
  deferral, integrity, and cap tests.

No producer, migration, release, VPS, Turso, R2, or provider file was changed.
`backend/application/services.py` is a C-owned shared integration surface;
Chat C should resolve any overlap rather than replacing newer changes.

## Commands and results

All Python commands used the required interpreter:

`C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe`

```text
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
Python 3.12.7

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest tests/test_product_analytics.py tests/test_phase_c_personalized_jobs.py tests/test_rc010_first_acquisition_slice.py -q
8 passed in 7.33s

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest tests/test_source_eligibility_manifest.py tests/test_rc029_wave_manifest.py -q
10 passed in 3.48s

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest tests/test_product_analytics.py tests/test_backend_api.py -k "product_analytics or cv_upload_is_idempotent_for_same_file_content" -q
4 passed, 124 deselected in 14.02s

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m ruff check backend/application/expansion_wave_manifest.py scripts/build_rc029_wave_manifests.py tests/test_rc029_wave_manifest.py
All checks passed!

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m py_compile backend/application/product_analytics.py backend/application/expansion_wave_manifest.py backend/application/services.py backend/profiles/cv_upload_jobs.py scripts/build_rc029_wave_manifests.py
exit code 0
```

The focused source-to-user regression suite passed. An earlier broader
`tests/test_backend_api.py` run reached 125 passed and 3 failures in unrelated
pre-existing tracker expectations:
`test_tracker_api` (fixture filename expectation) and
`test_tracker_ats_detail_returns_persisted_read_only_diagnostics`
(attempt-history expectation). No tracker code was changed.

Frontend dependency and acceptance checks:

```text
cd C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview-rc-a-observability-growth\frontend
npm ci
added 722 packages, audited 723; package-lock.json unchanged

$env:VITE_API_BASE_URL='http://127.0.0.1:8765/v1'
$env:VITE_E2E_AUTH='1'
$env:VITE_E2E_ADMIN='1'
$env:VITE_PERSONALIZED_JOBS_EXPERIENCE='1'
$env:VITE_PERSONALIZED_JOBS_DATA_MODE='real'
$env:VITE_REPLACE_LEGACY_JOBS_NAV='1'
npm run check
170 passed, 0 failed; ESLint exit code 0; 1148 modules transformed; Vite exit code 0

node --test scripts/production-build.test.mjs
1 passed, 0 failed
```

The npm audit summary reported 19 existing dependency advisories (2 low,
4 moderate, 11 high, 2 critical). No `npm audit fix` or dependency upgrade
was run.

## RC-025 real-data status

C's current handoff still reports that RC-027 has no real source request,
Turso/R2 publication, provider charge, R2 upload/download, CORS/browser, or
authenticated production-like UI publication evidence. Therefore no actual
acquisition-worker heartbeat, cycle, source outcome, publication, request, or
cost record was available to verify in this pass. The previously tested
synthetic customer worker remains distinct from an acquisition worker.

The RC-025 dashboard implementation still preserves unknown and failed
observations as unknown and derives liveness from heartbeat freshness. It does
not overwrite `last_success_at` with a failed attempt. After C/B make actual
runtime metadata available, verify the dashboard at the integrated endpoint
for worker role/version, heartbeat age, cycle/task identifiers, source
outcomes, publication ID/state, request/cost records, and attempt versus success
timestamps. This is a required integrated/live follow-up, not satisfied by
the fixture.

## RC-030 event contract and evidence

The first-party path is:

`authenticated frontend action -> POST /analytics/events -> analytics_events -> GET /analytics/overview -> /admin/events`

The existing Firebase event call remains available, but the new first-party
sink is the database-backed source for the admin product view. The sink is
asynchronous and cannot block or fail a user action.

| Funnel stage | Event/evidence | Classification |
| --- | --- | --- |
| Signup | existing `user_signed_up` | backend-confirmed |
| Usable profile | new idempotent `profile_ready` after CV worker success | backend-confirmed |
| Relevant job | `job_relevant_viewed` after the detail API succeeds | interaction |
| Saved | `job_saved` after the save API succeeds | backend-confirmed action result |
| Prepared application | existing backend `cv_generation_completed` | backend-confirmed |
| Confirmed outcome | `application_status_updated` only for confirmed status/email evidence | backend-confirmed |
| Paid conversion | existing `subscription_started` | backend-confirmed |

`apply_link_opened`, `application_preparation_opened`, and
`application_marked_applied` remain separate interaction signals. Opening an
employer page or marking a job applied is not treated as confirmed submission.
`job_relevance_feedback` carries only a controlled reason code.

Projection rules:

- Raw delivery records remain append-only; funnel counts deduplicate users and
  use the earliest same-environment signup/stage boundary.
- The query window is 90 days, start-inclusive/end-exclusive. Retention uses
  signup-week cohorts and exact D7 `[+7d,+8d)` and D30 `[+30d,+31d)` windows;
  immature denominators render null rather than zero.
- The backend writes `RUNR_ENV` into the event payload, overriding any client
  label. The projection separates production, staging, development, local,
  test, and internal traffic.
- Test/internal IDs, explicit exclusion flags, and test email domains are
  excluded from product denominators and counted by reason. No email is
  returned in the projection.
- Only allowlisted primitive properties are sent to the first-party sink,
  strings are capped at 160 characters, and CV contents, document contents,
  credentials, raw descriptions, and sensitive free text are excluded.
- No sampling is applied to allowed first-party events. The projection bounds
  reads to 90 days; physical raw-event deletion remains governed by the
  existing database policy and is not claimed here.
- No paid provider, replay tool, or new analytics infrastructure was added;
  incremental RC-030 provider spend is `$0`. Existing Firebase behavior and
  the application's legal consent policy remain unchanged. Before production
  enablement, C must confirm that the existing consent policy permits these
  authenticated, non-replay product events; this slice does not introduce
  cookie/replay collection.
- Latency is bucketed as `<1s`, `1-5s`, `5-20s`, `20s+`, or `unknown`.
  Failure categories use bounded error/failure codes, never raw messages.
  The dashboard labels these relationships as associations, not causal
  claims.

Local API/UI evidence used only
`C:\Users\ahmed\AppData\Local\Temp\runr-rc030-local-api-20260909-05`.
The server was started with `RUNR_ENV=development`, SQLite, local object
storage, `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED=false`, and loopback API/CORS
settings. The exact versioned walkthrough was:

```text
cd C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview-rc-a-observability-growth\frontend
$env:RC030_USER_TOKEN='<seed output, not committed>'
$env:RC030_ADMIN_TOKEN='<seed output, not committed>'
$env:RC030_UI_URL='http://127.0.0.1:4173'
$env:RC030_API_URL='http://127.0.0.1:8765/v1'
node scripts/rc030_local_browser_check.mjs
```

Result:

```json
{
  "user_flow": {
    "title": "Operations Analyst",
    "company": "Acme Labs",
    "filtered_count_visible": true,
    "saved_feedback_observed": true,
    "apply_feedback_observed": true,
    "apply_url_opened": "https://boards.greenhouse.io/acme/jobs/a",
    "preparation_panel_visible": true,
    "internal_fields_visible": false
  },
  "admin_flow": {
    "dashboard_visible": true,
    "funnel_visible": true,
    "retention_visible": true,
    "feature_usage_visible": true,
    "latency_failure_visible": true,
    "environment_visible": true
  }
}
```

The direct API check returned one Berlin job, `job-a`, company `Acme Labs`,
verified Apply URL `https://boards.greenhouse.io/acme/jobs/a`, user state
`saved`, evaluation state `available`, and product schema
`product_analytics_v1`. Persisted first-party rows from the final run were
tagged `real` after the data-mode fix. Earlier synthetic rows from prior
attempts remain in the disposable local database as accounted test history;
they are not production evidence.

## RC-030 acceptance mapping

| Plan criterion | Result | Evidence / remaining action |
| --- | --- | --- |
| Signup → usable profile → relevant job → saved/prepared application → confirmed outcome, separating backend confirmation from clicks | Satisfied offline; production data pending | Pure projection tests, backend profile-ready assertion, local authenticated Jobs flow, and explicit dashboard labels passed. Verify real signup/profile/application-status records after deployment. |
| Join task IDs, latency bands, versions, failure categories to usage | Satisfied offline | `product_analytics.py` projection and tests cover job/run IDs, duration buckets, versions, failures and later value users. Verify actual acquisition task IDs after RC-027. |
| Deduplicate and separate internal/staging/production | Satisfied offline | Environment overwrite, exclusion rules, deduplicated funnel, and environment test coverage passed. Verify integrated `RUNR_ENV` and internal-user policy with C. |
| Document fields, consent, sampling, retention, spend; exclude sensitive content | Satisfied as documented offline contract | Allowlist tests, no-new-provider path, explicit 90-day/read-retention and consent notes above. C must confirm legal consent before production enablement. |
| Dashboard answers dropoff, return-driving feature, slow-processing effect, and feedback gaps | Satisfied offline | `/admin/events` rendered all product panels and the controlled relevance feedback path. Production event volume and causal interpretation remain unverified. |

## RC-029 preparation and dependency

`backend/application/expansion_wave_manifest.py` validates the RC-005 schema,
hash presence, canonical-ID integrity, both source task sets, and unique task
keys. It sorts by canonical company ID and keeps all selected employer and
LinkedIn tasks for one employer in the same wave. Cohorts are explicit:
`pilot`, `expansion` (non-pilot source-specific tasks), or `all`.

Each wave records unique employers, canonical IDs, LinkedIn organization
groups, source tasks, request cap, credit cap, maximum failure rate, queue-age
threshold, budget/request stop conditions, unclassified-result pause, and
accepted-result preservation. The CLI requires all cap/threshold values; it
does not invent capacity from a fixture.

Offline CLI preparation used the sanitized RC-005 fixture:

```text
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' scripts/build_rc029_wave_manifests.py --manifest 'C:\Users\ahmed\AppData\Local\Temp\rc029-wave-cli-20260909-01\source.json' --output 'C:\Users\ahmed\AppData\Local\Temp\rc029-wave-cli-20260909-01\waves.json' --cohort pilot --wave-size 2 --request-cap 40 --credit-cap 70 --max-failure-rate 0.2 --max-queue-age-seconds 900
{"output": "...\\waves.json", "wave_manifest_hash": "2b80c3663cd5da0fd5f49a076797042d3a553e52e6f660683e5653df78a1081b", "waves": 1}
```

The generated fixture plan selected 2 source tasks and deferred 6. It was
never supplied to a collector. To execute, C must first record RC-028 Gate A
acceptance and provide RC-026 measured capacity/provider limits; then
operations can run the CLI against the restored RC-005 manifest and record
partial, failed, unsupported, deferred, accepted, and published outcomes.
“All companies attempted” must not be reported as “all jobs collected.”

## Handoff to Chat C and RC-032

C should integrate source tips `bdd58615` and `e728e364`, plus this documentation
commit (the final immutable tip is reported in the completion message), after
checking the target branch, then reconcile the shared
`backend/application/services.py` hunk. Run the
focused Python suites and the correct-flag frontend `npm run check` on the
integrated result. Do not merge the disposable local database or tokens.

For RC-025, C/B must append actual acquisition-worker dashboard evidence:
worker IDs/roles/versions, heartbeat timestamps, cycle/task IDs, source
outcomes, publication ID/state, request and cost records, and explicit
attempt/last-success values. The synthetic customer-worker evidence must stay
labelled separately.

For RC-032, this lane contributes two walkthroughs: (1) published employer
and LinkedIn-shaped records through the authenticated Jobs API/page, including
filter, company, details, verified Apply URL, save and preparation behavior;
and (2) the admin Events page showing the RC-030 funnel, retention,
feature-usage, latency/failure context, environment separation, exclusions,
and controlled feedback interpretation.

## Targeted rollback

No production data, migration, provider state, deployment, acquisition run, or
live request was created. Before integration, C can omit
`bdd58615`/`e728e364`. After integration, use `git revert` on the exact
immutable commits, checking descendants first; do not reset or restore whole
files. If only RC-029 preparation must be removed, revert the commit and leave
the RC-030 commit intact only after checking the dependency order. The
additive analytics projection has no migration rollback. The disposable local
fixture database and temporary CLI outputs are recoverable local artifacts and
must only be removed after confirming no local process uses them.

## LinkedIn producer reliability follow-up after RC-027

Date: 2026-09-09

Worktree: `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview-rc-a-observability-growth`

Branch: `temp/rc-a-observability-growth`

Combined baseline ancestry verified: `5cd2ece533e4e7615a8b6a7b08516014d5b82748`

Implementation commit: `9ac2ab4182c66d1aecdb6150574fdce6012153ca`

Status: **implementation verified offline; RC-027 live acceptance remains
pending**. The current host pilot is not reclassified as complete and no live
request was made in this follow-up. C still owns integration, shared request
accounting, and the next combined pilot.

### Actual pilot diagnosis

The RC-027 receipt and the persisted producer database were reviewed without
changing the host. The four LinkedIn companies produced two partial scans each,
all with `PARTIAL_SUSPICIOUS_EMPTY`. The persisted producer state contained 8
runs, 8 company scans, 111 search cards, 20 producer jobs and 20 producer job
observations. The integrated receipt separately reports 22 transport
observations and 21 canonical jobs; that is an aggregation difference between
the producer state and the integrated staging database, not evidence that the
producer state was changed here.

The page evidence shows valid cards before later suspicious pages: helmag had
complete pages through starts 0-40, while NOVENTI and Vincenz had a complete
page at start 0; MALZERS had no persisted cards. Later pages were recorded as
`SUSPICIOUS_EMPTY`. The producer stores page status, body hash and a bounded
classification, but not the response body. Host journal queries also supplied
no acquisition entries, and the response bodies could not be copied because
the evidence files are root-only. Therefore the exact historical split between
source blocking, legitimate empty results, and a short malformed response is
not provable from RC-027 alone. It must not be relabelled as a parser failure
or a confirmed empty result.

The persisted detail state does establish the budget effect. Across the
producer runs, successful details were followed by `RETRY`/`BUDGET_EXHAUSTED`
rows: helmag had 35 cycle-1 and 43 cycle-2 detail failures, and NOVENTI had 5
cycle-2 failures. The receipt measured 190/200 cumulative attempts (135 in
cycle 1, 55 in cycle 2); provider credits and cost were reported as unknown by
transport, never zero. No lifecycle events were created for the partial scans,
and the integrated tasks remained `valid_snapshot=0`, `closure_safe=0`; no
publication occurred.

Disposition of the investigated causes:

| Area | Finding and disposition |
| --- | --- |
| Company filtering | `build_search_url` retains `f_C`, Germany `location`, and `geoId`; ownership still requires the card/detail company URL to resolve to the manifest group. Existing source-gate tests pass. |
| Pagination | No historical pagination defect can be proved without bodies. Offline replay now proves that multiple nonempty pages continue and only explicit empty termination completes; cap/saturation remains partial. |
| Suspicious-empty classification | A demonstrated defect was fixed: a short 200 fragment containing a valid card was previously marked suspicious before parsing. It is now parsed first; short cardless/non-no-result responses remain suspicious. Historical suspicious pages remain unresolved. |
| Detail extraction | Apply fallback to the LinkedIn job URL was removed; an absent apply CTA is now blank at producer level and `unknown` at the observation boundary. Posted text now requires date-like evidence or a `time` element, so company text cannot become a posted date. Existing criteria, location, description, employment, workplace, applicant and external URL extraction remain covered. |
| Detail failure/budget | Retry and provider budget outcomes remain explicit. A failed attempt does not create a job or reset cached freshness. |
| Cache and resume | Pilot cycles reuse durable completed detail without issuing another detail request. Pending detail is transferred to the current run with its attempt count, due time and last error, rather than receiving a fresh budget; the old queue row is marked `TRANSFERRED`. |
| Closure/publication | Existing lifecycle gates were preserved: only complete scan statuses reconcile absence. Partial, blocked, suspicious and budget-exhausted scans cannot close jobs or produce a valid zero snapshot. |
| Cost accounting | `WebshareTransport` now exposes actual attempt counts by kind, including retries; logical calls remain separately observable. Provider credits/cost remain unknown when the transport does not report them. |
| Wrapper/eligibility | `scripts/run_manifested_linkedin.py` was inspected and unchanged. It defaults to the dual-source pilot and requires `--include-single-source` for expansion; no employer producer or shared contract was edited. |

### Exact changed files

Commit `9ac2ab4182c66d1aecdb6150574fdce6012153ca` changes only:

- `scripts/master_linkedin_jobs_catalog.py`
- `tests/test_master_linkedin_jobs_catalog.py`
- `tests/test_producer_adapters.py`
- `tests/fixtures/linkedin_job_search_compact_valid.html`

No deployment, migration, backend shared contract, employer producer, VPS,
Turso, R2, provider account, or production data was changed.

### Offline commands and results

All Python commands used the repository interpreter required by `AGENTS.md`:

`C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe`

```text
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
Python 3.12.7

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest tests/test_master_linkedin_jobs_catalog.py tests/test_producer_adapters.py -q
67 passed in 12.61s

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest tests/test_master_linkedin_jobs_catalog.py tests/test_producer_adapters.py tests/test_rc009_normalization_publication.py tests/test_source_eligibility_manifest.py tests/test_rc010_first_acquisition_slice.py tests/test_acquisition_quality.py -q
89 passed in 16.77s

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m ruff check scripts/master_linkedin_jobs_catalog.py backend/acquisition/producer_adapters.py tests/test_master_linkedin_jobs_catalog.py tests/test_producer_adapters.py
All checks passed!

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m py_compile scripts/master_linkedin_jobs_catalog.py backend/acquisition/producer_adapters.py
exit code 0

git diff --check
exit code 0
```

The focused tests cover company/Germany URL scope, multi-page completion,
compact valid cards, detail fields and missing apply/date evidence, adapter
field preservation, retry-inclusive request caps, pilot cache reuse, pending
detail adoption, budget quarantine, and partial-scan lifecycle protection.
They replay sanitized fixture behavior and persisted-state classifications;
they do not reproduce the unavailable raw RC-027 response bodies.

### Acceptance mapping

| Requested proof | Result | Boundary |
| --- | --- | --- |
| Company filtering and pagination completion | Satisfied offline | C must verify page starts, terminal evidence and `f_C` on the next bounded live run. |
| Detail extraction, missing fields, supported fields and application URLs | Satisfied offline | C must verify the actual current guest markup and preserve response classification/raw evidence within the approved evidence policy. |
| Current-cycle cache attribution | Satisfied offline | Verify run/scan IDs in the next integrated state. |
| Pending detail resumes without repeating completed work | Satisfied offline | Verify queue transfer and attempt counts after a deliberately interrupted bounded run. |
| Retry/discovery/detail limits and explicit budget exhaustion | Satisfied offline for producer transport | C remains authoritative for the combined source/provider/browser cap. Cost is unknown unless the provider transport reports it. |
| Partial/blocked scans cannot close existing jobs | Satisfied offline and observed in RC-027 integrated state | No publication or closure may be inferred from successful cards inside a partial scan. |
| Complete status requires completion evidence | Satisfied offline | Historical RC-027 statuses remain partial. |

### Smallest live verification for C

After integrating `9ac2ab4182c66d1aecdb6150574fdce6012153ca`, C should run one
manifest-approved LinkedIn company for one bounded cycle under the existing
combined accounting owner: one worker/browser, retry limit 1, the existing
per-company attempt ceiling, and an explicitly recorded cumulative request and
cost cap. Do not expand eligibility or purchase/top up a provider.

The receipt should retain, without credentials, the request kind and actual
attempt count (including retries), each search start and classification, card
count, detail success/failure/pending counts, provider credit/cost or
`unknown`, scan status, lifecycle/closure decision, and publication decision.
The minimum pass is: every search URL retains the manifest company filter and
Germany filters; completion has explicit empty/validated-terminal evidence;
valid cards are not suspicious solely because the body is short; failed or
budget-exhausted detail work remains pending/partial; and no partial or blocked
scan closes or publishes existing jobs. A second bounded cycle on the same
company should verify completed detail cache reuse and pending-detail transfer
separately. This is the next live verification, not performed by A.

### Handoff and rollback

C may cherry-pick/integrate the immutable commit
`9ac2ab4182c66d1aecdb6150574fdce6012153ca` after checking for newer shared
work. Do not amend or rebase it. B remains the owner for employer/runtime
changes, and C remains the owner for shared contracts, deployment, VPS
mutations, and live request accounting.

RC-027 remains blocked on source-complete evidence, integrated runtime
verification, and C's acceptance decision; no later expansion should treat
this offline repair as live operational acceptance. To roll back only this
lane, review descendants and run `git revert
9ac2ab4182c66d1aecdb6150574fdce6012153ca` on the integration branch. Do not
reset, clean, or restore whole files. The revert removes only the producer
repair, focused tests, and sanitized fixture; it does not touch prior
analytics/expansion work or any host/provider state.
