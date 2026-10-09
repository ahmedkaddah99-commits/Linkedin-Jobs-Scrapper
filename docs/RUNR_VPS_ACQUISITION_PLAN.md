# Runr: company registry, acquisition, and hybrid hosting delivery plan

Version 2.2 — 6 September 2026 — parallel delivery with one deployment integration branch

## Decision and scope

Keep the static frontend and public API on Render. Move acquisition and expensive customer processing into separately selectable workers on a VPS. Reuse the application's existing database-backed queues, Turso integration, object storage, identity evidence, and publication path. Add no separate gateway, tunnel, queue product, or database migration unless repository evidence establishes a need.

Release acquisition first. Keep existing customer processing available on Render while the VPS acquisition role is proven; move customer task families afterward, one at a time, through their own recovery and load gates. Two worker processes on one VPS provide resource separation, not host-failure redundancy. Published jobs and accepted queued work must remain available during a VPS outage, but processing will pause until recovery unless a second compatible worker host is provisioned. If that pause is unacceptable for customer tasks, keep their Render worker or fund another host. Do not promise high availability at a one-server price.

This is the best-supported next architecture for the supplied code and cost goals, conditional on measured total cost and recovery performance. The evidence does not establish Contabo as the best provider or prove that a particular VPS tier meets the workload. Buy compute after measuring the corrected pipeline. Missing IDs, repeated blocked requests, uncertain source completeness and absent producer-to-product integration are currently more consequential than machine size.

This is a planning deliverable, not authorization to change the repository, backfill production, purchase hosting, spend proxy/API credits, publish tickets externally, or deploy. Tickets are proposed and have not been executed. Implementation, migrations, commits, merges, paid/live tests, and production cutover remain distinct authorization boundaries. Use one controlled integration stream into deployment/render-turso-r2, with independent scoped implementation allowed in parallel as described below. Preserve existing dirty worktrees. Separate user-started Codex sessions may work concurrently; this plan does not require automatically spawning subagents.

The intended acquisition inputs are the user's company master list and its enriched subset. Initial live acquisition uses companies with a canonical Runr ID, a verified website, a LinkedIn company URL, and a verified numeric LinkedIn organization ID. Both source collectors remain independent; incomplete company rows go through identity/enrichment preparation and never disappear silently. Individual source eligibility is tracked even though the initial pilot uses the fully enriched intersection.

The existing collectors target Germany. In this plan, “all jobs” means all discoverable in-scope jobs for all eligible companies, with explicit coverage and failure accounting. It does not silently expand to worldwide collection or promise completeness on every website. Country scope stays explicit and versioned. Unknown coverage is never reported as complete.

## Mandatory implementation branch — applies to all 32 tickets

The sole integration and deployment target is **`deployment/render-turso-r2`**, as explicitly directed by the user. All completed ticket code, tests, repository documentation, migrations, deployment configuration and worker packaging must land and be validated there. Parallel sessions may prepare scoped changes in isolated working copies based on the selected deployment-branch snapshot; temporary task branches, if used for isolation, are not alternative integration or deployment targets. This supersedes the earlier plan's choice of `feature/admin-analytics-final-production` as the implementation workstream. Historical references to “primary” below identify evidence sources only.

Use the existing dedicated worktree for `deployment/render-turso-r2` as the integration worktree, with one writer at a time; verify its path, HEAD and current status before editing. Parallel implementation sessions each use their own isolated working copy and separate runtime/test state. The recorded baseline is `e7662c63082d605d8ae6de090d3a04a55bba6556`, not an instruction to reset to that commit. The supplement records three uncommitted employer/export changes on this branch; preserve and incorporate them. The user's choice of the most deployment-ready branch does not imply its current worktree has zero changes.

Treat `feature/admin-analytics-final-production` and `codex/master-linkedin-jobs-url` as source/reference worktrees. Bring useful acquisition, company-identity and enrichment code into `deployment/render-turso-r2` through scoped file/function integration with the required helpers, tests and dependency declarations. Preserve the source worktrees and their existing dirty/untracked files. “Move” means the target becomes self-contained; it does not require deleting the original copies. Avoid a whole-branch merge carrying unrelated browser-extension or frontend work.

| Component | Required disposition on deployment/render-turso-r2 |
| --- | --- |
| `scripts/master_linkedin_jobs_catalog.py` | Verify and retain the actual 14-table producer already evidenced on the target; recover only missing or demonstrably newer required changes from its producer worktree |
| `scripts/master_employer_jobs_catalog.py`, `scripts/build_master_jobs_catalog.py`, employer tests | Preserve the target's existing streaming/checkpoint/export changes; integrate needed primary-branch connector fixes and finish the planned decoupling |
| `scripts/clean_master_company_url.py`, `scripts/apply_known_company_websites.py` | Compare target versions and integrate missing identity/website preparation behavior with focused tests |
| Website discovery, `scripts/linkedin_company_enrichment_pipeline.py`, `scripts/run_linkedin_company_id_resolution.py` and required enrichment helpers | Select useful source versions; port missing scripts and their local dependencies/tests into the target, then apply the relevant safety/correctness tickets there |
| `scripts/master_linkedin_jobs_url_catalog.py` | Keep explicitly identified as the separate legacy implementation; do not substitute it for the actual producer in schedules or VPS entrypoints |
| Backend identity, normalization, queues and publication | Extend the deployment branch's existing Turso/Render/R2-compatible implementation; use primary snapshot code as reference without overwriting deployment-specific behavior blindly |
| Company master and scraper state | Preserve original data; use explicit runtime input/state paths and the planned import/checkpoint process. Do not commit large CSVs, databases, credentials or laptop-specific paths merely to make the target work |

A ticket cannot be accepted with its required implementation existing only on another branch or loading code through an absolute path, symlink or import into another worktree. Verify against the target worktree now and, at the approved release stage, against a clean checkout/container of its selected commit with declared runtime data mounted separately. Render and VPS builds must trace back to commits on this branch; component versions may differ during a documented compatible rollout.

The branch is the user's designated deployment branch. The exact revision currently serving production remains unverified until the release inventory check. Editing this plan does not itself commit, push or deploy code; inspect automatic-deployment behavior before any separately authorized push.

## Evidence and what must still be established

Inputs reviewed: RUNR_HOSTING_ARCHITECTURE_REVIEW.zip, SHA-256 FCFFA8C95258465030E4D3E7539E26DDF88E4E5718A08236EEF38CF345EC83E0; the entire attached scraper discussion, Pasted markdown(20260906-120638).md; and RUNR_ACQUISITION_IDENTITY_SUPPLEMENT.zip, SHA-256 aa048051598898d11201232dafe42eabbc736835a1cb163fa1ed4af723ed8271. ZIP integrity was independently checked. The supplement has 168 members; all 166 non-control manifest hashes match. MANIFEST.csv and VERIFICATION.md explicitly use N/A and are excluded from hash comparisons. Application tests were read, not executed. Sanitization breaks some source expressions; these copies must not be deployed.

Snapshots are working-tree snapshots, not guaranteed pristine commits:

| Snapshot | Branch / baseline | Relevant finding |
| --- | --- | --- |
| Primary | feature/admin-analytics-final-production / 0c4c4791 | Contains newer company-preparation scripts and dirty work. Correct producing LinkedIn script is absent from this snapshot. |
| Render candidate | deployment/render-turso-r2 / e7662c63 | Contains recovered LinkedIn producer and uncommitted employer/export optimization. Not confirmed live production. |
| Scraper worktree | codex/master-linkedin-jobs-url / 6d0fca4d | Separate producer history; must not be treated as the same revision as the primary branch. |

Confirmed distinctions:

- Employer producer: `scripts/master_employer_jobs_catalog.py`.
- LinkedIn producer identified by the attached discussion and recovered source: `scripts/master_linkedin_jobs_catalog.py`, with 14-table state. `scripts/master_linkedin_jobs_url_catalog.py` is a separate implementation, not an interchangeable filename.
- `scripts/build_master_jobs_catalog.py` is a projection/export tool, not an acquisition engine or an application-publication integration.
- The export optimization exists in the candidate working tree. Do not rebuild it from scratch. Its `export_only()` still passes `require_linkedin_csv=True`; employer-only export independence is unfinished.
- The employer input accepts several canonical-ID column spellings. The producing LinkedIn loader requires `canonical_CompanyID`. Normalize contracts without arbitrarily renaming or losing original fields.
- `scripts/clean_master_company_url.py::canonical_id()` preserves the first existing ID, otherwise derives an ID from enrichment ID/URL/domain/name/row evidence. It is not proof that every current master row has a stable assigned ID. Row order, changing identity evidence, and conflicting existing IDs need explicit treatment.
- The app already has `canonical_companies`, `company_identity_keys`, immutable identity evidence, and review candidates. Reuse and reconcile them instead of inventing another unrelated company registry.
- General runs have leases/recovery. The separate intelligence queue does not expose equivalent stale-processing recovery in inspected source. Its processing summary may also report availability after storing failure.
- Scheduled acquisition and enrichment execute before customer work in the same worker loop. Role separation is missing.
- The API still runs email synchronization and bulk-export assembly inline and relays some file downloads. Its Docker image also contains browser/OCR/office tooling and rebuilds the frontend.
- Firebase Analytics and backend event storage already exist. Source is newer than some analytics documents.

The supplement establishes the default local master schema, aggregate identity/readiness counts and local state sizes/statuses. It does not establish the deployed input, production company mapping, live capacity, actual provider limits or costs. No further bulk evidence ZIP is required to begin focused local work. RC-001 must check remaining local provenance discrepancies, while deployment and measurement gaps belong to the later release gates. Appendix A replaces the now-completed supplement request with a concrete evidence and handoff ledger.

### Master-list findings that change the backlog

The identified local input is `Company-Urls/Master-Company-Url/cleaned/Master-Company-Url-canonical_cleaned_linkedin_ids.csv`: 17,601 rows, 118 columns, 18,807,047 bytes, SHA-256 `7f416ec6ebbcb936a42061ef0adaa07e4a6c04d2959d0eb579779126682440d9`. These are reported aggregates over the original local CSV, not independently recounted from the 18-row pseudonymized sample. Its use in production remains unverified.

| Observed population | Rows / identifiers | Consequence |
| --- | ---: | --- |
| Rows with valid existing master canonical IDs | 7,513 | Preserve their IDs; application-ID equality is not established |
| Rows missing/placeholder canonical ID | 10,088 | Identity preparation is a major workstream, not an edge case |
| Rows with all four acquisition fields present/valid by report rules | 1,666 | Candidate dual-source cohort; still requires ownership and evidence validation |
| Rows with website, LinkedIn URL and numeric ID, but no canonical ID | 4,371 | Highest-value identity-first expansion cohort; avoid unnecessary re-enrichment |
| Rows missing website | 7,886 | Separate website discovery backlog |
| Rows missing LinkedIn URL | 2,147 | Separate source-discovery backlog |
| Rows missing/unresolved/non-numeric LinkedIn ID | 5,542 | Separate resolver backlog; not all are eligible for immediate retries |
| Unique numeric LinkedIn organizations | 11,907 | Source scan unit, not equivalent to Runr employer count |
| LinkedIn organizations associated with multiple existing master canonical IDs | 37 | Review ownership before assigning source jobs to a canonical employer |

Presence is not verification. The 1,666 count is not proof of 1,666 fully enriched, conflict-free companies. The potential 1,666 + 4,371 = 6,037 dual-field-ready rows after identity work is an upper bound before deduplication, evidence checks and ownership review; it is not a promised eligible-company count. The 7,513 distinct existing master IDs are not the total number of employers in the file.

The full reported readiness matrix must be a regression baseline. C = canonical ID, W = website, L = LinkedIn URL, I = numeric LinkedIn ID; uppercase means present/valid under the report's checks, lowercase means missing/invalid. It does not encode evidence freshness or verification quality.

| C | W | L | I | Rows |
| --- | --- | --- | --- | ---: |
| Yes | Yes | Yes | Yes | 1,666 |
| Yes | Yes | Yes | No | 1,404 |
| Yes | Yes | No | No | 2,138 |
| Yes | No | Yes | Yes | 705 |
| Yes | No | Yes | No | 1,591 |
| Yes | No | No | No | 9 |
| No | Yes | Yes | Yes | 4,371 |
| No | Yes | Yes | No | 136 |
| No | No | Yes | Yes | 5,317 |
| No | No | Yes | No | 264 |
| **Total** | | | | **17,601** |

The active file is flattened and has `Column1`–`Column9`, while the earlier cleaned file exposes JSON fields and `source_row_numbers`. Their row counts match, but that alone does not prove row-level lineage or explain the missing IDs. The original master has 9,129 rows; the local production-enriched export has 1,388 rows and is dated 16 August. They are different populations, not substitutes for the active master. Preserve unknown columns and existing evidence while building an explicit normalized import contract.

### Scraper state changes the definition of success

These figures are local aggregate snapshots spanning historical activity, not a fresh benchmark or proof of current production health.

| State | Observed evidence | Required action |
| --- | --- | --- |
| Employer | 428 company-state records: 1 completed, 82 partial, 194 no_jobs, 146 discovery_failed, 5 source_failed; 2,612 jobs | Audit negative outcomes and discovery failures before increasing concurrency or calling coverage complete |
| LinkedIn | 188,206 stored jobs; 11,896 source groups; 11,921 scans across two FINISHED runs | Reconcile input/group/scan units; scan rows are not unique current companies |
| LinkedIn completeness | 8,575 COMPLETE_ZERO_CONFIRMED scans; 23,926 SUSPICIOUS_EMPTY search-page records | Revalidate classification and legacy lifecycle evidence; aggregates do not prove each zero is false |
| LinkedIn pending work | 576 detail RETRY rows with blank next_attempt_at; 312 pending aliases; 7,381 alias-pending exclusions | Add durable retry scheduling and evidence-based alias review without bypassing ownership checks |
| LinkedIn proxy state | proxy_health has zero rows | Implement useful health accounting; an existing table is not an operating limiter |
| ID resolver | 1,475,495 request-log rows; 987,057 status 999 and 328,493 status 429 | 89.16% of logged attempts were blocked/rate-limited; prioritize circuit breaking and selective retries |

The resolver figures cover 23–28 August and multiple historical attempts. They do not prove one current invocation loops indefinitely, identify the exact cause, or establish present account concurrency. Its code already reuses terminal saved outcomes unless unresolved retries are requested. Preserve that behavior; add persistent request budgets and cooldowns so repeated invocations cannot recreate the historical request burden. This resolver is company preparation, separate from the job-detail collector.

The 14-table state is 3,479,191,552 bytes; the employer state is 83,841,024 bytes. The LinkedIn CSV is 774,860,470 bytes, its JSONL is 1,005,775,822 bytes, and the combined CSV is 1,421,822,599 bytes. Include temporary exports, raw evidence, backup transfer and retained generations in the disk/cost benchmark. These artifacts are overlapping representations, not independent job populations.

### Corrections to the supplement's narrative

- The supplement says it includes `master_linkedin_jobs_catalog.py`, but that implementation is absent from its members and manifest. Its tests are included. The earlier hosting ZIP contains the source in both candidate and scraper snapshots; retain that inspected evidence. The supplement reports original SHA-256 `AB2BB8EF64164F27D578425C3E4346D0B6DE35FFD10A4CDFD6AE43B8F8BD2C9B`, which must be checked against the real local file before implementation. Do not confuse this original hash with the sanitized archive-file hash.
- `run_linkedin_company_id_resolution.py::resolve_one()` selects `ids[0]` only inside `len(ids) == 1`; it does not blindly select from several IDs in that response. A narrower risk exists: an earlier ambiguous response updates `all_ids`, but a later single-ID response can return RESOLVED before checking accumulated conflicts. Separately, the actual job producer's `load_source_company_groups()` chooses `primary_canonical_company_id=ids[0]` when multiple master canonical IDs share an organization. These require distinct tests and policies.
- The provenance report labels some primary files tracked although its captured Git status lists them untracked. Git status/content on the real worktree must decide what can be committed or recovered. Some differences between ZIP copies are redaction differences, not evidence of new application changes.
- MISSING_EVIDENCE.md calls the 17,491,851-byte original master the actual master; the detailed input report identifies the 18,807,047-byte cleaned LinkedIn-ID file as the default active input. Use the latter for this planning baseline and verify the real invocation locally.
- Some purported safe distributions include `attempts_json` payload values. Those are not aggregate-only evidence and are unnecessary for the plan; do not propagate them into analytics, fixtures or future reports. Use an explicit allowlist of count/status fields.

These discrepancies narrow what is verified; they do not invalidate the matching source files and useful aggregate evidence or require another whole-repository export.

## Proposed architecture and durable-state ownership

| Layer | Owns | Must not depend on |
| --- | --- | --- |
| Render frontend and public API | Authentication, authorization, entitlements, fast queries, enqueue/status, admin views | A particular VPS being online to accept durable work or browse published jobs |
| Existing managed application database | Canonical IDs/mappings, source eligibility, cycle/task ownership, import receipts, published jobs, customer-task status | A worker's local files as the only record that a task was accepted |
| Object storage | Private artifacts, immutable export generations, recoverable scraper checkpoints and approved raw evidence | Relaying every large download through Render |
| Acquisition worker role | Schedule execution, LinkedIn collector, employer collector, normalization and publication staging | Customer request execution, user-triggered scraping, another collector's CSV |
| Customer worker role | CV/OCR/document tasks, requested intelligence, queued email tasks | Waiting for a full acquisition cycle to finish |
| Staging | Separate credentials, queues/database, object prefixes/buckets and test identities | Production data, emails, billing, schedules or analytics |

Keep fine-grained scraper state local initially if that is the smallest sound adaptation of the existing 14-table producer. Use a single owner per state database/shard, durable external task ownership, and consistent recoverable checkpoints. Do not copy a live SQLite main file without its consistency mechanism. A task is acknowledged only when its required result is durably accepted; losing local state may cause bounded rework, never loss of an accepted publication or customer artifact.

Do not move every request-attempt JSON blob into Turso. Store searchable normalized facts and compact control state there; put bounded raw evidence/checkpoint generations in object storage. Do not place the authoritative work queue on the only compute machine.

Scale later by non-overlapping company/source shards and additional workers, after fencing and replay tests pass. A LinkedIn organization shared by multiple master rows is one source scan with reviewed ownership mappings, not repeated scans or arbitrary reassignment to the first row.

The scraper remains an outbound worker: it fetches public sources and uses authenticated database/object-storage connections. Render does not need to call an exposed VPS scraper endpoint. Network separation alone does not make a worker safe: it processes untrusted pages and holds service credentials. Restrict credentials, isolate browser processes, and keep scrapers away from customer document/email secrets. If the managed database cannot provide the required worker permissions directly, document that concrete limitation and assess a narrow ingestion boundary in RC-023 rather than silently giving every scraper unrestricted access.

| Deployment choice | Cost/reliability implication | Decision |
| --- | --- | --- |
| All workloads on Render | Operational convenience; current user-reported compute cost concern remains | Retain as rollback baseline |
| Render public app + VPS acquisition; customer worker retained during pilot | Adds VPS cost temporarily; limits customer migration risk | First rollout stage |
| Render public app + separated acquisition/customer roles on one VPS | Consolidates compute; one host outage pauses both roles | Target only after recovery and load gates pass |
| Render public app + workers on two hosts | Better processing continuity; additional fixed cost and coordination | Triggered by required recovery/customer availability |
| Whole app/database on one VPS | Larger migration and failure responsibility; removes desired Render workflow | Outside this delivery plan |

## Milestones and execution order

| Milestone | Tickets | Exit condition |
| --- | --- | --- |
| M0 — Freeze evidence and measurement | RC-001–002 | Supplement review complete; local provenance/input checks and release thresholds recorded; live measurements remain a later authorized gate |
| M1 — Establish company identity and coverage | RC-003–006 | Every row accounted for, stable identities/mappings, verified pilot inputs |
| M2 — Prove the smallest complete product path | RC-007–010 | One eligible company runs through each producer into the same real Jobs UI using isolated fixtures/staging |
| M3 — Correct and optimize collectors | RC-011–017 | Independent reliable collectors, truthful coverage, measurable throughput and resumability |
| M4 — Make background processing portable | RC-018–022 | Separate roles, safe recovery, reachable stored artifacts, independent releases |
| M5 — Run on a VPS and validate | RC-023–027 | Secure reproducible setup, restore and load evidence, controlled complete pilot |
| M6 — Cut over and improve economics | RC-028–032 | Separate acquisition/customer cutovers, full eligible-list accounting and measured savings; analytics/second-host work only when enabled |

Dependency spine for the first product slice: RC-001 → RC-003 → RC-004 → RC-005 → RC-008 → RC-009 → RC-010. RC-002 can run alongside RC-003 and must supply its required baseline before RC-004; RC-007 can run separately immediately after RC-001 and joins at RC-008. Employer and LinkedIn correctness can start after source consolidation rather than waiting for RC-010. RC-006 expands eligibility but does not block a pilot of already verified companies. Only proceed to broad live acquisition after collector correctness, recovery and VPS gates. The original separate export formats and source provenance remain available throughout.

RC-004's pilot exit is a safe idempotent importer and reviewed mappings for the bounded pilot, not production backfill of all 10,088 missing-ID rows. Broader identity application follows dry-run review in waves. RC-006 has two separately reviewable slices: P0 resolver correctness/request controls before any resolver live run, then P1 enrichment expansion. Do not block acquisition for already verified companies on completion of the entire enrichment backlog. RC-028 has separate acquisition and customer cutover gates; paid Render worker removal follows actual task-family migration, not merely VPS provisioning.

For tickets spanning both workloads, record acceptance per release gate. Passing an acquisition slice never marks its deferred customer criteria Done.

| Gate | Required evidence | Explicitly deferred work |
| --- | --- | --- |
| Offline product proof | RC-001 input/source checks; RC-002 offline baseline/targets; RC-003–005 pilot identity/manifest; RC-007–010 source-to-Jobs fixtures | Purchase, live requests, full-list backfill, customer migration |
| RC-028 Gate A: acquisition | RC-011–017; acquisition role in RC-018; acquisition build/staging portions of RC-022; RC-023–024; acquisition monitoring/benchmark/pilot portions of RC-025–027; verified shared-DB impact on existing customer service | RC-019–021 and customer portions of RC-022/025–027 may remain open with customer workers retained on Render |
| RC-028 Gate B: customer workloads | RC-018–022 customer criteria; customer monitoring, load and failure drills in RC-025–027; chosen outage/continuity policy | Only unrelated optional product analytics or further scale |
| Full eligible acquisition waves | RC-028 Gate A, verified RC-005 manifests, relevant RC-026 capacity; RC-006 safety and enrichment only for cohorts that need resolver work | Whole-master enrichment completion and Gate B are not prerequisites |

These gate-specific dependencies take precedence over full-ticket dependency lists when only the named slice is released. Each remaining criterion stays assigned and visible in the tracker.

Priority definitions: P0 = required before the affected workload goes live; P1 = required before full-list expansion or broad customer migration; P2 = follow-up improvement with a specific trigger. Sizes are relative complexity, not time promises: S (focused), M (several connected changes), L (cross-component behavior). Split an L ticket into smaller reviewed changes if its diff grows beyond a reviewable slice; retain the ticket's end-to-end acceptance gate.

## Parallel execution plan

Use **three active implementation sessions initially**. Add a fourth operations/customer-work session only when file ownership, input contracts and integration are running smoothly. Three is a coordination recommendation, not a claim about subscription limits or machine capacity. More concurrent sessions do not guarantee proportional speedup and can increase review, context and merge work. Avoid running several browser-heavy test suites or live scrapers together on the laptop.

All lanes originate from the deployment branch after RC-001 consolidates the required code. Keep the historical feature and producer worktrees as read-only sources. Every completed change returns to deployment/render-turso-r2. The milestone table groups outcomes; it is not a command to finish every ticket in one milestone before starting the next.

### First launch after RC-001

| Codex session | Start with | Then, within this lane | Main files/ownership |
| --- | --- | --- | --- |
| A — Company identity and product integration | RC-002 offline baseline/targets and RC-003 identity mapping; a separate read-only reviewer may collect baseline evidence concurrently | RC-004 → RC-005 → RC-008 → RC-009 → RC-010, observing joins and collector-file ownership | Identity/import/manifest/adapters and application publication; migration changes assigned to this owner |
| B — Employer collector | RC-007 independent exports | RC-011 truthful outcomes → RC-012 bounded concurrency once RC-002 baseline is available | Employer producer, combined exporter, employer connectors and their focused tests |
| C — LinkedIn collector | RC-013 outcomes, retry/lifecycle and ownership correctness | RC-014 incremental refresh → RC-015 transport/storage, with RC-002 baseline available | Actual 14-table LinkedIn producer and its tests; no changes to company-resolution scripts owned by A |

RC-002 and RC-003 are dependency-independent but may share session A to keep the initial total to three sessions. First capture the collector baseline for B/C in their common starting snapshot, or preserve that exact snapshot for comparable replay, before claiming speed changes. Baseline capture does not require waiting for the rest of the cost report or logging into production.

When A reaches RC-008, it consumes the integrated RC-007 result and the RC-005 manifest contract. It can write separate adapter modules while B/C continue isolated collector work, but any edit inside an active producer or shared connector needs an explicit ownership handoff. Integrate the required collector version before running the combined RC-010 proof. A branch that merely contains competing unmerged changes is not a passing end-to-end result.

### Additional work that can overlap

| Work | Earliest useful start | What still waits |
| --- | --- | --- |
| RC-006a resolver correctness/budgets; RC-006b enrichment expansion | After RC-005; a free session may take the resolver files from A | Live enrichment waits for explicit budgets and authorization; same identity helpers retain one owner |
| RC-018 role filtering, then RC-019 intelligence recovery | After RC-001 and a recorded role/claim contract; use a freed session or optional session D | Scheduler integration with RC-016 and release gates still required |
| RC-020 slow routes → RC-021 portable artifacts | After the existing customer dependencies RC-018/019 | These touch related routes and should be sequential within one lane unless split by explicit non-overlapping files |
| RC-016 scheduler ownership | After RC-011 and RC-013 contracts/results are integrated | Shared worker/service and queue code must be handed off from RC-018/019 owner or remain in the same lane |
| RC-017 publication/expiry | After RC-009, RC-011, RC-013 and RC-016 | Serialize changes to acquisition repository/migrations with A; generation/export glue coordinates with B |
| RC-022 build/release/staging preparation | Deployment filters and packaging design can start after RC-001; role-specific build work after RC-018 | Removing API browser/OCR dependencies waits for RC-020 route extraction; full acceptance keeps ticket dependencies |
| RC-023 runtime setup definition | After RC-002 resource targets and RC-018 role interface | Purchase/provisioning and live verification remain separately scoped; do not claim an offline Compose file is a tested VPS |
| RC-025 dashboard view with fixtures | After RC-005 and an agreed coverage/status response contract | Live data/alert acceptance waits for actual RC-016/018/019 producers by workload gate |
| RC-024 backup/restore | After RC-015/016/023 | Actual recovery evidence needs the combined approved worker/state version |
| RC-030 analytics audit | Read-only audit can overlap after RC-001, when capacity is spare | Optional P2 implementation waits for its contracts; do not take a critical-path session away from acquisition |
| RC-031 scale and RC-032 handover | Draft runbooks/capacity triggers as implementation progresses | Full completion retains their release and measurement dependencies |

Early preparation does not mark a whole ticket Done or remove a listed final dependency. Only RC-007, RC-011, RC-013 and the implementation portion of RC-018 have their avoidable start dependencies relaxed in this revision. All quality, ownership, recovery, measurement and release criteria remain.

### Workspace isolation and integration rules

1. **One writer per working directory.** Never point three editing sessions at the same VS Code checkout, Git index, virtual environment under installation, SQLite test DB, export directory or test server port. Shared files may change even when tickets sound unrelated.
2. **Make RC-001's exact result available to every lane.** An approved baseline commit is simplest. If commits are not yet authorized, create consistent isolated working copies containing the exact required tracked changes and untracked source files, with a manifest/hash. A normal new worktree at HEAD does not automatically include the deployment worktree's uncommitted exporter changes. Never discard those changes to obtain a clean baseline.
3. **Use deployment-based isolation.** Temporary task worktrees/branches may use names such as `task/rc-employer` and `task/rc-linkedin`, based on the selected deployment snapshot. Their sole integration target remains deployment/render-turso-r2; they do not deploy or revive feature/admin-analytics-final-production as the workstream. An isolated patch-based working copy is also acceptable.
4. **Assign files before starting.** Record ticket/slice, base revision plus dirty-overlay hash where applicable, files owned, contracts consumed/produced, test command and integration prerequisite in each handoff. A session requests a file handoff from the coordinator before editing another lane's active file. It continues useful in-scope work while that handoff is pending.
5. **One integration owner.** A designated session applies reviewed results to the deployment worktree one at a time, reconciles overlaps semantically, and runs the focused affected tests plus a relevant combined smoke/E2E gate. It may be session A operating between its tasks; a continuously running fourth session is unnecessary. Commits/merges/pushes retain existing authorization boundaries.
6. **Shared contracts and migrations are serialized.** One owner changes canonical identity schema, shared source-status/observation contracts, scheduler/lease semantics, migration numbering and common worker entrypoints. Other lanes consume that contract or use test doubles. Two sessions must not independently invent versions of the same schema.
7. **Move dependencies forward explicitly.** After integrating a prerequisite, update dependent isolated copies using an approved commit or a narrowly reviewed patch. Record the new base. Do not let agents assume their sibling's unsaved work is present, overwrite their edits, or cherry-pick unrelated source-branch history.
8. **Separate preparation, validation and deployment.** Offline coding may overlap. Meaningful combined benchmarks must use one known integrated version and comparable workload; simultaneous tests that compete for CPU/RAM distort measurements. A single release owner coordinates live request budgets, migrations, worker ownership and production cutover. Independent offline fixtures may still run concurrently when their resources are isolated.

### Pairs that should stay with one owner

| Shared area | Ticket sequence / coordination |
| --- | --- |
| Employer producer/export path | RC-007 → RC-011 → RC-012; hand off producer hooks for RC-008 and export-generation changes for RC-017 |
| Actual LinkedIn producer | RC-013 → RC-014 → RC-015; coordinate RC-008 adapter hooks instead of parallel rewrites of the same script |
| Company identity/import | RC-003 → RC-004 → RC-005; explicit helper ownership when RC-006 runs separately |
| General worker/queue entrypoints | RC-018 then shared entrypoint changes in RC-016; separate RC-019 files only with agreed claim contract |
| Application acquisition store/migrations | RC-009 and RC-017 with one migration owner; never reserve conflicting migration versions independently |
| API routes and image dependencies | RC-020 → RC-021; coordinate RC-022 before deleting runtime packages |
| Production operations | RC-026 comparable benchmark → RC-027 combined pilot → RC-028 controlled cutover → RC-029 bounded waves |

The objective is overlapping independent development while keeping integration reviewable. It is not to run all 32 tickets at once. No ticket is Done until its acceptance evidence applies to the integrated deployment-branch result; a passing isolated task diff is Ready for integration.

## Ticket execution contract

Every ticket targets `deployment/render-turso-r2` and records: isolated implementation path and integration worktree path, owned files, starting branch/HEAD and dirty status; selected source revision; exact changed files/symbols; commands executed; observed results; limitations; before/after metrics where relevant; user-visible evidence; and rollback steps. No ticket is Done on the strength of a prose claim alone.

Use the repository-mandated Python environment. The supplied instructions require Python 3.12.7 in the project virtual environment. Do not silently substitute global Python. Resolve Linux/container runtime policy explicitly in RC-023. Existing test commands below are references for the implementation agent; execute them only in the verified environment with isolated data and network disabled unless a bounded live test is authorized.

Example existing focused suites: `python -m pytest tests/test_master_employer_jobs_catalog.py tests/test_master_linkedin_jobs_catalog.py tests/test_company_csv_consolidation.py tests/test_worker_service.py tests/test_phase_e_job_intelligence_async.py tests/test_object_storage.py tests/test_company_identity_reconciliation.py`. Substitute the verified project interpreter for `python`. Add behavioral tests where these suites do not cover a ticket; do not claim the current suite proves new behavior.

### RC-001 — Consolidate required acquisition code on the deployment branch and freeze inputs

Priority P0 · Size M · Dependencies: none · Owner: repository/backend.

Target branch: `deployment/render-turso-r2`.

Scope: first verify local source/input provenance, then integrate the useful acquisition, identity and enrichment scripts plus required helpers/tests into the existing deployment/render-turso-r2 worktree. Keep its deployment-compatible backend and existing exporter changes as the implementation baseline. Read feature/admin-analytics-final-production and the producer worktree as source references and preserve their files. Complete this as two reviewable slices: RC-001a provenance/input contract, then RC-001b scoped source consolidation with offline validation. Production revision is a later deployment gate, not a prerequisite for local work.

Acceptance:

- Every selected component has an exact path, content hash, worktree and baseline commit; dirty versions are labeled.
- The producing LinkedIn file is matched to the 14-table schema and existing exports. The URL-catalog implementation is explicitly excluded from live entrypoints unless separately approved.
- Existing export changes are classified as retain/fix/absent; no completed optimization is reimplemented unnecessarily.
- The master input path, header, input/output lineage, canonical-ID spellings, placeholders and aggregate eligibility are known; missing evidence is named.
- The source-transfer manifest records each selected file/function, originating branch/path/hash, existing target version, required helpers/tests and retain/port/adapt decision. RC-001a is read-only; RC-001b performs the scoped implementation on deployment/render-turso-r2. Preserve unrelated dirty work; no production access, push or deployment is part of either slice.
- Check the actual local LinkedIn producer against the reported original SHA-256; record its omission from the supplement and confirm the earlier source's relevant functions match. The sanitized source is never copied into executable code.
- Reproduce the 17,601-row/118-column master baseline and ten readiness buckets with documented validity rules; if the file hash changed, report both versions and their count deltas rather than forcing old counts.
- Resolve captured-status versus tracked-file-report contradictions and record upstream divergence (reported primary ahead 14/behind 37). No automatic pull/reset, overwrite of untracked files or global branch reconciliation is included.
- Produce a lineage assessment for original, cleaned, flattened LinkedIn-ID and production-enriched files. Preserve uncertainty about how missing IDs arose; do not attribute it to the cleaner without evidence.
- All required acquisition/preparation modules and focused tests are present on deployment/render-turso-r2, using declared dependencies and configurable data paths. Offline import/CLI-help and existing meaningful focused tests run from that worktree without importing code from other worktrees or making external requests.
- Preserve the target employer/export optimization and verify the actual producing LinkedIn implementation. Required source behavior is retained; legacy URL-catalog code and unrelated feature-branch changes are not accidentally installed as production entrypoints.

Verify: source/schema comparison, hashes, selected diffs and `git status`. Evidence artifacts: `BASELINE_AND_INPUT_CONTRACT.md` and `ACQUISITION_SOURCE_TRANSFER.md`. User result: the useful acquisition code and its dependencies are available and validated on the deployment branch before later feature work.

### RC-002 — Baseline throughput, cost and reliability targets

Priority P0 · Size M · Dependencies: RC-001 · Owner: backend/operations.

Target branch: `deployment/render-turso-r2`.

Scope: define representative offline workloads and the metrics needed for a bounded live benchmark. Agree a measurement table before tuning. Distinguish code defaults from actual provider/account limits.

Acceptance:

- Record company/source count, raw/unique/accepted jobs, HTTP/browser/detail requests, retries, wall time, peak RAM, CPU, disk, DB operations and measured/estimated/unknown external cost separately.
- Define explicit country scope, daily-cycle deadline, customer-task queue/completion targets, checkpoint recovery-point/recovery-time targets, storage retention and spend ceilings.
- Use the same input snapshot and comparable machine/configuration for before/after comparisons; compare quality and coverage as well as speed.
- Offline fixtures include small and large employers, multiple ATS families, rate limiting, malformed HTML and interrupted runs.
- No numeric production capacity or speedup is claimed until measured. A live benchmark has an exact company list, request cap and authorization before execution.
- Load profiles distinguish 1,666 dual-field-ready candidate rows, the 4,371 identity-first expansion rows, the eventual reviewed eligible population, and the 188,206-job existing state. Do not extrapolate from a 25-company smoke test alone.
- Capture historical state aggregates separately from measured runtime: 428 employer records, 576 LinkedIn detail retries and 1,475,495 resolver request logs are not single-run throughput measurements.
- Freeze the proposed service targets below or record explicit replacements before the pilot; production provider quotas, monthly budget and representative customer concurrency remain required concrete inputs to that freeze.

Verify: repeatable benchmark command and JSON summary. Evidence: `BASELINE_METRICS.md`. User result: measurable success criteria, not “it feels faster.”

### RC-003 — Define and reconcile the canonical company registry

Priority P0 · Size L · Dependencies: RC-001 · Owner: data/backend.

Target branch: `deployment/render-turso-r2`.

Scope: map the master list to existing canonical companies, external identity keys, evidence and aliases. Preserve the user's existing canonical IDs. A LinkedIn numeric organization ID is a source identifier, not the Runr primary key.

Acceptance:

- Document field-level mapping from master columns to current application tables and export fields, with source precedence and provenance.
- Existing conflicting IDs, same-name distinct employers, subsidiaries sharing domains, school/company/showcase URLs and duplicate LinkedIn mappings have explicit review behavior.
- No automatic merge is based only on company name or shared hosting/ATS domain. Multiple existing canonical IDs are never resolved by “take the first.”
- Missing identity and missing enrichment are separate states. A provisional registry record may exist without being eligible for acquisition/publication.
- Reimports, renames, changed websites and richer enrichment preserve established canonical IDs; aliases/redirects retain historical job and user references.
- Model master canonical IDs as durable external references until equality with application IDs is proven. Reuse existing application `canonical_company_<uuid>` records through reviewed strong identity keys; record the master-to-app crosswalk instead of rewriting either namespace casually.
- All 37 reported shared-organization cases receive an explicit disposition: same entity/alias, distinct related employers, or unresolved conflict. Retain distinct subsidiaries when justified; never assign ownership by sort order or fan every observed job to every employer automatically.
- One organization scan can serve multiple reviewed associations, but publication requires defensible observation-level employer ownership. Ambiguous observations remain quarantined without silently merging company identities.

Verify: identity fixtures plus existing reconciliation tests. Evidence: mapping table and conflict examples. User result: the same employer keeps the same identity throughout the product.

### RC-004 — Backfill missing IDs safely and idempotently

Priority P0 · Size M · Dependencies: RC-002, RC-003 · Owner: data/backend.

Target branch: `deployment/render-turso-r2`.

Scope: reuse or adapt existing ID creation and reconciliation. Allocate a stable ID once for each genuinely new registry entity; persist source-row mappings before exporting. A mutable row number/name must not be the sole long-term identity.

Acceptance:

- Dry-run reports retained IDs, new/provisional IDs, duplicate rows, ambiguous conflicts and rejected records; the original master is untouched.
- Every input row maps to a registry record or an explicit quarantine record. Eligible rows have exactly one nonempty canonical ID.
- Applying the same approved mapping twice creates no new IDs; reordering input or adding enrichment does not change existing mappings.
- Duplicate identity evidence and hash/ID collisions are detected and resolved/reviewed, never silently accepted.
- Backfill writes have a reviewed migration/import script, input hash, mapping manifest, backup and non-destructive rollback; production application is separately authorized.
- On the captured master, account for all 10,088 missing-ID rows without assuming they represent 10,088 new companies. Resolve strong matches to existing records before assigning a new ID; report retained, matched, new, provisional and quarantined counts separately.
- Prioritize the 4,371 rows with other acquisition fields present; preserve the 7,513 existing IDs. Reuse current website/LinkedIn evidence after validation without rerunning paid enrichment solely because the Runr ID was absent.
- A bounded offline pilot proves blank IDs, same-organization conflicts, reordering and enrichment changes. Full-list production application is a later wave, not a prerequisite to this first useful slice.

Verify: reordered/repeated import, conflict fixtures and referential-integrity checks. User result: missing IDs are filled without breaking existing company/job links.

### RC-005 — Build a versioned source-eligibility manifest

Priority P0 · Size M · Dependencies: RC-004 · Owner: acquisition/backend.

Target branch: `deployment/render-turso-r2`.

Scope: derive collector inputs from one versioned master snapshot. Preserve current pilot intent: run both sources for fully enriched verified companies. Track website-ready and LinkedIn-ready independently for later controlled expansion.

Acceptance:

- Each row reports canonical ID, website verification, LinkedIn URL, numeric-ID verification/evidence, source eligibility, exclusions and reasons.
- Blank IDs, `//`, `null`, malformed numeric IDs, unverified URL/ID pairs and conflicting ownership never enter an eligible task unnoticed.
- Duplicate rows yield one task per canonical employer/source, with LinkedIn grouping handled by reviewed organization mapping.
- Manifest counts reconcile: input rows, mapped entities, duplicate associations, dual-ready, single-ready and blocked entities are separately defined.
- The manifest has a content hash/version and immutable per-cycle snapshot. Removing an input does not falsely close all of its historical jobs.
- Keep field-presence readiness separate from evidence-verified eligibility. The baseline 1,666 candidate rows and potential 6,037 after identity work are not automatically eligible counts; report deductions for conflicts, invalid URLs, stale or unsupported evidence.
- Require the eligibility contract at both collector entrypoints. Existing LinkedIn code validates numeric ID/URL but can accept a blank canonical ID; employer code accepts a website without requiring the complete dual-source set. A direct scheduled CLI invocation must not bypass the manifest.
- Preserve a raw-column sidecar/schema contract for the 118-column source, including unexplained Column1–Column9; never silently drop provenance or treat row number as a persistent entity key.

Verify: input-contract fixtures using actual header spellings. User result: the admin can see exactly which companies will run and why others will not.

### RC-006 — Complete missing company enrichment through existing tools

Priority P0 for resolver safety; P1 for enrichment expansion · Size L · Dependencies: RC-005 · Owner: acquisition/data.

Target branch: `deployment/render-turso-r2`.

Scope: reuse website discovery, LinkedIn enrichment and numeric-ID resolution consolidated onto deployment/render-turso-r2 by RC-001 from the useful primary-branch source. Only request missing/stale evidence; acquisition does not require unrelated marketing-profile fields to be populated.

Acceptance:

- Missing canonical ID, missing website, missing LinkedIn URL, unresolved numeric ID and ownership conflict are separate queues/statuses.
- Verified values are reused; weaker evidence never overwrites stronger user-confirmed values silently.
- Name similarity alone cannot approve a new employer/source identity; ambiguous results remain reviewable.
- Network work has per-provider concurrency/rate/cost limits, cached results, bounded retries and resumable progress.
- Newly verified companies appear in the next versioned manifest without restarting every previously completed enrichment task.
- Split delivery into RC-006a (offline resolver correctness, budgets and cooldowns) and RC-006b (authorized enrichment expansion); these are slices of RC-006, not additional ticket IDs. Acquisition of verified companies does not depend on RC-006b.
- Test `resolve_one()` with ambiguous evidence followed by a conflicting single-ID response. Accumulated contradictory contextual IDs cannot become RESOLVED without a recorded reconciliation decision; same-response multi-ID handling and job-producer ownership grouping are tested separately.
- Persist per-URL/provider attempts, next eligible retry time and rolling budgets across restarts and repeated --retry-unresolved runs. Already resolved unchanged evidence causes zero network calls; retries target explicit due failures, not the entire catalog.
- Circuit breaking reacts to observed 429/blocked responses with bounded backoff and a small recovery probe; increasing workers/proxies cannot bypass a global request or provider credit ceiling. The resolver cannot exhaust the job collectors' reserved provider budget.
- A deterministic mostly-blocked fixture demonstrates an enforced upper request bound and recovery behavior. Report unresolved status honestly; no alternate identity guess is used to improve apparent success rate.

Verify: existing parser/resolver tests, synthetic transitions, then authorized bounded provider checks. User result: the eligible catalog expands predictably instead of losing incomplete companies.

### RC-007 — Decouple employer, LinkedIn and combined exports

Priority P0 · Size M · Dependencies: RC-001 · Owner: acquisition.

Target branch: `deployment/render-turso-r2`.

Scope: preserve the candidate's checkpoint/streaming optimization while removing the employer export's dependency on a LinkedIn CSV. Combined projection remains a separately invocable operation.

Acceptance:

- Employer collection and employer-only export succeed with no LinkedIn CSV or LinkedIn credentials, including zero-job valid state.
- Employer state is authoritative; export-only invokes no dotenv-dependent network setup or collector.
- LinkedIn exports work independently. Combined export declares required inputs and their generation IDs and fails clearly when those are missing.
- A combined-export failure does not relabel successful employer collection as failed or discard its valid independent artifacts.
- Real producer fields remain preserved; legacy field compatibility remains explicit. No per-company full export returns.

Verify: missing/corrupt input, zero rows, streaming and interrupted-promotion tests. User result: either source can finish and provide usable output while the other is offline.

### RC-008 — Adapt both producers to a shared observation contract

Priority P0 · Size L · Dependencies: RC-005, RC-007 · Owner: acquisition/backend.

Target branch: `deployment/render-turso-r2`.

Scope: add narrow adapters around the correct producer implementations. Preserve independently runnable CLIs and source-specific state. Emit bounded batches from durable state/results; avoid a CSV-only ingestion dependency.

Acceptance:

- Every observation carries canonical employer mapping, source, source job ID, source URL, apply URL/type, scope, cycle/scan IDs, observed timestamp, content hash and schema version.
- LinkedIn ownership, Easy Apply status, applicant data, source-company associations and employer ATS/extraction evidence survive mapping; missing fields stay unknown.
- Source records remain distinct. Raw observations are not discarded because the public catalog later deduplicates them.
- Delivery uses a stable idempotency key and bounded batch size. Replaying the same batch produces the same receipt and no duplicate logical observation.
- A fake transport can run each real producer's orchestration/parser path and reach the adapter without network credentials.

Verify: producer-to-contract tests and full field-preservation fixtures. User result: both scripts can feed Runr without depending on each other's output formats.

### RC-009 — Connect observations to existing normalization and publication

Priority P0 · Size L · Dependencies: RC-008 · Owner: backend/data.

Target branch: `deployment/render-turso-r2`.

Scope: integrate adapters with current acquisition stores, company identity, job versioning, validation, publication and user-facing Jobs queries. Extend existing infrastructure rather than creating a second public job catalog.

Acceptance:

- A fixture job from each source appears under the correct canonical employer in the real staging Jobs API/UI, with filters and details working.
- Cross-source duplicates may share one canonical public job only on strong evidence such as canonical application URL/requisition ID; ambiguous matches stay separate/reviewable.
- Different openings with similar titles are not merged. All source observations and accepted field provenance remain available to admins.
- Publication honors current external-application, ownership, geography, quality and entitlement rules. Quick/Easy Apply-only records remain excluded under current product policy.
- Bind the adapters to the existing `sqlite_acquisition.py::ingest_snapshot()` contract or a narrow extension. Preserve its bounded libSQL batches and explicit complete_snapshot/valid_snapshot/closure_safe controls; never pass a partial adapter batch as a complete company snapshot.
- Test a company larger than the existing 25-row libSQL batch size: only a validated final complete source inventory may authorize absence evaluation. Losing/retrying the final batch cannot close unseen-but-still-active jobs.
- Partial-source success can publish validated jobs without waiting for the other source; a failed source cannot replace the entire live catalog with an empty snapshot.

Verify: end-to-end fixtures for same/different jobs, foreign employer, invalid apply URL and partial failure. User result: collected jobs become usable product inventory.

### RC-010 — Demonstrate the first complete acquisition-to-user slice

Priority P0 · Size M · Dependencies: RC-009 · Owner: QA/backend.

Target branch: `deployment/render-turso-r2`.

Scope: one verified dual-ready employer, both collectors, durable ingestion and the actual frontend in isolated staging. Start with recorded/synthetic transport; add a bounded live case only when authorized.

Acceptance:

- An administrator can trace master row → canonical ID → both source scans → observations → published job → user Jobs page.
- A second user browsing the same jobs triggers zero new acquisition requests. Normal Jobs GETs stay read-only for acquisition.
- A deliberately failed collector leaves the other source's accepted result and prior catalog available with truthful source status.
- Replaying completed input does not duplicate published jobs or create new company IDs.
- Record UI walkthrough/screenshots, task IDs, counts and verification commands. No bulk catalog or VPS rollout is required to prove this milestone.

User result: visible evidence that the planned architecture actually connects the new scripts to Runr.

### RC-011 — Make employer coverage and zero-job statuses truthful

Priority P0 · Size L · Dependencies: RC-001, RC-007 · Owner: acquisition.

Target branch: `deployment/render-turso-r2`.

Scope: fix outcome classification, pagination, duplicate input handling and browser fallback decisions before increasing concurrency.

Acceptance:

- Distinguish complete-with-jobs, confirmed-zero, partial, failed, unsupported, blocked and skipped; preserve a mapping to existing stored statuses.
- A timeout, challenge, failed detail request, pagination cap or parser failure cannot become confirmed-zero.
- Nonempty HTTP/JSON results suppress browser fallback only when there is evidence extraction is complete; partial results can continue through fallback.
- Every eligible company/source receives a coverage record including detected ATS, discovered targets, extraction methods, counts, stop reason and completeness evidence.
- Resume does not permanently skip historical unverified `no_jobs` rows. Stale negative results and unsupported sources have explicit recheck policies.
- Audit the existing 428 company-state records before reuse. Report migration/recheck disposition for 194 no_jobs, 146 discovery_failed, 82 partial and 5 source_failed records; one completed record does not establish master-list coverage.
- Preserve the 2,612 existing observations with original timestamps/provenance while revalidating; do not delete legacy jobs simply because their parent scan is uncertain. Per-company rechecks consume a bounded separate recovery budget.

Verify: multipage ATS, static/embedded data, challenge pages, true zero and interrupted scans. User result: “no jobs” has an evidence-backed meaning.

### RC-012 — Add bounded employer concurrency and real request accounting

Priority P1 · Size L · Dependencies: RC-002, RC-011 · Owner: acquisition.

Target branch: `deployment/render-turso-r2`.

Scope: separate lightweight HTTP work from limited browser work; introduce backpressure and a safe persistence writer. Tune from benchmarks rather than fixed optimistic thread counts.

Acceptance:

- Multiple companies can progress concurrently, while per-origin and proxy/account limits are enforced across relevant worker roles.
- Browser processes, request queues, pending results and memory are bounded; SQLite connections are not unsafely shared across threads.
- Each actual request/attempt, fallback and browser navigation is counted at transport level, not inferred from job counts.
- Faster runs meet the agreed RC-002 coverage/correctness threshold and peak-memory limit; failed/partial results do not increase silently.
- A single stalled company cannot prevent every other company checkpointing; shutdown flushes or safely replays outstanding batches.

Verify: deterministic delayed transports and identical-input before/after benchmark. User result: useful parallel speedup without extra proxy spend from uncontrolled retries.

### RC-013 — Correct LinkedIn scan outcomes and job lifecycle

Priority P0 · Size L · Dependencies: RC-001 · Owner: acquisition.

Target branch: `deployment/render-turso-r2`.

Scope: inspect and fix stale pagination counters, scan completion, ownership classification, run timestamps and recovery partitions in the actual 14-table producer.

Acceptance:

- A scan that found eligible jobs cannot end as confirmed-zero because a local counter lagged; outcome derives from validated complete scan evidence.
- Saturated, repeated, challenged, malformed, capped and interrupted pages retain partial/blocked status; recovery partitions do not fabricate completeness.
- Existing card/detail ownership and verified-alias checks remain intact; shared organization IDs never assign jobs arbitrarily to the first canonical employer.
- Inactivation requires the existing two distinct complete qualifying scans, with stable scan IDs. Retry/replay of one scan cannot count as two absences.
- Run records have terminal status and finish time; incomplete outcomes and pending recovery are explicit in metrics.
- Repeated SUSPICIOUS_EMPTY responses cannot themselves prove zero inventory or complete pagination. Preserve uncertainty even when prior accepted jobs exist; test both empty-first and empty-after-nonempty paths.
- Run a read-only legacy consistency audit with explicit scan/observation keys before enabling expiry. Reconcile 8,575 recorded zero scans and 23,926 suspicious-empty pages without asserting that every one is false. Ambiguous legacy scans cannot supply qualifying absence evidence until revalidated.
- Each of the 576 historical RETRY detail rows receives a due/terminal/quarantined disposition with attempt budget and actual next retry time. A run with pending retries can be terminal as partial/finished-with-pending, but cannot claim all details complete.
- Account for the 312 pending aliases and 7,381 alias-related exclusions through a bounded verification queue. Approval preserves supporting organization/URL evidence; mismatch or uncertainty stays excluded. No global allow-all-alias flag is introduced to inflate coverage.

Verify: relevant producer tests plus empty-after-nonempty pagination, replay, partial and ownership-conflict fixtures. User result: jobs do not vanish because a scan failed or was misclassified.

### RC-014 — Make LinkedIn detail refresh economically incremental

Priority P1 · Size M · Dependencies: RC-013 · Owner: acquisition.

Target branch: `deployment/render-turso-r2`.

Scope: reuse active unchanged details across daily cycles. Separate durable description refresh from volatile applicant/freshness fields where feasible. A new policy must state what stale data users will see.

Acceptance:

- New jobs and changed card/detail evidence enqueue refresh; unchanged fresh jobs reuse cached details.
- A once-daily schedule does not accidentally invalidate essentially the whole catalog merely because refresh defaults equal 24 hours.
- Expired details, errors and volatile fields have explicit bounded refresh schedules; stale applicant counts retain observation timestamps.
- Record cache hits, refresh reasons, avoided requests and actual credits/cost; retries do not reset freshness as if successful.
- Source disappearance checks continue independently of whether detail content was reused.

Verify: simulated time, unchanged/changed cards and failure fixtures; compare request counts with the same job population. User result: daily updates cost proportionally to changes rather than repeated full-detail collection.

### RC-015 — Fix LinkedIn transport reuse, adaptive limits and storage throughput

Priority P1 · Size L · Dependencies: RC-002, RC-013 · Owner: acquisition.

Target branch: `deployment/render-turso-r2`.

Scope: reuse sessions safely per worker/proxy, enforce real dynamic request limits, persist useful proxy health, batch DB writes and stream exports without losing acknowledged work.

Acceptance:

- Persistent sessions are closed cleanly and do not leak cookies/auth across unrelated proxy identities.
- Rate limiting lowers actual in-flight work through a limiter/dispatcher; changing a number with unchanged active pools does not satisfy acceptance.
- Effective concurrency respects the account's verified limit, including shared consumption by both collectors; provider-specific limits remain distinct.
- Include company enrichment/resolution in shared account accounting. A one-request-per-proxy setting is not evidence that the account allows one total connection, nor that ten proxies authorize ten simultaneous requests.
- Proxy health records requests/success/blocks/rate limits and cooldowns without recording credential-bearing URLs.
- Database transactions and raw JSON retention are bounded; full LinkedIn export does not materialize the entire catalog into a Python list. A crash before a batch commit remains safely replayable.

Verify: rate-limit/proxy-switch fixtures, actual in-flight counters, large-state export and before/after memory/throughput results. User result: stable throughput with visible proxy economics.

### RC-016 — Schedule source cycles with durable ownership and replay safety

Priority P0 · Size L · Dependencies: RC-011, RC-013 · Owner: backend/acquisition.

Target branch: `deployment/render-turso-r2`.

Scope: extend current scheduler/task machinery to the new producer adapters. One server-owned 24-hour UTC cycle policy; one owner per source/company shard. Keep regular users unable to launch acquisition.

Acceptance:

- Schedule keys include manifest version and scope/source identity as needed without permitting duplicate daily work; manual admin recovery is separately audited.
- Durable task claim, heartbeat, expiry and fencing reject stale workers' publication or completion after ownership changes.
- A cycle longer than its interval follows an explicit skip/coalesce policy; no unlimited backlog of duplicate full scans.
- Checkpoint/retry/task IDs survive restarts and preserve per-source lifecycle semantics; transient failures use capped exponential backoff/jitter and retry budgets.
- Global and per-source kill switches prevent new external requests promptly; one paused source does not block the other or customer tasks.
- Reconcile the 11,907 reported numeric organizations with 11,896 stored source groups by an explicit input-to-loader report. Scan count 11,921 spans two runs and cannot substitute for a unique-current-organization denominator. Explain deltas as excluded, unprocessed, historical or unknown; do not manufacture missing tasks from aggregate subtraction alone.

Verify: two workers racing, lease loss, schedule overlap, repeated dispatch, restart and kill-switch cases. User result: daily collection runs once as intended and recovers without duplicate work storms.

### RC-017 — Preserve source evidence and make publication/expiry safe

Priority P0 · Size L · Dependencies: RC-009, RC-011, RC-013, RC-016 · Owner: data/backend.

Target branch: `deployment/render-turso-r2`.

Scope: distinguish source-specific activity from canonical public-job activity. Stage and validate batches, then publish with receipts/version checks. Make download snapshots independent of authoritative catalog state.

Acceptance:

- Failure/partial coverage in one source never closes all jobs attributed to that source. Removing a company from the input manifest is a separate administrative lifecycle event.
- A canonical job active on a verified employer source is not hidden solely because its LinkedIn observation becomes inactive; aggregate activity rules are documented.
- Duplicate batches, old scan results and stale worker writes cannot regress a newer job version or publication.
- CSV/JSONL/metrics belong to an immutable generation with manifest/hash. Readers see a complete generation via one small pointer/manifest transition; abandoned generations are recoverable or collectible.
- Source exports retain distinct rows/provenance even when the public catalog merges duplicates. Downloads can fail without discarding durable accepted jobs.

Verify: competing versions, one-source expiry, checkpoint replay and crash during export publication. User result: stable job visibility and coherent downloadable snapshots.

### RC-018 — Split customer and acquisition worker roles

Priority P0 · Size L · Dependencies: RC-001; agreed role/claim contract, with RC-016 required for integrated acquisition scheduling · Owner: backend.

Target branch: `deployment/render-turso-r2`.

Scope: add explicit allowed task families/roles to current worker entrypoints and claims. Keep one codebase and reuse existing run execution.

Acceptance:

- Customer workers never enter scheduled acquisition/company enrichment/admin imports; acquisition workers never claim customer document/email tasks.
- Role selection is applied at claim time, not after consuming an inappropriate task. Worker IDs are unique per process/host.
- Role filtering can be implemented and tested against existing queues before RC-016 finishes. Final acquisition release requires the RC-016 scheduler and RC-018 roles to pass together; the shared worker entrypoint has one code owner during both changes.
- Customer capacity is reserved through separate processes and resource limits; a busy scraper cannot take all CPU/RAM/browser slots.
- Worker heartbeats expose role, version, capacity and active-task information sufficient to detect a missing role.
- An old/default worker cannot silently run both role sets during rollout; compatibility/migration behavior is documented and tested.

Verify: queued mixed task families under a continuously busy acquisition fixture. User result: uploading a CV does not wait for the daily scraper to finish.

### RC-019 — Repair intelligence claiming, recovery and input-version handling

Priority P0 · Size L · Dependencies: RC-018 · Owner: backend.

Target branch: `deployment/render-turso-r2`.

Scope: bring the separate intelligence queue up to safe recovery standards; verify how description/match precompute is actually triggered. Avoid loading newer inputs and saving results under an older cache key.

Acceptance:

- A killed processing task is recoverable after a lease timeout with bounded attempts; two workers cannot both own the same attempt.
- Successful conditional claim is verified; completion/failure is fenced to the current owner/attempt, and returned status matches persisted status.
- Task inputs identify immutable job/profile/CV/evidence versions. Changed inputs either use their correct version or supersede/requeue the task under a new key.
- Publication/profile-change or explicit authorized workflow reliably schedules needed precompute. A missing cache cannot remain pending forever solely because no production enqueue caller exists.
- Precompute is bounded to a documented candidate set; do not introduce users × entire catalog model work. Read-only Jobs requests continue not to trigger acquisition/model execution.

Verify: crash, competing claim, stale completion, profile-change-during-task and new-user/new-job lifecycle tests. User result: scores/document tasks finish or fail truthfully and correspond to the user's actual inputs.

### RC-020 — Queue remaining slow public-request operations

Priority P1 · Size L · Dependencies: RC-018, RC-019 · Owner: API/backend/frontend.

Target branch: `deployment/render-turso-r2`.

Scope: move verified inline email-sync and bulk-export work, plus any other measured heavy route, into the customer role. Preserve fast UI updates and existing entitlements.

Acceptance:

- Public requests authorize/validate, persist a task and return task ID/status promptly against the RC-002 target; they do not perform the long operation inline.
- Duplicate clicks/retries do not create duplicate logical work, charges or concurrent destructive email-state updates.
- The frontend displays queued/running/complete/failed states, survives reload and stops polling terminal jobs with bounded backoff while pending.
- Only the owning user can read/download results; provider-token refresh and cancellation behavior are tested.
- Slow tasks are moved one route at a time with compatibility and rollback; no unrelated API rewrite is required.

Verify: E2E email test double and multi-document export, two-user isolation and lost response/retry. User result: responsive pages while work continues on the VPS.

### RC-021 — Make artifacts portable and reduce Render file traffic

Priority P1 · Size M · Dependencies: RC-020 · Owner: storage/API.

Target branch: `deployment/render-turso-r2`.

Scope: use existing private object storage and signed-download support for eligible files; make local caches disposable and bounded. Review upload paths separately before choosing direct signed uploads.

Acceptance:

- A document created on worker host A is available through Render with an empty local cache; no shared filesystem path is assumed.
- Authorization precedes short-lived signed URLs. Expired links, cross-user access and unapproved MIME/size cases are rejected appropriately.
- Eligible downloads go directly to object storage, avoiding API whole-file memory loading and egress; report bytes shifted from Render.
- Browser/extension fetch behavior, CORS, filenames and download UX work with the chosen redirect/URL contract.
- Cache retention/disk caps and immutable object keys prevent stale-content reuse and unbounded accumulation; a missing local cache never means lost final data.

Verify: two-host simulated storage test, large file download, expired URLs and empty-cache restart. User result: lower file-delivery overhead with the same document access experience.

### RC-022 — Separate builds, releases and staging contracts

Priority P1 · Size M · Dependencies: RC-018, RC-020 · Owner: deployment/frontend.

Target branch: `deployment/render-turso-r2`.

Scope: separate API/worker Docker targets as dependencies permit; remove redundant frontend builds; add accurate deployment filters and version compatibility checks.

Acceptance:

- Frontend, API and VPS worker releases use selected commits on deployment/render-turso-r2, with branch/commit recorded in release metadata; no worker build depends on uncommitted source in another worktree.
- A frontend-only commit deploys the frontend without restarting acquisition/customer workers; required shared-contract changes still trigger all affected checks.
- API image excludes browser/OCR/office dependencies only after route tracing proves they are no longer required.
- New worker capabilities deploy before their frontend flags turn on; previous client/worker schema versions coexist through rollout.
- Database migrations have one designated release owner, backward-compatible sequencing and rollback limits; multiple workers cannot concurrently run unsafe migrations.
- Staging has isolated data, queues, object access, billing/email targets and analytics. A preview cannot consume production work.

Verify: path-filter change matrix, image-content check and mixed-version E2E staging run. User result: quick frontend iteration while acquisition continues undisturbed.

### RC-023 — Provision a reproducible VPS runtime

Priority P0 · Size M · Dependencies: RC-002, RC-018 · Owner: operations.

Target branch: `deployment/render-turso-r2`.

Scope: select a monthly trial machine from measured resource needs and create reproducible worker deployment with Docker/Compose or the existing systemd approach. Choose one primary operational mechanism; avoid Kubernetes at this stage.

Acceptance:

- Document expected resource headroom, region relative to Turso, disk/checkpoint budget, final VAT/add-on price and provider limits before purchase authorization.
- OS/runtime and dependency versions are pinned reproducibly; Python 3.12.7 policy versus container/Linux behavior is explicitly reconciled.
- Workers run as non-root with protected credentials and role-appropriate access; unnecessary inbound application ports remain closed. No public scraper API is required.
- Browser/collector processes do not inherit customer OAuth/document credentials. Use read/write permissions scoped to the chosen worker boundary and verify effective provider granularity; if shared full-database credentials remain necessary, record and address the residual blast radius before customer workload cutover.
- Updates, service restart, unique worker identity, time synchronization, log rotation and CPU/memory/process limits are configured and documented.
- Setup from a clean replacement server restores the same approved worker release without relying on the laptop staying online.

Verify: clean-host setup, service restart, port check and synthetic worker task. User result: an always-on machine that can be replaced reproducibly.

### RC-024 — Checkpoint, restore and protect single-owner scraper state

Priority P0 · Size L · Dependencies: RC-015, RC-016, RC-023 · Owner: acquisition/operations.

Target branch: `deployment/render-turso-r2`.

Scope: protect existing local producer state without rewriting all of it into remote tables. Define shard ownership, checkpoint generation, restore and local backlog limits.

Acceptance:

- Consistent SQLite backups use an appropriate backup/checkpoint mechanism, not a copy of a changing main DB without WAL consistency.
- Checkpoints carry schema, source version, manifest, cycle/shard and high-water marks; no secrets/browser profiles are included.
- Restore on another host meets the RC-002 recovery objectives; replay produces no duplicate publication, false second absence or loss of accepted artifacts.
- No two machines write the same logical state shard concurrently; expired ownership fences publication from a resumed old host.
- Database/object outage causes bounded local buffering and safe pause/backpressure before disk exhaustion. Required receipts are durable before acknowledging publication.
- Measure backup duration/bytes against the existing 3.48 GB LinkedIn state before selecting cadence. Six-hour full copies alone would transfer about 13.9 GB/day before compression, other state and growth; copying this DB every few minutes is not an acceptable unmeasured default.
- Bound local export/backup generations and remote retention; include temp-file space at peak. Preserve compact terminal receipts and identity/absence evidence needed for replay even when pruning verbose request payloads.

Verify: kill during collection/backup/upload, lost disk, restored checkpoint and competing owner tests. User result: a VPS failure requires recovery, not starting the whole catalog from scratch.

### RC-025 — Add operational visibility and a company coverage dashboard

Priority P1 · Size L · Dependencies: RC-005, RC-016, RC-018, RC-019 · Owner: backend/frontend/operations.

Target branch: `deployment/render-turso-r2`.

Scope: extend existing admin data and structured logs. Record user-relevant operational outcomes rather than installing overlapping monitoring products by default.

Acceptance:

- Each company/source shows eligibility, last attempt/success, scan completeness, jobs observed/accepted/published/rejected, stop reason, freshness and next action.
- Dashboard totals distinguish master rows, unique employers, organization scan groups and source tasks; counts reconcile without double-counting.
- Show the baseline 17,601 rows, 7,513 existing master IDs, 10,088 missing-ID rows and evidence-verified eligibility as separate measures. Include identity-review, alias-review, negative-result recheck and due-retry backlogs without calling blocked companies zero-job companies.
- Customer queue age, processing duration, failure/retry count, worker heartbeat age, DB latency, disk/RAM and provider throttling are visible by role/version.
- Alerts identify missing workers, stale coverage, stuck tasks and spend/retention limits. “Online” uses heartbeat freshness, not merely a stored idle/running label.
- Admin retry/pause/recovery actions are authorized, scoped and audited; a normal user cannot trigger collection. Logs redact credentials and customer document/email contents.

Verify: offline worker, stale task, partial company and unknown-cost fixture states in the UI. User result: failures and actual coverage can be understood without reading raw logs.

### RC-026 — Benchmark full-sized state and tune costs

Priority P1 · Size M · Dependencies: RC-012, RC-014, RC-015, RC-021, RC-024, RC-025 · Owner: performance/operations.

Target branch: `deployment/render-turso-r2`.

Scope: replay representative workload sizes and then execute authorized bounded live samples. Tune worker/browser limits, batch sizes, indexes, caching and checkpoint frequency from observed bottlenecks.

Acceptance:

- Compare equivalent inputs before/after with coverage preserved. Report median and tail task times, peak RAM/disk, requests and actual/estimated costs.
- Existing large-state shapes are represented without loading all records into memory; report whether real local public-job state or synthetic scaling was used.
- Customer workload meets its agreed target while acquisition is active; admitted concurrency and resource ceilings match observed limits.
- Turso connection/transaction contention and billed reads/writes are measured before proposing a replacement database/queue.
- Monthly cost model separates fixed hosting, storage, build traffic, proxies, AI/OCR and analytics; include expected and adverse retry scenarios, not an invented flat user-capacity promise.
- Include the temporary overlap bill while Render customer workers remain active, operator recovery effort and backup bandwidth/operations/retention. Claim compute savings only after replaced services actually stop billing; acquisition on a VPS alone does not necessarily lower the current Render bill.

User result: evidence for the smallest sufficient VPS and the true cost per usable job/document.

### RC-027 — Run a controlled staging pilot with both real sources

Priority P0 · Size M · Dependencies: RC-010–017, RC-019, RC-022–026 · Owner: QA/acquisition.

Target branch: `deployment/render-turso-r2`.

Scope: select verified fully enriched companies covering relevant ATS and LinkedIn patterns. Declare the exact list and budget before network authorization.

Acceptance:

- Both collectors execute independently on VPS workers and publish through the integrated staging path; there are no manual CSV-copy steps required for product visibility.
- Independently checked employer/LinkedIn samples establish a dated coverage denominator. Compare the same country/filter scope and account for dynamic postings.
- Every planned source task has a result/reason; unresolved failures remain visible and do not masquerade as zero jobs or 100% coverage.
- A second cycle demonstrates incremental detail reuse, unchanged stable IDs and safe expiry rules; a frontend release during acquisition does not interrupt it.
- Reboot/worker-kill and source-outage drills preserve accepted data and meet recovery criteria; all business-analyst journeys below pass.

User result: a real, bounded demonstration before the full master list or production users depend on it.

### RC-028 — Cut over the paid worker workload with rollback

Priority P0 · Size M · Dependencies: RC-027 · Owner: release/operations.

Target branch: `deployment/render-turso-r2`.

Scope: migrate explicitly selected production task families after production authorization. Gate A releases integrated acquisition on the VPS while retaining customer processing on Render; Gate B later moves approved customer task families after their own role/recovery/load gates pass. Keep Render frontend/API; avoid double scheduling across old and new workers. Gate A may proceed with acquisition-relevant portions of RC-027 accepted and customer migration deferred; it cannot claim customer gates passed.

Acceptance:

- Record live revisions/settings, queue state and recovery points immediately before cutover; disable/drain old owners for the selected roles before enabling new ownership.
- New tasks and in-flight tasks have a documented owner throughout; no simultaneous old/new acquisition cycle or customer duplicate charge occurs.
- Verify real authorized user journeys, catalog freshness and external provider budgets during an agreed observation window.
- Rollback restores the compatible Render worker/previous image and task ownership without restoring an old database over newer customer writes.
- Only after acceptance is the replaced Render worker stopped/removed from billing under separate authorization; report actual bill changes.
- If acquisition already runs only on the laptop, do not invent a Render acquisition worker to drain. Inspect live owners, disable only competing schedules that exist, and measure added VPS cost separately from displaced customer-worker cost.
- Gate B has a written outage policy: either the measured single-host recovery delay is acceptable, or another compatible worker remains available within the cost ceiling. Resource reservations on one VPS do not satisfy two-host continuity.

User result: lower hosting overhead while the public app stays on Render.

### RC-029 — Expand to the full eligible master list in controlled waves

Priority P1 · Size L · Dependencies: RC-005, RC-026, RC-028 Gate A; RC-006 for companies needing new enrichment · Owner: acquisition/operations.

Target branch: `deployment/render-turso-r2`.

Scope: increase from pilot to bounded batches and then the complete eligible population. Wave size follows measured request/credit limits and capacity, not a fixed promise.

Acceptance:

- Each wave declares manifest version, unique employers, organization groups, source tasks, request/cost caps and stop conditions.
- Full-list coverage reconciles every eligible company/source, including partial, failed, unsupported and deferred work. Coverage and acceptance rates are reported separately.
- Customer targets remain met; queue growth, failure rates or budget breach automatically pause expansion without discarding accepted results.
- A new daily cycle reuses unchanged work; newly enriched companies join subsequent manifests. Backfills have an explicit budget separate from routine daily updates.
- Document the residual unsupported ATS/site backlog from evidence. “All companies attempted” is not reported as “all jobs collected.”
- Expand the reviewed portion of the 1,666 dual-field-ready rows first, then approved mappings from the 4,371 identity-first rows. Continue independent enrichment cohorts afterward; unresolved rows remain accounted for and do not block every ready company.

User result: full catalog operation with an honest view of remaining coverage gaps.

### RC-030 — Connect product analytics to customer outcomes

Priority P2 · Size M · Dependencies: RC-022, RC-025 · Owner: product/frontend/backend.

Target branch: `deployment/render-turso-r2`.

Scope: audit current Firebase and internal event pipelines, then choose whether they suffice or need an additional product-analytics/replay tool. Keep analytics independent from hosting migration success.

Acceptance:

- Track signup → usable profile → relevant job → saved/prepared application → confirmed outcome, with backend-confirmed completion separated from button clicks.
- Join non-sensitive task IDs, latency bands, versions and failure categories to feature usage so waiting/failures can be distinguished from poor job relevance.
- Deduplicate events and separate internal, staging and production traffic. Check existing events actually arrive before introducing replacements.
- Document allowed fields, consent behavior, sampling, retention and spend caps; exclude CV/email/credentials and sensitive form contents from analytics/replay.
- Deliver dashboards answering which step loses users, which feature drives return use, and whether slow processing hurts completion; include a feedback mechanism for reasons analytics cannot infer.

User result: product decisions based on successful outcomes and customer feedback, not merely more tracking.

### RC-031 — Add horizontal worker capacity and failure continuity when triggered

Priority P2 · Size L · Dependencies: RC-024, RC-026, RC-028 · Owner: operations/backend.

Target branch: `deployment/render-turso-r2`.

Scope: add a second host or more source shards only when queue-age/recovery targets require it. This is the path beyond one VPS; it is not assumed to be free or required on day one.

Acceptance:

- Scaling is triggered by agreed queue age, missed cycle deadline, saturation or customer-availability requirements, with a maximum cost ceiling.
- Shards do not overlap canonical/source ownership or split one shared LinkedIn organization incorrectly. Rebalancing has an explicit checkpoint and handoff.
- Two-host claim/publication races and host loss are tested. Remaining customer capacity meets the chosen degraded-service target.
- Adding acquisition workers does not multiply provider limits, full-catalog scans, migrations or scheduler ownership.
- If DB contention is the bottleneck, measure and propose the smallest remedy separately; do not assume more VPS cores solve it.

User result: scaling by adding measured capacity without redesigning the product or losing ownership guarantees.

### RC-032 — Operational handover and final acceptance

Priority P1 · Size M · Dependencies: RC-028, RC-029; RC-030/031 only if enabled · Owner: operations/product.

Target branch: `deployment/render-turso-r2`.

Scope: document day-to-day operation, recovery, releases and cost controls in one current runbook. Do not make optional analytics or second-host work a hidden blocker for core migration.

Acceptance:

- Runbook explains add/review a company, resolve missing identity, inspect failed source, pause/retry safely, release frontend/worker, replace VPS, restore state and roll back.
- Actual deployed component versions, source manifest, role ownership and schedules are recorded; credentials are referenced by name only.
- Required tickets have evidence; deferred work has an owner, reason and measurable trigger. No inaccurate zero/completion status is accepted as a known cosmetic issue.
- Compare observed monthly-cost projection with the original Render baseline and explain savings, added costs and uncertainty.
- User can complete the business-analyst acceptance walkthrough without code knowledge. No further work is marked complete solely because infrastructure is running.

Verify: review the release evidence against every enabled gate and complete the runbook walkthrough. User result: an operable service with a known monthly cost, recovery procedure and explicitly owned remaining work.

## Business-analyst acceptance walkthrough

These are the release journeys, not optional unit-test substitutes. Use synthetic/private staging data first; live/prod steps require explicit scope and authorization.

| Journey | Action | Observable pass condition | Main tickets |
| --- | --- | --- | --- |
| Missing company ID | Import a master row with no Runr ID | Stable ID/provisional mapping appears; repeated import keeps it; conflicting identity is reviewed | 003–005 |
| Company becomes ready | Supply verified missing website/LinkedIn evidence | Eligibility updates and the next cycle includes the company without rescraping everything | 005–006 |
| Both source paths | Run a dual-ready employer in staging | Source counts and provenance are visible; valid jobs appear on the same user Jobs page | 008–010 |
| One source fails | Make LinkedIn unavailable during employer collection | Employer output/publication succeeds; LinkedIn displays a failure/partial status, not zero | 007, 011, 017 |
| Same job twice | Deliver the same batch and matching source observations repeatedly | No duplicate logical job or lost source evidence; ambiguous jobs are not overmerged | 008–009, 017 |
| Daily refresh | Repeat the cycle with unchanged jobs | Existing details are reused, scans are accounted for and freshness dates remain truthful | 013–016 |
| Worker interruption | Kill the process while a task runs | Accepted work survives and recovers; no task remains silently stuck and no stale result wins | 016, 019, 024 |
| Customer responsiveness | Upload a CV while acquisition is busy | Processing starts/completes within the agreed target and result is downloadable | 018–021, 026 |
| Frontend release | Deploy a UI-only change during acquisition | UI updates; collector task ownership/progress continues | 022, 027 |
| Replaced server | Restore onto a clean host | Correct release/checkpoint resumes within agreed recovery limits | 023–024 |
| Full-list accounting | Open the coverage dashboard after a wave | Every eligible source task is accounted for and incomplete coverage is explicit | 025, 029 |
| Production rollback | Revert worker routing/version in an authorized drill | Public app remains usable and new customer data is not overwritten | 028 |

## Release gates and cost discipline

Before any broad live run: confirmed producer, canonical mappings, bounded manifest, truthful coverage, independent source exports, duplicate-safe publication, request budgets and kill switches. Before customer tasks move: separate roles, recovery/fencing, portable artifacts, staging compatibility and completed interruption tests. Before full expansion: measured workload capacity and reconciled pilot coverage.

The following are proposed initial acceptance targets, not measured capabilities or provider limits. RC-002 must freeze them, or justify replacements, before RC-026/027. Workload mix/concurrency, task-type completion budgets, proxy/account quotas and the monthly spending ceiling must be supplied from actual usage and pricing before a cost/capacity gate can pass. An unset cost ceiling is not unlimited authorization.

| Measure | Proposed pilot gate | Failure behavior / qualification |
| --- | --- | --- |
| Routine acquisition schedule | One 24-hour UTC policy; target finish within 20 hours, hard cycle deadline 24 hours | Coalesce/skip overlapping full cycles; expose missed/deferred sources rather than build duplicate backlog |
| Published source freshness | Alert when an enabled source has no qualifying success for 48 hours | Keep freshness visible; do not mass-close jobs because a source is unavailable |
| Fast API/status responsiveness | p95 at most 1 second at the frozen representative customer load, while acquisition is active | Exclude bulk file transfer and asynchronous execution; report endpoint-specific results and any existing baseline failure |
| Priority customer queue wait | p95 at most 30 seconds at the frozen admitted load | Measure OCR/document/email/intelligence classes separately; defer customer cutover if capacity is insufficient |
| Customer completion time | Freeze per task type from existing behavior and product need in RC-002 | AI/provider latency is not controlled by VPS core count; no single invented completion target for all tasks |
| Accepted publication/customer results | Zero loss in worker/host failure and replay drills after durable acknowledgment | This covers VPS failure; it is not a claim of zero-loss managed-provider disaster recovery |
| Scraper recovery | Recreate worker and resume from verified checkpoint within 60 minutes in the replacement-host drill | Requires available replacement capacity and credentials/runbook; retain customer worker elsewhere if unacceptable |
| Local-only scraper checkpoint age | Initially at most 6 hours during active collection, with at most 6 hours of local-only rework after disk loss | Managed receipts/accepted jobs remain durable; shorten cadence or add durable deltas if measured replay exceeds the cycle deadline |
| Sustained worker pressure | At least 25% RAM headroom at frozen load; disk reserve exceeds the largest measured temporary export/backup plus bounded outage buffer | Pause new acquisition before capacity exhaustion; do not count swap as a remedy for uncontrolled browser load |
| Logical correctness | Zero duplicate logical publications, zero cross-user access, zero identity changes on replay/reorder, zero false absence increments in failure fixtures | Any failure blocks the affected release |
| Provider protection | Honor verified account ceilings; initial circuit proposal: at least 50% blocked/rate-limited responses after 20 attempts in a rolling five-minute window opens a 15-minute cooldown, then one probe | Honor longer Retry-After; do not wait for the sample threshold to honor individual throttling; thresholds are tunable downward to actual limits |
| Resolver retries | Initial proposal: at most 10 outbound attempts per unresolved URL per rolling 24 hours across restarts and transports, plus separate account/credit limits | A URL remains unresolved when exhausted; no identity guessing or alternate unbounded invocation |
| Monthly total cost | A numeric user budget and expected/adverse scenario must be recorded before purchase/live scale | Include temporary Render/VPS overlap and provider/backup/operations costs; fail the economic gate if total cost does not meet the agreed goal |

The checkpoint and retry values are deliberately explicit planning defaults so tests can be written against a real policy. They may change after measurement, with the reasons recorded before acceptance. Quality and ownership checks are hard correctness requirements, not thresholds to weaken to hit a speed target.

Expected economic changes: replace Render worker compute; reduce repeated frontend/backend image builds; shift eligible file bytes to object storage; reuse unchanged scraper details; avoid duplicate company scans and excessive retries. Costs retained: Render API/static-site usage, database, storage operations, proxy/API/AI/OCR, backup/monitoring and operational effort. A VPS improves hosting economics only if measured total cost and reliability meet the frozen targets.

## Appendix A — Supplement disposition and first implementation handoff

The requested supplement has been received and reviewed. Do not rerun the old export prompt. The current plan remains 32 stable ticket IDs; revised scope and acceptance criteria supersede version 1.0. No ticket is marked implemented by receipt of an evidence archive. Version 2.1 mandated deployment/render-turso-r2 and source consolidation in RC-001; version 2.2 retains that integration target and allows isolated parallel implementation with one integration owner.

| Evidence question | Current disposition | Where the remaining check belongs |
| --- | --- | --- |
| Actual default local input/header/counts | Established by detailed reports and MASTER_SUMMARY.json; raw full CSV intentionally absent | RC-001 reproduces against local input/hash and verifies actual invocation |
| Missing-ID/field-readiness scale | Established as reported aggregates; full matrix sums to 17,601 | RC-003–005 turn presence counts into reviewed entity mappings and verified eligibility |
| Existing source-state shapes and historical backlog | Established by DB_AGGREGATES.json; no full DB or live benchmark provided | RC-002 baseline; RC-011/013 audit; RC-024/026 recovery/performance |
| Latest employer/export changes | Candidate source and three dirty export files present; preserve work | RC-001 consolidation on deployment/render-turso-r2, RC-007 independent exports |
| Actual LinkedIn implementation | Source in earlier hosting ZIP; supplement reports original hash but omits implementation | RC-001 verifies real local bytes and selected source before changes |
| Master IDs equal application IDs | Not established; app identity namespace and mapping boundary exist | RC-003 crosswalk, no blanket ID replacement |
| Shared-organization ownership | 37 groups reported; observation-level correct mapping not proven | RC-003 review and RC-013 ownership/alias tests |
| Producer-to-public Jobs integration | No verified adapter path | RC-008–010 implement and demonstrate it |
| Production revision/service sizes | Unverified | RC-022 release inventory and RC-028 pre-cutover checks |
| Provider quotas, actual monthly costs, customer concurrency | Unverified | RC-002/023/026; no external login or paid run assumed |

### Start with a bounded, useful first slice

1. **Complete RC-001 on deployment/render-turso-r2.** Inspect applicable instructions and the existing target worktree; use the mandated environment. Confirm producer/input hashes, counts and existing exporter changes. Write BASELINE_AND_INPUT_CONTRACT.md and ACQUISITION_SOURCE_TRANSFER.md. Bring useful acquisition/identity/enrichment scripts and required helpers/tests into the deployment branch, adapting to its current backend. Validate offline from that worktree. Preserve feature/admin-analytics-final-production and the producer worktree as source references; do not resolve unrelated branch divergence.
2. **Prepare RC-003/004/005 offline.** Build the reviewed identity mapping and non-destructive dry-run/eligibility path against existing repository conventions. Select representative cases from the local master: already valid, missing ID with all other fields, missing ID with incomplete enrichment, repeated import, two canonical IDs sharing an organization, and conflicting contextual LinkedIn IDs. Full-list dry-run may read the master without applying production changes.
3. **Deliver a reviewable result.** Show counts of retained/matched/new/provisional/quarantined IDs, a versioned manifest, preserved original fields, meaningful tests in the project environment, and one admin-readable before/after example. Do not require a VPS, network scraping, paid enrichment or full production backfill for this slice.
4. **Proceed to RC-007–010 in a separate scoped change.** Preserve export optimizations, add the producer adapters, and show both source fixtures in the real staging Jobs page. Correctness fixtures use fake/recorded transport and do not need to claim that production scraping is complete.
5. **Optimize and operate only after the product path works.** Run source correctness/retry/ownership work, role isolation and recovery. Freeze budgets before any bounded real-source pilot. Purchase/production changes follow their concrete release gates.

Do not issue one instruction to implement and deploy all 32 tickets. Each handoff explicitly names deployment/render-turso-r2 as the integration target, the isolated implementation directory, file ownership, common base snapshot, ticket/slice, source-transfer provenance, allowed actions, observable user result, focused tests, evidence and rollback. Commits/merges/deployments and paid/live collection remain separately scoped actions; follow any authorization already provided rather than requesting it repeatedly.

### Required regression scenarios added by this supplement

| Scenario | Expected observable result | Ticket |
| --- | --- | --- |
| Existing master ID differs from app ID | Stable crosswalk; existing app and master references preserved | RC-003 |
| Missing-ID row already has W/L/I | Identity mapped or allocated without redundant enrichment calls | RC-004 |
| All four fields present but ownership conflicts | Field-ready count includes row; verified-eligible count excludes it with reason | RC-005 |
| Resolver sees several contextual IDs, then one conflicting ID | Remains ambiguous/reviewable unless recorded evidence resolves conflict | RC-006a |
| Repeated unresolved retries through restarts | Persistent request budget and cooldown remain enforced | RC-006a |
| Complete source contains more than 25 jobs | All batches ingested; closure only after validated final inventory | RC-009 |
| Historical employer no_jobs followed by challenge/timeout | Remains unverified/blocked; does not close known jobs | RC-011 |
| LinkedIn two suspicious-empty pages | Partial/uncertain outcome, no confirmed zero or qualifying absence | RC-013 |
| Historical detail RETRY has blank due time | Migrates to explicit bounded due/terminal/review status | RC-013 |
| Shared organization or pending slug alias | No arbitrary first-employer assignment and no bypass of verification | RC-003/013 |
| Same published batch after lost local disk | Receipt replay produces no duplicate jobs or second absence | RC-017/024 |
| VPS down while user browses | Published catalog stays usable; queued compute status is truthful | RC-018/024/028 |

## Appendix B — Evidence references and limitations

References below are paths inside the supplied archives, not instructions to execute the sanitized code.

| Finding | Primary evidence |
| --- | --- |
| Master counts/header/readiness | Supplement MASTER_SCHEMA_AND_COUNTS.md; metadata/MASTER_SUMMARY.json; samples/MASTER_HEADER.txt |
| Historical state counts/statuses/schema | Supplement metadata/DB_AGGREGATES.json; STATE_AND_PERFORMANCE.md |
| Source baselines and dirty work | Supplement SOURCE_PROVENANCE.md; source/*/SNAPSHOT_NOTE.txt; patches/* |
| Master/application ID separation | Supplement source/primary/backend/domain/company_identity.py and backend/repositories/sqlite_acquisition.py |
| Cleaner ID generation | Supplement source/primary/scripts/clean_master_company_url.py::canonical_id |
| Resolver reuse, attempts and conflict path | Supplement source/primary/scripts/run_linkedin_company_id_resolution.py::run and ::resolve_one |
| Actual LinkedIn loader, suspicious empties, run finish | Hosting ZIP source_snapshots/02_render_candidate/source/scripts/master_linkedin_jobs_catalog.py::load_source_company_groups, ::_scan_company, ::finish_run |
| Employer export dependency and streaming slice | Supplement source/render_candidate/scripts/master_employer_jobs_catalog.py::export_catalogs_from_state and ::export_only; scripts/build_master_jobs_catalog.py |
| App publication batches and closure controls | Supplement source/primary/backend/repositories/sqlite_acquisition.py::ingest_snapshot |
| Worker roles/general and intelligence recovery | Hosting ZIP source_snapshots/02_render_candidate/source/backend/worker/service.py; backend/application/run_services.py; backend/repositories/sqlite_personalized_jobs.py |
| Remaining API work and object retrieval | Hosting ZIP source_snapshots/02_render_candidate/source/backend/api/routes/tracker.py, documents.py; backend/api/server.py; backend/storage/s3.py |
| Render build/service configuration | Hosting ZIP source_snapshots/02_render_candidate/source/render.yaml, Dockerfile and deploy/start.sh |

This review independently verified archive integrity, read source/report evidence, checked aggregate arithmetic, and corrected overbroad report claims. It did not run application tests, access the original full databases/master, log into providers, benchmark a VPS, observe production or change the repository. No speedup, monthly saving, ready-company count beyond the stated field-presence baseline, or full-source completeness is claimed without the corresponding ticket evidence.
