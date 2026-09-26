---
name: runr-ticket-merge-deployment
description: Use when explicitly promoting one Runr issue from predeployment approval to the protected deployment branch and finalizing its Linear lifecycle.
---

# Runr ticket merge deployment

This skill is explicit-only and operates on one issue or sub-issue. It promotes a ticket already tested on predeployment to the deployment branch, restores Render to deployment, cleans the ticket Git artifacts, and closes the Linear issue.

## Mandatory release approval

Require a matching unexpired release approval bound to the target, tested commit SHA, current issue/scope fingerprints, and predeployment test result. Any material change invalidates approval. Deployment and later cleanup remain serialized controller actions.

## Deterministic Issue Status label

The authoritative lifecycle marker is exactly one child label of the Issue Status group, using the registry in docs/tickets/TEMPLATE.md. For every transition in this skill:

1. Resolve the exact Linear issue and the target label by exact name and parent group.
2. If the target child is missing, create it under Issue Status with linear_save_issue_label as part of this skill. If an exact unarchived child already exists, reuse it and never create a duplicate.
3. Call linear_save_issue with addLabels containing the target label ID and removeLabels containing every other Issue Status child ID. Preserve unrelated labels.
4. Set the native Linear workflow state only when the exact state exists natively. For custom lifecycle names, apply the exact label and leave the native state unchanged; do not stop or substitute another label.
5. Re-read the exact issue and verify that exactly one Issue Status label is assigned and it is the target label before reporting the transition.

The label assignment is mandatory even when the native status update succeeds.
## Required state

For a VPS acceptance ticket, require the sanitized exact-revision host receipt and verified rollback specified in `docs/reverse-engineering/02-deployment/vps-predeployment-verification.md` before promotion. `Ready for Production` without that evidence is stale and must be corrected before deployment.

The issue must have the Ready for Production Issue Status label. Keep that label while deployment integration and verification run. Resolve the exact issue, tested revision, PR, branch, worktree, parent, dependencies, and latest predeployment evidence. `Predeployment Integrated` proves code availability only and is not deployable; never deploy an issue that is merely In Review or Predeployment Integrated.

If evidence, branch identity, or the tested revision is missing, stop without deleting anything and assign the Missing Requirement label or another appropriate blocked label.

## Promote safely

1. Work from a dedicated deployment integration worktree, never the shared checkout.
2. Fetch and verify the tested predeployment and protected deployment revisions.
3. Confirm the exact tested ticket changes are the changes being promoted; do not rebuild from an unreviewed branch tip.
4. Merge through the protected branch/PR flow. Do not drop conflicts or rewrite deployment history.
5. Verify the remote deployment revision and the application checks required by the ticket.
6. Point the Runr frontend, API, and worker Render services back to the deployment branch, wait for deployment, and verify health and the relevant smoke checks.
7. Attach the PR, deployment revision, Render deployment IDs, timestamps, and verification results.

Keep the Ready for Production label while these steps run. If the change itself is defective, assign Integration Fix Required and preserve all artifacts needed to repair it. If a temporary infrastructure failure prevents verification, leave the Ready for Production label with evidence; do not falsely assign Done. For another blocker, use the appropriate blocked label.

## Final cleanup and status

Only after the deployment branch and Render checks succeed:

- remove the issue worktree after verifying its exact absolute path;
- delete the local ticket branch only after confirming its commits are merged;
- delete the exact remote ticket branch if it still exists;
- leave the protected deployment and predeployment branches untouched;
- assign the Done label and set the native state to Done when available.

Use safe merged-branch deletion and never delete a branch merely because its name looks similar. If any cleanup is unsafe, stop, keep the Ready for Production label, and report what remains. The issue must not receive the Done label while required cleanup or evidence is incomplete.

The shared checkout must remain unchanged and clean throughout this skill.
