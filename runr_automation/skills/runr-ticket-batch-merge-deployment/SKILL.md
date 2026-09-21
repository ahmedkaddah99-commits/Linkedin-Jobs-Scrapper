---
name: runr-ticket-batch-merge-deployment
description: Use when explicitly promoting a selected set of Runr Linear issues or sub-issues from predeployment approval to the protected deployment branch and closing the passed issues.
---

# Runr batch merge deployment

This skill is explicit-only. The user supplies Linear IDs, URLs, or unambiguous issue details. It promotes selected Ready for Production issues as one controlled deployment and finalizes each issue independently.

## Mandatory release approval

Require a matching unexpired release approval whose exact targets and action fingerprint bind every tested commit SHA, issue/scope fingerprint, and predeployment test result. Any material change invalidates approval. Deployment integration and cleanup are serialized.

## Deterministic Issue Status label

The authoritative lifecycle marker is exactly one child label of the Issue Status group, using the registry in docs/tickets/TEMPLATE.md. For every transition in this skill:

1. Resolve the exact Linear issue and the target label by exact name and parent group.
2. If the target child is missing, create it under Issue Status with linear_save_issue_label as part of this skill. If an exact unarchived child already exists, reuse it and never create a duplicate.
3. Call linear_save_issue with addLabels containing the target label ID and removeLabels containing every other Issue Status child ID. Preserve unrelated labels.
4. Set the native Linear workflow state only when the exact state exists natively. For custom lifecycle names, apply the exact label and leave the native state unchanged; do not stop or substitute another label.
5. Re-read the exact issue and verify that exactly one Issue Status label is assigned and it is the target label before reporting the transition.

The label assignment is mandatory even when the native status update succeeds.
## Required state

Every selected issue must have the Ready for Production Issue Status label. Keep every selected issue labeled Ready for Production while the batch runs. Resolve each issue's tested revision, predeployment evidence, branch, worktree, dependencies, parent, and exact scope. `Predeployment Integrated` is an implementation-unblock state, not a deployment approval; exclude it and report it rather than silently promoting it. Exclude any issue without Ready for Production; do not silently include it.

## Batch safety and integration

Re-fetch the tested predeployment and protected deployment revisions. Build a dependency-aware order, serializing overlapping paths, migrations, schemas, deployment configuration, and shared resources. Confirm that every promoted commit is the one that passed predeployment. If a conflict or defective change is attributable to one issue, do not mark unrelated passed issues as failed.

Use one dedicated deployment integration worktree and protected-branch/PR flow. Point the Runr frontend, API, and worker Render services back to the deployment branch only after the protected merge, wait for deploy completion, and run combined smoke checks plus each issue's required verification. Record the exact deployment revision, PR, Render deployment IDs, timestamps, and results.

A change defect assigns Integration Fix Required to the responsible issue. A temporary infrastructure failure leaves affected issues labeled Ready for Production. A missing dependency, requirement, or external system receives the appropriate blocked label. Do not claim a batch passed because only some checks ran.

## Per-issue finalization

For each issue independently:

- passed deployment and verification -> assign Done;
- responsible integration defect -> assign Integration Fix Required;
- blocked -> assign the appropriate Waiting for Predecessor, Missing Requirement, or External Blocked label;
- temporary infrastructure failure -> remain labeled Ready for Production.

For each passed issue, only after its exact commits are confirmed merged:

- remove its dedicated worktree with `runr_automation/scripts/remove-worktree-safely.ps1 -RepositoryPath <shared-checkout> -WorktreePath <exact-issue-worktree>` so any `.venv` junction is detached before Git cleanup;
- delete its local ticket branch safely;
- delete its exact remote ticket branch if it still exists;
- preserve the protected deployment and predeployment branches.

Attach one batch report and link it from every affected issue. Set parent issues to Done only when their own acceptance criteria and all required child issues are complete. Never delete a failed or blocked issue branch. Keep the shared checkout unchanged and clean.
