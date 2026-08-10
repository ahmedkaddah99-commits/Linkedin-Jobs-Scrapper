# Current Runr acquisition pipeline map

This map is the verified implementation map for the repository as of the
`unified_mapping_v1` change. The requested map was not present in the checkout,
so it was reconstructed from the executable repositories, migrations, routes,
and tests.

## End-to-end path

```text
source registry / manifest
  -> acquisition target + cycle/task/request reservations
  -> connector response / employer-page response
  -> immutable job_source_observations
  -> normalize_job_for_ingestion()
       -> URL/application taxonomy
       -> description representations
       -> source metadata and timestamp semantics
       -> unified_mapping_v1 field map
  -> canonical company/job identity and version merge
  -> field provenance + rule output + company URL projections
  -> report-only quality/completeness and duplicate candidates
  -> review/publication read model
  -> admin API and Data inspector
```

## Ownership by stage

| Stage | Current implementation | Durable output | Failure behavior |
| --- | --- | --- | --- |
| Source registry | `backend/acquisition/manifest.py`, `SqliteAcquisitionStore.ensure_targets()` | `acquisition_targets` | Source/config error is recorded; no canonical fact is invented |
| Acquisition control | `SqliteAcquisitionStore.claim_due_cycle()`, task/request reservation and completion methods | `acquisition_cycles`, `acquisition_tasks`, `acquisition_requests`, attempts/events | Idempotent reservation and bounded retry |
| Raw evidence | `SqliteAcquisitionStore.ingest_snapshot()` | `job_source_observations.raw_payload_json`, `payload_json`, hashes, source metadata | Observation is inserted; it is immutable after migration 044 |
| Extraction/normalization | `backend/acquisition/quality.py` | Posting version payload and `acquisition_rule_outputs` | Missing/unsupported fields remain null/unknown; warnings are report-only |
| Identity | `backend/domain/job_identity.py` and acquisition identity helpers | `canonical_jobs`, external IDs, URL aliases, company aliases | Conservative identity; no ambiguous merge |
| Canonical merge | `_ensure_version()` and `_persist_unified_mapping()` | Immutable `job_posting_versions`, selected canonical pointer, provenance | Existing content hash reuses a version; changed content creates a new version |
| Field map | `backend/acquisition/unified_mapping.py` | `acquisition_field_provenance`, company URLs, timestamp projections | Every mapped field carries raw/normalized/state/source/method/evidence/confidence/time/rule |
| Quality | `completeness_rules()`, `acquisition_quality_events`, reprocessor | Completeness reports, warnings, duplicate candidate clusters | Report-only; no publication block is introduced |
| Publication | existing admin preview/publish services | `acquisition_publications`, publication jobs/head | Reprocessing never automatically promotes a publication |
| Admin read model | `backend/api/routes/job_import_admin.py`, `AdminJobImportPage.jsx` | inspection JSON, companies, rules, duplicates, reprocessing, publication endpoints | Admin-only, exact nulls and raw payload remain visible |

## Source-to-field contract

All connector-specific payload keys are retained under the immutable raw
observation. The normalized map covers:

- Job identity, title, location, detail URL, descriptions (`raw_html`,
  sanitized HTML, clean text), department/function/subfunction, employment,
  workplace, remote restrictions, language requirements, experience/seniority,
  application destination, and source timestamps.
- Company identity, description, website, careers URL, industry, size,
  headquarters, founding/stage/funding, leadership, benefits, sponsorship,
  logo URL, headcount, and associated member count when the source exposes
  them. Raw source values are retained even when normalization is unavailable.
- Admin provenance: observation IDs, connectors, source requests/credits,
  content/version hashes, warnings, completeness, review, duplicate state,
  and publication state.

The application destination is always separate from the job-detail URL and is
classified as one of `dedicated_apply`, `embedded_apply`,
`job_detail_with_apply`, `redirect_apply`, `job_detail_only`, or `unresolved`.
The resolver stores validation time, final URL, HTTP status, evidence type,
and failure reason when those observations exist.

## Reprocessing and idempotence

`backend/acquisition/reprocessing.py` processes preserved observations in
bounded batches. It checkpoints each batch in
`acquisition_reprocessing_runs` and `acquisition_stage_results`, creates a
local SQLite backup before apply, and only writes additive/versioned
projections. A second unchanged run reuses an existing stable version hash;
it does not append another posting version. Duplicate detection creates a
reviewable candidate cluster only when the conservative evidence agrees; it
does not merge records.

Operator entry point:

```powershell
.venv\Scripts\python.exe scripts\reprocess_acquisition.py --env-file user_config\.env
.venv\Scripts\python.exe scripts\reprocess_acquisition.py --env-file user_config\.env --apply --yes --allow-remote-additive-rollback
```

The first command is read-only apart from additive migration initialization.
The second command is the explicit apply operation.
