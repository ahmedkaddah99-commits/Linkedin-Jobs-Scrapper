---
name: runr-ticket-creation
description: Use when explicitly creating, normalizing, or grouping Runr Linear issues that need subsystem ownership, exact file scope, evidence, dependencies, and safe verification.
---

# Runr ticket creation

This skill is explicit-only: do not create, normalize, label, or regroup an issue unless the user invokes this skill or directly asks for that operation. Technical truth lives in GitHub; Linear owns current status, priority, assignment, dependencies, and the Subsystem grouped label.

## Read before writing

Read `docs/INDEX.md`, `docs/tickets/TEMPLATE.md`, and `docs/subsystems.yaml`. Then read the owning subsystem document's architecture and `Agent context and remaining work` sections. Use the Linear issue/project tools to inspect existing issues and avoid duplicates. After migration, create new work directly in Linear; do not append to `linear-ticket-candidates.md` or create a local ticket Markdown file. If a temporary Markdown payload is needed for an attachment, delete it after Linear confirms the upload.

## Issue shape

Keep the existing ticket structure. Put this sentence immediately after the title so both a person and an agent can understand the request:

`As a [role], I want [one bounded outcome], so that [observable value].`

Also include the requested issue type and assign exactly one matching child label from the `Issue Type` group. The current canonical choices are `Bug`, `Feature`, and `Improvement`; use the description to record a narrower subtype such as refactor, documentation, investigation, or chore.

For a `Bug`, retain the normal ticket sections and add:

- Observed behavior.
- Expected behavior.
- Reproduction steps and environment.
- Evidence and first known-good/bad revision, if known.
- Regression risk and affected subsystem.

Sub-issues use exactly the same structure. Add the parent Linear ID and state the child outcome independently; never rely on the parent description to supply missing scope.

## Classification and controller pipeline

Choose exactly one primary registry subsystem and assign exactly one matching child of the Subsystem grouped label. Never assign a subsystem project. Record co-owner subsystem IDs in the structured description, never as a second Subsystem child. Require minimal Required reading, exact Allowed paths, required tests, and evidence for dependencies. Subsystem ownership grants reads only; Allowed paths alone grant writes.

Invoke or enqueue `runr-ticket-deduplication`, `runr-ticket-research`, and `runr-parallelization-plan` through the local controller. Do not assign a permanent boolean or `exec-*` parallel label. Execution Mode and Execution Wave are projections of a current versioned plan.

## Deterministic Linear label assignment

Read the grouped label registry in `docs/tickets/TEMPLATE.md`. For every created or normalized issue:

1. Resolve the exact Runr child label under `Issue Status` for the target lifecycle result and the exact child label under `Issue Type` for the issue type.
2. Create a missing child label under the correct group with `linear_save_issue_label` as part of this explicitly invoked skill. Never create a second label when an exact unarchived child already exists.
3. Call `linear_save_issue` with the target status/type labels in `addLabels` and every other `Issue Status` and `Issue Type` child in `removeLabels`; preserve unrelated labels such as execution labels.
4. Re-read the exact issue and verify that exactly one `Issue Status` label and exactly one `Issue Type` label are assigned.

The grouped label is authoritative for custom lifecycle names. If a custom native workflow status is unavailable, apply the exact grouped label and leave the native workflow state unchanged; never stop and never substitute a different label. `Todo` and `Ready` are distinct labels even if the native state remains `Todo`.

## Required packet

Use these fields in this order, preserving the existing template:

1. Bounded title and the user story above.
2. Issue type.
3. Candidate ID, primary Subsystem grouped label, and co-owner subsystem IDs.
4. Outcome and evidence, including gap IDs and exact file/symbol/line references where known.
5. Baseline SHA, source branch/archive, and exact allowed paths.
6. Minimal required reading.
7. Allowed changes and prohibited changes.
8. Dependencies, parent/sub-issue relationship, conflict resources, and parallel-work restrictions. Every blocking relation must declare `dependency-kind` (`implementation`, `release`, or `external`), the required artifact or decision, and the exact `unblocks-when` condition. An implementation dependency may be satisfied by a predecessor's `Predeployment Integrated` revision; a release dependency requires `Ready for Production`.
9. Checkable acceptance criteria.
10. Safe local verification commands.
11. Worktree contract: the start skill will create the branch/worktree; creation must record the intended branch slug and worktree path pattern, but must not create either one.
12. Attempt-log and completion-documentation expectations.
13. Suggested priority and the next lifecycle state.

Never use `various files`. Separate files to inspect from files allowed to change. Treat static findings as unverified unless reproduced. Do not paste credentials, proxy values, customer CV content, or private payloads into Linear.

## Status contract

Status changes happen only as part of an explicitly invoked skill. On creation:

- Incoming issue may be `New issue` or `Backlog`.
- A complete, actionable issue becomes `Todo` or `Ready`. Use `Ready` only when required reading, scope, acceptance, verification, and dependencies are complete; otherwise use `Todo`.
- A missing predecessor receives the `Waiting for Predecessor` label.
- An underspecified request receives the `Missing Requirement` label.
- An unavailable external system receives the `External Blocked` label.

The exact lifecycle label must always be assigned to the exact issue before this skill reports success. Native workflow state is updated only when the requested state exists natively; labels are never silently substituted.

## Linear operations

Use `linear_list_issues`/`linear_search` to bound duplicate candidates and `linear_save_issue` to create or update the issue. Set priority, native state when available, grouped labels, parent, and dependency relations as Linear metadata; do not rely on duplicated prose. Preserve issue-specific safety boundaries when normalizing older tickets.

Creation must not create a branch, worktree, PR, commit, or deployment. Those are deliberate actions of the start and merge skills.

## Completion

Run the listed verification commands for the ticket document itself. Update the owning subsystem document, `docs/subsystems.yaml` when ownership/paths/invariants change, and `docs/reverse-engineering/06-history-and-provenance/known-gaps.md` when a gap is closed or narrowed. Attach evidence before any later merge skill moves the issue to a final state.

## Red flags

- Ticket has no user story, exact paths, issue type, or acceptance checks.
- A sub-issue says "see parent" instead of carrying its own executable scope.
- `exec-parallel-safe` is used without a path/dependency/shared-resource check.
- Creation is about to make a branch, worktree, commit, PR, or deployment.
- The exact `Issue Status` or `Issue Type` child label is missing from the ticket after creation.
- A custom label is replaced by a visually similar native status or another label.
