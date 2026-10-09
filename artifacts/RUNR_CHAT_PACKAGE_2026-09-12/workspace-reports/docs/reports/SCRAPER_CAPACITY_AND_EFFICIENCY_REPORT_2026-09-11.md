# Scraper capacity and efficiency report

Recorded: 2026-09-11

## Executive conclusion

The producer code has materially improved its data handling and resumability, but continuous VPS sustainability is **not yet proven**. The large historical run yielded many jobs, yet it also performed 271,193 LinkedIn requests and has no persisted CPU-time or peak-RSS measurement. The current production cycle is not delivering the historical catalog to Runr.

The safe conclusion is: the collectors can yield substantial data, but they need measured bounded cohorts and production telemetry before being treated as a continuously safe workload on the Contabo VPS.

## Output evidence

The preserved source run produced:

| Producer | Final catalog | Requests | Other evidence |
|---|---:|---:|---|
| LinkedIn | 188,206 CSV rows | 271,193 | 100 proxies; 187,741 detail successes; 69 partial companies |
| Employer career sites | 2,612 CSV rows | 5,132 | 9,715 accepted input companies; 2,612 persisted jobs |
| Combined projection | 190,818 CSV rows | — | Built from the two source projections |

The LinkedIn metrics file reports `jobs_written=187,741`, while the final resumable state and final CSV contain 188,206 rows. These are not two separate datasets: the run counter and the reconciled final state represent different stages of the resumable run.

The LinkedIn JSONL projection contains 197,915 historical observation rows and 1,305 duplicate keys; the canonical CSV projection is the correct unique catalog projection for downstream import.

## What improved

- Resumable SQLite state and checkpoints preserve progress across interruptions.
- LinkedIn collection uses bounded scan/detail queues, adaptive concurrency, proxy cooldowns, ownership checks, and retry handling.
- Employer collection records provider, extraction method, coverage status, failure evidence, and request accounting.
- CSV, JSONL, and metrics projections are generated for recovery and inspection.
- The production wrapper separates source collection from publication into Runr.

## Efficiency and capacity findings

### LinkedIn

The historical run averaged approximately 22.8 requests per input company and approximately 0.69 detail successes per request. It read 17,601 input rows, accepted 12,046 source rows, rejected 5,555, and recorded 7,360 blocked responses. The final output is large enough that full daily rescans are not a reasonable default for a 6-vCPU host without a measured schedule.

The current producer defaults are more bounded than the historical run: 10 scan workers, 5 detail workers, one request per proxy, and a maximum adaptive worker ceiling of 20. The older URL-catalog implementation used a different execution model and must not be confused with the canonical producer.

### Employer career sites

The historical run produced approximately 0.51 jobs per request. It used multiple extraction paths, but the source landscape is heterogeneous and many sites require discovery or rendering. The latest production run was intentionally capped at 6 requests: it processed 4 companies, produced 1 job, and deferred 5,131 companies. That is a bounded slice, not full coverage.

### CPU safety

The host exposes 6 vCPU, while the acquisition units cap the service at 300% CPU. The collectors are predominantly network-bound, but HTML parsing, JSON processing, SQLite writes, browser rendering, and large export serialization can create CPU and memory bursts. No production CPU-seconds, cgroup peak memory, or sustained-cycle duration was available in the captured evidence. Therefore no claim of continuous safe operation can be made yet.

## Required operating policy before continuous scheduling

1. Run rotating cohorts rather than selecting all companies in every cycle.
2. Start with a conservative worker/request budget and increase only after cgroup CPU and memory evidence.
3. Keep browser rendering behind the direct/ATS/JSON-LD paths and enforce a separate browser request cap.
4. Persist a cycle receipt containing duration, CPU time, peak memory, requests, responses, rate limits, jobs written, and deferred work.
5. Fail closed when an input manifest or pagination-evidence file is missing; do not publish a misleading zero or partial export.
6. Import verified source projections into the canonical Turso model through the existing producer-state bridge before exposing them in Runr.

## Current production gap

As of the inspection, Turso contained 299 canonical jobs and the active publication head contained 47 jobs. The latest cycle was degraded with `partial_source_coverage`, zero fresh observations, 7,368 pending tasks, and 39 partial tasks. The historical 190,818-row catalog remains in the local recovery snapshot and is not the active Runr publication.

