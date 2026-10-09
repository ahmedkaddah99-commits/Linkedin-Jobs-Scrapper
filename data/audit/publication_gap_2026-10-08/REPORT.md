# Active unpublished jobs: live reconciliation, 8 October 2026

The current catalog contains **20,483 active jobs outside the 35,653-job publication**. All 20,483 were reconciled individually against their latest observation, its acquisition cycle, and the current cycle's tasks. No production data, service, policy, or timer was changed during this investigation.

## Exact current exclusion paths

| Path | Jobs | Evidence |
|---|---:|---|
| Historical job; latest source target has no task in current cycle | 15,746 | Latest observation belongs to another cycle; target absent from current task inventory. |
| Historical job; current source-target task is still pending | 4,521 | No observation for this job in the current cycle; matching company task pending. |
| Historical job; company task partial, but this job was not delivered again | 176 | Latest observation belongs to another cycle despite a partial company task. |
| Delivered in current cycle but not included in committed publication | 40 | Current-cycle observation; valid partial task; absent from current membership; all pass the separate hard page-evidence gate. |
| **Total** | **20,483** | One mutually exclusive row per canonical job in `unpublished_jobs.csv`. |

**20,443 jobs have no current-cycle observation.** The ordinary publisher explicitly requires a current-cycle observation for a selected delivery target, or existing membership in the public head. These jobs satisfy neither branch. A partial company task does not make every historical job for that company a candidate. The publisher does not sweep all active catalog jobs.

The remaining 40 jobs belong to 13 valid partial company tasks, each with `jobs_published=0`. These records reached ingestion but did not reach public membership. Their current posting records pass the unconditional navigation/generic-page gate. Policy v1 is report-only for other completeness failures. They are a publication-stage gap rather than a demonstrated data-quality rejection.

## How the historical backlog arose

The latest observation cycles of the same jobs have these outcomes:

| Latest cycle outcome/error | Jobs |
|---|---:|
| recovery_required / max_failures | 11,515 |
| recovery_required / max_companies | 1,031 |
| recovery_required / stalepublicationheaderror | 97 |
| degraded / partial_source_coverage | 7,800 |
| running / no recorded error | 40 |

These are provenance counts, separate from the mutually exclusive current exclusion paths. A degraded cycle alone does not establish an individual rejection. Historical publications have been pruned; this report does not infer their former policies from today's v1 head.

The largest affected cycle, `acq_cycle_f64dc4fba03a458b87b7178c1e0272d9`, stopped with `max_failures`, no publication ID, and zero jobs published. It supplied the latest observations for 8,248 jobs in the gap. The next largest, `acq_cycle_476d061cd07f4a279f56aa0ec590a773`, recorded 15,987 observed jobs but only three published jobs; 4,363 of today's unpublished jobs have their latest observation there.

Ingestion and publication are separate durable steps. The publisher's stop path calls `complete_cycle(status='recovery_required')` and returns before checkpoint advancement. Persisted imports survive this stop. Subsequent delivery cycles only reconsider their bounded source window, not every previously imported unpublished job. That combination leaves active records stranded outside publication.

## Why normal retries have not drained the gap

The latest full attempt hit its 1,800-second wrapper timeout at 19:21 UTC (21:21 Berlin). Its final saved progress was delivery, 326 companies completed out of 669 selected targets. The catalog still lists 375 pending and 693 partial tasks for the cycle. The progress target count and durable task inventory differ; do not equate all stored tasks with the invocation's selected target set.

Subsequent service attempts reported `lock_overlap`. At the live process check, the holder was PID 2865861, a `flock` wrapper running `/tmp/runr-storage-publication-drain-supervisor.py`. This is catalog-history cleanup, not source publication. Its publisher lock prevented scheduled runs during that interval. Collector locks also caused earlier retries. The history supervisor had exited by a later check; its earlier lock ownership is not claimed as permanent.

LinkedIn checkpoint remains row 17,000, bootstrap incomplete, updated 2 October. The publisher saves checkpoints only after completing delivery and publication. Failed/stopped cycles therefore repeat old windows rather than advance through the whole backlog.

## Executing code, not the stale shared tree

The service's effective WorkingDirectory and ExecStart point to `/srv/runr/releases/catalog-storage-7bf1a6682806b85d4cfe0f2144a8b44faef27710`. Earlier chat analysis inspected `/opt/runr`, which is older and not the executing publisher release. That earlier explanation omitted incremental batch publication and the unconditional generic-page gate.

In the executing release:

- `backend/repositories/sqlite_acquisition.py`, `_prepare_publication_snapshot` (around line 3886): current-cycle/target candidate scope; previous membership only when requested.
- Same file, `publish_valid_snapshot` (line 3981): incremental batches combine previous membership with the changed current-cycle subset and commit membership atomically.
- Same file, `_publication_rows_with_completeness` (line 3739): unconditional generic-page exclusion; other completeness exclusions only for blocking policy.
- `scripts/publish_producer_states.py`, lines 1809–1845: resumed targets intersect current selected targets; publication batches contain up to 50 targets.
- Same script, lines 2250–2295: stop before final completion/checkpoint advancement; incremental mode does not perform an all-active-catalog sweep at the end.

The captured source files accompany this report. `job_page_evidence.py` in the executing release is retained for comparison with the evaluator used for the 216 partial-task jobs.

## Verification and artifacts

Python 3.12.7 verified locally and on VPS. Database identity matches the catalog used by today's other audits. Current publication ID and update timestamp remained unchanged on final read-back: `acq_publication_8054372339f34733acaf90540e90df42`, 19:06:15 UTC.

All 20,483 have a current posting version, a known company, and a latest source observation. All are producer-target records. The 216 jobs associated with partial tasks were checked against the hard page gate; zero failed. The 40 current-cycle jobs are a subset of those 216.

`analyze.py` asserts the exact ID reconciliation and count partition, then writes `summary.json` and `unpublished_jobs.csv`. Snapshots are bounded read-only queries captured over a time window rather than one cross-table transaction. The partial full-observation download was superseded by the complete covering-index snapshot plus targeted latest-observation reads; it is not used in the reconciliation.

The required correction is to reconcile the existing active unpublished catalog into publication deliberately, instead of relying on changing source windows to rediscover it, and make publication completion independent of historical delivery failure. Separately, publication must be able to complete within its bounded runtime without being starved by cleanup/collector locks. No fix or live republishing was performed as part of this investigation.


## Retention cleanup ? 2026-10-09

The owner requested removal of nonessential artifacts. Raw captures, generated outputs, historical source copies, one-time probes and deployment scripts, the superseded patch and partial download were deleted. Historical figures above describe the original investigation; the raw inputs are no longer retained. Keep the four reports and four reusable audit scripts. Run capture.py before analyze.py to regenerate its inputs. Verification scripts regenerate their JSON outputs.
