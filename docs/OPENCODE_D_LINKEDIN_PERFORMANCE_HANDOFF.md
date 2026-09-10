# OpenCode D — LinkedIn producer performance handoff

Owner: lane D (LinkedIn producer and source-specific helpers).
Scope: performance engineering, request-efficiency improvement, and safe
bounded concurrency for the existing 14-table LinkedIn producer
`scripts/master_linkedin_jobs_catalog.py`. Not a rewrite.

## SHAs

| Item | Value |
| --- | --- |
| Persistent target branch | `deployment/render-turso-r2` |
| Reported baseline | `848408f3024c3c675abb3f8d6696563eb4184c50` |
| Base SHA (worktree start) | `848408f3024c3c675abb3f8d6696563eb4184c50` |
| Worktree | `C:\Users\ahmed\Projects_Local\runr-opencode-d-linkedin-performance` |
| Branch | `temp/opencode-d-linkedin-performance` |
| Implementation SHA | `a9e9f33b7da0cdb1d57de64cdb3b4959b2200a21` |
| Final tip | verify with `git rev-parse HEAD` (docs-only descendant of the implementation SHA) |

The base SHA is the current committed tip of `deployment/render-turso-r2` and
contains the reported baseline. No branch or worktree was overwritten; the new
branch/worktree were created from the base SHA.

## Files changed

- `scripts/master_linkedin_jobs_catalog.py` — bounded pipelined execution,
  request-limiter ordering fix, retry jitter, batched SQLite writes, config
  knobs and environment override.
- `scripts/benchmark_linkedin_pipeline.py` — new offline, no-network replay
  benchmark that runs the real producer against deterministic synthetic
  fixtures with artificial latency and compares sequential vs pipelined.
- `tests/test_linkedin_pipeline_performance.py` — new correctness regressions
  for pipeline equivalence, overlap, cache identity, retry/budget, and request
  accounting.

No employer collector, deployment file, or shared publication code was edited.

## Original bottlenecks (with evidence)

The producer ran in two strictly sequential phases inside `_run_without_lock`:

1. All company search scans (pagination) via a `ThreadPoolExecutor` of
   `workers` threads.
2. Only after every scan finished, all detail rows via a second
   `ThreadPoolExecutor` of `detail_workers` threads.

Consequences, demonstrated by the offline benchmark (see below):

- Pagination workers sit idle while detail workers are saturated, and vice
  versa, so total wall time is `search_time + detail_time` instead of
  `max(search_time, detail_time)`.
- The global request limiter (`AdaptiveConcurrency`) was acquired *after*
  `WebshareTransport._take_proxy()` returned a proxy. Threads therefore held a
  proxy idle while waiting for a concurrency permit, reducing effective
  parallelism of the proxy pool.
- Every card produced a separate small SQLite transaction
  (`detail_queue` insert and `record_detail_cache_hit`), so cache-heavy daily
  cycles paid one commit per reused job instead of batched commits.
- Retry backoff had no jitter, so a burst of failures could produce a retry
  storm of synchronized sleeps.

Evidence: with 10 companies × 3 pages × 10 jobs (300 jobs, 340 requests) and
100 ms synthetic latency, the baseline (sequential) took 14.19 s wall while
the pipelined path took 10.64 s with identical requests and output.

## What was implemented

### 1. Pipelined search + detail execution

`CatalogRunner` now starts `detail_workers` daemon threads that consume a
bounded `queue.Queue` of detail tasks. `_scan_company` enqueues detail tasks as
soon as cards are parsed, so detail work overlaps pagination instead of waiting
for it. The `CompanyRunContext` is published to `self.contexts` at scan start
so detail workers can resolve the owning context mid-scan.

- `_stop_pipeline()` flushes buffered writes, drains the queue, and joins
  workers. After pipeline shutdown, the existing `get_detail_queue_entries`
  drain still runs as a resume safety net (adopted pending details and any row
  not routed through the in-memory queue).
- The bounded queue (`pipeline_detail_queue_size`, default 1000) provides
  backpressure: scan workers block on `put` instead of building an unbounded
  task list.

### 2. Request-limiter ordering fix in `WebshareTransport`

The account/provider permit is now acquired before `_take_proxy()`, so proxies
are never held while waiting for the limiter. The permit is released after the
proxy result is recorded. `max_requests` budget exhaustion still returns
`request_budget_exhausted` and checkpoints correctly.

### 3. Retry backoff jitter

Retry sleep is now `min(30.0, 0.5 * 2**attempt + uniform(0, 0.25*(attempt+1)))`,
preserving the existing exponential shape while de-synchronizing retries.

### 4. Batched SQLite writes

Detail enqueue rows and cache-hit updates are buffered under a lock and flushed
in a single transaction every `pipeline_flush_interval` (default 10) rows and
at every page/scan boundary. `enqueue_detail` uses a single `executemany` of
`INSERT OR IGNORE`, preserving dedup semantics. A flush always completes before
the corresponding detail task is published to the in-memory queue, so a detail
worker can never observe a missing queue row.

### 5. Thread-safety for shared mutable context

`CompanyRunContext` gained a per-context lock; `observed_job_ids` and
`detail_failures` mutations are guarded because scan and detail workers can now
touch the same context concurrently.

## Concurrency model and default limits

| Knob | Default | Meaning |
| --- | --- | --- |
| `--workers` | 10 | concurrent company scan/pagination threads |
| `--detail-workers` | 5 | concurrent detail worker threads |
| `--pipeline-detail-queue-size` | 1000 | bounded in-memory detail task queue (backpressure) |
| `--pipeline-flush-interval` | 10 | detail rows batched before one SQLite commit |
| `--pipeline` / `--no-pipeline` | enabled | enable/disable pipelining |
| `RUNR_LINKEDIN_PIPELINE` | `1` | environment override; `0` disables pipelining |
| `AdaptiveConcurrency` | min 1, initial 10, max 20 | global account/provider in-flight request cap |

The global request limiter is still shared across all pools, so independent
search and detail pools cannot exceed the total provider budget. The adaptive
limiter still backs off on 429/5xx/blocked and recovers after 20 healthy
observations. The durable `max_requests` budget remains the hard ceiling for
all request kinds and is unchanged.

## Before / after metrics (offline replay, no network)

Synthetic workload: 10 companies × 3 pages × 10 jobs = 300 jobs,
340 total requests (40 search + 300 detail), 100 ms artificial latency,
`--workers 5 --detail-workers 10`.

| Scenario | Sequential | Pipelined | Change |
| --- | ---: | ---: | ---: |
| Cold (340 requests) wall time | 14.19 s | 10.64 s | ~25% faster |
| Cold CPU time | 7.02 s | 6.72 s | ~4% less CPU |
| Cold peak RSS | 44.2 MiB | 44.9 MiB | within noise |
| Warm cache (40 requests, 300 cache hits) wall time | 8.57 s | 7.03 s | ~18% faster |

Both scenarios produced identical durable output: 300 jobs written (cold) and
300 cache hits with 0 detail requests (warm), identical request counts, and
`run_outcome == "COMPLETE"` in both modes. Peak RSS stayed ~45 MiB, far below
the documented VPS bounds (`MemoryHigh=9G`, `MemoryMax=12G`). Requests are
identical, so there is no increase in provider load for equivalent work.

These numbers are local Windows offline replay only. They are not live-source
or VPS measurements and do not claim production throughput.

## Estimated VPS resource requirements

No change to the runtime contract. The defaults (`workers=10`,
`detail_workers=5`, queue size 1000) run within the recorded VPS bounds
(`CPUQuota=300%`, `MemoryHigh=9G`, `MemoryMax=12G`, `TasksMax=512`, 6 vCPUs,
12 GB RAM). Measured peak RSS on the workstation was ~45 MiB; the bounded queue
caps in-memory task buffering at a small multiple of the flush interval, not at
the full detail set.

## Correctness and performance commands/results

All Python commands used the repository interpreter
`C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe`
(Python 3.12.7).

Focused producer + pipeline suite:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_master_linkedin_jobs_catalog.py tests/test_linkedin_pipeline_performance.py
# 69 passed
```

Broad producer/transport regression:

```powershell
.venv\Scripts\python.exe -m pytest -q `
  tests/test_master_linkedin_jobs_catalog.py `
  tests/test_linkedin_pipeline_performance.py `
  tests/test_master_linkedin_jobs_url_catalog.py `
  tests/test_producer_adapters.py `
  tests/test_rc010_first_acquisition_slice.py `
  tests/test_rc023_producer_state_paths.py `
  tests/test_rc024_backup_restore.py `
  tests/test_rc026_benchmark.py `
  tests/test_master_employer_jobs_catalog.py
# 155 passed, 1 failed
```

The single failure is the pre-existing timing-sensitive
`test_shared_limiter_gates_actual_account_and_provider_in_flight_work`, already
recorded in `docs/RC_B_HANDOFF.md` as failing only in mixed-process runs. It
passes in isolation:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_master_linkedin_jobs_catalog.py::test_shared_limiter_gates_actual_account_and_provider_in_flight_work
# 1 passed in 1.20s
```

Ruff and compilation:

```powershell
.venv\Scripts\python.exe -m ruff check scripts/master_linkedin_jobs_catalog.py scripts/benchmark_linkedin_pipeline.py tests/test_linkedin_pipeline_performance.py
# All checks passed!
.venv\Scripts\python.exe -m py_compile scripts/master_linkedin_jobs_catalog.py scripts/benchmark_linkedin_pipeline.py tests/test_linkedin_pipeline_performance.py
# ok
```

Performance comparison command:

```powershell
.venv\Scripts\python.exe scripts/benchmark_linkedin_pipeline.py --compare `
  --companies 10 --pages-per-company 3 --jobs-per-page 10 `
  --search-latency 0.1 --detail-latency 0.1 --workers 5 --detail-workers 10
```

Add `--warm-cache` to pre-seed state and measure the daily cache-reuse path.

## Correctness guarantees preserved

- Pagination/termination: unchanged; the final `get_detail_queue_entries` drain
  still processes any row not routed through the in-memory queue.
- Compact-but-valid responses are not treated as blocks; suspicious-empty,
  blocked, and genuinely empty outcomes remain distinct (untouched parsing).
- A partial cycle cannot close/erase prior jobs; lifecycle reconciliation is
  unchanged and only runs for `COMPLETE_SCAN_STATUSES`.
- Recurring bounded cycles advance through outstanding work; `adopt_pending_detail`
  preserves attempt history and `INSERT OR IGNORE` prevents duplicate detail
  requests within a run.
- Request concurrency never overrides the global `max_requests` budget.
- No job/company field was dropped; `CATALOG_FIELDS` and `upsert_catalog_row`
  are unchanged.

## Live uncertainties

- The benchmark is offline replay with synthetic latency; real provider
  latency, proxy cooldown, rate-limit behavior, and multi-proxy fan-out will
  change the absolute speedup.
- No live acquisition or provider request was run; paid/live acquisition remains
  stopped and the 188-confirmed + 12-reserved allowance was not touched.
- The `WebshareTransport` limiter-ordering fix and pipeline were validated
  against existing and new offline tests, not against a live endpoint.
- The batched `enqueue_detail` uses a single `INSERT OR IGNORE` executemany
  with the same columns as the existing method; dedup and resume semantics are
  covered by tests but not yet exercised against the 3.48 GB historical state.

## Exact shared/runtime changes required from C

No shared-code change is required; the producer is self-contained and the
pipeline is the default. Optional items C may choose to adopt:

- Expose `RUNR_LINKEDIN_PIPELINE` (default `1`) in the acquisition environment
  template if an emergency rollback to sequential execution is desired without
  a code change.
- Consider `--pipeline-detail-queue-size` and `--pipeline-flush-interval`
  overrides only if a future authorized host benchmark shows contention;
  defaults are already within the recorded VPS limits.

No migration, deployment, publication, or scheduler change is requested.

## Stopped-B commits reviewed

`docs/RC_B_HANDOFF.md` (B runtime) records B's `state_dir`/`require_existing_state`
producer changes, which are already integrated in the base and were preserved.
B's `benchmark_acquisition_full_state.py` and `benchmark_personalized_jobs.py`
are separate full-state benchmarks; the new `benchmark_linkedin_pipeline.py`
is a narrower producer-pipeline replay and does not overlap or replace them.
B's note about the timing-sensitive limiter test in mixed processes matches the
single pre-existing failure observed here.
