# Acquisition ingestion: directly edited database fields and override preservation

This document explains which application-database fields the acquisition
pipeline overwrites during ingestion and how existing correction/override
mechanisms preserve intentional edits.

## Scope

Applies to the acquisition ingestion path:

`collector output → producer adapter → SqliteAcquisitionStore.ingest_snapshot → canonical company/job tables → publication → Jobs API`

It does **not** describe customer-facing edits to user profiles, workspace
settings, tracker items, CVs or billing records.

## Stable identifiers (never overwritten)

| Entity | Field | Behavior |
| --- | --- | --- |
| Company | `canonical_company_id` | Created once by `_ensure_company` and retained forever. |
| Company | `company_identity_keys.identity_key` | Durable strong-identity key; new aliases are added, existing keys are not replaced. |
| Job | `canonical_job_id` | Created once when a job is first observed and retained. |
| Job | `canonical_jobs.identity_key` | Derived from company, title, location and URL; stable after first creation. |
| Job | `canonical_jobs.first_seen_at` | Set once and never updated. |
| Observation | `job_source_observations.observation_id` | Append-only evidence row. |
| External ID | `canonical_job_external_ids.external_id_id` | First-seen record is retained; `last_seen_at` may advance. |

## Fields that ingestion overwrites when a newer observation arrives

These fields are updated only when the incoming observation has a strictly
newer `observed_at` timestamp (`_observation_is_newer`). An equal or older
timestamp is treated as a replay and does not regress the projection.

| Table | Field | Source |
| --- | --- | --- |
| `canonical_jobs` | `title` | Producer observation. |
| `canonical_jobs` | `location` | Producer observation. |
| `canonical_jobs` | `canonical_url` | Primary source URL from observation. |
| `canonical_jobs` | `identity_signature` | Derived signature for duplicate detection. |
| `canonical_jobs` | `last_seen_at` | Latest observation timestamp. |
| `canonical_jobs` | `last_verified_at` | Latest observation timestamp. |
| `canonical_jobs` | `lifecycle_state` | Set to `active` when observed; set to `closed` only on a complete, valid, closure-safe snapshot after absence grace attempts. |
| `canonical_jobs` | `absence_count` | Reset to 0 on every newer observation. |
| `job_source_states` | `lifecycle_state`, `absence_count`, `last_checked_at` | Updated per-source when a complete snapshot is processed. |
| `canonical_job_url_aliases` | — | New aliases are appended; existing rows are untouched. |
| `canonical_job_versions` | `title`, `description`, `location`, `apply_url`, `content_hash` | A new version row is inserted when the content hash changes. Historical versions are retained. |

## Company profile fields

`_ensure_company_profile` writes profile fields from the producer observation or
from an explicitly configured `company_profile` in the target config. It updates
individual fields when the source provides a non-empty, non-unknown value. It
does **not** clear an existing known value when the new observation lacks it.

Directly edited company profile fields in the database or via an admin action
are preserved unless a later observation explicitly supplies a different known
value. A newer observation timestamp alone does not erase an existing known
field.

## Intentional corrections and overrides that survive refreshes

| Mechanism | Table(s) | Behavior |
| --- | --- | --- |
| Review decision | `job_reviews`, `canonical_jobs.lifecycle_state` | A manual `rejected`/`approved` review decision is honored during publication. Ingestion may set `lifecycle_state` back to `active` if the job is observed again, but the review decision remains in `job_reviews` and affects publication eligibility. |
| Company link candidate | `company_link_candidates` | Manual link candidates are retained and considered during identity reconciliation; ingestion does not delete them. |
| URL reconciliation disposition | `company_url_reconciliation` | Explicit `intentionally_ignored` or `persisted` dispositions are preserved. |
| Quarantine | `acquisition_targets.quarantined` | A quarantined target is never re-enabled by `ensure_targets`, regardless of manifest updates. |
| Publication head | `acquisition_publications` | Publication is explicit; ingestion never auto-publishes unless `publication_enabled` and a valid snapshot are produced. |
| Manual company profile edit | `company_profiles` | Known values are overwritten only by newer observations with explicit conflicting known values, not by missing/unknown values. |

## Fields that are intentionally never written by ingestion

- User, workspace, run, artifact and tracker tables.
- Billing, subscription and OAuth credential tables.
- Customer-task queue state.
- Analytics events (ingestion emits events; it does not edit existing events).

## What operators can expect after a refresh

- Correcting `title`, `location`, `apply_url` or company profile fields in the
database will survive until the next newer source observation that explicitly
provides a different value for the same field.
- Closing or rejecting a job via review will persist in `job_reviews`; if the
job is observed again, the canonical lifecycle may return to `active`, but the
review decision still gates publication.
- Quarantining a target is the strongest preservation mechanism: it disables
ingestion for that target entirely until the quarantine is explicitly lifted.

## Operational recommendation

Use review decisions and target quarantine for durable corrections. Direct
database edits to canonical fields are effective for short-term overrides but
should be paired with a review decision or quarantine if the change must survive
the next source refresh.

## Related code

- `backend/repositories/sqlite_acquisition.py` — `ingest_snapshot`, `_ensure_company`, `_ensure_company_profile`, `_ensure_version`, `_recompute_lifecycle`.
- `backend/acquisition/producer_adapters.py` — observation contract and batching.
- `backend/acquisition/quality.py` — ingestion normalization and field handling.
