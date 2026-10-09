# Grafana email history and publication backlog

Read all 429 messages in `Takeout/Mail/Grafana Export v1.mbox` from the supplied ZIP. Dates span 26 September to 8 October 2026. Only local audit artifacts were written; email content was treated as evidence, not instructions.

| Alert | Firing notifications | Resolved notifications |
|---|---:|---:|
| Acquisition run failed | 124 | 122 |
| Acquisition outcome partial | 83 | 71 |
| Publisher running unusually long | 4 | 5 |
| Publication head stale | 2 | 2 |
| Shared catalog inaccessible | 2 | 2 |
| Acquisition timer disabled | 3 | 4 |
| Monitoring missing/stale | 1 | 1 |
| Run missing/stale | 1 | 1 |
| Notification test | 1 | 0 |

These are notification counts, not independently deduplicated incidents or numbers of failed jobs. Failure firing messages occur on 11 Berlin calendar dates. The whole export spans 13 calendar dates. Notification timestamps and the message's observed alert-instance timestamp are distinct; the latter is not assumed to be the resolution timestamp.

## Meaning of recovery

The configured failure rule is `max(runr_acquisition_last_run_failed)` across sources. The partial rule is `max(runr_acquisition_last_run_partial)`. Their emails do not identify the failing source. The observer derives failure from last-run/service failure state, and partial from the latest collector outcome. A resolved alert says its evaluated condition cleared; it does not query whether all historical jobs are published.

The publication-stale rule only checks whether the head timestamp is more than 30 hours old. A new publication can clear that alert with a small membership change. It has no active-unpublished count, missing-membership check, or backlog-drain condition. Publisher-long-runtime resolution likewise does not prove publication succeeded; termination can end the long-running condition.

Concrete evidence: the 30 September stale-publication alert fired at 04:00 Berlin and resolved at 13:30 Berlin. The cycle started at 13:28 Berlin and completed at 13:29 Berlin, with 15,987 observations and only three published jobs. Its latest observations account for 4,363 jobs in the reconciled current unpublished group. This is direct evidence that timestamp recovery and backlog recovery are different.

On 7 October, publication-stale fired at 07:58 Berlin and resolved at 09:38 Berlin. Four publisher-long-runtime firing notices occurred across 29 September and 7 October. The recurring failures/partial notices are consistent with the interrupted-delivery history in the catalog audit; their shared-source labels do not prove every notice was a publisher failure.

## Relation to the 20,483-job audit

The exact catalog reconciliation shows 11,515 jobs whose latest cycle stopped with `max_failures`, 1,031 with `max_companies`, and 97 with a publication-head conflict. Another 7,800 have latest observations in degraded cycles, and 40 in the running current cycle. Existing imported records survive interrupted runs. The incremental publisher selects current-cycle deliveries plus existing public membership; it does not automatically sweep older active unpublished records.

Therefore the user's interpretation is substantially correct: unsuccessful/incomplete older publication paths left durable jobs outside the feed, and later cycles can move on without recovering those records. It is not correct to attribute every one of the 20,483 to a timeout alone: the historical error codes above distinguish failures, bounded stops, and conflicts; degraded outcomes alone do not identify an individual rejection.

Artifacts: `messages.json` preserves parsed message text, `timeline.csv` lists all notifications in Berlin time, and `summary.json` contains verified counts. Alert implementation references: `deploy/vps-observability/configure-alerts.py`, rules at lines 28–37; `deploy/vps-observability/observe.py`, metric projection at lines 240–243. Full job evidence is in the parent audit's `unpublished_jobs.csv` and `REPORT.md`.
