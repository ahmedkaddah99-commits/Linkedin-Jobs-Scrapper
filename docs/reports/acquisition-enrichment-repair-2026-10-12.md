# Acquisition and enrichment repair, 12 October 2026

The October 12 verification found SQLite lock failures, a publisher running an
older overridden release, and high rejection rates in Nemo enrichment. Fresh
collection through customer-visible enrichment had not been established.

The repair uses one final systemd override and one explicit lock directory for
collectors, publisher and lifecycle maintenance. Producer databases use WAL so
readers do not prevent collector commits. Employer exclusions, SQLite authority,
R2 storage, finite collection limits and the ten-dollar daily AI ceiling remain.

Indexed producer retention now compares against thirty days ago, rather than
today, and resumes by the metadata cursor rather than a potentially different
job rowid. Each maintenance round extends the index for newly collected jobs.
The recovery command restores only mistakenly retired eligible jobs from a
verified backup, preserving legitimate old/manual-work tombstones and current
producer rows. It holds all producer/publisher locks and defaults to dry-run.

AI requests have one combined response contract. Invalid classification and
description output each have one durable bounded repair stage. Paid output is
reused after restart; ambiguous requests cannot be replayed. Valid filters
survive a description validation failure. Cached reviewed responses can return
to the queue only when the corresponding repair has not been attempted, the
version is current and published, and its lifecycle is eligible. Missing or
incomplete source text is not retried without new acquisition evidence.
Source quotes remain original; summaries must be English. Source-section
fallback does not copy German text into an English summary. Unknown taxonomy
labels and unsupported quotations remain rejected.

## Verification

The final selected suite passed **134 tests**, covering producer retention,
publication recovery and completeness, acquisition through customer projection,
grounded English descriptions, durable provider request reuse, stage persistence,
and graceful shutdown. Rules output containing only an introductory overview
now requires AI enrichment; it cannot mark the description complete.

Runtime commit: `6747d20cc6b78255e89415827e83575fbb999aaa`, deployed to
`/srv/runr/releases/acquisition-repair-6747d20c`. The archive SHA-256 is
`cd0ac4d0d27c4cd3a08472ba2557bce3a0ea6845888faf2ba9258cd3f9b75043`.
Seventeen critical runtime files were verified against the archived commit and
again on the VPS. Deployment evidence is retained at
`/srv/runr/ops/acquisition-lifecycle/20261011T234123Z`.
The implementation branch was pushed and merged into the shared checkpoint
branch. Unrelated working changes were preserved.

Live verification on 12 October (Berlin time) established:

- A valid current publication head and **42 recently observed published jobs**
  since the repair began; this includes updated observations, not only new jobs.
- Seven freshly observed jobs passed the actual serving application's customer
  detail and combined role/company feed projections, with English summaries,
  original source evidence and current profile fact signatures. Serving API
  release was `21f6baa7f6346b907d5edbbbb23c9dd067be9b91`.
- A bounded 32-job AI canary completed 28 jobs and excluded four blue-collar
  postings. The later running worker completed another 234 jobs before a
  deliberate shutdown; its receipt confirmed `shutdown_drained: true` and
  systemd recorded successful deactivation. Provider failures and unsupported
  output were retained explicitly rather than counted as success.
- Recovery restored **5,588 eligible employer jobs** from a backup whose hash
  matched its off-host receipt. LinkedIn recovery found no eligible recent
  mistakenly retired jobs. Corrected retention removed 22,000 genuinely expired
  LinkedIn jobs in a bounded round; its physical cleanup backlog continues.
- A full bounded LinkedIn round exited successfully under the 900-second cap,
  without the prior database lock failure. Its coverage remained partial:
  source anomalies, empty listings and finite budgets still limit observations.
  Employer collection also completed successfully, with partial source coverage.
- All ten acquisition, publication, enrichment, fact, backup and lifecycle
  timers are enabled and active. The migration maintenance pause was archived.
  The final AI worker runs from the new release. Legacy competing acquisition
  schedulers remain disabled. Production readiness confirms SQLite and R2.

## Remaining operational work

The engine and sampled server lifecycle are verified; historical backfill is
still running. At the final snapshot, the queue held 9,939 completed enrichments,
75 blue-collar exclusions, 5,975 pending entries and 183 entries requiring review.
These are aggregate queue counts, not a claim that all are current published
jobs. There were also 538 source-missing and 24 source-incomplete entries.
Those need real acquisition evidence before enrichment can succeed. Profile
fact maintenance had 8,611 entries, including obsolete entries being removed in
bounded batches. Enrichment remains constrained by the ten-dollar daily budget;
uncertain provider spend is not automatically repeated.

Browser acceptance was not performed: the user explicitly requested to handle
the signed-in UI check. The seven customer checks above exercise server-side
application behavior and do not imply browser layout or interaction acceptance.
