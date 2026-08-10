# Final production acquisition acceptance report

Acceptance date: 2026-08-10  
Branch: `deployment/render-turso-r2`  
Evidence tags: `[C]` code, `[S]` schema/migration, `[T]` automated tests, `[P]` read-only query against the configured production database, `[A]` live HTTP, `[U]` uncertain or not proven.

## Executive result

The inspected environment is the configured production Turso/libSQL target from `user_config/.env`; the local SQLite database is not production. API, worker, and frontend were live on code commit `052d8e145c8034734ab5a302c198f23f5d70067f` at the runtime-fix verification boundary. Migration `047_product_completion_wave` is applied. The bounded remote projection fix recovered the existing N26/Qonto import without creating a second import or changing immutable evidence. [P][A]

The original reprocessing run is completed and the exact same ID/key replay returned `status=completed` and `idempotent_replay=true`. No failed observation IDs remain. [P]

Acceptance is **partial**, because the generic/JSON-LD Siemens attempt ended with an uncertain external outcome before any job was accepted, no production duplicate cluster existed for live merge/split/undo canaries, no approved logo provider is configured, and four additional ATS connectors remain disabled/unregistered. These are explicit deferred scope, not “complete” claims. [P][U]

## Environment, deployment, and migration proof

| Item | Observed truth |
|---|---|
| Runtime environment | `RUNR_ENV=production`, `DATABASE_BACKEND=turso`, remote libSQL/Turso configured, R2/S3 object storage configured |
| Local database | Not used as production evidence |
| API/worker/frontend runtime commit at code-fix boundary | `052d8e145c8034734ab5a302c198f23f5d70067f` |
| Migration 045 | `045_acquisition_reprocessing_leases`, applied `2026-08-10T11:47:21.395366+00:00` |
| Migration 046 | `046_acquisition_source_quarantine`, applied `2026-08-10T14:19:41.263182+00:00` |
| Migration 047 | `047_product_completion_wave`, applied `2026-08-10T16:39:13.185491+00:00` |
| `/health` | HTTP 200, `status=ok` |
| `/health/live` | HTTP 200, `status=ok` |
| `/health/ready` | HTTP 200, `status=ready`; database target is remote libSQL and object storage is R2 |
| Authenticated session | Admin and user pages rendered as Ahmed Kaddah; no unauthenticated 401 was used as authenticated-body evidence |

The code fix is in `backend/repositories/sqlite_acquisition.py`: remote libSQL projection work is split into bounded chunks of 25, with closure evaluated only after the complete source ID set is known. The admin Sources page now exposes a paid-source credit ceiling so ScrapeOps-backed generic imports can pass the server plan check. [C][T]

## End-to-end data path

```text
manifest / acquisition_targets
  -> bounded cycle -> task lease -> request/attempt
  -> Greenhouse, Lever, or bounded career-site connector
  -> immutable job_source_observations (raw JSON, raw hash, source URLs)
  -> extraction + URL/application classification + description representations
  -> unified_mapping_v1 typed fields and company URL evidence
  -> conservative company/job identity resolution
  -> canonical_jobs + immutable job_posting_versions
  -> field provenance + rule outputs + completeness + quality warnings
  -> duplicate candidates (human decision only)
  -> explicit publication preview -> valid publication head
  -> admin read models and authenticated personalized user feed/detail
```

| Stage | Code entry points | Tables/models | Inputs | Outputs | Owner rules |
|---|---|---|---|---|---|
| Environment/safety | `backend/database/connection.py`, `backend/config/*`, `scripts/reprocess_acquisition.py` | `schema_migrations`, config | runtime flags and env | selected remote target and storage | Production requires remote Turso; reprocessing requires project Python 3.12.7 and explicit additive acknowledgement |
| Source registry | `backend/acquisition/manifest.py`, `backend/application/acquisition_scheduler.py`, `SqliteAcquisitionStore.ensure_targets` | `acquisition_targets` | target manifest/config | canonical/request URLs, connector, maturity, limits | disabled, unproven, and quarantined targets are not productive evidence |
| Fetch/lease | `backend/application/acquisition_scheduler.py`, `backend/connectors/ats_router.py`, `company_career_sites.py`, `bounded_probe.py` | `acquisition_cycles`, `acquisition_tasks`, `acquisition_requests`, attempts | official ATS/career URL and bounded scope | raw connector response, cost/retry telemetry | one worker lease, bounded pages/requests/credits, durable uncertain-outcome state |
| Observation retention | `SqliteAcquisitionStore.ingest_snapshot` | `job_source_observations` | accepted source jobs and request context | immutable observation, raw payload/hash, URLs, source timestamps | no delete/update of immutable observations; remote projections are idempotent and chunked |
| Extraction/mapping | `backend/acquisition/phase_b.py`, `quality.py`, `unified_mapping.py` | observation/version/evidence/warning tables | ATS payload, HTML, JSON-LD, links/forms | typed values, raw/sanitized/clean description, application destination | direct application wins over detail/listing fallback; unknown/unsupported/inferred remain explicit |
| Identity/versioning | `backend/domain/job_identity.py`, acquisition identity helpers | `canonical_companies`, `canonical_jobs`, aliases/state tables, `job_posting_versions` | external ID, URL, employer/title/location/content | canonical entity, version number/hash, lifecycle | stable hash excludes volatile fields; changed stable content appends a version |
| Evidence/quality | `_persist_unified_mapping`, `rule_registry.py`, completeness rules | provenance, rule outputs, completeness, quality events | candidate field values and source evidence | selected/unselected evidence, confidence, warnings, report state | report-only; no ingestion/publication gate |
| Duplicate review | duplicate candidate/decision services | duplicate clusters/members/decisions | identity similarity and evidence | candidate cluster and append-only decision history | no automatic merge; merge/split/undo preserve observations and versions |
| Publication | `create_job_import_preview`, `publish_job_import_preview`, `undo_last_job_publication` | publications, publication jobs, singleton head | explicit admin preview/publish/undo | valid publication head | manual promotion only; reprocessing never promotes |
| API/UI | acquisition admin routes, personalized jobs service, React admin/feed pages | read models plus current head | authenticated identity and filters | admin inspection/operations and user feed/detail | raw evidence is admin-only; user feed reads current valid head |

## Canonical entity relationship map

```text
company (canonical_companies)
  ├─ aliases/profile/URLs (canonical_company_aliases, canonical_company_profiles, canonical_company_urls)
  └─ jobs (canonical_jobs)
       ├─ source records (job_source_observations)
       │    ├─ raw payload + request/cycle/task
       │    └─ field evidence/rule outputs/quality events
       └─ immutable versions (job_posting_versions)
            └─ publication job -> publication -> singleton publication head

source registry (acquisition_targets) -> observations
enrichment target/attempt/provider -> company profile/logo projection
identity similarity -> duplicate cluster/member -> append-only decision history
rule version -> mapping/evidence/quality/completeness/reprocessing/publication metadata
```

There is no separate complete durable `company_source` entity: source identity is currently composed from `acquisition_targets`, observation source fields, and company URL evidence. This is a known identity-model gap. [C][S][P]

## Production counts and reconciliation

The “before fresh” column is the post-Prompt-3 production baseline of 839 observations. The “after fresh” column includes the completed N26/Qonto acquisition and the Siemens attempt. The replay column is after invoking the completed reprocessing run again with its exact same key. [P]

| Projection/table | Before fresh | After fresh | After same-key replay | Delta from replay |
|---|---:|---:|---:|---:|
| `canonical_companies` | 11 | 11 | 11 | 0 |
| `canonical_jobs` | 146 | 146 | 146 | 0 |
| `job_source_observations` | 839 | 961 | 961 | 0 |
| `job_posting_versions` | 735 | 735 | 735 | 0 |
| `acquisition_field_provenance` | 26,009 | 29,791 | 29,791 | 0 |
| `acquisition_rule_outputs` | 839 | 961 | 961 | 0 |
| `acquisition_completeness_reports` | 146 | 146 | 146 | 0 |
| `acquisition_quality_events` | 6,749 | 7,133 | 7,133 | 0 |
| `canonical_company_urls` | 290 | 290 | 290 | 0 |
| `company_logo_enrichments` | 0 | 0 | 0 | 0 |
| `acquisition_duplicate_clusters` | 0 | 0 | 0 | 0 |
| `acquisition_duplicate_members` | 0 | 0 | 0 | 0 |
| `acquisition_duplicate_decisions` | 0 | 0 | 0 | 0 |
| `acquisition_connector_capability_snapshots` | 8 | 8 | 8 | 0 |
| `acquisition_publications` | 5 | 5 | 5 | 0 |
| `acquisition_publication_jobs` | 427 | 427 | 427 | 0 |
| current valid-head jobs | 133 | 133 | 133 | 0 |

Lifecycle after fresh acquisition: 135 active, 4 stale, 7 closed. The 7 closures are the 4 N26 plus 3 Qonto source-state closures from complete snapshots; no canonical job was deleted. [P]

### Fresh source reconciliation

| Source | Request URL | Provider result | Accepted/observed | Canonical delta | Lifecycle result | Warnings/reconciliation |
|---|---|---:|---:|---|---|---|
| N26 / Greenhouse | `https://boards-api.greenhouse.io/v1/boards/n26/jobs?content=true` | HTTP 200, 87 returned | 87 accepted, 87 observations, 0 rejected, 87 distinct IDs | 0 new, 0 updated, 87 unchanged | 4 closed; 87 active source states | 0 unexplained difference; application/detail, HTML-entity, timestamp, and department warnings retained |
| Qonto / Lever | `https://api.lever.co/v0/postings/qonto?mode=json` | HTTP 200, 35 returned | 35 accepted, 35 observations, 0 rejected, 35 distinct IDs | 0 new, 0 updated, 35 unchanged | 3 closed; 35 active source states | 0 unexplained difference; suspicious timestamp warning retained |
| Siemens generic/JSON-LD attempt | `https://www.siemens.com/en-us/company/jobs` | provider status 0; external outcome uncertain | 0 accepted, 0 observations | 0 | no lifecycle change | request `uncertain`, `recovery_required`; task also recorded runner-credit-budget failure; no JSON-LD success claim |

Current observation groups are: `n26_greenhouse` 433 legacy rows with blank connector plus 269 Greenhouse rows; `qonto_lever` 152 legacy rows with blank connector plus 105 Lever rows; one `fixture_source` row and one `x` row. All 961 observations have a non-empty retained raw payload in the inspected table. [P]

Fixtures are quarantined with `enabled=0`, `publication_enabled=0`, `maturity_state=quarantined`, and `quarantine_reason=fixture_or_test_target`; immutable rows remain in admin/raw evidence and neither fixture job is in the current head. Quality metrics exclude quarantined targets: 7,116 report-only events are in the normal quality metric view versus 7,133 physical event rows. [C][P]

## Connector capability matrix

| Connector/path | Can provide | Cannot guarantee/current limitation | Production state |
|---|---|---|---|
| Greenhouse direct API | external ID, title, location, HTML description, department/office/categories, requisition, hosted/detail URL, source metadata | employment, workplace, language, salary, experience, applicant counts are not guaranteed; direct apply may be absent | productive; fresh HTTP 200 |
| Lever direct API | external ID, title, department/team/category, location, commitment, workplace, salary, description, hosted/detail/apply URLs | applicant counts, consistent experience/language, closure/reactivation semantics | productive; fresh HTTP 200 |
| Generic career site / JSON-LD | title, location, description, JSON-LD dates, canonical/detail/apply candidates | no stable API schema; typed department/employment/workplace/language/experience not guaranteed | attempted via Siemens; outcome uncertain, not productive-proven |
| Workday | host classification and declared capability contract | no productive fetch path or current observations | disabled/unregistered, report-only |
| Personio | host classification and declared capability contract | no productive fetch path or current observations | disabled/unregistered, report-only |
| Recruitee | host classification and declared capability contract | no productive fetch path or current observations | disabled/unregistered, report-only |
| SmartRecruiters | host classification and declared capability contract | no productive fetch path or current observations | disabled/unregistered, report-only |
| Company enrichment/logo provider | provider profile/logo evidence when configured | no automatic enrichment during reads/reprocessing; no provider configured | 0 logo-enrichment rows |

No additional ATS connector was newly enabled for this acceptance wave. The four expansion connectors remain disabled/unregistered by design. [P]

## User-facing field, filter, and URL matrix

| Field/control | Raw/source evidence | Normalization/provenance | Authenticated consumer result | Current gap |
|---|---|---|---|---|
| title, company, canonical ID | ATS fields, employer fields, external ID/URL | deterministic identity/evidence; versioned | admin rows and user cards/detail | alias/source-company model incomplete |
| location/locations | ATS location/offices, JSON-LD `jobLocation`, page selectors | string plus typed payload collection | admin and user feed/detail; location filter rendered | multi-location public type is limited |
| description | ATS/HTML/JSON-LD | raw HTML, sanitized HTML, clean text; HTML entities warning retained | authenticated Qonto detail rendered full employer description | public summary/precompute may remain pending |
| source department | ATS department/team/custom fields | source-backed evidence | stored/admin rules; user category may be Unknown | source availability varies |
| Runr function/subfunction | versioned department taxonomy | `versioned_department_mapping`, evidence and confidence | admin function control; user category rendered | subfunction often unknown; taxonomy needs review |
| employment type | ATS commitment/type | taxonomy with present/unknown/unsupported | admin control and user detail; Qonto sample Full-time | Greenhouse coverage is sparse |
| workplace arrangement | Lever/source workplace fields, labeled text | Remote/Hybrid/On-site/etc. with state | admin control and user detail; Qonto sample Hybrid; user-selected Qonto detail showed Unknown | many Greenhouse/user records unknown |
| languages | source fields or explicit description labels | list with inferred/unknown state | admin rules; user feed/detail surface available | 626 jobs have unknown language evidence in current rule view |
| experience | source field or explicit description evidence | min/max/seniority with inferred/unknown state | admin filter and user detail surface | most current rows remain unknown; public min/max loss |
| posted/updated/seen timestamps | source dates plus observed/request lifecycle | UTC timestamps and freshness | feed age/admin freshness | many source posting timestamps are suspicious/blank |
| job-detail URL | ATS hosted/source URL and canonical URL aliases | canonical URL classification | detail link | redirect equivalence is not universal |
| application destination | direct ATS/employer URL, detail/listing/form candidates | verified direct, same-page, detail/listing fallback, unresolved; provenance retained | authenticated user detail exposes actionable Apply where valid | Greenhouse representative is unresolved job-detail-only; same-page child URL persistence remains incomplete |
| company homepage/careers/ATS/source URLs | configured official URLs, source URL, job detail URL | `canonical_company_urls` with type/source/validation | admin Companies exposes URL rows and provenance | N26/Qonto rows currently show only `source` and `job_detail`; no selected official homepage/careers/ATS identity row |
| logo | provider URL/object or deterministic fallback | logo source/verified timestamp | admin Companies shows fallback and not verified | provider rows are zero |
| admin typed filters | query parameters in `acquisition_admin.py` and `list_review_jobs` | search/source/function/workplace/employment/language/seniority/application/freshness/warning/duplicate/completeness/publication | all controls rendered; N26 search filter returned N26 rows; composite controls were submitted | per-filter response contract needs automated authenticated coverage; no duplicate-state data exists to exercise |

Quality/completeness warnings are exposed in admin Rules/Jobs and stored as report-only; they do not block crawling, canonicalization, publication, API access, or UI rendering. [C][A]

## Duplicate algorithm and workflow proof

The current algorithm uses source external ID/canonical URL/identity signature and stable content hashes to avoid collapsing distinct source identities. It writes candidate clusters/members and reasons only. Admin decisions are append-only, explicit, reversible, and separated from merge/publication side effects. [C][S]

Production currently has zero clusters, members, and decisions, so no live candidate, distinct/ignore, merge, split, or undo transition existed to exercise without fabricating production data. The authenticated Duplicates page correctly rendered an empty review queue. The local service/repository workflow suite covers candidate, confirmed duplicate, distinct, unsafe merge/split rejection, merge plan, split plan, and undo while preserving observation/version IDs: `tests/test_duplicate_decisions.py` plus `tests/test_product_completion_wave.py`, 10 tests passed. [T][A][U]

Observed risk cases are therefore code/test cases, not production examples: same source identity with stable-content change becomes a new version; different location-specific requisitions can be marked distinct; no-ID/same-title cases remain indistinguishable candidates; cross-employer same-title jobs are not automatically merged. [C][T]

## Reprocessing, replay, rollback, and operational safeguards

Run: `reprocess_ef912ccf2e9f44ca974222fe60732e55`  
Key: `unified-mapping-production-2026-08-10`  
Final status: `completed`  
Checkpoint: `observation_ffc65009d257463e95239c00166d6ab7`  
Failed observation IDs: none  
Stored counts: 67 batches, 587 observations, 5,870 fields, 585 historical repairs, 2,787 warnings, 0 failed observations, 0 duplicate clusters. [P]

The exact same command was invoked with the same ID and key after completion. It returned `idempotent_replay=true`, did not create a run, did not add semantic versions, and did not add duplicate projections. Remote rollback reference is additive checkpoint metadata; the recoverable local snapshot reference is `.backend_data/reprocessing_backups/production_before_reprocessing_resume_20260810.sqlite3` (not committed). Remote destructive restore remains operator-owned and untested. [P][U]

The worker recovery evidence shows one worker identity owning the import cycle at a time. The original N26/Qonto cycle completed after the new bounded projection deployment; no unrelated process was terminated. [P][A]

## UI/API, tests, and deployment results

Authenticated admin pages rendered: `/admin/acquisition/sources`, `/admin/acquisition/jobs`, `/admin/acquisition/companies`, `/admin/acquisition/duplicates`, `/admin/acquisition/rules`, `/admin/acquisition/reprocessing`, and `/admin/acquisition/publication`. The Publication page showed the valid 133-job head and automatic promotion disabled. [A]

Authenticated user `/jobs` rendered the personalized catalog and selected a Qonto detail with employer description and an Apply action. The selected product detail still displayed Unknown workplace/category and unknown application metadata for that representative role; no application was submitted. [A][U]

Validation passed:

- Python 3.12.7 project interpreter check.
- backend compilation and Ruff checks.
- product completion tests: 3 passed.
- duplicate decision/product completion tests: 10 passed.
- frontend tests: 148 passed.
- ESLint and Vite production build passed.
- live `/health`, `/health/live`, and `/health/ready` checks passed.
- Render API/worker/frontend deployments converged on the pushed runtime-fix commit.

## Prioritized gaps and next actions

1. **Data loss:** add raw-payload retention/archive completeness metrics and a recovery test for legacy rows that only have normalized payloads.
2. **Incorrect semantics:** persist Greenhouse same-page application child URLs; formalize unknown versus unsupported versus inferred values; repair timestamp and closure/reactivation semantics; expose typed locations and experience ranges consistently.
3. **Identity/duplicate risk:** add a first-class company-source/alias model, syndication rules, and a production-safe duplicate canary using preserved observations; keep merge/split/undo explicit and reversible.
4. **Missing enrichment:** configure one approved provider with budget/terms/refresh policy, then backfill profile/logo evidence without overwriting source URLs.
5. **Observability:** add per-target snapshot freshness, uncertain external outcome, lease heartbeat, source-to-canonical reconciliation, and authenticated contract metrics.
6. **Admin usability:** add per-filter authenticated contract tests, conflict/version diff review, and a visible recovery action for uncertain generic requests. Keep quality report-only.
7. **Connector expansion:** do not enable Workday, Personio, Recruitee, or SmartRecruiters until productive fetch, raw retention, authenticated response, closure safety, and rollback evidence exist.
8. **Pre-existing runtime issue:** the frontend bundle still contains the `api_host: ${n}` diagnostic placeholder and the proxy-health check has a DNS failure; this did not block the authenticated app pages above but remains unresolved.

Recommended implementation order: raw-retention/reconciliation observability; application and typed unknown semantics; company-source identity; approved enrichment; duplicate canary; then connector enablement with authenticated production gates.

## LIVE AND READY TO TEST

1. `https://app.userunr.com/admin/acquisition/sources` — select only a ready source, set the paid-source credit ceiling, queue a bounded import, and inspect its status.
2. `https://app.userunr.com/admin/acquisition/jobs` — search `N26`, apply typed source/workplace/employment/language/experience/application/freshness/warning/completeness/publication controls, then open a row.
3. `https://app.userunr.com/admin/acquisition/companies` — open N26 or Qonto and inspect source/job-detail URL provenance plus the deterministic logo fallback.
4. `https://app.userunr.com/admin/acquisition/duplicates` — inspect the empty candidate queue; do not fabricate or auto-merge production records.
5. `https://app.userunr.com/admin/acquisition/rules` — review field states, warnings, connector capabilities, and report-only behavior.
6. `https://app.userunr.com/admin/acquisition/publication` — verify the valid 133-job head; use preview/publish/undo only with an approved import.
7. `https://app.userunr.com/jobs` — search/filter jobs, open a Qonto and N26 detail, verify descriptions and Apply behavior, and confirm that no submission is made by merely opening Apply.

## NOT YET COMPLETE

- Siemens generic/JSON-LD acquisition did not produce a verified response; its request is explicitly `uncertain`/`recovery_required` and needs operator retry through the existing recovery path.
- No live production duplicate cluster existed, so live merge/split/undo evidence is deferred; local tests cover the transitions.
- Logo enrichment provider is not configured; all inspected company logos are deterministic fallback and unverified.
- Four ATS expansion connectors remain disabled/unregistered.
- Company homepage/careers/ATS identity selection and alias history are not fully modeled for N26/Qonto.
- Many source fields remain unknown or unsupported, especially Greenhouse workplace/employment/language/experience and public experience ranges.
- The pre-existing frontend API-host diagnostic/proxy DNS issue remains unresolved.
