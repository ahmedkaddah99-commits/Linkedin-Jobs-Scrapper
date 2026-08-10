# Unified acquisition mapping implementation report

## Result

Implemented and pushed the connector-independent acquisition map and safe
reprocessing path as:

- `5bbcac6` — unified mapping, provenance tables, admin read projections,
  reprocessing runner, map, and tests.
- `2776b1b` — explicit remote/libSQL transaction batching.
- `10d2366` — idempotent reprocessing warning events.

Branch: `deployment/render-turso-r2`.

## What changed

### Schema

Migration `044_unified_acquisition_mapping` adds:

- `raw_payload_json`, `raw_content_hash`, and `rule_version` to source
  observations; source observations now have immutable update/delete triggers.
- Canonical timestamp projections: `published_at`, `source_updated_at`,
  `closed_at`, and `last_reprocessed_at`.
- `acquisition_stage_results` for stage checkpoints.
- `acquisition_rule_outputs` for versioned deterministic outputs.
- `acquisition_field_provenance` for raw value, normalized value, state,
  source, source field, extraction method, evidence, confidence, observed
  time, selected state, and rule version.
- `acquisition_completeness_reports` for report-only field matrices.
- `acquisition_reprocessing_runs` for idempotency, checkpoints, counts,
  environment, scope, and backup metadata.
- `acquisition_duplicate_clusters` and `acquisition_duplicate_members` for
  review-only candidate clusters.
- `canonical_company_urls` for evidence-backed homepage, careers, employer
  jobs, ATS, detail, and source URLs.
- `company_logo_enrichments` as the durable provider/provenance projection for
  a configured logo adapter. No logo is fabricated when the provider has no
  source-backed result.

### Code and API

- `backend/acquisition/unified_mapping.py` implements
  `unified_mapping_v1`. It preserves raw source values and maps function,
  subfunction, employment, workplace, remote restrictions, language,
  experience, descriptions, application destination, timestamps, company
  URLs, logo URL, headcount, and associated members.
- `backend/acquisition/quality.py` now emits destination type plus validation
  fields and attaches the unified map to every normalized posting.
- `SqliteAcquisitionStore.ingest_snapshot()` stores the original observation
  before creating normalized projections. Existing canonical version rows stay
  immutable; identical stable content reuses any matching existing version.
- Admin inspection now returns raw observation payloads, field provenance,
  normalized rule outputs, company URLs, completeness reports, and duplicate
  candidates.
- Admin-only read endpoints:
  `/admin/job-import/companies`, `/duplicates`, `/rules`, `/reprocessing`,
  `/reprocessing/plan`, and `/publication`.
- Existing Data inspector layout was preserved. Its exact JSON view now
  exposes the added projections through the existing job inspection response.

## Reprocessing contract

The stage order is:

`source_registry` → `immutable_observation` → `extraction` → `normalization`
→ `identity_resolution` → `canonical_field_merge` → `quality_completeness`
→ `publication_read_model`.

The runner is `scripts/reprocess_acquisition.py` and is dry-run by default.
Apply requires both `--apply --yes`; a remote target additionally requires
`--allow-remote-additive-rollback`. Local SQLite gets a recoverable copy before
apply. Remote writes are additive/versioned and transaction-batched. No
automatic duplicate merge or publication promotion occurs.

## Production/dev environment run

The configured `user_config/.env` target is the Runr Turso development
database running with `RUNR_ENV=production`/Turso production safety settings.
The initial plan observed:

| Metric | Before run |
| --- | ---: |
| Source observations | 587 |
| Canonical jobs | 141 |
| Canonical companies | 11 |
| Posting versions | 587 |
| Existing normalized field rows | 62 |
| Existing completeness reports | 2 |
| Existing company URL rows | 2 |
| Existing warnings | 2,499 |

The additive reprocessing run uses idempotency key
`unified-mapping-production-2026-08-10` and is checkpointed in Turso. Its
final committed counts and completion timestamp are recorded below after the
remote run completes:

| Metric | Final |
| --- | ---: |
| Observations processed | pending completion |
| Historical raw repairs | pending completion |
| Field records mapped | pending completion |
| Report-only warnings | pending completion |
| Duplicate candidate clusters | pending completion |

The operation can be safely resumed with the same idempotency key. The first
50-observation checkpoint was committed before the remote batch size was
reduced; subsequent batches use the transaction-batched runner.

## Fresh vs historical behavior

- Fresh acquisition stores `raw_payload_json` at ingest time and produces the
  complete unified map immediately.
- Historical rows without preserved raw payloads are reprocessed from the
  existing normalized payload and receive the explicit warning
  `raw_payload_not_available_for_historical_repair`.
- Unknown, unsupported, and invalid fields remain explicit null/unknown
  states. The mapper does not call AI, Crunchbase, Apollo, or an unconfigured
  external enrichment provider.
- Company logo, website, headcount, and associated-member values appear only
  when visible in the preserved source or returned by an enabled configured
  provider; otherwise they remain null with null provenance.

## Verification

Passed:

- Python 3.12.7 project interpreter check.
- `compileall` for backend, tests, and reprocessing script.
- Ruff on all changed Python files.
- Targeted migrations, Phase A, quality, Phase B, company, admin, and unified
  pipeline tests: 47 passed, 4 subtests passed across the final targeted runs.
- Fresh fixture acquisition and two unchanged reprocessing runs: raw payload
  unchanged, no extra posting versions on the second run, no false duplicate
  cluster for differing descriptions.
- Live API `/health/live`: HTTP 200.
- Live API `/health/ready`: HTTP 200 with Turso and R2 visible.
- New admin paths reach the live authentication layer (HTTP 401 without an
  admin session, not a route 404).

The full repository pytest command exceeded its 120-second command ceiling
without emitting a test failure; it is therefore reported as a timeout, not a
pass.

## Operator guide

Read-only plan:

```powershell
.venv\Scripts\python.exe scripts\reprocess_acquisition.py --env-file user_config\.env
```

Remote additive apply:

```powershell
.venv\Scripts\python.exe scripts\reprocess_acquisition.py `
  --env-file user_config\.env `
  --apply --yes --allow-remote-additive-rollback `
  --batch-size 5 `
  --idempotency-key unified-mapping-production-2026-08-10
```

Inspect run state through the admin-only
`GET /admin/job-import/reprocessing` endpoint or directly through the
`acquisition_reprocessing_runs` projection. Do not delete observations to
undo a result; use the recorded checkpoint/idempotency key and reversible
publication or review actions.
