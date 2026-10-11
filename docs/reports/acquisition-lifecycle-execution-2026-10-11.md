# Acquisition lifecycle execution — 11 October 2026

Owner request: finish the acquisition lifecycle end to end and verify it in the deployed Runr app. The attached prior request defines the acceptance criteria below. This is an execution/evidence record, not a replacement Linear backlog.

## Acceptance and implementation

- [ ] SQLite-backed enrichment and matching-fact workers: existing connection authority, atomic claims, transactional fact writes/acknowledgements, lease recovery, current-version guards. Tests exercise real SQLite concurrency and rollback.
- [ ] One bounded Nemo request per new job/version combines source-supported classification, English descriptions, ATS/skills and metadata. Reuse existing acceptable output; deterministic blue-collar rejection first. Multiple independently stated experience requirements retain their distinct tags.
- [ ] Recurrent 30-day discovery retention and blue-collar removal: enforce eligibility before new publication; bounded maintenance with dry-run receipts; preserve customer-owned application/document references.
- [ ] Storage: retain R2 for objects and unattended backups per the latest owner instruction. Bound release/export/temp history with active references protected.
- [ ] Align manifest, publisher, enrichment and matching releases and SQLite configuration, preserving finite budgets, producer state, employer exclusions and locks.
- [ ] Run bounded collection → publication → enrichment → matching → authenticated customer Jobs acceptance; recover interrupted claims and disposition missing source without blind paid retries.
- [ ] Restore dedicated timers after acceptance, observe scheduled execution, verify public readiness and monitoring. Legacy scheduler stays disabled.
- [ ] Record exact deployed revisions, tests, receipts, counts, costs, and external blockers.

## Baseline

Source worktree: `implementation/acquisition-lifecycle-2026-10-11`, starting `06c34987`. Python verified 3.12.7. Shared checkout has unrelated dirty documentation and is preserved.

Live observation 18:49 UTC: API and customer worker active; 67 GiB free; acquisition paused through 17 October; catalog head valid with 41,730 memberships. Manifest worker has a recorded release/schema mismatch. Enrichment and matching scripts still contain direct Turso HTTP persistence. API serves `cv-assistance-687599a4`; customer worker serves `external-jobs-96868ca0`. These component releases must be preserved during acquisition deployment.

## Decisions

- Continue the owner-authorized implementation and deployment; no repeat approval for restarting the requested lifecycle after verification.
- Use existing shared database abstraction rather than another SQLite driver/connection implementation.
- Treat 30 days as a rolling interval, not calendar-month subtraction.
- Unknown source facts remain unknown; one-call cost bounds must not cause invented metadata.
- Owner superseded the Drive request: keep R2; Drive setup and local-object migration are removed from this change.

## Execution evidence

SQLite/concurrency, lifecycle, enrichment and publication-focused checks passed. Existing HTTP publication regression remains covered; the publisher wrapper now selects that path only for a configured remote database. Worker tests were updated to require one combined request and zero supplemental requests for already acceptable output. Live schema head confirmed `080_external_job_preview_quota`. Deployment acceptance remains in progress.
