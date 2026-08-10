# Final production acquisition acceptance report

Acceptance update: 2026-08-10. Branch: `deployment/render-turso-r2`.

Evidence labels: `[C]` code, `[S]` schema, `[T]` tests, `[P]` configured
production Turso/libSQL query, `[A]` live API/authenticated UI, `[U]` uncertain
or not live-proven. Production evidence came from the remote database loaded
from `user_config/.env`; local SQLite was not treated as production. No secrets
are shown.

## Acceptance result

The deployed acquisition path is live and ready for user testing. All five
deferred production items are implemented: the four ATS connectors are direct
and enabled, company homepage/careers/ATS identity is configured, the frontend
API/proxy diagnostic is healthy, the official-website logo provider is
configured with execution intentionally deferred, and Siemens generic/JSON-LD
has completed a fresh bounded production capture. [C][P][A]

The current publication head was not promoted by acquisition. It remains the
valid 133-job head with zero fixtures. Quality/completeness warnings remain
report-only. [P]

## Deployed commit and migration level

| Item | Result |
|---|---|
| API/worker deployed commit | `dc19cc05298e7d69e4548793798030d3bc059eac` |
| Branch | `deployment/render-turso-r2` |
| Database | Production Turso/libSQL; 93 tables |
| Latest migration | `047_product_completion_wave` |
| Required migrations | 045 leases, 046 fixture quarantine, 047 product completion: all applied |
| API health/readiness | `/health`, `/health/live`, `/health/ready` passed |
| Frontend origin | Absolute `https://runr-api.onrender.com/v1`; proxy health `ok` |
| Queue consumers | One `runr-worker`; duplicate `runr-process-next` cron persistently `/bin/true` |

## Production counts

| Entity/read model | Count |
|---|---:|
| Canonical companies | 16 |
| Company profiles | 14 |
| Company URL rows | 419 |
| Immutable observations | 1,041 |
| Immutable posting versions | 790 |
| Canonical jobs | 201 |
| Field provenance | 32,271 |
| Rule outputs | 1,041 |
| Completeness reports | 201 |
| Quality/warning events | 7,334; report-only |
| Logo enrichment rows | 0; execution deferred intentionally |
| Duplicate clusters/members/decisions | 0 / 0 / 0 |
| Publications/publication rows | 5 / 427 |
| Current publication head | 133 jobs |
| Fixtures in current head | 0 |
| Unresolved uncertain requests | 0 |

Lifecycle state: active 170, stale 4, closed 7, unknown 20. Unknown is used
for incomplete bounded source snapshots; it is not treated as an empty source
or a closure instruction. [P]

## Reprocessing and idempotency proof

The original run `reprocess_ef912ccf2e9f44ca974222fe60732e55` with key
`unified-mapping-production-2026-08-10` is completed at
`observation_ffc65009d257463e95239c00166d6ab7`. It processed 587 observations
in 67 batches, produced 5,870 field mappings, 585 historical repairs and 2,787
warnings, with zero failed observation IDs and an empty lease. Reinvoking the
same key returned `idempotent_replay=true`; no semantic version, duplicate
projection, publication row, or immutable observation was added by replay. [P]

## Fresh source reconciliation

| Connector/source | Request path | Final source rows | Canonical result | Lifecycle safety |
|---|---|---:|---:|---|
| Greenhouse / N26 | Official Greenhouse API | 702 total; latest 87 | N26 101; latest repeat unchanged | Complete source path |
| Lever / Qonto | Official Lever API | 257 total; latest 35 | Qonto 43; latest repeat unchanged | Complete source path |
| Workday / Lowell | Workday CXS API | 10 | Lowell 8; 8 new | Incomplete bounded page; no closure |
| Personio / LIQUI MOLY | Personio XML | 25 | LIQUI MOLY 25; 25 new | Completed XML snapshot |
| Recruitee / die Bayerische | Recruitee offers API | 20 | die Bayerische 10 | Repeat idempotent; no closure claim beyond snapshot |
| SmartRecruiters / RheinGroup | SmartRecruiters API | 20 | RheinGroup 10; first successful retry 10 new | Incomplete one-page cap; no closure |
| Generic JSON-LD / Siemens | Official Siemens listing + detail links | 5 | Siemens 1; final repeat added no version | Incomplete bounded detail cap; no closure |

Every fresh observation has raw source evidence and mapping projections. Source
count differences are explained by bounded page caps, repeat captures, and
canonical identity reuse; observations are not counted as unique current jobs.
No fresh import promoted a publication.

## Connector capability matrix

| Connector | Can provide | Cannot guarantee |
|---|---|---|
| Greenhouse | ID, title, location, content, department/offices, hosted/apply URL, timestamps | Employment, workplace, language, salary, experience completeness |
| Lever | ID, title, categories/team, location, commitment, workplace/salary when supplied, description, URLs | Applicant counts, closure semantics, consistent language/experience |
| Workday | Job family/category, external path, title, location, description, detail URL, time type/remote when supplied | Tenant-specific fields and complete snapshot under cap |
| Personio | Position ID/name, department/team, location, employment/type, description, detail URL | Stable XML fields and optional metadata across tenants |
| Recruitee | Offer ID/title, department/team, location, description, typed metadata when supplied, URLs | Complete pagination and all typed metadata under a bounded page |
| SmartRecruiters | ID/title/department/location/description, detail/apply candidates, raw API payload | Complete catalog from a one-page cap and all optional typed fields |
| Generic/JSON-LD | Title, description, location, datePosted, canonical/detail/apply candidates, raw HTML | Stable API schema and complete typed metadata/catalog |

## User-facing field and filter matrix

| Field/filter | Feed/detail | Admin | Current source/semantic behavior |
|---|---|---|---|
| Title/company/location | Yes | Yes | Structured source preferred; provenance retained |
| Detail URL/application URL | Yes | Yes | Direct application destination preferred; careers indexes are not Apply URLs |
| Description | Yes, clean text/detail representations | Yes, raw/sanitized/evidence | Raw payload retained; public output is sanitized/product-shaped |
| Department/team/function/subfunction | When present | Yes | Connector metadata and versioned taxonomy; unknown/inferred explicit |
| Employment/workplace | When present | Yes/filter | Source-dependent taxonomy; report-only if missing |
| Language/experience/salary | When present | Yes/filter | Structured or explicit labelled evidence; optional and source-dependent |
| Posted/freshness/lifecycle | Yes | Yes/filter | UTC timestamps; partial snapshots cannot close jobs |
| Completeness/warnings | Selected product fields | Full warnings/rules | Never blocks crawling, publication, API, or rendering |
| Company homepage/careers/ATS | Company detail where stored | Companies/inspection | Five configured source companies have selected official URL triples |
| Logo | Shape supported, no current logo rows | Provider state | Provider configured, execution off, logos intentionally later |
| Search and typed filters | User feed supports current product filters | Admin adds publication/warning/duplicate filters | Raw evidence remains admin-only |

## Company URL/logo coverage

`canonical_company_urls` contains five selected-primary homepage rows, five
careers rows, and five ATS jobs rows, each `validation_status=configured_official`.
The five configured source companies are Siemens, Lowell, LIQUI MOLY, die
Bayerische, and RheinGroup. RheinGroup homepage is
`https://www.rhein-bmw.de/`; careers/ATS is
`https://careers.smartrecruiters.com/RheinGroup`.

`official_website` is configured as the company enrichment provider in
`render.yaml`. The execution switch remains off, so zero logo enrichment rows
is expected and no logo coverage is claimed. [P]

## Duplicate workflow proof

The duplicate service and local test suite cover candidate generation,
distinct/ignore, unsafe merge/split rejection, merge/split plans, and undo
while preserving immutable observations and versions. Production has no natural
duplicate cluster, member, or decision, so a live merge/split/undo canary was
not fabricated. Automatic merge remains disabled. [T][P][U]

## Authenticated API/UI results

The authenticated production session rendered the admin acquisition pages and
the personalized user feed/detail and exercised their supported controls. The
live checker verified production health/readiness, the absolute API bundle
origin, and proxy health. Unauthenticated 401 checks were not treated as
authenticated body validation. [A]

## Tests and deployment

- Project interpreter verified: `.venv\\Scripts\\python.exe`, Python 3.12.7.
- Connector/scheduler/admin/JSON-LD tests passed; latest focused runs passed.
- Ruff passed on changed backend files.
- Frontend unit tests: 148 passed; build passed; ESLint passed with zero
  warnings. The package has no `lint` script, so that command is not reported as
  a code failure.
- API and worker are live on the commit listed above; API pre-deploy migration
  completed.

## NOT YET COMPLETE

1. Workday, SmartRecruiters, and Siemens need a complete source snapshot
   contract before their bounded captures can authorize closure/reactivation.
2. Logo provider execution and logo rows are intentionally deferred until the
   provider/budget/cache/rollback approval is supplied.
3. No naturally occurring production duplicate cluster exists for a live
   merge/split/undo canary.
4. A standalone company-source entity, full alias decision history, calibrated
   confidence, and automated remote restore drill remain future scope.

## LIVE AND READY TO TEST

1. Admin: open `/admin/acquisition` and review Overview, Sources, Jobs,
   Companies, Rules, Reprocessing, Publication, and Duplicates.
2. Admin: select Workday, Personio, Recruitee, SmartRecruiters, or Siemens,
   review the bounded plan, start an import, inspect raw/evidence/warnings, and
   confirm no automatic publication.
3. Admin: open Companies and verify homepage, careers, ATS URL types and
   provenance for Siemens, Lowell, LIQUI MOLY, die Bayerische, and RheinGroup.
4. User: open Personalized Jobs, search/filter by location, function,
   employment, workplace, language, experience, salary, and freshness; open a
   detail page and verify the Apply action targets a job destination rather
   than a careers index.
5. User: verify the current feed contains intended published jobs and no
   `fixture_source` or `x` records.
