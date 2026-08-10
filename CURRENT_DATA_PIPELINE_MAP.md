# Current Runr data-pipeline map

Audit date: 2026-08-10. Evidence tags: **[C]** executable code, **[S]**
migrations/schema, **[T]** tests/fixture runs, **[P]** read-only query against
the configured remote database, **[A]** live HTTP smoke check, **[U]**
uncertain or not observable without an authenticated session.

## Current truth

The inspected environment is the configured `user_config/.env` target, not a
local database: `DATABASE_BACKEND=turso`, `RUNR_ENV=production`, remote
libSQL/Turso configured, and R2/S3 object storage configured. No secret value
is reproduced here. [P]

The current production database has 45 applied migrations, 587 immutable job
observations, 609 posting-version rows, 141 canonical jobs, 11 canonical
companies, 7,316 field-evidence rows, 127 completeness reports, 4,002 quality
events, 252 company URL rows, zero logo-enrichment rows, zero duplicate
clusters, five publication rows, and one current publication head. [P]

N26/Greenhouse contributes 433 observations and Qonto/Lever 152. The database
also contains two one-row fixture/test sources (`fixture_source` and `x`) and
five quarantined/unproven bounded probes; those are not evidence of productive
connector coverage. [P]

The public head is valid and contains 133 jobs; canonical jobs include N26 97,
Qonto 42, Fixture source 1, and x 1. The current head was published at
`2026-08-10T00:02:55.648984+00:00`. [P]

Complete: immutable observation retention, ATS routing for Greenhouse/Lever,
URL/application classification, description representations, canonical job
identity/versioning, field provenance, report-only quality, conservative
duplicate candidates, publication-head control, admin inspection APIs, and
resumable reprocessing code. [C][S][T][P]

Partial: company URL/profile coverage, timestamp semantics, source metadata,
field precedence, enrichment, duplicate review, user-facing publication of
the new normalized fields, and production reprocessing. The production
reprocessing row has a durable checkpoint at 80 observations but is currently
stale/running after an external duplicate launcher was stopped; it is not a
completed backfill. [C][P]

Missing or not proven in the inspected data: logo provider results, durable
company-source/alias decision history, automatic semantic conflict resolution,
connector capability rows for every ATS, reactivation evidence, authenticated
production API bodies, and a tested automatic rollback of remote additive
projections. [P][U]

Quality and completeness are annotations. They do not reject ingestion, stop
canonicalization, block publication, or filter the user feed unless a separate
explicit publication/review action does so. [C][T]

## End-to-end path

```text
manifest / configured source registry
  -> target + acquisition cycle/task/request/attempt leases
  -> connector/API/career-page response with retry policy
  -> immutable job_source_observations (raw payload + hash + source metadata)
  -> extraction and typed normalization
       -> canonical URL/application destination
       -> raw/sanitized/plain description
       -> source metadata + timestamp semantics
       -> unified_mapping_v1 fields/company URLs/taxonomies
  -> company and job identity resolution
  -> canonical company/job + immutable posting version
  -> field evidence, rule outputs, completeness, quality events
  -> candidate duplicate clusters (human review; no auto merge)
  -> explicit publication preview -> valid publication head
  -> API serializers/read models
       -> admin acquisition console / legacy job-import dashboard
       -> authenticated personalized-jobs feed/detail and filters
```

## Processing stages and ownership

| Stage | Code entry points | Database tables/models | Inputs | Outputs | Owner rules |
|---|---|---|---|---|---|
| Environment and safety | `backend/database/connection.py`, `backend/config/*`, `scripts/reprocess_acquisition.py` | `config_values`, `schema_migrations` | Runtime flags and env file | Selected SQLite or remote libSQL target, storage backend | Production requires remote configuration; the reprocessor requires project Python 3.12.7 and explicit `--apply --yes`; remote apply requires the explicit additive-rollback acknowledgement. [C] |
| Source registry | `backend/acquisition/manifest.py`, `application/acquisition_scheduler.py`, `SqliteAcquisitionStore.ensure_targets()` | `acquisition_targets` | Manifest, target config, provider/connector | Canonical target URL, request URL, connector, source token, employer hosts, limits, maturity | Disabled/unproven/quarantined targets do not become productive evidence; production currently has manually enabled test rows. [C][P] |
| Career/ATS discovery | `backend/connectors/company_career_discovery.py`, `tools/discover_company_careers.py`, `connectors/ats_router.py` | Target config and URL observations | Homepage/careers URL, host/path | Detected ATS, board slug, careers/ATS candidates | Host suffix routing is deterministic; discovery can identify Greenhouse, Lever, Workday, Personio, Recruitee, SmartRecruiters; only Greenhouse/Lever are productive in the inspected database. [C][P] |
| Acquisition scheduling | `AcquisitionScheduler.run_due_cycle()`, `claim_due_cycle()`, `ensure_cycle_tasks()`, `claim_next_task()` | `acquisition_cycles`, `acquisition_tasks`, `acquisition_requests`, `acquisition_target_attempts`, `acquisition_stage_results` | Due target, window key, leases | Cycle/task/request reservations, attempt metrics, retries | Bounded requests and lease ownership; repeated cycle keys are idempotent; failure is recorded before retry. [C][S] |
| Connector fetch | `connectors/ats_router.py`, `connectors/company_career_sites.py`, `connectors/bounded_probe.py`, job-board collectors | Request/attempt/evidence tables | Official API URL or career page | Normalized connector jobs, request status/credits, raw response payload | Greenhouse uses boards API `.../v1/boards/{token}/jobs?content=true`; Lever uses `.../v0/postings/{slug}?mode=json`; generic career pages use bounded crawling; LinkedIn is a separate portal strategy and is not a current productive target. [C][P] |
| Retry and transport evidence | acquisition scheduler, `integrations/scrapeops.py`, request/attempt stores | `acquisition_requests`, `acquisition_target_attempts`, `acquisition_quality_events` | HTTP/network failures, retryable statuses, cost telemetry | Attempt history, retry counts, error categories, credits | Retry is bounded and transport-aware; content failures do not fabricate jobs. Exact production retry distribution was not queried. [C][U] |
| Immutable source record | `SqliteAcquisitionStore.ingest_snapshot()` | `job_source_observations` | Connector job plus target/cycle/task context | External ID, original URL, apply URL, source ATS, payload JSON, raw payload JSON/hash, observed timestamp | Observation rows are immutable by triggers after migration 044; raw payload retention is additive and historical rows may have only older payload fields. [C][S][P] |
| Extraction | `backend/acquisition/quality.py`, manual URL helpers | Observation payload and version payload | Raw HTML/JSON-LD/ATS fields | Title, location, URLs, description source, application candidates, metadata, timestamps | Extraction is deterministic; HTML is sanitized and JSON-LD/job markup preferred for generic pages; unsupported fields remain explicit rather than inferred silently. [C][T] |
| URL and application mapping | `classify_job_url()`, `resolve_application_destination()`, `phase_b.py`, `unified_mapping.py` | Observation/version payload, `canonical_job_url_aliases`, `acquisition_field_provenance` | Job/detail/apply/link/candidate URLs | Canonical URL, job-detail URL, verified direct apply URL, user-facing fallback, classification and validation metadata | A job-detail/listing URL is not promoted to direct apply; employer/official ATS candidates are distinct; validation is evidence-backed and admin resolution is audited. [C][T] |
| Description mapping | `normalize_description()` | Version payload, raw observation | Raw description HTML/text | `description_raw`, sanitized HTML, clean text, one-pass entity decoding | Raw and derived representations coexist; scripts/forms are removed from sanitized HTML; clean text is used by product serializers. [C][T] |
| Typed source metadata | `normalize_source_metadata()`, `normalize_source_timestamps()` | Version payload, provenance rows, quality events | ATS structured fields and raw payload | Department/team/office/location collection/employment/workplace/language/salary/requisition/categories/custom fields/seniority/education/status and source lifecycle timestamps | Connector capabilities are explicit where known; unknown connector capability is different from unsupported field; source `created/posted/updated/closed/reopened` semantics are retained. [C][T] |
| Unified field map | `backend/acquisition/unified_mapping.py::map_job_fields()` | `acquisition_field_provenance`, `acquisition_rule_outputs`, `canonical_company_urls` | Normalized job + company objects | Typed normalized fields, taxonomies, evidence, confidence, extraction method, rule version | Precedence is structured source field, then raw source field, then explicitly labeled description evidence; conflicts are flagged and not silently selected. The current storage vocabulary retains legacy `present`; `known` is the product/read-model compatibility name. [C][S] |
| Company identity | `canonical_employer_name()`, company profile helpers, `ensure_company()` | `canonical_companies`, `canonical_company_aliases`, `canonical_company_profiles`, `canonical_company_urls` | Employer label, official host, company object, careers/homepage URLs | Canonical company ID/name/entity kind, aliases, profile fields, URL candidates | Identity is conservative and evidence-backed; homepage/careers/ATS URLs are separate records; enrichment must not overwrite source evidence. Alias decision history is incomplete in current production data. [C][P] |
| Job identity | `backend/domain/job_identity.py`, acquisition store identity helpers | `canonical_jobs`, `canonical_job_external_ids`, `canonical_job_url_aliases`, `job_source_states`, relationships | Source ID, canonical URL, employer, title/location/signature | Canonical job ID, external ID links, URL aliases, identity key/signature, source state | Prefer source+external ID and canonical URL; canonicalize tracking/query noise; weak identity stays separate. Cross-source identity is conservative. [C][T] |
| Versioning and lifecycle | `_ensure_version()`, stable payload/content hash helpers, source snapshot completion | `job_posting_versions`, `canonical_jobs`, `job_source_observations` | Stable content fields and observed source state | Version number, semantic/content hash, current pointer, first/last seen, verified, closed/source timestamps | Identical stable content reuses a version; stable content changes create a new immutable version; closure/reactivation is source-state evidence, not disappearance from one partial crawl. Exact reactivation examples were not found. [C][S][U] |
| Provenance and rule outputs | `_persist_unified_mapping()`, provenance writers, `rule_registry.py` | `acquisition_field_provenance`, `acquisition_rule_outputs`, `acquisition_stage_results` | Mapper records and observation/version IDs | Per-field raw/normalized/state/source/source field/method/evidence/confidence/observed time/selected/reason/rule; semantic output hash | Rule version is `unified_mapping_v1`; quality/completeness and description/application families are separate registered rule families. [C][S] |
| Company enrichment | `CompanyEnrichmentService`, `run_due_company_enrichment()`, logo/object-storage helpers | `company_enrichment_targets`, `company_enrichment_attempts`, `canonical_company_profiles`, `company_logo_enrichments`, R2 object keys | Explicit worker/provider invocation and company URL | Provider attempts, profile evidence, cached logo metadata/object key | Disabled by default for catalog reads; no network enrichment is invoked by reprocessing; current production has zero logo-enrichment rows. [C][P] |
| Duplicate detection | `_store_duplicate_candidates()`, `list_admin_duplicate_clusters()` | `acquisition_duplicate_clusters`, `acquisition_duplicate_members`, job relationships | Same company/title/location/content hash and identity evidence | Candidate cluster, score, reasons, review history | Candidate only; no automatic merge. Review/merge decision model is incomplete and no current production clusters exist. [C][P] |
| Quality/completeness | `completeness_rules()`, `quality.py`, reprocessor | `acquisition_completeness_reports`, `acquisition_quality_events`, `acquisition_version_quality` | Canonical fields, evidence, publication/review state | Pass/warning, state vocabulary, denominator, report-only percentages, warning events | Warnings never block ingestion or publication; completeness is not a product eligibility gate. [C][T] |
| Publication | admin import service and acquisition store preview/publish/undo | `acquisition_publications`, `acquisition_publication_jobs`, `acquisition_publication_head`, audit rows | Explicit approved import/preview and admin action | Valid publication and single head read model | Only an explicit publish promotes the head; reprocessing cannot promote it; undo is an admin action. [C][P] |
| API/read models | `api/routes/acquisition_admin.py`, `job_import_admin.py`, `acquisition_catalog.py`, `personalized_jobs_service.py` | Read joins over canonical, version, evidence, publication/profile tables | Authenticated request and filters | Admin inspection/read model; user feed/card/detail serializers | Admin routes require admin identity; user routes require user identity and current publication. New normalized fields are stored more broadly than the public serializer exposes. [C][U] |
| Reprocessing/backfill | `scripts/reprocess_acquisition.py`, `acquisition/reprocessing.py` | Run/stage/checkpoint/rule/provenance/quality/duplicate tables | Preserved observations and explicit scope/idempotency key | Bounded additive projections, checkpoint, counts, rollback reference | Project interpreter guard, local backup, remote additive acknowledgement, compare-and-swap lease, stale reclaim, local SQLite savepoint per observation, remote libSQL replayable batch first with isolated per-observation retry fallback, resumable failure list, no delete/merge/publish. [C][T] |

## Canonical entity relationship map

```text
acquisition_target (source registry: connector, URL, ATS/provider, limits)
  1 -> many acquisition_cycles -> many tasks -> many requests/attempts
  1 -> many job_source_observations (immutable raw evidence)
job_source_observation
  many -> 1 canonical_job
  many -> 1 canonical_company (through canonical_job/company_id)
  1 -> many job_posting_versions (source_observation_id)
  1 -> many acquisition_field_provenance (entity_kind=job)
  1 -> many acquisition_rule_outputs
canonical_company
  1 -> many canonical_company_aliases / canonical_company_urls / profiles
  1 -> many company_enrichment_targets -> attempts -> logo/profile enrichments
canonical_job
  1 -> many external_ids / URL aliases / source states / relationships
  1 -> many immutable job_posting_versions
  1 -> many duplicate members -> duplicate cluster
  1 -> many field evidence / completeness reports / quality events
job_posting_version
  selected by canonical_job.current_version_id
  included by acquisition_publication_jobs -> acquisition_publication
acquisition_publication
  1 -> current acquisition_publication_head (single public pointer)
rule version (code registry + row on every projection)
  scopes rule outputs, evidence, completeness, versions/publications, reprocessing
```

The database does not have one table literally named “company source” or
“field evidence”: source ownership is represented by `acquisition_targets`,
observation `target_id/source_ats/source_token`, and the source fields in
`acquisition_field_provenance`. This is a real modeling gap, not an inferred
entity. [S]

## Field lineage matrix

`precedence` means the current deterministic selection order. `confidence` is
the mapper's bounded score; it is not a probability calibrated against labels.
Missing/unsupported/unknown values are retained as states and do not become
empty-string facts in the user serializer.

| Published field | Raw source locations and extraction | Normalized type / precedence | Provenance, confidence, completeness | API / consumer | Known gap |
|---|---|---|---|---|---|
| `posting_id`, `canonical_job_id` | Source external ID, canonical URL, employer/title identity | String ID; source ID then canonical URL identity | Observation/version IDs; identity is deterministic; identity rule is not a completeness blocker | Feed/detail; admin Jobs | Cross-source aliases are conservative; weak IDs remain indistinguishable. |
| `company_id`, `company`, `company_detail.name` | `company.name`, employer label, configured canonical employer | String; structured company then normalized employer label | Company ID/observation provenance; 0.95 when source-backed | Feed/detail and company view | Alias/merge audit history is incomplete. |
| `title` | ATS `title`, JSON-LD `title`, page title/meta | String; structured ATS then JSON-LD/page | Source field + observation, 0.95 when present | Cards, feed, detail, admin filter/search | No multilingual title reconciliation. |
| `location` | ATS location/offices, JSON-LD `jobLocation`, page location selectors | String/list collapsed for current serializer; structured then page | Source field evidence; location rule is report-only | Cards/feed/detail/admin filter | Multi-location typed structure is stored in payload but not consistently public. |
| `work_arrangement` | `workplace_arrangement`, `workplace_type`, `remote_type`, labeled text | Taxonomy On-site/Hybrid/Remote/Flexible/Unknown | Source field or inferred description evidence; 0.95/0.8 | Feed/detail filter | Remote geographic restrictions are stored in unified evidence but not public filterable. |
| `employment_type` | ATS employment/type/commitment and generic labeled text | Full-time/Part-time/Contract/Temporary/Internship/Apprenticeship/Freelance/Working student/Unknown | Structured 0.95, normalized 0.8; completeness warning only | Feed/detail filter | Greenhouse capability currently does not claim this field even when raw custom data may exist. |
| `experience_level` | `seniority`, `experience_level`, years/description evidence | String plus unified experience `{minimum_years, maximum_years, seniority}` | Structured 0.9, labeled description inferred 0.75; report-only | Feed/detail/filter | Public field loses the typed min/max structure. |
| `category` / function | `department`, `department_name`, source metadata | String taxonomy + unified `runr_function/subfunction` | Structured mapping 0.9/0.85; conflicting state retained | Feed/filter and admin | Taxonomy is code-owned; `Other` vs `Unclassified` semantics need product agreement. |
| `description` | ATS content, JSON-LD description, page HTML | String clean text; raw HTML -> sanitized HTML -> clean text | Raw/derived hashes and observation; 0.95; description completeness warning | Detail/feed/intelligence | Sanitized HTML is stored but public serializer primarily exposes clean text. |
| `salary` | ATS salary/range/compensation/custom fields | Existing salary object; no universal currency guarantee | Source metadata evidence; confidence connector dependent | Feed/detail/filter | Not in all connectors and not always normalized to comparable currency. |
| `languages` | ATS language fields, raw labeled `Languages:` line | List of `{language,status,proficiency}` in unified map; public strings | Structured 0.9, labeled inference 0.75; warning only | Feed/detail/filter | Language taxonomy/proficiency normalization is incomplete. |
| `work_authorization`, `sponsorship` | Raw requirement/company fields, profile fields | String/requirement projection | Evidence when source says it; unknown otherwise | Feed/detail/filter and company profile | No provider/source precedence contract across job and company. |
| `posted_at`, `posted_age_hours` | Explicit `datePosted/source_posted_at/published_at`; non-ATS page JSON-LD | ISO timestamp + computed age; explicit publication timestamp only for ATS | Timestamp source field + observed time; suspicious timestamp warning | Feed/detail/filter | ATS `createdAt`/`updatedAt` is not silently treated as publication; many rows remain ambiguous. |
| `first_seen_at`, `last_seen_at`, `last_verified_at` | Observation/canonical lifecycle timestamps | ISO timestamps | Observation/request provenance; completeness freshness rule | Feed/detail/admin | Freshness calculations use observation recency, not publication recency. |
| `canonical_url`, `job_detail_url` | Source URL, hosted URL, JSON-LD canonical/link | Canonical URL; tracking noise removed | URL alias + source observation | Feed/detail/admin | Redirect target validation is not universally stored. |
| `apply_url` | Apply URL, ATS `absolute_url/hostedUrl`, HTML forms | Verified direct URL only | URL classification/validation and admin audit; direct candidates only | Feed/detail/apply; admin inspection | Current public value can be null even when a detail/listing fallback exists. |
| `user_facing_url`, `application_method`, `application_status` | Application candidate set and destination classifier | URL + dedicated/embedded/job-detail/redirect/unresolved | Evidence candidates, validation metadata, warnings | Feed/detail/admin inspection | Embedded forms and redirect validation vary by connector. |
| `lifecycle_state` | Complete snapshot/source status/closed evidence | Current canonical lifecycle enum | Source state and observation history | Feed/detail | Reactivation/closure examples are not present in inspected production evidence. |
| `version_id`, `version`, `description_version.content_hash` | Stable content payload | Immutable version number/hash | Rule/version/observation pointer | Detail/admin | Semantic hash excludes volatile fields by rule; no user-facing diff view yet. |
| `user_state`, `evaluation`, `match_intelligence`, `priority` | User disposition, preference evaluator, cached intelligence | Product-owned state objects | User/workspace provenance, evaluator/prompt versions | Personalized feed/detail | These are not acquisition facts and are not filled by reprocessing. |
| `company_detail.profile.fields.description` | Company object/profile/enrichment payload | Evidence-backed field record `{value,state,provenance,observed_at}` | Source/provider + confidence; report-only | Detail/company panel | Public company profile exists but admin/public parity is incomplete. |
| Company website/careers/industry/size/HQ/founded/stage | Job company object, configured homepage/careers URL, profile/enrichment | Typed/string profile fields; source then provider only when enabled | Field evidence and URL rows; 0.95 source-backed | Company detail, filters for selected fields, admin Companies | Provider precedence and validation/redirect history not fully modeled. |
| Company funding/leadership/benefits/sponsorship | Company object, profile, enrichment provider | Typed/string where present | Evidence/provider metadata; no fabricated defaults | Company profile/filters | Usually stored but sparse; current production completeness is low. |
| Company logo | `logo_url/logo`, configured provider, R2 object | URL/object-key/monogram fallback | `company_logo_enrichments` and profile metadata | Company detail/logo | Zero logo-enrichment rows in inspected production; monogram is presentation fallback, not source fact. |

## Connector capability matrix

| Connector | Entry/API/crawl | Can provide now | Cannot reliably provide / current gap |
|---|---|---|---|
| Greenhouse | `ats_router.fetch_ats_snapshot`; boards API with `content=true` | External ID, title, location, content/description, department, office, categories, requisition, hosted URL, ATS apply URL, created/updated raw fields | Employment/workplace/language/salary/experience are not guaranteed by the declared capability set; applicant counts unavailable; production has 433 observations. |
| Lever | `ats_router.fetch_ats_snapshot`; Lever postings API `mode=json` | External ID, title, categories/department/team, location, commitment/employment, workplace, salary, description, hosted/apply URL, created/updated raw fields | Applicant counts unavailable; experience/language/closure semantics depend on payload; production has 152 observations. |
| Workday | Router detection and unsupported connector branch | Host/ATS classification and raw URL/metadata capability contract | No productive fetch path proven in current production; no observations. |
| Personio | Router detection and capability contract | Host detection and potential structured metadata fields | No productive fetch path/observations proven. |
| Recruitee | Router detection and capability contract | Host detection and potential structured metadata fields | No productive fetch path/observations proven. |
| SmartRecruiters | Router detection and capability contract | Host detection and potential structured metadata fields | No productive fetch path/observations proven. |
| Generic employer career site | `company_career_sites.py`, bounded crawler/manual URL JSON-LD/HTML | Page title, JSON-LD title/company/location/datePosted/description, canonical/link/apply candidates, conservative location selectors | No stable API schema; structured department/employment/workplace/language/experience usually missing; crawl retry distribution not proven. |
| Bounded probe | `bounded_probe.py`, scheduler | Request/response/HTML evidence under a hard request ceiling | Not a productive connector; five targets are quarantined/unproven in configured data. |
| LinkedIn guest/portal strategy | `job_boards/collector.py`, `strategies.scrape_linkedin_jobs()` | Portal job ID/title/location/description/link when authorized guest endpoint works | Not an official employer/ATS source; authorization/terms and applicant fields are not part of this acquisition catalog; no current production observations were attributed to it. |
| Company enrichment provider | `CompanyEnrichmentService`, provider interface | Explicit provider-returned profile/logo evidence and attempt metadata | Disabled for reads/reprocessing; current provider result count is zero. |

## Duplicate algorithm and observed cases

Current automatic candidate generation is conservative: it groups canonical
jobs only when the same canonical company, normalized title/location, and
stable content hash/identity evidence agree; it stores reasons, score, rule
version, members, and review history in candidate tables. It never merges,
rewrites observations, changes a canonical pointer, or publishes. [C][S]

Observed configured-data result: zero clusters and zero members. [P] Therefore
the following are evidence-backed fixtures/algorithm cases, not claims that
the production database contains a duplicate:

| Case | Result | Meaning |
|---|---|---|
| Same company/title/location but different descriptions (`a` and `b` in the unified pipeline fixture) | Not clustered; test passes | Prevents a false merge when stable content differs. [T] |
| Same source external ID or canonical URL with changed stable content | One canonical job, new immutable posting version | Correct version change, not a duplicate. [C][T] |
| Two different employers with the same title/location/description | No automatic cross-company merge | Conservative company boundary; may miss a true syndication duplicate. [C][T] |
| Same job with tracking parameters or ATS detail/apply aliases | Canonical URL normalization/alias path may coalesce | Depends on canonicalizer and source ID; redirect-equivalent URLs without stored redirect evidence remain indistinguishable. [C][U] |
| Two postings with no stable external ID, same title/location, and identical content hash | Candidate can be indistinguishable from a deliberate repost | Requires manual decision; no automatic merge. [C][U] |

False merges and missed duplicates found in the inspected configured database:
none demonstrated because the database has no duplicate candidates. The main
identity risk is therefore indistinguishable weak-ID records, not an observed
bad merge. [P]

## UI and consumer capability matrix

| Capability | Supported now | API but missing in admin | Stored but not exposed to users | Not yet modeled / gap |
|---|---|---|---|---|
| Source/connector inventory and bounded import | Acquisition admin Sources; API `/admin/acquisition/sources`, import plan/start | Full request/attempt retry detail is API/read-model dependent | Raw connector capability details | Unified connector capability registry with persisted field-by-field contract |
| Canonical job search/filter | Acquisition admin Jobs; source/publication/completeness filters; user feed filters | Function, workplace, language, seniority, warning and duplicate filters are API-supported; UI has only a subset | Full field-evidence state/filter combination | Typed multi-location and semantic conflict filter |
| Job inspection | Admin `/admin/acquisition/jobs/{id}` and legacy Data inspector | Full raw observations, versions, evidence, rule outputs, quality, URL candidates are returned | Raw payload and field evidence intentionally admin-only | Diff/revision timeline and direct field conflict resolver |
| Company inventory | Acquisition admin Companies with URL/profile/job count | Full provider attempts/enrichment history | Many profile fields and source URLs are admin-only | Durable company-source alias/merge decision screen |
| Duplicate review | Duplicate page is candidate-only | Cluster reasons/review history are API-supported | Candidate memberships and scores are not public | Explicit approve/reject/merge decision model and reversible merge operation |
| Rules/quality | Rules page; report-only warnings/completeness | Detailed rule outputs and per-field confidence are inspection API-supported | Provenance/confidence/rule versions are not user-facing | Calibrated confidence and persisted rule catalog UI |
| Reprocessing | Plan and recent runs visible; CLI is fully explicit/resumable | Checkpoint, errors, rollback metadata API-supported | Reprocessing diagnostics not public | Remote backup branch/restore automation and operator lease history UI |
| Publication | Preview/publish/undo admin actions and current head | Publication audit/read model API-supported | Publication provenance hidden from user feed | Automated release diff/approval workflow |
| User job feed/detail | Existing authenticated `/personalized-jobs` card/feed/detail serializers | New unified function/subfunction, remote restrictions, full field evidence and raw timestamps are available only in admin/current payload | Raw HTML, normalized taxonomies, evidence, confidence, completeness, duplicate state | Public contract version for the expanded acquisition fields |
| Company logo/enrichment | Profile serializer supports cached logo or deterministic monogram | Provider/attempt status is stored/admin-readable | Provider provenance and object storage metadata are not public | Product-approved enrichment provider and terms/refresh policy |

## Reprocessing, backfill, idempotency, and rollback

Read-only plan and apply entry point:

```powershell
.venv\Scripts\python.exe scripts/reprocess_acquisition.py --env-file user_config\.env
.venv\Scripts\python.exe scripts/reprocess_acquisition.py --env-file user_config\.env --apply --yes --allow-remote-additive-rollback --batch-size 25 --idempotency-key <stable-key>
```

The script refuses non-project Python or a version other than 3.12.7. Local
SQLite apply copies the database before writing. Remote apply is additive and
transaction-batched, uses an owner lease (`045_acquisition_reprocessing_leases`),
reclaims only a stale lease with compare-and-swap, checkpoints each batch,
uses per-observation savepoints on local SQLite. Remote libSQL first attempts a
replayable batch transaction and falls back to isolated per-observation
transactions when the batch fails; it records retryable failures and never deletes
observations/versions or automatically merges/publishes. A second completed
invocation with the same idempotency key returns an idempotent replay. [C][S][T]

Rollback is asymmetric: local SQLite has a recoverable copy; remote has a
transaction-safe additive checkpoint and reversible publication/review actions,
but there is no tested destructive remote restore command. The production
snapshot taken before the paused resume is documented in the implementation
report and remains outside version control. [P][U]

## Prioritized gap list

1. **Data loss:** older observations may not have `raw_payload_json`; raw
   retention is complete only for new captures and preserved legacy payloads.
   Add a retention/completeness metric and object-storage archive policy.
2. **Incorrect semantics:** formalize `known` versus legacy `present`, source
   timestamp semantics, closure/reactivation, multi-location, redirect and
   conflict precedence; migrate read models without losing old evidence.
3. **Identity/duplicate risk:** add company-source identity and alias decision
   entities, explicit duplicate decisions/merge provenance, reversible merge
   operations, and cross-source syndication rules.
4. **Missing enrichment:** choose and configure an approved provider, persist
   provider precedence/refresh/terms, and backfill logos/profile fields under a
   budget. Current logo rows are zero.
5. **Observability:** persist connector capability snapshots, retry/freshness
   distributions, source reconciliation, rule coverage by target, and deploy
   and reprocessing lease metrics; remove fixture/test targets from production.
6. **Admin usability:** add field-level conflict views, duplicate decision
   actions, reprocessing scope/remote acknowledgement controls, version diffs,
   and a source capability matrix in the admin console.

## Recommended implementation sequence

1. Make production source hygiene explicit: quarantine fixture/test rows,
   reconcile N26/Qonto counts, and finish the interrupted reprocessing with the
   new lease/checkpoint guard after the deployment migration is live.
2. Add durable capability snapshots, raw-retention/completeness metrics, and
   timestamp/lifecycle semantics before expanding connectors.
3. Add company-source/alias entities and reversible duplicate decisions with
   review-only defaults.
4. Configure one approved enrichment provider and run a budgeted, observable
   company backfill; then expose profile/URL/logo provenance in admin.
5. Expand public API serializers and user filters only after the field contract
   and `known`/unknown semantics are versioned.
6. Add remote backup/restore procedure, operational dashboards, version diffs,
   and authenticated production contract tests.
