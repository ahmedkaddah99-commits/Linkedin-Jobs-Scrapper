# Production data-pipeline implementation report

Audit/update: 2026-08-10. Branch: `deployment/render-turso-r2`.

This report supersedes earlier implementation snapshots. Evidence is marked
`[C]` code, `[S]` schema, `[T]` tests, `[P]` configured production Turso query,
`[A]` live API/UI, and `[U]` not live-proven. The inspected environment is the
remote production Turso/libSQL target loaded from `user_config/.env`; local
SQLite was not used as production evidence. No credentials are reproduced.

## Deployed result

| Component | Deployed commit / result |
|---|---|
| API | `dc19cc05298e7d69e4548793798030d3bc059eac`, live |
| Worker | `dc19cc05298e7d69e4548793798030d3bc059eac`, live |
| Frontend | production API origin pinned to `https://runr-api.onrender.com/v1`; frontend bundle/proxy diagnostic passed |
| Migrations | 045, 046, 047 applied; latest is `047_product_completion_wave` |
| Production database | Turso/libSQL; 93 tables observed |
| Logo provider | `RUNR_COMPANY_ENRICHMENT_PROVIDER=official_website` configured in Render; execution remains `0` by design |
| Duplicate queue launcher | Render `runr-process-next` command persistently changed to `/bin/true`; only `runr-worker` remains a queue consumer |

## Implementation changes now in force

1. Workday, Personio, Recruitee, and SmartRecruiters are registered in the
   server-owned manifest, use direct bounded connector paths, retain raw
   payloads, and are available to production admin imports. [C][P]
2. Generic/JSON-LD acquisition is registered for Siemens with a bounded
   listing/detail contract. A fresh production single-target run returned HTTP
   200, retained two observations, and completed as an intentionally incomplete
   snapshot without closure. [C][P]
3. Company identity now preserves configured homepage, careers, and ATS URL
   types as `configured_official` selected-primary rows. RheinGroup now has the
   verified homepage `https://www.rhein-bmw.de/` in addition to its
   SmartRecruiters careers/ATS URL. [C][P]
4. SmartRecruiters now allowlists its official API host
   `api.smartrecruiters.com`; before this fix, the request succeeded but the
   post-response host policy marked the request uncertain. [C][P]
5. The frontend API origin is absolute and pinned; the live production bundle
   and `/v1/health/proxy` diagnostic both pass. [C][A]
6. Safe exception-class diagnostics are recorded for future uncertain external
   outcomes without persisting secrets or raw payloads. [C][T]
7. The provider is configured but logo execution is deliberately deferred, so
   zero logo rows is an intentional state rather than a missing provider
   configuration. [C][P]

## Production counts and before/after delta

The baseline is the controlled post-reprocessing count captured before the
fresh connector wave. The final count includes the fresh direct imports and
the Siemens/RheinGroup verification runs. Immutable observations and posting
versions were not edited or deleted.

| Table/read model | Baseline | Final | Delta | Interpretation |
|---|---:|---:|---:|---|
| `canonical_companies` | 11 | 16 | +5 | New source-company identities |
| `canonical_company_profiles` | not captured in baseline table | 14 | — | Profile rows present; optional values can be unknown |
| `canonical_company_urls` | 290 | 419 | +129 | Source/job URL evidence and configured official URL rows |
| `job_source_observations` | 961 | 1,041 | +80 | Fresh source observations; immutable |
| `job_posting_versions` | 735 | 790 | +55 | New semantic versions only where stable content/identity required |
| `canonical_jobs` | 146 | 201 | +55 | New canonical identities from fresh connector records |
| `acquisition_field_provenance` | 29,791 | 32,271 | +2,480 | Additive mapping evidence |
| `acquisition_rule_outputs` | 961 | 1,041 | +80 | One current mapping output per observation |
| `acquisition_completeness_reports` | 146 | 201 | +55 | Report-only per canonical job |
| `acquisition_quality_events` | 7,133 | 7,334 | +201 | Report-only warnings; no ingestion gate |
| `company_logo_enrichments` | 0 | 0 | 0 | Provider configured, execution intentionally off |
| `acquisition_duplicate_clusters` | 0 | 0 | 0 | No automatic or manual production duplicate cluster |
| `acquisition_duplicate_members` | 0 | 0 | 0 | No live duplicate canary |
| `acquisition_duplicate_decisions` | 0 | 0 | 0 | No live merge/split/undo decision |
| `acquisition_publications` | 5 | 5 | 0 | No fresh import auto-published |
| `acquisition_publication_jobs` | 427 | 427 | 0 | Public read model unchanged |
| Current publication-head jobs | 133 | 133 | 0 | Current head preserved; fixture jobs 0 |
| Uncertain requests | released before final check | 0 | — | No unresolved external outcome remains |

The final lifecycle distribution is active 170, stale 4, closed 7, unknown 20.
The 20 unknown states correspond to incomplete bounded source snapshots and are
not silently treated as closed or empty. [P]

## Per-source reconciliation

| Source / target | Source URL or API | Final observations | Canonical jobs by company | Snapshot/result |
|---|---|---:|---:|---|
| N26 / Greenhouse | `https://boards-api.greenhouse.io/v1/boards/n26/jobs?content=true` | 702 | N26 101 | Direct complete runs; fresh verification returned 87 rows, 0 rejects, 0 new in the final N26/Qonto run |
| Qonto / Lever | `https://api.lever.co/v0/postings/qonto?mode=json` | 257 | Qonto 43 | Direct complete runs; fresh verification returned 35 rows, 0 rejects, 0 new |
| Lowell / Workday | `https://lowell.wd3.myworkdayjobs.com/de-DE/LowellGroup_Careers2` and `/wday/cxs/.../jobs` | 10 | Lowell 8 | Direct, 10 retained, 8 new, incomplete bounded snapshot; no closure |
| LIQUI MOLY / Personio | `https://liqui-moly-gmbh.jobs.personio.com/` and `/xml` | 25 | LIQUI MOLY 25 | Direct, completed XML snapshot, 25 new, 0 rejects |
| die Bayerische / Recruitee | `https://diebayerische.recruitee.com/` and `/api/offers` | 20 | die Bayerische 10 | Two direct bounded captures, 0 rejects; second capture unchanged |
| RheinGroup / SmartRecruiters | `https://careers.smartrecruiters.com/RheinGroup`; API `https://api.smartrecruiters.com/v1/companies/RheinGroup/postings?limit=10&offset=0` | 20 | RheinGroup 10 | Final direct run completed request persistence, retained 10 jobs, 10 new on first successful retry; incomplete page cap, no closure |
| Siemens / generic JSON-LD | `https://jobs.siemens.com/en_US/externaljobs/SearchJobs/?42392=%5B67940248%5D&42392_format=17551&listFilterMode=1&folderRecordsPerPage=6` | 5 | Siemens 1 | Final single-target run HTTP 200, 2 raw/observed rows, 0 rejects, 0 new after prior accepted observation; bounded detail cap, no closure |
| Fixtures | `fixture_source`, `x` | 2 | 1 + 1 | Preserved, quarantined, disabled for normal acquisition/quality/publication |

The final direct SmartRecruiters request was persisted at approximately
`2026-08-10T21:32:29Z` and the final Siemens single-target request at
approximately `2026-08-10T21:41:58Z`; both have no unresolved uncertain request.
The multi-target attempt that stopped after Siemens dispatch was isolated and
released before the single-target retry. [P]

## Reprocessing and duplicate-launcher proof

The exact production run remains:

| Item | Final evidence |
|---|---|
| Reprocessing ID | `reprocess_ef912ccf2e9f44ca974222fe60732e55` |
| Idempotency key | `unified-mapping-production-2026-08-10` |
| State/checkpoint | completed at `observation_ffc65009d257463e95239c00166d6ab7` |
| Processed | 587 observations, 67 batches, 5,870 fields |
| Historical repairs/warnings | 585 / 2,787 |
| Failed observation IDs | none |
| Lease | owner and expiry empty |
| Same-key replay | `idempotent_replay=true`; no semantic version or duplicate projection added |

The duplicate operational root was a stale Render `runr-process-next` cron
service plus local Codex-launched process copies. The repository’s lease and
private-call safeguards stopped projection duplication; the exact Render cron
service was identified by its `./deploy/start.sh process-next` command and is
now persistently `/bin/true`. The unrelated API, worker, backend, and
deployment processes were not terminated. [P]

Reprocessing before/after projections show no duplicate semantic versions,
publication rows, or duplicate clusters. Provenance, rule, completeness, and
quality rows are additive evidence projections. [P]

## Company identity, enrichment, and logos

The configured official URL rows are:

| URL type | Validation | Selected-primary rows |
|---|---|---:|
| Homepage | `configured_official` | 5 |
| Careers | `configured_official` | 5 |
| ATS jobs | `configured_official` | 5 |
| Job detail/source | `not_validated` | source/job evidence rows, not company primary URLs |

The five configured source companies with complete official URL triples are
Siemens, Lowell, LIQUI MOLY, die Bayerische, and RheinGroup. N26 and Qonto
company profiles existed before this source wave but their current profile
payloads remain sparse in optional fields. The standalone company-source entity
and complete alias decision history remain unmodeled. [P][U]

`official_website` is configured as the enrichment provider in `render.yaml`.
Execution is disabled by `RUNR_COMPANY_ENRICHMENT_ENABLED=0`, so logo rows are
zero and no logo claim is made. The next safe step is provider approval and a
bounded enrichment canary, not an automatic production fill. [C][P]

## API, admin, and user-facing behavior

The authenticated admin session verified Overview, Sources, Jobs, Companies,
Rules, Reprocessing, Publication, and the bounded source controls. The
authenticated user session verified personalized job feed/detail rendering and
application actions. Unauthenticated HTTP 401 responses were not treated as
authenticated body evidence. [A]

The public serializers expose canonical title, company, location, descriptions,
detail URL, application destination/method/status, timestamps/freshness,
employment/workplace/function fields where present, completeness/warnings, and
company URL/profile fields where stored. Search and typed filters are supported
for text, function/subfunction, location, workplace, employment, experience,
language, salary, sponsorship/authorization, company attributes, and freshness;
admin adds publication/completeness/warning/duplicate filters. Raw payloads,
alternate evidence, rule output and internal confidence remain admin-only.

## Tests, build, deployment

| Check | Result |
|---|---|
| Python interpreter | `.venv\\Scripts\\python.exe`, Python 3.12.7 |
| Direct connector/generic/scheduler/admin tests | Passed; latest focused run 19 passed, 3 subtests; diagnostic patch run 11 passed |
| Ruff | Passed on changed backend files |
| Frontend unit tests | 148 passed |
| Frontend build | Passed |
| Frontend ESLint | Passed with `--max-warnings=0`; package has no `lint` script |
| API/worker health | `/health`, `/health/live`, `/health/ready` passed during production checks |
| Frontend API diagnostic | Absolute API host and proxy health passed |
| Render deployment | API and worker live on `dc19cc05298e7d69e4548793798030d3bc059eac` |

## Remaining limitations

1. Siemens and SmartRecruiters are productive through bounded paths, but their
   current captures are intentionally incomplete; they must not be used as
   authoritative closure snapshots until a complete-page contract exists.
2. Logo enrichment is configured but execution is deferred; logo coverage is
   zero by design.
3. No live duplicate cluster exists, so production merge/split/undo has not
   been exercised against a naturally occurring candidate.
4. Company-source and full alias decision history are not first-class entities.
5. Confidence scores are not calibrated probabilities, and some optional typed
   fields remain unknown by source capability.
6. Automated remote backup restore and destructive rollback are not acceptance
   tested; reprocessing rollback is additive/replay-safe rather than a delete.

## Recommended next sequence

1. Add a durable snapshot manifest and expose source-reported/observed/accepted/
   rejected/closed reconciliation in the admin UI.
2. Add the company-source and alias decision model with reversible audit history.
3. Complete typed public serializers and calibrate confidence semantics.
4. Approve and enable a bounded official-website/logo provider canary.
5. Exercise duplicate decisions in an isolated production-shaped database, then
   run a reviewed live candidate without automatic merging.
6. Add backup/restore drills and structured connector telemetry dashboards.
