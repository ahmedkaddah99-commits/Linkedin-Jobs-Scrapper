# Assisted Apply AA-218 — deterministic control executor

Status: implemented on `deployment/render-turso-r2`; AA-216 boundary preserved.

`packages/ats-core/src/declarative-actions.ts` now exposes deterministic
`readControlValue`, `writeControlValue`, `verifyControlValue`, and
`inspectControlValidation` primitives. Native input/textarea/select controls,
accessible comboboxes, native and split month/year dates, adapter-declared
date-picker presence, checkbox/radio/current-employment controls, and
supported contenteditable rich text are read and written through the central
executor. Writes use the element-realm property setter and emit bubbled,
composed `input` and `change` events, with focus/blur and readback validation.

Verification requires the expected value and valid browser/ARIA/error state.
Readback or validation failures return `unresolved` from the executor and are
never reported as successful. The existing adapter compatibility result maps
that boundary to a rejected field execution while preserving readback and
validation evidence.

Closed shadow roots, unsupported widgets, missing controls, terminal controls,
and unsupported file targets remain manual/unresolved boundaries. No generic
widget clicking, navigation, submission, ATS-specific flow, or AI matching was
added.

Tests: `apps/browser-extension/tests/unit/aa218-controlled-controls.test.ts`
covers controlled inputs, selects/comboboxes, dates/split dates/date pickers,
rich text, checkbox/radio, validation, controlled readback failure, and
unsupported boundaries. Existing AA-216 and ATS-core tests cover no-submit/no-
navigation behavior and framework event compatibility.
