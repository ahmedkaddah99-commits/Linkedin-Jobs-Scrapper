# Runr Assisted Apply — Authoritative Ticket Pack

## Purpose

Build a reliable Assisted Apply workflow that prepares a real employer application in an inactive Chrome tab, fills candidate information and approved job-specific experience content, uploads the selected documents, and presents the completed application for human review.

The system must never perform final submission.

This ticket pack supersedes the earlier broad plans. Changes to its architecture, ticket boundaries, dependencies, or safety rules require an explicit architecture decision before implementation.

---

## Definition of done

The first production release is complete when Runr can:

1. Prepare supported Greenhouse and Lever applications in an inactive Chrome tab.
2. Fill supported personal, experience, education, date, rich-text, select, and standard-question fields.
3. Use the bullet points approved for the specific job application.
4. Upload the selected CV, cover letter, and supported additional documents.
5. Avoid duplicate experience and education entries when preparation is repeated.
6. Report unresolved, sensitive, ambiguous, and manually required fields.
7. Activate the exact prepared tab when the user clicks **Review filled application**.
8. Recover safely from a reload or closed tab through an explicit retry.
9. Never trigger final submission through a click, form API, keyboard event, navigation, or network request.
10. Pass the automated test suite and a controlled live pilot.

Workday is the first expansion after this core release. It has its own discovery and implementation tickets because it is likely to represent the repeated-experience workflow more strongly than the existing Greenhouse and Lever implementation.

---

## Locked architecture

These decisions are fixed unless a feasibility ticket proves one impossible:

- The Runr Chrome extension is the browser runtime.
- Playwright is used for testing, not as the production browser runtime.
- The extension service worker creates preparation tabs using `active: false`.
- The web application sends validated commands to the extension service worker through the existing externally connectable mechanism.
- The sidepanel is required only for extension-controlled interactions such as granting a missing optional host permission, reviewing unresolved fields, or manually resuming a blocked flow.
- Previously granted ATS host permission must not be requested again for every application.
- Browser-local `tabId` and `windowId` values never enter the backend.
- The backend owns durable product status; the extension owns live browser execution state.
- `chrome.storage.session` stores only the local tab mapping and transient execution state.
- Browser restart or extension update is not automatic recovery. It requires an explicit user retry.
- Application packages are immutable and contain only approved content.
- Job-specific approved bullets take precedence over generic Career Memory content.
- ATS adapters inspect and return declarative action proposals. They do not directly click or submit.
- A centralized executor owns DOM mutations, uploads, and approved intermediate navigation.
- Intermediate navigation is denied by default and must be explicitly recognized by the ATS adapter and independently validated by the navigation controller.
- Final submission is prohibited in every release.
- AI fallback is outside this release.
- CAPTCHA solving and anti-bot circumvention are prohibited.
- Only one preparation runs at a time in the first release.

---

## Mandatory instructions for every implementation ticket

Add these instructions to every Cline/Kanban task:

> Treat this ticket as an immutable scope contract. Do not expand, reinterpret, combine, split, rewrite, or change its dependencies. Do not modify other tickets. Do not perform adjacent refactoring unless explicitly required by this ticket’s acceptance criteria. Preserve existing unrelated changes.
>
> Before editing, inspect the referenced code and report any contradiction between repository reality and this ticket. If the ticket requires an architectural change, a new dependency, or changes outside scope, stop and report the blocker instead of silently redesigning the solution.
>
> Never add automatic final submission. Never bypass CAPTCHAs, login requirements, MFA, consent, or anti-bot controls.
>
> Implement the smallest change that satisfies the acceptance criteria. Add or update the required tests in the same ticket. Run the relevant tests using the repository’s configured Python 3.12 virtual environment and existing Node package manager.
>
> At completion, provide: changed files, acceptance-criterion evidence, tests executed with results, remaining limitations, and the commit hash. Do not mark the ticket complete merely because tests pass; verify each acceptance criterion individually.

---

## Branching strategy

### Long-lived integration branch

Create one integration branch from the current deployment branch:

```text
feature/assisted-apply-background-prep
```

Do not merge this branch into `deployment/render-turso-r2` until the production-pilot gate passes.

### Ticket branches

Each ticket receives its own branch:

```text
aa/<ticket-id>-<short-name>
```

Examples:

```text
aa/aa-200-architecture-baseline
aa/aa-201-background-tab-spike
aa/aa-219-greenhouse-complete
```

### Critical branching rule

Do not create every ticket branch immediately from `deployment/render-turso-r2`.

- A ticket branch must be created only when all dependencies have been merged into `feature/assisted-apply-background-prep`.
- Independent tickets in the same batch may branch from the same integration commit and run in parallel.
- After review, merge each ticket branch into the integration branch.
- Rebase or update parallel branches before merging if another ticket changed shared files.
- Delete the ticket branch only after its commit is confirmed on the integration branch.

---

# Phase A — Evidence gates

## AA-200 — Verify architecture baseline

**Branch:** `aa/aa-200-architecture-baseline`  
**Dependencies:** None  
**Parallel:** No  
**Code changes:** Documentation and test inventory only

### Objective

Produce one repository-grounded architecture record before implementation begins.

### Scope

- Inspect the existing web app, backend, extension, shared packages, tests, fixtures, and project instructions.
- Verify the current externally connectable flow and background message handlers.
- Verify optional host-permission behavior.
- Verify exact package, binding, extension-session, and document-grant TTL semantics.
- Verify whether a bound package remains retrievable after its original expiry.
- Verify the canonical source of the application URL.
- Verify current Greenhouse and Lever capabilities and fixtures.
- Verify how tailored CV experiences and bullets are represented and whether they retain source IDs.
- Record official Chrome documentation for inactive tabs, permissions, messaging, sidepanel user gestures, and session storage.
- Create or update a short architecture decision record under the repository’s existing documentation convention.

### Non-goals

- No production code.
- No database migration.
- No new message types.
- No speculative implementation timeline.

### Acceptance criteria

- Every claim is labeled repository-confirmed, externally verified, inferred, or proposed.
- Exact files and symbols support repository claims.
- TTL behavior is described by transitions, not constants alone.
- The application URL recovery source is identified.
- Current fixture gaps are listed.
- Contradictions between this ticket pack and repository reality are reported before further work.

### Tests/evidence

- Existing relevant tests are identified and run without modification.
- Output includes commands and results.

---

## AA-201 — Prove inactive-tab browser foundation

**Branch:** `aa/aa-201-background-tab-spike`  
**Dependencies:** AA-200  
**Parallel:** No  
**Gate:** Must pass before production schema or lifecycle changes

### Objective

Prove that the installed extension can prepare a form in an inactive tab and activate that same tab later.

### Scope

- Use existing sanitized Greenhouse and Lever fixtures or add minimal test-only fixtures.
- Create a tab from the extension service worker with `active: false`.
- Wait for readiness using browser events and content-script handshakes.
- Run the existing basic field filling in the inactive tab.
- Upload a dummy PDF through the existing grant/test mechanism or a test-only equivalent.
- Report completion to the service worker.
- Activate the exact tab later by local tab ID.
- Instrument the fixture to detect every submission pathway.
- Keep spike code isolated and explicitly mark what is disposable versus reusable.

### Non-goals

- No backend preparation-session table.
- No production status dashboard.
- No Workday implementation.
- No repeatable-section production engine.
- No AI.

### Acceptance criteria

- Both fixtures can be opened inactive.
- Content scripts execute without activating the tab.
- Basic fields are filled and verified.
- A test document is attached and verified.
- The service worker receives a completion result.
- The exact prepared tab can be activated later.
- Zero form submissions, final-action clicks, terminal requests, or success navigations occur.
- Results state whether background throttling affected execution.

### Tests/evidence

- Playwright extension test or controlled Chrome integration test.
- Trace or deterministic logs containing no personal data.
- Submission instrumentation result.

---

## AA-202 — Prove repeatable-section reconciliation

**Branch:** `aa/aa-202-reconciliation-spike`  
**Dependencies:** AA-201  
**Parallel:** Yes, with AA-203

### Objective

Prove a safe algorithm for experiences and education before designing the production data model.

### Scope

- Create sanitized fixtures with:
  - Two different employers.
  - Two roles at the same employer.
  - Overlapping dates.
  - An already-prefilled experience.
  - An ambiguous experience match.
  - Education entries.
- Prototype normalized matching using candidate arrays or a multimap.
- Match by visible employer/institution, title/degree, dates, current status, location, and existing content where available.
- Update one unique confident match.
- Add only when no plausible match exists.
- Stop on ambiguity.
- Never delete unmatched ATS entries.

### Non-goals

- Stable Runr IDs must not be treated as DOM identifiers.
- No fuzzy automatic merge when multiple candidates are plausible.
- No production backend schema.

### Acceptance criteria

- Running twice creates no duplicates.
- Reloading and running again creates no duplicates.
- SPA remount simulation creates no duplicates.
- Legitimate same-employer roles remain separate.
- Ambiguous matches stop with a review-required result.
- Existing unmatched ATS entries remain untouched.

### Tests/evidence

- Deterministic unit tests for normalization and matching.
- Playwright fixture tests for add, update, rerun, reload, remount, and ambiguity.

---

## AA-203 — Workday feasibility discovery

**Branch:** `aa/aa-203-workday-discovery`  
**Dependencies:** AA-201  
**Parallel:** Yes, with AA-202

### Objective

Determine whether the shared extension architecture can handle the repeated-experience workflow that motivates this feature.

### Scope

- Use a sanitized Workday fixture, authorized test account, or non-submitted controlled application.
- Document:
  - Login/session boundary.
  - Page/step structure.
  - Repeatable experience and education controls.
  - Date inputs and date pickers.
  - Rich-text or long-description controls.
  - Custom selects/comboboxes.
  - File uploads.
  - Iframes, shadow DOM, and SPA remount behavior.
  - Intermediate navigation and final-review detection.
- Attempt no final submission.
- Produce a capability-gap matrix against the shared executor design.

### Non-goals

- No full Workday adapter.
- No production host permission.
- No credentials committed to the repository.
- No CAPTCHA or anti-bot bypass.

### Acceptance criteria

- Evidence distinguishes standard reusable controls from Workday-specific controls.
- Manual boundaries are identified.
- A recommendation states whether Workday can reuse the core executor or needs an architectural exception.
- Unknowns are converted into explicit tests, not assumptions.

### Tests/evidence

- Sanitized DOM/fixture evidence where legally and technically appropriate.
- No submitted application.
- No personal credentials or candidate information in artifacts.

---

## AA-204 — Freeze the implementation architecture

**Branch:** `aa/aa-204-freeze-architecture`  
**Dependencies:** AA-202 and AA-203  
**Parallel:** No  
**Gate:** Required before production implementation branches

### Objective

Convert spike evidence into the final implementation contract.

### Scope

- Update the architecture record from AA-200.
- Freeze:
  - Message ownership and authentication.
  - Permission flow.
  - Package and preparation TTL behavior.
  - Application URL source.
  - Backend/local state split.
  - Declarative adapter/executor boundary.
  - Intermediate-navigation evidence requirements.
  - Repeatable-section matching rules.
  - Browser restart/retry behavior.
  - Greenhouse/Lever MVP scope.
  - Workday follow-up scope.
- Update later ticket acceptance criteria only when spike evidence requires it.

### Acceptance criteria

- No unresolved contradiction remains in shared architecture.
- Every proposed TTL has code-backed semantics or an explicit product decision.
- The implementation tickets below remain valid or receive a documented amendment.
- The final-submit prohibition has an enforceable architecture and test strategy.

---

# Phase B — Shared contracts and durable data

## AA-210 — Add preparation wire protocol

**Branch:** `aa/aa-210-preparation-protocol`  
**Dependencies:** AA-204  
**Parallel:** Yes, with AA-211 and AA-216

### Objective

Define validated, versioned messages for preparation without exposing browser-local IDs or personal data unnecessarily.

### Scope

- Extend `packages/extension-messages/src/index.ts` or the repository-confirmed equivalent.
- Add messages for:
  - Start preparation.
  - Permission required.
  - Preparation accepted/rejected.
  - Progress update.
  - Needs attention.
  - Ready for review.
  - Review/activate prepared application.
  - Cancel.
  - Explicit retry.
- Add preparation status and sanitized result types.
- Keep `tabId` and `windowId` out of web/backend messages.
- Version the protocol and preserve compatibility with the existing extension.

### Acceptance criteria

- Every inbound message has runtime validation.
- Unknown fields and unknown message versions fail closed.
- External commands carry only identifiers/capabilities required for resolution.
- Existing connection and package-binding flows remain compatible.

### Tests

- Type tests and runtime validator tests for valid, missing, malformed, forged, stale, and future-version messages.

---

## AA-211 — Preserve job-specific experience provenance

**Branch:** `aa/aa-211-tailored-experience-provenance`  
**Dependencies:** AA-204  
**Parallel:** Yes, with AA-210 and AA-216

### Objective

Preserve the link between approved tailored CV bullets and their source Career Memory experiences.

### Scope

- Update the repository-confirmed tailored-document pipeline.
- Preserve:
  - Source experience ID.
  - Stable bullet/provenance ID.
  - Approved bullet text.
  - CV/package version.
  - Generation provenance.
- Maintain current rendered CV output.
- Define fallback behavior for legacy documents without IDs.

### Non-goals

- No new bullet generation during browser filling.
- No modification of approved text by the extension.

### Acceptance criteria

- Structured tailored experiences retain source IDs end to end.
- Rendered CV output is unchanged unless an existing bug is identified.
- Legacy content remains readable and is marked with reduced provenance confidence.

### Tests

- Unit tests for ID propagation, tailored bullet preservation, legacy fallback, and render regression.

---

## AA-212 — Create immutable application package v2

**Branch:** `aa/aa-212-application-package-v2`  
**Dependencies:** AA-210 and AA-211  
**Parallel:** No

### Objective

Provide the extension with one immutable, approved, job-specific package.

### Scope

- Extend the application package with:
  - Personal/contact fields.
  - Experiences with approved job-specific bullets.
  - Education.
  - Skills and languages where confirmed.
  - Explicitly approved standard answers.
  - Document metadata.
  - Provenance, package version, and content hashes.
- Enforce source precedence:
  1. Approved job-specific content.
  2. Approved structured content for the selected CV version.
  3. Confirmed Career Memory facts.
  4. Unresolved/manual.
- Keep sensitive answers review-gated.
- Make changes require a new package version.

### Acceptance criteria

- The extension payload contains no silently invented values.
- Job-specific bullets survive serialization unchanged.
- Package mutation after approval is rejected.
- Legacy v1 packages remain handled safely.

### Tests

- Backend domain, serialization, validation, immutability, provenance, precedence, sensitive-answer, and v1 compatibility tests.

---

## AA-213 — Add durable preparation-session service

**Branch:** `aa/aa-213-preparation-session-backend`  
**Dependencies:** AA-204 and AA-210  
**Parallel:** Yes, while AA-211/AA-212 are being completed

### Objective

Store durable preparation status without storing browser-local state.

### Scope

- Add the domain model, repository/migration, service, and authenticated API routes.
- Store:
  - Session ID.
  - User/package/job association.
  - ATS.
  - Durable status.
  - Aggregate counts.
  - Sanitized error category.
  - Attempt count.
  - Created/updated/expiry timestamps.
  - Canonical application reference defined in AA-204.
- Enforce the state machine and TTL chosen in AA-204.
- Accept extension status reports and provide web-app reads.

### Non-goals

- No `tabId`, `windowId`, DOM selector, document token, or raw field value.
- No automatic `submitted` state.

### Acceptance criteria

- Invalid transitions fail.
- Cross-user access fails.
- Stale/replayed extension reports fail or are idempotent as specified.
- `submitted` is possible only through existing explicit user-confirmation logic.

### Tests

- Migration, domain, state transition, authorization, expiry, idempotency, retry, and API tests.

---

# Phase C — Secure extension runtime

## AA-214 — Implement external command and permission handshake

**Branch:** `aa/aa-214-external-command-permissions`  
**Dependencies:** AA-210 and AA-213  
**Parallel:** No

### Objective

Allow the Runr web app to request preparation while keeping permission grants extension-controlled.

### Scope

- Extend the existing `onMessageExternal` path.
- Validate exact Runr sender origin, schema, connection/binding, ownership, expiry, and package/session association.
- If host permission exists, accept the command.
- If missing, return `permission_required` without opening an ATS tab.
- Let the sidepanel request optional host permission only from a direct extension user gesture.
- Allow a safe retry after permission is granted.
- Implement review/activate command routing through the service worker.

### Acceptance criteria

- A forged origin cannot start or activate a preparation.
- Missing permission never triggers a silent permission request.
- Previously granted permission permits later preparations without reopening the sidepanel.
- The sidepanel is not required to remain open during preparation.
- External messages never include raw candidate payloads or browser-local IDs.

### Tests

- Trusted/untrusted origin, valid/expired binding, valid/wrong user, permission present/missing/denied/granted, replay, and sidepanel-closed tests.

---

## AA-215 — Implement local tab registry and preparation orchestrator

**Branch:** `aa/aa-215-tab-orchestrator`  
**Dependencies:** AA-212, AA-213, and AA-214  
**Parallel:** No

### Objective

Own inactive preparation tabs and coordinate one preparation at a time.

### Scope

- Add extension-local records in `chrome.storage.session`.
- Create ATS tab with `active: false`.
- Wait through `tabs.onUpdated` and a content-script ready handshake.
- Track session-to-tab mapping locally.
- Dispatch the immutable package to the content runtime.
- Report sanitized progress to the backend.
- Activate the exact tab on review command.
- Detect close, discard, navigation mismatch, auth loss, and cancellation.
- Queue at most one active preparation.

### Non-goals

- No automatic retry after browser restart/update.
- No backend browser-local IDs.
- No arbitrary long sleeps.

### Acceptance criteria

- Service-worker suspension does not lose the mapping while `storage.session` remains available.
- Browser restart/update results in an explicit retry-required state.
- Review activates only the tab owned by the correct preparation session.
- URL/origin mismatch fails closed.

### Tests

- Storage, service-worker restart, inactive creation, readiness, wrong-tab protection, activation, cancellation, discard, close, and queue tests.

---

## AA-216 — Implement declarative action executor and submit safety

**Branch:** `aa/aa-216-action-executor-safety`  
**Dependencies:** AA-204 and AA-210  
**Parallel:** Yes, with AA-211/AA-213

### Objective

Separate ATS inspection from DOM mutation and make final submission unreachable through the supported action protocol.

### Scope

- Define declarative actions for:
  - Fill text.
  - Select option.
  - Set date/date parts.
  - Set checkbox/radio.
  - Set rich text.
  - Add repeatable section.
  - Upload document.
  - Propose intermediate navigation.
- ATS adapters return action plans; they do not execute actions.
- The executor performs allowed field mutations.
- The navigation controller separately authorizes intermediate navigation.
- Intermediate `type="submit"` controls are dangerous by default but may be allowed only by an ATS-specific rule with current-step and expected-next-step evidence.
- Final `type="button"` controls are also blocked.
- Keep ordinary logic in the isolated content-script world.
- Keep the MAIN-world bridge minimal and limited to value-setting operations required by controlled components.
- Add static restrictions for direct click, submit APIs, synthetic navigation, and location mutation outside approved modules.

### Acceptance criteria

- Unknown action types fail closed.
- Adapters cannot request a final-submit action because none exists in the protocol.
- Ambiguous navigation produces `needs_attention`.
- The controller validates the post-navigation step.
- Direct forbidden APIs are rejected by lint/static checks where enforceable.
- Runtime tests detect attempts that bypass static rules.

### Tests

- Unit tests for every action and denial rule.
- Tests for intermediate `type="submit"` versus final controls.
- Tests instrumenting click, submit, `requestSubmit`, `form.submit`, Enter key, terminal navigation, fetch, and XHR.

---

## AA-217 — Implement production reconciliation engine

**Branch:** `aa/aa-217-reconciliation-engine`  
**Dependencies:** AA-202, AA-212, and AA-216  
**Parallel:** No

### Objective

Safely map approved package entries to repeatable ATS sections.

### Scope

- Convert the AA-202 algorithm into production code.
- Use candidate arrays/multimaps rather than overwriting identity maps.
- Normalize visible values.
- Produce `update`, `add`, `leave`, or `ambiguous` decisions.
- Use internal IDs only for Runr provenance.
- Use approved content hashes only for post-fill verification.

### Acceptance criteria

- No duplicate entries on rerun, reload, or remount.
- Same-employer promotions remain distinct.
- Ambiguity stops automation for the affected section.
- Unmatched ATS entries remain untouched.
- No automatic deletion or merge.

### Tests

- Port all AA-202 cases into permanent unit and Playwright tests.

---

## AA-218 — Implement reusable complex form controls

**Branch:** `aa/aa-218-complex-form-controls`  
**Dependencies:** AA-216  
**Parallel:** Yes, while AA-217 is developed

### Objective

Support the controls required for real candidate-history entry.

### Scope

- Native and controlled inputs.
- Standard selects and accessible comboboxes.
- Date fields, split month/year fields, and adapter-declared date pickers.
- Checkboxes/radios and current-employment toggles.
- Textareas and supported `contenteditable`/rich-text controls.
- Validation/error inspection.
- Closed shadow roots and unsupported widgets remain manual boundaries.

### Acceptance criteria

- Each supported control has a deterministic read, write, and verify operation.
- Value-setting triggers the events required by controlled frameworks.
- Failed verification becomes unresolved rather than falsely successful.
- The executor does not navigate or submit while filling.

### Tests

- Fixture tests for React/Vue-style controlled inputs, comboboxes, dates, rich text, validation, and unsupported controls.

---

# Phase D — Complete supported ATS adapters

## AA-219 — Complete Greenhouse preparation adapter

**Branch:** `aa/aa-219-greenhouse-complete`  
**Dependencies:** AA-215, AA-217, and AA-218  
**Parallel:** Yes, with AA-220

### Objective

Provide the complete approved Greenhouse workflow supported by the actual Greenhouse form structures discovered in AA-200/AA-204.

### Scope

- ATS detection.
- Field/section inspection.
- Declarative action planning.
- Personal fields.
- Supported experience/education structures or employer-defined equivalents.
- Dates, current status, descriptions, and bullets where present.
- Supported standard questions.
- Intermediate navigation where explicitly proven.
- Final-review detection.
- Unresolved/manual reporting.

### Acceptance criteria

- All repository-approved Greenhouse fixtures pass.
- Rerun creates no duplicates.
- Sensitive or ambiguous questions remain unresolved.
- The adapter never directly mutates DOM or navigates.
- Preparation stops before final submission.

### Tests

- Unit adapter-contract tests and Playwright full-form fixture tests.

---

## AA-220 — Complete Lever preparation adapter

**Branch:** `aa/aa-220-lever-complete`  
**Dependencies:** AA-215, AA-217, and AA-218  
**Parallel:** Yes, with AA-219

### Objective

Provide the complete approved Lever workflow supported by the actual Lever form structures discovered in AA-200/AA-204.

### Scope and safety

Same boundaries as AA-219, implemented only for confirmed Lever structures.

### Acceptance criteria

- All repository-approved Lever fixtures pass.
- Rerun creates no duplicates.
- Sensitive or ambiguous questions remain unresolved.
- The adapter never directly mutates DOM or navigates.
- Preparation stops before final submission.

### Tests

- Unit adapter-contract tests and Playwright full-form fixture tests.

---

## AA-221 — Automate and verify document uploads

**Branch:** `aa/aa-221-document-uploads`  
**Dependencies:** AA-212, AA-215, and AA-216  
**Parallel:** Yes, while AA-219/AA-220 run

### Objective

Upload the exact selected application documents and verify attachment.

### Scope

- Reuse one-time, session-bound, hash-verified grants.
- Map each package document to the correct supported upload field.
- Issue a fresh grant for every retry.
- Verify filename/type/attachment state after upload.
- Support multiple document fields when the adapter can identify their intent.
- Leave ambiguous upload destinations unresolved.

### Acceptance criteria

- Correct CV and cover letter are attached to their intended fields.
- Supporting documents are attached only when field intent is known.
- Expired or consumed grants are never reused.
- Hash mismatch and failed verification stop the upload and report a sanitized error.

### Tests

- Backend grant tests plus Playwright upload, multiple-file, expiry, retry, wrong-field, and verification tests.

---

## AA-222 — Implement explicit retry and recovery

**Branch:** `aa/aa-222-retry-recovery`  
**Dependencies:** AA-215, AA-217, and AA-221  
**Parallel:** No

### Objective

Recover safely without silent background reopening or duplicate entries.

### Scope

- Reload/remount: re-inspect and reconcile.
- Closed/discarded tab: mark interrupted.
- Browser restart or extension update: mark retry required.
- Explicit user retry:
  - Revalidate extension authentication.
  - Revalidate package availability/immutability.
  - Revalidate ATS host permission and session.
  - Create a new inactive tab.
  - Reconcile and refill.
  - Issue fresh document grants.
- Enforce bounded attempts selected in AA-204.

### Acceptance criteria

- No employer tab opens automatically on Chrome startup.
- Retry requires explicit user action.
- Retry never duplicates repeatable entries.
- An expired/unavailable package requires a new package instead of unsafe reuse.
- Login/CAPTCHA/MFA becomes `needs_attention`.

### Tests

- Reload, remount, close, discard, browser-state loss, expired auth, expired package, permission revoked, fresh grant, and maximum-attempt tests.

---

# Phase E — User experience

## AA-223 — Add extension preparation and review UI

**Branch:** `aa/aa-223-extension-review-ui`  
**Dependencies:** AA-215, AA-219, AA-220, and AA-221  
**Parallel:** Yes, with AA-224

### Objective

Give the user clear preparation, permission, attention, and review controls.

### Scope

- Show:
  - Permission required.
  - Queued/preparing.
  - Ready for review.
  - Needs attention with reasons.
  - Interrupted/retry required.
  - Expired/cancelled.
- Provide explicit grant, retry, cancel, and review actions.
- Show filled/unresolved counts without exposing unnecessary personal data.
- Do not show or implement an automatic submit control.

### Acceptance criteria

- Every backend/local state has a defined UI.
- Permission denial has a clear recovery path.
- Review activates the correct prepared tab.
- Sensitive/ambiguous fields are clearly distinguished from technical failures.

### Tests

- Component/state tests and extension integration tests with mocked service-worker responses.

---

## AA-224 — Add Runr web preparation status

**Branch:** `aa/aa-224-web-preparation-status`  
**Dependencies:** AA-213 and AA-214  
**Parallel:** Yes, with AA-223

### Objective

Let users start preparation and see durable status from Tracker/Review Queue without depending on an open sidepanel.

### Scope

- Start preparation from the existing reviewed package flow.
- Send the validated external command.
- Handle `permission_required`.
- Read durable status from the backend.
- Provide **Review filled application**, cancel, and explicit retry actions.
- Never display `submitted` without explicit user confirmation.

### Acceptance criteria

- The user does not need to keep the sidepanel open.
- Previously granted host permission enables a one-click preparation start.
- Missing permission gives exact extension instructions.
- Review command contains only preparation identity, not tab ID.

### Tests

- Component, API integration, extension-present/missing, permission-required, ready, retry, expiry, and explicit-submission-confirmation tests.

---

# Phase F — Release gates

## AA-225 — Run full integration and safety suite

**Branch:** `aa/aa-225-integration-safety-suite`  
**Dependencies:** AA-219, AA-220, AA-221, AA-222, AA-223, and AA-224  
**Parallel:** No  
**Gate:** Must pass before pilot

### Objective

Prove the complete workflow and safety invariants.

### Scope

- End-to-end fixture workflows for Greenhouse and Lever.
- Inactive start through review activation.
- Job-specific bullet provenance.
- Repeatable entries.
- Complex controls.
- Documents.
- Permission flow.
- Service-worker suspension.
- Reload/close/retry.
- Sensitive questions.
- Submission-path instrumentation.

### Acceptance criteria

- All supported fixture fields are correct or explicitly unresolved.
- Zero duplicate experience/education entries.
- Zero final submission events across all tests.
- Zero raw personal values in telemetry.
- Forged/replayed external commands fail.
- The full suite runs reliably in CI.

### Tests

- This ticket consolidates and runs the tests created in previous tickets; it must not postpone feature-level testing until this stage.

---

## AA-226 — Controlled Greenhouse/Lever production pilot

**Branch:** `aa/aa-226-greenhouse-lever-pilot`  
**Dependencies:** AA-225  
**Parallel:** No  
**Gate:** Required before merging the integration branch into deployment

### Objective

Validate the release against controlled live forms without submitting applications.

### Pilot criteria

- Test at least 10 forms total, with at least 4 from each ATS and variation in custom questions/uploads.
- Record field-level results without storing candidate values.
- At least 95% of supported fields must be filled correctly.
- 100% of unsupported, sensitive, or ambiguous fields must be surfaced rather than silently guessed.
- Zero duplicate repeatable entries.
- Zero final submissions or terminal network actions.
- Document upload must succeed and verify on every form where a supported upload field is present.
- Measure preparation time; do not impose an arbitrary 60-second pass/fail threshold until data exists.
- Every failure receives a reproducible sanitized fixture or test before its fix is merged.

### Completion

- Publish the pilot report.
- Fix release-blocking defects through separate bug branches.
- Rerun AA-225 after fixes.
- Open the final PR from `feature/assisted-apply-background-prep` to `deployment/render-turso-r2`.

---

# Phase G — Workday expansion

Do not start these branches until AA-225 passes. AA-203 may reveal amendments.

## AA-230 — Build sanitized Workday fixture and adapter contract

**Branch:** `aa/aa-230-workday-fixture-contract`  
**Dependencies:** AA-203 and AA-225  
**Parallel:** No

### Objective

Convert Workday discovery evidence into reproducible tests and a bounded adapter contract.

### Acceptance criteria

- Fixtures cover repeatable experience/education, dates, long descriptions, uploads, intermediate steps, and final-review boundary.
- Authentication/CAPTCHA/MFA remain explicit manual boundaries.
- Required shared-engine changes are identified before adapter work.

---

## AA-231 — Implement Workday adapter

**Branch:** `aa/aa-231-workday-adapter`  
**Dependencies:** AA-230  
**Parallel:** No

### Objective

Implement Workday using the existing declarative adapter and centralized executor.

### Acceptance criteria

- Supported Workday fixtures fill personal data, multiple experiences, dates, approved bullets, education, and documents.
- Ambiguous or unsupported controls stop for review.
- No Workday-specific code bypasses the shared executor or navigation controller.
- Zero final submissions.

### Tests

- Adapter contract, full Playwright fixtures, idempotency, recovery, and submission-safety tests.

---

## AA-232 — Controlled Workday pilot

**Branch:** `aa/aa-232-workday-pilot`  
**Dependencies:** AA-231  
**Parallel:** No

### Objective

Validate the actual repeated-experience user value on controlled Workday applications without submitting.

### Pilot criteria

- At least 8 varied Workday application flows.
- Multiple experiences and education successfully reconciled where the form supports them.
- At least 95% of supported fields correct.
- Zero duplicates.
- Zero final submissions.
- Every failure becomes a sanitized regression fixture.

---

# Dependency graph

```text
AA-200 Architecture baseline
  -> AA-201 Background-tab spike
       -> AA-202 Reconciliation spike
       -> AA-203 Workday discovery

AA-202 + AA-203
  -> AA-204 Freeze architecture

AA-204
  -> AA-210 Preparation protocol
  -> AA-211 Tailored provenance
  -> AA-216 Declarative executor/safety

AA-210 + AA-211
  -> AA-212 Application package v2

AA-204 + AA-210
  -> AA-213 Preparation backend

AA-210 + AA-213
  -> AA-214 External command/permissions

AA-212 + AA-213 + AA-214
  -> AA-215 Tab orchestrator

AA-202 + AA-212 + AA-216
  -> AA-217 Reconciliation engine

AA-216
  -> AA-218 Complex controls

AA-215 + AA-217 + AA-218
  -> AA-219 Greenhouse
  -> AA-220 Lever

AA-212 + AA-215 + AA-216
  -> AA-221 Document uploads

AA-215 + AA-217 + AA-221
  -> AA-222 Retry/recovery

AA-215 + AA-219 + AA-220 + AA-221
  -> AA-223 Extension UI

AA-213 + AA-214
  -> AA-224 Web UI

AA-219 + AA-220 + AA-221 + AA-222 + AA-223 + AA-224
  -> AA-225 Integration/safety gate
       -> AA-226 Greenhouse/Lever pilot

AA-203 + AA-225
  -> AA-230 Workday fixture/contract
       -> AA-231 Workday adapter
            -> AA-232 Workday pilot
```

---

# Recommended Kanban execution batches

## Batch 1

- AA-200 only

## Batch 2

- AA-201 only

## Batch 3 — parallel

- AA-202
- AA-203

## Batch 4

- AA-204 only

## Batch 5 — parallel

- AA-210
- AA-211
- AA-216
- AA-213 may begin after AA-210 is merged

## Batch 6

- AA-212
- AA-214 after AA-213
- AA-218 may run while AA-212/AA-214 run

## Batch 7

- AA-215
- AA-217 after AA-212

## Batch 8 — parallel

- AA-219
- AA-220
- AA-221

## Batch 9

- AA-222

## Batch 10 — parallel

- AA-223
- AA-224

## Batch 11

- AA-225

## Batch 12

- AA-226

## Workday batches

- AA-230
- AA-231
- AA-232

---

# Deferred backlog

Do not create branches yet for:

- AI-assisted unknown-field matching.
- Generic employer-form automation.
- Concurrent preparation above one.
- Personio, SmartRecruiters, Ashby, iCIMS, SAP SuccessFactors, Taleo, Recruitee, or Teamtailor.
- Remote browser infrastructure.
- Automatic submission.

Create separate discovery tickets for these only after Greenhouse, Lever, and Workday pilot evidence establishes the reusable architecture.
