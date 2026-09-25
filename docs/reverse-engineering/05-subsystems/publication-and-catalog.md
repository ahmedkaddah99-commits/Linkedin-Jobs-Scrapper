> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Publication and catalog (WS-3 secondary)

Secondary doc; the primary is [acquisition-and-collectors.md](acquisition-and-collectors.md) (producers, connector layer, manifest gate, scripts inventory). Scope here: the **producer-state publisher** (`scripts/publish_producer_states.py`), the **record-completeness gate** (`backend/acquisition/job_publication_completeness.py`), **publication policy versions** (`backend/acquisition/publication.py`), **source merging** (`backend/acquisition/job_source_merging.py`), the **store publication machinery** (`backend/repositories/sqlite_acquisition.py`), the **identity crosswalk application**, catalog recovery (`scripts/publish_existing_catalog.py`) and the **combined CSV projection** (`scripts/build_master_jobs_catalog.py`).

Method: static reading at `58a96674` only. Nothing was executed; production state is UNKNOWN and never claimed "live".

---

## 1. Purpose and user-facing capabilities

The publisher is the only bridge from the two durable producer state DBs to the shared acquisition catalog that customers browse in the Jobs UI (WS-4 consumes the catalog). Capabilities:

| Capability | What it does | Main code |
|---|---|---|
| Incremental producer-state publication | Bounded rowid bootstrap + watermark incremental reads; only changed companies are re-delivered; durable per-source checkpoints | `scripts/publish_producer_states.py` (`run_delivery`, `_load_incremental_source`); checkpoint state via `SqliteAcquisitionStore.publisher_checkpoint`/`save_publisher_checkpoint`; schema via WS-5 migration `061_acquisition_publisher_checkpoints` |
| Observation delivery | Adapts producer rows to `runr_source_observation_v1`, ingests per company as an independent target, batches ≤100, `send_final` closes a snapshot | `_deliver_group` L561–592; `backend/acquisition/producer_adapters.py:607` (`SqliteAcquisitionTransport`) |
| Record-completeness gate | Deterministic, source-independent publishability verdict per canonical job with machine-readable reason codes | `backend/acquisition/job_publication_completeness.py` (`validate_job_for_publication` L594) |
| Publication policies | v1 report-only (default), v2 blocking (opt-in, registered but **not used by the runtime publisher**) | `backend/acquisition/publication.py:34–45` |
| Publication snapshot + head | New publication row, thin snapshot JSON, `acquisition_publication_jobs`, single-row head with optimistic concurrency (`StalePublicationHeadError`) | `sqlite_acquisition.py:2360` (`publish_valid_snapshot`) |
| Identity crosswalk application | Persist reviewed old→winner company map, repoint mutable projections in one transaction, quarantine losers | `sqlite_acquisition.py:5232` (`apply_company_identity_crosswalk`) |
| Catalog recovery | Recheck and re-publish the stored active catalog without source replay | `scripts/publish_existing_catalog.py` → `publish_existing_catalog_snapshot` (`sqlite_acquisition.py:2568`) |
| Combined CSV projection | Concatenate LinkedIn + employer exports; never merges across sources; both sources required | `scripts/build_master_jobs_catalog.py` (docstring L1–6, `MASTER_FIELDS` L30) |

## 2. Owned paths and governing instructions

Owned by WS-3 (see primary §2): the files below are the publication slice.

| Path | Lines | Role |
|---|---:|---|
| `scripts/publish_producer_states.py` | 1,191 | publisher CLI (VPS runtime entry) |
| `scripts/publish_existing_catalog.py` | ~90 | recovery CLI (OPS) |
| `scripts/build_master_jobs_catalog.py` | 351 | combined CSV (RUNTIME, export unit) |
| `backend/acquisition/publication.py` | 91 | policy registry |
| `backend/acquisition/job_publication_completeness.py` | 873 | gate (`job_publication_completeness_v1`) |
| `backend/acquisition/job_source_merging.py` | ~300 | merge rules (`job_source_merging_v1`) |
| `backend/repositories/sqlite_acquisition.py` | 7,514 | store: cycles, tasks, observations, canonical jobs, publications, crosswalk (schema owned by WS-5 migrations) |

Governing docs: `docs/JOB_PUBLICATION_COMPLETENESS_CONTRACT.md` (contract for the gate; the Easy Apply rule was later changed by `a2c6fea7` — see §5), `docs/ACQUISITION_RUNTIME_DATA_INVENTORY.md`, `docs/RUNR_VPS_ACQUISITION_PLAN.md` (planning). `deploy/acquisition-data-manifest.json` describes the publisher wrapper as "publication policy v1 display-first completeness gate" (checked, matches code defaults).

## 3. Entry points and registered commands/units

- VPS: `runr-acquisition-publisher.service` (timer 04:00) → `deploy/run-acquisition-publisher.sh` → `scripts/publish_producer_states.py --manifest --linkedin-state --employer-state --data-dir --source-version [--identity-crosswalk] [--skip-status-only]` (wrapper L51–59); optional env `RUNR_COMPANY_IDENTITY_CROSSWALK` (L42–44), `RUNR_PUBLISHER_SKIP_STATUS_ONLY=1` (L46–48); receipt via `scripts/write_acquisition_receipt.py --source publisher` (L64–73). Wrapper takes `publisher.lock` plus non-blocking `linkedin.lock`/`employer.lock` (exit 75 retry, L17–34). Timers: WS-7 [../02-deployment/vps-runtime-and-acquisition-timers.md](../02-deployment/vps-runtime-and-acquisition-timers.md).
- Export unit: `runr-acquisition-export.service` → `scripts/build_master_jobs_catalog.py` (ExecStart L19–22).
- Operator: `scripts/publish_existing_catalog.py --data-dir [--created-by catalog_recovery] [--origin system] [--policy-version publication_policy_v1]`.
- No HTTP routes (admin publication routes deleted in `dd47acf9`).

## 4. Inputs, outputs, storage and dependencies

| Item | Detail |
|---|---|
| Inputs | RC-005 eligibility manifest (hash + sidecar verified, `load_manifest`), two producer state DBs opened **read-only** (`_read_only_connection` L54, `mode=ro`), optional `company_identity_crosswalk.json` (`--identity-crosswalk`, parsed L1165–1173) |
| Checkpoints | `acquisition_publisher_checkpoints` — **schema owned by WS-5 migration `061_acquisition_publisher_checkpoints`** (append-only, `CREATE TABLE IF NOT EXISTS`); **persistence owned by `SqliteAcquisitionStore`** (`require_publisher_checkpoint_table` preflight, `publisher_checkpoint` read, `save_publisher_checkpoint` UPSERT); the publisher is the sole runtime writer. Key: `source` (PRIMARY KEY, one row per `linkedin`/`employer`); columns: `source_rowid`, `source_watermark`, `bootstrap_complete`, `last_cycle_id`, `last_publication_id`, `updated_at`. Lifecycle: saved only after a successful `publish_valid_snapshot` + `complete_cycle`; a failed run leaves rows untouched, so a rerun re-reads the same window (at-least-once, deduped by observation identity keys). |
| Outputs | Cycle + per-company tasks + observations in `SqliteAcquisitionStore`; publication rows (`acquisition_publications`, `acquisition_publication_jobs`, `acquisition_publication_head`); JSON metrics on stdout → receipt; rejections in `acquisition_job_rejections` (L2311–2358) |
| DB location | `$RUNR_DATA_DIR/backend.sqlite3` (publisher L868) or Turso per `DATABASE_BACKEND` (schema/migrations: WS-5 [../03-data/schema-and-migrations.md](../03-data/schema-and-migrations.md)) |
| Consumers | WS-4 personalized Jobs service reads the catalog (`backend/application/personalized_jobs_service.py`); migration `060_publication_latest_observation_index` (WS-5) |
| Env | `RUNR_PUBLISHER_SOURCE_ROW_BATCH_SIZE` (default 250, bounded 25–1000, L894), `RUNR_SOURCE_VERSION`, Turso creds when remote |

## 5. Important call/data flows

1. **Delivery** (`run_delivery` L844): load manifest → apply optional crosswalk **before** delivery (L871–883, provenance `producer_state_publisher`) → per source, if bootstrap incomplete, read rowid windows of `job_company_observations` (LinkedIn) / `jobs` (employer) plus the latest run's rows (L240–288); after bootstrap, watermark incremental: changed companies from `company_scans.finished_at`/`last_seen_at` (LinkedIn) or `companies/jobs.updated_at` (employer) (L290–341).
2. **Targets**: each canonical company becomes target `producer_<source>_<company_id>` with `connector=producer_<source>` so the Phase G applicant gate cannot block delivery (L524–558; comment L536–539). Cycle key = SHA-256 of manifest hash + both source markers + checkpoints + source version (L986–998); `claim_due_cycle(force=True)`; `already_running` if leased.
3. **Closure safety**: LinkedIn company is `closure_safe` iff bootstrap complete AND all latest scan statuses ⊆ {COMPLETE, COMPLETE_ZERO_CONFIRMED, SATURATED_RECOVERED} (L46, L1048); employer iff coverage `outcome == confirmed_complete` (L47, L1053); failed employer statuses make the snapshot invalid (L47, L1054). Non-closure-safe company → task `partial`; any partial → cycle `degraded` + error `partial_source_coverage` (L1115–1121).
4. **Gate**: `publish_valid_snapshot` (store L2360) selects candidate canonical jobs (latest observation per job; includes jobs already in the previous head so publications are additive, L2463–2476), then `_publication_rows_with_completeness` (L2237) runs `validate_job_for_publication` with `require_application_destination=policy.missing_apply_is_blocker` (L2278–2283). Rejected rows persist to `acquisition_job_rejections` with reason codes (source `publication_completeness_gate`, L2343). Head update is compare-and-swap (`StalePublicationHeadError`, L2515–2536); audit event `publication_created` (L2537).
5. **Easy Apply / display feed**: `REASON_EASY_APPLY_NOT_SUPPORTED` fires for any truthy `easy_apply_status` on LinkedIn records **in every publication mode, including display-first** (completeness L711–720; commit `a2c6fea7` "reject easy apply from display feed"). Job-detail/tracking/redirect/listing URLs are rejected destinations (L256–266, L696–704).
6. **Source merging**: `merge_source_records` (`job_source_merging.py:197`) merges complementary observations only on explicit recorded relationships (`same_posting`, `duplicate`, `cross_source_match`, `repost`, `canonical_match`, L38–44); application destination precedence `dedicated_apply > embedded_apply > job_detail_with_apply > job_detail_only > redirect_apply` (L47–56); uncertain dedupe never publishes (docstring L11). Uncertainty is surfaced by the gate as `uncertain_dedupe_identity` / `unresolved_ownership_conflict` (completeness L653–662).
7. **Policy versions**: `publication_policy_v1` = report_only, missing-apply not a blocker; `publication_policy_v2` = blocking, `missing_apply_is_blocker=True`. The runtime incremental publisher now passes **v2** (`scripts/publish_producer_states.py` `RUNTIME_PUBLICATION_POLICY_VERSION`); the display-first compatibility mode remains available for explicit recovery or audit paths that set `require_application_destination=False`.
8. **Combined CSV**: `build_master_jobs_catalog.py` concatenates both source exports into `master_jobs.csv` with `MASTER_FIELDS = union(LINKEDIN_CATALOG_FIELDS, LEGACY_LINKEDIN_FIELDS, EMPLOYER_FIELDS)` (L27–30); refuses missing inputs; both CSVs must be non-empty (cycle wrapper L40–49). `LINKEDIN_CATALOG_FIELDS` now includes the blocking completeness fields (`seniority`, `company_logo`, `company_enrichment`) so they survive from the LinkedIn producer state into the CSV and DB projection.

## 6. Invariants, failure handling and recovery

| Invariant | Where |
|---|---|
| Producer DBs are read-only inputs to the publisher | `mode=ro` (L54–60); publisher lock barrier in wrapper |
| Crosswalk applied before delivery, in a transaction, mutable projections only; source observations/evidence never rewritten | `apply_company_identity_crosswalk` docstring L5240–5247; repointing L5344–5354 |
| A publication either advances the head atomically or raises | CAS head (L2515–2536); whole publish inside `_run_transaction` |
| Intermediate batches never authorize absence/closure; only `send_final` with a complete external-ID inventory closes a snapshot | transport (primary §5.3) |
| Empty-snapshot closure preserved by default; `--skip-status-only` is the explicit recovery mode | publisher L1098–1099, help L1150–1154 |
| Cycle failure → `recovery_required` + error code; checkpoints only saved after a successful publication | publisher `run_delivery` exception path + `save_publisher_checkpoint` call sites (post-`complete_cycle`) |
| Checkpoint saved only after success → a crashed run re-reads the same window (at-least-once, deduped by idempotency keys); same-cycle replay is a no-op | publisher `run_delivery`; store replay guard (`ingest` skips already-observed `(target_id, cycle_id, external_job_id)`); proven by `test_crash_before_checkpoint_save_reruns_the_same_window_idempotently` |
| Publisher never creates the checkpoint schema; it preflights and fails fast if migration `061_acquisition_publisher_checkpoints` has not run | `store.require_publisher_checkpoint_table` at the top of `run_delivery`; `RuntimeError` names the migration |
| Combined CSV never built from one source | cycle wrapper; `_generation_id` raises on missing CSV |

Recovery: `scripts/publish_existing_catalog.py` (schema preflight L40–61 then `publish_existing_catalog_snapshot`, origin `system`, created_by `catalog_recovery`); `--skip-status-only` publisher rerun; `scripts/reprocess_acquisition.py` rule replay (primary §4.3).

## 7. Relevant tests and safe verification commands (not executed in Phase 2)

| Area | Tests |
|---|---|
| Publisher | `tests/test_producer_state_delivery.py`, `tests/test_production_completion_regressions.py`, `tests/test_publish_existing_catalog.py`, `tests/test_rc023_producer_state_paths.py` |
| Gate / merging | `tests/test_job_publication_completeness.py`, `tests/test_job_source_merging.py`, `tests/test_job_completeness_audit.py`, `tests/test_real_job_data_audit.py`, `tests/test_rc009_normalization_publication.py` |
| Identity crosswalk | `tests/test_company_identity_canonicalization.py`; the store method `apply_company_identity_crosswalk` has no direct test at the baseline (**WS3-G10**) |

Safe (offline) commands, not executed in Phase 2:

```bash
node scripts/run-python.cjs -m pytest -q tests/test_producer_state_delivery.py tests/test_job_publication_completeness.py tests/test_job_source_merging.py
node scripts/run-python.cjs -m pytest -q tests/test_publish_existing_catalog.py tests/test_production_completion_regressions.py
node scripts/run-python.cjs scripts/publish_producer_states.py --help
node scripts/run-python.cjs scripts/build_master_jobs_catalog.py --help
git grep -n "publication_policy_v2" 58a96674 -- scripts backend   # confirm v2 opt-in status
```

Never run the publisher against a real data dir outside an authorized host (it writes the catalog DB).

## 8. Historical decisions and supporting commits

(`git log --oneline 58a96674 -- scripts/publish_producer_states.py` selected)

| Commit | Subject | Decision |
|---|---|---|
| `652d7ea8`, `6c8a34de`, `e7be355a` | completeness contract; opt-in policy v2; validate vs real state | gate is v1-default, v2 registered |
| `d44d3c0f` | restore canonical publication chain | publisher as sole bridge |
| `3d36d8cb` | persist identity crosswalk before delivery | crosswalk-before-delivery ordering |
| `a11d7b38`, `b28c3565`, `a8a39a2e`, `5dfdd106` | batch delivery transactions; skip redundant upserts; efficient target reads; avoid full cycle payload reads | Turso-friendly incremental publisher |
| `50b8f7c4` | rotation incremental publishing and display feed | incremental checkpoints |
| `35fd6396` | publisher company identity reconciliation | |
| `5e75e0df`, `914503de`…`10711462` | bound historical publisher recovery; bounded existing-catalog publication; display-first recovery | recovery paths |
| `dd47acf9` | remove admin surfaces | admin publication routes gone (merged `550ee00a`) |
| `a2c6fea7` | reject easy apply from display feed | Easy Apply rejected in every mode |
| `7251ae29` | reconcile producers inputs and runtime data | inputs committed, data manifest |

## 9. Current implementation status

| Capability | Classification |
|---|---|
| Incremental publisher entry + checkpointing | VERIFIED (scope: static full read of `scripts/publish_producer_states.py`; wrapper call verified in primary §3.1; T31 moved checkpoint schema to WS-5 migration `061_acquisition_publisher_checkpoints` and persistence to `SqliteAcquisitionStore` methods, with fresh/upgrade/crash-retry coverage in `tests/test_database_migrations.py` and `tests/test_producer_state_delivery.py`) |
| Observation transport + idempotency keys | VERIFIED (scope: static read of `producer_adapters.py`; primary §5.3) |
| Record-completeness gate (`job_publication_completeness_v1`) | VERIFIED (scope: static full read; reason codes and status precedence traced) |
| Easy Apply rejected in all publication modes | VERIFIED (scope: static; completeness L711–720, commit `a2c6fea7`) |
| Publication head CAS + audit events | VERIFIED (scope: static read of `publish_valid_snapshot`) |
| Blocking policy **v2 active in runtime** | PARTIAL — v2 is implemented and registered (publication.py L40–45) but the runtime publisher passes v1 (L1113); v2 appears only in the uncalled `_run_delivery_legacy` (L823) (**WS3-G7**) |
| Identity crosswalk application (store) | VERIFIED (scope: static read of `apply_company_identity_crosswalk` L5232+) |
| Combined CSV projection | VERIFIED (scope: static; both-sources invariant in cycle wrapper) |
| Catalog recovery (`publish_existing_catalog.py`) | IMPLEMENTED-UNVERIFIED (script read; not executed against a real catalog) |
| Source merging executed in the runtime publication path | UNKNOWN — `merge_source_records` exists and is tested, but the publisher/store publication path does not call it at the baseline (merging happens at observation identity level); confirm intended integration (**WS3-G8**) |
| Admin publication UI | RETIRED/HISTORICAL (`dd47acf9`) |

### Deployment evidence (documentary only — not live verification)
- `deploy/acquisition-data-manifest.json` (baseline, generated 2026-09-08, release `9ba1d551`): publisher wrapper classified "independent_publisher_service_wrapper", schema check "publication policy v1 display-first completeness gate", "publisher preserves last valid head on failure".
- Untracked `docs/reports/RUNR_PRODUCTION_COMPLETION_REPORT_2026-09-12.md` (feature checkout, not in git; T06): VPS release `4a1b1df5`; publisher timer described as enabled (host state UNKNOWN).
- `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` (WS-7 owns): Render-side catalog state as of `5dfdd106`, documentary only.

## 10. Confirmed gaps and unresolved questions

| ID | Gap |
|---|---|
| **WS3-G7** | `publication_policy_v2` (blocking) is registered but never used by the runtime publisher; the only v2 call site is the dead legacy path. Decide promotion or removal. |
| **WS3-G8** | `job_source_merging.merge_source_records` has no runtime call site in the publisher/store publication path at the baseline; cross-source merge is effectively observation-level only. Confirm intended integration or mark dormant. |
| **WS3-G9** | CLOSED by T31: `acquisition_publisher_checkpoints` is now created only by WS-5 migration `061_acquisition_publisher_checkpoints` (append-only, idempotent for pre-existing ad hoc tables); the publisher preflights via `store.require_publisher_checkpoint_table` and fails fast instead of creating the table; persistence lives in `SqliteAcquisitionStore.publisher_checkpoint`/`save_publisher_checkpoint`. |
| **WS3-G10** | `SqliteAcquisitionStore.apply_company_identity_crosswalk` (a destructive-in-projection, transactional operation) has no direct test file at the baseline (grep over `tests/` finds no reference). |
| N-5 / C4 / C5 | Wrapper-level concerns carried in primary §10 (caps, live-network flag, timers; WS-7). |
| T01 | Unmerged employer patch `6ea7f460` also touches delivery-side files; reference only (`UNMERGED (feature/admin-analytics-final-production @ ce3718b0)` branch context, patch on `temp/runr-employer-final`). |

## Agent context and remaining work

**(a) Agent context packet — publication & catalog**
- Required reading: this doc; [acquisition-and-collectors.md](acquisition-and-collectors.md) §3.1, §5.3; `scripts/publish_producer_states.py`; `backend/acquisition/job_publication_completeness.py`; `backend/acquisition/publication.py`; `backend/repositories/sqlite_acquisition.py` L2237–2600 and L5232–5420; `deploy/run-acquisition-publisher.sh` (read-only, WS-7).
- Allowed paths: `scripts/publish_producer_states.py`, `scripts/publish_existing_catalog.py`, `scripts/build_master_jobs_catalog.py`, `backend/acquisition/{publication,job_publication_completeness,job_source_merging}.py`, publication sections of `backend/repositories/sqlite_acquisition.py`; tests in §7 (with WS-10).
- Tests to run: the two pytest commands in §7.
- Prohibited: running the publisher or recovery script against a real data dir; enabling `publication_policy_v2` implicitly; editing `deploy/**` or migrations (WS-5/WS-7); rewriting historical observations/evidence.

**(b) Registry proposal**

| subsystem id | name | owned globs | primary doc | test globs | owner |
|---|---|---|---|---|---|
| `acquisition-publication` | Producer-state publication and catalog | `scripts/{publish_producer_states,publish_existing_catalog,build_master_jobs_catalog}.py`, `backend/acquisition/{publication,job_publication_completeness,job_source_merging}.py`, publication/crosswalk sections of `backend/repositories/sqlite_acquisition.py` | `docs/reverse-engineering/05-subsystems/acquisition-and-collectors.md` (this doc as secondary) | `tests/test_{producer_state_delivery,job_publication_completeness,job_source_merging,job_completeness_audit,real_job_data_audit,publish_existing_catalog,production_completion_regressions,rc009_normalization_publication}.py` | WS-3 |

**(c) Gap/ticket candidates**
1. WS3-G7: promote or delete `publication_policy_v2` (needs owner decision + audit against real stored records per publication.py L29–31).
2. WS3-G8: wire or retire `merge_source_records` in the publication path.
3. WS3-G9: ~~move `acquisition_publisher_checkpoints` into the migration registry (coordinate WS-5).~~ Done by T31 (migration `061_acquisition_publisher_checkpoints`).
4. WS3-G10: add direct tests for `apply_company_identity_crosswalk`.
