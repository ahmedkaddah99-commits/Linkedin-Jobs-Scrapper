# Production fresh acquisition report

Audit date: 2026-08-10. Branch: `deployment/render-turso-r2`.

Environment inspected: remote production Turso/libSQL loaded from
`user_config/.env`; local SQLite is not production. Secret values are omitted.
API and worker final live commit: `dc19cc05298e7d69e4548793798030d3bc059eac`.

## Result

Fresh direct acquisitions for all enabled sources produced preserved raw
payloads and mapping projections. No run auto-published. The valid publication
head remains `acq_publication_5884f63297fc4f56a0fb019c7cd4f063` with 133 jobs
and no fixture jobs.

| Source | Latest production evidence | Raw / accepted | New canonical | Rejected | Closure |
|---|---|---:|---:|---:|---|
| N26 / Greenhouse | `acq_request_beab98f46ba545e5a5e347110ab37891`; `2026-08-10T17:29:43Z`; `https://boards-api.greenhouse.io/v1/boards/n26/jobs?content=true` | 87 / 87 | 0 | 0 | Complete source path; 0 closure in this run |
| Qonto / Lever | `acq_request_2132d26740114203be1fbd593e2b6e37`; `2026-08-10T17:34:30Z`; `https://api.lever.co/v0/postings/qonto?mode=json` | 35 / 35 | 0 | 0 | Complete source path; 0 closure in this run |
| Lowell / Workday | `acq_request_9e7d35dd1d2945ea9de06b2d47b81ca0`; `2026-08-10T20:49:29Z`; Workday `/wday/cxs/.../jobs` | 10 / 10 | 8 | 0 | Incomplete bounded page; no closure |
| LIQUI MOLY / Personio | `acq_request_ddf5bb82774e4b698f5a8da1c7c618f3`; `2026-08-10T20:54:42Z`; `https://liqui-moly-gmbh.jobs.personio.com/xml` | 25 / 25 | 25 | 0 | Completed XML snapshot |
| die Bayerische / Recruitee | `acq_request_068183af444845aaa3924f1636ca2510`; `2026-08-10T20:48:37Z`; `https://diebayerische.recruitee.com/api/offers?limit=100&offset=0` | 10 / 10 | 0 on repeat; earlier capture added 10 | 0 | Completed bounded page |
| RheinGroup / SmartRecruiters | `acq_request_ce81ba1b95d1483296b39db04cbc4279`; `2026-08-10T21:32:29Z`; `https://api.smartrecruiters.com/v1/companies/RheinGroup/postings?limit=10&offset=0` | 10 / 10 | 10 on first successful retry | 0 | Incomplete one-page cap; no closure |
| Siemens / generic JSON-LD | `acq_request_bf428cccf358464cacb8ab3ac7ecbbf9`; `2026-08-10T21:41:57Z`; official Siemens listing URL below | 2 / 2 | 0 on repeat; prior accepted observation retained | 0 | Incomplete bounded detail cap; no closure |

The final aggregate production state is 1,041 observations, 790 posting
versions, 201 canonical jobs, 16 canonical companies, 419 company URL rows,
32,271 provenance rows, 1,041 rule outputs, 201 completeness reports, and
7,334 report-only quality events. [P]

## Source URLs and connector behavior

### N26 / Greenhouse

- Official careers target: `https://job-boards.greenhouse.io/n26/`
- API: `https://boards-api.greenhouse.io/v1/boards/n26/jobs?content=true`
- Latest request: HTTP 200, 87 returned, 87 accepted, zero rejects.
- Source fields: ID, title, location, content/description, department/offices,
  hosted URL, application URL when supplied, and source timestamps.

### Qonto / Lever

- Official careers target: `https://jobs.lever.co/qonto`
- API: `https://api.lever.co/v0/postings/qonto?mode=json`
- Latest request: HTTP 200, 35 returned, 35 accepted, zero rejects.
- Source fields: ID, title, categories/team, location, commitment,
  workplace/salary when supplied, description, hosted/apply URL, timestamps.

### Lowell / Workday

- Official careers/ATS: `https://lowell.wd3.myworkdayjobs.com/de-DE/LowellGroup_Careers2`
- Direct API: `https://lowell.wd3.myworkdayjobs.com/wday/cxs/lowell/LowellGroup_Careers2/jobs`
- Latest request: 10 retained, 8 new canonical jobs, incomplete page warning.
- Raw Workday payloads are retained. Workday family/category, external path,
  title, location, description, detail URL, time type and remote values are
  extracted when present.

### LIQUI MOLY / Personio

- Official careers/ATS: `https://liqui-moly-gmbh.jobs.personio.com/`
- XML: `https://liqui-moly-gmbh.jobs.personio.com/xml`
- Latest request: 25 retained and 25 new; completed XML snapshot.
- Position ID/name, department/team, location, employment/type, description and
  detail URL are retained when supplied by the XML.

### die Bayerische / Recruitee

- Official careers/ATS: `https://diebayerische.recruitee.com/`
- API: `https://diebayerische.recruitee.com/api/offers?limit=100&offset=0`
- Two bounded captures retained 20 observations across the target and 10
  canonical jobs; zero rejects. Repeat observations are idempotent.

### RheinGroup / SmartRecruiters

- Official homepage: `https://www.rhein-bmw.de/`
- Careers/ATS: `https://careers.smartrecruiters.com/RheinGroup`
- API: `https://api.smartrecruiters.com/v1/companies/RheinGroup/postings?limit=10&offset=0`
- The first retries were marked uncertain because `api.smartrecruiters.com`
  was absent from the official host allowlist. The manifest now includes the
  API host; the final retry persisted 10 raw/accepted observations and 10 new
  canonical jobs, with no unresolved uncertain request.
- SmartRecruiters detail candidates are converted from API URLs to
  `https://jobs.smartrecruiters.com/RheinGroup/{posting}`. A careers index is
  not used as an Apply destination.

### Siemens / generic JSON-LD

- Official homepage: `https://www.siemens.com/`
- Careers page: `https://www.siemens.com/en-us/company/jobs`
- Listing/ATS: `https://jobs.siemens.com/en_US/externaljobs/SearchJobs/?42392=%5B67940248%5D&42392_format=17551&listFilterMode=1&folderRecordsPerPage=6`
- Final single-target request: HTTP 200, two raw/accepted observations,
  zero rejects, incomplete bounded detail snapshot, and no closure.
- JSON-LD `JobPosting` values are used for title, description, location and
  datePosted; raw listing/detail HTML is retained. A listing/index URL is not
  treated as an Apply destination. The prior accepted Siemens observation was
  reused for identity; the repeat added no semantic version.

## Fixture/test quarantine

`fixture_source` and `x` still exist as immutable source evidence. Migration
046 marks them quarantined, disabled, and excluded from normal scheduler and
quality metrics. They are not in the current publication head. No delete or
rewrite was performed. [P]

## Representative field behavior

Across the direct adapters, stored evidence covers title, external ID, source
department/team/category when supplied, Runr function/subfunction mapping,
locations, employment type, workplace arrangement, description variants,
timestamps, job-detail URL, application destination classification,
completeness and field provenance. Missing connector fields are persisted as
unknown/unsupported/inferred/conflicting states and report-only warnings; they
do not reject a record or block publication/API/UI rendering. [C][P]

The current public head intentionally remains unchanged. New jobs are visible
to admins for review and require explicit preview/publish before user exposure.

## Authenticated API/UI checks

The signed-in production session exercised the admin acquisition pages and the
user personalized feed/detail. The production checker also verified health,
readiness, the absolute frontend API base, and proxy health. Unauthenticated
401 responses were not used as evidence of authenticated response bodies. [A]

## Unresolved evidence gaps

1. Workday, SmartRecruiters and Siemens snapshots are bounded/incomplete; a
   complete source snapshot is required before lifecycle closure is authoritative.
2. Logo provider execution is intentionally disabled; zero logo rows is expected.
3. No live duplicate cluster exists for merge/split/undo canary evidence.
4. Optional typed fields remain source-dependent and confidence is not calibrated.
5. Remote backup restore is not a destructive acceptance test.
