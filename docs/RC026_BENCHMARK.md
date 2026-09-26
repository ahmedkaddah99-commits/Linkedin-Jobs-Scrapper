# RC-026 offline benchmark and cost evidence

Status: offline benchmark preparation and comparable local-state evidence are
complete on B. RC-026 is not fully verified: VPS capacity, customer overlap,
Turso contention/billing, provider request/cost behavior, and any staging
sample remain gated by RC-023/024/025 integration and explicit staging
authorization.

Measurement date: 2026-09-09. Worktree: `temp/rc-b-vps-runtime`. The shared
repository interpreter was verified as Python 3.12.7:

```text
C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe
```

## Boundary and inputs

The final run used
`C:\Users\ahmed\AppData\Local\Temp\runr-rc026-benchmark-20260909-v3` as a
disposable workspace and wrote the sanitized JSON result to its `report.json`.
The inputs were the verified RC-024 checkpoint copies, not the historical
source databases directly:

| Role | Checkpoint | State bytes | Checkpoint SHA-256 | State shape |
| --- | --- | ---: | --- | --- |
| LinkedIn | `linkedin-20260909T085116426477Z-4b604df8392a` | 3,479,191,552 | `adc5c1ab7ac5b7bdca67cdabd7687fdd29913afae188fab2aba4377a41327525` | 188,206 observations; 14-table checkpoint |
| Employer | `employer-20260909T085018133133Z-53589d4a53bb` | 83,841,024 | `4f779500c9cd5fb66342cb36bd2fd236cefb9b9eebb3caf13876fca8b1265aaf` | 2,612 persisted jobs; two-table checkpoint |

Every historical source digest matched before and after the run. The benchmark
blocked `requests.Session.request`, cleared proxy credentials, forced the test
SQLite backend, and made no provider, Turso, R2, Render, or host request.

## Implementation

The benchmark is intentionally standalone and bounded:

- `scripts/benchmark_acquisition_full_state.py`
  - `run_employer_concurrency_matrix()` runs a 5-company deterministic fixture
    through the real employer `run_collection()` and atomic final export.
  - `benchmark_checkpoint()` validates an RC-024 manifest, copies the
    immutable database, verifies its digest, and measures isolated export.
  - `_export_linkedin_state()` streams one observation at a time using the
    producer's ordering and catalog fields, with an atomic temporary CSV.
  - `run_customer_replay()` reuses the existing 1,000-job personalized Jobs
    and Company warm-path benchmark.
  - `_ResourceMonitor` records peak process RSS and workspace bytes during each
    operation; all fixture matrix and customer limits are bounded.
- `scripts/benchmark_personalized_jobs.py` now uses explicit column lists for
  the current migrated fixture schema; this fixes the demonstrated 15-versus-
  22-column and 6-versus-13-column positional insert failures in the benchmark
  seed only.
- `tests/test_rc026_benchmark.py` covers bounded inputs, offline request
  blocking, coverage invariants, checkpoint-copy integrity, atomic employer
  export, customer replay, and unknown-cost behavior.

The large LinkedIn measurement uses a read-only equivalent of
`StateStore.export_catalog_csv`: it opens the verified copy read-only, executes
the same ordered `job_company_observations` stream, serializes the same catalog
fields, and atomically promotes the CSV. Reopening the full historical copy
through `StateStore` was not used for this timing because its legacy repair
scan is not bounded for a large state; see limitations below.

## Measured state copy and export

| Role | Copy time | Copy peak RSS | Copy workspace | Export/replay time | Export peak RSS | Output | Coverage/final state |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| LinkedIn | 5.2050 s | 73.5 MiB | 3,479,191,552 B | 137.6890 s | 106.7 MiB | 775,613,386 B CSV | 188,206 streamed observations; source unchanged |
| Employer | 0.1157 s | 108.7 MiB | 83,841,024 B | 4.9885 s | 112.3 MiB | 78,134,553 B CSV/JSONL/metrics | 2,612 persisted/exported jobs; `final_export_completed=true` |

The combined verified checkpoint bytes are 3,563,032,576 B (3.3183 GiB).
Four six-hourly copies would be 14,252,130,304 B (13.2733 GiB) per day as
bandwidth arithmetic only; no cadence or off-host price was assumed.

## Controlled concurrency and customer replay

All employer fixture rows completed with five persisted and five exported jobs,
zero network attempts, zero browser navigations, and `final_export_completed`.
The observed matrix was:

| Company workers | Wall time | Peak RSS | Peak active collectors | Workspace peak added |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0.2128 s | 63.9 MiB | 1 | 57,896 B |
| 2 | 0.1788 s | 64.0 MiB | 2 | 57,896 B |
| 4 | 0.1298 s | 64.4 MiB | 4 | 56,261 B |

The fixture-only tuning result admits 4 company workers in this matrix. It
does not set a production concurrency value: the production value remains
unknown until an authorized host benchmark measures real provider/browser
workload, RAM, disk, and customer overlap. The checked-in runtime contract
remains the ceiling reference only: `CPUQuota=300%`, `MemoryHigh=9G`,
`MemoryMax=12G`, `TasksMax=512`.

The existing customer warm path used 1,000 seeded local jobs and 30 iterations:

| Operation | p50 | p95 | Peak RSS | Network requests |
| --- | ---: | ---: | ---: | ---: |
| Personalized Jobs | 287.28 ms | 751.50 ms | 73.2 MiB overall run | 0 |
| Personalized Company detail | 63.32 ms | 210.37 ms | 73.2 MiB overall run | 0 |

This is local SQLite only. Database billed reads/writes and performance while
acquisition is active were not instrumented.

## Cost and request accounting

The measured offline boundary recorded zero provider/network requests. It does
not imply zero production cost. The report keeps all unmeasured prices as
`unknown`:

| Component/scenario | Result |
| --- | --- |
| Fixed VPS hosting and temporary Render overlap | Unknown; no pricing/billing access in this pass |
| State storage | 3.3183 GiB measured; storage price unknown |
| Backup bandwidth/operations/retention | Local copy measured; off-host path and price unknown |
| Build traffic, proxies, AI/OCR, analytics | Not exercised; price unknown |
| Expected provider retry scenario | Provider requests and retry factor unknown until bounded authorized sample |
| Adverse retry scenario | Retry factor, provider requests, and cost unknown; no uncapped run permitted |
| Turso reads/writes/contention | Not measured; local SQLite only |

No flat user-capacity, compute-savings, or euro cost claim is made.

## Acceptance status and limitations

| RC-026 criterion | Status |
| --- | --- |
| Representative state copies and integrity | Verified offline against both RC-024 manifests; sources unchanged |
| Streaming/export time and disk workspace | Verified offline; employer uses `export_only`, LinkedIn uses the bounded read-only equivalent |
| Controlled concurrency and coverage preservation | Verified fixture-only at workers 1/2/4 |
| Peak RAM/disk recording | Verified on this Windows workstation; not VPS headroom |
| Request accounting and no uncapped provider benchmark | Verified: network blocked, 0 observed attempts |
| Customer target during active acquisition | Not verified; replay was local SQLite and acquisition was not active |
| Turso contention/billed reads/writes | Not verified |
| Provider cost/retry model and monthly bill | Not verified; prices intentionally unknown |
| Full RC-026 | Pending integrated RC-023/024/025 and authorized staging/live sample |

An initial full-state attempt was stopped after the LinkedIn `StateStore`
reopen entered its legacy `_backfill_observation_scan_ids()` repair scan; it
had produced no final artifact and did not change the source. The final run
therefore measured the bounded read-only streaming equivalent and explicitly
records that the producer reopen path was not measured. This is an operational
follow-up for the integrated/staging gate, not a capacity claim.

## Reproduction

From the B worktree, using only the shared repository interpreter:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
# Python 3.12.7

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest -q tests\test_rc026_benchmark.py
# 5 passed in 4.86s (focused rerun after final probe fix)

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' scripts\benchmark_acquisition_full_state.py `
  --output-root 'C:\Users\ahmed\AppData\Local\Temp\runr-rc026-benchmark-20260909-v3' `
  --report-json 'C:\Users\ahmed\AppData\Local\Temp\runr-rc026-benchmark-20260909-v3\report.json' `
  --linkedin-checkpoint-dir 'C:\Users\ahmed\AppData\Local\Temp\runr-rc024-historical-20260909\linkedin\linkedin-20260909T085116426477Z-4b604df8392a' `
  --employer-checkpoint-dir 'C:\Users\ahmed\AppData\Local\Temp\runr-rc024-historical-20260909\employer\employer-20260909T085018133133Z-53589d4a53bb'
# completed; report.json contains the exact values summarized above
```

The benchmark result is ready for C to integrate before any staging execution.
Only C should merge/push; RC-027 remains the authorized staging gate.
