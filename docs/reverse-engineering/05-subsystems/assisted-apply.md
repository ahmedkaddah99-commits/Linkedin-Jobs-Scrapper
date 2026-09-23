> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14
> Update (T47, 2026-09-21): the L2 boundary gate now recursively scans `apps/browser-extension/entrypoints/**`, `apps/browser-extension/src/**` and `packages/ats-core/src/**`, detects synthetic pointer/keyboard activation, and runs in `check`, `check:all`, `check:edge` and both extension CI jobs. See §6.1 L2, §7, §9.1, §10 (WS9-G1, WS9-G4).

# Assisted Apply — extension-side subsystem

**Scope note (audit N-11).** This document covers Assisted Apply **from the browser extension's point of view**: the WXT extension in `apps/browser-extension`, the shared packages `packages/ats-core` and `packages/extension-messages`, the never-submit boundary, supported ATS adapters, the connection and token handshake as the extension performs it, and host permissions.
- Backend Assisted Apply **services** (connection service, package, preparation, document-grant, telemetry and tracker-confirmation services under `backend/application/`) are owned by WS-4 and described in [personalized-jobs-and-customer-app-services.md](personalized-jobs-and-customer-app-services.md).
- Backend Assisted Apply **routes** (`backend/api/routes/assisted_apply*.py`) are owned by WS-1 and described in [backend-api.md](../01-architecture/backend-api.md).
- Extension-origin configuration and auth are described from the security angle in [security-and-auth.md](../01-architecture/security-and-auth.md) (WS-6). CI jobs are in [ci-cd.md](../02-deployment/ci-cd.md) (WS-7).
- Companion WS-9 docs: [apps-and-extensions.md](../01-architecture/apps-and-extensions.md) covers the project structure, manifest and build, and [shared-packages.md](../01-architecture/shared-packages.md) covers package exports and consumers.

Here, route paths and service names are cited only to show what the extension calls.

---

## 1. Purpose and user-facing capabilities

"Runr Assisted Apply" (`apps/browser-extension/wxt.config.ts:7-9`, description: *"Review-first assistance for supported job applications. Runr never submits an application for you."*) is a Chrome/Edge MV3 extension that:

| Capability | What the user sees | Main code |
|---|---|---|
| Connect Runr account | Side panel "Connect" launches a browser auth window on the Runr web app; the extension gets a short-lived session | `apps/browser-extension/src/auth/connection-service.ts` |
| Receive a reviewed application package | The Runr web app ("Apply with Runr") binds a package to a tab or starts a preparation; the extension fetches the immutable package | `apps/browser-extension/entrypoints/background.ts` (`bindRunrWebLaunch`, `startPreparationCommand`) |
| Fill supported fields on Greenhouse / Lever | Standard facts and approved answers are filled into the live form, with readback verification | `packages/ats-core/src/index.ts` (`GreenhouseAdapter`, `LeverAdapter`, `executeApprovedField`) |
| Attach selected documents | The CV, cover letter or supporting document is downloaded through a document grant and attached to the exact upload field | `background.ts:uploadSelectedDocumentOnTab` (826), `packages/ats-core/src/index.ts:uploadApplicationDocument` |
| Review in side panel | Field rows, documents, corrections with a scope, retry/cancel/activate of a preparation | `apps/browser-extension/entrypoints/sidepanel/App.tsx`, `apps/browser-extension/src/review/panel-model.ts` |
| Possible-success detection | After the **user** submits, a confirmation banner or URL is reported as *possible* success for tracker confirmation | `apps/browser-extension/src/success/possible-success-observer.ts` |
| Adapter health telemetry | Aggregate outcome and error categories only; no candidate values | `packages/ats-core/src/telemetry.ts` |
| LinkedIn connections sync | The Runr web app asks the extension to read the user's LinkedIn connections page and upload a CSV snapshot | `apps/browser-extension/src/linkedin/connections.ts`, `apps/browser-extension/entrypoints/linkedin-connections.ts` |

**Never:** submit an application, click a terminal control, solve CAPTCHAs, accept legal terms or sign declarations. Legal-sensitivity answers are never autofilled (`application-form.ts:172-181` filter). See §6.

## 2. Owned paths and governing instructions

| Glob | Files @58a96674 | Notes |
|---|---:|---|
| `apps/**` | 77 | Only `apps/browser-extension/`: 9 entrypoints, 16 `src/`, 37 `tests/`, 3 `scripts/`, 4 icons, 8 root config/lock/README |
| `packages/**` | 12 | `packages/ats-core` (package.json + 9 src), `packages/extension-messages` (package.json + 1 src) |

Unchanged since `848408f3` (allocation carry-forward). The evidence-package claims were re-verified here by direct reads at `58a96674`.

Governing and supporting docs at baseline (checked against code where noted):
- `apps/browser-extension/README.md`: matches code on the PKCE `launchWebAuthFlow` connection, `storage.session`, and "no final-submit action". Its command list (`npm run check`, `npm run test:e2e`) matches `apps/browser-extension/package.json`.
- `docs/assisted-apply/runr-assisted-apply-ticket-pack.md` holds the AA ticket pack. Gates: `docs/assisted-apply/gates/AA-P01.md`, `docs/assisted-apply/gates/AA-P02.md`, `docs/assisted-apply/gates/AA-P03.md`. CI evidence: `docs/assisted-apply/ci/AA-225.md`. Pilot: `docs/assisted-apply/pilots/AA-226.md` (FAIL, 0/10 live forms). All are historical records dated 2026-08-01 and are not re-run.
- Architecture records live in `docs/architecture/assisted_apply_architecture_baseline_2026-08-01.md` and `docs/architecture/assisted_apply_aa2NN_*` (AA-201 … AA-224). Spot-checked: AA-219/220 adapters and AA-216 declarative executor match module names in `packages/ats-core/src/`.
- `docs/reports/runr_assisted_apply_permission_rationale_2026-07-18.md` documents the **narrow** permission model (API mandatory; Greenhouse/Lever optional). It **matches baseline code**, but it **conflicts with the owner's later decision** to grant broad access at install (see §6.3, WS9-G2).
- Owner standing decision (user memory `runr-extension-safety-posture`, 2026-08-15): broad host access at install, and a strict never-submit boundary enforced three ways. Verified against source in §6.
- Root `AGENTS.md` applies repository-wide.

## 3. Entry points and registered routes/commands

### 3.1 Extension entrypoints (WXT)

| Entrypoint | Kind | Injected / triggered by |
|---|---|---|
| `apps/browser-extension/entrypoints/background.ts` | MV3 service worker (`defineBackground`, L1015) | Always. Owns session secret, API calls, tab binding, message routing |
| `apps/browser-extension/entrypoints/sidepanel/App.tsx` (+ `main.tsx`, `index.html`, `style.css`) | Side panel page `sidepanel.html` | Toolbar action (`action.onClicked` L1020; `setPanelBehavior` L1027) |
| `apps/browser-extension/entrypoints/application-form.ts` | Unlisted script, isolated world | `scripting.executeScript` from `injectPageRunner` (`background.ts:107-124`) |
| `apps/browser-extension/entrypoints/controlled-field-bridge.ts` | Unlisted script, `world: "MAIN"` | Same, when a controlled-field bridge is needed (`background.ts:109-113`) |
| `apps/browser-extension/entrypoints/linkedin-connections.ts` | Unlisted script | `syncLinkedInConnections` (`background.ts:267-306`) |
| `apps/browser-extension/entrypoints/inactive-fixture-spike.ts` | Unlisted script, **testing only** | AA-201 spike (`background.ts:974-1013`; request guards require `MODE === "testing"`, L939-945) |

The manifest declares no `content_scripts`; all page code is injected after a user or web action (asserted by `apps/browser-extension/scripts/verify-manifest.mjs:92`).

> The allocation note naming `assistant-panel.tsx` as a baseline entrypoint is **incorrect for 58a96674**. `apps/browser-extension/entrypoints/assistant-panel.tsx` exists only UNMERGED (feature/admin-analytics-final-production @ ce3718b0); see §9.2.

### 3.2 Message surfaces (service worker)

| Listener | Sender check | Message types |
|---|---|---|
| `runtime.onMessageExternal` (`background.ts:1031-1078`) | `isExactRunrWebSender(sender, allowedWebOrigins)` (`apps/browser-extension/src/auth/trusted-sender.ts:15-26`) against `https://app.userunr.com`, `https://runr-frontend.onrender.com` (`apps/browser-extension/src/auth/config.ts:8-13`) | Preparation protocol `runr.assisted_apply.preparation` v1 (`start`/`retry`/`cancel`/`activate`); `RUNR_WEB_BIND_APPLICATION_PACKAGE` (`RunrWebLaunchRequest`, https-only outside testing, L1068); `RUNR_WEB_SYNC_LINKEDIN_CONNECTIONS`, `RUNR_WEB_LINKEDIN_CONNECTIONS_STATUS` |
| `runtime.onMessage`, content → worker (`background.ts:1080-1152`) | `sender.id === runtime.id`, `frameId === 0`, tab present; possible-success adapter must match the live URL | `ASSISTED_APPLY_CONTENT_READY`, `ASSISTED_APPLY_DYNAMIC_FORM_CHANGED`, `ASSISTED_APPLY_SAVE_EXACT_ANSWER` (length-bounded), `ASSISTED_APPLY_POSSIBLE_SUCCESS`, testing-only `AA201_*` |
| `runtime.onMessage`, side panel → worker (`background.ts:1153-1340`) | `isExactSidePanelSender(sender, runtime.id, getURL("/sidepanel.html"))` (L1154) + `isPanelRequest` (L1162) | `GET_EXTENSION_CONNECTION`, `CONNECT_RUNR` (L1179), `DISCONNECT_RUNR`, `UPDATE_ASSISTED_APPLY_PREFERENCES`, `GET/RETRY/CANCEL/ACTIVATE_ASSISTED_APPLY_PREPARATION`, `CHECK_PORTAL_PERMISSION`, `REQUEST_PORTAL_PERMISSION` (L1198), `CHECK/REQUEST_ALL_OPTIONAL_PERMISSIONS`, `BIND_APPLICATION_PACKAGE`, `GET_BOUND_APPLICATION_PACKAGE`, `REFETCH_APPLICATION_PACKAGE`, `GET_PENDING_APPLICATION_CONFIRMATION`, `RESPOND_TO_APPLICATION_CONFIRMATION`, `SAVE_APPLICATION_CORRECTION`, `UPLOAD_SELECTED_DOCUMENT`, `RUN_GREENHOUSE_APPLICATION_PACKAGE` (L1316), `RUN_LEVER_APPLICATION_PACKAGE`, testing `RUN_GREENHOUSE_FIXTURE_PROOF`, `REFRESH_ACTIVE_TAB_STATE` |
| worker → content (`tabs.sendMessage`) | Content accepts only `isApplicationPackageContentRequest` in production (`application-form.ts:121-123`) | `CONTENT_RUN_GREENHOUSE_APPLICATION_PACKAGE`, `CONTENT_RUN_LEVER_APPLICATION_PACKAGE`, `CONTENT_UPLOAD_SELECTED_DOCUMENT`; testing `CONTENT_RUN_GREENHOUSE_FIXTURE_PROOF` |

Type definitions and validators for all of these live in `packages/extension-messages/src/index.ts` (see [shared-packages.md](../01-architecture/shared-packages.md)).

### 3.3 Backend endpoints called by the extension (routes owned by WS-1)

Base URL: `https://runr-api.onrender.com/v1` in production and `http://127.0.0.1:4174` in testing (`apps/browser-extension/src/auth/config.ts:8-20`). All calls go from the **service worker** only, with `credentials: "omit"` and `Authorization: Bearer <session>` where needed (`apps/browser-extension/src/auth/browser-ports.ts:88-99`).

| Method + path (registered name) | Called from |
|---|---|
| POST `/assisted-apply/extension/connection-requests` (`assisted_apply.extension.connection_requests.create`) | `browser-ports.ts:21`, `connection-service.ts:399` |
| POST `/assisted-apply/extension/token` (`…token.exchange`) | `connection-service.ts:435` |
| POST `/assisted-apply/extension/session/verify`, DELETE `/assisted-apply/extension/session` | `browser-ports.ts:23-24` |
| PUT `/assisted-apply/extension/preferences` | `browser-ports.ts:25` |
| GET/POST `/assisted-apply/extension/packages`, POST `/assisted-apply/extension/packages/bind` | `browser-ports.ts:147`, `background.ts:352` |
| POST `/assisted-apply/extension/document-grants`, POST `…/document-grants/download` | `background.ts:848`, `browser-ports.ts:167` |
| POST `/assisted-apply/extension/preparations/report`, `…/preparations/action` (`auth_required=False`, session-token authenticated in handler) | `background.ts:429,446,459,577` |
| POST `/assisted-apply/extension/corrections`, `…/standard-answers`, `…/application-outcomes` | `background.ts:1283,1107,1250` |
| POST `/assisted-apply/extension/linkedin-connections` | `background.ts:300` |
| POST `/assisted-apply/telemetry/events` | `background.ts:886` |

Registration: `backend/api/routes/__init__.py:39-43`; files `backend/api/routes/assisted_apply.py`, `backend/api/routes/assisted_apply_packages.py`, `backend/api/routes/assisted_apply_preparations.py:19-23`, `backend/api/routes/assisted_apply_linkedin.py`, `backend/api/routes/assisted_apply_telemetry.py`.

### 3.4 npm scripts (from `apps/browser-extension/package.json`)

`dev`, `generate:icons`, `postinstall` (`wxt prepare`), `typecheck`, `test:unit`, `build`, `build:edge`, `build:test`, `build:test:edge`, `verify:manifest`, `verify:manifest:edge`, `verify:assisted-apply-boundary`, `package`, `test:e2e`, `test:e2e:edge`, `check`, `check:edge`, `check:all`, `check:all:edge`. Root wrappers in `package.json:9-10,16`: `check:extension`, `check:assisted-apply`, `build:extension`.

## 4. Inputs, outputs, storage and dependencies

| Kind | Item | Where |
|---|---|---|
| Input | Application package (`ApplicationPackagePayload`: job, answers, standardAnswers, candidate, documents meta, policy flags, version) | `packages/extension-messages/src/index.ts:458`; produced by WS-4 package service |
| Input | Web commands from the Runr frontend | `frontend/src/lib/assistedApplyLaunch.js`, `frontend/src/lib/assistedApplyPreparation.js`, `frontend/src/lib/linkedinSync.js` (WS-8 owns) |
| Input | Live DOM of Greenhouse/Lever forms | content script |
| Output | Filled field values and attached files **in the page only**. No submission. | `packages/ats-core/src/declarative-actions.ts`, `index.ts` |
| Output | Preparation reports, corrections, standard answers, possible-success outcomes, telemetry aggregates, LinkedIn CSV | endpoints in §3.3 |
| Storage | `storage.session` (access level `TRUSTED_CONTEXTS`, `browser-ports.ts:232-233`): `runr:assisted-apply:pending:v1` (PKCE state + verifier), `runr:assisted-apply:session:v1` (session token), per-tab upload/confirmation state (`apps/browser-extension/src/state/tab-state.ts`), `assisted-apply-preparation:local:v1` (`apps/browser-extension/src/preparation/local-session.ts:3`) | cleared on disconnect (`connection-service.ts:455-470`) |
| Storage | `storage.local`: `runr:assisted-apply:installation:v1` (non-secret installation id) | `browser-ports.ts:18,271-276` |
| Config | Backend `RUNR_ASSISTED_APPLY_EXTENSION_ORIGINS` must hold the exact `chrome-extension://<id>` origin; production validation fails closed | `backend/config/env_schema.py:193,422-432`; callback derived as `https://<id>.chromiumapp.org/runr/connect` in `backend/application/assisted_apply_service.py:85` |
| Config | `RUNR_ENABLE_ASSISTED_APPLY_PREPARATION`: preparation feature flag, disabled by default per AA-P03 | `backend/application/assisted_apply_preparation_service.py:34`, `backend/config/env_schema.py:198` |
| Build deps | WXT ^0.20.27, React 19, Vitest 4, Playwright ^1.60, TypeScript 5.9, Node ≥22.13 | `apps/browser-extension/package.json` |
| Shared policy | `packages/ats-core/src/policy.ts` mirrors `backend/domain/application_policy.py`; parity fixtures `tests/fixtures/policy_fixtures.json` are used by both `apps/browser-extension/tests/unit/policy.test.ts` and `tests/test_application_policy.py` | cross-language contract |

## 5. Important call/data flows

### 5.1 Connection / token handshake (explicit click, PKCE)
1. The side panel sends `CONNECT_RUNR` (`background.ts:1179`), which calls `ExtensionConnectionService.connect` → `connectOnce` (`apps/browser-extension/src/auth/connection-service.ts:379`).
2. If a stored session is still valid, it is reused. Otherwise the service clears the secret and pending state, creates a random `state` and `codeVerifier`, and derives the SHA-256 `code_challenge` (base64url, 32 bytes asserted).
3. `redirectUri = identity.getRedirectURL("runr/connect")` is validated (`connection-service.ts:199,395-396`).
4. POST `connection-requests` with `code_challenge`, `state`, `installation_id` and `extension_version` returns `request_id` and `expires_at`. The pending record goes to `storage.session`.
5. `identity.launchWebAuthFlow({ url: <frontendOrigin>/settings/assisted-apply?request_id=…, interactive: true })` (L419-424). The user approves in the Runr web app (web routes `assisted_apply.web.connection_requests.action`, WS-1/WS-4).
6. The callback is parsed against `redirectUri`, `state` and `requestId`. POST `token` with `request_id`, `authorization_code` and `code_verifier` returns `session_token` (≥20 chars, `apps/browser-extension/src/auth/protocol.ts:156-160`), session summary and preferences.
7. The secret is stored in `storage.session` and pending state is cleared in `finally`. The session is re-verified via `session/verify`, and user or session id mismatch invalidates it (`connection-service.ts:337-355`).
8. The token never leaves the service worker. `verify-manifest.mjs:150-155` fails the build if `session_token`, `sessionToken`, `code_verifier` or `codeVerifier` appear in any non-`background.js` bundle.

### 5.2 Web launch → package fill → user review
1. The Runr web app sends `RUNR_WEB_BIND_APPLICATION_PACKAGE` or a preparation `start` via `chrome.runtime.sendMessage(<extension id>, …)`. The external listener checks the exact origin (`background.ts:1032`).
2. `bindRunrWebLaunch` (L393) / `startPreparationCommand` (L584) waits for or creates the application tab (https only), then POSTs `/assisted-apply/extension/packages/bind` and fetches the package.
3. If portal host permission is missing, the preparation reports `permission_required`. The side panel requests it from a click handler: `requestPortalPermissionFromUserGesture` (`apps/browser-extension/entrypoints/sidepanel/App.tsx:239`, `apps/browser-extension/src/permissions/host-permissions.ts:97`). It is not routed via the worker, so the gesture is preserved.
4. `runGreenhousePackageOnTab` / `runLeverPackageOnTab` (`background.ts:184,308`) → `injectPageRunner` → `application-form.js` installs `installSubmissionGuard(document)` **first** (`application-form.ts:99`), then dynamic-form monitor and message listener.
5. `CONTENT_RUN_*_APPLICATION_PACKAGE` → `runGreenhouseStandardFacts` / `runLeverStandardFacts` (`packages/ats-core/src/index.ts:1636,1721`). Answers are filtered in the content script: no `ai_suggestion`, no `requiresReview`, confidence ≥0.95, never `legal`, `demographic` only if policy permits, personal scoped preferences only if policy permits (`application-form.ts:172-181`).
6. The adapter inspects and matches (`StandardFactsAdapter`, L652) and plans a `NativeValueAction`. `executeApprovedField` (L1172) → `executeNativeValueAction` / `executeComboboxOptionAction` (`declarative-actions.ts:229,269`) writes the value, fires `input`/`change`, and reads back plus validates.
7. The result (`PackageExecutionMessage`) returns to the worker, and tab state is updated for the side panel review model (`apps/browser-extension/src/review/panel-model.ts`). The owned tab is activated only for user review.
8. Documents: `UPLOAD_SELECTED_DOCUMENT` → `uploadSelectedDocumentOnTab` (`background.ts:826`) creates a grant, downloads the bytes (validated by `apps/browser-extension/src/documents/grant-validation.ts`), and sends base64 to content. `uploadApplicationDocument` attaches to the exact upload intent and zeroes the buffer (`application-form.ts:198-203`). Bounded telemetry is then sent.
9. The **user** clicks submit. `observePossibleSuccess` (armed in `application-form.ts:74-94`) reports `ASSISTED_APPLY_POSSIBLE_SUCCESS`. The worker validates the sender and adapter and stores a pending confirmation, and the user confirms in the side panel, which leads to POST `application-outcomes`.

### 5.3 LinkedIn connections sync
The web sends `RUNR_WEB_SYNC_LINKEDIN_CONNECTIONS`, which calls `syncLinkedInConnections` (`background.ts:267`). It finds or updates a LinkedIn tab to the connections URL, runs `executeScript` with `/linkedin-connections.js`, builds `linkedInConnectionsCsv`, and POSTs `linkedin-connections`. Host access to `https://www.linkedin.com/*` and `https://linkedin.com/*` is mandatory for this (`apps/browser-extension/wxt.config.ts:36-39`).

## 6. Invariants, failure handling and recovery

### 6.1 NEVER-SUBMIT boundary: layered enforcement (verified statically at 58a96674)

| # | Layer | Mechanism | Scope / limits (from reading the code) |
|---|---|---|---|
| L1 | **Type-level** | `AtsAdapter` interface (`packages/ats-core/src/index.ts:171-188`) has no submit method. `type ForbiddenSubmissionCapability = Extract<keyof AtsAdapter, \`${string}${"submit"\|"Submit"}${string}\`>` and `ADAPTER_SUBMISSION_CAPABILITY_FORBIDDEN: ForbiddenSubmissionCapability extends never ? true : false = true` (L201-209). Adding any key containing `submit`/`Submit` makes the assignment a compile error (caught by `typecheck`). `ATS_ADAPTER_CAPABILITIES` (L190-199) is `satisfies ReadonlyArray<keyof AtsAdapter>`. | Only guards `AtsAdapter` key names. The existing `detectPossibleSubmissionSuccess` contains "Submission", not "Submit", so it passes. Does not guard non-adapter code. Test: `apps/browser-extension/tests/unit/ats-core.test.ts:52-54`. |
| L2 | **Static regex scan: boundary script** | `apps/browser-extension/scripts/verify-assisted-apply-boundary.mjs` recursively scans `apps/browser-extension/entrypoints/**`, `apps/browser-extension/src/**` and `packages/ats-core/src/**` (T47). It rejects adapter `fill(` bypasses, programmatic `.click(`, `requestSubmit(`/`.submit(`, `location` assignment/`assign`/`replace`/`reload`, Enter-key submission paths, synthetic pointer activation (`dispatchEvent(new MouseEvent\|PointerEvent\|TouchEvent)`), synthetic keyboard activation (`KeyboardEvent`), synthetic `submit` event dispatch, and `PopStateEvent/HashChangeEvent/BeforeUnloadEvent` dispatch. Fully exempt: `submission-guard.ts` only. Explicitly classified non-terminal allowances: `declarative-actions.ts` `option.click()` (AA-216 combobox option value interaction; terminal controls are refused by `executeNativeValueAction`) and the side panel's own `App.tsx` Enter keydown accessibility handlers (document upload and review state, never page-form activation). | **Wired into `check`, `check:all`, `check:edge` and both extension CI jobs (T47).** Location patterns match mutations only, so `window.location.href` reads stay legal. Does **not** attempt data-flow analysis: a future label-based misclassification of a terminal control (§9.2) is a runtime/executor concern (L3/L4), not a static-scan one. → WS9-G1 resolved by T47 |
| L2b | **Static regex scan: manifest verifier** (wired into `check`/`check:edge`) | `apps/browser-extension/scripts/verify-manifest.mjs:99-126` scans `entrypoints/`, `src/`, `packages/ats-core/src`, `packages/extension-messages/src` for `eval(`, `new Function(`, URL imports, `.submit(`/`.requestSubmit(` (L120), and any identifier containing `submit`/`Submit` followed by `(` (L121-124). Built bundles: no fixture markers; `application-form.js`/`background.js` must not contain `.submit(`/`.requestSubmit(` (L143-148). | Catches submit-named calls and DOM submit APIs across apps and packages. Does **not** catch `.click()` or `dispatchEvent(new MouseEvent("click"))`. |
| L3 | **Runtime guard** | `installSubmissionGuard(document)` (`packages/ats-core/src/submission-guard.ts:8-97`), installed at the top of the injected content script (`apps/browser-extension/entrypoints/application-form.ts:99`). Capture-phase listeners: **click** on any `button` or `input[type=submit\|button\|image\|reset]`: untrusted events are `preventDefault` + `stopImmediatePropagation`, trusted (user) clicks pass and arm a one-shot "user submit pending" flag (L12-24). **submit** is cancelled unless trusted and preceded by a trusted click/Enter (L25-34). **Enter** keydown on inputs: untrusted is cancelled (L35-45). `HTMLFormElement.prototype.requestSubmit`/`submit` are replaced with recorders (no-op) (L54-60). `fetch`/XHR and navigation events are **recorded only**, not blocked (L49-52, L61-76). | Reading-based observations: (a) prototype patches live in the content script's isolated world, so they neutralise extension-side calls, not page-script calls. DOM event listeners do see page-dispatched untrusted clicks, so page JS clicking its own buttons is also cancelled while the guard is active. (b) The guard is never stopped (`void submissionGuard`, L100), and re-injection installs another instance (no idempotency flag). (c) It blocks **all** untrusted button clicks, including intermediate Next/Continue. Tests: `apps/browser-extension/tests/unit/aa216-declarative-actions.test.ts:55`; e2e fixtures count `data-submit-clicks` = 0 across `apps/browser-extension/tests/e2e/assisted-apply.spec.ts` and `assisted-apply.edge.spec.ts`. The "1" cases are user-initiated clicks. |
| L4 | **Executor refusals** | `writeControlValue` refuses `submit/button/image/reset/file` inputs (`declarative-actions.ts:215-217`). `executeNativeValueAction` rejects buttons and terminal inputs: "Terminal or button controls are never executable." (L239-241). `isDeclarativeAction` accepts only a fixed action set, so e.g. `submit_final` is rejected (test `aa216-declarative-actions.test.ts:33-34`). `manualReason` marks `type=submit` controls `final_submission` (`index.ts:333-338`). The adapter `fill` shim delegates to the central executor (`index.ts:833-836`). | — |
| L5 | **Protocol / UI** | No message type in `packages/extension-messages/src/index.ts` requests submission. Side panel e2e asserts no "submit" button (`assisted-apply.spec.ts:151,167`). | — |

**Intermediate navigation (Next/Continue) at baseline.** The owner decision allows recognised intermediate step navigation, and terminal submission is not allowed. At `58a96674` this is **authorization-only**. `DeclarativeAction` includes `propose_intermediate_navigation` (`declarative-actions.ts:11-16`). `authorizeIntermediateNavigation` (L102-117) refuses `button`/`link` kinds ("require explicit manual review"), and otherwise requires exact step id, selector and transition evidence plus a present element. Even when allowed, `executeDeclarativeAction` returns `needs_attention` ("Post-transition verification is required before navigation.") and **performs no click** (L325-331). Combined with L3 blocking untrusted button clicks, the baseline extension **never advances steps itself**. Automated step advance exists only UNMERGED (§9.2).

**Owner decision (memory `runr-extension-safety-posture`) vs source.** "Enforced three independent ways" is confirmed: L1 type constraint, L2 regex scan, L3 runtime guard all exist. Corrections: the L2 scan is a standalone script, **not** part of build or CI. The wired static gate is L2b (`verify-manifest.mjs`). If a parity or feature request seems to need a terminal submit click, it is an **owner question**, never licence to remove or relax a guard.

### 6.2 Other invariants
- **Secret boundary:** session token and PKCE verifier live only in service-worker `storage.session` at `TRUSTED_CONTEXTS`. Content, page and side panel never receive them. This is enforced by bundle scan (`verify-manifest.mjs:149-156`).
- **Sender authentication:** external messages come only from exact Runr web origins. Panel messages come only from the exact `sidepanel.html` URL. Content messages must come from the top frame of this extension (§3.2).
- **Manifest shape** (asserted by `verify-manifest.mjs`): MV3, fixed extension id `najcdfohhfgbjpbokhmmekkahghfhegp` derived from `key` (L9, L29-38), permissions exactly `activeTab identity scripting sidePanel storage` (L71-80), no `content_scripts` (L92), `externally_connectable` exactly the two Runr web origins (L93-97), Chrome ≥116 / Edge ≥120.
- **Fixture isolation:** fixture proofs, the AA-201 spike and local-URL targeting are gated on `import.meta.env.MODE === "testing"` (`background.ts:89-103,939-945`; `apps/browser-extension/src/fixture-runner.ts:44`). Production bundles must not contain fixture markers (`verify-manifest.mjs:139-142`).
- **Answer policy:** never autofill legal answers. Demographic and sensitive answers are off by default and gated by package policy (`packages/ats-core/src/policy.ts:decideFieldAction` L180; content filter §5.2). Existing user-entered values are preserved.
- **Exact-tab ownership:** preparation acts only on the session-owned tab. If it is gone or mismatched, the result is `retry_required` (`background.ts:787-790`). Retry is explicit and bounded (`apps/browser-extension/src/preparation/local-session.ts`; test `aa222-retry-recovery.test.ts`).

### 6.3 Host permissions: baseline code vs owner decision

| Aspect | Baseline 58a96674 (code + verifier) | Owner decision (memory, 2026-08-15) | UNMERGED (ce3718b0 / `0d7f2b5c`) |
|---|---|---|---|
| `host_permissions` | `https://runr-api.onrender.com/*`, `https://www.linkedin.com/*`, `https://linkedin.com/*` (`wxt.config.ts:36-39`) | Broad access granted at install | Same three **+ `https://*/*`** |
| `optional_host_permissions` | `https://boards.greenhouse.io/*`, `https://*.lever.co/*` (`wxt.config.ts:40-43`), requested per portal on user gesture (`apps/browser-extension/src/permissions/host-permissions.ts`) | Do **not** reintroduce a curated optional list or per-site opt-in as default | Removed. Verifier asserts none. |
| Verifier | `verify-manifest.mjs:82-91` enforces the narrow model | — | `verify-manifest.mjs` rewritten to require broad grant |
| Testing mode | `http://127.0.0.1/*` for both | — | same |

**Status:** the owner's broad-access decision is **not implemented on the integration baseline**. It exists only in UNMERGED `0d7f2b5c` (T03). Per the owner, broad access is the chosen design and should not be narrowed silently. Store-review and privacy trade-offs are raised for discussion, not resolved by narrowing (WS9-G2). The baseline rationale doc `docs/reports/runr_assisted_apply_permission_rationale_2026-07-18.md` describes the narrow model and would need revision if T03 lands (WS-11/owner).

### 6.4 Failure handling
- API errors surface as `RunrApiError` (`browser-ports.ts:29`). A gone session on disconnect is tolerated (`connection-service.ts:455-470`).
- An expired connection request throws "expired before it was completed" (L425-427). Pending state is always cleared in `finally`.
- If portal permission is denied, preparation reports `permission_required` and the panel offers a gesture-bound request.
- Upload statuses map to bounded telemetry categories (`application-form.ts:218-232`). Telemetry failures only `console.warn` (`background.ts:896`).
- On tab removal or update, tab state is cleaned up (`background.ts:1342-1376`).

## 7. Relevant tests and safe verification commands

**Tests (37 files under `apps/browser-extension/tests/`):** 26 unit (`apps/browser-extension/tests/unit/*.test.ts`, Vitest + jsdom), 4 e2e (`apps/browser-extension/tests/e2e/*.spec.ts`, Playwright), `apps/browser-extension/tests/fixture-server.mjs`, and 6 HTML fixtures.

| Concern | Tests |
|---|---|
| Never-submit / adapter contract | `apps/browser-extension/tests/unit/ats-core.test.ts`, `apps/browser-extension/tests/unit/aa216-declarative-actions.test.ts`, e2e `data-submit-clicks`/`data-aa201-*submit*` counters in `apps/browser-extension/tests/e2e/assisted-apply.spec.ts`, `apps/browser-extension/tests/e2e/assisted-apply.edge.spec.ts`, `apps/browser-extension/tests/e2e/aa201-inactive-fixture.spec.ts` |
| Adapters | `apps/browser-extension/tests/unit/aa219-greenhouse-adapter.test.ts`, `apps/browser-extension/tests/unit/aa220-lever-adapter.test.ts`, `apps/browser-extension/tests/unit/aa218-controlled-controls.test.ts`, `apps/browser-extension/tests/unit/aa08-dynamic-forms.test.ts` |
| Connection / auth / senders | `apps/browser-extension/tests/unit/connection-service.test.ts`, `apps/browser-extension/tests/unit/api-client.test.ts`, `apps/browser-extension/tests/unit/trusted-sender.test.ts`, `apps/browser-extension/tests/unit/runtime-config.test.ts` |
| Permissions | `apps/browser-extension/tests/unit/host-permissions.test.ts` |
| Documents | `apps/browser-extension/tests/unit/aa221-upload-intent.test.ts`, `apps/browser-extension/tests/unit/document-grant-validation.test.ts` |
| Preparation lifecycle | `apps/browser-extension/tests/unit/aa214-external-command.test.ts`, `apps/browser-extension/tests/unit/aa215-local-session.test.ts`, `apps/browser-extension/tests/unit/aa222-retry-recovery.test.ts`, `apps/browser-extension/tests/unit/preparation-report.test.ts` |
| Reconciliation | `apps/browser-extension/tests/unit/aa202-reconciliation.test.ts`, `apps/browser-extension/tests/e2e/aa202-reconciliation.spec.ts` |
| Messages / state / panel / success / telemetry / policy / LinkedIn | `apps/browser-extension/tests/unit/messages.test.ts`, `apps/browser-extension/tests/unit/tab-state.test.ts`, `apps/browser-extension/tests/unit/panel-model.test.ts`, `apps/browser-extension/tests/unit/possible-success-observer.test.ts`, `apps/browser-extension/tests/unit/aa15-telemetry.test.ts`, `apps/browser-extension/tests/unit/policy.test.ts`, `apps/browser-extension/tests/unit/application-url.test.ts`, `apps/browser-extension/tests/unit/linkedin-connections.test.ts` |
| Backend side (WS-1/WS-4 own) | `tests/test_backend_api.py -k "assisted_apply or extension_cors or extension_origin or clerk_only_identity"`, `tests/test_assisted_apply_connection_service.py`, `tests/test_application_policy.py` |

**CI (WS-7 owns `.github/workflows/ci.yml`):** job `assisted-apply-extension` (L111-141: `npm ci`, a dedicated `verify:assisted-apply-boundary` step, Playwright Chromium, `check:all`), job `assisted-apply-extension-edge` (L143-177: `npm ci`, a dedicated `verify:assisted-apply-boundary` step, Playwright msedge, `check:edge` then `test:e2e:edge`). Since T47, `check`, `check:all` and `check:edge` each end with `verify:assisted-apply-boundary`, so every extension CI job runs the gate twice (standalone step plus aggregate check). `docker` needs both (L178-185).

**Safe verification commands (not executed in Phase 2):**
```bash
npm ci --prefix apps/browser-extension
npm --prefix apps/browser-extension run typecheck
npm --prefix apps/browser-extension run test:unit
npm --prefix apps/browser-extension run check          # typecheck + unit + build + verify:manifest
npm --prefix apps/browser-extension run verify:assisted-apply-boundary
npm --prefix apps/browser-extension run check:edge
npm --prefix apps/browser-extension run check:all      # + Playwright Chromium e2e
npm --prefix apps/browser-extension run test:e2e:edge
npm run check:extension                                 # root wrapper
```

## 8. Historical decisions and supporting commits

`git log --oneline 58a96674 -- apps packages` gives 36 commits (2026-07-18 … 2026-08-06):

| Date | SHA | Subject / decision |
|---|---|---|
| 2026-07-18 | `75bfdbc1` | Add Runr Assisted Apply connection foundation |
| 2026-07-18 | `aa656b65` | Implement Assisted Apply package policy and CV upload |
| 2026-07-18 | `e9701702`, `43d92507` | AA-06/AA-05 cross-language policy parity |
| 2026-07-18 | `f3561b7f` | AA-10 production-bundle audit (verify-manifest bundle scan) |
| 2026-07-18 | `7beea8ce` | AA-18 Edge target |
| 2026-07-19 | `54d12940` | AA-07 native control support on both portals |
| 2026-07-19 | `7f2a352e` | AA-15 privacy-safe adapter telemetry |
| 2026-07-19 | `42f6ba04` | AA-16 Chrome install and permissions store-ready (narrow optional-host model) |
| 2026-07-19 | `f3b44d48` | Reviewed web launch flow |
| 2026-07-27 | `ac798a5a`, `dd4be9ab` | Repair extension CI gates; pin wasm runtime |
| 2026-08-01 | `2bf5e4ea` | AA-201 inactive-tab foundation |
| 2026-08-01 | `5ac36c79` | Policing gate AA-P01 |
| 2026-08-01 | `2e56d028` | Foundation through AA-221 |
| 2026-08-01 | `2a46a5f0`, `66b2d039` | AA-219 Greenhouse / AA-220 Lever adapter boundary |
| 2026-08-01 | `6a275554`, `a279ea2f` | AA-222 retry recovery / AA-223 preparation UI |
| 2026-08-01 | `a4a53e61` | AA-P03 remediation (adapter `fill` removed from contract; boundary script rejects `adapter.fill(`) |
| 2026-08-02 | `0bc0fbce` … `04fa1ba4` | Live flow fixes: package origin/URL, portal permission gesture (`9d62625f`), document selection, complete package filling |
| 2026-08-03 | `be237a31` | Auto-start assisted apply autofill |
| 2026-08-04 | `92760a3a`, `4018c07e`, `2831ec16` | LinkedIn connections sync; allow Render frontend origin; keep sync in background |
| 2026-08-06 | `fffef0dc` | Scope Edge review heading locator (last baseline change) |

## 9. Current implementation status

### 9.1 Capability table (baseline 58a96674)

| Capability | Classification |
|---|---|
| MV3 manifest shape, permissions, externally_connectable | VERIFIED (scope: static — `wxt.config.ts:34-48` matches assertions in `verify-manifest.mjs:71-97`; not built) |
| Never-submit L1 type constraint | VERIFIED (scope: static — `index.ts:171-209` read; construct is a compile-time error on submit-named keys; test `ats-core.test.ts:52-54` present, not run) |
| Never-submit L2 boundary script | VERIFIED (scope: static + unit — T47 rewrote it as a recursive three-root scan with synthetic-activation detection and explicit non-terminal allowances; wired into `check`, `check:all`, `check:edge` and both extension CI jobs; negative fixture check rejects synthetic click/submit/Enter; `tests/unit/ats-core.test.ts` "never-submit boundary gate" asserts roots/patterns and a clean live run) |
| Never-submit L2b manifest/bundle scan | VERIFIED (scope: static — wired in `check` and `check:edge` scripts, CI runs both) |
| Never-submit L3 runtime guard | VERIFIED (scope: static — installed at `application-form.ts:99` before any listener; behaviour read in `submission-guard.ts`; not executed) |
| Intermediate Next/Continue navigation | PARTIAL (authorization logic only; no execution at baseline — `declarative-actions.ts:325-331`) |
| PKCE connection / token handshake | IMPLEMENTED-UNVERIFIED (code path traced `connection-service.ts:379-453` ↔ routes registered `assisted_apply.py`; tests not run) |
| Web launch bind + package fill (Greenhouse, Lever) | IMPLEMENTED-UNVERIFIED (flow traced; AA-226 live pilot FAIL 0/10, `docs/assisted-apply/pilots/AA-226.md`) |
| Document grants and upload | IMPLEMENTED-UNVERIFIED |
| Preparation protocol (start/retry/cancel/activate) | IMPLEMENTED-UNVERIFIED (backend flag `RUNR_ENABLE_ASSISTED_APPLY_PREPARATION`; production value UNKNOWN) |
| Possible-success detection → tracker confirmation | IMPLEMENTED-UNVERIFIED |
| Adapter health telemetry | IMPLEMENTED-UNVERIFIED |
| LinkedIn connections sync | IMPLEMENTED-UNVERIFIED |
| Broad host permissions at install (owner decision) | PLANNED-NOT-IMPLEMENTED on baseline (decision: memory `runr-extension-safety-posture`; implementation UNMERGED `0d7f2b5c`, ticket T03) |
| Generic (non-Greenhouse/Lever) ATS planner, in-page assistant panel, step navigation | PLANNED-NOT-IMPLEMENTED on baseline (UNMERGED; T03) |
| AA-201 inactive fixture spike | RETIRED/HISTORICAL-style spike, testing-only code retained (`inactive-fixture-spike.ts`) |
| Chrome Web Store publication / installed user base | UNKNOWN |

### 9.2 UNMERGED (feature/admin-analytics-final-production @ ce3718b0)

`git diff --name-status 58a96674 ce3718b0 -- apps packages` gives **36 A / 9 M** (45 files, +7100/−23), all from commit `0d7f2b5c` (T03 lists 48 paths including backend route and 2 docs). **Not on baseline; do not restore.**

| Group | Paths (UNMERGED) |
|---|---|
| M manifest/permissions | `apps/browser-extension/wxt.config.ts` (broad `https://*/*`, no optional hosts, version 0.3.0), `apps/browser-extension/scripts/verify-manifest.mjs`, `apps/browser-extension/package.json` |
| M worker/messages | `apps/browser-extension/entrypoints/background.ts` (+101: runtime `registerContentScripts` reconciliation, `permissions.onAdded/onRemoved`, `ASSISTED_APPLY_PANEL_BOOTSTRAP/SET_COLLAPSED/PROFILE`, `ASSISTED_APPLY_PAGE_DETECTED`), `packages/extension-messages/src/index.ts` (+26) |
| A in-page panel | UNMERGED `apps/browser-extension/entrypoints/assistant-panel.tsx`; UNMERGED `apps/browser-extension/src/panel/{AssistantPanel.tsx, autofill-run.ts, mount-decision.ts, panel-styles.ts, profile-package.ts, script-registration.ts, step-navigation.ts}` |
| A/M ats-core | UNMERGED `packages/ats-core/src/{application-context, field-intent, generic-inspector, generic-planner, generic-upload, question-model, resume-match}.ts`; M `packages/ats-core/src/declarative-actions.ts` (adds `select_enhanced_options`; `DeclarativePlan.adapter` widened to `/^[a-z][a-z0-9_]{1,31}$/`), M `packages/ats-core/src/index.ts`, M `packages/ats-core/package.json` (8 new subpath exports) |
| A tests/fixtures | UNMERGED unit `aa301`…`aa309` (8), e2e `aa302-auto-panel.spec.ts`, 12 ATS fixtures (Ashby, Avature ×4, BambooHR, iCIMS, Jobvite, Recruitee, SmartRecruiters, Taleo, Workday); M `apps/browser-extension/tests/fixture-server.mjs` |

**Never-submit review requirement for T03 (read-only observations at ce3718b0):**
- UNMERGED `step-navigation.ts`: label-based classifier. `TERMINAL_PATTERNS` (submit, send application, finish/complete/confirm application, apply now, German) take precedence over `ADVANCE_PATTERNS` (next, continue, save and continue, proceed, weiter). `findAdvanceControl` refuses zero or >1 candidates. `installNavigationGuard` cancels untrusted clicks and submits except one `authorizeOnce` element. **It performs no click itself.**
- UNMERGED `assistant-panel.tsx:advanceStep` (≈L180-196) **does** operate a control: it re-classifies, authorizes once, then `dispatchEvent(new MouseEvent("click", …))`. This evades both static scans (L2 does not scan `apps/`, and neither regex matches `dispatchEvent(new MouseEvent`). The terminal decision rests solely on visible label text (`aria-label` / `textContent` / `value`), so a final control labelled "Next"/"Continue" would be classified `advance`. The reviewer must confirm fixtures such as `avature-final-step.html` cover this.
- UNMERGED `autofill-run.ts` (238 lines): no direct `.click(`, `dispatchEvent`, `submit`, `requestSubmit` or `location` tokens. Indirect execution via UNMERGED `generic-planner`/`declarative-actions` was **not traced** and T03 must trace it. The generic ats-core files contain no L2-forbidden tokens by grep.
- Interaction to verify: if `application-form.ts` (L3 guard) and the assistant panel run on the same document, L3 cancels the panel's authorized synthetic button click (L3 blocks all untrusted button clicks), or listener order decides.
- Owner acceptance (T03): `step-navigation.ts` and `autofill-run.ts` click no terminal submit control; L1/L2/L3 stay intact; intermediate Next/Continue allowed, terminal submit not.

### Deployment evidence (documentary only)
- `docs/assisted-apply/ci/AA-225.md` records CI e2e PASS (2026-08-01) with zero submission signals. `docs/assisted-apply/gates/AA-P03.md` records PASS including a manual `verify:assisted-apply-boundary` run.
- `docs/assisted-apply/pilots/AA-226.md` records the controlled live pilot as **FAIL** (no live forms available; feature "remains broadly disabled").
- Render blueprint secrets list `RUNR_ASSISTED_APPLY_EXTENSION_ORIGINS` and `RUNR_ENABLE_ASSISTED_APPLY_PREPARATION` by name (evidence package `deployment-evidence.md`). Values and live state are UNKNOWN.
- The Web Store URL is hard-coded in `apps/browser-extension/src/auth/config.ts:12`. Whether the listing is published is UNKNOWN. LIVE PRODUCTION = UNKNOWN.

## 10. Confirmed gaps and unresolved questions

| ID | Gap / question |
|---|---|
| WS9-G1 | ~~`verify:assisted-apply-boundary` is not run by `check`, `check:all`, `check:edge` or CI. It scans only top-level `packages/ats-core/src/*.ts` and exempts `declarative-actions.ts` (which calls `option.click()`).~~ **RESOLVED by T47 (2026-09-21):** the gate now scans `apps/browser-extension/entrypoints/**`, `apps/browser-extension/src/**` and `packages/ats-core/src/**` recursively, detects synthetic `dispatchEvent(new MouseEvent\|PointerEvent\|TouchEvent\|KeyboardEvent)` activation and location navigation mutations, exempts only `submission-guard.ts`, explicitly classifies the `declarative-actions.ts` `option.click()` value interaction and the side panel `App.tsx` Enter accessibility handlers, and runs through `check`, `check:all`, `check:edge` and both extension CI jobs. |
| WS9-G2 | The owner decision (broad host access at install, no curated optional list) is not implemented on baseline: `wxt.config.ts:36-43`, `verify-manifest.mjs:82-91` and `host-permissions.ts` enforce the narrow model. The implementation is UNMERGED in `0d7f2b5c` (T03). The permission rationale doc is stale relative to the decision. Store-review trade-off to discuss with owner. |
| WS9-G3 | Runtime guard L3 blocks *all* untrusted button clicks and Enter, including page-script-dispatched ones, for the life of the page. It is never stopped and is re-installed on each injection. Possible interference with portal JS and with UNMERGED synthetic step advance. Needs a behavioural test decision. |
| WS9-G4 | UNMERGED automated step advance relies on label text only and uses `dispatchEvent(MouseEvent)`, invisible to static gates. ~~T03 must add a static and a test gate for `apps/browser-extension/src/panel/**` and entrypoints.~~ **Static and test gate now exist (T47, 2026-09-21):** synthetic pointer/keyboard activation is a boundary-script violation in `entrypoints/**` and `src/**` (future panel code lands inside the scanned roots), and `tests/unit/aa216-declarative-actions.test.ts` proves synthetic terminal click/submit/Enter are blocked while trusted user activation remains allowed. **Remaining:** the label-only terminal/advance classification risk itself is still UNMERGED code and is owned by the T48–T51 hierarchy (T51 must prove safe intermediate navigation). |
| WS9-G5 | Allocation text says the extension imports ats-core from `assistant-panel.tsx`, but that file is UNMERGED only. Baseline consumers are `background.ts`, `application-form.ts`, `controlled-field-bridge.ts`, `inactive-fixture-spike.ts`. |
| WS9-G6 | Fetch/XHR/navigation are recorded but not blocked by L3. Protection against page-initiated terminal network requests relies on not clicking terminal controls. Document as intended or tighten. |
| U5 | Plan for feature-branch commits including extension changes (`0d7f2b5c`) → T03. |
| T03 | Review assisted-apply panel and generic ATS planner work (48 paths). |
| Open | Live state of the Web Store listing, backend extension-origin value, and preparation flag: UNKNOWN. |

## Agent context and remaining work

**(a) Proposed agent context packet: Assisted Apply extension**
- *Required reading:* this doc; [apps-and-extensions.md](../01-architecture/apps-and-extensions.md); [shared-packages.md](../01-architecture/shared-packages.md); `apps/browser-extension/README.md`; `packages/ats-core/src/submission-guard.ts`; `packages/ats-core/src/index.ts:171-209`; `packages/ats-core/src/declarative-actions.ts`; `apps/browser-extension/scripts/verify-manifest.mjs`; `apps/browser-extension/scripts/verify-assisted-apply-boundary.mjs`; `docs/assisted-apply/gates/AA-P03.md`; owner memory `runr-extension-safety-posture`.
- *Allowed paths:* `apps/browser-extension/**`, `packages/ats-core/**`, `packages/extension-messages/**`. Backend routes and services only with WS-1/WS-4 coordination.
- *Tests to run:* `npm --prefix apps/browser-extension run check`, `verify:assisted-apply-boundary`, `check:all`, `check:edge` + `test:e2e:edge`. For protocol changes, also `tests/test_backend_api.py -k "assisted_apply or extension_cors or extension_origin or clerk_only_identity"`.
- *Prohibited changes:* adding any submit-capable adapter method, message or UI; clicking or dispatching activation on terminal controls; removing or weakening `installSubmissionGuard`, the `AtsAdapter` type constraint, `verify-manifest.mjs` submit/secret scans, or the boundary script; exposing session token or PKCE verifier outside the service worker; adding manifest `content_scripts` or remote code; silently narrowing host permissions contrary to the owner decision (raise as trade-off instead); publishing to the Web Store or changing production env.

**(b) Registry proposal**

| subsystem id | name | owned globs | primary doc | test globs | owner WS |
|---|---|---|---|---|---|
| `assisted-apply-extension` | Assisted Apply browser extension and shared packages | `apps/**`, `packages/**` | `docs/reverse-engineering/05-subsystems/assisted-apply.md` (this doc; added in the WS-9 Phase 2 commit, so absent at 58a96674) | `apps/browser-extension/tests/**` | WS-9 |

**(c) Gap/ticket candidates**
1. ~~Wire `verify:assisted-apply-boundary` into `check` and CI, and extend its scan to `apps/browser-extension/{entrypoints,src}` with `dispatchEvent(new MouseEvent` / `.click(` detection (WS9-G1, G4; CI edit via WS-7).~~ DONE by T47 (2026-09-21).
2. Owner decision record + implementation of broad host permissions via T03, updating `verify-manifest.mjs`, `host-permissions.ts` and the permission rationale doc (WS9-G2).
3. T03 review record: 48-path accept/adapt/reject, with the never-submit review items in §9.2 (WS9-G3, G4).
4. Behavioural test for L3 guard interplay with portal JS and authorized intermediate navigation (WS9-G3, G6).
5. Correct allocation/evidence note about `assistant-panel.tsx` (WS9-G5; Phase 3 / WS-12).

## T49 implementation amendment (2026-09-23)

The approved profile-package extension contract is now implemented across the
backend route, shared message package, service worker, and panel mapper.

- The service worker handles `ASSISTED_APPLY_PANEL_PROFILE`, requests
  `POST /assisted-apply/extension/profile-package`, and validates the
  schema-versioned payload before returning it as `PanelResponse.profilePackage`.
- Session tokens remain service-worker-only. Untrusted senders, non-top frames,
  missing sessions, failed requests, and malformed payloads fail closed with a
  generic response.
- The payload contains only approved candidate facts, profile-verified answers,
  confirmed education/skills/languages, and career-memory experiences with
  approved bullets and provenance. The panel mapper consumes the approved
  `proposed_value` field and maps periods to planner-friendly ISO year-month
  values; it does not invent missing facts.
- The backend reuses `_profile_package_sections`; no profile-package store,
  migration, manifest permission, or new external provider call is added.

The route and wire contract are covered by backend API tests plus extension
message and mapper unit tests. Boundary verification remains required for every
future Assisted Apply change.
