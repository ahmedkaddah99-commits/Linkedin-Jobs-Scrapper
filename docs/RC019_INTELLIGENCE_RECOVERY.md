# RC-019 intelligence recovery

Target branch: `deployment/render-turso-r2`

The customer intelligence queue now has a durable lease contract. A claim
records `lease_owner`, a random `lease_token`, `lease_expires_at`, the
incremented `attempt_count`, and `max_attempts`. SQLite's write transaction
and conditional state/attempt update prevent two workers from owning one
attempt. Completion requires the owner, token, and attempt; stale completion
is reported without changing the cache or queue.

Expired processing claims are recovered before the next customer claim. They
return to `queued` while attempts remain, or become a truthful terminal
`failed` result with `lease_expired_max_attempts`. Re-enqueueing a currently
processing key preserves its claim; re-enqueueing a failed key clears the old
payload and starts a new bounded attempt. Available completed keys remain
immutable.

Every key includes the canonical job version, profile version, CV version,
evidence version, evaluator version, input hash, and intelligence kind. A
worker compares those fields with current published/profile inputs before
generating. A changed input fails the old claim and enqueues the current key;
old output cannot be written as the current version.

The read-only personalized Jobs detail path still does not enqueue work. The
explicit authenticated `POST /personalized-jobs/{posting_id}/precompute`
action queues the bounded description plus two match evaluator candidates.
Tailored documents remain an explicit Pro action. There is no users × full
catalog fan-out.

Migration `057_phase_e_intelligence_recovery` adds the lease columns and
index. Rollback is code/configuration rollback only after draining or
pausing customer intelligence workers; do not restore an old database over
newer queue writes. Existing queued rows receive the default three-attempt
bound and empty lease fields during migration.
