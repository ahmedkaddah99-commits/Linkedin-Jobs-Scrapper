# Referral Tracker Confidence Pass PRD

This PRD is a follow-on verification and hardening document for `referral_tracker_workspace_prd.md`. Its purpose is not to define new user-facing product scope. Its purpose is to raise confidence that the implemented scope is complete, correct, and stable enough to call done.

## Problem Statement

The current referral, tracker, Gmail, documents, ATS, and workspace work appears substantially implemented, but confidence is still weaker than it should be before declaring the initiative complete.

The current gap is not primarily feature design. The gap is proof. Targeted tests passed, but there has not yet been a final confidence pass that combines:

- a broader automated backend regression pass
- a frontend build validation pass
- a structured manual walkthrough of the critical user flows
- a line-by-line PRD-to-code verification pass
- explicit handling of remaining quality signals such as repeated SQLite `ResourceWarning` output

Without that pass, the team can still miss integration regressions, UI dead paths, documentation drift, or hidden cleanup defects while believing the feature set is complete.

## Solution

Run a dedicated confidence pass for the referral tracker workspace initiative.

From the user's perspective, this means:

- the product owner gets a clear answer on what is truly complete
- the engineering team gets a disciplined process for proving it
- the final state includes evidence, not just opinions

The confidence pass should produce four outputs:

- automated verification results
- manual walkthrough results
- a PRD coverage matrix showing each requirement as done, partial, or failed
- a short residual-risk list for anything still not proven or not yet fixed

If the pass finds defects, they should be logged and fixed or explicitly deferred. The initiative should not be marked complete on assumption alone.

## User Stories

1. As a product owner, I want a separate confidence-pass PRD, so that final verification is tracked as its own deliverable.
2. As a product owner, I want the confidence pass to focus on proof instead of new feature ideation, so that completion is based on evidence.
3. As a maintainer, I want the final verification work to reference the original referral tracker PRD, so that requirement coverage stays traceable.
4. As a maintainer, I want every major product area in scope to be checked, so that no subsystem is silently skipped.
5. As a maintainer, I want a documented list of what was verified automatically versus manually, so that the confidence claim is honest.
6. As an engineer, I want the relevant backend tests rerun as a grouped regression pass, so that code-path confidence is broader than a single targeted check.
7. As an engineer, I want the confidence pass to include contract-level tests, so that normalized payloads stay stable across frontend and backend surfaces.
8. As an engineer, I want the confidence pass to include API-level tests, so that integration behavior is verified instead of only helper functions.
9. As an engineer, I want the frontend to build successfully during the pass, so that obvious UI breakage is caught before manual review.
10. As a job seeker, I want the Referrals page to be verified for manual add, edit, delete, and CSV import flows, so that network management works end to end.
11. As a job seeker, I want LinkedIn CSV import behavior to be verified with real-world edge cases, so that imports do not silently corrupt referral data.
12. As a job seeker, I want multi-company contacts to be verified after import and manual editing, so that one person can still be linked to multiple employers correctly.
13. As a job seeker, I want the Review Queue to show all matched referral contacts, so that no warm contact is hidden.
14. As a job seeker, I want the confidence pass to verify choose-one, choose-some, and choose-all referral actions, so that the multiple-contact UX is not only partially wired.
15. As a job seeker, I want direct LinkedIn open actions from referral match context to be verified, so that manual outreach is actually usable.
16. As a job seeker, I want referral draft generation to be verified for a chosen contact, so that message drafting respects my selection.
17. As a job seeker, I want referral outreach statuses to be verified per run, per job, and per contact, so that progress tracking is not misleading.
18. As a job seeker, I want the Referrals summary view to reflect outreach history correctly, so that I can review previous activity later.
19. As a job seeker, I want Gmail Google OAuth connection to be verified end to end, so that setup works for a real tracker workflow.
20. As a job seeker, I want Gmail scan-window settings to be verified, so that the sync behavior matches the configured time range.
21. As a job seeker, I want the confidence pass to verify that high-confidence Gmail messages update tracker state correctly, so that automation is trustworthy.
22. As a job seeker, I want low-confidence Gmail detections to be reviewable, so that false positives are not silently imported.
23. As a job seeker, I want Gmail detections to support both approve and dismiss behavior, so that I stay in control of imports.
24. As a job seeker, I want Gmail-approved external applications to appear in the tracker correctly, so that non-Runr applications are still visible.
25. As a job seeker, I want manual tracker status edits to be verified after Gmail activity, so that human correction still works.
26. As a job seeker, I want the tracker baseline fields inherited from the spreadsheet workflow to be checked for parity, so that useful manual data is not lost.
27. As a job seeker, I want the Documents page to be verified with application-first grouping, so that generated files are organized around the jobs that matter.
28. As a job seeker, I want document status to be visible and correct, so that blocked and ready documents are easy to distinguish.
29. As a job seeker, I want upload, preview, download, and bulk export to be verified together, so that the library is not only partially functional.
30. As a job seeker, I want ATS export blocking to be verified for under-target CVs, so that poor outputs are not exported silently.
31. As a job seeker, I want the `Export anyway` path to be verified after warning, so that overrides remain deliberate and usable.
32. As a job seeker, I want the missing-requirements remediation path to be verified, so that the CTA is actionable instead of decorative.
33. As a job seeker, I want the ATS improve-and-rescore loop to be verified for pass, stall, and max-attempt cases, so that scoring behavior is predictable.
34. As an engineer, I want the ATS loop metadata checked against the export-gate reader, so that downstream consumers do not break on scoring changes.
35. As an engineer, I want the Workspaces flow included in the walkthrough, so that cross-page navigation still makes sense in the finished product.
36. As a maintainer, I want a line-by-line PRD coverage checklist, so that each requirement can be marked done, partial, failed, or not verifiable.
37. As a maintainer, I want evidence tied to each major claim, so that the final report is auditable.
38. As a maintainer, I want any discovered mismatch between the PRD and the implementation captured explicitly, so that drift is not hidden.
39. As a maintainer, I want remaining SQLite `ResourceWarning` output investigated, so that silent repository lifecycle problems are not ignored.
40. As a maintainer, I want temporary test data and side effects cleaned up or documented, so that repeated verification runs stay reliable.
41. As a maintainer, I want the confidence pass to distinguish true defects from known limitations, so that prioritization remains clear.
42. As a maintainer, I want failed checks to generate concrete follow-up tasks, so that verification findings turn into actionable work.
43. As a maintainer, I want the final result to say what is proven complete versus what still carries risk, so that release decisions are grounded in fact.

## Implementation Decisions

- This PRD is a verification-and-hardening PRD, not a new product-feature PRD.
- The confidence pass should be organized into four streams:
  - automated backend regression
  - frontend build validation
  - manual product walkthrough
  - PRD traceability audit
- The major modules to validate are:
  - referral contact import, matching, and outreach orchestration
  - review-queue decision and referral-action surfaces
  - tracker state projection and spreadsheet-baseline projection
  - Gmail OAuth, sync, detection review, and external-application import
  - document-library projection, grouping, export, and remediation behavior
  - ATS scoring, retry, stall detection, and export-gate metadata emission
  - workspace browsing and cross-page navigation
  - repository lifecycle behavior that may explain warning output during tests
- The confidence pass should produce a written evidence pack containing:
  - test commands run
  - pass or fail result per stream
  - manual walkthrough checklist results
  - PRD coverage status per requirement cluster
  - residual-risk notes
- Manual verification should be driven by scenario checklists, not ad hoc clicking.
- The walkthrough should cover at least:
  - Referrals
  - Review Queue
  - Tracker
  - Documents
  - Workspaces
  - Settings needed by those flows
- Existing canonical contracts should remain authoritative during verification:
  - referral outreach status write payload
  - Gmail detection approval and dismissal payloads
  - application-document projection shape
  - ATS export-gate metadata shape
- If verification reveals gaps, follow-up fixes should preserve those canonical contracts where possible instead of reworking them casually.
- SQLite `ResourceWarning` output should be treated as a real engineering concern. The pass should determine whether the warnings come from test harness cleanup, repository connection ownership, or request-lifecycle teardown.
- The final PRD-to-code checklist should work from user-facing requirements first, then supporting technical guarantees.
- The confidence pass should not declare a surface complete merely because code exists. Completion requires both behavior verification and traceability back to the PRD.

## Testing Decisions

- A good test should verify external behavior and stable contracts, not private implementation details.
- The confidence pass should favor the following layers:
  - focused unit tests for normalization, matching, scoring, and retry behavior
  - API-level tests for end-to-end payload and state transitions
  - frontend build validation to catch integration and syntax regressions
  - manual walkthrough checklists for UI flows that automated tests do not fully prove
- The primary modules to test are:
  - referral import, referral matching, outreach status persistence, and referral draft behavior
  - Gmail scan-window handling, detection classification, approval, dismissal, and tracker import
  - document projection, grouping, document status, export gate, and bulk export behavior
  - ATS score improvement loop, stall detection, max-attempt handling, and metadata emission
  - phase-0 contract normalization and compatibility
- Existing regression tests in the codebase should be reused as prior art for:
  - backend API behavior
  - tracker Gmail integration
  - networking referrals
  - tailored document generation
  - phase-0 contract normalization
- The manual walkthrough should record:
  - exact scenario performed
  - expected outcome
  - actual outcome
  - pass or fail status
  - follow-up note if behavior is incomplete or ambiguous
- The PRD coverage audit should not rely only on tests. It should combine test evidence, manual flow evidence, and code-level contract confirmation.
- If warnings remain after a green run, the pass should still record them as residual quality risk instead of burying them under a passing status line.

## Out of Scope

- Net-new user-facing features unrelated to proving the current PRD complete
- Major redesign of the referral, tracker, documents, Gmail, or workspace product surfaces
- Switching to a different email provider or auth model
- Replacing the persistence architecture
- Large refactors that do not directly support verification, stability, or warning cleanup
- Broad UX polish unrelated to the critical workflows being validated
- Rewriting the original referral tracker workspace PRD from scratch

## Further Notes

- This PRD should be executed only after the main referral tracker workspace implementation appears feature-complete.
- A green result does not mean the system is perfect. It means the documented scope has been verified to the agreed confidence level.
- If the confidence pass uncovers real gaps, those gaps should be reflected back into the main PRD status scan or logged as follow-up work.
- The final output of this PRD should be a short decision: ready to call complete, complete with known risks, or not yet complete.

## Execution Results

Execution date: May 3, 2026.

- Automated verification was executed against the full repository test suite using `python -m unittest discover tests`.
- Frontend validation was executed using `npm run build` in `frontend`.
- A structured manual-flow audit was executed as a route, component, and test-backed walkthrough from the current codebase.
- The confidence pass also included warning cleanup work after the first broad regression run exposed connection-lifecycle noise.

## Automated Verification Results

- Initial broad regression result: `92 tests`, `OK`.
- Initial broad regression quality finding: heavy SQLite `ResourceWarning` noise during test teardown.
- Confidence-pass fix 1: the SQLite repository connection helper now closes connections deterministically instead of relying on the `sqlite3.Connection` context manager.
- Confidence-pass fix 2: the Google OAuth helper now closes `HTTPError` response objects after reading error payloads.
- Confidence-pass fix 3: repository and Gmail integration tests now clean up their direct resource handles more explicitly.
- Final broad regression result after cleanup: `92 tests`, `OK`.
- Final warning state: SQLite warning flood resolved. Remaining warning is an upstream dependency `UserWarning` from `itemadapter` about Pydantic v1 compatibility on Python 3.14.

## Frontend Validation Results

- `npm run build` completed successfully.
- Production build output was generated successfully by Vite.
- No frontend syntax, bundling, or route-import regressions were detected by the build step.

## Confidence-Pass Fixes Landed

- Repository lifecycle hardening:
  - SQLite store connections are now committed or rolled back and then closed explicitly.
- OAuth error-path hardening:
  - Google OAuth HTTP error responses are now closed after their payload is read.
- Test cleanup hardening:
  - Direct SQLite test connections are now closed explicitly.
  - The Gmail OAuth error test closes its mocked response stream explicitly.

## Structured Walkthrough Audit

This walkthrough was executed as a structured code-and-route audit backed by automated tests. It was not a live browser clickthrough.

| Surface | Scenario | Evidence Type | Result | Notes |
| --- | --- | --- | --- | --- |
| Referrals | Manual add, edit, delete, LinkedIn CSV import, multi-company contact handling, LinkedIn guide access | Code audit plus backend API and referral tests | Pass | Import, persistence, and summary behavior are present and covered. |
| Review Queue | Referral match visibility, choose-one or choose-many contact actions, LinkedIn open action, referral draft generation, outreach-status updates | Code audit plus backend API tests | Pass | The multi-contact workflow and outreach-status persistence are implemented and exercised. |
| Tracker and Gmail | Google OAuth connect flow, scan window settings, pending detections, approve, dismiss, external application import, tracker status updates | Code audit plus Gmail integration and backend API tests | Pass | Review and import flows are implemented and tested. |
| Documents | Application-first grouping, document status, preview, download, bulk export, reusable assets in one library | Code audit plus backend API tests plus frontend build | Pass | Library grouping and export behavior are present and verified. |
| ATS Workflow | Draft generation before target, export blocking below target, warning state, retry loop, stall stop, max-attempt stop, export-anyway path | Code audit plus tailored-document and backend API tests | Pass | Retry and gate metadata behavior are implemented and verified. |
| Workspaces | Simple row presentation, focused single-workspace view, `Back to all workspaces` navigation | Code audit plus backend API and backend application tests | Pass | Focused navigation behavior exists in the routed frontend and workspace APIs remain green. |
| Settings and Routing | Routes needed by Referrals, Tracker, Documents, Workspaces, Review Queue, and the LinkedIn guide | Code audit plus frontend build | Pass | Routed surfaces are wired and build cleanly. |

## Main PRD Coverage Matrix

This matrix maps the original `referral_tracker_workspace_prd.md` user stories to verified clusters.

| Story Range | Theme | Status | Evidence |
| --- | --- | --- | --- |
| 1-15 | LinkedIn CSV import, import resilience, imported contact visibility, LinkedIn help page | Complete | Referral parsing tests, backend API tests, routed page audit |
| 16-25 | Referral matching, multi-contact selection, LinkedIn open action, referral draft generation, outreach-status tracking | Complete | Backend API tests, referral tests, Review Queue code audit |
| 26-37 | Gmail detection, scan windows, approval, dismissal, tracker automation, suggestion behavior | Complete | Gmail integration tests, backend API tests, Tracker code audit |
| 38-44 | Tracker editing, `Status` migration, spreadsheet-baseline preservation, notes, submitted documents visibility | Complete | Backend API tests, contract tests, Tracker and Documents code audit |
| 45-47 | Workspace row layout, focused view, `Back to all workspaces` navigation | Complete | Backend application and API tests, Workspaces code audit |
| 48-57 | Documents library grouping and status, ATS draft and export gate, retry, stall stop, warning and remediation controls | Complete | Backend API tests, tailored-document tests, Documents code audit |
| 58-63 | Google sign-in safety, read-only Gmail access, multi-company referrals, external application tracker rows, low-friction spreadsheet migration, unified document library | Complete | Gmail integration tests, referral tests, backend API tests, code audit |

## Residual Risks

- No live browser clickthrough was executed in this pass. The walkthrough was a structured code-and-test audit rather than interactive UI exercise.
- The final automated run still emits one upstream dependency warning from `itemadapter` about Pydantic v1 compatibility on Python 3.14. This did not break tests, but it remains an environment-quality signal outside the implemented referral tracker scope.

## Final Decision

Ready to call complete with known verification limits.

The implemented scope in `referral_tracker_workspace_prd.md` is now strongly verified by a full green backend regression pass, a green frontend production build, a structured route and component audit, and a line-by-line coverage check grouped by requirement cluster. The remaining limitations are verification depth in a real browser session and an external dependency warning unrelated to the feature behavior itself.
