# Chat A handoff — RC-025

Status: **verified offline; implementation complete for the bounded read model; live/integrated acceptance pending**.

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
- Full frontend suite/build evidence requires dependencies to be available in
  an already provisioned offline environment.

## Handoff to Chat C

The implementation commit is recorded below. Chat C should integrate this tip
only after checking the target and B/C worktree state, then run the focused
backend and frontend tests from the accepted integrated tip. C owns conflict
resolution, route/release integration and any later shared changes.

Implementation commit: **`297e6827`**

Next dependency: **RC-025 integration review**, then RC-026 comparable offline
benchmark inputs and RC-028 Gate A before RC-029. Do not treat this offline
fixture as live RC-027/028/029 evidence.

## Targeted rollback

This slice creates no application data, provider state, migration, deployment
artifact or production side effect; no data rollback is required. Before
integration, C can omit the implementation commit from the integration branch.
After integration, revert only the documentation commit and this RC-025
implementation commit (implementation last, in reverse order), after checking
that no later change depends on the additive `coverage`/`health` fields. Do not
reset or whole-file-restore the target checkout. The source master and all
existing runtime state remain unchanged.
