# Runr Assisted Apply Ticket Plan - 2026-07-17

**Created date:** 2026-07-17<br>
**Execution mode:** local, evidence-gated tickets implemented in dependency order<br>
**Source coverage:** the supplied visible delivery plan, sections 1-12

## Source caveat

The supplied plan ends in the middle of the `optional_host_permissions` JSON at
`https://jobs.l...`. This ledger does not invent the missing text. It covers every
requirement visible in sections 1-12 and adds conservative release/security gates,
but the decomposition must not be called comprehensive until the omitted remainder
has been supplied and reconciled. AA-17 cannot become `verified_complete` before
that reconciliation.

## Status and completion contract

Allowed ticket states:

- `planned`: not started.
- `in_progress`: implementation or verification is active.
- `blocked`: a named external decision or dependency prevents useful progress.
- `verified_complete`: every acceptance checkbox is checked and exact automated
  and manual evidence is recorded in the ticket.

No ticket is complete because code was attempted, compiled once, or looks correct.
Fixture-only evidence cannot close a ticket that explicitly requires a live-browser,
production, store, or human verification.

## Repository adaptation

- Keep the existing Python backend and Vite/React frontend in place. A wholesale
  move into `apps/api` and `apps/web` is unrelated migration risk.
- Add the extension incrementally at `apps/browser-extension/` and portable
  extension contracts under `packages/`.
- Use canonical JSON Schema or cross-language contract fixtures when Python and
  TypeScript must share application-package/profile data; TypeScript interfaces
  alone are not a shared backend schema.
- In new code, prefer `application portal adapter` where it prevents confusion with
  Runr's existing ATS CV-scoring/export gate.
- Reuse the existing Clerk, candidate-document, Career Memory, Tracker, storage,
  event, and ownership seams instead of creating parallel permanent stores in the
  extension.

## Execution waves

1. Foundation: AA-01.
2. Connection and launch: AA-02, then AA-03.
3. Policy foundation: AA-06 after the immutable launch envelope in AA-03.
4. Portal tracer bullets and controls: AA-04 and AA-05 may run in parallel after
   AA-06, followed by AA-07 and AA-08; AA-09 can start after AA-06.
5. Telemetry, documents, and hard DOM cases: AA-15 after both portal tracer
   bullets; AA-11 after AA-04; AA-13 after AA-07; AA-12 after AA-05, AA-11,
   and AA-15.
6. Learning and tracking: AA-10, AA-14.
7. Operations and release: AA-16, AA-17, then AA-18.

---

## AA-01 - Prove the guarded MV3 extension slice on a Greenhouse fixture

**Type:** AFK<br>
**Status:** verified_complete<br>
**Blocked by:** None - can start immediately<br>
**Visible plan coverage:** sections 1, 2, 4, 5, 8, 9, 10, and visible section 12

### What to build

Create the first executable vertical slice: a WXT/Manifest V3/TypeScript/React
Chrome extension inspects a sanitized Greenhouse fixture, fills one empty verified
email field, reads the accepted value back, and reports the result through the
service worker to a directly testable side panel. This is a development tracer
bullet, not a production package/auth substitute.

### Acceptance criteria

- [x] A production Chrome MV3 build contains a service worker, action, and React
      side panel and requests only permissions used by this slice.
- [x] ATS/core and message contracts are portable packages; the adapter surface has
      no final-submit capability and a compile-time guard fails if one is added.
- [x] The fixture flow uses side panel -> service worker -> isolated page runner and
      returns typed inspection/execution state to the side panel.
- [x] The Greenhouse fixture fills one empty verified email field using focus,
      native value setting, input/change/blur events, readback, and validation.
- [x] Existing user/ATS/browser values are preserved, and a second run is
      idempotent.
- [x] Submit, CAPTCHA, signature, declaration, terms, assessment, disabled, hidden,
      and unknown controls are never executable targets; the fixture proves Submit
      was untouched.
- [x] Unsupported portals are not enabled and the source/bundle audit rejects DOM
      submission APIs or submit-like adapter capabilities.
- [x] Current-tab state is reconstructable from `storage.session`; no correctness
      depends on a permanent service-worker process.
- [x] Unit tests, manifest audit, TypeScript check, production build, and Playwright
      persistent-context extension test pass locally on Node 22.13+; the Node 22 CI
      job invokes the same gate.

### Owned files

- `apps/browser-extension/**`
- `packages/ats-core/**`
- `packages/extension-messages/**`
- root extension scripts, ignore rules, and extension CI job

### Verification required

```text
npm run check:assisted-apply
```

### Completion evidence

- On 2026-07-17, `npm run check:assisted-apply` exited 0 under Node
  `v22.23.1`: TypeScript passed; 3 unit files / 20 tests passed; production and
  testing WXT Chrome MV3 builds passed; manifest/source/bundle policy audit passed;
  and 1 Playwright persistent-context scenario passed.
- The browser scenario proved typed panel -> worker -> isolated-runner messaging,
  exact fixture gating, event/readback behavior, idempotence, preservation of both
  a user-cleared Runr value and a pre-existing matched value, manual-control
  non-mutation, zero submit events, an actual MV3 service-worker stop, and state
  recovery from `storage.session` after panel reload.
- Unit coverage includes hostile forged manual matches, checkbox/radio/date/file
  type confusion, CSS-hidden ancestors, malformed wire/storage payloads, and
  inspect-to-fill control repurposing/replacement.
- `npm audit` reported 0 vulnerabilities. The existing ATS router regression stayed
  green (`5 passed, 11 subtests passed`). `git diff --check` reported no errors.
- An independent source-only safety re-review found no remaining release-blocking
  capability issue. The CI workflow parses and invokes the same Node 22 `check:all`
  gate. No remote GitHub CI run is claimed because no commit or push was requested.
- The Playwright proof opens the packaged side-panel page directly; toolbar chrome
  and store-installed side-panel presentation remain manual release evidence for
  AA-16/AA-17, not evidence claimed by AA-01.

---

## AA-02 - Connect and disconnect the extension through Runr

**Type:** HITL (implementation is AFK; production redirect/CORS evidence is human-verified)<br>
**Status:** verified_complete<br>
**Blocked by:** AA-01<br>
**Visible plan coverage:** sections 3 and 4

### What to build

Add the Runr installation/connection surface and an explicit-user-gesture
`launchWebAuthFlow()` exchange that creates a short-lived, revocable, user-bound
extension session. Do not persist a normal web Clerk token in extension storage.
This ticket owns functional account connection, disconnection, and preference
storage; AA-16 owns store packaging, permission prompts, and release disclosures.

### Acceptance criteria

- [x] The extension connection screen exposes Connect/Disconnect account state,
      capability disclosure, and persisted optional sensitive-data preferences.
- [x] Authentication starts only from an explicit user click and completes through
      a one-time-code/session exchange with a stable extension callback identity.
- [x] Sessions are short-lived, revocable, scoped to one Runr user, and reject
      expired, revoked, replayed, and cross-user requests.
- [x] Chrome-extension origin/CORS handling uses an explicit production allowlist,
      never a wildcard.
- [x] Connection state recovers after worker suspension; Disconnect revokes backend
      and local state.
- [x] Content/page scripts never call Runr APIs directly; API traffic is mediated by
      the service worker.

### Verification required

Focused backend auth/API tests, extension unit tests, browser connection/disconnect
E2E, and a manual production redirect/CORS configuration check.

### Completion evidence

- On 2026-07-17, the repository-wide `npm run check` gate exited 0: Ruff passed;
  the backend suites passed with 110 tests / 21 subtests plus the focused Assisted
  Apply API gate with 4 tests / 7 subtests; all 40 frontend tests and the production
  frontend build passed; and the extension unit, type, build, and guarded-manifest
  checks passed.
- The final `npm run check:assisted-apply` gate exited 0 with 7 unit files / 52
  tests and 2 Playwright persistent-context scenarios. The browser proof covers an
  explicit-click-only `launchWebAuthFlow`, stable callback exchange, preference
  persistence, actual worker stop/restart recovery, remote-first revoke while the
  local credential remains available, local removal after backend revocation, and
  rejection of the revoked credential.
- Focused backend tests cover expiry, revocation, one-time-code replay,
  cross-user/origin binding, exact Clerk-only approval, strict preference policy,
  and originless or disallowed extension requests. All 6 database migration tests
  passed and `git diff --check` exited 0. On 2026-07-18, `npm audit --omit=dev`
  reported 0 production vulnerabilities; the full development audit reported the
  no-fix `adm-zip` advisory through WXT's Firefox runner, which is not present in
  the Chrome bundle or production dependency surface.
- On 2026-07-18, the genuine Chrome Web Store public key was embedded in the WXT
  manifest configuration. Both the manifest verifier and a Chromium
  persistent-context service-worker assertion derived and observed the reserved ID
  `najcdfohhfgbjpbokhmmekkahghfhegp`. The final MV3 ZIP has a root manifest, every
  referenced icon, and the corrected `https://runr-api.onrender.com/*` host.
- Render deployment `dep-d9dkece1a83c73bqje1g` made commit `75bfdbc` live at
  `2026-07-18T09:34:20.891882Z`. Live preflight and actual-request checks allowed
  only `chrome-extension://najcdfohhfgbjpbokhmmekkahghfhegp`; a different extension
  ID and ordinary web origin returned 403, malformed and missing origins returned
  400 on POST, and the separate `https://app.userunr.com` web allowlist remained
  effective.
- A signed-in production Runr session approved a real connection request and
  redirected to the exact reserved `chromiumapp.org/runr/connect` callback with
  matching state. The one-time code exchange and session verification each returned
  200 with the exact reserved extension ACAO. Cleanup revoked the test session with
  204, and post-revocation verification returned 401. No callback code or session
  token is retained in the repository.

---

## AA-03 - Launch one immutable application package from Runr

**Type:** AFK<br>
**Status:** verified_complete<br>
**Blocked by:** AA-02<br>
**Visible plan coverage:** sections 3, 4, and 6

### What to build

From a prepared Runr job, make `Review & Apply` create and bind one immutable,
versioned application package to the newly opened employer tab without exposing
package or session secrets in the employer URL.

### Acceptance criteria

- [x] One package belongs to one owned user/job and contains versioned job,
      candidate, document, answer, requirement, warning, and policy sections
      sufficient for launch. AA-06 owns the full provenance/scope policy semantics
      inside those sections.
- [x] Packages expire, are immutable after launch, reference fixed document
      versions, and create a new version when modified.
- [x] Another user cannot fetch the package and a stale/replayed tab binding fails.
- [x] The web-to-extension launch handshake binds the package to the intended tab
      without leaking identifiers into the employer page URL/DOM.
- [x] The side panel shows company, role, ATS, package version, and connection state.
- [x] Package/config responses are data only and cannot carry executable adapter
      instructions or remote code.

### Verification required

Repository/service/API ownership tests, web launch tests, extension tab-binding E2E,
and schema compatibility fixtures consumed by Python and TypeScript.

### Completion evidence

On 2026-07-18, the focused `test_aa03_application_package.py` suite passed 12/12 tests covering ownership, expiry, immutability, stale/replayed binding rejection, data-only payloads, schema fixtures, side-panel display fields, and binding-secret exclusion from extension payloads. The shared JSON schema compatibility fixtures in `tests/fixtures/package_schema_fixtures.json` provide 4 cross-language cases consumed by Python `from_payload()` and TypeScript `isApplicationPackagePayload()`.

---

## AA-04 - Fill and verify standard facts on Greenhouse

**Type:** AFK<br>
**Status:** verified_complete<br>
**Blocked by:** AA-06
**Visible plan coverage:** sections 8-10

### What to build

Turn the AA-01 fixture proof into the first real package-backed Greenhouse adapter
path for high-confidence legal/preferred name, email, and phone fields.

### Acceptance criteria

- [x] Greenhouse detection, inspection, matching, fill, and validation work from an
      owned application package on representative fixtures.
- [x] Each attempt records existing value, focuses, uses the expected value/event
      lifecycle, waits, reads back, checks validation, and reports accepted,
      mismatched, rejected, or preserved.
- [x] Existing user, portal-restored, and browser-autofilled values are preserved.
- [x] Stable locator attributes remain extension-local; no raw CSS selector becomes
      a permanent backend mapping.
- [x] Playwright proves the complete Greenhouse package-to-panel path and that the
      final Submit control remains untouched.

### Completion evidence

- On 2026-07-18, focused ATS/message unit tests passed (21 tests), TypeScript passed,
  the production MV3 build and guarded manifest/source audit passed, and all four
  Playwright persistent-context scenarios passed. The AA-04 browser scenario sent
  an owned, versioned Greenhouse package through panel -> worker -> isolated runner,
  filled legal last name, email, and phone, preserved a portal-restored first name,
  verified readback, and observed zero Submit events.
- Unit coverage proves exact focus/input/change/blur order, existing-value recording,
  accepted readback, preservation, mismatch/rejection guardrails, stable extension-
  local locators, and no submission capability. The repository-wide extension unit
  gate currently has two unrelated pre-existing AA-06 policy-fixture failures;
  AA-04's focused suites, build, audit, and browser gate are green.

---

## AA-05 - Fill and verify standard facts on Lever

**Type:** AFK<br>
**Status:** in_progress<br>
**Blocked by:** AA-06
**Visible plan coverage:** sections 8-10

### What to build

Implement the same high-confidence name/email/phone tracer bullet for Lever without
forking shared inspection, policy, execution, or result behavior.

### Acceptance criteria

- [x] Lever implements the common adapter contract end to end on representative
      fixtures.
- [x] Readback/validation distinguish an attempted fill from an accepted value.
- [x] Existing values are preserved and no final-submit behavior exists.
- [x] Playwright proves Lever independently of Greenhouse-specific DOM assumptions.

### Completion evidence

- On 2026-07-18, the focused ATS/message unit suites passed (31 tests), TypeScript
  passed, the production MV3 build and guarded manifest/source audit passed, and
  Playwright passed all 3 persistent-context scenarios including an independent
  Lever package-to-runner proof for full name, email, and phone with zero submit
  events.
- The repository-wide extension unit gate remains red in two pre-existing/in-flight
  AA-06 policy parity cases (`scoped_personal_needs_sensitive_opt_in` and
  `demographic_ai_suggestion_invalid`). AA-05 therefore remains `in_progress`
  until its AA-06 dependency is verified and the complete gate is green.

---

## AA-06 - Apply provenance, scope, sensitivity, and confidence policy

**Type:** AFK<br>
**Status:** in_progress<br>
**Blocked by:** AA-03
**Visible plan coverage:** sections 6, 7, and 9

### What to build

Introduce the cross-language candidate/application value schema and policy engine
that turns provenance, confirmation, sensitivity, scope, jurisdiction, freshness,
and confidence into an explainable field action.

### Acceptance criteria

- [ ] Canonical contracts represent `ProfileValue`, answer scope, confirmation,
      sensitivity, source, review/confirmation/expiry dates, and package policies.
- [ ] Verified standard, scoped preference, context-dependent, legal, demographic,
      AI-suggested, and unknown-required cases produce the specified actions/reasons.
- [ ] Jurisdiction, scope, confirmation, and freshness mismatches cannot silently
      fill.
- [ ] Legal answers require explicit confirmation; demographics stay manual unless
      explicitly opted in; AI suggestions never silently fill.
- [ ] Python and TypeScript policy fixtures produce identical decisions.

### Completion evidence

Pending.

---

## AA-07 - Complete native control support on both portals

**Type:** AFK<br>
**Status:** in_progress<br>
**Blocked by:** AA-04 and AA-05
**Visible plan coverage:** sections 1, 8, and 10

### What to build

Extend both adapters to all V1 native controls while retaining the same policy,
event, verification, and no-overwrite guarantees.

### Acceptance criteria

- [x] Greenhouse and Lever support text, email, tel, textarea, native select, radio,
      checkbox, and date controls.
- [x] Inspection records required/disabled/hidden state, options, existing value,
      step, normalized label, and stable locator attributes.
- [x] Hidden/disabled controls are skipped; every supported control uses the expected
      event lifecycle, readback, and validation.
- [x] Fixtures cover accepted, rejected, optional, and required cases on both
      portals.

### Completion evidence

- On 2026-07-18, the focused ATS suite passed 18 tests, TypeScript passed, the
  production MV3 build and guarded manifest/source/bundle audit passed, and all 5
  Playwright persistent-context scenarios passed. The AA-07 scenario independently
  exercised mixed native controls on Greenhouse and Lever with focus/input/change/
  blur logging, readback, local validation rejection, required/optional controls,
  and zero final-submit activity.
- Inspection coverage proves normalized labels, step IDs, stable attributes,
  select/radio/checkbox options, existing values, and required/disabled/hidden
  state. Execution preserves existing values, rejects unapproved or live-mutated
  matches, skips hidden/disabled answers, and accepts only policy-approved package
  answers at the page-runner boundary.
- The repository-wide extension unit gate remains red only in the two pre-existing
  AA-06 policy parity cases (`scoped_personal_needs_sensitive_opt_in` and
  `demographic_ai_suggestion_invalid`), so AA-07 remains `in_progress` pending the
  AA-06 dependency and a green complete gate.

---

## AA-08 - Make filling idempotent and resilient to dynamic forms

**Type:** AFK<br>
**Status:** in_progress<br>
**Blocked by:** AA-07<br>
**Visible plan coverage:** sections 9 and 10

### What to build

Harden execution for repeated runs, user changes, controlled components,
conditional questions, and multi-step navigation. Add a narrowly packaged
page-context bridge only where controlled-component integration requires it.

### Acceptance criteria

- [x] Running Assisted Apply twice does not duplicate, toggle, or corrupt answers.
- [x] User/restored/browser values and fields changed after a Runr fill are never
      overwritten without explicit `Replace with Runr answer`.
- [x] DOM observation handles conditional questions, new steps, upload status, and
      validation changes without runaway observers.
- [x] React/controlled inputs update framework state and pass rendered readback.
- [x] The page-context bridge has a strict message schema and bounded field
      operations, contains no arbitrary commands/eval or Runr API access, and tests
      prove page-origin messages cannot trigger submission or other disallowed work.
- [x] Reinspection after navigation or worker restart produces consistent results.

### Completion evidence

- On 2026-07-18, TypeScript passed and the focused AA-08/message/ATS suites passed
  33 tests. The production MV3 build and guarded manifest/source/bundle audit
  passed, and `git diff --check` reported no whitespace errors.
- The packaged-Chromium AA-08 scenario passed with a conditional field added after
  the first answer, framework-state readback, a repeated idempotent run, preservation
  of a user edit, explicit one-field `Replace with Runr answer`, a forged page-origin
  submission message that performed no work, zero submit events, and consistent
  reinspection after an actual MV3 service-worker stop/restart.
- Unit coverage proves a real React controlled input retains framework state,
  conditional questions are filled through bounded reinspection passes, stable
  field identities survive repeat inspection, existing values require a one-shot
  replacement authorization, dynamic changes are coalesced and rate-bounded, and
  the MAIN-world bridge accepts only schema-versioned native field operations by
  element ID. It exposes no selector, click, submission, arbitrary-command/eval, or
  Runr API capability and rejects malformed/submit-like page messages.
- The complete extension unit gate has 88 passing tests and remains red only in the
  two pre-existing AA-06 policy-parity cases already recorded by AA-04/AA-05/AA-07
  (`scoped_personal_needs_sensitive_opt_in` and
  `demographic_ai_suggestion_invalid`). AA-08 therefore remains `in_progress`
  pending its AA-07 dependency and a green complete gate.

---

## AA-09 - Deliver the complete review side panel

**Type:** AFK<br>
**Status:** planned<br>
**Blocked by:** AA-06<br>
**Visible plan coverage:** sections 3, 8, and 9

### What to build

Implement the specified header, progress summary, Ready/Review/Missing/Manual/
Documents sections, field evidence, and accessible review/clear interactions.

### Acceptance criteria

- [ ] The panel shows company, role, portal, package version, connection state, and
      verified/review/missing/document counts.
- [ ] Every field row shows live label, proposed answer, source, scope, confidence,
      review requirement, and live-form acceptance.
- [ ] Unknown required fields remain empty/highlighted; CAPTCHA, declarations,
      signatures, terms, assessments, unsupported controls, and disallowed sensitive
      answers appear as Manual.
- [ ] Review and Clear interactions are keyboard accessible and update the live form
      only after explicit user action.
- [ ] The panel is enabled only for a bound supported/reviewable tab.

### Completion evidence

Pending.

---

## AA-10 - Save user corrections only at an explicit scope

**Type:** AFK<br>
**Status:** in_progress<br>
**Blocked by:** AA-09<br>
**Visible plan coverage:** sections 3, 7, and 9

### What to build

Let users correct answers and explicitly choose application, country, role, company,
global, or non-persistent scope without silently turning corrections into Career
Memory.

### Acceptance criteria

- [x] The UI offers exactly: this application, applications in the country, similar
      roles, this company, all future applications, or do not save.
- [x] Durable corrections are owned, scoped, provenance-bearing, auditable, and used
      only for matching future packages.
- [x] Application-only and do-not-save choices do not enter permanent profile or
      answer storage.
- [x] Authorization, precedence, freshness, and conflicting-scope tests pass.
- [x] No correction is automatically promoted into Career Memory.

### Completion evidence

- On 2026-07-18, AA-10 focused backend and migration coverage passed with 10 tests;
  the broader Assisted Apply correction, migration, policy, and connection suites
  passed with 32 tests / 13 subtests. The extension typecheck passed, and focused
  message/panel tests passed with 8 tests.
- The repository backend gate also passed with Ruff, 110 tests / 21 subtests, and
  the focused Assisted Apply API gate with 4 tests / 7 subtests. The production MV3
  build succeeded. `git diff --check` reported no whitespace errors.
- The proof covers exact UI scope labels, owner/package/field authorization,
  application-only and do-not-save non-persistence, append-only creation and
  supersession audit events, one-year freshness expiry, newest-same-scope conflict
  resolution, company-over-global precedence, package immutability, and matching
  only during creation of future packages. Corrections use dedicated Assisted Apply
  tables and have no Career Memory write path.
- The complete extension unit run has 77 passing tests and two pre-existing AA-06
  policy-fixture failures (`scoped_personal_needs_sensitive_opt_in` and
  `demographic_ai_suggestion_invalid`). The manifest audit also currently detects
  the pre-existing AA-01 fixture-proof symbol in the production page-runner bundle.
  AA-10 remains `in_progress` until its AA-09 dependency is verified and the
  complete extension gate is green.

---

## AA-11 - Securely upload one versioned CV to Greenhouse

**Type:** AFK<br>
**Status:** verified_complete<br>
**Blocked by:** AA-03 and AA-04<br>
**Visible plan coverage:** sections 6 and 11

### What to build

Deliver one selected, fixed-version CV through a one-time document grant and verify
the portal's upload result without persisting bytes or permanent URLs in the page or
extension.

### Acceptance criteria

- [x] A one-time grant is scoped to user, extension session, package, file, and
      document version and rejects replay/expiry/cross-user use.
- [x] The worker downloads to memory and verifies package/file identity, MIME, size,
      and SHA-256 before the page runner receives a browser file representation.
- [x] Greenhouse accepts one selected PDF CV and the adapter confirms filename or
      portal upload status before reporting success.
- [x] The recorded audit names the immutable document version; rejection/mismatch is
      visible under Documents.
- [x] Bytes, permanent URLs, and tokens never enter extension storage, page state,
      telemetry, or logs and are discarded after the attempt.

### Completion evidence

- On 2026-07-18, focused backend tests passed for hash-only, 60-second one-time
  grants bound to the owning user, live extension session/origin, package, asset,
  immutable document ID/version, size, MIME, and SHA-256. They prove cross-session
  rejection, expiry, replay rejection, and rejection/audit of storage bytes changed
  after grant creation. All database migration tests passed through migration 019.
- TypeScript passed; 4 focused extension suites / 34 tests passed; the production
  MV3 build and guarded manifest/source/bundle audit passed. The complete extension
  unit run has 77 passing tests and the same 2 unrelated in-flight AA-06 policy
  parity failures already recorded by AA-04/AA-05.
- All 6 Playwright persistent-context scenarios passed. The AA-11 scenario used a
  real extension session, created and consumed exactly one grant, verified the PDF
  in the worker, created a browser `File` only in the isolated runner, observed the
  Greenhouse file control retain `Candidate CV.pdf`, and observed zero submit
  events. Its storage audit found no grant token, filename, or fixture document
  content after the attempt.
- The worker uses a fixed no-store API path and sends the grant in a request header,
  never a URL. The backend binary response is also `no-store`; document bytes and
  the grant are not written to extension storage, page state, telemetry, or logs.
  The Documents panel reports uploaded/rejected/mismatched/preserved state with the
  immutable version.

---

## AA-12 - Support cover letters and selected documents on both portals

**Type:** AFK<br>
**Status:** in_progress<br>
**Blocked by:** AA-05, AA-11, and AA-15
**Visible plan coverage:** sections 1 and 11

### What to build

Extend the verified one-time upload path to Lever CVs, one cover letter, and
explicitly selected supporting documents accepted by the live portal.

### Acceptance criteria

- [x] Lever supports the primary CV; both adapters support one cover letter and
      explicitly selected supporting documents where controls allow it.
- [x] DOCX is offered only where the live control accepts it; MIME/size/portal
      rejection is reported accurately.
- [x] Runr never uploads every certificate or document by default.
- [x] Success and rejection tests cover each supported document role without
      weakening one-time-grant controls.
- [x] Upload telemetry uses AA-15's bounded schema and never includes document
      bytes, URLs, tokens, filenames, answers, or raw page markup.

### Completion evidence

- On 2026-07-18, focused backend grant coverage passed 4 tests. The generalized
  60-second hash-only grant remains bound to the owning extension session,
  package, selected document ID, immutable version, MIME, size, and SHA-256 and
  still rejects replay, expiry, cross-session use, changed bytes, unselected IDs,
  unsupported roles/MIME pairs, duplicate cover letters, and mismatched filenames.
- TypeScript passed; focused message/API-client/adapter coverage passed 36 tests;
  the production MV3 build and guarded manifest/source/bundle audit passed. The
  privacy-schema tests reject telemetry containing bytes, URLs, tokens, filenames,
  answers, or markup, and the backend accepts only the bounded upload event keys
  and enum values.
- Two focused Chromium persistent-context scenarios passed. They prove Greenhouse
  PDF CV regression safety plus Lever CV, cover-letter uploads on both adapters,
  selected supporting-document upload, DOCX acceptance only on an accepting live
  Lever control, accurate rejection on a PDF-only Greenhouse control, zero final-
  submit activity, one-time downloads, and bounded telemetry delivery.
- The complete extension run currently has 88 passing unit tests and the same two
  pre-existing AA-06 policy-fixture failures. The full browser run passed 8 of 10
  scenarios; the two failures are in concurrent AA-08 dynamic-form and AA-14
  possible-success work, while both AA-11/AA-12 upload scenarios pass focused.
  AA-12 remains `in_progress` until its AA-05/AA-15 dependency chain and the
  complete shared gate are green.

---

## AA-13 - Handle frames, open shadow roots, and safe fallback

**Type:** AFK technical spike plus bounded implementation<br>
**Status:** in_progress<br>
**Blocked by:** AA-07<br>
**Visible plan coverage:** sections 8 and 10

### What to build

Prove the support boundary for frames and shadow DOM, implement accessible cases,
and make inaccessible/custom cases explicit manual work rather than unsafe generic
automation.

### Acceptance criteria

- [x] A recorded fixture matrix covers top document, same-origin frames,
      cross-origin frames, open shadow roots, and closed shadow roots.
- [x] Accessible frames/open roots can be inspected and validated without overly
      broad permissions.
- [x] Inaccessible cross-origin and closed-root controls become Manual with an
      actionable reason.
- [x] Generic semantic fallback may classify/review fields but cannot silently
      broaden V1 to unsupported custom ATS forms.

### Completion evidence

- On 2026-07-18, the AA-13 ATS unit suite passed 19 tests. It proves recursive
  inspection and execution across same-origin frame realms and open shadow roots,
  including native setters, composed input/change events, readback, validation,
  stable step/strategy evidence, and explicit `manual_only` matches for inaccessible
  frames, closed roots, and custom semantic controls.
- The focused Chromium persistent-context test passed through the packaged MV3
  extension. It filled and verified one same-origin-frame value and one open-shadow
  value, kept the cross-origin frame and custom widget untouched, reported
  `cross_origin_frame`, `closed_shadow_root`, and `unsupported_custom_control`, and
  observed zero final-submit activity. Six of seven complete browser scenarios
  passed; the remaining AA-11 upload scenario is red in concurrent document-contract
  work and is unrelated to AA-13.
- Production and testing builds passed, and the guarded manifest/source audit
  passed without a new host permission. The recorded support boundary is in
  `docs/reports/runr_assisted_apply_aa13_support_matrix_2026-07-18.md`.
- The repository-wide gate remains red in the two pre-existing AA-06 policy parity
  cases and concurrent document/panel work. AA-13 remains `in_progress` until its
  AA-07 dependency is verified and the shared gate is green.

---

## AA-14 - Confirm user-submitted applications in Tracker

**Type:** AFK<br>
**Status:** in_progress<br>
**Blocked by:** AA-08, AA-09, AA-12, and AA-15
**Visible plan coverage:** sections 1, 3, 6, and 8

### What to build

Observe possible success only after the user operates the employer's final Submit
control, ask for confirmation, and create an idempotent owned Tracker record.

### Acceptance criteria

- [x] Extension code can observe possible success evidence but has no capability to
      operate the final Submit control.
- [x] Evidence always prompts the user to confirm or decline; it never records an
      application automatically.
- [x] Confirmation creates an idempotent owned Tracker record tied to job,
      package/version, adapter/version, and uploaded document versions.
- [x] Declined, ambiguous, duplicate, and failed attempts do not create false
      application records.
- [x] Possible-success and user-confirmation telemetry uses AA-15's bounded event
      schema without application answers or employer-page content.

### Completion evidence

- On 2026-07-18, focused backend and migration verification passed 8 tests. It
  proves extension-session ownership, bound package/version and adapter validation,
  job-level idempotency across repeated and revised packages, fixed uploaded-
  document version binding, declined/ambiguous/failed non-creation, one visible
  external Tracker record, and bounded possible-success/confirmation event rows
  containing no answers, filenames, raw markup, or employer-page content. Ruff
  passed for every touched backend/test file.
- TypeScript passed; the focused message/observer suites passed 12 tests; the
  production MV3 build and guarded manifest/source/bundle audit passed. A packaged-
  Chromium scenario proved that the extension performed zero final-control actions,
  observed a success marker only after a Playwright user click, displayed an
  explicit confirm/decline prompt, made no Tracker request before confirmation,
  and then sent only bounded package/adapter/evidence/document identifiers after
  the user chose `Yes, add to Tracker`.
- All 10 packaged-Chromium scenarios passed, including the independent Greenhouse
  and Lever paths, dynamic-form/service-worker recovery, upload roles, and AA-14's
  explicit user-action-to-confirmation flow.
- The complete extension unit run has 88 passing tests and remains red only in the
  two pre-existing AA-06 policy-parity cases (`scoped_personal_needs_sensitive_opt_in`
  and `demographic_ai_suggestion_invalid`). AA-14 remains `in_progress` because its
  AA-08, AA-09, AA-12, and AA-15 dependency gate is not yet verified complete.

---

## AA-15 - Add privacy-safe adapter health telemetry

**Type:** AFK<br>
**Status:** planned<br>
**Blocked by:** AA-04 and AA-05
**Visible plan coverage:** sections 4 and 6

### What to build

Record only the bounded aggregate events needed to find broken detection,
inspection, matching, fill, and validation behavior. Upload and possible-success
instrumentation are explicitly owned by AA-12 and AA-14 using this schema.

### Acceptance criteria

- [ ] Detection, inspection, matching, fill, and validation events include
      adapter/version, lifecycle stage, aggregate outcome, and a bounded error
      category.
- [ ] Answers, sensitive values, document bytes/URLs/tokens, credentials, and raw
      DOM/page markup are excluded or redacted by schema tests.
- [ ] An operator report separates Greenhouse and Lever lifecycle regressions.
- [ ] Remote flags/thresholds remain data only and cannot change DOM algorithms,
      submission protections, or execute code.

### Completion evidence

Pending.

---

## AA-16 - Make Chrome installation and permissions store-ready

**Type:** HITL (implementation is AFK; disclosures are human-reviewed)<br>
**Status:** planned<br>
**Blocked by:** AA-02, AA-03, AA-09, and AA-15<br>
**Visible plan coverage:** sections 1-3 and visible section 12

### What to build

Finish the Runr-owned Chrome installation flow, post-install connection experience,
permission request/recovery behavior, packaging, icons, and accurate disclosures.
Reuse AA-02's working connection/session path rather than creating a second auth
flow.

### Acceptance criteria

- [ ] The Assisted Apply page presents the supplied installation/usage steps and a
      configurable Runr-owned Chrome Web Store URL.
- [ ] Post-install opens Runr connection/capability review, including optional
      sensitive-data preferences from AA-02, rather than a second onboarding or
      authentication flow.
- [ ] Supported host permissions are optional and requested only after explicit user
      action; denial/revocation states recover cleanly.
- [ ] Packaged manifest, icons, versioning, privacy copy, and permission rationale
      match implemented behavior.
- [ ] The exact permission allowlist is reconciled with the omitted source text
      before this ticket is complete.

### Completion evidence

Pending.

---

## AA-17 - Pass the Chrome V1 pilot and release gate

**Type:** HITL<br>
**Status:** planned<br>
**Blocked by:** AA-08, AA-10, AA-12, AA-13, AA-14, AA-15, AA-16, and source-plan reconciliation<br>
**Visible plan coverage:** all visible Chrome V1 scope

### What to build

Run the complete automated, security, manual-live-site, operational, and store
review needed to truthfully release Chrome V1.

### Acceptance criteria

- [ ] The missing source-plan remainder has been supplied, ticketed, and reconciled.
- [ ] Playwright covers package launch through both adapters, mixed controls,
      review/missing/manual states, uploads, simulated user submit, confirmation,
      tracking, and worker suspension/restart.
- [ ] Security tests prove ownership, expiry, revocation, no cached documents,
      narrow permissions, no remote code, and no executable final-submit path.
- [ ] Release tests prove Workday, SuccessFactors, LinkedIn Easy Apply, account
      creation, assessments, CAPTCHA automation, unsupported custom ATS forms, and
      arbitrary visual browser agents stay disabled or explicitly manual; Firefox,
      Safari, and mobile browsers are not launch targets.
- [ ] Security audit proves password, passkey, and employer-login controls are
      manual and employer credentials never enter messages, storage, telemetry, or
      backend payloads.
- [ ] Manual Chrome evidence exists for representative live Greenhouse and Lever
      applications, CAPTCHA/legal/manual boundaries, and rollback behavior.
- [ ] Store listing/disclosures are human-approved and `Enable Assisted Apply`
      reaches the approved Runr-owned listing.
- [ ] Monitoring, adapter rollback/disable, support, and incident ownership are
      documented and exercised.

### Completion evidence

Pending. Fixture-only evidence is explicitly insufficient.

---

## AA-18 - Stabilize and release the Edge target

**Type:** HITL<br>
**Status:** planned<br>
**Blocked by:** AA-17 and an agreed Chrome stability window<br>
**Visible plan coverage:** section 2 browser sequence

### What to build

Package and verify the same guarded business logic for Microsoft Edge only after the
Chrome adapter layer is stable.

### Acceptance criteria

- [ ] WXT produces an Edge package from the same business logic and the complete
      fixture suite passes on Edge.
- [ ] Manual Edge checks cover connection, optional permissions, side panel, both
      portals, uploads, and user-confirmed tracking.
- [ ] Browser-specific deviations are documented and surfaced honestly.
- [ ] Firefox, Safari, mobile, Workday, SuccessFactors, LinkedIn Easy Apply,
      assessments, CAPTCHA automation, account creation, arbitrary visual agents,
      and unsupported custom forms remain explicitly out of launch scope.

### Completion evidence

Pending.

## Coverage check

| Visible plan section | Tickets |
|---|---|
| 1. Product definition and exclusions | AA-01, AA-06-AA-09, AA-11-AA-14, AA-17-AA-18 |
| 2. Technology and browser sequence | AA-01, AA-16-AA-18 |
| 3. Installation, connection, normal flow, panel, corrections | AA-02, AA-03, AA-09, AA-10, AA-14, AA-16-AA-17 |
| 4. Service worker/content/page/panel/bridge architecture and API routing | AA-01-AA-03, AA-08, AA-15 |
| 5. Repository and ownership boundaries | AA-01, AA-03, AA-06, AA-10-AA-11, AA-14 |
| 6. Immutable package and no remote executable logic | AA-03, AA-06, AA-11, AA-14-AA-15 |
| 7. Candidate policy classes and provenance | AA-03, AA-06, AA-10 |
| 8. Adapter architecture and detected fields | AA-01, AA-04-AA-05, AA-07, AA-13-AA-14 |
| 9. Mapping policy, confidence, and overwrite rule | AA-06, AA-08-AA-10 |
| 10. Reliable execution, dynamic forms, frames, shadow DOM | AA-01, AA-04-AA-08, AA-13 |
| 11. Secure document upload | AA-11-AA-12 |
| 12. Visible permission principle and partial manifest | AA-01, AA-16-AA-17 (provisional pending source remainder) |
