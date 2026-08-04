# Runr Jobs acquisition audit and revised implementation plan

Status: audit complete; implementation intentionally not started.

This document updates the Jobs-page integration plan after tracing the current
repository. It is deliberately repository-specific. The current branch was
left unchanged except for this report; existing user changes in the worktree
were not touched.

## Executive decision

The existing system has a durable, lease-aware worker and a useful set of
run-local acquisition stages, but it does not yet have the shared catalog,
system-owned acquisition identity, 24-hour cycle lock, lifecycle model,
personalization service, or real Jobs API required by the request.

The target flow is therefore:

```text
Runr-controlled 24-hour scheduler
  -> server-configured source acquisition
  -> raw observations and canonical upserts
  -> shared active-job repository
  -> user preferences and evaluation service
  -> authenticated personalized Jobs API
  -> Jobs / Hidden Jobs pages
```

The browser, onboarding, user filters, refreshes, and Jobs API must never
start acquisition. A user can read, filter, paginate, save, hide, restore, or
report. Only the trusted scheduler, worker process, and explicitly protected
admin recovery path can operate acquisition.

| Actor | Permitted operations |
| --- | --- |
| User/frontend | Read personalized jobs; filter; paginate; save; hide; restore; report; update own preferences |
| Personalization service | Query shared jobs; apply deterministic filters; retrieve or calculate user-scoped evaluations |
| Scheduler/worker | Start and execute the controlled 24-hour acquisition cycle using server-configured sources and policies |
| Admin/internal operations | Inspect cycle/source status; change server policy; run explicitly protected recovery/reconciliation |

No user, onboarding, page-load, refresh, filter, zero-result, or personalized
Jobs API action may start acquisition.

## Audit: scheduling and acquisition

For every item, “Reuse” states whether the existing capability should be used
unchanged, extended, or excluded from the new path.

1. **Where recurring work is scheduled?** File:
   `backend/application/services.py`; symbols:
   `update_workspace_schedule()` and `enqueue_due_scheduled_runs()`.
   Current behavior: an authenticated workspace owner stores `run_schedule` in
   workspace metadata; the worker polls due workspaces and enqueues a run for
   the workspace owner. Reuse: extend only as a reference for legacy
   workspace automation; do not use it for shared catalog acquisition.

2. **Production scheduler or recurring abstraction?** Files:
   `backend/worker/service.py`, `workspace_runner.py`, `render.yaml`, and
   `deploy/start.sh`; symbols `WorkerService.run_loop()` and the
   `run-worker` entry point. Current behavior: Render runs a continuous
   background worker; it polls the queue and runs maintenance. There is no
   separate production cron or system acquisition scheduler. Reuse: extend
   the worker process with a small system scheduler service; reuse queue,
   leases, and process supervision.

3. **Once-per-24-hour acquisition cycle?** File:
   `backend/application/services.py`; symbol `update_workspace_schedule()`.
   Current behavior: interval days are configurable per workspace and accept
   any interval of at least one day. There is no fixed global 24-hour catalog
   window or freshness objective. Reuse: no; add a server-configured UTC
   cycle window and durable cycle key.

4. **Concurrent scheduled-cycle prevention?** Files:
   `backend/application/services.py` and `backend/application/run_services.py`;
   symbols `enqueue_due_scheduled_runs()` and
   `claim_next_queued_run()`. Current behavior: workspace scheduling checks
   active run statuses and the worker uses run leasing. This is not an atomic
   global cycle lock and does not prevent two scheduler instances from
   enqueueing the same window. Reuse: extend run leasing; add a unique
   acquisition-cycle key plus transactional claim/lease.

5. **Missed, delayed, or failed schedule recovery?** Files:
   `backend/application/services.py` and `backend/application/run_services.py`;
   symbols `enqueue_due_scheduled_runs()`, `execute_run()`, and
   `recover_stale_workers()`. Current behavior: a due workspace is found on a
   later poll; workspace schedule errors advance the next timestamp; run
   attempts and stale-worker recovery handle task failures. There is no
   bounded cycle retry policy, source-level recovery, or freshness alert. Reuse:
   extend existing bounded retries and stale-worker recovery; add cycle/source
   recovery metadata and admin recovery.

6. **Scheduling scope?** Files:
   `backend/application/services.py` and `docs/security/runr_data_ownership.md`;
   symbols `run_schedule`, `owner_user_id`, and `RunRecord.user_id`. Current
   behavior: scheduling is workspace-specific and executes as that workspace's
   user. Reuse: not for catalog acquisition; the new schedule must be global
   and source-policy-driven, with no user or workspace ownership.

7. **Admin endpoint or command that starts acquisition manually?** Files:
   `backend/api/routes/admin.py` and `backend/api/routes/workspace.py`; symbols
   `POST /admin/scrapeops/reconciliation/run`, `POST /workers/process-next`,
   and `POST /runs`. Current behavior: there is no dedicated admin “run the
   catalog acquisition” command. Admin can reconcile ScrapeOps, a worker token
   can process the generic queue, and users can create ordinary or quick-apply
   runs. Reuse: reuse reconciliation as an operational dependency; add a
   narrowly scoped internal/admin acquisition recovery command only after the
   scheduler path exists.

8. **Authentication and authorization for that operation?** Files:
   `backend/security/auth.py`, `backend/api/server.py`, and
   `backend/api/routes/workspace.py`; symbols `ROLE_DEFAULT_SCOPES`,
   `_require_scope()`, `_require_admin()`, `_require_workspace_access()`,
   `POST /workers/process-next`, and `POST /runs`. Current behavior: worker
   execution requires `TOKEN_SCOPE_WORKER_EXECUTE`; admin operations require
   admin authorization; ordinary run creation is available to authenticated
   users with `runs:write` and workspace access. Reuse: extend the existing
   scope/admin machinery; do not make user `runs:write` an acquisition
   authority.

9. **Top-level acquisition entry point?** Files:
   `backend/application/run_services.py` and `backend/adapters/stage_adapters.py`;
   symbols `RunLifecycleService.execute_run()`, `StageEngine.execute()`, and
   `register_stage_adapters()`. Current behavior: a claimed run executes its
   planned stages; acquisition stage IDs dispatch to the registered stage
   classes. Reuse: extend this execution seam for the controlled acquisition
   run, while keeping catalog ingestion separate from candidate-specific
   filtering and document generation.

10. **Orchestration service the scheduler should call?** Files:
    `backend/worker/service.py` and `backend/application/run_services.py`;
    symbols `WorkerService.process_next()`,
    `RunLifecycleService.enqueue_run()`, `claim_next_queued_run()`, and
    `execute_run()`. Current behavior: the worker claims and executes queued
    `RunRecord`s. Reuse: call this existing lifecycle after a new
    `SystemAcquisitionScheduler.enqueue_due_cycle()` has atomically claimed the
    cycle; do not call a connector directly from an HTTP handler.

11. **Existing job-board and company-site stages?** Files:
    `backend/adapters/stage_adapters.py`;
    symbols `JobBoardAcquisitionStage`, `CompanyCareerSiteAcquisitionStage`,
    `LinkedInAcquireStage`, `ManualUrlIngestionStage`, and
    `MergeJobSetsStage`. Current behavior: job boards use the reusable
    collector, company sites use source-policy and crawl controls, LinkedIn
    uses candidate-oriented enrichment, manual URLs ingest explicit links, and
    merge deduplicates a run-local job set. Reuse: job-board and company-site
    acquisition can be adapted; exclude manual URL ingestion and the
    candidate-specific LinkedIn pipeline from the shared scheduled catalog.

12. **Production-ready strategies and connectors?** Files:
    `backend/connectors/job_boards/collector.py`,
    `backend/connectors/job_boards/strategies.py`,
    `backend/connectors/company_career_sites.py`, and
    `docs/scraping_strategy_report_2026-05-26.md`; symbols
    `collect_jobs_from_portals()`, `PORTAL_STRATEGIES`,
    `ADDITIONAL_PORTAL_STRATEGIES`, and `scrape_company_career_sites()`.
    Current behavior: several portal strategies and a policy-aware company-site
    crawler exist, but they accept user/runtime settings, have uneven source
    coverage, and some depend on ScrapeOps. The report also records LinkedIn
    account/terms and cost risk. Reuse: start with one approved source through
    a server policy; reuse connectors behind source adapters only after health,
    terms, cost, and unattended-run validation. Do not classify every existing
    strategy as production-ready by filename alone.

13. **Are runs associated with a user or workspace?** Files:
    `backend/domain/models.py`, `backend/application/run_services.py`, and
    `docs/security/runr_data_ownership.md`; symbols `WorkspaceDefinition`,
    `RunRecord`, `resolve_run_user_id()`, and `RunRecord.create()`. Current
    behavior: runs carry `workspace_id`, `requested_by`, and normally a user
    ID; scheduled runs execute as the workspace owner. Reuse: retain for
    existing product workflows; add a distinct system-owned run kind and
    principal for catalog cycles.

14. **Can the run system support a system-owned acquisition run?** Files:
    `backend/domain/models.py` and `backend/application/run_services.py`;
    symbols `RunRecord.create()`, `enqueue_run()`, and `execute_run()`. Current
    behavior: the model permits an empty user ID, but run plans and workspace
    access assumptions are user/workspace-oriented; some stages resolve plan,
    CV, quota, and owner settings. It cannot safely support the requested
    shared run unchanged. Reuse: extend the run kind and authorization
    metadata, or introduce a narrowly scoped internal acquisition record that
    still uses the existing worker execution lifecycle.

15. **System, service-account, or internal-run concept?** Files:
    `backend/domain/models.py`, `backend/security/auth.py`, and
    `docs/security/runr_data_ownership.md`; symbols `requested_by`, `user_id`,
    token scopes, and ownership rules. Current behavior: `requested_by` is a
    string audit field and worker/admin scopes exist, but there is no durable
    system principal or internal run authorization model. Reuse: extend the
    existing audit fields and scopes; add an explicit non-user system identity,
    accepted only by trusted scheduler/worker code.

16. **Retries, cancellation, timeouts, and partial failures?** Files:
    `backend/application/run_services.py`, `backend/worker/service.py`, and
    `backend/adapters/stage_adapters.py`; symbols `execute_run()`,
    `process_next()`, stage status/outcomes, run cancellation checks, worker
    lease recovery, and connector retry helpers. Current behavior: run/stage
    states, bounded attempts, cancellation, lease renewal/recovery, and
    partial stage outcomes already exist; source failures can be returned while
    another stage's output survives. This is run-local and lacks durable
    source reconciliation. Reuse: reuse lifecycle and connector retry code;
    extend with source-level results and cycle retry rules.

17. **Existing idempotency protections?** Files:
    `backend/application/run_services.py`, `backend/domain/job_identity.py`,
    `backend/repositories/sqlite_backed.py`, and
    `backend/repositories/sqlite_migrations.py`; symbols run leasing,
    `dedupe_job_records()`, `run_job_sets`, and `site_job_url_history`.
    Current behavior: workers lease runs, merge removes duplicates within a run,
    and the site URL table upserts by URL. There is no scheduled-window key,
    observation idempotency key, or canonical posting upsert transaction.
    Reuse: reuse run leases and URL normalization; add durable idempotency keys
    for cycle, source attempt, and observation.

18. **Can concurrent executions of the same source be consolidated or
    rejected?** Files: `backend/application/run_services.py`,
    `backend/application/services.py`, and `backend/repositories/sqlite_backed.py`;
    symbols run status checks, `active_workspace_ids`, and source policy stores.
    Current behavior: duplicate workspace runs are avoided best-effort, but no
    source-cycle uniqueness or source lease exists. Reuse: extend with a unique
    `(cycle_window, source_id)` claim and a stale lease timeout; reject or
    coalesce duplicate source work before external requests.

## Audit: storage, contracts, canonicalization, and lifecycle

19. **Where are acquired jobs stored?** Files:
    `backend/repositories/contracts.py`, `backend/repositories/sqlite_backed.py`,
    and `backend/repositories/file_backed.py`; symbols `JobStoreProtocol`,
    `SqliteJobStore.save_job_set()`, `run_job_sets`, and the file-backed job
    store. Current behavior: acquisition outputs are saved under a run and
    set key. Reuse: retain for run inspection and legacy workflows; do not use
    as the Jobs catalog.

20. **Durable or run-local?** Files:
    `backend/repositories/sqlite_migrations.py` and
    `backend/repositories/sqlite_backed.py`; symbols `run_job_sets`, `run_jobs`,
    and `SqliteJobStore`. Current behavior: SQLite/file persistence is durable,
    but the records are scoped to one run and are replaced/cleared by run-set
    operations. Reuse: no for the shared feed; migration logic can be reused
    for new durable tables.

21. **Existing shared jobs repository?** Files:
    `backend/repositories/contracts.py`, `backend/repositories/sqlite_backed.py`,
    and `docs/personalized_jobs_contracts.md`; symbols `JobStoreProtocol` and
    P0 contract notes. Current behavior: no repository can query shared active
    postings across runs or users. Reuse: extend repository wiring and SQLite
    migration conventions; implement a new canonical catalog repository.

22. **Existing schemas for the required domain objects?**

    - Job postings: `backend/repositories/sqlite_migrations.py`,
      `run_job_sets`/`run_jobs`, and `backend/domain/models.py::JobRecord`.
      These are run-local, not canonical. Reuse: only as source mapping.
    - Source observations and source-specific identifiers: `site_job_url_history`
      and `JobSourceObservation` in
      `backend/domain/personalized_jobs_contracts.py`. The table is URL-keyed
      and company-site oriented; the contract has the right shape but no
      repository. Reuse: extend the contract and add durable observation rows.
    - Job versions: `JobPosting.version` and provenance fields in the contract
      exist in memory only. No version table exists. Reuse: extend the contract
      semantics and persist immutable versions or content hashes.
    - Job status/lifecycle: `site_job_url_history.active_status` and
      `JobPostingState` (`active`, `expired`, `unknown`) exist. They do not
      model source absence grace periods, closed/reposted relationships, or
      canonical lifecycle transitions. Reuse: extend.
    - Search preferences: `CandidateSearchPreferences` is a shape only;
      `career_profiles` and workspace settings are the nearest durable data.
      Reuse: adapt profile/CV references, then add a user preference repository.
    - Eligibility and match evaluations: `ProfileRequirementMatch` and
      `JobApplicationBinding` are existing application-domain inputs/adapters;
      no evaluation tables exist. Reuse: adapters only; add feed evaluation
      persistence.
    - Saved/hidden states: `JobDisposition` is an in-memory contract and
      frontend preview state is local storage. No backend disposition schema
      exists. Reuse: contract transition rules; add user-scoped persistence.

23. **Which `personalized_jobs_contracts.py` contracts are already used?**
    File: `backend/domain/__init__.py` re-exports the contracts and
    `tests/test_personalized_jobs_contracts.py` exercises their serialization,
    adapters, and transition rules. Current runtime behavior: production
    services do not use these contracts to persist or serve Jobs data. Reuse:
    use the shapes and tests as the starting domain boundary; add runtime
    integration deliberately rather than treating re-export or tests as
    production use.

24. **Which are definitions with no persistence/runtime integration?** File:
    `backend/domain/personalized_jobs_contracts.py`; symbols
    `CandidateSearchPreferences`, `JobPosting`, `JobSourceObservation`,
    `EligibilityEvaluation`, `MatchEvaluation`, and `JobDisposition`. The
    module explicitly says it defines shapes only. Reuse: all require
    persistence/service integration; `MatchEvaluation` adapters can be reused
    for legacy evidence, but application binding itself must not run during
    feed construction.

25. **Canonicalization or cross-source deduplication?** File:
    `backend/domain/job_identity.py`; symbols `canonicalize_url()`,
    `canonical_posting_url()`, `posting_url_identity_key()`,
    `job_identity_keys()`, and `dedupe_job_records()`. Current behavior:
    tracking parameters and URL variants are normalized; within-run records are
    deduped by run-local ID or title/company/location signatures. Reuse: extend
    these pure helpers into observation normalization; do not use URL as the
    permanent canonical primary key.

26. **Closed, expired, removed, and reposted representation?** Files:
    `backend/domain/personalized_jobs_contracts.py` and
    `backend/repositories/sqlite_backed.py`; symbols `JobPostingState` and
    `active_status`. Current behavior: only active/inactive/unknown or
    active/expired/unknown is represented; no source-specific grace period,
    explicit closed reason, repost link, or duplicate relationship exists.
    Reuse: extend lifecycle states/metadata and add canonical relationship
    records.

27. **Availability verification in later cycles?** Files:
    `backend/repositories/sqlite_backed.py` and
    `backend/adapters/stage_adapters.py`; symbols `get_cached_job_postings()`,
    `record_job_url_attempts()`, source-policy crawl callbacks, and
    `site_job_url_history`. Current behavior: company-site attempts update the
    last URL status; a missing URL is not reconciled with source-specific
    absence rules, and portal records have no shared later-cycle verification.
    Reuse: extend attempt history and source policy; implement cautious
    missing-observation grace periods before closing a canonical posting.

## Audit: ScrapeOps and cost control

28. **Where ScrapeOps is used?** Files:
    `backend/integrations/scrapeops.py`, `backend/connectors/job_boards/strategies.py`,
    `backend/connectors/company_career_sites.py`,
    `backend/adapters/stage_adapters.py`, and
    `backend/application/services.py`; symbols `build_proxy_params()`,
    `scrapeops_request_with_retry()`, `require_scrapeops_proxy_health()`,
    `_record_usage_event()`, and reconciliation services. Current behavior:
    portal fallback, company-site fetching, health checks, usage ledger, and
    reconciliation use ScrapeOps. Reuse: keep the integration and retry
    plumbing; place new governance around it.

29. **Direct, fallback, and mandatory-proxy sources?** Files:
    `backend/connectors/job_boards/strategies.py`,
    `backend/connectors/job_boards/collector.py`, and
    `backend/config/scrapeops_admin_policy.py`; symbols portal strategies,
    `PORTAL_STRATEGIES`, request modes, and domain policy. Current behavior:
    strategies generally try direct requests and may use proxy fallback;
    company-site policy can select request modes; there is no normalized
    server-owned per-source policy enum covering direct-only,
    direct-with-fallback, proxy-required, or disabled. Reuse: extend policy
    configuration and source adapters; do not infer policy from connector
    branching.

30. **Usage accounting, budget enforcement, and policy code?** Files:
    `backend/config/scrapeops_admin_policy.py`,
    `backend/adapters/stage_adapters.py`,
    `backend/repositories/sqlite_migrations.py`, and
    `backend/application/services.py`; symbols plan limits, `_record_usage_event()`,
    `scrapeops_usage_ledger`, `get_scrapeops_admin_policy()`, and
    `run_scrapeops_reconciliation_cycle()`. Current behavior: plan/user run
    credit limits, domain request modes, analytics ledger, and remote usage
    reconciliation exist. Reuse: extend the policy and ledger model for
    system cycle/source attribution; do not apply per-user billing budgets to
    the shared acquisition.

31. **Atomic before-request enforcement or afterward?** Files:
    `backend/adapters/stage_adapters.py` and
    `backend/repositories/sqlite_backed.py`; symbols `_record_usage_event()` and
    `record_scrapeops_usage()`. Current behavior: callbacks enforce user/run
    limits and ledger events are recorded after provider work; actual credit
    reconciliation occurs later. There is no atomic reservation before an
    external request. Reuse: keep post-request reconciliation; add a
    transactionally reserved estimated budget before each request and release
    or reconcile the delta afterward.

32. **Global/source/run/monthly limits?** Files:
    `backend/config/scrapeops_admin_policy.py` and
    `backend/adapters/stage_adapters.py`; symbols `runner_credits_per_month`,
    `runner_credits_per_run`, `company_sites_per_run`, and stage limits.
    Current behavior: plan/user monthly and per-run limits exist, but not a
    centralized global cycle ceiling or source ceiling for shared acquisition.
    Reuse: extend limit normalization; add global, source, and cycle ceilings.

33. **Kill switch?** Files:
    `backend/config/scrapeops_admin_policy.py` and
    `backend/integrations/scrapeops.py`; symbols `alert_policy`, request modes,
    and health checks. Current behavior: alerts, health failures, and limits can
    stop some work, but there is no explicit shared-acquisition or ScrapeOps
    kill switch. Reuse: extend the admin policy with an explicit disabled flag
    checked before reservation and request.

34. **Usage-record idempotency?** Files:
    `backend/repositories/sqlite_migrations.py` and
    `backend/repositories/sqlite_backed.py`; symbols `scrapeops_usage_ledger`
    and `record_scrapeops_usage()`. Current behavior: rows have generated event
    or ledger IDs and indexes, but no request-attempt idempotency key or unique
    cycle/source/request constraint. Reuse: retain ledger fields; add a unique
    internal usage-attempt key and upsert semantics.

35. **Reusable admin usage/policy endpoints?** File:
    `backend/api/routes/admin.py`; symbols `GET /admin/scrapeops/usage`,
    `GET/PUT /admin/scrapeops/policy`, and
    `POST /admin/scrapeops/reconciliation/run`. Current behavior: admin can
    inspect usage, edit policy, and run reconciliation; `/scrapeops/usage` is
    user-facing usage reporting. Reuse: extend admin policy/dashboard with
    cycle/source views; keep internal credit details out of personalized Jobs
    responses.

36. **Startup validation of `SCRAPEOPS_API_KEY`?** Files:
    `backend/config/env_schema.py`, `backend/api/server.py`, and
    `backend/integrations/scrapeops.py`; symbols `ENV_SCHEMA`, `validate_environment()`,
    `check_scrapeops_proxy_health()`, and `require_scrapeops_proxy_health()`.
    Current behavior: startup validation does not require the key; health is
    checked when proxy-backed work occurs. Reuse: keep runtime health checks;
    extend worker/cycle readiness validation so a configured proxy-required
    source fails closed before the cycle begins.

## Audit: personalization and evaluation

37. **Where onboarding preferences are stored?** Files:
    `frontend/src/lib/personalizedPreviewState.js` and
    `frontend/src/pages/PersonalizedOnboardingPage.jsx`; symbols
    `saveUserOnboardingState()`, `finish()`, and local-storage keys. Current
    behavior: preview answers are local; real-mode CV documents can use the
    existing documents API, but search preferences are not persisted to a
    personalized backend. Reuse: map the form to `CandidateSearchPreferences`
    and existing CV asset references; add authenticated preference persistence.

38. **Existing role, location, employment, and arrangement filters?** Files:
    `backend/domain/personalized_jobs_contracts.py`,
    `backend/domain/phase0_contracts.py`,
    `frontend/src/lib/personalizedJobs.js`, and
    `frontend/src/components/personalized/JobsWorkspace.jsx`; symbols
    `CandidateSearchPreferences`, normalized work arrangement rules, and
    `getFeedJobs()`. Current behavior: the contract and preview have target
    roles, locations, employment types, seniority, and arrangement filters;
    the preview filters fixture data locally. Reuse: reuse normalization and
    UI vocabulary; implement server-side deterministic filtering against the
    shared repository.

39. **Language and work-authorization rules?** Files:
    `backend/domain/personalized_jobs_contracts.py` and
    `backend/domain/language_rules.py`; symbols preference fields,
    `EligibilityEvaluation`, and `detect_reasons()`. Current behavior:
    language proficiency and authorization/sponsorship fields and uncertainty
    rules are defined; the existing language adapter can produce reasons. Reuse:
    reuse rule normalization/reason codes; extend with source evidence and a
    persisted eligibility evaluator.

40. **Reusable job-requirement analysis?** Files:
    `backend/domain/language_rules.py`,
    `backend/domain/personalized_jobs_contracts.py`, and
    `backend/capabilities/tailored_documents/acquisition.py`; symbols
    `detect_reasons()`, `EligibilityEvaluation`, and current AI/title filtering.
    Current behavior: deterministic language/reason analysis exists; tailored
    acquisition also performs candidate-specific AI filtering. Reuse: reuse
    deterministic analyzers; do not reuse candidate-specific acquisition AI as
    the source-ingestion boundary.

41. **Reusable profile-evidence matching?** Files:
    `backend/domain/models.py` and
    `backend/domain/personalized_jobs_contracts.py`; symbols
    `ProfileRequirementMatch`, `MatchEvaluation.from_profile_requirement_matches()`,
    `CareerProfile`, work-experience/evidence stores, and the binding adapter.
    Current behavior: profile requirements and evidence can be adapted into a
    match evaluation, but no shared feed evaluator or result cache exists.
    Reuse: reuse evidence references and the adapter; add a read-only
    personalization evaluation service.

42. **Workflows that mutate application/profile state and must not run for a
    feed?** Files:
    `backend/application/services.py`,
    `backend/api/routes/application_bindings.py`,
    `backend/api/routes/assisted_apply*.py`, and
    `backend/domain/models.py`; symbols application-package/preparation,
    binding, document-generation, and profile mutation services. Current
    behavior: these create or update application packages, tailored documents,
    evidence, or application bindings. Reuse: none inside feed building;
    maintain a hard boundary so feed reads/evaluations cannot invoke them.

43. **Eligibility and match caching/versioning?** Files:
    `backend/domain/personalized_jobs_contracts.py` and
    `backend/repositories/sqlite_migrations.py`; symbols evaluator version,
    profile/job evidence version fields and existing profile version tables.
    Current behavior: the contract carries version metadata, and profiles/CV
    evidence have versions, but no eligibility or match result repository/cache
    exists. Reuse: use those version fields as cache keys; add persistent
    evaluation tables with invalidation on job/profile/evaluator changes.

44. **Deterministic filtering before expensive evaluation?** Files:
    `frontend/src/lib/personalizedJobs.js`,
    `backend/domain/phase0_contracts.py`, and
    `backend/domain/language_rules.py`; symbols `getFeedJobs()`, normalized
    preference fields, and reason detection. Current behavior: cheap filtering
    exists only over preview fixtures; backend acquisition filtering is mixed
    into user-specific pipeline stages. Reuse: move/reuse deterministic
    predicates server-side and execute them before semantic evaluation.

## Audit: authenticated API

45. **Authenticated job APIs?** Files:
    `backend/api/routes/workspace.py`; symbols `/runs/{run_id}/jobs`,
    `/runs/{run_id}/jobs/{job_id}`, and related run-resource handlers. Current
    behavior: authorized users can inspect jobs belonging to their runs; no
    shared personalized Jobs API exists. Reuse: reuse auth/serialization
    conventions, not the run-local data contract.

46. **Feed, pagination, or query abstraction?** Files:
    `backend/api/routes/workspace.py` and `backend/api/server.py`; symbols
    `_pagination_meta()`, bounded run listing, and run job-set loading. Current
    behavior: pagination exists for runs/resources, but no cursor-based shared
    posting query, feed projection, or evaluation-aware ordering exists. Reuse:
    reuse bounded pagination conventions; add a feed query service and cursor.

47. **Strict user ownership enforcement?** Files:
    `backend/api/server.py`, `backend/security/auth.py`, and
    `docs/security/runr_data_ownership.md`; symbols `_require_workspace_access()`,
    `_require_run_access()`, role scopes, `owner_user_id`, and `RunRecord.user_id`.
    Current behavior: non-admin users need matching run/user and workspace
    access; admin bypasses are explicit. Reuse: use the same authenticated
    identity and admin separation; enforce `user_id` on preferences,
    evaluations, dispositions, and reports while canonical postings remain
    shared and public-safe.

48. **Route registry for personalized Jobs?** Files:
    `backend/api/routes/__init__.py` and `backend/api/routes/registry.py`; symbols
    `register_routes()` and `RouteRegistry`. Current behavior: modular route
    modules register through the central registry. Reuse: add a dedicated
    `backend/api/routes/personalized_jobs.py` module and register it there; do
    not overload run-resource routes.

49. **Saved, hidden, restored, or reported endpoints?** Files:
    `backend/api/routes/tracker.py` and
    `backend/application/services.py`; symbol
    `POST /rejected-jobs/requeue`. Current behavior: requeue is an
    application/document workflow, not a Jobs disposition restore operation;
    no saved/hidden/report API exists. Reuse: do not reuse requeue; add
    disposition/report endpoints backed by `JobDisposition` transitions.

50. **User-facing endpoints capable of starting acquisition?** Files:
    `backend/api/routes/workspace.py` and `backend/api/server.py`; symbols
    `POST /runs`, `POST /quick-apply/runs`, `PUT /workspaces/{id}/schedule`,
    `_build_run_input_overrides()`, and
    `_build_quick_apply_run_input_overrides()`. Current behavior: users with
    workspace access can enqueue runs and configure recurring workspace runs;
    quick apply accepts validated manual URLs. These are acquisition-capable
    paths even though they are not currently Jobs-page routes. Reuse: preserve
    only for explicitly supported legacy workflows; ensure the personalized
    Jobs boundary cannot call or configure them.

51. **How to restrict those paths without breaking internal operations?** Files:
    `backend/api/routes/workspace.py`, `backend/security/auth.py`,
    `backend/application/services.py`, and `workspace_runner.py`; symbols
    route handlers, worker scope, `update_workspace_schedule()`, and
    `run-worker`. Plan: keep legacy run APIs only for their existing product
    workflows, remove acquisition semantics from the personalized Jobs UI,
    reject user-supplied catalog source/policy overrides, and introduce a
    distinct trusted internal acquisition command/scope. Worker queue
    processing remains available to the worker; admin recovery is separate.
    Reuse: existing scope checks and worker process; extend route-level
    validation and tests.

## Audit: frontend

52. **Where the Jobs page obtains preview data?** Files:
    `frontend/src/components/personalized/JobsWorkspace.jsx`,
    `frontend/src/pages/HiddenJobsPage.jsx`, and
    `frontend/src/lib/personalizedJobs.js`; symbols `PREVIEW_JOBS`,
    `getFeedJobs()`, `getHiddenReasonGroups()`, and `JobsWorkspace`. Current
    behavior: fixture records and local derived filters drive Jobs and Hidden
    Jobs. Reuse: preserve fixtures for synthetic mode; replace the data source
    only in real mode.

53. **Provider boundary between preview and real data?** Files:
    `frontend/src/lib/personalizedJobs.js` and
    `docs/PERSONALIZED_JOBS_PREVIEW.md`; symbols
    `VITE_PERSONALIZED_JOBS_DATA_MODE`, `resolvePersonalizedJobsDataMode()`,
    and preview contracts. Current behavior: a data-mode flag exists, but the
    pages/components still import fixtures and local state directly; it is not
    a functioning provider boundary. Reuse: extend the existing flag and
    contract into a provider hook; keep synthetic default and remove fixture
    leakage from real mode.

54. **API client and resource hooks to reuse?** Files:
    `frontend/src/lib/api.js` and `frontend/src/hooks/useApiResource.js`; symbols
    `apiRequest()`, `apiRequestWithRetry()`, auth token handling, cache, and
    in-flight dedupe. Current behavior: generic authenticated API and resource
    lifecycle utilities already exist. Reuse: unchanged at the transport/cache
    layer; add personalized Jobs API functions and provider state above them.

55. **Job states held only in local storage?** File:
    `frontend/src/lib/personalizedPreviewState.js`; symbols
    `saveDispositions()`, `loadDispositions()`, `usePreviewDispositions()`,
    onboarding state, and preview offer state. Current behavior: saved/hidden/
    restored dispositions and preview preference changes are local; the
    disposition store is not consistently user-keyed. Reuse: only as synthetic
    mode behavior; real mode must use backend disposition/report state.

56. **How `HiddenJobsPage` obtains data?** File:
    `frontend/src/pages/HiddenJobsPage.jsx`; symbols `PREVIEW_JOBS`,
    `getHiddenReasonGroups()`, and `usePreviewDispositions()`. Current behavior:
    it derives hidden groups from fixture flags and local dispositions; report
    says it was not sent to a backend. Reuse: preserve the visual grouping
    contract; connect real mode to the personalized feed/disposition API.

57. **Existing loading, empty, partial, and failure components?** Files:
    `frontend/src/components/personalized/JobsWorkspace.jsx`,
    `frontend/src/pages/PersonalizedOnboardingPage.jsx`, and
    `frontend/src/hooks/useApiResource.js`; symbols `.jobs-empty`, onboarding
    `stepError`, and resource status/error fields. Current behavior: there are
    fixture empty states and onboarding validation errors, but no real Jobs
    loading skeleton, partial-evaluation state, stale-snapshot banner, or feed
    failure state. Reuse: use existing empty/error styling and resource
    lifecycle; add explicit loading/partial/stale/failure components.

58. **Search or refresh mistaken for acquisition?** File:
    `frontend/src/components/personalized/JobsWorkspace.jsx`; symbols local
    `updateFilter()`, search input, filter pills, “Save search”, and clear
    filters. Current behavior: actions filter fixtures locally; there is no
    scrape progress or refresh button. Reuse: preserve filtering as a read
    operation; in real mode implement query/pagination only and do not add a
    user-triggered refresh/acquisition action. “Save search” must either save
    preferences or be clearly removed, never enqueue a run.

## Audit: operations and observability

59. **Scheduler-health monitoring?** Files:
    `backend/worker/service.py`, `backend/api/routes/admin.py`, and
    `backend/application/services.py`; symbols worker loop logs, admin dashboard,
    analytics events, and ScrapeOps maintenance. Current behavior: worker and
    run health are visible, but no scheduler heartbeat, last successful cycle,
    or missed-window metric exists. Reuse: extend worker/admin telemetry and
    analytics event storage with sanitized scheduler-cycle events.

60. **Source freshness and acquisition-failure monitoring?** Files:
    `backend/adapters/stage_adapters.py`,
    `backend/repositories/sqlite_backed.py`, and
    `backend/api/routes/admin.py`; symbols stage metrics/failure payloads,
    source policy timestamps, and admin analytics. Current behavior: metrics are
    attached to runs/source policy and generic analytics; no shared posting
    freshness or source-failure dashboard exists. Reuse: emit source-cycle
    events; add durable source freshness/status projection.

61. **Admin view for acquisition status?** Files:
    `backend/api/routes/admin.py` and
    `backend/application/services.py`; symbols admin dashboard, analytics, and
    ScrapeOps endpoints. Current behavior: admin can view general runs,
    analytics, and provider usage, but not a catalog cycle/source status view.
    Reuse: extend the admin route/dashboard with catalog status; do not expose
    it through the user Jobs API.

62. **Can the system report the required metrics?** Existing evidence:
    `backend/repositories/sqlite_backed.py::analytics_events`,
    `backend/application/services.py::get_scrapeops_usage_summary()`,
    `backend/api/routes/admin.py` analytics/dashboard handlers, and
    `site_job_url_history`. Current behavior: ScrapeOps usage, generic run
    counts, and some source URL timestamps are available. Last successful cycle,
    last successful source refresh, active canonical count, new/updated/closed
    counts, duplicate rate, and acquisition failure rate are not available as
    shared-catalog metrics. Reuse: use analytics for sanitized events and
    provider usage; add cycle/source/posting counters to the catalog metadata.

63. **Where should 24-hour failure alerts go?** Files:
    `backend/application/services.py` and
    `docs/scrapeops_usage_and_admin_dashboard_implementation_report.md`; symbols
    `SCRAPEOPS_ALERT_EVENT_NAME`, reconciliation alert events, and admin event
    history. Current behavior: alerts are stored as in-app admin events; there
    is no email/Slack destination configured in this repository. Reuse: first
    emit a catalog freshness/failure admin event using the existing mechanism;
    the Runr team must choose whether an external destination is required.

64. **Existing recovery mechanism?** Files:
    `backend/worker/service.py` and `backend/application/run_services.py`; symbols
    worker lease renewal, `recover_stale_workers()`, retry/resume/cancel, and
    ScrapeOps reconciliation. Current behavior: stale workers and run tasks can
    be recovered and provider usage reconciled; there is no cycle-level retry,
    source resume, or stale-snapshot publication policy. Reuse: extend the
    existing worker/run recovery and reconciliation; add bounded cycle/source
    recovery and preserve the last good catalog snapshot.

## Reuse matrix

### Reuse unchanged

- `WorkerService` queue polling, worker leases, heartbeat, stale-worker
  recovery, and run/stage status machinery.
- `RunLifecycleService` claim/execute/cancel/retry mechanics, subject to a
  system-owned run kind being added around it.
- `backend/api/routes/registry.py` and existing authentication/scope/admin
  helpers.
- `canonicalize_url()` and related pure identity helpers as normalization
  inputs, not as the final identity model.
- Existing job-board/company-site connector internals only where a source is
  explicitly approved and its policy/cost behavior is known.
- `apiRequest()`, `apiRequestWithRetry()`, `useApiResource()`, and the
  synthetic data-mode flag.
- Existing profile, CV asset, work-experience, and evidence repositories as
  read-only personalization inputs.
- ScrapeOps health checks, request retry/backoff, admin policy normalization,
  analytics ledger, and reconciliation plumbing.

### Extend

- Add a system principal and system acquisition run/cycle metadata without
  changing user-owned run semantics.
- Add a durable cycle window lock, source claims, bounded retry state, and
  scheduler heartbeat.
- Extend source policy to server-configured source definitions and direct /
  fallback / proxy-required / disabled behavior.
- Extend `JobSourceObservation`, `JobPosting`, and lifecycle contracts for
  source identity, canonical aliases, content versions, duplicate/repost
  relationships, source absence grace periods, and freshness.
- Extend ScrapeOps policy and ledger with pre-request reservations, global /
  source / cycle ceilings, kill switch, and idempotent attempt keys.
- Add feed-specific admin status/metrics and in-app alerts.
- Turn the frontend data-mode flag into a provider boundary and add real
  loading, partial, stale, and failure states.

### Genuine gaps

- Shared canonical job repository and migrations.
- Acquisition-cycle/source-run repository and system scheduler.
- User preference repository.
- Deterministic personalization/filter service.
- Eligibility and match evaluation execution/cache.
- User disposition/report repository and API.
- Personalized read API and feed query/pagination service.
- Real frontend provider wiring for Jobs and Hidden Jobs.
- An explicit trusted-only acquisition authorization boundary.

## Revised implementation plan

### 1. Establish and enforce the trust boundary

Add a system-owned acquisition identity and an internal acquisition run kind.
The scheduler and worker may create/execute it; a normal user token may not.
Keep user-facing operations limited to personalized reads, preferences,
filters, pagination, save/hide/restore/report, and evaluation state.

Audit and restrict `POST /runs`, `POST /quick-apply/runs`, and
`PUT /workspaces/{id}/schedule` so they cannot be used by the Jobs experience
to configure or trigger catalog acquisition. Preserve legacy behavior only for
the existing run/application workflows that explicitly require it. The
generic worker queue endpoint remains worker-scope-only; catalog recovery gets
its own admin/internal authorization and audit event.

### 2. Add the exact scheduler entry point

Introduce a service such as
`backend/application/acquisition_scheduler.py::SystemAcquisitionScheduler` and
invoke it from `WorkerService.run_loop()` on the existing bounded poll cadence.
The scheduler should:

1. Compute the server-configured UTC 24-hour window.
2. Atomically claim `acquisition_cycles(window_key)` with a unique key and
   stale-claim recovery.
3. Refuse a second active cycle and coalesce duplicate source work.
4. Create the system-owned acquisition run through the existing
   `RunLifecycleService.enqueue_run()` seam, with a server-side source manifest.
5. Record cycle state, source states, retry budget, freshness timestamps, and
   sanitized errors.

This is a worker-internal scheduler, not a user endpoint and not a workspace
schedule. It preserves the current Render deployment model, which has one
continuous worker process and no cron service.

### 3. Add the exact acquisition orchestration path

The scheduler should enqueue a catalog run that reaches
`RunLifecycleService.execute_run()` and then a catalog-specific acquisition
orchestrator/stage. The first vertical slice should call the existing
`JobBoardAcquisitionStage` or `CompanyCareerSiteAcquisitionStage` using a
server-owned source manifest and write observations rather than only saving a
run-local job set.

Do not route through `LinkedInAcquireStage` unchanged: it loads a candidate CV,
performs candidate-specific filtering/enrichment, and is coupled to a user
run. Do not route through `ManualUrlIngestionStage` for the shared catalog.
Keep the existing connector retry/cancellation callbacks and make each source
result independently durable so one source failure does not discard successful
sources.

### 4. Build the shared repository and lifecycle model

Use the SQLite migration/repository conventions to add the minimum durable
catalog set:

- `acquisition_cycles`: cycle window key, status, started/finished timestamps,
  scheduler lease, run ID, retry/error metadata, last successful publication.
- `acquisition_source_runs`: cycle/source claim, policy version, status,
  attempts, source freshness, counts, reserved/actual credits, sanitized error.
- `canonical_job_postings`: stable canonical posting ID, normalized public
  fields, current lifecycle, first/last seen, last verified, current version,
  freshness and closure metadata.
- `job_source_observations`: immutable or append-only observation ID, source
  type/source ID, source-specific observation ID, original URL, raw payload
  reference, observed facts, observation time, cycle/source run, and provider
  metadata.
- `job_posting_versions` or an equivalent versioned payload table, plus
  canonical URL aliases/external identifiers and duplicate/repost relationships.

Add a repository protocol that supports transactional observation upsert,
canonical resolution, lifecycle reconciliation, active/fresh query, source
metrics, and publication metadata. Keep run-local `JobStoreProtocol` for run
inspection; it is not the shared repository.

Lifecycle rules must be source-aware. A single missing observation must not
close a posting. Require source-specific absence thresholds/grace periods and
retain a stale/unknown state when the source is unhealthy. Reposts and
duplicates must retain provenance and relationships rather than collapsing
history into a URL-only record.

### 5. Define canonicalization and idempotent upserts

Normalize each connector result into `JobSourceObservation`; retain raw facts
and the source-specific identifier separately from the canonical ID. Reuse
`canonicalize_url()`, `posting_url_identity_key()`, and title/company/location
normalization as candidate keys. Resolve identity in this order:

1. Stable source external ID plus source identity.
2. Known canonical URL alias.
3. Strong normalized employer/title/location and content signals.
4. A new canonical posting ID.

The URL is an alias/provenance value, not the permanent primary identity.
Use unique observation keys and transactional canonical upserts so replaying a
cycle is safe. Increment versions only when normalized facts change and retain
the observation that caused the change.

### 6. Add ScrapeOps operational governance before expanding sources

Reuse request modes, proxy health, retries, admin policy, and reconciliation.
Before any external request, atomically reserve an estimated credit against the
global, source, and cycle ceilings. If reservation or the explicit kill switch
fails, do not request. Afterward, record an idempotent attempt keyed by cycle,
source, target, request sequence, and provider request identity; reconcile
estimated versus actual usage and release unused reservation.

Attribute shared usage to cycle/source/stage/domain, not to a user plan. Keep
user benefit/product analytics separate. Require key/readiness checks for
proxy-required sources at cycle start, and expose details only to protected
admin operations. Publish alerts as sanitized admin events; add an external
destination only after the team decides where it belongs.

### 7. Add the shared-jobs read and personalization path

Persist `CandidateSearchPreferences` keyed to the authenticated user/profile,
including the selected CV/profile asset reference. Add a read-only feed service:

```text
GET preferences/profile context
  -> query shared active/fresh postings
  -> deterministic role/location/arrangement/employment/language/
     authorization filters
  -> cached or computed eligibility evaluation
  -> cached/computed match evaluation when appropriate
  -> cursor-paginated personalized feed
```

Use `CandidateSearchPreferences`, `JobPosting`, `EligibilityEvaluation`,
`MatchEvaluation`, and `JobDisposition` as the domain boundary, extending only
where lifecycle/version semantics require it. Reuse language-reason adapters
and profile evidence references. Never call application binding, tailored
document generation, assisted apply, profile mutation, or candidate-specific
acquisition while building a feed.

Add persistent evaluation rows keyed by posting version, profile/CV/evidence
version, evaluator version, and input hash. A missing or stale evaluation must
be represented explicitly; it must not silently become a fabricated score.

### 8. Add the authenticated personalized Jobs API

Create `backend/api/routes/personalized_jobs.py` and register it from
`backend/api/routes/__init__.py`. The initial contract should include:

- `GET /personalized-jobs/preferences`
- `PUT /personalized-jobs/preferences`
- `GET /personalized-jobs` with cursor, deterministic filters, and feed metadata
- `GET /personalized-jobs/{posting_id}`
- `PUT`/`POST /personalized-jobs/{posting_id}/disposition` for save, hide,
  restore, and other allowed transitions
- `POST /personalized-jobs/{posting_id}/report`
- an evaluation detail/read endpoint only if needed by the UI

There must be no `POST /personalized-jobs/search`, `refresh`, or acquisition
endpoint. The API reads the shared catalog and user-owned state only. Enforce
authenticated user identity on every preference, evaluation, disposition, and
report query; never accept a user ID from the browser as authority.

### 9. Wire real frontend data without fixture leakage

Keep `VITE_PERSONALIZED_JOBS_DATA_MODE=synthetic` as the safe default. Add a
provider in `frontend/src/lib/personalizedJobs.js` or a focused companion
module that uses `apiRequest`/`useApiResource` in real mode and returns one
normalized view model for `JobsWorkspace` and `HiddenJobsPage`.

Onboarding should save preferences and CV/profile reference through the API,
then request the feed and navigate to `/jobs` when feed data is ready. It must
not start a run or show scrape progress. Real mode must not import
`PREVIEW_JOBS`, use synthetic totals, or write real dispositions to preview
local storage. Search/filter/pagination are API reads; save/hide/restore/report
are authenticated mutations.

Add explicit loading, no-results, partial-evaluation, stale-snapshot, and
failure states. When acquisition is degraded, the API should continue to serve
the last valid active snapshot with freshness/degraded metadata rather than
making the browser retry acquisition.

### 10. Metrics, admin status, failure behavior, and recovery

Publish cycle and source metadata after each source is reconciled, including
last successful cycle/source refresh, active count, new/updated/closed counts,
duplicate rate, failure rate, freshness age, and ScrapeOps reservation/actual
usage. Extend the admin dashboard with cycle/source status and freshness
objectives. Emit sanitized events and an in-app admin alert when a cycle misses
the 24-hour objective or the catalog becomes stale.

Failures are isolated by source. Successful source observations are committed
and published even if another source fails. The previous active snapshot stays
readable. Cycle/source retries are bounded and use the existing connector/run
retry behavior; stale worker recovery remains the first recovery layer. Admin
recovery may retry a failed source/cycle through the trusted internal path but
must not be callable by Jobs-page users.

## Required tests before enabling real mode

- Scheduler claims one UTC window exactly once under two worker instances.
- A missed poll, worker restart, stale lease, bounded retry, cancellation, and
  manual admin recovery behave idempotently.
- Source A remains published when source B fails; stale snapshots remain
  readable and report freshness/degraded metadata.
- Global/source/cycle ScrapeOps reservations are atomic, kill-switch-aware,
  reconciled, bounded, and idempotent under duplicate callbacks.
- Replayed observations do not duplicate postings, versions, or usage rows.
- Stable external IDs, URL aliases, reposts, duplicate relationships, and
  source-specific missing-job grace periods are correct.
- Canonical repository queries never expose raw private/provider data and only
  return active/fresh or explicitly stale-safe postings.
- User A cannot read or mutate User B's preferences, evaluations,
  dispositions, or reports; canonical postings remain shared.
- No user/frontend route can enqueue catalog acquisition or mutate source
  policy; worker/admin scopes are enforced and audited.
- Deterministic filters precede expensive evaluation; evaluator/version cache
  invalidation is correct; absent scores remain absent.
- API pagination, empty, partial, stale, and failure contracts are stable.
- Synthetic mode remains fixture-only; real mode has no fixture leakage and no
  local disposition leakage.
- Onboarding saves preferences, waits for feed readiness, and does not start a
  run; Jobs filters/pagination never start acquisition; Hidden Jobs uses the
  disposition API; report is persisted.
- Existing workspace runs, quick apply, worker processing, and document flows
  retain their current tests and behavior unless deliberately restricted by
  the trust-boundary change.

Per repository instructions, Python tests may only run after verifying
`.venv\Scripts\python.exe --version` reports Python 3.12.7. This report does
not run tests because it changes documentation only.

## Expected implementation order

The implementation should follow the requested tracer-bullet order. Each step
must leave the preceding boundary and tests intact:

1. Audit and execution-path tracing (this document).
2. Close or restrict user-triggerable acquisition paths.
3. Integrate the system-owned scheduler.
4. Add the shared durable canonical repository and lifecycle gaps.
5. Put one approved existing source through the scheduled pipeline.
6. Add canonicalization, versioning, and idempotent upserts.
7. Add operational ScrapeOps enforcement and monitoring.
8. Add the shared Jobs read API.
9. Add preferences and deterministic filtering.
10. Add persistent user dispositions and reports.
11. Add eligibility evaluation.
12. Add cached match evaluation.
13. Integrate onboarding to the feed without acquisition.
14. Integrate Jobs and Hidden Jobs with real data.
15. Add additional approved existing job sources.
16. Run end-to-end, security, failure, and recovery verification.
17. Roll out behind the existing feature flag, with synthetic mode remaining
    the default until freshness and cost objectives are met.

## Migration and rollout order

1. Land the route/security audit and explicit internal acquisition boundary.
2. Add migrations/repositories for cycle state, observations, canonical
   postings, versions, lifecycle, preferences, evaluations, and dispositions.
3. Add the system principal, `SystemAcquisitionScheduler`, and cycle/source
   claims while keeping real acquisition disabled.
4. Add reservation/reconciliation/kill-switch governance and admin metrics.
5. Run one approved source through the scheduler into the shared repository.
6. Verify canonicalization, lifecycle, stale snapshot, and recovery behavior.
7. Add the shared read API, preferences, deterministic filters, dispositions,
   eligibility, and cached matching in independent vertical slices.
8. Add the real frontend provider and onboarding integration behind the existing
   data-mode flag; retain synthetic mode as the default.
9. Add further approved sources one at a time after operational validation.
10. Run end-to-end security/failure tests, then controlled rollout and monitor
    freshness, source success, duplicate rate, and provider usage.

## Expected files to change during implementation

This list is a plan, not a claim that these files were changed in this audit.

- `backend/application/acquisition_scheduler.py`: global 24-hour cycle claim
  and system-run enqueueing.
- `backend/application/run_services.py`, `backend/application/services.py`,
  `backend/domain/models.py`: system run kind/principal and lifecycle seam.
- `backend/worker/service.py`: scheduler invocation and heartbeat.
- `backend/repositories/contracts.py`, `sqlite_migrations.py`,
  `sqlite_backed.py`: cycle, catalog, observation, evaluation, preference,
  disposition, reservation, and metrics persistence.
- `backend/domain/personalized_jobs_contracts.py` and
  `backend/domain/job_identity.py`: lifecycle/version/identity extensions.
- `backend/acquisition/*` or equivalent source adapter modules and
  `backend/adapters/stage_adapters.py`: server-controlled observation
  ingestion, source isolation, and canonical upsert calls.
- `backend/config/scrapeops_admin_policy.py` and
  `backend/integrations/scrapeops.py`: policy, reservation, kill switch, and
  usage idempotency.
- `backend/api/routes/__init__.py`, new `backend/api/routes/personalized_jobs.py`,
  and existing workspace/admin route modules: read API and trust restrictions.
- `frontend/src/lib/personalizedJobs.js` or a new provider module,
  `frontend/src/lib/personalizedPreviewState.js`,
  `frontend/src/components/personalized/JobsWorkspace.jsx`,
  `frontend/src/pages/HiddenJobsPage.jsx`, and
  `frontend/src/pages/PersonalizedOnboardingPage.jsx`: real provider,
  authenticated actions, and state handling.
- `docs/PERSONALIZED_JOBS_PREVIEW.md`,
  `docs/personalized_jobs_contracts.md`, and
  `docs/security/runr_data_ownership.md`: update preview status, persistence
  ownership, and system-run boundary once implementation lands.

## Unresolved Runr-team decisions

1. Should the system-owned acquisition run reuse the existing `RunRecord` with
   a reserved internal workspace/run kind, or should cycle execution have a
   separate internal record that delegates only to the worker lifecycle?
2. Which initial sources are approved for unattended daily acquisition, given
   source terms, health, coverage, and ScrapeOps cost—especially LinkedIn?
3. What freshness SLA and source-specific missing-job grace period should be
   used for each source?
4. What is the required alert destination beyond the existing in-app admin
   event stream (email, Slack, PagerDuty, or another Runr-owned channel)?
5. What global/cycle/source ScrapeOps ceiling and kill-switch owner should be
   configured for production?
6. Should “save search” remain a preference mutation, or should it be removed
   until multiple saved preference sets are supported?

Implementation should begin only after this audit and the above boundary/
source decisions are reviewed. No code implementation was performed as part
of this plan update.
