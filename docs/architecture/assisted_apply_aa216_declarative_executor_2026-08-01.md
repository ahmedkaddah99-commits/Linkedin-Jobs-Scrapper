# Assisted Apply AA-216 — declarative actions and guarded executor

Status: implemented on `deployment/render-turso-r2`; no final-submit capability exists.

## Boundary

`packages/ats-core/src/declarative-actions.ts` defines the closed action union:
`fill_text`, `select`, `set_date`, `set_checkbox`, `set_radio`,
`fill_rich_text`, `add_repeatable_section`, `upload_document`, and
`propose_intermediate_navigation`. Unknown action types and malformed fields
fail closed through `isDeclarativeAction`, `isDeclarativePlan`, and
`executeDeclarativeAction`. There is deliberately no final-submit action.

`StandardFactsAdapter.plan` converts an approved native match to a declarative
native action. The existing `fill` compatibility method now delegates the DOM
mutation to `executeNativeValueAction`; adapter matching and inspection do not
perform clicks or navigation. The controlled MAIN-world bridge remains limited
to value setting in `packages/ats-core/src/page-bridge.ts`.

## Navigation and submission policy

`propose_intermediate_navigation` is proposal data only. `authorizeIntermediateNavigation`
requires matching current step, selector, from/to transition, and a present
control. Button/link proposals are denied; submit controls are only eligible
when the independently supplied evidence matches. The executor still returns
`needs_attention` until post-transition verification is completed, so filling
itself never navigates. No final submit action is representable.

`packages/ats-core/src/submission-guard.ts` installs runtime capture for
terminal clicks, submit events, Enter on native inputs, form `requestSubmit`,
form `submit`, fetch, XHR, and navigation signals. Terminal click/submit/Enter
events are prevented and recorded. The guard is installed by
`apps/browser-extension/entrypoints/application-form.ts`.

## Static enforcement

`apps/browser-extension/scripts/verify-assisted-apply-boundary.mjs` scans ATS
source outside the explicitly approved bridge/guard/action modules for direct
clicks, submit APIs, navigation assignments, keyboard navigation, and dispatched
navigation events. It is exposed as
`npm run verify:assisted-apply-boundary`.

## Evidence

`apps/browser-extension/tests/unit/aa216-declarative-actions.test.ts` covers
all native action kinds, rich text, repeatable/upload review boundaries,
unknown actions, final/button denial, intermediate evidence ambiguity,
post-transition `needs_attention`, and runtime instrumentation for click,
submit, requestSubmit, form.submit, Enter, fetch, and XHR. Existing
`apps/browser-extension/tests/unit/ats-core.test.ts` continues to verify
native events, readback, iframe controls, preservation, and submission count.

Limitations: no live ATS navigation was executed; the controller deliberately
stops before an intermediate transition because post-transition verification
is not implemented in this bounded ticket. No production submit path is added.
