# AA-210 versioned preparation protocol

Status: repository-grounded contract only; no transport, UI, orchestration,
backend schema, or ATS behavior is implemented here.

## Contract

`packages/extension-messages/src/index.ts` defines protocol
`runr.assisted_apply.preparation` at version `1`. Every message contains only
the version, source (`web` or `extension`), opaque `messageId`,
`preparationId`, `packageId`, and ISO `emittedAt`, plus the bounded fields for
its message type.

The supported lifecycle messages are:

- web → extension: `start`, `review_activate`, `cancel`, `retry`;
- extension → web: `permission_required`, `accepted`, `rejected`, `progress`,
  `needs_attention`, `ready_for_review`.

Capabilities are restricted to Greenhouse/Lever adapters and the bounded
features `fill`, `document_attachment`, and `reconciliation`. Results contain
only enumerated statuses/codes, bounded progress counts, and an opaque review
ID. Candidate records, browser tab/window IDs, DOM data, document bytes,
credentials, and tokens are not protocol fields.

## Runtime safety behavior

`isAssistedApplyPreparationMessage` performs strict version-1 structural
validation. Unknown fields, unknown message types, malformed capabilities,
invalid identifiers, invalid dates, and future protocol versions fail closed.

`AssistedApplyPreparationValidator` additionally requires the expected
preparation/package association, rejects messages older than the five-minute
protocol freshness window (or the caller's smaller explicit window), rejects
future timestamps beyond the small clock-skew allowance, rejects replayed
message IDs, and enforces lifecycle order. Retry must reference the immediately
preceding rejected/needs-attention message; review activation must reference
the emitted ready-for-review ID.

Version behavior is exact: version 1 is accepted; unknown or future versions
are rejected. A future protocol must be introduced as a separately reviewed
version rather than being accepted by a permissive fallback.

## Compatibility boundary

The existing `RunrWebLaunchRequest` and `isRunrWebLaunchRequest` binding
contract remain unchanged. AA-210 adds no transport handler and does not
replace package binding, connection authentication, panel requests, content
requests, or existing package payload validation.

## Evidence

`apps/browser-extension/tests/unit/messages.test.ts` covers valid lifecycle
messages, explicit retry, strict unknown-field rejection, malformed and
duplicate capabilities, browser-local ID/candidate rejection, forged
associations, stale messages, replay, future versions, and compatibility with
the existing web package-binding validator.
