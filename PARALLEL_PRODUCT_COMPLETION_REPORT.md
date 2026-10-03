# Parallel product-completion wave report

Date: 2026-08-10
Repository: Runr, branch `deployment/render-turso-r2`
Inspected environment: configured production Turso/libSQL from
`user_config/.env`. The local SQLite file was used only for code tests and a
capability canary; it was not treated as production.

## Result

The four Prompt 3 workstreams are integrated into the API, admin UI, worker
contracts, migrations, and tests. The product-code deployment was
`8ba4e5ec2f4f61a145636e2ff1a7e761e14d526f`; the subsequent documentation push
is the current API/worker deployment at
`b3477b0c8504dd4bd43c4749bf6cfb46e7a0584f`. The frontend containing the UI
changes is deployed on `0ba834a8b59dcdbc660ef03dad4429904a700a39`. Migration
047 is applied in production. No duplicate merge, publication promotion, or
company enrichment write was performed during validation.

The runtime gate is passed for integration and deployment. Production data
still exposes known limitations: no live duplicate cluster existed to run a
decision transition, no approved enrichment provider was configured for a
logo/profile canary, and representative user-facing fields remain unknown or
missing where the source did not provide them.

## Deployment and migration evidence

| Surface | Deployed commit | Evidence |
|---|---|---|
| API | `b3477b0c8504dd4bd43c4749bf6cfb46e7a0584f` | Current Render live deployment; product code came from `8ba4e5e`; authenticated admin routes returned successfully |
| Worker | `b3477b0c8504dd4bd43c4749bf6cfb46e7a0584f` | Current Render live deployment; product code came from `8ba4e5e` |
| Frontend | `0ba834a8b59dcdbc660ef03dad4429904a700a39` | Render live deployment; authenticated browser rendered new panels |
| Database | migration `047_product_completion_wave` | production `schema_migrations` max is 047 |
| Prior gate | Prompt 2 | previous report ended `PROMPT 2 GATE PASSED` |

The deployed API/worker Render deployment IDs were `dep-d9svv9oae00c73b4i3q0`
and `dep-d9svv9oae00c73b4i4dg`. Credentials and environment values are not
included in this report.

## Workstream A — company URLs, logos, enrichment, and admin controls

Implemented code entry points:

| Area | Entry point | Behavior |
|---|---|---|
| URL operations | `backend/application/company_operations.py` | Normalizes, validates, aggregates, ranks, and selects company URL candidates with provenance and confidence; preserves source observations |
| Logo adapter | `backend/application/company_logo_adapter.py` | Validates/cache-keys provider candidates and provides a deterministic monogram fallback when no verified logo exists |
| Persistence/read model | `backend/repositories/sqlite_acquisition.py:get_admin_company_detail` | Returns company identity, URL rows, logo enrichments, profile, and job count as separate projections |
| Bounded action | `backend/application/services.py:run_admin_company_enrichment` | Explicit admin action capped at 25 companies, concurrency 3, request budget 50; worker enrichment remains separately gated |
| Admin API | `GET /v1/admin/acquisition/companies/{id}`, `POST /v1/admin/acquisition/companies/{id}/enrich` | Authenticated inspection and explicit bounded request |
| Admin UI | `frontend/src/pages/AdminAcquisitionPage.jsx:InteractiveCompanies` | Company detail, URL validation/provenance, logo state, and bounded enrichment button |

Production evidence: the authenticated Companies page showed N26 with 101
jobs and 202 URL rows, Qonto with 43 jobs and 86 URL rows, and source-derived
URL provenance. The N26 detail showed `not_validated · source_observation`
URL evidence and a deterministic monogram fallback. The enrichment button was
not clicked and no provider was configured or invoked. Production
`company_logo_enrichments` remains 0, so no logo is claimed as verified.

Known limitation: company URL rows are source evidence and are not yet a
complete official-domain/homepage/careers/ATS identity model. Provider
precedence, terms, refresh scheduling, and selected URL promotion remain
unimplemented.

## Workstream B — reversible duplicate decisions

Migration 047 adds the append-only
`acquisition_duplicate_decisions` table. It records cluster, decision, actor,
reason, bounded evidence, affected IDs, rule version, superseded decision, and
undo timestamp. The repository methods
`record_admin_duplicate_decision` and `undo_admin_duplicate_decision` validate
state transitions, require a review plan for merge/split states, append an
event, and update only the duplicate cluster review state/history. They do not
modify jobs, observations, immutable posting versions, or publication heads.

Authenticated routes and UI:

- `POST /v1/admin/acquisition/duplicate-clusters/{cluster_id}/decisions`
- `POST /v1/admin/acquisition/duplicate-clusters/{cluster_id}/undo`
- `GET /v1/admin/acquisition/duplicates`
- `InteractiveDuplicates` in `AdminAcquisitionPage.jsx`

The UI exposes confirmed duplicate, distinct, ignored, and undo actions and
states that merge and publication remain separate explicit operations.

Production currently has zero duplicate clusters and zero members, so there
was no safe live cluster on which to create a decision event. The production
decision table remains empty. Local tests proved append-only decision plus undo
and verified that immutable relationships are preserved. No automatic merge or
publication occurred.

## Workstream C — typed public fields, filters, and admin usability

`backend/acquisition/public_contract.py` defines additive typed contract
version `public_typed_contract_v1`, including normalized location, taxonomy,
language, experience, employment, workplace, salary, application, timestamp,
completeness, warning, freshness, duplicate, logo, enrichment, and publication
states. Public serialization adds the `typed` namespace while retaining legacy
keys for compatibility. Known raw/admin payload keys are excluded from public
typed output; bounded `typed_lineage` is available only to admin serialization.

`backend/application/personalized_jobs_service.py` now attaches the typed
contract to both job-card and job-detail projections. Typed filter predicates
match normalized values rather than searching raw serialized payloads. The
admin Jobs page sends search, source, function, workplace, employment type,
language, experience, application method, freshness, warning, duplicate,
completeness, and publication filters to the authenticated admin read model.

Authenticated browser evidence:

- `/admin/acquisition/jobs` rendered the expanded typed filter controls and
  canonical rows.
- `/jobs` rendered `Showing 25 of 133 jobs` and a Qonto detail with an
  actionable Apply button.
- The selected Qonto detail currently displayed unknown workplace/category and
  unknown application method, and displayed no verified description. This is
  an observed data-quality/read-model gap, not an inferred value.

The contract tests passed for normalization, serialization, raw-field
exclusion, scalar filters, language/location matching, lineage, and version
diff behavior. The production browser check authenticated the UI and route
requests; it did not treat an unauthenticated 401 as response-body evidence.

## Workstream D — connector capability and raw-retention metrics

`backend/connectors/ats_expansions.py` defines disabled-by-default contracts for
Workday, Personio, Recruitee, and SmartRecruiters. Each declares capability
fields, request limits, bounded retries, report-only failure policy, stable
identity rules, application-destination classification, pagination behavior,
and raw-payload retention requirements. No connector is registered as a
productive target.

Migration 047 adds
`acquisition_connector_capability_snapshots`. The API exposes:

- `GET /v1/admin/acquisition/connectors/capabilities`
- `GET /v1/admin/acquisition/retention`
- `POST /v1/admin/acquisition/connectors/capabilities/snapshot`

The Rules page displayed all four connectors as disabled/unregistered, with
raw retention `required`, scope `admin-only`, and failure policy `report_only`.
The production canary recorded two historical snapshots per connector; the
admin read model deduplicates them to four latest connector views. Historical
snapshot rows are retained by design.

The inspected production observation table retained 839 of 839 payload-bearing
source observations. This is a current table-level retention check, not proof
that every legacy payload is complete in object storage or that all raw fields
are semantically extractable.

## Production counts and source reconciliation

Counts after the Prompt 3 deployment and capability snapshot canary:

| Table/read model | Count |
|---|---:|
| `schema_migrations` | 47 |
| `acquisition_targets` | 9 |
| `acquisition_cycles` | 14 |
| `acquisition_requests` | 33 |
| `canonical_companies` | 11 |
| `canonical_jobs` | 146 |
| `job_source_observations` | 839 |
| `job_posting_versions` | 735 |
| `acquisition_publications` | 5 |
| `acquisition_publication_head` | 1 |
| `acquisition_publication_jobs` | 427 historical rows |
| Current valid publication head jobs | 133 |
| `acquisition_field_provenance` | 26,009 |
| `acquisition_rule_outputs` | 839 |
| `acquisition_completeness_reports` | 146 |
| `acquisition_quality_events` | 6,749 |
| `acquisition_duplicate_clusters` | 0 |
| `acquisition_duplicate_members` | 0 |
| `canonical_company_urls` | 290 |
| `company_logo_enrichments` | 0 |
| `acquisition_duplicate_decisions` | 0 |
| `acquisition_connector_capability_snapshots` | 8 historical rows / 4 latest views |

Source observations and source-associated canonical jobs:

| Source | Observations | Source-associated jobs | Canonical company job rows |
|---|---:|---:|---:|
| N26 / Greenhouse | 615 | 101 | 101 |
| Qonto / Lever | 222 | 43 | 43 |
| `fixture_source` | 1 | 1 | 1 |
| `x` | 1 | 1 | 1 |

The two quarantined fixture/test rows remain immutable evidence and are not in
the valid current publication head. Lifecycle totals are 139 active and 7
stale; no closed rows were observed in the source reconciliation. Source-row
counts are not unique current jobs: observations and historical posting
versions can outnumber the 133 jobs in the current publication.

The completed reprocessing run remains:

| Field | Value |
|---|---|
| Reprocessing ID | `reprocess_ef912ccf2e9f44ca974222fe60732e55` |
| Idempotency key | `unified-mapping-production-2026-08-10` |
| State | `completed` |
| Checkpoint | final observation `observation_ffc65009d257463e95239c00166d6ab7` |
| Failed observation IDs | none |
| Counts | 67 batches, 587 observations, 5,870 fields, 585 historical repairs, 2,787 warnings |

No Prompt 3 operation changed immutable observations, posting versions, the
publication head, or canonical job identity.

## Tests and authenticated checks

Passed checks:

- Python 3.12.7 project interpreter; backend compileall and Ruff.
- Public contract, duplicate decision, ATS expansion, and company operation
  tests: 30 passed with 3 subtests.
- Migration and acquisition repository tests: 15 passed.
- Admin/mapping/quality/unified tests: 41 passed with 4 subtests.
- Product completion repository tests: 2 passed.
- Additional phase C/D/F tests: 18 passed.
- Frontend check: 148 Node tests, ESLint, and Vite build passed.
- `git diff --check` passed.
- Authenticated production admin browser checks for duplicates, companies,
  rules/capabilities, and typed Jobs filters.
- Authenticated production user feed/detail check for 25 of 133 jobs and an
  actionable Qonto Apply destination.

The pre-existing deployed frontend API-host diagnostic (`api_host: "${n}"`)
and associated proxy DNS failure remained unresolved; it is not attributed to
the Prompt 3 workstream code. The admin browser session nevertheless loaded
the authenticated production read models through the existing application
path.

## Remaining gaps and implementation sequence

1. **Data loss:** add durable raw-retention coverage and archive verification;
   distinguish payload presence from field-level recoverability.
2. **Incorrect semantics:** fix/annotate missing Qonto description and unknown
   workplace/category/application fields; persist Greenhouse same-page child
   application URLs; formalize `unknown`, `unsupported`, `inferred`, and
   conflicting values in every public consumer.
3. **Identity/duplicate risk:** add company-source aliases and syndication
   rules; exercise reversible decisions against a real review cluster before
   enabling any merge workflow.
4. **Missing enrichment:** configure one approved provider with terms,
   refresh, budget, provenance, and logo caching; run a separately approved
   bounded backfill.
5. **Observability:** add snapshot freshness, per-target raw coverage,
   request/retry distributions, and source-to-publication reconciliation to
   the admin metrics.
6. **Admin usability:** add conflict resolution, version diff, explicit
   decision evidence review, and retention drill-down; preserve the current
   preview/publish/undo boundary.

Recommended order: raw-retention and source reconciliation metrics; typed
unknown/conflict semantics and application destinations; company-source
identity; approved enrichment; real duplicate-review canary; then broader
connector enablement only after each connector has a productive authenticated
contract and rollback procedure.

## Evidence files

- [CURRENT_DATA_PIPELINE_MAP.md](CURRENT_DATA_PIPELINE_MAP.md)
- [CURRENT_DATA_PIPELINE_MAP.json](CURRENT_DATA_PIPELINE_MAP.json)
- [PRODUCTION_DATA_PIPELINE_IMPLEMENTATION_REPORT.md](PRODUCTION_DATA_PIPELINE_IMPLEMENTATION_REPORT.md)

No credentials, tokens, raw secrets, or database connection strings are stored
in this report.
