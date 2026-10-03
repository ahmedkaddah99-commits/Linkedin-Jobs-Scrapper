# AA-213 durable preparation status

Status: bounded, disabled-by-default backend foundation. It does not store
browser-local identity, raw DOM data, raw field values, document tokens, or
submission state.

## Frozen ownership and reference

Repository-confirmed: preparation creation loads the immutable
`ApplicationPackage` through `ApplicationPackageService._store.get` in
`backend/application/assisted_apply_preparation_service.py`, checks the owning
user, and copies only `package.job.url` and `package.job.portal`. The client
cannot supply or replace the application URL. This follows AA-204’s frozen
retry source: the persisted package `job.url`, originally selected from
`apply_link`, then `link`, then `source_url`.

## Durable model and migration

Repository-confirmed: `backend/domain/assisted_apply_preparation.py` defines
the durable state model, sanitized error categories, and transition functions.
`backend/repositories/sqlite_migrations.py`, migration
`027_assisted_apply_preparations`, adds preparation state plus a report
idempotency table. Stored fields are preparation/session/user/package/job IDs,
ATS, frozen application URL, state, aggregate counts, sanitized error category,
attempt count, and lifecycle timestamps. The migration stores no `tabId`,
`windowId`, DOM selector, document token, raw field value, or submitted flag.

`backend/repositories/assisted_apply_preparation.py` is the SQLite repository
boundary. Reports store only report ID, preparation ID, bounded report type,
fingerprint, and timestamp.

## State machine and lifecycle

Repository-confirmed transitions:

- `created` accepts permission-required, accepted, rejected, or attention
  reports.
- `permission_required` accepts accepted/rejected and idempotent repeated
  permission-required reports.
- `preparing` accepts progress, attention, or ready-for-review.
- `ready_for_review` accepts explicit web `activate` only; this means local
  preparation review activation and is not submission.
- Web `cancel` is allowed for nonterminal non-active states.
- `needs_attention` and `expired` accept explicit web `retry`; retry clears
  aggregate progress, increments `attempt_count`, and returns to `created`.
- Active, cancelled, and expired states reject unsupported reports/actions.

Preparation expiry is aligned with the existing authenticated Assisted Apply
session TTL (`ASSISTED_APPLY_SESSION_TTL_SECONDS`, eight hours). Reads and
reports lazily transition an unfinished record to `expired` once `expires_at`
is reached. Retry sets a new expiry and requires a fresh report sequence. This
does not change the AA-204 package binding TTL or introduce a bound-package
expiry.

## Authentication, authorization, and API

Repository-confirmed: web routes are registered in
`backend/api/routes/assisted_apply_preparations.py` for authenticated create,
read, and actions. The extension report route authenticates the existing
extension session and exact client origin before binding the first report to
the authenticated connection request ID. Later reports must use that same
session ID. Package and preparation reads/actions require the owning Clerk
user.

The feature flag `RUNR_ENABLE_ASSISTED_APPLY_PREPARATION` defaults to `0` in
`backend/config/env_schema.py`; migration deployment is therefore additive
while routes return a disabled response until explicitly enabled.

Replay behavior is deterministic: a previously seen message ID with the same
sanitized fingerprint returns the current state without another transition. A
message ID reused with different content fails closed. Invalid transitions,
cross-user access, expired reports, malformed counts, unknown result fields,
and unsupported error categories fail closed.

Existing explicit outcome confirmation remains the only submission-related
logic. AA-213 introduces no submitted state and does not call ATS behavior.

## Tests

`tests/test_aa213_preparation.py` covers additive migration fields and
forbidden-data absence, transition validation, cross-user authorization,
session binding, replay/idempotency, expiry/retry, disabled-by-default service
behavior, frozen URL recovery, and web/extension route registration and
sanitized payload rejection.
