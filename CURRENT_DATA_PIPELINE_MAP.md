# Current Runr data-pipeline map

Audit date: 2026-08-10. Repository branch: `deployment/render-turso-r2`.

Evidence labels: `[C]` code, `[S]` schema/migration, `[T]` automated tests,
`[P]` configured production Turso/libSQL query, `[A]` live API/UI check, and
`[U]` uncertain or not live-proven. The inspected database is the remote
production database configured by `user_config/.env`; local SQLite is not
production. Secrets are intentionally omitted. [P]

## Current truth

The deployed API and worker are live on `dc19cc05298e7d69e4548793798030d3bc059eac`.
The frontend API bundle is pinned to `https://runr-api.onrender.com/v1`; the
production diagnostic reports `api_host=runr-api.onrender.com`, an absolute
base URL, and `/v1/health/proxy` status `ok`. [A]

Migrations 045, 046, and 047 are applied. The original reprocessing run
`reprocess_ef912ccf2e9f44ca974222fe60732e55` is completed at observation
`observation_ffc65009d257463e95239c00166d6ab7`, has an empty lease and zero
failed observations; replay with the same idempotency key returned
`idempotent_replay=true`. [P]

Production counts at the end of this audit:

| Area | Count / state |
|---|---:|
| Canonical companies | 16 |
| Company profiles | 14 |
| Company URL evidence rows | 419 |
| Immutable job observations | 1,041 |
| Immutable posting versions | 790 |
| Canonical jobs | 201 |
| Field provenance rows | 32,271 |
| Rule outputs | 1,041 |
| Completeness reports | 201 |
| Report-only quality events | 7,334 |
| Logo enrichment rows | 0; provider configured, execution intentionally off |
| Duplicate clusters / members / decisions | 0 / 0 / 0 |
| Publications / publication rows | 5 / 427 |
| Current valid publication head | 133 jobs; fixture jobs 0 |
| Uncertain acquisition requests | 0 |

Lifecycle counts are active 170, stale 4, closed 7, and unknown 20. Unknown
states are expected for incomplete bounded snapshots: a partial source page is
not treated as an authoritative empty catalog and cannot close jobs. [C][P]

Connector observations are Greenhouse 702, Lever 257, Workday 10, Personio
25, Recruitee 20, SmartRecruiters 20, generic/JSON-LD 5, and other career-site
2. Fixture targets `fixture_source` and `x` remain immutable evidence but are
quarantined from acquisition and normal quality metrics; neither is in the
publication head. [P]

## End-to-end path

```text
manifest / configured source registry
  -> target registry -> cycle/task/request leases
  -> direct ATS API, generic JSON-LD, or bounded career-site fetch
  -> raw response + retry/cost telemetry
  -> immutable source observation and raw-payload hash
  -> extraction / URL classification / description representations
  -> typed normalization and taxonomies
  -> company identity + URL evidence
  -> job identity + canonical job + immutable semantic version
  -> field evidence + rule outputs + completeness + quality warnings
  -> duplicate candidate review (human decision only)
  -> explicit publication preview -> valid publication head
  -> authenticated admin read models and user feed/detail
```

## Processing-stage map

| Stage | Code entry points | Tables/models | Inputs | Outputs | Owner rules |
|---|---|---|---|---|---|
| Environment and safety | `backend/config/env_schema.py`, `backend/database/connection.py`, `scripts/reprocess_acquisition.py` | `schema_migrations`, `config_values` | Runtime env, Turso/R2 configuration, project interpreter | Selected remote DB/storage and operation safeguards | Production requires remote Turso/libSQL; Python 3.12.7 is mandatory; remote reprocessing is additive and explicitly acknowledged. |
| Source/connector registry | `backend/acquisition/manifest.py`, `backend/application/admin_job_import.py`, `backend/application/acquisition_scheduler.py`, `SqliteAcquisitionStore.ensure_targets` | `acquisition_targets` | Manifest target, company profile, source token, connector, limits | Careers URL, ATS/API URL, official host allowlist, maturity and publication flags | Manifest is server-owned; canonical target URLs are normalized; fixtures are quarantined; target flags do not by themselves publish. |
| Acquisition planning | `AdminJobImportService.plan_import`, `start_import` | `admin_job_imports`, `admin_job_audit_events` | Authenticated source IDs and bounded scope | Idempotent queued import, cost/request forecast, audit event | No automatic publication; paid web imports require a credit ceiling; direct official connectors have no ScrapeOps charge. |
| Lease and dispatch | `PhaseAAcquisitionScheduler.run_controlled_import`, `_execute_target` | `acquisition_cycles`, `acquisition_tasks`, `acquisition_requests`, `acquisition_budget_reservations` | Queued import, target, request/credit ceilings | Durable lease, dispatch state, latency, request result | One deployed worker is the queue writer; uncertain outcomes require explicit release/retry; no duplicate launcher. |
| Connector fetch | `ats_router.fetch_ats_snapshot`, `ats_expansions.fetch_expansion_snapshot`, `generic_jsonld.fetch_generic_snapshot`, `company_career_sites.scrape_company_career_sites` | Request detail and raw retention fields | Official ATS/API URL or bounded careers page | Bounded jobs, source count, raw payload, retry/page warnings | Workday, Personio, Recruitee, SmartRecruiters, Greenhouse, Lever and generic JSON-LD use direct bounded paths; incomplete snapshots never close source states. |
| Observation retention | `SqliteAcquisitionStore.ingest_snapshot` | `job_source_observations`, source-state tables | Accepted normalized source records plus request context | Immutable observation, external ID, source URLs, raw payload/hash, observed time | Observations are never rewritten or deleted; projections are replayable. |
| Extraction and URL mapping | `backend/acquisition/phase_b.py`, `backend/acquisition/quality.py`, URL/application helpers | Observation/version/provenance/quality tables | ATS objects, HTML, JSON-LD, links/forms | Title, locations, descriptions, source metadata, timestamps, detail/apply URL candidates | Direct application destination wins over detail/listing fallback; careers index URLs are not Apply destinations. |
| Unified normalization | `backend/acquisition/unified_mapping.py`, `rule_registry.py` | `acquisition_field_provenance`, `acquisition_rule_outputs`, `canonical_company_urls` | Extracted fields and source evidence | Typed fields, taxonomy values, field states, rule/version metadata | Structured source > raw payload > explicitly labelled text; unknown, unsupported, inferred and conflicting states remain representable. |
| Company identity and URLs | `canonical_employer_name`, `SqliteAcquisitionStore` company helpers, `company_enrichment.py` | `canonical_companies`, `canonical_company_aliases`, `canonical_company_profiles`, `canonical_company_urls` | Employer name, configured homepage/careers/ATS, observed source URLs | Company identity, aliases, selected primary URL per type, profile evidence | Configured official URLs are source-backed and selected; enrichment cannot overwrite stronger source evidence; ambiguous aliases are not silently merged. |
| Company enrichment/logo | `CompanyEnrichmentService`, `CompanyLogoEnrichmentService`, provider adapter | `company_enrichment_targets`, `company_enrichment_attempts`, `company_logo_enrichments`, profile logo columns | Company URL/profile and explicit provider configuration | Provider attempts, profile fields, logo object/provenance | `official_website` is configured in Render; execution is `0`, so no logo row is fabricated. |
| Job identity/versioning | `backend/domain/job_identity.py`, acquisition identity helpers, version writer | `canonical_jobs`, `canonical_job_external_ids`, `canonical_job_url_aliases`, `job_source_states`, `job_posting_versions` | External ID, canonical URL, employer/title/location, stable content | Canonical job, aliases, lifecycle, immutable version/hash | Source+external ID and canonical URL are preferred; stable content hash excludes volatile telemetry; changed stable content appends a version. |
| Provenance/quality/completeness | `_persist_unified_mapping`, completeness rules, `rule_registry.py` | `acquisition_field_provenance`, `acquisition_rule_outputs`, `acquisition_completeness_reports`, `acquisition_quality_events` | Candidate field values and evidence | Selected/unselected evidence, confidence, rule output, completeness and warnings | Report-only. Missing metadata, unsupported values, and quality warnings do not stop ingestion, canonicalization, publication, API, or UI rendering. |
| Duplicate review | Duplicate candidate and decision services | `acquisition_duplicate_clusters`, `acquisition_duplicate_members`, `acquisition_duplicate_decisions`, merge/split audit tables | Similarity candidates and human decision | Candidate, distinct/ignore, merge/split plan, undo history | No automatic merge. Immutable observations and versions survive decisions; live production has no cluster yet. |
| Publication | `create_job_import_preview`, `publish_job_import_preview`, `undo_last_job_publication` | `acquisition_publications`, `acquisition_publication_jobs`, `acquisition_publication_head`, admin audit | Explicit preview and administrator action | Staging snapshot, valid head, reversible undo | Acquisition and reprocessing never promote a publication; fixture-only jobs are excluded from previews. |
| API/read models | `backend/api/routes/acquisition_admin.py`, `job_import_admin.py`, `acquisition_catalog.py`, `personalized_jobs_service.py` | Canonical/read-model/evidence/publication tables | Authenticated admin/user and filters | Admin inspection/operation JSON; user feed/card/detail JSON | Raw payloads and evidence are admin-only; user reads the valid publication head. |
| Reprocessing/backfill | `scripts/reprocess_acquisition.py`, `backend/acquisition/reprocessing.py` | `acquisition_reprocessing_runs`, `acquisition_stage_results`, projection tables | Immutable observations, idempotency key, checkpoint | Additive versioned projections, durable counts/checkpoint and failure IDs | Project venv only; CAS lease and stale reclaim; bounded batches; per-observation isolation; no destructive rollback of immutable evidence. |

## Canonical entity relationship map

```text
company: canonical_companies
  ├─ aliases: canonical_company_aliases
  ├─ profiles/enrichment: canonical_company_profiles, company_enrichment_*
  ├─ official URL evidence: canonical_company_urls
  └─ owns canonical_jobs

source registry: acquisition_targets
  └─ cycles/tasks/requests -> job_source_observations (immutable)
                                  ├─ raw payload + source URL + external ID
                                  ├─ acquisition_field_provenance
                                  ├─ acquisition_rule_outputs / quality events
                                  └─ canonical job

canonical_jobs
  ├─ external IDs / URL aliases / source states
  ├─ current_version_id -> job_posting_versions (immutable semantic versions)
  └─ publication job -> acquisition_publications -> singleton publication head

rule code/version metadata -> evidence, rules, completeness, quality, reprocessing
identity similarity -> duplicate cluster/member -> append-only decision/audit history
```

There is no standalone complete `company_source` table. Source identity is
currently composed from `acquisition_targets`, observation source fields, and
company URL evidence. That is an explicit model gap, not an inferred entity.

## Field lineage matrix

| User-facing field | Raw source locations | Extraction / normalized type | Precedence | Provenance / confidence | Completeness rule | API and UI/filter consumer | Known gap |
|---|---|---|---|---|---|---|---|
| Job ID / canonical ID | ATS `id`, `external_job_id`, canonical URL | Identity resolver / stable string | Source+external ID, then URL/signature | Observation/version IDs; deterministic when stable ID exists | Identity warning only | Feed/detail, admin Jobs | Cross-source weak-ID ambiguity |
| Title | ATS title, JSON-LD `name/title`, page title | Connector/JSON-LD parser / string | Structured > JSON-LD > page | Source field evidence; high when present | `title` warning | Feed card/detail, search | No multilingual reconciliation |
| Company name / company ID | ATS employer, `company.name`, configured canonical employer | Employer normalizer / string + FK | Configured canonical > structured employer > normalized text | Company and observation evidence | Company identity warning | Feed/detail/company page/admin Companies | Alias decision history is incomplete |
| Location(s) | ATS office/location, JSON-LD `jobLocation`, page selectors | Location parser / collection + display string | Structured > JSON-LD > page | Field evidence; source-dependent | `location` warning | Cards, detail, location filter/admin | Public multi-location type is not uniform |
| Source department/team/category | `department`, `team`, ATS family/category, labelled description | Connector aliases / strings | Explicit structured field > raw payload > label | Observation field evidence | Department/category warning | Detail/admin inspection/filter | Connector coverage varies |
| Runr function/subfunction | Source department/category/team and mapping taxonomy | Versioned taxonomy mapper / enum-like strings | Source metadata > explicit labelled text > inferred mapping | Rule version and state; mapping confidence is not calibrated | Report-only | Feed/detail/admin typed filters | `Other` semantics need product agreement |
| Employment type | `employment_type`, `employmentType`, `type`, `commitment`, Workday time type | Alias mapper / taxonomy | Structured ATS > raw source > labelled text | Field evidence/state; structured high, inferred lower | Report-only | Feed/detail/admin filter | Not available from every connector |
| Workplace arrangement | `workplace_arrangement`, `workplaceType`, `remoteType`, `remote`, labelled text | Arrangement taxonomy / On-site, Hybrid, Remote, Flexible, Unknown | Structured > labelled text | Evidence/state; inferred is explicit | Report-only | Feed/detail/filter/admin | Geographic remote restriction is separate and sparse |
| Language(s) | `languages`, requirements, JSON-LD/description language lines | List/proficiency parser / list of language records | Structured > explicit labelled text | Field evidence; inferred state preserved | Report-only | Detail/filter/admin | Proficiency and taxonomy incomplete |
| Experience/seniority | `seniority`, `experience_level`, years fields, labelled description | Experience parser / seniority + optional min/max | Structured > explicit description | Rule/evidence; inferred lower confidence | Report-only | Feed/detail/filter/admin | Public min/max exposure is incomplete |
| Salary | Salary/range/compensation/custom ATS fields | Salary parser / amount, currency, period | Structured > raw source | Evidence; connector-dependent | Report-only | Detail/filter/admin | Currency comparability incomplete |
| Description | ATS content, JSON-LD `description`, page HTML | Raw HTML + sanitized HTML + clean text | Structured source > JSON-LD > page | Observation/version/hash; high when present | `full_description` warning | Detail and admin; clean text in feed | Public representation is primarily clean text |
| Job detail URL | `url`, `link`, `source_url`, `hostedUrl`, `absolute_url`, canonical/link tags | URL canonicalizer / HTTP URL | Source canonical/detail > aliases | Candidate evidence and observation | `job_detail_url` warning | Detail link, admin | Redirect equivalence is not universal |
| Application URL | `apply_url`, `application_url`, ATS apply route, verified link/form | Application resolver / URL + status | Direct employer/ATS apply > detail fallback | Candidate validation and rule version | Direct-apply warning | Apply action/detail/admin | Embedded/redirect validation varies |
| Application method/status | Link/form/ATS hosted route, URL classification | Destination classifier / direct, same-page, external, unavailable | Verified destination > fallback | Provenance and validation state | Report-only | Apply action/admin | A detail URL fallback is actionable only when explicitly classified |
| Posted/updated timestamps | `datePosted`, `source_posted_at`, ATS created/updated/published | Timestamp normalizer / UTC ISO | Explicit publication date; no silent substitution | Source field and observed_at; deterministic when explicit | Timestamp semantics warning | Freshness/sort/detail/admin | Some ATS dates are ambiguous |
| First/last seen and verified | Observation/request/canonical lifecycle timestamps | Store lifecycle writer / UTC ISO | Durable observation/request state | Cycle/request/observation provenance | Freshness report | Admin and detail | Observation age is not publication age |
| Lifecycle | Complete source snapshot, source state, absence history | State machine / active, stale, closed, unknown | Explicit source state + complete snapshot | Source state and observation history | Report-only | Feed visibility/detail/admin | Reactivation is modeled but no live reactivation canary exists |
| Completeness/warnings | Missing field checks, connector warnings, source reconciliation | Completeness/rule engine / report state + warning list | All evidence retained; no silent suppression | Rule version, field evidence, severity | Always report-only | Admin warnings; UI may show badges | Not a publication/API gate |
| Freshness/publication state | Observation times, current head, publication row | Read-model serializer / state object | Current publication and timestamps | Deterministic read-model metadata | Not a gate | Feed/detail/admin | No public version diff UI |
| Company homepage | Manifest `company_profile.website`, official company URL evidence | Configured URL mapper / URL | Explicit official source > provider | `configured_official`, selected primary | Company URL warning only | Company detail/admin Companies | Only five configured source companies have homepage rows |
| Company careers URL | Manifest `careers_page`, careers/source URL | URL mapper / URL | Explicit careers source > provider | URL row + source observation/config | Company URL warning only | Company detail/admin | No separate company-source entity |
| Company ATS URL | Manifest `ats_url`, detected ATS/source URL | URL mapper / URL | Explicit ATS source > detected source | URL row + connector provenance | Company URL warning only | Company detail/admin | ATS URLs are not application URLs unless job-level resolver says so |
| Company aliases | Employer variants, configured canonical name | Alias resolver / string list | Explicit alias evidence only | Alias/source audit when present | Report-only | Admin/company detail | Manual alias decision UX is limited |
| Company profile fields | Company payload/profile/enrichment provider | Profile alias mapper / typed field records | Source profile > enabled provider | Per-field state, source URL, verification time | Report-only | Company detail/admin | Many fields remain unknown |
| Company logo | Provider URL/content, configured logo object | Logo adapter / object metadata | Explicit provider > stored fallback | Logo enrichment row, provider/rule version | Report-only | Company detail/card/admin | Provider is configured but execution is intentionally off; zero rows |

## Source/connector capability matrix

| Connector | Production registry and request | Can provide | Cannot guarantee / current limitation | Current observations |
|---|---|---|---|---:|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | ID, title, location, description, department, offices, categories, hosted/apply URLs, raw timestamps | Employment, workplace, language, salary, experience are sparse/optional | 702 |
| Lever | `api.lever.co/v0/postings/{slug}?mode=json` | ID, title, categories/team, location, commitment, workplace, salary, description, hosted/apply URL, timestamps | Applicant counts, closure semantics, consistent language/experience | 257 |
| Workday | `wday/cxs/{tenant}/{site}/jobs` POST | Job family/category, external path, title, location, description, detail URL, time type/remote when supplied | XML/tenant variations; page may be partial; no closure from bounded page | 10 |
| Personio | `<target>/xml` | Position ID, name, department/team, location, employment/type, description, detail URL when supplied | XML field variation, language/experience/salary consistency | 25 |
| Recruitee | `<target>/api/offers?limit=&offset=` | Offer ID/title, department/team, location, description, employment/workplace when supplied, detail/apply URLs | Coverage depends on public offer payload; incomplete pagination is report-only | 20 |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/{slug}/postings?limit=10&offset=0` | ID, title, department, location, description, `jobs.smartrecruiters.com` detail/apply candidates, raw payload | API does not guarantee all typed metadata; current one-page result is intentionally incomplete | 20 |
| Generic/JSON-LD | Siemens listing URL plus up to bounded detail links | JSON-LD title, description, location, datePosted, canonical/detail/apply candidates; raw HTML | No stable API schema; typed department/employment/workplace/language/experience are sparse; snapshot partial by cap | 5 |
| Generic career-site/ScrapeOps | `company_career_sites.py` | HTML/page discovery, JSON-LD, conservative location and apply candidates | Paid cost ceiling required; structured metadata varies | 2 |
| Fixture/test | Test payloads only | Contract coverage and raw evidence | Not production source; quarantined and excluded from normal metrics/head | 2 |

## Duplicate algorithm and evidence

The current algorithm first groups by stable source+external ID, then by
canonical URL/URL aliases, then uses conservative employer/title/location and
stable-content similarity. It emits a candidate cluster with reason/evidence;
it does not merge automatically. Human decisions are append-only and merge,
split, distinct/ignore, and undo preserve observation/version rows. [C][T]

Production currently has zero clusters, members, and decisions. Therefore no
live false merge or missed-duplicate example can honestly be claimed. The
configured data does show the indistinguishable boundary: source rows with
missing/weak IDs and similar normalized title/employer/location require a
human decision; fixture rows are quarantined rather than used as a duplicate
canary. Local tests cover same identity with changed content (new version),
unsafe merge/split rejection, explicit distinct/ignore, merge plan, split plan,
and undo without losing immutable rows. [P][T][U]

## UI and API capability matrix

| Capability | Supported now | API-supported but missing in admin | Stored but not exposed to users | Not yet modeled / live-proven gap |
|---|---|---|---|---|
| Admin overview, source registry, bounded import plan/start | Yes; Sources and Overview pages | — | Raw payload, request detail and cost telemetry | None for the current direct connector wave |
| Admin job inspection/search | Yes; Jobs page and admin inspection API | Some deep provenance/rule evidence requires API/read model inspection | Full raw payload, alternate field evidence, rule outputs | Rich side-by-side source diff |
| Typed function/subfunction, employment, workplace, language, seniority, location filters | API and service support; core controls are present | Some typed controls are not equally surfaced in every admin table | Source fields and inferred/conflicting evidence | Calibrated confidence and complete connector parity |
| Company page and URL types | API/read model and Companies page; homepage/careers/ATS rows configured for five companies | Alias decision history and full profile provenance views | Provider attempts and unselected URL candidates | Standalone company-source entity |
| Logo | Profile/logo serializer shape exists | No admin execution control needed while provider is off | Provider/logo rows would be stored but currently zero | Provider execution and live logo coverage |
| Duplicate candidate/decision workflows | Service and local tests cover candidate, distinct, merge, split, undo | No live production cluster to exercise safely | All decision/audit evidence if created | Live canary without fabricating production duplicates |
| Publication preview/publish/undo | Supported; current head unchanged | Fixture-excluding preview path is available | Staging snapshot and audit events | No automatic publication by design |
| Personalized feed/detail/application | Authenticated API/UI verified; current head has 133 jobs | Raw evidence and full provenance intentionally admin-only | Source payload, field evidence, quality detail | Public version diff and complete typed-field display |
| Reprocessing/backfill | CLI, lease/checkpoint, idempotent replay | Detailed per-observation report available through admin/API | Internal rule outputs and failure references | Automated remote restore/rollback execution |

## Prioritized gap list

### Data loss

1. Generic and ATS snapshots are bounded; incomplete pages preserve evidence but
   do not prove a complete catalog. [P]
2. Raw payload retention is present for inspected connector observations, but
   long-term object-storage archival and restore is not an automated acceptance
   test. [C][U]

### Incorrect semantics

1. Unknown lifecycle is correct for partial snapshots but is easy for consumers
   to misread as empty; keep completeness beside lifecycle in every serializer.
2. Confidence is a bounded mapper score, not a calibrated probability.
3. Public experience/language/salary representations are less expressive than
   stored evidence for some connectors.

### Identity/duplicate risk

1. There is no standalone `company_source` entity or complete alias decision
   history.
2. Live duplicate clusters and manual decisions are zero, so live merge/split/
   undo safety remains unproven.
3. Weak-ID cross-source cases remain human-review cases.

### Missing enrichment

1. `official_website` is configured but disabled (`RUNR_COMPANY_ENRICHMENT_ENABLED=0`);
   logo coverage is therefore zero by design.
2. Most company profile fields are explicitly unknown rather than fabricated.

### Observability

1. Acquisition uncertainty now records a safe exception class, but per-target
   connector metrics should be emitted directly into structured worker logs.
2. Source reconciliation would benefit from a durable snapshot manifest with
   source-reported count, accepted count, and closure authority in one row.

### Admin usability

1. Expose raw-vs-normalized-vs-selected field evidence and provenance in one
   inspection view.
2. Add a source-specific completeness/partial-snapshot banner before a user
   previews publication.
3. Add live duplicate canary fixtures in an isolated non-production database,
   not by mutating this production catalog.

## Recommended implementation sequence

1. Add snapshot manifests and first-class partial/complete semantics to the
   admin reconciliation view.
2. Add company-source and alias decision entities with reversible audit history.
3. Add a calibrated confidence contract and public typed-field serializers.
4. Enable official-website/logo enrichment only after provider credentials,
   budget, cache, and rollback controls are approved.
5. Run isolated duplicate merge/split canaries, then expose the same workflow
   to production admins without automatic merges.
6. Add object-storage backup/restore drills and a durable per-target worker
   telemetry dashboard.
