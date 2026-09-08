# Workspace Run Progress Visibility PRD

## Problem Statement

The current workspace run experience is not operationally trustworthy for long-running runs.

From the user's perspective, the failure is simple:

- a workspace can show `running` for hours with no useful explanation
- the frontend does not tell the user what stage is active, what unit of work is being processed, how much work remains, or whether the run is making forward progress
- a run can be effectively stuck while still appearing alive because the worker heartbeat continues
- stale runs can remain marked `running`, which makes the system state misleading

The current company career site acquisition path makes this worse because one run can fan out across a very large discovered-site list and spend a long time inside one blocking stage before any stage result is written.

This creates three product failures:

1. users cannot tell the difference between healthy progress and a hung run
2. users cannot estimate whether waiting is rational
3. maintainers cannot quickly diagnose whether a run is slow, stuck, stale, or overloaded

## Solution

Add useful progress reporting for workspace runs, starting with long-running acquisition stages and especially company career site sourcing.

The product should expose run progress at two levels:

- user-facing run visibility in the frontend
- operational progress and health tracking in the backend/worker layer

The system should report what is happening while work is still in progress instead of only writing status when a stage completes.

For long-running stages, the run should expose:

- current stage name and stage type
- stage start time and elapsed duration
- a progress summary in plain language
- work counters for the current stage
- recent warnings or failures that do not yet fail the full run
- whether the run still appears healthy or stale

For company career site acquisition specifically, the run should expose at minimum:

- total sites scheduled for this run
- number of sites completed
- number of sites currently being processed
- number of sites failed
- number of jobs found so far
- the current company/site being processed
- whether the run is using direct fetch or proxy fallback

## Product Goals

- Make long-running runs understandable while they are still running.
- Let users distinguish slow progress from no progress.
- Surface enough detail to explain why a company-site run may take a long time.
- Detect and expose stale or misleading `running` states.
- Give users a clear way to cancel or abandon stuck work.

## Non-Goals

- Replacing the current run engine with a separate distributed job system.
- Full historical analytics for all past runs.
- Real-time websocket infrastructure if polling can satisfy the requirement.
- Large UI redesign outside the run list/detail surfaces.

## User Stories

1. As a job seeker, I want to see what a run is doing right now, so that `running` is not a meaningless label.
2. As a job seeker, I want stage-specific progress counters, so that I can judge whether the run is moving.
3. As a job seeker, I want long-running company-site discovery to show which company or site is being processed, so that I know why the run is taking time.
4. As a job seeker, I want to see jobs found so far during acquisition, so that progress feels tangible.
5. As a job seeker, I want the UI to show when a run appears stale, so that I do not wait forever on a dead process.
6. As a job seeker, I want stale and active runs distinguished clearly, so that the system state is credible.
7. As a job seeker, I want a cancel action that works during long-running stages, so that I can stop a bad run.
8. As a maintainer, I want progress persisted during stage execution, so that state survives refreshes and process restarts.
9. As a maintainer, I want the backend to record partial progress and recent failures without failing the whole run immediately, so that diagnosis is possible.
10. As a maintainer, I want limits and defaults for company-site runs to be visible and reviewable, so that runaway runs are less likely.

## Scope

This task should cover:

- backend support for in-progress run and stage progress snapshots
- worker-side progress updates during long-running stages
- stale-run detection and status projection improvements
- frontend progress rendering on run list and run detail pages
- company career site acquisition instrumentation and guardrails

This task should also review whether the current default company-site source behavior is too broad for normal user-triggered runs and whether safer defaults are required.

## Implementation Decisions

- Progress must be written during stage execution, not only after stage completion.
- Progress data should be persisted in a backend-owned structure attached to the run or stage state, not kept only in process memory.
- The first implementation should prioritize polling-based updates using existing API patterns before introducing push transport.
- Company career site acquisition should emit incremental progress after each site completes and after meaningful internal milestones.
- The UI should prefer simple, high-signal progress language over raw debugging dumps.
- A run that still has worker heartbeat but shows no stage progress movement for too long should be surfaced as potentially stuck.
- Active runs should expose enough metadata for support and debugging without requiring direct database inspection.

## Acceptance Criteria

- Starting a long-running workspace run shows a current stage label and elapsed runtime in the UI.
- Company career site runs show total sites, processed sites, failed sites, and jobs found so far while still running.
- The UI shows the current company/site being processed for company-site acquisition.
- Refreshing the page does not lose visible progress state for an active run.
- A run detail page can distinguish `running normally`, `slow but active`, and `possibly stale` states using concrete backend signals.
- Cancelling a long-running run is reflected in the UI and honored by the worker at the next safe checkpoint.
- Stale `running` runs from abandoned or wedged execution paths can be identified and surfaced correctly instead of looking healthy forever.
- Normal successful runs still complete and persist final stage results correctly after progress instrumentation is added.

## Risks

- Writing progress too frequently could add avoidable database churn.
- Exposing too much low-level detail could turn the UI into a debug console instead of a product surface.
- Long-running HTTP fetch loops may still feel slow even with progress reporting unless default scope is reduced.
- Cancellation support may need explicit safe checkpoints in blocking acquisition loops.

## Follow-Up Questions For Implementation

- Should company-site runs be capped by default for manual user-triggered runs unless the user explicitly opts into a broad crawl?
- Should stale detection be based only on worker heartbeat age, or also on lack of progress-counter movement?
- Should run summary progress appear directly in workspace cards, or only in run list and run detail views?
- Should partial failures during acquisition be summarized live in the UI, or only counted until the run finishes?
