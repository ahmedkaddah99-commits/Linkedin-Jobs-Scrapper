# Real-data Job Publication Completeness Audit

- Contract: `job_publication_completeness_v1`
- Generated: `2026-09-10T19:16:53.606537+00:00`

## linkedin

- Records evaluated: 188206
- Distinct source job identities: 188206
- Duplicate source job identities: 0
- Publishable: 42564
- Distinct publishable companies: 1235

### Outcomes

| Status | Count |
|---|---|
| `publishable_complete` | 42564 |
| `not_publishable_missing_required` | 0 |
| `not_publishable_invalid` | 5 |
| `not_publishable_unresolved_identity` | 145637 |
| `not_publishable_placeholder` | 0 |
| `stale_or_closed` | 0 |

### Source field gaps

- Missing canonical company id: 145637
- Missing description: 0
- Missing application URL: 0
- Missing location: 0
- Apply metrics: {"apply_url_is_linkedin_view": 188206, "easy_apply_true": 631}

### Top blocking reasons

| Reason | Count |
|---|---|
| `missing_canonical_company_id` | 145637 |
| `insufficient_description` | 466 |
| `blocked_or_error_body` | 51 |

## employer

- Records evaluated: 2612
- Distinct source job identities: 2440
- Duplicate source job identities: 172
- Publishable: 63
- Distinct publishable companies: 4

### Outcomes

| Status | Count |
|---|---|
| `publishable_complete` | 63 |
| `not_publishable_missing_required` | 487 |
| `not_publishable_invalid` | 41 |
| `not_publishable_unresolved_identity` | 2018 |
| `not_publishable_placeholder` | 3 |
| `stale_or_closed` | 0 |

### Source field gaps

- Missing canonical company id: 2018
- Missing description: 1404
- Missing application URL: 0
- Missing location: 1911
- Apply metrics: {"has_job_detail_url_fallback": 2612, "missing_explicit_apply_url": 1663}

### Top blocking reasons

| Reason | Count |
|---|---|
| `missing_canonical_company_id` | 2018 |
| `missing_location` | 1911 |
| `missing_description` | 1404 |
| `insufficient_description` | 72 |
| `blocked_or_error_body` | 3 |
| `placeholder_title` | 1 |

## Combined

- Total records: 190818
- Publishable: 42627

## Reconciliation

- `linkedin_outcome_total_equals_records`: True
- `employer_outcome_total_equals_records`: True
