# Referral, Tracker, Workspace, Documents, and ATS Gate PRD

## Problem Statement

Runr already has parts of the job-search workflow in place, but several user-facing areas are still unreliable or unclear.

From the user's perspective:

- LinkedIn referral connections should be importable directly from the file LinkedIn provides, without manual cleanup.
- Referral matches should show all useful people at a company, not hide options or show stale contacts.
- The application tracker should reflect real application status, including jobs applied to outside Runr.
- Gmail should help detect outside applications and status updates without reading unrelated personal email.
- The tracker should preserve the important fields from the existing manual Excel workflow.
- Workspaces should be easy to browse and focus on one at a time.
- Documents should be organized around applications, not exposed as a generic technical artifact dump.
- Final CV export should be gated by ATS score quality, while still letting the user override after a clear warning.

The core problem is that the current app has useful pieces, but it does not yet maintain reliable product state for referrals, applications, documents, and workspace navigation.

## Solution

Build a product-facing workflow that makes Runr behave like a complete application-management system:

- Import LinkedIn connections from the real `Connections.csv` export without requiring manual cleaning.
- Treat each new LinkedIn upload as the current source of truth for referral contacts.
- Show imported contacts and all referral matches clearly.
- Let the user open a matching person's LinkedIn profile directly from the stored profile URL.
- Track referral outreach manually without sending LinkedIn messages automatically.
- Use Gmail through Google OAuth to discover likely external applications and application-status updates, with user approval where needed.
- Treat the old Excel `applied?` column as the basis for a real `Status` field.
- Use the existing Excel tracker structure as the baseline data model for the app tracker.
- Simplify workspace browsing into a list and focused workspace detail view.
- Turn the documents area into an application document library.
- Add an ATS score gate before final CV export.

## Verified Baseline

- Phase 0 contract alignment already exists in code and must remain the stability boundary for this work: `workspace_configuration_v2`, `candidate_asset_descriptor`, `rejected_job_review`, `mail_connection`, `referral_relationship`, `tracker_application`, `gmail_application_detection`, `application_document`, and `ats_export_gate`.
- The LinkedIn connections help flow should remain an app-native page linked from Referrals, not a detached HTML artifact.
- Review Queue referral badges and outreach draft generation already exist as product concepts and should be hardened, not replaced with a disconnected side flow.
- The tracker, documents, referrals, and workspace surfaces should remain separate user-facing areas so each one can evolve without collapsing back into a generic artifacts view.

## External Setup and Dependencies

- Gmail sync should use Google OAuth as the canonical connection flow, with Gmail API access and read-only scope.
- OAuth refresh and access tokens must be stored through the app's secret storage layer and never returned raw to the client.
- Mail connection state must persist authorization state, sync cursor or `history_id`, last sync summary, and last sync error.
- Legacy IMAP-password support may remain only as a migration fallback. It is not the target end-user experience for this PRD.

## Implementation Status Scan

This status snapshot reflects a codebase scan plus targeted test execution on May 3, 2026. Python dependencies from `requirements.txt` were installed, the remaining PRD streams were run sequentially, and the targeted test slices for contracts, referrals, Gmail review, documents, and ATS scoring all passed.

### Done

- LinkedIn CSV import is implemented with real-header scanning, note skipping, split-header tolerance, missing-email support, upload-order preservation, re-upload deactivation, and safe company matching.
- Referrals UI exists for manual contacts, LinkedIn CSV import, multi-company contacts, LinkedIn URLs, inactive-contact display, and the LinkedIn export help page.
- Review Queue now supports explicit referral-contact selection when multiple matches exist, direct LinkedIn open actions from the matched context, referral draft generation for a chosen contact, and outreach-status tracking per `run_id`, `job_id`, and `contact_id`.
- Gmail OAuth tracker sync is implemented, including Google start/callback flow, scan-window settings, inbox sync, Gmail detection approval, Gmail detection dismissal, and creation of external tracker applications from approved detections.
- Tracker UI exists with status editing, notes, email-confirmed toggle, external-application rows, and an Excel-compatible baseline row projection.
- Workspace browsing is implemented as a list plus focused single-workspace view with a `Back to all workspaces` action.
- Documents library exists with upload, preview, download, bulk export, rejected-jobs review, application-first grouping, first-class document-status display, and an ATS remediation CTA that leads to actionable next steps.
- ATS tailored-document generation includes an improve-and-rescore loop with a 3-attempt cap, early stop on score stall, and export-gate metadata persistence.
- Phase 0 shared contracts exist in code and are exposed through the phase-0 contract catalog.
- Referral outreach-status writes now accept the same canonical payload shape used by the frontend and API tests.

### Partial

- The tracker preserves a broad Excel-compatible baseline row, but exact parity with the original manual workbook is not proven by the current repo scan.
- Targeted tests pass, but they emit repeated `ResourceWarning` messages about unclosed SQLite connections under Python 3.14. That is a cleanup concern rather than a feature gap.

### Not Done Yet

- No remaining PRD feature gaps were found in this pass beyond the verification-only notes above.

## Parallel Delivery Plan

The remaining work can be done in parallel, but not as five separate streams. The first two unfinished items belong together because they share the same referral and review-queue surfaces. The safest split is one short contract pass followed by four workers.

### Phase 0: Contract Pass

One owner should land this first. It is intentionally small and exists to reduce merge chaos in `backend/api/server.py`.

Required outputs:

- Freeze the referral selection contract used by Review Queue:
  - each matched contact payload should include `contact_id`, `name`, `linkedin_url`, `can_refer`, and current `outreach_status`
  - referral-draft generation should continue to accept an explicit `contact_id`
- Freeze the referral outreach-status contract:
  - keep `run_id`, `job_id`, `contact_id`, and `outreach_status` as the canonical write payload
  - keep `Not contacted`, `Contacted`, `Replied`, `Referral offered`, and `No referral` as the canonical values
- Freeze the document projection contract:
  - document entries should expose a primary application grouping key
  - document entries should expose a first-class `document_status` field
  - existing group labels and bulk-export semantics should remain backward-compatible where possible
- Freeze the ATS loop output contract:
  - continue writing `ats_score`, `ats_target_score`, `ats_attempt_count`, `ats_max_attempts`, and `missing_requirements`
  - add an explicit stall signal if needed, but do not break the existing export-gate reader
- Install Python dependencies from `requirements.txt` before stream work starts so test execution is unblocked.

### Worker A: Referrals and Outreach UX

Scope:

- Build the full UI flow for choosing exactly which referral contact to act on when multiple matches exist.
- Add the frontend workflow for referral outreach-status tracking per application and per contact.
- Add a direct open-LinkedIn-profile action in the matched referral context.

Primary ownership:

- `frontend/src/pages/ReviewQueuePage.jsx`
- `frontend/src/pages/ReferralsPage.jsx`
- referral-related blocks in `backend/api/server.py`
- referral selection and draft behavior in `backend/application/services.py`
- referral API and UI tests in `tests/test_backend_api.py`

Boundaries:

- This worker owns referral behavior only.
- It should not change Gmail tracker logic.
- It should not restructure the Documents page.

### Worker B: Gmail Detection Review

Scope:

- Add a dismiss flow for low-confidence Gmail detections.
- Tighten the Gmail review UX around pending detections.
- Improve Gmail filtering where possible without replacing the current sync architecture.

Primary ownership:

- `frontend/src/hooks/useTracker.js`
- `frontend/src/pages/TrackerPage.jsx`
- Gmail integration sections in `backend/api/server.py`
- `backend/capabilities/tracker/email_integration.py`
- Gmail-related tests in `tests/test_tracker_gmail_integration.py`
- Gmail-related API tests in `tests/test_backend_api.py`

Boundaries:

- This worker owns tracker email-review behavior only.
- It should not take ownership of referral UI.
- It should not change document-library grouping.

### Worker C: Documents by Application

Scope:

- Rework the document-library experience so application or job grouping is primary.
- Add a first-class document-status field to the user-facing library.
- Keep bulk export, preview, download, and rejected-jobs review intact while improving application context.
- Wire the `Review missing requirements` CTA to a meaningful remediation path once the ATS metadata contract is frozen.

Primary ownership:

- `frontend/src/pages/ArtifactsPage.jsx`
- document presentation in `frontend/src/pages/RunDetailPage.jsx` if needed
- document projection helpers and document endpoints in `backend/api/server.py`
- `backend/domain/phase0_contracts.py` only if the application-document contract needs additive fields
- document API tests in `tests/test_backend_api.py`

Boundaries:

- This worker owns document projection and document UI.
- It should consume ATS metadata, not own the ATS improvement engine itself.
- It should not own Gmail review logic.

### Worker D: ATS Improvement Engine

Scope:

- Implement the improve-and-rescore loop for tailored CV generation.
- Retry improvement up to 3 times.
- Stop early when score improvement stalls.
- Persist the metadata already consumed by the export gate so the current gate UI and API remain compatible.

Primary ownership:

- `backend/capabilities/tailored_documents/*`
- related orchestration or runtime wiring under `backend/orchestration/*` if required
- ATS-specific contract additions in `backend/domain/phase0_contracts.py` only if strictly necessary
- ATS-related API tests in `tests/test_backend_api.py`
- pipeline or service tests closest to the tailored-documents workflow

Boundaries:

- This worker owns backend scoring and retry behavior.
- It should avoid frontend document-library work.
- It should avoid referral and Gmail tracker surfaces.

### Shared Merge Rules

- `backend/api/server.py` is the main merge hotspot. Workers should reserve separate route/helper regions and avoid moving unrelated functions.
- Worker A owns referral and review-queue route changes in `backend/api/server.py`.
- Worker B owns tracker email-integration route changes in `backend/api/server.py`.
- Worker C owns document projection and document endpoint changes in `backend/api/server.py`.
- Worker D should avoid `backend/api/server.py` unless the existing export-gate reader must be extended.

### Recommended Merge Order

1. Land Phase 0 contract pass.
2. Merge Worker B or Worker A next. They are largely independent.
3. Merge the other of Worker A or Worker B.
4. Merge Worker D so ATS metadata behavior is stable.
5. Merge Worker C last if its document-status or remediation UX depends on the final ATS metadata shape.

### Why This Split

- Worker A bundles the two unfinished referral tasks because both depend on the same matched-contact UI and the same referral payloads.
- Worker B is isolated to tracker email review and can move without waiting on referrals or documents.
- Worker C is isolated to document projection and UI, but should avoid owning ATS internals.
- Worker D is mostly backend and can move independently as long as the ATS metadata contract is frozen first.

## Execution Board

This board turns the parallel-delivery plan into concrete implementation tasks. Each worker has a bounded write scope, explicit deliverables, and acceptance criteria.

Execution result on May 3, 2026:

- Phase 0 was verified after dependency install.
- Worker A completed with a referral outreach-status API compatibility fix and passing referral tests.
- Worker B was verified green by Gmail integration and dismissal tests.
- Worker C was verified green by documents-library and ATS export-gate tests.
- Worker D was verified green by tailored-document generation and ATS loop tests.

### Phase 0 Checklist

Deliverables:

- Confirm the referral-selection payload used by Review Queue includes:
  - `contact_id`
  - `name`
  - `linkedin_url`
  - `can_refer`
  - `outreach_status`
- Confirm the referral outreach-status write contract remains:
  - `run_id`
  - `job_id`
  - `contact_id`
  - `outreach_status`
- Confirm document projection exposes:
  - an application grouping key
  - a first-class `document_status`
  - backward-compatible group labels for existing document filters
- Confirm ATS loop output writes metadata already consumed by the gate:
  - `ats_score`
  - `ats_target_score`
  - `ats_attempt_count`
  - `ats_max_attempts`
  - `missing_requirements`
  - optional stall metadata if needed
- Install Python dependencies from `requirements.txt` so test execution is not blocked.

Acceptance criteria:

- The contract pass lands without changing unrelated UX.
- Existing referral, tracker, and documents payloads stay backward-compatible where possible.
- Tests can import and run after dependency setup.

### Worker A Board: Referrals and Outreach UX

Primary files:

- `frontend/src/pages/ReviewQueuePage.jsx`
- `frontend/src/pages/ReferralsPage.jsx`
- referral sections of `backend/api/server.py`
- `backend/application/services.py`
- referral API tests in `tests/test_backend_api.py`

Deliverables:

- Add explicit referral-contact choice when more than one match exists for a job.
- Let the user open a matched contact's LinkedIn profile directly from the review context.
- Add a frontend control for referral outreach statuses:
  - `Not contacted`
  - `Contacted`
  - `Replied`
  - `Referral offered`
  - `No referral`
- Preserve draft generation without automatic LinkedIn sending.

Acceptance criteria:

- Review Queue shows all matching contacts for a company.
- The user can choose exactly which contact to use for a referral draft.
- Outreach status changes persist per `run_id`, `job_id`, and `contact_id`.
- At least one frontend/API test covers multi-contact selection and outreach-status persistence.

### Worker B Board: Gmail Detection Review

Primary files:

- `frontend/src/hooks/useTracker.js`
- `frontend/src/pages/TrackerPage.jsx`
- Gmail integration routes in `backend/api/server.py`
- `backend/capabilities/tracker/email_integration.py`
- `tests/test_tracker_gmail_integration.py`
- Gmail-related API tests in `tests/test_backend_api.py`

Deliverables:

- Add dismiss support for low-confidence or unwanted Gmail detections.
- Keep approve/import support intact.
- Improve pending-detection review UX so status is clear and actions are explicit.
- Tighten Gmail filtering where safe without replacing the existing sync model.

Acceptance criteria:

- A pending detection can be approved or dismissed.
- Dismissed detections do not reappear in the same sync result workflow unless re-detected freshly.
- Existing high-confidence auto-update behavior still works.
- At least one test covers detection dismissal behavior.

### Worker C Board: Documents by Application

Primary files:

- `frontend/src/pages/ArtifactsPage.jsx`
- `frontend/src/pages/RunDetailPage.jsx` if needed
- document projection helpers in `backend/api/server.py`
- additive document-contract updates in `backend/domain/phase0_contracts.py` only if required
- document API tests in `tests/test_backend_api.py`

Deliverables:

- Make application or job grouping the primary library view.
- Add a first-class `document_status` field in the documents surface.
- Preserve upload, preview, download, and bulk export behavior.
- Wire the `Review missing requirements` CTA to a real remediation path.

Acceptance criteria:

- Users can see documents grouped by application or job.
- Each document card or row shows document status.
- Bulk export still works with the new grouping model.
- The ATS remediation CTA leads somewhere actionable instead of being a dead button.

### Worker D Board: ATS Improvement Engine

Primary files:

- `backend/capabilities/tailored_documents/*`
- supporting orchestration or runtime wiring under `backend/orchestration/*` if needed
- additive ATS-contract changes in `backend/domain/phase0_contracts.py` only if required
- ATS-related API tests in `tests/test_backend_api.py`
- tailored-documents tests closest to the scoring and generation flow

Deliverables:

- Implement a CV improve-and-rescore loop.
- Retry improvement up to 3 attempts.
- Stop early when score improvement stalls.
- Persist the metadata needed by the existing export gate and documents UI.

Acceptance criteria:

- The loop stops when the target score is reached.
- The loop stops after 3 failed attempts.
- The loop stops when the score no longer improves.
- Export-gate behavior continues to work using the emitted metadata.

### Sequential Run Order For A Single Chat

If one implementation chat is executing the remaining work serially instead of multiple workers:

1. Complete Phase 0 contract pass and dependency install.
2. Execute Worker A.
3. Execute Worker B.
4. Execute Worker C.
5. Execute Worker D.
6. Run targeted tests after each stream and a final regression pass at the end.

## User Stories

1. As a job seeker, I want to upload the LinkedIn connections CSV exactly as LinkedIn gives it to me, so that I do not need to manually clean the file.
2. As a job seeker, I want Runr to find the real LinkedIn table header inside the CSV, so that extra LinkedIn text before the table does not break the import.
3. As a job seeker, I want empty rows in the LinkedIn CSV to be ignored, so that blank lines do not create bad referral contacts.
4. As a job seeker, I want rows with missing email addresses to import successfully, so that LinkedIn contacts without shared emails are still useful.
5. As a job seeker, I want names with commas or special characters to import correctly, so that real international names are preserved.
6. As a job seeker, I want LinkedIn profile URLs from the CSV to be saved, so that I can open a connection's profile directly.
7. As a job seeker, I want job titles and positions from the CSV to be saved, so that I can judge who might be useful for a referral.
8. As a job seeker, I want connected dates from the CSV to be saved, so that I can understand how recent a relationship is.
9. As a job seeker, I want a new CSV upload to update my referral network, so that Runr reflects my current LinkedIn connections.
10. As a job seeker, I want contacts missing from a new upload to be hidden from future matches but preserved in history, so that old outreach records are not lost.
11. As a job seeker, I want to see a simple success message after import, so that I know the upload worked without reviewing an unnecessary summary step.
12. As a job seeker, I want to see my imported LinkedIn connections in the Referrals section, so that I can verify what Runr imported.
13. As a job seeker, I want the imported connections list to show name, company, position, LinkedIn URL, and connected date, so that I can spot bad imports.
14. As a job seeker, I want a full help page explaining how to export LinkedIn connections, so that I can complete the upload without external instructions.
15. As a job seeker, I want the help page linked from the upload screen, so that help is available exactly where I need it.
16. As a job seeker, I want referral matching to use exact company matches first, so that obvious matches are reliable.
17. As a job seeker, I want referral matching to support safe close company matches, so that `Stripe Inc.` can match `Stripe`.
18. As a job seeker, I want risky company matches to be avoided, so that `Meta` does not match unrelated companies such as `Metabolic Health GmbH`.
19. As a job seeker, I want all matching connections at a company to be shown, so that no referral option is hidden.
20. As a job seeker, I want to choose all, some, or one matching connection to contact, so that I control outreach.
21. As a job seeker, I want a direct button to open a matching person's LinkedIn profile, so that I can message them manually.
22. As a job seeker, I want Runr to optionally draft a referral message, so that outreach is faster.
23. As a job seeker, I do not want Runr to send LinkedIn messages automatically, so that I stay in control and avoid unsafe automation.
24. As a job seeker, I want to track referral outreach status per job and contact, so that I know who I contacted and what happened.
25. As a job seeker, I want referral outreach statuses such as `Not contacted`, `Contacted`, `Replied`, `Referral offered`, and `No referral`, so that referral progress is clear.
26. As a job seeker, I want Gmail-connected external applications to be detected, so that jobs I applied to outside Runr can still appear in my tracker.
27. As a job seeker, I want to choose how far back Gmail should scan, so that I can import only the period I care about.
28. As a job seeker, I want Gmail scan options such as now, 1 month, 2 months, and 3 months, so that setup is simple.
29. As a job seeker, I want Runr to scan only likely application emails, so that unrelated personal email is not searched unnecessarily.
30. As a job seeker, I want Runr to prefer application, recruiting, career, candidate, and ATS email signals, so that detected jobs are more accurate.
31. As a job seeker, I want detected external applications to be shown before import, so that false positives are not silently added.
32. As a job seeker, I want to approve which Gmail-detected applications are imported, so that my tracker stays clean.
33. As a job seeker, I want Gmail to update a job to `Applied` when it finds a reliable application confirmation, so that the tracker stays current.
34. As a job seeker, I want Gmail to detect interview emails, so that the tracker can move jobs to `Interviewing`.
35. As a job seeker, I want Gmail to detect rejection emails, so that the tracker can move jobs to `Rejected`.
36. As a job seeker, I want Gmail to detect offer emails, so that the tracker can move jobs to `Offer`.
37. As a job seeker, I want unclear Gmail detections to become suggestions instead of automatic updates, so that Runr does not make wrong status changes.
38. As a job seeker, I want to edit application status manually, so that I can correct or override automation.
39. As a job seeker, I want the old Excel `applied?` field to become a proper `Status` field, so that the tracker is clearer.
40. As a job seeker, I want status values including `Not applied`, `Applied`, `Interviewing`, `Rejected`, `Offer`, `Withdrawn`, and `Unknown`, so that applications can be tracked realistically.
41. As a job seeker, I want the app tracker to preserve the important fields from my existing Excel workflow, so that I do not lose my manual process.
42. As a job seeker, I want to track company, role, location, links, description, generated documents, status, and notes, so that Runr replaces the useful parts of the spreadsheet.
43. As a job seeker, I want notes to remain editable, so that I can add human context to each application.
44. As a job seeker, I want documents sent for each application to be visible, so that I know what I submitted.
45. As a job seeker, I want each workspace shown as a simple row, so that the workspace list is easy to scan.
46. As a job seeker, I want clicking a workspace to open only that workspace, so that I am not confused by other workspaces while scrolling.
47. As a job seeker, I want a `Back to all workspaces` button, so that I can return to the workspace list easily.
48. As a job seeker, I want the Documents section to show documents grouped by job or application, so that files are connected to real use cases.
49. As a job seeker, I want document name, type, related job, created date, status, and open/download actions, so that documents are easy to manage.
50. As a job seeker, I want document types such as original CV, tailored CV, cover letter, transcript, certificate, and other, so that documents are categorized clearly.
51. As a job seeker, I want draft CVs to be created before the ATS target is reached, so that Runr can iterate and improve them.
52. As a job seeker, I want final CV export blocked until the ATS target is reached, so that low-quality CVs are not accidentally submitted.
53. As a job seeker, I want the default ATS score target to be 90%, so that the quality threshold is clear.
54. As a job seeker, I want Runr to improve and rescore the CV up to a fixed retry limit, so that it does not loop forever.
55. As a job seeker, I want Runr to stop after 3 failed improvement attempts or when the score stops improving, so that I get a clear decision point.
56. As a job seeker, I want a warning if the target cannot be reached, so that I understand the best score and what is missing.
57. As a job seeker, I want options to review missing requirements, edit inputs, try again, or export anyway, so that I remain in control.
58. As a job seeker, I want to connect Gmail through Google sign-in, so that I never enter my mailbox password into Runr.
59. As a job seeker, I want Gmail access limited to read-only mailbox scanning, so that tracker sync feels safe.
60. As a job seeker, I want one referral contact to be linked to multiple companies, so that referral opportunities reflect real career changes.
61. As a job seeker, I want approved Gmail detections of outside applications to create tracker rows even when no Runr run created them, so that external applications are not lost.
62. As a job seeker, I want the tracker table to preserve familiar Excel columns while making `Status` the primary field, so that spreadsheet migration stays low-friction.
63. As a job seeker, I want generated job-specific files and reusable supporting documents to appear together in the Documents library, so that every application asset lives in one place.

## Required Data Baseline

- Referral data should use a person-first model: one contact, one LinkedIn URL, optional relationship note, lifecycle state, source metadata, and one or more company entries with role title and referral eligibility.
- Tracker data should support both Runr-created applications and Gmail-imported external applications, with manual editing available in both cases.
- The tracker should project a user-facing `Status` field while keeping a legacy-compatible `applied?` projection for Excel continuity.
- Baseline tracker and export identity fields to preserve are `run_date`, `run_timestamp`, `job_id`, `title`, `company`, `location_raw`, `keyword`, `posted_time_text`, and `posted_age_hours`.
- Baseline tracker and export prioritization fields to preserve are `applicant_count`, `priority_rank`, `priority_rule`, `easy_apply_status`, `Status`, and `applied?`.
- Baseline tracker and export link and enrichment fields to preserve are `apply_link`, `apply_link_source`, `linkedin_link`, `link`, `enrich_status_code`, and `enrich_error`.
- Baseline tracker and export content and document fields to preserve are `full_description`, `cv_professional_summary`, `cv_professional_experience`, `cv_strategic_initiatives`, `cv_skills`, `cv_education`, `tailored_cv`, `cv_docx`, `cv_pdf`, `tailored_cv_docx`, `pdf_generation_error`, and `doc_generation_error`.
- Document library entries should cover both application-scoped generated files and reusable candidate assets, with type, related application, source scope, download action, and created-at metadata.
- ATS gate data should preserve `target_score`, `best_score`, `attempt_count`, `max_attempts`, `missing_requirements`, `gate_state`, `can_export_final`, `export_anyway_allowed`, and warning text shown to the user.

## Implementation Decisions

- Build or refine a deep LinkedIn connection import module with a stable interface: accept uploaded CSV content and return parsed contacts plus import results.
- The LinkedIn import module must scan for the real header row: `First Name`, `Last Name`, `URL`, `Email Address`, `Company`, `Position`, and `Connected On`.
- Rows before the real LinkedIn header are ignored.
- Multiline LinkedIn notes before the real table are ignored even when they contain commas, quoted blocks, or header-like text.
- Split header rows such as `Email` followed by `Address` are treated as a valid LinkedIn header when the resulting logical header matches the expected schema.
- Empty rows inside and at the end of the file are ignored.
- A row is skipped only when it has no usable person name and no company.
- Missing email is valid.
- Special characters, commas in names, LinkedIn profile URLs, company names, positions, and connected dates are valid.
- LinkedIn import preserves the uploaded file order and does not impose an arbitrary connection-count cap.
- A new LinkedIn upload is the source of truth for current referral contacts.
- Contacts still present in a new upload are updated.
- Contacts newly present in a new upload are added.
- Contacts missing from a new upload are marked inactive, not deleted.
- Inactive contacts are excluded from new referral matching but remain available for historical outreach records.
- The canonical referral model is one person with one or more company relationships, not one flat contact record per company.
- Imports should merge same-person LinkedIn rows into the richer person-plus-companies relationship shape where possible.
- Build or refine a company-name matching module with exact matching first and safe close matching second.
- Company matching should normalize casing, punctuation, and common legal suffixes where safe.
- Company matching must avoid ambiguous or substring-only false positives.
- Referral matching must return all active contacts that safely match the application company.
- Referral outreach state is tracked per application and referral contact.
- Referral outreach does not send LinkedIn messages automatically.
- Referral UI exposes the saved LinkedIn profile URL as a direct open-profile action.
- Review Queue should continue to show referral badges for matched jobs and expose referral-draft generation from that same review context.
- The LinkedIn export guide should be implemented as a normal app page, using app components and styling, not as standalone pasted HTML.
- The tracker should use the existing manual Excel workflow as the baseline data model.
- The old `applied?` meaning becomes the app `Status` field.
- Status values are `Not applied`, `Applied`, `Interviewing`, `Rejected`, `Offer`, `Withdrawn`, and `Unknown`.
- The tracker should project both `Status` and legacy-compatible `applied?` values from the same canonical application status.
- Gmail connection uses `google_oauth` as the canonical auth strategy and read-only Gmail access as the canonical permission scope.
- Mail connection state must separate connection status, authorization state, token references, and sync cursor or `history_id` state.
- Gmail scanning is limited to likely application-status emails.
- The canonical Gmail scan-window keys are `now`, `last_1_month`, `last_2_months`, and `last_3_months`.
- Gmail-detected external applications are presented to the user before import.
- High-confidence Gmail status changes may update applications automatically.
- Unclear Gmail detections become suggested updates requiring user approval.
- Gmail detection is limited to application confirmations, interviews, rejections, and offers.
- Approved Gmail detections may create external tracker applications when no matching Runr application exists.
- External tracker applications remain manually editable after import.
- Referral-related Gmail detection is out of scope for now.
- Workspace list UI should show simple rows with minimal information.
- Workspace detail UI should show only the selected workspace and include a return action.
- Documents should be modeled as user-facing application documents plus reusable candidate assets, not just backend artifacts.
- Documents library should group application-scoped generated files and reusable candidate assets in one user-facing surface, with bulk export where files have download paths.
- Final CV export should require the configured ATS score target unless the retry limit fails and the user explicitly chooses to export anyway.
- ATS improvement stops after 3 failed attempts or when score improvement stalls.
- When the ATS gate remains blocked after retries, the warning should include the best score reached and the missing requirements that prevented the target from being met.

## Testing Decisions

- Tests should focus on external behavior and user-visible outcomes, not internal implementation details.
- CSV import tests should cover:
  - extra LinkedIn text before the header
  - multiline note blocks before the header
  - header-like text inside quoted notes before the real header
  - exact header detection
  - split header rows that still form the valid LinkedIn schema
  - empty rows before, inside, and after data
  - missing emails
  - names with commas
  - special characters
  - profile URLs
  - connected dates
  - invalid rows
  - no artificial contact-count cap
  - upload-order preservation
  - re-upload marking absent contacts inactive
- Referral matching tests should cover:
  - exact company matches
  - safe suffix/casing/punctuation matches
  - false-positive prevention
  - multiple matches returned without caps
  - one person linked to multiple companies
  - inactive contacts excluded from current matches
- Referral outreach tests should cover:
  - per-job/per-contact status changes
  - direct profile URL preserved
  - review-queue referral badge visibility
  - draft generation offered without automatic sending
- Gmail tracker tests should cover:
  - Google OAuth start, callback, reconnect, and disconnect behavior
  - selected scan window respected
  - likely application email filtering
  - query fallback when Gmail rejects the first filtered message-list request
  - external application suggestions before import
  - approved external-application import into tracker rows
  - high-confidence status updates
  - unclear detections requiring approval
  - no referral-status updates from Gmail
- Tracker tests should cover:
  - Excel-compatible baseline fields represented in app data
  - `applied?` migration or mapping to `Status`
  - `Status` and `applied?` projection staying in sync
  - manual status edits
  - imported external applications remaining editable
  - notes persistence
- Workspace UI tests should cover:
  - list displays multiple workspaces as rows
  - selecting one workspace hides the others
  - back action returns to all workspaces
- Documents tests should cover:
  - documents grouped by application
  - reusable candidate assets shown alongside generated application documents
  - document metadata visible
  - document types represented correctly
  - bulk export across downloadable files
  - open/download actions available
- ATS gate tests should cover:
  - draft generation before target is reached
  - final export blocked under target
  - improvement retry limit
  - warning shown after failure
  - warning includes best score reached and missing requirements
  - export anyway allowed after warning

Prior art already exists in the codebase for backend API tests, application service tests, referral import tests, tracker email integration tests, frontend page tests, and repository tests. New tests should follow those existing styles.

## Out of Scope

- Automatic LinkedIn message sending.
- LinkedIn account OAuth or direct LinkedIn API integration.
- Scraping LinkedIn messages.
- Gmail scanning for referral conversations.
- Fully automatic import of every Gmail-detected application without user review.
- Replacing the existing job scraping pipeline.
- Replacing ScrapeOps.
- Automating job applications.
- Building a complete CRM for all professional contacts.
- Redesigning the entire app shell outside the affected areas.
- Changing the company career URL discovery crawler unless required to connect tracker data.

## Further Notes

- The LinkedIn connection upload guide provided by the user should be treated as content direction, not as final app code. It should be converted into app-native React and restyled to match Runr.
- The existing manual Excel workbook is the source of truth for tracker baseline fields.
- The product should bias toward user control where automation can be wrong: Gmail detections, ambiguous matches, and ATS export overrides.
- The product should bias toward automatic behavior where the decision is deterministic: LinkedIn header detection, empty-row cleanup, inactive contact marking, and preserving all valid imported contacts.
- The strongest implementation opportunity is to create deep, independently testable modules for LinkedIn CSV import, company matching, Gmail application detection, tracker status transitions, document library projection, and ATS export gating.
