# Live Acquisition Stage Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce real, bounded LinkedIn and employer stage/time/city aggregates and show readable Grafana charts without browser auto-refresh.

**Architecture:** A read-only VPS collector summarizes producer and shared catalog evidence into bounded metrics. The existing Alloy path ships those aggregates to Grafana; no raw job records leave the host. Unknown historical evidence is explicit.

**Tech Stack:** Python 3.12.7, SQLite, libSQL/Turso, Prometheus textfile, Grafana.

**Spec:** `docs/superpowers/specs/2026-09-28-live-acquisition-stage-charts-design.md`

## Global Constraints

- Preserve the four scraper/publisher/backup timers and all request budgets.
- No enrichment calls, job-row metric labels, or fabricated historical dates.
- Dashboard automatic refresh Off; underlying aggregator remains scheduled.
- Use project `.venv\Scripts\python.exe` for local Python tests.

## Review Focus

- Duplicated job across multiple source observations: count once per source and stage.
- Missing/ambiguous location: Unknown, not a guessed city.
- Absent event timestamp: Unknown date, not the current date.
- Collector failure: retain last-good timestamp and mark failed.
- Published job with multiple source observations: show once per source with disclosed overlap.

---

### Task 1: Stage aggregation

**Files:** Create `deploy/vps-observability/stage_charts.py`; test `tests/test_stage_charts.py`.

**Interfaces:** Produce aggregate metric items compatible with `pipeline.metric` and read-only source/catalog connections.

- [ ] Write fixture tests for source stage identities, UTC dates, city groups, duplicates and unknowns.
- [ ] Run focused test and confirm failure for missing collector.
- [ ] Implement read-only bounded aggregation; stage mapping must use durable IDs and explicit evidence.
- [ ] Run focused test; verify expected counts and data bounds.

### Task 2: Observer and dashboard

**Files:** Modify `deploy/vps-observability/pipeline.py`, `deploy/vps-observability/configure-pipeline.py`, `tests/test_pipeline_observability.py`.

**Interfaces:** Observer emits section health, stage/current and dated aggregates. Dashboard consumes these only.

- [ ] Write failing dashboard and observer tests for separate source charts, freshness and refresh Off.
- [ ] Run focused tests; confirm expected failure.
- [ ] Integrate collector as a separate section and replace dense top with readable LinkedIn/employer charts.
- [ ] Run focused tests and validate generated Grafana JSON.

### Task 3: Live deployment and verification

**Files:** Modify `deploy/vps-observability/install-pipeline.sh`, `deploy/vps-observability/PIPELINE.md`.

**Interfaces:** Existing protected VPS binding and Grafana Editor/read tokens; no scraper changes.

- [ ] Add deployment verification test/check for service completion, panel queries and timers.
- [ ] Run focused/full relevant tests.
- [ ] Install collector on VPS, publish dashboard, verify fresh aggregate series and timer state.
- [ ] Document limitations and locations, then report actual results.
