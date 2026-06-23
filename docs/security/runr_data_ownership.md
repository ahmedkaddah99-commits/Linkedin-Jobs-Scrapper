# Runr Data Ownership

## Invariants

- Every workspace has exactly one `owner_user_id`.
- A non-admin user can access a workspace only when they own it or its ID is explicitly present in their `allowed_workspace_ids`.
- An empty `allowed_workspace_ids` list grants no workspace access.
- Every user-initiated or scheduled run has a `user_id`.
- A non-admin user can access a run only when the run's `user_id` matches their user ID and they can access its workspace.
- Jobs, tracker entries, reviews, artifacts, documents, referrals, and run actions inherit the run-access decision.
- Admin users retain global access for support and operations.

## Creation And Updates

- API-created workspaces receive the authenticated user's ID as `owner_user_id`.
- Workspace updates preserve the existing owner; ownership cannot be transferred through normal workspace payloads.
- Quick Apply workspaces are owned by the authenticated user.
- Scheduled runs execute as the workspace owner.

## Legacy Backfill

Migration `014_workspace_ownership` assigns an existing workspace owner using this order:

1. Existing persisted ownership metadata.
2. The single distinct non-empty `runs.user_id` associated with the workspace.
3. The sole user in the database when the workspace has no runs.

If ownership is ambiguous, the workspace remains unowned and inaccessible to non-admin users. This is intentionally fail-closed.

## Production Verification

After deployment:

1. Confirm migration `014_workspace_ownership` is applied.
2. Confirm every customer workspace has a non-empty owner.
3. Sign in as a second non-admin account.
4. Verify `/workspaces`, `/runs`, and `/tracker` return none of the first account's records.
5. Verify direct access to the first account's run, job, review, and artifact URLs returns `403`.
