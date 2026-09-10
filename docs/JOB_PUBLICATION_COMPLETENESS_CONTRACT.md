# Job Publication Completeness Contract

- **Contract version:** `job_publication_completeness_v1`
- **Owner:** F (OpenCode, this workstream)
- **Status:** Implemented, un-wired (integration is C-owned; see "Wiring" below)
- **Base SHA:** `848408f3024c3c675abb3f8d6696563eb4184c50`
- **Final SHA:** branch tip at handoff (see `docs/OPENCODE_F_JOB_COMPLETENESS_HANDOFF.md`)

## 1. Purpose

Two different questions are deliberately kept separate:

1. **Record completeness** (this contract): does one job record contain enough
   trustworthy information to be published to Runr users?
2. **Source-scan completeness** (out of scope): did the collector exhaust the
   employer or LinkedIn source?

A collector can exit successfully and still produce records that must not be
published; an individually complete record remains publishable even when the
collector did not exhaust its source. This contract only evaluates record
completeness.

## 2. Inputs evaluated

The core validator consumes one *normalized canonical-job record* — the shape
written by `backend/acquisition/quality.normalize_job_for_ingestion` and read
back from `canonical_jobs` + `job_posting_versions` +
`job_source_observations`. It is a plain mapping; the validator never reads a
live database and never mutates its input.

A separate read-only audit helper (`scripts/audit_real_job_data.py`) was added
to evaluate real producer-state SQLite snapshots from the LinkedIn and employer
collectors without mutating them.

Optionally the caller passes:

- `company_registry` — the set of known canonical company IDs, used to flag a
  present-but-unknown company ID as `unresolved_identity`.
- `source_records` — the underlying source observations, used only to surface
  cross-source value conflicts (never silently blended).

## 3. Schemas analyzed

| Source | What it defines |
|---|---|
| `backend/database/schema.py` | Application/workspace/review tables (not job catalog). |
| `backend/repositories/sqlite_migrations.py` | `canonical_jobs`, `canonical_companies`, `job_source_observations`, `job_posting_versions`, `canonical_job_external_ids`, `acquisition_publications`, `acquisition_publication_jobs`, `acquisition_publication_head`. |
| `backend/acquisition/producer_adapters.py` | `SourceObservation` (source, source_job_id, source_url, apply_url, apply_type, canonical_company_id, observed_at, content_hash). |
| `backend/acquisition/quality.py` | `normalize_job_for_ingestion` → `title`, `company`, `description_text`, `location_raw`, `application_destination`, `source_timestamps`, `quality_warnings`. |
| `backend/acquisition/unified_mapping.py` | `map_job_fields` → `runr_function`, `employment_type`, `workplace_arrangement`, `salary`, `locations`, etc. |
| `backend/acquisition/public_contract.py` | Typed read model (completeness, freshness, duplicate, publication_state). |
| `frontend/src/lib/personalizedJobsApi.js` | `toPersonalizedJobView` — the exact fields the customer UI renders. |
| `data/acquisition/inputs/company_registry_canonical.csv` | 17,601 canonical companies (`canonical_CompanyID`). |

## 4. Field classification

Salary, benefits, seniority, employment type and similar fields are **not**
automatically mandatory; actual Runr behavior does not require them to render a
publishable job.

### Required for publication

A record missing any of these is `not_publishable_missing_required` (or a more
specific status when the failure is identity/placeholder/invalid).

| Field | Canonical source fields | Failure reason |
|---|---|---|
| Stable canonical job identity | `canonical_job_id` | `missing_canonical_job_id` |
| Stable canonical company ID | `canonical_company_id` / `company_id` | `missing_canonical_company_id`, `unknown_canonical_company_id` |
| Non-placeholder company display name | `company_name` / `employer_name` | `missing_company_name`, `placeholder_company_name` |
| Meaningful job title | `title` | `missing_title`, `placeholder_title` |
| Trustworthy direct application/job URL | `application_destination.resolved_url` / `apply_url` | `missing_application_url`, `invalid_application_url`, `tracking_only_application_url`, `listing_fallback_application_url` |
| Sufficient job description | `description_text` | `missing_description`, `placeholder_description`, `insufficient_description`, `blocked_or_error_body` |
| Location or explicit remote/unknown classification | `location_raw` / `workplace_arrangement` | `missing_location` |
| Source | `source` / `source_ats` | `missing_source` |
| Source-specific job identity | `source_job_id` / `external_job_id` | `missing_source_job_id` |
| Observation/freshness timestamp | `observed_at` | `missing_observed_at`, `stale_observation` |
| Active publication state | `lifecycle_state` | `closed_lifecycle_state` |

### Conditionally required

| Field | Condition | Failure reason |
|---|---|---|
| Posted date | Must not be in the future | `future_posted_at` |
| Closing date | Must not precede the posted date | `closed_before_posted_at` |
| Cross-source consistency | Conflicting identity fields must not be silently merged | `conflicting_source_values` |
| Ownership / dedupe certainty | No unresolved ownership or dedupe conflict | `unresolved_ownership_conflict`, `uncertain_dedupe_identity` |

### Recommended (not blocking)

`employment_type`, `workplace_arrangement`, `experience_level`, `salary`.

### Optional (not blocking)

`benefits`, `seniority`, `company_logo`, `company_enrichment`.

## 5. Deterministic statuses

| Status | Meaning |
|---|---|
| `publishable_complete` | All required and conditional checks pass. |
| `not_publishable_missing_required` | A required field is absent. |
| `not_publishable_invalid` | A value is present but invalid (bad URL, short description, future date, conflict). |
| `not_publishable_unresolved_identity` | Canonical job/company/source identity or ownership/dedupe is unresolved. |
| `not_publishable_placeholder` | A required field is a placeholder or a blocked/error body. |
| `stale_or_closed` | The observation is stale or the lifecycle state is closed. |

When multiple reasons apply, the most specific status wins in this priority
order: `stale_or_closed` > `unresolved_identity` > `placeholder` > `invalid` >
`missing_required` > `publishable_complete`.

## 6. Reason codes

| Reason code | Status |
|---|---|
| `missing_canonical_job_id` | unresolved_identity |
| `missing_canonical_company_id` | unresolved_identity |
| `unknown_canonical_company_id` | unresolved_identity |
| `missing_source_job_id` | unresolved_identity |
| `uncertain_dedupe_identity` | unresolved_identity |
| `unresolved_ownership_conflict` | unresolved_identity |
| `missing_company_name` | missing_required |
| `placeholder_company_name` | placeholder |
| `missing_title` | missing_required |
| `placeholder_title` | placeholder |
| `missing_application_url` | missing_required |
| `invalid_application_url` | invalid |
| `tracking_only_application_url` | invalid |
| `listing_fallback_application_url` | invalid |
| `missing_description` | missing_required |
| `placeholder_description` | placeholder |
| `insufficient_description` | invalid |
| `blocked_or_error_body` | placeholder |
| `missing_location` | missing_required |
| `missing_source` | missing_required |
| `missing_observed_at` | missing_required |
| `stale_observation` | stale_or_closed |
| `closed_lifecycle_state` | stale_or_closed |
| `future_posted_at` | invalid |
| `closed_before_posted_at` | invalid |
| `conflicting_source_values` | invalid |

Every rejection carries the machine-readable code plus the affected field names
via `CompletenessResult.to_dict()`.

## 7. Application URL policy

A job detail page is a **valid user-facing application/job URL** as long as it
links directly to the advertised posting. Accepted destination classes:
`dedicated_apply`, `embedded_apply`, `job_detail_with_apply`, `job_detail_only`.

Rejected: `redirect_apply`, `listing_fallback`, `search_results`,
`portal_listing`, `careers_index`, `unresolved`, empty strings, URLs that are
not HTTP/HTTPS, tracking-only/shortener links (`bit.ly`, `lnkd.in`, …), and
URLs whose only query parameters are tracking keys.

Real-data observation: every LinkedIn record in the RC-023 historical snapshot
(188,206 jobs) used the LinkedIn job-detail view URL as its apply URL; this is
treated as acceptable. Employer records often lack an explicit apply URL; the
source job-detail URL is used as a fallback and is also acceptable.

## 8. Description policy

A description is required and must contain at least 80 meaningful characters
(letters/digits) after HTML-tag stripping. `unknown`/`n/a`/`tbd`/empty tokens
and pure template strings (e.g. `{{job_description}}`) are rejected as
placeholders, but only when the whole value is short; a long description that
merely contains a leaked JSON/HTML artifact (for example, `}}` inside otherwise
real prose) is **not** a placeholder. Blocked/error bodies (captcha,
"attention required", 403/404, leaked JSON pagination markers) are rejected.
Validation never fabricates a description from other fields.

## 9. Source merging and provenance

See `backend/acquisition/job_source_merging.py`.

- Canonical job identity is URL-based. Observations of the same canonical URL
  are re-observations and merge trivially; the latest, richest description and
  the highest-ranked application destination win, and a provenance map is
  preserved.
- Cross-source observations (LinkedIn + employer) merge into one canonical job
  **only** with an explicit recorded relationship
  (`same_posting`, `duplicate`, `cross_source_match`, `repost`,
  `canonical_match`). Title/company resemblance is never enough.
- Different vacancies are never merged because titles/companies resemble each
  other.
- Uncertain deduplication yields `uncertain_dedupe_identity` and cannot produce
  a publishable job.
- Field precedence: `dedicated_apply` > `embedded_apply` >
  `job_detail_with_apply` > `job_detail_only` > `redirect_apply` >
  `listing_fallback`. Provenance is always retained (`_source_provenance`,
  `_merged_application_source`, `_merged_description_source`).

## 10. Direct database-edit implications

- The ingestion pipeline (`ingest_snapshot` / `normalize_job_for_ingestion`)
  **overwrites** normalized fields (`title`, `description_text`, `location_raw`,
  `application_destination`, `source_timestamps`) from each fresh source
  observation. Direct edits to those normalized fields will be lost on the next
  refresh.
- Existing durable correction surfaces: admin review decisions
  (`record_job_review_decision` / `undo_job_review_decision`),
  `resolve_admin_job_apply_url` (explicit apply-URL override), and the
  `acquisition.override` token scope. Intentional corrections must be recorded
  through these surfaces, not by editing observation/posting rows, to survive
  refreshes.
- `job_posting_versions` is immutable by trigger; source observations are
  immutable at the boundary. There is no generic field-lock/provenance override
  for arbitrary normalized fields. This contract does **not** promise arbitrary
  direct edits will persist, and it does **not** build a replacement admin
  dashboard.

## 11. Audit results

### 11.1 Real producer-state audit (RC-023, 2026-09-08)

`scripts/audit_real_job_data.py` was run read-only against the RC-023 historical
producer snapshots:

- LinkedIn: `state/linkedin/master_linkedin_jobs_state.db` (188,206 records,
  `job_company_observations.row_json`).
- Employer: `state/employer/master_employer_jobs_state.db` (2,612 records,
  `jobs.payload_json`).
- Company registry: `data/acquisition/inputs/company_registry_canonical.csv`
  (17,601 canonical companies), profiled read-only.

| Source | Records | Publishable | % | Dominant blocker |
|---|---|---|---|---|
| LinkedIn | 188,206 | 42,564 | 22.6% | `missing_canonical_company_id` (145,637; 77.4%) |
| Employer | 2,612 | 63 | 2.4% | `missing_canonical_company_id` (2,018; 77.2%) |
| **Combined** | **190,818** | **42,627** | **22.3%** | `missing_canonical_company_id` (**147,655**; **77.4%**) |

LinkedIn top blocking reasons:

| Reason | Count |
|---|---|
| `missing_canonical_company_id` | 145,637 |
| `insufficient_description` | 466 |
| `blocked_or_error_body` | 51 |

Employer top blocking reasons:

| Reason | Count |
|---|---|
| `missing_canonical_company_id` | 2,018 |
| `missing_location` | 1,911 |
| `missing_description` | 1,404 |
| `insufficient_description` | 72 |
| `blocked_or_error_body` | 3 |
| `placeholder_title` | 1 |

Outcomes reconcile exactly to the record counts (see `reconciliation` in the
JSON report). Distinct publishable companies: 1,235 (LinkedIn), 4 (employer).
LinkedIn had 0 duplicate source job ids; employer had 172 duplicates across
2,440 distinct source ids.

### 11.2 Synthetic sample audit (300 records, seed 20260812)

| Status | Count | Percent |
|---|---|---|
| `publishable_complete` | 60 | 20.0% |
| `not_publishable_missing_required` | 50 | 16.7% |
| `not_publishable_invalid` | 58 | 19.3% |
| `not_publishable_unresolved_identity` | 36 | 12.0% |
| `not_publishable_placeholder` | 35 | 11.7% |
| `stale_or_closed` | 61 | 20.3% |

Top blocking reasons: `missing_description` (59), `insufficient_description`
(55), `missing_location` (41), `missing_canonical_company_id` (36),
`closed_lifecycle_state` (34), `missing_application_url` (33),
`stale_observation` (31), `tracking_only_application_url` (28),
`listing_fallback_application_url` (28), `placeholder_description` (27).

Totals reconcile exactly (300 = sum of outcome counts). The synthetic sample
and report remain committed at `data/audit/report/completeness_audit.{json,md}`.
The real-data report is at `data/audit/real/completeness_audit_real.{json,md}`.

## 12. Tests

```
.venv\Scripts\python.exe -m pytest tests/test_job_publication_completeness.py tests/test_job_source_merging.py tests/test_job_completeness_audit.py tests/test_real_job_data_audit.py -q
```

Result: **53 passed**. Boundary conditions covered include: every status, every
reason-code family, input immutability, collector-success-does-not-imply-
publishable, source-scan-incompleteness-does-not-invalidate, real producer
state field mapping, and audit reconciliation.

## 13. Wiring (C-owned, not applied here)

See `docs/OPENCODE_F_JOB_COMPLETENESS_HANDOFF.md`.
