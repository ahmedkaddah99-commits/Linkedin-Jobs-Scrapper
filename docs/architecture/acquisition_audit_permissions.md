# Acquisition audit and operation permissions

This recovery preserves the legacy administrator contract through the explicit
`acquisition_permissions_v1` migration policy. A user with role `admin`, or an
existing token carrying the legacy `admin` scope, continues to grant all
acquisition permissions. No production role reassignment or permission-data
migration is performed.

## Permission matrix

| Permission | Viewer | Reviewer | Editor | Administrator compatibility |
| --- | --- | --- | --- | --- |
| `acquisition.view` | yes | yes | yes | all |
| `acquisition.collect` | no | no | yes | all |
| `acquisition.enrich` | no | no | yes | all |
| `acquisition.review` | no | yes | yes | all |
| `acquisition.override` | no | no | no | all |
| `acquisition.duplicates` | no | yes | yes | all |
| `acquisition.preview` | yes | yes | yes | all |
| `acquisition.publish` | no | no | no | all |
| `acquisition.rollback` | no | no | no | all |
| `acquisition.providers` | no | no | no | all |
| `acquisition.audit` | no | no | no | all |

Explicit token scopes may grant individual permissions. The compatibility grant
is evaluated before role defaults and is intentionally versioned.

## Unified audit contract

Every event belongs to domain `acquisition` and has:

`event_id`, `domain`, `event`, `actor`/`actor_id`, `entity_type`, `entity_id`,
`operation_id`, `occurred_at`, redacted `payload`, `previous_event_hash`, and
`event_hash`.

The append-only SQLite stream covers imports, reviews, enrichment,
reprocessing, duplicate decisions, publication, rollback, provider changes and
policy changes. Legacy `admin_job_audit_events` rows are bridged into the
stream for compatibility.

Query methods accept `domain`, `event`, `actor`, `entity_type`, `entity_id`,
`operation_id`, `occurred_from`, `occurred_to`, `limit`, and `offset`. Results
include `pagination` metadata (`returned`, `total`, and `has_more`). Entity
timelines are the same query constrained by entity type and ID.

HTTP endpoints:

- `GET /admin/acquisition/audit`
- `GET /admin/acquisition/entities/{entity_type}/{entity_id}/timeline`

Both endpoints require `acquisition.audit`.

## Redaction and immutability

Secrets, credentials, authorization values, access/refresh tokens, source text,
emails, phone numbers and unnecessary personal fields are redacted before
persistence and before serialization. SQLite update/delete triggers reject
mutations to audit rows; a hash chain makes append ordering tamper-evident.

## Migration status

The identifier `053_acquisition_audit_permissions` is preserved provisionally
from the completed implementation report. It does not collide with the base
registry in `0068a5f` (which ends at `049_enrichment_foundation`). It is not a
final Wave 1 migration-numbering decision.
