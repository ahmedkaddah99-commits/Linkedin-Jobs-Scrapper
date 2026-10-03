# Assisted Apply AA-217 — production reconciliation

Status: implemented on `deployment/render-turso-r2`; ATS-specific adapters remain unchanged for AA-219/AA-220.

## Repository-confirmed design

`packages/ats-core/src/reconciliation.ts` is the stable production facade;
`reconciliation-spike.ts` remains the compatibility implementation/export for
the AA-202 callers. `reconcileVisibleEntries` indexes visible entries in
kind/employer multimaps, normalizes visible ATS text with
`normalizeReconciliationText`, and evaluates dates, current state, location,
content overlap, and approved content hashes.

Decisions are now `update`, `add`, `leave`, and `ambiguous`. Candidate scoring
is deterministic: higher score wins, then `atsEntryId` is the stable tie order;
equal top scores stop only that candidate as `ambiguous`. A content-hash
mismatch also stops that candidate for review rather than treating the hash as
an ATS DOM identity or creating a duplicate.

`sourceId` and `candidateId` are provenance/audit identifiers only. Matching
uses visible normalized ATS values. `contentHash` verifies approved content
after a visible fill; it never identifies a section. Unmatched ATS entries are
copied into every result and are never deleted or merged.

## Idempotence and remount behavior

The permanent unit coverage in
`apps/browser-extension/tests/unit/aa202-reconciliation.test.ts` covers
normalization, update/add/leave, same-employer promotions, overlapping roles,
ambiguity, candidate collisions, unmatched preservation, rerun idempotence,
content-hash verification, and audit output. The Playwright fixture coverage in
`apps/browser-extension/tests/e2e/aa202-reconciliation.spec.ts` covers add,
update, rerun, reload, SPA remount, promotions, overlapping roles, and
ambiguous no-mutation behavior using sanitized visible entries.

Audit fields contain score, matched field names, and bounded reason only; they
do not add raw personal telemetry. Application values remain in the local
reconciliation plan only where required to perform the approved update/add.

## Explicit boundary

This ticket changes shared reconciliation policy only. It does not add DOM
section locators, ATS-specific controls, navigation, uploads, submission, or
adapter behavior. Those remain outside this module and reserved for later
tickets.
