# Production Fresh Acquisition Report

Audit date: 2026-08-10 (Europe/Berlin)
Branch: `deployment/render-turso-r2`
Environment inspected: the configured production Turso/libSQL database loaded
from `user_config/.env`. The local SQLite database is not production and was
not used for production counts. Credentials and secret values are omitted.

## Current truth

The completed Prompt 1 reprocessing remains intact. Migration 045 and the new
source-hygiene migration 046 are applied in production. The valid publication
head is still `acq_publication_5884f63297fc4f56a0fb019c7cd4f063` with 133 jobs.
The fresh N26 and Qonto imports completed without rejected observations and did
not automatically publish a new head.

The application and worker services were live on commit
`5e494dc68a7bf2b3c2bc49d6a52886110cccc2db` at the validation boundary. The
frontend remained live on `9a62e81b0ea7e3a7f02026ae07cbd56f705a0e12`.

| Area | Current truth | Evidence |
|---|---|---|
| Reprocessing | Complete; 587/587 observations, 67 batches, 5,870 fields, 2,787 warnings, 0 failures; lease empty | `acquisition_reprocessing_runs` |
| Schema | 46 migrations applied; 045 at `2026-08-10T11:47:21.395366+00:00`; 046 at `2026-08-10T14:19:41.263182+00:00` | `schema_migrations` |
| Publication | Valid head, 133 jobs; no fixture/test jobs | `acquisition_publication_head`, `acquisition_publication_jobs` |
| Lifecycle | 139 active, 7 stale, 0 closed | `canonical_jobs` |
| Fresh acquisition | N26 and Qonto completed; no new semantic versions, publications, duplicates, or closures | fresh cycle rows and deltas below |
| Fixture hygiene | `fixture_source` and `x` retained but disabled, publication-disabled, and quarantined | migration 046 and target rows |

## Changes made during validation

1. Migration 046 adds explicit `quarantined`, `quarantine_reason`, and
   `quarantined_at` target state. Fixture/test targets are disabled and removed
   from normal scheduler and quality-metric selection without deleting their
   immutable observations.
2. Completed/stalled admin imports are reconciled from terminal cycles. A
   running import is reclaimed only when its cycle lease is expired and the
   import has been stale for at least 15 minutes.
3. Remote acquisition cycle/task leases are held for at least 1,800 seconds,
   preventing a normal five-minute lease from expiring while the Turso
   projection transaction is still committing. This is a single-writer guard,
   not a parallel retry.
4. Preview construction excludes canonical jobs whose only observations are
   quarantined fixture/test targets. Preview, explicit publish, and undo
   behavior remains unchanged.

## Fresh imports

### N26 / Greenhouse

| Item | Value |
|---|---|
| Import | `job_import_870c6fab348e4aaba91dbf722df6fc39` |
| Idempotency key | `admin-acquisition-1786371852231` |
| Cycle | `acq_cycle_8fc75e5e4f5149379db22e2b4ba89c3e` |
| Request | `acq_request_424bb7aff1b548caa493633bd0b1b55f` |
| Canonical target | `https://job-boards.greenhouse.io/n26/` |
| Direct request URL | `https://boards-api.greenhouse.io/v1/boards/n26/jobs?content=true` |
| Request window | `2026-08-10T14:24:16.780837+00:00`–`14:24:18.386640+00:00` |
| Cycle complete | `2026-08-10T14:29:21.475469+00:00` |
| Import complete | `2026-08-10T14:29:22.966845+00:00` |
| HTTP / returned | 200 / 91 |
| Accepted source records | 91 |
| Distinct external IDs | 91 |
| Rejected / duplicate records | 0 / 0 |
| Canonical jobs in cycle | 91; active 91, stale 0, closed 0 |
| New / updated / unchanged | 0 / 0 / 91 |
| Closed / published | 0 / 0 |
| Raw retention | 91 non-empty raw payloads and raw hashes |

The source snapshot was complete and valid. The difference between 91 fetched
rows and current publication participation is intentional: the cycle was a
fresh verification of already-known jobs and did not auto-publish.

Observed report-only warnings: 91 each for missing direct application URL,
job-detail URL used as application URL, HTML entities in the description, and
suspicious posting timestamp; one additional `department_not_available`
warning was recorded. The warning rows did not reject or stop any job.

### Qonto / Lever

| Item | Value |
|---|---|
| Import | `job_import_df980bf7cb194bb7ab3795097449f0fe` |
| Idempotency key | `admin-acquisition-1786372234773` |
| Cycle | `acq_cycle_33efc4e694d14e87bef67306d2fa12d2` |
| Requests | `acq_request_f6c4c40d172742fcad5490a5983f016e`, then `acq_request_643767775c884950b6243e60a6687b43` |
| Canonical target | `https://jobs.lever.co/qonto/` |
| Direct request URL | `https://api.lever.co/v0/postings/qonto?mode=json` |
| First request | HTTP 200, 35 rows at `14:30:39`; projection writer exceeded the old lease and was safely resumed |
| Resumed request | HTTP 200, 35 rows at `14:43:20` |
| Cycle complete | `2026-08-10T14:45:14.667189+00:00` |
| Import complete | `2026-08-10T14:45:16.070742+00:00` |
| Raw request rows | 70 across two preserved request attempts |
| Accepted unique source records | 35 |
| Distinct external IDs | 35 |
| Rejected / duplicate records | 0 / 0 |
| Canonical jobs in cycle | 35; active 35, stale 0, closed 0 |
| New / updated / unchanged | 0 / 0 / 35 |
| Closed / published | 0 / 0 |
| Raw retention | 35 committed observations with non-empty raw payloads and hashes |

The Qonto count of 70 raw rows is transport-attempt count, not unique-job
count. The first attempt completed the HTTP request but did not commit its
projection before the old lease expired. Reclaim resumed the same import and
cycle with the same idempotency key; it did not create a second import or
duplicate projection. The second attempt committed the 35 unique records.
The only fresh quality warning was `suspicious_posting_timestamp` (35 rows).

## Source reconciliation

| Source/target | Registry state | Raw fetched rows | Accepted unique source records | Rejected (reason) | Distinct canonical jobs | Active / stale / closed from fresh cycle | Current-head jobs |
|---|---|---:|---:|---:|---:|---:|---:|
| N26 / Greenhouse | candidate, enabled | 91 | 91 | 0 | 91 | 91 / 0 / 0 | 91 |
| Qonto / Lever | candidate, enabled | 70 across 2 attempts | 35 | 0 | 35 | 35 / 0 / 0 | 42 |
| `fixture_source` | quarantined, disabled | 1 preserved historical observation | excluded | excluded from normal metrics | 1 historical | not acquired | 0 |
| `x` | quarantined, disabled | 1 preserved historical observation | excluded | excluded from normal metrics | 1 historical | not acquired | 0 |
| Other registered sources (adidas, BASF, Bosch, DHL, Siemens) | enabled but unproven | 0 in configured data | 0 | n/a | 0 | n/a | 0 |

The 42 Qonto jobs in the head include 7 older Qonto jobs already in the
publication; the fresh cycle itself contributed 35 unchanged records. N26's
head count is 91. The head is therefore 91 + 42 = 133 unique canonical jobs,
not 126 observations and not 133 source rows. There are no fresh duplicate
candidates or duplicate cluster/member rows.

The configured data after the fresh runs contains 839 immutable observations:
615 N26, 222 Qonto, and one each for `fixture_source` and `x`. The increase
from the pre-fresh boundary `2026-08-10T14:24:13.369788+00:00` was 126
observations (91 + 35). There was no increase in posting versions because all
126 records were unchanged by content hash.

## Before/after projection counts

The boundary is the creation time of the N26 fresh import. “After” is the
delta created by the N26 and Qonto fresh work; tables without a row timestamp
are shown as current totals and compared to the pre-fresh read.

| Table/read model | Before | After/current | Delta | Interpretation |
|---|---:|---:|---:|---|
| `job_source_observations` | 713 | 839 | +126 | Two complete source snapshots; immutable rows retained |
| `job_posting_versions` | 735 | 735 | 0 | No semantic content changed |
| `acquisition_field_provenance` | 22,103 | 26,009 | +3,906 | Fresh field evidence for 126 observations |
| `acquisition_rule_outputs` | 713 | 839 | +126 | One mapping output per fresh observation |
| `acquisition_completeness_reports` | 20 before boundary | 146 current | +126 | One report per fresh observation; report-only |
| `acquisition_quality_events` | 6,349 | 6,749 | +400 | 365 N26 warnings + 35 Qonto warnings |
| `canonical_company_urls` | 290 | 290 | 0 | No URL projection changed during fresh acquisition |
| `company_logo_enrichments` | 0 | 0 | 0 | No enrichment provider invoked |
| `acquisition_duplicate_clusters` | 0 | 0 | 0 | No automatic duplicate cluster created |
| `acquisition_duplicate_members` | 0 | 0 | 0 | No duplicate membership projection |
| `acquisition_publications` | 5 | 5 | 0 | No automatic preview or publication |
| `acquisition_publication_jobs` | 427 | 427 | 0 | Publication read models unchanged |
| Current publication head jobs | 133 | 133 | 0 | Valid head preserved |

The old Qonto request increased request-attempt metadata but not observations,
versions, or projections. This is why its request-level raw count is 70 while
its source and canonical count is 35.

## Representative end-to-end fields

Evidence below is from the latest fresh observation, its current posting
version, the raw payload, field-provenance rows, completeness report, and the
authenticated product surface.

| Field | N26 representative | Qonto representative |
|---|---|---|
| Job identity | External ID `7140058`; canonical `canonical_job_3113a5b27bd84545b72a261c9ee3a2d7`; version 6 | External ID `043279bd-c543-4e54-bffa-094c77f4c97b`; canonical `canonical_job_69710e8f6e4d4476b8255e503807ca02`; version 5 |
| Title / location | Senior Product Manager - Payment Processing & Settlement / Berlin | Senior Operations Project Manager / Paris |
| Source department/team | `Product - Payments`; team unavailable | `Operations & Customer Success`; team `Ops Excellence` in categories |
| Runr function/subfunction | `Product` / null; department mapping confidence 0.90 | `Customer Support` / null; department mapping confidence 0.90 |
| Employment type | Unsupported / null; raw custom field contains `Time Type: Full time` but no supported normalized mapping | `Full-time`, source field, confidence 0.80 |
| Workplace arrangement | Unsupported / null | `Hybrid`, source field, confidence 0.80 |
| Language | `en`, raw-source evidence, confidence 0.75 | Unknown; no supported source field |
| Experience | Unknown; no year/seniority evidence selected | Unknown; no year/seniority evidence selected |
| Description | Raw HTML entities retained; sanitized HTML and clean text representations stored; warning recorded | Full description stored as HTML/text; authenticated detail rendered the employer description |
| Job detail / application | Detail `https://n26.com/en-eu/careers/positions/7140058?gh_jid=7140058`; same-page detail contains `Apply for this position` at `/en-eu/careers/positions/7140058/apply?...` | Detail `https://jobs.lever.co/qonto/043279bd-c543-4e54-bffa-094c77f4c97b`; direct application `.../apply` |
| Timestamp | Source posted timestamp unavailable; suspicious timestamp warning | Source posted timestamp unavailable; suspicious timestamp warning |
| Completeness | `warning`; selected fields and unsupported/unknown states retained | `warning`; selected fields and unknown states retained |
| Company evidence | Canonical company N26; Greenhouse documentation provenance; no selected company URL row for this representative | Canonical company Qonto; Lever postings API provenance; no selected company URL row for this representative |

The N26 job-detail URL is not classified as a direct ATS application. It is an
employer job-detail fallback whose live page exposes a separate application
route. The Qonto Apply action was clicked in the authenticated product and
opened the exact Lever application URL. Careers index URLs are not used as
application destinations by `phase_b.py` destination rules.

## Fixture quarantine and publication compatibility

The two historical fixture observations remain immutable:

- `fixture_source`, external ID `a`, canonical job
  `canonical_job_539...`, `https://jobs.example.com/a`.
- `x`, external ID `a`, canonical job `canonical_job_d7...`,
  `https://x.example/a`.

Migration 046 marks both targets `quarantined=1`, `enabled=0`,
`publication_enabled=0`, `maturity_state=quarantined`, and
`quarantine_reason=fixture_or_test_target`. They are excluded from future
acquisition and normal quality metrics without deleting evidence. The current
valid head contains zero fixture jobs, so the conditional exclusion preview
was not needed and no preview was silently promoted. The code path for an
explicit preview now excludes quarantined-only canonical jobs and existing
preview/publish/undo tests remain passing.

## Authenticated API/UI checks

Using the repository-supported authenticated browser session (not an
unauthenticated 401 probe):

- `/admin/acquisition/sources` rendered the authenticated source registry and
  showed N26 and Qonto as enabled candidate sources. The admin queue action was
  exercised for each source and the imports completed through the worker.
- `/jobs` rendered the authenticated user feed with “Showing 25 of 133 jobs”,
  search, location, workplace, experience, category, and sort controls.
- The authenticated Qonto detail rendered title, company, description,
  location, full-time type, workplace, and Apply. Clicking Apply opened
  `https://jobs.lever.co/qonto/043279bd-c543-4e54-bffa-094c77f4c97b/apply`.
- The N26 employer detail rendered the separate application link described
  above. No application was submitted.

Raw authenticated response bodies are not claimed from direct browser fetch;
the browser DOM is the authenticated contract evidence. Public unauthenticated
HTTP checks are not substituted for these checks.

## Required validation

Passed focused tests: 42 tests and 4 subtests in mapping contracts, quality,
admin imports, unified acquisition, scheduler, and catalog suites. These cover
Greenhouse and Lever mapping, raw-payload retention, bounded pagination and
complete-snapshot closure safety, source-to-canonical reconciliation,
application destination classification, publication preview/publish/undo,
and fixture quarantine.

## Remaining evidence gaps and limitations

- Five registered employer career-site targets are enabled but unproven and
  have no observations in this configured database; they were not silently
  acquired as part of the N26/Qonto baseline.
- Greenhouse did not provide a direct application URL in the fresh payload;
  the current fallback is verified as a live same-page employer detail with an
  application route, but the connector should persist that child application
  URL when available.
- N26 employment type, workplace arrangement, and experience remain
  unsupported/unknown despite a raw custom `Time Type` field; Qonto language and
  experience remain unknown.
- No logo enrichment rows exist and the representative companies have no
  selected company URL row; enrichment and company-source URL policy remain
  incomplete.
- The production access diagnostic still reports a pre-existing malformed
  frontend bundle API-host token (`${n}`) and a ScrapeOps proxy timeout. Direct
  ATS acquisition and authenticated app pages succeeded; these are separate
  operational limitations.

## Recommended implementation sequence

1. Persist connector capability snapshots and Greenhouse same-page application
   child URLs; add explicit source timestamp and closure semantics.
2. Add raw-retention coverage metrics and a bounded remote projection heartbeat
   so transaction duration is observable before lease pressure.
3. Model company-source aliases and selected homepage/careers/ATS URL evidence;
   then add one approved logo/enrichment provider with refresh/terms controls.
4. Add reversible duplicate decisions and cross-source syndication rules with
   review-only defaults.
5. Version the public field contract, then expose supported function,
   workplace, language, experience, provenance, and completeness states in API,
   admin, and user filters.
6. Resolve the frontend API-host bundle diagnostic and add authenticated
   production contract tests to deployment gates.
