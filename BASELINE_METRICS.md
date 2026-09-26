# RC-002 offline baseline metrics

Status: complete locally on 2026-09-06. This is the stopping point for Session A; RC-003 was not started.

Target: `deployment/render-turso-r2`, worktree `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview`.

This evidence measures the current offline adapter, SQLite acquisition, and application-publication path. It does not claim production capacity, provider limits, source coverage, or monthly savings. No live HTTP, browser, proxy, Turso, paid enrichment, deployment, push, pull, merge, reset, or cleanup operation was performed.

## Files added

- `scripts/benchmark_acquisition_baseline.py` — repeatable offline benchmark command with a network guard, adapter counters, SQLite trace counters, publication replay check, and checkpoint resume drill.
- `tests/test_acquisition_baseline.py` — three deterministic RC-002 tests.
- `tests/fixtures/rc002/workload_profiles.json`
- `tests/fixtures/rc002/greenhouse_payload.json`
- `tests/fixtures/rc002/lever_payload.json`
- `tests/fixtures/rc002/workday_payload.json`
- `tests/fixtures/rc002/recruitee_payload.json`
- `tests/fixtures/rc002/generic_listing.html`
- `tests/fixtures/rc002/generic_job_valid.html`
- `tests/fixtures/rc002/generic_job_malformed.html`
- `tests/fixtures/rc002/interrupted_run.json`
- `BASELINE_METRICS.json` — JSON output from the recorded benchmark run.
- `BASELINE_METRICS.md` — this evidence record.

This session did not edit the existing dirty exporter/producer files:
`scripts/build_master_jobs_catalog.py`, `scripts/master_employer_jobs_catalog.py`, and `tests/test_master_employer_jobs_catalog.py`.
During the session, additional dirty edits became visible in
`scripts/master_linkedin_jobs_catalog.py` and `tests/test_master_linkedin_jobs_catalog.py`; those changes were also left untouched. The producer files are excluded from RC-002.

## Workload contract

Country scope is Germany. A source is considered measured only when the fixture provides a bounded, deterministic response. Field-presence cohorts remain distinct from reviewed eligibility.

| Profile | Shape | Execution status |
| --- | ---: | --- |
| Representative offline fixture | 5 companies / 5 source tasks; 2 small and 3 large fixture employers; one large employer expands to 32 jobs | Measured |
| RC-001 dual-field-ready cohort | 1,666 candidate rows; 3,332 source tasks if reviewed for both sources | Shape only; not executed |
| RC-001 identity-first expansion cohort | 4,371 candidate rows; 8,742 source tasks if reviewed for both sources | Shape only; not executed |
| Reviewed eligible population | Not established before identity review | Deferred to RC-003–005 |
| Existing LinkedIn state | 188,206 stored jobs / 11,896 source groups / 11,921 scans | Historical aggregate; not executed |

Fixture coverage includes Greenhouse, Lever, Workday, Recruitee, generic JSON-LD, a 429 followed by a successful retry, a malformed detail page, malformed LinkedIn card/challenge HTML, duplicate source records, and an interrupted checkpoint resumed after source task 2.

## Recorded command

The target checkout has no local `.venv`; RC-001 established the repository interpreter at the path below. Its version was verified before running Python:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
# Python 3.12.7
```

The summary was generated from the target worktree with:

```powershell
$summaryPath = 'C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\BASELINE_METRICS.json'
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' scripts/benchmark_acquisition_baseline.py --output $summaryPath
```

Fixture manifest hash for this run: `cf85434bc5632276c4477c1c19d6e159b084567389deccee6e0a5187af0ab2c9`.

## Measured offline result

The run completed successfully on Windows with Python 3.12.7. Timings are one local run and should be regenerated for before/after comparisons; the fixture hash and counts must remain fixed.

| Metric | Result | Meaning |
| --- | ---: | --- |
| Companies | 5 | Fixture companies only |
| Source tasks | 5 | One task per fixture source |
| Raw jobs | 38 | Parsed source records before cross-source key deduplication |
| Unique jobs | 37 | Unique source keys; one Workday duplicate collapses |
| Accepted unique jobs | 36 | Unique jobs with a usable title and URL |
| Rejected raw jobs | 1 | Malformed generic detail record |
| HTTP requests | 7 | Injected fixture transport calls; no network |
| Browser requests | 0 | Browser was not launched |
| Detail requests | 2 | Generic detail fixture pages |
| Retries | 1 | One bounded Workday retry after HTTP 429 |
| Rate-limited responses | 1 | Fixture-only 429 |
| Wall time | 2.535561 s | Includes local backend initialization and SQLite publication |
| CPU time | 1.84375 s | Process CPU time |
| Peak RSS | 66,428,928 bytes | Windows peak working set |
| SQLite statements | 2,553 total / 1,930 writes | Temporary trace counter during workload/publication |
| SQLite database | 7,892,992 bytes | Temporary benchmark database |
| Temporary run storage | 7,893,358 bytes | Database plus checkpoint/artifacts |

Derived fixture-only rates are approximately 1.75 source tasks/s and 12.60 accepted unique jobs/s. These are not production throughput or a speedup claim.

Per-source outcomes:

| Source | Status | Raw / accepted | Requests | Details | Retries | Publication eligibility |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Greenhouse small | completed | 1 / 1 | 1 | 0 | 0 | Included |
| Lever large | completed | 32 / 32 | 1 | 0 | 0 | Included |
| Workday rate-limited | completed | 2 / 2 | 2 | 0 | 1 | Included; duplicate-safe ingestion |
| Recruitee fixture | completed | 1 / 1 | 0 | 0 | 0 | Included; no request |
| Generic large | incomplete | 2 / 1 | 3 | 2 | 0 | Excluded from valid publication because bounded detail closure was not complete |

## Publication and recovery observations

- SQLite stored 36 canonical jobs and 36 source observations.
- The valid publication contained 35 jobs; the incomplete generic source was staged but not included in the valid publication.
- Replaying the same cycle returned the same publication ID.
- Duplicate publications: 0. Duplicate logical jobs: 0.
- The checkpoint drill wrote 366 bytes, interrupted after two source tasks, resumed with three remaining tasks, and replayed zero completed sources. Recovery time was 0.0 seconds because this was a local file read, not a host replacement or process-restart measurement.
- The checkpoint hash was `a99226a28b2e7a02e02f343e2cbf6b2c98397a1ee970a2841498edb2d1a2948f`.

## Cost and storage baseline

| Cost/storage measure | Result |
| --- | --- |
| Offline fixture/provider cost | EUR 0.00 measured |
| Provider/API/proxy/AI estimate | Unknown; no pricing/account ceilings supplied or queried |
| Monthly budget ceiling | Unset; economic gate cannot pass until a numeric user budget is supplied |
| Retained state policy | Not yet implemented by RC-002; plan requires explicit generations, raw-evidence retention, backup transfer, and temporary-export headroom before live scale |

Historical storage/state evidence is recorded separately from this runtime:

| Historical item | Reported value | Classification |
| --- | ---: | --- |
| Employer state records / jobs | 428 / 2,612 | RC-001 aggregate |
| LinkedIn stored jobs / source groups / scans | 188,206 / 11,896 / 11,921 | RC-001 aggregate |
| LinkedIn detail retry rows | 576 | RC-001 aggregate |
| Resolver request logs | 1,475,495 | RC-001 aggregate; not one invocation |
| Resolver status 999 / 429 | 987,057 / 328,493 | RC-001 aggregate |
| LinkedIn 14-table state | 3,479,191,552 bytes | RC-001 local-state report |
| Employer state | 83,841,024 bytes | RC-001 local-state report |

## Proposed pilot targets frozen for later measurement

These are explicit planning targets, not capabilities established by this offline run:

- One daily UTC cycle should target completion within 20 hours and must not exceed 24 hours.
- Alert when an enabled source has no qualifying success for 48 hours.
- Measure fast API/status endpoints at p95 <= 1 second and priority customer queue wait at p95 <= 30 seconds at a separately frozen representative load.
- Preserve accepted publication/customer results with zero loss in worker/host failure and replay drills after durable acknowledgment.
- Replacement-host scraper recovery target: resume from a verified checkpoint within 60 minutes.
- Local-only checkpoint age target: at most 6 hours during active collection and at most 6 hours of local-only rework after disk loss.
- Maintain at least 25% RAM headroom; disk reserve must exceed the largest measured temporary export/backup plus an outage buffer.
- Provider circuit proposal: after at least 50% blocked/rate-limited responses among 20 attempts in a rolling five-minute window, cool down 15 minutes and allow one probe; honor individual `Retry-After` values first.
- Resolver proposal: at most 10 outbound attempts per unresolved URL per rolling 24 hours across restarts/transports.
- Monthly total-cost target is intentionally unset until expected/adverse provider and operations costs are supplied.

No numeric production capacity, customer completion target, provider quota, or speedup is claimed by this artifact.

## Limitations and next boundary

- The representative fixture is deliberately small and synthetic, even though it includes a 32-job large-employer shape. It cannot extrapolate to 1,666, 4,371, or the historical 188,206-job state.
- The 1,666 and 4,371 cohorts are field/readiness shapes from RC-001, not verified eligible populations. The reviewed population remains unknown until identity/reconciliation work.
- The benchmark uses local SQLite, not Turso/libSQL, Render, a VPS, object storage, browser automation, proxies, or paid providers.
- Memory and storage are measured on the local Windows host. Provider/account cost, network latency, remote DB contention, concurrency, and replacement-host recovery remain unknown.
- The generic adapter correctly reports an incomplete bounded snapshot; no source is treated as complete merely because it returned jobs.
- Historical aggregates are copied from RC-001 evidence and are explicitly not runtime throughput measurements.

RC-003 is intentionally not started. The next authorized slice would be identity mapping/reconciliation against the existing application registry, not a live benchmark or broad import.

## Verification commands and results

Python version check:

```text
Python 3.12.7
```

Focused RC-002 tests:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest -q tests/test_acquisition_baseline.py
```

Result after the final fixture/measurement changes: `3 passed`.

The benchmark itself exits `0`, emits JSON, and writes `BASELINE_METRICS.json`. No selected command performs live/network I/O.

## Rollback

This session did not change a tracked application or producer file. The target had additional dirty producer/exporter changes at handoff; preserve them. To roll back RC-002, first verify the target worktree status, then move aside or remove only these newly added paths:

```text
BASELINE_METRICS.md
BASELINE_METRICS.json
scripts/benchmark_acquisition_baseline.py
tests/test_acquisition_baseline.py
tests/fixtures/rc002/
```

Leave the three pre-existing dirty exporter files and all unrelated user changes untouched. The rollback is recoverable from the worktree only if the added files are moved aside rather than deleted; no rollback was executed during this session.
