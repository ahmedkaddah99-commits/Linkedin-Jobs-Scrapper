> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Known gaps registry (carry-forward)

Secondary doc for WS-11. Primary: [repository-artifacts.md](repository-artifacts.md). Related: [retired-features.md](retired-features.md).

This file only records items that are already known. It does **not** add new product-gap analysis. It combines three sources:

- the canonical contradiction and unknown list, `evidence-package-2026-09-13/contradictions-and-unknowns.md` (C1–C9, U1–U13);
- the errata in `phase-1-delta-audit-2026-09-13.md` (N-1…N-12), which override the evidence package where the two conflict;
- the active clean-slate tickets in `clean-slate-2026-09-13/linear-ticket-candidates.md` (T01, T03, T04, T05, T06, T08, T10, T11, T12, T14).

Both evidence files live outside the repository, under `C:\Users\ahmed\Projects_Local\RUNR_REVERSE_ENGINEERING_2026-09-10\`.

**Phase 3 merge rule:** each Phase 2 doc adds its own local gaps with IDs like `WS<n>-G<k>` in its section 10. This registry does not copy them. Phase 3 (WS-12 synthesis) merges them here, keyed by ID. The target doc paths below follow `recommended-documentation-tree.md`, all relative to `docs/reverse-engineering/`.

LIVE PRODUCTION = UNKNOWN. Production SHAs below come from documents only.

## 1. Confirmed contradictions (C1–C10)

| ID | Contradiction (errata applied) | Evidence at baseline | Owner WS | Target Phase-2 doc | Status |
|---|---|---|---|---|---|
| C1 | `RELEASE_LEDGER.md` names `3c5e609a` as the last live deployment. The handoff records Render on `5dfdd106`. | Ledger L245 "Wave 3 deployment hold", L252–253; unchanged since `848408f3`. Handoff `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` L8–20. | WS-7 | `02-deployment/release-process-and-production-records.md` | OPEN |
| C2 | Three different VPS release SHAs are recorded. | Handoff L12 says `5dfdd106`. `deploy/vps-runtime-contract.json` L6 says `9ba1d551`. The untracked 2026-09-12 completion report L7–8 says `4a1b1df5`. | WS-7 | `02-deployment/release-process-and-production-records.md` | OPEN |
| C3 | The release migration head is `058_customer_task_queue`, but the registry head is `060_publication_latest_observation_index`. No gate compares them. | `render.yaml` L76–77 and L193–194; `backend/deployment/release_contract.py:14` (default) and `:136` (read); `backend/repositories/sqlite_migrations.py:3533`, `:3543` | WS-5 / WS-7 | `03-data/schema-and-migrations.md`; `02-deployment/release-process-and-production-records.md` | OPEN |
| C4 | The handoff says the live-network flag was reset to false after the pilot, but the linkedin and employer units hard-set it to true. | Handoff L31; `deploy/acquisition.env.example`; `deploy/systemd/runr-acquisition-linkedin.service` and `runr-acquisition-employer.service` set `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED=true` (`c85f7275`) | WS-7 / WS-3 | `02-deployment/vps-runtime-and-acquisition-timers.md` | OPEN |
| C5 | Which component owns unattended acquisition is unclear. The handoff names the cycle timer, but `runr.target` wants the linkedin, employer and publisher timers and not the cycle timer. The cycle and LinkedIn timers both fire at 02:00. Enabled timers on the host: UNKNOWN. | Handoff L27–28; `deploy/systemd/runr.target`; `deploy/vps-runtime-contract.json` | WS-7 | `02-deployment/vps-runtime-and-acquisition-timers.md` | OPEN |
| C6 | The handoff says the acquisition worker service is disabled, but the VPS contract still names that unit. | Handoff L29; `deploy/vps-runtime-contract.json` `roles.acquisition.unit`; `deploy/systemd/runr-acquisition-worker.service` sets `RUNR_ACQUISITION_SCHEDULER_DISABLED=true` | WS-7 / WS-2 | `02-deployment/vps-runtime-and-acquisition-timers.md`; `01-architecture/backend-workers-and-orchestration.md` | OPEN |
| C7 | Admin retirement residue remains after `dd47acf9`. Rewritten by N-1: (a) `backend/api/routes/admin.py` still holds **unregistered** bodies for `dashboard` L102, `users` L113/127/132, `tokens` L154, `secrets` L177/196 and `analytics/events` L239, and `backend/api/server.py` `_dashboard_payload` L7358 → `_dashboard_analytics_payload` L7143 is reachable only from the dead `admin.py:105`; (b) `frontend/e2e/admin-operations-console.spec.ts` targets deleted `/admin/acquisition/*` routes; (c) migration `055_acquisition_analytics_indexes` must stay because migrations are append-only; (d) `backend/config/scrapeops_admin_policy.py` is imported by `backend/application/services.py:29–32` and used at L685–700 and L1724; (e) the admin-dashboard docs; (f, added by N-1) the frontend emitters in `frontend/src/lib/analytics.js:125` and `frontend/src/lib/api.js:267` POST to the missing endpoint and swallow the errors. See [retired-features.md](retired-features.md) §4. | `admin.py` `register_routes` L23–33; `tests/test_customer_route_surface.py` L9–13 | (a) WS-1 · (b)(f) WS-8 · (c)(d) WS-5 · (e) WS-11 | `01-architecture/backend-api.md`; `01-architecture/frontend-app.md`; `03-data/schema-and-migrations.md`; `06-history-and-provenance/retired-features.md` | OPEN (residue; (c) retained by design) |
| C8 | The local `deployment/render-turso-r2` ref is stale. | Local `c25d394a` is 0 ahead / 42 behind origin. The worktree deletion of the handoff doc was not reproduced (N-12, excluded worktree). | Owner git hygiene (WS-7 via T12) | `06-history-and-provenance/branch-divergence.md` (WS-12) | OPEN → T12 |
| C9 | The VPS contract still has purchase and region placeholders even though a VPS deployment is recorded. | `deploy/vps-runtime-contract.json` L12 and L29 | WS-7 | `02-deployment/vps-runtime-and-acquisition-timers.md` | OPEN |
| **C10** (new, from N-5) | (i) `runr-acquisition-export.service` has `Wants=` and `After=runr-acquisition-cycle.service`, so the 06:00 export timer can pull in the combined oneshot cycle outside `runr.target`. (ii) The handoff caps (12 total / 6 / 6) differ from the source defaults (110/100/10). A host override is UNKNOWN. | `deploy/systemd/runr-acquisition-export.service` L3–4 (Wants/After, re-checked at baseline); handoff L32; `deploy/acquisition.env.example`; `deploy/run-acquisition-cycle.sh` L6–8 | WS-7 (WS-3 for caps semantics) | `02-deployment/vps-runtime-and-acquisition-timers.md` | OPEN |

## 2. Unknowns (U1–U13)

| ID | Unknown (errata applied) | Would resolve it | Owner WS | Target Phase-2 doc | Status |
|---|---|---|---|---|---|
| U1 | Which revision Render is actually running. The handoff says `5dfdd106` (2026-09-11), but 44 commits have landed since and `autoDeployTrigger: commit` could have redeployed. | Render deploy list or the release-metadata endpoint | WS-7 | `02-deployment/render.md` | OPEN |
| U2 | Which revision the VPS is running, and which timers and services are enabled | `systemctl list-timers`; the `/opt/runr` git revision on the host | WS-7 | `02-deployment/vps-runtime-and-acquisition-timers.md` | OPEN |
| U3 | Which branch Render is bound to | Render dashboard setting | WS-7 | `02-deployment/render.md` | OPEN |
| U4 | Whether to merge `temp/runr-employer-final` `6ea7f460`. `git cherry` gives `+`, so the patch is absent from the baseline. | Owner decision → **T01** | WS-3 | `05-subsystems/acquisition-and-collectors.md` | OPEN → T01 |
| U5 | Plan for the 16 commits on `feature/admin-analytics-final-production` (CV editor and performance, catalog docs, the `Company-Urls/` dataset, extension changes) | Owner decision → T03/T04/T05 (T02 closed: dataset archived) | WS-12 (records); WS-9/WS-3/WS-11 per ticket | `06-history-and-provenance/branch-divergence.md` | OPEN → T03, T04, T05 |
| U6 | **Narrowed by N-7.** `temp/opencode-b-collectors` is resolved: `git cherry 58a96674` gives `+ 66b61445`, 1 ahead / 74 behind, **UNMERGED, docs-only**. The commit adds only `docs/OPENCODE_B_HANDOFF.md` (80 lines, absent at baseline). Still unchecked: the `codex/*`, `recovery/*` and `phase-*` branches against the baseline. | `git cherry 58a96674 <ref>` per branch | WS-12 | `06-history-and-provenance/branch-divergence.md` | PARTIAL |
| U7 | **Rewritten by N-1.** `POST /analytics/events` and the old `GET /dashboard` API are **dead** at baseline and return 404: `admin.py:239` and `:102` bodies are not registered, and `server.py` `do_POST` dispatches only through `route_registry.dispatch`. The frontend still posts events to the 404 (`lib/analytics.js:125`, `lib/api.js:267`) and swallows the errors. `analytics_events` is still written only by worker-side `backend/adapters/stage_adapters.py:143–161` (run events and ScrapeOps usage) through `analytics_store.emit_event`. **Open question:** delete the dead endpoint bodies and the frontend emitter, or re-register the endpoint? | Owner decision | WS-1 (handler), WS-8 (emitter), WS-5 (table/055), WS-2 (worker writer) | `01-architecture/backend-api.md`; `01-architecture/frontend-app.md`; `03-data/schema-and-migrations.md` | OPEN (decision) |
| U8 | **Narrowed by N-9 to host-only.** Source has no reverse-proxy config: `git grep -il "nginx\|caddy" 58a96674` hits only the 3 `data/acquisition/inputs/*.csv` (false positives). The VPS API binds `127.0.0.1` with `inbound_ports: []`. Whether the host has a proxy remains UNKNOWN. | Host inspection | WS-7 | `02-deployment/vps-runtime-and-acquisition-timers.md` | OPEN (host-only) |
| U9 | Whether PM2 (`ecosystem.config.cjs`) is used anywhere | Host inspection | WS-7 | `02-deployment/vps-runtime-and-acquisition-timers.md` | OPEN |
| U10 | Authenticated `/jobs` API payloads were not visually verified (handoff L78). | Signed-in browser check | WS-8 / WS-4 | `01-architecture/frontend-app.md` | OPEN |
| U11 | Full backend suite result at the baseline. The handoff ran focused selections only. | `npm run check:backend:full` (not run in Phase 2) | WS-10 | `04-testing/test-suite-map.md` | OPEN |
| U12 | **Closed by N-9: no Redis or broker.** `git grep -il redis 58a96674 -- backend scripts deploy` gives 3 files, all false positives (`PreparationFeatureDisabledError`). | — | WS-5 / WS-2 (record only) | `01-architecture/backend-workers-and-orchestration.md` | CLOSED |
| U13 | Internal call graph of the VPS wrappers `deploy/run-acquisition-source.sh`, `deploy/run-acquisition-publisher.sh`, `deploy/run-acquisition-cycle.sh` into `scripts/` | Full read of the wrappers | WS-7 / WS-3 | `02-deployment/vps-runtime-and-acquisition-timers.md`; `05-subsystems/acquisition-and-collectors.md` | OPEN |

## 3. Old-package items without a disposition (N-8)

| Item | Disposition | Owner |
|---|---|---|
| `origin/codex/revert-referral-redesign` | HISTORICAL: an ancestor, 0 ahead / 177 behind. Resolved. | WS-12 (record) |
| `origin/feature/admin-operations-console` | HISTORICAL retired admin work: an ancestor, 0 ahead / 243 behind. Resolved; not to be restored. | WS-12 (record) |
| Duplicate-subject commits `af94ef4c` / `2a42c332` "feat: add branded social links to CVs" | Both are ancestors of the baseline; their contents were not diffed. LOW unknown. | WS-12 |
| `848408f3` "docs: record acquisition repairs and provider spending stop" | Whether the provider spending stop is still in force is UNKNOWN. LOW. | WS-7 / WS-3 |
| Old U11 `run_daily.ps1` root scripts | The old root scripts are absent. `run_daily.ps1` itself is still tracked and owned by WS-7. Moot for this registry. | WS-7 |

Other errata relevant here: N-2 (ownership wording fix, applied), N-3 (`data/acquisition/inputs/*.csv` are inputs, WS-3), N-4 (full `dd47acf9` deletion list, see [retired-features.md](retired-features.md) §3), N-6 (numeric corrections: env_schema 48 keys, 7 CREEM product IDs, `server.py` −648), N-10 (`admin.scrapeops` is a customer usage prefix), N-11 (`assisted-apply.md` ownership note, WS-9), N-12 (C8 above).

## 4. Active clean-slate tickets

None of these tickets has been created in Linear (no connector). The text is ready in `linear-ticket-candidates.md`.

| Ticket | Title | Owner WS | Depends on | Risk | Related IDs | Target Phase-2 doc |
|---|---|---|---|---|---|---|
| T01 | Review the employer-producer scheduling and browser-reuse patch `6ea7f460` (`temp/runr-employer-final`) | WS-3 (tests WS-10) | — | Medium | U4 | `05-subsystems/acquisition-and-collectors.md` |
| T03 | Review the assisted-apply panel and generic ATS planner work from `0d7f2b5c` (48 paths; never-submit boundary) | WS-9 (route WS-1; docs WS-11) | — | High | U5 | `05-subsystems/assisted-apply.md` |
| T04 | Review the enrichment and LinkedIn transport scripts from `0d7f2b5c` (18 paths, including requirements) | WS-3 (tests WS-10; requirements WS-7) | — | Medium | U5 | `05-subsystems/company-identity-enrichment-and-logos.md` |
| T05 | Commit the master LinkedIn jobs catalog design docs, the master jobs acquisition docs and the `.worktrees/` ignore rule | WS-11 | — | Low | U5 | `06-history-and-provenance/repository-artifacts.md` |
| T06 | Commit the 2026-09-11/12 production and scraper reports to `docs/reports/` (3 files, byte-identical) | WS-11 (content cited by WS-3/7/8) | — | Low | C2, U1, U2 | `06-history-and-provenance/repository-artifacts.md` |
| T08 | Create an encrypted vault for sensitive local data and make off-machine copies | WS-5 (security WS-6) | — | High | — | `03-data/acquisition-source-state.md`; `01-architecture/security-and-auth.md` |
| T10 | Privacy review of the customer personal branches `Bodda`, `Helbo`, `Mohamed-Bahy` | WS-11 / owner (security advice WS-6) | — | High | — | `06-history-and-provenance/repository-artifacts.md` (locations only) |
| T11 | Fix the default Runr root in the untracked `scripts/audit_runr_data_readiness.py` (it points at the stale worktree) | WS-3 | — | Low | C8 | `05-subsystems/acquisition-and-collectors.md` |
| T12 | Retire the stale `runr-admin-linkedin-preview` worktree and fast-forward the local ref | WS-7 / owner git hygiene | T11, T08 | Low | C8 | `02-deployment/release-process-and-production-records.md` |
| T14 | Retire the 17 retained checkouts once their blocking tickets close | Owner git hygiene (recorded by WS-12) | T01, T03, T04, T05, T06, T08, T10, T12 | Medium | U5, U6 | `06-history-and-provenance/branch-divergence.md` |

Closed without a ticket (do not re-open): T02 (datasets archived), T07 (archive built), T09 (env files never committed), T13 (stashes exported and dropped), T15 (`.codex/tmp` frames hash-recorded and removed).

## 5. Resolved (do not re-open)

These are carried over from the canonical list §3: two lines of development (superseded); admin-analytics page path (moot, deleted in `dd47acf9`); `Company-Urls/` exists only in `0d7f2b5c` on the unmerged branch; `backend/worker/roles.py` has exactly `customer` and `acquisition`; connectors import acquisition, not the reverse; the broken germany test is not on the baseline; the VPS contract commit placeholder is filled (see C2); `39d15b8f` is an ancestor; `@runr/ats-core` is consumed by the extension. Added by the errata: U12 (no Redis); U6 for `temp/opencode-b-collectors`; the N-8 origin refs.

## Agent context and remaining work

**(a) Context packet.**
- **Required reading:** this file; `contradictions-and-unknowns.md`; `phase-1-delta-audit-2026-09-13.md` §3; `linear-ticket-candidates.md`.
- **Allowed paths:** this file only.
- **Tests:** none; verify with `git grep`/`git show 58a96674:<path>` at the cited lines.
- **Prohibited:** adding product analysis; resolving items by editing code; creating Linear tickets.

**(b) Registry row.** See the primary doc: `WS-11 | Docs corpus and repository artifacts | … | 06-history-and-provenance/repository-artifacts.md`.

**(c) Candidates.** None new. Phase 3 must merge the `WS<n>-G<k>` gaps from every Phase 2 doc into this registry and re-validate each OPEN row against the then-current SHA.
