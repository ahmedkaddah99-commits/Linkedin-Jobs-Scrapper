# AA-P03 policing gate — FAIL

Date: 2026-08-01
Branch: `deployment/render-turso-r2`
Prior gate baseline: `AA-P02` (`docs/assisted-apply/gates/AA-P02.md`)
Reviewed commits: `6a27555` (AA-222), `a279ea2` (AA-223), `7605a62` (AA-224), plus their parent Assisted Apply implementation through `2e56d02`.

## Verdict

**FAIL.** AA-P03 does not authorize AA-225. A release-blocking adapter/executor boundary contradiction remains, and the complete backend suite did not finish within the controlled 240-second run. The gate must be rerun after bounded remediation; acceptance criteria were not changed.

## Blocking findings

### P03-B1 — Adapter runners still mutate DOM directly

Repository-confirmed. `packages/ats-core/src/index.ts:900-987` implements
`StandardFactsAdapter.fill`; it calls `executeNativeValueAction`, uses the
controlled page bridge, calls `control.blur()`, waits, and verifies the DOM.
`packages/ats-core/src/index.ts:1422-1443` (`runGreenhouseStandardFacts`)
and `:1501-1524` (`runLeverStandardFacts`) call `adapter.fill(...)` directly.
The same functions are the application-form execution path used by
`apps/browser-extension/entrypoints/application-form.ts:89-127`.

This contradicts the locked AA-216/AA-219/AA-220 contract that adapters
inspect and return declarative plans while the centralized executor performs
mutations. The static boundary script does not catch it because it scans only
for terminal DOM/navigation APIs and does not prohibit `adapter.fill` or
adapter-owned mutation. The adapter unit tests prove planning in
`apps/browser-extension/tests/unit/aa219-greenhouse-adapter.test.ts` and
`aa220-lever-adapter.test.ts`, but the browser execution path does not use
those plans.

Bounded remediation: split the adapter execution API from planning; make both
Greenhouse and Lever runners return declarative actions plus verification
metadata; have one approved central executor consume those actions; remove or
privatize adapter-owned mutation; add a structural test that fails on adapter
mutation/execution calls and a Playwright assertion that the production
runner uses the central executor. Do not broaden adapter scope or change final
submission behavior.

### P03-B2 — Complete backend suite timed out without a result

Execution evidence: `.venv\\Scripts\\python.exe --version` returned Python
3.12.7. The independent command `.venv\\Scripts\\python.exe -m pytest -q`
was terminated by the 240-second tool timeout with exit code 124 and no
completion summary. The relevant Assisted Apply/package suite did pass (100
tests, 17 subtests), but the repository-wide backend result is unknown.

Bounded remediation: split the full backend run into documented deterministic
CI shards or increase the controlled timeout after identifying the slow/hung
test; record a completed result and any reproducible failure before rerunning
AA-P03. Do not mark this as a flake without evidence.

## Invariant matrix

| Invariant | Evidence | Result |
|---|---|---|
| Greenhouse and Lever declarative-only adapters | `packages/ats-core/src/index.ts:900-987,1422-1443,1501-1524` | **FAIL — B1** |
| Approved precedence and sensitive answers | `packages/ats-core/src/index.ts:509-527,1414-1437`; adapter tests; Playwright package tests | PASS for covered paths |
| Repeatable-section idempotency | `packages/ats-core/src/reconciliation-spike.ts`; `apps/browser-extension/tests/e2e/aa202-reconciliation.spec.ts` | PASS for sanitized fixture cases; production adapter coverage remains bounded/manual |
| Exact document selection and verification | `backend/application/assisted_apply_package_service.py:517-626`; `apps/browser-extension/tests/unit/aa221-upload-intent.test.ts`; upload Playwright cases | PASS for covered grant/upload paths |
| Explicit retry and bounded attempts | `apps/browser-extension/src/preparation/local-session.ts:3-121`; `aa222-retry-recovery.test.ts`; `tests/test_aa213_preparation.py` | PASS |
| Extension/web state agreement | `apps/browser-extension/entrypoints/sidepanel/App.tsx:626-678`; `frontend/src/lib/assistedApplyPreparation.js`; AA-223 tests | Partial — no browser E2E proves web start → external command → backend status → exact-tab review as one flow |
| Sidepanel optional after permission | `apps/browser-extension/entrypoints/background.ts:REQUEST_PORTAL_PERMISSION`; `aa214`/host-permission tests | PASS for unit/extension paths; integrated web flow not proven |
| User-entered values preserved | `packages/ats-core/src/index.ts:900-940`; adapter tests; fixture tests | PASS for covered controls |
| Submitted remains explicit-user-owned | `packages/ats-core/src/submission-guard.ts`; `apps/browser-extension/src/success/possible-success-observer.ts`; 22 Playwright tests | PASS for exercised paths |
| No final-submission path in supported protocol | `apps/browser-extension/scripts/verify-assisted-apply-boundary.mjs`; `verify-manifest.mjs`; Playwright instrumentation | PASS for scanned/covered paths; B1 keeps executor-boundary risk open |
| Production feature disabled by default | `frontend/src/lib/assistedApplyPreparation.js:10-12`; `backend/application/assisted_apply_preparation_service.py:34`; UI guard in `AssistedApplyLaunchDialog.jsx:37,80-85,215-219` | PASS |
| Full backend result | Repository-wide pytest command above | **FAIL — B2** |

## Commands and results

All commands were run on `deployment/render-turso-r2` with the existing dirty
worktree preserved. The repository-required interpreter reported Python
3.12.7. Node reported v24.11.0 and npm v11.6.1.

- `git branch --show-current` → `deployment/render-turso-r2`.
- `git status --short` → unrelated pre-existing modifications only; none were
  edited or staged by this gate.
- `npm --prefix apps/browser-extension run test:unit` → **23 files, 183 tests passed** in 63.15s.
- `npm --prefix apps/browser-extension run typecheck` → passed.
- `npm --prefix apps/browser-extension run verify:manifest` → passed.
- `npm --prefix apps/browser-extension run verify:assisted-apply-boundary` → passed.
- `npm --prefix apps/browser-extension run test:e2e` → **22 passed** in 49.7s.
  This included Greenhouse and Lever fixture execution and submission
  instrumentation; the AA-201 log reported zero submit events, requestSubmit,
  form.submit, Enter submissions, terminal clicks/requests, success
  transitions, and final navigation.
- `npm --prefix frontend run check` → **107 tests passed**, ESLint passed, Vite
  production build passed.
- `.venv\\Scripts\\python.exe -m pytest -q tests/test_aa03_application_package.py tests/test_aa213_preparation.py tests/test_assisted_apply_document_grants.py tests/test_tailored_document_generation.py tests/test_database_migrations.py tests/test_assisted_apply_connection_service.py tests/test_assisted_apply_corrections.py tests/test_assisted_apply_launch_prepare.py tests/test_assisted_apply_telemetry.py tests/test_assisted_apply_tracker_confirmation.py` → **100 passed, 17 subtests passed** in 47.83s.
- `.venv\\Scripts\\python.exe -m ruff check backend tests` → passed.
- `.venv\\Scripts\\python.exe -m pytest -q` → **timed out after 240s**, exit
  code 124; no repository-wide completion result.
- `git diff --check` → passed; warnings only reported that Git may normalize
  line endings in unrelated dirty files.
- A repository search for adapter DOM/navigation/submission APIs, raw IDs,
  telemetry payloads, placeholders, and skipped tests was performed. It
  confirmed test-only fixture code is marked in
  `apps/browser-extension/entrypoints/inactive-fixture-spike.ts`, but also
  exposed the unscanned `adapter.fill` boundary described in B1.

## Reviewed files and artifacts

- `packages/ats-core/src/index.ts`, `declarative-actions.ts`,
  `submission-guard.ts`, `telemetry.ts`, and `page-bridge.ts`.
- `packages/extension-messages/src/index.ts`.
- Greenhouse/Lever adapter tests and fixture Playwright tests.
- `apps/browser-extension/entrypoints/application-form.ts` and `background.ts`.
- `apps/browser-extension/entrypoints/sidepanel/App.tsx`, local preparation
  state, retry tests, upload tests, manifest and boundary scripts.
- `backend/application/assisted_apply_preparation_service.py`, preparation
  domain/routes, package/document-grant services, and relevant Python tests.
- `frontend/src/components/AssistedApplyLaunchDialog.jsx` and
  `frontend/src/lib/assistedApplyPreparation.js` plus tests.
- Architecture records AA-219, AA-220, AA-222, AA-223, and AA-224, and
  `docs/assisted-apply/gates/AA-P02.md`.

## Authorization

**AA-P03: FAIL.** Block AA-225 until B1 and B2 are remediated within their
bounded scopes. Then rerun this gate independently; do not authorize the next
phase based on the current green targeted tests.
