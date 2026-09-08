# Public Job Index And User-Level Posting URL Dedupe

Date: 2026-05-31

This report formalizes and implements the corrected scraping and deduplication flow.

## Summary

The system now separates three concepts that were previously too easy to mix:

1. Public job discovery
2. User/workspace matching
3. User tracker/application deduplication

The corrected rule is:

```text
A public posting URL can be known globally.
A user can only have that posting URL once as an actionable tracker/application job.
Multiple workspaces can encounter the same posting internally, but they must not create duplicate tracker rows for the same user.
```

Hard deduplication is based on the canonical posting URL. The system should not hard-dedupe by title/company, because the same role title can legitimately be posted again, posted in another city, or posted under another requisition.

## Corrected Terminology

I stopped treating this as a temporary cache.

The correct term is:

```text
public job index
```

This is persistent backend storage, not temporary memory. It stores public facts discovered from career sites and ATS sources so later runs can avoid unnecessary detail-page scraping.

## Public Job Index

The public job index stores public posting facts such as:

- Canonical posting URL
- Source site URL
- Source group URL, when available
- Last workspace/run that saw it
- Job ID
- Title
- Company
- Location
- Last scrape status
- Active status
- First seen time
- Last seen time
- Last verified time
- Serialized job payload

The SQLite table used for this is:

```text
site_job_url_history
```

Despite the old name, the table now behaves as a public job index keyed by:

```text
job_url
```

not:

```text
workspace_id + job_url
```

This is important because the public posting belongs to the public source, not to one workspace.

## Why The Previous Workspace Scope Was Wrong

The previous workspace-scoped key prevented one workspace from overwriting another workspace's history, but it also implied the wrong model:

```text
same job URL + different workspace = separate job
```

That is not correct for tracker/application behavior.

The corrected model is:

```text
same job URL + same user = one actionable tracker job
same job URL + many workspaces = internal sightings only
same job URL + many users = each user may independently match and track it once
```

## How The Public Job Index Is Reused

The scraper does not blindly surface old indexed jobs.

A job from the public job index is reused only when the current career-site scan still discovers that posting URL on the current listing/source page.

The flow is:

1. Fetch or read the current career-site listing page.
2. Extract posting URLs from the current source page.
3. Ask the public job index whether any of those URLs already have stored job details.
4. If a posting URL is currently present on the source page and has indexed details, reuse the indexed details.
5. If a posting URL is new or has no usable indexed details, fetch the detail page and normalize it.
6. Run the current user's workspace filters separately.
7. Save/update the public job index with the latest sighting.

This means the app avoids unnecessary detail-page scraping while still allowing another user/workspace to see the job.

## Active Job Understanding

This implementation does not claim impossible certainty.

The strongest practical guarantee in this pass is:

```text
If the current source scan still lists the posting URL, the job can be considered currently visible on that source.
```

The system therefore does not reuse a public job just because it exists in the index. It reuses it only when the URL appears in the current source scan.

Future strengthening can add deeper verification:

- Detail URL returns 200.
- Detail page still contains apply controls.
- ATS API says the job is open.
- Page does not contain "job no longer available" wording.
- Posting disappears from the source listing and is marked inactive.

The current implementation stores fields needed for that direction:

- `active_status`
- `last_seen_at`
- `last_verified_at`
- `last_status`

## User-Level Tracker Dedupe

Tracker/application dedupe is separate from public scraping.

The hard rule is:

```text
one user + one canonical posting URL = one actionable tracker/application job
```

The backend now prevents duplicate tracker approvals for the same user and canonical posting URL.

This applies across workspaces.

Example:

1. User has Workspace A for Product Owner Germany.
2. User has Workspace B for Remote Product Roles.
3. The same posting URL appears in both.
4. Workspace A creates the tracker job first.
5. Workspace B later finds the same URL.
6. The second job is not allowed to become a second actionable tracker job.

## Same Title In Another City

The system should not hard-dedupe this:

```text
Product Owner - Berlin
Product Owner - Cairo
```

if the posting URLs are different.

That is why the hard tracker dedupe uses canonical posting URL, not title/company.

Title/company can still be useful for soft warnings later, but it should not be used to prevent a user from seeing or tracking a genuinely different posting.

## Sister URL Understanding

The shared meaning of sister URLs is:

```text
Different career URLs or ATS URLs that belong to the same employer hiring surface.
```

Examples:

```text
https://company.com/careers
https://company.com/careers/jobs
https://jobs.company.com
https://company.greenhouse.io
https://company.lever.co
https://company.com/en/careers
https://company.com/de/careers
```

These URLs may be separate technical entry points, but they can represent the same company's job source.

Sister URLs are useful for public discovery grouping. They are not separate permission to create duplicate tracker jobs for the same user.

## Backend-Only Visibility

The public job index is backend behavior.

The user should not see implementation details such as:

- Cache hit
- Indexed posting reused
- Previously seen URL skipped
- Internal public job index state

The user should see normal product behavior:

- Valid jobs
- Rejected jobs when relevant
- Tracker rows
- Application warnings
- High-level source coverage limits when a configured cap affects coverage

I removed the previous Run Review wording that exposed "previously seen job URLs skipped."

## Implemented Code Changes

### Job Identity

File:

```text
backend/domain/job_identity.py
```

Added:

- `canonical_posting_url`
- `posting_url_identity_key`
- URL-field ordering through `POSTING_URL_FIELDS`

Changed:

- Hard dedupe no longer uses title/company by default.
- Title/company signature remains available, but it is not used for hard dedupe unless explicitly requested.

### Public Job Index Storage

File:

```text
backend/repositories/sqlite_backed.py
```

Added/changed:

- `site_job_url_history` now has a public job index shape.
- Added migration `011_site_job_url_history_public_index`.
- `get_seen_job_urls` is global, not workspace-scoped.
- Added `get_cached_job_postings`.
- `record_job_url_attempts` stores serialized job payloads and active/verification metadata.

### Scraper Reuse Flow

File:

```text
backend/connectors/company_career_sites.py
```

Added/changed:

- Added `cached_job_lookup`.
- Known URLs are no longer hidden from later users/workspaces.
- If the current listing page still exposes a known URL, cached details can be reused.
- Reused indexed jobs still go through the current workspace keyword/date filtering.
- Fresh jobs still get normalized from their detail page.
- Recorded status `cache_reused` for reused public-index entries.

### Stage Adapter

File:

```text
backend/adapters/stage_adapters.py
```

Added:

- Stage-level callback from scraper to `get_cached_job_postings`.
- Metric `public_index_reused_job_urls`.

### Tracker/Application Dedupe Guard

File:

```text
backend/application/services.py
```

Added:

- Per-user lookup of existing actionable tracker posting URLs.
- Backend guard that blocks approving/tracking the same canonical posting URL twice for the same user.
- Auto-approval duplicate handling. Duplicate generated jobs are marked as duplicate instead of approved.

### Tracker Read Dedupe

File:

```text
backend/api/server.py
```

Added:

- Tracker read-side dedupe by canonical posting URL.
- Older stored duplicate reviews do not produce duplicate tracker rows.
- Run Review hides jobs whose review decision is `duplicate`.

### Frontend Visibility Correction

File:

```text
frontend/src/pages/RunDetailPage.jsx
```

Changed:

- Removed user-facing "previously seen URLs skipped" wording.
- Kept high-level company-site link-cap coverage notice.

## Tests Added Or Updated

Updated:

```text
tests/test_job_dedupe.py
```

Coverage:

- Same title/company with different posting URLs is not hard-deduped.

Updated:

```text
tests/test_sqlite_repositories.py
```

Coverage:

- Public job index stores URL globally.
- Workspace ID no longer controls whether a URL is considered seen.
- Cached posting details can be loaded.
- Migration `011_site_job_url_history_public_index` is applied.

Updated:

```text
tests/test_company_career_discovery.py
```

Coverage:

- The scraper reuses indexed job details without hiding that job from the run.
- Only the new uncached URL is normalized from the detail page.

Updated:

```text
tests/test_backend_api.py
```

Coverage:

- Same user cannot approve/track the same canonical posting URL twice across two workspaces.
- Tracker returns one row for that posting.

## Final Flow

The intended full backend flow is now:

```text
Company source or sister URL is scanned
        |
        v
Current listing page yields posting URLs
        |
        v
Public job index is checked for those exact canonical URLs
        |
        +--> URL has indexed details and is currently listed
        |       reuse details
        |
        +--> URL is new or weakly indexed
                fetch detail page and normalize
        |
        v
Workspace/user filters run
        |
        v
Public job index is updated
        |
        v
Before tracker approval/application:
same user + canonical posting URL is checked
        |
        +--> already tracked
        |       block duplicate actionable tracker job
        |
        +--> not tracked
                allow one tracker/application record
```

## What This Does Not Do Yet

This implementation does not yet perform full inactive-job cleanup.

It does not delete old public index entries. That is intentional. Old entries are useful for history, diagnostics, and dedupe.

A later cleanup policy can archive or compact old inactive rows after a long retention period, but it should not be treated like temporary RAM cache eviction.

This implementation also does not yet group sister URLs into a first-class `company_source_id`. The current logic supports the public index and URL-level reuse; a future slice can add explicit company source grouping for reporting and source management.
