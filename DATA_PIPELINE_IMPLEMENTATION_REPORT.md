# Unified acquisition mapping - final production closeout

## Gate result

GATE PASSED.

Final verification completed on `deployment/render-turso-r2`.

- Deployed functional code commit: `f551c34` (`Quarantine fixture acquisition targets`).
- Guarded reprocessing code is in its deployed ancestor `cba90b6`.
- Latest closeout report push: `ae3399e`.
- Rule version: `unified_mapping_v1`.
- Live migrations: `045_acquisition_reprocessing_leases` and
  `046_acquisition_source_quarantine`.
- `/health/live`: HTTP 200.
- `/health/ready`: HTTP 200.
- No automatic publication, duplicate merge, destructive cleanup, or new
  blocking quality rule was introduced.

## Implementation scope

Migration 044 and the unified mapping implementation provide:

- immutable source payloads and content hashes;
- versioned normalized posting projections;
- field-level provenance and deterministic rule outputs;
- report-only completeness and quality warnings;
- review-only duplicate candidates;
- evidence-backed company URLs and logo-provider projections; and
- guarded, resumable, idempotent reprocessing.

Fresh acquisition stores `raw_payload_json` before normalized projections.
Historical repair preserves unknown values and reports when raw source payloads
were unavailable. No AI, Crunchbase, Apollo, or unconfigured enrichment was
used.

## Reprocessing: 587/587 and replay proof

Idempotency key:
`unified-mapping-production-2026-08-10`

Reprocessing ID:
`reprocess_ef912ccf2e9f44ca974222fe60732e55`

Final guarded run:

| Field | Result |
| --- | ---: |
| Status | `completed` |
| Checkpoint | `587 / 587` observations |
| Failed observations | `0` |
| Batches | `67` |
| Run field mappings | `5,870` |
| Historical repairs | `585` |
| Run warnings | `2,787` |
| Duplicate candidate clusters | `0` |

The official guarded CLI was run again with the identical key. It returned:

```json
{
  "status": "completed",
  "idempotent_replay": true,
  "idempotency_key": "unified-mapping-production-2026-08-10",
  "reprocessing_id": "reprocess_ef912ccf2e9f44ca974222fe60732e55"
}
```

The projection counts immediately before and after that replay were identical:

| Projection | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Source observations | 587 | 587 | 0 |
| Canonical jobs | 141 | 141 | 0 |
| Canonical companies | 11 | 11 | 0 |
| Posting versions | 609 | 609 | 0 |
| Field provenance rows | 18,197 | 18,197 | 0 |
| Rule-output rows | 587 | 587 | 0 |
| Completeness rows | 141 | 141 | 0 |
| Warning rows | 5,949 | 5,949 | 0 |
| Company URL rows | 280 | 280 | 0 |
| Logo enrichment rows | 0 | 0 | 0 |
| Duplicate clusters/members | 0 / 0 | 0 / 0 | 0 / 0 |
| Publications | 5 | 5 | 0 |

Unique-key duplicate checks were zero for provenance, rule outputs,
completeness, and warning event IDs. Replay created no unnecessary posting
version.

## Source reconciliation

Final totals after the fresh acquisition:

| Source | Observations | Canonical jobs | Distinct external IDs | Fresh observations |
| --- | ---: | ---: | ---: | ---: |
| N26 / Greenhouse | 524 | 101 | 101 | 91 |
| Qonto / Lever | 187 | 43 | 43 | 35 |
| Fixture/test targets (`fixture_source`, `x`) | 2 | 2 | 2 | 0 |
| Total | 713 | 146 | 146 | 126 |

Current public head remains unchanged at 133 jobs: 91 N26 and 42 Qonto.
It contains zero fixture/test jobs, proving that the fresh import did not
publish automatically.

## Fixture quarantine

`fixture_source` and `x` were durably quarantined with:

- `maturity_state=quarantined`;
- `enabled=0`; and
- `publication_enabled=0`; and
- `quarantined=1`, with reason `fixture_or_test_target` and a timestamp.

Their two source observations remain present (one per target), and no audit
history was deleted. They are excluded from normal enabled-target metrics and
from the current publication head.

## Fresh N26 and Qonto acquisition

Completed import:
`job_import_22074593266d42c3a66d4206c1995f7c`

Completed cycle:
`acq_cycle_7a82ce40fdfd482a88819cd68e13bd6e`

| Evidence | N26 | Qonto |
| --- | ---: | ---: |
| Source result | HTTP 200 | HTTP 200 |
| Raw observations | 91 | 35 |
| Descriptions present | 91 | 35 |
| `source_metadata` present | 91 | 35 |
| `source_timestamps` present | 91 | 35 |
| `apply_url` present | 91 | 35 |
| `application_url` present | 0 | 35 |
| Field provenance rows | 2,821 | 1,085 |
| Rule-output rows | 91 | 35 |
| Completeness reports | 91 warning-state | 35 warning-state |

N26 uses the verified employer job-detail destination and records the
report-only warnings `missing_direct_application_url` and
`job_detail_url_used_as_application_url` for all 91 rows. Qonto has 35 direct
Lever Apply destinations. Both sources preserve descriptions, source metadata,
timestamps, application classification, raw payloads, and report-only quality
warnings.

## Authenticated production verification

Using the authenticated production browser session, these UI-backed API reads
and screens succeeded:

- `/admin/acquisition` overview;
- sources;
- jobs and admin job inspection;
- companies;
- rules;
- reprocessing and reprocessing plan;
- publication;
- authenticated public Jobs feed and detail; and
- Apply navigation.

The public detail loaded a Qonto job with its full employer description. Apply
opened the real employer/ATS destination:

`https://jobs.lever.co/qonto/694b8f90-e783-4aa6-af36-ba7bfb3c974f/apply`

The destination page rendered the Qonto application form. No application was
submitted.

The targeted affected-suite verification passed: 63 tests and 8 subtests in
the latest affected suite; the focused reprocessing/mapping/admin suite passed
27 tests and 4 subtests. The full repository pytest command previously
exceeded its 120-second command ceiling without emitting a failure, so it is
reported as a timeout rather than a pass.

## Remaining product gaps

- N26 currently exposes a verified employer detail URL but no direct ATS Apply
  URL in the source payload. This is reported, not invented. A future
  provider-specific detail-page extraction can improve it.
- `company_logo_enrichments` is empty because no configured logo provider
  supplied source-backed results. Headcount and associated-member values remain
  source/provider dependent and are not fabricated.
- The observed 91-row N26 persistence transaction exceeded the five-minute
  acquisition lease before completing. It completed safely, but the worker
  should renew leases during long persistence or use smaller durable chunks.

## Operator command

Read-only plan:

```powershell
.venv\Scripts\python.exe scripts\reprocess_acquisition.py --env-file user_config\.env
```

Guarded remote apply/resume:

```powershell
.venv\Scripts\python.exe scripts\reprocess_acquisition.py `
  --env-file user_config\.env `
  --apply --yes --allow-remote-additive-rollback `
  --batch-size 5 --max-batches 1 `
  --idempotency-key unified-mapping-production-2026-08-10 `
  --resume reprocess_ef912ccf2e9f44ca974222fe60732e55
```

Do not modify a reprocessing run row manually while a worker may still be
active. Resume with the same key and inspect the durable checkpoint.
