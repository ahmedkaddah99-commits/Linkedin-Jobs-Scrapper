---
name: runr-ticket-implementation
description: Use when explicitly implementing one exact Runr Linear issue or sub-issue independently of the full local automation queue, without polling or processing other tickets.
---

# Runr ticket implementation

This skill is explicit-only and owns one complete implementation attempt for one exact Linear issue or sub-issue. It is the standalone path when the user wants a single ticket implemented without running `runr-auto once`, `daemon`, `reconcile`, or any controller operation that can process other tickets.

The implementation boundary ends at `In Review`, `Implementation Fix Required`, or an appropriate blocked status. This skill must never merge, never deploy, delete issue artifacts, or assign `Done`.

## Resolve the one-ticket packet

Require one exact Linear issue ID, URL, or unambiguous issue detail. Resolve and re-read the issue before changing anything. Capture:

- issue ID, identifier, title, parent/sub-issue relationship, native branch name, and current status;
- exactly one primary subsystem, co-owner subsystem IDs, allowed reads, `Allowed paths`, denied roots, required tests, acceptance criteria, and prohibited changes;
- baseline SHA, current scope/plan fingerprint, dependencies, conflict resources, latest attempt evidence, and any existing dedicated worktree;
- completion-documentation obligations from `docs/tickets/TEMPLATE.md`.

Do not treat "only one ticket" as permission to skip safety gates. The issue must have a valid hashed scope manifest and a current compatible execution plan. If deduplication, research, or plan evidence is absent or stale, perform the relevant per-issue/connected-component check with the corresponding Runr skill or stop. For every blocking relation, distinguish an `implementation dependency` from a `release dependency`: an implementation dependency may be satisfied by a predecessor's exact tested revision in `Predeployment Integrated` or `Ready for Production`, while a release dependency remains a later promotion gate. Never run the global queue to manufacture evidence. A missing requirement, unresolved dependency, ambiguous scope, or stale plan is a blocked outcome, not an invitation to broaden the ticket.

The starting `Issue Status` label must be exactly `Ready`, `Implementation Fix Required`, or `Integration Fix Required`. If the issue has another status, stop without editing. Before proceeding, verify that no controller run is actively implementing this same issue. Do not create a second branch or worktree for an unknown existing attempt.

## Deterministic status labels

Use the grouped `Issue Status` registry in `docs/tickets/TEMPLATE.md`. For every lifecycle transition:

1. Resolve the exact child label under the `Issue Status` group; create it only if missing and never duplicate an exact unarchived label.
2. Call `linear_save_issue` with the target label in `addLabels` and every other `Issue Status` child in `removeLabels`; preserve unrelated labels.
3. Set the native Linear state only when the exact state exists natively.
4. Re-read the issue and verify that exactly one `Issue Status` child is assigned.

The grouped label is authoritative. A missing custom native state is not a reason to substitute a different label or stop.

## Isolate before implementation

1. Read `docs/INDEX.md` and only the ticket's minimal required reading plus manifest-approved files.
2. Fetch and verify the permanent predeployment branch `predeployment/render-turso-r2` and use its exact revision as the worktree creation base. If an implementation dependency supplies an exact `integration_revision`, verify that revision is present on the permanent predeployment branch and record it in the attempt evidence. The ticket's named deployment baseline remains provenance evidence; do not silently replace the predeployment base with current `HEAD`.
3. Create or resume one issue-specific branch: use the Linear branch name when available; otherwise use `runr/<RUN-ID>-<short-slug>`.
4. Create the worktree outside the shared checkout, for example `../runr-worktrees/<RUN-ID>`, from the verified permanent predeployment revision. Verify its absolute path, branch, starting SHA, and ownership before editing.
5. Leave the shared checkout byte-for-byte and index-for-index unchanged. Assign `In Progress` only after isolation succeeds.

If baseline, branch identity, scope, or worktree ownership cannot be verified, assign the appropriate blocked label and stop. Never use the shared checkout as a fallback.

## Implement within the packet

Follow the acceptance criteria and prohibited-change list. Read only allowed paths and write only `Allowed paths`; validate every changed path before handoff. Preserve unrelated user changes and untracked files. Do not install packages, access production, use credentials, or alter deployment configuration unless the ticket explicitly allows it.

## Persistent repository virtual environment

Git worktrees do not inherit ignored directories such as `.venv`. The canonical environment is the shared checkout's `.venv` directory, and every dedicated implementation worktree must expose that same environment through a directory junction named `.venv`.

Immediately after creating or resuming a worktree:

1. Verify `<shared-checkout>\.venv\Scripts\python.exe --version` reports exactly `Python 3.12.7`. If the canonical interpreter is missing or has another version, stop; never use a global interpreter.
2. If `<worktree>\.venv` is absent, create an explicit Windows directory junction to the canonical `.venv`:

```powershell
New-Item -ItemType Junction -Path "<worktree>\.venv" -Target "<shared-checkout>\.venv"
```

3. If a worktree already has `.venv`, verify it is the junction to the canonical environment. Do not overwrite a non-junction or an environment with a different target.
4. Run `<worktree>\.venv\Scripts\python.exe --version` before any ticket command and require `Python 3.12.7`.

This keeps the environment persistent across Runr tickets without copying it into Git worktrees or placing it in ticket branches.

Never remove a worktree that has a `.venv` junction with `git worktree remove --force` or a recursive filesystem delete: that cleanup has emptied the shared environment. Authorized cleanup must use `runr_automation/scripts/remove-worktree-safely.ps1` with the verified repository and worktree paths. The helper detaches the junction first and lets Git refuse a dirty worktree.

For this repository, verify the interpreter before tests:

```powershell
.venv\Scripts\python.exe --version
```

It must report Python `3.12.7`. Use `.venv\Scripts\python.exe` for all Python commands; never use global Python or pip. Run the ticket's listed safe verification commands, replacing bare Python references with the project interpreter. Do not replace a failing required check with an unrelated "quick" check.

Update the owning subsystem documentation, `docs/subsystems.yaml`, or `known-gaps.md` when the ticket requires it. Run the focused documentation link/registry checks when documentation changes.

## Attempt evidence and handoff

Record every attempt: successful, failed, blocked, interrupted, or no-op. Before handoff, record the issue ID and attempt number, chat/session link, baseline SHA, branch, absolute worktree, final implementation SHA, exact changed files, commands/results, acceptance-criteria results, and failure or blocker reason.

If implementation files changed, commit the implementation/result changes first, even when a failed attempt must be preserved. Record the attempt evidence directly in Linear or upload it as a Linear attachment; do not create or commit `docs/tickets/attempts/*.md`. If a temporary Markdown payload is needed for upload, delete it after Linear confirms the attachment. If no implementation files changed, use the baseline SHA and do not create an empty implementation commit. Attach the evidence to the exact Linear issue using a labelled attachment such as `RUN-123-ATTEMPT-01-<commit-sha>-passed.md` or `...-failed.md`; include the chat link in the attachment and issue comment when supported.

On a validated implementation, assign `In Review`. On a failed implementation or failed required check, assign `Implementation Fix Required`. Use `Waiting for Predecessor`, `Missing Requirement`, or `External Blocked` when appropriate. Verify the final label after mutation.

Leave the issue branch, remote branch, and worktree intact for review and later merge. Do not merge, deploy, clean up, discard, or mark the issue `Done`; use the separate predeployment, deployment, or discard skill.

## Red flags

- Running `runr-auto once`, `daemon`, `reconcile`, or `retry` when it can touch unrelated tickets.
- "It is only one ticket, so deduplication, dependencies, or plan freshness do not matter."
- Using the shared checkout or current `HEAD` because it is faster.
- Treating passing tests as permission to assign `Done`.
- Deleting the issue worktree or branch after implementation.
- Reporting success without the implementation commit, exact checks, and Linear evidence.
