# Assisted Apply AA-220 — Lever adapter boundary

Status: implemented on `deployment/render-turso-r2`.

## Repository-confirmed scope

`packages/ats-core/src/index.ts` (`detectAtsFromUrl`, `LeverAdapter`,
`inspectionTargets`, `standardCandidateMatch`) confirms Lever detection,
inspection of native text/email/tel/textarea/select/date/checkbox/radio/file
controls, semantic standard-fact matching, upload-field intents, and manual
classification for final submission, CAPTCHA, signatures, legal declarations,
legal terms, assessments, inaccessible frames, closed shadow roots, and custom
controls.

`planLeverApplication` inspects, matches, and proposes shared declarative value
actions only. It does not mutate the DOM, click, navigate, upload, invent
answers, or overwrite nonempty values. Execution remains behind the shared
declarative/native executor and document-upload contract.

## Explicit boundaries

Repository-confirmed: `apps/browser-extension/tests/fixtures/lever-application.html`
contains no experience/education repeater or proven intermediate-navigation
control. The planner reports those structures unresolved/manual and emits no
repeatable-section or navigation action. The separate reconciliation fixture
is not presented as a Lever DOM capability.

Repository-confirmed: the fixture submit control is classified as
`final_submission`; preparation stops at review and no terminal action is
possible. Existing fixture instrumentation covers submit events, terminal
clicks, requestSubmit, form.submit, Enter, terminal requests, success, and
final navigation.

Proposed/future: Lever repeaters, intermediate steps, ATS-specific rich-text
widgets, and adapter-declared date pickers require sanitized fixture evidence
before support can be added. They remain manual boundaries in AA-220.

## Evidence

- Unit contract: `apps/browser-extension/tests/unit/aa220-lever-adapter.test.ts`.
- Full fixture execution: `apps/browser-extension/tests/e2e/assisted-apply.spec.ts`.
- Shared action boundary: `packages/ats-core/src/declarative-actions.ts`.
- Shared reconciliation boundary: `packages/ats-core/src/reconciliation-spike.ts`.
- Shared document boundary: `packages/ats-core/src/index.ts` (`uploadApplicationDocument`).
