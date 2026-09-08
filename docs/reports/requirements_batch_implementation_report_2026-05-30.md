# Requirements Batch Implementation Report

Date: 2026-05-30

This report explains what was implemented for each requested item, including small technical details, user-facing behavior, and the verification that was run.

## Overall Status

All requested items were either implemented or, where explicitly requested, documented as a proposal only.

The one item that was not implemented as runtime behavior was the premium paywall, because the requirement said this should only be a proposal for now. I added the proposal in `docs/proposals/premium_paywall_placement.md`.

I also did one final completion fix while writing this report: the job URL history now preserves the same job URL separately per workspace. This matters because two different users or workspaces can legitimately encounter the same job URL, and one workspace should not overwrite another workspace's history.

## Requirement 1: Incremental Career Site Scraping

### Original Need

The scraper should avoid repeatedly scraping old job URLs that were already processed before. The desired behavior is:

- First run: scrape everything available.
- Later runs: scrape only newly discovered job URLs.
- If a company has a main site and multiple related career URLs, job URLs should be centralized enough that old links can be recognized.
- The system should be able to scrape less while still providing more useful results per user.
- The user should be able to understand what happened when old URLs were skipped or source coverage was capped.

### What I Implemented

I added a persistent URL history for company career-site scraping.

The new storage is in SQLite:

- Table: `site_job_url_history`
- Migration: `009_site_job_url_history`
- Follow-up migration: `010_site_job_url_history_workspace_scope`
- Key columns:
  - `workspace_id`
  - `job_url`
  - `site_url`
  - `run_id`
  - `job_id`
  - `title`
  - `company`
  - `last_status`
  - `first_seen_at`
  - `last_seen_at`

The table now uses `(workspace_id, job_url)` as the primary key. This means the same job URL can exist once for workspace A and once for workspace B without one overwriting the other.

I added repository methods:

- `get_seen_job_urls(job_urls, workspace_id=...)`
- `record_job_url_attempts(records, run_id=..., workspace_id=...)`

These methods canonicalize URLs before checking or saving them. For example, tracking parameters are removed so the same link with `utm_source` does not look like a new job.

### How The Scraper Uses It

The company career-site scraper now accepts two callbacks:

- `seen_job_url_lookup`
- `job_url_history_callback`

During scraping, the scraper:

1. Discovers candidate job links from the career site.
2. Canonicalizes the candidate URLs.
3. Checks the persistent history for URLs already seen in the current workspace.
4. Skips those seen URLs before spending more work normalizing or scraping their pages.
5. Records what happened to each candidate URL.

The recorded statuses include:

- `skipped_seen`: the URL was already processed before.
- `accepted`: the job made it through discovery.
- `keyword_filtered`: the job was rejected by keyword filters.
- `old_posting`: the posting looked too old.
- `failed`: the scraper tried but could not process it.

This is important because the history is not just a yes/no cache. It stores what happened last time, which gives us better debugging and future reporting.

### Run Metrics Added

The stage adapter now stores company-site metrics in the run stage outcome:

- `incremental_skipped_job_urls`
- `candidate_jobs_discovered`
- `candidate_jobs_followed`
- `candidate_jobs_skipped`
- `link_cap_hits`

This means Run Review can show whether the scraper skipped old URLs or hit source link limits.

### Run Review UI Added

I added a Run Review notice that can display:

- How many previously seen job URLs were skipped.
- Whether source link caps were hit.
- Which site URLs were capped, when that data exists on the run.

This is the user-facing part of the incremental scraping work. The user can see that the scraper is doing less repeated work and why coverage might be limited.

### Files Changed

- `backend/repositories/sqlite_backed.py`
- `backend/connectors/company_career_sites.py`
- `backend/adapters/stage_adapters.py`
- `frontend/src/pages/RunDetailPage.jsx`
- `tests/test_sqlite_repositories.py`
- `tests/test_company_career_discovery.py`

## Requirement 2: Premium Upgrade Proposal Only

### Original Need

The app should make the option to convert to premium visible in the sections where it matters most. There should also be an independent reusable popup paywall. But this requirement should only be a proposal right now, not implemented.

### What I Did

I did not implement a paywall. I created a proposal document only.

The proposal recommends premium upgrade placement in:

1. Workspace run setup
2. Run Review
3. Tracker documents area
4. CV Studio

The strongest recommended first placement is Run Review, because that is where the user can directly see capped scraping coverage or skipped sources.

### Paywall Modal Shape Proposed

The proposed reusable modal would receive:

- `featureId`
- `context`
- `limitDetails`
- `returnAction`

The idea is that any premium trigger can open the same modal, and after upgrade the app can retry or continue the original action.

### File Added

- `docs/proposals/premium_paywall_placement.md`

## Requirement 3: Job-Specific Application Requirements And Document Warnings

### Original Need

Some job descriptions contain instructions that should change how the user applies. Examples:

- Send the CV without a photo.
- Upload a motivation letter.
- Upload a recommendation letter.
- Upload transcript of records.
- Upload grades.
- Upload final university certificate or degree certificate.

The user should not apply blindly when these instructions exist. The system should surface them reliably.

### What I Implemented

I added a new deterministic requirement detector:

- `backend/capabilities/tailored_documents/application_requirements.py`

It reads job fields such as:

- `title`
- `company`
- `location_raw`
- `location`
- `full_description`
- `description_text`
- `description`
- `snippet`

Then it detects:

- CV without photo instructions.
- Requested motivation or cover letters.
- Requested recommendation or reference letters.
- Requested transcripts.
- Requested grade documents.
- Requested degree or final university certificates.

### Why Deterministic First

The requirement mentioned that an AI API could assist. I did not add an LLM call here because this is a high-risk workflow: a false positive or false negative can directly affect an application. I implemented a deterministic first layer with structured evidence snippets. This is more reliable, testable, and explainable.

An AI classifier can still be added later as a second layer, but the base system now has a predictable rules engine.

### CV Photo Behavior

If the app is generating the CV and the job asks for a CV without a photo:

- The generated CV for that job disables the photo.
- The rendering seed uses no profile image for that job.
- The stored application requirements are recomputed after disabling the photo.

This means the generated CV should follow the job-specific instruction instead of blindly following the workspace default.

If the user has an uploaded or already-applied CV that appears to include a photo, the system surfaces a warning instead of silently assuming it is fine.

### Document Warnings

The API now resolves detected requested documents against the user's available documents and returns:

- `application_requirements`
- `application_warnings`

These are included on Run Review jobs and Tracker jobs.

The warnings include:

- A warning code.
- Severity.
- Human-readable title.
- Human-readable message.
- Evidence from the job description.
- Document type when relevant.

### UI Added

I added `ApplicationWarnings` UI in:

- Run Review included jobs.
- Tracker card view.
- Tracker table resource cell.

This means the warning is visible before applying and remains visible later in the tracker.

### Files Changed

- `backend/capabilities/tailored_documents/application_requirements.py`
- `backend/capabilities/tailored_documents/documents.py`
- `backend/api/server.py`
- `frontend/src/pages/RunDetailPage.jsx`
- `frontend/src/pages/TrackerPage.jsx`
- `tests/test_tailored_document_generation.py`

## Requirement 4: Modular Language Rejection Fix

### Original Need

Rejected jobs were showing a misleading reason such as "role requires French" even when the role did not require French. The logic needed to become modular for all languages and based on the user's saved language setup.

Example of desired behavior:

- If the user speaks Chinese and applies in China, do not show a random French rejection.
- If the role needs fluent English and the user does not have fluent English, the rejection should clearly say that.
- If a listing is written in an excluded language, that should be explained separately from a role requiring that language.

### What I Implemented

I rebuilt the language rules around two separate concepts:

1. Required language mismatch
2. Listing language exclusion

These are different. A job description can be written in French without requiring French. Or it can be written in English but require Spanish. The user-facing reason must not mix those up.

### Language Rule Details

The language rules now support:

- Language aliases.
- Required language extraction.
- CEFR level parsing.
- User saved language levels.
- Comparison between required level and saved level.
- Separate listing-language detection based on configured thresholds.

Examples of generated technical reasons:

- `Required language English is not listed in configured languages.`
- `English level requirement (C1) is above saved level (B2).`
- `Listing appears to be written in French above configured threshold.`

The API then maps those into customer-facing messages.

### False French Fix

I removed the German `u` umlaut signal from the French/Spanish character detection path. German words containing German characters should no longer push a job into a French rejection path.

### User-Facing Rejection Labels

The customer view can now return labels such as:

- `Required language not listed`
- `Language level not reached`
- `Language level missing`
- `Listing language excluded`

That fixes the misleading wording where the app made it sound like the role required French when it was only detecting the listing language.

### Files Changed

- `backend/capabilities/tailored_documents/language_rules.py`
- `backend/capabilities/tailored_documents/screening.py`
- `backend/capabilities/tailored_documents/prioritization.py`
- `backend/adapters/stage_adapters.py`
- `backend/api/server.py`
- `tests/test_tailored_document_generation.py`
- `tests/test_backend_api.py`

## Requirement 5: Redirect To Run Review After Starting A Run

### Original Need

When the user sets up a workspace and clicks Run, they should immediately go to Run Review so they can see the checklist loading, included jobs, rejected jobs, and then move to the tracker.

### What I Implemented

After run creation succeeds from the workspace page:

- The frontend immediately navigates to `/runs/{run.id}`.
- It passes a route state message saying the run was queued and will start automatically.
- The workspace refresh still happens, but it no longer blocks the redirect.

On the Run Review page:

- The page reads the route state.
- The success message appears directly on Run Review.

This makes the user land where the active run is actually happening.

### Files Changed

- `frontend/src/pages/WorkspacesPage.jsx`
- `frontend/src/pages/RunDetailPage.jsx`

## Secondary Requirement: Smaller And Easier CV Layout Variants

### Original Need

The React-generated CV preview looked good, but it used too much space and relied too heavily on repeated blocks. The request was to provide variations that take less space and are easier to read.

### What I Implemented

I added three compact CV templates:

- `compact_flow`
- `two_column_digest`
- `timeline_brief`

These templates reduce the amount of boxed layout and use denser visual structure.

### Template Intent

`compact_flow` is for a cleaner single-flow CV with less blockiness.

`two_column_digest` is for a more compressed CV where supporting details can sit beside the main content.

`timeline_brief` is for a scannable timeline-oriented CV with compact entries.

### Small Styling Details

I added compact rendering helpers and CSS so these templates are separate from the previous block-heavy layout.

I also set letter spacing to `0` in the generated CV CSS. This follows the frontend design rule and avoids overly stylized text that can reduce readability.

### Files Changed

- `frontend/src/lib/cvStudio.js`

## Requirement After That: Edit Generated CV From Tracker

### Original Need

The user should be able to modify the React-generated CV after it has been exported or put into the tracker, then export it again in the attractive React-generated format rather than only as a Word document.

### What I Implemented

Tracker entries now receive a `cv_studio_seed` when the backend has enough generated CV data.

In the Tracker UI:

- If a tracker item has an editable generated CV seed, an `Edit CV` action appears.
- Clicking it stashes the seed temporarily in browser storage.
- The app navigates to CV Studio.
- CV Studio consumes the seed and initializes the editor from that generated CV data.

This gives the user a path from a tracked generated CV back into the visual CV editor.

### Editor Improvements

I also added editors for content that was not previously editable enough in CV Studio:

- Projects
- Custom sections

This matters because generated CVs often contain tailored sections beyond summary, skills, and experience.

### Stale Draft Protection

CV Studio now avoids applying an old local draft when a tracker seed has just been consumed. Without this, the user could click `Edit CV` and accidentally see stale local data instead of the tracker CV they wanted to modify.

### Files Changed

- `backend/api/server.py`
- `frontend/src/lib/cvStudio.js`
- `frontend/src/pages/TrackerPage.jsx`
- `frontend/src/pages/CvStudioPage.jsx`

## Last Requirement: Fix "Available Immediately For Tailored Roles"

### Original Need

The phrase `Available immediately for tailored roles` looked obviously AI-generated and should not appear. The CV should either say a normal availability phrase, ask the user, or hide the field if it is not present.

### What I Implemented

I removed the hardcoded default phrase.

Availability now comes only from actual user/profile/document data:

- `profile.availability`
- `profile.available_from`
- `documents.availability`

If none of those exists:

- The availability line is not shown.
- The additional section does not appear just to show an invented availability phrase.

This prevents the CV from inventing availability text.

### File Changed

- `frontend/src/lib/cvStudio.js`

## Verification

I ran backend syntax checks:

```powershell
python -m py_compile backend/repositories/sqlite_backed.py backend/adapters/stage_adapters.py
```

I ran focused backend unit tests:

```powershell
python -m unittest tests.test_sqlite_repositories tests.test_company_career_discovery tests.test_stage_adapters tests.test_backend_api.BackendApiTests.test_run_customer_view_normalizes_language_rejection_messages tests.test_tailored_document_generation
```

Result:

- 51 tests ran.
- All passed.

I ran the frontend production build:

```powershell
npm --prefix frontend run build
```

Result:

- Build passed.
- Vite still reports existing large chunk warnings. These are warnings, not build failures.

## Important Notes

The paywall was intentionally not implemented because the requirement asked for a proposal only.

The application requirements detector is currently deterministic and rule-based. That was intentional for reliability. It can be extended with an AI classifier later, but the app now has structured warning data, evidence snippets, and test coverage without relying on a model call.

The URL history is workspace-scoped now. This is important because the same job URL can appear for multiple users or workspaces, and one user's run should not destroy another user's history.

The Run Review page is now the main place where the user sees the active run, including the loading/checklist state, included/rejected jobs, application warnings, and source coverage information.
