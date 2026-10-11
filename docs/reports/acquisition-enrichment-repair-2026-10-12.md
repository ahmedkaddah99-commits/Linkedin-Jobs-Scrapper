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

Focused tests cover the retention boundary, distinct index cursors, recovery
selection, independent-stage persistence, restart reuse and uncertain provider
spend. Production acceptance and final release identity will be recorded below
after the staged release is activated.
