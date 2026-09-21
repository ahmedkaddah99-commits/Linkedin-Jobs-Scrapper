---
name: runr-ticket-batch-merge-predeployment
description: Use when explicitly promoting a selected set of Runr Linear issues or sub-issues from review to the permanent predeployment branch as one verified batch.
---

# Runr batch merge predeployment

This skill is explicit-only. The user supplies Linear IDs, URLs, or unambiguous issue details. It integrates only the selected issues, keeps their individual branches and worktrees, temporarily points Render at predeployment, and updates every issue separately.

## Mandatory controller approval

Require one matching unexpired local approval whose targets exactly equal the batch and whose action fingerprint binds every tested commit SHA, issue/scope fingerprint, and test result. Any change invalidates it. Batch integration is serialized through the controller.

## Deterministic Issue Status label

The authoritative lifecycle marker is exactly one child label of the Issue Status group, using the registry in docs/tickets/TEMPLATE.md. For every transition in this skill:

1. Resolve the exact Linear issue and the target label by exact name and parent group.
2. If the target child is missing, create it under Issue Status with linear_save_issue_label as part of this skill. If an exact unarchived child already exists, reuse it and never create a duplicate.
3. Call linear_save_issue with addLabels containing the target label ID and removeLabels containing every other Issue Status child ID. Preserve unrelated labels.
4. Set the native Linear workflow state only when the exact state exists natively. For custom lifecycle names, apply the exact label and leave the native state unchanged; the sole exception is a successfully integrated, live-pending `Predeployment Integrated` outcome, which sets native Linear `Done` as an administrative implementation closure. Do not stop or substitute another label.
5. Re-read the exact issue and verify that exactly one Issue Status label is assigned and it is the target label before reporting the transition.

The label assignment is mandatory even when the native status update succeeds.
## Required state

Every selected issue must have either the `In Review` Issue Status label for initial integration or `Predeployment Integrated` for a live-verification retry. Keep each issue's applicable label while the batch runs. Resolve each issue and collect its tested commit, attempt evidence, parent, subsystem, execution label, dependencies, exact paths, and acceptance checks. For a `Predeployment Integrated` issue, verify its recorded `integration_revision` is already on `predeployment/render-turso-r2` and skip a duplicate merge. If an issue has neither allowed label, exclude it and report it; never silently widen the selection.

## Batch safety analysis

Before merging, compute a dependency-aware order:

- predecessors before dependents;
- overlapping paths, migrations, schemas, deployment configuration, and shared resources serially;
- execution labels are hints that must be confirmed against actual paths and issue metadata;
- issues with unresolved conflicts or missing evidence are blocked before integration.

Do not call a batch parallel-safe merely because the issues have different titles or subsystems. If the analysis cannot prove separation, use serial integration or stop with the appropriate blocked status.

Use a dedicated batch integration worktree and branch from the verified permanent predeployment revision. Integrate one issue's tested commit at a time. Keep each ticket branch, remote branch, and issue worktree intact. If one issue fails, do not hide it by rolling its status into the batch result: exclude its changes when feasible, continue only with independently verifiable issues, and mark the responsible issue Integration Fix Required or the appropriate blocked status.

## Render verification

After the selected passing changes are present, merge the batch through the protected predeployment flow, point the frontend, API, and worker Render services to the permanent predeployment branch, wait for deployment, and run the combined checks plus each issue's acceptance path. Record the exact batch revision and deployment evidence.

A temporary Render/infrastructure failure after successful code integration assigns affected issues the `Predeployment Integrated` label and records each exact `integration_revision`; it does not leave them indistinguishable from unintegrated review work. A defective integration assigns the Integration Fix Required label to the responsible issue or issues. Missing predecessor, requirement, or external system uses the appropriate blocked label. Do not label a failed issue Ready for Production.

The dependency contract must distinguish `implementation` dependencies from `release` dependencies. An implementation dependency is unblocked when the predecessor's exact tested commit is present on permanent predeployment and the combined checks pass; implementation-dependent tickets may consume that revision. A release dependency remains blocked until the predecessor reaches `Ready for Production`. The batch report must state both gates for every issue.

## Per-issue result

For each selected issue independently:

- passed integration and live verification -> assign Ready for Production;
- passed integration with live verification pending -> assign Predeployment Integrated, record the exact batch revision, and set the native Linear workflow state to Done as an administrative implementation closure;
- responsible integration defect -> assign Integration Fix Required;
- blocked -> assign Waiting for Predecessor, Missing Requirement, or External Blocked;
- temporary infrastructure failure after successful integration -> assign Predeployment Integrated.

Attach a batch report linking every issue, commit, result, and chat link. Native Done in the live-pending outcome is administrative only; preserve the custom `Predeployment Integrated` label and never treat it as production completion. Leave all ticket branches and worktrees available for the deployment merge or discard skill. Keep the shared checkout untouched and clean.
