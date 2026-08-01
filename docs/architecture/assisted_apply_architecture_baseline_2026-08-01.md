# Assisted Apply Architecture Baseline — 2026-08-01

Status: repository-grounded baseline for AA-200

Date: 2026-08-01

Scope: documentation and test-inventory only. No production behavior, schema,
dependency, deployment, or feature changes were made.

## Evidence labels

- **Repository-confirmed** means directly observed in the cited file and symbol.
- **Externally verified** means supported by the official Chrome documentation
  linked in the cited row.
- **Inferred** means a conclusion derived from multiple repository facts.
- **Proposed** means an unresolved future design choice, not current behavior.

## Executive baseline

**Repository-confirmed:** Runr is a review-first MV3 extension. The web app can
send one narrowly validated launch message to the extension; the extension
binds a server package to the current tab, fills verified standard facts, and
uploads fixed-version documents. The extension has no final-submit adapter
operation or message. Evidence after a user-driven submit is classified as
possible success and requires an explicit Tracker decision.

**Inferred:** The current system has three distinct lifetimes: connection
authorization/session, application-package launch binding, and one-time
document grant. They are not one shared TTL, and package status is the
authoritative lifecycle boundary for most package operations.

**Unresolved:** The package constant `APPLICATION_PACKAGE_TTL_SECONDS` says
“30 min after launch,” but the current stale-expiry query does not expire a
bound package by that value. Whether bound packages should remain retrievable
indefinitely, expire after a separate bound lifetime, or be explicitly consumed
is a decision for a follow-up ticket; this record does not choose it.

## 1. Web-to-extension connection and external messaging

| Finding | Label | Exact evidence |
|---|---|---|
| Production web pages allowed to message the extension are `https://app.userunr.com/*`; testing allows `http://127.0.0.1/*`. | Repository-confirmed | `apps/browser-extension/wxt.config.ts`, manifest builder at `defineConfig().manifest`, `externally_connectable.matches` (lines 41–43). |
| The external flow is a single `RUNR_WEB_BIND_APPLICATION_PACKAGE` request. It validates the sender origin, message shape, HTTPS (outside tests), then calls `bindRunrWebLaunch(bindingId, applicationUrl)` and returns asynchronously. | Repository-confirmed | `apps/browser-extension/entrypoints/background.ts`, `defineBackground` external listener (lines 429–443); `packages/extension-messages/src/index.ts`, `isRunrWebLaunchRequest` (lines 773–786). |
| The web message carries a binding ID and application URL; the binding ID is not put in the employer page URL/DOM. | Repository-confirmed | `backend/application/assisted_apply_package_service.py`, `launch_package` docstring and transition (lines 287–325); `packages/extension-messages/src/index.ts`, `RunrWebLaunchRequest` validator. |
| Chrome’s page-to-extension messaging requires the page to match `externally_connectable.matches`, and the extension receives it through `runtime.onMessageExternal`. | Externally verified | [Chrome message passing — Send messages from web pages](https://developer.chrome.com/docs/extensions/develop/concepts/messaging). |
| The extension also has internal paths: side panel → background via `runtime.onMessage`, background → injected page runner via `tabs.sendMessage`, and content/page runner → background via `runtime.sendMessage`. | Repository-confirmed | `apps/browser-extension/entrypoints/background.ts`, `onMessage` listener (lines 445–476); `apps/browser-extension/entrypoints/application-form.ts`, listener and runtime event (lines 63–68, 42–53); `apps/browser-extension/entrypoints/sidepanel/App.tsx`, `requestPackage` call sites (e.g. lines 373–376, 447–450). |

## 2. Optional ATS permissions and gesture boundary

| Finding | Label | Exact evidence |
|---|---|---|
| Greenhouse and Lever access are optional host permissions; the API host is mandatory. | Repository-confirmed | `apps/browser-extension/wxt.config.ts`, manifest `host_permissions` and `optional_host_permissions` (lines 34–40). |
| Runtime requests are per portal or all-at-once through `browser.permissions.request({ origins })`. | Repository-confirmed | `apps/browser-extension/src/permissions/host-permissions.ts`, `requestPortalPermission` and `requestAllOptionalHostPermissions` (lines 69–98). |
| The code documents that permission requests must be called from a click/user gesture, but the background listener itself does not establish a gesture; callers must preserve that boundary. | Repository-confirmed | `apps/browser-extension/src/permissions/host-permissions.ts`, request function comments (lines 70–75); `apps/browser-extension/entrypoints/background.ts`, `REQUEST_PORTAL_PERMISSION`/`REQUEST_ALL_OPTIONAL_PERMISSIONS` dispatch (lines 496–512). |
| Chrome documents optional host permissions as runtime-grantable and says `permissions.request()` must be called from a user gesture such as a button click. | Externally verified | [Chrome permissions API](https://developer.chrome.com/docs/extensions/reference/api/permissions?hl=en), “Declare optional permissions” and “Request optional permissions”. |
| Current UI exposes connection, fill, upload, and review actions as explicit buttons. No current side-panel call site requests portal permissions directly; the message cases are available and covered by unit tests. | Repository-confirmed | `apps/browser-extension/entrypoints/sidepanel/App.tsx`, button handlers (lines 343–350, 373–376, 447–455); `apps/browser-extension/tests/unit/host-permissions.test.ts`, request tests (lines 89–131). |
| **Gap:** there is no repository test proving that a permission request invoked after an asynchronous hop still retains a Chrome user gesture. | Repository-confirmed | Inventory of `apps/browser-extension/tests/unit/host-permissions.test.ts` and `apps/browser-extension/tests/e2e/assisted-apply.spec.ts`; tests assert request arguments/results, not browser gesture provenance. |

## 3. Lifecycle and TTL state transitions

### Connection/session

**Repository-confirmed state transitions:**

1. `pending` is created with `request_expires_at`; `create_request` uses a ten-minute request lifetime (`backend/application/assisted_apply_service.py`, constants lines 26–28 and `create_request` lines 164–191).
2. `pending → authorized` occurs only after the user authorizes; the authorization code receives its own two-minute `authorization_code_expires_at` (`authorize` lines 250–284).
3. `authorized → active` occurs after PKCE exchange; the session receives an eight-hour `session_expires_at` (`exchange` lines 310–354).
4. On dashboard/authorize/reject/exchange, `_expire_if_needed` checks the expiry belonging to the current state and transitions the record to `expired` when elapsed (`backend/application/assisted_apply_service.py`, `_expire_if_needed`, lines 193–213).
5. Extension storage mirrors expiry: `getConnection` clears expired pending/session state and reconnects only through the explicit connect flow (`apps/browser-extension/src/auth/connection-service.ts`, `getConnection`, lines 319–365; `connectOnce`, lines 379–452).

### Application package and binding

**Repository-confirmed state transitions:**

1. `created → launched` creates an opaque binding ID and sets
   `launch_tab_binding_expires_at` to five minutes after launch (`backend/domain/application_package.py`, statuses/constants lines 9–24; `backend/application/assisted_apply_package_service.py`, `launch_package`, lines 287–325).
2. `launched → bound` occurs when the extension presents the binding before its binding expiry; the original package payload remains immutable (`backend/application/assisted_apply_package_service.py`, `bind_package`, lines 327–379; `backend/domain/application_package.py`, `ApplicationPackage` docstring lines 171–177).
3. An unbound created package is stale when `now > created_at` in `ApplicationPackageStore.expire_stale`; a launched or bound package is considered stale only through the launched binding-expiry branch in that query (`backend/application/assisted_apply_package_service.py`, `ApplicationPackageStore.expire_stale`, lines 151–176).
4. A bound package can be retrieved by package ID for an authenticated owner without a status or package-expiry check (`backend/application/assisted_apply_package_service.py`, `get_package_for_extension`, lines 381–398; `backend/api/routes/assisted_apply_packages.py`, `_get_package_for_extension`, lines 318–330).
5. Therefore, **repository-confirmed contradiction:** the named 30-minute package TTL (`backend/domain/application_package.py`, `APPLICATION_PACKAGE_TTL_SECONDS`, line 10) is not used by the shown launch/bind/retrieval paths. **Inferred consequence:** after successful binding, retrieval remains possible after the original launch-binding window unless another operation changes status; the intended bound-package expiry policy is unresolved.
6. The extension stores the bound package in `storage.session` under a tab key and retrieves it on later side-panel actions; it removes all tab state only on disconnect or explicit tab cleanup (`apps/browser-extension/src/state/tab-state.ts`, `readTabPackage`, `writeTabPackage`, `removeTabState`, lines 66–89; `apps/browser-extension/entrypoints/background.ts`, `BIND_APPLICATION_PACKAGE` and `GET_BOUND_APPLICATION_PACKAGE`, lines 514–530).

### Document grant

**Repository-confirmed state transitions:**

1. `bound package + authenticated session + selected fixed document → issued grant`; the grant stores only a token hash/prefix, package/document identity, expected size/hash, `expires_at`, and `issued` status (`backend/application/assisted_apply_package_service.py`, `create_document_grant`, lines 425–517; `backend/repositories/sqlite_migrations.py`, document-grant table, lines 928–959).
2. `issued → consumed` is an atomic one-time transition before bytes are returned. A second consume is rejected (`backend/application/assisted_apply_package_service.py`, `consume_document_grant`, lines 519–571).
3. `issued → expired` occurs when the current time reaches the one-minute grant expiry; `issued → rejected` occurs if downloaded bytes do not match the recorded size/hash (`consume_document_grant`, lines 545–583).
4. The grant is tied to user, connection request, and extension origin, and the extension verifies size/hash again before injecting bytes (`backend/application/assisted_apply_package_service.py`, lines 548–583; `apps/browser-extension/entrypoints/background.ts`, `uploadSelectedDocument`, lines 360–375).

## 4. Canonical application URL and retry recovery

**Repository-confirmed:** package preparation chooses the application URL in this order:

`job.apply_link` → `job.link` → `job.source_url` → empty, then rejects unsupported portals. The selected URL is stored both in the response and in `ApplicationPackageJob.url` (`backend/api/routes/assisted_apply_packages.py`, `_prepare_package`, lines 249–265 and 271–278; `backend/domain/application_package.py`, `ApplicationPackageJob.from_payload`, lines 118–127).

**Repository-confirmed:** Greenhouse and Lever normalization populate all three job URL aliases from the provider URL, with `apply_link_source` identifying the adapter (`backend/connectors/ats_router.py`, `_normalize_greenhouse_job`, lines 71–92; `_normalize_lever_job`, lines 95–122).

**Repository-confirmed:** retry/refetch uses the persisted package by ID (`background.ts`, `REFETCH_APPLICATION_PACKAGE`, lines 568–570), and Tracker records use `confirmed_package.job.url` as `apply_link` (`backend/application/assisted_apply_package_service.py`, outcome persistence lines 703–735). **Conclusion:** the canonical recovery source is the immutable persisted package’s `job.url`, originally selected from `apply_link` then `link` then `source_url`; it is not re-scraped from the current tab.

## 5. Greenhouse, Lever, fixtures, and test inventory

**Repository-confirmed:** both adapters exist in `packages/ats-core/src/index.ts` as `GreenhouseAdapter` and `LeverAdapter` (lines 1055–1061), and both support inspection, standard-fact matching/filling, validation, and document upload. `detectPossibleSubmissionSuccess` returns `null` in the portable adapter base (lines 1033–1053); possible-success classification is implemented separately in `apps/browser-extension/src/success/possible-success-observer.ts`.

**Repository-confirmed fixture capabilities:**

- Greenhouse fixture: standard inputs/select/radio/checkbox/date, file roles, cross-origin and same-origin frames, open/closed shadow roots, custom control, manual controls, and a submit handler that increments `data-submit-clicks` but calls `preventDefault()` (`apps/browser-extension/tests/fixtures/greenhouse-application.html`, form lines 23–92 and script lines 94–125).
- Lever fixture: standard facts, CV/cover/supporting uploads, and a submit handler that prevents default (`apps/browser-extension/tests/fixtures/lever-application.html`, form/script lines 4–36).
- E2E coverage exercises both Greenhouse and Lever package fills, uploads, recovery, and post-user-submit confirmation (`apps/browser-extension/tests/e2e/assisted-apply.spec.ts`, scenarios around lines 199–357, 597–720; Edge equivalents in `apps/browser-extension/tests/e2e/assisted-apply.edge.spec.ts`).

**Fixture/test gaps:**

- **Repository-confirmed:** fixtures are local HTML, not live Greenhouse/Lever pages; they do not prove provider-specific production DOM drift, redirects, cross-origin upload behavior, CAPTCHA vendors, or ATS server submission semantics.
- **Repository-confirmed:** no test covers package retrieval after a bound package’s intended 30-minute lifetime, because the implementation currently has no enforced bound-package expiry transition.
- **Repository-confirmed:** no tailored-document contract test proves that generated tailored experience/bullet records retain source `experience_id` and `bullet_id` through the application-package boundary; the package document model carries document IDs/versions, not CV provenance IDs (`backend/domain/application_package.py`, `ApplicationPackageDocumentRef`, lines 41–68 and `to_extension_payload`, lines 227–271).

## 6. Tailored CV provenance

**Repository-confirmed:** source processing creates stable `experience_id` values and attaches source asset IDs (`backend/capabilities/source_processing/pipeline.py`, `_stable_experience_id` and `_structured_experiences`, lines 58–94). Work-experience records also persist `experience_id` and source asset IDs (`backend/domain/models.py`, `WorkExperienceRecord`, lines 1495–1586).

**Repository-confirmed:** tailored-document normalization/rendering preserves structured experience and bullet text/order, but the generated tailored payload is text/list-oriented and does not assign or carry per-bullet IDs (`backend/capabilities/tailored_documents/generation.py`, normalization/rendering helpers around lines 416–516).

**Repository-confirmed:** baseline replacement diffs create new `bullet_id` values for diff records and track old/new experience IDs, while tests verify diff identity/lifecycle rather than tailored-document source-ID propagation (`backend/application/baseline_cv_replacement_service.py`, `_compare_bullets` and diff construction, lines 129–182, 201–257; `tests/test_baseline_cv_replacement.py`, identity/provenance tests around lines 173–233).

**Conclusion:** source experience identity is preserved in source-processing/work-experience/rebind paths, but tailored CV output does not currently provide evidence that source experience IDs or bullet IDs survive generation. **Label: unresolved evidence gap**, not a claim that they are intentionally discarded everywhere.

## 7. Submission protections and reachable mutation/navigation paths

**Repository-confirmed protections:**

- `packages/ats-core/src/index.ts`, `ManualReason` classifies final submission, CAPTCHA, signature, declaration, terms, assessment, cross-origin frames, closed shadow roots, and unsupported controls as manual (lines 31–41).
- `StandardFactsAdapter.detectPossibleSubmissionSuccess` returns `null`; there is no adapter submit method (`packages/ats-core/src/index.ts`, lines 1033–1061). The package tests explicitly assert that adapter capabilities do not include `submit`/`submitApplication` (`apps/browser-extension/tests/unit/ats-core.test.ts`, lines 35–54).
- Form filling mutates only approved controls through adapter `fill`, dispatching input/change events; document upload targets verified file controls (`packages/ats-core/src/index.ts`, `run...StandardFacts` around lines 1200–1215 and `uploadApplicationDocument`, lines 1069–1091; `packages/ats-core/src/page-bridge.ts`, event bridge around lines 70–104).
- Existing values are preserved unless a user explicitly chooses a replacement; the side panel labels this action “Replace with Runr answer” (`apps/browser-extension/entrypoints/sidepanel/App.tsx`, lines 471–485; `packages/ats-core/src/index.ts`, fill matching/authorization around lines 1200–1206).
- Success observation arms only on a trusted click on a final submit control, then watches submit/mutation/URL state for up to 30 seconds and emits bounded evidence (`apps/browser-extension/src/success/possible-success-observer.ts`, `observePossibleSuccess`, lines 49–82).
- Backend outcome recording requires a bound package, matching package version/adapter, allowed evidence category, explicit `confirmed`/`declined` decision, and idempotent Tracker insertion (`backend/application/assisted_apply_package_service.py`, `respond_to_application_outcome`, lines 593–685; `backend/repositories/sqlite_migrations.py`, event/Tracker constraints, lines 965–995).

**Reachable paths:**

1. Side-panel button → background `runGreenhousePackage`/`runLeverPackage` → injected page runner → adapter fill/upload (`background.ts`, lines 161–200 and 606–610; `application-form.ts`, lines 81–165).
2. Web app → external bind message → server package bind → tab session storage (`background.ts`, lines 429–443; `backend/api/routes/assisted_apply_packages.py`, `_bind_package`, lines 305–315).
3. Page runner → internal possible-success event → background pending confirmation → side-panel explicit Tracker decision (`application-form.ts`, lines 32–53; `background.ts`, lines 449–465 and 537–566).
4. User/ATS navigation and DOM mutation → observer classification: success banner, confirmation/thanks/success path, same-origin URL transition, form submit, or mutation (`possible-success-observer.ts`, `classifyPossibleSuccess`, lines 30–47; `observePossibleSuccess`, lines 55–77).
5. **Repository-confirmed absent path:** no extension code calls `form.submit()`, `requestSubmit()`, `window.location` assignment, `history.pushState`, `tabs.update`, or an adapter submission API. The observed navigation is therefore user/ATS-owned; this absence is also covered by the manifest/source boundary audit and unit/E2E zero-submit assertions.

## 8. Contradictions and decisions left open

- **Contradiction:** package domain constant says 30 minutes after launch, while stale-expiry/retrieval logic does not enforce that lifetime after binding. Evidence: `backend/domain/application_package.py:10`; `backend/application/assisted_apply_package_service.py:151–176, 381–398`.
- **Unresolved:** whether a bound package is intentionally reusable until explicit consumption, should expire at a separate deadline, or should be revoked on tab/session conditions.
- **Unresolved:** whether tailored CV generation should gain explicit source experience/bullet identity fields before Assisted Apply treats tailored artifacts as provenance-safe.
- **Unresolved:** whether production permission requests are always invoked synchronously from a visible user gesture; repository tests do not prove this browser-level condition.
- **Proposed:** add a follow-up evidence ticket that defines bound-package expiry semantics and adds a state-transition test for retrieval before/after that boundary; do not infer the desired policy from the unused constant.

## 9. Verification run for AA-200

Python interpreter was verified first: `.venv\Scripts\python.exe --version` → `Python 3.12.7`.

Existing relevant tests were run unmodified:

```text
.venv\Scripts\python.exe -m pytest -q tests/test_aa03_application_package.py tests/test_application_binding.py tests/test_assisted_apply_connection_service.py tests/test_assisted_apply_document_grants.py tests/test_assisted_apply_launch_prepare.py tests/test_assisted_apply_tracker_confirmation.py tests/test_baseline_cv_replacement.py tests/test_tailored_document_generation.py tests/test_stage_adapters.py
→ 148 passed, 17 subtests passed in 49.69s

npm run test:unit   (cwd: apps/browser-extension)
→ 13 test files passed; 137 tests passed

npm run verify:manifest   (cwd: apps/browser-extension)
→ Verified guarded Chrome MV3 manifest and source boundary.

npm run test:e2e   (cwd: apps/browser-extension)
→ Testing WXT build succeeded; 12 Playwright tests passed in 37.0s.
```

These are fixture/browser tests, not live-provider verification; live-provider
behavior remains an explicit fixture limitation. No commit was created.
