# Production data-pipeline implementation report

Date: 2026-08-10  
Branch: `deployment/render-turso-r2`  
Implementation commits inspected: `a1a1c92` through `cba90b6`. The production
reprocessing run executed while the Runr API and worker were deployed at
`cba90b654b13eb7d4951c2e418de57719906ab11`, which includes the lease-expiry and
private-caller fencing fixes described below. The subsequent report-only
deployment is `9a7423f`; the separate frontend deployment is `9a62e81`.

## Scope and safety

This report covers the acquisition mapping, evidence, quality, duplicate,
company URL/enrichment, admin read model, and resumable reprocessing work in
the Runr repository. The local database was not treated as production. The
production evidence below came from the configured `user_config/.env` target:
Turso/libSQL with `RUNR_ENV=production` and R2/S3 object storage. No credential
or secret value is included.

Before the paused production reprocessing resume, a database-native embedded
libSQL snapshot was created at:

`.backend_data/reprocessing_backups/production_before_reprocessing_resume_20260810.sqlite3`

The snapshot was reported as recoverable, 91 tables, 44 migrations, and
102,760,448 bytes. It is ignored and was not committed. Remote restore is not
automated; the safe remote rollback boundary remains additive checkpoint plus
publication/review reversal.

## Implementation delivered

### Acquisition contract

- `unified_mapping_v1` maps job identity, title, locations, descriptions,
  department/function/subfunction, employment, workplace, remote restrictions,
  languages, experience/seniority, application destination, lifecycle
  timestamps, and company profile/URL fields.
- `rule_registry.py` centralizes field states, state descriptions, confidence
  bounds, and rule-family metadata.
- Raw observations remain immutable. Raw payload JSON/hash, normalized
  projections, semantic hashes, rule outputs, selected/unselected field
  evidence, warnings, and completeness reports are separate durable layers.
- Company homepage, careers, employer-jobs, ATS, detail, and source URLs are
  retained independently in `canonical_company_urls`.
- Generic pages preserve raw HTML, sanitized HTML, clean text, JSON-LD fields,
  source posted date, and conservative HTML location evidence.
- Application links distinguish direct employer/ATS apply from embedded,
  redirect, detail, and listing fallback destinations.

### Identity and duplicate safety

- Job IDs prefer source external ID and canonical URL/signature; URL aliases,
  external IDs, source states, and immutable posting versions are retained.
- Stable content hashing excludes volatile observation/telemetry fields;
  unchanged content reuses a version and changed stable content appends one.
- Duplicate detection writes candidate clusters/members/reasons only. No
  automatic merge, observation rewrite, canonical pointer change, or
  publication promotion is performed.
- The new lease migration `045_acquisition_reprocessing_leases` uses an
  owner token and compare-and-swap stale reclaim. A second active caller gets
  `in_progress`; a stale caller resumes from the durable checkpoint.

### Admin and API

The new admin console is mounted at `/admin/acquisition` with sections:

- Overview: source counts, quality boundary, publication head, and links.
- Sources: choose bounded sources, plan an import, and queue an idempotent
  admin import.
- Jobs: canonical job search/filter and inspection drawer.
- Companies: canonical company search, profile and URL counts.
- Duplicates: candidate cluster/reasons view; review-only.
- Rules: field-state, stage, completeness, and warning counts.
- Reprocessing: read-only plan and recent run/checkpoint/rollback metadata.
- Publication: preview, explicit publish, and undo of the current head.

The legacy `/admin/job-import` routes remain available and now share the
inspection/reprocessing capabilities. Both route families are admin-only.
Raw source evidence is returned by the admin inspection API but is not placed
in the public user serializer.

## Production baseline and evidence

The inspected target was the configured production Turso/libSQL database, not
the local SQLite path. `/health/live` and `/health/ready` both returned HTTP
200; readiness reported `runtime_environment=production`, `target_backend=libsql`,
`remote_required=true`, and R2/S3 object storage. Migration 045 is present with
its applied timestamp and checksum:
`045_acquisition_reprocessing_leases`, applied at
`2026-08-10T11:47:21.395366+00:00`.

The completed post-replay inventory was:

| Metric | Observed |
|---|---:|
| Applied migrations | 45 |
| Immutable observations | 587 |
| Canonical jobs/companies | 141 / 11 |
| Posting versions | 609 |
| Field provenance/rule outputs | 18,197 / 587 |
| Completeness reports/quality events | 141 / 5,949 |
| Company URL/logo-enrichment rows | 280 / 0 |
| Duplicate clusters/members | 0 / 0 |
| Publications/current head | 5 / 1 |
| Rows in all publication snapshots | 427 |
| Jobs in current valid head | 133 |

Source reconciliation:

| Configured source | Connector | Observations | Canonical-company jobs |
|---|---|---:|---:|
| N26 | Greenhouse | 433 | 97 |
| Qonto | Lever | 152 | 42 |
| Fixture source | fixture/career site | 1 | 1 |
| x | fixture/career site | 1 | 1 |

The fixture rows and the `x` row are production-data hygiene findings, not
connector success. They should be quarantined or removed through an explicit
operational decision before a future quality report is treated as a clean
production baseline.

## Reprocessing state

The requested production run is complete:

| Field | Final value |
|---|---|
| Reprocessing ID | `reprocess_ef912ccf2e9f44ca974222fe60732e55` |
| Idempotency key | `unified-mapping-production-2026-08-10` |
| Status | `completed` |
| Checkpoint | `observation_ffc65009d257463e95239c00166d6ab7` |
| Observations / batches | `587 / 67` |
| Fields / historical repairs | `5,870 / 585` |
| Warnings / failed observations | `2,787 / 0` |
| Failed observation IDs | `[]` |
| Completed at | `2026-08-10T13:51:01.341004+00:00` |
| Rule version | `unified_mapping_v1` |

The original report of `80/587` and 28 batches was a stale intermediate
checkpoint. The shared run row was subsequently claimed by multiple local
Codex-launched copies. Those writers advanced operational counters and wrote
replayable evidence/quality projections; they did not increase posting
versions, canonical jobs, publication rows, or duplicate projections. The
controlled finalization baseline at checkpoint 512 was reconciled against the
completed snapshot below.

| Table/model | Controlled baseline | Completed + replay | Delta |
|---|---:|---:|---:|
| `job_source_observations` | 587 | 587 | 0 |
| `job_posting_versions` | 609 | 609 | 0 |
| `acquisition_field_provenance` | 15,810 | 18,197 | +2,387 |
| `acquisition_rule_outputs` | 510 | 587 | +77 |
| `acquisition_completeness_reports` | 141 | 141 | 0 |
| `canonical_company_urls` | 280 | 280 | 0 |
| `company_logo_enrichments` | 0 | 0 | 0 |
| `acquisition_duplicate_clusters` | 0 | 0 | 0 |
| `acquisition_duplicate_members` | 0 | 0 | 0 |
| `acquisition_quality_events` | 5,585 | 5,949 | +364 |
| `acquisition_publications` | 5 | 5 | 0 |
| `acquisition_publication_head` | 1 | 1 | 0 |
| `acquisition_publication_jobs` | 427 | 427 | 0 |
| Current-head jobs | 133 | 133 | 0 |
| `canonical_jobs` | 141 | 141 | 0 |
| `canonical_companies` | 11 | 11 | 0 |

The field-evidence and report-only warning deltas are expected mapping output;
the immutable source, semantic-version, identity, duplicate, publication, and
current-head counts did not inflate.

### Duplicate-launcher root cause and durable fix

Evidence ruled out a Render reprocessor, Windows scheduled task, Windows
service, repository launcher, or deployment job. Render `runr-worker` runs
`./deploy/start.sh worker`; `runr-api` runs `./deploy/start.sh api` with
`./deploy/start.sh migrate` as pre-deploy; and `runr-process-next` is a separate
old cron running `./deploy/start.sh process-next` at commit `731119a`. Its logs
contained no `reprocess_acquisition.py` invocation.

The precise duplicate root was the local Codex app-server (`codex.exe`, parent
PID 12128) spawning lingering PowerShell commands. Observed variants called
private `_claim_run`/`_process_batch`, performed a raw lease `UPDATE`, or ran
old public script copies with batch sizes 1, 5, 10, and 25. Examples included
legacy roots PID 3324 and PID 8548; only those exact roots and their matching
Python descendants were terminated. Unrelated Python, API, worker, and
deployment processes were not terminated. The `.venv` base-Python child seen
under the intended runner is normal Windows virtual-environment behavior, not
itself a duplicate launcher.

The persistent application-side fix is deployed in `620cdb7`, `07e9fdb`, and
`20b9930` (included in live `cba90b6`):

- every resumable takeover requires an empty or expired lease, including rows
  marked `incomplete`;
- only the public runner receives the internal claim capability;
- private `_process_batch` callers without that capability return before any
  projection work.

The completed run was operated with one public writer, bounded batches, durable
checkpoints, and exact-process checks. Quality/completeness failures remained
report-only. No observation, posting version, duplicate merge, or publication
promotion was deleted or rewritten.

### Same-key replay proof

Immediately after completion, the exact same command/key was invoked. It
returned exit code 0 with:

```json
{
  "status": "completed",
  "idempotent_replay": true,
  "reprocessing_id": "reprocess_ef912ccf2e9f44ca974222fe60732e55",
  "idempotency_key": "unified-mapping-production-2026-08-10",
  "counts": {"batches": 67, "observations": 587, "fields": 5870,
             "historical_repairs": 585, "warnings": 2787,
             "failed_observations": 0}
}
```

The post-replay snapshot matched the completion snapshot: no semantic version,
duplicate projection, publication, current-head, observation, or canonical
identity delta occurred during replay.

The safe resumable command shape, if an operator must inspect the completed
run, is:

```powershell
.venv\Scripts\python.exe scripts/reprocess_acquisition.py `
  --env-file user_config\.env `
  --apply --yes --allow-remote-additive-rollback `
  --batch-size 5 `
  --max-batches 1 `
  --stale-after-seconds 1800 `
  --idempotency-key unified-mapping-production-2026-08-10 `
  --resume reprocess_ef912ccf2e9f44ca974222fe60732e55
```

The backup reference remains
`.backend_data/reprocessing_backups/production_before_reprocessing_resume_20260810.sqlite3`;
it is recoverable and was not committed. Remote rollback remains additive
checkpoint/resume plus publication/review reversal; no destructive automatic
restore exists.

## Validation completed

- Project interpreter: Python 3.12.7; focused reprocessing tests passed 5/5
  after the lease-expiry and private-caller fixes; Ruff passed.
- Frontend production build: Vite build passed; the new
  `AdminAcquisitionPage` chunk was generated.
- Local fixture validation: raw observation payload remained unchanged,
  differing descriptions did not false-merge, bounded resume completed, a
  failed observation was retryable, duplicate-finalize failure was resumable,
  and completed idempotency replay returned stable counts.
- Live API health: `/health/live` and `/health/ready` returned HTTP 200; ready
  reported Turso/libSQL and R2/S3 backends. Admin and user bodies require
  authenticated sessions, so no unauthenticated production catalog body is
  claimed here.
- Machine-readable map parsed successfully as JSON with 12 stages, 11
  entities, 21 lineage entries, 10 connector capability entries, and 6 gap
  categories.

## Remaining limitations and recommended sequence

No failed observations or unresolved lease owners remain. Remaining
limitations are operational/data-quality items, not a reprocessing gate:

1. Quarantine fixture/test targets and decide whether to exclude them from
   production quality metrics.
2. Do not grant external callers direct database write access; the observed
   raw-SQL launcher variant bypassed application fencing and was terminated by
   exact process identity. A future control should enforce this boundary at
   the database/operator surface as well.
3. Add durable connector capability snapshots, raw-retention coverage,
   timestamp/lifecycle conflict semantics, and company-source alias decisions.
4. Add reversible duplicate decisions, one approved enrichment provider with
   budget/terms/refresh controls, and authenticated production contract tests.
5. Expand public serializers and admin controls only after versioning the
   `known`/legacy-`present` compatibility contract.

The complete stage, entity, field-lineage, connector, consumer, duplicate, and
gap map is in [CURRENT_DATA_PIPELINE_MAP.md](CURRENT_DATA_PIPELINE_MAP.md) and
[CURRENT_DATA_PIPELINE_MAP.json](CURRENT_DATA_PIPELINE_MAP.json).

## Prompt 2 — fresh production baseline (2026-08-10)

The configured environment inspected was production Turso/libSQL from
`user_config/.env`; the local SQLite database was not treated as production.
At the validation boundary, the API and worker were live on
`5e494dc68a7bf2b3c2bc49d6a52886110cccc2db` and the frontend was live on
`9a62e81b0ea7e3a7f02026ae07cbd56f705a0e12`. Migration 046,
`046_acquisition_source_quarantine`, was applied at
`2026-08-10T14:19:41.263182+00:00`; migration 045 was already applied at
`2026-08-10T11:47:21.395366+00:00`.

The source hygiene fix quarantines `fixture_source` and `x` by setting
`enabled=0`, `publication_enabled=0`, and `maturity_state=quarantined`, while
retaining their immutable observations. Normal scheduler and quality-metric
selection exclude quarantined targets. The current valid publication head
`acq_publication_5884f63297fc4f56a0fb019c7cd4f063` contains 133 jobs and zero
fixture jobs, so no exclusion preview was necessary and no publication was
promoted.

Fresh production acquisition completed through the authenticated admin path:

| Source | Import / idempotency key | Cycle | Request evidence | Result |
|---|---|---|---|---|
| N26 / Greenhouse | `job_import_870c6fab348e4aaba91dbf722df6fc39` / `admin-acquisition-1786371852231` | `acq_cycle_8fc75e5e4f5149379db22e2b4ba89c3e` | HTTP 200, 91 returned from `https://boards-api.greenhouse.io/v1/boards/n26/jobs?content=true` | 91 accepted, 0 rejected, 91 distinct IDs, 0 new/updated, 91 unchanged, 0 closed |
| Qonto / Lever | `job_import_df980bf7cb194bb7ab3795097449f0fe` / `admin-acquisition-1786372234773` | `acq_cycle_33efc4e694d14e87bef67306d2fa12d2` | Two HTTP 200 attempts, 35 rows each from `https://api.lever.co/v0/postings/qonto?mode=json` | 35 unique accepted, 0 rejected, 35 distinct IDs, 0 new/updated, 35 unchanged, 0 closed |

Qonto's first request exceeded the former five-minute remote projection lease.
The worker did not create a new import or key: after the stale lease guard and
30-minute remote lease were deployed, the same import/cycle/key resumed and
committed 35 rows. The two fetched batches explain 70 request-level rows versus
35 unique source records; no duplicate observation, semantic version, or
projection inflation occurred.

The before/after production projection read was:

| Table/read model | Before | After/current | Delta |
|---|---:|---:|---:|
| `job_source_observations` | 713 | 839 | +126 |
| `job_posting_versions` | 735 | 735 | 0 |
| `acquisition_field_provenance` | 22,103 | 26,009 | +3,906 |
| `acquisition_rule_outputs` | 713 | 839 | +126 |
| `acquisition_completeness_reports` | 20 before boundary | 146 | +126 |
| `acquisition_quality_events` | 6,349 | 6,749 | +400 |
| `canonical_company_urls` | 290 | 290 | 0 |
| `company_logo_enrichments` | 0 | 0 | 0 |
| `acquisition_duplicate_clusters/members` | 0 / 0 | 0 / 0 | 0 / 0 |
| `acquisition_publications` | 5 | 5 | 0 |
| `acquisition_publication_jobs` | 427 | 427 | 0 |
| Current head jobs | 133 | 133 | 0 |

The complete source reconciliation, representative N26/Qonto field lineage,
application destination checks, authenticated admin/user UI checks, warnings,
and unresolved gaps are recorded in
[PRODUCTION_FRESH_ACQUISITION_REPORT.md](PRODUCTION_FRESH_ACQUISITION_REPORT.md).

## Prompt 3 — parallel product-completion wave (2026-08-10)

Prompt 2 ended with `PROMPT 2 GATE PASSED`, so the four bounded product
workstreams were integrated and deployed. The inspected environment remained
configured production Turso/libSQL from `user_config/.env`; local SQLite was
not treated as production. The product-code API/worker deployment was
`8ba4e5ec2f4f61a145636e2ff1a7e761e14d526f`; the current API/worker deployment
after the documentation push is
`b3477b0c8504dd4bd43c4749bf6cfb46e7a0584f`. The frontend containing the new
admin UI is live on `0ba834a8b59dcdbc660ef03dad4429904a700a39`, and production
has migration `047_product_completion_wave`.

### Integrated workstreams

- **A — company identity/enrichment:** typed URL aggregation, validation,
  provenance, primary-candidate selection, logo adapter/monogram fallback,
  company detail API, and bounded admin enrichment controls. Production N26
  and Qonto URL evidence rendered in the authenticated Companies page. No
  provider was configured or invoked; `company_logo_enrichments` remains 0.
- **B — duplicate decisions:** migration-backed append-only decisions, state
  validation, evidence/reason capture, reversible undo, authenticated API, and
  admin review controls. Production has zero duplicate clusters, so no live
  decision event was created. No merge or publication occurred.
- **C — typed product contract:** additive `typed` public job-card/detail
  namespace, bounded admin lineage/version helpers, normalized typed filters,
  application-destination safety, and admin Jobs filters. Authenticated
  production feed/detail and admin Jobs checks passed. Current Qonto detail
  data still exposes unknown workplace/category/application and no verified
  description; these are source/read-model gaps, not invented values.
- **D — connector capability/retention:** disabled-by-default Workday,
  Personio, Recruitee, and SmartRecruiters contracts, bounded retry and
  pagination rules, raw-retention metrics, capability snapshots, and Rules UI.
  Production contains 8 historical snapshots, displayed as 4 latest views;
  all four remain disabled/unregistered and report-only.

The full workstream report is [PARALLEL_PRODUCT_COMPLETION_REPORT.md](PARALLEL_PRODUCT_COMPLETION_REPORT.md).

### Current production read after deployment

| Metric | Current value |
|---|---:|
| Migration | 047 |
| Canonical companies/jobs | 11 / 146 |
| Source observations / posting versions | 839 / 735 |
| Field provenance / rule outputs | 26,009 / 839 |
| Completeness reports / quality events | 146 / 6,749 |
| Company URLs / verified logo rows | 290 / 0 |
| Duplicate clusters / decisions | 0 / 0 |
| Capability snapshots | 8 historical, 4 latest connector views |
| Raw payload-bearing observations | 839 of 839 |
| Valid publication head | `acq_publication_5884f63297fc4f56a0fb019c7cd4f063`, 133 jobs |

The completed reprocessing run remains
`reprocess_ef912ccf2e9f44ca974222fe60732e55` with idempotency key
`unified-mapping-production-2026-08-10`, final observation checkpoint
`observation_ffc65009d257463e95239c00166d6ab7`, and no failed observation IDs.
Prompt 3 added no semantic versions, duplicate projections, merges, or
publication changes.

### Validation and limitations

The project interpreter was Python 3.12.7. Backend compile/Ruff, focused
product-completion and acquisition tests, frontend Node tests/ESLint/Vite, and
`git diff --check` passed. Authenticated production browser checks rendered the
new duplicate, company, capability, and typed Jobs admin surfaces plus the
user feed/detail. No unauthenticated 401 response was used as authenticated
body evidence.

The pre-existing deployed frontend API-host diagnostic (`api_host: "${n}"`)
and proxy DNS failure remain unresolved. A production enrichment provider was
not configured, and the zero-cluster state prevented a live duplicate-decision
canary. Quality and completeness remain report-only and do not block unrelated
observations. See the parallel report and current map for the prioritized
follow-up sequence.
