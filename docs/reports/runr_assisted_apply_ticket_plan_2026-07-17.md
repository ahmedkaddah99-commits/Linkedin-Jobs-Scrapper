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
**Status:** planned<br>
**Blocked by:** AA-02<br>
**Visible plan coverage:** sections 3, 4, and 6

### What to build

From a prepared Runr job, make `Review & Apply` create and bind one immutable,
versioned application package to the newly opened employer tab without exposing
package or session secrets in the employer URL.

### Acceptance criteria

- [ ] One package belongs to one owned user/job and contains versioned job,
      candidate, document, answer, requirement, warning, and policy sections
      sufficient for launch. AA-06 owns the full provenance/scope policy semantics
      inside those sections.
- [ ] Packages expire, are immutable after launch, reference fixed document
      versions, and create a new version when modified.
- [ ] Another user cannot fetch the package and a stale/replayed tab binding fails.
- [ ] The web-to-extension launch handshake binds the package to the intended tab
      without leaking identifiers into the employer page URL/DOM.
- [ ] The side panel shows company, role, ATS, package version, and connection state.
- [ ] Package/config responses are data only and cannot carry executable adapter
      instructions or remote code.

### Verification required

Repository/service/API ownership tests, web launch tests, extension tab-binding E2E,
and schema compatibility fixtures consumed by Python and TypeScript.

### Completion evidence

Pending.

---

## AA-04 - Fill and verify standard facts on Greenhouse

**Type:** AFK<br>
**Status:** planned<br>
**Blocked by:** AA-06
**Visible plan coverage:** sections 8-10

### What to build

Turn the AA-01 fixture proof into the first real package-backed Greenhouse adapter
path for high-confidence legal/preferred name, email, and phone fields.

### Acceptance criteria

- [ ] Greenhouse detection, inspection, matching, fill, and validation work from an
      owned application package on representative fixtures.
- [ ] Each attempt records existing value, focuses, uses the expected value/event
      lifecycle, waits, reads back, checks validation, and reports accepted,
      mismatched, rejected, or preserved.
- [ ] Existing user, portal-restored, and browser-autofilled values are preserved.
- [ ] Stable locator attributes remain extension-local; no raw CSS selector becomes
      a permanent backend mapping.
- [ ] Playwright proves the complete Greenhouse package-to-panel path and that the
      final Submit control remains untouched.

### Completion evidence

Pending.

---

## AA-05 - Fill and verify standard facts on Lever

**Type:** AFK<br>
**Status:** planned<br>
**Blocked by:** AA-06
**Visible plan coverage:** sections 8-10

### What to build

Implement the same high-confidence name/email/phone tracer bullet for Lever without
forking shared inspection, policy, execution, or result behavior.

### Acceptance criteria

- [ ] Lever implements the common adapter contract end to end on representative
      fixtures.
- [ ] Readback/validation distinguish an attempted fill from an accepted value.
- [ ] Existing values are preserved and no final-submit behavior exists.
- [ ] Playwright proves Lever independently of Greenhouse-specific DOM assumptions.

### Completion evidence

Pending.

---

## AA-06 - Apply provenance, scope, sensitivity, and confidence policy

**Type:** AFK<br>
**Status:** planned<br>
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
**Status:** planned<br>
**Blocked by:** AA-04 and AA-05
**Visible plan coverage:** sections 1, 8, and 10

### What to build

Extend both adapters to all V1 native controls while retaining the same policy,
event, verification, and no-overwrite guarantees.

### Acceptance criteria

- [ ] Greenhouse and Lever support text, email, tel, textarea, native select, radio,
      checkbox, and date controls.
- [ ] Inspection records required/disabled/hidden state, options, existing value,
      step, normalized label, and stable locator attributes.
- [ ] Hidden/disabled controls are skipped; every supported control uses the expected
      event lifecycle, readback, and validation.
- [ ] Fixtures cover accepted, rejected, optional, and required cases on both
      portals.

### Completion evidence

Pending.

---

## AA-08 - Make filling idempotent and resilient to dynamic forms

**Type:** AFK<br>
**Status:** planned<br>
**Blocked by:** AA-07<br>
**Visible plan coverage:** sections 9 and 10

### What to build

Harden execution for repeated runs, user changes, controlled components,
conditional questions, and multi-step navigation. Add a narrowly packaged
page-context bridge only where controlled-component integration requires it.

### Acceptance criteria

- [ ] Running Assisted Apply twice does not duplicate, toggle, or corrupt answers.
- [ ] User/restored/browser values and fields changed after a Runr fill are never
      overwritten without explicit `Replace with Runr answer`.
- [ ] DOM observation handles conditional questions, new steps, upload status, and
      validation changes without runaway observers.
- [ ] React/controlled inputs update framework state and pass rendered readback.
- [ ] The page-context bridge has a strict message schema and bounded field
      operations, contains no arbitrary commands/eval or Runr API access, and tests
      prove page-origin messages cannot trigger submission or other disallowed work.
- [ ] Reinspection after navigation or worker restart produces consistent results.

### Completion evidence

Pending.

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
**Status:** planned<br>
**Blocked by:** AA-09<br>
**Visible plan coverage:** sections 3, 7, and 9

### What to build

Let users correct answers and explicitly choose application, country, role, company,
global, or non-persistent scope without silently turning corrections into Career
Memory.

### Acceptance criteria

- [ ] The UI offers exactly: this application, applications in the country, similar
      roles, this company, all future applications, or do not save.
- [ ] Durable corrections are owned, scoped, provenance-bearing, auditable, and used
      only for matching future packages.
- [ ] Application-only and do-not-save choices do not enter permanent profile or
      answer storage.
- [ ] Authorization, precedence, freshness, and conflicting-scope tests pass.
- [ ] No correction is automatically promoted into Career Memory.

### Completion evidence

Pending.

---

## AA-11 - Securely upload one versioned CV to Greenhouse

**Type:** AFK<br>
**Status:** planned<br>
**Blocked by:** AA-03 and AA-04<br>
**Visible plan coverage:** sections 6 and 11

### What to build

Deliver one selected, fixed-version CV through a one-time document grant and verify
the portal's upload result without persisting bytes or permanent URLs in the page or
extension.

### Acceptance criteria

- [ ] A one-time grant is scoped to user, extension session, package, file, and
      document version and rejects replay/expiry/cross-user use.
- [ ] The worker downloads to memory and verifies package/file identity, MIME, size,
      and SHA-256 before the page runner receives a browser file representation.
- [ ] Greenhouse accepts one selected PDF CV and the adapter confirms filename or
      portal upload status before reporting success.
- [ ] The recorded audit names the immutable document version; rejection/mismatch is
      visible under Documents.
- [ ] Bytes, permanent URLs, and tokens never enter extension storage, page state,
      telemetry, or logs and are discarded after the attempt.

### Completion evidence

Pending.

---

## AA-12 - Support cover letters and selected documents on both portals

**Type:** AFK<br>
**Status:** planned<br>
**Blocked by:** AA-05, AA-11, and AA-15
**Visible plan coverage:** sections 1 and 11

### What to build

Extend the verified one-time upload path to Lever CVs, one cover letter, and
explicitly selected supporting documents accepted by the live portal.

### Acceptance criteria

- [ ] Lever supports the primary CV; both adapters support one cover letter and
      explicitly selected supporting documents where controls allow it.
- [ ] DOCX is offered only where the live control accepts it; MIME/size/portal
      rejection is reported accurately.
- [ ] Runr never uploads every certificate or document by default.
- [ ] Success and rejection tests cover each supported document role without
      weakening one-time-grant controls.
- [ ] Upload telemetry uses AA-15's bounded schema and never includes document
      bytes, URLs, tokens, filenames, answers, or raw page markup.

### Completion evidence

Pending.

---

## AA-13 - Handle frames, open shadow roots, and safe fallback

**Type:** AFK technical spike plus bounded implementation<br>
**Status:** planned<br>
**Blocked by:** AA-07<br>
**Visible plan coverage:** sections 8 and 10

### What to build

Prove the support boundary for frames and shadow DOM, implement accessible cases,
and make inaccessible/custom cases explicit manual work rather than unsafe generic
automation.

### Acceptance criteria

- [ ] A recorded fixture matrix covers top document, same-origin frames,
      cross-origin frames, open shadow roots, and closed shadow roots.
- [ ] Accessible frames/open roots can be inspected and validated without overly
      broad permissions.
- [ ] Inaccessible cross-origin and closed-root controls become Manual with an
      actionable reason.
- [ ] Generic semantic fallback may classify/review fields but cannot silently
      broaden V1 to unsupported custom ATS forms.

### Completion evidence

Pending.

---

## AA-14 - Confirm user-submitted applications in Tracker

**Type:** AFK<br>
**Status:** planned<br>
**Blocked by:** AA-08, AA-09, AA-12, and AA-15
**Visible plan coverage:** sections 1, 3, 6, and 8

### What to build

Observe possible success only after the user operates the employer's final Submit
control, ask for confirmation, and create an idempotent owned Tracker record.

### Acceptance criteria

- [ ] Extension code can observe possible success evidence but has no capability to
      operate the final Submit control.
- [ ] Evidence always prompts the user to confirm or decline; it never records an
      application automatically.
- [ ] Confirmation creates an idempotent owned Tracker record tied to job,
      package/version, adapter/version, and uploaded document versions.
- [ ] Declined, ambiguous, duplicate, and failed attempts do not create false
      application records.
- [ ] Possible-success and user-confirmation telemetry uses AA-15's bounded event
      schema without application answers or employer-page content.

### Completion evidence

Pending.

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
