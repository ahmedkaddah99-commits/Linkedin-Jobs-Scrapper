# VPS acquisition: owner operating policy

Owner decision, 2026-09-26: Ahmed Kaddah wants reliable unattended collection,
publication, and visibility while validating Runr. There are currently no customers.
Deployment is not evidence of customers and is not a reason to stop scraping.
This supersedes earlier precautionary stops based on assumed customer traffic.

## Every agent and deployment

- Keep the dedicated LinkedIn, employer, and publisher timers enabled and active
  across sessions, reboots, verification, and deployments. Inactive oneshot
  services between scheduled runs are normal; disabled timers are not.
- Do not silently disable/mask those timers, turn off their network access,
  remove their publisher database overlay, reduce budgets, or switch them to
  a test database. Report any operational interruption, reason, expiration,
  and restoration. Never infer customer traffic from deployment.
- The legacy acquisition scheduler stays disabled because dedicated timers own
  scraping. `worker_acquisition_kill_switch_blocked` does not establish that the
  dedicated collectors are stopped. Do not enable a competing scheduler.
- Preserve finite request budgets, source locks, timeouts, resource limits,
  manifest checks, and valid-publication rules. Partial results remain partial.
- Inspect the live host before claiming deployment or scraper success. Linear
  Done and a wrapper exit code zero are insufficient evidence.

## Persistent host controls

`/etc/runr/acquisition-policy.json` records the decision. The independently
installed `/opt/runr-ops/observe.py` runs through `runr-acquisition-health.timer`
every minute, restores accidentally disabled dedicated timers, and records
repairs in its snapshot and journal. It lives outside `/opt/runr` so replacing
application code does not replace it. The three source timers remain daily,
with their existing finite limits; this policy does not create unbounded loops.

An explicitly owner-approved maintenance pause uses
`/etc/runr/acquisition-pause.json`, containing `approved_by: "Ahmed Kaddah"`,
`reason`, and an ISO UTC `expires_at`. The guard resumes enforcing timer state
after expiry. The pause does not itself stop a currently running collector.
It is an audit record, not an authentication system. The guard repairs normal
disablement; unrestricted root access can still remove the guard itself.

The intended shared catalog binding is isolated in
`/etc/runr/acquisition-catalog.env` (root:runr-acquisition, 0640), loaded last by
`/etc/systemd/system/runr-acquisition-publisher.service.d/50-owner-approved-catalog.conf`.
Never print the credential file. Source collectors retain their producer SQLite
databases. Removing the publisher overlay sends publication back to the old
local staging catalog and breaks app delivery.

## Agent visibility and Grafana

Read a sanitized snapshot without a Grafana credential:

```powershell
ssh runr-vps "cat /var/lib/runr/observability/health.json"
ssh runr-vps "sudo /opt/runr/.venv/bin/python /opt/runr-ops/observe.py --catalog-env /opt/runr/.env.acquisition"
```

The first updates every minute. The second is a fresh read-only check; it does
not repair timers unless explicitly given `--enforce-policy`. Recurring catalog
checks are cached five minutes to bound database load. The snapshot exposes
timer/running state, wrapper status, collector outcomes, partial/failure reasons,
last-run time, resource measurements, reported counts, publication head, catalog
job count, and publisher checkpoints. Reported counts can include existing
durable rows; they do not automatically mean new jobs.

Alloy scrapes `/var/lib/runr/observability/acquisition.prom` using its textfile
collector and ships these metrics to Grafana Cloud. It also tails the bounded
sanitized health-events JSONL into Loki:

```logql
{job="runr/acquisition-health"} | json
```

Useful PromQL queries: `runr_acquisition_timer_enabled`,
`runr_acquisition_last_run_partial`, `runr_acquisition_last_run_age_seconds`,
`runr_catalog_head_jobs`, and `time() - runr_catalog_head_timestamp_seconds`.

The prepared dashboard is `deploy/vps-observability/dashboard.json`.
`configure-grafana.py --publish-dashboard` installs it using a separate Editor
service-account token at `user_config/grafana-dashboard-editor-token.txt`.
Cloud read verification uses a separate access-policy token with `metrics:read`
and `logs:read` at `user_config/grafana-cloud-observer-read-token.txt`.
Neither token belongs in Git or chat. Creating a policy/service account alone
does not create a token: use **Add token** and save the value displayed once.

Live verification on 2026-09-26: the observer read token successfully queried
both metrics and logs. The Editor token published and read back the dashboard
at https://pluckyhovercraft81.grafana.net/d/runr-vps-acquisition/runr-vps-and-scraper-outcomes.
All initial 13 panel queries returned series or streams; four publisher phase
and progress panels were added during the recovery investigation. A brief HTTP 403 immediately
after dashboard creation cleared on retry as permissions propagated; it did
not require an Admin token. Dashboard availability is not proof that publication finished.

The agent entry point is:

```powershell
.venv\Scripts\python.exe deploy/vps-observability/read-status.py --ssh --alerts
```

Without `--ssh`, it uses the Cloud read APIs only. `--alerts` additionally uses
the Editor token to report rule evaluation state and errors. Treat scrape/API
latency and the five-minute catalog cache as part of the evidence timestamps.

Eight Grafana rules in **Runr VPS operations** are active: observer absent or
older than five minutes; timer disabled; receipt missing or older than 30 hours;
failed run; partial outcome; catalog inaccessible; publication head older than
30 hours; publisher running longer than two hours. The explicit owner contact
point is **Runr VPS owner alerts**, email `ahmedkaddah99@gmail.com`. Rule-specific
routing preserves the existing global notification policy. Notifications are
grouped for one minute, updated at ten-minute intervals, and repeat every 12
hours while unresolved. Test notification API returned `status: success` on
2026-09-26; inbox receipt is a separate confirmation. All rules evaluated with
`health: ok`; partial coverage correctly entered Pending.

Reconcile configuration with `configure-alerts.py --email <owner-address>`.
Add `--send-test` only when intentionally sending another test email. The
Grafana 13 receiver test uses the notifications v1beta1 API and this stack's
`stacks-1845254` namespace; the removed legacy test endpoint returns HTTP 410.

Publisher progress is atomically written to
`/srv/runr/exports/receipts/publisher-progress.json` by the `60-progress.conf`
unit override, then included in health JSON, metrics and Loki. Older progress
files are rejected when they precede the current service start. The latest
cycle and per-status task counts are included in the catalog snapshot.

Recovery on 2026-09-26 identified two costly remote-write paths: the full
18,537-identity / 17,601-company reconciliation before cycle creation, and
per-field provenance writes during ingestion. Bounded multi-row SQL preserves
transaction rollback, existing company data, and append-only evidence rules.
Two explained recovery restarts applied these changes; the daily timers stayed
enabled. Previous source files are saved under
`/opt/runr-ops/backups/publisher-20260926T160200Z` and
`/opt/runr-ops/backups/publisher-20260926T160957Z`.

Final live recovery evidence: publisher PID 561404 completed all 43 companies
at 2026-09-26T16:13:04Z. Shared Turso publication
`acq_publication_70cc7376580148619dc9a9b85efb72fa` is valid, updated at
16:12:39Z, and contains 120 jobs (previous head contained three). The cycle
reported 25 new jobs, zero rejected, and `partial_source_coverage`; all 43
tasks were partial. Publication completion is therefore proven, but complete
source coverage is not. Cloud/SSH observer readback at 16:15Z confirmed the
new head and all eight alert evaluations healthy; partial coverage was Pending.
The focused repository regression suite passed 42 tests, including bounded
remote writes, transaction rollback, append-only provenance and monitoring.

Grafana provides history, correlation, dashboards, query APIs, and alert evaluation.
The OS quickstart alone cannot answer whether collection or publication worked.
SSH JSON is the immediate agent interface. Cloud verification and dashboard/alert
installation require their credentials and cannot be claimed without them.

## Verification and rollback

Focused tests: `.venv\Scripts\python.exe -m pytest -q tests/test_vps_observability.py`.
The installer validates Alloy before restart and keeps timestamped backups under
`/etc/alloy`. A live disable/guard-repair test restored the LinkedIn timer.

Preserve `/opt/runr-ops`, its units, and current Alloy configuration during upgrades.
To undo only the publisher binding, rename the exact `50-owner-approved-catalog.conf`
drop-in with a `.disabled` suffix and reload systemd. Record that publication is
now local staging. Do not delete either database. Use rollback for an explained
failure, not silent end-of-session cleanup; enabled timers and intended binding
are the normal state.
