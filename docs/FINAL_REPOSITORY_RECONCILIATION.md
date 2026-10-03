# Final repository reconciliation

Status: offline reconciliation recorded 2026-09-08. No deployment,
production migration, or live scraping was performed.

## Scope and starting state

The integration worktree was
`C:/Users/ahmed/Projects_Local/runr-admin-linkedin-preview` on
`deployment/render-turso-r2`, starting at `7251ae297c55f7f6a4524181cdafb4648f7fdcde`.
The original feature worktree was
`C:/Users/ahmed/Projects_Local/job-automation/Linkedin Jobs Scrapper` on
`feature/admin-analytics-final-production`, starting at
`0d7f2b5cca64a2c3fa0d5efcf0a357fb574b04c3`.

The feature worktree had an unfinished merge with `MERGE_HEAD`
`93099afc9bcadc4355d21bea9fde772f141e2859` and one unmerged path:
`frontend/src/pages/AdminAcquisitionPage.jsx`. It also had 27 staged paths.
The target had six untracked data artifacts and no merge state.

Before aborting the feature merge, recovery material was written under:
`C:/Users/ahmed/Projects_Local/runr-acquisition-snapshots/rc023-20260908/feature-worktree-recovery/`.
This includes staged, unstaged, and conflict patches, porcelain/name-status
inventories, all three conflict stages plus the working copy, and a complete
147-file `Jobs-Urls` preservation copy.

## Per-file feature-worktree reconciliation

The 28 staged/unmerged paths were compared to target HEAD. Twenty-one staged
paths were byte-identical to target content and required no transfer:

| Path | Class | Disposition |
| --- | --- | --- |
| `.dockerignore` | D | Already represented in target HEAD |
| `backend/acquisition/manifest.py` | D | Already represented in target HEAD |
| `backend/api/routes/acquisition_admin.py` | D | Already represented in target HEAD |
| `docs/admin_operations_console_parity.md` | D | Already represented in target HEAD |
| `frontend/e2e/admin-operations-console.spec.ts` | D | Already represented in target HEAD |
| `frontend/scripts/serve-production-e2e.mjs` | D | Already represented in target HEAD |
| `frontend/src/admin/adminOperations.css` | D | Already represented in target HEAD |
| `frontend/src/admin/AdminOperationsRouter.jsx` | D | Already represented in target HEAD |
| `frontend/src/admin/AdminPlatformPages.jsx` | D | Already represented in target HEAD |
| `frontend/src/admin/adminRoutes.js` | D | Already represented in target HEAD |
| `frontend/src/admin/adminRoutes.test.js` | D | Already represented in target HEAD |
| `frontend/src/App.jsx` | D | Already represented in target HEAD |
| `frontend/src/components/admin/AdminOperationsShell.jsx` | D | Already represented in target HEAD |
| `frontend/src/components/admin/AdminPrimitives.jsx` | D | Already represented in target HEAD |
| `frontend/src/context/SessionContext.jsx` | D | Already represented in target HEAD |
| `frontend/src/lib/acquisitionOperations.test.js` | D | Already represented in target HEAD |
| `frontend/src/pages/AcquisitionOperationsPage.jsx` | D | Already represented in target HEAD |
| `frontend/src/pages/AdminAcquisitionAnalyticsPage.jsx` | D | Already represented in target HEAD |
| `frontend/src/pages/AdminEventsPage.jsx` | D | Already represented in target HEAD |
| `frontend/src/pages/AdminPage.jsx` | D | Already represented in target HEAD |
| `frontend/src/pages/AdminScrapeOpsPage.jsx` | D | Already represented in target HEAD |

The remaining seven paths were reviewed individually:

| Path | Class | Disposition |
| --- | --- | --- |
| `backend/repositories/sqlite_acquisition.py` | D | Feature side removes RC-016/017 lease fencing, retry, heartbeat, and recovery behavior. Target contains the newer implementation; not transferred. |
| `RELEASE_LEDGER.md` | D | Feature side removes the RC-022 release contract. Target version is newer and retained. |
| `render.yaml` | D | Feature side reverts separate API/worker Dockerfiles, build filters, and release variables. Target RC-022 configuration is retained. |
| `frontend/src/adminInspectorV3.css` | D | Deletion already matches target HEAD. |
| `frontend/src/components/acquisition/AcquisitionShell.jsx` | D | Deletion already matches target HEAD. |
| `frontend/src/pages/AdminJobImportPage.jsx` | D | Deletion already matches target HEAD. |
| `frontend/src/pages/AdminAcquisitionPage.jsx` | D | Conflict resolved by retaining target HEAD. The feature-side `AcquisitionShell` version and the merge-side reduced version were older/incompatible with the current admin router and target's LinkedIn-enrichment view. |

No feature-worktree code required transfer. The merge was aborted only after
the recovery bundle and comparison were complete.

## External data disposition

The six target-worktree artifacts were moved to
`C:/Users/ahmed/Projects_Local/runr-acquisition-snapshots/rc023-20260908/external-artifacts/`
with matching hashes before and after the move:

| File | Bytes | SHA-256 | Class |
| --- | ---: | --- | --- |
| `RC004_BACKFILL_REPORT.json` | 28,554,398 | `720179efd9eea4eed75a36792e840fb2b506b6473d4bdb16d7ba195db9c517c4` | G: review-gated proposed mappings |
| `SOURCE_ELIGIBILITY_MANIFEST_RC005.json` | 43,035,396 | `a45239d6c713b4142fe6faadd3b770b3fdbe32c705f85670d5e3620f215cc59d` | G: historical non-reconciled generation |
| `SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json` | 43,035,445 | `72b61f100a0d9edbba315b5f19db589f40cfecd42c19ce3ef95b78b331621873` | G: external immutable input |
| `SOURCE_ELIGIBILITY_RAW_RC005.jsonl` | 63,665,149 | `cda46fee441e2e6e02d52ffe2fc86ae33121c82edc9f0636562367b63cbb5ef7` | G: historical raw sidecar |
| `SOURCE_ELIGIBILITY_RAW_RC005_RECONCILED.jsonl` | 63,665,149 | `cda46fee441e2e6e02d52ffe2fc86ae33121c82edc9f0636562367b63cbb5ef7` | G: external immutable sidecar |
| `ss\uF01B\uF01B` | 1,772 | `e6cf8902dca9beb1ae3cc7a1c4f612f8f9a3a333aa3d6656444731a378208c3a` | H: unknown quarantined material |

The original worktree's ignored `Jobs-Urls` directory was copied and hashed
before removal from the repository worktree: 147 files, 9,611,859,565 bytes,
zero mismatches. The verified copy is under
`feature-worktree-recovery/jobs-urls-preserved/Jobs-Urls/`; the moved source
quarantine is retained under `feature-worktree-recovery/jobs-urls-source-quarantine/`.
The complete hash inventory is `jobs-urls-preserved-verification.csv`.

The authoritative LinkedIn, employer, resolver, legacy, and export hashes are
also recorded in `docs/ACQUISITION_RUNTIME_DATA_INVENTORY.md` and
`deploy/acquisition-data-manifest.json`. No mutable database, WAL/SHM file,
credential, cookie, token, or authenticated proxy value was committed.

Committed `Company-Urls` files in the original branch were not current dirty
changes and were not deleted. The reviewed canonical seed inputs already live
under `data/acquisition/inputs/` on the deployment branch.

## Merge and cleanup result

`git merge --abort` restored the original feature worktree to its own HEAD
`0d7f2b5cca64a2c3fa0d5efcf0a357fb574b04c3`. The target branch was not merged
with the feature branch. Both worktrees now have no staged, unstaged, or
unmerged paths; ignored generated build/dependency directories remain governed
by `.gitignore` and are not source deliverables.

The deployment branch retains the two prior commits:

- `39d15b8f3da9870b03102525ed03431194edaad6` — `RC-022 separate release and runtime contracts`
- `7251ae297c55f7f6a4524181cdafb4648f7fdcde` — `feat(acquisition): reconcile producers inputs and runtime data`

## Final integration correction

The exact CI-equivalent non-API shard exposed one real target-branch defect in
the libSQL projection batching path: the accumulator iterated `stale_ignored`
without initializing it. The fix initializes that counter and adds the focused
assertion in `tests/test_product_completion_wave.py`. The complete rerun passed
`1497` tests, `78` subtests, with five deprecation warnings.

The complete API shard passed `123` tests and retained exactly the two known
baseline failures: `BackendApiTests.test_tracker_api` and
`BackendApiTests.test_tracker_ats_detail_returns_persisted_read_only_diagnostics`.

The first GitHub Actions run on the reconciled commit also exposed one
Linux-only portability defect that the required Windows 3.12.7 run could not
exercise: `tests/test_acquisition_runtime_manifest.py::test_historical_absolute_sidecar_path_can_be_restored_next_to_manifest`
could not recognize a recorded Windows drive-qualified sidecar path on POSIX.
The loader now recognizes both host-native and Windows absolute paths before
falling back to a colocated restored sidecar. The focused manifest file passes
locally, and the follow-up GitHub Actions verification is recorded in the
final handoff.

The final cleanup documentation and focused CI corrections are committed after
the two release commits above.
