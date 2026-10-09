# AA-P01 policing gate — PASS

Date: 2026-08-01  
Branch: `deployment/render-turso-r2`  
Reviewed commit: `2bf5e4e` (`AA-201 — Prove inactive-tab browser foundation`) plus uncommitted AA-P01 remediation changes  
Gate report commit: none

## Verdict

**PASS.** AA-P01 authorizes the next phase, subject to the explicit user
waiver of AA-P01-R1 below. AA-P01-R2, R3, and R4 are fixed and independently
tested.

## Reviewed artifacts

Reviewed committed AA-201 files, the AA-202/AA-203/AA-204 documentation and
spike artifacts, and these remediation files:

- `apps/browser-extension/src/application-url.ts` — `preparedApplicationUrlMatches`
- `apps/browser-extension/entrypoints/background.ts` — `bindRunrWebLaunch`
- `apps/browser-extension/tests/unit/application-url.test.ts`
- `backend/application/assisted_apply_package_service.py` — `get_package_for_extension`
- `tests/test_aa03_application_package.py` — bound-retrieval lifecycle test
- `packages/ats-core/src/reconciliation-spike.ts` — `reconcileVisibleEntries`
- `apps/browser-extension/tests/unit/aa202-reconciliation.test.ts`
- `apps/browser-extension/tests/e2e/assisted-apply.spec.ts`
- `apps/browser-extension/tests/e2e/aa201-inactive-fixture.spec.ts`
- `docs/architecture/assisted_apply_architecture_baseline_2026-08-01.md`
- `docs/architecture/assisted_apply_aa202_reconciliation_spike_2026-08-01.md`
- `docs/architecture/assisted_apply_aa203_workday_discovery_2026-08-01.md`

## Criterion evidence

### Chrome API claims — PASS

Claims about externally connected messaging, inactive tabs, tab updates,
optional permissions, and script injection are supported by official Chrome
documentation: [message passing](https://developer.chrome.com/docs/extensions/develop/concepts/messaging),
[tabs](https://developer.chrome.com/docs/extensions/reference/api/tabs),
[scripting](https://developer.chrome.com/docs/extensions/reference/api/scripting),
and [permissions](https://developer.chrome.com/docs/extensions/reference/api/permissions).
Repository symbols reviewed include `isExactRunrWebSender`,
`isExactSidePanelSender`, `runInactiveFixtureSpike`,
`reconcileVisibleEntries`, and `observePossibleSuccess`.

### Inactive-tab proof — PASS, bounded

AA-201 creates `active: false` tabs, waits on browser events and the content
readiness handshake, verifies the exact tab ID, fills both sanitized ATS
fixtures, uploads a dummy PDF, reports completion, and activates that exact
tab only afterward. The fixture instrumentation reported zero submit events,
`requestSubmit`, `form.submit`, Enter submissions, terminal clicks, terminal
requests, success transitions, and final navigation.

The evidence does not measure Chrome's internal throttling state. It proves
successful local completion within the controlled test timeout only.

### Reconciliation — PASS

`reconcileVisibleEntries` uses deterministic normalization, candidate arrays,
and employer/institution multimaps. It updates one unique confident match,
adds only when no plausible match exists, preserves unmatched entries, and
returns `review_required` on ambiguity. A same-run claimed ATS-entry set now
stops a second candidate from claiming the same entry; newly added entries are
also indexed so identical unmatched candidates cannot create duplicates. Unit
tests cover both collision forms, and E2E tests cover add/update/rerun,
reload, remount, same-employer roles, overlapping roles, ambiguity, and
unmatched preservation.

### Workday scope — PASS, conservative

AA-203 explicitly records that no Workday fixture, authorized account, or live
page was available. Repeaters, rich text, custom comboboxes/date pickers,
uploads, iframe/shadow boundaries, SPA remount persistence, intermediate
routes, and final-review selectors remain unverified. No adapter or permission
was introduced, and the executor recommendation is limited to proven native
controls.

### TTL, retry, and URL ownership — PASS

`get_package_for_extension` now raises `ApplicationPackageStateError` unless
the package is `APPLICATION_PACKAGE_STATUS_BOUND`; the backend test covers
created, launched, and bound retrieval. The frozen architecture record's
post-bind TTL decision is unchanged.

`bindRunrWebLaunch` now requires the returned immutable package job URL to
match the requested URL through `preparedApplicationUrlMatches`. Only the
fragment is normalized; missing, malformed, or different paths fail closed.
The URL helper tests cover equal URLs, fragments, different paths, and missing
values. The positive web-launch E2E uses the fixture's canonical URL.

### Final submission reachability — PASS

The reviewed `AtsAdapter` contract has no submit method; submission-forbidden
constants/tests and the AA-201 instrumentation enforce that supported actions
cannot submit. The test-only activation uses tab activation, not submission.
No production `form.submit`, `requestSubmit`, terminal click, terminal
request, or automatic success path was found.

### Permissions, backend tab IDs, and telemetry — PASS

Optional production permissions remain limited to Greenhouse/Lever. No backend
tab/window identifier or raw candidate/DOM/document telemetry was found in the
reviewed Assisted Apply paths.

## Findings and disposition

### AA-P01-R1 — unrelated AA-201 production change (waived)

`frontend/src/pages/CareerProfilesPage.jsx` contains an unrelated change in
the AA-201 commit. The user explicitly instructed this gate to ignore that
finding. It remains outside this gate's remediation scope and was not edited.

### AA-P01-R2 — exact package/job URL binding (resolved)

Resolved by `preparedApplicationUrlMatches`, the `bindRunrWebLaunch` guard,
the canonical fixture package URL, and URL helper tests.

### AA-P01-R3 — bound-state extension retrieval (resolved)

Resolved by the explicit `APPLICATION_PACKAGE_STATUS_BOUND` guard and the
backend lifecycle test. No consumed state exists in the current extension
retrieval domain path, so no artificial transition was added.

### AA-P01-R4 — same-run reconciliation claims (resolved)

Resolved by the claimed-entry invariant and deterministic unit tests for
duplicate candidate claims and duplicate unmatched additions. Existing
ambiguity tests remain unchanged and passing.

## Commands and results

- `git branch --show-current` → `deployment/render-turso-r2`.
- `.venv\Scripts\python.exe --version` → Python 3.12.7.
- `.venv\Scripts\python.exe -m pytest tests/test_aa03_application_package.py -q` → **13 passed, 4 subtests passed**.
- `npm run test:unit -- --run tests/unit/application-url.test.ts tests/unit/aa202-reconciliation.test.ts` → **2 files, 9 tests passed**.
- `npm run test:e2e` → **18 tests passed**, including AA-201 and AA-202 scenarios.
- `npm run typecheck` → passed.
- `npm run verify:manifest` → passed in the prior independent gate run.
- `npm test` in `frontend` → **102 passed, 0 failed** in the prior independent gate run.
- `git diff --check` → passed in the prior independent gate run.

## Authorization

**AA-P01: PASS.** R1 is explicitly waived by the user; R2, R3, and R4 are
resolved and independently tested. No commit was created.
