# Production data-pipeline implementation report

Date: 2026-08-10  
Branch: `deployment/render-turso-r2`  
Implementation commit inspected: `9a62e81` (`Add acquisition admin console and resilient reprocessing leases`)

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

The read-only inventory immediately before deployment packaging was:

| Metric | Observed |
|---|---:|
| Applied migrations | 44 |
| Acquisition targets/cycles/requests | 9 / 10 / 25 |
| Immutable observations | 587 |
| Canonical jobs/companies | 141 / 11 |
| Posting versions | 609 |
| Field provenance/rule outputs | 7,316 / 236 |
| Completeness reports/quality events | 127 / 3,729 |
| Company URL/logo-enrichment rows | 252 / 0 |
| Duplicate clusters/members | 0 / 0 |
| Publications/current head | 5 / 1 |
| Jobs in current valid head | 133 |

Source reconciliation:

| Configured source | Connector | Observations | Canonical-company jobs |
|---|---|---:|---:|
| N26 | Greenhouse | 433 | 97 |
| Qonto | Lever | 152 | 42 |
| Fixture source | fixture/career site | 1 | 1 |
| x | fixture/career site | 1 | 1 |

The fixture rows and five bounded probe targets are production-data hygiene
findings, not connector success. They should be quarantined or removed through
an explicit operational decision before a future quality report is treated as
a clean production baseline.

## Reprocessing state

The requested production idempotency key is
`unified-mapping-production-2026-08-10`. Two concurrent invocations were
found and stopped after exact command inspection; one was using the project
venv and one used a global interpreter. The global interpreter is now rejected
by the script guard. No further production invocation was started during
implementation review.

The remote run row was left in `running` with a stale checkpoint after those
processes were stopped. Its latest observed checkpoint/count projection was
23 committed observations, 23 fields, 23 historical repairs, 115 warnings,
and 23 batches in the row after the concurrent invocation. The count anomaly
is itself an operational finding: the new lease/checkpoint deployment must go
live before resuming so the row is reclaimed once, with the same idempotency
key, and its post-resume counts are reconciled against table deltas.

Required post-deploy operator command:

```powershell
.venv\Scripts\python.exe scripts/reprocess_acquisition.py `
  --env-file user_config\.env `
  --apply --yes --allow-remote-additive-rollback `
  --batch-size 25 `
  --idempotency-key unified-mapping-production-2026-08-10 `
  --resume reprocess_ef912ccf2e9f44ca974222fe60732e55
```

Then run the same command again without a new key. The expected second result
is `idempotent_replay=true` with no additional observation/version/evidence
rows beyond the first completed projection. The current admin UI deliberately
does not authorize remote additive apply by default; the CLI acknowledgement
is the explicit operational path until a visible admin acknowledgement control
is added.

## Validation completed

- Project interpreter: Python 3.12.7.
- Focused acquisition, migration, quality, admin, ATS, dedupe, mapping, and
  reprocessing tests: 47 passed, 15 subtests passed before the final docs-only
  edits; the committed lease workstream also includes four dedicated
  reprocessing tests.
- Ruff: all changed Python files passed.
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

## Remaining blockers and recommended sequence

1. Deploy the committed migration/code to API and worker; verify migration 045,
   health, worker readiness, and that the current publication head is unchanged.
2. Resume the stale production run exactly once, reconcile table deltas and
   warnings by N26/Qonto/fixture source, then run the same idempotency key again.
3. Quarantine fixture/test targets and decide whether to backfill or exclude
   their observations from production quality metrics.
4. Add durable connector capability snapshots, raw-retention coverage,
   timestamp/lifecycle conflict semantics, and company-source alias decisions.
5. Add reversible duplicate decisions, one approved enrichment provider with
   budget/terms/refresh controls, and authenticated production contract tests.
6. Expand public serializers and admin controls only after versioning the
   `known`/legacy-`present` compatibility contract.

The complete stage, entity, field-lineage, connector, consumer, duplicate, and
gap map is in [CURRENT_DATA_PIPELINE_MAP.md](CURRENT_DATA_PIPELINE_MAP.md) and
[CURRENT_DATA_PIPELINE_MAP.json](CURRENT_DATA_PIPELINE_MAP.json).
