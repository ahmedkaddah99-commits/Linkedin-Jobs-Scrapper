> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Repository artifacts: documentation corpus, root reports and non-code assets

Primary doc for WS-11 (Docs corpus and repository artifacts, classification only). Secondary docs: [retired-features.md](retired-features.md) (admin analytics dashboard retirement), [known-gaps.md](known-gaps.md) (registry of C#/U#/T# items).

WS-11 does not author product documentation. This doc classifies every owned tracked path so later workstreams and Phase 3 know what is authoritative, what is history, and what is safe to ignore. Classification is judged from headers/first lines/dates and spot-checks against code at the cited lines; most files were not read in full. No file listed here was edited, moved or deleted.

## 1. Purpose and user-facing capabilities

None directly — WS-11 documents artifacts, it is not a product subsystem. The classified corpus supports every other workstream: `docs/**` (129 files) is the project's accumulated specs, handoffs, PRDs, architecture notes and reports; root `*.md`/`*.json` reports are point-in-time RC/production evidence; `test CV/`, `test-CV/`, `screenshots/`, `user_config/` are generated or local fixture/asset directories; `.agents/`, `.cline/`, `.codex/` are duplicated agent-skill directories for three different coding-agent tools; `AGENTS.md` governs how agents run Python in this repo.

## 2. Owned paths (exact, with file counts) and governing instructions

| Path group | Count at `58a96674` | Notes |
|---|---|---|
| `docs/**` | 129 | Except `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` (WS-7) |
| Root report `*.md` | 24 | `ACQUISITION_REPAIR_REPORT.md` … `SOURCE_ELIGIBILITY_MANIFEST.md`, `README.md`, `AGENTS.md`, `REMAINING_APP_ISSUES.md`. Excludes `RELEASE_LEDGER.md` (WS-7). |
| Root report `*.json` | 6 | `BASELINE_METRICS.json`, `COMPANY_REGISTRY_RECONCILIATION.json`, `CURRENT_DATA_PIPELINE_MAP.json`, `RC006_RESOLUTION_SAFETY.json`, `RC007_EXPORT_SEPARATION.json`, `RC008_PRODUCER_ADAPTERS.json`. Excludes `package.json`/`package-lock.json` (WS-7, audit correction N-2). |
| `test CV/**` | 240 | Generated CV-rendering samples (space in directory name) |
| `test-CV/**` | 224 | Overlapping but non-identical generated samples (hyphen) |
| `screenshots/**` | 9 | Feature/e2e screenshots (PNG) |
| `user_config/**` (tracked only) | 3 | 1 empty text file, 2 logo images. Most of `user_config/` is gitignored (personal data, T10/T08). |
| `.agents/**` | 38 | Claude/generic agent skills source |
| `.cline/**` | 39 | Synced copy for Cline |
| `.codex/**` | 40 | Synced copy for Codex, plus 2 extra files |
| `image.png` | 1 | Root-level duplicate of a screenshot |
| `.backend_api_stderr.log` | 1 | Stray local log, 2,650 bytes |
| `.backend_api_stdout.log` | 1 | Stray local log, empty |
| `.gitignore` | 1 | 1,600 bytes |
| `.gitattributes` | 1 | 384 bytes |

**Governing instructions — `AGENTS.md`** (25 lines, added `bdd6b970` 2026-07-19, unchanged since): mandates that every Python command in this repository use `.venv\Scripts\python.exe` (never the global interpreter/pip), specifies Python **3.12.7**, and says to stop and report if the venv is missing or the wrong version rather than falling back to a global interpreter. This governs every workstream's "safe verification commands" — none in Phase 2 were executed, but any future run must follow this rule. Classification: **CURRENT-AUTHORITATIVE**.

**Other governing docs relevant to this corpus (owned by WS-11, content authored elsewhere):**
- `docs/architecture/source_control_artifact_policy.md` (171 lines, "Status: accepted for cleanup planning", 2026-05-31) recommends untracking `test CV/`, `test-CV/` (unless converted to a maintained fixture package) and the `user_config/` personal files, and lists exact `git rm --cached` commands (L156–161). **Verified against the current `.gitignore`:** `test CV/` and `test-CV/` are gitignored (`.gitignore:75–76`) but both directories are still tracked at `58a96674` — the ignore rule only stops *new* untracked files, it does not untrack the 464 files already committed. This is a live discrepancy between policy and repo state (see §9).
- `docs/agent-skills.md` (41 lines) documents the `.agents/skills/` → `.cline/skills/` and `.codex/skills/` sync scheme, explaining the duplication as a workaround for `core.symlinks=false` on Windows. **Verified:** `scripts/sync-agent-skills.sh` and `scripts/sync-agent-skills.ps1` exist and implement exactly this (source→destination copy with kebab-case validation).

## 3. Entry points and registered routes/commands/units

Not applicable — WS-11 owns no executable code. The only "commands" touching these paths are `scripts/sync-agent-skills.{sh,ps1}` (owned by WS-3's `scripts/**` allocation, referenced here because they operate on `.agents/`/`.cline/`/`.codex/`) and `backend/tools/build_test_cv_bundle.py` / `build_test_cv_web_templates.py` (WS-4's `backend/tools/**`), which generate `test CV/` content (`build_test_cv_bundle.py:32` sets `OUTPUT_DIR = ROOT / "test CV"`).

## 4. Inputs, outputs, storage and dependencies

- `test CV/` and `test-CV/` are **outputs** of `backend/tools/build_test_cv_bundle.py` (WS-4), not inputs to any pipeline.
- `screenshots/` is written to by three frontend e2e specs (WS-8): `frontend/e2e/admin-operations-console.spec.ts:111` (stale, targets the retired admin console — see [retired-features.md](retired-features.md)), `frontend/e2e/phase-d-jobs-cutover.spec.ts:97`, `frontend/e2e/phase-e-job-intelligence.spec.ts:54`.
- `user_config/discovered_regular_company_career_sites.txt`, `github_logo.jpg`, `linkedin_logo.png` are read by document-generation code (WS-4's `backend/capabilities/tailored_documents/documents.py`), which resolves logo paths via config keys (`documents.py:515–528`) rather than hardcoding these filenames — so whether these exact tracked files are the ones actually used depends on `user_config` config values (UNKNOWN without running the app).
- `docs/legal/RUNR_TERMS_AND_CONDITIONS.md` and `RUNR_USER_AGREEMENT.md` are imported directly by the frontend at build time: `frontend/src/pages/MarketingSite.jsx:3-4` (`import termsMarkdown from "../../../docs/legal/RUNR_TERMS_AND_CONDITIONS.md?raw"`). This is the one `docs/**` file with a live code dependency.
- `backend/acquisition/employer_coverage.py:8` and `scripts/audit_real_job_data.py:8` reference `docs/OPENCODE_E_EMPLOYER_COMPLETENESS_HANDOFF.md` and `docs/ACQUISITION_RUNTIME_DATA_INVENTORY.md` in code comments as the correctness/dataset-authority contract — these two HISTORICAL-dated docs are still cited as living contracts by WS-3 code. Flagged for WS-3 to confirm currency.
- `.dockerignore` (WS-7-owned file, read here only for context) excludes `docs/*` from the Docker build except `docs/legal/` (`.dockerignore:29-31`) and excludes `.codex` (`:3`) — confirming these doc/skill directories are dev-only, not shipped.

## 5. Important call/data flows

- **Skill sync flow:** `.agents/skills/<name>/SKILL.md` is authored once, then `scripts/sync-agent-skills.sh|.ps1` copies each skill directory into `.cline/skills/` and `.codex/skills/` (kebab-case name validation, both source and destination must be inside the repo). `docs/agent-skills.md` documents this as intentional, not accidental drift.
- **Test-CV generation flow:** `backend/tools/build_test_cv_bundle.py` (role/tailored CV renders) and `build_test_cv_web_templates.py` (`04_web_inspired_templates`) write into `test CV/`; nothing writes into `test-CV/` at the baseline (no code reference to the hyphenated path was found — its generator, if any, is not in the current tree).
- **Root-report flow:** every root `RC0NN_*`/`BASELINE_*`/`COMPANY_REGISTRY_*`/`ACQUISITION_*` doc pair (`.md` + matching `.json`) is a one-time offline evidence snapshot from the 2026-09-06…09-08 "RC-00N" ticket sequence; none is regenerated by code at the baseline (no script writes to these root paths — they are historical artifacts committed directly).

## 6. Invariants, failure handling and recovery

- **Invariant (policy, not enforced by tooling):** `docs/architecture/source_control_artifact_policy.md` states real CVs, profile photos and candidate documents must never be committed. At `58a96674`, `test CV/`/`test-CV/` contain **generated** samples (role-based and tailored CVs built from fixture/template data), not real customer CVs — this is consistent with the policy's carve-out, but the directories remain tracked against the policy's own recommendation to untrack them (§9 gap).
- **No personal data was read or copied into this doc.** Per the brief's rule (T10), `user_config/`'s three tracked files were checked by name and byte size only; their content was not opened beyond confirming the `.txt` file is empty (0 lines) and the two image files are ordinary logo assets (89,230 and 69,440 bytes).
- **Duplication invariant:** `.agents/`, `.cline/`, `.codex/` are supposed to be byte-identical per-skill (see §9 verification). A divergence found in one file (`skills/production-debug/scripts/check_production_access.py`) is a real drift, not a hash-tool artifact — `.codex`'s copy has an extra template-literal filter that `.agents`/`.cline` lack.

## 7. Relevant tests and safe verification commands (not executed in Phase 2)

No test suite covers these paths (WS-10's `tests/**` has no test targeting `docs/**`, `test CV/`, `screenshots/`, or the skill directories). Verification is git-only:

```bash
git cat-file -e 58a96674:<path>                       # confirm a path exists at baseline
git ls-tree -r --name-only 58a96674 -- docs | wc -l    # recount docs/** (expect 129)
git diff --no-index <(git show 58a96674:.agents/skills/X/SKILL.md) <(git show 58a96674:.cline/skills/X/SKILL.md)
git show 58a96674:AGENTS.md
```

## 8. Historical decisions and supporting commits

`git log --oneline 58a96674 -- docs | wc -l` = 148 commits touching `docs/**`. Notable:
- `dd47acf9` 2026-09-10 "Complete acquisition delivery and remove admin surfaces" — no `docs/**` file was deleted by this commit (verified: `git show --stat --format= dd47acf9 -- docs` is empty); the admin-dashboard docs survive as HISTORICAL residue (§9, and [retired-features.md](retired-features.md) §6).
- `7251ae29` 2026-09-08 "feat(acquisition): reconcile producers inputs and runtime data" — added most of the root `RC00N`/`BASELINE`/`COMPANY_REGISTRY`/`SOURCE_ELIGIBILITY` report pairs in one commit.
- `bdd6b970` 2026-07-19 "gitignore update" — last touch to `.gitignore` before baseline; also added `AGENTS.md` the same day.
- `c7bf7cbd` 2026-06-18 "deoployment prep initial setup" [sic] — added most of `docs/architecture/`, `docs/deployment/`, `docs/prd/README.md`, `docs/reports/` (21 reports).
- `92123ba9` 2026-04-19 "Full refactor and retirement of legacy codebase…" — earliest ancestor commit touching `.codex/`.

## 9. Current implementation status

### 9.1 `docs/**` classification table (129 files)

Columns: classification is one of CURRENT-AUTHORITATIVE / CURRENT-PARTIAL / HISTORICAL / RETIRED-RESIDUE / UNKNOWN. WS = subject workstream (documentation content, not WS-11 itself, which merely classifies).

**Root of `docs/` (51 files)**

| Path | Date/status line | Classification | WS |
|---|---|---|---|
| `ACQUISITION_EDITED_FIELDS_AND_OVERRIDES.md` | 2026-09-10, no explicit status | CURRENT-AUTHORITATIVE | WS-3 |
| `ACQUISITION_RUNTIME_DATA_INVENTORY.md` | "reconciliation recorded 2026-09-08, amended" | HISTORICAL | WS-3 |
| `FINAL_REPOSITORY_RECONCILIATION.md` | "offline reconciliation recorded 2026-09-08" | HISTORICAL | WS-3 |
| `JOB_PUBLICATION_COMPLETENESS_CONTRACT.md` | "Implemented, un-wired…Base SHA 848408f3" | CURRENT-PARTIAL — code (`backend/acquisition/job_publication_completeness.py`, `producer_adapters.py`, `personalized_jobs_service.py`) exists at baseline; whether it is now wired needs WS-3 confirmation | WS-3 |
| `OPENCODE_C_HANDOFF.md` | 2026-09-10 | HISTORICAL | WS-3 |
| `OPENCODE_D_LINKEDIN_PERFORMANCE_HANDOFF.md` | 2026-09-10 | HISTORICAL | WS-3 |
| `OPENCODE_E_EMPLOYER_COMPLETENESS_HANDOFF.md` | 2026-09-10 | HISTORICAL | WS-3 |
| `OPENCODE_E_EMPLOYER_COVERAGE_REAL_REPORT.json` | 2026-09-10 | HISTORICAL | WS-3 |
| `OPENCODE_E_EMPLOYER_COVERAGE_REPORT.json` | 2026-09-10 | HISTORICAL | WS-3 |
| `OPENCODE_F_JOB_COMPLETENESS_HANDOFF.md` | 2026-09-10 (mentions the deleted admin dashboard, L164) | HISTORICAL | WS-3 |
| `PERSONALIZED_JOBS_PREVIEW.md` | 2026-08-04, frontend-only flag | CURRENT-PARTIAL — flag `VITE_PERSONALIZED_JOBS_EXPERIENCE` still referenced in `frontend/src/lib/personalizedJobs.js` | WS-4/WS-8 |
| `RC009_NORMALIZATION_PUBLICATION.json` | "COMPLETE — offline evidence only" | HISTORICAL | WS-3 |
| `RC009_NORMALIZATION_PUBLICATION.md` | same | HISTORICAL | WS-3 |
| `RC010_FIRST_ACQUISITION_SLICE.md` | "complete locally 2026-09-08" | HISTORICAL | WS-3 |
| `RC011_EMPLOYER_COVERAGE.md` | same | HISTORICAL | WS-3 |
| `RC012_EMPLOYER_CONCURRENCY.md` | same | HISTORICAL | WS-3 |
| `RC013_LINKEDIN_LIFECYCLE.md` | same | HISTORICAL | WS-3 |
| `RC014_LINKEDIN_INCREMENTAL_REFRESH.md` | same | HISTORICAL | WS-3 |
| `RC015_LINKEDIN_TRANSPORT_STORAGE.md` | same | HISTORICAL | WS-3 |
| `RC018_WORKER_ROLES.md` | no date; describes `customer`/`acquisition` roles | CURRENT-AUTHORITATIVE — verified: `backend/worker/roles.py` has exactly those two roles (confirmed resolved item in known-gaps §5) | WS-2 |
| `RC019_INTELLIGENCE_RECOVERY.md` | "complete locally 2026-09-08" | HISTORICAL | WS-4 |
| `RC020_CUSTOMER_TASK_QUEUE.md` | describes `bulk-export`/`email-integration/sync` async routes | CURRENT-AUTHORITATIVE — verified: `backend/api/routes/documents.py:217,223,502` still implement `documents/bulk-export(s)` | WS-1/WS-4 |
| `RC021_PORTABLE_ARTIFACT_STORAGE.md` | "complete locally 2026-09-08" | CURRENT-PARTIAL | WS-5 |
| `RC022_BUILD_RELEASE_STAGING.md` | "implemented and verified offline on deployment/render-turso-r2" | CURRENT-AUTHORITATIVE | WS-7 |
| `RC023_VPS_RUNTIME.md` | "offline preparation complete…VPS acceptance is pending" | HISTORICAL — superseded by the later recorded VPS deployment (handoff, WS-7) | WS-7 |
| `RC024_BACKUP_RESTORE.md` | "implementation and fixture rehearsal are integrated, bounded [rehearsal]" | CURRENT-PARTIAL | WS-7 |
| `RC026_BENCHMARK.md` | "offline benchmark preparation" | HISTORICAL | WS-3 |
| `RC027_APPROVED_PILOT_PACKET.md` | "frozen selection; local rehearsal complete" | HISTORICAL | WS-3/WS-7 |
| `RC027_LIVE_PILOT_RECEIPT_20260909.md` | 2026-09-09/10 | HISTORICAL | WS-3/WS-7 |
| `RC027_LIVE_STAGING_EVIDENCE.md` | 2026-09-09 | HISTORICAL | WS-3/WS-7 |
| `RC_A_HANDOFF.md` | title says "Historical…superseded" | HISTORICAL (self-declared) | WS-3 |
| `RC_B_HANDOFF.md` | "B completed the authorized VPS-local RC-024 rehearsal" | HISTORICAL | WS-7 |
| `RC_CURRENT_STATUS_AND_NEXT_STEPS.md` | 702 lines, last touched 2026-09-10 | CURRENT-PARTIAL — broad status roll-up, references `backend/application/admin_job_import.py` (deleted, L491) alongside still-valid content | WS-3 |
| `RC_C_HANDOFF.md` | 647 lines | CURRENT-PARTIAL — mostly release/integration handoff; L215–217 and L260–262 are HISTORICAL admin-analytics/RC-027-superseded sections (see [retired-features.md](retired-features.md) §6) | WS-7 |
| `RC_IDENTITY_RECONCILIATION_HANDOFF.md` | 2026-09-08 | HISTORICAL | WS-3 |
| `RC_PRODUCER_VERIFICATION_HANDOFF.md` | 2026-09-08 | HISTORICAL | WS-3 |
| `RC_WORKSTREAM_MANIFEST.md` | last touched 2026-09-10 | CURRENT-PARTIAL | WS-3 |
| `RC_CURRENT_STATUS_AND_NEXT_STEPS.md` | (listed once above) | — | — |
| `RUNR_PRODUCTION_COMPLETION_HANDOFF.md` | — | **Excluded — WS-7 owns this file**, not classified here | WS-7 |
| `RUNR_VPS_ACQUISITION_PLAN.md` | "Version 2.2 — 6 September 2026" | CURRENT-AUTHORITATIVE | WS-7/WS-3 |
| `admin_job_import_data_flow.md` | 2026-08-07 | HISTORICAL (retired feature) | see [retired-features.md](retired-features.md) |
| `admin_operations_console_parity.md` | 2026-08-13 | HISTORICAL (retired feature) | see [retired-features.md](retired-features.md) |
| `agent-skills.md` | no date | CURRENT-AUTHORITATIVE — verified against `.agents`/`.cline`/`.codex` and the sync scripts | WS-11 |
| `collection-controls.md` | 2026-08-12 | CURRENT-PARTIAL — describes an admin-import `scope` contract whose admin route was removed by `dd47acf9`; unverified whether the contract moved elsewhere (WS11-G1 in [known-gaps.md](known-gaps.md)) | WS-3 |
| `personalized_jobs_acquisition_audit_and_plan_2026-08-04.md` | "Phase A implementation complete; later phases intentionally not started" | CURRENT-PARTIAL | WS-4 |
| `personalized_jobs_contracts.md` | "P0 definitions only…stable payload shapes" | CURRENT-AUTHORITATIVE | WS-4 |
| `phase-c-feed-performance-security.md` | 2026-08-06, 15 lines | HISTORICAL | WS-4/WS-8 |
| `runr-analytics-spec.md` | 2026-05-17, "Generated from a codebase review" | HISTORICAL — predates the admin-dashboard retirement and describes a broader analytical surface than exists now; cross-reference [known-gaps.md](known-gaps.md) U7 | WS-1/WS-8 |
| `runr-monetization-deliverables.md` | 25,361 lines; self-declared "historical rollout snapshot" | HISTORICAL (self-declared) | WS-6 |
| `runr-website-discovery.md` | 2026-06-24, 1,341 lines | HISTORICAL | WS-8 |
| `scrapeops_usage_and_admin_dashboard_implementation_report.md` | 2026-05-25 | HISTORICAL (retired feature) | see [retired-features.md](retired-features.md) |
| `scraping_strategy_report_2026-05-26.md` | 2026-05-26 | HISTORICAL | WS-3 |

**`docs/architecture/` (26 files)**

| Path | Classification | WS |
|---|---|---|
| `acquisition_audit_permissions.md` (2026-08-12) | CURRENT-PARTIAL | WS-3 |
| `api_route_extraction.md` ("Status: active agent context", verified: `backend/api/server.py` is still the compatibility host, route bodies live in `backend/api/routes/`) | CURRENT-AUTHORITATIVE | WS-1 |
| 16 `assisted_apply_aa2NN_*_2026-08-01.md` spikes/prototypes (AA-201…AA-224) | HISTORICAL (dated spike/implementation records; several self-describe as "bounded", "prototype", or "spike") | WS-9 |
| `assisted_apply_architecture_baseline_2026-08-01.md` ("frozen repository-grounded architecture record") | HISTORICAL (explicitly frozen) | WS-9 |
| `backend_service_repository_boundaries.md` ("Status: active agent context") | CURRENT-AUTHORITATIVE | WS-1/WS-5 |
| `current_system.md` ("Status: active agent context"; verified: entrypoints list matches `workspace_runner.py`, `backend/api/server.py`, `backend/worker/service.py`, `frontend/src/App.jsx`, `apps/browser-extension/`) | CURRENT-AUTHORITATIVE | general (WS-12 cites) |
| `enrichment_foundation.md` (2026-08-12) | CURRENT-PARTIAL | WS-3 |
| `repository_hygiene_runbook.md` ("Status: active") | CURRENT-AUTHORITATIVE | WS-11 |
| `source_control_artifact_policy.md` ("Status: accepted for cleanup planning"; verified against `.gitignore`, §2 above) | CURRENT-AUTHORITATIVE (policy), but its own recommendation is unimplemented for `test CV/`/`test-CV/` (§9.4) | WS-11 |

**`docs/assisted-apply/` (6 files)**

| Path | Classification | WS |
|---|---|---|
| `ci/AA-225.md` ("PASS") | HISTORICAL | WS-9 |
| `gates/AA-P01.md`, `AA-P02.md`, `AA-P03.md` (all "PASS") | HISTORICAL | WS-9 |
| `pilots/AA-226.md` ("FAIL") | HISTORICAL | WS-9 |
| `runr-assisted-apply-ticket-pack.md` (1,190 lines) | HISTORICAL | WS-9 |

**`docs/deployment/` (8 files)**

| Path | Classification | WS |
|---|---|---|
| `cloud-checklist.md` | CURRENT-PARTIAL | WS-7 |
| `creem.md` | CURRENT-PARTIAL | WS-6/WS-7 |
| `creem_phase_h_audit.md` | HISTORICAL | WS-6 |
| `implementation-status.md` | HISTORICAL | WS-7 |
| `remaining-tasks-guide.md` (561 lines) | CURRENT-PARTIAL | WS-7 |
| `render.md` (verified: matches `render.yaml`'s three services — frontend static site, `runr-api`, `runr-worker`) | CURRENT-AUTHORITATIVE | WS-7 |
| `runtime.md` | CURRENT-PARTIAL | WS-7 |
| `target-architecture.md` ("Status: implementation baseline", 2026-06-18) | HISTORICAL — predates the VPS acquisition move (`RUNR_VPS_ACQUISITION_PLAN.md` v2.2, 2026-09-06) | WS-7 |

**`docs/legal/` (2 files)**

| Path | Classification | WS |
|---|---|---|
| `RUNR_TERMS_AND_CONDITIONS.md` ("Draft for legal review — do not publish until bracketed fields completed"; imported live by `MarketingSite.jsx`) | CURRENT-PARTIAL | legal/WS-6 |
| `RUNR_USER_AGREEMENT.md` ("Draft for legal review") | CURRENT-PARTIAL | legal/WS-6 |

**`docs/prd/` (9 files)**

| Path | Classification | WS |
|---|---|---|
| `README.md` | HISTORICAL (index of an older PRD set) | WS-4 |
| `application_remediation_parallel_workstreams_prd.md` (2026-04-20) | HISTORICAL | WS-4 |
| `phase0_contract_alignment.md` (2026-04-20) | HISTORICAL | WS-4/WS-5 |
| `product_requirements_document.md` (last touched 2026-06-22) | CURRENT-PARTIAL | WS-4 |
| `referral_tracker_confidence_pass_prd.md` (2026-05-05) | HISTORICAL | WS-4 |
| `referral_tracker_workspace_prd.md` (2026-05-03) | HISTORICAL | WS-4 |
| `scrapeops_usage_and_local_market_sourcing_prd.md` (2026-05-25) | HISTORICAL (base PRD for the retired admin-dashboard implementation report) | WS-3/WS-6 |
| `workspace_automation_nav_issue_drafts.md` (2026-05-09) | HISTORICAL | WS-4 |
| `workspace_run_progress_visibility_prd.md` (2026-05-25) | HISTORICAL | WS-4 |

**`docs/proposals/` (1 file)**

| Path | Classification | WS |
|---|---|---|
| `premium_paywall_placement.md` (2026-06-18) | UNKNOWN — a proposal; no confirmation it was implemented or rejected | WS-6 |

**`docs/reports/` (21 files)**

All dated 2026-05-27 through 2026-08-12/2026-08-07; `README.md` self-describes as a "Reports Hub" index. All 21 are **HISTORICAL** point-in-time reports (`README.md`, `ai_document_catalog_2026-05-27.md`, `codebase_cleanup_ticket_plan_2026-05-31.md`, `cv_export_pdf_preview_bullets_fix_report_2026-05-28.md`, `cv_language_section_parser_report_2026-05-30.md`, `deterministic_enrichment_trial_2026-08-12.{md,json}`, `phase_a_live_validation_incident_2026-08-05.json`, `phase_b_live_validation_2026-08-05.json`, `phase_e_job_intelligence_implementation_2026-08-07.md`, `phase_g_applicant_intelligence_audit_and_boundary_2026-08-07.md` ("Status: **BLOCKED**"), `phase_i_production_rollout_acceptance_2026-08-07.md` ("Status: **not complete**"), `public_job_index_user_dedupe_flow_2026-05-31.md`, `requirements_batch_implementation_report_2026-05-30.md`, `runr_assisted_apply_aa13_support_matrix_2026-07-18.md`, `runr_assisted_apply_aa18_edge_report_2026-07-18.md` ("Status: in_progress"), `runr_assisted_apply_permission_rationale_2026-07-18.md`, `runr_assisted_apply_ticket_plan_2026-07-17.md`, `runr_scraping_p1_questions_and_answers_2026-05-28.md`, `runr_scraping_p1_work_and_efficiency_report_2026-05-27.md`, `worker_architecture_reliability_audit_2026-05-27.md`). Owners: WS-3 (scraping/acquisition reports), WS-4 (CV/document reports), WS-9 (assisted-apply reports), WS-2 (worker audit).

**`docs/reviews/` (4 files)**

| Path | Classification | WS |
|---|---|---|
| `runr_app_review_clarifications.md`, `runr_app_review_complete_report.md`, `runr_app_review_implementation_guide.md`, `runr_app_review_part_iv_issue_proposal.md` (all 2026-06-22/23) | HISTORICAL | WS-4/WS-8 |

**`docs/security/` (1 file)**

| Path | Classification | WS |
|---|---|---|
| `runr_data_ownership.md` (2026-06-23) | CURRENT-PARTIAL | WS-6 |

### 9.2 Root report classification (24 `.md` + 6 `.json`)

| Path | Status line | Classification | WS |
|---|---|---|---|
| `ACQUISITION_REPAIR_REPORT.md` | 2026-08-10, 199 lines | HISTORICAL | WS-3 |
| `ACQUISITION_SOURCE_INVENTORY.md` | 2026-08-10 | HISTORICAL | WS-3 |
| `ACQUISITION_SOURCE_TRANSFER.md` | "completed locally on 2026-09-06" | HISTORICAL | WS-3 |
| `AGENTS.md` | governing instructions, unchanged since 2026-07-19 | CURRENT-AUTHORITATIVE | all (see §2) |
| `ARCHITECTURE.md` | 2026-04-18/19, 369 lines | HISTORICAL — superseded by `docs/architecture/current_system.md` | general |
| `BASELINE_AND_INPUT_CONTRACT.md` | "completed locally on 2026-09-06" | HISTORICAL | WS-3 |
| `BASELINE_METRICS.md` / `.json` | "complete locally on 2026-09-06. RC-003 was not started" | HISTORICAL | WS-3 |
| `CLERK_SETUP.md` | 2026-05-18, one-time dashboard setup steps | CURRENT-PARTIAL | WS-6 |
| `COMPANY_REGISTRY_RECONCILIATION.md` / `.json` | "complete locally on 2026-09-06, offline read-only" | HISTORICAL | WS-3 |
| `CREEM_REMAINING_STEPS.md` | 2026-06-19, last touched 2026-08-07 | CURRENT-PARTIAL | WS-6 |
| `CURRENT_DATA_PIPELINE_MAP.md` / `.json` | title says "current", last touched 2026-08-10 | CURRENT-PARTIAL | WS-3 |
| `DATA_PIPELINE_IMPLEMENTATION_REPORT.md` | "final production closeout" | HISTORICAL | WS-3 |
| `FINAL_PRODUCTION_ACQUISITION_ACCEPTANCE_REPORT.md` | 2026-08-10 | HISTORICAL | WS-3 |
| `PARALLEL_PRODUCT_COMPLETION_REPORT.md` | 2026-08-10 | HISTORICAL | WS-3/WS-4 |
| `PRODUCTION_DATA_PIPELINE_IMPLEMENTATION_REPORT.md` | 2026-08-10 | HISTORICAL | WS-3 |
| `PRODUCTION_FRESH_ACQUISITION_REPORT.md` | 2026-08-10 | HISTORICAL | WS-3 |
| `RC004_BACKFILL_REPORT.md` | "complete for the bounded offline pilot" | HISTORICAL | WS-3 |
| `RC006_RESOLUTION_SAFETY.md` / `.json` | "complete offline on 2026-09-06" | HISTORICAL | WS-3 |
| `RC007_EXPORT_SEPARATION.md` / `.json` | "complete offline on 2026-09-06" | HISTORICAL | WS-3 |
| `RC008_PRODUCER_ADAPTERS.md` / `.json` | "complete offline on 2026-09-07" | HISTORICAL | WS-3 |
| `README.md` | verified: commands (`npm run dev`, `npm run check:backend`, etc.) match `docs/architecture/current_system.md` | CURRENT-AUTHORITATIVE | general |
| `REMAINING_APP_ISSUES.md` | 697 lines; 8 Resolved, 3 Persistent-after-fix, 1 Open, 1 Local-fix-implemented | CURRENT-PARTIAL | WS-4/WS-8 |
| `SCRAPER_SOURCE_BASELINE_MANIFEST.md` | 2026-09-05 | HISTORICAL | WS-3 |
| `SOURCE_ELIGIBILITY_MANIFEST.md` | "complete locally on 2026-09-06" | HISTORICAL | WS-3 |

### 9.3 Skill-directory duplicate check (`.agents/`, `.cline/`, `.codex/`)

Verified with `git ls-tree -r` blob hashes, per-file, across all three trees (38/39/40 files respectively).

| Comparison | Result |
|---|---|
| `.agents/skills/**` vs `.cline/skills/**` | **Identical** for all 38 shared paths (blob hashes match). `.cline/` has one extra file, `kanban/config.json` (not a skill; a Cline-specific shortcut config, PowerShell command referencing a local `kanban-autopilot.ps1`). |
| `.agents/skills/**` vs `.codex/skills/**` | **38/40 identical.** `.codex/` has two extra files (`skills/LICENSE`, `skills/README.md`) and **one real divergence**: `skills/production-debug/scripts/check_production_access.py` differs (`.agents`/`.cline` blob `43b15719…`, `.codex` blob `16473052…`). The diff (`git diff --no-index`) shows `.codex`'s copy adds a guard against Vite/minifier template-literal false positives (`if "${" in candidate or "}" in candidate …: continue`) when scanning for API base URLs — `.agents`/`.cline` lack this fix. |

Classification: `.agents/**` **CURRENT-AUTHORITATIVE** (source of truth), `.cline/**` **CURRENT-AUTHORITATIVE** (in-sync mirror), `.codex/**` **CURRENT-PARTIAL** (mirror plus one un-back-ported fix and 2 extra files) — WS-11 records this drift; back-porting is a maintenance action outside Phase 2's scope.

### 9.4 `test CV/`, `test-CV/`, `screenshots/`, `user_config/`, stray files

| Path group | Type description (no content beyond structure/size) | Classification |
|---|---|---|
| `test CV/` (240 files: 169 `.docx`, 50 `.txt`, 13 `.html`, 5 `.md`, 2 `.json`, 1 `.png`) | Generated CV-rendering samples across 4 subfolders (`01_current_codebase_outputs`, `02_builtin_style_matrix`, `03_external_better_alternative`, `04_web_inspired_templates`), plus `README.md` and `manifest.json` describing the bundle (role/tailored counts, output paths). Produced by `backend/tools/build_test_cv_bundle.py`/`build_test_cv_web_templates.py` (WS-4). No customer PII confirmed — the README describes them as built from "current reusable role CV files" and one external comparison sample, not live customer data. | RETIRED-RESIDUE relative to policy — `docs/architecture/source_control_artifact_policy.md` recommends untracking this directory (`git rm -r --cached -- "test CV"`), and `.gitignore:75` already ignores it, but it remains tracked. |
| `test-CV/` (224 files: 169 `.docx`, 50 `.txt`, 3 `.md`, 2 `.json`; no `.html` or `.png`) | Same generation family as `test CV/` but only 3 of its 4 subfolders (`01`, `02`, `03`; no `04_web_inspired_templates`). 101 filenames are byte-for-byte identical to `test CV/`'s (content diff not verified beyond name/blob match where hashes were compared); 139 files exist only under `test CV/` and 123 only under `test-CV/` — **the two are not duplicates**, they diverged at different generation runs. Both were added in the same commit `8adbc5ab` (2026-05-05) and never touched again. | RETIRED-RESIDUE — same policy recommendation applies (`git rm -r --cached -- test-CV`); policy doc allows keeping it only "if converted into a maintained fixture package," which has not happened. |
| `screenshots/` (9 PNG, 68 KB–512 KB) | Feature/e2e screenshots: `dashboard-loading-current-state.png` (the retired dashboard), 5 `personalized-*.png` (hidden-jobs, job-detail, jobs-feed, onboarding-result, upgrade-prompt), 3 `phase-d-jobs-{1366,1920,375}.png` (responsive widths). Written by e2e specs (§4). | HISTORICAL/CURRENT-PARTIAL split — the dashboard screenshot is RETIRED-RESIDUE (see [retired-features.md](retired-features.md)); the `personalized-*` and `phase-d-*` ones correspond to still-present frontend routes and specs (CURRENT-PARTIAL). |
| `user_config/` tracked files (3) | `discovered_regular_company_career_sites.txt` (0 bytes/lines — empty placeholder), `github_logo.jpg` (89,230 bytes), `linkedin_logo.png` (69,440 bytes) — ordinary logo image assets, no personal data. Everything else under `user_config/` (candidate assets, profile photos, CV master, job-seeker config, `.live.txt` discovery files) is gitignored per `.gitignore:60-66` and out of scope (T08/T10). | CURRENT-PARTIAL (logo assets plausibly still used by document generation, §4) |
| `image.png` (root, 512,382 bytes) | **Byte-identical** to `screenshots/dashboard-loading-current-state.png` (same blob hash `fa607bfc…`) — a duplicate copy at the repo root, added by the same commit (`26ddaf08` 2026-06-20, "Dashboard Improvement") that added the screenshot. | RETIRED-RESIDUE (duplicate of a retired-dashboard screenshot; safe to remove, not removed in Phase 2 per the no-deletion rule) |
| `.backend_api_stderr.log` (2,650 bytes) | A single captured Python traceback (`ConnectionAbortedError` / `WinError 10053`) from a local dev run of `backend/api/server.py`. Contains only a local Windows file path and a loopback-range client address; no secrets or credentials found. | RETIRED-RESIDUE (stray local dev artifact; matches `.gitignore:39` pattern `*.log` for future files, but this one predates/bypassed that rule since it's already tracked) |
| `.backend_api_stdout.log` (0 bytes) | Empty stray log file | RETIRED-RESIDUE |
| `.gitignore` (1,600 bytes, last touched `bdd6b970` 2026-07-19) | Governs local/runtime/generated exclusions: Python/Node artifacts, `.env*`, `.backend_*`/`.runr_*`/logs/databases, generated docs/outputs, `user_config` personal files, `Archive/`, `Jobs-Urls/`, `test CV/`, `test-CV/`. | CURRENT-AUTHORITATIVE |
| `.gitattributes` (384 bytes) | Two rules: preserve `data/acquisition/inputs/*.csv` as binary (exact-byte seed data), and force LF line endings for `*.sh` and `deploy/systemd/*.{service,timer,target}` (Linux runtime files). | CURRENT-AUTHORITATIVE |

**Deployment evidence subsection:** none of the paths in this document are deployed or referenced by `render.yaml`/Dockerfiles as runtime dependencies (`.dockerignore` explicitly excludes `docs/*` except `docs/legal/`, and excludes `.codex`). Any "current production" language elsewhere in this corpus (e.g., RC-027 pilot receipts) is documentary only per the common brief; LIVE PRODUCTION = UNKNOWN.

## 10. Confirmed gaps and unresolved questions

All cross-cutting gaps (C1–C10, U1–U13, T01–T14) are tracked centrally in [known-gaps.md](known-gaps.md); admin-dashboard-specific residue is in [retired-features.md](retired-features.md) §4. New WS-11-local gaps found while classifying this corpus:

- **WS11-G1:** `docs/collection-controls.md` documents an admin-import `scope` contract whose route (`backend/api/routes/acquisition_admin.py`) was deleted in `dd47acf9`. Whether the `scope` object still has a live consumer is unverified — WS-3 to confirm. (Also recorded in [retired-features.md](retired-features.md) §7.)
- **WS11-G2:** `test CV/` and `test-CV/` are both gitignored (`.gitignore:75-76`) yet still tracked (464 files combined), contradicting `docs/architecture/source_control_artifact_policy.md`'s own recommendation. No ticket among T01–T14 covers untracking them; a cleanup ticket candidate.
- **WS11-G3:** `image.png` at the repository root is a byte-identical duplicate of `screenshots/dashboard-loading-current-state.png` (retired-dashboard evidence). Same disposition as WS11-G2 — safe-removal candidate, not executed in Phase 2.
- **WS11-G4:** `.codex/skills/production-debug/scripts/check_production_access.py` has a real fix (template-literal false-positive guard) that `.agents/`/`.cline/`'s copies lack — the sync direction assumed by `docs/agent-skills.md` (`.agents` is the source) has been violated at least once. Back-port or reconcile.
- **WS11-G5:** `docs/runr-analytics-spec.md` (2026-05-17) describes a broader analytics surface than exists after the `dd47acf9` retirement; it was not updated to reflect the retirement. Cross-reference [known-gaps.md](known-gaps.md) U7/C7.

## 11. Agent context and remaining work

**(a) Proposed agent context packet for anyone extending this classification:**
- **Required reading:** this file; `evidence-package-2026-09-13/{subsystem-allocation,recommended-documentation-tree,contradictions-and-unknowns}.md`; `phase-1-delta-audit-2026-09-13.md`.
- **Allowed paths:** read anything; write only `docs/reverse-engineering/06-history-and-provenance/{repository-artifacts,retired-features,known-gaps}.md`.
- **Tests to run:** none (git-only verification, §7).
- **Prohibited:** editing any file outside these three; opening `user_config/`'s gitignored personal content; running `scripts/sync-agent-skills.*`; deleting/moving `test CV/`, `test-CV/`, `image.png`, or the logs even though §10 flags them as removal candidates.

**(b) Registry proposal:**

| subsystem id | name | owned globs | primary doc | test globs | owner WS |
|---|---|---|---|---|---|
| ws-11-docs-artifacts | Docs corpus and repository artifacts | `docs/**` (excl. `RUNR_PRODUCTION_COMPLETION_HANDOFF.md`), root `*.md`/`*.json` (excl. `RELEASE_LEDGER.md`, `package.json`, `package-lock.json`), `test CV/**`, `test-CV/**`, `screenshots/**`, `user_config/**` (tracked only), `.agents/**`, `.cline/**`, `.codex/**`, `image.png`, `.backend_api_std{err,out}.log`, `.gitignore`, `.gitattributes` | `docs/reverse-engineering/06-history-and-provenance/repository-artifacts.md` | none | WS-11 |

**(c) Gap/ticket candidates:** WS11-G1…WS11-G5 above (§10); the ten active clean-slate tickets T01/T03/T04/T05/T06/T08/T10/T11/T12/T14 in [known-gaps.md](known-gaps.md) §4, three of which are WS-11's directly (T05, T06, T10).
