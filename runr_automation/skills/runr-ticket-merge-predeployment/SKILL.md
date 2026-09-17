---
name: runr-ticket-merge-predeployment
description: Use when explicitly promoting one Runr issue from implementation review to the permanent predeployment branch for live production-like testing.
---

# Runr ticket merge predeployment

This skill is explicit-only and operates on one issue or sub-issue. It integrates a reviewed ticket into the permanent predeployment branch, temporarily points the Runr Render services at that branch, and records live verification. It does not close the issue or delete its branch/worktree.

## Mandatory controller approval

Require a matching unexpired local approval bound to this action, target issue, current issue/scope/test fingerprints, and tested commit SHA. Any change invalidates it. Integration is serialized through the controller; never merge concurrently into the shared integration branch.

## Deterministic Issue Status label

The authoritative lifecycle marker is exactly one child label of the Issue Status group, using the registry in docs/tickets/TEMPLATE.md. For every transition in this skill:

1. Resolve the exact Linear issue and the target label by exact name and parent group.
2. If the target child is missing, create it under Issue Status with linear_save_issue_label as part of this skill. If an exact unarchived child already exists, reuse it and never create a duplicate.
3. Call linear_save_issue with addLabels containing the target label ID and removeLabels containing every other Issue Status child ID. Preserve unrelated labels.
4. Set the native Linear workflow state only when the exact state exists natively. For custom lifecycle names, apply the exact label and leave the native state unchanged; do not stop or substitute another label.
5. Re-read the exact issue and verify that exactly one Issue Status label is assigned and it is the target label before reporting the transition.

The label assignment is mandatory even when the native status update succeeds.
## Required state and invariants

The issue must have the In Review Issue Status label. Assign and keep that label while integration and predeployment verification run. Set the native state to In Review when available. Confirm the exact issue, branch, worktree, latest attempt attachment, parent, dependencies, and allowed paths before changing anything.

If the issue branch/worktree or a successful implementation attempt cannot be identified, do not guess. Assign the Missing Requirement label or another appropriate blocked label and stop. Do not merge a failed attempt.

## Integration

1. Use a dedicated integration worktree, never the shared checkout.
2. Fetch the remote deployment and predeployment branches and verify their revisions.
3. Confirm the ticket branch contains the commit recorded by the latest successful attempt and has no uncommitted scoped work.
4. Re-check dependency order, execution label, path overlap, migrations, shared resources, and deployment configuration.
5. Merge the ticket branch into the permanent predeployment branch through the repository's normal protected-branch/PR flow. Preserve the ticket branch, remote branch, and issue worktree after the merge.
6. Verify the resulting predeployment revision and collect the commit/PR link.

Do not silently resolve conflicts by dropping ticket changes or overwriting another issue. A conflict or defective change is an integration failure, not an implementation success.

## Render predeployment verification

As part of this explicitly invoked skill, point the Runr frontend, API, and worker Render services to the permanent predeployment branch and retain the deployment-branch binding as the rollback target. Wait for the Render deploy to finish, then verify the application health and the ticket's acceptance path using the approved production-like checks. Record deployment IDs, revision, URLs, timestamps, and check results in the issue evidence.

Do not switch branches, trigger a deploy, or change service configuration outside this skill. If Render infrastructure is temporarily unavailable but the code integration is complete, keep the In Review label and attach the failure evidence for retry. If the change itself is defective, assign the Integration Fix Required label. For a missing dependency or external prerequisite, assign the appropriate Waiting for Predecessor, Missing Requirement, or External Blocked label.

## Successful handoff

Only after the predeployment branch contains the ticket and live checks pass:

- attach the integration and Render evidence;
- assign the Ready for Production label;
- leave the ticket branch, remote branch, and worktree intact;
- leave the Render services bound to predeployment for testing.

This skill never sets Done. A failed or temporary-infrastructure outcome must be explicit in Linear and in the evidence attachment.

## Clean handoff

The dedicated integration worktree must be clean. Do not clean the issue worktree here; it is intentionally preserved for deployment or discard. Never modify the user's shared checkout or remove unrelated branches.
