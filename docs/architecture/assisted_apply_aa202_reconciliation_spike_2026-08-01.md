# AA-202 reconciliation prototype

Status: bounded sanitized-fixture prototype; not a production reconciliation engine.

## Scope

**Repository-confirmed:** The prototype is isolated to `packages/ats-core/src/reconciliation-spike.ts`, its unit test `apps/browser-extension/tests/unit/aa202-reconciliation.test.ts`, and the local fixture/test path `apps/browser-extension/tests/fixtures/reconciliation-application.html`, `tests/fixture-server.mjs`, and `tests/e2e/aa202-reconciliation.spec.ts`.

It has no backend schema, production UI, adapter, dependency, deployment, or ATS submission changes. `sourceId` is retained only on candidate input as provenance metadata; matching uses only visible ATS fields.

## Deterministic matching contract

**Repository-confirmed:** `normalizeReconciliationText` applies NFKC normalization, lower-casing, ampersand expansion, punctuation removal, and whitespace folding.

**Repository-confirmed:** `reconcileVisibleEntries` builds a `Map` multimap keyed by `kind + normalized employerOrInstitution`. A candidate is plausible only when kind, employer/institution, and title/degree match visibly; dates, current state, location, and content add deterministic score. A single plausible match can produce `update` or `noop`; multiple plausible entries produce `review_required` with no mutation; no plausible entry produces `add`. Every unmatched ATS entry is copied into the result and is never deleted.

**Repository-confirmed:** Added entries receive a disposable local `aa202-added-*` identifier. This is not presented as an ATS DOM identifier or Runr provenance identity.

## Fixture matrix

**Repository-confirmed:** The sanitized fixture contains two employers, two roles at Acme & Co., overlapping Beta Labs dates, one prefilled experience, one ambiguous duplicate Beta Labs entry created by the test, and a University of Example education entry.

**Repository-confirmed:** `aa202-reconciliation.spec.ts` verifies:

- unique update, add, unmatched-entry preservation, and second-run idempotence;
- reload plus rerun idempotence;
- SPA remount plus rerun idempotence;
- distinct same-employer promotion and overlapping-role targets;
- education matching;
- ambiguity returns `review_required` and leaves entries unchanged.

## Evidence

- `npx vitest run tests/unit/aa202-reconciliation.test.ts` — 5 passed.
- `npm run test:unit` — 14 files, 142 tests passed.
- `npx playwright test tests/e2e/aa202-reconciliation.spec.ts --reporter=line` — 4 passed.
- `npm run test:e2e` — 18 passed, including AA-201 regression coverage and all AA-202 fixture tests.
- `npm run typecheck` — passed.

## Limitations and unresolved decisions

**Inferred limitation:** This proves deterministic behavior against controlled visible fixture data only. It does not prove live ATS DOM compatibility, provider-specific repeated-section semantics, cross-origin behavior, server-side reconciliation, or production lifecycle ownership.

**Unresolved:** Production matching thresholds, field-level conflict policy, section-specific DOM identity, and whether a future production engine should expose stable ATS entry IDs remain open. This spike intentionally does not choose those designs.
