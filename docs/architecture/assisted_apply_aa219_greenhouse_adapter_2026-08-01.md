# Assisted Apply AA-219 — Greenhouse adapter boundary

Status: implemented on `deployment/render-turso-r2`.

## Repository-confirmed scope

`packages/ats-core/src/index.ts` (`detectAtsFromUrl`, `GreenhouseAdapter`,
`inspectionTargets`, `standardCandidateMatch`) confirms Greenhouse detection,
inspection of native text/email/tel/textarea/select/date/checkbox/radio/file
controls, semantic standard-fact matching, upload-field intents, and manual
classification for final submission, CAPTCHA, signatures, legal declarations,
legal terms, assessments, inaccessible frames, closed shadow roots, and custom
controls.

`planGreenhouseApplication` produces only shared declarative value actions by
calling the adapter’s inspection/match/plan contract. It does not mutate the
DOM, click, navigate, upload, invent answers, or overwrite values. Execution
remains in the shared declarative/native executor and document-upload contract.

## Explicit boundaries

Repository-confirmed: `apps/browser-extension/tests/fixtures/greenhouse-application.html`
contains no experience/education repeater or proven intermediate navigation
control. The planner therefore reports those structures unresolved/manual and
does not emit `add_repeatable_section` or navigation actions. Existing
reconciliation coverage remains in `reconciliation-application.html`; it is
not presented as a Greenhouse DOM capability.

Repository-confirmed: the fixture’s submit control is classified as
`final_submission`; plans stop at review and contain no terminal action.
Existing submission instrumentation and Playwright tests cover submit events,
terminal clicks, requestSubmit, form.submit, Enter, terminal requests, success,
and final navigation.

Proposed/future: Greenhouse repeaters, intermediate steps, ATS-specific rich
text widgets, and adapter-declared date pickers require a sanitized fixture
before support can be added. They remain manual boundaries in AA-219.

## Evidence

- Unit contract: `apps/browser-extension/tests/unit/aa219-greenhouse-adapter.test.ts`.
- Existing full fixture execution: `apps/browser-extension/tests/e2e/assisted-apply.spec.ts`.
- Shared action boundary: `packages/ats-core/src/declarative-actions.ts`.
- Shared reconciliation boundary: `packages/ats-core/src/reconciliation-spike.ts`.
- Shared document boundary: `packages/ats-core/src/index.ts` (`uploadApplicationDocument`).
