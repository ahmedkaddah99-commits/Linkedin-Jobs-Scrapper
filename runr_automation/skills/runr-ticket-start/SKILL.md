---
name: runr-ticket-start
description: Use when explicitly starting a Runr Linear issue or sub-issue for implementation in its own branch and worktree.
---

# Runr ticket start

This skill is explicit-only and is the controller-managed implementation entrypoint. It creates the issue's isolated branch and worktree, moves the issue through implementation, and leaves a complete attempt record whether the attempt passes or fails. For one-ticket execution without the full local automation queue, use `runr-ticket-implementation`; do not invoke both paths for the same issue.

## Controller eligibility gate

Require a valid hashed scope manifest and current plan before creating a worktree. The manifest must identify exactly one primary subsystem, co-owners, allowed reads, Allowed paths for writes, denied roots, tests, issue ID, and content hashes. Deduplication must be Clear, research Current or Not Required, dependencies ready, and the issue must belong to an explicitly compatible current wave. Validate every checkpoint and final diff against Allowed paths. All implementation runs in the dedicated issue worktree; the shared checkout is never a fallback.

## Deterministic Issue Status label

The authoritative lifecycle marker is exactly one child label of the Issue Status group, using the registry in docs/tickets/TEMPLATE.md. For every transition in this skill:

1. Resolve the exact Linear issue and the target label by exact name and parent group.
2. If the target child is missing, create it under Issue Status with linear_save_issue_label as part of this skill. If an exact unarchived child already exists, reuse it and never create a duplicate.
3. Call linear_save_issue with addLabels containing the target label ID and removeLabels containing every other Issue Status child ID. Preserve unrelated labels.
4. Set the native Linear workflow state only when the exact state exists natively. For custom lifecycle names, apply the exact label and leave the native state unchanged; do not stop or substitute another label.
5. Re-read the exact issue and verify that exactly one Issue Status label is assigned and it is the target label before reporting the transition.

The label assignment is mandatory even when the native status update succeeds.
## Resolve and validate

Resolve means read the exact Linear issue by ID, URL, or an unambiguous identifier and collect its title, native git branch name, parent, project, subsystem, labels, dependencies, allowed paths, acceptance criteria, and current status. It does not mean close the issue.

The required starting Issue Status label is exactly one of:

- Ready
- Implementation Fix Required
- Integration Fix Required

If the issue has any other Issue Status label, do not start it. If the requested target label is absent, create it under Issue Status through the deterministic label procedure before changing the issue; absence of a native custom workflow status is not a reason to stop.

## Isolate before editing

1. Read the issue and the relevant files listed by the ticket.
2. Fetch the named deployment baseline and verify the baseline revision.
3. Verify the shared checkout is not the implementation directory. Do not edit, stash, reset, clean, or commit the shared checkout, and never use it as a fallback.
4. Create one dedicated branch using the Linear native branch name when available; otherwise use runr/<RUN-ID>-<short-slug>.
5. Create one worktree outside the shared checkout, using a stable path such as ../runr-worktrees/<RUN-ID>.
6. Verify the new directory is a worktree on the expected branch and that its starting SHA is the recorded baseline.
7. Record the branch and absolute worktree path in the issue attachment or implementation note.

If the intended worktree already exists, verify its branch and path before use. Never silently reuse a worktree belonging to another issue. If the baseline or worktree cannot be verified, assign the appropriate blocked Issue Status label and stop.

## Lifecycle status

After isolation succeeds, assign the In Progress Issue Status label and set the native state to In Progress. Keep that label while implementation is running.

A successful implementation attempt ends with the In Review label. A failed implementation attempt ends with the Implementation Fix Required label. A missing predecessor, requirement, or external system receives the appropriate Waiting for Predecessor, Missing Requirement, or External Blocked label. This skill never assigns Done, Ready for Production, or Canceled.

## Implement within the packet

Read the minimum required docs and inspect only the ticket's allowed paths plus necessary tests. Follow the issue's acceptance criteria and prohibited-change list. Parent and sub-issue scope are independent; do not silently implement unrelated parent work.

Before finishing, check:

- acceptance criteria and regression behavior;
- the ticket's listed verification commands;
- changed paths against the allowed paths;
- documentation and registry obligations;
- source-control status and untracked files in the dedicated worktree.

Do not discard user changes to make a check pass. If unrelated files appear, stop and classify the scope problem.

## Attempt log is part of this skill

Create an attempt log for every implementation attempt, including a successful attempt, a failed test, a blocked attempt, or a no-op. The log must include:

- Linear issue ID and attempt number;
- chat/session link;
- baseline SHA, branch, worktree, and final commit SHA;
- exact files changed;
- checks run and their results;
- acceptance criteria passed, failed, or not run;
- failure or blocked reason;
- next action.

Commit the implementation/result changes first, whether checks pass or fail, and capture that implementation commit SHA. A failed implementation commit must remain only on the issue branch and must be clearly labelled as failed. Then write the attempt log with the implementation SHA and commit the log as a separate metadata commit. This two-commit order avoids the impossible circular requirement of putting a commit's own SHA inside itself. Include both the implementation SHA and attempt-log commit SHA in the attachment. If no implementation files changed, record the baseline SHA and do not create an empty implementation commit merely to manufacture a SHA.

Use a labelled Linear attachment named with the implementation commit SHA, like:
RUN-123-ATTEMPT-01-<commit-sha>-passed.md
or
RUN-123-ATTEMPT-01-<commit-sha>-failed.md
For a no-op, use the baseline SHA. Upload the attachment through the available Linear attachment flow and include the chat link in both the attachment and the issue comment when comments are supported.

The attachment is evidence, not a substitute for the issue description. Never omit it because the implementation succeeded.

## Source-control cleanliness

Before handoff, the dedicated worktree must be clean except for intentionally preserved ignored runtime files, and the attempt log itself must be committed. The shared checkout must remain byte-for-byte and index-for-index as it was before the skill started. If clean handoff is impossible without deleting or overwriting user data, stop and use an appropriate blocked status.

## Common mistakes

- Starting from Todo or In Review instead of a required starting status.
- Editing the shared checkout because the requested file is already open there.
- Calling "resolve" a close operation.
- Reporting a passing implementation without committing and attaching the attempt log.
- Deleting a failed branch or worktree before the predeployment decision.
- Moving the issue to Done; integration skills own that transition.
