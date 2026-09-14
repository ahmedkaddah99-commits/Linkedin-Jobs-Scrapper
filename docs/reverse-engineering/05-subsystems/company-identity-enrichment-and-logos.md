> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Company identity, enrichment and logos (WS-3 secondary)

Secondary doc; primary is [acquisition-and-collectors.md](acquisition-and-collectors.md) (see also [publication-and-catalog.md](publication-and-catalog.md) for crosswalk *application*). Scope: the offline company-identity toolchain (registry reconciliation, canonical-ID backfill, identity canonicalization/crosswalk construction), the worker-side company enrichment service, the enrichment foundation package (`backend/enrichment/**`), logo validation/caching and the logo importers.

Method: static reading at `58a96674`. No network call, provider request or DB write was performed; production state is UNKNOWN.

---

## 1. Purpose and user-facing capabilities

Indirectly user-facing: company identity decides which producer rows belong to which canonical company (and therefore which jobs are publishable — unresolved identity is a hard gate rejection), and logos/monograms appear in the customer Jobs UI.

| Capability | What it does | Main code |
|---|---|---|
| Registry reconciliation (RC-003) | Read-only master-list vs identity-state diff; reviewable crosswalk proposal; never allocates IDs | `backend/application/company_registry_reconciliation.py` (schema `company_registry_reconciliation_v1`, docstring "stops before RC-004") |
| Canonical-ID backfill (RC-004) | Deterministic, non-destructive master-namespace ID backfill; dry-run manifest then approved CSV write; never targets the input file | `backend/application/company_id_backfill.py` (schema `rc004_company_id_backfill_v1`); CLI `scripts/backfill_company_ids.py` |
| Identity canonicalization / crosswalk construction | Pure registry rows → old-identity → surviving-canonical-ID map; LinkedIn org URL primary, org ID/CompanyEnrich ID corroborate, website evidence-only, name never an identity seed | `backend/application/company_identity_canonicalization.py` (schema `runr.company_identity_crosswalk.v1`, rules in docstring L9–21) |
| Canonicalized producer states | Immutable versioned copies of the producer DBs with canonical IDs + `company_identity_crosswalk.json` | `scripts/canonicalize_producer_states.py` (default registry `data/acquisition/inputs/company_registry_canonical.csv`, L38) |
| Worker company enrichment | Bounded, config/env-gated (`acquisition.phase_f.company_enrichment_enabled`, default off) enrichment of employer companies with verified-field semantics; ScrapeOps providers, Webshare LinkedIn provider | `backend/application/company_enrichment.py` (`CompanyEnrichmentService` L1110, `OfficialWebsiteProvider` L87, `ScrapeOpsCompanyProvider` L366, `ScrapeOpsLinkedInCompanyProvider` L577, `WebshareLinkedInCompanyProvider` L968); entry `backend/application/services.py:940` (`run_due_company_enrichment`) |
| Resolution safety (RC-006) | Offline-safe policies, durable resolver gate around provider calls, evidence ranks (`user_confirmed > verified > discovered > provisional`) | `backend/application/company_enrichment_resolution.py` (ranks L30–36) |
| Enrichment foundation | Provider-neutral, **inactive-by-default** contracts/evaluation/fixtures; fail-closed activation flags; publication hard-disabled | `backend/enrichment/**` (`__init__.py` docstring, `activation.py:14–20`) |
| Logo validation & caching | MIME/size/dimension checks, SSRF host blocks, content-addressed object-storage cache, deterministic monogram fallback | `backend/application/company_logo.py` (limits L20–28, blocked hosts L29–35); provider-independent adapter `company_logo_adapter.py` |
| LinkedIn logo import | Download/validate `.licdn.com`/`.linkedin.com` logos, cache to object storage, write `canonical_company_profiles` logo columns; never writes Turso/Render | `scripts/import_linkedin_company_logos.py` (docstring L1–8, host suffixes L43) |
| Free CompanyEnrich logos | Fill free CompanyEnrich logo URLs in place (CSV + SQLite) | `scripts/populate_free_companyenrich_logos.py` |
| Website discovery (Bing) | Multi-query consensus discovery + logo fill; JSONL checkpoints | `scripts/discover_websites_consensus.py`, `scripts/discover_websites_from_web_search.py` (NET-OPS) |
| Known websites | Match user website list, call CompanyEnrich free logo endpoint | `scripts/apply_known_company_websites.py` (NET-OPS; differs on UNMERGED `0d7f2b5c`, T04) |
| URL view / operations | Provider-free read-model views of company URLs and enrichment state | `backend/application/company_operations.py`, `company_reconciliation.py` |

## 2. Owned paths and governing instructions

| Path | Lines | Role |
|---|---:|---|
| `backend/application/company_enrichment.py` | 1,249 | worker enrichment service + providers |
| `backend/application/company_enrichment_resolution.py` | 484 | RC-006 safety policies |
| `backend/application/company_identity_canonicalization.py` | 384 | crosswalk construction |
| `backend/application/company_logo.py` / `company_logo_adapter.py` | 258 / 375 | logo primitives / adapter |
| `backend/application/company_id_backfill.py` | 467 | RC-004 backfill |
| `backend/application/company_registry_reconciliation.py` | 638 | RC-003 reconciliation |
| `backend/application/company_reconciliation.py` | 129 | read-only URL reconciliation |
| `backend/application/company_operations.py` | 570 | read-model views |
| `backend/application/duplicate_decisions.py` | 747 | reversible duplicate-review state machine (persistence-neutral; no executor) |
| `backend/enrichment/**` | 13 files | inactive foundation (contracts, evaluation, fixtures, providers, boundaries, cache, persistence, activation, fixture) |
| Related scripts | `scripts/{canonicalize_producer_states,backfill_company_ids,reconcile_company_registry,import_linkedin_company_logos,populate_free_companyenrich_logos,apply_known_company_websites,discover_websites_*,linkedin_company_enrichment_pipeline,run_linkedin_company_id_resolution,run_linkedin_company_sweep,clean_master_company_url,add_website_discovery_status_column,profile_company_inputs,run_offline_enrichment_trial,generate_completeness_sample}.py` | PREP/NET-OPS/AUDIT (classification in primary §4.3) |

Governing docs: RC-003/004/006 decisions survive only in module docstrings, test names and `deploy/acquisition-data-manifest.json` notes at this SHA — no `docs/RC003_*`/`RC004_*`/`RC006_*` report exists at the baseline (checked with `git ls-tree`); the module docstrings cited above are the authoritative statement (**WS3-G17**).

## 3. Entry points

- **Runtime (VPS restore path only):** `deploy/restore-acquisition-states.sh` → `scripts/canonicalize_producer_states.py` (wrapper L54–58) — the only enrichment/identity script called by a baseline unit/wrapper.
- **Worker (in-app, gated):** `workspace_runner.py run-worker --worker-role customer` poll → `services.run_due_company_enrichment` (`services.py:940`); returns `{"status": "disabled"}` unless env `RUNR_COMPANY_ENRICHMENT_ENABLED` or config `acquisition.phase_f.company_enrichment_enabled` opts in (L952–959). Manual bounded sweep: `scripts/run_linkedin_company_sweep.py` (prefix `manual-linkedin-full-sweep-20260815-bg`, batch 25).
- **Operator/NET-OPS CLIs:** the scripts table above; all bounded with budgets/checkpoints; `linkedin_company_enrichment_pipeline.py` is offline-usable for parsing/scoring and online only via explicit bounded/live CLI modes (docstring L3–6).
- No HTTP routes (admin enrichment routes + `backend/enrichment/operations.py` removed in `dd47acf9`).

## 4. Inputs, outputs, storage and dependencies

| Item | Detail |
|---|---|
| Registry inputs | `data/acquisition/inputs/company_registry_canonical.csv` (17,601×42, `canonical_CompanyID`) — INPUT (N-3); `company_master.csv` (9,129×82) — INPUT; details: [../03-data/acquisition-source-state.md](../03-data/acquisition-source-state.md) |
| Resolver state | `/srv/runr/state/enrichment/linkedin_id_resolution.sqlite3` (~414 MB snapshot in the data manifest; RC-006b pending) |
| Producer states | read by `canonicalize_producer_states.py`; versioned outputs under `/srv/runr/state/versions` + `active` symlink |
| Logo storage | object storage via `backend.storage.create_object_storage` (WS-5 [../03-data/object-storage-r2.md](../03-data/object-storage-r2.md)); keys content-addressed (`cache_logo`) |
| Catalog writes | enrichment profiles via `PersonalizedJobsService.upsert_company_profile` (`services.py:929`); logo columns in `canonical_company_profiles` |
| Providers (names only) | ScrapeOps (LinkedIn company, native credits), Webshare proxies, CompanyEnrich free logo endpoint, Bing web search |

## 5. Important call/data flows

1. **Identity:** registry CSV → `canonicalize_registry_rows` → `CompanyCrosswalk` (`runr.company_identity_crosswalk.v1`) → written by `canonicalize_producer_states.py` as `company_identity_crosswalk.json` → applied to the catalog by the publisher (`--identity-crosswalk`, see [publication-and-catalog.md](publication-and-catalog.md) §5). `resolve_company_id(payload, crosswalk)` is also used inline by the publisher to map source identities at delivery time.
2. **Backfill (RC-004):** `scripts/backfill_company_ids.py` dry-run → mapping manifest → approved write of a **new** CSV (never the input) — anchors `companyenrich_id`/`linkedin_org_id`, excludes school/showcase pages.
3. **Enrichment:** `run_due_company_enrichment` (bounded `max_companies=25`, `request_budget=25`) → `CompanyEnrichmentService` → provider (ScrapeOps LinkedIn company pages via `ScrapeOpsLinkedInCompanyProvider`, direct-then-Webshare fallback `WebshareLinkedInCompanyProvider`) → verified-field semantics (`_valid_value`) → profiles/logos via `company_logo` primitives → `upsert_company_profile`.
4. **Logos:** `validate_logo` (MIME allow-list PNG/JPEG/WebP/SVG, ≤2 MB, 32–4096 px) + `assert_public_official_host` (blocks localhost/metadata hosts) → `cache_logo` (content-addressed) → `canonical_company_profiles.logo_object_key`; Jobs UI signs a 900 s URL (`personalized_jobs_service.py:870–876`); monogram fallback via `deterministic_monogram`. Importer `scripts/import_linkedin_company_logos.py` accepts only `.licdn.com`/`.linkedin.com` hosts (L43).
5. **Foundation (inactive):** `backend/enrichment` exposes contracts + offline evaluation (`OfflineTrialOrchestrator`, golden labels fixtures) and fail-closed activation (`activation.py`: projection flag config-store opt-in; publication **hard-disabled**, L19–20). Worker-side analytics residue is out of scope (owner decision; WS-5/WS-11 record residue).

## 6. Invariants, failure handling and recovery

| Invariant | Where |
|---|---|
| Identity modules are pure/non-destructive; the caller persists and applies in separate transactions | `company_identity_canonicalization.py` docstring L3–6; `company_id_backfill.py` docstring |
| Website/domain is evidence only; never merges companies alone; name never an identity seed | `company_identity_canonicalization.py` docstring L13–18 |
| Discovered evidence can never silently replace verified or user-confirmed values | `company_enrichment_resolution.py` evidence ranks L30–36 |
| Backfill can never write the input CSV and needs an approved manifest | `company_id_backfill.py` docstring L5–8 |
| Enrichment is disabled by default (env + config gate) and bounded | `services.py:952–959` |
| Enrichment foundation publication is hard-disabled | `backend/enrichment/activation.py:19–20` |
| Logo bytes validated (type/size/dimensions) and host must be public/official; cached content-addressed | `company_logo.py` L20–35 |
| Logo importer never writes Turso or Render | `import_linkedin_company_logos.py` docstring L7 |
| Duplicate decisions are reversible, persistence-neutral; no merge executor exists | `duplicate_decisions.py` docstring (state machine only) |
| Canonicalized state copies are immutable; `active` switched atomically | `canonicalize_producer_states.py`; restore wrapper (WS-7) |

Recovery: resolver state has durable checkpoints (`linkedin_id_resolution.sqlite3`, restore-separately in `deploy/acquisition-data-manifest.json`); enrichment runs are resumable (`linkedin_company_enrichment_pipeline.py`, `--resume` semantics); logo import is idempotent per company scope.

## 7. Relevant tests and safe verification commands (not executed in Phase 2)

| Area | Tests |
|---|---|
| Identity/canonicalization | `tests/test_company_identity_canonicalization.py`, `tests/test_company_id_backfill.py`, `tests/test_company_registry_reconciliation.py` |
| Enrichment/resolution | `tests/test_linkedin_company_enrichment_pipeline.py`, `tests/test_rc006_resolution_safety.py`, `tests/test_linkedin_company_id_browser_resolution.py`, `tests/test_deterministic_enrichment_evaluation.py`, `tests/test_known_company_websites.py`, `tests/test_company_website_consensus.py` |
| Logos | `tests/test_import_linkedin_company_logos.py` |
| Duplicate decisions | `tests/test_duplicate_decisions.py` (state machine only; no executor exists) |
| Worker enrichment gate | `tests/test_phase_f_company_enrichment.py`, `tests/test_phase_a_rc018.py` |

Safe (offline) commands, not executed in Phase 2:

```bash
node scripts/run-python.cjs -m pytest -q tests/test_company_identity_canonicalization.py tests/test_company_id_backfill.py tests/test_company_registry_reconciliation.py
node scripts/run-python.cjs -m pytest -q tests/test_import_linkedin_company_logos.py tests/test_rc006_resolution_safety.py
node scripts/run-python.cjs scripts/canonicalize_producer_states.py --help
node scripts/run-python.cjs scripts/backfill_company_ids.py --help
```

Never run the NET-OPS scripts (`apply_known_company_websites.py`, `discover_websites_*.py`, `populate_free_companyenrich_logos.py`, `run_linkedin_company_id_resolution.py`, `run_linkedin_company_sweep.py`, `linkedin_company_enrichment_pipeline.py --live`) outside an authorized host: they spend provider credit.

## 8. Historical decisions and supporting commits

(`git log --oneline 58a96674 -- backend/application/company_* backend/enrichment scripts/canonicalize_producer_states.py scripts/import_linkedin_company_logos.py` selected)

| Commit | Subject | Decision |
|---|---|---|
| `3d36d8cb` | publisher: persist identity crosswalk before delivery | crosswalk ordering |
| `35fd6396` | fix publisher company identity reconciliation | |
| `8c27ac4e`, `c8dd517d`, `58a96674` | import LinkedIn logos; SQLite rows in logo importer; resolve SQLite row company matches | logo pipeline at head |
| `92bca0ac`, `4a1b1df5` | Webshare for public logos; avoid empty logo refs | logo transport; `4a1b1df5` = last recorded VPS release |
| `dd47acf9` | remove admin surfaces | deleted `backend/enrichment/operations.py` (1,370 lines) and admin enrichment routes |
| RC-003/004/006 era commits | registry reconciliation, ID backfill, resolution safety | see primary §8; decision records absent from baseline docs (WS3-G17) |

## 9. Current implementation status

| Capability | Classification |
|---|---|
| Identity canonicalization + crosswalk construction | VERIFIED (scope: static read of `company_identity_canonicalization.py` in full; consumers traced to publisher and restore script) |
| Canonicalized producer-state copies (restore path) | VERIFIED (scope: static; wrapper call verified in primary §3.1) |
| RC-004 backfill | VERIFIED (scope: static read; safety invariants above) |
| RC-003 registry reconciliation | VERIFIED (scope: static read; read-only confirmed) |
| Worker company enrichment | IMPLEMENTED-UNVERIFIED (code + gate verified statically; default disabled; no evidence any host enabled it) |
| RC-006 resolver safety | VERIFIED (scope: static read of `company_enrichment_resolution.py`) |
| Enrichment foundation (`backend/enrichment/**`) | PARTIAL — implemented, tested offline, fail-closed activation; publication path hard-disabled; no runtime consumer of the projection flag found (**WS3-G11**) |
| Logo validation/caching primitives | VERIFIED (scope: static read of `company_logo.py` + importer) |
| LinkedIn logo importer | IMPLEMENTED-UNVERIFIED (static read; last recorded VPS release `4a1b1df5` claims runs — documentary only) |
| Free CompanyEnrich logos / Bing discovery | IMPLEMENTED-UNVERIFIED (NET-OPS; historical runs recorded in untracked reports only) |
| Admin enrichment operations UI + `backend/enrichment/operations.py` | RETIRED/HISTORICAL (`dd47acf9`) |
| `Company-Urls/` dataset, enrichment scripts on `0d7f2b5c` | RETIRED/HISTORICAL / UNMERGED (`0d7f2b5c`, ticket T04; absent at baseline) |

### Deployment evidence (documentary only — not live verification)
- Untracked `docs/reports/RUNR_PRODUCTION_COMPLETION_REPORT_2026-09-12.md` (feature checkout; T06): VPS release `4a1b1df5` logo/`92bca0ac` Webshare public-logo claims — recorded, not verified.
- `deploy/acquisition-data-manifest.json` (baseline): `linkedin_id_resolution_state` snapshot listed with "RC-006b remains pending".
- `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` (WS-7 owns): documentary only.

## 10. Confirmed gaps and unresolved questions

| ID | Gap |
|---|---|
| **WS3-G11** | `backend/enrichment` foundation has no runtime consumer at the baseline (activation flags referenced only within the package + offline trial scripts). Confirm whether it is dead code or awaiting an integration owner decision. |
| **WS3-G12** | RC-006b (LinkedIn numeric-ID resolution completion) is pending per the data manifest; resolver state snapshot exists but the work is unfinished. |
| **WS3-G17** | The RC-003/RC-004/RC-006 decision records are not in the baseline `docs/` corpus; only docstrings/tests reference them. If the reports matter, they live outside git. |
| T04 | 11 enrichment/transport scripts exist only on `0d7f2b5c` and 3 baseline scripts differ there (verify per file before any merge; `tests/test_linkedin_germany_adaptive.py` import broken on that branch only). |
| C4 | `run_linkedin_company_sweep.py`/providers are not gated by `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED` (Phase-A-only flag; primary WS3-G1). |

## Agent context and remaining work

**(a) Agent context packet — identity, enrichment, logos**
- Required reading: this doc; `backend/application/company_identity_canonicalization.py`; `backend/application/company_enrichment.py` (service + provider classes); `backend/application/company_logo.py`; `scripts/canonicalize_producer_states.py`; `scripts/import_linkedin_company_logos.py`; [publication-and-catalog.md](publication-and-catalog.md) §5 (crosswalk application).
- Allowed paths: `backend/application/company_*.py`, `backend/enrichment/**`, the identity/logo scripts in §2; tests in §7 (with WS-10).
- Tests to run: the two pytest commands in §7.
- Prohibited: running NET-OPS scripts; enabling `RUNR_COMPANY_ENRICHMENT_ENABLED` outside an authorized host; editing `deploy/**` (WS-7), object storage config (WS-5); rewriting registry input CSVs in place (backfill must write a new file).

**(b) Registry proposal**

| subsystem id | name | owned globs | primary doc | test globs | owner |
|---|---|---|---|---|---|
| `company-identity-enrichment` | Company identity, enrichment and logos | `backend/application/company_*.py`, `backend/enrichment/**`, `scripts/{canonicalize_producer_states,backfill_company_ids,reconcile_company_registry,import_linkedin_company_logos,populate_free_companyenrich_logos,apply_known_company_websites,discover_websites_*,linkedin_company_enrichment_pipeline,run_linkedin_company_id_resolution,run_linkedin_company_sweep,clean_master_company_url,add_website_discovery_status_column,profile_company_inputs,run_offline_enrichment_trial}.py` | this doc (secondary to `05-subsystems/acquisition-and-collectors.md`) | `tests/test_{company_identity_canonicalization,company_id_backfill,company_registry_reconciliation,linkedin_company_enrichment_pipeline,rc006_resolution_safety,linkedin_company_id_browser_resolution,deterministic_enrichment_evaluation,known_company_websites,company_website_consensus,import_linkedin_company_logos}.py` | WS-3 |

**(c) Gap/ticket candidates**
1. WS3-G11: decide the fate of `backend/enrichment` foundation (integrate or retire).
2. WS3-G12: finish or formally close RC-006b (coordinate with T04 review).
3. Execute T04 file-by-file review before any enrichment-script merge.
