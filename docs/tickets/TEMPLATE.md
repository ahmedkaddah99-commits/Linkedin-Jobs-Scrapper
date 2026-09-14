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

- **Candidate ID:** stable, e.g. `T16`. Never reused once assigned, even if the candidate is closed or rejected.
- **Outcome and subsystem:** one sentence stating the end state, plus the owning `docs/subsystems.yaml` id(s).
- **Evidence for the gap:** what was actually found (file:line, command output, or a doc section), not an assumption. If live access was unavailable, say so explicitly — that is a verification task, not a defect claim.
- **Source SHA and exact source paths:** the baseline SHA this candidate was scoped against, and every path it touches (or the small number of path groups, for a bounded outcome-based issue — never a bare "various").
- **Minimal required reading:** the smallest set of docs/files someone needs before starting.
- **Allowed and prohibited changes:** what may be edited, and standing prohibitions (e.g. no migration edits, no live acquisition, no Assisted Apply submit path, no admin-surface restoration).
- **Dependencies and parallel-work restrictions:** other candidate IDs this depends on or conflicts with.
- **Acceptance criteria:** checkable conditions, not vibes.
- **Safe verification commands:** commands that can run locally without live network, production credentials, or a full product deploy. Include deployment evidence only when the candidate is itself about deployment.
- **Suggested priority and status:** Low/Medium/High risk-weighted priority; status one of `Ready`, `Blocked by deps`, `In review`, `Done`.
- **Preservation/source branch references:** the branch, bundle, or archive location the content came from, if it originated outside the baseline.
- **Owner decisions, if genuinely needed:** name the decision explicitly; do not present a planned idea as a confirmed defect, and do not let a missing owner decision block filing the ticket — file it with the decision as an open field.

## Rules that keep the backlog useful

- Group related findings into one bounded, outcome-based issue. Never file a ticket per file, commit, cache, or report.
- A planned idea or a static-analysis finding is not a confirmed defect until it has been reproduced or explicitly reasoned through; say which it is.
- Completed preservation/recovery work is recorded as done with its evidence and is never reopened as a new candidate.
