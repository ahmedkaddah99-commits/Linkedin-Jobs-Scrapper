# Personalized Jobs domain contracts

Status: P0 definitions only. These contracts are stable payload shapes for the
personalized Jobs workstreams. They are not yet persisted and do not change the
current feed, run, matching, disposition, billing, or frontend API behavior.

Implementation: [`backend/domain/personalized_jobs_contracts.py`](../backend/domain/personalized_jobs_contracts.py).

## Contract definitions

All contracts use `to_dict()` and `from_dict()` for repository-style
serialization. Nullable or unavailable information is represented by JSON
`null`; an empty list means that the collection is known to be empty. Invalid
enum values and missing stable identifiers raise `ContractValidationError`.

### CandidateSearchPreferences

Owned by one authenticated user/profile. It contains search choices and stable
asset references, not candidate facts:

- `profile_id`, optional `user_id`
- `target_roles`, `keywords`, `preferred_locations`, `country_codes`
- `work_arrangements`, `seniority_levels`, `employment_types`
- `languages` as `{language, proficiency}`
- `work_authorization` as country/region plus authorization status and an
  optional reference ID
- `sponsorship_requirement`, `relocation_preference`
- `minimum_salary`, `salary_currency`, `earliest_start_date`,
  `notice_period_days`, `maximum_commute_minutes`,
  `willingness_to_travel`
- `associated_asset_id` (a stable CV/document asset ID, never file content)
- `active`, `created_at`, `updated_at`, `schema_version`

`from_workspace_settings()` initially adapts target roles, keywords, country
codes, locations/cities, work arrangement, experience levels, languages, and
the selected CV asset. Employment type, authorization, sponsorship,
relocation, salary, start date, notice period, commute, and travel preferences
require new preference persistence. Workspace source selection, crawl windows,
technical runtime controls, prompt overrides, and document rendering settings
remain workspace execution configuration.

### JobPosting

`posting_id` is the stable internal posting ID. The projection contains
normalized title/company/location, nullable work arrangement, description,
canonical apply/source URLs, nullable `posted_at`, `first_seen`, `last_seen`,
`state` (`active`, `expired`, `unknown`), nullable salary, `version`, and the
complete `source_observations` plus compact `provenance` references.

### JobSourceObservation

An observation records one source view of a posting: `source_type`,
`source_identifier`, original URL, observed title/company/location,
`observation_time`, optional `run_id` and `workspace_id`, `raw_job_id`, source
metadata, and a stable `observation_id`. Every contributing run/source should
remain represented by an observation. `site_job_url_history` is not changed or
promoted to the canonical posting repository by this ticket.

### EligibilityEvaluation and EligibilityReason

`EligibilityEvaluation.status` is one of `eligible`, `likely_eligible`,
`ineligible`, `uncertain`, or `not_evaluated`. An evaluation is profile/user
specific and carries evaluator name/version, evaluated profile/evidence/job
versions, timestamp, and provenance references.

Each reason has a stable `reason_code`, category, user-facing summary,
evaluation outcome, source type, optional job-description excerpt, optional
`candidate_reference`, confidence, explicit/inferred marker, and evaluator
name/version. Initial categories are language, authorization, sponsorship,
location, work arrangement, experience, education, employment type, salary,
relevance, and insufficient information.

Authorization or sponsorship uncertainty is represented as `uncertain`; the
model rejects an `ineligible` evaluation when either category is uncertain.
An authorization/sponsorship reason may only be `ineligible` when the job
requirement is explicitly stated (`is_explicit: true`).

`adapt_language_rule_reasons()` maps existing
`language_rules.detect_reasons()` strings into reasons without changing
`language_rules.py`.

### MatchEvaluation and MatchEvidenceReference

Match is separate from eligibility. `MatchEvaluation` contains nullable
`overall_score`, `score_scale`, `score_version`, label, matching/missing/
uncertain structured requirements, evidence references, explanation summary,
evaluator metadata, evaluated profile/evidence/job versions, timestamp, and
provenance. A score requires an evaluator, scale, and version; no score is
emitted when no evaluator ran.

`MatchEvidenceReference` contains only a pointer to an existing verified
`CandidateEvidence`, `WorkExperienceRecord`, `EvidenceRecord`, `CareerProfile`,
or other verified profile record: `reference_type`, `reference_id`,
`profile_id`, optional record version/location. It deliberately contains no
untraceable copied prose.

`MatchEvaluation.from_profile_requirement_matches()` adapts existing
`ProfileRequirementMatch` values. Existing `matched_evidence_ids` are treated
as references, with `work_experience` as the default type. The adapter maps
`strong`/`partial` to matching and `missing` to missing; it does not rename
`priority_rank` or call token overlap semantic matching.

`from_job_application_binding()` adapts an existing
`JobApplicationBinding`. Its legacy `job_id` is only a provisional fallback
unless the caller supplies a canonical `posting_id`. Existing application
bindings remain application-specific records, not the new feed projection.

### JobDisposition

The user-specific current state for a stable posting is one of `none`,
`saved`, `hidden`, `interested`, `preparing`, `applied`, `dismissed`, or
`archived`. It contains `user_id`, `posting_id`, optional `reason_code`,
`source_of_change`, timestamps, version, and schema version.

Hidden and dismissed restore to `none`; `saved` can move to `preparing`, and
`preparing` can move to `applied`. Other ordinary state updates remain
representable and versioned. Restoration is not connected to
`/rejected-jobs/requeue`. Requeue remains document-generation behavior, not a
feed disposition.

### PersonalizedFeatureKey

Canonical backend identifiers are:

`ai_eligibility_filtering`, `semantic_job_matching`,
`full_match_explanations`, `tailored_cv`, `tailored_motivation_letter`,
`scheduled_job_searches`, `multiple_job_searches`, `assisted_apply`,
`priority_ranking`, and `advanced_application_insights`.

The backend plan IDs are exactly `none`, `launch`, `momentum`, and `scale`.
The contract defines identifiers only; it does not allocate features to plans
or enforce access. Synthetic frontend keys are adapted as follows:

| Synthetic frontend key | Canonical backend key |
| --- | --- |
| `ai_eligibility_filter` | `ai_eligibility_filtering` |
| `semantic_matching` | `semantic_job_matching` |
| `full_match_explanation` | `full_match_explanations` |
| `multiple_active_searches` | `multiple_job_searches` |
| canonical names | unchanged |

`free` and `Pro` are not backend plan IDs. They remain presentation/legacy
labels outside this contract.

## Ownership and serialization visibility

| Contract | Owner/visibility |
| --- | --- |
| CandidateSearchPreferences | One authenticated user/profile; candidate-private |
| JobPosting | Shared canonical public posting data |
| JobSourceObservation | May reference a user-owned run/workspace; source metadata is not automatically public |
| EligibilityEvaluation | User/profile-specific |
| MatchEvaluation | User/profile-specific |
| JobDisposition | User-specific |

Normal `to_dict()` output is authenticated/domain output. Public posting output
must be an explicit projection of posting fields and must not expose candidate
preferences, evaluations, or dispositions. `to_analytics_dict()` is a separate
projection. It excludes salary preferences, authorization status, sponsorship
preference, CV/document content, job-description excerpts, detailed evidence,
and candidate evidence references. Source metadata is excluded from analytics
observation output as well.

## Versioning and provenance

Each payload carries a contract-specific `schema_version`. Derived evaluation
payloads carry evaluator name/version, evaluated job version, evaluated profile
version, evaluated evidence version, evaluation timestamp, and provenance
references. Posting versions are incremented by the future projection/persistence
layer; the P0 module does not create that layer.

The canonical URL adapter hashes the existing canonicalized URL into a stable
`posting_id`. If a legacy record has no URL, the adapter creates a visibly
`provisional_posting_...` ID from run ID, legacy job ID, title, and company. A
run-local `job_id` is never independently treated as a global ID.

## Existing-to-new mappings

| Existing concept | New contract mapping |
| --- | --- |
| `JobRecord.job_id` / `PipelineJob.job_id` | `JobSourceObservation.raw_job_id` and `source_identifier`; only a URL-derived `posting_id` is canonical |
| `title`, `company`, `location_raw` | `normalized_title`, `normalized_company`, `normalized_location` and observed fields |
| `link`, `source_url`, `apply_link` | canonical source/apply URLs plus original observation URL |
| `description_text`, `full_description` | `JobPosting.description` |
| `posted_datetime_estimated_utc` | `JobPosting.posted_at` |
| `priority_rank` | Remains prioritization metadata; it is not `MatchEvaluation.overall_score` |
| `CandidateEvidence.evidence_id` | `MatchEvidenceReference(reference_type="candidate_evidence")` |
| `WorkExperienceRecord.experience_id` | `MatchEvidenceReference(reference_type="work_experience")` |
| `ProfileRequirementMatch` | `MatchRequirement` through the explicit adapter |
| `JobApplicationBinding` | Match adapter input only; not a canonical posting or disposition |
| `language_rules.detect_reasons()` | Eligibility reasons through `adapt_language_rule_reasons()` |
| workspace `target_roles`, keywords, locations, country codes, arrangements, levels, languages, CV asset | Initial CandidateSearchPreferences adaptation |

Unsupported in P0: feed projection/querying, cross-run reconciliation,
preference repositories, evaluation engines, semantic scoring, disposition
storage, entitlement allocation/enforcement, billing changes, and frontend API
integration.

## Example serialized objects

```json
{
  "profile_id": "prof_123",
  "user_id": "user_123",
  "target_roles": ["Business Analyst"],
  "keywords": ["business analyst", "sql"],
  "preferred_locations": ["Berlin"],
  "country_codes": ["DE"],
  "work_arrangements": ["hybrid"],
  "seniority_levels": ["mid"],
  "employment_types": ["full_time"],
  "languages": [{"language": "English", "proficiency": "C1"}],
  "work_authorization": [{"country_code": "DE", "region": null, "status": "unknown", "reference_id": "ev_auth_1"}],
  "sponsorship_requirement": "unknown",
  "relocation_preference": "conditional",
  "minimum_salary": null,
  "salary_currency": null,
  "earliest_start_date": null,
  "notice_period_days": null,
  "maximum_commute_minutes": 45,
  "willingness_to_travel": false,
  "associated_asset_id": "asset_cv_123",
  "active": true,
  "created_at": "2026-08-04T10:00:00+00:00",
  "updated_at": "2026-08-04T10:00:00+00:00",
  "schema_version": "candidate_search_preferences_v1"
}
```

```json
{
  "posting_id": "posting_9c7...",
  "normalized_title": "Business Analyst",
  "normalized_company": "Example GmbH",
  "normalized_location": "Berlin, DE",
  "work_arrangement": "hybrid",
  "description": "...",
  "canonical_apply_url": "https://example.com/jobs/123",
  "canonical_source_url": "https://example.com/jobs/123",
  "posted_at": null,
  "first_seen": "2026-08-04T10:00:00+00:00",
  "last_seen": "2026-08-04T10:00:00+00:00",
  "state": "unknown",
  "salary": null,
  "source_observations": [{
    "source_type": "linkedin_search",
    "source_identifier": "run-local-42",
    "original_url": "https://example.com/jobs/123?utm_source=runr",
    "observed_title": "Business Analyst",
    "observed_company": "Example GmbH",
    "observed_location": "Berlin, DE",
    "observation_time": "2026-08-04T10:00:00+00:00",
    "run_id": "run_123",
    "workspace_id": "workspace_123",
    "raw_job_id": "run-local-42",
    "source_metadata": {},
    "observation_id": "obs_123",
    "schema_version": "job_source_observation_v1"
  }],
  "provenance": [{"source_observation_id": "obs_123", "source_type": "linkedin_search", "source_identifier": "run-local-42", "run_id": "run_123", "workspace_id": "workspace_123"}],
  "version": 1,
  "schema_version": "job_posting_v1"
}
```

## Future persistence responsibilities

P1 owns persistence and update semantics for CandidateSearchPreferences. P2
owns cross-run source observation ingestion and canonical JobPosting projection.
P5 owns feature entitlement allocation against the canonical feature keys and
existing plan IDs. A later evaluation workstream owns EligibilityEvaluation and
MatchEvaluation execution and reproducibility storage. Disposition storage and
feed APIs must use `posting_id`, not run-local `job_id`. None of these
responsibilities are implemented by this P0 ticket.
