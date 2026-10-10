# Runr VPS migration - complete status and remaining work

Verified 10 October 2026, approximately 23:55 Europe/Berlin.

The customer app, API, worker and authoritative database are on the VPS. The
backup/restore migration is verified. The full acquisition and enrichment system
is not yet restored to operation. Render API/worker remain suspended by the owner.

## Completed and verified

| Area | Result |
|---|---|
| Public app | app.userunr.com resolves to the VPS; HTTPS frontend and API readiness pass. Returning browsers retire the former Render API address. |
| API and customer worker | Active, enabled for reboot, protected env files, resource limits. Existing failed runs are not automatically retried. |
| Database | Production SQLite 3.54.0, Python 3.12.7, migration 077, shared WAL permissions, R2 object storage. |
| Data migration | Complete export restored; full integrity and foreign-key checks passed. 68 customer/billing tables matched frozen Turso. Major catalog counts, publication head and queue reconciled. Whole-catalog payload equality was not exhaustively established. |
| Recurring backups | Daily at 03:30 UTC with up to five minutes jitter; seven verified R2 generations. First backup passed integrity, compressed restore hash and complete off-host readback. Temporary local snapshot removed. |
| Restore drill | Fresh download from R2 restored into isolation; 33,902,178,304 bytes matched the backup hash. Structural/FK checks, schema and customer counts passed. Temporary restored DB removed. |
| Publisher preparation | SQLite binding, shared group permissions, 555 employer exclusions and bounded empty-queue smoke test passed. No real producer-to-publication cycle has run after migration. |
| Document rendering | Chromium generated a PDF under the app service account. |
| Historical cleanup | rc024 evidence and four historical/rehearsal backup directories archived to R2, full readback verified, then removed locally. |
| Grafana | Alloy delivery repaired. Customer dashboard has 15 panels. API/query health and verified-backup metrics are visible in Grafana. Five customer alerts configured. |
| Documentation | Superseded migration notes replaced with this current operating record; original notes remain in Git history. Broad repository cleanup is not complete. |

The root filesystem is 193 GiB, with **136 GiB used and 58 GiB available** at this
inspection. Rounded df figures may not sum exactly. Live DB is approximately
32 GiB. Remaining backups use 30 GiB, scraper state 26 GiB, exports 10 GiB,
retained releases 6.1 GiB and acquisition data 6.9 GiB; these are directory
inventories, not a claim that all their content is safely deletable.

## Scrapers and publication - still paused

| Component | Current state | Required next step |
|---|---|---|
| LinkedIn collector | Timer disabled for migration | Preserve state/checkpoints and request budgets; run a bounded catch-up collection, verify its receipt, then restore timer. |
| Employer-site collector | Timer disabled | Bounded catch-up with the existing exclusion policy and source state; verify coverage/errors before timer restoration. |
| Manifest refresh | Timer disabled | Confirm current company/source inputs and refresh without losing exclusions or state bindings. |
| Publisher | Timer disabled; SQLite preflight passed | Publish real newly collected input to SQLite and verify current head, counts, apply links and queue convergence. |
| Export | Timer disabled | Determine active consumers, reconnect to current authority and restore only the required bounded exports. |
| Legacy acquisition scheduler | Disabled | Keep disabled; dedicated collectors own scraping. |

The owner pause expires **17 October 2026, 14:00 Europe/Berlin**. Finish and remove
it deliberately after acceptance, or extend it if work remains. Do not let expiry
silently restart a partially migrated pipeline.

## AI filters, rules, extracted keywords and descriptions

These functions already exist in the codebase and their stored results were
migrated. Their continuous processing workers have not completed migration.

| Function | What it does | Remaining work |
|---|---|---|
| AI job classification | Nemo assigns source-supported job functions and metadata such as experience, employment type, work model and skills. Shared taxonomy controls function labels. | process_catalog_enrichment.py still calls Turso HTTP directly. Add SQLite persistence, update the actual worker release/env/permissions, verify an AI batch and restart its timer with bounded concurrency/cost. |
| Logical filtering | API applies selected functions and other filter predicates before pagination; checks current version/content hash and excludes classified blue-collar jobs. Rules validate model evidence and numeric years. | Regression-check the deployed SQLite feed, combined filters, pagination, saved filter reloads and stale-result rejection. Preserve rules rather than regenerating everything. |
| Keywords/skills for filters | AI extracts source-supported skills; deterministic validation rejects unsupported labels. Function assignments come from duties, not incidental keywords. | Catch up missing current records and confirm their fields are usable by the current filter UI. This is part of enrichment, not a separate scraper. |
| AI-generated descriptions | Structured English overview, duties, qualifications and benefits grounded in employer text, with original quotations retained. Current code uses budgeted Nemo translation for non-English passages; no local Argos/Torch installation is required by that path. | Migrate description persistence, verify English translation/output and source evidence, recover interrupted claims, process pending work and restart the AI description/filter timer. |
| Rule-based descriptions | Separate source-grounded fallback/backfill service using employer text. | Rebind its actual release and DB access, verify current output, then restore its timer alongside the existing shared lock. |
| Profile matching facts | Provider-free logic turns description/filter evidence into skill/experience facts used by matching. It does not ask Nemo to invent a fit score. | process_profile_job_facts.py still calls Turso; migrate reads and atomic writes/acknowledgements, drain queue and restart timer. |

All three timers - AI descriptions/filters, rule-based descriptions and profile
job facts - are disabled. The AI/rules service failure states reflect termination
at maintenance; profile facts also has a recorded pre-migration read timeout.
Do not treat an old failed service state as evidence of an active new failure.

Live stored results: **32,243 descriptions, 33,824 filter records and 41,796
profile-fact records**. These are total stored rows, not certified current-job
coverage or accuracy rates.

Current publication has **41,730 memberships**. Version/hash-matched filter
inspection found 24,656 white-collar classifications, 9,077 blue-collar
classifications, 7,976 missing current filter records and 21 records without a
collar value. No invalid JSON was found in the matched filter records. These
figures do not mean every white-collar job is fully ready in the customer feed.

AI queue snapshot:

| State | Items |
|---|---:|
| Completed | 28,569 |
| Pending | 9,932 |
| Processing left at pause | 23 |
| Review required | 2,314 |
| Source missing | 928 |
| Source incomplete | 21 |
| Superseded | 9 |

Profile-fact queue: **25,238 items**. Recover expired processing leases before
normal work. Review-required and missing-source items need explicit disposition;
blind retries will not fix missing employer text. Regenerate changed/missing work
only, preserving acceptable paid results and the existing cost ledger.

## Other work still required

1. **Authenticated acceptance:** login, Jobs feed/detail, filters, saved searches,
   workspace/run creation, uploads/downloads, CV exports, tracker and customer
   task completion. Browser automation was blocked because administrator policy
   could not be verified. Server readiness does not establish these journeys.
2. **Provider callbacks and operation:** verify Clerk, Creem webhook/checkout and
   Google tracker OAuth against the public VPS endpoint. Their relevant backend
   credentials are present; presence is not live provider acceptance. DeepSeek
   and ScrapeOps keys are present; OpenRouter key exists in the old description
   environment and needs protected wiring into the migrated worker.
3. **Grafana completion:** acquisition stage-charts and source-store panels report
   down/stale. Pipeline observer repeatedly times out in stage charts. Repair its
   queries/runtime and add verified enrichment backlog/progress, provider errors,
   cost, matching-fact freshness and scraper coverage visibility. Main customer
   health/backup panels are healthy; Render/Turso analytics parity is not complete.
4. **Original uploads:** eight original objects remain missing. One is a current
   real CV, seven are retained document references; one retained source is bound
   to workspace text. The current test resume was recovered from an exact local
   content-hash match and its R2 readback passed. Preserve text and history; do not
   fabricate originals or classify them as missing frontend code assets.
5. **Disk and retention:** continue offloading verified inactive backup/export/
   scraper-copy history. Acquisition backup policy is now two local and seven
   remote generations; old checkpoints have not all been pruned. Bound export,
   release and enrichment audit retention. Check overlap/headroom between daily
   customer and acquisition backup jobs; keep operating space for WAL and restore.
6. **Repository/deployment clarity:** consolidate historical docs and generated
   artifacts without touching active inputs or unrelated work. Migration fixes
   are pushed on migration/vps-sqlite-20261010; normal deployment/release automation
   and branch integration still need reconciliation to prevent a future release
   restoring the former Turso/Render configuration. /opt/runr remains a dependency
   source for shared venv/node packages; do not delete it as an old release.
7. **Operational acceptance:** rehearse a complete bounded collection ->
   publication -> classification/descriptions -> matching-facts -> frontend cycle.
   Verify reboot/scheduled jobs, rollback instructions and notification delivery.
   No alert test email has been sent. Review 13 historical failed customer runs
   individually before any retry; automatic historical retry stays disabled.
8. **Domain/hosting inventory:** app.userunr.com is verified. Any separate public
   website, additional domain or externally configured callback has not received
   a complete acceptance audit in this migration. Keep Render suspended and keep
   the Turso rollback source until final acceptance; decommission them afterwards.

## Completion order

1. Migrate and verify the three enrichment/fact workers and rule-based backfill.
2. Repair incomplete pipeline monitoring and check callback/public app acceptance.
3. Run a small end-to-end catch-up cycle, preserving all budgets/checkpoints.
4. Drain viable AI/facts backlog; separate manual-review and missing-source items.
5. Restore dedicated timers deliberately, then observe a full scheduled cycle.
6. Finish verified retention/repository cleanup and reconcile release automation.
7. Decommission old hosting only after acceptance and a tested rollback record.

The migration is complete only when both the customer app and the continuous
acquisition/enrichment pipeline pass these checks. There is no defensible overall
percentage yet; the verified status and remaining criteria above are the record.

## Durable evidence

- Initial restore: /srv/runr/migration-20261010/verification.json.
- Latest customer backup: /var/lib/runr/customer-backups/latest.json.
- Isolated restore: /var/lib/runr/customer-restore-drill/receipt.json.
- Reconciliation, archived-history receipts and current status audits:
  /srv/runr/ops/alloy-repair-20261010/.
- Publisher smoke: /var/lib/runr/acquisition-data/publisher-sqlite-smoke.json.
- [Customer Grafana dashboard](https://pluckyhovercraft81.grafana.net/d/runr-vps-customer/runr-vps-customer-services).
- [Acquisition operating policy](vps-acquisition-operating-policy.md).

Historical plans remain available in Git history. This report supersedes their
migration status; subsystem docs still contain historical runtime descriptions
that require reconciliation with the current source and live configuration.