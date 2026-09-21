---
name: runr-discard-issue
description: Use when explicitly discarding one or more Runr non-final issues and removing their dedicated Git branches and worktrees without touching the shared checkout.
---

# Runr discard issue

This skill is explicit-only and accepts one or more exact Linear issue IDs, URLs, or unambiguous issue details. It is the destructive cleanup path for abandoned issue work. It is not a merge, rollback, or generic repository cleanup.

## Mandatory discard approval

Require a matching unexpired discard approval before any deletion. Its action fingerprint must bind the exact issue IDs, verified absolute worktree paths, exact local/remote branch names, and current commit/scope state. Any mismatch invalidates approval and stops cleanup.

## Deterministic Issue Status label

The authoritative lifecycle marker is exactly one child label of the Issue Status group, using the registry in docs/tickets/TEMPLATE.md. For every transition in this skill:

1. Resolve the exact Linear issue and the target label by exact name and parent group.
2. If the target child is missing, create it under Issue Status with linear_save_issue_label as part of this skill. If an exact unarchived child already exists, reuse it and never create a duplicate.
3. Call linear_save_issue with addLabels containing the target label ID and removeLabels containing every other Issue Status child ID. Preserve unrelated labels.
4. Set the native Linear workflow state only when the exact state exists natively. For custom lifecycle names, apply the exact label and leave the native state unchanged; do not stop or substitute another label.
5. Re-read the exact issue and verify that exactly one Issue Status label is assigned and it is the target label before reporting the transition.

The label assignment is mandatory even when the native status update succeeds.
## Eligible state and resolution

The issue must have an appropriate non-final Issue Status label. Do not discard production-final work. Native Linear `Done` paired with the custom `Predeployment Integrated` label is an administrative implementation closure, not production completion; retain it for live verification and deployment handling. Resolve each exact issue and verify its dedicated branch, worktree, parent, and current label before deleting anything. A vague title, shared worktree, protected branch, deployment branch, or predeployment branch is never a safe target.

If the exact Git artifacts cannot be identified, do not delete anything and leave the issue state unchanged. If the issue is already merged or its changes are needed by another issue, stop and use a deliberate revert or dependency workflow instead.

## Destructive order

For each issue, and only after exact-target checks:

1. Do not edit the shared checkout.
2. Remove the dedicated issue worktree using its verified absolute path through `runr_automation/scripts/remove-worktree-safely.ps1 -RepositoryPath <shared-checkout> -WorktreePath <exact-issue-worktree>`. This detaches any `.venv` junction before Git removes the worktree. Never call `git worktree remove --force` or recursively delete a worktree containing a junction to the shared environment.
3. Delete the exact local ticket branch.
4. Delete the exact remote ticket branch if it still exists.
5. Remove an issue PR only when the connected tool explicitly supports that exact operation and the PR is unmerged; otherwise leave the PR and report it.
6. Verify no worktree, local branch, or remote branch for that issue remains.
7. Assign the Canceled label and set the native state to Canceled when available.

Use safe path validation and exact branch names. Never use a broad recursive delete, repository-wide clean, reset, or wildcard branch deletion. Do not create an attempt log for a discard; record only the cleanup result and chat link if the Linear connector supports comments.

## Failure and status

If every required Git cleanup and the Linear label update succeed, the result is Canceled. If cleanup cannot safely complete, leave the current Issue Status label unchanged and report the exact artifact that remains. A connector that cannot hard-delete a Linear issue does not justify pretending the issue is gone: assign Canceled and state that the Linear record remains. Never delete unrelated evidence or shared branch history.

The shared checkout must remain exactly as it was before the skill started.
