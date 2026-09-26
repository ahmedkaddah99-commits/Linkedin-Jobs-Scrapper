# RC-020 — Customer slow-task queue

RC-020 moves the two remaining measured slow public operations behind the customer worker role:

- `POST /tracker/email-integration/sync`
- `POST /documents/bulk-export`

Both routes still validate/authenticate synchronously, persist a user-scoped task, and return `202` with a task ID and status URL when `RUNR_CUSTOMER_TASKS_ASYNC=true`. Development and test environments remain compatible with the previous inline responses unless the flag is explicitly enabled.

## Contract

Migration `058_customer_task_queue` creates `customer_tasks` with:

- user ownership and a unique `(user_id, idempotency_key)`;
- `queued`, `running`, `completed`, and `failed` states;
- bounded attempts, lease expiry, lease owner/token, and fenced completion;
- sanitized payload/result/error timestamps.

Only a `customer` worker can claim these tasks. Acquisition workers return before touching this queue. A stale lease is requeued until the bounded attempt limit, then becomes terminal failure. A late completion with the old owner/token/attempt cannot overwrite the current attempt.

The email task stores only scan options and never provider passwords or OAuth tokens. Worker execution reuses the existing token refresh, provider sync, tracker persistence, and reauthorization lifecycle. Bulk export reuses the existing per-user document authorization/export gate and writes through the existing bundle/download path.

## Client behavior

The frontend recognizes `202` task responses, polls the returned status URL with bounded exponential backoff, displays queued/running state, downloads only a completed bundle, and leaves a still-running task reloadable. Repeating a request while the task is pending returns the same task through the stable idempotency key.

## Rollout and rollback

Render web and customer-worker services set `RUNR_CUSTOMER_TASKS_ASYNC=true`. Rollback is reversible:

1. Set the flag to `false` on the web and worker services.
2. Restart those processes through the normal deployment controls.
3. Leave existing queued tasks for inspection/retry; do not delete task rows or generated bundles.
4. If required, drain queued tasks with a customer worker before removing the flag.

The old inline path remains available while the flag is disabled. The migration is additive; rolling back code without rolling back migration leaves `customer_tasks` unused and preserves its audit state.

## Limitations

- There is no customer-facing cancellation endpoint yet.
- One customer worker process currently provides the capacity boundary; separate CPU/RAM reservation and horizontal scaling remain a later worker-capacity ticket.
- Existing frontend polling is bounded to eight attempts. A task that outlives that window remains visible through its status URL but is not held in the browser.
- The existing local/R2 bundle storage and download authorization behavior were preserved; this ticket does not introduce a new artifact store.
