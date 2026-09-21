---
name: runr-ticket-merge-predeployment
description: Use when explicitly promoting one Runr issue from implementation review to the permanent predeployment branch for live production-like testing.
---

# Runr ticket merge predeployment

This skill is explicit-only and operates on one issue or sub-issue. It integrates a reviewed ticket into the permanent predeployment branch, temporarily points the Runr Render services at that branch, and records live verification. A live-pending integration may administratively close the native Linear workflow state while retaining the custom `Predeployment Integrated` label; it never production-closes the issue or deletes its branch/worktree.

## Mandatory controller approval

Require a matching unexpired local approval bound to this action, target issue, current issue/scope/test fingerprints, and tested commit SHA. Any change invalidates it. Integration is serialized through the controller; never merge concurrently into the shared integration branch.

## Deterministic Issue Status label

The authoritative lifecycle marker is exactly one child label of the Issue Status group, using the registry in docs/tickets/TEMPLATE.md. For every transition in this skill:

1. Resolve the exact Linear issue and the target label by exact name and parent group.
2. If the target child is missing, create it under Issue Status with linear_save_issue_label as part of this skill. If an exact unarchived child already exists, reuse it and never create a duplicate.
3. Call linear_save_issue with addLabels containing the target label ID and removeLabels containing every other Issue Status child ID. Preserve unrelated labels.
4. Set the native Linear workflow state only when the exact state exists natively. For custom lifecycle names, apply the exact label and leave the native state unchanged; the sole exception is a successfully integrated, live-pending `Predeployment Integrated` outcome, which sets native Linear `Done` as an administrative implementation closure. Do not stop or substitute another label.
5. Re-read the exact issue and verify that exactly one Issue Status label is assigned and it is the target label before reporting the transition.

The label assignment is mandatory even when the native status update succeeds.
## Required state and invariants

The issue must have the `In Review` Issue Status label for initial integration, or `Predeployment Integrated` for a live-verification retry after its exact integration revision is already on permanent predeployment. Keep the applicable label while this skill runs. Set the native state to In Review when available. Confirm the exact issue, branch, worktree, latest attempt attachment, parent, dependencies, and allowed paths before changing anything.

If the issue branch/worktree or a successful implementation attempt cannot be identified, do not guess. Assign the Missing Requirement label or another appropriate blocked label and stop. Do not merge a failed attempt.

## Integration

1. Use a dedicated integration worktree, never the shared checkout. The permanent predeployment branch is `predeployment/render-turso-r2`. For a `Predeployment Integrated` retry, verify the recorded `integration_revision` is already on that branch and do not merge the ticket a second time.
2. Fetch the remote deployment and predeployment branches and verify their revisions.
3. Confirm the ticket branch contains the commit recorded by the latest successful attempt and has no uncommitted scoped work.
4. Re-check dependency order, execution label, path overlap, migrations, shared resources, and deployment configuration.
5. Merge the ticket branch into the permanent predeployment branch through the repository's normal protected-branch/PR flow. Preserve the ticket branch, remote branch, and issue worktree after the merge.
6. Verify the resulting predeployment revision and collect the commit/PR link.

Before assigning `Predeployment Integrated`, verify the tested implementation commit is an ancestor of the permanent predeployment revision, or prove an equivalent integrated tree when the protected flow creates a squash commit. Verify at least the ticket's changed files against that tree. An attempt-log commit or batch merge comment alone is insufficient. If this check fails, assign `Integration Fix Required` and keep the ticket branch/worktree.

Do not silently resolve conflicts by dropping ticket changes or overwriting another issue. A conflict or defective change is an integration failure, not an implementation success.

## Render predeployment verification

For any ticket requiring VPS acceptance, also follow `docs/reverse-engineering/02-deployment/vps-predeployment-verification.md`. Render branch switching does not change `/opt/runr`. Pin the exact integrated predeployment SHA on the VPS during a serialized maintenance window, prove the live systemd entrypoint and receipt, and verify rollback. If the VPS check is pending, keep `Predeployment Integrated` with the exact integration revision and explicit live-pending evidence. Never assign `Ready for Production` from Render checks alone for such a ticket.

As part of this explicitly invoked skill, point the Runr frontend, API, and worker Render services to the permanent predeployment branch and retain the deployment-branch binding as the rollback target. Wait for the Render deploy to finish, then verify the application health and the ticket's acceptance path using the approved production-like checks. Record deployment IDs, revision, URLs, timestamps, and check results in the issue evidence.

Do not switch branches, trigger a deploy, or change service configuration outside this skill. If the code integration and required local/combined checks are complete but Render infrastructure is temporarily unavailable, assign the `Predeployment Integrated` Issue Status label, record the exact `integration_revision`, and attach the live-verification failure evidence for retry. This state unblocks implementation dependencies that consume the integrated revision, but it never unblocks release or deployment dependencies. If the change itself is defective, assign the Integration Fix Required label. For a missing dependency or external prerequisite, assign the appropriate Waiting for Predecessor, Missing Requirement, or External Blocked label.

The dependency contract must distinguish `implementation` dependencies from `release` dependencies. An implementation dependency is satisfied by this ticket's exact integrated predeployment revision; implementation-dependent tickets may consume that revision. A release dependency remains unsatisfied until this ticket reaches `Ready for Production`.

## Successful handoff

After the predeployment branch contains the ticket and local/combined checks pass:

- attach the integration and Render evidence;
- record the exact `integration_revision`;
- assign `Ready for Production` only when live checks pass; otherwise assign `Predeployment Integrated` when live verification is pending;
- when assigning `Predeployment Integrated` for a live-pending outcome, set the native Linear workflow state to `Done` as an administrative implementation closure and preserve the custom label;
- leave the ticket branch, remote branch, and worktree intact;
- leave the Render services bound to predeployment for testing.

When live verification is pending after successful integration, set the native Linear workflow state to Done as an administrative implementation closure while preserving the custom `Predeployment Integrated` Issue Status label. This does not mean production deployment is complete; the grouped label remains authoritative and deployment still requires `Ready for Production`. A failed outcome must be explicit in Linear and in the evidence attachment.

## Clean handoff

The dedicated integration worktree must be clean. Do not clean the issue worktree here; it is intentionally preserved for deployment or discard. Never modify the user's shared checkout or remove unrelated branches.
