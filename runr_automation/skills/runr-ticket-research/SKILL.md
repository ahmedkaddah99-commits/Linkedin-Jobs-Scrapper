---
name: runr-ticket-research
description: Use when a Runr ticket asks research questions, depends on unstable external facts, or needs repository evidence before implementation.
---

# Runr ticket research

Internal research may inspect only the supplied scope manifest. Cite exact repository paths and symbols; identify reusable capabilities, missing primitives, migrations, interfaces, tests, blockers, and prerequisite tickets. State whether implementation can start now.

External research runs only when requested or when internal evidence identifies an unstable unknown. Use primary sources for technical claims. Record URL, access date, supported claim, and implementation impact; do not copy substantial copyrighted text.

Write the bounded evidence artifact directly into the Linear issue or as a Linear attachment and return one Research State. Do not create a committed local ticket Markdown file. If a temporary Markdown payload is needed for upload, delete it after Linear confirms the attachment. Freshness follows the input fingerprint and cited premise, not merely elapsed time. Missing access becomes `Research Blocked`; ambiguity requiring product choice becomes `Needs Decision`.

## Implementation handoff

`Current` means the evidence artifact is complete, its input fingerprint and cited premise are current, and the research result explicitly states whether implementation can start. Before handoff, classify each predecessor relation. An `implementation dependency` is satisfied by an exact predecessor revision in `Predeployment Integrated` or `Ready for Production`; a `release dependency` remains a later promotion gate and does not prevent implementation. When the issue's implementation gate is satisfied, this skill hands the exact Linear issue to the implementation skill by moving its lifecycle marker to `Ready`:

1. Resolve the exact issue and the exact `Ready` Issue Status label under the `Issue Status` group using the registry in `docs/tickets/TEMPLATE.md`. If the exact unarchived child is missing, create it with `linear_save_issue_label`; never create a duplicate.
2. Call `linear_save_issue` with the `Ready` label in `addLabels` and remove every other `Issue Status` child through `removeLabels`. Preserve unrelated labels.
3. Set the native Linear state to `Ready` only when that exact native state exists. The grouped `Ready` label remains authoritative when the native state is unavailable.
4. Re-read the exact issue and verify that exactly one `Issue Status` child is assigned and that it is `Ready` before reporting the handoff.

Research does not create an implementation branch or worktree and does not assign `In Progress`; those actions belong to the implementation skill. `Research Blocked` and `Needs Decision` must not move to `Ready`. Use the appropriate blocked Issue Status label instead: `Waiting for Predecessor` for an unresolved dependency, `Missing Requirement` for missing scope or an owner decision, or `External Blocked` for unavailable external access. Apply the same exact-label cleanup and re-read verification to a blocked transition.

Never inspect beyond allowed reads, infer write permission, or hide unsupported claims behind model confidence.
