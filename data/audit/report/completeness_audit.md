# Job Publication Completeness Audit

- Contract: `job_publication_completeness_v1`
- Generated: `2026-09-10T15:19:02.879242+00:00`
- Input records: 300
- Unique canonical jobs: 300
- Duplicate-identity records skipped: 0

## Outcomes

| Status | Count | Percent |
|---|---|---|
| `publishable_complete` | 60 | 20.0% |
| `not_publishable_missing_required` | 50 | 16.67% |
| `not_publishable_invalid` | 58 | 19.33% |
| `not_publishable_unresolved_identity` | 36 | 12.0% |
| `not_publishable_placeholder` | 35 | 11.67% |
| `stale_or_closed` | 61 | 20.33% |

## Counts by source

| Source | Count |
|---|---|
| `employer_site` | 174 |
| `linkedin` | 126 |

## Top blocking reasons

| Reason code | Count |
|---|---|
| `missing_description` | 59 |
| `insufficient_description` | 55 |
| `missing_location` | 41 |
| `missing_canonical_company_id` | 36 |
| `closed_lifecycle_state` | 34 |
| `missing_application_url` | 33 |
| `stale_observation` | 31 |
| `tracking_only_application_url` | 28 |
| `listing_fallback_application_url` | 28 |
| `placeholder_description` | 27 |
| `placeholder_title` | 13 |
| `missing_title` | 13 |
| `unknown_canonical_company_id` | 13 |
| `blocked_or_error_body` | 6 |
| `future_posted_at` | 6 |

## Coverage

- Publishable jobs: 60
- Distinct publishable companies: 50
- Records lacking canonical company identity: 36
- Invalid or missing application URLs: 89
- Missing descriptions: 59
- Placeholder descriptions: 27
- Published that would fail the contract: 219
