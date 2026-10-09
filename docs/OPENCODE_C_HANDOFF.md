# OpenCode C delivery handoff

## Current status

Date: 2026-09-10
Worktree: `C:\Users\ahmed\Projects_Local\runr-opencode-c-delivery`
Branch: `temp/opencode-c-delivery`
Baseline: `848408f3024c3c675abb3f8d6696563eb4184c50`
Current HEAD: `6c8a34de` (clean; only this handoff is untracked)
Target branch: `deployment/render-turso-r2`

Interpreter: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe` → Python 3.12.7.

## Lane SHAs reviewed (committed snapshots only)

| Lane | Branch | Commits since baseline | Implementation SHA |
|---|---|---|---|
| A | `temp/opencode-a-remove-admin` | none | none yet |
| B | `temp/opencode-b-collectors` | `66b61445` (handoff doc only) | none (no collector code) |
| D | `temp/opencode-d-linkedin-performance` | `a9e9f33b` + 4 docs | `a9e9f33b7da0cdb1d57de64cdb3b4959b2200a21` |
| E | `temp/opencode-e-employer-completeness` | `13ccb9a7` + 1 doc | `13ccb9a7d03ef5a12d6f35a2dd9f39813ac5be5b` |
| F | `temp/opencode-f-job-completeness` | `652d7ea8` | `652d7ea8` |

D/E/F are still correcting their remaining acceptance gaps; these SHAs are snapshots, not real-data acceptance.

### B findings (stopped; carried into D/E/F)

B made no code changes. Its handoff identifies two collector defects that live in D/E-owned files (not C):
- Bounded-cycle advancement: both collectors slice `companies[:limit]` / `selected[:max_companies]` from the head, so small `resume=True` cycles re-hit the same first rows and never advance. Needs a durable cursor in `EmployerState`/`StateStore` and rotated order.
- Exact cohort selection + recheck-budget interaction: `run_collection` must never silently expand a `--company-ids` cohort, and must keep filling the slice with fresh rows once the recheck budget is exhausted.

C-owned items B explicitly deferred to C:
- `scripts/build_master_jobs_catalog.py`: keep `MASTER_FIELDS` in sync with `CATALOG_FIELDS`/`EMPLOYER_FIELDS`; confirm `source_provider` fallback; decide first-class vs JSONL-only for `extraction_method`/`discovery_method`/`transport`.
- `backend/application/source_eligibility_manifest.py`: cohort semantics must be validated here; `company_ids` must never be expanded/reordered/merged.
- Publication/lifecycle: combined export concatenates sources without cross-source dedupe; document whether to keep this or introduce a `(canonical_company_id, source_job_id, source_type)` merge key.

### D interface (LinkedIn performance)

Self-contained in `scripts/master_linkedin_jobs_catalog.py`. No shared change required. Optional C adoption: expose `RUNR_LINKEDIN_PIPELINE` (default `1`) in the acquisition env template for emergency rollback. No migration/publication/scheduler change requested.

### E interface (employer coverage receipts)

New `backend/acquisition/employer_coverage.py` + `coverage_receipts` table (lazily created in `master_employer_jobs_state.db`). C required to:
1. Treat only `confirmed_complete` companies as eligible for closure-safe publication; everything else stays open/recheck.
2. Set `RUNR_RELEASE_COMMIT` or `RUNR_SOURCE_VERSION` in the acquisition worker environment for receipt provenance.
3. Keep receipts in the durable state DB (not the export catalog) — the existing state/export split is preserved.
4. No migration required (table is created lazily and is backward-compatible).

### F interface (job publication completeness)

New `backend/acquisition/job_publication_completeness.py` validator (`validate_job_for_publication`) + `backend/acquisition/job_source_merging.py`. C required to wire the gate (not yet wired by F). Recommended read-time gate in `backend/repositories/sqlite_personalized_jobs.py`, plus an explicit opt-in policy version. F's exact validator signature is documented in `docs/OPENCODE_F_JOB_COMPLETENESS_HANDOFF.md`.

## Completed C-owned changes

### Commit `da565e94` — deployment topology + scheduler hour gate
1. `render.yaml`: disabled live acquisition and company-enrichment on the Render API and customer worker; acquisition can only run on the VPS role.
2. `deploy/start.sh`: added `acquisition` role pinning `WORKER_ROLE=acquisition`.
3. `deploy/systemd/runr-acquisition-worker.service`: uses `deploy/start.sh acquisition`.
4. `deploy/systemd/runr-acquisition-export.service` + `.timer`: daily 06:00 UTC combined company/job export.
5. `backend/application/acquisition_scheduler.py`: `scheduled_hour_utc` gate (production 00:00 UTC). The window key is date-based (`%Y-%m-%d`), so a worker that comes up after the configured hour still claims that day's unclaimed window; a restarted worker recovers dispatching requests via `recover_dispatching_requests()` before claiming.
6. `backend/application/services.py`: `run_due_acquisition(now=...)` for deterministic tests/replay.
7. `.gitattributes`: LF for `*.sh`, `*.service`, `*.timer`, `*.target`.
8. `tests/test_phase_a_scheduler.py`: `scheduled_hour_utc` regression.
9. `docs/ACQUISITION_EDITED_FIELDS_AND_OVERRIDES.md`.

### Commit `6c8a34de` — opt-in publication blocking policy (completeness wiring prep)
1. `backend/acquisition/publication.py`: registered `publication_policy_v2` (`completeness_mode="blocking"`, `missing_apply_is_blocker=True`). Default remains `publication_policy_v1` (`report_only`); no blocker is activated implicitly.
2. `backend/repositories/sqlite_acquisition.py` `_build_publication_preflight`: under a blocking policy, escalate completeness warnings and broken apply destinations into `blockers` and set `report_only=False`. Report-only output is unchanged.
3. `tests/test_publication_policy_rollback.py`: new test proving v2 escalates blockers while v1 stays report-only.

This prepares F's completeness gate without activating it. The full F-validator read-time gate is **not** wired yet (F's module is still changing); the policy flag + preflight escalation is the C-owned enforcement primitive the read-time gate will consume.

## Verification

- `tests/test_phase_a_scheduler.py`: 2 passed.
- Combined focused check after both commits (`test_phase_a_scheduler`, `test_phase_a_rc016`, `test_phase_a_rc017`, `test_phase_a_remediation`, `test_publication_policy_rollback`, `test_rc009_normalization_publication`, `test_worker_service`, `test_database_migrations`, `test_rc022_build_release_contract`): **65 passed, 8 subtests passed**.
- Expanded backend regression (26 files, identity/eligibility/adapters/producers/publication/scheduler/roles/recovery/storage/migrations/repos) before the publication-policy commit: **277 passed, 8 subtests passed**.
- Ruff + `py_compile` clean on all changed Python files; `git diff --check` clean.
- `bash -n deploy/start.sh`: passed. `systemd-analyze verify`: structural syntax valid (warnings are Windows-permission / missing `/opt/runr` path only).
- Frontend: `npm ci` (722 pkgs), `npm run build` passed (1,148 modules), `npm test` 170/170 passed.

## C-owned shared implementation verified (item 2 of coordination)

- Exact cohort forwarding/selection: `materialize_source_input` raises if any requested `company_ids` is not eligible and never expands/reorders the cohort. The remaining head-slicing risk is in D/E collector files, not C.
- Scheduler recovery: `claim_due_cycle` reopens `partial`/`interrupted` cycles only when pending/retry tasks remain; `recover_dispatching_requests()` surfaces stuck dispatches before a fresh claim; lease expiry reclaims stale cycles. Covered by `test_phase_a_remediation.py`.
- Durable ownership: lease tokens + compare-and-swap head update + `StalePublicationHeadError` prevent duplicate acquisition and publication.
- Stable identity/field preservation: `publish_valid_snapshot` is idempotent by `cycle_id`, preserves prior-head jobs on partial cycles (`OR EXISTS ...`), and uses CAS head updates.
- Idempotent replay/partial-publication: verified (see above).
- Combined export: `build_master_jobs_catalog.py` requires per-source generation IDs (explicit flags or colocated `*_metrics.json`), atomic `os.replace`, header+row-count validation, and a `master_jobs_manifest.json` with generation IDs + SHA-256. Export failure returns exit 2 without corrupting the prior output (atomic temp + replace); the `Persistent=true` timer re-runs missed exports.

## Real master data paths (for E/F)

Authoritative inventory: `deploy/acquisition-data-manifest.json` (branch `deployment/render-turso-r2`, release commit `39d15b8f`).

Server roots (env override in `deploy/validate_acquisition_runtime.py`):
- inputs `/srv/runr/shared/inputs` → `RUNR_ACQUISITION_INPUT_ROOT`
- state `/srv/runr/state` → `RUNR_ACQUISITION_STATE_ROOT`
- exports `/srv/runr/exports` → `RUNR_ACQUISITION_EXPORT_ROOT`
- backups `/srv/runr/backups` → `RUNR_ACQUISITION_BACKUP_ROOT`

Seed inputs (committed in git, immutable SHA-256):
- `data/acquisition/inputs/company_master.csv` (9129 rows, 82 cols)
- `data/acquisition/inputs/company_registry_canonical.csv` (17601 rows, 42 cols) — F's audit input
- `data/acquisition/inputs/company_sources_linkedin_ids.csv` (17601 rows, 118 cols)

Restore-separately inputs:
- `/srv/runr/shared/inputs/SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json` (+ `.jsonl` raw sidecar)

State databases (not committed; restore-separately):
- LinkedIn 14-table: `/srv/runr/state/linkedin/master_linkedin_jobs_state.db` (~3.48 GB)
- Employer: `/srv/runr/state/employer/master_employer_jobs_state.db` (428 companies, 2612 jobs)

Exports:
- `/srv/runr/exports/linkedin/master_linkedin_jobs.csv` (+ `master_linkedin_jobs_metrics.json`)
- `/srv/runr/exports/employer/master_employer_jobs.csv` (+ `master_employer_jobs_metrics.json`)
- `/srv/runr/exports/combined/master_jobs.csv` (+ `master_jobs_manifest.json`)

## Completeness wiring findings (item 3 of coordination)

- E (source coverage) and F (job eligibility) have distinct purposes; both feed publication. A valid individual job may publish from a partial scan, but closing absent jobs requires trustworthy current-generation completeness — a historical last-success receipt cannot authorize closure after a newer failed scan.
- Eligibility should be computed on the VPS during ingestion/publication, not as full-catalog validation on Render; list pagination/counts and eligibility must stay consistent.
- F's unmeasured synthetic-data policy (`generate_completeness_sample.py`) must **not** be activated against production. The correct first step is to audit existing stored observations and measure the effect on valid publication. C has registered the opt-in `publication_policy_v2` flag but left the default v1 (report-only) in place.
- Required contract still pending F's finalization: `validate_job_for_publication(record, now=None, company_registry=None, source_records=None) -> result(publishable, status, reason_codes, to_dict())`, plus the `_published_jobs_sql()` `source_job_id` column addition documented in F's handoff.

## Exact missing interfaces / data / access (item 4)

- A's admin-removal changes: no commits yet → cannot integrate; does not block the C-owned items above.
- F's validator module is still changing → do not import it into the read path yet; the C-owned policy flag is in place.
- E's `RUNR_RELEASE_COMMIT`/`RUNR_SOURCE_VERSION` provenance requires adding one env var to the acquisition worker environment template (pending).
- Actual Turso staging verification: blocked on isolated Turso management credentials (management namespace/scope, not Hobby-plan assumption) — this prevents live scheduler/publication write verification, not offline integration.
- Retained-feature R2/CORS: pending external R2 administration — this prevents browser direct-download acceptance, not server-side object/HEAD/sign/range.
- Paid/live acquisition: remains stopped pending explicit authorization; no provider credits are used by any offline work.

## Remaining release sequence

1. D/E/F commit their corrected implementations; record descendant SHAs.
2. Integrate A/D/E/F descendant fixes into C normally (review shared-file hunks: `backend/api/server.py`, `sqlite_migrations.py`, `services.py`, `run_services.py`, `worker/service.py`, `render.yaml`, route registries).
3. Wire F's read-time gate (offline) against the finalized validator, audit existing records, then — only after measurement — promote `publication_policy_v2` explicitly if safe.
4. Add `RUNR_RELEASE_COMMIT`/`RUNR_SOURCE_VERSION` to the acquisition env; optionally `RUNR_LINKEDIN_PIPELINE`.
5. Focused integrated regression + customer frontend build; then final production merge/deploy (still deferred until corrected implementations land and authorization is given).
