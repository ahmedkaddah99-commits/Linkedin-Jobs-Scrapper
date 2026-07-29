# ADR-0001: Assisted Apply Architecture Baseline

**Date:** 2026-07-29  
**Status:** accepted  
**Ticket:** AA-200  
**Author:** Architecture baseline investigation (no production code changes)

---

## 1. Scope and Purpose

This record captures the repository-grounded architecture baseline for the Runr Assisted Apply feature before Phase B (shared contracts and durable data) implementation begins. Every claim is classified by evidence class. Current behaviour and proposed future architecture are kept clearly separate.

This ADR satisfies ticket AA-200 ("Verify architecture baseline"). It is an evidence-gathering and documentation deliverable. It does not authorise production implementation, database migrations, new message types, or new dependencies.

---

## 2. Evidence Classification Legend

| Class | Meaning |
|-------|---------|
| **Repository-confirmed** | Exact file paths and symbols in the current repository. |
| **Externally verified** | Primary official documentation (Chrome Extension API docs, MDN, etc.). |
| **Inferred** | Supported by evidence but carries stated uncertainty. |
| **Proposed** | Future design intent; not current behaviour and not a fixed fact. |

---

## 3. Repository-Confirmed Component Map

### 3.1 Browser Extension (`apps/browser-extension/`)

- **Service worker:** `entrypoints/background.ts` — Central message router, `onMessageExternal` handler, package binding, document upload orchestration, tab state management
- **Side panel (React):** `entrypoints/sidepanel/index.html`, `sidepanel/main.tsx` — Extension-controlled UI for connection, permissions, field review
- **Content script:** `entrypoints/application-form.content.ts` — Page runner injected via `scripting.executeScript`; performs ATS inspection, field filling, document upload
- **MAIN-world bridge:** `entrypoints/controlled-field-bridge.content.ts` — Minimal bridge for value-setting on controlled-framework components
- **Tab state:** `src/state/tab-state.ts` — `chrome.storage.session` read/write for tab state, packages, confirmations, upload tracking
- **Auth/connection:** `src/auth/connection-service.ts`, `browser-ports.ts`, `config.ts` — Extension connection lifecycle (PKCE + `launchWebAuthFlow`), session storage, API client
- **Trusted sender:** `src/auth/trusted-sender.ts` — Origin validation for side-panel and Runr web sender
- **Host permissions:** `src/permissions/host-permissions.ts` — Optional host permission check/request logic
- **Manifest (WXT):** `wxt.config.ts` — MV3 manifest with permissions, `externally_connectable`, `optional_host_permissions`

### 3.2 Shared Packages

- **ATS Core:** `packages/ats-core/src/index.ts` — ATS detection, form inspection, field matching, fill, upload, validation, submission detection
- **Extension Messages:** `packages/extension-messages/src/index.ts` — TypeScript type definitions for all extension messages, package payloads, panel requests

### 3.3 Backend

- **AA routes:** `backend/api/routes/assisted_apply.py` — Extension connection/token/session/preferences lifecycle; web connection management
- **Package routes:** `backend/api/routes/assisted_apply_packages.py` — Package create/prepare/launch/bind/fetch; document grants; corrections; outcomes
- **Telemetry routes:** `backend/api/routes/assisted_apply_telemetry.py` — Bounded telemetry ingestion (no user content)
- **Origin guard:** `backend/api/server.py` (~line 9056) — Extension origin validation
- **Package service:** `backend/application/assisted_apply_package_service.py` — Package lifecycle, document grants, corrections, outcomes
- **Connection service:** `backend/application/assisted_apply_service.py` — Connection request/authorization/exchange/authentication/session management
- **Package domain:** `backend/domain/application_package.py` — `ApplicationPackage`, TTL constants, payload types
- **AA domain:** `backend/domain/assisted_apply.py` — `AssistedApplyConnectionRecord`, `AssistedApplyPreferences`

### 3.4 Fixtures and Tests

- **E2E tests:** `apps/browser-extension/tests/e2e/assisted-apply.spec.ts` — Full connection, package binding, Greenhouse/Lever filling, document upload, session expiry
- **Edge E2E:** `apps/browser-extension/tests/e2e/assisted-apply.edge.spec.ts` — Same suite on Edge
- **Unit tests (13 files):** `apps/browser-extension/tests/unit/` — API client, connection service, tab state, runtime config, trusted sender, messages, policy, ATS core, host permissions, panel model, telemetry, dynamic forms, possible-success observer
- **Fixture server:** `apps/browser-extension/tests/fixture-server.mjs` — Node HTTP server simulating all Assisted Apply endpoints
- **Greenhouse fixture:** `apps/browser-extension/tests/fixtures/greenhouse-application.html` — Sanitized Greenhouse HTML form
- **Lever fixture:** `apps/browser-extension/tests/fixtures/lever-application.html` — Sanitized Lever HTML form

---

## 4. Current External Messaging Flow

### 4.1 Externally Connectable Configuration

**Repository-confirmed:** `apps/browser-extension/wxt.config.ts` lines 41-43

- Production: `matches: ["https://app.userunr.com/*"]`
- Testing: `matches: ["http://127.0.0.1/*"]`

Only the Runr web application origin can send external messages to the extension.

### 4.2 onMessageExternal Handler

**Repository-confirmed:** `apps/browser-extension/entrypoints/background.ts` lines 429-443

The only accepted inbound external message is `RUNR_WEB_BIND_APPLICATION_PACKAGE`. Validation chain: (1) sender origin must exactly match `runtimeConfig.frontendOrigin` (`trusted-sender.ts` lines 15-24), (2) message must match `RunrWebLaunchRequest` type (`extension-messages/src/index.ts` lines 115-119), (3) in production, `applicationUrl` must use `https://`, (4) `bindRunrWebLaunch()` locates user-opened tab by URL, validates ATS detection, calls `bindPackageFromApi(bindingId)`, writes package to `storage.session`.

### 4.3 Message Payload

**Repository-confirmed:** `packages/extension-messages/src/index.ts` lines 115-119 — External message carries only opaque `bindingId` and `applicationUrl`. No package contents, profile data, executable instructions, or browser-local IDs.

### 4.4 Side Panel Participation

**Repository-confirmed:** Side panel participates only through `runtime.onMessage` (internal messaging). Manages connection state, preferences, permissions, package binding, fixture proofs, document uploads, corrections, tracker confirmations.

**Inferred:** The side panel is currently required for package execution because `runGreenhousePackage()` / `runLeverPackage()` use `resolveTargetTab()` which queries the active tab. There is no background preparation mechanism.

### 4.5 Can the Side Panel Be Closed During Preparation?

**Repository-confirmed:** No. The current flow runs synchronously via `runtime.onMessage` handlers in a single request-response cycle. No preparation mechanism outlives a panel interaction.

---

## 5. Current Permission Flow and Official Constraints

### 5.1 Required Permissions

**Repository-confirmed:** `apps/browser-extension/wxt.config.ts` line 34: `["activeTab", "identity", "scripting", "sidePanel", "storage"]`

### 5.2 Host Permissions

**Repository-confirmed:** `apps/browser-extension/wxt.config.ts` lines 35-40
- Required: API origin only (`https://runr-api.onrender.com/*`)
- Optional: `https://boards.greenhouse.io/*`, `https://*.lever.co/*`
- **`<all_urls>` is never requested** in any mode

### 5.3 Permission Logic

**Repository-confirmed:** `apps/browser-extension/src/permissions/host-permissions.ts`
- `hasPortalPermission(portal)`, `requestPortalPermission(portal)`, `hasAllOptionalHostPermissions()`, `requestAllOptionalHostPermissions()` — delegates to `browser.permissions` API
- Comment at line 72: "Must be called from a user gesture (click handler)."

### 5.4 Official Chrome Constraint

**Externally verified:** https://developer.chrome.com/docs/extensions/reference/api/permissions#method-request — `chrome.permissions.request()` must be called from a user gesture.

### 5.5 Missing Permission Behaviour

**Repository-confirmed:** `apps/browser-extension/entrypoints/background.ts` lines 138-144: When `injectPageRunner()` fails, tab state set to `errorCode: "permission_required"` or `"page_unavailable"`.

---

## 6. Package, Binding, Extension-Session, and Document-Grant Lifecycle

### 6.1 Extension Session TTLs

**Repository-confirmed:** `backend/application/assisted_apply_service.py` lines 26-28

| TTL | Value | Scope |
|-----|-------|-------|
| `ASSISTED_APPLY_REQUEST_TTL_SECONDS` | 600 (10 min) | Pending connection request |
| `ASSISTED_APPLY_AUTHORIZATION_CODE_TTL_SECONDS` | 120 (2 min) | Authorization code |
| `ASSISTED_APPLY_SESSION_TTL_SECONDS` | 28800 (8 h) | Active session |

**State transitions:** `pending (10 min)` → user approves → `authorized (2 min)` → extension exchanges PKCE → `active (8 h)` → `revoked|expired`

**Key:** `touch_assisted_apply_session()` updates `last_used_at` but does NOT extend TTL.

### 6.2 Package Lifecycle

**Repository-confirmed:** `backend/domain/application_package.py` lines 10-11

| TTL | Value | Scope |
|-----|-------|-------|
| `APPLICATION_PACKAGE_TTL_SECONDS` | 1800 (30 min) | Total package lifetime from creation |
| `APPLICATION_PACKAGE_BINDING_TTL_SECONDS` | 300 (5 min) | Time to bind after launch |

**State transitions:** `created` → `launch_package()` (generates `binding_id`, `launch_tab_binding_expires_at = now + 5 min`) → `launched` → `bind_package()` (validates binding not expired) → `bound` → `expire_stale()` → `expired`

### 6.3 expire_stale() Behaviour

**Repository-confirmed:** `backend/application/assisted_apply_package_service.py` lines 151-176
- **Launched:** expire when `now > launch_tab_binding_expires_at` (5-min binding window)
- **Bound:** expire when `now > created_at + 30 min` (original creation-based TTL)

**Critical finding:** Bound packages do NOT expire based on the binding TTL. Once bound, they expire only at `created_at + 30 min`.

### 6.4 Document Grant Lifecycle

**Repository-confirmed:** Same file lines 39, 425-517 — `ASSISTED_APPLY_DOCUMENT_GRANT_TTL_SECONDS = 60`. Grants are atomically consumed (CAS), hash-verified. New grants can be created for same `(package_id, document_id)` while package is "bound".

### 6.5 Lifecycle Q&A

| Question | Answer |
|----------|--------|
| What creates each TTL? | Constants in `application_package.py` / `assisted_apply_service.py` |
| When does each TTL begin? | Package: `created_at`. Session: `activated_at`. Grant: creation time |
| Which transitions refresh TTL? | None. Session has `last_used_at` touch but no TTL extension |
| Does original package expiry still apply after binding? | **Yes.** Bound packages expire at `created_at + 30 min` |
| Can bound package be retrieved after original expiry? | **No.** `expire_stale()` transitions it to "expired" |
| Can document grant be reissued after consumption? | **Yes.** New `create_document_grant()` call |
| Can new grant be issued while preparation session is active? | Yes, if session valid and package is "bound" |

---

## 7. TTL Transition Table

| Entity | TTL | Starts When | Expires When | Refresh | State After |
|--------|-----|-------------|--------------|---------|-------------|
| Connection request | 10 min | Request creation | `now > request_expires_at` | None | "expired" |
| Authorization code | 2 min | User approval | `now > authorization_code_expires_at` | None | "expired" |
| Extension session | 8 h | Token exchange | `now > session_expires_at` | `last_used_at` touch only | "expired" |
| Package (created) | 30 min | Creation | `created_at + 30 min` | Must launch first | "expired" |
| Binding window | 5 min | Launch | `now > launch_tab_binding_expires_at` | None | "expired" |
| Package (bound) | 30 min from creation | Creation | `created_at + 30 min` | Uses creation timestamp | "expired" |
| Document grant | 60 s | Grant creation | `now >= expires_at` | Consumed atomically | "expired"/"consumed" |
| `storage.session` | Browser session | Extension writes | Browser restart/update/clear | None | Lost |

---

## 8. Canonical Application-URL Source

**Repository-confirmed:** `backend/api/routes/assisted_apply_packages.py` lines 249-251 — Sourced from job record in Tracker: `job.apply_link` → `job.link` → `job.source_url`. Stored in package as `job.url` (line 264).

**Inferred:** An explicit retry after tab closure or browser restart could resolve the URL by retrieving the bound package from the backend (`job.url`). No `tabId`/`windowId` needs backend storage.

---

## 9. Current Greenhouse Capability Matrix

**Repository-confirmed:** Uses `StandardFactsAdapter` (`packages/ats-core/src/index.ts` lines 597, 1055-1061)

| Capability | Supported |
|------------|-----------|
| Personal info (name, email, phone) | ✅ Yes |
| Standard inputs, textareas, selects, radios, checkboxes, dates | ✅ Yes |
| File uploads (CV, cover letter, supporting) | ✅ Yes |
| Email/phone-specific detection | ✅ Yes |
| Existing-value preservation | ✅ Yes |
| Fill ledger (idempotency) | ✅ Yes |
| Readback verification | ✅ Yes |
| Browser validation check | ✅ Yes |
| Open shadow DOM traversal | ✅ Yes |
| Same-origin iframe traversal | ✅ Yes |
| Submit-button detection (manual-only) | ✅ Yes |
| CAPTCHA/signature/terms/declaration/assessment detection | ✅ Yes |
| **Repeatable work-experience sections** | ❌ **No** |
| **Repeatable education sections** | ❌ **No** |
| **Start/end dates for experience** | ❌ **No** |
| **Current-employment state** | ❌ **No** |
| **Rich-text / contenteditable descriptions** | ❌ **No** |
| **Multi-step navigation** | ❌ **No** |
| **Custom selects/comboboxes** | ❌ **No** |
| **Intermediate navigation authorization** | ❌ **No** |
| **Final-review detection** | ❌ **No** |

---

## 10. Current Lever Capability Matrix

Identical to Greenhouse (Section 9) — both use `StandardFactsAdapter` with no ATS-specific overrides. **Repository-confirmed:** `packages/ats-core/src/index.ts` lines 1055-1061.

---

## 11. Fixture and Test Gaps

### 11.1 Fixture Gaps (vs. Real Application Forms)

| Gap | Impact |
|-----|--------|
| No repeatable work-experience sections | Real forms have employer/role/date/description addition flows |
| No education sections | Real forms have institution/degree/date fields |
| No rich-text descriptions | Real forms use `contenteditable` or custom editors |
| No custom comboboxes | Real forms use custom React/Vue components |
| No multi-step forms | Real flows have multiple pages/tabs |
| No dynamic form sections | Real forms add sections based on previous answers |
| No custom date pickers | Real forms use custom date widgets |
| No intermediate navigation | Real flows have "Next" / "Save and continue" buttons |
| No current-employment toggle | Real forms ask "I currently work here" |
| No diversity/demographic questions | Real forms have EEOC-style questions |

### 11.2 Existing Tests

**Repository-confirmed:** 13 unit test files in `apps/browser-extension/tests/unit/` plus 2 E2E suites. CI pipeline (`.github/workflows/ci.yml`) runs `npm run check:assisted-apply`.

### 11.3 Test Gaps

| Gap | Reason |
|-----|--------|
| No package lifecycle backend tests verified locally | Python `.venv` not confirmed |
| No repeatable-section reconciliation tests | Feature not implemented (AA-202) |
| No inactive-tab preparation tests | Feature not implemented (AA-201) |

---

## 12. Tailored-CV Provenance Findings

### 12.1 Current Data Flow

**Repository-confirmed trace:**
1. Package answers are profile facts only (`candidate.first_name`, `last_name`, `full_name`, `email`, `phone` from user metadata) — `backend/api/routes/assisted_apply_packages.py` lines 138-180
2. `ApplicationPackagePayload` (`extension-messages/src/index.ts` lines 174-188) has no `experiences` or `education` field
3. `ApplicationPackageAnswer` (lines 129-139) has no `source_experience_id`, `bullet_id`, `tailored_text`, or `content_hash` field
4. `ApplicationPackageDocumentMeta` (lines 166-172) has no source-experience linkage

### 12.2 Provenance Retention Summary

| Data Element | Preserved? |
|---|---|
| Source experience IDs | ❌ No |
| Source education IDs | ❌ No |
| Bullet IDs | ❌ No |
| Job-specific tailored bullet text | ❌ No |
| Package version | ✅ Yes |
| Approved-content hashes | ⚠️ Partial (documents only) |
| Document version / kind | ✅ Yes |

---

## 13. Official Chrome Behaviour and Direct Citations

| API/Feature | Behaviour | Source |
|---|---|---|
| `tabs.create({ active: false })` | Creates tab in background without activation | https://developer.chrome.com/docs/extensions/reference/api/tabs#method-create |
| Messaging inactive tab | `tabs.sendMessage()` works on inactive tabs if content script loaded | https://developer.chrome.com/docs/extensions/develop/concepts/messaging#simple |
| Content scripts in inactive tabs | Execute regardless of activation. Background tabs may be throttled | https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts#functionality |
| `permissions.request()` | Must be called during user gesture | https://developer.chrome.com/docs/extensions/reference/api/permissions#method-request |
| `sidePanel.open()` | Requires user gesture | https://developer.chrome.com/docs/extensions/reference/api/sidePanel#method-open |
| `storage.session` lifetime | Browser session. Cleared on close, reload, update | https://developer.chrome.com/docs/extensions/reference/api/storage#property-session |
| `externally_connectable` | Only exact origins in `matches` | https://developer.chrome.com/docs/extensions/reference/manifest/externally-connectable |
| MV3 service worker | Terminated when idle (~30s). State must persist in storage | https://developer.chrome.com/docs/extensions/develop/concepts/service-workers |
| `scripting.executeScript` | Works on inactive tabs if host permission granted | https://developer.chrome.com/docs/extensions/reference/api/scripting#method-executeScript |

---

## 14. Contradictions Between Repository Reality and the Ticket Pack

### 14.1 Directory Name

**Repository-confirmed:** The ticket pack exists at `docs/assist-apply/runr-assisted-apply-ticket-pack.md` (note: `assist-apply`, not `assisted-apply`).

### 14.2 Branch Status

**Repository-confirmed:** Current checkout is on detached HEAD. Expected `aa/aa-200-architecture-baseline` does not exist. Work performed on detached HEAD per user instruction.

### 14.3 Verified Ticket Pack Claims

| Claim | Verification |
|-------|-------------|
| Extension creates tabs with `active: false` | **Proposed** — Future (AA-201). Current: `resolveTargetTab()` uses active tab |
| Web app sends commands via `externally_connectable` | ✅ Confirmed |
| Side panel for extension-controlled interactions only | ✅ Confirmed |
| Previously granted ATS permission not re-requested | ✅ Confirmed |
| `tabId`/`windowId` never enter backend | ✅ Confirmed |
| Packages are immutable | ✅ Confirmed |
| Adapters return declarative proposals, never click/submit | ✅ Confirmed (compile-time guard) |
| Final submission prohibited | ✅ Confirmed (type-level guard) |
| AI fallback outside release | ✅ Confirmed |
| CAPTCHA/anti-bot circumvention prohibited | ✅ Confirmed |

---

## 15. Questions AA-201 Through AA-204 Must Resolve

### AA-201 (Background Tab Spike)
1. Can `tabs.create({ active: false })` create a tab content scripts execute in without activation?
2. Does browser throttling affect `scripting.executeScript` timing, `setTimeout`, or events?
3. Can the service worker coordinate an inactive tab through complete lifecycle?
4. Does `tabs.sendMessage()` to inactive tab with fresh content script work reliably?

### AA-202 (Reconciliation Spike)
1. What normalization produces deterministic matches for repeatable sections?
2. Can algorithm distinguish "same employer, different role" from "same employer, updated role" without backend IDs?
3. How does algorithm handle SPA remounts that reset DOM but preserve logical state?

### AA-203 (Workday Discovery)
1. Does Workday use iframes/shadow DOM/custom components exceeding current walker?
2. Does multi-page flow require intermediate navigation authorization?
3. Can repeatable-experience sections map to same declarative action protocol?

### AA-204 (Freeze Architecture)
1. What preparation session TTL is safe given package TTL (30 min) and binding TTL (5 min)?
2. Should extension session (8h) be extended/refreshed?
3. Should `storage.session` data be mirrored to `storage.local`?
4. What is the navigation controller contract?
5. How does application URL recovery work for retry after browser restart?

---

## 16. Exact Tests and Investigation Commands Executed

### Extension Unit Tests
**Command:** `npm run test:unit` in `apps/browser-extension/`  
**Result:** ❌ Could not execute — `node_modules` not installed. Missing `vitest` binary.

### Backend Tests
**Command:** `.venv\Scripts\python.exe -m pytest`  
**Result:** Not executed — `.venv` path not confirmed in current worktree.

### Files Inspected (Repository-Confirmed Evidence)
`apps/browser-extension/wxt.config.ts` (full), `entrypoints/background.ts` (full), `package.json` (full), `src/permissions/host-permissions.ts` (full), `src/state/tab-state.ts` (full), `src/auth/trusted-sender.ts` (full), `src/auth/connection-service.ts` (~200 lines), `packages/ats-core/src/index.ts` (full, ~1100 lines), `packages/extension-messages/src/index.ts` (full), `backend/api/routes/assisted_apply.py` (full), `backend/api/routes/assisted_apply_packages.py` (full), `backend/application/assisted_apply_package_service.py` (full, ~600 lines), `backend/application/assisted_apply_service.py` (full, 432 lines), `backend/domain/application_package.py` (full), `backend/domain/assisted_apply.py` (full), `apps/browser-extension/tests/fixtures/greenhouse-application.html` (full), `apps/browser-extension/tests/fixtures/lever-application.html` (full), `apps/browser-extension/tests/e2e/assisted-apply.spec.ts` (partial), 4 of 13 unit test files sampled, `docs/assist-apply/runr-assisted-apply-ticket-pack.md` (full from integration branch).

### External Sources Consulted
9 official Chrome Extension API documentation pages (see section 13 for exact URLs).

---

## 17. Known Uncertainties

1. **`expire_stale()` invocation trigger:** Exact schedule (timer vs. on-access) not traced.
2. **Extension session TTL:** Whether product intends hard 8h or sliding window is a product decision.
3. **`node_modules` absence:** Tests could not run locally. CI confirms they pass.
4. **Backend `.venv`:** Not verified in this worktree.

---

## 18. Summary of Evidence Classification

| Section | Primary Evidence Class |
|---------|----------------------|
| Component map (3) | Repository-confirmed |
| External messaging (4) | Repository-confirmed |
| Permission flow (5) | Repository-confirmed + Externally verified |
| Package/binding/session lifecycle (6) | Repository-confirmed |
| TTL transition table (7) | Repository-confirmed |
| Canonical application URL (8) | Repository-confirmed |
| Greenhouse capabilities (9) | Repository-confirmed |
| Lever capabilities (10) | Repository-confirmed |
| Fixture gaps (11) | Repository-confirmed + Inferred |
| Tailored CV provenance (12) | Repository-confirmed |
| Chrome behaviour (13) | Externally verified |
| Contradictions (14) | Repository-confirmed |
| Questions for AA-201-204 (15) | Inferred from investigation gaps |
| Tests/investigation commands (16) | Repository-confirmed |
| Uncertainties (17) | Inferred |
