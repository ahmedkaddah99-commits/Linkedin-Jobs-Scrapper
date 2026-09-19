# Work item template

## Ownership split

GitHub owns technical documentation and implementation evidence: subsystem docs under `docs/reverse-engineering/`, `docs/subsystems.yaml`, `docs/INDEX.md`. Linear owns current work status, priority, dependencies and assignment. A candidate recorded in the consolidated backlog (`RUNR_REVERSE_ENGINEERING_2026-09-10/clean-slate-2026-09-13/linear-ticket-candidates.md`) is the technical record; its live status/priority/assignment lives in Linear once created there, not in this repo.

**Every implementation ticket must, on completion, update:**
- the subsystem doc(s) its change affects (listed in the ticket's "Subsystem" field, cross-referenced in `docs/subsystems.yaml`);
- the matching `docs/subsystems.yaml` entry, if it changed an owned path, entry point, dependency, or invariant;
- `docs/reverse-engineering/06-history-and-provenance/known-gaps.md`, if it closes or narrows a C#/U#/WS<n>-G<k> item.

Registry/path/link checks (see `docs/INDEX.md` "Verification") run whenever documentation changes, not the full product test suite.

**Once the backlog file's candidates are created in Linear, that file becomes a migration cross-reference only — not a second live backlog.** New work is filed directly in Linear from then on, using this template's fields; do not add new candidates to the old file after migration.

## Required fields

### User story and issue type

- **User story:** `As a [role], I want [one bounded outcome], so that [observable value].` This is the first explanatory line after the title and applies to parent issues and sub-issues.
- **Issue type:** `Feature`, `Bug`, `Refactor`, `Documentation`, `Investigation`, or `Chore`.
- **Bug fields when applicable:** observed behavior, expected behavior, reproduction steps/environment, evidence and first known-good/bad revision when known, and regression risk.

### Deterministic grouped labels

Linear labels are the authoritative lifecycle marker because the Runr workflow has custom lifecycle names. Every issue must have exactly one child label from `Issue Status`, and ticket creation must have exactly one child label from `Issue Type`. Preserve unrelated labels.

The current Runr `Issue Status` label registry is:

| Label | Linear label ID |
|---|---|
| Backlog | `a346cd70-1c5c-42a6-85b4-100b05a4dca6` |
| Todo | `120ec4c7-3ad6-4410-86ab-da566f1d4d37` |
| Ready | `b372a50e-c2e0-49a9-861f-defbc0a4e17b` |
| In Progress | `9b6ced10-5c38-4918-a5bc-b3e9cd744462` |
| In Review | `3d37a79a-5846-4d67-bf06-5de318d5dd2c` |
| Implementation Fix Required | `462733e6-5f8f-4331-bf5b-8630751b00c2` |
| Integration Fix Required | `b156f610-dc03-4823-a52f-6c69ac8ec006` |
| Ready for Production | `73745eed-38a1-4d67-bf06-5de318d5dd2c` |
| Waiting for Predecessor | `1ef39763-5a42-4805-8e1c-a1cadfe1bdbb` |
| Missing Requirement | `0300c1e5-08b9-4d60-a0ea-84eb80b2f240` |
| External Blocked | `884aa6c9-10fb-45a0-bd2f-41c7c9d60f43` |
| Duplicate | `7e827c5a-a264-4e96-a7a6-abcb800a825f` |
| Done | `11478999-1b28-46cf-bbf1-f3016e55062b` |
| Canceled | `fb0b29ec-ef96-4a97-85b7-6dee8d1965ca` |

The current Runr `Issue Type` labels are `Bug` (`25d5bce9-8d70-4f69-b486-8b8470efdcb2`), `Feature` (`2794bc78-94af-491d-b955-a76ab2ba3fed`), and `Improvement` (`c189e709-7b93-4b65-82a3-ac8d413f46e2`). If an explicitly requested type has no exact child label, the ticket-creation skill creates that child under `Issue Type` before creating the ticket.

When a skill changes lifecycle, it must remove every other child of the `Issue Status` group and apply the exact target label to the exact Linear issue. It must then re-read the issue and verify that exactly one `Issue Status` label is present. Custom labels do not require a matching native workflow status; never silently substitute a different label or stop merely because the native status is unavailable.

### Canonical classification

- **Primary subsystem:** assign exactly one child of the `Subsystem` grouped label derived from one normalized `docs/subsystems.yaml` ID. Record co-owner subsystem IDs in the description; never assign a second Subsystem child or a subsystem project.
- **Completion documentation:** identify the subsystem document, `docs/subsystems.yaml` entry, and `known-gaps.md` row that must be updated when the work changes technical truth.

- **Candidate ID:** stable, e.g. `T16`. Never reused once assigned, even if the candidate is closed or rejected.
- **Outcome and subsystem:** one sentence stating the end state, plus the owning `docs/subsystems.yaml` id(s).
- **Evidence for the gap:** what was actually found (file:line, command output, or a doc section), not an assumption. If live access was unavailable, say so explicitly — that is a verification task, not a defect claim.
- **Source SHA and exact source paths:** the baseline SHA this candidate was scoped against, and every path it touches (or the small number of path groups, for a bounded outcome-based issue — never a bare "various").
- **Minimal required reading:** the smallest set of docs/files someone needs before starting.
- **Allowed and prohibited changes:** what may be edited, and standing prohibitions (e.g. no migration edits, no live acquisition, no Assisted Apply submit path, no admin-surface restoration).
- **Dependencies and parallel-work restrictions:** native blocking relations plus evidence and shared conflict resources.
- **Execution plan:** no permanent boolean parallel label. `Execution Mode` and `Execution Wave` are projections of the current versioned controller plan and must be recomputed when dependencies, paths, resources, priority, estimate, lifecycle, or completion changes.
- **Acceptance criteria:** checkable conditions, not vibes.
- **Safe verification commands:** commands that can run locally without live network, production credentials, or a full product deploy. Include deployment evidence only when the candidate is itself about deployment.
- **Worktree contract:** record the intended branch slug and worktree path pattern; the ticket-start skill creates them only when explicitly invoked. Ticket creation never creates them.
- **Attempt-log contract:** every implementation attempt, passing or failing, records its attempt number, implementation commit SHA (or baseline SHA for a no-op), attempt-log metadata commit SHA when applicable, result, checks, and chat link in a labelled Linear attachment.
- **Suggested priority and status:** Low/Medium/High risk-weighted priority; creation uses `Todo` or `Ready`, or one of `Waiting for Predecessor`, `Missing Requirement`, or `External Blocked` when blocked. Later lifecycle skills use `In Progress`, `In Review`, `Implementation Fix Required`, `Integration Fix Required`, `Ready for Production`, `Done`, or `Canceled` according to their explicit status contract.
- **Preservation/source branch references:** the branch, bundle, or archive location the content came from, if it originated outside the baseline.
- **Owner decisions, if genuinely needed:** name the decision explicitly; do not present a planned idea as a confirmed defect, and do not let a missing owner decision block filing the ticket — file it with the decision as an open field.

## Lifecycle status and label contract

Status and Issue Status label changes are explicit skill actions. The grouped Issue Status label is authoritative for custom lifecycle names, and the exact label must be assigned to the exact issue before a skill reports success. Do not move or label an issue because a conversation ended or because a branch was created.

| Skill | Required starting status/label | Status/label while running | Successful result/label | Implementation failure | Integration failure | Blocked result |
|---|---|---|---|---|---|---|
| `runr-ticket-creation` | New issue / Backlog | - | Todo or Ready | - | - | Waiting for Predecessor, Missing Requirement, or External Blocked |
| `runr-ticket-start` | Ready, Implementation Fix Required, or Integration Fix Required | In Progress | In Review | Implementation Fix Required | - | Appropriate blocked status |
| `runr-ticket-merge-predeployment` | In Review | In Review | Ready for Production | - | Integration Fix Required | Appropriate blocked status, or remain In Review for temporary infrastructure failure |
| `runr-ticket-merge-deployment` | Ready for Production | Ready for Production | Done | - | Integration Fix Required when the change is defective | Appropriate blocked status, or remain Ready for Production |
| `runr-ticket-batch-merge-predeployment` | Selected issues In Review | In Review | Passed issues -> Ready for Production | - | Responsible issues -> Integration Fix Required | Appropriate blocked status |
| `runr-ticket-batch-merge-deployment` | Selected issues Ready for Production | Ready for Production | Passed issues -> Done | - | Responsible issues -> Integration Fix Required | Appropriate blocked status |
| `runr-discard-issue` | Appropriate non-final state | - | Canceled | - | - | Leave current state if discard cannot safely complete |

## Rules that keep the backlog useful

- Group related findings into one bounded, outcome-based issue. Never file a ticket per file, commit, cache, or report.
- A planned idea or a static-analysis finding is not a confirmed defect until it has been reproduced or explicitly reasoned through; say which it is.
- Completed preservation/recovery work is recorded as done with its evidence and is never reopened as a new candidate.
