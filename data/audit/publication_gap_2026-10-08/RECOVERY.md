# Publication recovery, 2026-10-09

## Confirmed causes

1. Publication candidates were limited to current-cycle observations and existing published membership. Older stored, unpublished jobs therefore never reached the publication gate.
2. The delivery cycle key included collector run IDs. Each new scrape could replace a capped or failed publication cycle before its pending targets were delivered. Checkpoints remained at 2026-10-02 while new cycles continued.
3. Empty-task completion used remote `executemany`, which issues one statement per task. A measured phase took approximately 211 seconds; the observed transport exception was `connection closed before message completed`, previously missing from transient retry classification.
4. Publication candidate reads downloaded full version payloads, and incremental updates downloaded and re-uploaded the complete publication snapshot. Recorded publication batches took roughly 69–142 seconds (an earlier batch 255 seconds), and ingest batches took 26–215 seconds. Source preparation alone took approximately 163 seconds. These are phase measurements, not a claim that all ingest cost is eliminated.

Stored producer and catalog rows survived failures. Docker isolation is not the cause of their exclusion. AI enrichment is not a prerequisite under the current report-only completeness policy; existing hard publication checks still apply.

## Implemented and verified locally

Commit `46f38c029e1050e49a7834fb6c2e51905e90edb1`, branch `fix/publication-recovery-20261009`:

- Add migration 076: a durable queue seeded with active unpublished jobs and database triggers for new/changed jobs and replaced publication heads.
- Drain bounded batches independently of source cycles, using the existing gate, atomic membership/snapshot/queue updates and revision/head fences. Rejections retain explicit reason codes.
- Keep producer cycle identity stable across collector rounds, preserving a conservative watermark for subsequent changes.
- Complete empty tasks using bounded set updates; retry the observed transport disconnect.
- Read only gate fields from payloads; update publication JSON on the database server.
- Install a recurring recovery service and run recovery before producer locks in the publisher wrapper.
- Expose queue progress and install a stalled-backlog alert. Capped runs are partial rather than unexplained failures.

Focused verification: **156 tests and 13 subtests passed**. Additional observer compatibility change `c380f795` passed all 10 observer tests.

## VPS rollout

Additive migration 076 applied to the intended shared Turso catalog. At installation, queue pending: **20,441**, published head membership: **36,195**. Recovery release:
`/srv/runr/releases/publication-recovery-46f38c029e1050e49a7834fb6c2e51905e90edb1`.

The existing producer publisher was left running; its next invocation uses the new release. The independent worker shares its publisher lock and retries every thirty seconds. All original collector, publisher and off-host backup timers remained enabled and active. Shell syntax and systemd unit verification passed.

Monitoring uses an older independent database adapter; its queue query was adjusted to compatible bounded SELECTs (`c380f795`) and verified live with `access_ok: true`. Grafana now has nine verified active rules including stalled backlog. No notification test was sent.

## Live recovery findings

At 2026-10-09 00:22:27 UTC, head membership and snapshot both contained **36,520** rows. The queue contained **19,526 pending**, **273 published**, and **727 rejected** entries. Some queue entries were already published by the producer; they were acknowledged rather than duplicated. Every active unpublished row had a queue entry.

The recorded hard rejections at that check were 649 `unverified_generic_page`, 53 `unlinked_application`, 22 `incomplete_job_posting`, and 3 `generic_navigation_title`. A 200-row comparison of compact gate input against complete stored payloads produced identical acceptance and rejection outcomes.

Completed recovery batches took 14.7–26.8 seconds after initial preparation; intermittent batches waited 138–198 seconds. The trace localized the major wait to write-transaction acquisition. A separate idempotent no-op queue write also timed out while ordinary bounded reads completed in about 0.15 seconds and candidate preparation in 2–4 seconds.

**Verified provider failure:** an independent read-only `EXPLAIN QUERY PLAN` through the deployed profile-facts adapter returned:

`SQLITE_IOERR: SQLite error: request interrupted because local diskless state diverged from S3`

The atomic HTTP recovery batch independently returned `SQLITE_IOERR`. This establishes a Turso storage-state failure in addition to the application publication/retry bugs. No claim is made that the application caused that storage divergence. Restarting VPS containers cannot repair Turso's provider-side storage state.

Additional fixes on the isolated branch acquire the write transaction before optimistic fences and provide an opt-in conditional atomic Hrana HTTP batch, so the entire write can be submitted in one request with rollback on failed steps. The worker uses this path; stale revisions were verified to roll back all publication changes. Provider errors remain visible rather than marked complete.

For a two-minute isolation experiment, only the profile-facts companion timer/service were paused, with automatic restoration scheduled. The no-op write still timed out; the timer was explicitly restored and verified active. The four required acquisition/backup timers remained active throughout.

Provider management access is not configured: local configuration contains only the SQL URL/token, no Turso account-management token, no available Turso CLI, and no connected browser session. Management access was requested to continue provider recovery. No support message was sent and no database was recreated or restored.

**Not complete:** the backlog has not drained, the provider write failure persists, and producer checkpoint advancement is not yet verified. The queue and recurring retry remain installed. The exact provider failure must be cleared before end-to-end completion can be established.

Latest pinned verification at **2026-10-09 00:38:54 UTC**: **37,196 published**, **16,878 active unpublished pending evaluation**, and **2,647 active unpublished rejected**. Rejections: 2,340 unverified generic pages, 184 unlinked applications, 99 incomplete postings, 24 navigation pages. The queue has 16,926 pending entries because 48 queued jobs were already published by the producer and await acknowledgement. Membership and snapshot both contain 37,196 rows; the head stayed stable during verification.

The independent worker now uses bounded 500-job batches and the atomic HTTP path. The publisher wrapper uses the same path with a finite kill-after watchdog. The latest recovery regression suite passed **13 tests**; the initial focused suite passed **156 tests and 13 subtests**. Eight consecutive 200-job HTTP batches completed in 7–15 seconds before provider timeouts recurred. Provider issue text prepared in `TURSO_INCIDENT.md`; it has not been sent.


## Retention cleanup ? 2026-10-09

The owner requested removal of nonessential artifacts. Raw captures, generated outputs, historical source copies, one-time probes and deployment scripts, the superseded patch and partial download were deleted. Historical figures above describe the original investigation; the raw inputs are no longer retained. Keep the four reports and four reusable audit scripts. Run capture.py before analyze.py to regenerate its inputs. Verification scripts regenerate their JSON outputs.

Cleanup verification: 36 focused recovery, migration and observability tests passed. The active VPS blue-policy release contains the recovery runtime changes; preserve its additional employer exclusions rather than replacing it with the older recovery branch. A live recovery retry encountered a database HTTP read timeout; this is an operational observation, not a successful health verification.
