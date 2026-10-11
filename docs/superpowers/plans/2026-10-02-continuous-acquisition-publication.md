# Continuous Acquisition Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish eligible collected jobs in bounded, resumable batches while collectors continue running.

**Architecture:** Read a consistent producer window under short source locks, then release those locks before remote delivery. Each committed delivery batch advances an immutable public publication using only changed job IDs plus the previous published set; a durable cursor prevents replay or skipped work. Preserve existing head, rollback, completeness, and closure semantics.

**Tech Stack:** Python 3.12.7, SQLite producer state, Turso/libSQL catalog, systemd, pytest.

**Spec:** User request on 2026-10-02: implement all five publication recovery steps and deploy only after live verification.

## Global Constraints

- Keep the LinkedIn, employer, publisher, and backup timers enabled and active.
- Keep finite per-batch timeout, source locks for consistent reads, publication size safety, and atomic head updates.
- Use the repository virtual environment for every Python command.
- The shared checkout has unrelated changes; work in the isolated feature worktree.

## Tasks

- [x] Record durable phase and batch timings with bounded identifiers and no sensitive data; existing `RUNR_PUBLISHER_TRACE_BULK_SQL=1` records individual remote SQL timings.
- [x] Capture a consistent source window while holding source locks only for source reads; SQLite backup and shell syntax tests pass.
- [x] Deliver fixed-size company/job batches with task-based resume and a finite outer timeout; focused retry tests pass.
- [x] Create immutable incremental publications and atomically advance the public head after each successful batch without revalidating the previous catalog; prior-head and replay tests pass. Membership is still copied within Turso and full snapshot JSON is retained for rollback compatibility.
- [ ] Deploy to VPS from an exact committed revision; monitor new head, job counts, publisher timings, all four timers, and a real Runr job lookup. Restore the temporary recovery timeout to the reviewed steady-state setting.

## Review Focus

- A batch crash after remote commit and before cursor save must replay idempotently.
- Partial company batches must never imply absence or close jobs.
- A new head must retain previously published eligible jobs.
- Concurrent publication and rollback must obey compare-and-swap head semantics.
- A failed or slow batch must not prevent unrelated completed batches from becoming public.
