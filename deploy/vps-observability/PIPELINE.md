# Aggregate pipeline overview

Owner-requested visibility layer; independent of collection and publication.

Dashboard: https://pluckyhovercraft81.grafana.net/d/runr-data-pipeline

## Live source-stage charts

The top of the dashboard separates LinkedIn and employer jobs. Each source
starts with its latest completed run: selected companies, full/partial/failed
scans, valid cards, detail successes/failures and per-run written jobs where
reported. The employer producer's `jobs_written` value is cumulative store
inventory, so it is intentionally omitted from latest-run job production.
Bounded run-status and scan-reason labels distinguish partial scans and budget
exhaustion. Missing producer metrics are absent, never invented zeroes. The
same run-outcome metrics are graphed over observation time; between completed
runs the latest result repeats, so this is not per-interval throughput.

Each source also has a current four-stage funnel, stage inventory **over time**
and dated first-known stage evidence. Stage counts are distinct within each
source and cumulative across stages: they must not be added together. A job
with both sources can appear once in each source view. The trend x-axis is when
Grafana received each five-minute aggregate snapshot; history begins when this
observer was installed. The dated bars use durable first-evidence dates where
known. Current publication membership without a reliable first-publication
timestamp stays in Unknown, not today's bucket. The employer “detailed” stage
requires a usable title and description; LinkedIn detail requires a durable
job payload. Location is intentionally not shown on this operational dashboard.

The default dashboard range is seven days; the viewer can select any range
retained by Grafana. A failed collector retains its last good snapshot, so read
section health and age before interpreting a flat line.

`stage_charts.py` performs aggregation in a short-lived disk-backed SQLite
table; it does not hold all recovered jobs in RAM. The observer has a bounded
512 MiB service cap and six-minute timeout after the 256 MiB/four-minute
settings proved insufficient on the live VPS. Grafana receives bounded numeric metrics only.
Browser auto-refresh is Off; the five-minute collector/Alloy schedule continues.

The owner also raised the *finite* live source limits on 2026-09-28. The
linked-in collector now has 1,000 requests / 200 selected companies per run,
employer 200 requests / 10 companies, combined cap 1,200 and per-source
timeout 900 seconds. This is not a promise of 1,000 successful job details:
actual outcomes and proxy/provider errors must be read from the next receipts.
`raise-acquisition-budgets.py` performs a guarded, atomic change of the protected
VPS environment, leaving a timestamped protected backup. No request concurrency
or publication-validation rule was raised or removed.

## Runtime

- `/opt/runr-ops/pipeline.py`, outside the application deployment directory.
- `runr-pipeline-overview.timer`: every five minutes; independent of daily source timers.
- `runr-pipeline-overview.service`: read-only access, 512 MiB memory ceiling, six-minute timeout, low scheduling priority.
- `/var/lib/runr/observability/pipeline.json`: aggregate section cache, no company/job rows.
- `/var/lib/runr/observability/pipeline.prom`: bounded-label Prometheus metrics.
- Existing Alloy textfile exporter ships these gauges every minute. No Alloy restart/configuration change is needed.
- Existing health observer and source/publisher/backup timers are unchanged;
  source request/company limits were raised as documented above.

The shared catalog binding is loaded from the existing protected VPS environment
and overlay; it is never copied into Grafana or printed. Queries do not initialize
databases or perform schema migrations. Canonical database aggregation happens in
SQL. Manifest rows and the identity crosswalk are streamed with the pinned ijson
parser. Only needed input identity mappings are retained. Producer SQLite files
are opened `mode=ro`; count and final-row lookups avoid loading job payloads.

## Panels and semantics

The dashboard provides company readiness/cohort pivots, field completeness,
manifest exclusion reasons, configured limits, completed-run outcomes, budget
utilization, detail errors, provider inventory, source/catalog/publication counts,
checkpoint backlog proxies, resolver inactivity, infrastructure and public HTTP
availability. Filters select source, readiness, membership, provider and host.

Global inventory/health panels intentionally stay global; source/cohort filters
do not redefine their denominator. Core-populated is a presence baseline, not
the deployed publication policy. Source rows, company records, unique jobs,
active jobs and current publication membership are separate units. Latest-run
metrics are gauges, not cumulative counters suitable for `rate()`.

The scraper service memory chart plots systemd `MemoryPeak` readings from the
health observer at their Grafana sample times. Each value is the peak for the
service run retained by systemd, not the highest value ever recorded across
all runs. Gaps mean no sample was exported; earlier history is limited by
Grafana retention and the observer installation date.

Backlog is a **rowid-distance proxy**, not exact pending eligible jobs. Source
rowid gaps or deletions matter. Historical import completeness is a separate
1/0 metric. Manifest exclusion reasons overlap and describe the input snapshot,
not an automatic fresh reassessment of live profiles. Unrecognized detailed
error codes are bucketed as `other`, preventing unbounded labels.

Collector errors expose exception classes only, retain last-good values and
their timestamps, and set section_up=0. Process-level termination is detected
through freshness aging, not by inventing a zero-row result. Graph history
starts at installation; it does not fabricate historical inventory.

Public API/frontend probes do not prove an authenticated jobs page, company
logo rendering, Apply success or served-job equality. These remaining gaps are
listed on the dashboard. No secret, job ID, company ID, URL or free-form error
is used as a Prometheus label.

## Install and verify

Check Python 3.12.7 before installing. Upload only the observer, requirements,
installer and its service/timer into a staging directory, then run
`sudo bash install-pipeline.sh`. It installs the small streaming-parser dependency
in `/opt/runr/.venv`, enables only the new observer timer and starts a collection.
Existing observer script versions are preserved as timestamped backups.

Local commands use the project venv:

```powershell
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -m pytest tests/test_pipeline_observability.py -q
.venv\Scripts\python.exe deploy/vps-observability/configure-pipeline.py --publish --verify
```

The publisher uses existing separate Grafana Editor/read credentials without
printing their contents. UID is `runr-data-pipeline`; existing dashboard UID
`runr-vps-acquisition` is untouched. New dashboard read permission can briefly
lag a successful creation; query ingestion also lags by about one scrape cycle.

```powershell
ssh runr-vps "sudo systemctl is-enabled runr-pipeline-overview.timer"
ssh runr-vps "sudo systemctl is-active runr-pipeline-overview.timer"
ssh runr-vps "sudo journalctl -u runr-pipeline-overview.service -n 15 --no-pager"
```

The section journal records names, status and timings only. Do not print live
environment files or unrestricted Alloy/systemd environment output.
