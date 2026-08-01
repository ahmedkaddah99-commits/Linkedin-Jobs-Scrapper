# AA-201 inactive-fixture browser foundation spike

Status: bounded test-only spike; no production submission behavior is introduced.

Related baseline: [Assisted Apply architecture baseline](assisted_apply_architecture_baseline_2026-08-01.md).

## Scope and labels

- **Repository-confirmed** means observed in the files and symbols cited below.
- **Externally verified** means supported by official Chrome documentation.
- **Inferred** means a conclusion from repository evidence or test observation, not a platform guarantee.
- **Proposed** means intentionally disposable spike behavior or an unresolved future choice.

The implementation is limited to the sanitized local Greenhouse and Lever fixtures. It does not add a backend preparation-session table, status UI, Workday support, repeatable-section production behavior, AI, broad host permissions, schema changes, dependencies, deployment settings, or real-application submission behavior.

## Spike flow

**Repository-confirmed:** `apps/browser-extension/entrypoints/background.ts` symbols `runInactiveFixtureSpike`, `waitForFixtureTabReady`, `isInactiveSpikeRequest`, and `isInactiveSpikeActivation` implement this sequence:

1. The testing-only service-worker message handler receives `AA201_START_INACTIVE_FIXTURE_SPIKE`.
2. `browser.tabs.create({ url, active: false })` creates the locally owned fixture tab.
3. `tabs.onUpdated` plus `tabs.get` wait for `status: "complete"` and exact URL, including the initial `about:blank` transition.
4. The service worker installs the readiness listener, injects `/inactive-fixture-spike.js`, and waits for `AA201_INACTIVE_FIXTURE_READY` from the exact tab.
5. The injected disposable runner installs its command listener before sending readiness, runs the existing `runGreenhouseStandardFacts` or `runLeverStandardFacts` primitive, creates a dummy PDF `File`, and calls existing `uploadApplicationDocument`.
6. It reports `AA201_INACTIVE_FIXTURE_COMPLETED`; the service worker returns the tab ID, `active: false`, readiness, response, and completion report.
7. `AA201_ACTIVATE_INACTIVE_FIXTURE_TAB` verifies the exact tab still belongs to `http://127.0.0.1:4174/` and updates only that tab to `active: true`.

**Externally verified:** Chrome documents that `tabs.create` can create tabs and that the `active` property controls whether a tab is active; the Chrome API reference documents `active` as defaulting to `false`. Chrome also documents that `scripting.executeScript` injects a file into a target tab and waits for a returned Promise to settle. Sources: [Chrome tabs API](https://developer.chrome.com/docs/extensions/reference/api/tabs), [Chrome scripting API](https://developer.chrome.com/docs/extensions/reference/api/scripting).

**Proposed/disposable:** The `inactive-fixture-spike.ts` runner and the `AA201_*` message names are spike protocol, not a production contract. The reusable parts are the ATS standard-facts and document-upload primitives in `packages/ats-core/src/index.ts`.

## Fixture coverage and evidence

**Repository-confirmed:** `apps/browser-extension/tests/e2e/aa201-inactive-fixture.spec.ts` runs the same flow against both exact fixture URLs, asserts representative field readback, asserts the dummy PDF file input readback, verifies the completion report, verifies the exact tab ID remains inactive before activation, then verifies that same tab becomes active after review.

**Repository-confirmed:** The fixture instrumentation in `apps/browser-extension/tests/fixtures/greenhouse-application.html` and `lever-application.html` counts:

- native `submit` events;
- `HTMLFormElement.prototype.requestSubmit`;
- `HTMLFormElement.prototype.submit`;
- Enter key paths inside forms;
- submit-control clicks;
- fetch and XMLHttpRequest URLs matching submit/application;
- success-marker mutations;
- same-document `history.pushState`/`replaceState` URL changes and `beforeunload`.

**Test evidence:** Both tests emitted sanitized evidence with every signal equal to `"0"`:

```text
greenhouse: tab inactive before activation, upload=uploaded,
submitEvents=0, requestSubmitCalls=0, formSubmitCalls=0,
enterSubmissions=0, terminalClicks=0, terminalRequests=0,
successTransitions=0, finalNavigation=0
lever: same result
```

**Inferred:** No inactive-tab throttling was observed during these local runs: readiness, field verification, upload verification, completion, and activation all completed within the Playwright test timeouts while the tab stayed inactive. This is not evidence of a production-site throttling guarantee; the fixtures contain no network or background timer workload that could model every Chrome throttling condition.

## Repository boundaries and unresolved items

**Repository-confirmed:** Existing external-message handling is in `apps/browser-extension/entrypoints/background.ts` `browser.runtime.onMessageExternal.addListener`; its sender is restricted by `isExactRunrWebSender`, and production launches require HTTPS. Existing in-extension messages use the side-panel sender guard and content sender/frame checks. Existing optional host-permission and explicit-gesture behavior remains in `src/permissions/host-permissions.ts` and the side panel flows documented by AA-200.

**Repository-confirmed:** The implementation does not exercise production package binding, document grants, session TTLs, retry URL recovery, tailored-CV identity preservation, or production success confirmation. Those remain covered by the AA-200 baseline and existing tests, not by this spike.

**Fixture/test gaps:** There is no real ATS network traffic, no real user account, no real application submission, no browser-matrix coverage, no long-duration inactive-tab run, no discarded/frozen-tab recovery test, no extension restart during the inactive run, and no server-side terminal-request oracle. The fixture instrumentation and unchanged URL checks are therefore bounded local evidence only.

**Unresolved decision:** Whether a future production design should use a background-owned inactive tab, an active-tab/user-gesture flow, or another browser-supported interaction model remains open. This spike records feasibility evidence without selecting that architecture.

## Test record

All commands ran on branch `deployment/render-turso-r2`; no commit was created.

- `npm run typecheck` — passed.
- `npm run test:unit` — 13 files, 137 tests passed.
- `npm run verify:manifest` — passed: guarded Chrome MV3 manifest and source boundary verified.
- `npm run test:e2e` — 14 tests passed, including the two AA-201 fixture tests.
- Focused command `npm run build:test; npx playwright test tests/e2e/aa201-inactive-fixture.spec.ts --reporter=line` — 2 passed.

No real application was opened or submitted.
